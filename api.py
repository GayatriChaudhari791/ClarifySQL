
import json
import re
import sqlite3
import uuid
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


app = FastAPI(title="ClarifySQL API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).parent / "frontend"
if FRONTEND_DIR.is_dir():
    app.mount("/frontend", StaticFiles(directory=FRONTEND_DIR), name="frontend")

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "qwen2.5:3b"
MAX_FILE_SIZE = 20 * 1024 * 1024
MAX_ROWS = 100_000
MAX_RESULT_ROWS = 500

DATA_DIR = Path(__file__).parent / "uploaded_data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

CONVERSATIONS_DB_DIR = Path(__file__).parent / "data"
CONVERSATIONS_DB_DIR.mkdir(parents=True, exist_ok=True)
CONVERSATIONS_DB_PATH = CONVERSATIONS_DB_DIR / "conversations.db"


def get_conversations_db():
    conn = sqlite3.connect(str(CONVERSATIONS_DB_PATH), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_conversations_db():
    CONVERSATIONS_DB_DIR.mkdir(parents=True, exist_ok=True)
    with get_conversations_db() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                dataset_id TEXT,
                dataset_name TEXT,
                is_pinned INTEGER NOT NULL DEFAULT 0,
                is_custom_title INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                sql TEXT,
                columns_json TEXT,
                rows_json TEXT,
                chart TEXT,
                is_error INTEGER NOT NULL DEFAULT 0,
                dataset_id TEXT,
                dataset_name TEXT,
                clarification_options_json TEXT,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_messages_conv_id ON messages(conversation_id, id);
            CREATE INDEX IF NOT EXISTS idx_conversations_updated ON conversations(updated_at DESC);
        ''')
        cols = [r[1] for r in conn.execute('PRAGMA table_info("messages")').fetchall()]
        if "clarification_options_json" not in cols:
            conn.execute('ALTER TABLE messages ADD COLUMN clarification_options_json TEXT')

        conv_cols = [r[1] for r in conn.execute('PRAGMA table_info("conversations")').fetchall()]
        if "is_pinned" not in conv_cols:
            conn.execute('ALTER TABLE conversations ADD COLUMN is_pinned INTEGER NOT NULL DEFAULT 0')
        if "is_custom_title" not in conv_cols:
            conn.execute('ALTER TABLE conversations ADD COLUMN is_custom_title INTEGER NOT NULL DEFAULT 0')

        conn.execute('CREATE INDEX IF NOT EXISTS idx_conversations_pinned_updated ON conversations(is_pinned DESC, updated_at DESC)')


init_conversations_db()


def validate_id(identifier: str, name: str = "ID") -> str:
    if not identifier or not re.fullmatch(r"[a-f0-9]{32}", identifier):
        raise HTTPException(status_code=400, detail=f"Invalid {name}.")
    return identifier


def get_dataset_info_if_available(dataset_id: Optional[str]):
    if not dataset_id or not re.fullmatch(r"[a-f0-9]{32}", dataset_id):
        return False, None
    folder = DATA_DIR / dataset_id
    db_path = folder / "dataset.sqlite"
    if not db_path.is_file():
        return False, None
    try:
        uri = db_path.resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=10) as connection:
            info = connection.execute('PRAGMA table_info("uploaded_data")').fetchall()
            columns = [item[1] for item in info]
            row_count = connection.execute('SELECT COUNT(*) FROM "uploaded_data"').fetchone()[0]
            sample_rows = connection.execute('SELECT * FROM "uploaded_data" LIMIT 5').fetchall()
            preview = [list(row) for row in sample_rows]
            return True, {
                "columns": columns,
                "row_count": row_count,
                "preview": preview,
            }
    except Exception as e:
        print(f"Error inspecting dataset {dataset_id}: {e}")
        return False, None


class QueryRequest(BaseModel):
    dataset_id: str
    question: str
    conversation_id: Optional[str] = None
    original_question: Optional[str] = None
    selected_option_id: Optional[str] = None
    selected_option_label: Optional[str] = None


class CreateConversationRequest(BaseModel):
    title: Optional[str] = None
    dataset_id: Optional[str] = None
    dataset_name: Optional[str] = None
    is_pinned: Optional[bool] = None


class UpdateConversationRequest(BaseModel):
    title: Optional[str] = None
    dataset_id: Optional[str] = None
    dataset_name: Optional[str] = None
    is_pinned: Optional[bool] = None


class AddMessageRequest(BaseModel):
    role: str
    content: str
    sql: Optional[str] = None
    columns: Optional[List[str]] = None
    rows: Optional[List[List[Any]]] = None
    chart: Optional[str] = None
    is_error: Optional[bool] = False
    dataset_id: Optional[str] = None
    dataset_name: Optional[str] = None
    clarification_options: Optional[List[Any]] = None


def get_dataset_paths(dataset_id: str):
    if not re.fullmatch(r"[a-f0-9]{32}", dataset_id):
        raise HTTPException(status_code=400, detail="Invalid dataset ID.")

    folder = DATA_DIR / dataset_id
    db_path = folder / "dataset.sqlite"

    if not db_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Dataset not found. Please upload your file again.",
        )

    return folder, db_path


def quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def read_uploaded_file(filename: str, content: bytes) -> pd.DataFrame:
    extension = Path(filename).suffix.lower()

    try:
        if extension == ".csv":
            from io import BytesIO

            try:
                frame = pd.read_csv(BytesIO(content), encoding="utf-8-sig")
            except UnicodeDecodeError:
                frame = pd.read_csv(BytesIO(content), encoding="latin-1")

        elif extension in {".xlsx", ".xls"}:
            from io import BytesIO

            frame = pd.read_excel(BytesIO(content))

        else:
            raise HTTPException(
                status_code=400,
                detail="Unsupported file type. Upload a CSV or Excel file.",
            )

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=400,
            detail=f"Could not read the file: {error}",
        ) from error

    if frame.empty or len(frame.columns) == 0:
        raise HTTPException(
            status_code=400,
            detail="The uploaded file contains no usable data.",
        )

    if len(frame) > MAX_ROWS:
        raise HTTPException(
            status_code=400,
            detail=f"This prototype supports up to {MAX_ROWS:,} rows per file.",
        )

    if len(frame.columns) > 200:
        raise HTTPException(
            status_code=400,
            detail="This prototype supports up to 200 columns per file.",
        )

    if any(not str(column).strip() for column in frame.columns):
        raise HTTPException(
            status_code=400,
            detail="Every column must have a name. Please fix the file and upload it again.",
        )

    frame.columns = [str(column).strip() for column in frame.columns]

    if len(set(frame.columns)) != len(frame.columns):
        raise HTTPException(
            status_code=400,
            detail="The file contains duplicate column names. Please make them unique and upload again.",
        )

    return frame


def dataframe_to_json_rows(frame: pd.DataFrame):
    clean = frame.astype(object).where(pd.notna(frame), None)
    return clean.values.tolist()


def call_ollama(prompt: str, timeout: int = 180) -> str:
    payload = {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0},
    }

    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))

        text = result.get("message", {}).get("content", "").strip()

        if not text:
            raise RuntimeError("Ollama returned an empty response.")

        return text

    except urllib.error.URLError as error:
        raise RuntimeError(
            "Cannot connect to Ollama. Open Ollama and check that "
            f"the {MODEL_NAME} model is available."
        ) from error


def get_schema(frame: pd.DataFrame) -> str:
    lines = [
        'The uploaded dataset is stored in one SQLite table named "uploaded_data".',
        "Use only this table and the listed column names.",
        "Quote column identifiers with double quotes, especially when names contain spaces or punctuation.",
        "",
        "TABLE: uploaded_data",
    ]

    for column, dtype in frame.dtypes.items():
        examples = frame[column].dropna().head(3).tolist()
        example_text = ", ".join(str(value)[:80] for value in examples)
        lines.append(
            f'- "{column}" | inferred type: {dtype} | sample values: {example_text or "none"}'
        )

    lines.extend(
        [
            "",
            f"Approximate row count: {len(frame)}",
            "",
            "Use SQLite syntax. Do not assume relationships with other tables.",
        ]
    )

    return "\n".join(lines)


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower()).strip("_")
    return slug[:40] or "option"


def clean_clarification_text(clarification: str, question: Optional[str] = None) -> str:
    cleaned = clarification.strip()
    if not question:
        return cleaned

    # Strip leading echo of the question if model repeated it
    # E.g. 'Give me a breakdown of sellers. How would you like to group the sellers?'
    # -> 'How would you like to group the sellers?'
    q_clean = question.strip().rstrip("?.!").strip()
    pattern = r'^(?:(?:regarding|about|for)\s+[\"\'\`]?' + re.escape(q_clean) + r'[\"\'\`]?[,:\s-]*|' + re.escape(q_clean) + r'[\"\'\`]?[.?!:\s-]+)\s*'
    stripped = re.sub(pattern, '', cleaned, flags=re.IGNORECASE).strip()
    if stripped:
        cleaned = stripped[0].upper() + stripped[1:] if len(stripped) > 1 else stripped.upper()
    return cleaned


def parse_ambiguity_response(text: str, question: Optional[str] = None) -> dict:
    clarify_match = re.search(r"CLARIFY:\s*(.*?)(?=\n\s*(?:OPTIONS:?|[-*•\d]\s)|\Z)", text, flags=re.DOTALL | re.IGNORECASE)
    options_match = re.search(r"OPTIONS:\s*(.*)", text, flags=re.DOTALL | re.IGNORECASE)

    if clarify_match:
        clarification_text = clarify_match.group(1).strip()
        if question:
            clarification_text = clean_clarification_text(clarification_text, question)

        raw_options = []
        if options_match:
            raw_options = options_match.group(1).strip().splitlines()
        else:
            after_clarify = text[clarify_match.end():]
            for line in after_clarify.splitlines():
                if re.match(r"^\s*[-*•\d\.\)]\s+", line):
                    raw_options.append(line)

        options = []
        for line in raw_options:
            cleaned = re.sub(r"^[\s*\-•\d\.\)]+\s*", "", line).strip()
            if cleaned and not cleaned.lower().startswith("sql:"):
                options.append({
                    "id": slugify(cleaned),
                    "label": cleaned
                })
        return {
            "is_clarification": True,
            "clarification": clarification_text,
            "options": options[:4]
        }

    # If not a clarification, treat as SQL
    sql = text
    sql = re.sub(r"^\s*```(?:sql)?\s*", "", sql, flags=re.IGNORECASE | re.MULTILINE)
    sql = re.sub(r"\s*```\s*$", "", sql, flags=re.MULTILINE).strip()
    sql = re.sub(r"^\s*SQL:\s*", "", sql, flags=re.IGNORECASE).strip()
    return {
        "is_clarification": False,
        "sql": sql
    }


def ground_options_in_schema(ambig_result: dict, question: str, columns: List[str]) -> dict:
    if not columns:
        return ambig_result

    lower_cols = [c.lower() for c in columns]

    metric_terms = [
        'price', 'sale', 'sales', 'rev', 'revenue', 'pay', 'payment', 'order',
        'orders', 'amount', 'total', 'quant', 'quantity', 'score', 'rate',
        'rating', 'value', 'cost', 'profit', 'margin', 'units', 'sold'
    ]
    has_performance = any(any(t in col for t in metric_terms) for col in lower_cols)

    is_ranking_question = any(term in question.lower() for term in [
        'best', 'top', 'rank', 'performer', 'performance', 'highest revenue',
        'most sales', 'highest sales', 'most popular', 'worst', 'lowest'
    ])

    if not has_performance and is_ranking_question:
        def col_rank(c: str) -> int:
            cl = c.lower()
            if 'state' in cl:
                return 0
            if 'city' in cl:
                return 1
            if 'type' in cl or 'cat' in cl or 'status' in cl:
                return 2
            if 'zip' in cl:
                return 3
            return 4

        sorted_cols = sorted(columns, key=col_rank)
        alt_options = []
        for col in sorted_cols:
            c_low = col.lower()
            if 'id' in c_low and not any(k in c_low for k in ['category', 'type']):
                continue
            clean_name = col.replace('_', ' ').strip()
            entity_prefix = "Group sellers by" if "seller" in question.lower() else ("Group customers by" if "customer" in question.lower() else "Group by")
            alt_options.append({
                "id": slugify(f"group_by_{col}"),
                "label": f"{entity_prefix} {clean_name}"
            })
            if len(alt_options) >= 3:
                break

        if not alt_options:
            alt_options = [
                {"id": "preview_records", "label": "Show first records"},
                {"id": "count_total", "label": "Total count of records"}
            ]

        entity = "sellers" if "seller" in question.lower() else ("customers" if "customer" in question.lower() else "records")
        return {
            "is_clarification": True,
            "clarification": f"This dataset does not contain sales, order, or revenue columns to evaluate {entity} performance. Would you like to explore {entity} by their available attributes instead?",
            "options": alt_options
        }

    if ambig_result.get("is_clarification"):
        valid_options = []
        for opt in ambig_result.get("options", []):
            label_low = opt["label"].lower()
            if 'order' in label_low and not any('order' in c for c in lower_cols):
                continue
            if any(term in label_low for term in ['sale', 'revenue', 'rev']) and not any(k in c for k in ['sale', 'rev', 'price', 'amount', 'val', 'total'] for c in lower_cols):
                continue
            if 'price' in label_low and not any(k in c for k in ['price', 'cost', 'val', 'amount'] for c in lower_cols):
                continue
            valid_options.append(opt)

        if len(valid_options) < 2:
            for col in columns:
                c_low = col.lower()
                if 'id' in c_low and not any(k in c_low for k in ['category', 'type']):
                    continue
                clean_name = col.replace('_', ' ').strip()
                entity_prefix = "Group sellers by" if "seller" in question.lower() else ("Group customers by" if "customer" in question.lower() else "Group by")
                new_opt = {
                    "id": slugify(f"group_by_{col}"),
                    "label": f"{entity_prefix} {clean_name}"
                }
                if not any(o["id"] == new_opt["id"] or o["label"].lower() == new_opt["label"].lower() for o in valid_options):
                    valid_options.append(new_opt)
                if len(valid_options) >= 3:
                    break

        if len(valid_options) >= 2:
            return {
                "is_clarification": True,
                "clarification": ambig_result.get("clarification"),
                "options": valid_options[:4]
            }

    return ambig_result


def generate_sql_or_clarification(question: str, schema: str, columns: Optional[List[str]] = None) -> dict:
    preview_match = re.match(
        r"^\s*(?:show|display|get|select|preview)?\s*(?:me\s*)?(?:the\s*)?first\s+(\d+)\s*(?:rows?|records?|items?)\s*\.?\s*$",
        question.strip(),
        re.IGNORECASE,
    )
    if preview_match:
        limit_val = int(preview_match.group(1))
        return {
            "is_clarification": False,
            "sql": f'SELECT * FROM "uploaded_data" LIMIT {limit_val}',
        }

    prompt = f"""
You are ClarifySQL, an expert natural-language-to-SQL assistant.

Your task is to analyze the user's question against the dataset schema and:
1. If the question has a clear, specific meaning, generate exactly one valid SQLite SELECT query.
2. If the question is ambiguous (meaning it uses subjective or underspecified terms like "best", "top", "performance", "location", "distribution", "status"):
   - Propose options ONLY for metrics and columns that actually exist in the schema.
   - If performance metrics (sales, revenue, orders) DO NOT exist in the schema, do not propose them. Offer options based on available columns instead.
   - Format:
CLARIFY: <Clarification question>
OPTIONS:
- <Option 1 label>
- <Option 2 label>
- <Option 3 label>
3. If the question genuinely cannot be answered using the available columns, return INVALID.

DATASET SCHEMA:
{schema}

RULES FOR SQL GENERATION:
- Return only the SQL query if clear. Do not use Markdown fences.
- Query only the table "uploaded_data".
- Use only the columns listed in the schema.
- Quote column names using double quotes.
- Use SQLite-compatible SQL.
- Generate one read-only SELECT statement only.
- Do not use INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, PRAGMA,
  ATTACH, DETACH, REPLACE, or multiple statements.
- Never invent columns, tables, values, or relationships.
- Return INVALID only if the question genuinely cannot be answered
  using the available columns.
- Do not return INVALID merely because a question requires calculations,
  aggregation, grouping, sorting, filtering, or percentages.
- For requests involving percentages, calculate the percentage as
  (numerator * 100.0 / denominator).
- Use a subquery to calculate the total when the denominator requires
  the total number of rows in the dataset.
- Use GROUP BY when the user asks for results by category or entity.
- Use COUNT(*) when counting rows.
- Use COUNT(DISTINCT column) when counting unique values.
- Use SUM, AVG, MIN, and MAX when appropriate for the available data.
- For top-N questions, use ORDER BY and LIMIT.
- For general requests to inspect, preview, or show rows or records, SELECT * is allowed with LIMIT.
- If the user asks a question about a column that does not exist,
  return INVALID.
- For questions asking for the percentage distribution across states,
  cities, or another available categorical column, calculate the count
  for each category and divide it by the total number of rows.
- Do not assume that a question is impossible merely because it requires
  more than one SQL operation.

RULES FOR CLARIFICATION:
- Use CLARIFY when a question is ambiguous, underspecified, or has multiple plausible interpretations based on the schema columns.
- Under CLARIFY, write ONLY the direct clarification question (e.g. "How would you like to group sellers?"). NEVER echo, prefix, or repeat the user's original question.
- Never invent columns or metrics that are absent from the schema.
- Provide 2 to 4 realistic options that directly correspond to available columns in the schema.
- Format:
CLARIFY: <Clarification question>
OPTIONS:
- <Option 1 label>
- <Option 2 label>
- <Option 3 label>

EXAMPLES:

Question: Show me the first 5 rows
SQL:
SELECT * FROM "uploaded_data" LIMIT 5

Question: What percentage of sellers belong to each state?
SQL:
SELECT
    "seller_state",
    COUNT(*) AS seller_count,
    ROUND(
        COUNT(*) * 100.0 /
        (SELECT COUNT(*) FROM "uploaded_data"),
        2
    ) AS percentage
FROM "uploaded_data"
GROUP BY "seller_state"
ORDER BY percentage DESC

Question: Which state has the most sellers?
SQL:
SELECT
    "seller_state",
    COUNT(*) AS seller_count
FROM "uploaded_data"
GROUP BY "seller_state"
ORDER BY seller_count DESC
LIMIT 1

Question: Where are most sellers located?
CLARIFY: How would you like to group sellers by location?
OPTIONS:
- Group by state
- Group by city
- Group by zip code prefix

Question: Give me a breakdown of sellers.
CLARIFY: How would you like to group the sellers?
OPTIONS:
- Group by state
- Group by city
- Group by zip code prefix

Question: Which are the best customers?
CLARIFY: How would you like to define best customers?
OPTIONS:
- Highest total payment value
- Most orders placed
- Highest average order value

Question: What is the total revenue?
SQL:
INVALID

USER QUESTION:
{question}
"""
    answer = call_ollama(prompt)
    raw_res = parse_ambiguity_response(answer, question)
    if columns:
        return ground_options_in_schema(raw_res, question, columns)
    return raw_res


def generate_resolved_sql(original_question: str, selected_option: str, schema: str) -> str:
    prompt = f"""
You are ClarifySQL, an expert natural-language-to-SQL assistant.

The user originally asked an ambiguous question: "{original_question}"
The user has now clarified their intent: "{selected_option}"

Generate exactly one valid SQLite SELECT query that answers the user's clarified intent.
Do not ask for clarification. Return only the SQL query.

DATASET SCHEMA:
{schema}

RULES:
- Return only the SQL query. Do not use Markdown fences.
- Query only the table "uploaded_data".
- Use only the columns listed in the schema.
- Quote column names using double quotes.
- Use SQLite-compatible SQL.
- Generate one read-only SELECT statement only.
- Do not use INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, PRAGMA,
  ATTACH, DETACH, REPLACE, or multiple statements.
- Never invent columns, tables, values, or relationships.
- Return INVALID only if the question genuinely cannot be answered
  using the available columns.
- Use GROUP BY when grouping or aggregating by category or entity.
- Use SUM, AVG, MIN, MAX, and COUNT as appropriate.
- For grouping or ranking questions, order by the aggregated count descending. If grouping by high-cardinality attributes like zip codes or when exploring top entities, use LIMIT 20 to avoid exceeding result limits.

EXAMPLES:

Question: Show me the first 5 rows
SQL:
SELECT * FROM "uploaded_data" LIMIT 5

Question: Which state has the most sellers?
SQL:
SELECT
    "seller_state",
    COUNT(*) AS seller_count
FROM "uploaded_data"
GROUP BY "seller_state"
ORDER BY seller_count DESC
LIMIT 1

Question: Group sellers by seller state
SQL:
SELECT
    "seller_state",
    COUNT(*) AS seller_count
FROM "uploaded_data"
GROUP BY "seller_state"
ORDER BY seller_count DESC

USER CLARIFIED INTENT:
Original question: {original_question}
User clarified choice: {selected_option}

SQL:
"""
    answer = call_ollama(prompt)
    answer = re.sub(
        r"^\s*```(?:sql)?\s*",
        "",
        answer,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    answer = re.sub(r"\s*```\s*$", "", answer, flags=re.MULTILINE).strip()
    answer = re.sub(r"^\s*SQL:\s*", "", answer, flags=re.IGNORECASE).strip()
    return answer


def generate_sql(question: str, schema: str) -> str:
    res = generate_sql_or_clarification(question, schema)
    if res.get("is_clarification"):
        return "INVALID"
    return res.get("sql", "INVALID")

def validate_sql(query: str) -> str:
    query = query.strip()

    if query.upper() == "INVALID":
        raise ValueError(
            "This question cannot be answered using the uploaded dataset. "
            "Try asking about its available columns."
        )

    if query.endswith(";"):
        query = query[:-1].strip()

    if not query:
        raise ValueError("The AI returned an empty SQL query.")

    if ";" in query:
        raise ValueError("Multiple SQL statements are not allowed.")

    if not re.match(r"\ASELECT\b", query, flags=re.IGNORECASE):
        raise ValueError("Only SELECT queries are allowed.")

    if "--" in query or "/*" in query or "*/" in query:
        raise ValueError("SQL comments are not allowed.")

    if re.search(
        r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|ATTACH|"
        r"DETACH|PRAGMA|VACUUM|REINDEX|TRIGGER|VIEW|INDEX)\b",
        query,
        flags=re.IGNORECASE,
    ):
        raise ValueError("The generated query contains a restricted SQL keyword.")

    if not re.search(r"\buploaded_data\b", query, flags=re.IGNORECASE):
        raise ValueError('The query must use the "uploaded_data" table.')

    return query


def execute_readonly_query(db_path: Path, query: str):
    uri = db_path.resolve().as_uri() + "?mode=ro"

    with sqlite3.connect(uri, uri=True, timeout=15) as connection:
        connection.execute("PRAGMA query_only = ON")

        def authorize(action, arg1, arg2, database_name, trigger_name):
            if action == sqlite3.SQLITE_SELECT:
                return sqlite3.SQLITE_OK

            if action == sqlite3.SQLITE_READ:
                if arg1 == "uploaded_data":
                    return sqlite3.SQLITE_OK
                return sqlite3.SQLITE_DENY

            if action == sqlite3.SQLITE_FUNCTION:
                function_name = (arg2 or arg1 or "").lower()

                if function_name in {
                    "load_extension",
                    "writefile",
                    "readfile",
                }:
                    return sqlite3.SQLITE_DENY

                return sqlite3.SQLITE_OK

            return sqlite3.SQLITE_DENY

        connection.set_authorizer(authorize)
        cursor = connection.execute(query)

        if cursor.description is None:
            raise ValueError("The query did not return tabular results.")

        columns = [item[0] for item in cursor.description]
        rows = cursor.fetchmany(MAX_RESULT_ROWS + 1)

        if len(rows) > MAX_RESULT_ROWS:
            raise ValueError(
                f"The query returned more than {MAX_RESULT_ROWS} rows. "
                "Please narrow your question."
            )

        return columns, [list(row) for row in rows]


def explain_results(question: str, sql: str, columns: list, rows: list) -> str:
    if not rows:
        return "The query completed successfully, but no matching records were found."

    sample = [
        dict(zip(columns, row))
        for row in rows[:10]
    ]

    prompt = f"""
You are ClarifySQL, a professional data analytics assistant.

Answer the user's question using only the query results below.
Explain important values and patterns in clear, concise English.
Do not invent causes, statistics, or facts not supported by these results.
If the results are limited, say so.
Do not generate another SQL query.

USER QUESTION:
{question}

SQL EXECUTED:
{sql}

RESULT SAMPLE:
{json.dumps(sample, default=str)}

Write a short explanation of what the results show.
"""

    try:
        return call_ollama(prompt, timeout=180)
    except Exception:
        return "The query succeeded. Review the result table above; an AI explanation could not be generated."


@app.get("/")
def root():
    return {
        "message": "ClarifySQL API is running.",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/conversations")
def list_conversations():
    with get_conversations_db() as conn:
        rows = conn.execute("""
            SELECT 
                c.id, c.title, c.created_at, c.updated_at, c.dataset_id, c.dataset_name,
                c.is_pinned, c.is_custom_title,
                COUNT(m.id) AS message_count
            FROM conversations c
            LEFT JOIN messages m ON c.id = m.conversation_id
            GROUP BY c.id
            ORDER BY c.is_pinned DESC, c.updated_at DESC
        """).fetchall()
        return [
            {
                "id": r["id"],
                "title": r["title"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
                "dataset_id": r["dataset_id"],
                "dataset_name": r["dataset_name"],
                "is_pinned": bool(r["is_pinned"]),
                "is_custom_title": bool(r["is_custom_title"]),
                "message_count": r["message_count"],
            }
            for r in rows
        ]


@app.post("/conversations")
def create_conversation(request: Optional[CreateConversationRequest] = None):
    conv_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    has_custom_title = bool(request and request.title and request.title.strip())
    title = (request.title.strip() if request and request.title else "") or "New conversation"
    dataset_id = request.dataset_id if request else None
    dataset_name = request.dataset_name if request else None
    is_pinned = 1 if (request and request.is_pinned) else 0
    is_custom_title = 1 if has_custom_title else 0

    if dataset_id:
        validate_id(dataset_id, "dataset ID")

    with get_conversations_db() as conn:
        conn.execute(
            """
            INSERT INTO conversations (id, title, created_at, updated_at, dataset_id, dataset_name, is_pinned, is_custom_title)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (conv_id, title, now, now, dataset_id, dataset_name, is_pinned, is_custom_title),
        )

    return {
        "id": conv_id,
        "title": title,
        "created_at": now,
        "updated_at": now,
        "dataset_id": dataset_id,
        "dataset_name": dataset_name,
        "is_pinned": bool(is_pinned),
        "is_custom_title": bool(is_custom_title),
        "messages": [],
    }


@app.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str):
    validate_id(conversation_id, "conversation ID")
    with get_conversations_db() as conn:
        conv = conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found.")

        msg_rows = conn.execute(
            """
            SELECT id, role, content, created_at, sql, columns_json, rows_json, chart, is_error, dataset_id, dataset_name, clarification_options_json
            FROM messages
            WHERE conversation_id = ?
            ORDER BY id ASC
            """,
            (conversation_id,),
        ).fetchall()

    messages_list = []
    for m in msg_rows:
        messages_list.append({
            "id": m["id"],
            "role": m["role"],
            "content": m["content"],
            "created_at": m["created_at"],
            "sql": m["sql"],
            "columns": json.loads(m["columns_json"]) if m["columns_json"] else None,
            "rows": json.loads(m["rows_json"]) if m["rows_json"] else None,
            "chart": m["chart"],
            "is_error": bool(m["is_error"]),
            "dataset_id": m["dataset_id"],
            "dataset_name": m["dataset_name"],
            "clarification_options": json.loads(m["clarification_options_json"]) if m["clarification_options_json"] else None,
        })

    dataset_available, dataset_info = get_dataset_info_if_available(conv["dataset_id"])

    return {
        "id": conv["id"],
        "title": conv["title"],
        "created_at": conv["created_at"],
        "updated_at": conv["updated_at"],
        "dataset_id": conv["dataset_id"],
        "dataset_name": conv["dataset_name"],
        "is_pinned": bool(conv["is_pinned"]),
        "is_custom_title": bool(conv["is_custom_title"]),
        "dataset_available": dataset_available,
        "dataset_info": dataset_info,
        "messages": messages_list,
    }


@app.post("/conversations/{conversation_id}/messages")
def add_message(conversation_id: str, request: AddMessageRequest):
    validate_id(conversation_id, "conversation ID")
    now = datetime.now(timezone.utc).isoformat()

    with get_conversations_db() as conn:
        conv = conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found.")

        new_title = conv["title"]
        if not conv["is_custom_title"] and conv["title"] in ("New conversation", "") and request.role == "user" and request.content.strip():
            clean = request.content.strip()
            new_title = clean[:50] + ("..." if len(clean) > 50 else "")

        cursor = conn.execute(
            """
            INSERT INTO messages (
                conversation_id, role, content, created_at, sql, columns_json, rows_json, chart, is_error, dataset_id, dataset_name, clarification_options_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conversation_id,
                request.role,
                request.content,
                now,
                request.sql,
                json.dumps(request.columns) if request.columns is not None else None,
                json.dumps(request.rows) if request.rows is not None else None,
                request.chart,
                1 if request.is_error else 0,
                request.dataset_id or conv["dataset_id"],
                request.dataset_name or conv["dataset_name"],
                json.dumps(request.clarification_options) if request.clarification_options is not None else None,
            ),
        )
        msg_id = cursor.lastrowid

        conn.execute(
            """
            UPDATE conversations 
            SET updated_at = ?, title = ?,
                dataset_id = COALESCE(?, dataset_id),
                dataset_name = COALESCE(?, dataset_name)
            WHERE id = ?
            """,
            (now, new_title, request.dataset_id, request.dataset_name, conversation_id),
        )

    return {
        "id": msg_id,
        "conversation_id": conversation_id,
        "role": request.role,
        "content": request.content,
        "created_at": now,
        "sql": request.sql,
        "columns": request.columns,
        "rows": request.rows,
        "chart": request.chart,
        "is_error": request.is_error,
        "dataset_id": request.dataset_id or conv["dataset_id"],
        "dataset_name": request.dataset_name or conv["dataset_name"],
        "clarification_options": request.clarification_options,
    }


@app.patch("/conversations/{conversation_id}")
def update_conversation(conversation_id: str, request: UpdateConversationRequest):
    validate_id(conversation_id, "conversation ID")
    now = datetime.now(timezone.utc).isoformat()
    with get_conversations_db() as conn:
        conv = conn.execute(
            "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found.")

        title = request.title.strip() if request.title is not None else conv["title"]
        dataset_id = request.dataset_id if request.dataset_id is not None else conv["dataset_id"]
        dataset_name = request.dataset_name if request.dataset_name is not None else conv["dataset_name"]
        is_pinned = (1 if request.is_pinned else 0) if request.is_pinned is not None else conv["is_pinned"]

        is_custom_title = conv["is_custom_title"]
        if request.title is not None and request.title.strip():
            is_custom_title = 1

        conn.execute(
            """
            UPDATE conversations
            SET title = ?, dataset_id = ?, dataset_name = ?, is_pinned = ?, is_custom_title = ?, updated_at = ?
            WHERE id = ?
            """,
            (title, dataset_id, dataset_name, is_pinned, is_custom_title, now, conversation_id),
        )

    return {
        "id": conversation_id,
        "title": title,
        "dataset_id": dataset_id,
        "dataset_name": dataset_name,
        "is_pinned": bool(is_pinned),
        "is_custom_title": bool(is_custom_title),
        "updated_at": now,
    }


@app.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str):
    validate_id(conversation_id, "conversation ID")
    with get_conversations_db() as conn:
        conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
        cursor = conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Conversation not found.")

    return {"status": "deleted", "id": conversation_id}


@app.post("/upload")
async def upload_dataset(
    file: UploadFile = File(...),
    conversation_id: Optional[str] = Form(None),
):
    filename = Path(file.filename or "dataset.csv").name

    if Path(filename).suffix.lower() not in {".csv", ".xlsx", ".xls"}:
        raise HTTPException(
            status_code=400,
            detail="Please upload a CSV or Excel file.",
        )

    content = await file.read(MAX_FILE_SIZE + 1)

    if not content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="The file exceeds the 20 MB upload limit.",
        )

    frame = read_uploaded_file(filename, content)
    dataset_id = uuid.uuid4().hex
    folder = DATA_DIR / dataset_id
    folder.mkdir(parents=True, exist_ok=False)
    db_path = folder / "dataset.sqlite"

    try:
        frame.to_sql(
            "uploaded_data",
            sqlite3.connect(db_path),
            if_exists="replace",
            index=False,
        )
    except Exception as error:
        raise HTTPException(
            status_code=400,
            detail=f"Could not prepare the dataset: {error}",
        ) from error

    if conversation_id:
        validate_id(conversation_id, "conversation ID")
        now = datetime.now(timezone.utc).isoformat()
        with get_conversations_db() as conn:
            conn.execute(
                """
                UPDATE conversations
                SET dataset_id = ?, dataset_name = ?, updated_at = ?
                WHERE id = ?
                """,
                (dataset_id, filename, now, conversation_id),
            )

    return {
        "dataset_id": dataset_id,
        "filename": filename,
        "row_count": len(frame),
        "columns": list(frame.columns),
        "preview": dataframe_to_json_rows(frame.head(5)),
        "schema": get_schema(frame),
        "conversation_id": conversation_id,
    }


@app.post("/query")
def query_dataset(request: QueryRequest):
    question = request.question.strip()
    orig_q = (request.original_question or "").strip()
    selected_opt_label = (request.selected_option_label or question).strip()
    print(f"QUERY RECEIVED: {question!r} (orig: {orig_q!r}) on dataset {request.dataset_id!r}")

    if not question:
        raise HTTPException(status_code=400, detail="Please enter a question.")

    if len(question) > 2000:
        raise HTTPException(
            status_code=400,
            detail="Please keep your question under 2,000 characters.",
        )

    conv_id = request.conversation_id
    if conv_id:
        validate_id(conv_id, "conversation ID")
        now = datetime.now(timezone.utc).isoformat()
        with get_conversations_db() as conn:
            conv = conn.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)).fetchone()
            if not conv:
                raise HTTPException(status_code=404, detail="Conversation not found.")

            new_title = conv["title"]
            if not conv["is_custom_title"] and conv["title"] in ("New conversation", ""):
                clean_title = (orig_q or question)[:50] + ("..." if len(orig_q or question) > 50 else "")
                new_title = clean_title

            conn.execute(
                """
                INSERT INTO messages (conversation_id, role, content, created_at, dataset_id)
                VALUES (?, 'user', ?, ?, ?)
                """,
                (conv_id, selected_opt_label, now, request.dataset_id),
            )
            conn.execute(
                """
                UPDATE conversations
                SET updated_at = ?, title = ?, dataset_id = COALESCE(?, dataset_id)
                WHERE id = ?
                """,
                (now, new_title, request.dataset_id, conv_id),
            )

    _, db_path = get_dataset_paths(request.dataset_id)

    with sqlite3.connect(
        db_path.resolve().as_uri() + "?mode=ro",
        uri=True,
    ) as connection:
        info = connection.execute('PRAGMA table_info("uploaded_data")').fetchall()
        columns_in_dataset = [item[1] for item in info]
        row_count = connection.execute(
            'SELECT COUNT(*) FROM "uploaded_data"'
        ).fetchone()[0]
        sample_rows = connection.execute('SELECT * FROM "uploaded_data" LIMIT 3').fetchall()

    schema_lines = [
        'TABLE: "uploaded_data"',
        f"Row count: {row_count}",
        "Columns:",
    ]

    for idx, column in enumerate(columns_in_dataset):
        samples = [str(r[idx])[:40] for r in sample_rows if r[idx] is not None][:2]
        sample_str = f" | samples: {', '.join(samples)}" if samples else ""
        schema_lines.append(f'- "{column}"{sample_str}')

    schema = "\n".join(schema_lines)

    try:
        if orig_q:
            # Resolving an ambiguous question with user's selected/typed option
            generated_sql = generate_resolved_sql(orig_q, selected_opt_label, schema)
        else:
            ambig_res = generate_sql_or_clarification(question, schema, columns_in_dataset)
            if ambig_res.get("is_clarification"):
                clarification_text = ambig_res.get("clarification", "Could you please clarify your question?")
                options = ambig_res.get("options", [])

                if conv_id:
                    now = datetime.now(timezone.utc).isoformat()
                    with get_conversations_db() as conn:
                        conn.execute(
                            """
                            INSERT INTO messages (
                                conversation_id, role, content, created_at, clarification_options_json, dataset_id
                            ) VALUES (?, 'assistant', ?, ?, ?, ?)
                            """,
                            (
                                conv_id,
                                clarification_text,
                                now,
                                json.dumps(options),
                                request.dataset_id,
                            ),
                        )
                        conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conv_id))

                return {
                    "dataset_id": request.dataset_id,
                    "question": question,
                    "original_question": question,
                    "clarification": clarification_text,
                    "options": options,
                    "conversation_id": conv_id,
                }
            generated_sql = ambig_res.get("sql", "INVALID")

        validated_sql = validate_sql(generated_sql)
        result_columns, result_rows = execute_readonly_query(
            db_path,
            validated_sql,
        )
        context_q = f"{orig_q} ({selected_opt_label})" if orig_q else question
        explanation = explain_results(
            context_q,
            validated_sql,
            result_columns,
            result_rows,
        )

        if conv_id:
            now = datetime.now(timezone.utc).isoformat()
            with get_conversations_db() as conn:
                conn.execute(
                    """
                    INSERT INTO messages (
                        conversation_id, role, content, created_at, sql, columns_json, rows_json, chart, is_error, dataset_id
                    ) VALUES (?, 'assistant', ?, ?, ?, ?, ?, ?, 0, ?)
                    """,
                    (
                        conv_id,
                        explanation,
                        now,
                        validated_sql,
                        json.dumps(result_columns),
                        json.dumps(result_rows),
                        None,
                        request.dataset_id,
                    ),
                )
                conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conv_id))

    except RuntimeError as error:
        print(f"QUERY RUNTIME ERROR: {error}")
        if conv_id:
            now = datetime.now(timezone.utc).isoformat()
            with get_conversations_db() as conn:
                conn.execute(
                    """
                    INSERT INTO messages (conversation_id, role, content, created_at, is_error, dataset_id)
                    VALUES (?, 'assistant', ?, ?, 1, ?)
                    """,
                    (conv_id, str(error), now, request.dataset_id),
                )
                conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conv_id))
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ValueError as error:
        print(f"QUERY VALUE ERROR: {error} | Generated SQL: {locals().get('generated_sql')!r}")
        if conv_id:
            now = datetime.now(timezone.utc).isoformat()
            with get_conversations_db() as conn:
                conn.execute(
                    """
                    INSERT INTO messages (conversation_id, role, content, created_at, is_error, dataset_id)
                    VALUES (?, 'assistant', ?, ?, 1, ?)
                    """,
                    (conv_id, str(error), now, request.dataset_id),
                )
                conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conv_id))
        raise HTTPException(status_code=422, detail=str(error)) from error
    except sqlite3.Error as error:
        print(f"QUERY SQLITE ERROR: {error}")
        if conv_id:
            now = datetime.now(timezone.utc).isoformat()
            with get_conversations_db() as conn:
                conn.execute(
                    """
                    INSERT INTO messages (conversation_id, role, content, created_at, is_error, dataset_id)
                    VALUES (?, 'assistant', ?, ?, 1, ?)
                    """,
                    (conv_id, str(error), now, request.dataset_id),
                )
                conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conv_id))
        raise HTTPException(status_code=422, detail=str(error)) from error

    return {
        "dataset_id": request.dataset_id,
        "question": question,
        "original_question": orig_q or question,
        "sql": validated_sql,
        "columns": result_columns,
        "rows": result_rows,
        "answer": explanation,
        "row_count": len(result_rows),
        "chart": None,
        "conversation_id": conv_id,
    }
