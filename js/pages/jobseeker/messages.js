const rawAppBase = window.JobGenixApp?.apiBase || window.JobGenixApp?.apiBaseUrl;
const apiBaseFromApp = rawAppBase ? rawAppBase.replace(/\/api\/?$/, "") : null;
const API_BASE =
    window.API_BASE_URL ||
    apiBaseFromApp ||
    (location.origin.includes("8001")
        ? location.origin.replace("8001", "8000")
        : "http://localhost:8000");
const apiUrl = (path) =>
    path.startsWith("http")
        ? path
        : `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
const TOKEN_KEYS = ["auth_token", "authToken", "token", "jobgenix_token"];
const getToken = () => {
    if (window.JobGenixApp?.getToken) {
        return window.JobGenixApp.getToken();
    }
    for (const key of TOKEN_KEYS) {
        const stored = localStorage.getItem(key);
        if (stored) return stored;
    }
    return null;
};

let threads = [];
let selectedThread = null;
let pendingThreadId = null;

async function authedFetch(url, options = {}) {
    const token = getToken();
    if (!token) throw new Error("Authentication token is missing");
    const opts = { ...options, headers: { ...(options.headers || {}), Authorization: "Bearer " + token } };
    return fetch(url, opts);
}

async function loadThreads() {
    try {
        const res = await authedFetch(apiUrl("/api/messages/conversations"));
        const data = await res.json().catch(() => ({}));
        threads = data.conversations || [];
        renderThreads(threads);
        if (pendingThreadId) {
            selectThread(Number(pendingThreadId));
        } else if (threads.length) {
            selectThread(threads[0].id);
        } else {
            renderEmptyChat();
        }
    } catch (err) {
        console.error("Failed to load conversations", err);
    }
}

async function loadMessages(convId) {
    try {
        const res = await authedFetch(apiUrl(`/api/messages/conversations/${convId}/messages`));
        const data = await res.json().catch(() => ({}));
        const msgs = data.messages || [];
        const thread = threads.find((t) => t.id === convId);
        if (thread) {
            thread.messages = msgs.map((m) => ({
                from: m.sender_type === "job_seeker" ? "me" : "them",
                text: m.message_text,
                time: formatTime(m.created_at),
            }));
            renderChat(thread);
        }
    } catch (err) {
        console.error("Failed to load messages", err);
    }
}

function renderThreads(list) {
    const container = document.getElementById("threadList");
    if (!container) return;
    container.innerHTML = list
        .map(
            (t) => `
        <div class="thread-item ${selectedThread?.id === t.id ? "active" : ""}" data-id="${t.id}">
            <div>
                <div class="thread-title">${t.company_name || "Company"}</div>
                <div class="thread-meta">${t.job_title || ""}</div>
            </div>
            <div class="thread-time">${formatRelative(t.last_message_at)}</div>
        </div>
    `
        )
        .join("");
}

function renderChat(thread) {
    selectedThread = thread;
    renderThreads(threads);

    const chatBody = document.getElementById("chatBody");
    if (!chatBody) return;
    chatBody.innerHTML = (thread.messages || [])
        .map(
            (m) => `
        <div class="chat-bubble ${m.from === "me" ? "me" : "them"}">
            <div>${m.text}</div>
            <div class="bubble-meta">${m.time}</div>
        </div>
    `
        )
        .join("");

    document.getElementById("chatCompany").textContent = thread.company_name || "Company";
    document.getElementById("chatTitle").textContent = thread.job_title || "Conversation";
    document.getElementById("chatMeta").textContent = `${thread.job_title || "Conversation"} ƒ?› ${
        thread.last_message_text ? "Active" : ""
    }`;
    document.getElementById("chatStatus").textContent = "Active";

    const body = document.getElementById("chatBody");
    if (body) body.scrollTop = body.scrollHeight;
}

function renderEmptyChat() {
    const chatBody = document.getElementById("chatBody");
    if (chatBody) chatBody.innerHTML = '<p class="muted">No conversations yet.</p>';
}

function selectThread(id) {
    const thread = threads.find((t) => t.id === id);
    if (!thread) return;
    loadMessages(id);
}

function setupThreadClicks() {
    const list = document.getElementById("threadList");
    if (!list) return;
    list.addEventListener("click", (e) => {
        const item = e.target.closest(".thread-item");
        if (item) {
            selectThread(Number(item.dataset.id));
        }
    });
}

function setupSend() {
    const sendBtn = document.getElementById("sendBtn");
    const input = document.getElementById("messageInput");
    if (!sendBtn || !input) return;
    sendBtn.addEventListener("click", async () => {
        if (!selectedThread) return alert("Pick a conversation first.");
        const text = input.value.trim();
        if (!text) return;
        try {
            await authedFetch(apiUrl(`/api/messages/conversations/${selectedThread.id}/messages`), {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ text }),
            });
            input.value = "";
            await loadMessages(selectedThread.id);
        } catch (err) {
            console.error("Send failed", err);
            alert("Failed to send message.");
        }
    });
}

function setupSearch() {
    const search = document.getElementById("messageSearch");
    if (!search) return;
    search.addEventListener("input", () => {
        const q = search.value.toLowerCase();
        const filtered = threads.filter(
            (t) =>
                (t.company_name || "").toLowerCase().includes(q) ||
                (t.job_title || "").toLowerCase().includes(q)
        );
        renderThreads(filtered);
    });
}

function formatTime(ts) {
    if (!ts) return "";
    try {
        const d = new Date(ts);
        return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    } catch {
        return ts;
    }
}

function formatRelative(ts) {
    if (!ts) return "";
    try {
        const d = new Date(ts);
        const now = new Date();
        const diff = now - d;
        const mins = Math.floor(diff / 60000);
        if (mins < 60) return `${mins}m ago`;
        const hrs = Math.floor(mins / 60);
        if (hrs < 24) return `${hrs}h ago`;
        return d.toLocaleDateString();
    } catch {
        return ts;
    }
}

document.addEventListener("DOMContentLoaded", () => {
    pendingThreadId = new URLSearchParams(window.location.search).get("conversation_id");
    loadThreads();
    setupThreadClicks();
    setupSend();
    setupSearch();
});
