
import json
import re
import sqlite3
import urllib.request
import urllib.error
from pathlib import Path

import pandas as pd
import streamlit as st


# ============================================================
# 1. CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="ClarifySQL | AI Analytics",
    page_icon="🔎",
    layout="wide",
)

DB_PATH = Path(__file__).parent / "data" / "sales.db"
OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "qwen2.5:3b"


# ============================================================
# 2. CLARIFYSQL DESIGN SYSTEM
# ============================================================

st.markdown(
    """
    <style>
    /* Main application canvas */
    .stApp {
        background-color: #0B1220;
        color: #E8EEF7;
    }

    /* Main content spacing */
    .block-container {
        max-width: 1440px;
        padding-top: 2.2rem;
        padding-bottom: 3rem;
        padding-left: 2.5rem;
        padding-right: 2.5rem;
    }

    /* Headings */
    h1, h2, h3 {
        color: #F2F7FC !important;
        letter-spacing: -0.025em;
    }

    h1 {
        font-weight: 750 !important;
    }

    /* Body text */
    p, label, .stCaption {
        color: #B8C6D9;
    }

    /* Dividers */
    hr {
        border-color: #26364A;
    }

    /* Buttons */
    .stButton > button {
        background-color: #20B8A6;
        color: #071722;
        border: 1px solid #20B8A6;
        border-radius: 10px;
        padding: 0.55rem 1.1rem;
        font-weight: 650;
        transition: all 0.2s ease;
    }

    .stButton > button:hover {
        background-color: #36D6C2;
        border-color: #36D6C2;
        color: #071722;
    }

    /* Text input */
    .stTextInput input {
        background-color: #121E2E;
        color: #F2F7FC;
        border: 1px solid #34465D;
        border-radius: 10px;
        min-height: 46px;
    }

    .stTextInput input:focus {
        border-color: #20B8A6;
        box-shadow: 0 0 0 1px #20B8A6;
    }

    /* Metric cards */
    [data-testid="stMetric"] {
        background-color: #121E2E;
        border: 1px solid #26364A;
        border-radius: 14px;
        padding: 1.1rem 1.2rem;
    }

    [data-testid="stMetricLabel"] {
        color: #B8C6D9;
    }

    [data-testid="stMetricValue"] {
        color: #F2F7FC;
    }

    /* Tables */
    [data-testid="stDataFrame"] {
        border: 1px solid #26364A;
        border-radius: 12px;
        overflow: hidden;
    }

    /* SQL code blocks */
    [data-testid="stCodeBlock"] {
        border: 1px solid #26364A;
        border-radius: 12px;
    }

    /* Status messages */
    [data-testid="stAlert"] {
        border-radius: 10px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# 3. DATABASE HELPERS
# ============================================================

def load_sales_data():
    """Load product sales analytics from SQLite."""

    query = """
        SELECT
            p.product_name,
            p.category,
            SUM(s.quantity) AS units_sold,
            SUM(s.quantity * p.price) AS revenue
        FROM sales AS s
        JOIN products AS p
            ON s.product_id = p.product_id
        GROUP BY
            p.product_id,
            p.product_name,
            p.category
        ORDER BY revenue DESC
    """

    db_uri = DB_PATH.resolve().as_uri() + "?mode=ro"

    with sqlite3.connect(db_uri, uri=True) as conn:
        conn.execute("PRAGMA query_only = ON")
        return pd.read_sql_query(query, conn)


# ============================================================
# 4. AI: NATURAL LANGUAGE TO SQL
# ============================================================

def generate_sql(question):
    """Generate SQL using the locally running Ollama model."""

    schema = """
    TABLE products:
        product_id
        product_name
        category
        price

    TABLE sales:
        sale_id
        product_id
        quantity
        sale_date

    RELATIONSHIP:
        sales.product_id = products.product_id

    REVENUE FORMULA:
        sales.quantity * products.price
    """

    prompt = f"""
You are ClarifySQL, an expert SQLite query generator.

Convert the user's question into one valid SQLite SELECT query.

DATABASE SCHEMA:
{schema}

RULES:
1. Return SQL only, without Markdown or explanations.
2. Use only the tables and columns listed above.
3. Generate exactly one SELECT statement.
4. Never modify the database.
5. For units sold, calculate SUM(s.quantity).
6. For revenue, calculate SUM(s.quantity * p.price).
7. Join products and sales using product_id when needed.
8. Use GROUP BY for product or category totals.
9. For top-three questions, sort descending and use LIMIT 3.
10. Use valid SQLite syntax.
11. Return INVALID only if the question cannot be answered
    using the available schema.

EXAMPLE 1
Question: Show the top 3 products by units sold.

SELECT p.product_name, SUM(s.quantity) AS units_sold
FROM products p
JOIN sales s ON p.product_id = s.product_id
GROUP BY p.product_id, p.product_name
ORDER BY units_sold DESC
LIMIT 3

EXAMPLE 2
Question: What is the total revenue across all products?

SELECT SUM(s.quantity * p.price) AS total_revenue
FROM sales s
JOIN products p ON s.product_id = p.product_id

EXAMPLE 3
Question: What is the total revenue for each category?

SELECT p.category, SUM(s.quantity * p.price) AS revenue
FROM products p
JOIN sales s ON p.product_id = s.product_id
GROUP BY p.category
ORDER BY revenue DESC

USER QUESTION:
{question}

Return only the SQL query or INVALID.
"""

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
        "stream": False,
        "options": {
            "temperature": 0,
        },
    }

    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            result = json.loads(response.read().decode("utf-8"))

    except urllib.error.URLError as error:
        raise RuntimeError(
            "Cannot connect to Ollama. Make sure Ollama is running."
        ) from error

    answer = result.get("message", {}).get("content", "").strip()

    # Remove optional Markdown code fences.
    answer = re.sub(
        r"\A```(?:sql)?\s*",
        "",
        answer,
        flags=re.IGNORECASE,
    )

    answer = re.sub(r"\s*```\s*\Z", "", answer).strip()

    if not answer:
        raise RuntimeError("The AI returned an empty response.")

    return answer


# ============================================================
# 5. AI: EXPLAIN QUERY RESULTS
# ============================================================

def explain_results(question, sql, results):
    """Generate a detailed explanation of query results."""

    if results.empty:
        return (
            "The query completed successfully, "
            "but no matching records were found."
        )

    prompt = f"""
You are ClarifySQL, a professional data analytics assistant.

Analyze the SQL query results and create a detailed,
easy-to-understand report using Markdown headings and bullet points.

USER QUESTION:
{question}

SQL QUERY:
{sql}

QUERY RESULTS:
{json.dumps(results.head(10).to_dict(orient="records"), default=str)}

Write the report using this exact structure:

### 1. Key Findings
- Explain the most important results using actual values.
- Mention relevant product names, categories, dates, or metrics.
- Include up to 3-5 useful findings when the data supports them.

### 2. Data Comparison
- Compare the most relevant values.
- Calculate differences or percentages only when they can
  be derived reliably from the supplied results.
- If the results do not support a meaningful comparison,
  explain what can be compared instead.

### 3. Important Observations
- Explain meaningful patterns, rankings, or differences.
- Distinguish observed facts from possible interpretations.
- Never invent trends, causes, or business explanations.

### 4. Summary
- Give a short, direct conclusion answering the user's question.
- Mention the most important number or result.

RULES:
- Use clear Markdown headings and bullet points.
- Be informative but concise.
- Use simple, professional English.
- Base every factual claim on the supplied results.
- Do not invent missing data or claim statistical significance.
- Do not repeat the same point in multiple sections.
- If only a few rows are available, analyze only those rows.
- If the result set is empty, explain that no matching records were found.
- Do not return SQL or code.
"""

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "user", "content": prompt}
        ],
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
        with urllib.request.urlopen(request, timeout=180) as response:
            data = json.loads(response.read().decode("utf-8"))

        explanation = data.get("message", {}).get("content", "").strip()

        if not explanation:
            return (
                "Results retrieved successfully. "
                "No explanation was generated."
            )

        return explanation

    except Exception:
        return (
            "Your query results are available above, "
            "but the AI explanation could not be generated."
        )


# ============================================================
# 6. SQL VALIDATION
# ============================================================

def validate_sql(query):
    """
    Accept one simple SELECT statement.

    This is a basic prototype validator, not a complete SQL
    security parser. Read-only SQLite access is also enforced.
    """

    query = query.strip()

    if query.upper() == "INVALID":
        return None

    # Permit one optional trailing semicolon.
    if query.endswith(";"):
        query = query[:-1].strip()

    if not query:
        raise ValueError("The generated SQL query is empty.")

    if ";" in query:
        raise ValueError("Multiple SQL statements are not allowed.")

    # Only SELECT statements are supported in this version.
    if not re.match(r"\ASELECT\b", query, flags=re.IGNORECASE):
        raise ValueError("Only SELECT queries are allowed.")

    if "--" in query or "/*" in query or "*/" in query:
        raise ValueError("SQL comments are not allowed.")

    forbidden_pattern = re.compile(
        r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|"
        r"ATTACH|DETACH|PRAGMA|VACUUM|REINDEX|UNION|WITH|"
        r"TRIGGER|VIEW|INDEX)\b",
        flags=re.IGNORECASE,
    )

    if forbidden_pattern.search(query):
        raise ValueError(
            "The query contains a restricted SQL keyword."
        )

    return query


# ============================================================
# 7. READ-ONLY SQL EXECUTION
# ============================================================

def run_readonly_sql(query):
    """Run SQL against the existing database without write access."""

    db_uri = DB_PATH.resolve().as_uri() + "?mode=ro"

    with sqlite3.connect(
        db_uri,
        uri=True,
        timeout=10,
    ) as conn:

        conn.execute("PRAGMA query_only = ON")

        cursor = conn.execute(query)

        if cursor.description is None:
            raise ValueError("The query returned no tabular results.")

        columns = [item[0] for item in cursor.description]
        rows = cursor.fetchmany(501)

        if len(rows) > 500:
            raise ValueError(
                "More than 500 rows were returned. "
                "Please narrow your question."
            )

        return pd.DataFrame(rows, columns=columns)


# ============================================================
# 8. PAGE HEADER
# ============================================================

st.title("🔎 ClarifySQL")

st.caption("Ask questions about your data. Get clear answers.")

st.markdown(
    """
    Welcome to your personal analytics workspace.

    Explore sales performance, ask questions in plain English,
    and inspect the SQL used to retrieve your results.
    """
)


# ============================================================
# 9. CHECK DATABASE
# ============================================================

if not DB_PATH.exists():
    st.error(
        "Database not found. Check that data/sales.db exists."
    )
    st.stop()

try:
    results = load_sales_data()

except Exception as error:
    st.error(f"Could not load sales data: {error}")
    st.stop()


# ============================================================
# 10. KPI CARDS
# ============================================================

total_revenue = results["revenue"].sum()
total_units = results["units_sold"].sum()
total_products = len(results)

col1, col2, col3 = st.columns(3)

col1.metric(
    "Total Revenue",
    f"₹{total_revenue:,.0f}",
)

col2.metric(
    "Units Sold",
    f"{total_units:,.0f}",
)

col3.metric(
    "Products Sold",
    total_products,
)

st.divider()


# ============================================================
# 11. DASHBOARD CHART AND TABLE
# ============================================================

left, right = st.columns([3, 2])

with left:
    st.subheader("Revenue by Product")

    chart_data = results.set_index("product_name")[["revenue"]]

    st.bar_chart(chart_data)

with right:
    st.subheader("Product Performance")

    st.dataframe(
        results,
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# 12. ASK YOUR DATA
# ============================================================

st.divider()

st.subheader("💬 Ask your data")

st.caption(
    "Powered by Qwen 2.5 3B through local Ollama."
)

question = st.text_input(
    "What would you like to know?",
    placeholder="e.g. Show the top 3 products by units sold.",
    key="user_question",
)

if st.button("Generate answer", type="primary"):

    if not question.strip():
        st.warning("Please enter a question first.")

    else:
        try:
            with st.spinner("AI is generating your SQL..."):
                generated_sql = generate_sql(question)

            validated_sql = validate_sql(generated_sql)

            if validated_sql is None:
                st.warning(
                    "The AI could not answer this question "
                    "using the available database schema."
                )

            else:
                st.markdown("### Generated SQL")

                st.code(
                    validated_sql,
                    language="sql",
                )

                with st.spinner("Running read-only query..."):
                    answer = run_readonly_sql(validated_sql)

                st.markdown("### Query Results")

                st.dataframe(
                    answer,
                    use_container_width=True,
                    hide_index=True,
                )

                st.success(
                    f"Query completed successfully. "
                    f"{len(answer)} row(s) returned."
                )

                # AI-generated explanation
                st.markdown("### ✨ AI Insights")

                with st.spinner("Explaining your results..."):
                    explanation = explain_results(
                        question,
                        validated_sql,
                        answer,
                    )

                st.write(explanation)

                if answer.empty:
                    st.info(
                        "The query ran successfully but returned no rows."
                    )

        except Exception as error:
            st.error(f"Could not answer the question: {error}")

            st.caption(
                "Check that Ollama is running and that the generated "
                "SQL matches the database schema."
            )


# ============================================================
# 13. FOOTER
# ============================================================

st.divider()

st.caption(
    "ClarifySQL | Local AI analytics prototype | "
    "Read-only database access"
)
