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

const rowsEl = document.getElementById("companyRows");
const countEl = document.getElementById("companyCount");
const searchInput = document.getElementById("companySearch");
const verifiedSelect = document.getElementById("companyVerifiedFilter");
const refreshBtn = document.getElementById("refreshCompanies");
const logoutBtn = document.getElementById("companyLogout");
const applyFilterBtn = document.getElementById("applyCompanyFilter");
const newCompanyBtn = document.getElementById("newCompanyBtn");

const renderRows = (items) => {
    if (!rowsEl) return;
    if (!items || !items.length) {
        rowsEl.innerHTML = `<tr><td colspan="8" class="table-placeholder">No companies found.</td></tr>`;
        countEl.textContent = "0 companies";
        return;
    }
    countEl.textContent = `${items.length} company${items.length === 1 ? "" : "ies"}`;
    rowsEl.innerHTML = items
        .map((company) => {
            const verifiedBadge = company.isVerified ? "verified" : "unverified";
            return `
                <tr>
                    <td>${company.id}</td>
                    <td>${escapeHtml(company.companyName)}</td>
                    <td>${escapeHtml(company.industry)}</td>
                    <td>${company.website ? `<a href="${escapeHtml(company.website)}" target="_blank">Link</a>` : "-"}</td>
                    <td class="${verifiedBadge}">${company.isVerified ? "Yes" : "No"}</td>
                    <td>${escapeHtml(company.contactEmail)}</td>
                    <td>${formatDate(company.createdAt)}</td>
                    <td>
                        <button class="btn btn-sm btn-ghost edit-company-btn"
                            data-company-id="${company.id}"
                            data-company-name="${escapeHtml(company.companyName)}"
                            data-company-industry="${escapeHtml(company.industry)}"
                            data-company-website="${escapeHtml(company.website)}"
                            data-company-description="${escapeHtml(company.description)}"
                            data-company-contact="${escapeHtml(company.contactEmail)}"
                            data-company-verified="${company.isVerified}"
                        >Edit</button>
                        <button class="btn btn-sm btn-outline verify-company-btn"
                            data-company-id="${company.id}"
                            data-company-verified="${company.isVerified}"
                        >
                            ${company.isVerified ? "Unverify" : "Verify"}
                        </button>
                    </td>
                </tr>
            `;
        })
        .join("");
};

const showLoading = () => {
    if (rowsEl) {
        rowsEl.innerHTML = `<tr><td colspan="8" class="table-placeholder">Loading companies…</td></tr>`;
    }
};

const fetchCompanies = async () => {
    const token = getToken();
    if (!token) return navigateToLogin();
    const headers = {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
    };
    showLoading();
    const params = new URLSearchParams();
    const q = (searchInput?.value || "").trim();
    const verified = (verifiedSelect?.value || "").trim();
    if (q) params.set("q", q);
    if (verified !== "") {
        params.set("status", verified === "true" ? "verified" : "unverified");
    }
    params.set("limit", "200");
    try {
        const response = await fetch(apiUrl(`/api/admin/companies?${params.toString()}`), {
            headers,
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
            rowsEl.innerHTML = `<tr><td colspan="8" class="table-placeholder">Unable to load companies. ${escapeHtml(
                payload.error || "Try again later."
            )}</td></tr>`;
            return;
        }
        renderRows(payload.companies || []);
    } catch (error) {
        console.error("Failed to load companies", error);
        rowsEl.innerHTML = `<tr><td colspan="8" class="table-placeholder">Failed to load companies.</td></tr>`;
    }
};

const makeModal = (content) => {
    const overlay = document.createElement("div");
    overlay.className = "admin-modal-overlay";
    overlay.innerHTML = `
        <div class="admin-modal">
            ${content}
        </div>
    `;
    document.body.appendChild(overlay);
    overlay.addEventListener("click", (event) => {
        if (event.target === overlay) overlay.remove();
    });
    return overlay;
};

const openEditModal = (company, headers) => {
    const overlay = makeModal(`
        <div class="modal-header">
            <h3>Edit Company</h3>
            <button class="health-close-btn" aria-label="Close">A-</button>
        </div>
        <div class="modal-body">
            <label>Name</label>
            <input type="text" id="companyName" class="form-input" value="${escapeHtml(company.companyName)}" />
            <label>Industry</label>
            <input type="text" id="companyIndustry" class="form-input" value="${escapeHtml(company.industry)}" />
            <label>Website</label>
            <input type="url" id="companyWebsite" class="form-input" value="${escapeHtml(company.website)}" />
            <label>Description</label>
            <textarea id="companyDescription" class="form-input">${escapeHtml(company.description)}</textarea>
            <label>Contact email</label>
            <input type="email" id="companyEmail" class="form-input" value="${escapeHtml(company.contactEmail)}" />
            <label>Verified</label>
            <select id="companyVerified" class="form-input">
                <option value="1">Verified</option>
                <option value="0">Unverified</option>
            </select>
        </div>
        <div class="modal-footer">
            <button class="btn btn-sm btn-outline" id="cancelCompany">Cancel</button>
            <button class="btn btn-sm btn-primary" id="saveCompany">Save</button>
        </div>
    `);
    overlay.querySelector(".health-close-btn")?.addEventListener("click", () => overlay.remove());
    overlay.querySelector("#cancelCompany")?.addEventListener("click", () => overlay.remove());
    overlay.querySelector("#companyVerified")?.value = company.isVerified ? "1" : "0";

    overlay.querySelector("#saveCompany")?.addEventListener("click", async () => {
        const payload = {
            companyName: overlay.querySelector("#companyName")?.value || "",
            industry: overlay.querySelector("#companyIndustry")?.value || "",
            website: overlay.querySelector("#companyWebsite")?.value || "",
            description: overlay.querySelector("#companyDescription")?.value || "",
            contactEmail: overlay.querySelector("#companyEmail")?.value || "",
            isVerified: overlay.querySelector("#companyVerified")?.value === "1",
        };
        try {
            const res = await fetch(apiUrl(`/api/admin/companies/${company.id}`), {
                method: "PUT",
                headers,
                body: JSON.stringify(payload),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                alert(data.error || "Unable to update company");
                return;
            }
            overlay.remove();
            fetchCompanies();
        } catch (error) {
            console.error("Company update failed", error);
            alert("Failed to update company");
        }
    });
};

const toggleVerification = async (companyId, currentVerified) => {
    const token = getToken();
    if (!token) return navigateToLogin();
    const headers = {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
    };
    try {
        const res = await fetch(apiUrl(`/api/admin/companies/${companyId}`), {
            method: "PUT",
            headers,
            body: JSON.stringify({ isVerified: !currentVerified }),
        });
        if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            alert(data.error || "Unable to update verification status");
            return;
        }
        fetchCompanies();
    } catch (error) {
        console.error("Verification toggle failed", error);
        alert("Failed to update verification status");
    }
};

document.addEventListener("DOMContentLoaded", () => {
    const token = getToken();
    if (!token) {
        return navigateToLogin();
    }
    const headers = {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
    };

    const rowClickHandler = async (event) => {
        const verifyBtn = event.target.closest(".verify-company-btn");
        if (verifyBtn) {
            const id = verifyBtn.dataset.companyId;
            const verified = verifyBtn.dataset.companyVerified === "true";
            await toggleVerification(id, verified);
            return;
        }
        const editBtn = event.target.closest(".edit-company-btn");
        if (editBtn) {
        const company = {
            id: editBtn.dataset.companyId,
            companyName: editBtn.dataset.companyName || "",
            industry: editBtn.dataset.companyIndustry || "",
            website: editBtn.dataset.companyWebsite || "",
            description: editBtn.dataset.companyDescription || "",
            contactEmail: editBtn.dataset.companyContact || "",
            isVerified: editBtn.dataset.companyVerified === "true",
        };
            openEditModal(company, headers);
        }
    };

    rowsEl?.addEventListener("click", rowClickHandler);
    refreshBtn?.addEventListener("click", fetchCompanies);
    applyFilterBtn?.addEventListener("click", fetchCompanies);
    logoutBtn?.addEventListener("click", () => {
        clearAuthTokens();
        navigateToLogin();
    });
    newCompanyBtn?.addEventListener("click", () => {
        alert("Company creation not available yet.");
    });

    fetchCompanies();
});
