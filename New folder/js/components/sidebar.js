import { auth } from '../core/auth.js';

class SidebarManager {
    constructor() {
        this.sidebar = null;
        this.toggleBtn = null;
        this.isCollapsed = localStorage.getItem('sidebar_collapsed') === 'true';
        this.init();
    }
    
    init() {
        this.sidebar = document.querySelector('.sidebar');
        this.toggleBtn = document.querySelector('.sidebar-toggle');
        
        if (!this.sidebar || !this.toggleBtn) return;
        
        this.setupEventListeners();
        this.loadUserData();
        this.setInitialState();
    }
    
    setupEventListeners() {
        // Toggle button
        this.toggleBtn.addEventListener('click', () => {
            this.toggle();
        });
        
        // Close sidebar on mobile when clicking outside
        document.addEventListener('click', (e) => {
            if (window.innerWidth <= 1024 && 
                this.sidebar.classList.contains('show') &&
                !e.target.closest('.sidebar') &&
                !e.target.closest('.navbar-mobile-toggle')) {
                this.hide();
            }
        });
        
        // Responsive behavior
        window.addEventListener('resize', () => {
            this.handleResize();
        });
        
        // Handle sidebar links
        document.addEventListener('click', (e) => {
            const link = e.target.closest('.sidebar-link');
            if (link) {
                this.handleLinkClick(link);
            }
        });
    }
    
    setInitialState() {
        if (this.isCollapsed) {
            this.collapse();
        } else {
            this.expand();
        }
        
        this.handleResize();
    }
    
    toggle() {
        if (this.isCollapsed) {
            this.expand();
        } else {
            this.collapse();
        }
        this.isCollapsed = !this.isCollapsed;
        localStorage.setItem('sidebar_collapsed', this.isCollapsed);
    }
    
    collapse() {
        this.sidebar.classList.add('collapsed');
        this.toggleBtn.innerHTML = '<i class="fas fa-chevron-right"></i>';
        
        // Update main content margin
        const mainContent = document.querySelector('.main-content');
        if (mainContent) {
            mainContent.style.marginLeft = '80px';
        }
    }
    
    expand() {
        this.sidebar.classList.remove('collapsed');
        this.toggleBtn.innerHTML = '<i class="fas fa-chevron-left"></i>';
        
        // Update main content margin
        const mainContent = document.querySelector('.main-content');
        if (mainContent) {
            mainContent.style.marginLeft = '280px';
        }
    }
    
    show() {
        this.sidebar.classList.add('show');
        document.body.style.overflow = 'hidden';
    }
    
    hide() {
        this.sidebar.classList.remove('show');
        document.body.style.overflow = '';
    }
    
    handleResize() {
        if (window.innerWidth <= 1024) {
            this.sidebar.classList.remove('collapsed');
            this.toggleBtn.style.display = 'none';
            
            // Hide sidebar by default on mobile
            if (!this.sidebar.classList.contains('show')) {
                this.hide();
            }
        } else {
            this.toggleBtn.style.display = 'flex';
            document.body.style.overflow = '';
            
            // Restore collapsed state
            if (this.isCollapsed) {
                this.collapse();
            } else {
                this.expand();
            }
        }
    }
    
    loadUserData() {
        const user = auth.getUser();
        if (!user) return;
        
        // Update user info in sidebar
        const userNameElement = this.sidebar.querySelector('.user-name-sm');
        const userRoleElement = this.sidebar.querySelector('.user-role-sm');
        const userAvatarElement = this.sidebar.querySelector('.user-avatar-sm img');
        
        if (userNameElement) {
            userNameElement.textContent = user.name || 'User';
        }
        
        if (userRoleElement) {
            userRoleElement.textContent = this.getUserRoleText(auth.getUserType());
        }
        
        if (userAvatarElement) {
            userAvatarElement.src = auth.getUserAvatarUrl();
            userAvatarElement.alt = user.name || 'User';
        }
        
        // Update sidebar navigation based on user type
        this.updateNavigation(user);
    }
    
    getUserRoleText(userType) {
        const roles = {
            jobseeker: 'Job Seeker',
            company: 'Recruiter',
            admin: 'Administrator'
        };
        return roles[userType] || 'User';
    }
    
    updateNavigation(user) {
        const userType = auth.getUserType();
        
        // Hide/show sections based on user type
        const cvSection = this.sidebar.querySelector('.cv-upload-section');
        const companySection = this.sidebar.querySelector('.company-section');
        const adminSection = this.sidebar.querySelector('.admin-section');
        
        if (userType === 'jobseeker') {
            if (cvSection) cvSection.style.display = 'block';
            if (companySection) companySection.style.display = 'none';
            if (adminSection) adminSection.style.display = 'none';
        } else if (userType === 'company') {
            if (cvSection) cvSection.style.display = 'none';
            if (companySection) companySection.style.display = 'block';
            if (adminSection) adminSection.style.display = 'none';
        } else if (userType === 'admin') {
            if (cvSection) cvSection.style.display = 'none';
            if (companySection) companySection.style.display = 'none';
            if (adminSection) adminSection.style.display = 'block';
        }
        
        // Update active link based on current page
        this.updateActiveLink();
    }
    
    updateActiveLink() {
        const currentPath = window.location.pathname;
        const links = this.sidebar.querySelectorAll('.sidebar-link');
        
        links.forEach(link => {
            const href = link.getAttribute('href');
            if (href && currentPath.includes(href)) {
                link.classList.add('active');
            } else {
                link.classList.remove('active');
            }
        });
    }
    
    handleLinkClick(link) {
        // Remove active class from all links
        const links = this.sidebar.querySelectorAll('.sidebar-link');
        links.forEach(l => l.classList.remove('active'));
        
        // Add active class to clicked link
        link.classList.add('active');
        
        // Hide sidebar on mobile after click
        if (window.innerWidth <= 1024) {
            this.hide();
        }
    }
    
    // Public methods
    static initialize() {
        return new SidebarManager();
    }
}

// Initialize sidebar when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    SidebarManager.initialize();
});

// Export for manual initialization
export default SidebarManager;