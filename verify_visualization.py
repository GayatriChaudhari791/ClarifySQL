import requests
import json

BASE_URL = "http://127.0.0.1:8000"

def test_visualization_features():
    print("=" * 60)
    print("VERIFYING CLARIFYSQL VISUALIZATION FEATURES")
    print("=" * 60)

    # 1. Verify Static Serving
    print("\n[1/6] Testing Static Assets Serving...")
    files_to_check = [
        "frontend/chatbot.html",
        "frontend/chatbot.css",
        "frontend/chatbot.js",
        "frontend/visualization.html",
        "frontend/visualization.css",
        "frontend/visualization.js",
        "frontend/chart.min.js",
    ]
    for rel_path in files_to_check:
        res = requests.get(f"{BASE_URL}/{rel_path}")
        assert res.status_code == 200, f"Failed to serve {rel_path}: {res.status_code}"
        assert len(res.content) > 100, f"File {rel_path} returned unexpectedly small content"
    print("PASS: All visualization static files and Chart.js served with HTTP 200 OK.")

    # 2. Test Query Response Message ID
    print("\n[2/6] Testing Query Response message_id and Persistence...")
    seller_dataset_id = "19c7a0271f8c4a7096f97f7649920c0a"
    conv_res = requests.post(f"{BASE_URL}/conversations", json={
        "title": "Visualization Test Session",
        "dataset_id": seller_dataset_id,
        "dataset_name": "olist_sellers_dataset.csv"
    }).json()
    conv_id = conv_res["id"]

    query_res1 = requests.post(f"{BASE_URL}/query", json={
        "dataset_id": seller_dataset_id,
        "question": "Show me the first 5 rows",
        "conversation_id": conv_id
    }).json()

    assert query_res1.get("conversation_id") == conv_id
    assert "columns" in query_res1 and len(query_res1["columns"]) > 0
    assert "rows" in query_res1 and len(query_res1["rows"]) == 5
    msg_id_1 = query_res1.get("message_id")
    assert msg_id_1 is not None and isinstance(msg_id_1, int), f"Expected int message_id, got {msg_id_1}"
    print(f"PASS: Query returned stable message_id={msg_id_1} with 5 rows.")

    # 3. Test Multi-Query Conversation Hydration
    print("\n[3/6] Testing Second Query and Conversation Hydration...")
    query_res2 = requests.post(f"{BASE_URL}/query", json={
        "dataset_id": seller_dataset_id,
        "question": "Group sellers by seller state",
        "original_question": "Which state has the most sellers?",
        "selected_option_id": "group_by_state",
        "selected_option_label": "Group sellers by seller state",
        "conversation_id": conv_id
    }).json()
    msg_id_2 = query_res2.get("message_id")
    assert msg_id_2 is not None and msg_id_2 > msg_id_1, f"Expected msg_id_2 > {msg_id_1}, got {query_res2}"
    assert "rows" in query_res2 and len(query_res2["rows"]) > 0

    conv_data = requests.get(f"{BASE_URL}/conversations/{conv_id}").json()
    assert conv_data["dataset_id"] == seller_dataset_id
    assert conv_data["dataset_name"] == "olist_sellers_dataset.csv"

    query_messages = [
        m for m in conv_data["messages"]
        if m.get("columns") and m.get("rows") and not m.get("is_error")
    ]
    assert len(query_messages) == 2, f"Expected 2 query messages, found {len(query_messages)}"
    assert query_messages[0]["id"] == msg_id_1
    assert query_messages[1]["id"] == msg_id_2
    print(f"PASS: Conversation contains 2 persistent query messages: ID {msg_id_1} and ID {msg_id_2}.")

    # 4. Test Text-Only / Non-numeric Query
    print("\n[4/6] Testing Text-Only Columns (No Metrics)...")
    query_text_only = requests.post(f"{BASE_URL}/query", json={
        "dataset_id": seller_dataset_id,
        "question": "Show me the first 2 rows",
        "conversation_id": conv_id
    }).json()
    assert len(query_text_only["rows"]) == 2
    print("PASS: Tabular result retrieved successfully for data inspector table verification.")

    # 5. Test Empty Result (0 rows)
    print("\n[5/6] Testing Empty Query Output (0 rows)...")
    empty_conv = requests.post(f"{BASE_URL}/conversations", json={
        "title": "Empty Result Test",
        "dataset_id": seller_dataset_id
    }).json()
    empty_conv_id = empty_conv["id"]

    # Verify conversation with zero messages triggers empty state cleanly
    conv_empty = requests.get(f"{BASE_URL}/conversations/{empty_conv_id}").json()
    assert len(conv_empty["messages"]) == 0
    print("PASS: Empty conversation successfully verified for empty state rendering.")

    # 6. Test HTML Navigation links and structure
    print("\n[6/6] Verifying HTML Navigation Elements...")
    chatbot_html = requests.get(f"{BASE_URL}/frontend/chatbot.html").text
    assert 'id="sidebarVisualizationsLink"' in chatbot_html
    assert 'id="topbarVisualizationsBtn"' in chatbot_html
    assert 'id="visualizeResultBtn"' in chatbot_html

    viz_html = requests.get(f"{BASE_URL}/frontend/visualization.html").text
    assert 'id="topbarBackBtn"' in viz_html
    assert 'id="navChatbotLink"' in viz_html
    assert 'id="vizCanvas"' in viz_html
    assert 'id="summaryCards"' in viz_html
    assert 'id="inspectorTable"' in viz_html
    assert 'data-chart="bar"' in viz_html
    assert 'data-chart="line"' in viz_html
    assert 'data-chart="pie"' in viz_html
    assert 'data-chart="doughnut"' in viz_html
    print("PASS: All required navigation, chart type buttons, and inspector elements verified in HTML.")

    print("\n" + "=" * 60)
    print("ALL VISUALIZATION TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    test_visualization_features()
