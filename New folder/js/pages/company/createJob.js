import { auth } from '../../core/auth.js';
import { api } from '../../core/api.js';
import { showNotification } from '../../core/notifications.js';

class CreateJobPage {
    constructor() {
        if (!auth.requireAuth() || !auth.requireUserType(['company'])) return;
        this.init();
    }

    init() {
        this.setupForm();
        this.setupEventListeners();
        this.loadJobData();
    }

    loadJobData() {
        const urlParams = new URLSearchParams(window.location.search);
        const jobId = urlParams.get('id');
        
        if (jobId) {
            // Load existing job data for editing
            this.loadJobDetails(jobId);
        }
    }

    async loadJobDetails(jobId) {
        try {
            // showNotification('Loading job details...', 'info');
            
            // Get company jobs and find the specific job
            const response = await api.getCompanyJobs();
            const job = response.jobs.find(j => j.id == jobId);
            
            if (job) {
                this.populateForm(job);
                showNotification('Job details loaded', 'success');
            } else {
                showNotification('Job not found', 'error');
            }
        } catch (error) {
            showNotification('Failed to load job details', 'error');
            console.error(error);
        }
    }

    renderSkillChips(skills, inputId, chipsId) {
    const input = document.getElementById(inputId);
    const chips = document.getElementById(chipsId);
    if (!input || !chips) return;

    chips.innerHTML = '';
    input.value = '';

    skills.forEach(skill => {
        const chip = document.createElement('span');
        chip.className = 'skill-chip';
        chip.innerHTML = `
            ${skill}
            <button type="button" class="chip-remove">&times;</button>
        `;

        chip.querySelector('button').onclick = () => chip.remove();
        chips.appendChild(chip);
    });

    input.value = skills.join(', ');
}

populateForm(job) {
        // Update page title
        document.querySelector('h1').textContent = 'Edit Job';
        
        // Populate form fields
        const form = document.getElementById('createJobForm');
        if (!form) return;

        // Basic fields
        if (job.title) form.querySelector('#jobTitle').value = job.title;
        if (job.description) form.querySelector('#jobDescription').value = job.description;
        if (job.requirements) form.querySelector('#requirements').value = job.requirements;
        if (job.benefits) form.querySelector('#benefits').value = job.benefits;
        if (job.location) form.querySelector('#location').value = job.location;
        if (job.department) form.querySelector('#department').value = job.department;
        if (job.job_type) form.querySelector('#jobType').value = job.job_type;
        if (job.experience_level) form.querySelector('#experienceLevel').value = job.experience_level;
        if (job.education_level) form.querySelector('#education').value = job.education_level;
        if (job.positions_available) form.querySelector('#positions').value = job.positions_available;
        
        // Salary
        if (job.salary_min || job.salary_max) {
            const salaryMin = form.querySelector('#salaryMin');
            const salaryMax = form.querySelector('#salaryMax');
            if (salaryMin && job.salary_min) salaryMin.value = job.salary_min;
            if (salaryMax && job.salary_max) salaryMax.value = job.salary_max;
        }
        
        if (job.salary_type) {
            const salaryType = form.querySelector('#salaryType');
            if (salaryType) salaryType.value = job.salary_type;
        }
        
        // Application deadline
        if (job.application_deadline) {
            const deadline = form.querySelector('#deadline');
            if (deadline) {
                const date = new Date(job.application_deadline);
                deadline.value = date.toISOString().split('T')[0];
            }
        }
        
        // --- NEW/CORRECTED SKILLS HANDLING ---
        const requiredInput = form.querySelector('#requiredSkillsInput');
        const bonusInput = form.querySelector('#bonusSkillsInput');

        // 1. Handle Required Skills
        if (job.required_skills && requiredInput) {
            try {
                // Assuming job.required_skills is a JSON string of a string array
                const skills = typeof job.required_skills === 'string' ? JSON.parse(job.required_skills) : job.required_skills;

                if (Array.isArray(skills)) {
                    this.updateSkillsDisplay(requiredInput, skills);
                }
            } catch (e) {
                console.error('Failed to parse and display required skills:', e);
            }
        }

        // 2. Handle Bonus Skills
        if (job.bonus_skills && bonusInput) {
            try {
                const skills = typeof job.bonus_skills === 'string' ? JSON.parse(job.bonus_skills) : job.bonus_skills;

                if (Array.isArray(skills)) {
                    this.updateSkillsDisplay(bonusInput, skills);
                }
            } catch (e) {
                console.error('Failed to parse and display bonus skills:', e);
            }
        }
        
        // Featured and urgent (uncommenting if you need them later)
        if (job.is_featured !== undefined) {
             const featured = form.querySelector('#featured');
             if (featured) featured.checked = job.is_featured == 1;
        }
        
        if (job.is_urgent !== undefined) {
             const urgent = form.querySelector('#urgent');
             if (urgent) urgent.checked = job.is_urgent == 1;
        }
    }

    setupForm() {
        const form = document.getElementById('createJobForm');
        if (!form) return;

        // If another script already bound the handler, skip to avoid double submits
        if (form.dataset.createJobBound === 'true') return;

        // Mark as bound so inline fallback in the HTML doesn’t attach a second listener
        form.dataset.createJobBound = 'true';

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            // Gather form data
            const formData = new FormData(form);
            const jobData = {};
            
            // Convert FormData to object
            for (let [key, value] of formData.entries()) {
                if (value) jobData[key] = value;
            }

            // Map form field names to API expectations
            if (!jobData.jobType && jobData.type) {
                jobData.jobType = jobData.type;
            }
            // Ensure backend "type" key is set (API expects "type" -> job_type column)
            if (!jobData.type && jobData.jobType) {
                jobData.type = jobData.jobType;
            }
            // Provide snake_case for experience_level if backend reads that
            if (!jobData.experience_level && jobData.experienceLevel) {
                jobData.experience_level = jobData.experienceLevel;
            }
            // Backend expects "experience" and "education"
            if (!jobData.experience && jobData.experienceLevel) {
                jobData.experience = jobData.experienceLevel;
            }
            if (!jobData.education && jobData.educationLevel) {
                jobData.education = jobData.educationLevel;
            }
            if (!jobData.applicationDeadline && jobData.deadline) {
                jobData.applicationDeadline = jobData.deadline;
            }
            if (!jobData.positionsAvailable && jobData.positions) {
                jobData.positionsAvailable = jobData.positions;
            }
            
            // Handle salary object
            if (jobData.salaryMin || jobData.salaryMax || jobData.salaryType) {
                jobData.salary = {
                    min: jobData.salaryMin || null,
                    max: jobData.salaryMax || null,
                    type: jobData.salaryType || null
                };
                delete jobData.salaryMin;
                delete jobData.salaryMax;
                delete jobData.salaryType;
            }
            
            // Inside your "Edit Mode" fetch logic
            if (data.requiredSkills) {
                requiredSkillsArr.length = 0; 
                requiredSkillsArr.push(...data.requiredSkills);
                renderSkills(requiredSkillsArr, "requiredSkillsChips");
            }

            if (data.bonusSkills) {
                bonusSkillsArr.length = 0;
                bonusSkillsArr.push(...data.bonusSkills);
                renderSkills(bonusSkillsArr, "bonusSkillsChips");
            }
            // if (requiredSkillsInput && requiredSkillsInput.dataset.skills) {
            //     try {
            //         // Change the key name to match what your Python script expects
            //         jobData.requiredSkillsInput = JSON.parse(requiredSkillsInput.dataset.skills);
            //     } catch (e) {
            //         jobData.requiredSkillsInput = [];
            //     }
            // }

            // if (bonusSkillsInput && bonusSkillsInput.dataset.skills) {
            //     try {
            //         // Change the key name to match what your Python script expects
            //         jobData.bonusSkillsInput = JSON.parse(bonusSkillsInput.dataset.skills);
            //     } catch (e) {
            //         jobData.bonusSkillsInput = [];
            //     }
            // }

            // Handle skills
            // if (jobData.requiredSkillsInput) {
            //     jobData.requiredSkillsInput = jobData.requiredSkillsInput
            //         .split(',')
            //         .map(skill => skill.trim())
            //         .filter(skill => skill.length > 0);
            // }
            
            // if (jobData.bonusSkillsInput) {
            //     jobData.bonusSkillsInput = jobData.bonusSkillsInput
            //         .split(',')
            //         .map(skill => skill.trim())
            //         .filter(skill => skill.length > 0);
            // }
            
            // Handle featured and urgent
            // jobData.featured = form.querySelector('#featured').checked;
            // jobData.urgent = form.querySelector('#urgent').checked;
            
            // --- Handle skills ---
            const requiredSkillsInput = form.querySelector('#requiredSkillsInput');
            const bonusSkillsInput = form.querySelector('#bonusSkillsInput');

            if (requiredSkillsInput && requiredSkillsInput.dataset.skills) {
                try {
                    jobData.requiredSkills = JSON.parse(requiredSkillsInput.dataset.skills);
                } catch (e) {
                    console.error('Failed to parse required skills dataset:', e);
                    jobData.requiredSkills = [];
                }
            } else {
                jobData.requiredSkills = [];
            }

            if (bonusSkillsInput && bonusSkillsInput.dataset.skills) {
                try {
                    jobData.bonusSkills = JSON.parse(bonusSkillsInput.dataset.skills);
                } catch (e) {
                    console.error('Failed to parse bonus skills dataset:', e);
                    jobData.bonusSkills = [];
                }
            } else {
                jobData.bonusSkills = [];
            }
            // Validation
            if (!jobData.title || !jobData.description || !jobData.location || !jobData.jobType || !jobData.experienceLevel) {
                showNotification('Please fill in title, description, location, job type, and experience level.', 'error');
                return;
            }
            
            // Show loading state
            const submitBtn = form.querySelector('button[type="submit"]');
            const originalText = submitBtn.innerHTML;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';
            submitBtn.disabled = true;

            try {
                const urlParams = new URLSearchParams(window.location.search);
                const jobId = urlParams.get('id');
                if (jobId) {
                    await api.updateCompanyJob(jobId, jobData);
                    showNotification('Job updated successfully!', 'success');
                } else {
                    const response = await api.createJob(jobData);
                    if (response.job_id) {
                        showNotification('Job created successfully!', 'success');
                    } else {
                        throw new Error(response.error || 'Failed to create job');
                    }
                }
            } catch (error) {
                showNotification(error.message || 'Failed to save job', 'error');
                console.error(error);
            } finally {
                // Reset button state
                submitBtn.innerHTML = originalText;
                submitBtn.disabled = false;
            }
        });
    }

    setupEventListeners() {
        // Cancel button
        const cancelBtn = document.getElementById('cancelBtn');
        if (cancelBtn) {
            cancelBtn.addEventListener('click', (e) => {
                e.preventDefault();
                if (confirm('Are you sure you want to cancel? Unsaved changes will be lost.')) {
                    window.location.href = '/pages/company/jobs/list.html';
                }
            });
        }
        
        // Preview button
        const previewBtn = document.getElementById('previewBtn');
        if (previewBtn) {
            previewBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this.previewJob();
            });
        }
        
        // Skills auto-suggest
        this.setupSkillsAutoSuggest();
    }

    setupSkillsAutoSuggest() {
        const requiredSkillsInput = document.querySelector('#requiredSkillsInput');
        const bonusSkillsInput = document.querySelector('#bonusSkillsInput');
        
        if (requiredSkillsInput) {
            this.setupSkillsInput(requiredSkillsInput);
        }
        
        if (bonusSkillsInput) {
            this.setupSkillsInput(bonusSkillsInput);
        }
    }

    setupSkillsInput(inputElement) {
        const skillsList = [
            'JavaScript', 'Python', 'React', 'Node.js', 'Java', 'C#', 'PHP', 'Ruby',
            'Go', 'Swift', 'Kotlin', 'TypeScript', 'Angular', 'Vue.js', 'Next.js',
            'Django', 'Flask', 'Spring', 'Laravel', 'Express.js', 'MySQL', 'PostgreSQL',
            'MongoDB', 'Redis', 'Oracle', 'SQL Server', 'AWS', 'Azure', 'Google Cloud',
            'Docker', 'Kubernetes', 'Jenkins', 'Git', 'GitHub', 'GitLab', 'Jira',
            'Figma', 'Adobe XD', 'Photoshop', 'Illustrator', 'HTML', 'CSS', 'Sass',
            'Tailwind CSS', 'Bootstrap', 'Material UI', 'REST API', 'GraphQL',
            'Machine Learning', 'Data Science', 'AI', 'TensorFlow', 'PyTorch',
            'Pandas', 'NumPy', 'SciPy', 'Tableau', 'Power BI', 'Excel'
        ];
        
        // Create datalist for autocomplete
        const datalistId = `${inputElement.id}_suggestions`;
        let datalist = document.getElementById(datalistId);
        
        if (!datalist) {
            datalist = document.createElement('datalist');
            datalist.id = datalistId;
            
            skillsList.forEach(skill => {
                const option = document.createElement('option');
                option.value = skill;
                datalist.appendChild(option);
            });
            
            document.body.appendChild(datalist);
        }
        
        inputElement.setAttribute('list', datalistId);
        
        // Add chips functionality
        inputElement.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ',') {
                e.preventDefault();
                const value = inputElement.value.trim();
                if (value) {
                    this.addSkillChip(value, inputElement);
                }
            }
        });
    }

    addSkillChip(skill, inputElement) {
        // Remove skill from input
        inputElement.value = '';

        // Get current skills
        const currentSkills = inputElement.dataset.skills ? 
            JSON.parse(inputElement.dataset.skills) : [];

        if (!currentSkills.includes(skill)) {
            currentSkills.push(skill);
            // Update input display
            this.updateSkillsDisplay(inputElement, currentSkills);
        }
    }

    setSkillsState(inputElement, skills) {
        const serialized = JSON.stringify(skills || []);
        inputElement.dataset.skills = serialized;
        const hiddenInputId = inputElement.id.replace(/Input$/, '');
        const hiddenInput = document.getElementById(hiddenInputId);
        if (hiddenInput) {
            hiddenInput.value = serialized;
        }
    }

    updateSkillsDisplay(inputElement, skills) {
        // 1. Determine the correct chips container ID based on the input ID
        let chipsContainerId = '';
        if (inputElement.id === 'requiredSkillsInput') {
            chipsContainerId = 'requiredSkillsChips';
        } else if (inputElement.id === 'bonusSkillsInput') {
            chipsContainerId = 'bonusSkillsChips';
        } else {
            return; // Safety check
        }

    // 2. Select the existing container by ID
    const chipsContainer = document.getElementById(chipsContainerId);
    if (!chipsContainer) return; // Should not happen if HTML is correct
    
    // 3. Update chips
    chipsContainer.innerHTML = skills.map(skill => `
        <span class="skill-chip">
            ${skill}
            <button type="button" class="chip-remove" data-skill="${skill}">
                &times;
            </button>
        </span>
    `).join('');
    
    // 4. Add remove functionality (using 'this' because it's in a class method)
    chipsContainer.querySelectorAll('.chip-remove').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault(); // Stop form submission if button is type="submit" (though yours is type="button")
            const skillToRemove = btn.dataset.skill; 
            
            // Get the current skills array from the input's dataset
            const currentSkills = inputElement.dataset.skills ? 
                JSON.parse(inputElement.dataset.skills) : [];
                
            const updatedSkills = currentSkills.filter(s => s !== skillToRemove);
            
            // Update dataset
            inputElement.dataset.skills = JSON.stringify(updatedSkills);
            
            // Re-render the display
            this.updateSkillsDisplay(inputElement, updatedSkills);
        });
    });
        
        // Update input value for form submission
        inputElement.value = skills.join(', ');
        // Sync dataset and hidden input after rendering
        this.setSkillsState(inputElement, skills);
    }

    previewJob() {
        const form = document.getElementById('createJobForm');
        const formData = new FormData(form);
        
        // Store preview data in sessionStorage
        const previewData = {};
        for (let [key, value] of formData.entries()) {
            previewData[key] = value;
        }
        
        sessionStorage.setItem('jobPreviewData', JSON.stringify(previewData));
        
        // Open preview in new tab
        window.open('/pages/company/job-preview.html', '_blank');
    }
}

// Initialize create job page when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new CreateJobPage();
});
