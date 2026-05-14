import Config from '../core/config.js';

class ChartManager {
    constructor() {
        this.charts = new Map();
        this.colors = Config.COLORS;
        this.init();
    }
    
    init() {
        // Initialize Chart.js if available
        if (typeof Chart !== 'undefined') {
            this.setupChartDefaults();
        }
    }
    
    setupChartDefaults() {
        // Chart.js defaults
        Chart.defaults.font.family = "'Inter', system-ui, -apple-system, sans-serif";
        Chart.defaults.color = Config.colors.gray[600];
        Chart.defaults.plugins.legend.display = false;
        Chart.defaults.plugins.tooltip.backgroundColor = 'rgba(0, 0, 0, 0.8)';
        Chart.defaults.plugins.tooltip.titleFont = { size: 12 };
        Chart.defaults.plugins.tooltip.bodyFont = { size: 12 };
        Chart.defaults.plugins.tooltip.padding = 8;
        Chart.defaults.plugins.tooltip.cornerRadius = 4;
    }
    
    createLineChart(canvasId, data, options = {}) {
        if (typeof Chart === 'undefined') {
            console.warn('Chart.js is not loaded');
            return null;
        }
        
        const ctx = document.getElementById(canvasId)?.getContext('2d');
        if (!ctx) return null;
        
        const defaultOptions = {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                }
            },
            scales: {
                x: {
                    grid: {
                        display: false
                    }
                },
                y: {
                    beginAtZero: true,
                    grid: {
                        borderDash: [2, 2]
                    }
                }
            }
        };
        
        const chart = new Chart(ctx, {
            type: 'line',
            data: data,
            options: { ...defaultOptions, ...options }
        });
        
        this.charts.set(canvasId, chart);
        return chart;
    }
    
    createBarChart(canvasId, data, options = {}) {
        if (typeof Chart === 'undefined') {
            console.warn('Chart.js is not loaded');
            return null;
        }
        
        const ctx = document.getElementById(canvasId)?.getContext('2d');
        if (!ctx) return null;
        
        const defaultOptions = {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                }
            },
            scales: {
                x: {
                    grid: {
                        display: false
                    }
                },
                y: {
                    beginAtZero: true,
                    grid: {
                        borderDash: [2, 2]
                    }
                }
            }
        };
        
        const chart = new Chart(ctx, {
            type: 'bar',
            data: data,
            options: { ...defaultOptions, ...options }
        });
        
        this.charts.set(canvasId, chart);
        return chart;
    }
    
    createPieChart(canvasId, data, options = {}) {
        if (typeof Chart === 'undefined') {
            console.warn('Chart.js is not loaded');
            return null;
        }
        
        const ctx = document.getElementById(canvasId)?.getContext('2d');
        if (!ctx) return null;
        
        const defaultOptions = {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'right',
                }
            }
        };
        
        const chart = new Chart(ctx, {
            type: 'pie',
            data: data,
            options: { ...defaultOptions, ...options }
        });
        
        this.charts.set(canvasId, chart);
        return chart;
    }
    
    createDoughnutChart(canvasId, data, options = {}) {
        if (typeof Chart === 'undefined') {
            console.warn('Chart.js is not loaded');
            return null;
        }
        
        const ctx = document.getElementById(canvasId)?.getContext('2d');
        if (!ctx) return null;
        
        const defaultOptions = {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'right',
                }
            },
            cutout: '60%'
        };
        
        const chart = new Chart(ctx, {
            type: 'doughnut',
            data: data,
            options: { ...defaultOptions, ...options }
        });
        
        this.charts.set(canvasId, chart);
        return chart;
    }
    
    createRadarChart(canvasId, data, options = {}) {
        if (typeof Chart === 'undefined') {
            console.warn('Chart.js is not loaded');
            return null;
        }
        
        const ctx = document.getElementById(canvasId)?.getContext('2d');
        if (!ctx) return null;
        
        const defaultOptions = {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                }
            },
            scales: {
                r: {
                    beginAtZero: true,
                    ticks: {
                        display: false
                    }
                }
            }
        };
        
        const chart = new Chart(ctx, {
            type: 'radar',
            data: data,
            options: { ...defaultOptions, ...options }
        });
        
        this.charts.set(canvasId, chart);
        return chart;
    }
    
    // Helper methods for common chart data
    
    createJobTrendsData(labels, data) {
        return {
            labels: labels,
            datasets: [{
                label: 'Job Postings',
                data: data,
                borderColor: this.colors.primary,
                backgroundColor: 'rgba(59, 130, 246, 0.1)',
                borderWidth: 2,
                tension: 0.4,
                fill: true
            }]
        };
    }
    
    createApplicationStatusData(labels, data) {
        return {
            labels: labels,
            datasets: [{
                data: data,
                backgroundColor: [
                    this.colors.primary,
                    this.colors.success,
                    this.colors.warning,
                    this.colors.danger,
                    this.colors.gray[400]
                ],
                borderWidth: 0
            }]
        };
    }
    
    createSkillsDemandData(labels, data) {
        return {
            labels: labels,
            datasets: [{
                label: 'Skill Demand',
                data: data,
                backgroundColor: this.colors.primary,
                borderColor: this.colors.primary,
                borderWidth: 1
            }]
        };
    }
    
    createSalaryDistributionData(labels, data) {
        return {
            labels: labels,
            datasets: [{
                label: 'Salary Range',
                data: data,
                backgroundColor: 'rgba(59, 130, 246, 0.5)',
                borderColor: this.colors.primary,
                borderWidth: 1
            }]
        };
    }
    
    createMatchScoreData(score) {
        return {
            datasets: [{
                data: [score, 100 - score],
                backgroundColor: [
                    this.colors.primary,
                    this.colors.gray[200]
                ],
                borderWidth: 0
            }]
        };
    }
    
    // Update chart data
    updateChart(canvasId, newData) {
        const chart = this.charts.get(canvasId);
        if (chart) {
            chart.data = newData;
            chart.update();
        }
    }
    
    // Destroy chart
    destroyChart(canvasId) {
        const chart = this.charts.get(canvasId);
        if (chart) {
            chart.destroy();
            this.charts.delete(canvasId);
        }
    }
    
    // Destroy all charts
    destroyAllCharts() {
        this.charts.forEach((chart, canvasId) => {
            chart.destroy();
        });
        this.charts.clear();
    }
    
    // Responsive chart resizing
    setupResponsiveCharts() {
        window.addEventListener('resize', () => {
            this.charts.forEach(chart => {
                chart.resize();
            });
        });
    }
}

// Global chart manager instance
const chartManager = new ChartManager();

// Export convenience functions
export function createLineChart(canvasId, data, options) {
    return chartManager.createLineChart(canvasId, data, options);
}

export function createBarChart(canvasId, data, options) {
    return chartManager.createBarChart(canvasId, data, options);
}

export function createPieChart(canvasId, data, options) {
    return chartManager.createPieChart(canvasId, data, options);
}

export function createDoughnutChart(canvasId, data, options) {
    return chartManager.createDoughnutChart(canvasId, data, options);
}

export function createRadarChart(canvasId, data, options) {
    return chartManager.createRadarChart(canvasId, data, options);
}

export function updateChart(canvasId, newData) {
    return chartManager.updateChart(canvasId, newData);
}

export function destroyChart(canvasId) {
    return chartManager.destroyChart(canvasId);
}

// Export chart manager for advanced usage
export default chartManager;