// browse.js - Browse all tools with card layout

let currentTools = [];

document.addEventListener('DOMContentLoaded', async function() {
    initTheme();
    await loadToolData();
    populateFilters();
    renderToolsGrid(virometricsData.tools);
    setupEventListeners();
});

function populateFilters() {
    // Categories
    const catSelect = document.getElementById('filter-category');
    Object.keys(virometricsData.categories).sort().forEach(cat => {
        catSelect.innerHTML += `<option value="${cat}">${cat} (${virometricsData.categories[cat]})</option>`;
    });

    // Subcategories - we need to extract from tools
    const subCats = new Set();
    virometricsData.tools.forEach(t => {
        if (t.subcategory) subCats.add(t.subcategory);
    });
    const subcatSelect = document.getElementById('filter-subcategory');
    Array.from(subCats).sort().forEach(sub => {
        subcatSelect.innerHTML += `<option value="${sub}">${sub}</option>`;
    });

    // Languages
    const langSelect = document.getElementById('filter-language');
    Object.entries(virometricsData.languages)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 20)
        .forEach(([lang, count]) => {
            langSelect.innerHTML += `<option value="${lang}">${lang} (${count})</option>`;
        });

    // Package managers
    const pkgSelect = document.getElementById('filter-pkgmgr');
    Object.keys(virometricsData.packageManagers).sort().forEach(pkg => {
        pkgSelect.innerHTML += `<option value="${pkg}">${pkg} (${virometricsData.packageManagers[pkg]})</option>`;
    });
    pkgSelect.innerHTML += `<option value="Unknown">Unknown</option>`;
}

function setupEventListeners() {
    document.getElementById('filter-category').addEventListener('change', applyBrowseFilters);
    document.getElementById('filter-subcategory').addEventListener('change', applyBrowseFilters);
    document.getElementById('filter-language').addEventListener('change', applyBrowseFilters);
    document.getElementById('filter-pkgmgr').addEventListener('change', applyBrowseFilters);
    document.getElementById('search-box').addEventListener('keyup', applyBrowseFilters);
    document.getElementById('exportCSV').addEventListener('click', exportCSV);
}

function applyBrowseFilters() {
    const category = document.getElementById('filter-category').value;
    const subcategory = document.getElementById('filter-subcategory').value;
    const language = document.getElementById('filter-language').value;
    const packageMgr = document.getElementById('filter-pkgmgr').value;
    const search = document.getElementById('search-box').value.toLowerCase();

    const filters = { category, subcategory, language, packageManager: packageMgr, search };
    const filtered = filterTools(filters);

    renderToolsGrid(filtered);
}

function renderToolsGrid(tools) {
    const grid = document.getElementById('tools-grid');
    const noResults = document.getElementById('no-results');
    const resultCount = document.getElementById('result-count');

    resultCount.textContent = `${tools.length} tool(s) found`;

    if (tools.length === 0) {
        grid.innerHTML = '';
        noResults.style.display = 'block';
        return;
    }

    noResults.style.display = 'none';

    grid.innerHTML = tools.map(tool => `
        <div class="col-xl-3 col-lg-4 col-md-6 mb-3">
            <div class="card tool-card h-100">
                <div class="card-body">
                    <h5 class="card-title">
                        <a href="tool.html?name=${encodeURIComponent(tool.name)}" class="text-decoration-none">
                            ${tool.name}
                        </a>
                    </h5>
                    <p class="card-text text-muted small mb-2">${tool.category || 'Unknown'}</p>
                    <p class="card-text small">${(tool.description || 'No description').substring(0, 100)}${(tool.description || '').length > 100 ? '...' : ''}</p>
                    <div class="mt-auto">
                        ${tool.package_manager ? `<span class="badge bg-success">${tool.package_manager}</span>` : ''}
                        ${tool.github_stars ? `<span class="badge bg-warning text-dark"><i class="bi bi-star-fill"></i> ${tool.github_stars}</span>` : ''}
                        ${Array.isArray(tool.languages) ? tool.languages.slice(0, 3).map(l => `<span class="badge bg-info">${l}</span>`).join(' ') : ''}
                    </div>
                </div>
            </div>
        </div>
    `).join('');
}

function clearAllFilters() {
    document.getElementById('filter-category').value = '';
    document.getElementById('filter-subcategory').value = '';
    document.getElementById('filter-language').value = '';
    document.getElementById('filter-pkgmgr').value = '';
    document.getElementById('search-box').value = '';
    applyBrowseFilters();
}
window.clearAllFilters = clearAllFilters;

function exportCSV() {
    const filtered = filterTools({
        category: document.getElementById('filter-category').value,
        subcategory: document.getElementById('filter-subcategory').value,
        language: document.getElementById('filter-language').value,
        packageManager: document.getElementById('filter-pkgmgr').value,
        search: document.getElementById('search-box').value
    });

    const headers = ['Name', 'Category', 'Subcategory', 'Stars', 'DOI', 'URL'];
    const rows = [headers.join(',')];

    filtered.forEach(tool => {
        const escapedName = `"${(tool.name || '').replace(/"/g, '""')}"`;
        const escapedURL = `"${(tool.url || '').replace(/"/g, '""')}"`;
        rows.push([escapedName, tool.category || '', tool.subcategory || '', tool.github_stars || 0, tool.doi || '', escapedURL].join(','));
    });

    const csv = rows.join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'virometrics_tools.csv';
    a.click();
    URL.revokeObjectURL(url);
}
