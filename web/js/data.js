// data.js - Load and process tool data for Virometrics dashboard

let virometricsData = {
    tools: [],
    categories: {},
    languages: {},
    packageManagers: {},
    inputFormats: {}
};

// Load tool data from JSON file
async function loadToolData() {
    const paths = [
        '../data/tools_enhanced.json',  // When served from web/ with project root
        'data/tools_enhanced.json',    // When data is in web/data/
        '/data/tools_enhanced.json',    // Absolute path from project root
        'https://raw.githubusercontent.com/virometrics/data/main/tools_enhanced.json' // Fallback
    ];

    for (const path of paths) {
        try {
            const response = await fetch(path);
            if (!response.ok) continue;
            const tools = await response.json();
            virometricsData.tools = tools;
            processToolData();
            console.log(`Loaded ${tools.length} tools from ${path}`);
            return tools;
        } catch (error) {
            console.warn(`Failed to load from ${path}:`, error);
        }
    }

    console.error('Error loading tool data from all paths');
    return [];
}

// Process tool data to extract statistics
function processToolData() {
    const tools = virometricsData.tools;

    // Count by category
    virometricsData.categories = {};
    // Count by language
    virometricsData.languages = {};
    // Count by package manager
    virometricsData.packageManagers = {};
    // Count by input format
    virometricsData.inputFormats = {};

    tools.forEach(tool => {
        // Categories
        const cat = tool.category || 'Uncategorized';
        virometricsData.categories[cat] = (virometricsData.categories[cat] || 0) + 1;

        // Languages
        const langs = tool.languages;
        if (Array.isArray(langs)) {
            langs.forEach(lang => {
                virometricsData.languages[lang] = (virometricsData.languages[lang] || 0) + 1;
            });
        }

        // Package managers
        const pkgMgr = tool.package_manager || 'Unknown';
        virometricsData.packageManagers[pkgMgr] = (virometricsData.packageManagers[pkgMgr] || 0) + 1;

        // Input formats
        let inputs = tool.input_formats;
        if (typeof inputs === 'string') {
            try { inputs = JSON.parse(inputs); } catch(e) { inputs = []; }
        }
        if (Array.isArray(inputs)) {
            inputs.forEach(fmt => {
                virometricsData.inputFormats[fmt] = (virometricsData.inputFormats[fmt] || 0) + 1;
            });
        }
    });
}

// Get unique values for a field
function getUniqueValues(field) {
    const values = new Set();
    virometricsData.tools.forEach(tool => {
        if (Array.isArray(tool[field])) {
            tool[field].forEach(v => values.add(v));
        } else if (tool[field]) {
            values.add(tool[field]);
        }
    });
    return Array.from(values).sort();
}

// Filter tools based on criteria
function filterTools(filters) {
    return virometricsData.tools.filter(tool => {
        if (filters.category && tool.category !== filters.category) return false;
        if (filters.language) {
            const langs = Array.isArray(tool.languages) ? tool.languages : [];
            if (!langs.includes(filters.language)) return false;
        }
        if (filters.packageManager && tool.package_manager !== filters.packageManager) return false;
        if (filters.search) {
            const search = filters.search.toLowerCase();
            const name = (tool.name || '').toLowerCase();
            const desc = (tool.description || '').toLowerCase();
            if (!name.includes(search) && !desc.includes(search)) return false;
        }
        return true;
    });
}

// Get tool by ID or name
function getTool(identifier) {
    return virometricsData.tools.find(t =>
        t.name === identifier || t.id == identifier
    );
}
