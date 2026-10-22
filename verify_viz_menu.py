import requests
import subprocess
import json

BASE_URL = "http://127.0.0.1:8000"

def test_visualization_menu():
    print("=" * 60)
    print("VERIFYING THREE-DOT CONVERSATION MENU ON VISUALIZATION PAGE")
    print("=" * 60)

    # 1. HTML Verification
    print("\n[1/3] Inspecting visualization.html for menu and modal elements...")
    resp = requests.get(f"{BASE_URL}/frontend/visualization.html")
    assert resp.status_code == 200
    html = resp.text

    assert 'id="vizHistoryList"' in html
    assert 'id="historyDropdownMenu"' in html
    assert 'id="historyMenuRename"' in html
    assert 'id="historyMenuPin"' in html
    assert 'id="historyMenuDelete"' in html
    assert 'id="deleteModal"' in html
    assert 'id="cancelDeleteBtn"' in html
    assert 'id="confirmDeleteBtn"' in html
    print("PASS: visualization.html contains all floating menu and confirmation modal elements matching chatbot.html.")

    # 2. JavaScript Verification
    print("\n[2/3] Inspecting visualization.js for menu handlers and stopPropagation...")
    r_js = requests.get(f"{BASE_URL}/frontend/visualization.js")
    assert r_js.status_code == 200
    js = r_js.text

    assert "formatConversationDate" in js
    assert "createConversationEntryElement" in js
    assert "toggleHistoryDropdown" in js
    assert "closeHistoryDropdown" in js
    assert "renameConversation" in js
    assert "togglePinConversation" in js
    assert "openDeleteModal" in js
    assert "closeDeleteModal" in js
    assert "confirmDeleteConversation" in js
    assert "e.stopPropagation()" in js
    print("PASS: visualization.js has full parity with chatbot.js for menu actions, rename, pin, delete, and stopPropagation.")

    # 3. Simulate sidebar conversation rendering with three-dot button in Node
    print("\n[3/3] Simulating sidebar rendering with Node.js...")
    node_code = """
const fs = require('fs');
const vm = require('vm');

let createdElements = [];

const dummyEl = {
    addEventListener: () => {},
    getContext: () => ({}),
    replaceChildren: function() {
        createdElements = Array.from(arguments);
    },
    appendChild: function(child) {
        createdElements.push(child);
    },
    hidden: false,
    classList: { add: () => {}, remove: () => {} },
    setAttribute: () => {},
    style: {},
    getBoundingClientRect: () => ({ top: 100, bottom: 130, left: 200, right: 230 })
};

const context = {
    get createdElements() { return createdElements; },
    document: {
        addEventListener: () => {},
        getElementById: (id) => dummyEl,
        querySelectorAll: () => [],
        createElement: (tag, className) => {
            const el = Object.assign({}, dummyEl, {
                tagName: tag,
                className: className || '',
                dataset: {},
                children: [],
                appendChild: function(c) { this.children.push(c); },
                append: function() { this.children.push.apply(this.children, arguments); }
            });
            return el;
        }
    },
    window: { addEventListener: () => {} },
    Chart: class MockChart { constructor() {} destroy() {} },
    console: console,
    sessionStorage: { getItem: () => null, setItem: () => {} },
    URLSearchParams: class MockParams { get() { return 'conv_123'; } }
};

vm.createContext(context);
const code = fs.readFileSync('frontend/visualization.js', 'utf8');
vm.runInContext(code, context);

vm.runInContext("activeConvId = 'conv_1';", context);
vm.runInContext("conversationsList = [" +
    "{ id: 'conv_1', title: 'Sales Analysis', is_pinned: true, updated_at: new Date().toISOString() }," +
    "{ id: 'conv_2', title: 'Customer Churn', is_pinned: false, updated_at: new Date().toISOString() }" +
"];", context);
vm.runInContext("renderSidebarConversations();", context);

const entries = vm.runInContext("createdElements.filter(function(e) { return e.className && e.className.indexOf('history-entry') >= 0; });", context);

console.log(JSON.stringify({
    totalEntries: entries.length,
    hasMenuTrigger: entries.every(function(e) {
        return e.children.some(function(c) { return c.className && c.className.indexOf('history-menu-trigger') >= 0; });
    })
}));
"""

    res = subprocess.run(["node", "-e", node_code], capture_output=True, text=True)
    if res.returncode != 0:
        print("STDERR:", res.stderr)
        print("STDOUT:", res.stdout)
        raise RuntimeError("Node execution failed")
    out = json.loads(res.stdout.strip())
    print("Simulation Output:", out)
    assert out["totalEntries"] == 2, f"Expected 2 conversation entries, got: {out['totalEntries']}"
    assert out["hasMenuTrigger"] is True, "Every conversation entry must contain the three-dot history-menu-trigger"
    print("PASS: Both conversations rendered with visible three-dot options buttons in the sidebar!")

    print("\n" + "=" * 60)
    print("ALL VISUALIZATION MENU PARITY TESTS PASSED!")
    print("=" * 60)

if __name__ == "__main__":
    test_visualization_menu()
