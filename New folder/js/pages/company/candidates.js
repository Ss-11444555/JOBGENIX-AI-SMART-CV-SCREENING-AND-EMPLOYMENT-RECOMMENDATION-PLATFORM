document.addEventListener("DOMContentLoaded", () => {
    const tokenKeys = ["authToken", "token", "jobgenix_token"];
    const token = tokenKeys.map((k) => localStorage.getItem(k)).find(Boolean);
    const API_BASE =
        window.API_BASE_URL ||
        (location.origin.includes("8001")
            ? location.origin.replace("8001", "8000")
            : "http://localhost:8000");
    const apiUrl = (path) =>
        path.startsWith("http") ? path : `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;

    const clearSessionAndRedirect = () => {
        tokenKeys.forEach((k) => localStorage.removeItem(k));
        localStorage.removeItem("user");
        window.location.href = "/pages/auth/login.html";
    };

    if (!token) {
        clearSessionAndRedirect();
        return;
    }

    const authHeaders = { Authorization: "Bearer " + token };

    // Logout
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

    const candidatesList = document.getElementById("candidatesList");
    const candidateCount = document.getElementById("candidateCount");

    const filterSearch = document.getElementById("filterSearch");
    const filterExperience = document.getElementById("filterExperience");
    const filterLocation = document.getElementById("filterLocation");
    const applyFiltersBtn = document.getElementById("applyFiltersBtn");
    const clearFiltersBtn = document.getElementById("clearFiltersBtn");

    function initials(name) {
        if (!name) return "CN";
        return name
            .split(" ")
            .filter(Boolean)
            .slice(0, 2)
            .map((n) => n[0].toUpperCase())
            .join("");
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
        if (!candidateId) {
            alert("Unable to open profile: missing candidate id.");
            return;
        }
        try {
            console.debug("Opening candidate profile", candidateId);
            const res = await fetch(
                apiUrl(`/api/company/candidates/${candidateId}`),
                { headers: authHeaders }
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

    function renderCandidates(candidates) {
        if (!candidates || !candidates.length) {
            candidatesList.innerHTML =
                '<p class="panel-placeholder">No candidates found.</p>';
            candidateCount.textContent = "";
            return;
        }

        candidateCount.textContent = `${candidates.length} candidates`;
        candidatesList.innerHTML = "";

        candidates.forEach((c) => {
            const row = document.createElement("div");
            row.className = "candidate-row";
            const candidateId = c.job_seeker_id || c.id || c.user_id;
            if (candidateId) {
                row.dataset.candidateId = candidateId;
            }

            const main = document.createElement("div");
            main.className = "candidate-main";

            const avatar = document.createElement("div");
            avatar.className = "candidate-avatar";
            avatar.textContent = initials(c.full_name || "Candidate");

            const info = document.createElement("div");
            info.className = "candidate-info";

            const name = document.createElement("h3");
            name.textContent = c.full_name || "Candidate";

            const role = document.createElement("div");
            role.className = "role";
            role.textContent = c.current_title || c.title || "Role not set";

            const meta = document.createElement("div");
            meta.className = "meta";
            const loc = c.location || "Location not set";
            const exp = c.experience_level || "Experience not set";
            meta.textContent = `${loc} | ${exp}`;

            const tags = document.createElement("div");
            tags.className = "candidate-tags";
            if (c.skills && c.skills.length) {
                c.skills.slice(0, 4).forEach((s) => {
                    const pill = document.createElement("span");
                    pill.className = "pill";
                    pill.textContent = s;
                    tags.appendChild(pill);
                });
            }

            info.appendChild(name);
            info.appendChild(role);
            info.appendChild(meta);
            info.appendChild(tags);

            main.appendChild(avatar);
            main.appendChild(info);

            const right = document.createElement("div");
            right.className = "candidate-right";

            const match = document.createElement("div");
            match.className = "match-pill";
            const score = c.match_score != null ? `${c.match_score}%` : "N/A";
            match.textContent = `Match ${score}`;

            const actions = document.createElement("div");
            actions.className = "candidate-actions";

            const viewBtn = document.createElement("a");
            viewBtn.href = "#";
            viewBtn.className = "btn btn-secondary view-profile-btn";
            viewBtn.textContent = "View Profile";
            if (candidateId) {
                viewBtn.dataset.candidateId = candidateId;
            }

            const messageBtn = document.createElement("button");
            messageBtn.className = "btn btn-secondary";
            messageBtn.textContent = "Message";
            messageBtn.addEventListener("click", () => startConversation(c));

            actions.appendChild(viewBtn);
            actions.appendChild(messageBtn);

            right.appendChild(match);
            right.appendChild(actions);

            row.appendChild(main);
            row.appendChild(right);

            candidatesList.appendChild(row);
        });
    }

    async function loadCandidates() {
        candidatesList.innerHTML =
            '<p class="panel-placeholder">Loading candidates...</p>';
        try {
            const res = await fetch(apiUrl("/api/company/candidates"), {
                headers: { Authorization: authHeaders.Authorization },
            });

            if (res.status === 401 || res.status === 403) {
                clearSessionAndRedirect();
                return;
            }

            const data = await res.json();
            if (!res.ok) {
                console.error("Failed to fetch candidates:", data);
                candidatesList.innerHTML =
                    `<p class="panel-placeholder">Unable to load candidates. ${data.error || ""}</p>`;
                return;
            }

            const candidates = data.candidates || [];
            renderCandidates(candidates);
        } catch (err) {
            console.error("Error loading candidates:", err);
            candidatesList.innerHTML =
                '<p class="panel-placeholder">Unable to load candidates.</p>';
        }
    }

    async function startConversation(candidate) {
        const candidateId = candidate?.id || candidate?.user_id;
        if (!candidateId) {
            alert("Unable to start conversation: missing candidate id.");
            return;
        }
        try {
            const res = await fetch(apiUrl("/api/company/messages/start"), {
                method: "POST",
                headers: {
                    Authorization: authHeaders.Authorization,
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    job_seeker_id: candidateId,
                }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                alert(data.error || data.detail || "Failed to start conversation");
                return;
            }
            const convId = data.conversation_id;
            if (convId) {
                window.location.href = `/pages/company/messages.html?conversation_id=${convId}`;
            }
        } catch (err) {
            console.error("Failed to start conversation:", err);
            alert(`Network error while starting conversation. ${err?.message || ""}`);
        }
    }

    function applyFilters() {
        const search = (filterSearch?.value || "").toLowerCase();
        const experience = (filterExperience?.value || "").toLowerCase();
        const location = (filterLocation?.value || "").toLowerCase();

        const rows = Array.from(
            candidatesList.querySelectorAll(".candidate-row")
        );
        rows.forEach((row) => {
            const text = row.textContent.toLowerCase();
            const matchesSearch = !search || text.includes(search);
            const matchesExp = !experience || text.includes(experience);
            const matchesLoc = !location || text.includes(location);
            row.style.display =
                matchesSearch && matchesExp && matchesLoc ? "" : "none";
        });
    }

    applyFiltersBtn?.addEventListener("click", applyFilters);
    clearFiltersBtn?.addEventListener("click", () => {
        if (filterSearch) filterSearch.value = "";
        if (filterExperience) filterExperience.value = "";
        if (filterLocation) filterLocation.value = "";
        applyFilters();
    });

    candidatesList?.addEventListener("click", (e) => {
        const btn = e.target.closest(".view-profile-btn");
        if (!btn) return;
        e.preventDefault();
        const candidateId = btn.dataset.candidateId;
        openCandidateProfile(candidateId);
    });

    loadCandidates();
});
