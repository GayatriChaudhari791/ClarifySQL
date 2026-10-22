"use strict";

// ============================================
// 1. Backend configuration
// ============================================

const API_BASE = "http://127.0.0.1:8000";
const CONVERSATIONS_URL = `${API_BASE}/conversations`;

// ============================================
// 2. DOM Elements
// ============================================

const emptyState = document.getElementById("emptyState");
const emptyTitle = document.getElementById("emptyTitle");
const emptyMessage = document.getElementById("emptyMessage");
const emptyBackBtn = document.getElementById("emptyBackBtn");

const vizWorkspace = document.getElementById("vizWorkspace");
const datasetBadge = document.getElementById("datasetBadge");
const datasetBadgeName = document.getElementById("datasetBadgeName");
const topbarBackBtn = document.getElementById("topbarBackBtn");
const navChatbotLink = document.getElementById("navChatbotLink");
const brandLink = document.getElementById("brandLink");

const currentQuestionDisplay = document.getElementById("currentQuestionDisplay");
const querySelectorWrap = document.getElementById("querySelectorWrap");
const querySelect = document.getElementById("querySelect");
const toggleSqlBtn = document.getElementById("toggleSqlBtn");
const queryMetaText = document.getElementById("queryMetaText");
const sqlCollapsible = document.getElementById("sqlCollapsible");
const sqlDisplay = document.getElementById("sqlDisplay");

const summaryCards = document.getElementById("summaryCards");
const summaryRowCount = document.getElementById("summaryRowCount");
const summarySum = document.getElementById("summarySum");
const summarySumLabel = document.getElementById("summarySumLabel");
const summaryAvg = document.getElementById("summaryAvg");
const summaryAvgLabel = document.getElementById("summaryAvgLabel");
const summaryRange = document.getElementById("summaryRange");
const summaryRangeLabel = document.getElementById("summaryRangeLabel");

const chartTypeButtons = document.querySelectorAll(".chart-type-btn");
const labelColSelect = document.getElementById("labelColSelect");
const metricColSelect = document.getElementById("metricColSelect");
const sortSelect = document.getElementById("sortSelect");
const limitSelect = document.getElementById("limitSelect");
const downloadChartBtn = document.getElementById("downloadChartBtn");

const canvasContainer = document.getElementById("canvasContainer");
const vizCanvas = document.getElementById("vizCanvas");
const unsuitableNotice = document.getElementById("unsuitableNotice");
const unsuitableTitle = document.getElementById("unsuitableTitle");
const unsuitableDesc = document.getElementById("unsuitableDesc");

const tableSearchInput = document.getElementById("tableSearchInput");
const copyTableBtn = document.getElementById("copyTableBtn");
const inspectorTable = document.getElementById("inspectorTable");
const inspectorTableHead = document.getElementById("inspectorTableHead");
const inspectorTableBody = document.getElementById("inspectorTableBody");
const inspectorRowSummary = document.getElementById("inspectorRowSummary");

const vizHistoryList = document.getElementById("vizHistoryList");
const historyDropdownMenu = document.getElementById("historyDropdownMenu");
const historyMenuRename = document.getElementById("historyMenuRename");
const historyMenuPin = document.getElementById("historyMenuPin");
const historyMenuPinText = document.getElementById("historyMenuPinText");
const historyMenuDelete = document.getElementById("historyMenuDelete");

const deleteModal = document.getElementById("deleteModal");
const cancelDeleteBtn = document.getElementById("cancelDeleteBtn");
const confirmDeleteBtn = document.getElementById("confirmDeleteBtn");

// ============================================
// 3. Application State
// ============================================

let activeConvId = null;
let activeDatasetId = null;
let activeDatasetName = "";
let availableQueries = []; // Array of { id, question, sql, columns, rows, created_at }
let selectedQueryIndex = 0;
let currentChartType = "bar";
let chartInstance = null;
let conversationsList = [];
let activeMenuConvId = null;
let activeMenuTrigger = null;
let pendingDeleteConvId = null;
let renamingConvId = null;

// Teal & Navy aligned palette
const THEME_COLORS = [
    "#20B8A6", // Primary Teal
    "#0EA5E9", // Sky Blue
    "#6366F1", // Indigo
    "#F59E0B", // Amber
    "#10B981", // Emerald
    "#EC4899", // Pink
    "#8B5CF6", // Purple
    "#14B8A6", // Mint
    "#F97316", // Orange
    "#06B6D4", // Cyan
    "#3B82F6", // Blue
    "#84CC16"  // Lime
];

// ============================================
// 4. Utility Helpers
// ============================================

function createElement(tag, className = "", text = "") {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined && text !== null) el.textContent = String(text);
    return el;
}

function updateBackLinks() {
    const targetUrl = activeConvId ? `chatbot.html?conv_id=${encodeURIComponent(activeConvId)}` : "chatbot.html";
    if (topbarBackBtn) topbarBackBtn.href = targetUrl;
    if (navChatbotLink) navChatbotLink.href = targetUrl;
    if (brandLink) brandLink.href = targetUrl;
    if (emptyBackBtn) emptyBackBtn.href = targetUrl;
}

function formatNumber(num) {
    if (num === null || num === undefined || isNaN(num)) return "—";
    if (Number.isInteger(num)) {
        return num.toLocaleString();
    }
    return Number(num.toFixed(2)).toLocaleString();
}

function isNumericValue(val) {
    if (val === null || val === undefined || val === "") return false;
    if (typeof val === "number") return !isNaN(val);
    if (typeof val === "string") {
        const clean = val.replace(/,/g, "").trim();
        return clean !== "" && !isNaN(Number(clean));
    }
    return false;
}

function parseNumber(val) {
    if (typeof val === "number") return val;
    if (typeof val === "string") {
        const clean = val.replace(/,/g, "").trim();
        const parsed = parseFloat(clean);
        return isNaN(parsed) ? 0 : parsed;
    }
    return 0;
}

function sanitizeCategoryLabel(val, rowIndex) {
    if (val === null || val === undefined) return `(Unspecified ${rowIndex + 1})`;
    const str = String(val).trim();
    if (str === "" || str.toLowerCase() === "null" || str.toLowerCase() === "none") {
        return `(Unspecified ${rowIndex + 1})`;
    }
    return str;
}

// ============================================
// 5. Sidebar Conversations Loader & Menu Actions
// ============================================

function formatConversationDate(isoString) {
    if (!isoString) return "";
    try {
        const date = new Date(isoString);
        if (isNaN(date.getTime())) return "";

        const now = new Date();
        const isToday = date.toDateString() === now.toDateString();

        const yesterday = new Date(now);
        yesterday.setDate(now.getDate() - 1);
        const isYesterday = date.toDateString() === yesterday.toDateString();

        const timeStr = date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

        if (isToday) {
            return `Today, ${timeStr}`;
        }
        if (isYesterday) {
            return `Yesterday, ${timeStr}`;
        }

        const diffDays = Math.floor((now - date) / (1000 * 60 * 60 * 24));
        if (diffDays < 7 && diffDays > 0) {
            const weekday = date.toLocaleDateString([], { weekday: "short" });
            return `${weekday}, ${timeStr}`;
        }

        return date.toLocaleDateString([], { month: "short", day: "numeric" });
    } catch {
        return "";
    }
}

async function fetchConversations() {
    try {
        const res = await fetch(CONVERSATIONS_URL);
        if (!res.ok) return;
        conversationsList = await res.json();
        renderSidebarConversations();
    } catch (err) {
        console.warn("Could not load conversations in visualization:", err);
    }
}

function renderSidebarConversations() {
    if (!vizHistoryList) return;
    vizHistoryList.replaceChildren();

    if (!conversationsList || !conversationsList.length) {
        vizHistoryList.appendChild(
            createElement("p", "empty-history", "Your conversations will appear here.")
        );
        return;
    }

    const pinnedConvs = conversationsList.filter(c => c.is_pinned);
    const unpinnedConvs = conversationsList.filter(c => !c.is_pinned);

    if (pinnedConvs.length > 0) {
        const pinnedHeader = createElement("div", "history-group-header");
        pinnedHeader.appendChild(createElement("p", "history-group-label", "Pinned"));
        vizHistoryList.appendChild(pinnedHeader);

        pinnedConvs.forEach(conv => {
            vizHistoryList.appendChild(createConversationEntryElement(conv));
        });

        if (unpinnedConvs.length > 0) {
            const recentHeader = createElement("div", "history-group-header");
            recentHeader.appendChild(createElement("p", "history-group-label", "Recent"));
            vizHistoryList.appendChild(recentHeader);

            unpinnedConvs.forEach(conv => {
                vizHistoryList.appendChild(createConversationEntryElement(conv));
            });
        }
    } else {
        conversationsList.forEach(conv => {
            vizHistoryList.appendChild(createConversationEntryElement(conv));
        });
    }
}

function createConversationEntryElement(conv) {
    const entry = createElement("div", "history-entry");
    entry.dataset.id = conv.id;
    if (conv.id === activeConvId) {
        entry.classList.add("active");
    }

    // Rename mode
    if (renamingConvId === conv.id) {
        const renameForm = createElement("form", "history-rename-form");
        const renameInput = createElement("input", "history-rename-input");
        renameInput.type = "text";
        renameInput.value = conv.title || "New conversation";
        renameInput.maxLength = 100;
        renameInput.setAttribute("aria-label", "Rename conversation");

        const actions = createElement("div", "history-rename-actions");
        const confirmBtn = createElement("button", "history-rename-btn confirm", "✓");
        confirmBtn.type = "submit";
        confirmBtn.title = "Save title";
        confirmBtn.setAttribute("aria-label", "Save title");

        const cancelBtn = createElement("button", "history-rename-btn cancel", "✕");
        cancelBtn.type = "button";
        cancelBtn.title = "Cancel";
        cancelBtn.setAttribute("aria-label", "Cancel renaming");

        actions.append(confirmBtn, cancelBtn);
        renameForm.append(renameInput, actions);

        renameForm.addEventListener("click", e => e.stopPropagation());
        renameForm.addEventListener("submit", async e => {
            e.preventDefault();
            e.stopPropagation();
            await renameConversation(conv.id, renameInput.value);
        });

        cancelBtn.addEventListener("click", e => {
            e.stopPropagation();
            renamingConvId = null;
            renderSidebarConversations();
        });

        renameInput.addEventListener("keydown", e => {
            if (e.key === "Escape") {
                e.stopPropagation();
                renamingConvId = null;
                renderSidebarConversations();
            }
        });

        entry.appendChild(renameForm);
        setTimeout(() => {
            renameInput.focus();
            renameInput.select();
        }, 20);

        return entry;
    }

    // Normal display mode
    const content = createElement("div", "history-entry-content");
    const titleRow = createElement("div", "history-title-row");

    if (conv.is_pinned) {
        const pinBadge = createElement("span", "history-pin-badge", "📌");
        pinBadge.title = "Pinned";
        pinBadge.setAttribute("aria-hidden", "true");
        titleRow.appendChild(pinBadge);
    }

    const titleText = conv.title || "New conversation";
    const question = createElement("p", "history-question", titleText);
    titleRow.appendChild(question);

    const time = createElement(
        "small",
        "history-time",
        formatConversationDate(conv.updated_at || conv.created_at)
    );

    content.append(titleRow, time);
    entry.title = titleText;

    // Three-dot action button
    const trigger = createElement("button", "history-menu-trigger");
    trigger.type = "button";
    trigger.setAttribute("aria-label", `Options for ${titleText}`);
    trigger.setAttribute("aria-haspopup", "true");
    trigger.title = "Options";
    trigger.innerHTML = "<span>⋮</span>";

    if (activeMenuConvId === conv.id) {
        trigger.classList.add("active");
    }

    trigger.addEventListener("click", e => {
        e.stopPropagation();
        toggleHistoryDropdown(conv, trigger);
    });

    entry.append(content, trigger);

    entry.addEventListener("click", () => {
        if (conv.id === activeConvId) return;
        window.location.href = `visualization.html?conv_id=${encodeURIComponent(conv.id)}`;
    });

    return entry;
}

function toggleHistoryDropdown(conv, trigger) {
    if (activeMenuConvId === conv.id && historyDropdownMenu && !historyDropdownMenu.hidden) {
        closeHistoryDropdown();
        return;
    }

    closeHistoryDropdown();

    activeMenuConvId = conv.id;
    activeMenuTrigger = trigger;
    trigger.classList.add("active");

    if (historyMenuPinText) {
        historyMenuPinText.textContent = conv.is_pinned ? "Unpin" : "Pin";
    }

    if (!historyDropdownMenu) return;
    historyDropdownMenu.hidden = false;

    // Dynamic viewport positioning
    const rect = trigger.getBoundingClientRect();
    const menuWidth = historyDropdownMenu.offsetWidth || 145;
    const menuHeight = historyDropdownMenu.offsetHeight || 125;

    let top = rect.bottom + 4;
    let left = rect.right - menuWidth;

    if (top + menuHeight > window.innerHeight - 8) {
        top = rect.top - menuHeight - 4;
    }

    if (top < 8) top = 8;
    if (top + menuHeight > window.innerHeight - 8) {
        top = Math.max(8, window.innerHeight - menuHeight - 8);
    }

    if (left < 8) left = 8;
    if (left + menuWidth > window.innerWidth - 8) {
        left = Math.max(8, window.innerWidth - menuWidth - 8);
    }

    historyDropdownMenu.style.top = `${top}px`;
    historyDropdownMenu.style.left = `${left}px`;
}

function closeHistoryDropdown() {
    if (!historyDropdownMenu) return;
    historyDropdownMenu.hidden = true;
    if (activeMenuTrigger) {
        activeMenuTrigger.classList.remove("active");
        activeMenuTrigger = null;
    }
    activeMenuConvId = null;
}

async function renameConversation(convId, newTitle) {
    const trimmed = (newTitle || "").trim();
    if (!trimmed) {
        renamingConvId = null;
        renderSidebarConversations();
        return;
    }

    const conv = conversationsList.find(c => c.id === convId);
    if (!conv) return;

    if (conv.title === trimmed) {
        renamingConvId = null;
        renderSidebarConversations();
        return;
    }

    try {
        const response = await fetch(`${CONVERSATIONS_URL}/${convId}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title: trimmed })
        });
        if (!response.ok) {
            const errData = await response.json().catch(() => ({}));
            throw new Error(errData.detail || "Failed to rename conversation");
        }
        const updated = await response.json();
        conv.title = updated.title || trimmed;
        conv.is_custom_title = true;
        conv.updated_at = updated.updated_at || conv.updated_at;
    } catch (err) {
        console.error("Failed to rename conversation:", err);
        alert("Could not rename conversation: " + (err.message || err));
    } finally {
        renamingConvId = null;
        renderSidebarConversations();
    }
}

async function togglePinConversation(convId) {
    const conv = conversationsList.find(c => c.id === convId);
    if (!conv) return;

    const newPinnedState = !conv.is_pinned;

    try {
        const response = await fetch(`${CONVERSATIONS_URL}/${convId}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ is_pinned: newPinnedState })
        });
        if (!response.ok) {
            const errData = await response.json().catch(() => ({}));
            throw new Error(errData.detail || "Failed to update pin state");
        }
        conv.is_pinned = newPinnedState;
        conversationsList.sort((a, b) => {
            if (Boolean(b.is_pinned) !== Boolean(a.is_pinned)) {
                return (b.is_pinned ? 1 : 0) - (a.is_pinned ? 1 : 0);
            }
            return new Date(b.updated_at || 0) - new Date(a.updated_at || 0);
        });
        renderSidebarConversations();
    } catch (err) {
        console.error("Failed to pin/unpin conversation:", err);
        alert("Could not update pin state: " + (err.message || err));
    }
}

function openDeleteModal(convId) {
    pendingDeleteConvId = convId;
    if (deleteModal) {
        deleteModal.hidden = false;
        if (confirmDeleteBtn) confirmDeleteBtn.disabled = false;
        if (cancelDeleteBtn) cancelDeleteBtn.focus();
    }
}

function closeDeleteModal() {
    if (deleteModal) {
        deleteModal.hidden = true;
    }
    pendingDeleteConvId = null;
}

async function confirmDeleteConversation() {
    if (!pendingDeleteConvId) return;
    const convId = pendingDeleteConvId;

    try {
        if (confirmDeleteBtn) confirmDeleteBtn.disabled = true;
        const response = await fetch(`${CONVERSATIONS_URL}/${convId}`, {
            method: "DELETE"
        });
        if (!response.ok) {
            const errData = await response.json().catch(() => ({}));
            throw new Error(errData.detail || "Failed to delete conversation");
        }

        conversationsList = conversationsList.filter(c => c.id !== convId);
        closeDeleteModal();

        if (convId === activeConvId) {
            activeConvId = null;
            try {
                sessionStorage.removeItem("clarify_active_viz");
            } catch {}

            if (conversationsList.length > 0) {
                window.location.href = `visualization.html?conv_id=${encodeURIComponent(conversationsList[0].id)}`;
            } else {
                window.location.href = `visualization.html`;
            }
        } else {
            renderSidebarConversations();
        }
    } catch (err) {
        console.error("Delete conversation failed:", err);
        alert("Could not delete conversation: " + (err.message || err));
    } finally {
        if (confirmDeleteBtn) confirmDeleteBtn.disabled = false;
    }
}

// ============================================
// 6. Data Hydration & Initialization
// ============================================

async function initVisualization() {
    const params = new URLSearchParams(window.location.search);
    const convId = params.get("conv_id");
    const msgId = params.get("msg_id");
    const datasetId = params.get("dataset_id");

    activeConvId = convId || null;
    activeDatasetId = datasetId || null;
    updateBackLinks();
    await fetchConversations();

    // Check transient fast-path cache first
    let cached = null;
    try {
        const rawCache = sessionStorage.getItem("clarify_active_viz");
        if (rawCache) cached = JSON.parse(rawCache);
    } catch {}

    if (cached && (!convId || cached.conversation_id === convId) && cached.rows && cached.rows.length) {
        if (!activeConvId) activeConvId = cached.conversation_id;
        activeDatasetId = cached.dataset_id || activeDatasetId;
        activeDatasetName = cached.dataset_name || "Uploaded dataset";
        updateBackLinks();

        availableQueries = [{
            id: cached.message_id || 1,
            question: cached.question || "Natural language query",
            sql: cached.sql || "",
            columns: cached.columns || [],
            rows: cached.rows || []
        }];
        selectedQueryIndex = 0;
        renderActiveQuery();
    }

    // Now hydrate authoritative data from backend if conversation ID is available
    if (activeConvId) {
        try {
            const res = await fetch(`${CONVERSATIONS_URL}/${activeConvId}`);
            if (!res.ok) throw new Error("Conversation not found");
            const conv = await res.json();

            activeDatasetId = conv.dataset_id || activeDatasetId;
            activeDatasetName = conv.dataset_name || activeDatasetName || "Uploaded dataset";

            // Extract all successful query messages
            const queryMessages = [];
            let lastUserQ = "Natural language query";

            (conv.messages || []).forEach(m => {
                if (m.role === "user") {
                    lastUserQ = m.content || "Natural language query";
                } else if (m.role === "assistant" && !m.is_error && m.columns && m.columns.length && m.rows) {
                    queryMessages.push({
                        id: m.id,
                        question: lastUserQ,
                        sql: m.sql || "",
                        columns: m.columns,
                        rows: m.rows,
                        created_at: m.created_at
                    });
                }
            });

            if (queryMessages.length > 0) {
                availableQueries = queryMessages;

                // Pick message based on msg_id if specified, else latest
                if (msgId) {
                    const foundIdx = availableQueries.findIndex(q => String(q.id) === String(msgId));
                    selectedQueryIndex = foundIdx >= 0 ? foundIdx : availableQueries.length - 1;
                } else {
                    selectedQueryIndex = availableQueries.length - 1;
                }

                renderActiveQuery();
            } else {
                if (!cached) {
                    showEmptyState(
                        "No query results in this conversation",
                        activeDatasetName
                            ? `Dataset "${activeDatasetName}" is active, but no successful SQL queries were found. Ask a question in the chatbot first.`
                            : "Run a query in the chatbot first to generate results for visualization."
                    );
                }
            }
        } catch (err) {
            console.error("Failed to load conversation for visualization:", err);
            if (!availableQueries.length) {
                showEmptyState("Conversation not found", "Could not load the specified conversation. Please return to the chatbot.");
            }
        }
    } else if (!availableQueries.length) {
        showEmptyState("No dataset or query selected", "Please open a conversation from the chatbot workspace to view its visualizations.");
    }

    renderDatasetBadge();
}

function showEmptyState(title, message) {
    if (emptyState) emptyState.hidden = false;
    if (vizWorkspace) vizWorkspace.hidden = true;
    if (emptyTitle) emptyTitle.textContent = title;
    if (emptyMessage) emptyMessage.textContent = message;
}

function renderDatasetBadge() {
    if (activeDatasetName) {
        datasetBadge.hidden = false;
        datasetBadgeName.textContent = activeDatasetName;
    } else {
        datasetBadge.hidden = true;
    }
}

// ============================================
// 7. Render Active Query
// ============================================

function renderActiveQuery() {
    if (!availableQueries || !availableQueries.length) {
        showEmptyState("No query results available", "Ask a question in the chatbot to generate data for visualization.");
        return;
    }

    const currentQuery = availableQueries[selectedQueryIndex] || availableQueries[0];
    emptyState.hidden = true;
    vizWorkspace.hidden = false;

    // 1. Question & SQL
    currentQuestionDisplay.textContent = currentQuery.question || "Natural language query";
    sqlDisplay.textContent = currentQuery.sql || "No SQL statement available.";
    queryMetaText.textContent = `${currentQuery.rows.length} row${currentQuery.rows.length === 1 ? "" : "s"} returned`;

    // 2. Query selector dropdown (if multiple queries)
    if (availableQueries.length > 1) {
        querySelectorWrap.hidden = false;
        querySelect.replaceChildren();
        availableQueries.forEach((q, idx) => {
            const opt = document.createElement("option");
            opt.value = idx;
            const shortQ = q.question.length > 40 ? q.question.slice(0, 40) + "..." : q.question;
            opt.textContent = `${idx + 1}. ${shortQ} (${q.rows.length} rows)`;
            if (idx === selectedQueryIndex) opt.selected = true;
            querySelect.appendChild(opt);
        });
    } else {
        querySelectorWrap.hidden = true;
    }

    // 3. Schema & Column detection
    setupColumnSelectors(currentQuery);

    // 4. Update KPI summaries & Chart
    updateChartAndMetrics();

    // 5. Render Data Inspector Table
    renderInspectorTable(currentQuery.columns, currentQuery.rows);
}

// ============================================
// 8. Column Detection & Controls
// ============================================

function setupColumnSelectors(query) {
    const columns = query.columns || [];
    const rows = query.rows || [];

    labelColSelect.replaceChildren();
    metricColSelect.replaceChildren();

    if (!columns.length || !rows.length) {
        return;
    }

    // Detect numeric columns
    const numericCols = [];
    const categoricalCols = [];

    columns.forEach((col, idx) => {
        let numericCount = 0;
        let nonNullCount = 0;

        rows.forEach(r => {
            const val = r[idx];
            if (val !== null && val !== undefined && val !== "") {
                nonNullCount++;
                if (isNumericValue(val)) numericCount++;
            }
        });

        const isNumeric = nonNullCount > 0 && (numericCount / nonNullCount) >= 0.75;
        if (isNumeric) {
            numericCols.push({ name: col, index: idx });
        } else {
            categoricalCols.push({ name: col, index: idx });
        }
    });

    // Populate Category/X options
    columns.forEach((col, idx) => {
        const opt = document.createElement("option");
        opt.value = idx;
        opt.textContent = col;
        labelColSelect.appendChild(opt);
    });

    // Populate Metric/Y options
    if (numericCols.length > 0) {
        numericCols.forEach(c => {
            const opt = document.createElement("option");
            opt.value = c.index;
            opt.textContent = c.name;
            metricColSelect.appendChild(opt);
        });
    } else {
        // Fallback if no strictly numeric columns
        columns.forEach((col, idx) => {
            const opt = document.createElement("option");
            opt.value = idx;
            opt.textContent = col;
            metricColSelect.appendChild(opt);
        });
    }

    // Smart default selection
    if (categoricalCols.length > 0) {
        labelColSelect.value = categoricalCols[0].index;
    } else {
        labelColSelect.value = 0;
    }

    if (numericCols.length > 0) {
        // Prefer columns with words like count, total, sum, sales, rev, price, amount
        const preferred = numericCols.find(c => {
            const low = c.name.toLowerCase();
            return low.includes("count") || low.includes("total") || low.includes("sum") ||
                   low.includes("sales") || low.includes("rev") || low.includes("price") ||
                   low.includes("amount") || low.includes("qty");
        });
        metricColSelect.value = preferred ? preferred.index : numericCols[0].index;
    } else {
        metricColSelect.value = columns.length > 1 ? 1 : 0;
    }
}

// ============================================
// 9. Chart Rendering & Statistics Calculation
// ============================================

function updateChartAndMetrics() {
    const currentQuery = availableQueries[selectedQueryIndex];
    if (!currentQuery) return;

    const columns = currentQuery.columns || [];
    const rows = currentQuery.rows || [];

    if (!rows.length) {
        showUnsuitableNotice(
            "Empty query results",
            "The query returned 0 rows. There is no data available to visualize."
        );
        clearMetrics();
        return;
    }

    const labelIdx = parseInt(labelColSelect.value, 10);
    const metricIdx = parseInt(metricColSelect.value, 10);

    if (isNaN(labelIdx) || isNaN(metricIdx) || labelIdx < 0 || metricIdx < 0) {
        showUnsuitableNotice("Invalid columns", "Please select valid columns for the chart axes.");
        return;
    }

    const labelName = columns[labelIdx] || "Label";
    const metricName = columns[metricIdx] || "Value";

    // Extract raw data points with sanitized category labels
    let dataPoints = rows.map((r, i) => {
        const rawLabel = r[labelIdx];
        const rawVal = r[metricIdx];
        return {
            label: sanitizeCategoryLabel(rawLabel, i),
            value: isNumericValue(rawVal) ? parseNumber(rawVal) : null,
            rawRow: r
        };
    });

    // Check if metric column contains usable numeric values
    const validNumericPoints = dataPoints.filter(p => p.value !== null);
    if (validNumericPoints.length === 0) {
        showUnsuitableNotice(
            "Non-numeric metric selected",
            `Column "${metricName}" contains only text or non-numeric values. Charts require numeric values to plot. Select a numeric metric or view the underlying table below.`
        );
        updateSummaryCards(rows.length, null, metricName);
        return;
    }

    // Hide notice and show chart
    unsuitableNotice.hidden = true;
    canvasContainer.hidden = false;

    // Apply sorting
    const sortMode = sortSelect.value;
    if (sortMode === "desc") {
        dataPoints.sort((a, b) => (b.value ?? -Infinity) - (a.value ?? -Infinity));
    } else if (sortMode === "asc") {
        dataPoints.sort((a, b) => (a.value ?? Infinity) - (b.value ?? Infinity));
    } else if (sortMode === "alpha") {
        dataPoints.sort((a, b) => a.label.localeCompare(b.label));
    }

    // Apply limit
    const limitVal = limitSelect.value;
    let chartPoints = dataPoints;
    if (limitVal !== "all") {
        const lim = parseInt(limitVal, 10);
        if (!isNaN(lim) && lim > 0) {
            chartPoints = dataPoints.slice(0, lim);
        }
    }

    // Calculate metrics based on ALL valid numeric rows (not just sliced)
    const allNumericVals = validNumericPoints.map(p => p.value);
    const sum = allNumericVals.reduce((acc, v) => acc + v, 0);
    const avg = allNumericVals.length ? sum / allNumericVals.length : 0;
    const min = Math.min(...allNumericVals);
    const max = Math.max(...allNumericVals);

    updateSummaryCards(rows.length, { sum, avg, min, max }, metricName);

    // Build Chart.js chart
    renderChartJS(chartPoints, labelName, metricName);
}

function updateSummaryCards(rowCount, stats, metricName) {
    summaryRowCount.textContent = formatNumber(rowCount);

    if (stats) {
        summarySum.textContent = formatNumber(stats.sum);
        summarySumLabel.textContent = `Sum of ${metricName}`;

        summaryAvg.textContent = formatNumber(stats.avg);
        summaryAvgLabel.textContent = `Average ${metricName}`;

        summaryRange.textContent = `${formatNumber(stats.min)} - ${formatNumber(stats.max)}`;
        summaryRangeLabel.textContent = `Min to Max range`;
    } else {
        summarySum.textContent = "—";
        summarySumLabel.textContent = "Non-numeric metric";
        summaryAvg.textContent = "—";
        summaryAvgLabel.textContent = "Non-numeric metric";
        summaryRange.textContent = "—";
        summaryRangeLabel.textContent = "Non-numeric metric";
    }
}

function clearMetrics() {
    summaryRowCount.textContent = "0";
    summarySum.textContent = "—";
    summaryAvg.textContent = "—";
    summaryRange.textContent = "—";
}

function showUnsuitableNotice(title, desc) {
    unsuitableNotice.hidden = false;
    canvasContainer.hidden = true;
    unsuitableTitle.textContent = title;
    unsuitableDesc.textContent = desc;

    if (chartInstance) {
        chartInstance.destroy();
        chartInstance = null;
    }
}

// ============================================
// 10. Chart.js Drawing
// ============================================

function renderChartJS(points, labelName, metricName) {
    if (typeof Chart === "undefined") {
        showUnsuitableNotice(
            "Visualization library unavailable",
            "The Chart.js rendering library could not be loaded. You can still inspect and copy the underlying data table below."
        );
        return;
    }

    if (chartInstance) {
        chartInstance.destroy();
        chartInstance = null;
    }

    const isCircular = currentChartType === "pie" || currentChartType === "doughnut";

    let chartPoints = points;
    if (isCircular) {
        chartPoints = points.filter(p => p.value !== null && p.value > 0);
        if (chartPoints.length === 0) {
            showUnsuitableNotice(
                "No positive numeric values for pie/doughnut",
                "Pie and doughnut charts require positive numeric values to plot proportional slices. Select a metric with positive numbers or switch to Bar chart."
            );
            return;
        }
    }

    const labels = chartPoints.map(p => p.label);
    const dataValues = chartPoints.map(p => p.value ?? 0);

    // Colors
    const backgroundColors = isCircular
        ? chartPoints.map((_, i) => THEME_COLORS[i % THEME_COLORS.length])
        : "rgba(32, 184, 166, 0.85)"; // Teal

    const borderColors = isCircular
        ? "#ffffff"
        : "#245B43"; // Teal dark border

    const dataset = {
        label: metricName,
        data: dataValues,
        backgroundColor: backgroundColors,
        borderColor: borderColors,
        borderWidth: isCircular ? 2 : 1.5,
        borderRadius: currentChartType === "bar" ? 5 : 0
    };

    if (currentChartType === "line") {
        dataset.tension = 0.35;
        dataset.fill = true;
        dataset.backgroundColor = "rgba(32, 184, 166, 0.14)";
        dataset.borderColor = "#20B8A6";
        dataset.pointBackgroundColor = "#20B8A6";
        dataset.pointBorderColor = "#ffffff";
        dataset.pointHoverRadius = 6;
    }

    const config = {
        type: currentChartType,
        data: {
            labels: labels,
            datasets: [dataset]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: {
                duration: 400
            },
            plugins: {
                legend: {
                    display: isCircular,
                    position: "right",
                    labels: {
                        boxWidth: 14,
                        font: { family: "'DM Sans', sans-serif", size: 12 },
                        color: "#1F3027"
                    }
                },
                tooltip: {
                    backgroundColor: "#1F3027",
                    titleFont: { family: "'Manrope', sans-serif", size: 13, weight: "700" },
                    bodyFont: { family: "'DM Sans', sans-serif", size: 12.5 },
                    padding: 10,
                    cornerRadius: 8,
                    callbacks: {
                        label: function (ctx) {
                            const val = ctx.raw;
                            return ` ${metricName}: ${formatNumber(val)}`;
                        }
                    }
                }
            }
        }
    };

    if (!isCircular) {
        config.options.scales = {
            x: {
                grid: { display: false },
                ticks: {
                    font: { family: "'DM Sans', sans-serif", size: 11.5 },
                    color: "#718078",
                    maxRotation: 45,
                    minRotation: 0
                }
            },
            y: {
                beginAtZero: true,
                grid: { color: "#E4E9E3" },
                ticks: {
                    font: { family: "'DM Sans', sans-serif", size: 11.5 },
                    color: "#718078",
                    callback: function (val) {
                        return formatNumber(val);
                    }
                }
            }
        };
    }

    if (currentChartType === "doughnut") {
        config.options.cutout = "60%";
    }

    try {
        const ctx = vizCanvas.getContext("2d");
        chartInstance = new Chart(ctx, config);
    } catch (err) {
        console.error("Chart.js render error:", err);
        showUnsuitableNotice("Chart render error", "Could not render chart. Please inspect the underlying data table.");
    }
}

// ============================================
// 11. Data Inspector Table
// ============================================

function renderInspectorTable(columns, rows) {
    inspectorTableHead.replaceChildren();
    inspectorTableBody.replaceChildren();

    if (!columns || !columns.length) {
        inspectorRowSummary.textContent = "No tabular data returned.";
        return;
    }

    // Header
    const trHead = document.createElement("tr");
    columns.forEach(col => {
        trHead.appendChild(createElement("th", "", col));
    });
    inspectorTableHead.appendChild(trHead);

    // Filter rows based on search
    const filterText = (tableSearchInput.value || "").trim().toLowerCase();

    let displayRows = rows;
    if (filterText) {
        displayRows = rows.filter(r => {
            return r.some(val => val !== null && val !== undefined && String(val).toLowerCase().includes(filterText));
        });
    }

    displayRows.forEach(r => {
        const tr = document.createElement("tr");
        columns.forEach((_, idx) => {
            const val = r[idx];
            tr.appendChild(createElement("td", "", val === null || val === undefined ? "—" : val));
        });
        inspectorTableBody.appendChild(tr);
    });

    inspectorRowSummary.textContent = filterText
        ? `Showing ${displayRows.length} of ${rows.length} rows (filtered)`
        : `Showing all ${rows.length} rows`;
}

// ============================================
// 12. Event Listeners
// ============================================

// Chart type switcher
chartTypeButtons.forEach(btn => {
    btn.addEventListener("click", () => {
        chartTypeButtons.forEach(b => {
            b.classList.remove("active");
            b.setAttribute("aria-selected", "false");
        });
        btn.classList.add("active");
        btn.setAttribute("aria-selected", "true");
        currentChartType = btn.dataset.chart || "bar";
        updateChartAndMetrics();
    });
});

// Dropdowns
if (labelColSelect) labelColSelect.addEventListener("change", updateChartAndMetrics);
if (metricColSelect) metricColSelect.addEventListener("change", updateChartAndMetrics);
if (sortSelect) sortSelect.addEventListener("change", updateChartAndMetrics);
if (limitSelect) limitSelect.addEventListener("change", updateChartAndMetrics);

// Query selector (when multiple queries)
if (querySelect) {
    querySelect.addEventListener("change", () => {
        selectedQueryIndex = parseInt(querySelect.value, 10) || 0;
        renderActiveQuery();
    });
}

// SQL Toggle
if (toggleSqlBtn) {
    toggleSqlBtn.addEventListener("click", () => {
        const isHidden = sqlCollapsible.hidden;
        sqlCollapsible.hidden = !isHidden;
        toggleSqlBtn.setAttribute("aria-expanded", String(isHidden));
    });
}

// Table search filter
if (tableSearchInput) {
    tableSearchInput.addEventListener("input", () => {
        const currentQuery = availableQueries[selectedQueryIndex];
        if (currentQuery) {
            renderInspectorTable(currentQuery.columns, currentQuery.rows);
        }
    });
}

// Copy table data
if (copyTableBtn) {
    copyTableBtn.addEventListener("click", async () => {
        const currentQuery = availableQueries[selectedQueryIndex];
        if (!currentQuery || !currentQuery.rows || !currentQuery.rows.length) return;

        const headerLine = currentQuery.columns.join("\t");
        const rowLines = currentQuery.rows.map(r => r.map(c => c === null || c === undefined ? "" : c).join("\t"));
        const tsv = [headerLine, ...rowLines].join("\n");

        try {
            await navigator.clipboard.writeText(tsv);
            copyTableBtn.textContent = "Copied TSV!";
            setTimeout(() => {
                copyTableBtn.textContent = "Copy data";
            }, 1500);
        } catch {
            alert("Could not access clipboard.");
        }
    });
}

// Download chart PNG
if (downloadChartBtn) {
    downloadChartBtn.addEventListener("click", () => {
        if (!chartInstance || !vizCanvas) return;
        try {
            const url = vizCanvas.toDataURL("image/png");
            const a = document.createElement("a");
            a.download = `ClarifySQL-Chart-${Date.now()}.png`;
            a.href = url;
            a.click();
        } catch (e) {
            console.error("Export PNG failed:", e);
        }
    });
}

// Conversation menu & modal listeners
if (historyMenuRename) {
    historyMenuRename.addEventListener("click", () => {
        const convId = activeMenuConvId;
        closeHistoryDropdown();
        if (convId) {
            renamingConvId = convId;
            renderSidebarConversations();
        }
    });
}

if (historyMenuPin) {
    historyMenuPin.addEventListener("click", () => {
        const convId = activeMenuConvId;
        closeHistoryDropdown();
        if (convId) {
            togglePinConversation(convId);
        }
    });
}

if (historyMenuDelete) {
    historyMenuDelete.addEventListener("click", () => {
        const convId = activeMenuConvId;
        closeHistoryDropdown();
        if (convId) {
            openDeleteModal(convId);
        }
    });
}

if (cancelDeleteBtn) {
    cancelDeleteBtn.addEventListener("click", closeDeleteModal);
}

if (confirmDeleteBtn) {
    confirmDeleteBtn.addEventListener("click", confirmDeleteConversation);
}

if (deleteModal) {
    deleteModal.addEventListener("click", e => {
        if (e.target === deleteModal) closeDeleteModal();
    });
}

// Global dismiss listeners
document.addEventListener("pointerdown", e => {
    if (historyDropdownMenu && !historyDropdownMenu.hidden) {
        if (!historyDropdownMenu.contains(e.target) && !e.target.closest(".history-menu-trigger")) {
            closeHistoryDropdown();
        }
    }
});

document.addEventListener("keydown", e => {
    if (e.key === "Escape") {
        if (historyDropdownMenu && !historyDropdownMenu.hidden) {
            closeHistoryDropdown();
        } else if (deleteModal && !deleteModal.hidden) {
            closeDeleteModal();
        }
    }
});

window.addEventListener("scroll", () => {
    if (historyDropdownMenu && !historyDropdownMenu.hidden) {
        closeHistoryDropdown();
    }
}, true);

// ============================================
// 13. Initialize on Load
// ============================================

window.addEventListener("DOMContentLoaded", () => {
    initVisualization();
});
