document.addEventListener("DOMContentLoaded", () => {
    const token =
        localStorage.getItem("authToken") ||
        localStorage.getItem("token") ||
        localStorage.getItem("jobgenix_token");
    const API_BASE = window.API_BASE_URL || "http://localhost:8000";
    const apiUrl = (path) =>
        path.startsWith("http") ? path : `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;

    if (!token) {
        window.location.href = "/pages/auth/login.html";
        return;
    }

    const headers = {
        Authorization: "Bearer " + token,
        "Content-Type": "application/json",
    };

    const conversationList = document.getElementById("conversationList");
    const chatMessages = document.getElementById("chatMessages");
    const chatTitle = document.getElementById("chatTitle");
    const chatSubtitle = document.getElementById("chatSubtitle");
    const chatMeta = document.getElementById("chatMeta");
    const messageInput = document.getElementById("messageInput");
    const sendBtn = document.getElementById("sendBtn");
    const refreshBtn = document.getElementById("refreshBtn");

    let currentConversationId = null;

    const clearSession = () => {
        ["authToken", "token", "jobgenix_token"].forEach((k) =>
            localStorage.removeItem(k)
        );
        localStorage.removeItem("user");
    };

    const logoutBtn = document.getElementById("companyLogoutBtn");
    if (logoutBtn) {
        logoutBtn.addEventListener("click", () => {
            try {
                if (window.auth && typeof auth.logout === "function") {
                    auth.logout();
                    return;
                }
            } catch (_) {}
            clearSession();
            window.location.href = "/pages/auth/login.html";
        });
    }

    function renderConversations(conversations) {
        if (!conversations || !conversations.length) {
            conversationList.innerHTML =
                '<p class="panel-placeholder">No conversations yet.</p>';
            return;
        }
        conversationList.innerHTML = "";
        conversations.forEach((c, idx) => {
            const item = document.createElement("div");
            item.className = "conversation-item";
            if (!currentConversationId && idx === 0) {
                currentConversationId = c.conversation_id;
            }
            if (currentConversationId === c.conversation_id) {
                item.classList.add("active");
            }
            const title = document.createElement("div");
            title.className = "conversation-title";
            const who = c.job_seeker_email || c.job_seeker_name || c.current_title || '';
            title.textContent = who || '';

            const snippet = document.createElement("div");
            snippet.className = "conversation-snippet";
            snippet.textContent = c.message_text || "No messages";

            const meta = document.createElement("div");
            meta.className = "conversation-meta";
            const namePart = c.job_seeker_email || c.job_seeker_name || "";
            const timePart = c.created_at
                ? new Date(c.created_at).toLocaleString()
                : "";
            meta.textContent = [namePart, timePart].filter(Boolean).join(" • ");

            item.appendChild(title);
            item.appendChild(snippet);
            item.appendChild(meta);

            item.addEventListener("click", () => {
                currentConversationId = c.conversation_id;
                loadMessages(currentConversationId);
                document
                    .querySelectorAll(".conversation-item.active")
                    .forEach((el) => el.classList.remove("active"));
                item.classList.add("active");
            });

            conversationList.appendChild(item);
        });
    }

    function renderMessages(messages) {
        if (!messages || !messages.length) {
            chatMessages.innerHTML =
                '<p class="panel-placeholder">No messages in this conversation.</p>';
            return;
        }
        chatMessages.innerHTML = "";
        messages.forEach((m) => {
            const bubble = document.createElement("div");
            bubble.className = "bubble";
            if (m.sender_type === "company") {
                bubble.classList.add("me");
            }
            bubble.textContent = m.message_text || "(no text)";
            const meta = document.createElement("span");
            meta.className = "meta";
            meta.textContent = m.created_at
                ? new Date(m.created_at).toLocaleString()
                : "";
            bubble.appendChild(meta);
            chatMessages.appendChild(bubble);
        });
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    async function loadConversations() {
        conversationList.innerHTML =
            '<p class="panel-placeholder">Loading conversations...</p>';
        try {
            const res = await fetch(apiUrl("/api/company/messages"), {
                headers,
            });
            if (res.status === 401 || res.status === 403) {
                clearSession();
                window.location.href = "/pages/auth/login.html";
                return;
            }
            const data = await res.json();
            if (!res.ok) {
                console.error("Failed to load conversations:", data);
                conversationList.innerHTML =
                    '<p class="panel-placeholder">Unable to load conversations.</p>';
                return;
            }
            renderConversations(data.conversations || []);
            if (currentConversationId) {
                loadMessages(currentConversationId);
            }
        } catch (err) {
            console.error("Conversations load error:", err);
            conversationList.innerHTML =
                '<p class="panel-placeholder">Unable to load conversations.</p>';
        }
    }

    async function loadMessages(conversationId) {
        if (!conversationId) {
            chatMessages.innerHTML =
                '<p class="panel-placeholder">No conversation selected.</p>';
            return;
        }
        chatMessages.innerHTML =
            '<p class="panel-placeholder">Loading messages...</p>';
        try {
            const res = await fetch(
                apiUrl(`/api/company/messages?conversation_id=${conversationId}`),
                { headers }
            );
            if (res.status === 401 || res.status === 403) {
                clearSession();
                window.location.href = "/pages/auth/login.html";
                return;
            }
            const data = await res.json();
            if (!res.ok) {
                console.error("Failed to load messages:", data);
                chatMessages.innerHTML =
                    '<p class="panel-placeholder">Unable to load messages.</p>';
                return;
            }
            const firstMsg = (data.messages || [])[0] || {};
            const participant =
                firstMsg.job_seeker_email ||
                firstMsg.job_seeker_name ||
                firstMsg.current_title ||
                "";
            chatTitle.textContent = participant || "";
            chatSubtitle.textContent = participant ? `Conversation with ${participant}` : "Direct messages";
            chatMeta.textContent = `${(data.messages || []).length} messages`;
            renderMessages(data.messages || []);
        } catch (err) {
            console.error("Messages load error:", err);
            chatMessages.innerHTML =
                '<p class="panel-placeholder">Unable to load messages.</p>';
        }
    }

    async function sendMessage() {
        if (!currentConversationId) {
            alert("Select a conversation first.");
            return;
        }
        const text = (messageInput.value || "").trim();
        if (!text) {
            alert("Enter a message before sending.");
            return;
        }
        sendBtn.disabled = true;
        try {
            const res = await fetch(apiUrl("/api/company/messages"), {
                method: "POST",
                headers,
                body: JSON.stringify({
                    conversation_id: currentConversationId,
                    message_text: text,
                    message_type: "text",
                }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                alert(data.error || "Failed to send message");
                return;
            }
            messageInput.value = "";
            await loadMessages(currentConversationId);
        } catch (err) {
            console.error("Send message error:", err);
            alert("Network error while sending message.");
        } finally {
            sendBtn.disabled = false;
        }
    }

    sendBtn?.addEventListener("click", sendMessage);
    refreshBtn?.addEventListener("click", loadConversations);
    messageInput?.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // If conversation id is provided in URL, set it first
    const urlParams = new URLSearchParams(window.location.search);
    const convFromUrl = urlParams.get("conversation_id");
    if (convFromUrl) {
        currentConversationId = Number(convFromUrl);
    }

    loadConversations();
    if (currentConversationId) {
        loadMessages(currentConversationId);
    }
});
