// Authentication specific JavaScript
import Config from './config.js';
import { api } from './api.js';

class AuthService {
    constructor() {
        this.tokenKey = Config?.STORAGE_KEYS?.AUTH_TOKEN || 'auth_token';
        this.userKey = Config?.STORAGE_KEYS?.USER_DATA || 'user';
        this.userTypeKey = Config?.STORAGE_KEYS?.USER_TYPE || 'user_type';
    }

    getStoredToken() {
        const possibleKeys = [
            this.tokenKey,
            'authToken',
            'token',
            'jobgenix_token'
        ];
        for (const key of possibleKeys) {
            const val = localStorage.getItem(key);
            if (val) return val;
        }
        return null;
    }

    getStoredUser() {
        const possibleKeys = [this.userKey, 'user'];
        for (const key of possibleKeys) {
            const raw = localStorage.getItem(key);
            if (!raw) continue;
            try {
                return JSON.parse(raw);
            } catch (e) {
                console.error('Failed to parse stored user', e);
            }
        }
        return null;
    }

    getRedirectForUser(user) {
        if (!user || !user.user_type) return '/';
        if (user.user_type === 'job_seeker') return '/pages/jobseeker/dashboard.html';
        if (user.user_type === 'company') return '/pages/company/dashboard.html';
        return '/';
    }

    storeSession(token, user) {
        if (token) {
            localStorage.setItem(this.tokenKey, token);
            // keep legacy keys in sync
            localStorage.setItem('authToken', token);
            localStorage.setItem('token', token);
            localStorage.setItem('jobgenix_token', token);
        }
        if (user) {
            localStorage.setItem(this.userKey, JSON.stringify(user));
            if (user.user_type) {
                localStorage.setItem(this.userTypeKey, user.user_type);
            }
        }
    }

    async login(email, password) {
        try {
            const resp = await api.login(email, password);
            this.storeSession(resp.token, resp.user);
            const redirect = this.getRedirectForUser(resp.user);
            return { success: true, redirect, user: resp.user, token: resp.token };
        } catch (err) {
            console.error('Login failed:', err);
            throw err;
        }
    }

    logout() {
        const clear = () => {
            localStorage.removeItem(this.tokenKey);
            localStorage.removeItem('authToken');
            localStorage.removeItem('token');
            localStorage.removeItem('jobgenix_token');
            localStorage.removeItem(this.userKey);
            localStorage.removeItem(this.userTypeKey);
            window.location.href = '/pages/auth/login.html';
        };
        try {
            const base = window.API_BASE_URL || 'http://localhost:8000';
            fetch(`${base}/api/auth/logout`, { method: 'POST' }).finally(clear);
        } catch (e) {
            clear();
        }
    }

    requireAuth() {
        const token = this.getStoredToken();
        if (!token) {
            window.location.href = '/pages/auth/login.html';
            return false;
        }
        try {
            api.setToken(token);
        } catch (e) {
            console.error('Failed to set token on API instance', e);
        }
        return true;
    }

    requireUserType(allowed = []) {
        if (!allowed || !allowed.length) return true;
        const user = this.getStoredUser();
        const userType = user?.user_type || localStorage.getItem(this.userTypeKey);
        if (!userType || !allowed.includes(userType)) {
            window.location.href = '/pages/auth/login.html';
            return false;
        }
        return true;
    }
}

class AuthManager {
    constructor() {
        this.init();
    }

    init() {
        this.setupRegisterForms();
        this.setupPasswordToggles();
    }

    setupRegisterForms() {
        // User type selection
        document.querySelectorAll('.user-type-card').forEach(card => {
            card.addEventListener('click', function() {
                document.querySelectorAll('.user-type-card').forEach(c => {
                    c.classList.remove('selected');
                });
                this.classList.add('selected');
                
                const userType = this.dataset.type;
                if (userType === 'job_seeker') {
                    document.getElementById('jobSeekerForm').style.display = 'block';
                    document.getElementById('companyForm').style.display = 'none';
                } else {
                    document.getElementById('jobSeekerForm').style.display = 'none';
                    document.getElementById('companyForm').style.display = 'block';
                }
            });
        });

        // Job seeker registration
        const jobSeekerForm = document.getElementById('jobSeekerForm');
        if (jobSeekerForm) {
            jobSeekerForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                await this.handleJobSeekerRegistration(jobSeekerForm);
            });
        }

        // Company registration
        const companyForm = document.getElementById('companyForm');
        if (companyForm) {
            companyForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                await this.handleCompanyRegistration(companyForm);
            });
        }

        // CV upload
        const cvDropZone = document.getElementById('cvDropZone');
        const cvFileInput = document.getElementById('cvFile');
        
        if (cvDropZone && cvFileInput) {
            cvDropZone.addEventListener('click', () => cvFileInput.click());
            
            cvFileInput.addEventListener('change', (e) => {
                if (e.target.files.length) {
                    const file = e.target.files[0];
                    this.showFilePreview(cvDropZone, file);
                }
            });
        }
    }

    setupPasswordToggles() {
        document.querySelectorAll('.toggle-password').forEach(btn => {
            btn.addEventListener('click', function() {
                const input = this.closest('.password-input').querySelector('input');
                const type = input.getAttribute('type') === 'password' ? 'text' : 'password';
                input.setAttribute('type', type);
                this.innerHTML = type === 'password' ? 
                    '<i class="fas fa-eye"></i>' : 
                    '<i class="fas fa-eye-slash"></i>';
            });
        });
    }

    async handleJobSeekerRegistration(form) {
        const formData = new FormData(form);
        
        // Basic validation
        const password = formData.get('password');
        const confirmPassword = formData.get('confirmPassword');
        
        if (password !== confirmPassword) {
            this.showAlert('Passwords do not match', 'error');
            return;
        }
        
        if (password.length < 6) {
            this.showAlert('Password must be at least 6 characters', 'error');
            return;
        }

        const submitBtn = form.querySelector('button[type="submit"]');
        const originalText = submitBtn.innerHTML;
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Creating account...';
        submitBtn.disabled = true;

        try {
            const response = await fetch(`${Config.API_BASE_URL}/api/auth/job-seeker/register`, {
                method: 'POST',
                body: formData
            });

            const data = await response.json();

            if (response.ok) {
                this.showAlert('Account created successfully! Redirecting...', 'success');
                
                // Store token and user data
                localStorage.setItem('token', data.token);
                localStorage.setItem('user', JSON.stringify(data.user));
                
                setTimeout(() => {
                    window.location.href = '/pages/jobseeker/dashboard.html';
                }, 1500);
            } else {
                this.showAlert(data.error || 'Registration failed', 'error');
            }
        } catch (error) {
            this.showAlert('Network error. Please try again.', 'error');
            console.error('Registration error:', error);
        } finally {
            submitBtn.innerHTML = originalText;
            submitBtn.disabled = false;
        }
    }

    async handleCompanyRegistration(form) {
        const formData = new FormData(form);
        const data = Object.fromEntries(formData.entries());
        
        // Basic validation
        const password = data.password;
        const confirmPassword = data.confirmPassword;
        
        if (password !== confirmPassword) {
            this.showAlert('Passwords do not match', 'error');
            return;
        }
        
        if (password.length < 6) {
            this.showAlert('Password must be at least 6 characters', 'error');
            return;
        }

        const submitBtn = form.querySelector('button[type="submit"]');
        const originalText = submitBtn.innerHTML;
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Creating account...';
        submitBtn.disabled = true;

        try {
            const response = await fetch(`${Config.API_BASE_URL}/api/auth/company/register`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(data)
            });

            const result = await response.json();

            if (response.ok) {
                this.showAlert('Company account created successfully! Redirecting...', 'success');
                
                localStorage.setItem('token', result.token);
                localStorage.setItem('user', JSON.stringify(result.user));
                
                setTimeout(() => {
                    window.location.href = '/pages/company/dashboard.html';
                }, 1500);
            } else {
                this.showAlert(result.error || 'Registration failed', 'error');
            }
        } catch (error) {
            this.showAlert('Network error. Please try again.', 'error');
            console.error('Registration error:', error);
        } finally {
            submitBtn.innerHTML = originalText;
            submitBtn.disabled = false;
        }
    }

    showFilePreview(dropZone, file) {
        if (!file.type.includes('pdf') && !file.type.includes('word') && !file.type.includes('msword')) {
            this.showAlert('Please upload a PDF or Word document', 'error');
            return;
        }

        if (file.size > 5 * 1024 * 1024) {
            this.showAlert('File size should be less than 5MB', 'error');
            return;
        }

        dropZone.innerHTML = `
            <i class="fas fa-check-circle" style="color: var(--success); font-size: 2.5rem;"></i>
            <p style="margin: 0.5rem 0; font-weight: 500;">${file.name}</p>
            <p style="color: var(--gray); font-size: 0.9rem;">(${(file.size / 1024 / 1024).toFixed(2)} MB)</p>
            <button type="button" class="btn" style="background: var(--gray-light); color: var(--dark); margin-top: 0.5rem; padding: 8px 16px; font-size: 0.9rem;" onclick="document.getElementById('cvFile').value = ''; location.reload();">
                Change File
            </button>
        `;
    }

    showAlert(message, type = 'error') {
        const alert = document.createElement('div');
        alert.className = `alert alert-${type}`;
        alert.innerHTML = `
            <div style="display: flex; align-items: center; gap: 10px;">
                <i class="fas fa-${type === 'success' ? 'check-circle' : 'exclamation-circle'}"></i>
                <span>${message}</span>
            </div>
            <button onclick="this.parentElement.remove()" style="background: none; border: none; color: inherit; cursor: pointer;">
                <i class="fas fa-times"></i>
            </button>
        `;
        
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
            z-index: 1000;
            min-width: 300px;
            max-width: 400px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            animation: slideIn 0.3s ease;
            ${type === 'success' ? 'background: #d1fae5; color: #065f46; border: 1px solid #a7f3d0;' : ''}
            ${type === 'error' ? 'background: #fee2e2; color: #991b1b; border: 1px solid #fecaca;' : ''}
        `;
        
        document.body.appendChild(alert);
        
        setTimeout(() => {
            if (alert.parentElement) {
                alert.remove();
            }
        }, 5000);
    }
}

// Initialize auth manager
export const auth = new AuthService();
const authManager = new AuthManager();

export default auth;
