// js/pages/jobseeker/mock-interview.js
(function () {
    let api = null;

    const joinBtn = document.getElementById('joinBtn');
    const joinBtnText = document.getElementById('joinBtnText');
    const countdownEl = document.getElementById('countdownTimer');
    const companyNameEl = document.getElementById('companyName');
    const jobTitleEl = document.getElementById('jobTitle');
    const scheduledAtEl = document.getElementById('scheduledAt');
    const matchScoreEl = document.getElementById('matchScore');
    const interviewScoreEl = document.getElementById('interviewScore');
    const statusEl = document.getElementById('sessionStatus');
    const sessionTitleEl = document.getElementById('sessionTitle');
    const sessionSubtitleEl = document.getElementById('sessionSubtitle');
    const timelineScheduleEl = document.getElementById('timelineSchedule');
    const scheduleTag = document.getElementById('scheduleTag');
    const statusTag = document.getElementById('statusTag');
    const roleTag = document.getElementById('predictedRoleTag');
    const prepRole = document.getElementById('prepRole');
    const calendarBtn = document.getElementById('calendarBtn');
    const apiStatusEl = document.getElementById('apiStatus');
    const listEl = document.getElementById('interviewList');
    const listStatusEl = document.getElementById('listStatus');
    const modal = document.getElementById('startModal');
    const modalBackdrop = document.getElementById('modalBackdrop');
    const modalClose = document.getElementById('modalClose');
    const modalCancel = document.getElementById('modalCancel');
    const modalStartBtn = document.getElementById('modalStartBtn');
    const modalTitle = document.getElementById('modalTitle');
    const modalSubtitle = document.getElementById('modalSubtitle');
    const modalCompany = document.getElementById('modalCompany');
    const modalRole = document.getElementById('modalRole');
    const modalDate = document.getElementById('modalDate');
    const modalStatus = document.getElementById('modalStatus');
    const modalMatch = document.getElementById('modalMatch');
    const modalScore = document.getElementById('modalScore');
    const modalNote = document.getElementById('modalNote');

    let activeInterview = null;
    let selectedInterview = null;
    let countdownTimer = null;

    const pad = (v) => String(v).padStart(2, '0');

    function formatDate(val) {
        if (!val) return '-';
        try {
            const d = new Date(val);
            return d.toLocaleString(undefined, {
                month: 'short',
                day: 'numeric',
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });
        } catch (e) {
            return val;
        }
    }

    function formatCountdown(targetDate) {
        if (!targetDate) return '--:--:--';
        const diff = targetDate - new Date();
        if (diff <= 0) return '00:00:00';
        const h = Math.floor(diff / 1000 / 3600);
        const m = Math.floor((diff / 1000 % 3600) / 60);
        const s = Math.floor(diff / 1000 % 60);
        return `${pad(h)}:${pad(m)}:${pad(s)}`;
    }

    function setCountdown(targetDate) {
        if (countdownTimer) clearInterval(countdownTimer);
        if (!targetDate) {
            countdownEl.textContent = '--:--:--';
            return;
        }
        const target = typeof targetDate === 'string' ? new Date(targetDate) : targetDate;
        countdownEl.textContent = formatCountdown(target);
        countdownTimer = setInterval(() => {
            countdownEl.textContent = formatCountdown(target);
        }, 1000);
    }

    function getScheduled(item) {
        if (!item) return null;
        return item.scheduled_at || item.applied_at || null;
    }

    function isCompleted(item) {
        const st = (item?.interview_status || item?.status || '').toLowerCase();
        if (st.includes('completed') || st.includes('done')) return true;
        // Treat a rating plus non-empty status as completed fallback
        if (item?.interview_score != null && st && !st.includes('interview')) return true;
        return false;
    }

    function isJoinable(item) {
        if (isCompleted(item)) return false;
        const scheduled = getScheduled(item) ? new Date(getScheduled(item)) : null;
        if (!scheduled) return false;
        return new Date() >= scheduled;
    }

    function openModal(target) {
        if (!modal || !target) return;
        selectedInterview = target;
        activeInterview = target;
        modalTitle.textContent = target.job_title || 'Mock interview';
        modalSubtitle.textContent = target.company ? `With ${target.company}` : '';
        modalCompany.textContent = target.company || '-';
        modalRole.textContent = target.job_title || '-';
        modalDate.textContent = formatDate(getScheduled(target));
        modalStatus.textContent = target.status || 'accepted';
        modalMatch.textContent = target.match_score != null ? `${target.match_score}%` : 'N/A';
        modalScore.textContent = target.interview_score != null ? target.interview_score : '-';
        const completed = isCompleted(target);
        const joinable = isJoinable(target);
        modalStartBtn.disabled = !joinable || completed;
        modalNote.textContent = completed
            ? 'Interview completed.'
            : joinable
                ? 'Room is unlocked. Start will open in a new tab.'
                : 'Start unlocks at the company scheduled date/time.';
        modal.classList.add('active');
        modal.setAttribute('aria-hidden', 'false');
    }

    function closeModal() {
        if (!modal) return;
        modal.classList.remove('active');
        modal.setAttribute('aria-hidden', 'true');
    }

    function updateUI(data) {
        const interviews = data?.interviews || [];
        const predictedRole = data?.predicted_role || '-';

        if (roleTag) roleTag.textContent = `Predicted role: ${predictedRole}`;
        if (prepRole) prepRole.textContent = `Predicted role: ${predictedRole}`;
        if (scheduleTag) scheduleTag.textContent = 'Schedule: -';
        if (statusTag) statusTag.textContent = 'Status: -';

        if (!interviews.length) {
            sessionTitleEl.textContent = 'No upcoming mock interview yet';
            sessionSubtitleEl.textContent = 'Accepted and scheduled virtual meetings will appear here.';
            joinBtn.disabled = true;
            joinBtnText.textContent = 'Waiting for schedule';
            setCountdown(null);
            apiStatusEl.textContent = 'No accepted/scheduled applications yet. Once your application is accepted and scheduled, the room will appear.';
            companyNameEl.textContent = '-';
            jobTitleEl.textContent = '-';
            scheduledAtEl.textContent = '-';
            matchScoreEl.textContent = '-';
            statusEl.textContent = '-';
            interviewScoreEl.textContent = '-';
            renderList([]);
            if (listStatusEl) listStatusEl.textContent = 'No accepted/scheduled applications yet.';
            return;
        }

        const sorted = [...interviews].sort((a, b) => {
            const sa = getScheduled(a) ? new Date(getScheduled(a)).getTime() : Infinity;
            const sb = getScheduled(b) ? new Date(getScheduled(b)).getTime() : Infinity;
            return sa - sb;
        });
        activeInterview = sorted[0];

        const scheduledVal = getScheduled(activeInterview);
        const scheduledDate = scheduledVal ? new Date(scheduledVal) : null;
        const matchScore = activeInterview.match_score != null ? `${activeInterview.match_score}%` : 'N/A';
        const completed = isCompleted(activeInterview);
        const interviewScore = activeInterview.interview_score != null ? activeInterview.interview_score : '-';

        sessionTitleEl.textContent = activeInterview.job_title || 'Upcoming mock interview';
        sessionSubtitleEl.textContent = activeInterview.company ? `With ${activeInterview.company}` : 'Virtual mock interview';
        companyNameEl.textContent = activeInterview.company || '-';
        jobTitleEl.textContent = activeInterview.job_title || '-';
        scheduledAtEl.textContent = formatDate(scheduledVal);
        matchScoreEl.textContent = matchScore;
        statusEl.textContent = activeInterview.status || 'accepted';
        interviewScoreEl.textContent = interviewScore;
        timelineScheduleEl.textContent = scheduledVal ? formatDate(scheduledVal) : 'Awaiting schedule';

        if (statusTag) statusTag.textContent = `Status: ${activeInterview.status || '-'}`;
        if (scheduleTag) scheduleTag.textContent = `Schedule: ${scheduledVal ? formatDate(scheduledVal) : '-'}`;

        setCountdown(scheduledDate);
        const allowJoin = isJoinable(activeInterview);

        apiStatusEl.textContent = completed
            ? 'Interview completed.'
            : allowJoin
                ? 'You can start the interview now. We open the room in a new tab.'
                : 'Start unlocks at the scheduled time set by the company.';
        joinBtn.disabled = completed ? true : false;
        joinBtnText.textContent = completed ? 'Completed' : allowJoin ? 'Start interview' : 'View details';

        renderList(interviews);
        if (listStatusEl) listStatusEl.textContent = '';
    }

    async function loadData() {
        if (!api) api = window.JobGenixApp;
        if (!api) {
            console.error('JobGenixApp not available');
            return;
        }
        try {
            const res = await api.getRequest('/job-seeker/mock-interviews');
            if (!res || res.error) {
                apiStatusEl.textContent = res?.error || 'Unable to load mock interviews.';
                if (listStatusEl) listStatusEl.textContent = res?.error || 'Unable to load accepted applications.';
                return;
            }
            apiStatusEl.textContent = 'Session data synced.';
            updateUI(res);
        } catch (err) {
            console.error('Failed to load mock interviews', err);
            apiStatusEl.textContent = 'Unable to load session info. Please retry.';
            if (listStatusEl) listStatusEl.textContent = 'Unable to load accepted applications.';
        }
    }

    async function startMeeting() {
        const target = selectedInterview || activeInterview;
        if (!api) api = window.JobGenixApp;
        if (!api) return;
        if (!target) return;
        try {
            modalStartBtn.disabled = true;
            joinBtnText.textContent = 'Connecting...';
            sessionStorage.setItem(
                `mock_session_${target.application_id}`,
                JSON.stringify({
                    application_id: target.application_id,
                    job_title: target.job_title,
                    company: target.company,
                    scheduled_at: target.scheduled_at || target.applied_at,
                    applied_at: target.applied_at,
                    status: target.status,
                    match_score: target.match_score,
                    meeting_url: target.meeting_url
                })
            );
            window.open(`/pages/jobseeker/mock-interview-room.html?application_id=${target.application_id}`, '_blank');
        } catch (err) {
            console.error('Unable to start meeting', err);
            api.showAlert?.(err?.detail || 'Unable to open interview room', 'error');
        } finally {
            modalStartBtn.disabled = false;
            joinBtnText.textContent = 'Start interview';
            closeModal();
        }
    }

    function buildIcs() {
        const target = selectedInterview || activeInterview;
        const schedVal = getScheduled(target);
        if (!target || !schedVal) {
            api.showAlert?.('Schedule not set yet.', 'info');
            return;
        }
        const start = new Date(schedVal);
        const end = new Date(start.getTime() + 45 * 60 * 1000);
        const toIso = (d) => d.toISOString().replace(/[-:]/g, '').split('.')[0] + 'Z';
        const ics = [
            'BEGIN:VCALENDAR',
            'VERSION:2.0',
            'BEGIN:VEVENT',
            `DTSTART:${toIso(start)}`,
            `DTEND:${toIso(end)}`,
            `SUMMARY:Mock Interview - ${target.job_title || 'Role'}`,
            'DESCRIPTION:Virtual mock interview aligned to your predicted role',
            'END:VEVENT',
            'END:VCALENDAR'
        ].join('\n');

        const blob = new Blob([ics], { type: 'text/calendar' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'mock-interview.ics';
        a.click();
        setTimeout(() => URL.revokeObjectURL(url), 500);
    }

    function ensureAuth() {
        if (!api) api = window.JobGenixApp;
        const token = api?.getToken ? api.getToken() : localStorage.getItem('token');
        if (!token) {
            window.location.href = '/pages/auth/login.html';
        }
    }

    function renderList(items) {
        if (!listEl || !listStatusEl) return;
        if (!items.length) {
            listEl.innerHTML = '';
            listStatusEl.textContent = 'No accepted/scheduled applications yet.';
            return;
        }
        listStatusEl.textContent = '';
        listEl.innerHTML = items
            .map((item) => {
                const scheduledVal = getScheduled(item);
                const scheduled = scheduledVal ? formatDate(scheduledVal) : 'No date set';
        const status = item.status || 'accepted';
        const completed = isCompleted(item);
        const match = item.match_score != null ? `${item.match_score}%` : 'N/A';
        const joinable = isJoinable(item);
        const badge = completed ? 'Completed' : joinable ? 'Room unlocked' : 'Locked until scheduled time';
        return `
        <div class="interview-card">
            <div class="interview-main">
                <h4>${item.job_title || 'Role'}</h4>
                <div class="meta">
                            <span class="pill pill-soft small">${item.company || 'Company'}</span>
                            <span class="pill pill-soft small">${scheduled}</span>
                            <span class="pill pill-soft small">Match ${match}</span>
                        </div>
                    </div>
                    <div class="interview-meta">
                        <div class="meta-line"><strong>Scheduled:</strong> ${scheduled}</div>
                        <div class="meta-line"><strong>Status:</strong> ${completed ? 'Completed' : status}</div>
                        <div class="meta-line"><strong>Start:</strong> ${badge}</div>
            </div>
            <div class="interview-actions">
                        <button class="btn primary" data-app="${item.application_id}" ${completed ? 'disabled' : (joinable ? '' : 'disabled')}>
                            ${completed ? 'Completed' : joinable ? 'Start interview' : 'View details'}
                        </button>
            </div>
        </div>
    `;
            })
            .join('');

        listEl.querySelectorAll('button[data-app]').forEach((btn) => {
            btn.addEventListener('click', () => {
                const appId = btn.getAttribute('data-app');
                const target = items.find((i) => String(i.application_id) === String(appId));
                if (target) {
                    selectedInterview = target;
                    startMeeting();
                }
            });
        });
    }

    function handleJoinClick() {
        if (!activeInterview) return;
        if (isCompleted(activeInterview)) {
            api.showAlert?.('Interview already completed.', 'info');
            return;
        }
        startMeeting();
    }

    document.addEventListener('DOMContentLoaded', () => {
        api = window.JobGenixApp;
        ensureAuth();
        loadData();
        joinBtn?.addEventListener('click', handleJoinClick);
        calendarBtn?.addEventListener('click', buildIcs);
        modalClose?.addEventListener('click', closeModal);
        modalCancel?.addEventListener('click', closeModal);
        modalBackdrop?.addEventListener('click', closeModal);
        modalStartBtn?.addEventListener('click', startMeeting);
    });
})();
