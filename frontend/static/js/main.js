/* ═══════════════════════════════════════════════════════════
   GymDesk — Core JavaScript
   ═══════════════════════════════════════════════════════════ */

// Auto-dismiss flash messages
document.addEventListener('DOMContentLoaded', () => {
    const flashes = document.querySelectorAll('.flash-message');
    flashes.forEach((flash, i) => {
        setTimeout(() => {
            flash.style.animation = 'slideOut 0.3s ease-out forwards';
            setTimeout(() => flash.remove(), 300);
        }, 4000 + (i * 500));
    });

    // Initialize Lucide icons if loaded
    if (typeof lucide !== 'undefined') {
        try { lucide.createIcons(); } catch (e) { }
    }
});

// Confirm dialog helper
function confirmAction(message) {
    return confirm(message);
}
