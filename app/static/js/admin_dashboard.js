/**
 * ArogyaMaa Admin Dashboard JavaScript
 * 
 * Provides common functionality for all admin pages:
 * - Alert notifications
 * - Timestamp updates
 * - API error handling
 */

// Show alert notification
function showAlert(message, type = 'info') {
    const container = document.getElementById('alert-container');
    
    const alert = document.createElement('div');
    alert.className = `alert alert-${type}`;
    alert.textContent = message;
    
    container.appendChild(alert);
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
        alert.style.opacity = '0';
        setTimeout(() => alert.remove(), 300);
    }, 5000);
}

// Update last update timestamp
function updateTimestamp() {
    const timestampEl = document.getElementById('last-update');
    if (timestampEl) {
        const now = new Date();
        const timeString = now.toLocaleTimeString('en-US', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
        timestampEl.textContent = timeString;
    }
}

// Initialize timestamp on page load
document.addEventListener('DOMContentLoaded', () => {
    updateTimestamp();
});
