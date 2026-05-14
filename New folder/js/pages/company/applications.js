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

    const authHeaders = {
        Authorization: "Bearer " + token,
        "Content-Type": "application/json",
    };

    const listEl = document.getElementById("applicationsContainer");
    const countEl = document.getElementById("applicationsCount");
    const statTotal = document.getElementById("statTotal");
    const statInterviews = document.getElementById("statInterviews");
    const statHires = document.getElementById("statHires");
    const statAvgMatch = document.getElementById("statAvgMatch");

    const filterSearch = document.getElementById("filterSearch");
    const filterStatus = document.getElementById("filterStatus");
    const filterRole = document.getElementById("filterRole");

    const detailCard = document.getElementById("detailCard");
    const detailName = document.getElementById("detailName");
    const detailJob = document.getElementById("detailJob");
    const detailStatus = document.getElementById("detailStatus");
    const detailMatch = document.getElementById("detailMatch");
    const detailRole = document.getElementById("detailRole");
    const detailInterview = document.getElementById("detailInterview");
    const detailApplied = document.getElementById("detailApplied");
    const detailScheduled = document.getElementById("detailScheduled");
    const detailInterviewStatus = document.getElementById("detailInterviewStatus");
    const detailMeetingLink = document.getElementById("detailMeetingLink");
    const detailInterviewNotes = document.getElementById("detailInterviewNotes");
    const btnSchedule = document.getElementById("btnSchedule");
    const scheduleDate = document.getElementById("scheduleDate");
    const btnAccept = document.getElementById("btnAccept");
    const btnReject = document.getElementById("btnReject");

    const selected = { app: null };
    let companyId = null;
    let applications = [];
    let modalEl = null;

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
            ["authToken", "token", "jobgenix_token"].forEach((k) => localStorage.removeItem(k));
            localStorage.removeItem("user");
            window.location.href = "/pages/auth/login.html";
        });
    }

    function formatDate(val) {
        if (!val) return "-";
        try {
            const d = new Date(val);
            return d.toLocaleDateString(undefined, {
                month: "short",
                day: "numeric",
                year: "numeric",
            });
        } catch {
            return val;
        }
    }

    function formatDateTime(val) {
        if (!val) return "-";
        try {
            const d = new Date(val);
            return d.toLocaleString(undefined, {
                month: "short",
                day: "numeric",
                year: "numeric",
                hour: "numeric",
                minute: "2-digit",
            });
        } catch {
            return val;
        }
    }

    function statusClass(status) {
        if (!status) return "muted";
        const s = status.toLowerCase();
        if (s.includes("interview")) return "interview";
        if (s.includes("accept") || s.includes("hire")) return "accepted";
        if (s.includes("reject") || s.includes("decline")) return "rejected";
        return "pending";
    }

    function applicationSnapshot(app) {
        if (!app) return {};
        const seeker = app.seeker || {};
        const matchScore = app.applied_match_score != null ? app.applied_match_score : app.match_score;
        const predictedRole =
            app.applied_predicted_role ||
            app.predicted_role ||
            app.predictedRole ||
            app.match_predicted_role ||
            app.role_prediction ||
            app.job_title;
        const name = app.applied_full_name || seeker.full_name || "Candidate";
        const jobTitle = app.applied_job_title || app.job_title || "Role";
        const jobLocation = app.applied_job_location || app.job_location || "Location not set";
        const email = app.applied_email || seeker.email;
        const phone = app.applied_phone || seeker.phone;
        const skills = seeker.skills || [];
        const resume =
            app.applied_resume_url ||
            app.resume_url ||
            app.resume ||
            seeker.resume_url;
        return {
            name,
            jobTitle,
            jobLocation,
            predictedRole,
            matchScore,
            skills,
            email,
            phone,
            resume,
        };
    }

    function formatMatch(score) {
        if (score == null || score === "") return "N/A";
        const num = Number(score);
        if (Number.isNaN(num)) return String(score);
        return `${num}%`;
    }

    function renderStats(apps) {
        const total = apps.length;
        const interviews = apps.filter((a) => (a.status || "").toLowerCase().includes("interview")).length;
        const hires = apps.filter((a) =>
            (a.status || "").toLowerCase().includes("hire") ||
            (a.status || "").toLowerCase().includes("accept")
        ).length;
        const matches = apps
            .map((a) => parseFloat(applicationSnapshot(a).matchScore))
            .filter((n) => !isNaN(n));
        const avg = matches.length ? Math.round(matches.reduce((a, b) => a + b, 0) / matches.length) : null;

        statTotal.textContent = total || "-";
        statInterviews.textContent = interviews || "-";
        statHires.textContent = hires || "-";
        statAvgMatch.textContent = avg != null ? `${avg}%` : "-";
    }

    function renderApplications() {
        if (!applications.length) {
            listEl.innerHTML = '<p class="panel-placeholder">No applications yet.</p>';
            countEl.textContent = "0 applications";
            renderDetails(null);
            renderStats([]);
            return;
        }

        const search = (filterSearch?.value || "").toLowerCase();
        const role = (filterRole?.value || "").toLowerCase();
        const status = (filterStatus?.value || "").toLowerCase();

        const filtered = applications.filter((app) => {
            const snap = applicationSnapshot(app);
            const text = `${snap.name || ""} ${snap.jobTitle || ""} ${snap.predictedRole || ""}`.toLowerCase();
            const roleMatch = !role || (snap.jobTitle || "").toLowerCase().includes(role);
            const searchMatch = !search || text.includes(search);
            const statusMatch = !status || (app.status || "").toLowerCase().includes(status);
            return roleMatch && searchMatch && statusMatch;
        });

        renderStats(filtered);

        countEl.textContent = `${filtered.length} application${filtered.length === 1 ? "" : "s"}`;
        listEl.innerHTML = "";

        filtered.forEach((app) => {
            const snapshot = applicationSnapshot(app);
            const card = document.createElement("div");
            card.className = "application-card";
            card.addEventListener("click", () => renderDetails(app));

            const main = document.createElement("div");
            main.className = "application-main";
            const title = document.createElement("h3");
            title.textContent = snapshot.name;
            const subtitle = document.createElement("div");
            subtitle.className = "subtitle";
            subtitle.textContent = `${snapshot.jobTitle} | ${snapshot.jobLocation}`;

            const meta = document.createElement("div");
            meta.className = "application-meta";
            const statusPill = document.createElement("span");
            statusPill.className = `status-pill ${statusClass(app.status)}`;
            statusPill.textContent = app.status || "pending";
            const matchPill = document.createElement("span");
            matchPill.className = "pill match-pill";
            const matchVal = formatMatch(snapshot.matchScore);
            matchPill.textContent = `Match ${matchVal}`;
            const rolePill = document.createElement("span");
            rolePill.className = "pill";
            rolePill.textContent = snapshot.predictedRole || "Predicted role n/a";
            const schedPill = document.createElement("span");
            schedPill.className = "pill pill-soft";
            const schedVal = (app.interview && app.interview.scheduled_at) || app.scheduled_at;
            schedPill.textContent = schedVal ? `Interview ${formatDateTime(schedVal)}` : "No date";
            meta.appendChild(statusPill);
            meta.appendChild(matchPill);
            meta.appendChild(rolePill);
            meta.appendChild(schedPill);

            main.appendChild(title);
            main.appendChild(subtitle);
            main.appendChild(meta);

            const actions = document.createElement("div");
            actions.className = "application-actions";

            const statusVal = (app.status || "").toLowerCase();
            const isAccepted = ["interview", "accept", "hire", "offer", "hired"].some((k) => statusVal.includes(k));
            const isRejected = statusVal.includes("reject");

            const viewBtn = document.createElement("button");
            viewBtn.className = "btn btn-secondary";
            viewBtn.textContent = "View";
            viewBtn.addEventListener("click", (e) => {
                e.stopPropagation();
                renderDetails(app);
                openApplicantModal(app);
            });

            const acceptBtn = document.createElement("button");
            acceptBtn.className = "btn btn-primary";
            acceptBtn.textContent = "Accept";
            acceptBtn.addEventListener("click", (e) => {
                e.stopPropagation();
                renderDetails(app);
                if (isAccepted || isRejected) return;
                openScheduleModal(app);
            });

            const rejectBtn = document.createElement("button");
            rejectBtn.className = "btn btn-danger";
            rejectBtn.textContent = "Reject";
            rejectBtn.addEventListener("click", (e) => {
                e.stopPropagation();
                renderDetails(app);
                if (isAccepted || isRejected) return;
                updateStatus(app.id, "rejected");
            });

            if (isAccepted) {
                acceptBtn.textContent = "Accepted";
                acceptBtn.style.backgroundColor = "#10b981";
                acceptBtn.style.borderColor = "#10b981";
                acceptBtn.style.color = "#fff";
                acceptBtn.disabled = true;
                rejectBtn.disabled = true;
                rejectBtn.style.opacity = 0.5;
            } else if (isRejected) {
                rejectBtn.textContent = "Rejected";
                rejectBtn.style.color = "white";
                rejectBtn.style.fontWeight = "600";
                acceptBtn.disabled = true;
                acceptBtn.style.opacity = 0.5;
                rejectBtn.disabled = true;
                rejectBtn.style.opacity = 0.6;
            }

            const resultBtn = document.createElement("button");
            resultBtn.className = "btn btn-primary";
            resultBtn.textContent = "Result";
            resultBtn.addEventListener("click", (e) => {
                e.stopPropagation();
                renderDetails(app);
                openResultModal(app);
            });

            actions.appendChild(viewBtn);
            actions.appendChild(acceptBtn);
            actions.appendChild(rejectBtn);
            actions.appendChild(resultBtn);

            card.appendChild(main);
            card.appendChild(actions);

            listEl.appendChild(card);
        });
    }

    function renderDetails(app) {
        if (!detailCard) {
            return;
        }
        selected.app = app;
        if (!app) {
            detailName.textContent = "Select an application";
            detailJob.textContent = "Applicant details and AI insights will appear here.";
            detailStatus.textContent = "-";
            detailStatus.className = "status-pill muted";
            detailMatch.textContent = "-";
            detailRole.textContent = "-";
            detailInterview.textContent = "-";
            detailApplied.textContent = "-";
            detailScheduled.textContent = "-";
            detailInterviewStatus.textContent = "-";
            detailMeetingLink.textContent = "-";
            detailInterviewNotes.textContent = "-";
            if (scheduleDate) scheduleDate.value = "";
            return;
        }

        const snapshot = applicationSnapshot(app);
        const interview = app.interview || {};
        const scheduledVal = interview.scheduled_at || app.scheduled_at;
        const meetingUrl = interview.meeting_url || app.meeting_url;
        const interviewNotes = interview.feedback || interview.notes;

        detailName.textContent = snapshot.name;
        detailJob.textContent = `${snapshot.jobTitle} | ${snapshot.jobLocation}`;
        detailStatus.textContent = app.status || "pending";
        detailStatus.className = `status-pill ${statusClass(app.status)}`;
        detailMatch.textContent = formatMatch(snapshot.matchScore);
        detailRole.textContent = snapshot.predictedRole || "Not available";
        const interviewScoreVal = interview.rating != null ? `${interview.rating}` : app.interview_score;
        detailInterview.textContent = interviewScoreVal != null ? `${interviewScoreVal}` : "Not set";
        detailApplied.textContent = formatDate(app.applied_at);
        detailScheduled.textContent = formatDateTime(scheduledVal);
        detailInterviewStatus.textContent = interview.status || "-";
        if (meetingUrl) {
            detailMeetingLink.innerHTML = `<a href="${meetingUrl}" target="_blank" rel="noopener">Join meeting</a>`;
        } else {
            detailMeetingLink.textContent = "-";
        }
        detailInterviewNotes.textContent = interviewNotes || "-";
        if (scheduleDate) {
            scheduleDate.value = "";
        }
    }

    async function fetchCompanyProfile() {
        try {
            const res = await fetch(apiUrl("/api/company/profile"), {
                headers: { Authorization: authHeaders.Authorization },
            });
            const data = await res.json().catch(() => ({}));
            if (res.ok && data.company && data.company.id) {
                companyId = data.company.id;
            }
        } catch (err) {
            console.error("Failed to load company profile", err);
        }
    }

    async function fetchApplications() {
        listEl.innerHTML = '<p class="panel-placeholder">Loading applications...</p>';
        try {
            const qs = companyId ? `?company_id=${encodeURIComponent(companyId)}` : "";
            const res = await fetch(apiUrl(`/api/company/applications${qs}`), {
                headers: { Authorization: authHeaders.Authorization },
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                console.error("Failed to load applications:", data);
                listEl.innerHTML = `<p class="panel-placeholder">Unable to load applications. ${data.error || ""}</p>`;
                return;
            }
            applications = data.applications || [];
            renderApplications();
        } catch (err) {
            console.error("Error loading applications:", err);
            listEl.innerHTML = `<p class="panel-placeholder">Unable to load applications.</p>`;
        }
    }

    async function updateStatus(appId, status, interviewScore, scheduleDateVal) {
        if (!appId) return;
        try {
            const payload = { status };
            if (interviewScore != null && interviewScore !== "") {
                payload.interview_score = interviewScore;
            }
            if (scheduleDateVal) {
                payload.schedule_date = scheduleDateVal;
                payload.notes = `Interview scheduled: ${scheduleDateVal}`;
            }
            const res = await fetch(apiUrl(`/api/company/applications/${appId}/status`), {
                method: "PUT",
                headers: authHeaders,
                body: JSON.stringify(payload),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                alert(data.error || data.detail || "Failed to update status");
                return;
            }
            await fetchApplications();
            if (status.toLowerCase().includes("accept") || status.toLowerCase().includes("interview")) {
                alert("Status updated and virtual meeting queued.");
            }
        } catch (err) {
            console.error("Failed to update status:", err);
            alert("Network error while updating application.");
        }
    }

    function openScheduleModal(app) {
        closeModal();
        const overlay = document.createElement("div");
        overlay.className = "modal-overlay";
        const modal = document.createElement("div");
        modal.className = "modal-card";
        modal.style.maxWidth = "780px";
        modal.style.width = "200%";
            modal.innerHTML = `
                <h3>Schedule interview</h3>
                <p style="margin:4px 0 10px 0;">Pick a date/time for this candidate. Saving will move status to interview.</p>
                <label style="font-size:13px;color:#6b7280;margin-bottom:4px;display:block;">Date & Time</label>
            <input type="datetime-local" id="modalScheduleInput" style="width:100%;padding:8px;border:1px solid #e5e7eb;border-radius:8px;margin-bottom:12px;">
            <div style="display:flex;gap:8px;justify-content:flex-end;">
                    <button class="btn btn-ghost" id="modalCancelBtn">Cancel</button>
                    <button class="btn btn-primary" id="modalSaveBtn">Save</button>
                </div>
            `;
        overlay.appendChild(modal);
        document.body.appendChild(overlay);
        modalEl = overlay;

        const scheduleInput = modal.querySelector("#modalScheduleInput");
        if (scheduleInput) {
            const future = new Date();
            const pad = (num) => num.toString().padStart(2, "0");
            const isoLocal = `${future.getFullYear()}-${pad(future.getMonth() + 1)}-${pad(
                future.getDate()
            )}T${pad(future.getHours())}:${pad(future.getMinutes())}`;
            scheduleInput.min = isoLocal;
        }
        modal.querySelector("#modalCancelBtn").addEventListener("click", closeModal);
        modal.querySelector("#modalSaveBtn").addEventListener("click", () => {
            const val = modal.querySelector("#modalScheduleInput").value;
            if (!val) {
                alert("Please pick a date and time.");
                return;
            }
            const selectedDate = new Date(val);
            if (isNaN(selectedDate.getTime())) {
                alert("Invalid date provided.");
                return;
            }
            const now = new Date();
            if (selectedDate < now) {
                alert("The scheduled time must be in the future.");
                return;
            }
            const iso = selectedDate.toISOString();
            closeModal();
            updateStatus(app.id, "interview", undefined, iso);
        });
    }

    function openApplicantModal(app) {
        closeModal();
        const overlay = document.createElement("div");
        overlay.className = "modal-overlay";
        const modal = document.createElement("div");
        modal.className = "modal-card";

        const snapshot = applicationSnapshot(app);
        const skills = snapshot.skills || [];
        const resume = snapshot.resume;

        modal.innerHTML = `
            <h3 style="margin-bottom:6px;">${snapshot.name || "Applicant"}</h3>
            <p style="margin:0 0 10px 0;color:#6b7280;">${snapshot.jobTitle || "Role"} | ${snapshot.jobLocation || ""}</p>
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;margin-bottom:12px;">
                <div><p class="detail-label">Predicted Role</p><p class="detail-value">${snapshot.predictedRole || "N/A"}</p></div>
                <div><p class="detail-label">Match</p><p class="detail-value">${formatMatch(snapshot.matchScore)}</p></div>
                <div><p class="detail-label">Contact</p><p class="detail-value" style="white-space:normal;word-break:break-word;">${snapshot.email || ""}${snapshot.phone ? "<br>" + snapshot.phone : ""}</p></div>
            </div>
            <div style="margin-bottom:10px;">
                <p class="detail-label">Skills</p>
                <div style="display:flex;flex-wrap:wrap;gap:6px;">${
                    skills.length
                        ? skills
                              .map(
                                  (s) =>
                                      `<span class="pill pill-soft">${s.skill_name || s || ""}${s.proficiency_level ? " - " + s.proficiency_level : ""}</span>`
                              )
                              .join("")
                        : '<span class="panel-subtitle">No skills recorded</span>'
                }</div>
            </div>
            <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
                <p class="detail-label" style="margin:0;">Resume</p>
                ${
                    resume
                        ? `<a class="btn btn-secondary" href="${resume}" target="_blank" rel="noopener">Download PDF</a>`
                        : '<span class="panel-subtitle">Not uploaded</span>'
                }
            </div>
            <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:14px;">
                <button class="btn btn-ghost" id="modalCloseApplicant">Close</button>
            </div>
        `;
        overlay.appendChild(modal);
        document.body.appendChild(overlay);
        modalEl = overlay;

        modal.querySelector("#modalCloseApplicant").addEventListener("click", closeModal);
    }

    function openResultModal(app) {
        closeModal();
        const overlay = document.createElement("div");
        overlay.className = "modal-overlay";
        const modal = document.createElement("div");
        modal.className = "modal-card";

        const interview = app.interview || {};
        const status = interview.status || app.status || "pending";
        const sched = interview.scheduled_at || app.scheduled_at;
        const meeting = interview.meeting_url || app.meeting_url;
        const feedback = interview.feedback || interview.notes || "Not submitted yet";
        const rating = interview.rating != null ? `${interview.rating}` : "Not set";

        modal.innerHTML = `
            <h3 style="margin-bottom:8px;">Interview Result</h3>
            <p style="margin:0 0 10px 0;color:#6b7280;">${app.seeker?.full_name || "Candidate"} - ${app.job_title || ""}</p>
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;margin-bottom:12px;">
                <div><p class="detail-label">Status</p><p class="detail-value">${status}</p></div>
                <div><p class="detail-label">Interview Date</p><p class="detail-value">${formatDateTime(sched)}</p></div>
                <div><p class="detail-label">Rating</p><p class="detail-value">${rating}</p></div>
                <div><p class="detail-label">Meeting Link</p><p class="detail-value">${meeting ? `<a href="${meeting}" target="_blank" rel="noopener">Join</a>` : "-"}</p></div>
            </div>
            <div style="margin-bottom:12px;">
                <p class="detail-label">Feedback / Notes</p>
                <p class="panel-subtitle" style="white-space:pre-line;">${feedback}</p>
            </div>
            <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:10px;">
                <button class="btn btn-ghost" id="modalCloseResult">Close</button>
            </div>
        `;
        overlay.appendChild(modal);
        document.body.appendChild(overlay);
        modalEl = overlay;
        modal.querySelector("#modalCloseResult").addEventListener("click", closeModal);
    }

    function closeModal() {
        if (modalEl && modalEl.parentElement) {
            modalEl.parentElement.removeChild(modalEl);
        }
        modalEl = null;
    }

    function handleSchedule(app) {
        if (!app) {
            alert("Select an application first.");
            return;
        }
        const statusVal = (app.status || "").toLowerCase();
        if (!statusVal || !(statusVal.includes("interview") || statusVal.includes("accept"))) {
            alert("Schedule is only available after moving the application to interview.");
            return;
        }
        const dateVal = scheduleDate?.value;
        if (!dateVal) {
            alert("Select a date before scheduling.");
            return;
        }
        const iso = new Date(dateVal).toISOString();
        updateStatus(app.id, "interview", undefined, iso);
    }

    document.getElementById("applyFilters")?.addEventListener("click", renderApplications);
    document.getElementById("clearFilters")?.addEventListener("click", () => {
        if (filterSearch) filterSearch.value = "";
        if (filterRole) filterRole.value = "";
        if (filterStatus) filterStatus.value = "";
        renderApplications();
    });
    document.getElementById("refreshApplications")?.addEventListener("click", fetchApplications);
    document.getElementById("quickRefresh")?.addEventListener("click", fetchApplications);

    if (btnSchedule) {
        btnSchedule.addEventListener("click", () => handleSchedule(selected.app));
    }
    if (btnAccept) {
        btnAccept.addEventListener("click", () => {
            if (!selected.app) return alert("Select an application first.");
            updateStatus(selected.app.id, "accepted");
        });
    }
    if (btnReject) {
        btnReject.addEventListener("click", () => {
            if (!selected.app) return alert("Select an application first.");
            updateStatus(selected.app.id, "rejected");
        });
    }

    (async () => {
        await fetchCompanyProfile();
        await fetchApplications();
    })();
});
