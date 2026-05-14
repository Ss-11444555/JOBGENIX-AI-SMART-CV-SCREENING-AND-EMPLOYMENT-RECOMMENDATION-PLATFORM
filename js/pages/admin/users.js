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
        const d = new Date(value);
        return d.toLocaleString();
    } catch {
        return value;
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

    const rowsEl = document.getElementById("userRows");
    const countEl = document.getElementById("userCount");
    const searchInput = document.getElementById("userSearch");
    const typeSelect = document.getElementById("userTypeFilter");
    const refreshBtn = document.getElementById("refreshUsers");
    const logoutBtn = document.getElementById("adminUsersLogout");

const renderRows = (users) => {
        if (!rowsEl) return;
        if (!users.length) {
            rowsEl.innerHTML = `<tr><td colspan="7" class="table-placeholder">No users found.</td></tr>`;
            countEl.textContent = "0 users";
            return;
        }
        countEl.textContent = `${users.length} user${users.length === 1 ? "" : "s"}`;
        rowsEl.innerHTML = users
            .map((user) => {
                const statusClass = user.isActive ? "" : "inactive";
                const typeLabel = user.userType ? user.userType.replace("_", " ") : "unknown";
                return `
                <tr>
                    <td>${user.id}</td>
                    <td>${user.name}</td>
                    <td>${user.email || "-"}</td>
                    <td>${typeLabel}</td>
                    <td class="${statusClass}">${user.isActive ? "Active" : "Inactive"}</td>
                    <td class="user-action">
                        <button class="btn btn-sm btn-ghost edit-user-btn" data-user-id="${user.id}"
                            data-user-name="${user.name}"
                            data-user-email="${user.email}"
                            data-user-type="${user.userType}"
                            data-user-active="${user.isActive}">
                            Edit
                        </button>
                        <button class="btn btn-sm btn-outline delete-user-btn" data-user-id="${user.id}">
                            Delete
                        </button>
                    </td>
                    <td>${formatDate(user.createdAt)}</td>
                </tr>
                `;
            })
            .join("");
    };

    const showLoading = () => {
        if (rowsEl) {
        rowsEl.innerHTML = `<tr><td colspan="7" class="table-placeholder">Loading users…</td></tr>`;
        }
    };

    const fetchUsers = async () => {
        showLoading();
        const params = new URLSearchParams();
        const q = (searchInput?.value || "").trim();
        const typeVal = (typeSelect?.value || "").trim();
        if (q) params.set("q", q);
        if (typeVal) params.set("type", typeVal);
        params.set("limit", "200");
        try {
            const res = await fetch(apiUrl(`/api/admin/users?${params.toString()}`), {
                headers,
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
            rowsEl.innerHTML = `<tr><td colspan="7" class="table-placeholder">Unable to load users. ${data.error || ""}</td></tr>`;
                return;
            }
            renderRows(data.users || []);
        } catch (err) {
            console.error("Failed to fetch users", err);
            rowsEl.innerHTML = `<tr><td colspan="7" class="table-placeholder">Failed to load users.</td></tr>`;
        }
    };

    refreshBtn?.addEventListener("click", fetchUsers);
    document.getElementById("applyFilter")?.addEventListener("click", fetchUsers);
    logoutBtn?.addEventListener("click", () => {
        clearAuthTokens();
        navigateToLogin();
    });

    const makeModal = (content) => {
        const overlay = document.createElement("div");
        overlay.className = "admin-modal-overlay";
        overlay.innerHTML = `
            <div class="admin-modal">
                ${content}
            </div>
        `;
        document.body.appendChild(overlay);
        overlay.addEventListener("click", (e) => {
            if (e.target === overlay) overlay.remove();
        });
        return overlay;
    };

    const openEditModal = (user) => {
        const overlay = makeModal(`
            <div class="modal-header">
                <h3>Edit user</h3>
                <button class="health-close-btn" aria-label="Close">×</button>
            </div>
            <div class="modal-body">
                <label>Name</label>
                <input type="text" id="editUserName" class="form-input" value="${user.name || ""}" />
                <label>Email</label>
                <input type="email" id="editUserEmail" class="form-input" value="${user.email || ""}" />
                <label>User type</label>
                <select id="editUserType" class="form-input">
                    <option value="job_seeker">Job seeker</option>
                    <option value="company">Company</option>
                    <option value="admin">Admin</option>
                </select>
                <label>Status</label>
                <select id="editUserActive" class="form-input">
                    <option value="1">Active</option>
                    <option value="0">Inactive</option>
                </select>
            </div>
            <div class="modal-footer">
                <button class="btn btn-sm btn-outline" id="cancelEdit">Cancel</button>
                <button class="btn btn-sm btn-primary" id="saveEdit">Save</button>
            </div>
        `);
        overlay.querySelector(".health-close-btn")?.addEventListener("click", () => overlay.remove());
        overlay.querySelector("#cancelEdit")?.addEventListener("click", () => overlay.remove());
        const typeSelect = overlay.querySelector("#editUserType");
        if (typeSelect) typeSelect.value = user.userType || "job_seeker";
        const activeSelect = overlay.querySelector("#editUserActive");
        if (activeSelect) activeSelect.value = user.isActive ? "1" : "0";
        overlay.querySelector("#saveEdit")?.addEventListener("click", async () => {
            const name = overlay.querySelector("#editUserName")?.value || "";
            const email = overlay.querySelector("#editUserEmail")?.value || "";
            const userType = typeSelect?.value;
            const isActive = activeSelect?.value === "1";
            try {
                const res = await fetch(apiUrl(`/api/admin/users/${user.id}`), {
                    method: "PUT",
                    headers,
                    body: JSON.stringify({ name, email, user_type: userType, is_active: isActive }),
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    alert(data.error || "Failed to update user");
                    return;
                }
                overlay.remove();
                fetchUsers();
            } catch (err) {
                console.error("Update failed", err);
                alert("Unable to update user");
            }
        });
    };

    rowsEl?.addEventListener("click", async (event) => {
        const deleteBtn = event.target.closest(".delete-user-btn");
        if (deleteBtn) {
            const userId = deleteBtn.dataset.userId;
            if (!userId || !confirm("Delete this user? This cannot be undone.")) return;
            try {
                const res = await fetch(apiUrl(`/api/admin/users/${userId}`), {
                    method: "DELETE",
                    headers,
                });
                if (!res.ok) {
                    const data = await res.json().catch(() => ({}));
                    alert(data.error || "Failed to delete user");
                    return;
                }
                alert("User deleted");
                fetchUsers();
            } catch (err) {
                console.error("Delete failed", err);
                alert("Unable to delete user");
            }
            return;
        }
        const editBtn = event.target.closest(".edit-user-btn");
        if (editBtn) {
            const user = {
                id: editBtn.dataset.userId,
                name: editBtn.dataset.userName,
                email: editBtn.dataset.userEmail,
                userType: editBtn.dataset.userType,
                isActive: editBtn.dataset.userActive === "true",
            };
            openEditModal(user);
        }
    });

    fetchUsers();
});
