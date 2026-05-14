document.addEventListener("DOMContentLoaded", () => {
    const token =
        localStorage.getItem("authToken") ||
        localStorage.getItem("token") ||
        localStorage.getItem("jobgenix_token");
    const API_BASE =
        window.API_BASE_URL ||
        (location.origin.includes("8001")
            ? location.origin.replace("8001", "8000")
            : "http://localhost:8000");
    const apiUrl = (path) =>
        path.startsWith("http")
            ? path
            : `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;

    if (!token) {
        window.location.href = "/pages/auth/login.html";
        return;
    }

    const headers = { Authorization: "Bearer " + token };

    const elStatus = document.getElementById("reportByStatus");
    const elInterviews = document.getElementById("reportInterviews");
    const elHires = document.getElementById("reportHires");

    const safe = (v, fb = "-") => (v === 0 || v ? v : fb);

    async function loadReports() {
        try {
            const res = await fetch(apiUrl("/api/company/dashboard"), { headers });
            if (res.status === 401 || res.status === 403) {
                window.location.href = "/pages/auth/login.html";
                return;
            }
            const data = await res.json();
            if (!res.ok) {
                console.error("Reports load error:", data);
                return;
            }
            const m = data.metrics || {};
            const byStatus = m.applications_by_status || {};
            const pending = safe(byStatus.pending, "-");
            const interview = safe(byStatus.interview || byStatus.interviews, "-");
            const hired = safe(byStatus.hired, "-");
            elStatus.textContent = `Pending: ${pending}, Interview: ${interview}, Hired: ${hired}`;
            elInterviews.textContent = `Upcoming: ${safe(m.upcoming_interviews, "-")}, Completed: ${safe(m.completed_interviews, "-")}`;
            elHires.textContent = `Total: ${safe(m.recent_hires, "-")}`;
        } catch (err) {
            console.error("Failed to load reports:", err);
        }
    }

    loadReports();
});
