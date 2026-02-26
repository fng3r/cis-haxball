(function() {
    const ALLOWED_THEMES = [
        'light',
        'dark',
        'bumblebee',
        'emerald',
        'retro',
        'halloween',
        'garden',
        'forest',
        'lofi',
        'luxury',
        'dracula',
        'cmyk',
        'autumn',
        'business',
        'night',
        'coffee',
        'dim',
        'sunset',
    ];
    
    function getDefaultTheme() {
        if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
            return 'dark';
        }
        return 'light';
    }

    function getStoredTheme() {
        const savedTheme = localStorage.getItem('theme');
        if (!savedTheme || !ALLOWED_THEMES.includes(savedTheme)) {
            return getDefaultTheme();
        }

        return savedTheme;
    }
    
    function setTheme(theme) {
        document.body.setAttribute('data-theme', theme);
        localStorage.setItem('theme', theme);
    
        const radio = document.querySelector(`input[name="theme-dropdown"][value="${theme}"]`);
        if (radio) {
            radio.checked = true;
        }
    }
    
    const theme = getStoredTheme();
    setTheme(theme);
    
    document.addEventListener('DOMContentLoaded', function() {
        const radio = document.querySelector(`input[name="theme-dropdown"][value="${theme}"]`);
        if (radio) {
            radio.checked = true;
        }

        const themeInputs = document.querySelectorAll('input[name="theme-dropdown"]');
        themeInputs.forEach(input => {
            input.addEventListener('change', function(e) {
                const selectedTheme = e.target.value;
                setTheme(selectedTheme);
            });
        });
    });
})()
