document.addEventListener("DOMContentLoaded", () => {
    const token =
        localStorage.getItem("authToken") ||
        localStorage.getItem("token") ||
        localStorage.getItem("jobgenix_token");
    const API_BASE = window.API_BASE_URL || "http://localhost:8000";
    const apiUrl = (path) =>
        path.startsWith("http") ? path : `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;

    if (!token) {
        window.location.href = "/pages/auth/login.html";
        return;
    }

    const authHeaders = {
        Authorization: "Bearer " + token,
        "Content-Type": "application/json"
    };

    // Logout button
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

    // ----- COMPANY PROFILE -----

    const profileForm = document.getElementById("companyProfileForm");
    const companyJobsList = document.getElementById("companyJobsList");

    async function loadCompanyProfile() {
        try {
            const res = await fetch(apiUrl("/api/company/profile"), {
                headers: { Authorization: authHeaders.Authorization }
            });

            if (res.status === 401 || res.status === 403) {
                localStorage.removeItem("authToken");
                localStorage.removeItem("token");
                window.location.href = "/pages/auth/login.html";
                return;
            }

            const data = await res.json();
            if (!res.ok) {
                console.error("Failed to fetch company profile:", data);
                return;
            }

            const c = data.company || {};

            if (document.getElementById("companyName"))
                document.getElementById("companyName").value = c.company_name || "";
            if (document.getElementById("industry"))
                document.getElementById("industry").value = c.industry || "";
            if (document.getElementById("companySize"))
                document.getElementById("companySize").value = c.company_size || "";
            if (document.getElementById("website"))
                document.getElementById("website").value = c.website || "";
            if (document.getElementById("contactEmail"))
                document.getElementById("contactEmail").value = c.contact_email || "";
            if (document.getElementById("description"))
                document.getElementById("description").value = c.description || "";
        } catch (err) {
            console.error("Error loading company profile:", err);
        }
    }

    if (profileForm) {
        profileForm.addEventListener("submit", async (e) => {
            e.preventDefault();

            const payload = {
                company_name: document.getElementById("companyName").value.trim(),
                industry: document.getElementById("industry").value.trim(),
                company_size: document.getElementById("companySize").value,
                website: document.getElementById("website").value.trim(),
                contact_email: document.getElementById("contactEmail").value.trim(),
                description: document.getElementById("description").value.trim()
            };

            const submitBtn = profileForm.querySelector("button[type='submit']");
            const originalText = submitBtn.textContent;
            submitBtn.textContent = "Saving...";
            submitBtn.disabled = true;

            try {
                const res = await fetch(apiUrl("/api/company/profile"), {
                    method: "PUT",
                    headers: authHeaders,
                    body: JSON.stringify(payload)
                });

                const data = await res.json();
            if (!res.ok) {
                alert(data.error || "Failed to update company profile");
                console.error("Profile update error:", data);
                return;
            }

            alert("Company profile updated successfully.");
        } catch (err) {
            console.error("Profile update error:", err);
            alert("Network error while updating profile.");
        } finally {
            submitBtn.textContent = originalText;
            submitBtn.disabled = false;
        }
    });
    }

    // ----- JOB LIST (REAL DATA) -----

    async function loadCompanyJobs() {
        companyJobsList.innerHTML =
            '<p class="panel-placeholder">Loading your jobs...</p>';

        try {
            const res = await fetch(apiUrl("/api/company/jobs"), {
                headers: { Authorization: authHeaders.Authorization }
            });

            if (res.status === 401 || res.status === 403) {
                localStorage.removeItem("authToken");
                localStorage.removeItem("token");
                window.location.href = "/pages/auth/login.html";
                return;
            }

            const data = await res.json();
            if (!res.ok) {
                console.error("Failed to fetch company jobs:", data);
                companyJobsList.innerHTML =
                    '<p class="panel-placeholder">Unable to load jobs.</p>';
                return;
            }

            const jobs = data.jobs || [];
            if (!jobs.length) {
                companyJobsList.innerHTML =
                    '<p class="panel-placeholder">You have no job postings yet.</p>';
                return;
            }

            companyJobsList.innerHTML = "";

            jobs.forEach((job) => {
                // Only show active ones (or show all if no status column)
                const status = (job.status || "active").toLowerCase();
                if (status !== "active" && job.status) {
                    return; // skip non-active
                }

                const row = document.createElement("div");
                row.className = "company-job-row";

                const main = document.createElement("div");
                main.className = "company-job-main";

                const title = document.createElement("div");
                title.className = "company-job-title";
                title.textContent = job.title || "Untitled job";

                const sub = document.createElement("div");
                sub.className = "company-job-sub";
                sub.textContent = job.location || "Location not set";

                const meta = document.createElement("div");
                meta.className = "company-job-meta";
                const type = job.job_type || "Type not set";
                const dept = job.department || "Department not set";
                meta.textContent = `${type} • ${dept}`;

                main.appendChild(title);
                main.appendChild(sub);
                main.appendChild(meta);

                const right = document.createElement("div");
                right.className = "company-job-right";

                const statusPill = document.createElement("div");
                statusPill.className = "job-status-pill";
                if (status === "active") statusPill.classList.add("job-status-active");
                else if (status === "draft") statusPill.classList.add("job-status-draft");
                else statusPill.classList.add("job-status-closed");
                statusPill.textContent = status.charAt(0).toUpperCase() + status.slice(1);

                const salary = document.createElement("div");
                if (job.salary_min != null && job.salary_max != null) {
                    salary.textContent =
                        `${job.salary_min} - ${job.salary_max}` +
                        (job.salary_type ? ` ${job.salary_type}` : "");
                } else {
                    salary.textContent = "Salary: not specified";
                }

                const posted = document.createElement("div");
                posted.textContent = job.created_at
                    ? `Posted: ${new Date(job.created_at).toLocaleDateString()}`
                    : "";

                const actions = document.createElement("div");
                actions.className = "company-job-actions";

                // const viewBtn = document.createElement("a");
                // viewBtn.href = `/pages/company/jobs/view.html?id=${job.id}`;
                // viewBtn.className = "btn btn-secondary";
                // viewBtn.textContent = "View";

                const editBtn = document.createElement("a");
                editBtn.href = `/pages/company/jobs/create.html?id=${job.id}`;
                editBtn.className = "btn btn-secondary";
                editBtn.textContent = "Edit";

                const deleteBtn = document.createElement("button");
                deleteBtn.type = "button";
                deleteBtn.className = "btn btn-danger";
                deleteBtn.textContent = "Delete";
                deleteBtn.addEventListener("click", async (e) => {
                    e.preventDefault();
                    if (!confirm("Are you sure you want to delete this job posting?")) return;
                    deleteBtn.disabled = true;
                    try {
                        const res = await fetch(apiUrl(`/api/company/jobs/${job.id}`), {
                            method: "DELETE",
                            headers: { Authorization: authHeaders.Authorization },
                        });
                        const data = await res.json().catch(() => ({}));
                        if (!res.ok) {
                            alert(data.error || "Failed to delete job");
                            return;
                        }
                        loadCompanyJobs();
                    } catch (err) {
                        console.error("Delete job error:", err);
                        alert("Network error while deleting job.");
                    } finally {
                        deleteBtn.disabled = false;
                    }
                });

                // actions.appendChild(viewBtn);
                actions.appendChild(editBtn);
                actions.appendChild(deleteBtn);

                right.appendChild(statusPill);
                right.appendChild(salary);
                right.appendChild(posted);
                right.appendChild(actions);

                row.appendChild(main);
                row.appendChild(right);

                companyJobsList.appendChild(row);
            });

            if (!companyJobsList.innerHTML.trim()) {
                companyJobsList.innerHTML =
                    '<p class="panel-placeholder">No active job postings.</p>';
            }
        } catch (err) {
            console.error("Error loading company jobs:", err);
            companyJobsList.innerHTML =
                '<p class="panel-placeholder">Unable to load jobs.</p>';
        }
    }

    // Initial loads
    loadCompanyProfile();
    loadCompanyJobs();
});
