console.info("Job search script v2 loaded");

document.addEventListener("DOMContentLoaded", () => {
    const API_BASE = (window.JobGenixApp && window.JobGenixApp.apiBase) || "http://localhost:8000/api";
    const token =
        localStorage.getItem("authToken") ||
        localStorage.getItem("token") ||
        localStorage.getItem("jobgenix_token");
    const storedUserRaw = localStorage.getItem("user");
    let storedUser = null;
    try {
        storedUser = storedUserRaw ? JSON.parse(storedUserRaw) : null;
    } catch (_) {
        storedUser = null;
    }

    // Require login
    if (!token) {
        window.location.href = "/pages/auth/login.html";
        return;
    }

    let profileReady = false;
    async function ensureProfile() {
        if (profileReady) return true;
        try {
            const res = await fetch(`${API_BASE}/job-seeker/profile`, {
                headers: { Authorization: "Bearer " + token }
            });
            if (res.status === 404) {
                alert("Job seeker profile not found. Please complete your profile first.");
                window.location.href = "/pages/jobseeker/profile.html";
                return false;
            }
            if (!res.ok) {
                console.warn("Profile check failed:", res.status);
                return false;
            }
            profileReady = true;
            return true;
        } catch (err) {
            console.warn("Profile check error", err);
            return false;
        }
    }
    // Kick off a check immediately
    ensureProfile();

    const form = document.getElementById("jobSearchForm");
    const resultsContainer = document.getElementById("jobsResults");
    const resultsCountEl = document.getElementById("resultsCount");
    const noResultsEl = document.getElementById("noResultsMessage");

    const modal = document.getElementById("jobDetailsModal");
    const modalBody = document.getElementById("jobModalBody");
    const modalClose = document.getElementById("jobModalClose");

    const keywordInput   = document.getElementById("keyword");
    const locationInput  = document.getElementById("location");
    const jobTypeSelect  = document.getElementById("jobType");
    const expSelect      = document.getElementById("experience");

    const APPLIED_PREFIX = "jobgenix_applied_jobs_";
    function buildUserStorageKey(user) {
        if (!user) return null;
        const id = user.id ?? user.user_id ?? user.userId;
        if (id) return `u_${id}`;
        if (user.email) return `e_${String(user.email).trim().toLowerCase()}`;
        return null;
    }
    function getCurrentUserKey() {
        const keyFromUser = buildUserStorageKey(storedUser);
        if (keyFromUser) return keyFromUser;
        if (token) return `t_${token}`;
        return "anon";
    }
    const APPLIED_STORAGE_KEY = `${APPLIED_PREFIX}${getCurrentUserKey()}`;

    // Remove applied maps from other users to avoid cross-account bleed
    function clearStaleAppliedMaps() {
        try {
            const keys = Object.keys(localStorage);
            for (const k of keys) {
                if (k.startsWith(APPLIED_PREFIX) && k !== APPLIED_STORAGE_KEY) {
                    localStorage.removeItem(k);
                }
            }
        } catch (_) {}
    }
    clearStaleAppliedMaps();

    function readStoredApplications() {
        try {
            const raw = localStorage.getItem(APPLIED_STORAGE_KEY);
            return raw ? JSON.parse(raw) : {};
        } catch (_) {
            return {};
        }
    }

    function persistApplications(map) {
        try {
            localStorage.setItem(APPLIED_STORAGE_KEY, JSON.stringify(map));
        } catch (_) {
            // Best effort; ignore storage failures
        }
    }

    let appliedMap = readStoredApplications();
    const statusClasses = ["status-applied", "status-approved", "status-rejected"];

    function getJobKey(jobish) {
        const val = jobish?.id ?? jobish?.job_id ?? jobish?._id ?? jobish?.jobId ?? jobish?.jobID ?? jobish;
        return val != null ? String(val) : "";
    }

    function normalizeStatus(status) {
        const s = (status || "").toString().toLowerCase();
        const approvedSignals = ["approved", "accepted", "hired", "interview", "interviewing", "shortlisted", "selected", "offer", "interview scheduled"];
        const rejectedSignals = ["rejected", "declined", "denied", "cancelled", "withdrawn", "unsuccessful"];
        if (approvedSignals.some((term) => s.includes(term))) return "approved";
        if (rejectedSignals.some((term) => s.includes(term))) return "rejected";
        return "applied";
    }

    function applyStatusToButton(btn, status) {
        const normalized = normalizeStatus(status);
        btn.disabled = true;
        btn.classList.remove("btn-primary", "btn-disabled", ...statusClasses);
        btn.classList.add("job-apply", `status-${normalized}`);
        if (!btn.classList.contains("btn")) btn.classList.add("btn");
        if (normalized === "approved") {
            btn.textContent = "Approved";
        } else if (normalized === "rejected") {
            btn.textContent = "Rejected";
        } else {
            btn.textContent = "Applied";
        }
    }

    async function loadApplied() {
        try {
            const res = await fetch(`${API_BASE}/job-seeker/applications`, {
                headers: { Authorization: "Bearer " + token }
            });
            const data = await res.json().catch(() => ({}));
            if (res.ok && data.applications) {
                const serverApplied = {};
                data.applications.forEach(a => {
                    const jobId = getJobKey(a.job_id ?? a.job ?? a);
                    if (!jobId) return;
                    serverApplied[jobId] = normalizeStatus(a.status || a.application_status || a.state);
                });
                appliedMap = { ...appliedMap, ...serverApplied };
                persistApplications(appliedMap);
            }
        } catch (e) {
            console.error("Failed to load existing applications", e);
        }
    }

    async function refreshJobCards() {
        await loadApplied();
        await loadJobs();
    }

    async function loadJobs() {
        const params = new URLSearchParams();

        const q          = keywordInput.value.trim();
        const loc        = locationInput.value.trim();
        const type       = jobTypeSelect.value;
        const experience = expSelect.value;

        if (q)          params.append("q", q);
        if (loc)        params.append("location", loc);
        if (type && type !== 'any')       params.append("type", type);
        if (experience && experience !== 'any') params.append("experience", experience);
        params.append("limit", "1000");

        try {
            const res = await fetch(`${API_BASE}/jobs/search?${params.toString()}`, {
                headers: {
                    "Authorization": "Bearer " + token
                }
            });

            if (res.status === 401 || res.status === 403) {
                localStorage.removeItem("authToken");
                localStorage.removeItem("token");
                localStorage.removeItem("jobgenix_token");
                window.location.href = "/pages/auth/login.html";
                return;
            }

        const data = await res.json().catch(() => ({}));

        if (!res.ok) {
            console.error("Job search error:", data);
            showError(data.error || "Failed to load jobs.");
            return;
        }

        renderJobs(data.jobs || []);
    } catch (err) {
        console.error("Job search network error:", err);
        showError("Network error. Please try again.");
    }
}

    function renderJobs(jobs) {
        resultsContainer.innerHTML = "";

        if (!jobs.length) {
            resultsCountEl.textContent = "0 jobs found";
            noResultsEl.style.display = "block";
            return;
        }

        noResultsEl.style.display = "none";
        resultsCountEl.textContent =
            `${jobs.length} job${jobs.length === 1 ? "" : "s"} found`;

        jobs.forEach((job) => {
            const card = document.createElement("div");
            card.className = "job-card";

            const main = document.createElement("div");
            main.className = "job-main";

            const title = document.createElement("div");
            title.className = "job-title";
            title.textContent = job.title || "Untitled role";

            const company = document.createElement("div");
            company.className = "job-company";
            const companyName = job.company_name || job.company || "Company";
            company.textContent =
                `${companyName} • ${job.location || "Location not set"}`;

            const meta = document.createElement("div");
            meta.className = "job-meta";
            const typeText = job.job_type || job.type || "Type not set";
            const expText =
                job.experience_level || job.experience || "Experience not set";
            meta.textContent = `${typeText} • ${expText}`;

            const skills = document.createElement("div");
            skills.className = "job-skills";
            (job.required_skills || []).slice(0, 6).forEach((s) => {
                const tag = document.createElement("span");
                tag.textContent = s;
                skills.appendChild(tag);
            });

            main.appendChild(title);
            main.appendChild(company);
            main.appendChild(meta);
            if ((job.required_skills || []).length) {
                main.appendChild(skills);
            }

            const actions = document.createElement("div");
            actions.className = "job-actions";

            const salary = document.createElement("div");
            salary.className = "job-salary";
            if (job.salary_min != null && job.salary_max != null) {
                salary.textContent = `${job.salary_min} - ${job.salary_max} ${job.salary_type || ""}`;
            } else {
                salary.textContent = "Salary not specified";
            }

            const viewBtn = document.createElement("button");
            viewBtn.type = "button";
            viewBtn.className = "btn btn-secondary";
            viewBtn.textContent = "View Details";

            const applyBtn = document.createElement("button");
            applyBtn.className = "btn btn-primary job-apply";
            const jobKey = getJobKey(job);
            const existingStatus = appliedMap[jobKey];
            if (existingStatus) {
                applyStatusToButton(applyBtn, existingStatus);
            } else {
                applyBtn.textContent = "Quick Apply";
                applyBtn.addEventListener("click", () => submitApplication(job, applyBtn, jobKey));
            }

            actions.appendChild(salary);
            actions.appendChild(viewBtn);
            actions.appendChild(applyBtn);

            viewBtn.addEventListener("click", () => openJobModal(job.id));

            card.appendChild(main);
            card.appendChild(actions);

            resultsContainer.appendChild(card);
        });
    }

    async function submitApplication(job, btn, jobKeyOverride) {
        const jobId = jobKeyOverride || getJobKey(job);
        if (!jobId) {
            alert("Job id missing.");
            return;
        }
        const okProfile = await ensureProfile();
        if (!okProfile) return;
        const original = btn.textContent;
        btn.disabled = true;
        btn.textContent = "Applying...";
        try {
            const res = await fetch(`${API_BASE}/job-seeker/applications`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    Authorization: "Bearer " + token,
                },
                body: JSON.stringify({ job_id: jobId }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                if (res.status === 404 && (data.error || "").toLowerCase().includes("profile")) {
                    alert("Job seeker profile not found. Please complete your profile first.");
                    window.location.href = "/pages/jobseeker/profile.html";
                    return;
                }
                alert(data.error || data.detail || "Failed to apply.");
                return;
            }
            const nextStatus = normalizeStatus(data.status || data.application_status || "applied");
            appliedMap[jobId] = nextStatus;
            persistApplications(appliedMap);
            applyStatusToButton(btn, nextStatus);
        } catch (err) {
            console.error("Apply error", err);
            alert("Network error while applying. " + (err?.message || ""));
        } finally {
            if (!btn.disabled || btn.textContent === original) {
                btn.textContent = original;
                btn.disabled = false;
            }
        }
    }

    function openJobModal(jobId) {
        if (!modal || !modalBody) return;
        modalBody.innerHTML = "<p>Loading...</p>";
        modal.style.display = "flex";
        modal.setAttribute("aria-hidden", "false");
        fetchJobDetails(jobId);
    }

    function closeJobModal() {
        if (!modal) return;
        modal.style.display = "none";
        modal.setAttribute("aria-hidden", "true");
    }

    async function fetchJobDetails(jobId) {
        try {
            const res = await fetch(`${API_BASE}/jobs/${jobId}`, {
                headers: { "Authorization": "Bearer " + token }
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok || !data.job) {
                modalBody.innerHTML = `<p>Unable to load job details.</p>`;
                return;
            }
            renderJobModal(data.job);
        } catch (e) {
            modalBody.innerHTML = `<p>Unable to load job details.</p>`;
        }
    }

    function renderJobModal(job) {
        const companyName = job.company_name || job.company || "Company not provided";
        const location = job.location || "Not specified";
        const typeText = job.job_type || job.type || "Not specified";
        const expText = job.experience_level || job.experience || "Not specified";
        const description = job.description || job.requirements || "No description provided.";
        const benefits = normalizeList(job.benefits);
        const required = normalizeList(job.required_skills || job.requiredSkills);
        const bonus = normalizeList(job.bonus_skills || job.bonusSkills);
        const salaryText = (job.salary_min != null && job.salary_max != null)
            ? `${job.salary_min} - ${job.salary_max} ${job.salary_type || ""}`.trim()
            : "Not specified";
        const deadline = job.application_deadline || job.deadline || "";

        const chips = (label, items) => items.length
            ? `<div class="job-modal__section"><h4>${label}</h4><div class="job-modal__list">${items.map(s => `<span>${s}</span>`).join("")}</div></div>`
            : "";
        
        const dateOnly = deadline ? new Date(deadline).toLocaleDateString() : "";        
        
        modalBody.innerHTML = `
            <div class="job-modal__header">
                <h3>${job.title || "Job details"}</h3>
                <div class="job-modal__meta">
                    <span class="job-modal__pill">${companyName}</span>
                    <span class="job-modal__pill">${location}</span>
                    <span class="job-modal__pill">${typeText}</span>
                    <span class="job-modal__pill">${expText}</span>
                </div>
            </div>
            <div class="job-modal__section">
                <h4>Salary</h4>
                <p>${salaryText}</p>
            </div>
            <div class="job-modal__section">
                <h4>Description</h4>
                <p>${description}</p>
            </div>
            ${chips("Required skills", required)}
            ${chips("Bonus skills", bonus)}
            ${chips("Benefits", benefits)}
            ${deadline ? `<div class="job-modal__section"><h4>Application deadline</h4><p>${dateOnly}</p></div>` : ""}        `;
    }

    function normalizeList(val) {
        if (!val) return [];
        if (Array.isArray(val)) return val;
        if (typeof val === "string") {
            try {
                const parsed = JSON.parse(val);
                return Array.isArray(parsed) ? parsed : val.split(",").map(s => s.trim()).filter(Boolean);
            } catch (_) {
                return val.split(",").map(s => s.trim()).filter(Boolean);
            }
        }
        return [];
    }

    modalClose?.addEventListener("click", closeJobModal);
    modal?.addEventListener("click", (e) => {
        if (e.target === modal || e.target.classList.contains("job-modal__backdrop")) {
            closeJobModal();
        }
    });

    function showError(msg) {
        resultsCountEl.textContent = msg;
    }

    // Handle form submit
    form.addEventListener("submit", (e) => {
        e.preventDefault();
        loadJobs();
    });

    // Initial load
    loadApplied().then(() => loadJobs());

    window.addEventListener("pageshow", (event) => {
        if (event.persisted) {
            refreshJobCards();
        }
    });
    window.addEventListener("focus", () => {
        refreshJobCards();
    });
});
