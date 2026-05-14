// js/pages/jobseeker/analytics.js
(function () {
    const API_BASE = (window.JobGenixApp && window.JobGenixApp.apiBase) || "http://localhost:8000/api";
    const token = localStorage.getItem("authToken") || localStorage.getItem("token") || localStorage.getItem("jobgenix_token");

    const metricApps = document.getElementById('metricApps');
    const metricInterviews = document.getElementById('metricInterviews');
    const metricOffers = document.getElementById('metricOffers');
    const metricHires = document.getElementById('metricHires');
    const trendBars = document.getElementById('trendBars');
    const topRolesEl = document.getElementById('topRoles');
    const recentActivityEl = document.getElementById('recentActivity');

    if (!token) {
        window.location.href = '/pages/auth/login.html';
        return;
    }

    function renderMetrics(metrics = {}) {
        metricApps.textContent = metrics.applications ?? '--';
        metricInterviews.textContent = metrics.interviews ?? '--';
        metricOffers.textContent = metrics.offers ?? '--';
        metricHires.textContent = metrics.hires ?? '--';
    }

    function renderTrend(arr = []) {
        if (!trendBars) return;
        trendBars.innerHTML = '';
        const max = Math.max(...arr, 0);
        arr.forEach((v) => {
            const bar = document.createElement('div');
            bar.className = 'trend-bar' + (v ? '' : ' empty');
            const h = max > 0 ? Math.max(6, (v / max) * 100) : 6;
            bar.style.height = `${h}%`;
            bar.title = `${v} applications`;
            trendBars.appendChild(bar);
        });
    }

    function renderTopRoles(list = []) {
        if (!topRolesEl) return;
        if (!list.length) {
            topRolesEl.innerHTML = '<p class="muted small">No applications yet.</p>';
            return;
        }
        topRolesEl.innerHTML = list.map(r => `
            <div class="list-item">
                <strong>${r.title || 'Role'}</strong>
                <p class="sub">${r.count || 0} applications</p>
            </div>
        `).join('');
    }

    function renderRecent(list = []) {
        if (!recentActivityEl) return;
        if (!list.length) {
            recentActivityEl.innerHTML = '<p class="muted small">No recent activity.</p>';
            return;
        }
        recentActivityEl.innerHTML = list.map(item => `
            <div class="list-item">
                <strong>${item.title || 'Application'}</strong>
                <p class="sub">${item.sub || ''}</p>
                <p class="meta">${item.time || ''}</p>
            </div>
        `).join('');
    }

    async function loadAnalytics() {
        try {
            const res = await fetch(`${API_BASE}/job-seeker/analytics`, {
                headers: { "Authorization": "Bearer " + token }
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok || data.error) {
                console.warn('Analytics load failed', data);
                return;
            }
            renderMetrics(data.metrics || {});
            renderTrend(data.applications_trend || []);
            renderTopRoles(data.top_roles || []);
            renderRecent(data.recent_activity || []);
        } catch (e) {
            console.warn('Analytics load error', e);
        }
    }

    document.addEventListener('DOMContentLoaded', loadAnalytics);
})();
