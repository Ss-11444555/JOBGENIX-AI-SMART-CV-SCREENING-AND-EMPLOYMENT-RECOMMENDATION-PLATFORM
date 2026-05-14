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

    const headers = {
        Authorization: "Bearer " + token,
        "Content-Type": "application/json",
    };

    const form = document.getElementById("companySettingsForm");
    const saveBtn = document.getElementById("saveProfileBtn");
    const statusPill = document.getElementById("profileStatus");

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

    function setStatus(text, variant = "primary") {
        if (!statusPill) return;
        statusPill.textContent = text;
        statusPill.className = "status-pill";
        if (variant === "success") {
            statusPill.style.background = "var(--success-50, #ecfdf3)";
            statusPill.style.color = "var(--success-700, #15803d)";
        } else {
            statusPill.removeAttribute("style");
        }
    }

    async function loadProfile() {
        try {
            const res = await fetch(apiUrl("/api/company/profile"), {
                headers: { Authorization: headers.Authorization },
            });
            if (res.status === 401 || res.status === 403) {
                ["authToken", "token", "jobgenix_token"].forEach((k) =>
                    localStorage.removeItem(k)
                );
                window.location.href = "/pages/auth/login.html";
                return;
            }
            const data = await res.json();
            if (!res.ok) {
                console.error("Failed to load company profile:", data);
                return;
            }
            const c = data.company || {};
            form.companyName.value = c.company_name || "";
            form.industry.value = c.industry || "";
            form.companySize.value = c.company_size || "";
            form.website.value = c.website || "";
            form.contactEmail.value = c.contact_email || "";
            form.description.value = c.description || "";
            setStatus("Saved", "success");
        } catch (err) {
            console.error("Profile load error:", err);
        }
    }

    async function saveProfile() {
        setStatus("Saving...");
        saveBtn.disabled = true;
        const payload = {
            company_name: form.companyName.value.trim(),
            industry: form.industry.value.trim(),
            company_size: form.companySize.value,
            website: form.website.value.trim(),
            contact_email: form.contactEmail.value.trim(),
            description: form.description.value.trim(),
        };
        try {
            const res = await fetch(apiUrl("/api/company/profile"), {
                method: "PUT",
                headers,
                body: JSON.stringify(payload),
            });
            const data = await res.json();
            if (!res.ok) {
                alert(data.error || "Failed to update company profile");
                console.error("Save error:", data);
                setStatus("Error");
                return;
            }
            setStatus("Saved", "success");
        } catch (err) {
            console.error("Save profile error:", err);
            alert("Network error while updating profile.");
            setStatus("Error");
        } finally {
            saveBtn.disabled = false;
        }
    }

    saveBtn?.addEventListener("click", (e) => {
        e.preventDefault();
        saveProfile();
    });

    loadProfile();
});
