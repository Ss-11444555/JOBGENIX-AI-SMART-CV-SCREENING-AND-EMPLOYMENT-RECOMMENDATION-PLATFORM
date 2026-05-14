document.addEventListener("DOMContentLoaded", () => {
    const tokenKeys = ["authToken", "token", "jobgenix_token"];
    const safeParse = (val) => {
        try {
            return JSON.parse(val);
        } catch (_) {
            return {};
        }
    };
    const inferUserTypeFromPath = () =>
        window.location.pathname.includes("/company/") ? "company" : null;
    const getStoredAuth = () => {
        const token = tokenKeys
            .map((k) => localStorage.getItem(k))
            .find(Boolean);
        const userRaw = localStorage.getItem("user");
        const userType =
            (userRaw ? safeParse(userRaw || "{}").user_type : null) ||
            localStorage.getItem("user_type") ||
            inferUserTypeFromPath();
        return { token, userType };
    };
    const { token, userType } = getStoredAuth();
    const API_BASE =
        window.API_BASE_URL ||
        (location.origin.includes("8001")
            ? location.origin.replace("8001", "8000")
            : "http://localhost:8000");
    const apiUrl = (path) =>
        path.startsWith("http")
            ? path
            : `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;

    const clearSessionAndRedirect = () => {
        tokenKeys.forEach((k) => localStorage.removeItem(k));
        ["user", "user_type"].forEach((k) => localStorage.removeItem(k));
        window.location.href = "/pages/auth/login.html";
    };

    const enforceAuth = () => {
        const { token: freshToken, userType: freshType } = getStoredAuth();
        if (!freshToken) {
            clearSessionAndRedirect();
            return false;
        }
        if (freshType !== "company") {
            if (!freshType) {
                localStorage.setItem("user_type", "company");
                return true;
            }
            clearSessionAndRedirect();
            return false;
        }
        return true;
    };

    if (!token || userType !== "company") {
        if (token && !userType) {
            localStorage.setItem("user_type", "company");
        } else {
            clearSessionAndRedirect();
            return;
        }
    }

    enforceAuth();

    const headers = { Authorization: "Bearer " + token };

    const logoutBtn = document.getElementById("companyLogoutBtn");
    if (logoutBtn) {
        logoutBtn.addEventListener("click", () => {
            try {
                if (window.auth && typeof auth.logout === "function") {
                    auth.logout();
                    return;
                }
            } catch (_) {}
            clearSessionAndRedirect();
        });
    }

    const elActiveJobs = document.getElementById("metricActiveJobs");
    const elApplications = document.getElementById("metricApplications");
    const elInterviews = document.getElementById("metricInterviews");
    const elHires = document.getElementById("metricHires");
    const activeJobsList = document.getElementById("activeJobsList");
    const recentCandidatesList = document.getElementById("recentCandidatesList");

    const safeText = (val, fallback = "-") =>
        val === 0 || val ? val : fallback;
    const initials = (name) =>
        (name || "CN")
            .split(" ")
            .filter(Boolean)
            .slice(0, 2)
            .map((n) => n[0].toUpperCase())
            .join("");

    async function loadMetrics() {
        try {
            const res = await fetch(apiUrl("/api/company/dashboard"), {
                headers,
            });

            if (res.status === 401 || res.status === 403) {
                clearSessionAndRedirect();
                return;
            }

            const data = await res.json();
            if (!res.ok) {
                console.error("Dashboard metrics error:", data);
                return;
            }

            const m = data.metrics || {};
            elActiveJobs.textContent = safeText(m.total_jobs);
            elApplications.textContent = safeText(m.total_applications);
            elInterviews.textContent = safeText(m.active_interviews);
            elHires.textContent = safeText(m.recent_hires);
        } catch (err) {
            console.error("Failed to load metrics:", err);
        }
    }

    async function loadActiveJobs() {
        activeJobsList.innerHTML =
            '<p class="panel-placeholder">Loading active jobs...</p>';

        try {
            const res = await fetch(
                apiUrl("/api/company/jobs?status=active&limit=5"),
                { headers }
            );

            if (res.status === 401 || res.status === 403) {
                clearSessionAndRedirect();
                return;
            }

            const data = await res.json();
            if (!res.ok) {
                console.error("Company jobs error:", data);
                activeJobsList.innerHTML =
                    '<p class="panel-placeholder">Unable to load jobs.</p>';
                return;
            }

            const jobs = Array.isArray(data.jobs) ? data.jobs : [];

    if (!jobs.length) {
        activeJobsList.innerHTML =
            '<p class="panel-placeholder">No active job postings yet.</p>';
        return;
    }

    const formatSalary = (value) => {
        if (value == null || value === "") return null;
        const num = Number(value);
        if (Number.isFinite(num)) {
            return num.toLocaleString();
        }
        return String(value);
    };

            activeJobsList.innerHTML = "";
            jobs.forEach((job) => {
                const status = (job.status || "active").toLowerCase();
                if (status !== "active" && job.status) return;

                const card = document.createElement("div");
                card.className = "dashboard-job-card";

                const left = document.createElement("div");
                left.className = "dashboard-job-info";

                const title = document.createElement("div");
                title.className = "dashboard-job-title";
                title.textContent = job.title || "Untitled role";

                const company = document.createElement("div");
                company.className = "dashboard-job-company";
                company.textContent = job.location || job.department || "Location not set";

                const meta = document.createElement("div");
                meta.className = "dashboard-job-meta";
                const type = job.job_type || "Type not set";
                const dept = job.department || job.education_level || "Department not set";
                meta.textContent = `${type} • ${dept}`;

                left.appendChild(title);
                left.appendChild(company);
                left.appendChild(meta);

                const right = document.createElement("div");
                right.className = "dashboard-job-actions";

                const statusTag = document.createElement("span");
                statusTag.className = `job-status-tag ${status === "active" ? "status-active" : "status-draft"}`;
                statusTag.textContent = status.charAt(0).toUpperCase() + status.slice(1);

                const salary = document.createElement("div");
                salary.className = "dashboard-job-salary";
                const minSalary = formatSalary(job.salary_min);
                const maxSalary = formatSalary(job.salary_max);
                if (minSalary && maxSalary) {
                    salary.textContent =
                        `${minSalary} - ${maxSalary}` +
                        (job.salary_type ? ` ${job.salary_type}` : "");
                } else {
                    salary.textContent = "Salary not specified";
                }

                const posted = document.createElement("div");
                posted.className = "dashboard-job-posted";
                posted.textContent = job.created_at
                    ? `Posted: ${new Date(job.created_at).toLocaleDateString()}`
                    : "Posted: N/A";

                const buttons = document.createElement("div");
                buttons.className = "dashboard-job-buttons";

                const editBtn = document.createElement("a");
                editBtn.href = `/pages/company/jobs/create.html?id=${job.id}`;
                editBtn.className = "btn btn-ghost";
                editBtn.textContent = "Edit";

                const deleteBtn = document.createElement("button");
                deleteBtn.type = "button";
                deleteBtn.className = "btn btn-danger";
                deleteBtn.textContent = "Delete";
                deleteBtn.addEventListener("click", async () => {
                    if (!confirm("Are you sure you want to delete this job posting?")) return;
                    deleteBtn.disabled = true;
                    try {
                        const res = await fetch(apiUrl(`/api/company/jobs/${job.id}`), {
                            method: "DELETE",
                            headers,
                        });
                        const data = await res.json().catch(() => ({}));
                        if (!res.ok) {
                            alert(data.error || "Failed to delete job");
                            return;
                        }
                        loadActiveJobs();
                    } catch (err) {
                        console.error("Delete job error:", err);
                        alert("Network error while deleting job.");
                    } finally {
                        deleteBtn.disabled = false;
                    }
                });
                buttons.appendChild(deleteBtn);
                buttons.appendChild(editBtn);

                right.appendChild(statusTag);
                right.appendChild(salary);
                right.appendChild(posted);
                right.appendChild(buttons);

                card.appendChild(left);
                card.appendChild(right);
                activeJobsList.appendChild(card);
            });
        } catch (err) {
            console.error("Failed to load company jobs:", err);
            activeJobsList.innerHTML =
                '<p class="panel-placeholder">Unable to load jobs.</p>';
        }
    }

    function buildProfileModal(profile = {}) {
        const overlay = document.createElement("div");
        overlay.className = "modal-overlay";

        const card = document.createElement("div");
        card.className = "modal-card";

        const close = document.createElement("button");
        close.className = "modal-close";
        close.setAttribute("aria-label", "Close");
        close.innerHTML = "&times;";
        close.addEventListener("click", () => overlay.remove());

        const header = document.createElement("div");
        header.className = "modal-header";

        const avatar = document.createElement("div");
        avatar.className = "modal-avatar";
        const avatarUrl = profile.profile_picture_url;
        if (avatarUrl) {
            const img = document.createElement("img");
            img.src = avatarUrl;
            img.alt = profile.full_name || "Avatar";
            avatar.appendChild(img);
        } else {
            avatar.style.display = "flex";
            avatar.style.alignItems = "center";
            avatar.style.justifyContent = "center";
            avatar.style.background =
                "linear-gradient(135deg, #e0e7ff, #c7d2fe)";
            avatar.style.color = "#0f172a";
            avatar.style.fontWeight = "700";
            avatar.textContent = initials(profile.full_name || "Candidate");
        }

        const nameBlock = document.createElement("div");
        const name = document.createElement("h2");
        name.textContent = profile.full_name || "Candidate";
        const title = document.createElement("p");
        title.className = "modal-title";
        title.textContent = profile.current_title || "Role not set";
        const meta = document.createElement("p");
        meta.className = "modal-meta";
        const location = profile.location || "Location not set";
        const exp = profile.experience_level || "Experience not set";
        meta.textContent = `${location} | ${exp}`;
        nameBlock.appendChild(name);
        nameBlock.appendChild(title);
        nameBlock.appendChild(meta);

        const matchPill = document.createElement("div");
        matchPill.className = "match-pill";
        const score =
            profile.match_score != null ? `${profile.match_score}%` : "N/A";
        matchPill.textContent = score;

        header.appendChild(avatar);
        header.appendChild(nameBlock);
        header.appendChild(matchPill);

        const bio = document.createElement("p");
        bio.className = "modal-bio";
        bio.textContent =
            profile.bio || profile.about || "No bio provided.";

        const matchRow = document.createElement("div");
        matchRow.className = "modal-row";
        const matchLabel = document.createElement("span");
        matchLabel.textContent = "Match";
        const matchValue = document.createElement("strong");
        matchValue.textContent = score;
        matchRow.appendChild(matchLabel);
        matchRow.appendChild(matchValue);

        const skillsWrap = document.createElement("div");
        skillsWrap.className = "modal-skills";
        const skillsLabel = document.createElement("div");
        skillsLabel.className = "skills-label";
        skillsLabel.textContent = "Skills";
        skillsWrap.appendChild(skillsLabel);

        const skills = Array.isArray(profile.skills) ? profile.skills : [];
        const skillsContainer = document.createElement("div");
        skillsContainer.className = "skills-wrap";
        if (skills.length) {
            skills.forEach((s) => {
                const pill = document.createElement("span");
                pill.className = "pill";
                pill.textContent = s;
                skillsContainer.appendChild(pill);
            });
        } else {
            const none = document.createElement("span");
            none.textContent = "No skills listed.";
            skillsContainer.appendChild(none);
        }
        skillsWrap.appendChild(skillsContainer);

        card.appendChild(close);
        card.appendChild(header);
        card.appendChild(bio);
        card.appendChild(matchRow);
        card.appendChild(skillsWrap);

        overlay.appendChild(card);
        overlay.addEventListener("click", (e) => {
            if (e.target === overlay) overlay.remove();
        });
        return overlay;
    }

    async function openCandidateProfile(candidateId) {
        if (!candidateId) return;
        try {
            const res = await fetch(
                apiUrl(`/api/company/candidates/${candidateId}`),
                { headers }
            );

            if (res.status === 401 || res.status === 403) {
                clearSessionAndRedirect();
                return;
            }

            const data = await res.json();
            if (!res.ok || !data.profile) {
                console.error("Failed to load candidate profile:", data);
                alert(data.error || "Unable to load candidate profile.");
                return;
            }

            const modal = buildProfileModal(data.profile);
            document.body.appendChild(modal);
        } catch (err) {
            console.error("Error loading candidate profile:", err);
            alert("Unable to load candidate profile right now.");
        }
    }

    async function loadRecentCandidates() {
        recentCandidatesList.innerHTML =
            '<p class="panel-placeholder">Loading candidates...</p>';

        try {
            const res = await fetch(apiUrl("/api/company/recent-candidates"), {
                headers,
            });

            if (res.status === 401 || res.status === 403) {
                clearSessionAndRedirect();
                return;
            }

            const data = await res.json();
            if (!res.ok) {
                console.error("Recent candidates error:", data);
                recentCandidatesList.innerHTML =
                    '<p class="panel-placeholder">Unable to load candidates.</p>';
                return;
            }

            const candidates = data.candidates || [];
            if (!candidates.length) {
                recentCandidatesList.innerHTML =
                    '<p class="panel-placeholder">No candidates yet.</p>';
                return;
            }

            recentCandidatesList.innerHTML = "";
            candidates.slice(0, 5).forEach((c) => {
                const row = document.createElement("div");
                row.className = "candidate-row";

                const main = document.createElement("div");
                main.className = "candidate-main";

                const name = document.createElement("div");
                name.className = "candidate-name";
                name.textContent = c.full_name || "Candidate";

                const role = document.createElement("div");
                role.className = "candidate-role";
                role.textContent =
                    c.title || c.current_title || "Role not set";

                const meta = document.createElement("div");
                meta.className = "candidate-meta";
                const loc = c.location || "Location not set";
                const exp = c.experience_level || "Experience not set";
                meta.textContent = `${loc} | ${exp}`;

                main.appendChild(name);
                main.appendChild(role);
                main.appendChild(meta);

                const right = document.createElement("div");
                right.className = "candidate-right";

                const matchWrap = document.createElement("div");
                matchWrap.innerHTML =
                    'Match <span class="match-pill">' +
                    (c.match_score != null ? `${c.match_score}%` : "N/A") +
                    "</span>";

                const view = document.createElement("a");
                view.href = "#";
                view.className = "btn btn-outline btn-link-action view-profile-btn";
                view.textContent = "View profile";
                view.dataset.candidateId = c.id || c.user_id;

                right.appendChild(matchWrap);
                right.appendChild(view);

                row.appendChild(main);
                row.appendChild(right);

                recentCandidatesList.appendChild(row);
            });
        } catch (err) {
            console.error("Failed to load recent candidates:", err);
            recentCandidatesList.innerHTML =
                '<p class="panel-placeholder">Unable to load candidates.</p>';
        }
    }

    recentCandidatesList?.addEventListener("click", (e) => {
        const btn = e.target.closest(".view-profile-btn");
        if (!btn) return;
        e.preventDefault();
        openCandidateProfile(btn.dataset.candidateId);
    });

    loadMetrics();
    loadActiveJobs();
    loadRecentCandidates();

    history.replaceState(null, "", "/pages/company/dashboard.html");
    window.addEventListener("popstate", () => {
        window.location.href = "/";
    });

    window.addEventListener("pageshow", () => {
        enforceAuth();
    });
    document.addEventListener("visibilitychange", () => {
        if (!document.hidden) enforceAuth();
    });
});
