const AuthGuard = (function () {
    const AUTH_KEYS = ["authToken", "token", "jobgenix_token"];
    const redirectToLogin = () => {
        history.replaceState(null, "", "/pages/auth/login.html");
        window.location.replace("/pages/auth/login.html");
    };

    const validate = (expectedRole) => {
        try {
            const token = AUTH_KEYS.map((key) => localStorage.getItem(key)).find(Boolean);
            const userRaw = localStorage.getItem("user") || "{}";
            const user = JSON.parse(userRaw);
            if (!token || !user.user_type || user.user_type !== expectedRole) {
                throw new Error("Invalid token/user");
            }
        } catch (err) {
            redirectToLogin();
        }
    };

    return { validate };
})();

export default AuthGuard;
