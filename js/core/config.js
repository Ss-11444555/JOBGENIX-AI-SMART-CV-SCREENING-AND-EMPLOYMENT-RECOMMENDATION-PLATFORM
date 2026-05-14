// JobGenix AI Configuration
const Config = {
    // API Configuration - Updated to match Flask backend
    API_BASE_URL: 'http://localhost:8000',
    API_VERSION: '',
    
    // Application Configuration
    APP_NAME: 'JobGenix AI',
    APP_VERSION: '1.0.0',
    
    // Feature Flags
    FEATURES: {
        CV_UPLOAD: true,
        AI_RECOMMENDATIONS: true,
        INTERVIEW_SIMULATION: true,
        REAL_TIME_NOTIFICATIONS: true,
        MULTI_LANGUAGE: false,
        DARK_MODE: true,
    },
    
    // Limits
    LIMITS: {
        MAX_CV_SIZE: 5 * 1024 * 1024, // 5MB
        MAX_SKILLS_PER_USER: 20,
        MAX_JOBS_PER_PAGE: 20,
        MAX_CANDIDATES_PER_PAGE: 15,
        SESSION_TIMEOUT: 30 * 60 * 1000, // 30 minutes
    },
    
    // File Types
    ALLOWED_FILE_TYPES: [
        'application/pdf',
        'image/png'
    ],
    
    // Local Storage Keys
    STORAGE_KEYS: {
        AUTH_TOKEN: 'jobgenix_token',
        USER_DATA: 'jobgenix_user',
        USER_TYPE: 'jobgenix_user_type',
        THEME: 'jobgenix_theme',
        LANGUAGE: 'jobgenix_language',
        RECENT_SEARCHES: 'jobgenix_recent_searches',
        SAVED_JOBS: 'jobgenix_saved_jobs'
    },
    
    // Cache Settings
    CACHE: {
        JOBS_TTL: 5 * 60 * 1000, // 5 minutes
        USER_DATA_TTL: 30 * 60 * 1000, // 30 minutes
        RECOMMENDATIONS_TTL: 10 * 60 * 1000 // 10 minutes
    },

    // Notification defaults
    NOTIFICATIONS: {
        position: 'top-right',
        duration: 4000,
        maxNotifications: 3
    }
};

export default Config;
