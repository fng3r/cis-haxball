function setTheme(theme) {
    document.body.setAttribute('data-theme', theme);
    const radio = document.querySelector(`input[name="theme-dropdown"][value="${theme}"]`);
    if (radio) {
        radio.checked = true;
    }
}

// Set theme immediately after body is rendered
const savedTheme = localStorage.getItem('theme') || 'light';
document.body.setAttribute('data-theme', savedTheme);

// Update radio button state as soon as DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    const radio = document.querySelector(`input[name="theme-dropdown"][value="${savedTheme}"]`);
    if (radio) {
        radio.checked = true;
    }

    const themeInputs = document.querySelectorAll('input[name="theme-dropdown"]');
    themeInputs.forEach(input => {
        input.addEventListener('change', function(e) {
            const selectedTheme = e.target.value;
            localStorage.setItem('theme', selectedTheme);
            setTheme(selectedTheme);
        });
    });
});
