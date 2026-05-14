document.addEventListener("DOMContentLoaded", () => {
    console.debug("[sidebar] init");
    const sidebar = document.querySelector(".sidebar-company");
    const main = document.getElementById("main-content");
    const menuBtn = document.querySelector(".menu-button");
    const logoutBtn = document.getElementById("companyLogoutBtn");

    const openSidebar = () => {
        if (!sidebar || !main || !menuBtn) return;
        sidebar.classList.add("open");
        main.classList.add("pushed");
        menuBtn.setAttribute("aria-expanded", "true");
    };

    const closeSidebar = () => {
        if (!sidebar || !main || !menuBtn) return;
        sidebar.classList.remove("open");
        main.classList.remove("pushed");
        menuBtn.setAttribute("aria-expanded", "false");
    };

    const toggleSidebar = () => {
        if (!sidebar || !main || !menuBtn) return;
        if (sidebar.classList.contains("open")) {
            closeSidebar();
        } else {
            openSidebar();
        }
    };

    // Sidebar only if elements exist
    if (sidebar && main && menuBtn) {
        if (window.innerWidth >= 1024) {
            openSidebar();
        } else {
            closeSidebar();
        }

        menuBtn.addEventListener("click", (e) => {
            e.preventDefault();
            toggleSidebar();
        });

        document.addEventListener("click", (e) => {
            if (
                window.innerWidth < 1024 &&
                sidebar.classList.contains("open") &&
                !e.target.closest(".sidebar-company") &&
                !e.target.closest(".menu-button")
            ) {
                closeSidebar();
            }
        });

        window.addEventListener("resize", () => {
            if (window.innerWidth >= 1024) {
                openSidebar();
            } else {
                closeSidebar();
            }
        });
    }

    // Enforce logout via confirmation modal only
    const existingOverlay = () => document.querySelector(".logout-overlay");
    const clearSession = () => {
        const keys = ["auth_token", "authToken", "token", "jobgenix_token", "user", "user_type"];
        keys.forEach((k) => localStorage.removeItem(k));
    };
    const performLogout = () => {
        try {
            const base = window.API_BASE_URL || "http://localhost:8000";
            fetch(`${base}/api/auth/logout`, { method: "POST" }).finally(() => {
                clearSession();
                window.location.href = "/pages/auth/login.html";
            });
        } catch (_) {
            clearSession();
            window.location.href = "/pages/auth/login.html";
        }
    };
    const placeModalByButton = (modalEl) => {
        if (!modalEl || !logoutBtn) return;
        const btnRect = logoutBtn.getBoundingClientRect();
        const modalRect = modalEl.getBoundingClientRect();

        let left = btnRect.left;
        let top = btnRect.top - modalRect.height - 12;

        if (top < 12) {
            top = btnRect.bottom + 12;
        }

        const maxLeft = window.innerWidth - modalRect.width - 12;
        if (left > maxLeft) left = maxLeft;
        if (left < 12) left = 12;

        modalEl.style.left = `${left}px`;
        modalEl.style.top = `${top}px`;
        modalEl.style.transform = "none";
    };

    const showLogoutConfirm = () => {
        if (existingOverlay()) return existingOverlay();
        const overlay = document.createElement("div");
        overlay.className = "logout-overlay";
        const modal = document.createElement("div");
        modal.className = "logout-modal";

        const title = document.createElement("h3");
        title.textContent = "Sign out?";
        const desc = document.createElement("p");
        desc.textContent = "You will be signed out of your company account.";

        const actions = document.createElement("div");
        actions.className = "logout-actions";
        const cancelBtn = document.createElement("button");
        cancelBtn.className = "btn btn-secondary";
        cancelBtn.textContent = "Stay signed in";
        cancelBtn.addEventListener("click", () => removeOverlay());

        const confirmBtn = document.createElement("button");
        confirmBtn.className = "btn btn-danger";
        confirmBtn.textContent = "Sign out";
        confirmBtn.addEventListener("click", () => {
            console.debug("[sidebar] logout confirmed");
            performLogout();
        });

        actions.appendChild(cancelBtn);
        actions.appendChild(confirmBtn);

        modal.appendChild(title);
        modal.appendChild(desc);
        modal.appendChild(actions);
        overlay.appendChild(modal);
        const removeOverlay = () => {
            overlay.remove();
            window.removeEventListener("resize", handleResize);
        };
        overlay.addEventListener("click", (e) => {
            if (e.target === overlay) removeOverlay();
        });
        document.body.appendChild(overlay);
        const handleResize = () => placeModalByButton(modal);
        window.addEventListener("resize", handleResize);
        requestAnimationFrame(() => placeModalByButton(modal));
        return overlay;
    };

    const handleLogoutClick = (e) => {
        e.preventDefault();
        e.stopImmediatePropagation();
        showLogoutConfirm();
    };

    if (logoutBtn) {
        console.debug("[sidebar] binding logout button");
        logoutBtn.addEventListener("click", handleLogoutClick, true);
    } else {
        console.warn("[sidebar] companyLogoutBtn not found");
    }

    // Fallback: delegate in case the button is re-rendered or listeners were lost
    document.addEventListener(
        "click",
        (e) => {
            const btn = e.target.closest && e.target.closest("#companyLogoutBtn");
            if (!btn) return;
            console.debug("[sidebar] delegated logout click");
            handleLogoutClick(e);
        },
        true
    );
});
