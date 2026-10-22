import requests
import subprocess
import json

BASE_URL = "http://127.0.0.1:8000"

def test_74_row_visualization():
    print("=" * 60)
    print("VERIFYING 74-ROW QUERY VISUALIZATION & TABLE RENDERING")
    print("=" * 60)

    # 1. Create a conversation with a 74-row result message
    print("\n[1/4] Creating conversation with 74 rows in SQLite...")
    conv = requests.post(f"{BASE_URL}/conversations", json={"title": "74 Rows Regression Test"}).json()
    conv_id = conv["id"]

    # Generate 74 mock rows
    rows_74 = [[f"State_{i+1:02d}", (i + 1) * 15.5] for i in range(74)]
    cols = ["seller_state", "total_sales"]

    # Post user question and assistant message with 74 rows
    requests.post(f"{BASE_URL}/conversations/{conv_id}/messages", json={
        "role": "user",
        "content": "Show sales across all 74 states/regions"
    })

    msg_resp = requests.post(f"{BASE_URL}/conversations/{conv_id}/messages", json={
        "role": "assistant",
        "content": "Here is the sales breakdown across 74 regions.",
        "sql": "SELECT seller_state, total_sales FROM uploaded_data ORDER BY total_sales DESC",
        "columns": cols,
        "rows": rows_74
    }).json()

    msg_id = msg_resp["id"]
    print(f"PASS: Conversation {conv_id} created with message ID {msg_id} containing {len(rows_74)} rows.")

    # 2. Verify backend returns all 74 rows accurately
    print("\n[2/4] Verifying backend retrieves all 74 rows...")
    conv_fetch = requests.get(f"{BASE_URL}/conversations/{conv_id}").json()
    saved_msg = next((m for m in conv_fetch["messages"] if m["id"] == msg_id), None)
    assert saved_msg is not None, "Message not found in conversation"
    assert len(saved_msg["rows"]) == 74, f"Expected 74 rows, got {len(saved_msg['rows'])}"
    assert saved_msg["columns"] == ["seller_state", "total_sales"]
    print("PASS: Backend accurately preserved and retrieved all 74 rows.")

    # 3. Simulate frontend execution in Node.js with the actual visualization.js file
    print("\n[3/4] Running simulation of visualization.js with 74 rows...")
    node_test_script = f"""
    const fs = require('fs');
    const vm = require('vm');

    let summaryText = '';
    let inspectorText = '';
    let chartLabelsCount = 0;
    let chartDataCount = 0;

    const dummyEl = {{
        addEventListener: () => {{}},
        getContext: () => ({{}}),
        replaceChildren: () => {{}},
        appendChild: () => {{}},
        hidden: false,
        value: '0',
        textContent: '',
        set textContent(val) {{ this._text = val; }},
        get textContent() {{ return this._text || ''; }}
    }};

    const inspectorRowSummaryEl = {{
        _text: 'Showing 0 rows',
        addEventListener: () => {{}},
        set textContent(val) {{ this._text = val; inspectorText = val; }},
        get textContent() {{ return this._text; }}
    }};

    const summaryRowCountEl = {{
        _text: '',
        addEventListener: () => {{}},
        set textContent(val) {{ this._text = val; summaryText = val; }},
        get textContent() {{ return this._text; }}
    }};

    const selectEl = {{
        value: '0',
        replaceChildren: () => {{}},
        appendChild: () => {{}},
        addEventListener: () => {{}}
    }};

    const context = {{
        document: {{
            addEventListener: () => {{}},
            getElementById: (id) => {{
                if (id === 'inspectorRowSummary') return inspectorRowSummaryEl;
                if (id === 'summaryRowCount') return summaryRowCountEl;
                if (id === 'tableSearchInput') return {{ value: '', addEventListener: () => {{}} }};
                if (id === 'labelColSelect') return {{ value: '0', replaceChildren: () => {{}}, appendChild: () => {{}}, addEventListener: () => {{}} }};
                if (id === 'metricColSelect') return {{ value: '1', replaceChildren: () => {{}}, appendChild: () => {{}}, addEventListener: () => {{}} }};
                if (id === 'sortSelect') return {{ value: 'desc', addEventListener: () => {{}} }};
                if (id === 'limitSelect') return {{ value: 'all', addEventListener: () => {{}} }};
                return dummyEl;
            }},
            querySelectorAll: () => [],
            createElement: () => ({{ appendChild: () => {{}}, className: '', textContent: '' }})
        }},
        window: {{ addEventListener: () => {{}} }},
        Chart: class MockChart {{
            constructor(ctx, config) {{
                chartLabelsCount = config.data.labels.length;
                chartDataCount = config.data.datasets[0].data.length;
            }}
            destroy() {{}}
        }},
        console: console,
        sessionStorage: {{ getItem: () => null, setItem: () => {{}} }},
        URLSearchParams: class MockParams {{ get() {{ return null; }} }}
    }};

    vm.createContext(context);
    const code = fs.readFileSync('frontend/visualization.js', 'utf8');
    vm.runInContext(code, context);

    const mockQuery = {{
        id: {msg_id},
        question: 'Show sales across all 74 states/regions',
        sql: 'SELECT seller_state, total_sales FROM uploaded_data',
        columns: {json.dumps(cols)},
        rows: {json.dumps(rows_74)}
    }};

    vm.runInContext(`
        availableQueries = [${{JSON.stringify(mockQuery)}}];
        selectedQueryIndex = 0;
        renderActiveQuery();
    `, context);

    console.log(JSON.stringify({{
        summaryRowCount: summaryText,
        inspectorRowSummary: inspectorText,
        chartLabelsCount: chartLabelsCount,
        chartDataCount: chartDataCount
    }}));
    """

    res = subprocess.run(["node", "-e", node_test_script], capture_output=True, text=True, check=True)
    out = json.loads(res.stdout.strip())
    print("Simulation Output:", out)

    assert out["summaryRowCount"] == "74", f"Expected KPI row count '74', got: {out['summaryRowCount']}"
    assert "74" in out["inspectorRowSummary"], f"Expected 74 rows in inspector, got: {out['inspectorRowSummary']}"
    assert out["chartLabelsCount"] == 74, f"Expected 74 chart labels, got: {out['chartLabelsCount']}"
    assert out["chartDataCount"] == 74, f"Expected 74 chart data points, got: {out['chartDataCount']}"
    print("PASS: KPI cards show 74, data table shows all 74 rows, and chart plots all 74 points without any error!")

    # 4. Clean up test conversation
    print("\n[4/4] Cleaning up test conversation...")
    requests.delete(f"{BASE_URL}/conversations/{conv_id}")
    print("PASS: Cleanup complete.")

    print("\n" + "=" * 60)
    print("ALL 74-ROW VISUALIZATION REGRESSION TESTS PASSED!")
    print("=" * 60)

if __name__ == "__main__":
    test_74_row_visualization()
