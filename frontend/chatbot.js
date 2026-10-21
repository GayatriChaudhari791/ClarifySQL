"use strict";

// ============================================
// 1. Backend configuration
// ============================================

const API_BASE = "http://127.0.0.1:8000";
const UPLOAD_URL = `${API_BASE}/upload`;
const QUERY_URL = `${API_BASE}/query`;
const CONVERSATIONS_URL = `${API_BASE}/conversations`;

// ============================================
// 2. HTML elements
// ============================================

const uploadForm = document.getElementById("uploadForm");
const fileInput = document.getElementById("fileInput");
const uploadZone = document.getElementById("uploadZone");
const selectedFile = document.getElementById("selectedFile");
const fileName = document.getElementById("fileName");
const fileSize = document.getElementById("fileSize");
const removeFileButton = document.getElementById("removeFileButton");
const changeFileButton = document.getElementById("changeFileButton");
const uploadMessage = document.getElementById("uploadMessage");

const questionInput = document.getElementById("questionInput");
const sendButton = document.getElementById("sendButton");
const sendButtonText = document.getElementById("sendButtonText");

const welcome = document.getElementById("welcome");
const messages = document.getElementById("messages");
const conversationArea = document.getElementById("conversationArea");

const datasetPanel = document.getElementById("datasetPanel");
const datasetTitle = document.getElementById("datasetTitle");
const datasetMeta = document.getElementById("datasetMeta");
const previewWrap = document.getElementById("previewWrap");

const responseDetails = document.getElementById("responseDetails");
const sqlOutput = document.getElementById("sqlOutput");
const sqlStatus = document.getElementById("sqlStatus");
const resultsOutput = document.getElementById("resultsOutput");
const resultCount = document.getElementById("resultCount");

const chartSection = document.getElementById("chartSection");
const chartOutput = document.getElementById("chartOutput");

const copySQLButton = document.getElementById("copySQLButton");
const newChatButton = document.getElementById("newChatButton");
const historyList = document.getElementById("historyList");
const historyDropdownMenu = document.getElementById("historyDropdownMenu");
const historyMenuRename = document.getElementById("historyMenuRename");
const historyMenuPin = document.getElementById("historyMenuPin");
const historyMenuPinIcon = document.getElementById("historyMenuPinIcon");
const historyMenuPinText = document.getElementById("historyMenuPinText");
const historyMenuDelete = document.getElementById("historyMenuDelete");

const deleteModal = document.getElementById("deleteModal");
const cancelDeleteBtn = document.getElementById("cancelDeleteBtn");
const confirmDeleteBtn = document.getElementById("confirmDeleteBtn");
const inlineChangeFileButton = document.getElementById("inlineChangeFileButton");

// ============================================
// 3. Application state
// ============================================

let activeConversationId = null;
let conversationsList = [];
let selectedDatasetFile = null;
let currentDatasetId = null;
let currentDatasetName = "";
let isLoading = false;
let pendingCustomClarification = null; // { conversationId, originalQuestion, optionsContainer }
let activeMenuConvId = null;
let activeMenuTrigger = null;
let pendingDeleteConvId = null;
let renamingConvId = null;

// ============================================
// 4. Helper functions
// ============================================

function createElement(tag, className = "", text = "") {
    const element = document.createElement(tag);

    if (className) {
        element.className = className;
    }

    if (text !== undefined && text !== null) {
        element.textContent = String(text);
    }

    return element;
}

function scrollMessagesToBottom(smooth = true) {
    if (!messages) return;
    try {
        messages.scrollTo({
            top: messages.scrollHeight,
            behavior: smooth ? "smooth" : "auto"
        });
    } catch {
        messages.scrollTop = messages.scrollHeight;
    }
}

function updateDatasetFormState() {
    if (!uploadForm) return;
    const isWelcome = Boolean(welcome && !welcome.hidden);
    const hasActiveDataset = Boolean(currentDatasetId && !isWelcome);

    if (hasActiveDataset) {
        uploadForm.classList.add("dataset-active");
        if (questionHint) {
            questionHint.textContent = "Ask a question about your dataset in plain English.";
        }
        if (inlineChangeFileButton) {
            inlineChangeFileButton.hidden = false;
        }
    } else {
        uploadForm.classList.remove("dataset-active");
        if (questionHint) {
            questionHint.textContent = "Upload a dataset to begin your analysis.";
        }
        if (inlineChangeFileButton) {
            inlineChangeFileButton.hidden = true;
        }
    }
}

function formatFileSize(bytes) {
    if (bytes < 1024) return `${bytes} B`;

    if (bytes < 1024 * 1024) {
        return `${(bytes / 1024).toFixed(1)} KB`;
    }

    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

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

function showFormMessage(message, isError = true) {
    uploadMessage.textContent = message;
    uploadMessage.style.color = isError ? "#b42318" : "#245b43";
}

function setLoading(loading, label = "Working...") {
    isLoading = loading;

    sendButton.disabled = loading;
    fileInput.disabled = loading;
    uploadZone.disabled = loading;
    questionInput.disabled = loading;
    removeFileButton.disabled = loading;
    changeFileButton.disabled = loading;
    newChatButton.disabled = loading;

    sendButtonText.textContent = loading ? label : "Continue";
}

// ============================================
// 5. Chat messages
// ============================================

function addMessage(role, text, isError = false) {
    const message = createElement("div", `message ${role}`);

    const label = createElement(
        "span",
        "message-label",
        role === "user" ? "YOU" : "CLARIFYSQL"
    );

    const bubble = createElement(
        "div",
        "message-bubble",
        text
    );

    if (isError) {
        bubble.classList.add("error");
    }

    message.append(label, bubble);
    messages.appendChild(message);
    scrollMessagesToBottom(true);

    return message;
}

function renderClarificationOptions(messageElement, options, originalQuestion, isAnswered = false, selectedValue = null, hasResolutionSql = false) {
    if (!options || !options.length) return;

    const container = createElement("div", "clarification-options");
    container.setAttribute("role", "group");
    container.setAttribute("aria-label", "Clarification options");

    options.forEach(opt => {
        const btn = createElement("button", "clarification-pill", opt.label);
        btn.type = "button";
        btn.dataset.optionId = opt.id;
        btn.dataset.optionLabel = opt.label;

        if (isAnswered) {
            btn.disabled = true;
            if (selectedValue && (selectedValue === opt.id || selectedValue.toLowerCase() === opt.label.toLowerCase())) {
                btn.classList.add("selected");
            }
        } else {
            btn.addEventListener("click", () => {
                if (isLoading) return;
                btn.classList.add("selected");
                container.querySelectorAll("button").forEach(b => b.disabled = true);
                pendingCustomClarification = null;
                questionInput.placeholder = "Ask a question about your dataset in plain English...";
                submitClarification(originalQuestion, opt.id, opt.label);
            });
        }
        container.appendChild(btn);
    });

    // "Other…" option for custom typing
    const otherBtn = createElement("button", "clarification-pill other-pill", "Other…");
    otherBtn.type = "button";
    if (isAnswered) {
        otherBtn.disabled = true;
        if (selectedValue && hasResolutionSql && !options.some(o => o.id === selectedValue || o.label.toLowerCase() === selectedValue.toLowerCase())) {
            otherBtn.classList.add("selected");
        }
    } else {
        otherBtn.addEventListener("click", () => {
            if (isLoading) return;
            container.querySelectorAll(".clarification-pill").forEach(b => b.classList.remove("selected"));
            otherBtn.classList.add("selected");
            pendingCustomClarification = {
                conversationId: activeConversationId,
                originalQuestion: originalQuestion,
                optionsContainer: container
            };
            const shortQ = originalQuestion.length > 35 ? originalQuestion.slice(0, 35) + "..." : originalQuestion;
            questionInput.placeholder = `Type your clarification for: "${shortQ}"`;
            questionInput.focus();
            questionInput.scrollIntoView({ behavior: "smooth", block: "nearest" });
        });
    }
    container.appendChild(otherBtn);

    messageElement.appendChild(container);
    scrollMessagesToBottom(true);
}

// ============================================
// 6. File selection
// ============================================

function setSelectedFile(file) {
    selectedDatasetFile = file || null;

    if (!file) {
        selectedFile.hidden = true;
        fileInput.value = "";
        fileName.textContent = "";
        fileSize.textContent = "";
        return;
    }

    const extension = file.name.split(".").pop().toLowerCase();

    if (!["csv", "xlsx", "xls"].includes(extension)) {
        selectedDatasetFile = null;
        fileInput.value = "";
        selectedFile.hidden = true;

        showFormMessage(
            "Please choose a CSV or Excel file."
        );

        return;
    }

    if (file.size > 20 * 1024 * 1024) {
        selectedDatasetFile = null;
        fileInput.value = "";
        selectedFile.hidden = true;

        showFormMessage(
            "The file is too large. Please choose a file under 20 MB."
        );

        return;
    }

    selectedFile.hidden = false;
    fileName.textContent = file.name;
    fileSize.textContent = formatFileSize(file.size);

    showFormMessage("", false);
}

// ============================================
// 7. Dataset preview
// ============================================

function renderDatasetPreview(data, filename) {
    currentDatasetName =
        data.filename || filename || "Uploaded dataset";

    datasetTitle.textContent = currentDatasetName;

    datasetMeta.replaceChildren();
    previewWrap.replaceChildren();

    const rowCount = data.row_count ?? data.total_rows;

    const columns = Array.isArray(data.columns)
        ? data.columns
        : [];

    const previewRows = Array.isArray(data.preview)
        ? data.preview
        : Array.isArray(data.rows_preview)
            ? data.rows_preview
            : [];

    if (rowCount !== undefined && rowCount !== null) {
        datasetMeta.appendChild(
            createElement("span", "meta-chip", `${rowCount.toLocaleString()} rows`)
        );
    }

    if (columns.length) {
        datasetMeta.appendChild(
            createElement(
                "span",
                "meta-chip",
                `${columns.length} columns`
            )
        );
    }

    const fileType = currentDatasetName.split(".").pop().toUpperCase();

    if (fileType) {
        datasetMeta.appendChild(
            createElement("span", "meta-chip", fileType)
        );
    }

    if (!columns.length) {
        previewWrap.appendChild(
            createElement(
                "p",
                "muted-text",
                "Your dataset was uploaded. A column preview was not returned by the backend."
            )
        );

        datasetPanel.hidden = false;
        return;
    }

    const table = createElement("table", "preview-table");
    const thead = document.createElement("thead");
    const headerRow = document.createElement("tr");

    columns.forEach(column => {
        headerRow.appendChild(
            createElement("th", "", column)
        );
    });

    thead.appendChild(headerRow);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");

    previewRows.slice(0, 5).forEach(row => {
        const tr = document.createElement("tr");

        columns.forEach((column, index) => {
            let value;

            if (Array.isArray(row)) {
                value = row[index];
            } else if (row && typeof row === "object") {
                value = row[column];
            } else {
                value = "";
            }

            tr.appendChild(
                createElement(
                    "td",
                    "",
                    value === null || value === undefined
                        ? "—"
                        : value
                )
            );
        });

        tbody.appendChild(tr);
    });

    table.appendChild(tbody);
    previewWrap.appendChild(table);

    datasetPanel.hidden = false;
}

// ============================================
// 8. API response handling
// ============================================

async function readResponse(response) {
    let data;

    try {
        data = await response.json();
    } catch {
        throw new Error(
            "The server returned an unreadable response."
        );
    }

    if (!response.ok) {
        throw new Error(
            data.detail ||
            data.error ||
            data.message ||
            `Request failed with status ${response.status}.`
        );
    }

    return data;
}

// ============================================
// 9. Persistent Conversation Management
// ============================================

async function fetchConversations() {
    try {
        const response = await fetch(CONVERSATIONS_URL);
        if (!response.ok) return;
        conversationsList = await response.json();
        renderConversationsList();
    } catch (err) {
        console.warn("Could not fetch conversations:", err);
    }
}

function renderConversationsList() {
    historyList.replaceChildren();

    if (!conversationsList || !conversationsList.length) {
        historyList.appendChild(
            createElement("p", "empty-history", "Your conversations will appear here.")
        );
        return;
    }

    const pinnedConvs = conversationsList.filter(c => c.is_pinned);
    const unpinnedConvs = conversationsList.filter(c => !c.is_pinned);

    if (pinnedConvs.length > 0) {
        const pinnedHeader = createElement("div", "history-group-header");
        pinnedHeader.appendChild(createElement("p", "history-group-label", "Pinned"));
        historyList.appendChild(pinnedHeader);

        pinnedConvs.forEach(conv => {
            historyList.appendChild(createConversationEntryElement(conv));
        });

        if (unpinnedConvs.length > 0) {
            const recentHeader = createElement("div", "history-group-header");
            recentHeader.appendChild(createElement("p", "history-group-label", "Recent"));
            historyList.appendChild(recentHeader);

            unpinnedConvs.forEach(conv => {
                historyList.appendChild(createConversationEntryElement(conv));
            });
        }
    } else {
        conversationsList.forEach(conv => {
            historyList.appendChild(createConversationEntryElement(conv));
        });
    }
}

function createConversationEntryElement(conv) {
    const entry = createElement("div", "history-entry");
    entry.dataset.id = conv.id;
    if (conv.id === activeConversationId) {
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
            renderConversationsList();
        });

        renameInput.addEventListener("keydown", e => {
            if (e.key === "Escape") {
                e.stopPropagation();
                renamingConvId = null;
                renderConversationsList();
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
        if (isLoading) return;
        if (conv.id === activeConversationId) return;
        loadConversation(conv.id);
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

    // Dynamic viewport positioning to prevent clipping by sidebar scroll container
    const rect = trigger.getBoundingClientRect();
    const menuWidth = 145;
    const menuHeight = historyDropdownMenu.offsetHeight || 125;

    let top = rect.bottom + 4;
    let left = rect.right - menuWidth;

    // Flip above if overflowing bottom
    if (top + menuHeight > window.innerHeight - 8) {
        top = rect.top - menuHeight - 4;
    }

    // Clamp strictly within viewport bounds
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
        renderConversationsList();
        return;
    }

    const conv = conversationsList.find(c => c.id === convId);
    if (!conv) return;

    if (conv.title === trimmed) {
        renamingConvId = null;
        renderConversationsList();
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
        renderConversationsList();
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
        renderConversationsList();
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

        if (convId === activeConversationId) {
            activeConversationId = null;
            try {
                localStorage.removeItem("clarify_active_conv_id");
            } catch {}

            if (conversationsList.length > 0) {
                await loadConversation(conversationsList[0].id);
            } else {
                await startNewConversation();
            }
        } else {
            renderConversationsList();
        }
    } catch (err) {
        console.error("Delete conversation failed:", err);
        alert("Could not delete conversation: " + (err.message || err));
    } finally {
        if (confirmDeleteBtn) confirmDeleteBtn.disabled = false;
    }
}

// Attach menu & modal handlers once
if (historyMenuRename) {
    historyMenuRename.addEventListener("click", () => {
        const convId = activeMenuConvId;
        closeHistoryDropdown();
        if (convId) {
            renamingConvId = convId;
            renderConversationsList();
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

async function createConversation(title = "New conversation", datasetId = null, datasetName = null) {
    try {
        const response = await fetch(CONVERSATIONS_URL, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                title: title || "New conversation",
                dataset_id: datasetId,
                dataset_name: datasetName
            })
        });
        return await readResponse(response);
    } catch (err) {
        console.error("Failed to create conversation:", err);
        throw err;
    }
}

async function postMessageToConversation(convId, role, content, extra = {}) {
    if (!convId) return null;
    try {
        const response = await fetch(`${CONVERSATIONS_URL}/${convId}/messages`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                role,
                content,
                sql: extra.sql || null,
                columns: extra.columns || null,
                rows: extra.rows || null,
                chart: extra.chart || null,
                is_error: extra.is_error || false,
                dataset_id: extra.dataset_id || null,
                dataset_name: extra.dataset_name || null
            })
        });
        return await readResponse(response);
    } catch (err) {
        console.error("Failed to persist message:", err);
        return null;
    }
}

async function loadConversation(conversationId) {
    if (isLoading) return;
    setLoading(true, "Loading conversation...");

    try {
        const response = await fetch(`${CONVERSATIONS_URL}/${conversationId}`);
        const conv = await readResponse(response);

        activeConversationId = conv.id;
        try {
            localStorage.setItem("clarify_active_conv_id", conv.id);
        } catch {
            // ignore
        }

        // Clear active conversation view
        messages.replaceChildren();
        resetResults();
        showFormMessage("", false);
        questionInput.value = "";
        questionInput.placeholder = "Ask a question about your dataset in plain English...";
        setSelectedFile(null);
        pendingCustomClarification = null;

        // Restore dataset state
        if (conv.dataset_id) {
            if (conv.dataset_available && conv.dataset_info) {
                currentDatasetId = conv.dataset_id;
                currentDatasetName = conv.dataset_name || "Uploaded dataset";
                renderDatasetPreview(conv.dataset_info, currentDatasetName);
            } else {
                currentDatasetId = null;
                currentDatasetName = "";
                datasetPanel.hidden = true;
                const missingName = conv.dataset_name ? `"${conv.dataset_name}"` : "previously uploaded";
                addMessage(
                    "assistant",
                    `⚠️ The dataset ${missingName} is no longer available on the server. You can upload a new dataset to continue querying.`,
                    true
                );
            }
        } else {
            currentDatasetId = null;
            currentDatasetName = "";
            datasetPanel.hidden = true;
        }

        // Restore messages in chronological order
        if (!conv.messages || conv.messages.length === 0) {
            welcome.hidden = false;
        } else {
            welcome.hidden = true;
            let lastResultMsg = null;

            conv.messages.forEach((msg, idx) => {
                const msgEl = addMessage(msg.role, msg.content, msg.is_error);
                if (msg.clarification_options && Array.isArray(msg.clarification_options) && msg.clarification_options.length > 0) {
                    const hasSubsequent = idx < conv.messages.length - 1;
                    const originalQ = (idx > 0 && conv.messages[idx - 1].role === "user") ? conv.messages[idx - 1].content : "";
                    const nextUserMsg = (hasSubsequent && conv.messages[idx + 1].role === "user") ? conv.messages[idx + 1].content : null;
                    const hasResolutionSql = Boolean(idx + 2 < conv.messages.length && conv.messages[idx + 2].sql);
                    renderClarificationOptions(msgEl, msg.clarification_options, originalQ, hasSubsequent, nextUserMsg, hasResolutionSql);
                }
                if (msg.sql || (msg.rows && msg.rows.length)) {
                    lastResultMsg = msg;
                }
            });

            // Restore the SQL code, results table and chart from the latest query
            if (lastResultMsg) {
                responseDetails.hidden = false;
                const sql = lastResultMsg.sql || "";
                updateSQL(sql, sql ? "READY" : "WAITING");
                renderResults({
                    columns: lastResultMsg.columns || [],
                    rows: lastResultMsg.rows || []
                });
                renderChart(lastResultMsg.chart || null);
            } else {
                resetResults();
            }
        }

        renderConversationsList();
        updateDatasetFormState();
        scrollMessagesToBottom(false);
    } catch (err) {
        console.error("Failed to load conversation:", err);
        showFormMessage("Could not load conversation: " + (err.message || err));
    } finally {
        setLoading(false);
        updateDatasetFormState();
        questionInput.focus();
    }
}

async function startNewConversation() {
    if (isLoading) return;

    // If current conversation is already empty (no messages, no dataset in DB or view), reuse it
    if (activeConversationId) {
        const currentConv = conversationsList.find(c => c.id === activeConversationId);
        if (currentConv && currentConv.message_count === 0 && !currentConv.dataset_id && messages.children.length === 0) {
            messages.replaceChildren();
            welcome.hidden = false;
            datasetPanel.hidden = true;
            resetResults();
            setSelectedFile(null);
            currentDatasetId = null;
            currentDatasetName = "";
            pendingCustomClarification = null;
            questionInput.value = "";
            questionInput.placeholder = "Ask a question about your dataset in plain English...";
            updateDatasetFormState();
            questionInput.focus();
            return;
        }
    }

    setLoading(true, "Starting new conversation...");
    try {
        const newConv = await createConversation("New conversation");
        activeConversationId = newConv.id;
        try {
            localStorage.setItem("clarify_active_conv_id", newConv.id);
        } catch {}

        // Clear active conversation view only; old conversations remain in sidebar
        messages.replaceChildren();
        welcome.hidden = false;
        datasetPanel.hidden = true;
        resetResults();
        setSelectedFile(null);
        currentDatasetId = null;
        currentDatasetName = "";
        pendingCustomClarification = null;
        questionInput.value = "";
        questionInput.placeholder = "Ask a question about your dataset in plain English...";
        showFormMessage("", false);

        await fetchConversations();
    } catch (err) {
        console.error("Could not start new conversation:", err);
        showFormMessage("Could not create new conversation: " + (err.message || err));
    } finally {
        setLoading(false);
        updateDatasetFormState();
        questionInput.focus();
    }
}

// ============================================
// 10. Upload dataset
// ============================================

async function uploadDataset(file) {
    if (!activeConversationId) {
        const newConv = await createConversation("New conversation");
        activeConversationId = newConv.id;
        try {
            localStorage.setItem("clarify_active_conv_id", newConv.id);
        } catch {}
    }

    const formData = new FormData();
    formData.append("file", file);
    if (activeConversationId) {
        formData.append("conversation_id", activeConversationId);
    }

    const response = await fetch(UPLOAD_URL, {
        method: "POST",
        body: formData
    });

    const data = await readResponse(response);

    if (!data.dataset_id) {
        throw new Error(
            "The upload endpoint did not return a dataset_id. The Python backend must return one."
        );
    }

    currentDatasetId = data.dataset_id;
    currentDatasetName = data.filename || file.name || "Uploaded dataset";

    renderDatasetPreview(data, currentDatasetName);

    return data;
}

// ============================================
// 11. Display query results
// ============================================

function renderResults(data) {
    resultsOutput.replaceChildren();

    const columns = Array.isArray(data.columns)
        ? [...data.columns]
        : [];

    let rows = Array.isArray(data.rows)
        ? data.rows
        : Array.isArray(data.results)
            ? data.results
            : [];

    if (
        rows.length > 0 &&
        !Array.isArray(rows[0]) &&
        typeof rows[0] === "object"
    ) {
        const inferredColumns = Object.keys(rows[0]);

        if (!columns.length) {
            columns.push(...inferredColumns);
        }

        rows = rows.map(row =>
            columns.map(column => row[column])
        );
    }

    if (
        !columns.length &&
        rows.length &&
        Array.isArray(rows[0])
    ) {
        rows[0].forEach((value, index) => {
            columns.push(`Column ${index + 1}`);
        });
    }

    resultCount.textContent =
        `${rows.length} row${rows.length === 1 ? "" : "s"}`;

    if (!columns.length) {
        resultsOutput.appendChild(
            createElement(
                "p",
                "muted-text",
                data.message ||
                "The query completed, but no tabular results were returned."
            )
        );

        return;
    }

    const wrapper = createElement("div", "preview-wrap");
    const table = createElement("table", "result-table");

    const thead = document.createElement("thead");
    const headerRow = document.createElement("tr");

    columns.forEach(column => {
        headerRow.appendChild(
            createElement("th", "", column)
        );
    });

    thead.appendChild(headerRow);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");

    rows.forEach(row => {
        const tr = document.createElement("tr");

        row.forEach(value => {
            tr.appendChild(
                createElement(
                    "td",
                    "",
                    value === null || value === undefined
                        ? "—"
                        : value
                )
            );
        });

        tbody.appendChild(tr);
    });

    table.appendChild(tbody);
    wrapper.appendChild(table);
    resultsOutput.appendChild(wrapper);

    if (!rows.length) {
        resultsOutput.appendChild(
            createElement(
                "p",
                "muted-text",
                "No matching records were found."
            )
        );
    }
}

// ============================================
// 12. Display chart
// ============================================

function renderChart(chart) {
    chartOutput.replaceChildren();

    if (!chart) {
        chartSection.hidden = true;
        return;
    }

    if (
        typeof chart === "string" &&
        chart.startsWith("data:image/")
    ) {
        const image = document.createElement("img");

        image.src = chart;
        image.alt = "Chart generated from query results";

        chartOutput.appendChild(image);
        chartSection.hidden = false;

        return;
    }

    if (
        typeof chart === "string" &&
        /^https?:\/\//i.test(chart)
    ) {
        const link = document.createElement("a");

        link.href = chart;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = "Open chart";

        chartOutput.appendChild(link);
        chartSection.hidden = false;

        return;
    }

    if (typeof chart === "string") {
        chartOutput.appendChild(
            createElement("p", "muted-text", chart)
        );

        chartSection.hidden = false;
        return;
    }

    chartSection.hidden = true;
}

// ============================================
// 13. SQL display
// ============================================

function updateSQL(sql, status = "READY") {
    sqlOutput.textContent = sql || "No SQL was returned.";
    sqlStatus.textContent = status.toUpperCase();

    sqlStatus.classList.remove("ready", "error");

    if (status.toLowerCase() === "ready") {
        sqlStatus.classList.add("ready");
    }

    if (status.toLowerCase() === "error") {
        sqlStatus.classList.add("error");
    }
}

// ============================================
// 14. Conversation and result reset
// ============================================

function showConversation() {
    welcome.hidden = true;
    updateDatasetFormState();
}

function resetResults() {
    responseDetails.hidden = true;

    updateSQL("Your SQL query will appear here.", "WAITING");

    resultsOutput.replaceChildren();

    resultsOutput.appendChild(
        createElement(
            "p",
            "muted-text",
            "Results will appear here after a query runs."
        )
    );

    resultCount.textContent = "";

    chartOutput.replaceChildren();
    chartSection.hidden = true;
}

// ============================================
// 15. Generate SQL from natural language
// ============================================

async function askQuestion(question) {
    const cleanQuestion = question.trim();

    if (!currentDatasetId) {
        showFormMessage("Please upload a dataset first.");
        return;
    }

    if (!cleanQuestion || isLoading) {
        return;
    }

    if (!activeConversationId) {
        const newConv = await createConversation(cleanQuestion.slice(0, 50), currentDatasetId, currentDatasetName);
        activeConversationId = newConv.id;
        try {
            localStorage.setItem("clarify_active_conv_id", newConv.id);
        } catch {}
    }

    const currentConvId = activeConversationId;

    showConversation();
    addMessage("user", cleanQuestion);

    questionInput.value = "";
    showFormMessage("", false);
    resetResults();

    setLoading(true, "Analyzing...");

    const loadingMessage = addMessage(
        "assistant",
        "Understanding your question and generating SQL..."
    );

    try {
        console.log("Sending query request:", QUERY_URL);

        const response = await fetch(QUERY_URL, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                dataset_id: currentDatasetId,
                question: cleanQuestion,
                conversation_id: currentConvId
            })
        });

        const data = await readResponse(response);
        console.log("Query API response:", data);

        loadingMessage.remove();

        // Ensure user hasn't switched to another conversation in the meantime
        if (activeConversationId !== currentConvId) {
            await fetchConversations();
            return;
        }

        if (data.clarification) {
            const msgEl = addMessage("assistant", data.clarification);
            if (Array.isArray(data.options) && data.options.length) {
                renderClarificationOptions(msgEl, data.options, cleanQuestion, false, null);
            }
            questionInput.placeholder = "Select an option above or click 'Other…' to type...";
            questionInput.focus();
            await fetchConversations();
            return;
        }

        addMessage(
            "assistant",
            data.answer ||
            data.explanation ||
            data.message ||
            "Your query has been processed."
        );

        responseDetails.hidden = false;

        const sql = data.sql || data.query || "";
        updateSQL(sql, sql ? "READY" : "WAITING");

        renderResults({
            columns: data.columns || [],
            rows: data.rows || data.results || [],
            message: data.message
        });

        renderChart(data.chart || data.chart_url || null);

        await fetchConversations();
    } catch (error) {
        loadingMessage.remove();
        console.error("ClarifySQL query failed:", error.message || error);

        if (activeConversationId === currentConvId) {
            addMessage(
                "assistant",
                error instanceof TypeError
                    ? "I couldn't connect to the Python backend. Make sure the API is running and the frontend endpoint is correct."
                    : error.message ||
                      "Something went wrong while processing your question.",
                true
            );
        }

        await fetchConversations();
    } finally {
        setLoading(false);
        questionInput.focus();
        scrollMessagesToBottom(true);
    }
}

async function submitClarification(originalQuestion, optionId, optionLabel) {
    if (!currentDatasetId || isLoading) return;

    if (!activeConversationId) {
        const newConv = await createConversation(originalQuestion.slice(0, 50), currentDatasetId, currentDatasetName);
        activeConversationId = newConv.id;
        try {
            localStorage.setItem("clarify_active_conv_id", newConv.id);
        } catch {}
    }

    const currentConvId = activeConversationId;
    showConversation();
    addMessage("user", optionLabel);

    questionInput.value = "";
    questionInput.placeholder = "Ask a question about your dataset in plain English...";
    showFormMessage("", false);
    resetResults();

    setLoading(true, "Applying your clarification...");

    const loadingMessage = addMessage(
        "assistant",
        "Understanding your selection and generating SQL..."
    );

    try {
        console.log("Sending clarification query to:", QUERY_URL);

        const response = await fetch(QUERY_URL, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                dataset_id: currentDatasetId,
                question: optionLabel,
                conversation_id: currentConvId,
                original_question: originalQuestion,
                selected_option_id: optionId,
                selected_option_label: optionLabel
            })
        });

        const data = await readResponse(response);
        console.log("Clarification API response:", data);

        loadingMessage.remove();

        if (activeConversationId !== currentConvId) {
            await fetchConversations();
            return;
        }

        if (data.clarification) {
            const msgEl = addMessage("assistant", data.clarification);
            if (Array.isArray(data.options) && data.options.length) {
                renderClarificationOptions(msgEl, data.options, originalQuestion, false, null);
            }
            questionInput.placeholder = "Select an option above or click 'Other…' to type...";
            questionInput.focus();
            await fetchConversations();
            return;
        }

        addMessage(
            "assistant",
            data.answer ||
            data.explanation ||
            data.message ||
            "Your query has been processed."
        );

        responseDetails.hidden = false;

        const sql = data.sql || data.query || "";
        updateSQL(sql, sql ? "READY" : "WAITING");

        renderResults({
            columns: data.columns || [],
            rows: data.rows || data.results || [],
            message: data.message
        });

        renderChart(data.chart || data.chart_url || null);

        await fetchConversations();
    } catch (error) {
        loadingMessage.remove();
        console.error("ClarifySQL clarification failed:", error.message || error);

        if (activeConversationId === currentConvId) {
            addMessage(
                "assistant",
                error instanceof TypeError
                    ? "I couldn't connect to the Python backend. Make sure the API is running and the frontend endpoint is correct."
                    : error.message ||
                      "Something went wrong while processing your clarification.",
                true
            );
        }

        await fetchConversations();
    } finally {
        setLoading(false);
        questionInput.focus();
        scrollMessagesToBottom(true);
    }
}

// ============================================
// 16. Form submission
// ============================================

async function handleSubmission(event) {
    if (event && typeof event.preventDefault === "function") {
        event.preventDefault();
    }

    if (isLoading) return;

    const question = questionInput.value.trim();

    if (!selectedDatasetFile && !currentDatasetId) {
        showFormMessage(
            "Please choose a CSV or Excel file first."
        );
        return;
    }

    showFormMessage("", false);

    if (selectedDatasetFile) {
        setLoading(true, "Uploading...");

        try {
            const fileToUpload = selectedDatasetFile;

            const data = await uploadDataset(fileToUpload);

            selectedDatasetFile = null;
            fileInput.value = "";
            selectedFile.hidden = true;

            showFormMessage(
                "Dataset uploaded successfully.",
                false
            );

            showConversation();
            updateDatasetFormState();

            const readyText = `Your dataset "${data.filename || currentDatasetName}" is ready.`;
            addMessage("assistant", readyText);
            await postMessageToConversation(activeConversationId, "assistant", readyText, {
                dataset_id: currentDatasetId,
                dataset_name: currentDatasetName
            });

            if (question) {
                setLoading(false);
                await askQuestion(question);
                return;
            }

            setLoading(false);

            const promptText = "What do you want to know about this data?";
            addMessage("assistant", promptText);
            await postMessageToConversation(activeConversationId, "assistant", promptText, {
                dataset_id: currentDatasetId,
                dataset_name: currentDatasetName
            });

            questionInput.placeholder = promptText;
            questionInput.focus();

            await fetchConversations();
        } catch (error) {
            console.error("ClarifySQL upload failed:", error);

            showFormMessage(
                error instanceof TypeError
                    ? "Could not connect to the Python backend. The upload API needs to be running."
                    : error.message ||
                      "The file could not be uploaded."
            );
        } finally {
            setLoading(false);
        }
        return;
    }

    if (currentDatasetId) {
        if (pendingCustomClarification && pendingCustomClarification.conversationId === activeConversationId) {
            const customClarification = question.trim();
            if (!customClarification) {
                showFormMessage("Please type your clarification.");
                questionInput.focus();
                return;
            }
            const origQ = pendingCustomClarification.originalQuestion;
            const container = pendingCustomClarification.optionsContainer;
            if (container) {
                container.querySelectorAll("button").forEach(b => b.disabled = true);
            }
            pendingCustomClarification = null;
            questionInput.placeholder = "Ask a question about your dataset in plain English...";
            await submitClarification(origQ, "other", customClarification);
            return;
        }

        if (!question) {
            showFormMessage("Please enter a question about your dataset.");
            questionInput.focus();
            return;
        }

        await askQuestion(question);
    }
}

// ============================================
// 17. File picker and drag-and-drop
// ============================================

uploadZone.addEventListener("click", () => {
    if (!isLoading) {
        fileInput.click();
    }
});

fileInput.addEventListener("change", () => {
    if (fileInput.files && fileInput.files[0]) {
        setSelectedFile(fileInput.files[0]);
    }
});

removeFileButton.addEventListener("click", () => {
    if (!isLoading) {
        setSelectedFile(null);
    }
});

changeFileButton.addEventListener("click", () => {
    if (!isLoading) {
        fileInput.click();
    }
});

if (inlineChangeFileButton) {
    inlineChangeFileButton.addEventListener("click", () => {
        if (!isLoading) {
            fileInput.click();
        }
    });
}

uploadZone.addEventListener("dragover", event => {
    event.preventDefault();
    uploadZone.classList.add("drag-over");
});

uploadZone.addEventListener("dragleave", () => {
    uploadZone.classList.remove("drag-over");
});

uploadZone.addEventListener("drop", event => {
    event.preventDefault();

    uploadZone.classList.remove("drag-over");

    const file = event.dataTransfer.files[0];

    if (file) {
        setSelectedFile(file);
    }
});

// ============================================
// 18. Connect submission handlers
// ============================================

console.log("ClarifySQL: submit handler attached");

uploadForm.addEventListener("submit", (event) => {
    event.preventDefault();
    handleSubmission(event);
});

sendButton.addEventListener("click", (event) => {
    event.preventDefault();
    handleSubmission(event);
});

// Enter submits the question; Shift+Enter inserts a new line.
questionInput.addEventListener("keydown", (event) => {
    if (
        event.key === "Enter" &&
        !event.shiftKey &&
        !event.isComposing
    ) {
        event.preventDefault();
        handleSubmission(event);
    }
});

// ============================================
// 19. Copy SQL
// ============================================

copySQLButton.addEventListener("click", async () => {
    const sql = sqlOutput.textContent.trim();

    if (
        !sql ||
        sql === "Your SQL query will appear here."
    ) {
        return;
    }

    try {
        await navigator.clipboard.writeText(sql);

        copySQLButton.textContent = "Copied!";

        setTimeout(() => {
            copySQLButton.textContent = "Copy SQL";
        }, 1500);
    } catch {
        const selection = document.createElement("textarea");

        selection.value = sql;

        document.body.appendChild(selection);

        selection.select();

        document.execCommand("copy");

        selection.remove();

        copySQLButton.textContent = "Copied!";
    }
});

// ============================================
// 20. New chat button
// ============================================

newChatButton.addEventListener("click", () => {
    startNewConversation();
});

// ============================================
// 21. Initialize application
// ============================================

async function initClarifySQL() {
    resetResults();
    await fetchConversations();

    let targetConvId = null;
    try {
        targetConvId = localStorage.getItem("clarify_active_conv_id");
    } catch {}

    if (targetConvId && conversationsList.some(c => c.id === targetConvId)) {
        await loadConversation(targetConvId);
    } else if (conversationsList.length > 0) {
        await loadConversation(conversationsList[0].id);
    } else {
        await startNewConversation();
    }

    updateDatasetFormState();
    console.log("ClarifySQL persistent history initialized.");
}

initClarifySQL();
