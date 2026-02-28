(function() {
    const ALLOWED_THEMES = [
        'light',
        'dark',
        'bumblebee',
        'retro',
        'cyberpunk',
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

    function setSelectedThemeInput(theme) {
        const radio = document.querySelector(`input[name="theme-dropdown"][value="${theme}"]`);
        if (radio) {
            radio.checked = true;
        }
    }
    
    function setTheme(theme) {
        document.body.setAttribute('data-theme', theme);
        localStorage.setItem('theme', theme);
        setSelectedThemeInput(theme)
    }
    
    const theme = getStoredTheme();
    setTheme(theme);
    
    document.addEventListener('DOMContentLoaded', function() {
        setSelectedThemeInput(theme);

        const themeInputs = document.querySelectorAll('input[name="theme-dropdown"]');
        themeInputs.forEach(input => {
            input.addEventListener('change', function(e) {
                const selectedTheme = e.target.value;
                setTheme(selectedTheme);
            });
        });
    });
})()
