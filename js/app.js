// js/app.js - Enhanced for real-world workflow
class JobGenixApp {
    constructor() {
        const API_BASE = "http://localhost:8000/api";
        this.apiBase = API_BASE;
        this.currentUser = null;
        this.tokenKeys = ['authToken', 'token', 'jobgenix_token'];
        this.init();
    }

    init() {
        this.setupGlobalEventListeners();
        this.loadUser();
        this.checkAuth();
        this.setupPasswordToggle();
    }

    loadUser() {
        const userJson = localStorage.getItem('user');
        let token = null;
        for (const key of this.tokenKeys) {
            const val = localStorage.getItem(key);
            if (val) { token = val; break; }
        }
        if (!userJson || !token) return;
        try {
            this.currentUser = JSON.parse(userJson);
            this.token = token;
        } catch (e) {
            console.error('Failed to parse user data:', e);
            this.logout();
        }
    }

    setupGlobalEventListeners() {
        // Logout functionality
        document.addEventListener('click', (e) => {
            if (e.target.closest('.logout-btn')) {
                e.preventDefault();
                this.logout();
            }
        });

        // Form submissions
        document.addEventListener('submit', (e) => {
            // Login form
            if (e.target.id === 'loginForm' || e.target.classList.contains('login-form')) {
                e.preventDefault();
                this.handleLogin(e.target);
            }
            
            // Unified registration form
            if (e.target.id === 'registerForm' || e.target.classList.contains('register-form')) {
                e.preventDefault();
                this.handleRegistration(e.target);
            }
            
            // Job seeker specific registration
            if (e.target.id === 'jobseekerRegisterForm') {
                e.preventDefault();
                this.handleJobseekerRegistration(e.target);
            }
            
            // Company specific registration
            if (e.target.id === 'companyRegisterForm') {
                e.preventDefault();
                this.handleCompanyRegistration(e.target);
            }
        });
    }

    setupPasswordToggle() {
        document.addEventListener('click', (e) => {
            if (e.target.closest('.toggle-password')) {
                const button = e.target.closest('.toggle-password');
                const input = button.parentElement.querySelector('input');
                const icon = button.querySelector('i');
                
                if (input.type === 'password') {
                    input.type = 'text';
                    icon.classList.remove('fa-eye');
                    icon.classList.add('fa-eye-slash');
                } else {
                    input.type = 'password';
                    icon.classList.remove('fa-eye-slash');
                    icon.classList.add('fa-eye');
                }
            }
        });
    }

    async handleLogin(form, options = {}) {
        const email = form.querySelector('#email')?.value || 
                     form.querySelector('#loginEmail')?.value ||
                     form.querySelector('input[type="email"]')?.value;
        const password = form.querySelector('#password')?.value || 
                        form.querySelector('#loginPassword')?.value ||
                        form.querySelector('input[type="password"]')?.value;

        if (!email || !password) {
            this.showAlert('Please fill in all fields', 'error');
            return;
        }

        const submitBtn = form.querySelector('button[type="submit"]');
        const originalText = submitBtn.innerHTML;
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Signing in...';
        submitBtn.disabled = true;

        try {
            const response = await fetch(`${this.apiBase}/auth/login`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ email, password })
            });

            const data = await response.json();

            if (response.ok) {
                // Store token in all known keys for compatibility
                localStorage.setItem("authToken", data.token);
                localStorage.setItem("token", data.token);
                localStorage.setItem("jobgenix_token", data.token);
                localStorage.setItem('user', JSON.stringify(data.user));
                this.currentUser = data.user;
                this.token = data.token;
                
                this.showAlert('Login successful! Redirecting...', 'success');
                
                // Redirect based on user type
                setTimeout(() => {
                    const redirectUrl = options.redirectUrl;
                    const targetUrl = redirectUrl || this.getDefaultDashboardUrl(data.user.user_type);
                    history.replaceState(null, '', targetUrl);
                    window.location.replace(targetUrl);
                }, 1000);
            } else {
                this.showAlert(data.error || 'Login failed. Please check your credentials.', 'error');
            }
        } catch (error) {
            console.error('Login error:', error);
            this.showAlert('Network error. Please try again.', 'error');
        } finally {
            submitBtn.innerHTML = originalText;
            submitBtn.disabled = false;
        }
    }

    async handleRegistration(form) {
        // Unified registration - determine user type from form
        const userType = form.querySelector('input[name="user_type"]')?.value || 
                        form.dataset.userType ||
                        (form.id.includes('jobseeker') ? 'job_seeker' : 
                         form.id.includes('company') ? 'company' : null);

        if (!userType) {
            this.showAlert('User type not specified', 'error');
            return;
        }

        const submitBtn = form.querySelector('button[type="submit"]');
        const originalText = submitBtn.innerHTML;
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Creating Account...';
        submitBtn.disabled = true;

        try {
            // Collect form data
            const formData = new FormData(form);
            const data = {};
            formData.forEach((value, key) => {
                data[key] = value;
            });
            
            // Add user type
            data.user_type = userType;

            const response = await fetch(`${this.apiBase}/auth/register`, {
                method: 'POST',
                headers: {
                    "Authorization": "Bearer " + token
                },
                body: JSON.stringify(data)
            });

            const result = await response.json();

            if (response.ok) {
                this.showAlert('Registration successful! Redirecting to login...', 'success');
                
                // Redirect to login after 2 seconds
                setTimeout(() => {
                    window.location.href = '/pages/auth/login.html';
                }, 2000);
            } else {
                this.showAlert(result.error || 'Registration failed', 'error');
            }
        } catch (error) {
            console.error('Registration error:', error);
            this.showAlert('Network error. Please try again.', 'error');
        } finally {
            submitBtn.innerHTML = originalText;
            submitBtn.disabled = false;
        }
    }

    async handleJobseekerRegistration(form) {
        // For backward compatibility - calls unified registration
        form.dataset.userType = 'job_seeker';
        await this.handleRegistration(form);
    }

    async handleCompanyRegistration(form) {
        // For backward compatibility - calls unified registration
        form.dataset.userType = 'company';
        await this.handleRegistration(form);
    }

    getDefaultDashboardUrl(userType) {
        switch(userType) {
            case 'job_seeker':
                return '/pages/jobseeker/dashboard.html';
            case 'company':
                return '/pages/company/dashboard.html';
            case 'admin':
                return '/pages/admin/dashboard.html';
            default:
                return '/';
        }
    }

    logout() {
        if (this.isLoggingOut) return;
        this.isLoggingOut = true;
        ['user','user_type','jobgenix_user','jobgenix_user_type'].forEach(k => localStorage.removeItem(k));
        ['authToken','token','jobgenix_token'].forEach(k => localStorage.removeItem(k));
        this.currentUser = null;
        this.token = null;
        this.showAlert('Logged out successfully', 'success');
        history.pushState(null, '', '/pages/auth/login.html');
        setTimeout(() => {
            window.location.replace('/pages/auth/login.html');
        }, 500);
    }

    checkAuth() {
        const currentPath = window.location.pathname;
        
        // Skip auth check for public pages
        const publicPages = ['/', '/index.html', '/pages/auth/login.html', 
                            '/pages/auth/register-jobseeker.html', '/pages/auth/register-company.html',
                            '/pages/auth/forgot-password.html', '/pages/about.html'];
        
        if (publicPages.some(page => currentPath === page || currentPath.startsWith(page))) {
            return;
        }
        
        // Check if user is authenticated
        if (!this.token || !this.currentUser) {
            if (!publicPages.includes(currentPath)) {
                this.showAlert('Please login to continue', 'warning');
                setTimeout(() => {
                    window.location.href = '/pages/auth/login.html';
                }, 1000);
            }
            return;
        }
        
        // Check if user has access to current page
        const userType = this.currentUser.user_type;
        const isOnCorrectDashboard = currentPath.includes(`/pages/${userType}/`);
        
        if (!isOnCorrectDashboard && !currentPath.includes('/pages/auth/')) {
            this.showAlert(`Access denied. Please use the ${userType} dashboard.`, 'error');
            setTimeout(() => {
                this.redirectToDashboard(userType);
            }, 1500);
        }
    }

    showAlert(message, type = 'info') {
        // Remove existing alerts
        const existingAlerts = document.querySelectorAll('.jobgenix-alert');
        existingAlerts.forEach(alert => alert.remove());

        // Create alert element
        const alert = document.createElement('div');
        alert.className = `jobgenix-alert jobgenix-alert-${type}`;
        alert.innerHTML = `
            <div style="display: flex; align-items: center; gap: 10px;">
                <i class="fas fa-${type === 'success' ? 'check-circle' : 
                                 type === 'error' ? 'exclamation-circle' : 
                                 type === 'warning' ? 'exclamation-triangle' : 
                                 'info-circle'}"></i>
                <span>${message}</span>
            </div>
            <button onclick="this.parentElement.remove()" style="background: none; border: none; color: inherit; cursor: pointer;">
                <i class="fas fa-times"></i>
            </button>
        `;
        
        // Style the alert
        alert.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 1rem 1.5rem;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            z-index: 10000;
            min-width: 300px;
            max-width: 400px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            animation: slideIn 0.3s ease;
            ${type === 'success' ? 'background: #d1fae5; color: #065f46; border: 1px solid #a7f3d0;' : ''}
            ${type === 'error' ? 'background: #fee2e2; color: #991b1b; border: 1px solid #fecaca;' : ''}
            ${type === 'warning' ? 'background: #fef3c7; color: #92400e; border: 1px solid #fde68a;' : ''}
            ${type === 'info' ? 'background: #dbeafe; color: #1e40af; border: 1px solid #bfdbfe;' : ''}
        `;
        
        document.body.appendChild(alert);
        
        // Auto remove after 5 seconds
        setTimeout(() => {
            if (alert.parentElement) {
                alert.remove();
            }
        }, 5000);
    }

    async getRequest(endpoint) {
        try {
            const token = this.getToken();

            const headers = {
                'Content-Type': 'application/json'
            };
            
            if (token) {
                headers['Authorization'] = `Bearer ${token}`;
            } else {
                this.logout();
                return null;
            }
            
            const response = await fetch(`${this.apiBase}${endpoint}`, {
                headers
            });
            
            if (response.status === 401) {
                this.logout();
                return null;
            }
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            return await response.json();
        } catch (error) {
            console.error('API GET Error:', error);
            this.showAlert('Failed to fetch data. Please try again.', 'error');
            return null;
        }
    }

    async postRequest(endpoint, data) {
        try {
            const token = this.getToken();
            const headers = {
                'Content-Type': 'application/json'
            };
            
            if (token) {
                headers['Authorization'] = `Bearer ${token}`;
            }
            
            const response = await fetch(`${this.apiBase}${endpoint}`, {
                method: 'POST',
                headers,
                body: JSON.stringify(data)
            });
            
            if (response.status === 401) {
                this.logout();
                return null;
            }
            
            return await response.json();
        } catch (error) {
            console.error('API POST Error:', error);
            this.showAlert('Failed to submit data. Please try again.', 'error');
            return null;
        }
    }

    getToken() {
        for (const key of this.tokenKeys) {
            const val = localStorage.getItem(key);
            if (val) return val;
        }
        return null;
    }

    getUser() {
        return this.currentUser;
    }

    isAuthenticated() {
        return !!(this.token && this.currentUser);
    }
}

// Initialize app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.JobGenixApp = new JobGenixApp();
});

// Add animation for alerts
if (!document.querySelector('style[data-alert-animations]')) {
    const style = document.createElement('style');
    style.setAttribute('data-alert-animations', 'true');
    style.textContent = `
        @keyframes slideIn {
            from {
                transform: translateX(100%);
                opacity: 0;
            }
            to {
                transform: translateX(0);
                opacity: 1;
            }
        }
    `;
    document.head.appendChild(style);
}
