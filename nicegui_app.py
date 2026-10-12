import json
import re
import sqlite3
import urllib.request
import urllib.error
from pathlib import Path

import pandas as pd
from nicegui import ui, run


# =========================================================
# 1. CONFIGURATION
# =========================================================

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "sales.db"
OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "qwen2.5:3b"

STATE = {
    "history": [],
    "last_question": None,
    "last_sql": None,
    "last_results": None,
    "last_insights": None,
    "current_question": "",
    "dark": True,
}

# UI references are initialized when the page is created.
UI = {}


# =========================================================
# 2. SHARED CSS
# =========================================================

UI_CSS = """
<style>
:root {
    --accent: #24c7b3;
    --accent-hover: #42dfcc;
    --border: #263b50;
    --muted: #92a8bf;
}

* { box-sizing: border-box; }

body {
    margin: 0;
    font-family: Inter, "Segoe UI", system-ui, sans-serif;
}

.app-shell {
    min-height: 100vh;
    width: 100%;
    display: flex;
}

.app-sidebar {
    width: 245px;
    min-width: 245px;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    padding: 20px 14px;
    border-right: 1px solid var(--border);
    background: #0c1726;
}

.app-main {
    min-width: 0;
    flex: 1;
    background: #080f1d;
}

.app-topbar {
    min-height: 76px;
    padding: 15px 28px;
    border-bottom: 1px solid var(--border);
}

.app-content {
    padding: 28px;
    max-width: 1700px;
    margin: 0 auto;
    width: 100%;
}

.brand-icon {
    width: 43px;
    height: 43px;
    display: flex;
    align-items: center;
    justify-content: center;
    border: 1px solid rgba(36,199,179,.4);
    background: rgba(36,199,179,.12);
    border-radius: 13px;
    color: var(--accent);
    flex-shrink: 0;
}

.brand-name {
    font-size: 21px;
    font-weight: 750;
    letter-spacing: -.5px;
}

.muted, .studio-muted {
    color: var(--muted);
}

.section-label {
    color: var(--muted);
    font-size: 10px;
    font-weight: 750;
    letter-spacing: 1.4px;
    text-transform: uppercase;
}

.studio-card, .result-panel {
    border: 1px solid var(--border);
    border-radius: 15px;
    padding: 20px;
    box-shadow: none;
    background: #101e2e;
    color: #eaf2fa;
}

.nav-button {
    width: 100%;
    min-height: 42px;
    border-radius: 9px;
    justify-content: flex-start;
    color: var(--muted);
}

.nav-button .q-btn__content {
    justify-content: flex-start;
    width: 100%;
}

.nav-button.active {
    background: rgba(36,199,179,.12);
    color: var(--accent);
    font-weight: 700;
}

.primary-action {
    background: var(--accent) !important;
    color: #05232a !important;
    border-radius: 9px !important;
    font-weight: 750 !important;
    min-height: 40px;
}

.primary-action:hover {
    background: var(--accent-hover) !important;
}

.suggestion-card {
    cursor: pointer;
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px;
    min-height: 112px;
    transition: border-color .15s, transform .15s;
}

.suggestion-card:hover {
    border-color: var(--accent);
    transform: translateY(-1px);
}

.q-field--outlined .q-field__control {
    border-radius: 10px;
}

.q-table th {
    font-weight: 700;
}

@media (max-width: 1000px) {
    .app-sidebar {
        width: 200px;
        min-width: 200px;
    }

    .app-content {
        padding: 18px;
    }
}

@media (max-width: 700px) {
    .app-sidebar {
        width: 65px;
        min-width: 65px;
        padding: 12px 6px;
    }

    .app-sidebar .nav-label,
    .app-sidebar .sidebar-heading,
    .app-sidebar .sidebar-brand-text,
    .app-sidebar .history-entry {
        display: none !important;
    }

    .app-sidebar .nav-button {
        justify-content: center;
        padding: 0;
    }

    .app-content {
        padding: 14px;
    }

    .app-topbar {
        padding: 12px 16px;
    }
}
</style>
"""

# Register shared HTML outside the page function.
ui.add_head_html(UI_CSS, shared=True)


# =========================================================
# 3. DATABASE
# =========================================================

def database_uri():
    return DB_PATH.resolve().as_uri() + "?mode=ro"


def get_schema():
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Sample database not found: {DB_PATH}"
        )

    schema = {}

    with sqlite3.connect(database_uri(), uri=True) as conn:
        conn.execute("PRAGMA query_only = ON")

        tables = conn.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """).fetchall()

        for (table_name,) in tables:
            safe_name = table_name.replace('"', '""')

            columns = conn.execute(
                f'PRAGMA table_info("{safe_name}")'
            ).fetchall()

            count = conn.execute(
                f'SELECT COUNT(*) FROM "{safe_name}"'
            ).fetchone()[0]

            schema[table_name] = {
                "rows": count,
                "columns": [
                    {
                        "name": column[1],
                        "type": column[2] or "UNKNOWN",
                    }
                    for column in columns
                ],
            }

    return schema


def schema_prompt():
    lines = []

    for table, details in get_schema().items():
        lines.append(f"TABLE {table}:")

        for column in details["columns"]:
            lines.append(
                f"  {column['name']} ({column['type']})"
            )

        lines.append(f"  Rows: {details['rows']}")
        lines.append("")

    return "\n".join(lines)


def load_sales_data():
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

    with sqlite3.connect(database_uri(), uri=True) as conn:
        conn.execute("PRAGMA query_only = ON")
        return pd.read_sql_query(query, conn)


# =========================================================
# 4. LOCAL OLLAMA AI
# =========================================================

def ask_ollama(prompt):
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
        with urllib.request.urlopen(
            request, timeout=180
        ) as response:
            data = json.loads(
                response.read().decode("utf-8")
            )

    except urllib.error.URLError as error:
        raise RuntimeError(
            "Cannot connect to Ollama. Make sure Ollama is "
            "running and qwen2.5:3b is available."
        ) from error

    answer = data.get("message", {}).get(
        "content", ""
    ).strip()

    if not answer:
        raise RuntimeError("The AI returned an empty response.")

    return answer


def generate_sql(question):
    prompt = f"""
You are ClarifySQL, a professional natural-language-to-SQL assistant.

DATABASE SCHEMA:
{schema_prompt()}

USER QUESTION:
{question}

RULES:
- Return exactly one SQLite SELECT statement.
- Use only tables and columns in the schema.
- Never modify the database.
- Use suitable JOIN, GROUP BY, ORDER BY and LIMIT clauses.
- Do not invent columns or tables.
- Do not use UNION, CTEs, SQL comments, or multiple statements.
- Return SQL only, without Markdown or explanation.
- Return INVALID if the schema cannot answer the question.
"""

    answer = ask_ollama(prompt)

    answer = re.sub(
        r"\A```(?:sql)?\s*",
        "",
        answer,
        flags=re.IGNORECASE,
    )
    answer = re.sub(
        r"\s*```\s*\Z",
        "",
        answer,
    ).strip()

    return answer


# =========================================================
# 5. SQL VALIDATION AND READ-ONLY EXECUTION
# =========================================================

def validate_sql(query):
    query = query.strip()

    if query.upper() == "INVALID":
        return None

    if query.endswith(";"):
        query = query[:-1].strip()

    if not query:
        raise ValueError("The generated SQL query is empty.")

    if ";" in query:
        raise ValueError("Only one SQL statement is allowed.")

    if not re.match(
        r"\ASELECT\b", query, flags=re.IGNORECASE
    ):
        raise ValueError("Only SELECT queries are allowed.")

    if "--" in query or "/*" in query or "*/" in query:
        raise ValueError("SQL comments are not allowed.")

    forbidden = re.compile(
        r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|"
        r"ATTACH|DETACH|PRAGMA|VACUUM|REINDEX|UNION|WITH|"
        r"TRIGGER|VIEW|INDEX)\b",
        flags=re.IGNORECASE,
    )

    if forbidden.search(query):
        raise ValueError(
            "The query contains a restricted SQL keyword."
        )

    return query


def execute_sql(query):
    with sqlite3.connect(
        database_uri(),
        uri=True,
        timeout=10,
    ) as conn:
        conn.execute("PRAGMA query_only = ON")
        cursor = conn.execute(query)

        if cursor.description is None:
            raise ValueError(
                "The query did not return tabular results."
            )

        columns = [
            column[0] for column in cursor.description
        ]

        rows = cursor.fetchmany(501)

        if len(rows) > 500:
            raise ValueError(
                "More than 500 rows were returned. "
                "Narrow your question."
            )

        return pd.DataFrame(rows, columns=columns)


# =========================================================
# 6. AI INSIGHTS
# =========================================================

def explain_results(question, sql, results):
    if results.empty:
        return (
            "### Summary\n\n"
            "The query completed successfully, but no matching "
            "records were found."
        )

    prompt = f"""
You are ClarifySQL, a professional data analytics assistant.

USER QUESTION:
{question}

SQL QUERY:
{sql}

QUERY RESULTS:
{json.dumps(results.head(15).to_dict(orient="records"), default=str)}

Write a report using these headings:

### 1. Key Findings
Explain the most important results using actual values.

### 2. Data Comparison
Compare values when the results support a comparison.

### 3. Important Observations
Describe patterns and distinguish facts from interpretations.

### 4. Summary
Give a concise answer to the user's question.

Use professional, easy-to-understand English and Markdown bullets.
Do not invent facts, trends, causes, or missing data.
Do not return SQL or code.
"""

    try:
        return ask_ollama(prompt)
    except Exception:
        return (
            "The query succeeded, but the AI explanation could "
            "not be generated. Your results are still available."
        )


# =========================================================
# 7. NAVIGATION AND THEME
# =========================================================

def navigate(page):
    for name, panel in UI["pages"].items():
        panel.set_visibility(name == page)

    for name, button in UI["nav_buttons"].items():
        if name == page:
            button.classes(add="active")
        else:
            button.classes(remove="active")

    titles = {
        "chat": "Analysis workspace",
        "dashboard": "Dashboard Studio",
        "data": "Data sources",
        "settings": "Settings",
        "profile": "Profile",
    }

    UI["page_title"].text = titles.get(page, "ClarifySQL")

    if page == "dashboard":
        render_dashboard()


def apply_theme(is_dark):
    STATE["dark"] = is_dark

    if is_dark:
        ui.query("body").style(
            "background:#080f1d;color:#eaf2fa;"
        )
        ui.query(".app-sidebar").style(
            "background:#0c1726;color:#eaf2fa;"
        )
        ui.query(".app-main").style(
            "background:#080f1d;color:#eaf2fa;"
        )
        ui.query(".studio-card").style(
            "background:#101e2e;color:#eaf2fa;"
        )
        ui.query(".result-panel").style(
            "background:#101e2e;color:#eaf2fa;"
        )
    else:
        ui.query("body").style(
            "background:#f3f7fb;color:#172b40;"
        )
        ui.query(".app-sidebar").style(
            "background:#ffffff;color:#172b40;"
        )
        ui.query(".app-main").style(
            "background:#f3f7fb;color:#172b40;"
        )
        ui.query(".studio-card").style(
            "background:#ffffff;color:#172b40;"
        )
        ui.query(".result-panel").style(
            "background:#ffffff;color:#172b40;"
        )


def new_chat():
    STATE["current_question"] = ""
    UI["question"].value = ""
    UI["results"].clear()
    navigate("chat")


def set_current_question(value):
    STATE["current_question"] = str(value or "")


def fill_question(question):
    STATE["current_question"] = question
    UI["question"].value = question
    navigate("chat")


# =========================================================
# 8. DATASET SCHEMA
# =========================================================

def render_schema():
    container = UI["schema"]
    container.clear()

    try:
        schema = get_schema()

        with container:
            for table_name, details in schema.items():
                with ui.expansion(
                    f"{table_name} · {details['rows']} rows",
                    icon="table_chart",
                ).classes("w-full"):
                    for column in details["columns"]:
                        with ui.row().classes(
                            "w-full items-center justify-between"
                        ):
                            ui.label(
                                column["name"]
                            ).classes("text-sm")

                            ui.label(
                                column["type"]
                            ).classes("text-xs muted")

    except Exception as error:
        with container:
            ui.label(str(error)).classes("text-red-400")


# =========================================================
# 9. CONVERSATION HISTORY
# =========================================================

def render_history():
    container = UI["history"]
    container.clear()

    with container:
        if not STATE["history"]:
            ui.label(
                "Your analyses will appear here."
            ).classes("text-xs muted")
            return

        for index, item in reversed(
            list(enumerate(STATE["history"]))
        ):
            label = item["question"]

            if len(label) > 28:
                label = label[:28] + "..."

            ui.button(
                label,
                icon="chat_bubble_outline",
                on_click=lambda i=index: restore_history(i),
            ).props("flat align=left no-caps").classes(
                "w-full history-entry"
            )


def restore_history(index):
    if index < 0 or index >= len(STATE["history"]):
        return

    item = STATE["history"][index]

    STATE["last_question"] = item["question"]
    STATE["last_sql"] = item["sql"]
    STATE["last_results"] = item["results"].copy()
    STATE["last_insights"] = item["insights"]
    STATE["current_question"] = item["question"]

    UI["question"].value = item["question"]
    navigate("chat")

    render_results(
        item["question"],
        item["sql"],
        item["results"],
        item["insights"],
    )


# =========================================================
# 10. RESULTS
# =========================================================

def render_results(question, sql, results, insights):
    container = UI["results"]
    container.clear()

    with container:
        with ui.card().classes("result-panel w-full"):
            with ui.row().classes("w-full items-center gap-3"):
                ui.icon("auto_awesome").classes(
                    "text-2xl text-teal-400"
                )

                with ui.column().classes("gap-0"):
                    ui.label(
                        "Analysis results"
                    ).classes("text-lg font-bold")

                    ui.label(question).classes("text-sm muted")

                ui.space()

                ui.button(
                    "Create dashboard",
                    icon="bar_chart",
                    on_click=lambda: navigate("dashboard"),
                ).props("outline color=teal no-caps")

        with ui.card().classes("result-panel w-full"):
            with ui.row().classes("w-full items-center"):
                ui.icon("table_chart").classes(
                    "text-teal-400 text-xl"
                )
                ui.label(
                    "Query results"
                ).classes("text-lg font-bold")
                ui.space()
                ui.badge(f"{len(results)} rows", color="teal")

            if results.empty:
                ui.label(
                    "No matching rows were found."
                ).classes("muted")
            else:
                rows = json.loads(
                    results.to_json(
                        orient="records",
                        date_format="iso",
                    )
                )

                ui.table(
                    columns=[
                        {
                            "name": str(column),
                            "label": str(column).replace(
                                "_", " "
                            ).title(),
                            "field": str(column),
                            "align": "left",
                        }
                        for column in results.columns
                    ],
                    rows=rows,
                    row_key=str(results.columns[0]),
                ).classes("w-full").props("flat bordered")

        with ui.card().classes("result-panel w-full"):
            with ui.row().classes("w-full items-center"):
                ui.icon("code").classes(
                    "text-teal-400 text-xl"
                )
                ui.label(
                    "Generated SQL"
                ).classes("text-lg font-bold")
                ui.space()

                ui.button(
                    "Copy SQL",
                    icon="content_copy",
                    on_click=lambda: ui.clipboard.write(sql),
                ).props("flat color=teal no-caps")

            ui.code(sql, language="SQL").classes("w-full")

        with ui.card().classes("result-panel w-full"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("auto_awesome").classes(
                    "text-teal-400 text-xl"
                )
                ui.label(
                    "AI Insights"
                ).classes("text-lg font-bold")

            ui.markdown(insights).classes("w-full")


# =========================================================
# 11. ANALYSE QUESTION
# =========================================================

async def submit_question():
    # Prefer the live input value, then use the saved value.
    question = str(
        UI["question"].value
        or STATE.get("current_question", "")
        or ""
    ).strip()

    # Debugging output: shows exactly what the function received.
    print("ClarifySQL received:", repr(question))

    if not question:
        ui.notify(
            "Please type a question before clicking Analyse data.",
            type="warning",
        )
        return

    STATE["current_question"] = question

    if not DB_PATH.exists():
        ui.notify(
            "Sample database not found.",
            type="negative",
        )
        return

    UI["results"].clear()

    with UI["results"]:
        with ui.card().classes("result-panel w-full"):
            ui.spinner("dots", size="lg", color="teal")
            ui.label("ClarifySQL is analysing your question...")

    try:
        generated = await run.io_bound(
            generate_sql, question
        )
        sql = validate_sql(generated)

        if sql is None:
            UI["results"].clear()

            with UI["results"]:
                with ui.card().classes("result-panel w-full"):
                    ui.label(
                        "Unable to answer this question"
                    ).classes("text-lg font-bold")

                    ui.label(
                        "Try asking about products, categories, "
                        "revenue, or units sold in the sample dataset."
                    ).classes("muted")

            return

        results = await run.io_bound(execute_sql, sql)

        insights = await run.io_bound(
            explain_results,
            question,
            sql,
            results,
        )

        STATE["last_question"] = question
        STATE["last_sql"] = sql
        STATE["last_results"] = results.copy()
        STATE["last_insights"] = insights

        STATE["history"].append({
            "question": question,
            "sql": sql,
            "results": results.copy(),
            "insights": insights,
        })

        render_history()
        render_results(question, sql, results, insights)

        ui.notify(
            "Analysis completed successfully!",
            type="positive",
        )

    except Exception as error:
        UI["results"].clear()

        with UI["results"]:
            with ui.card().classes("result-panel w-full"):
                ui.label(
                    "Analysis failed"
                ).classes("text-lg font-bold text-red-400")

                ui.label(str(error))

                ui.label(
                    "Check that Ollama is running and "
                    "the qwen2.5:3b model is available."
                ).classes("muted")

        ui.notify(
            "Could not complete the analysis.",
            type="negative",
        )


# =========================================================
# 12. DASHBOARD
# =========================================================

def render_dashboard():
    container = UI["dashboard_content"]
    container.clear()

    try:
        data = load_sales_data()
    except Exception as error:
        with container:
            ui.label(
                f"Could not load dashboard: {error}"
            )
        return

    with container:
        with ui.grid(columns=3).classes("w-full gap-3"):
            with ui.card().classes("studio-card"):
                ui.label("TOTAL REVENUE").classes("section-label")
                ui.label(
                    f"₹{data['revenue'].sum():,.0f}"
                ).classes("text-2xl font-bold text-teal-400")

            with ui.card().classes("studio-card"):
                ui.label("UNITS SOLD").classes("section-label")
                ui.label(
                    f"{data['units_sold'].sum():,.0f}"
                ).classes("text-2xl font-bold")

            with ui.card().classes("studio-card"):
                ui.label("PRODUCTS").classes("section-label")
                ui.label(
                    str(len(data))
                ).classes("text-2xl font-bold")

        with ui.card().classes("studio-card w-full"):
            ui.label(
                "Revenue by product"
            ).classes("text-lg font-bold")

            ui.echart({
                "tooltip": {"trigger": "axis"},
                "xAxis": {
                    "type": "category",
                    "data": data["product_name"].tolist(),
                    "axisLabel": {"rotate": 20},
                },
                "yAxis": {"type": "value"},
                "series": [{
                    "type": "bar",
                    "data": data["revenue"].tolist(),
                    "itemStyle": {"color": "#24c7b3"},
                    "barMaxWidth": 50,
                }],
                "grid": {
                    "left": 60,
                    "right": 20,
                    "bottom": 70,
                    "top": 25,
                },
            }).classes("w-full h-80")

            ui.table(
                columns=[
                    {
                        "name": str(column),
                        "label": str(column).replace(
                            "_", " "
                        ).title(),
                        "field": str(column),
                    }
                    for column in data.columns
                ],
                rows=json.loads(
                    data.to_json(orient="records")
                ),
                row_key="product_name",
            ).classes("w-full")


# =========================================================
# 13. APPLICATION PAGE
# =========================================================

@ui.page("/")
def main_page():
    ui.dark_mode(value=True)

    with ui.element("div").classes("app-shell"):

        # SIDEBAR
        with ui.column().classes("app-sidebar gap-0"):
            with ui.row().classes(
                "items-center gap-3 px-2 mb-7 sidebar-brand-text"
            ):
                with ui.element("div").classes("brand-icon"):
                    ui.icon("query_stats").classes("text-2xl")

                with ui.column().classes("gap-0"):
                    ui.label("ClarifySQL").classes("brand-name")
                    ui.label(
                        "DATA INTELLIGENCE STUDIO"
                    ).classes("text-xs muted tracking-widest")

            ui.button(
                "New analysis",
                icon="add",
                on_click=new_chat,
            ).classes("primary-action w-full mb-6")

            ui.label("WORKSPACE").classes(
                "section-label px-3 mb-1 sidebar-heading"
            )

            chat_button = ui.button(
                "Chat",
                icon="forum",
                on_click=lambda: navigate("chat"),
            ).props("flat no-caps").classes("nav-button active")

            dashboard_button = ui.button(
                "Dashboards",
                icon="bar_chart",
                on_click=lambda: navigate("dashboard"),
            ).props("flat no-caps").classes("nav-button")

            data_button = ui.button(
                "Data sources",
                icon="database",
                on_click=lambda: navigate("data"),
            ).props("flat no-caps").classes("nav-button")

            ui.separator().classes("my-5")

            ui.label("RECENT ANALYSES").classes(
                "section-label px-3 mb-2 sidebar-heading"
            )

            history_container = ui.column().classes("w-full gap-1")
            UI["history"] = history_container
            render_history()

            ui.space()
            ui.separator().classes("my-4")

            settings_button = ui.button(
                "Settings",
                icon="settings",
                on_click=lambda: navigate("settings"),
            ).props("flat no-caps").classes("nav-button")

            profile_button = ui.button(
                "Profile",
                icon="account_circle",
                on_click=lambda: navigate("profile"),
            ).props("flat no-caps").classes("nav-button")

            with ui.row().classes("items-center gap-2 px-3 mt-4"):
                ui.icon("shield_lock").classes("text-teal-400")
                with ui.column().classes("gap-0"):
                    ui.label("Local AI workspace").classes("text-xs")
                    ui.label(
                        "Read-only sample database"
                    ).classes("text-xs muted")

        # MAIN AREA
        with ui.column().classes("app-main gap-0"):
            with ui.row().classes("app-topbar w-full items-center"):
                with ui.column().classes("gap-0"):
                    ui.label("CLARIFYSQL").classes("section-label")
                    page_title = ui.label(
                        "Analysis workspace"
                    ).classes("text-xl font-bold")

                ui.space()
                ui.label("Light").classes("text-xs muted")

                ui.switch(
                    value=True,
                    on_change=lambda event: apply_theme(event.value),
                ).props("color=teal")

                ui.label("Dark").classes("text-xs muted")

            with ui.column().classes("app-content w-full gap-5"):

                # CHAT PAGE
                chat_page = ui.column().classes("w-full gap-5")

                with chat_page:
                    with ui.row().classes(
                        "w-full items-start justify-between gap-4"
                    ):
                        with ui.column().classes("gap-1"):
                            ui.label(
                                "Turn questions into insights."
                            ).classes(
                                "text-3xl font-bold tracking-tight"
                            )

                            ui.label(
                                "Explore your data with natural language, "
                                "transparent SQL, and AI explanations."
                            ).classes("muted")

                        ui.badge("LOCAL AI", color="teal")

                    with ui.card().classes("studio-card w-full"):
                        with ui.row().classes(
                            "w-full items-center gap-3"
                        ):
                            with ui.element("div").classes("brand-icon"):
                                ui.icon("database").classes("text-xl")

                            with ui.column().classes("gap-0"):
                                ui.label(
                                    "Active dataset"
                                ).classes("text-lg font-bold")

                                ui.label(
                                    "sales.db · Sample workspace"
                                ).classes("text-sm muted")

                            ui.space()
                            ui.badge("Connected", color="positive")

                        ui.separator().classes("my-3")

                        schema_container = ui.column().classes(
                            "w-full gap-1"
                        )
                        UI["schema"] = schema_container
                        render_schema()

                    with ui.card().classes("studio-card w-full"):
                        with ui.row().classes(
                            "items-center gap-3"
                        ):
                            ui.icon("auto_awesome").classes(
                                "text-2xl text-teal-400"
                            )

                            with ui.column().classes("gap-0"):
                                ui.label(
                                    "Ask your data"
                                ).classes("text-xl font-bold")

                                ui.label(
                                    "Ask a question in plain English."
                                ).classes("text-sm muted")

                        ui.label("SUGGESTED QUESTIONS").classes(
                            "section-label mt-4 mb-2"
                        )

                        with ui.grid(columns=2).classes("w-full gap-3"):
                            with ui.element("div").classes(
                                "suggestion-card"
                            ).on(
                                "click",
                                lambda: fill_question(
                                    "Show the top 3 products by units sold."
                                ),
                            ):
                                ui.icon("trending_up").classes(
                                    "text-xl text-teal-400"
                                )
                                ui.label("Top products").classes(
                                    "font-bold mt-2"
                                )
                                ui.label(
                                    "Find the highest quantities sold."
                                ).classes("text-sm muted")

                            with ui.element("div").classes(
                                "suggestion-card"
                            ).on(
                                "click",
                                lambda: fill_question(
                                    "Show total revenue by category."
                                ),
                            ):
                                ui.icon("pie_chart").classes(
                                    "text-xl text-teal-400"
                                )
                                ui.label("Category analysis").classes(
                                    "font-bold mt-2"
                                )
                                ui.label(
                                    "Compare revenue by category."
                                ).classes("text-sm muted")

                            with ui.element("div").classes(
                                "suggestion-card"
                            ).on(
                                "click",
                                lambda: fill_question(
                                    "Which products generated the most revenue?"
                                ),
                            ):
                                ui.icon("leaderboard").classes(
                                    "text-xl text-teal-400"
                                )
                                ui.label("Revenue ranking").classes(
                                    "font-bold mt-2"
                                )
                                ui.label(
                                    "Find the leading products."
                                ).classes("text-sm muted")

                            with ui.element("div").classes(
                                "suggestion-card"
                            ).on(
                                "click",
                                lambda: fill_question(
                                    "What is the total revenue across all products?"
                                ),
                            ):
                                ui.icon("query_stats").classes(
                                    "text-xl text-teal-400"
                                )
                                ui.label("Sales overview").classes(
                                    "font-bold mt-2"
                                )
                                ui.label(
                                    "Get a quick sales overview."
                                ).classes("text-sm muted")

                        # Important: save the question whenever it changes.
                        question_input = ui.textarea(
                            placeholder=(
                                "Ask a question about your data..."
                            ),
                            value="",
                            on_change=lambda event: set_current_question(
                                event.value
                            ),
                        ).props(
                            "outlined autogrow"
                        ).classes("w-full mt-4")

                        UI["question"] = question_input

                        with ui.row().classes(
                            "w-full items-center justify-between mt-2"
                        ):
                            ui.label(
                                "Local AI · Read-only query execution"
                            ).classes("text-xs muted")

                            ui.button(
                                "Analyse data",
                                icon="arrow_upward",
                                on_click=submit_question,
                            ).classes("primary-action")

                    results_container = ui.column().classes(
                        "w-full gap-4"
                    )
                    UI["results"] = results_container

                # DASHBOARD PAGE
                dashboard_page = ui.column().classes("w-full gap-5")

                with dashboard_page:
                    ui.label("Dashboard Studio").classes(
                        "text-3xl font-bold"
                    )

                    ui.label(
                        "Create visualizations only when you need them."
                    ).classes("muted")

                    with ui.card().classes("studio-card w-full"):
                        ui.icon("bar_chart").classes(
                            "text-2xl text-teal-400"
                        )

                        ui.label("Build a dashboard").classes(
                            "text-lg font-bold mt-2"
                        )

                        ui.label(
                            "Generate metrics and charts from the "
                            "sample sales database."
                        ).classes("muted")

                        ui.button(
                            "Create dashboard",
                            icon="auto_graph",
                            on_click=render_dashboard,
                        ).classes("primary-action mt-3")

                    dashboard_content = ui.column().classes(
                        "w-full gap-4"
                    )
                    UI["dashboard_content"] = dashboard_content

                # DATA SOURCES PAGE
                data_page = ui.column().classes("w-full gap-5")

                with data_page:
                    ui.label("Data sources").classes(
                        "text-3xl font-bold"
                    )

                    ui.label(
                        "Inspect the connected dataset."
                    ).classes("muted")

                    with ui.card().classes("studio-card w-full"):
                        ui.icon("database").classes(
                            "text-2xl text-teal-400"
                        )

                        ui.label(
                            "Sample sales database"
                        ).classes("text-lg font-bold mt-2")

                        ui.label(
                            "Connected from data/sales.db"
                        ).classes("muted")

                        ui.button(
                            "Refresh schema",
                            icon="refresh",
                            on_click=render_schema,
                        ).props(
                            "outline color=teal"
                        ).classes("mt-3")

                        ui.separator().classes("my-4")

                        ui.label("Upload CSV / Excel").classes(
                            "text-lg font-bold"
                        )

                        ui.label(
                            "File upload and querying of uploaded "
                            "datasets are not implemented yet."
                        ).classes("muted")

                # SETTINGS PAGE
                settings_page = ui.column().classes("w-full gap-5")

                with settings_page:
                    ui.label("Settings").classes("text-3xl font-bold")
                    ui.label(
                        "Application preferences"
                    ).classes("muted")

                    with ui.card().classes("studio-card w-full"):
                        ui.label("AI provider").classes(
                            "text-lg font-bold"
                        )
                        ui.label(
                            "Ollama · qwen2.5:3b · Local inference"
                        ).classes("muted")

                        ui.separator().classes("my-3")

                        ui.label("Database access").classes(
                            "text-lg font-bold"
                        )
                        ui.label(
                            "SQLite sample database · Read-only mode"
                        ).classes("muted")

                        ui.separator().classes("my-3")

                        ui.label("Appearance").classes(
                            "text-lg font-bold"
                        )
                        ui.label(
                            "Use the theme switch in the top bar."
                        ).classes("muted")

                # PROFILE PAGE
                profile_page = ui.column().classes("w-full gap-5")

                with profile_page:
                    ui.label("Profile").classes("text-3xl font-bold")
                    ui.label(
                        "Local application profile"
                    ).classes("muted")

                    with ui.card().classes("studio-card w-full"):
                        with ui.row().classes("items-center gap-4"):
                            ui.avatar(
                                icon="person",
                                color="teal",
                                text_color="white",
                            )

                            with ui.column().classes("gap-1"):
                                ui.label("Local user").classes(
                                    "text-xl font-bold"
                                )
                                ui.label(
                                    "ClarifySQL workspace"
                                ).classes("muted")

                        ui.separator().classes("my-3")

                        ui.label(
                            "Authentication and registered user accounts "
                            "are not implemented in this prototype."
                        ).classes("muted")

                # Register page panels and navigation buttons.
                UI["pages"] = {
                    "chat": chat_page,
                    "dashboard": dashboard_page,
                    "data": data_page,
                    "settings": settings_page,
                    "profile": profile_page,
                }

                UI["nav_buttons"] = {
                    "chat": chat_button,
                    "dashboard": dashboard_button,
                    "data": data_button,
                    "settings": settings_button,
                    "profile": profile_button,
                }

                UI["page_title"] = page_title

                dashboard_page.set_visibility(False)
                data_page.set_visibility(False)
                settings_page.set_visibility(False)
                profile_page.set_visibility(False)


# =========================================================
# 14. START APPLICATION
# =========================================================

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        title="ClarifySQL | Data Intelligence Studio",
        host="127.0.0.1",
        port=8080,
        reload=False,
        dark=True,
    )