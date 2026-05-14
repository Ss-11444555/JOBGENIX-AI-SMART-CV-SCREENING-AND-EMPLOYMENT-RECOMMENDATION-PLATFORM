// js/core/api.js
import Config from './config.js';

class JobGenixAPI {
    constructor() {
        this.baseURL = Config.API_BASE_URL;
        this.token = localStorage.getItem(Config.STORAGE_KEYS.AUTH_TOKEN);
    }
    
    setToken(token) {
        this.token = token;
        localStorage.setItem(Config.STORAGE_KEYS.AUTH_TOKEN, token);
    }
    
    getHeaders(contentType = 'application/json') {
        const headers = {};

        // only set content-type if we know it (for JSON calls)
        if (contentType) {
            headers['Content-Type'] = contentType;
        }
        
        if (this.token) {
            headers['Authorization'] = `Bearer ${this.token}`;
        }
        
        return headers;
    }
    
    async handleResponse(response) {
        if (!response.ok) {
            const error = await response.json().catch(() => ({
                error: `HTTP error! status: ${response.status}`
            }));
            
            throw new Error(error.error || error.message || 'Request failed');
        }
        
        return response.json();
    }
    
    async request(endpoint, options = {}) {
        const url = `${this.baseURL}${endpoint}`;
        
        // take contentType out, everything else goes directly to fetch
        const { contentType = 'application/json', ...rest } = options;
        
        const response = await fetch(url, {
            headers: this.getHeaders(contentType),
            ...rest
        });
        
        return this.handleResponse(response);
    }
    
    // ---------- Auth ----------
    async login(email, password) {
        return this.request('/api/auth/login', {
            method: 'POST',
            body: JSON.stringify({ email, password })
        });
    }
    
    async jobSeekerRegister(formData) {
        const data = Object.fromEntries(formData);
        return this.request('/api/auth/job-seeker/register', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }
    
    async companyRegister(formData) {
        const data = Object.fromEntries(formData);
        return this.request('/api/auth/company/register', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }
    
    async forgotPassword(email) {
        return this.request('/api/auth/forgot-password', {
            method: 'POST',
            body: JSON.stringify({ email })
        });
    }
    
    // ---------- CV Processing ----------
    async uploadCV(file) {
        const formData = new FormData();
        formData.append('cvFile', file);
        
        const response = await fetch(`${this.baseURL}/api/job-seeker/upload-cv`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${this.token}`
            },
            body: formData
        });
        
        return this.handleResponse(response);
    }
    
    async extractSkills(cvId) {
        return this.request(`/api/cv/${cvId}/extract`);
    }
    
    // ---------- Job Seeker Profile ----------
    async getJobSeekerProfile() {
        return this.request('/api/job-seeker/profile');
    }
    
    async updateJobSeekerProfile(profileData) {
        return this.request('/api/job-seeker/profile', {
            method: 'PUT',
            body: JSON.stringify(profileData)
        });
    }
    
    async getJobSeekerDashboard() {
        return this.request('/api/job-seeker/dashboard');
    }
    
    // ---------- Jobs & Applications ----------
    async searchJobs(filters = {}) {
        const queryParams = new URLSearchParams(filters).toString();
        return this.request(`/api/jobs/search?${queryParams}`);
    }
    
    async getJob(jobId) {
        return this.request(`/api/jobs/${jobId}`);
    }
    
    async applyToJob(jobId, coverLetter = '') {
        return this.request(`/api/jobs/${jobId}/apply`, {
            method: 'POST',
            body: JSON.stringify({ coverLetter })
        });
    }
    
    async getApplications(filters = {}) {
        const queryParams = new URLSearchParams(filters).toString();
        return this.request(`/api/applications?${queryParams}`);
    }
    
    async getApplication(applicationId) {
        return this.request(`/api/applications/${applicationId}`);
    }
    
    // ---------- Saved Jobs ----------
    async saveJob(jobId) {
        return this.request(`/api/jobs/${jobId}/save`, {
            method: 'POST'
        });
    }
    
    async unsaveJob(jobId) {
        return this.request(`/api/jobs/${jobId}/unsave`, {
            method: 'DELETE'
        });
    }
    
    async getSavedJobs() {
        return this.request('/api/jobs/saved');
    }
    
    // ---------- Company ----------
    async createJob(jobData) {
        return this.request('/api/company/jobs', {
            method: 'POST',
            body: JSON.stringify(jobData)
        });
    }

    async updateCompanyJob(jobId, jobData) {
        return this.request(`/api/company/jobs/${jobId}`, {
            method: 'PUT',
            body: JSON.stringify(jobData)
        });
    }

    async deleteCompanyJob(jobId) {
        return this.request(`/api/company/jobs/${jobId}`, {
            method: 'DELETE'
        });
    }
    
    async getCompanyJobs() {
        return this.request('/api/company/jobs');
    }
    
    async getCompanyCandidates() {
        return this.request('/api/company/candidates');
    }
    
    async getRecentCandidates() {
        return this.request('/api/company/recent-candidates');
    }
    
    async getCompanyDashboard() {
        return this.request('/api/company/dashboard');
    }
    
    // ---------- Interview ----------
    async startInterview(jobId) {
        return this.request(`/api/interview/start/${jobId}`, {
            method: 'POST'
        });
    }
    
    async submitAnswer(interviewId, questionId, answer) {
        return this.request(`/api/interview/${interviewId}/answer`, {
            method: 'POST',
            body: JSON.stringify({ questionId, answer })
        });
    }
    
    async getInterviewResults(interviewId) {
        return this.request(`/api/interview/${interviewId}/results`);
    }
    
    // ---------- Analytics ----------
    async getDashboardStats() {
        return this.request('/api/dashboard/stats');
    }
    
    // ---------- Delete Account ----------
    async deleteJobSeekerAccount() {
        return this.request('/api/job-seeker/account', {
            method: 'DELETE'
        });
    }
}

export const api = new JobGenixAPI();
