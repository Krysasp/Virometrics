// app.js - Main application logic for Virometrics

// Global state
let isDarkMode = false;

// Initialize app
document.addEventListener('DOMContentLoaded', async function() {
    console.log('Virometrics Dashboard initializing...');

    // Load tool data
    const tools = await loadToolData();

    if (tools && tools.length > 0) {
        updateStats(tools);
        renderAllCharts();
        initToolsTable();
        populateFilters();
        setupEventListeners();
        updateStatsSummary(tools.length);
        
        // Initialize network visualization
        setTimeout(initNetworkVisualization, 500);
        
        // Initialize recommendation engine
        setTimeout(initRecommendationEngine, 1000);
    } else {
        console.error('No tool data loaded');
        document.getElementById('stats-summary').textContent = 'Error loading data';
    }

    // Initialize theme
    initTheme();
});

// Update header stats
function updateStats(tools) {
    document.getElementById('stat-total').textContent = tools.length;
    document.getElementById('stat-categories').textContent = Object.keys(virometricsData.categories).length;

    const langCount = Object.keys(virometricsData.languages).length;
    document.getElementById('stat-languages').textContent = langCount;

    const doiCount = tools.filter(t => t.doi).length;
    document.getElementById('stat-doi').textContent = doiCount;
}

// Update navbar summary
function updateStatsSummary(totalTools) {
    const el = document.getElementById('stats-summary');
    if (el) {
        el.innerHTML = `<i class="bi bi-tools"></i> ${totalTools} tools | ${Object.keys(virometricsData.categories).length} categories`;
    }
}

// Setup event listeners
function setupEventListeners() {
    // Filters
    $('#filter-category').on('change', applyFilters);
    $('#filter-language').on('change', applyFilters);
    $('#filter-pkgmgr').on('change', applyFilters);
    $('#search-box').on('keyup', applyFilters);

    // Export button
    $('#exportCSV').on('click', exportTableToCSV);

    // Theme toggle
    $('#themeToggle').on('click', toggleTheme);
    
    // Regex toggle
    $('#regexToggle').on('click', toggleRegexMode);
}

// Theme management
function initTheme() {
    const savedTheme = localStorage.getItem('virometrics-theme');
    if (savedTheme === 'dark') {
        enableDarkMode();
    }
}

function toggleTheme() {
    if (isDarkMode) {
        disableDarkMode();
    } else {
        enableDarkMode();
    }
}

function enableDarkMode() {
    document.documentElement.setAttribute('data-theme', 'dark');
    document.body.classList.add('dark-mode');
    $('#themeToggle i').removeClass('bi-moon').addClass('bi-sun');
    isDarkMode = true;
    localStorage.setItem('virometrics-theme', 'dark');
}

function disableDarkMode() {
    document.documentElement.removeAttribute('data-theme');
    document.body.classList.remove('dark-mode');
    $('#themeToggle i').removeClass('bi-sun').addClass('bi-moon');
    isDarkMode = false;
    localStorage.setItem('virometrics-theme', 'light');
}

// Make functions available globally
window.applyFilters = applyFilters;
window.exportTableToCSV = exportTableToCSV;
window.toggleTheme = toggleTheme;
window.toggleRegexMode = toggleRegexMode;

// Regex mode state
let isRegexMode = false;

function toggleRegexMode() {
    isRegexMode = !isRegexMode;
    const btn = $('#regexToggle');
    const icon = btn.find('i');
    
    if (isRegexMode) {
        btn.addClass('active');
        icon.removeClass('bi-regex').addClass('bi-regex-fill');
        $('#search-box').attr('placeholder', 'Search with regex /pattern/');
    } else {
        btn.removeClass('active');
        icon.removeClass('bi-regex-fill').addClass('bi-regex');
        $('#search-box').attr('placeholder', 'Search tools...');
    }
    
    // Re-apply filters with new mode
    applyFilters();
}
