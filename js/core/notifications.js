import Config from './config.js';

class NotificationManager {
    constructor() {
        this.container = null;
        this.notifications = [];
        this.maxNotifications = Config.NOTIFICATIONS.maxNotifications;
        this.init();
    }
    
    init() {
        this.createContainer();
        this.setupEventListeners();
    }
    
    createContainer() {
        this.container = document.createElement('div');
        this.container.id = 'notification-container';
        this.container.className = `notification-container ${Config.NOTIFICATIONS.position}`;
        document.body.appendChild(this.container);
    }
    
    setupEventListeners() {
        // Auto-remove notifications on click
        document.addEventListener('click', (e) => {
            if (e.target.closest('.notification')) {
                const notification = e.target.closest('.notification');
                this.removeNotification(notification.dataset.id);
            }
        });
    }
    
    show(message, type = 'info', duration = Config.NOTIFICATIONS.duration) {
        const id = Date.now().toString();
        const notification = this.createNotification(id, message, type, duration);
        
        // Add to container
        this.container.appendChild(notification);
        this.notifications.push({ id, element: notification });
        
        // Remove oldest notification if limit exceeded
        if (this.notifications.length > this.maxNotifications) {
            const oldest = this.notifications.shift();
            this.removeNotification(oldest.id);
        }
        
        // Auto-remove after duration
        if (duration > 0) {
            setTimeout(() => {
                this.removeNotification(id);
            }, duration);
        }
        
        // Animate in
        setTimeout(() => {
            notification.classList.add('show');
        }, 10);
        
        return id;
    }
    
    createNotification(id, message, type, duration) {
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.dataset.id = id;
        
        const icon = this.getIcon(type);
        const progressBar = duration > 0 ? '<div class="notification-progress"></div>' : '';
        
        notification.innerHTML = `
            <div class="notification-icon">${icon}</div>
            <div class="notification-content">
                <div class="notification-message">${message}</div>
            </div>
            <button class="notification-close">
                <i class="fas fa-times"></i>
            </button>
            ${progressBar}
        `;
        
        // Add progress bar animation
        if (duration > 0) {
            const progressBar = notification.querySelector('.notification-progress');
            if (progressBar) {
                progressBar.style.animationDuration = `${duration}ms`;
            }
        }
        
        return notification;
    }
    
    getIcon(type) {
        const icons = {
            success: '<i class="fas fa-check-circle"></i>',
            error: '<i class="fas fa-exclamation-circle"></i>',
            warning: '<i class="fas fa-exclamation-triangle"></i>',
            info: '<i class="fas fa-info-circle"></i>'
        };
        return icons[type] || icons.info;
    }
    
    removeNotification(id) {
        const index = this.notifications.findIndex(n => n.id === id);
        if (index === -1) return;
        
        const notification = this.notifications[index].element;
        notification.classList.remove('show');
        notification.classList.add('hide');
        
        // Remove from DOM after animation
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
            this.notifications.splice(index, 1);
        }, 300);
    }
    
    clearAll() {
        this.notifications.forEach(notification => {
            this.removeNotification(notification.id);
        });
    }
    
    // Shortcut methods
    success(message, duration) {
        return this.show(message, 'success', duration);
    }
    
    error(message, duration) {
        return this.show(message, 'error', duration);
    }
    
    warning(message, duration) {
        return this.show(message, 'warning', duration);
    }
    
    info(message, duration) {
        return this.show(message, 'info', duration);
    }
}

// Global notification function
const notificationManager = new NotificationManager();

export function showNotification(message, type = 'info', duration) {
    return notificationManager.show(message, type, duration);
}

export function showSuccess(message, duration) {
    return notificationManager.success(message, duration);
}

export function showError(message, duration) {
    return notificationManager.error(message, duration);
}

export function showWarning(message, duration) {
    return notificationManager.warning(message, duration);
}

export function showInfo(message, duration) {
    return notificationManager.info(message, duration);
}

export function clearAllNotifications() {
    notificationManager.clearAll();
}

// Add CSS for notifications
const style = document.createElement('style');
style.textContent = `
.notification-container {
    position: fixed;
    z-index: 9999;
    pointer-events: none;
}

.notification-container.top-right {
    top: 20px;
    right: 20px;
}

.notification-container.top-left {
    top: 20px;
    left: 20px;
}

.notification-container.bottom-right {
    bottom: 20px;
    right: 20px;
}

.notification-container.bottom-left {
    bottom: 20px;
    left: 20px;
}

.notification {
    position: relative;
    display: flex;
    align-items: flex-start;
    gap: 12px;
    width: 350px;
    padding: 16px;
    margin-bottom: 10px;
    background: white;
    border-radius: 8px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    pointer-events: auto;
    transform: translateX(400px);
    opacity: 0;
    transition: all 0.3s ease;
}

.notification.show {
    transform: translateX(0);
    opacity: 1;
}

.notification.hide {
    transform: translateX(400px);
    opacity: 0;
}

.notification-icon {
    font-size: 20px;
    flex-shrink: 0;
}

.notification-success .notification-icon {
    color: #10b981;
}

.notification-error .notification-icon {
    color: #ef4444;
}

.notification-warning .notification-icon {
    color: #f59e0b;
}

.notification-info .notification-icon {
    color: #3b82f6;
}

.notification-content {
    flex: 1;
    min-width: 0;
}

.notification-message {
    font-size: 14px;
    line-height: 1.5;
    color: #1f2937;
}

.notification-close {
    width: 24px;
    height: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
    border: none;
    background: none;
    color: #9ca3af;
    cursor: pointer;
    border-radius: 4px;
    flex-shrink: 0;
    transition: all 0.2s ease;
}

.notification-close:hover {
    color: #6b7280;
    background: #f3f4f6;
}

.notification-progress {
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    height: 3px;
    background: #3b82f6;
    border-radius: 0 0 8px 8px;
    transform-origin: left;
    animation: notification-progress linear forwards;
}

@keyframes notification-progress {
    from { transform: scaleX(1); }
    to { transform: scaleX(0); }
}

@media (max-width: 640px) {
    .notification {
        width: calc(100vw - 40px);
        max-width: 350px;
    }
    
    .notification-container.top-right,
    .notification-container.top-left,
    .notification-container.bottom-right,
    .notification-container.bottom-left {
        right: 20px;
        left: 20px;
    }
}
`;
document.head.appendChild(style);
