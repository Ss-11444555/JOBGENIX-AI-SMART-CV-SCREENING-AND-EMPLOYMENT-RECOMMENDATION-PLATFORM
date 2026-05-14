const rawAppBase = window.JobGenixApp?.apiBase || window.JobGenixApp?.apiBaseUrl;
const apiBaseFromApp = rawAppBase ? rawAppBase.replace(/\/api\/?$/, "") : null;
const API_BASE =
    window.API_BASE_URL ||
    apiBaseFromApp ||
    (location.origin.includes("8001")
        ? location.origin.replace("8001", "8000")
        : "http://localhost:8000");
const apiUrl = (path) =>
    path.startsWith("http") ? path : `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
const TOKEN_KEYS = ["auth_token", "authToken", "token", "jobgenix_token"];
const LOGOUT_KEYS = ["auth_token", "authToken", "token", "jobgenix_token"];

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

const escapeHtml = (value) => {
    if (!value) return "";
    return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
};

const formatRelative = (timestamp) => {
    if (!timestamp) return "";
    const date = new Date(timestamp);
    if (Number.isNaN(date.getTime())) return timestamp;
    const diff = Date.now() - date.getTime();
    if (diff < 60000) return "Just now";
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
    return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
};

const formatDateShort = (timestamp) => {
    if (!timestamp) return "";
    try {
        return new Date(timestamp).toLocaleString();
    } catch {
        return timestamp;
    }
};

let allowNavigationAway = false;
const lockOverlayId = "adminLockOverlay";

const clearAuthTokens = () => {
    LOGOUT_KEYS.forEach((key) => localStorage.removeItem(key));
    localStorage.removeItem("user");
};

const navigateToLogin = () => {
    allowNavigationAway = true;
    window.location.href = "/pages/auth/login.html";
};

const handleLogoutClick = () => {
    if (window.auth && typeof window.auth.logout === "function") {
        window.auth.logout();
    }
    clearAuthTokens();
    navigateToLogin();
};

const logoutPromptId = "adminLogoutPrompt";
const showLogoutPrompt = () => {
    closeLogoutPrompt();
    const overlay = document.createElement("div");
    overlay.id = logoutPromptId;
    overlay.className = "admin-lock-overlay";
    overlay.innerHTML = `
        <div class="admin-lock-card">
            <p>Are you sure you want to log out?</p>
            <div style="display:flex;gap:0.75rem;justify-content:center;">
                <button class="btn btn-sm btn-outline" id="cancelLogoutPrompt">Cancel</button>
                <button class="btn btn-sm btn-primary" id="confirmLogoutPrompt">Logout</button>
            </div>
        </div>
    `;
    document.body.appendChild(overlay);
    overlay.querySelector("#cancelLogoutPrompt")?.addEventListener("click", closeLogoutPrompt);
    overlay.querySelector("#confirmLogoutPrompt")?.addEventListener("click", () => {
        closeLogoutPrompt();
        handleLogoutClick();
    });
};

const closeLogoutPrompt = () => {
    const existing = document.getElementById(logoutPromptId);
    if (existing) {
        existing.remove();
    }
};

const closeLockOverlay = () => {
    const existing = document.getElementById(lockOverlayId);
    if (existing) {
        existing.remove();
    }
};

const showLockOverlay = () => {
    if (allowNavigationAway) return;
    closeLockOverlay();
    const overlay = document.createElement("div");
    overlay.id = lockOverlayId;
    overlay.className = "admin-lock-overlay";
    overlay.innerHTML = `
        <div class="admin-lock-card">
            <p>Please log out before leaving this secure page.</p>
            <button class="btn btn-primary" id="lockLogoutBtn">Logout</button>
        </div>
    `;
    document.body.appendChild(overlay);
    overlay.querySelector("#lockLogoutBtn")?.addEventListener("click", handleLogoutClick);
};

const enforceStayPage = () => {
    history.pushState(null, "", location.href);
    window.addEventListener("popstate", () => {
        if (allowNavigationAway) return;
        allowNavigationAway = true;
        window.location.href = "/";
    });
    window.addEventListener("beforeunload", (event) => {
        if (allowNavigationAway) return;
        event.preventDefault();
        event.returnValue = "";
    });
};

const healthModalId = "adminHealthModal";

const closeHealthModal = () => {
    const existing = document.getElementById(healthModalId);
    if (existing) {
        existing.remove();
    }
};

const renderHealthModal = (payload) => {
    closeHealthModal();
    const overlay = document.createElement("div");
    overlay.id = healthModalId;
    overlay.className = "health-modal-overlay";
    const tables = payload?.tables || {};
    const tableRows = Object.entries(tables)
        .map(([name, value]) => {
            let state = "warn";
            if (value === true) state = "ok";
            else if (value === false) state = "missing";
            else if (typeof value === "string" && value.toLowerCase().startsWith("error")) state = "error";
            return `
                <div class="health-table-row">
                    <span class="health-table-name">${name}</span>
                    <span class="health-table-value ${state}">${value === true ? "ok" : value === false ? "not found" : value}</span>
                </div>
            `;
        })
        .join("");

    const dbStatus = payload?.database || {};
    overlay.innerHTML = `
        <div class="health-modal">
            <div class="health-modal-header">
                <h3>System Health</h3>
                <button class="health-close-btn" aria-label="Close">×</button>
            </div>
            <div class="health-modal-body">
                <section class="health-section">
                    <p class="health-label">Database</p>
                    <p class="health-value ${dbStatus.status === "ok" ? "ok" : "error"}">
                        ${dbStatus.status || "unknown"} ${dbStatus.details ? `— ${dbStatus.details}` : ""}
                    </p>
                    <small>Last checked: ${payload.last_checked || "unknown"}</small>
                </section>
                <section class="health-section">
                    <p class="health-label">Tables</p>
                    <div class="health-table">
                        ${tableRows || '<div class="health-table-row"><span class="health-table-name">No table data</span></div>'}
                    </div>
                </section>
                <section class="health-section">
                    <p class="health-label">Status</p>
                    <p class="health-status-pill ${payload.status === "ok" ? "ok" : "warn"}">
                        ${payload.status || "unknown"}
                    </p>
                </section>
            </div>
        </div>
    `;
    document.body.appendChild(overlay);

    overlay.querySelector(".health-close-btn")?.addEventListener("click", closeHealthModal);
    overlay.addEventListener("click", (ev) => {
        if (ev.target === overlay) {
            closeHealthModal();
        }
    });
};

const fetchSystemHealth = async (headers = {}) => {
    try {
        closeHealthModal();
        const loadingModal = document.createElement("div");
        loadingModal.className = "health-modal-overlay";
        loadingModal.id = "health-loading";
        loadingModal.innerHTML = `
            <div class="health-modal">
                <p style="margin:0;">Checking system health…</p>
            </div>
        `;
        document.body.appendChild(loadingModal);

        const res = await fetch(apiUrl("/api/admin/health"), {
            headers,
        });
        const payload = await res.json().catch(() => ({}));
        loadingModal.remove();
        if (!res.ok) {
            renderHealthModal({
                status: "error",
                database: { status: "error", details: payload.error || "Unable to reach admin health" },
                tables: {},
                last_checked: new Date().toISOString(),
            });
            return;
        }
        renderHealthModal(payload);
    } catch (error) {
        closeHealthModal();
        console.error("Admin health failed", error);
        alert("Unable to fetch system health at the moment.");
    }
};

document.addEventListener("DOMContentLoaded", () => {
    const token = getToken();
    if (!token) {
        window.location.href = "/pages/auth/login.html";
        return;
    }

    const headers = {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
    };

    const statIds = [
        "totalUsers",
        "jobSeekers",
        "companies",
        "totalJobs",
        "activeJobs",
        "pendingJobs",
        "totalApplications",
        "hired",
        "interviews",
        "aiMatches",
    ];

    const updateStat = (id, value) => {
        const el = document.getElementById(id);
        if (!el) return;
        el.textContent = value != null ? value.toString() : "0";
    };

    const renderStats = (stats) => {
        statIds.forEach((id) => updateStat(id, stats[id] ?? 0));
        updateStat("matchRate", `${stats.matchRate ?? 0}%`);
        updateStat("successRate", `${stats.successRate ?? 0}%`);
    };

    const activityList = document.getElementById("activityList");
    const renderActivity = (items) => {
        if (!activityList) return;
        if (!items || !items.length) {
            activityList.innerHTML = '<p class="activity-empty">No recent activity yet.</p>';
            return;
        }
        activityList.innerHTML = items
            .map((activity) => {
                const jobLabel = escapeHtml(activity.job_title || `Job #${activity.id || ""}`);
                const statusLabel = escapeHtml(activity.status || "Update");
                const timeLabel = formatRelative(activity.time);
                const meta = activity.time ? new Date(activity.time).toLocaleString() : "Pending";
                return `
                    <div class="activity-item">
                        <div class="activity-info">
                            <div style="display:flex;gap:.5rem;align-items:center;flex-wrap:wrap;">
                                <strong>${jobLabel}</strong>
                                <span class="activity-status">${statusLabel}</span>
                            </div>
                            <span class="activity-meta">${meta}</span>
                        </div>
                        <div class="activity-time">${timeLabel}</div>
                    </div>
                `;
            })
            .join("");
    };

    const pendingJobsContainer = document.getElementById("pendingJobsList");
    const auditListContainer = document.getElementById("auditList");

    const renderPendingApprovals = (items) => {
        if (!pendingJobsContainer) return;
        if (!items || !items.length) {
            pendingJobsContainer.innerHTML = '<p class="panel-placeholder">No pending approvals.</p>';
            return;
        }
        pendingJobsContainer.innerHTML = items
            .map(
                (job) => `
                    <article class="pending-job-item">
                        <strong>${escapeHtml(job.title || "Untitled Job")}</strong>
                        <div class="pending-job-meta">
                            ${escapeHtml(job.company || "Unknown company")}
                            &middot; ${formatDateShort(job.createdAt || job.updatedAt)}
                        </div>
                    </article>
                `
            )
            .join("");
    };

    const renderUserAudits = (audits) => {
        if (!auditListContainer) return;
        if (!audits || !audits.length) {
            auditListContainer.innerHTML = '<p class="panel-placeholder">No audit entries yet.</p>';
            return;
        }
        auditListContainer.innerHTML = audits
            .map(
                (audit) => `
                    <article class="audit-entry">
                        <span class="audit-type">${escapeHtml(audit.type || "audit")}</span>
                        <strong>${escapeHtml(audit.title || "Audit event")}</strong>
                        <div class="audit-meta">
                            ${escapeHtml(audit.userEmail || "System")} &middot;
                            ${audit.relatedEntityType ? ` ${escapeHtml(audit.relatedEntityType)}` : ""}
                            ${formatDateShort(audit.createdAt)}
                        </div>
                        <p>${escapeHtml(audit.message || "")}</p>
                    </article>
                `
            )
            .join("");
    };

    const loadOverview = async () => {
        const placeholder = document.getElementById("activityList");
        if (placeholder) {
            placeholder.innerHTML = '<p class="activity-empty">Loading activity…</p>';
        }
        try {
            const res = await fetch(apiUrl("/api/admin/overview"), {
                headers,
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                console.error("Failed to load admin overview", data);
                if (placeholder) {
                    placeholder.innerHTML = `<p class="activity-empty">Unable to load activity. ${escapeHtml(
                        data.error || ""
                    )}</p>`;
                }
                renderPendingApprovals([]);
                renderUserAudits([]);
                return;
            }
            renderStats(data.stats || {});
            renderActivity(data.recentActivity || []);
            renderPendingApprovals(data.pendingApprovals || []);
            renderUserAudits(data.userAudits || []);
        } catch (error) {
            console.error("Admin overview error", error);
            if (placeholder) {
                placeholder.innerHTML = '<p class="activity-empty">Unable to load activity right now.</p>';
            }
            renderPendingApprovals([]);
            renderUserAudits([]);
        }
    };

    document.getElementById("refreshStats")?.addEventListener("click", loadOverview);
    document.getElementById("systemHealth")?.addEventListener("click", () => fetchSystemHealth(headers));
    document.getElementById("adminLogoutBtn")?.addEventListener("click", (ev) => {
        ev.preventDefault();
        showLogoutPrompt();
    });
    enforceStayPage();
    document.getElementById("viewAllActivity")?.addEventListener("click", () => {
        window.location.href = "/pages/admin/analytics.html";
    });

    loadOverview();
});
