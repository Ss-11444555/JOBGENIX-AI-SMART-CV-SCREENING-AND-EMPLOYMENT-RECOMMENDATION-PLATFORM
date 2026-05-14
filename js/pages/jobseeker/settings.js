// js/pages/jobseeker/settings.js
(function () {
    const API_BASE = (window.JobGenixApp && window.JobGenixApp.apiBase) || "http://localhost:8000/api";
    const token = localStorage.getItem("authToken") || localStorage.getItem("token") || localStorage.getItem("jobgenix_token");

    const firstNameInput = document.getElementById('firstName');
    const lastNameInput = document.getElementById('lastName');
    const emailInput = document.getElementById('email');
    const phoneInput = document.getElementById('phone');
    const headlineInput = document.getElementById('headline');
    const aboutInput = document.getElementById('about');
    const locationInput = document.getElementById('location');
    const experienceSelect = document.getElementById('experience');
    const saveBtn = document.getElementById('saveBtn');
    const cancelBtn = document.getElementById('cancelBtn');
    const statusMsg = document.getElementById('statusMsg');

    let originalProfile = null;

    if (!token) {
        window.location.href = '/pages/auth/login.html';
        return;
    }

    function setStatus(msg, isError = false) {
        if (!statusMsg) return;
        statusMsg.textContent = msg || '';
        statusMsg.style.color = isError ? '#dc2626' : '#6b7280';
    }

    function fillForm(profile) {
        if (!profile) return;
        originalProfile = profile;
        const fullName = profile.full_name || '';
        const parts = fullName.split(' ');
        firstNameInput.value = parts.slice(0, -1).join(' ') || fullName || '';
        lastNameInput.value = parts.length > 1 ? parts.slice(-1).join(' ') : '';
        emailInput.value = profile.email || '';
        phoneInput.value = profile.phone || '';
        headlineInput.value = profile.current_title || '';
        aboutInput.value = profile.bio || '';
        locationInput.value = profile.location || '';
        experienceSelect.value = profile.experience_level || '';
    }

    async function loadProfile() {
        try {
            setStatus('Loading profile...');
            const res = await fetch(`${API_BASE}/job-seeker/profile`, {
                headers: { "Authorization": "Bearer " + token }
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok || data.error) {
                setStatus(data.error || 'Unable to load profile.', true);
                return;
            }
            fillForm(data.profile || {});
            setStatus('');
        } catch (e) {
            setStatus('Network error loading profile.', true);
        }
    }

    function collectPayload() {
        const fn = firstNameInput.value.trim();
        const ln = lastNameInput.value.trim();
        return {
            full_name: [fn, ln].filter(Boolean).join(' ').trim() || fn || ln,
            phone: phoneInput.value.trim(),
            current_title: headlineInput.value.trim(),
            bio: aboutInput.value.trim(),
            location: locationInput.value.trim(),
            experience_level: experienceSelect.value || null
        };
    }

    async function saveProfile(e) {
        e?.preventDefault();
        const payload = collectPayload();
        try {
            saveBtn.disabled = true;
            setStatus('Saving...');
            const res = await fetch(`${API_BASE}/job-seeker/profile`, {
                method: 'PUT',
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": "Bearer " + token
                },
                body: JSON.stringify(payload)
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok || data.error) {
                setStatus(data.error || 'Unable to save profile.', true);
                saveBtn.disabled = false;
                return;
            }
            setStatus('Saved successfully.');
            await loadProfile();
        } catch (err) {
            setStatus('Network error saving profile.', true);
        } finally {
            saveBtn.disabled = false;
        }
    }

    function resetForm() {
        fillForm(originalProfile);
        setStatus('');
    }

    document.addEventListener('DOMContentLoaded', () => {
        loadProfile();
        saveBtn?.addEventListener('click', saveProfile);
        cancelBtn?.addEventListener('click', (e) => {
            e.preventDefault();
            resetForm();
        });
    });
})();
