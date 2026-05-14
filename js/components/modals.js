import { showNotification } from '../core/notifications.js';

class ModalManager {
    constructor() {
        this.modals = new Map();
        this.activeModal = null;
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        this.setupEscapeKey();
    }
    
    setupEventListeners() {
        // Close modal on backdrop click
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('modal-backdrop')) {
                this.closeActiveModal();
            }
        });
        
        // Close modal on close button click
        document.addEventListener('click', (e) => {
            if (e.target.closest('.modal-close')) {
                this.closeActiveModal();
            }
        });
    }
    
    setupEscapeKey() {
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.activeModal) {
                this.closeActiveModal();
            }
        });
    }
    
    createModal(config) {
        const modalId = `modal-${Date.now()}`;
        const modal = document.createElement('div');
        modal.className = 'modal';
        modal.id = modalId;
        
        if (config.size) {
            modal.classList.add(`modal-${config.size}`);
        }
        
        if (config.className) {
            modal.classList.add(config.className);
        }
        
        // Create modal HTML
        modal.innerHTML = `
            <div class="modal-backdrop"></div>
            <div class="modal-dialog">
                <div class="modal-header">
                    <h3 class="modal-title">${config.title || ''}</h3>
                    <button class="modal-close">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
                <div class="modal-body">
                    ${config.content || ''}
                </div>
                ${config.footer ? `
                <div class="modal-footer">
                    ${config.footer}
                </div>
                ` : ''}
            </div>
        `;
        
        // Store modal configuration
        this.modals.set(modalId, {
            element: modal,
            config: config,
            onClose: config.onClose
        });
        
        document.body.appendChild(modal);
        
        return modalId;
    }
    
    show(modalId) {
        const modalData = this.modals.get(modalId);
        if (!modalData) return false;
        
        // Close any active modal
        if (this.activeModal) {
            this.closeActiveModal();
        }
        
        // Show modal
        modalData.element.classList.add('show');
        modalData.element.querySelector('.modal-backdrop').classList.add('show');
        this.activeModal = modalId;
        
        // Focus first focusable element
        setTimeout(() => {
            const focusable = modalData.element.querySelector('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
            if (focusable) focusable.focus();
        }, 100);
        
        // Call onShow callback
        if (modalData.config.onShow) {
            modalData.config.onShow();
        }
        
        return true;
    }
    
    close(modalId) {
        const modalData = this.modals.get(modalId);
        if (!modalData) return false;
        
        modalData.element.classList.remove('show');
        modalData.element.querySelector('.modal-backdrop').classList.remove('show');
        
        // Remove from DOM after animation
        setTimeout(() => {
            if (modalData.element.parentNode) {
                modalData.element.parentNode.removeChild(modalData.element);
            }
            this.modals.delete(modalId);
            
            if (this.activeModal === modalId) {
                this.activeModal = null;
            }
            
            // Call onClose callback
            if (modalData.onClose) {
                modalData.onClose();
            }
        }, 300);
        
        return true;
    }
    
    closeActiveModal() {
        if (this.activeModal) {
            this.close(this.activeModal);
        }
    }
    
    // Predefined modal types
    
    confirm(options) {
        return new Promise((resolve) => {
            const modalId = this.createModal({
                title: options.title || 'Confirm Action',
                size: 'sm',
                className: 'confirmation-modal warning',
                content: `
                    <div class="modal-icon">
                        <i class="fas fa-exclamation-triangle"></i>
                    </div>
                    <div class="modal-message">
                        ${options.message || 'Are you sure you want to perform this action?'}
                    </div>
                `,
                footer: `
                    <button class="btn btn-secondary btn-cancel">Cancel</button>
                    <button class="btn btn-danger btn-confirm">${options.confirmText || 'Confirm'}</button>
                `,
                onShow: () => {
                    const modal = document.getElementById(modalId);
                    modal.querySelector('.btn-cancel').addEventListener('click', () => {
                        this.close(modalId);
                        resolve(false);
                    });
                    modal.querySelector('.btn-confirm').addEventListener('click', () => {
                        this.close(modalId);
                        resolve(true);
                    });
                }
            });
            
            this.show(modalId);
        });
    }
    
    alert(options) {
        return new Promise((resolve) => {
            const modalId = this.createModal({
                title: options.title || 'Alert',
                size: 'sm',
                className: `alert-modal alert-${options.type || 'info'}`,
                content: `
                    <div class="alert-icon">
                        <i class="fas fa-${this.getAlertIcon(options.type)}"></i>
                    </div>
                    <div class="alert-content">
                        <h4>${options.title || 'Alert'}</h4>
                        <p>${options.message || ''}</p>
                    </div>
                `,
                footer: `
                    <button class="btn btn-primary btn-ok">OK</button>
                `,
                onShow: () => {
                    const modal = document.getElementById(modalId);
                    modal.querySelector('.btn-ok').addEventListener('click', () => {
                        this.close(modalId);
                        resolve();
                    });
                }
            });
            
            this.show(modalId);
        });
    }
    
    prompt(options) {
        return new Promise((resolve) => {
            const inputType = options.type || 'text';
            const placeholder = options.placeholder || '';
            const defaultValue = options.defaultValue || '';
            
            const modalId = this.createModal({
                title: options.title || 'Input Required',
                size: 'sm',
                content: `
                    <div class="form-group">
                        <label class="form-label">${options.label || 'Enter value:'}</label>
                        <${inputType === 'textarea' ? 'textarea' : 'input'} 
                            type="${inputType === 'textarea' ? 'text' : inputType}"
                            class="form-control prompt-input"
                            placeholder="${placeholder}"
                            value="${defaultValue}"
                            ${options.required ? 'required' : ''}
                            ${inputType === 'textarea' ? 'rows="4"' : ''}
                        >
                        ${options.helpText ? `<div class="form-text">${options.helpText}</div>` : ''}
                    </div>
                `,
                footer: `
                    <button class="btn btn-secondary btn-cancel">Cancel</button>
                    <button class="btn btn-primary btn-submit">${options.submitText || 'Submit'}</button>
                `,
                onShow: () => {
                    const modal = document.getElementById(modalId);
                    const input = modal.querySelector('.prompt-input');
                    
                    // Focus input
                    setTimeout(() => input.focus(), 100);
                    
                    modal.querySelector('.btn-cancel').addEventListener('click', () => {
                        this.close(modalId);
                        resolve(null);
                    });
                    
                    modal.querySelector('.btn-submit').addEventListener('click', () => {
                        const value = inputType === 'textarea' ? input.value : input.value;
                        this.close(modalId);
                        resolve(value);
                    });
                    
                    // Submit on Enter key
                    input.addEventListener('keypress', (e) => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                            e.preventDefault();
                            modal.querySelector('.btn-submit').click();
                        }
                    });
                }
            });
            
            this.show(modalId);
        });
    }
    
    loading(options = {}) {
        const modalId = this.createModal({
            title: options.title || 'Loading...',
            size: 'sm',
            className: 'loading-modal',
            content: `
                <div class="loading-spinner"></div>
                <p>${options.message || 'Please wait...'}</p>
            `,
            footer: options.showCancel ? `
                <button class="btn btn-secondary btn-cancel">Cancel</button>
            ` : ''
        });
        
        this.show(modalId);
        
        return {
            close: () => this.close(modalId),
            update: (newOptions) => {
                const modalData = this.modals.get(modalId);
                if (modalData) {
                    if (newOptions.message) {
                        const messageEl = modalData.element.querySelector('p');
                        if (messageEl) messageEl.textContent = newOptions.message;
                    }
                    if (newOptions.title) {
                        const titleEl = modalData.element.querySelector('.modal-title');
                        if (titleEl) titleEl.textContent = newOptions.title;
                    }
                }
            }
        };
    }
    
    form(options) {
        return new Promise((resolve) => {
            const modalId = this.createModal({
                title: options.title || 'Form',
                size: options.size || 'md',
                className: 'form-modal',
                content: options.content || '',
                footer: `
                    <button class="btn btn-secondary btn-cancel">Cancel</button>
                    <button class="btn btn-primary btn-submit" type="submit">${options.submitText || 'Submit'}</button>
                `,
                onShow: () => {
                    const modal = document.getElementById(modalId);
                    const form = modal.querySelector('form');
                    
                    if (form) {
                        form.addEventListener('submit', (e) => {
                            e.preventDefault();
                            const formData = new FormData(form);
                            const data = Object.fromEntries(formData);
                            this.close(modalId);
                            resolve(data);
                        });
                        
                        modal.querySelector('.btn-submit').addEventListener('click', () => {
                            form.requestSubmit();
                        });
                    }
                    
                    modal.querySelector('.btn-cancel').addEventListener('click', () => {
                        this.close(modalId);
                        resolve(null);
                    });
                }
            });
            
            this.show(modalId);
        });
    }
    
    // Helper methods
    getAlertIcon(type) {
        const icons = {
            success: 'check-circle',
            error: 'exclamation-circle',
            warning: 'exclamation-triangle',
            info: 'info-circle'
        };
        return icons[type] || 'info-circle';
    }
}

// Global modal manager instance
const modalManager = new ModalManager();

// Export convenience functions
export function showModal(config) {
    const modalId = modalManager.createModal(config);
    return modalManager.show(modalId);
}

export function closeModal(modalId) {
    return modalManager.close(modalId);
}

export function closeAllModals() {
    modalManager.closeActiveModal();
}

export function showConfirm(options) {
    return modalManager.confirm(options);
}

export function showAlert(options) {
    return modalManager.alert(options);
}

export function showPrompt(options) {
    return modalManager.prompt(options);
}

export function showLoading(options) {
    return modalManager.loading(options);
}

export function showForm(options) {
    return modalManager.form(options);
}

// Export modal manager for advanced usage
export default modalManager;