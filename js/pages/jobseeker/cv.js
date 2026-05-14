document.addEventListener("DOMContentLoaded", () => {
    const API_BASE = (window.JobGenixApp && window.JobGenixApp.apiBase) || "http://localhost:8000/api";
    // Try both keys in case your login stored "token" instead of "authToken"
    const token =
        localStorage.getItem("authToken") ||
        localStorage.getItem("token") ||
        localStorage.getItem("jobgenix_token");

    if (!token) {
        window.location.href = "/pages/auth/login.html";
        return;
    }

    const cvFileNameEl   = document.getElementById("cvFileName");
    const cvDownloadLink = document.getElementById("cvDownloadLink");
    const cvFileInput    = document.getElementById("cvFileInput");
    const uploadBtn      = document.getElementById("uploadCvBtn");
    const uploadStatus   = document.getElementById("uploadStatus");

    const aiRoleEl       = document.getElementById("aiRole");
    const aiSalaryEl     = document.getElementById("aiSalary");
    const aiExperienceEl = document.getElementById("aiExperience");
    const matchScoreEl   = document.getElementById("matchScore");
    const aiSkillsList   = document.getElementById("aiSkills");

    // 1) Load existing CV + AI info from /api/job-seeker/profile
    async function loadCvData() {
        try {
            const res = await fetch(`${API_BASE}/job-seeker/profile`, {
                headers: {
                    "Authorization": "Bearer " + token
                }
            });

            if (res.status === 401 || res.status === 403) {
                // token invalid → logout
                localStorage.removeItem("authToken");
                localStorage.removeItem("token");
                window.location.href = "/pages/auth/login.html";
                return;
            }

            const data = await res.json();

            if (!res.ok) {
                console.error("Profile error:", data);
                uploadStatus.textContent =
                    data.error || "Failed to load CV information.";
                return;
            }

            const profile = data.profile || {};

            // CV file info
            if (profile.resume_url_full || profile.resume_url) {
                const url =
                    profile.resume_url_full || profile.resume_url;
                const name =
                    (profile.cv_analysis &&
                        profile.cv_analysis.cv_file_name) ||
                    url.split("/").pop();

                cvFileNameEl.textContent = name || "CV uploaded";
                cvDownloadLink.href = url;
                cvDownloadLink.style.display = "inline-block";
            } else {
                cvFileNameEl.textContent = "No resume uploaded yet";
                cvDownloadLink.style.display = "none";
            }

            // AI fields
            aiRoleEl.textContent =
                profile.predicted_job_role ||
                (profile.cv_analysis &&
                    profile.cv_analysis.predicted_job_role) ||
                "—";

            aiSalaryEl.textContent =
                profile.predicted_salary ||
                (profile.cv_analysis &&
                    profile.cv_analysis.predicted_salary) ||
                "—";

            aiExperienceEl.textContent =
                profile.predicted_experience_years ||
                (profile.cv_analysis &&
                    profile.cv_analysis.predicted_experience_years) ||
                "—";

            matchScoreEl.textContent =
                profile.match_score ||
                (profile.cv_analysis &&
                    profile.cv_analysis.match_score) ||
                0;

            const skills =
                (profile.cv_analysis &&
                    profile.cv_analysis.skills_detected) ||
                [];

            aiSkillsList.innerHTML = "";

            if (skills.length) {
                skills.forEach((s) => {
                    const li = document.createElement("li");
                    li.textContent = s;
                    aiSkillsList.appendChild(li);
                });
            } else {
                const li = document.createElement("li");
                li.textContent =
                    "No skills detected yet. Upload a CV to analyze.";
                li.style.opacity = "0.7";
                aiSkillsList.appendChild(li);
            }
        } catch (err) {
            console.error("Failed to load CV data:", err);
            uploadStatus.textContent = "Error loading CV information.";
        }
    }

    // 2) Upload new CV to /api/job-seeker/upload-cv
    async function uploadCv() {
        const file = cvFileInput.files[0];
        if (!file) {
            alert("Please choose a CV file first.");
            return;
        }

        uploadStatus.textContent = "Uploading and analyzing CV...";
        uploadBtn.disabled = true;

        const formData = new FormData();
        formData.append("cvFile", file); // name matches app.py: request.files['cvFile']

        try {
            const res = await fetch(`${API_BASE}/job-seeker/upload-cv`, {
                method: "POST",
                headers: {
                    "Authorization": "Bearer " + token
                    // Don't set Content-Type for FormData
                },
                body: formData
            });

            const data = await res.json();

            if (!res.ok) {
                console.error("Upload error:", data);
                uploadStatus.textContent =
                    data.error || "Failed to upload CV.";
                uploadBtn.disabled = false;
                return;
            }

            // Backend: { message, resume_url, profile, analysis }
            uploadStatus.textContent =
                "CV uploaded successfully. AI analysis updated.";

            // Refresh with new DB data
            await loadCvData();
        } catch (err) {
            console.error("CV upload failed:", err);
            uploadStatus.textContent =
                "Network error while uploading CV.";
        } finally {
            uploadBtn.disabled = false;
        }
    }

    uploadBtn.addEventListener("click", uploadCv);

    // Initial load
    loadCvData();
});
