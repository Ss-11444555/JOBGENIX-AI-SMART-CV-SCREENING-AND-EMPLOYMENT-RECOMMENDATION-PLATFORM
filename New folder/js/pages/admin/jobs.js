const rawAppBase = window.JobGenixApp?.apiBase || window.JobGenixApp?.apiBaseUrl;
const apiBaseFromApp = rawAppBase ? rawAppBase.replace(/\/api\/?$/, "") : null;
const API_BASE =
    window.API_BASE_URL ||
    apiBaseFromApp ||
    (location.origin.includes("8001") ? location.origin.replace("8001", "8000") : "http://localhost:8000");
const apiUrl = (path) =>
    path.startsWith("http") ? path : `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
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

const LOGOUT_KEYS = [...TOKEN_KEYS];
const clearAuthTokens = () => {
    LOGOUT_KEYS.forEach((key) => localStorage.removeItem(key));
    localStorage.removeItem("user");
};

const navigateToLogin = () => {
    window.location.href = "/pages/auth/login.html";
};

const formatDate = (value) => {
    if (!value) return "-";
    try {
        return new Date(value).toLocaleString();
    } catch {
        return value;
    }
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

const jobRows = document.getElementById("jobRows");
const jobCount = document.getElementById("jobCount");
const searchInput = document.getElementById("jobSearch");
const statusSelect = document.getElementById("jobStatusFilter");
const refreshBtn = document.getElementById("refreshJobs");
const logoutBtn = document.getElementById("jobsLogout");
const applyFilterBtn = document.getElementById("applyJobFilter");

const renderJobs = (jobs) => {
    if (!jobRows) return;
    if (!jobs || !jobs.length) {
        jobRows.innerHTML = `<tr><td colspan="7" class="table-placeholder">No jobs found.</td></tr>`;
        jobCount.textContent = "0 jobs";
        return;
    }
    jobCount.textContent = `${jobs.length} job${jobs.length === 1 ? "" : "s"}`;
    jobRows.innerHTML = jobs
        .map((job) => {
            return `
                <tr>
                    <td>${job.id}</td>
                    <td>${escapeHtml(job.title)}</td>
                    <td>${escapeHtml(job.companyName)}</td>
                    <td>${escapeHtml(job.status)}</td>
                    <td>${escapeHtml(job.location)}</td>
                    <td>${formatDate(job.createdAt)}</td>
                    <td>
                        <button class="btn btn-sm btn-danger delete-job-btn" data-job-id="${job.id}">
                            Delete
                        </button>
                    </td>
                </tr>
            `;
        })
        .join("");
};

const showLoading = () => {
    if (jobRows) {
        jobRows.innerHTML = `<tr><td colspan="7" class="table-placeholder">Loading jobs…</td></tr>`;
    }
};

const fetchJobs = async () => {
    const token = getToken();
    if (!token) return navigateToLogin();
    const headers = {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
    };
    showLoading();
    const params = new URLSearchParams();
    const q = (searchInput?.value || "").trim();
    const status = (statusSelect?.value || "").trim();
    if (q) params.set("q", q);
    if (status) params.set("status", status.toLowerCase());
    params.set("limit", "200");
    try {
        const response = await fetch(apiUrl(`/api/admin/jobs?${params.toString()}`), {
            headers,
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
            jobRows.innerHTML = `<tr><td colspan="7" class="table-placeholder">Unable to load jobs. ${escapeHtml(
                payload.error || "Try again later."
            )}</td></tr>`;
            return;
        }
        renderJobs(payload.jobs || []);
    } catch (error) {
        console.error("Failed to load jobs", error);
        jobRows.innerHTML = `<tr><td colspan="7" class="table-placeholder">Failed to load jobs.</td></tr>`;
    }
};

const deleteJob = async (jobId) => {
    if (!confirm("Delete this job posting? This action cannot be undone.")) return;
    const token = getToken();
    if (!token) return navigateToLogin();
    const headers = {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
    };
    try {
        const response = await fetch(apiUrl(`/api/admin/jobs/${jobId}`), {
            method: "DELETE",
            headers,
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
            alert(payload.error || "Unable to delete job.");
            return;
        }
        fetchJobs();
    } catch (error) {
        console.error("Failed to delete job", error);
        alert("Failed to delete job.");
    }
};

document.addEventListener("DOMContentLoaded", () => {
    if (!jobRows) return;
    const token = getToken();
    if (!token) {
        return navigateToLogin();
    }
    jobRows.addEventListener("click", (event) => {
        const deleteBtn = event.target.closest(".delete-job-btn");
        if (deleteBtn) {
            const jobId = deleteBtn.dataset.jobId;
            if (jobId) {
                deleteJob(jobId);
            }
        }
    });

    refreshBtn?.addEventListener("click", fetchJobs);
    applyFilterBtn?.addEventListener("click", fetchJobs);
    logoutBtn?.addEventListener("click", () => {
        clearAuthTokens();
        navigateToLogin();
    });

    fetchJobs();
});
