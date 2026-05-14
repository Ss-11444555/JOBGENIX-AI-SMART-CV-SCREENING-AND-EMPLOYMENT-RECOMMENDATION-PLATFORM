const API_BASE = (window.JobGenixApp && window.JobGenixApp.apiBase) || "http://localhost:8000/api";
const tokenKeys = ["authToken", "token", "jobgenix_token"];

let token = null;
for (const k of tokenKeys) {
    const v = localStorage.getItem(k);
    if (v) { token = v; break; }
}
if (!token || token.length < 10) {
    window.location.href = "/pages/auth/login.html";
}

const $ = (id) => document.getElementById(id);
const setText = (id, val, fallback = "—") => {
    const el = $(id);
    if (el) el.textContent = (val === 0 || val) ? val : fallback;
};
const setValue = (id, val) => {
    const el = $(id);
    if (el) el.value = val ?? "";
};

function formatTopRole(role) {
    if (!role) return null;
    if (typeof role === "string") {
        return role;
    }
    return role.title || role.name || role.role || null;
}

function formatEducationText(profile, cvAnalysis, aiPrediction) {
    const entries = profile.education_detected || cvAnalysis.education_detected || (aiPrediction?.education_detected) || [];
    const level = profile.education_level || cvAnalysis.education_level_detected || (aiPrediction?.education_level_predicted);
    const segments = [];
    if (level) {
        segments.push(level.toUpperCase());
    }
    if (entries.length) {
        segments.push([...new Set(entries)].join(" • "));
    }
    return segments.length ? segments.join(" — ") : null;
}

async function loadProfile() {
    try {
        const res = await fetch(`${API_BASE}/job-seeker/profile`, {
            headers: { Authorization: "Bearer " + token }
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
            alert(data.error || "Failed to load profile");
            return;
        }

        const p = data.profile || {};
        const cv = p.cv_analysis || {};

        // Top summary
        setText("matchScoreHighlight", p.match_score ?? cv.match_score);
        setText("roleHighlight", p.predicted_job_role || cv.predicted_job_role);
        setText("salaryHighlight", p.predicted_salary ?? cv.predicted_salary);
        setText("experienceHighlight", p.predicted_experience_years ?? p.manual_experience_years ?? cv.predicted_experience_years);

        // Profile summary
        setText("profileName", p.full_name || "");
        setText("profileTitle", p.current_title || "");
        setText("profileLocation", p.location || "");
        setText("profileBio", p.bio || "");
        if (p.profile_picture_url) {
            const avatarEl = $("profileAvatar");
            if (avatarEl) avatarEl.src = p.profile_picture_url;
        }

        // Form fields
        setValue("fullName", p.full_name || "");
        setValue("currentTitle", p.current_title || "");
        setValue("location", p.location || "");
        setValue("phone", p.phone || "");
        setValue("bio", p.bio || "");
        setValue("manualExperienceInput", p.manual_experience_years ?? "");

        updateSkills(p.skills || []);

        // CV info
        setText("cvFileName", p.resume_url ? p.resume_url.split("/").pop() : "No resume uploaded yet");

        // AI details
        setText("aiRole", p.predicted_job_role || cv.predicted_job_role);
        setText("aiSalary", p.predicted_salary ?? cv.predicted_salary);
        setText("aiExperience", p.predicted_experience_years ?? p.manual_experience_years ?? cv.predicted_experience_years);
        setValue("manualExperienceInput", p.manual_experience_years ?? "");
        setText("matchScore", p.match_score ?? cv.match_score);

        const aiSkills = cv.skills_detected || [];
        const aiSkillsList = $("aiSkills");
        if (aiSkillsList) {
            aiSkillsList.innerHTML = aiSkills.map((s) => `<li>${s}</li>`).join("");
        }
        const aiSkillsMessage = $("aiSkillsMessage");
        const resumeUploaded = Boolean(p.resume_url || cv.cv_file_url || cv.analysis_date);
        if (aiSkillsMessage) {
            if (!aiSkills.length && resumeUploaded) {
                aiSkillsMessage.textContent = "This project targets IT roles; please include relevant IT skills for a better match.";
                aiSkillsMessage.style.display = "block";
            } else {
                aiSkillsMessage.textContent = "";
                aiSkillsMessage.style.display = "none";
            }
        }

        const topRolesList =
            p.top_job_roles ||
            (p.ai_prediction ? p.ai_prediction.top_job_roles : null) ||
            cv.top_job_roles;
        const formattedRoles = (Array.isArray(topRolesList) ? topRolesList : [])
            .map(formatTopRole)
            .filter(Boolean);
        const topJobRolesEl = $("topJobRoles");
        if (topJobRolesEl) {
            topJobRolesEl.textContent = formattedRoles.length ? formattedRoles.join(" • ") : "—";
        }

        const educationText = formatEducationText(p, cv, p.ai_prediction);
        const educationEl = $("educationSummary");
        if (educationEl) {
            educationEl.textContent = educationText || "—";
        }
    } catch (err) {
        console.error("Profile load failed", err);
        alert("Unable to load profile right now.");
    }
}

function updateSkills(skills) {
    const container = $("skillsList");
    if (!container) return;
    container.innerHTML = skills.map((skill) => `<span>${skill}</span>`).join("");
}

const addSkillBtn = $("addSkillBtn");
if (addSkillBtn) {
    addSkillBtn.onclick = () => {
        const input = $("newSkill");
        if (!input) return;
        const val = input.value.trim();
        if (!val) return;
        const list = $("skillsList");
        if (list) list.innerHTML += `<span>${val}</span>`;
        input.value = "";
    };
}

const saveBtn = $("saveProfileBtn");
if (saveBtn) {
    saveBtn.onclick = async () => {
        const skills = Array.from(document.querySelectorAll("#skillsList span")).map((s) => s.textContent);
        const payload = {
            full_name: $("fullName")?.value || "",
            current_title: $("currentTitle")?.value || "",
            location: $("location")?.value || "",
            phone: $("phone")?.value || "",
            bio: $("bio")?.value || "",
            skills: skills,
        };
        const manualValue = $("manualExperienceInput")?.value;
        if (manualValue) {
            payload.manual_experience_years = parseFloat(manualValue);
        }

        try {
            const res = await fetch(`${API_BASE}/job-seeker/profile`, {
                method: "PUT",
                headers: {
                    "Content-Type": "application/json",
                    Authorization: "Bearer " + token,
                },
                body: JSON.stringify(payload),
            });

            if (res.ok) {
                alert("Profile updated successfully.");
                loadProfile();
            } else {
                const err = await res.json().catch(() => ({}));
                alert(err.error || err.detail || "Error updating profile.");
            }
        } catch (err) {
            console.error("Profile save failed", err);
            alert("Network error. Please try again.");
        }
    };
}

const uploadBtn = $("uploadCvBtn");
if (uploadBtn) {
    uploadBtn.onclick = async () => {
        const file = $("cvUpload")?.files?.[0];
        if (!file) return alert("Choose a CV file");

        const formData = new FormData();
        formData.append("cvFile", file);

        try {
            const res = await fetch(`${API_BASE}/job-seeker/upload-cv`, {
                method: "POST",
                headers: { Authorization: "Bearer " + token },
                body: formData,
            });

            const data = await res.json().catch(() => ({}));
            if (res.ok) {
                alert("CV uploaded and analyzed");
                loadProfile();
            } else {
                alert(data.error || "Failed to upload CV");
            }
        } catch (err) {
            console.error("CV upload failed", err);
            alert("Network error while uploading CV.");
        }
    };
}

// AVATAR UPLOAD
const avatarBtn = $("avatarUploadBtn");
if (avatarBtn) {
    avatarBtn.onclick = async () => {
        const input = $("avatarInput");
        if (!input) return;
        input.click();
    };
}

const avatarInput = $("avatarInput");
if (avatarInput) {
    avatarInput.onchange = async () => {
        const file = avatarInput.files?.[0];
        if (!file) return;
        const formData = new FormData();
        formData.append("avatar", file);
        try {
            const res = await fetch(`${API_BASE}/job-seeker/profile-picture`, {
                method: "POST",
                headers: { Authorization: "Bearer " + token },
                body: formData
            });
            const data = await res.json().catch(() => ({}));
            if (res.ok) {
                const avatarEl = $("profileAvatar");
                if (avatarEl && data.url) avatarEl.src = data.url;
                alert("Profile picture updated.");
            } else {
                alert(data.error || "Failed to upload avatar.");
            }
        } catch (err) {
            console.error("Avatar upload failed", err);
            alert("Network error while uploading avatar.");
        } finally {
            avatarInput.value = "";
        }
    };
}

loadProfile();
