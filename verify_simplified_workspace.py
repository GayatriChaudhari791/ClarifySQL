import requests
import re

BASE_URL = "http://127.0.0.1:8000"

def test_simplified_workspace():
    print("=" * 60)
    print("VERIFYING SIMPLIFIED WORKSPACE & THREE-DOT CONVERSATION MENU")
    print("=" * 60)

    # 1. Inspect chatbot.html
    print("\n[1/5] Checking chatbot.html for simplified navigation...")
    r_chat = requests.get(f"{BASE_URL}/frontend/chatbot.html")
    assert r_chat.status_code == 200, f"chatbot.html failed: {r_chat.status_code}"
    chat_html = r_chat.text

    # Must NOT have dashboard elements
    assert "sidebarDashboardLink" not in chat_html, "Found leftover sidebarDashboardLink in chatbot.html"
    assert "topbarDashboardBtn" not in chat_html, "Found leftover topbarDashboardBtn in chatbot.html"
    assert "dashboard.html" not in chat_html, "Found leftover link to dashboard.html in chatbot.html"

    # MUST have Visualizations navigation and Visualize result action
    assert 'id="sidebarVisualizationsLink"' in chat_html, "Missing sidebarVisualizationsLink in chatbot.html"
    assert 'id="topbarVisualizationsBtn"' in chat_html, "Missing topbarVisualizationsBtn in chatbot.html"
    assert 'id="visualizeResultBtn"' in chat_html, "Missing visualizeResultBtn in chatbot.html"

    # MUST have three-dot menu and modal elements
    assert 'id="historyDropdownMenu"' in chat_html, "Missing historyDropdownMenu in chatbot.html"
    assert 'id="historyMenuRename"' in chat_html, "Missing historyMenuRename in chatbot.html"
    assert 'id="historyMenuPin"' in chat_html, "Missing historyMenuPin in chatbot.html"
    assert 'id="historyMenuDelete"' in chat_html, "Missing historyMenuDelete in chatbot.html"
    assert 'id="deleteModal"' in chat_html, "Missing deleteModal in chatbot.html"
    assert 'id="confirmDeleteBtn"' in chat_html, "Missing confirmDeleteBtn in chatbot.html"
    assert 'id="cancelDeleteBtn"' in chat_html, "Missing cancelDeleteBtn in chatbot.html"
    print("PASS: chatbot.html successfully cleaned of dashboard links while keeping visualizations and three-dot menu!")

    # 2. Inspect visualization.html
    print("\n[2/5] Checking visualization.html for simplified workspace...")
    r_viz = requests.get(f"{BASE_URL}/frontend/visualization.html")
    assert r_viz.status_code == 200, f"visualization.html failed: {r_viz.status_code}"
    viz_html = r_viz.text

    # Must NOT have dashboard items
    assert "navDashboardLink" not in viz_html, "Found leftover navDashboardLink in visualization.html"
    assert "addToDashboardBtn" not in viz_html, "Found leftover addToDashboardBtn in visualization.html"
    assert "addToDashboardModal" not in viz_html, "Found leftover addToDashboardModal in visualization.html"
    assert "dashboard.html" not in viz_html, "Found leftover dashboard.html in visualization.html"

    # MUST have chart tabs, export, inspector table, summary cards
    assert 'id="topbarBackBtn"' in viz_html, "Missing topbarBackBtn in visualization.html"
    assert 'id="navChatbotLink"' in viz_html, "Missing navChatbotLink in visualization.html"
    assert 'id="downloadChartBtn"' in viz_html, "Missing downloadChartBtn in visualization.html"
    assert 'id="vizCanvas"' in viz_html, "Missing vizCanvas in visualization.html"
    assert 'id="summaryCards"' in viz_html, "Missing summaryCards in visualization.html"
    assert 'id="inspectorTable"' in viz_html, "Missing inspectorTable in visualization.html"
    print("PASS: visualization.html successfully simplified with no dashboard elements and full visualizer controls intact!")

    # 3. Inspect chatbot.css for three-dot menu visibility and positioning
    print("\n[3/5] Inspecting chatbot.css for three-dot menu visibility & styling...")
    r_css = requests.get(f"{BASE_URL}/frontend/chatbot.css")
    assert r_css.status_code == 200
    css_text = r_css.text

    # Check .history-menu-trigger styles
    trigger_match = re.search(r'\.history-menu-trigger\s*\{([^}]+)\}', css_text)
    assert trigger_match, "Could not find .history-menu-trigger in chatbot.css"
    trigger_rules = trigger_match.group(1)
    assert "opacity: 0.75" in trigger_rules or "opacity: 0.8" in trigger_rules or "opacity: 1" in trigger_rules, (
        f".history-menu-trigger must have visible opacity by default, got: {trigger_rules}"
    )
    assert "pointer-events: auto" in trigger_rules, ".history-menu-trigger must have pointer-events: auto"
    assert "flex-shrink: 0" in trigger_rules, ".history-menu-trigger must have flex-shrink: 0"

    # Check .history-dropdown-menu styles
    menu_match = re.search(r'\.history-dropdown-menu\s*\{([^}]+)\}', css_text)
    assert menu_match, "Could not find .history-dropdown-menu in chatbot.css"
    menu_rules = menu_match.group(1)
    assert "position: fixed" in menu_rules, ".history-dropdown-menu must be position: fixed"
    assert "z-index: 99999" in menu_rules, ".history-dropdown-menu must have high z-index"
    print("PASS: chatbot.css guarantees that three-dot menu trigger is visible by default (opacity: 0.75), clickable, and fixed-positioned!")

    # 4. Inspect chatbot.js and visualization.js for clean bindings
    print("\n[4/5] Checking chatbot.js & visualization.js code integrity...")
    r_cjs = requests.get(f"{BASE_URL}/frontend/chatbot.js")
    assert r_cjs.status_code == 200
    cjs_text = r_cjs.text

    assert "sidebarDashboardLink" not in cjs_text
    assert "topbarDashboardBtn" not in cjs_text
    assert "dashboard.html" not in cjs_text
    assert "toggleHistoryDropdown" in cjs_text
    assert "renameConversation" in cjs_text
    assert "togglePinConversation" in cjs_text
    assert "confirmDeleteConversation" in cjs_text

    r_vjs = requests.get(f"{BASE_URL}/frontend/visualization.js")
    assert r_vjs.status_code == 200
    vjs_text = r_vjs.text
    assert "addToDashboardBtn" not in vjs_text
    assert "targetDashboardSelect" not in vjs_text
    assert "dashboard.html" not in vjs_text
    print("PASS: chatbot.js and visualization.js are free of dashboard logic with clean conversation menu bindings!")

    # 5. Live API test for conversation lifecycle: create, rename, pin, delete
    print("\n[5/5] Testing full conversation menu lifecycle via API...")
    # Create
    conv = requests.post(f"{BASE_URL}/conversations", json={"title": "Test Menu Flow"}).json()
    cid = conv["id"]
    assert conv["title"] == "Test Menu Flow"

    # Rename
    renamed = requests.patch(f"{BASE_URL}/conversations/{cid}", json={"title": "Renamed Flow"}).json()
    assert renamed["title"] == "Renamed Flow"
    assert renamed["is_custom_title"] is True

    # Pin
    pinned = requests.patch(f"{BASE_URL}/conversations/{cid}", json={"is_pinned": True}).json()
    assert pinned["is_pinned"] is True

    # Delete
    del_res = requests.delete(f"{BASE_URL}/conversations/{cid}")
    assert del_res.status_code == 200
    get_res = requests.get(f"{BASE_URL}/conversations/{cid}")
    assert get_res.status_code == 404
    print("PASS: Full conversation menu lifecycle (Create, Rename, Pin, Delete) works reliably!")

    print("\n" + "=" * 60)
    print("ALL SIMPLIFIED WORKSPACE & MENU VERIFICATION TESTS PASSED!")
    print("=" * 60)

if __name__ == "__main__":
    test_simplified_workspace()
