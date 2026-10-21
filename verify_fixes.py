import io
import json
import requests

BASE_URL = "http://127.0.0.1:8000"

def run_focused_verification():
    print("=" * 60)
    print("RUNNING FOCUSED CLARIFYSQL VERIFICATION")
    print("=" * 60)

    # Check /health
    health = requests.get(f"{BASE_URL}/health").json()
    assert health.get("status") == "ok", f"Health check failed: {health}"
    print("[1/6] Health check OK:", health)

    # 1. Test Seller-Only Dataset (olist_sellers_dataset.csv)
    print("\n[2/6] Testing Seller-Only Dataset with 'Show me the best sellers'")
    seller_dataset_id = "19c7a0271f8c4a7096f97f7649920c0a" # olist_sellers_dataset.csv
    conv_seller = requests.post(f"{BASE_URL}/conversations", json={"title": "Seller Only Test", "dataset_id": seller_dataset_id, "dataset_name": "olist_sellers_dataset.csv"}).json()
    conv_seller_id = conv_seller["id"]

    query_resp1 = requests.post(f"{BASE_URL}/query", json={
        "dataset_id": seller_dataset_id,
        "question": "Show me the best sellers",
        "conversation_id": conv_seller_id
    })
    assert query_resp1.status_code == 200, query_resp1.text
    data1 = query_resp1.json()

    print("Response for 'Show me the best sellers' on seller-only dataset:")
    print("  Clarification text:", data1.get("clarification"))
    print("  Options:", [o["label"] for o in data1.get("options", [])])

    assert data1.get("clarification"), "Must return clarification"
    assert "sales" in data1.get("clarification").lower() or "performance" in data1.get("clarification").lower(), "Clarification must explain that performance/sales data is not available"
    # Ensure options DO NOT contain revenue, order, price, or payment
    for opt in data1.get("options", []):
        lbl = opt["label"].lower()
        assert not any(forbidden in lbl for forbidden in ["revenue", "order", "price", "payment", "profit"]), f"Hallucinated option found: {opt['label']}"
    assert len(data1.get("options", [])) >= 2, "Must return at least 2 valid alternatives"
    print("PASS: Seller-only dataset correctly rejected unsupported revenue/order rankings and offered valid schema-grounded alternatives!")

    # 2. Test selecting an option on seller-only dataset
    print("\n[3/6] Testing Option Selection on Seller-Only Dataset")
    chosen_opt = data1["options"][0] # e.g. "Group sellers by seller city" or "Group sellers by seller state"
    print(f"Selecting option: {chosen_opt['label']}")
    resolve_resp = requests.post(f"{BASE_URL}/query", json={
        "dataset_id": seller_dataset_id,
        "question": chosen_opt["label"],
        "conversation_id": conv_seller_id,
        "original_question": "Show me the best sellers",
        "selected_option_id": chosen_opt["id"],
        "selected_option_label": chosen_opt["label"]
    })
    assert resolve_resp.status_code == 200, resolve_resp.text
    res_data = resolve_resp.json()
    assert res_data.get("sql"), "Must return executed SQL"
    assert "uploaded_data" in res_data["sql"]
    assert res_data.get("rows") is not None
    print("PASS: Selected option resolved to valid SQL:", res_data["sql"])
    print("Rows returned:", len(res_data["rows"]))

    # 3. Test Dataset WITH Sales Columns
    print("\n[4/6] Testing Dataset WITH Sales/Revenue Columns")
    sales_csv = (
        "seller_id,seller_city,seller_state,order_id,price,total_sales_revenue\n"
        "s1,campinas,SP,ord_1,29.90,299.00\n"
        "s2,curitiba,PR,ord_2,89.90,899.00\n"
        "s1,campinas,SP,ord_3,19.90,199.00\n"
        "s3,rio de janeiro,RJ,ord_4,149.90,1499.00\n"
    )
    conv_sales = requests.post(f"{BASE_URL}/conversations", json={"title": "Sales Dataset Test"}).json()
    conv_sales_id = conv_sales["id"]
    upload_sales = requests.post(
        f"{BASE_URL}/upload",
        files={"file": ("sales_test.csv", io.BytesIO(sales_csv.encode("utf-8")), "text/csv")},
        data={"conversation_id": conv_sales_id}
    ).json()
    sales_dataset_id = upload_sales["dataset_id"]

    query_resp2 = requests.post(f"{BASE_URL}/query", json={
        "dataset_id": sales_dataset_id,
        "question": "Show me the best sellers",
        "conversation_id": conv_sales_id
    })
    assert query_resp2.status_code == 200, query_resp2.text
    data2 = query_resp2.json()
    print("Response for 'Show me the best sellers' on dataset with sales columns:")
    print("  Clarification text:", data2.get("clarification"))
    print("  Options:", [o["label"] for o in data2.get("options", [])])
    assert data2.get("options") and len(data2.get("options")) >= 2
    # Verify that ranking options DO appear when columns exist
    has_ranking_opt = any(any(m in opt["label"].lower() for m in ["revenue", "order", "price", "sale"]) for opt in data2["options"])
    assert has_ranking_opt, "Dataset with sales columns must offer ranking options"
    print("PASS: Dataset with sales columns offered valid supported ranking options!")

    # 4. Test Clear Question Execution
    print("\n[5/6] Testing Clear Question Flow")
    clear_resp = requests.post(f"{BASE_URL}/query", json={
        "dataset_id": sales_dataset_id,
        "question": "Show the first 2 rows",
        "conversation_id": conv_sales_id
    })
    assert clear_resp.status_code == 200, clear_resp.text
    clear_data = clear_resp.json()
    assert "clarification" not in clear_data
    assert "sql" in clear_data and "LIMIT 2" in clear_data["sql"]
    assert len(clear_data["rows"]) == 2
    print("PASS: Clear question executed directly without clarification. SQL:", clear_data["sql"])

    # 5. Test Persistence & SQL Safety
    print("\n[6/6] Testing Persistence and SQL Safety")
    # Persistence check
    conv_detail = requests.get(f"{BASE_URL}/conversations/{conv_seller_id}").json()
    messages = conv_detail.get("messages", [])
    assert len(messages) >= 3, f"Expected at least 3 messages, got {len(messages)}"
    clarif_msg = next((m for m in messages if m.get("clarification_options")), None)
    assert clarif_msg is not None, "Clarification message with options must persist in SQLite"
    print("PASS: Conversation history and clarification options persisted correctly in SQLite.")

    # SQL Safety check (SQL injection / write attempts)
    bad_resp = requests.post(f"{BASE_URL}/query", json={
        "dataset_id": sales_dataset_id,
        "question": "DROP TABLE uploaded_data",
        "conversation_id": conv_sales_id
    })
    assert bad_resp.status_code in [400, 422], f"Expected 422/400 for unsafe query, got {bad_resp.status_code}"
    print("PASS: SQL safety checks successfully rejected unsafe operation.")

    print("\n" + "=" * 60)
    print("ALL FOCUSED VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    run_focused_verification()
