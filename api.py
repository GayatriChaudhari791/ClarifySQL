
import json
import re
import sqlite3
import uuid
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


app = FastAPI(title="ClarifySQL API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "qwen2.5:3b"
MAX_FILE_SIZE = 20 * 1024 * 1024
MAX_ROWS = 100_000
MAX_RESULT_ROWS = 500

DATA_DIR = Path(__file__).parent / "uploaded_data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


class QueryRequest(BaseModel):
    dataset_id: str
    question: str


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


def generate_sql(question: str, schema: str) -> str:
    prompt = f"""
You are ClarifySQL, an expert natural-language-to-SQL assistant.

Convert the user's question into exactly one valid SQLite SELECT query.

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
- Do not return INVALID merely because a question requires calculations,
  aggregation, grouping, sorting, filtering, or percentages.
- For requests involving percentages, calculate the percentage as
  (numerator * 100.0 / denominator).
- Use a subquery to calculate the total when the denominator requires
  the total number of rows in the dataset.
- Use GROUP BY when the user asks for results by category.
- Use COUNT(*) when counting rows.
- Use COUNT(DISTINCT column) when counting unique values.
- Use SUM, AVG, MIN, and MAX when appropriate for the available data.
- For top-N questions, use ORDER BY and LIMIT.
- Do not use SELECT * unless the user explicitly asks to see all columns.
- If the user asks a question about a column that does not exist,
  return INVALID.
- For questions asking for the percentage distribution across states,
  cities, or another available categorical column, calculate the count
  for each category and divide it by the total number of rows.
- Do not assume that a question is impossible merely because it requires
  more than one SQL operation.

EXAMPLES:

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

Question: What is the average postal code prefix?
SQL:
SELECT AVG("seller_zip_code_prefix") AS average_zip_code_prefix
FROM "uploaded_data"

Question: What is the total revenue?
SQL:
INVALID

The final example must return INVALID when the schema contains no
revenue column or other information from which revenue can be calculated.

USER QUESTION:
{question}

Return only the SQL query or INVALID.
"""

    answer = call_ollama(prompt)

    answer = re.sub(
        r"\\A```(?:sql)?\\s*",
        "",
        answer,
        flags=re.IGNORECASE,
    )
    answer = re.sub(r"\\s*```\\s*\\Z", "", answer).strip()

    return answer

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


@app.post("/upload")
async def upload_dataset(file: UploadFile = File(...)):
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

    return {
        "dataset_id": dataset_id,
        "filename": filename,
        "row_count": len(frame),
        "columns": list(frame.columns),
        "preview": dataframe_to_json_rows(frame.head(5)),
        "schema": get_schema(frame),
    }


@app.post("/query")
def query_dataset(request: QueryRequest):
    question = request.question.strip()

    if not question:
        raise HTTPException(status_code=400, detail="Please enter a question.")

    if len(question) > 2000:
        raise HTTPException(
            status_code=400,
            detail="Please keep your question under 2,000 characters.",
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

    schema_lines = [
        'TABLE: "uploaded_data"',
        f"Row count: {row_count}",
        "Columns:",
    ]

    for column in columns_in_dataset:
        schema_lines.append(f'- "{column}"')

    schema = "\n".join(schema_lines)

    try:
        generated_sql = generate_sql(question, schema)
        validated_sql = validate_sql(generated_sql)
        result_columns, result_rows = execute_readonly_query(
            db_path,
            validated_sql,
        )
        explanation = explain_results(
            question,
            validated_sql,
            result_columns,
            result_rows,
        )

    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except sqlite3.Error as error:
        raise HTTPException(
            status_code=422,
            detail=f"The generated query could not be executed: {error}",
        ) from error

    return {
        "dataset_id": request.dataset_id,
        "question": question,
        "sql": validated_sql,
        "columns": result_columns,
        "rows": result_rows,
        "answer": explanation,
        "row_count": len(result_rows),
        "chart": None,
    }
