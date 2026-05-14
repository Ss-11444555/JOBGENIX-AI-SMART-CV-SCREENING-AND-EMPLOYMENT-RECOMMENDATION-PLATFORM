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
        path.startsWith("http") ? path : `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;

    if (!token) {
        window.location.href = "/pages/auth/login.html";
        return;
    }

    const headers = {
        Authorization: "Bearer " + token,
        "Content-Type": "application/json",
    };

    const statOpenRoles = document.getElementById("statOpenRoles");
    const statApplications = document.getElementById("statApplications");
    const statInterviews = document.getElementById("statInterviews");
    const statHires = document.getElementById("statHires");
    const funnelApplied = document.getElementById("funnelApplied");
    const funnelInterview = document.getElementById("funnelInterview");
    const funnelOffer = document.getElementById("funnelOffer");
    const funnelHired = document.getElementById("funnelHired");
    const rolesChart = document.getElementById("rolesChart");
    const applicationsChart = document.getElementById("applicationsChart");
    const recentActivity = document.getElementById("recentActivity");

    const logoutBtn = document.getElementById("companyLogoutBtn");
    if (logoutBtn) {
        logoutBtn.addEventListener("click", () => {
            try {
                if (window.auth && typeof auth.logout === "function") {
                    auth.logout();
                    return;
                }
            } catch (_) {}
            ["authToken", "token", "jobgenix_token"].forEach((k) =>
                localStorage.removeItem(k)
            );
            localStorage.removeItem("user");
            window.location.href = "/pages/auth/login.html";
        });
    }

    document
        .getElementById("refreshAnalytics")
        ?.addEventListener("click", () => loadAnalytics());
function renderSparkline(values = []) {
    if (!values.length) {
        applicationsChart.textContent = "No data";
        return;
    }

    const labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
    const max = Math.max(...values);
    
    // --- FIX 1: Define svgWidth ---
    const svgWidth = 800; // This is the internal coordinate width
    const svgHeight = 200;
    const padding = 40;

    // These control the actual display size in the browser
    const minDisplayWidth = "400px";
    const maxDisplayWidth = "100%"; 

    const chartWidth = svgWidth - (padding * 2);
    const chartHeight = svgHeight - (padding * 2);
    const step = chartWidth / (values.length - 1 || 1);

    const points = values.map((v, i) => {
        const x = padding + (i * step);
        const y = (svgHeight - padding) - (max ? (v / max) * chartHeight : 0);
        return { x, y, val: v, time: labels[i] || "" };
    });

    const coords = points.map(p => `${p.x},${p.y}`).join(" ");

    const hoverPoints = points.map(p => `
        <g class="chart-point">
            <circle cx="${p.x}" cy="${p.y}" r="10" fill="transparent" class="trigger">
                <title>${p.time}: ${p.val} applications</title>
            </circle>
            <circle cx="${p.x}" cy="${p.y}" r="4" fill="#3b82f6" style="pointer-events: none;" />
        </g>
    `).join("");

    // --- FIX 2 & 3: Use viewBox and valid CSS styles ---
    applicationsChart.innerHTML = `
        <svg viewBox="0 0 ${svgWidth} ${svgHeight}" 
             style="background: rgba(59, 130, 246, 0.1); 
                    border-radius: 8px; 
                    display: block;
                    min-width: ${minDisplayWidth}; 
                    max-width: ${maxDisplayWidth}; 
                    width: 100%; 
                    height: auto;">
            
            <line x1="${padding}" y1="${padding}" x2="${padding}" y2="${svgHeight - padding}" stroke="#94a3b8" />
            <text x="${padding - 10}" y="${padding}" text-anchor="end" font-size="12" fill="#64748b">${max}</text>
            <text x="${padding - 10}" y="${svgHeight - padding}" text-anchor="end" font-size="12" fill="#64748b">0</text>

            <line x1="${padding}" y1="${svgHeight - padding}" x2="${svgWidth - padding}" y2="${svgHeight - padding}" stroke="#94a3b8" />
            
            <polyline fill="none" stroke="#3b82f6" stroke-width="3" stroke-linejoin="round" points="${coords}" />
            
            ${hoverPoints}

            <text x="${svgWidth / 2}" y="${svgHeight - 5}" text-anchor="middle" font-size="14" fill="#64748b">Time</text>
            <text x="${15}" y="${svgHeight / 2}" text-anchor="middle" font-size="14" fill="#64748b" transform="rotate(-90 15,${svgHeight / 2})">Count</text>
        </svg>
    `;
}
    function renderRoles(list = []) {
        if (!list.length) {
            rolesChart.textContent = "No role data";
            return;
        }
        rolesChart.innerHTML = "";
        const max = Math.max(...list.map((r) => r.count || 0), 1);
        list.slice(0, 6).forEach((r) => {
            const item = document.createElement("div");
            item.className = "bar-item";
            const label = document.createElement("div");
            label.className = "bar-label";
            label.textContent = r.title || "Role";
            const track = document.createElement("div");
            track.className = "bar-track";
            const fill = document.createElement("div");
            fill.className = "bar-fill";
            fill.style.width = `${Math.round(((r.count || 0) / max) * 100)}%`;
            track.appendChild(fill);
            const count = document.createElement("div");
            count.textContent = r.count || 0;
            item.appendChild(label);
            item.appendChild(track);
            item.appendChild(count);
            rolesChart.appendChild(item);
        });
    }

    function renderActivity(items = []) {
        if (!items.length) {
            recentActivity.innerHTML = '<p class="panel-placeholder">No recent activity.</p>';
            return;
        }
        recentActivity.innerHTML = "";
        items.slice(0, 6).forEach((a) => {
            const row = document.createElement("div");
            row.className = "activity-item";
            const main = document.createElement("div");
            const title = document.createElement("div");
            title.className = "activity-title";
            title.textContent = a.title || "Activity";
            const sub = document.createElement("div");
            sub.className = "activity-sub";
            sub.textContent = a.sub || "";
            main.appendChild(title);
            main.appendChild(sub);
            const time = document.createElement("div");
            time.className = "activity-time";
            time.textContent = a.time || "";
            row.appendChild(main);
            row.appendChild(time);
            recentActivity.appendChild(row);
        });
    }

    async function loadAnalytics() {
        try {
            const res = await fetch(apiUrl("/api/company/analytics"), { headers });
            if (res.status === 401 || res.status === 403) {
                ["authToken", "token", "jobgenix_token"].forEach((k) =>
                    localStorage.removeItem(k)
                );
                window.location.href = "/pages/auth/login.html";
                return;
            }
            const data = await res.json();
            if (!res.ok) {
                console.error("Analytics load error:", data);
                return;
            }

            const metrics = data.metrics || {};
            statOpenRoles.textContent = metrics.open_roles ?? "-";
            statApplications.textContent = metrics.applications ?? "-";
            statInterviews.textContent = metrics.interviews ?? "-";
            statHires.textContent = metrics.hires ?? "-";

            const funnel = data.funnel || {};
            funnelApplied.textContent = funnel.applied ?? "-";
            funnelInterview.textContent = funnel.interview ?? "-";
            funnelOffer.textContent = funnel.offer ?? "-";
            funnelHired.textContent = funnel.hired ?? "-";

            renderSparkline(data.applications_trend || []);
            renderRoles(data.top_roles || []);
            renderActivity(data.recent_activity || []);
        } catch (err) {
            console.error("Analytics fetch failed:", err);
        }
    }

    loadAnalytics();
});
