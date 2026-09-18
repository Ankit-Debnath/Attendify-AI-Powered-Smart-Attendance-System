
function showToast(message, type = 'info') {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        document.body.appendChild(container);
    }
    
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <div>${message}</div>
        <button class="toast-close" onclick="this.parentElement.remove()">&times;</button>
    `;
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'fadeOut 0.3s forwards';
        setTimeout(() => toast.remove(), 300);
    }, 5000);
}

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    if(sidebar) sidebar.classList.toggle('open');
    if(overlay) overlay.classList.toggle('open');
}

function togglePassword(inputId) {
    const input = document.getElementById(inputId);
    if(input) {
        if (input.type === 'password') {
            input.type = 'text';
        } else {
            input.type = 'password';
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    // Process server-side flash messages
    const flashMessages = document.querySelectorAll('.server-flash');
    flashMessages.forEach(msg => {
        let type = msg.dataset.category;
        if(type === 'message') type = 'info';
        showToast(msg.dataset.message, type);
        msg.remove();
    });
});
