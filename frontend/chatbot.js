"use strict";

// ============================================
// 1. Backend configuration
// ============================================

const API_BASE = "http://127.0.0.1:8000";
const UPLOAD_URL = `${API_BASE}/upload`;
const QUERY_URL = `${API_BASE}/query`;

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

// ============================================
// 3. Application state
// ============================================

let selectedDatasetFile = null;
let currentDatasetId = null;
let currentDatasetName = "";
let isLoading = false;
let queryHistory = [];

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

function formatFileSize(bytes) {
    if (bytes < 1024) return `${bytes} B`;

    if (bytes < 1024 * 1024) {
        return `${(bytes / 1024).toFixed(1)} KB`;
    }

    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
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

    message.scrollIntoView({
        behavior: "smooth",
        block: "nearest"
    });

    return message;
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
            createElement("span", "meta-chip", `${rowCount} rows`)
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
// 9. Upload dataset
// ============================================

async function uploadDataset(file) {
    const formData = new FormData();

    formData.append("file", file);

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

    try {
        sessionStorage.setItem("clarify_dataset_id", currentDatasetId);
        sessionStorage.setItem("clarify_dataset_name", file.name);
        sessionStorage.setItem("clarify_dataset_data", JSON.stringify(data));
    } catch {
        // Ignore storage errors
    }

    renderDatasetPreview(data, file.name);

    return data;
}

// ============================================
// 10. Display query results
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
// 11. Display chart
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
// 12. SQL display
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
// 13. Query history
// ============================================

function saveHistory(question, sql) {
    queryHistory.unshift({
        question,
        sql,
        time: new Date().toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit"
        })
    });

    queryHistory = queryHistory.slice(0, 10);

    renderHistory();
}

function renderHistory() {
    historyList.replaceChildren();

    if (!queryHistory.length) {
        historyList.appendChild(
            createElement(
                "p",
                "empty-history",
                "Your queries will appear here."
            )
        );

        return;
    }

    queryHistory.forEach(item => {
        const entry = createElement("div", "history-entry");

        const question = createElement(
            "p",
            "history-question",
            item.question
        );

        const time = createElement(
            "small",
            "history-time",
            item.time
        );

        entry.append(question, time);
        historyList.appendChild(entry);
    });
}

// ============================================
// 14. Conversation and result reset
// ============================================

function showConversation() {
    welcome.hidden = true;
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
                question: cleanQuestion
            })
        });

        const data = await readResponse(response);

        console.log("Query API response:", data);

        loadingMessage.remove();

        if (data.clarification) {
            addMessage("assistant", data.clarification);

            questionInput.placeholder =
                "Please clarify your question...";

            questionInput.focus();

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

        if (sql) {
            saveHistory(cleanQuestion, sql);
        }
    } catch (error) {
        loadingMessage.remove();

        console.error("ClarifySQL query failed:", error.message || error);

        addMessage(
            "assistant",
            error instanceof TypeError
                ? "I couldn't connect to the Python backend. Make sure the API is running and the frontend endpoint is correct."
                : error.message ||
                  "Something went wrong while processing your question.",
            true
        );
    } finally {
        setLoading(false);

        questionInput.focus();

        conversationArea.scrollTop =
            conversationArea.scrollHeight;
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

            addMessage(
                "assistant",
                `Your dataset "${data.filename || currentDatasetName}" is ready.`
            );

            if (question) {
                setLoading(false);
                await askQuestion(question);
                return;
            }

            setLoading(false);

            addMessage(
                "assistant",
                "What do you want to know about this data?"
            );

            questionInput.placeholder =
                "What do you want to know about this data?";

            questionInput.focus();
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
// 20. New chat
// ============================================

newChatButton.addEventListener("click", () => {
    if (isLoading) return;

    messages.replaceChildren();

    welcome.hidden = false;
    datasetPanel.hidden = true;
    responseDetails.hidden = true;

    setSelectedFile(null);

    currentDatasetId = null;
    currentDatasetName = "";

    try {
        sessionStorage.removeItem("clarify_dataset_id");
        sessionStorage.removeItem("clarify_dataset_name");
        sessionStorage.removeItem("clarify_dataset_data");
    } catch {
        // Ignore
    }

    questionInput.value = "";

    questionInput.placeholder =
        "What do you want to know about this data?";

    showFormMessage("", false);

    resetResults();

    queryHistory = [];

    renderHistory();

    questionInput.focus();
});

// ============================================
// 21. Initialize application
// ============================================

renderHistory();
resetResults();

try {
    const savedId = sessionStorage.getItem("clarify_dataset_id");
    const savedName = sessionStorage.getItem("clarify_dataset_name");
    const savedData = sessionStorage.getItem("clarify_dataset_data");
    if (savedId && savedData) {
        currentDatasetId = savedId;
        currentDatasetName = savedName || "Uploaded dataset";
        renderDatasetPreview(JSON.parse(savedData), currentDatasetName);
        showConversation();
        addMessage(
            "assistant",
            `Dataset "${currentDatasetName}" is ready. What do you want to know about this data?`
        );
    }
} catch {
    // Ignore restore error
}

console.log("ClarifySQL frontend initialized.");              