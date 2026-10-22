import io
import json
import requests

BASE_URL = "http://127.0.0.1:8000"

def test_all():
    print("=" * 70)
    print("RUNNING VERIFICATION FOR ISSUE 1 (>500 ROWS / DATE GROUPING) AND ISSUE 2 (100 MB UPLOAD)")
    print("=" * 70)

    # 0. Health check
    health = requests.get(f"{BASE_URL}/health").json()
    assert health.get("status") == "ok"
    print("\n[Step 0] Health check OK:", health)

    # =========================================================================
    # PART 1: ISSUE 1 - Clarification Flow and Date Grouping on Olist Orders
    # =========================================================================
    print("\n" + "=" * 50)
    print("PART 1: Testing Issue 1 - Date Grouping and Row Safeguards")
    print("=" * 50)

    olist_dataset_id = "347678cc24b14a10842df6bc7c76b4bd"
    conv_res = requests.post(f"{BASE_URL}/conversations", json={
        "title": "Olist Orders Date Test",
        "dataset_id": olist_dataset_id,
        "dataset_name": "olist_orders_dataset.csv"
    }).json()
    conv_id = conv_res["id"]
    print(f"Created conversation {conv_id} on Olist orders dataset.")

    # 1.1 Clarification question asking how to group orders
    print("\n[1.1] Testing clarification for ambiguous order grouping question...")
    q1_resp = requests.post(f"{BASE_URL}/query", json={
        "dataset_id": olist_dataset_id,
        "question": "How would you like to group the orders?",
        "conversation_id": conv_id
    })
    assert q1_resp.status_code == 200, f"Query failed: {q1_resp.text}"
    q1_data = q1_resp.json()
    assert q1_data.get("clarification"), f"Expected clarification, got: {q1_data}"
    options = q1_data.get("options", [])
    print("Clarification text:", q1_data.get("clarification"))
    print("Options returned:")
    for o in options:
        print(f"  - [{o['id']}] {o['label']}")

    # Verify options contain meaningful periods (month or date) rather than raw timestamps
    has_meaningful_period = any(
        any(p in o["label"].lower() for p in ["month", "date", "day", "year"])
        for o in options
    )
    assert has_meaningful_period, "Clarification options must offer meaningful periods for date/time columns!"
    print("PASS [1.1]: Clarification options offer meaningful periods for date/time columns.")

    # 1.2 User selects 'Group by order purchase timestamp' (the exact bug scenario)
    print("\n[1.2] Testing resolution with exact user selection: 'Group by order purchase timestamp'...")
    q2_resp = requests.post(f"{BASE_URL}/query", json={
        "dataset_id": olist_dataset_id,
        "question": "Group by order purchase timestamp",
        "conversation_id": conv_id,
        "original_question": "How would you like to group the orders?",
        "selected_option_id": "group_by_order_purchase_timestamp",
        "selected_option_label": "Group by order purchase timestamp"
    })
    assert q2_resp.status_code == 200, f"Query failed unexpectedly: {q2_resp.status_code} - {q2_resp.text}"
    q2_data = q2_resp.json()
    print("SQL Generated:", q2_data.get("sql"))
    print("Rows returned:", len(q2_data.get("rows", [])))
    print("First 3 rows:", q2_data.get("rows", [])[:3])
    print("Message ID:", q2_data.get("message_id"))

    assert "strftime" in q2_data.get("sql").lower(), "SQL must use SQLite strftime date function!"
    assert len(q2_data.get("rows", [])) == 25, f"Expected 25 monthly rows, got {len(q2_data.get('rows', []))}"
    assert q2_data.get("message_id") is not None, "Must return message_id for visualization"
    print("PASS [1.2]: 'Group by order purchase timestamp' successfully aggregated by month using strftime without exceeding row limits!")

    # 1.3 User selects 'Group by date (order purchase timestamp)' (daily aggregation with 634 rows)
    print("\n[1.3] Testing daily aggregation with 634 rows (exceeds old 500 limit, within 2000 aggregate limit)...")
    q3_resp = requests.post(f"{BASE_URL}/query", json={
        "dataset_id": olist_dataset_id,
        "question": "Group by date (order purchase timestamp)",
        "conversation_id": conv_id,
        "original_question": "How would you like to group the orders?",
        "selected_option_id": "group_by_order_purchase_timestamp_date",
        "selected_option_label": "Group by date (order purchase timestamp)"
    })
    assert q3_resp.status_code == 200, f"Query failed unexpectedly: {q3_resp.status_code} - {q3_resp.text}"
    q3_data = q3_resp.json()
    print("SQL Generated:", q3_data.get("sql"))
    print("Rows returned:", len(q3_data.get("rows", [])))
    print("First 3 rows:", q3_data.get("rows", [])[:3])
    assert len(q3_data.get("rows", [])) == 634, f"Expected 634 daily rows, got {len(q3_data.get('rows', []))}"
    print("PASS [1.3]: Daily aggregation returned 634 rows successfully under the 2,000 aggregate limit!")

    # 1.4 Raw query exceeding raw limit (500 rows)
    print("\n[1.4] Testing raw query exceeding raw limit of 500 rows...")
    raw_resp = requests.post(f"{BASE_URL}/query", json={
        "dataset_id": olist_dataset_id,
        "question": "Show all order IDs",
        "conversation_id": conv_id,
        "original_question": "Show order IDs",
        "selected_option_label": "Show all order IDs"
    })
    assert raw_resp.status_code == 422, f"Expected 422 for raw query exceeding limit, got {raw_resp.status_code}: {raw_resp.text}"
    err_detail = raw_resp.json().get("detail", "")
    print("Error returned:", err_detail)
    assert "raw data" in err_detail.lower() and "500" in err_detail, f"Unexpected error message: {err_detail}"
    assert "narrow" in err_detail.lower() or "filter" in err_detail.lower(), "Must provide actionable next steps"
    print("PASS [1.4]: Raw query exceeding 500 rows returned informative error with actionable next steps.")

    # 1.5 Aggregate query exceeding aggregate limit (2,000 rows)
    print("\n[1.5] Testing aggregate query exceeding aggregate limit of 2,000 rows...")
    agg_resp = requests.post(f"{BASE_URL}/query", json={
        "dataset_id": olist_dataset_id,
        "question": "Group by customer id",
        "conversation_id": conv_id,
        "original_question": "How would you like to group the orders?",
        "selected_option_label": "Group by customer id"
    })
    assert agg_resp.status_code == 422, f"Expected 422 for aggregate query exceeding limit, got {agg_resp.status_code}: {agg_resp.text}"
    agg_detail = agg_resp.json().get("detail", "")
    print("Error returned:", agg_detail)
    assert "aggregate query returned more than 2,000 rows" in agg_detail.lower(), f"Unexpected error message: {agg_detail}"
    assert "broader time period" in agg_detail.lower() or "top results" in agg_detail.lower(), "Must provide actionable next steps"
    print("PASS [1.5]: Aggregate query exceeding 2,000 rows returned informative error with actionable next steps.")

    # =========================================================================
    # PART 2: ISSUE 2 - 100 MB Upload Limit
    # =========================================================================
    print("\n" + "=" * 50)
    print("PART 2: Testing Issue 2 - 100 MB Upload Limit")
    print("=" * 50)

    # 2.1 Uploading a 25 MB CSV file (previously failed with 20 MB limit, now succeeds)
    print("\n[2.1] Testing upload of a 25 MB CSV file...")
    # Generate ~25 MB CSV in-memory
    row_line = "item_12345,category_abc,99.95,2026-10-22 12:00:00,some descriptive text about the item\n"
    line_bytes = len(row_line.encode("utf-8"))
    num_rows = int((25 * 1024 * 1024) / line_bytes) + 100
    
    csv_header = "item_id,category,price,created_at,description\n"
    csv_content = (csv_header + (row_line * num_rows)).encode("utf-8")
    actual_mb = len(csv_content) / (1024 * 1024)
    print(f"Generated test CSV of size {actual_mb:.2f} MB ({len(csv_content):,} bytes)...")

    files = {"file": ("large_25mb_test.csv", io.BytesIO(csv_content), "text/csv")}
    upload_resp = requests.post(f"{BASE_URL}/upload", files=files)
    assert upload_resp.status_code == 200, f"Upload of 25MB file failed: {upload_resp.status_code} - {upload_resp.text}"
    upload_data = upload_resp.json()
    print("Upload succeeded! Dataset ID:", upload_data["dataset_id"])
    print("Row count:", upload_data["row_count"])
    print("Columns:", upload_data["columns"])
    print("Preview rows:", len(upload_data["preview"]))
    assert upload_data["dataset_id"], "Must return dataset_id"
    assert upload_data["row_count"] > 100000, "Must contain all uploaded rows"
    assert len(upload_data["preview"]) == 5, "Must return 5 preview rows"
    print("PASS [2.1]: 25 MB CSV file successfully uploaded, prepared in SQLite, and previewed!")

    # 2.2 Uploading a file exceeding 100 MB limit (e.g. 101 MB)
    print("\n[2.2] Testing upload rejection for file > 100 MB...")
    # Generate 101 MB dummy payload
    oversized_size = 101 * 1024 * 1024
    oversized_content = b"a" * oversized_size
    files_oversized = {"file": ("oversized_test.csv", io.BytesIO(oversized_content), "text/csv")}
    oversized_resp = requests.post(f"{BASE_URL}/upload", files=files_oversized)
    assert oversized_resp.status_code == 413, f"Expected HTTP 413, got {oversized_resp.status_code}: {oversized_resp.text}"
    over_err = oversized_resp.json().get("detail", "")
    print("Error returned:", over_err)
    assert "100 MB" in over_err, f"Error message should mention 100 MB: {over_err}"
    print("PASS [2.2]: File exceeding 100 MB was properly rejected with HTTP 413 and 'The file exceeds the 100 MB upload limit.'")

    # 2.3 Verify Excel support (XLSX)
    print("\n[2.3] Testing Excel (.xlsx) file upload...")
    import pandas as pd
    excel_io = io.BytesIO()
    df_excel = pd.DataFrame({
        "order_id": [f"ord_{i}" for i in range(20)],
        "revenue": [10.5 * i for i in range(20)],
        "status": ["completed" if i % 2 == 0 else "pending" for i in range(20)]
    })
    df_excel.to_excel(excel_io, index=False)
    excel_content = excel_io.getvalue()

    files_excel = {"file": ("test_data.xlsx", io.BytesIO(excel_content), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    excel_resp = requests.post(f"{BASE_URL}/upload", files=files_excel)
    assert excel_resp.status_code == 200, f"Excel upload failed: {excel_resp.text}"
    excel_data = excel_resp.json()
    print("Excel upload succeeded! Dataset ID:", excel_data["dataset_id"], "Rows:", excel_data["row_count"])
    assert excel_data["row_count"] == 20
    print("PASS [2.3]: Excel (.xlsx) file successfully uploaded and read into SQLite!")

    # 2.4 Verify frontend file check in chatbot.js
    print("\n[2.4] Verifying chatbot.js file size limit...")
    js_resp = requests.get(f"{BASE_URL}/frontend/chatbot.js")
    assert js_resp.status_code == 200
    js_text = js_resp.text
    assert "100 * 1024 * 1024" in js_text, "chatbot.js must check 100 MB limit"
    assert "under 100 MB" in js_text or "under ${MAX_UPLOAD_MB} MB" in js_text, "chatbot.js must show under 100 MB message"
    print("PASS [2.4]: Frontend chatbot.js verifies 100 MB file limit with consistent messaging.")

    print("\n" + "=" * 70)
    print("ALL TESTS FOR ISSUE 1 AND ISSUE 2 PASSED SUCCESSFULLY!")
    print("=" * 70)

if __name__ == "__main__":
    test_all()
