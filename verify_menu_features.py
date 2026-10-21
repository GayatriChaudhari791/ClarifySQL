import requests
import sqlite3

BASE_URL = "http://127.0.0.1:8000"

def test_menu_api_and_persistence():
    print("=" * 60)
    print("VERIFYING THREE-DOT CONVERSATION MENU & PERSISTENCE")
    print("=" * 60)

    # 1. Create a fresh conversation
    print("\n[1/5] Testing Conversation Creation & Initial State...")
    res = requests.post(f"{BASE_URL}/conversations", json={}).json()
    conv_id = res["id"]
    assert res["title"] == "New conversation"
    assert res.get("is_pinned") is False
    assert res.get("is_custom_title") is False
    print("PASS: Conversation created with is_pinned=False, is_custom_title=False.")

    # 2. Test Rename & Auto-Title Protection
    print("\n[2/5] Testing Rename & Auto-Title Overwrite Protection...")
    patch_res = requests.patch(f"{BASE_URL}/conversations/{conv_id}", json={"title": "Q3 Seller Performance Analysis"}).json()
    assert patch_res["title"] == "Q3 Seller Performance Analysis"
    assert patch_res["is_custom_title"] is True
    print("PASS: Title updated to 'Q3 Seller Performance Analysis', is_custom_title set to True.")

    # Fetch conversation to confirm persistence
    get_res = requests.get(f"{BASE_URL}/conversations/{conv_id}").json()
    assert get_res["title"] == "Q3 Seller Performance Analysis"
    assert get_res["is_custom_title"] is True

    # Send a user message and verify auto-title does NOT overwrite the custom title
    msg_res = requests.post(f"{BASE_URL}/conversations/{conv_id}/messages", json={
        "role": "user",
        "content": "Where are most sellers located in this state?"
    }).json()
    get_after_msg = requests.get(f"{BASE_URL}/conversations/{conv_id}").json()
    assert get_after_msg["title"] == "Q3 Seller Performance Analysis", f"Expected custom title preserved, got: {get_after_msg['title']}"
    print("PASS: Auto-title generation did NOT overwrite the user's custom title!")

    # 3. Test Pin / Unpin & Ordering
    print("\n[3/5] Testing Pin / Unpin & Ordering...")
    # Create another unpinned conversation
    conv2 = requests.post(f"{BASE_URL}/conversations", json={"title": "Unpinned Older Chat"}).json()
    conv2_id = conv2["id"]

    # Pin the first conversation
    pin_res = requests.patch(f"{BASE_URL}/conversations/{conv_id}", json={"is_pinned": True}).json()
    assert pin_res["is_pinned"] is True
    print("PASS: Conversation pinned successfully.")

    # Fetch conversation list and verify pinned conversation is first
    list_res = requests.get(f"{BASE_URL}/conversations").json()
    pinned_ids = [c["id"] for c in list_res if c["is_pinned"]]
    assert conv_id in pinned_ids
    assert list_res[0]["id"] == conv_id, f"Expected pinned conversation to be first, got: {list_res[0]['id']}"
    print(f"PASS: Pinned conversation {conv_id} appears first in /conversations list.")

    # Unpin the conversation
    unpin_res = requests.patch(f"{BASE_URL}/conversations/{conv_id}", json={"is_pinned": False}).json()
    assert unpin_res["is_pinned"] is False
    print("PASS: Conversation unpinned successfully.")

    # 4. Test Deletion of Conversation and Messages
    print("\n[4/5] Testing Conversation & Cascaded Messages Deletion...")
    del_res = requests.delete(f"{BASE_URL}/conversations/{conv_id}")
    assert del_res.status_code == 200, del_res.text
    assert del_res.json()["status"] == "deleted"

    # Verify conversation is gone from API
    get_del = requests.get(f"{BASE_URL}/conversations/{conv_id}")
    assert get_del.status_code == 404, "Deleted conversation should return 404"

    # Verify in SQLite directly that messages for this conversation are deleted
    conn = sqlite3.connect("data/conversations.db")
    c_count = conn.execute("SELECT COUNT(*) FROM conversations WHERE id = ?", (conv_id,)).fetchone()[0]
    m_count = conn.execute("SELECT COUNT(*) FROM messages WHERE conversation_id = ?", (conv_id,)).fetchone()[0]
    conn.close()
    assert c_count == 0, "Conversation record should be 0 in DB"
    assert m_count == 0, "Messages for deleted conversation should be 0 in DB"
    print("PASS: Conversation and associated messages completely removed.")

    # Clean up conv2
    requests.delete(f"{BASE_URL}/conversations/{conv2_id}")

    # 5. Test Non-existent Deletion Graceful Failure
    print("\n[5/5] Testing Non-existent Conversation Deletion (404)...")
    fake_id = "0123456789abcdef0123456789abcdef"
    fake_del = requests.delete(f"{BASE_URL}/conversations/{fake_id}")
    assert fake_del.status_code == 404
    print("PASS: Deleting non-existent conversation returns 404 error cleanly.")

    print("\n" + "=" * 60)
    print("ALL THREE-DOT MENU API TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    test_menu_api_and_persistence()
