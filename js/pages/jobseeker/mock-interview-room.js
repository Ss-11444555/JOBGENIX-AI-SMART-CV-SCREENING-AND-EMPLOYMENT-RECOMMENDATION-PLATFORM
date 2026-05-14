// js/pages/jobseeker/mock-interview-room.js
(function () {
    const TOTAL_QUESTIONS = 5;
    let api = null;
    let apiBase = null;
    let authToken = null;
    let recorder = null;
    let chunks = [];
    let recognition = null;
    let currentQuestionIndex = 0;
    let currentQuestionNumber = 0;
    let questions = [];
    let appId = null;
    let sessionCtx = null;
    let levelInterval = null;
    let elapsedInterval = null;
    let startTs = null;
    let synthUtterance = null;
    let recordTimeout = null;
    let answers = [];
    let lastTtsUrl = null;
    let lastFeedbackTtsUrl = null;
    let isSending = false;
    let recordCountdown = null;
    const MAX_RECORD_MS = 20000;
    // allow play and record concurrently per user request
    

    const roomCompany = document.getElementById('roomCompany');
    const roomRole = document.getElementById('roomRole');
    const roomTime = document.getElementById('roomTime');
    const roomTitle = document.getElementById('roomTitle');
    const roomSubtitle = document.getElementById('roomSubtitle');
    const roomStatus = document.getElementById('roomStatus');
    const questionList = document.getElementById('questionList');
    const transcriptBox = document.getElementById('transcriptBox');
    const micHint = document.getElementById('micHint');
    const playQuestionBtn = document.getElementById('playQuestionBtn');
    const recordBtn = document.getElementById('recordBtn');
    const stopBtn = document.getElementById('stopBtn');
    const nextBtn = document.getElementById('nextBtn');
    const levelMeter = document.getElementById('levelMeter');
    const questionCounter = document.getElementById('questionCounter');
    const tlApplication = document.getElementById('tlApplication');
    const tlScheduled = document.getElementById('tlScheduled');
    const tlMeeting = document.getElementById('tlMeeting');
    const tlStatus = document.getElementById('tlStatus');
    const elapsedEl = document.getElementById('elapsed');
    const aiVoice = document.getElementById('aiVoice');
    const autoStatusText = document.getElementById('autoStatusText');
    const autoStage = document.getElementById('autoStage');
    const autoTimer = document.getElementById('autoTimer');
    const autoProgress = document.getElementById('autoProgress');

    function qs(name) {
        const params = new URLSearchParams(window.location.search);
        return params.get(name);
    }

    function getStoredSession(appId) {
        try {
            const raw = sessionStorage.getItem(`mock_session_${appId}`);
            if (raw) return JSON.parse(raw);
        } catch (e) {
            console.warn('Failed to read session cache', e);
        }
        return null;
    }

    function fmtDate(val) {
        if (!val) return '-';
        try {
            const d = new Date(val);
            return d.toLocaleString(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' });
        } catch (e) {
            return val;
        }
    }

    function pad(n) { return String(n).padStart(2, '0'); }

    function setAutoStatus(stage, text) {
        if (autoStage) autoStage.textContent = stage || '';
        if (autoStatusText) autoStatusText.textContent = text || '';
    }

    function setAutoTimer(ms) {
        if (!autoTimer) return;
        const s = Math.max(0, Math.floor(ms / 1000));
        const mm = String(Math.floor(s / 60)).padStart(2, '0');
        const ss = String(s % 60).padStart(2, '0');
        autoTimer.textContent = `${mm}:${ss}`;
    }

    function setAutoProgress(percent) {
        if (autoProgress) autoProgress.style.width = `${Math.min(100, Math.max(0, percent))}%`;
    }

    function startElapsed() {
        startTs = Date.now();
        if (elapsedInterval) clearInterval(elapsedInterval);
        elapsedInterval = setInterval(() => {
            const diff = Date.now() - startTs;
            const m = Math.floor(diff / 60000);
            const s = Math.floor((diff % 60000) / 1000);
            elapsedEl.textContent = `${pad(m)}:${pad(s)}`;
        }, 1000);
    }

    function stopElapsed() {
        if (elapsedInterval) clearInterval(elapsedInterval);
    }

    function setQuestions(list) {
        questions = list && list.length ? list.slice(0, 5) : [];
        renderQuestions();
    }

    function renderQuestions() {
        if (!questions.length) {
            questionList.innerHTML = '<div class="muted">Questions will appear in your virtual meeting.</div>';
            questionCounter.textContent = 'No questions loaded';
            nextBtn.disabled = true;
            if (playQuestionBtn) playQuestionBtn.disabled = true;
            return;
        }
        if (playQuestionBtn) playQuestionBtn.disabled = false;
        questionList.innerHTML = questions.map((q, idx) => {
            const clean = q.replace(/\*\*Question\s*\d+\/5:\*\*\s*/i, '');
            return `
            <div class="question ${idx === currentQuestionIndex ? 'active' : ''}">
                <strong>Q${idx + 1}</strong> ${clean}
            </div>`;
        }).join('');
        questionCounter.textContent = `Question ${currentQuestionIndex + 1} of ${TOTAL_QUESTIONS}`;
    }

    function appendTranscript(text) {
        const line = document.createElement('div');
        line.textContent = text;
        transcriptBox.appendChild(line);
        transcriptBox.scrollTop = transcriptBox.scrollHeight;
    }

    function setStatus(text) {
        roomStatus.textContent = text;
    }

    function setLevel(val) {
        levelMeter.style.width = `${Math.min(100, Math.max(0, val))}%`;
    }

    async function fetchMeeting(appId) {
        if (!api) return;
        try {
            const res = await api.postRequest('/job-seeker/mock-interviews/start', { application_id: appId });
            if (res?.meeting_url) {
                tlMeeting.href = res.meeting_url;
            }
        } catch (e) {
            console.warn('Start endpoint failed', e);
        }
    }

    function initRecognition() {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognition) {
            micHint.textContent = 'Speech recognition not supported in this browser.';
            recordBtn.disabled = true;
            return;
        }
        recognition = new SpeechRecognition();
        recognition.lang = 'en-US';
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.onresult = (event) => {
            let transcript = '';
            for (let i = event.resultIndex; i < event.results.length; i++) {
                transcript += event.results[i][0].transcript;
            }
            transcriptBox.lastChild ? transcriptBox.lastChild.textContent = transcript : appendTranscript(transcript);
        };
        recognition.onerror = () => {
            setStatus('Mic error');
            recordBtn.disabled = false;
            stopBtn.disabled = true;
        };
    }

    async function startSession(appIdVal) {
        if (!apiBase || !authToken) return;
        try {
            setStatus('Syncing session');
            const res = await fetch(`${apiBase}/job-seeker/mock-interviews/session`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${authToken}`
                },
                body: JSON.stringify({ application_id: appIdVal })
            });
            const data = await res.json();
            if (!res.ok || data.error) throw new Error(data.error || 'Failed to start session');
            const firstQ = data.question || 'Question loading, please try Play.';
            const qNum = data.question_number || 1;
            const placeholder = 'Previous question';
            questions = new Array(qNum > 0 ? qNum : 1).fill(placeholder);
            questions[questions.length - 1] = firstQ;
            currentQuestionIndex = Math.max(0, qNum - 1);
            currentQuestionNumber = qNum;
            lastTtsUrl = data.tts_url || null;
            lastFeedbackTtsUrl = data.feedback_tts_url || null;
            roomRole.textContent = data.role || roomRole.textContent;
            renderQuestions();
            setStatus('Ready');
            recordBtn.disabled = true;
            setAutoStatus('Question', 'Listening to the AI question...');
            playQuestionAudio(lastTtsUrl);
        } catch (err) {
            console.warn('Session start failed', err);
            setStatus('Session unavailable: ' + (err.message || 'Unable to start interview session'));
            micHint.textContent = 'Unable to start interview session. Check OpenAI key/server and retry.';
            recordBtn.disabled = true;
            stopBtn.disabled = true;
            setAutoStatus('Error', 'Unable to start interview session.');
        }
    }

    async function startRecording() {
        if (!navigator.mediaDevices?.getUserMedia) {
            micHint.textContent = 'Microphone not available.';
            return;
        }
        setAutoStatus('Answer', 'Answer now. Recording in progress.');
        micHint.textContent = 'Answer now — recording...';
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        recorder = new MediaRecorder(stream);
        chunks = [];
        recorder.ondataavailable = (e) => chunks.push(e.data);
        recorder.onstop = async () => {
            const blob = new Blob(chunks, { type: 'audio/webm' });
            stream.getTracks().forEach(t => t.stop());
            await sendAnswer(blob);
        };
        recorder.start();
        setStatus('Recording (20s max)');
        recordBtn.disabled = true; // manual controls hidden but keep disabled
        stopBtn.disabled = true;
        micHint.textContent = 'Listening... recording will auto-stop at 20s.';
        startElapsed();
        if (recordTimeout) clearTimeout(recordTimeout);
        recordTimeout = setTimeout(() => {
            stopRecording();
        }, MAX_RECORD_MS);
        if (recognition) recognition.start();

        const startedAt = Date.now();
        if (recordCountdown) clearInterval(recordCountdown);
        recordCountdown = setInterval(() => {
            const diff = Date.now() - startedAt;
            setAutoTimer(MAX_RECORD_MS - diff);
            setAutoProgress((diff / MAX_RECORD_MS) * 100);
            if (diff >= MAX_RECORD_MS) {
                clearInterval(recordCountdown);
            }
        }, 120);

        const ctx = new AudioContext();
        const source = ctx.createMediaStreamSource(stream);
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 256;
        source.connect(analyser);
        const dataArray = new Uint8Array(analyser.frequencyBinCount);
        levelInterval = setInterval(() => {
            analyser.getByteFrequencyData(dataArray);
            const value = dataArray.reduce((a, b) => a + b, 0) / dataArray.length;
            setLevel(value / 2);
        }, 120);
    }

    async function stopRecording() {
        if (recorder && recorder.state !== 'inactive') recorder.stop();
        if (recognition) recognition.stop();
        if (levelInterval) clearInterval(levelInterval);
        if (recordTimeout) clearTimeout(recordTimeout);
        if (recordCountdown) clearInterval(recordCountdown);
        stopElapsed();
        setLevel(0);
        setAutoProgress(0);
        setAutoTimer(0);
        setStatus('Stopped');
        recordBtn.disabled = false;
        stopBtn.disabled = true;
        nextBtn.disabled = true;
        micHint.textContent = 'Processing answer...';
    }

    async function sendAnswer(blob) {
        if (isSending) return;
        isSending = true;
        try {
            setAutoStatus('Processing', 'Processing your answer...');
            setAutoProgress(25);
            // block record while sending
            recordBtn.disabled = true;

            const fd = new FormData();
            fd.append('audio', blob, 'answer.webm');
            fd.append('application_id', appId);
            fd.append('question_number', currentQuestionNumber || currentQuestionIndex + 1);

            const res = await fetch(`${apiBase}/job-seeker/mock-interviews/respond`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${authToken}`
                },
                body: fd
            });
            const data = await res.json();
            if (!res.ok || data.error) throw new Error(data.error || 'Answer failed');

            const transcript = data.transcript || '';
            const feedback = data.feedback || 'Captured.';
            if (transcript) {
                appendTranscript(`[You] ${transcript}`);
            }
            appendTranscript(`[Feedback] ${feedback}`);
            micHint.textContent = feedback;
            lastFeedbackTtsUrl = data.feedback_tts_url || null;

            if (data.done) {
                setStatus('Interview complete');
                setAutoStatus('Complete', 'Interview complete. Thank you.');
                setAutoProgress(100);
                recordBtn.disabled = true;
                stopBtn.disabled = true;
                nextBtn.disabled = true;
                return;
            }

            if (data.next_question) {
                const nextIdx = currentQuestionIndex + 1;
                questions[nextIdx] = data.next_question;
                currentQuestionIndex = nextIdx;
                currentQuestionNumber = data.next_question_number || (currentQuestionNumber + 1);
                lastTtsUrl = data.tts_url || null;
                lastFeedbackTtsUrl = data.feedback_tts_url || null;
                renderQuestions();
                transcriptBox.innerHTML = '';
                setStatus('Ready');
                micHint.textContent = 'Next question is coming. Listen for the prompt.';
                setAutoProgress(0);
                playQuestionAudio(lastTtsUrl);
            } else {
                // No next question returned; keep state but disable next
                nextBtn.disabled = true;
            }
        } catch (err) {
            console.warn('Answer send failed', err);
            micHint.textContent = err.message || 'Unable to process answer.';
            setStatus('Error');
            setAutoStatus('Error', 'Unable to process answer.');
            setAutoProgress(0);
        } finally {
            isSending = false;
            recordBtn.disabled = false;
        }
    }

    function nextQuestion() {
        // Manual advance is disabled in audio-native flow; keep for fallback
        currentQuestionIndex = Math.min(currentQuestionIndex + 1, questions.length - 1);
        currentQuestionNumber = currentQuestionIndex + 1;
        renderQuestions();
        transcriptBox.innerHTML = '';
        setStatus('Ready');
        micHint.textContent = 'Click Record to continue.';
    }

    function playAnyAudio(_fbUrl, qUrl) {
        // Playback flow replaced by auto voice flow
    }

    function playQuestionAudio(url) {
        setAutoProgress(0);
        setAutoTimer(0);
        setAutoStatus('Question', 'Listening to the AI question...');
        if (!url || !aiVoice) {
            setAutoStatus('Answer', 'Audio unavailable. Please answer now.');
            startRecording();
            return;
        }
        aiVoice.onended = () => {
            setAutoProgress(100);
            setTimeout(() => startRecording(), 150);
        };
        aiVoice.onerror = () => {
            setAutoStatus('Answer', 'Audio blocked. Please answer now.');
            startRecording();
        };
        aiVoice.src = url;
        aiVoice.load();
        aiVoice.play().catch(() => {
            setAutoStatus('Answer', 'Autoplay blocked. Please answer now.');
            setTimeout(() => startRecording(), 400);
        });
    }
    function hydrateSession(appId) {
        sessionCtx = getStoredSession(appId) || {};
        roomCompany.textContent = sessionCtx.company || 'Company';
        roomRole.textContent = sessionCtx.job_title || 'Role';
        roomTitle.textContent = sessionCtx.job_title || 'Mock Interview';
        roomSubtitle.textContent = sessionCtx.company ? `With ${sessionCtx.company}` : 'Virtual mock interview';
        roomTime.textContent = fmtDate(sessionCtx.scheduled_at || sessionCtx.applied_at);
        tlApplication.textContent = sessionCtx.application_id || appId;
        tlScheduled.textContent = fmtDate(sessionCtx.scheduled_at || sessionCtx.applied_at);
        tlStatus.textContent = sessionCtx.status || 'interview';
        if (sessionCtx.meeting_url) {
            tlMeeting.href = sessionCtx.meeting_url;
        }
    }

    function ensureAuth() {
        api = window.JobGenixApp;
        apiBase = api?.apiBase || 'http://localhost:8000/api';
        const token = api?.getToken ? api.getToken() : localStorage.getItem('token');
        if (!token) {
            window.location.href = '/pages/auth/login.html';
            return;
        }
        authToken = token;
    }

    document.addEventListener('DOMContentLoaded', async () => {
        setAutoStatus('Syncing', 'Preparing your interview session...');
        ensureAuth();
        appId = qs('application_id');
        hydrateSession(appId);
        initRecognition();
        await startSession(appId);
        fetchMeeting(appId);

        recordBtn?.addEventListener('click', startRecording);
        stopBtn?.addEventListener('click', stopRecording);
        nextBtn?.addEventListener('click', nextQuestion);
    });
})();
