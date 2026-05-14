import { auth } from '../../core/auth.js';
import { showNotification } from '../../core/notifications.js';

class JobSeekerRegisterPage {
    constructor() {
        this.init();
    }

    init() {
        this.setupForm();
        this.setupCVUpload();
        this.setupEventListeners();
    }

    setupForm() {
        const form = document.getElementById('registerForm');
        if (!form) return;

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            // Gather form data
            const formData = new FormData(form);
            
            // Basic validation
            const email = formData.get('email');
            const password = formData.get('password');
            const confirmPassword = formData.get('confirmPassword');
            const fullName = formData.get('fullName');

            if (!email || !password || !confirmPassword || !fullName) {
                showNotification('Please fill in all required fields', 'error');
                return;
            }

            if (password !== confirmPassword) {
                showNotification('Passwords do not match', 'error');
                return;
            }

            if (password.length < 6) {
                showNotification('Password must be at least 6 characters', 'error');
                return;
            }

            // Show loading state
            const submitBtn = form.querySelector('button[type="submit"]');
            const originalText = submitBtn.innerHTML;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Creating account...';
            submitBtn.disabled = true;

            try {
                const result = await auth.jobSeekerRegister(formData);
                
                if (result.success) {
                    showNotification('Account created successfully!', 'success');
                    // Redirect will happen automatically via auth
                }
            } catch (error) {
                console.error('Registration error:', error);
            } finally {
                // Reset button state
                submitBtn.innerHTML = originalText;
                submitBtn.disabled = false;
            }
        });
    }

    setupCVUpload() {
        const dropZone = document.getElementById('cvDropZone');
        const fileInput = document.getElementById('cvFile');
        const uploadBtn = document.getElementById('uploadCVBtn');
        const fileName = document.getElementById('cvFileName');

        if (!dropZone || !fileInput || !uploadBtn) return;

        // Drag and drop events
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                e.stopPropagation();
            });
        });

        ['dragenter', 'dragover'].forEach(eventName => {
            dropZone.addEventListener(eventName, () => {
                dropZone.classList.add('dragover');
            });
        });

        ['dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, () => {
                dropZone.classList.remove('dragover');
            });
        });

        dropZone.addEventListener('drop', (e) => {
            const files = e.dataTransfer.files;
            if (files.length) {
                this.handleFileSelect(files[0], fileName);
            }
        });

        fileInput.addEventListener('change', (e) => {
            if (e.target.files.length) {
                this.handleFileSelect(e.target.files[0], fileName);
            }
        });

        uploadBtn.addEventListener('click', () => {
            fileInput.click();
        });
    }

    handleFileSelect(file, fileNameElement) {
        if (!file.type.includes('pdf') && !file.type.includes('word') && !file.type.includes('msword')) {
            showNotification('Please upload a PDF or Word document', 'error');
            return;
        }

        if (file.size > 5 * 1024 * 1024) { // 5MB limit
            showNotification('File size should be less than 5MB', 'error');
            return;
        }

        if (fileNameElement) {
            fileNameElement.textContent = file.name;
            fileNameElement.style.display = 'block';
        }
    }

    setupEventListeners() {
        // Toggle password visibility
        const togglePasswordBtns = document.querySelectorAll('.toggle-password');
        togglePasswordBtns.forEach(btn => {
            btn.addEventListener('click', (e) => {
                const input = e.target.closest('.password-input').querySelector('input');
                const type = input.getAttribute('type') === 'password' ? 'text' : 'password';
                input.setAttribute('type', type);
                btn.innerHTML = type === 'password' ? 
                    '<i class="fas fa-eye"></i>' : 
                    '<i class="fas fa-eye-slash"></i>';
            });
        });

        // Terms and conditions
        const termsCheckbox = document.getElementById('terms');
        const submitBtn = document.querySelector('button[type="submit"]');
        
        if (termsCheckbox && submitBtn) {
            termsCheckbox.addEventListener('change', () => {
                submitBtn.disabled = !termsCheckbox.checked;
            });
            
            // Initial state
            submitBtn.disabled = !termsCheckbox.checked;
        }
    }
}

// Initialize register page when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new JobSeekerRegisterPage();
});