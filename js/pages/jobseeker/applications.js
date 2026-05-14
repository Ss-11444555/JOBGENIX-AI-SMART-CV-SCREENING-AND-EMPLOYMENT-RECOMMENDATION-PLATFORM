document.addEventListener("DOMContentLoaded", () => {
    const app = window.JobGenixApp;
    const token = localStorage.getItem("authToken") || localStorage.getItem("token");
    if (!token) {
        window.location.href = "/pages/auth/login.html";
        return;
    }

    const user = app?.getUser ? app.getUser() : null;
    const userEmailEl = document.getElementById("userEmail");
    const userAvatar = document.getElementById("userAvatar");
    if (user) {
        if (userEmailEl) userEmailEl.textContent = user.email || user.name || "JobGenix user";
        if (userAvatar) {
            const initials = (user.name || user.email || "JS")
                .split(" ")
                .map((p) => p[0])
                .join("")
                .substring(0, 2)
                .toUpperCase();
            userAvatar.textContent = initials;
        }
    }

    // Logout
    document.getElementById("logoutBtn")?.addEventListener("click", (e) => {
        e.preventDefault();
        if (app && typeof app.logout === "function") {
            app.logout();
        } else {
            ["authToken", "token", "jobgenix_token", "user"].forEach((k) =>
                localStorage.removeItem(k)
            );
            window.location.href = "/pages/auth/login.html";
        }
    });

    const tbody = document.getElementById("applicationsBody");

    function statusClass(status) {
        if (!status) return "status-applied";
        const s = status.toLowerCase();
        if (s.includes("interview")) return "status-interview";
        if (s.includes("accept") || s.includes("offer") || s.includes("hire")) return "status-accepted";
        if (s.includes("reject") || s.includes("decline")) return "status-rejected";
        return "status-applied";
    }

    function formatDate(val) {
        if (!val) return "-";
        try {
            const d = new Date(val);
            return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
        } catch {
            return val;
        }
    }

    async function loadApplications() {
        tbody.innerHTML = `<tr><td colspan="4" class="empty-row">Loading...</td></tr>`;
        try {
            const data = await app.getRequest("/job-seeker/applications");
            if (!data || !data.applications) {
                tbody.innerHTML = `<tr><td colspan="4" class="empty-row">No applications found.</td></tr>`;
                return;
            }
            if (!data.applications.length) {
                tbody.innerHTML = `<tr><td colspan="4" class="empty-row">No applications yet.</td></tr>`;
                return;
            }
            tbody.innerHTML = data.applications
                .map((a) => {
                    const status = a.status || "applied";
                    return `
                        <tr>
                            <td>${a.job_title || "—"}</td>
                            <td>${a.company || "—"}</td>
                            <td><span class="status-pill ${statusClass(status)}">${status}</span></td>
                            <td>${formatDate(a.applied_at)}</td>
                        </tr>
                    `;
                })
                .join("");
        } catch (err) {
            console.error("Failed to load applications", err);
            tbody.innerHTML = `<tr><td colspan="4" class="empty-row">Unable to load applications.</td></tr>`;
        }
    }

    document.getElementById("refreshBtn")?.addEventListener("click", loadApplications);

    loadApplications();
});
