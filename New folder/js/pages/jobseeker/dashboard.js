// js/pages/jobseeker/dashboard.js
class JobseekerDashboard {
    constructor() {
        this.init();
    }

    init() {
        const safeParse = (val) => {
            try {
                return JSON.parse(val);
            } catch (_) {
                return {};
            }
        };
        const inferUserTypeFromPath = () => {
            if (window.location.pathname.includes('/jobseeker/')) return 'job_seeker';
            if (window.location.pathname.includes('/company/')) return 'company';
            return null;
        };
        const getStoredAuth = () => {
            const token =
                (window.JobGenixApp?.getToken && window.JobGenixApp.getToken()) ||
                localStorage.getItem('authToken') ||
                localStorage.getItem('token') ||
                localStorage.getItem('jobgenix_token');
            const userRaw = localStorage.getItem('user');
            const userType =
                (userRaw ? safeParse(userRaw || '{}').user_type : null) ||
                localStorage.getItem('user_type') ||
                inferUserTypeFromPath();
            return { token, userType };
        };

        const clearSessionAndRedirect = () => {
            ['authToken', 'token', 'jobgenix_token', 'user', 'user_type'].forEach((k) =>
                localStorage.removeItem(k)
            );
            window.location.href = '/pages/auth/login.html';
        };

        this.getStoredAuth = getStoredAuth;
        this.clearSessionAndRedirect = clearSessionAndRedirect;
        this.enforceAuth = () => {
            const { token, userType } = this.getStoredAuth();
            if (!token) {
                this.clearSessionAndRedirect();
                return false;
            }
            if (userType !== 'job_seeker') {
                // If we have a token but no type, assume job seeker on this page
                if (!userType) {
                    localStorage.setItem('user_type', 'job_seeker');
                    return true;
                }
                this.clearSessionAndRedirect();
                return false;
            }
            return true;
        };

        const { token, userType } = this.getStoredAuth();
        if (!token || userType !== 'job_seeker') {
            this.clearSessionAndRedirect();
            return;
        }
        this.enforceAuth();

        this.setupEventListeners();
        this.loadDashboardData();
        this.loadTopMatches();
        this.loadUpcomingInterviews();
        this.loadRecentActivity();
        this.setupCharts();

    window.addEventListener('pageshow', () => this.enforceAuth());
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) this.enforceAuth();
    });

    history.replaceState(null, "", "/pages/jobseeker/dashboard.html");
    window.addEventListener("popstate", () => {
        window.location.href = "/";
    });
    }

    setupEventListeners() {
        document.addEventListener('click', (e) => {
            const jobMatch = e.target.closest('.job-match');
            if (jobMatch) {
                this.viewJobDetails(jobMatch);
            }

            const actionBtn = e.target.closest('.action-button');
            if (actionBtn) {
                e.preventDefault();
                this.handleQuickAction(actionBtn);
            }
        });

        const logoutBtn = document.getElementById("jobseekerLogoutBtn");
        if (logoutBtn) {
            logoutBtn.addEventListener("click", (event) => {
                event.preventDefault();
                this.showLogoutPrompt();
            });
        }
    }

    showLogoutPrompt() {
        this.closeLogoutPrompt();
        const overlay = document.createElement("div");
        overlay.className = "admin-lock-overlay";
        overlay.id = "jobseekerLogoutPrompt";
        overlay.innerHTML = `
            <div class="admin-lock-card">
                <p>Are you sure you want to log out?</p>
                <div style="display:flex;gap:0.75rem;justify-content:center;">
                    <button class="btn btn-sm btn-outline" id="cancelJobseekerLogout">Cancel</button>
                    <button class="btn btn-sm btn-primary" id="confirmJobseekerLogout">Logout</button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);
        overlay.querySelector("#cancelJobseekerLogout")?.addEventListener("click", () => this.closeLogoutPrompt());
        overlay.querySelector("#confirmJobseekerLogout")?.addEventListener("click", () => {
            this.closeLogoutPrompt();
            if (window.JobGenixApp && typeof window.JobGenixApp.logout === "function") {
                window.JobGenixApp.logout();
            }
        });
    }

    closeLogoutPrompt() {
        const existing = document.getElementById("jobseekerLogoutPrompt");
        if (existing) existing.remove();
    }

    async loadDashboardData() {
        try {
            const data = await window.JobGenixApp.getRequest('/job-seeker/dashboard');
            if (!data) return;
            this.updateDashboardStats(data.metrics || {});
            const recent = data.recent_applications || [];
            if (recent.length) {
                this.updateRecentApplications(recent);
            } else {
                this.loadApplicationsFallback();
            }
            this.updateWelcome(data.profile || {});
        } catch (error) {
            console.error('Failed to load dashboard data:', error);
        }
    }

    async loadTopMatches() {
        const container = document.getElementById('topMatches');
        if (!container) return;
        container.innerHTML = '<p style="color:#6b7280;margin:0;">Loading matches...</p>';
        try {
            const data = await window.JobGenixApp.getRequest('/job-seeker/top-matches');
            let jobs = data?.matches || [];
            // Fallback to public jobs search if no personalized matches
            if (!jobs.length) {
                const alt = await window.JobGenixApp.getRequest('/jobs/search?limit=10');
                jobs = alt?.jobs || [];
            }
            if (!jobs.length) {
                container.innerHTML = '<p style="color:#6b7280;margin:0;">No matches yet. Try updating your profile or searching jobs.</p>';
                return;
            }
            container.innerHTML = jobs.map(job => this.renderMatchCard(job)).join('');
        } catch (err) {
            console.error('Failed to load top matches', err);
            container.innerHTML = '<p style="color:#dc2626;margin:0;">Unable to load matches.</p>';
        }
    }

    renderMatchCard(job) {
        const company = job.company_name || job.company || 'Company';
        const location = job.location || 'Location';
        const salary = (job.salary_min != null && job.salary_max != null) ? `$${job.salary_min} - $${job.salary_max}` : 'Not specified';
        const jobType = job.job_type || job.type || 'N/A';
        const skills = (job.required_skills || []).slice(0, 2);
        const matchVal = job.match_score != null ? parseInt(job.match_score) : null;
        const match = matchVal != null ? `${matchVal}%` : '--';

        const skillTags = skills.map(s => `<span class="job-tag"><i class="fas fa-code"></i> ${s}</span>`).join('');
        const deg = match === '--' ? 0 : (matchVal / 100 * 360);
        return `
        <div class="job-match">
            <div class="company-logo">
                <i class="fas fa-briefcase"></i>
            </div>
            <div class="job-details">
                <h4>${job.title || 'Job title'}</h4>
                <p class="company">${company} • ${location}</p>
                <div class="job-meta">
                    <span class="job-tag">
                        <i class="fas fa-dollar-sign"></i> ${salary}
                    </span>
                    <span class="job-tag">
                        <i class="fas fa-clock"></i> ${jobType}
                    </span>
                    ${skillTags}
                </div>
            </div>
            <div class="match-score">
                <div class="score-circle" style="--percentage: ${deg}deg">
                    <span class="score-value">${match}</span>
                </div>
                <span class="score-label">Match</span>
            </div>
        </div>
        `;
    }

    async loadUpcomingInterviews() {
        const container = document.getElementById('upcomingInterviews');
        if (!container) return;
        container.innerHTML = '<p style="color:#6b7280;margin:0;">Loading interviews...</p>';
        try {
            const data = await window.JobGenixApp.getRequest('/job-seeker/mock-interviews');
            const interviews = data?.interviews || [];
            if (!interviews.length) {
                container.innerHTML = '<p style="color:#6b7280;margin:0;">No upcoming interviews.</p>';
                return;
            }
            container.innerHTML = interviews.map(iv => this.renderInterview(iv)).join('');
        } catch (err) {
            console.error('Failed to load upcoming interviews', err);
            container.innerHTML = '<p style="color:#dc2626;margin:0;">Unable to load interviews.</p>';
        }
    }

    renderInterview(iv) {
        const company = iv.company || 'Company';
        const role = iv.job_title || 'Role';
        const status = iv.status || iv.interview_status || '';
        const time = iv.scheduled_at || iv.applied_at || '';
        const meeting = iv.meeting_url ? `<a href="${iv.meeting_url}" target="_blank" rel="noopener" class="btn btn-sm btn-primary"><i class="fas fa-video"></i> Join</a>` : '';
        return `
        <div class="app-status-item">
            <div class="app-info">
                <h4>${company} • ${role}</h4>
                <p><i class="fas fa-calendar"></i> ${time}</p>
                ${status ? `<p><i class="fas fa-info-circle"></i> ${status}</p>` : ''}
            </div>
            ${meeting}
        </div>
        `;
    }

    updateWelcome(profile) {
        const h1 = document.querySelector('.user-welcome h1');
        if (h1 && profile.full_name) {
            h1.textContent = `Welcome back, ${profile.full_name}!`;
        }
        const avatarEl = document.getElementById('dashboardAvatar');
        if (avatarEl && profile.profile_picture_url) {
            avatarEl.src = profile.profile_picture_url;
        }
    }

    updateDashboardStats(metrics) {
        const statCards = document.querySelectorAll('.quick-stats .stat-card');
        const values = [
            metrics.total_applications || 0,
            metrics.pending || 0,
            metrics.interviews || 0,
            metrics.hired || 0
        ];
        statCards.forEach((card, idx) => {
            const h3 = card.querySelector('h3');
            if (h3) h3.textContent = values[idx] ?? 0;
        });
    }

    updateRecentApplications(applications) {
        const container = document.getElementById('applicationStatusList');
        if (!container) return;
        if (!applications.length) {
            container.innerHTML = '<p style="color: var(--gray-600); margin:0;">No recent applications yet.</p>';
            return;
        }
        container.innerHTML = applications.map(app => `
            <div class="app-status-item">
                <div class="app-info">
                    <h4>${app.company || ''} – ${app.job_title || ''}</h4>
                    <p><i class="fas fa-building"></i> ${app.company || ''}</p>
                    <p><i class="fas fa-calendar"></i> ${app.applied_at || ''}</p>
                </div>
                <span class="status-badge">${app.status || 'applied'}</span>
            </div>
        `).join('');
    }

    async loadApplicationsFallback() {
        try {
            const data = await window.JobGenixApp.getRequest('/job-seeker/applications');
            if (data && data.applications) {
                this.updateRecentApplications(data.applications.slice(0, 4));
            }
        } catch (err) {
            console.error('Failed to load applications fallback', err);
        }
    }

    setupCharts() {
        const scoreCircles = document.querySelectorAll('.score-circle');
        scoreCircles.forEach(circle => {
            const score = circle.querySelector('.score-value').textContent;
            const percentage = parseInt(score) / 100 * 360;
            circle.style.setProperty('--percentage', `${percentage}deg`);
        });
    }

    viewJobDetails(jobMatch) {
        const jobTitle = jobMatch.querySelector('h4').textContent;
        const company = jobMatch.querySelector('.company').textContent;
        window.JobGenixApp.showAlert(`Viewing ${jobTitle} at ${company}`, 'info');
    }

    handleQuickAction(button) {
        const action = button.querySelector('span').textContent.toLowerCase();
        const actions = {
            'update profile': () => window.location.href = '/pages/jobseeker/profile.html',
            'messages': () => window.location.href = '/pages/jobseeker/messages.html',
            'search jobs': () => window.location.href = '/pages/jobseeker/jobs/search.html',
            'mock interview': () => this.startMockInterview(),
            'analytics': () => window.location.href = '/pages/jobseeker/analytics.html',
            'settings': () => window.location.href = '/pages/jobseeker/settings.html'
        };

        if (actions[action]) {
            actions[action]();
        }
    }

    async refreshMatches() {
        const btn = document.querySelector('.header-actions .btn-outline');
        const originalText = btn.innerHTML;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Refreshing...';
        btn.disabled = true;

        try {
            await new Promise(resolve => setTimeout(resolve, 1500));
            window.JobGenixApp.showAlert('Job matches refreshed successfully!', 'success');
            this.loadDashboardData();
        } catch (error) {
            window.JobGenixApp.showAlert('Failed to refresh matches', 'error');
        } finally {
            btn.innerHTML = originalText;
            btn.disabled = false;
        }
    }

    uploadCV() {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = '.pdf,.doc,.docx,.txt';
        
        input.onchange = async (e) => {
            const file = e.target.files[0];
            if (!file) return;

            window.JobGenixApp.showAlert('Uploading CV...', 'info');
            
            try {
                await new Promise(resolve => setTimeout(resolve, 2000));
                window.JobGenixApp.showAlert('CV uploaded successfully! AI is analyzing your profile...', 'success');
                setTimeout(() => this.loadDashboardData(), 1000);
            } catch (error) {
                window.JobGenixApp.showAlert('Failed to upload CV', 'error');
            }
        };

        input.click();
    }

    startMockInterview() {
        window.location.href = '/pages/jobseeker/mock-interview.html';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.JobseekerDashboard = new JobseekerDashboard();
});
