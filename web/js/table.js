// table.js - DataTable initialization and management

let toolsTable = null;

// Initialize DataTable
function initToolsTable() {
    if (toolsTable) {
        toolsTable.destroy();
    }

    toolsTable = $('#tools-table').DataTable({
        data: virometricsData.tools,
        columns: [
            {
                data: 'name',
                render: function(data, type, row) {
                    const url = row.url || '#';
                    return `<a href="tool.html?name=${encodeURIComponent(data)}" target="_blank">${data}</a>`;
                }
            },
            { data: 'category' },
            {
                data: 'languages',
                render: function(data) {
                    if (!Array.isArray(data)) return '-';
                    return data.slice(0, 3).map(l =>
                        `<span class="badge bg-secondary">${l}</span>`
                    ).join(' ');
                }
            },
            {
                data: 'github_stars',
                render: function(data) {
                    if (!data) return '0';
                    return `<i class="bi bi-star-fill text-warning"></i> ${data}`;
                }
            },
            {
                data: 'doi',
                render: function(data) {
                    if (!data) return '-';
                    return `<a href="https://doi.org/${data}" target="_blank">${data}</a>`;
                }
            },
            {
                data: 'license',
                render: function(data) {
                    return data || '-';
                }
            },
            {
                data: null,
                render: function(data, type, row) {
                    return `<a href="tool.html?name=${encodeURIComponent(row.name)}" class="btn btn-sm btn-primary">
                                <i class="bi bi-info-circle"></i> Details
                            </a>`;
                },
                orderable: false
            }
        ],
        pageLength: 25,
        lengthMenu: [[10, 25, 50, -1], [10, 25, 50, "All"]],
        order: [[3, 'desc']], // Sort by stars by default
        language: {
            search: "Search tools:",
            lengthMenu: "Show _MENU_ tools per page",
            info: "Showing _START_ to _END_ of _TOTAL_ tools",
            emptyTable: "No tools match your filters"
        }
    });

    return toolsTable;
}

// Apply filters to table
function applyFilters() {
    const category = $('#filter-category').val();
    const language = $('#filter-language').val();
    const packageMgr = $('#filter-pkgmgr').val();
    const search = $('#search-box').val();

    if (toolsTable) {
        // Custom filter function
        $.fn.dataTable.ext.search.pop(); // Remove previous filter
        $.fn.dataTable.ext.search.push(function(settings, data, dataIndex) {
            const tool = virometricsData.tools[dataIndex];
            if (!tool) return false;

            if (category && tool.category !== category) return false;

            if (language) {
                const langs = Array.isArray(tool.languages) ? tool.languages : [];
                if (!langs.includes(language)) return false;
            }

            if (packageMgr && packageMgr !== 'All') {
                if (packageMgr === 'Unknown' && tool.package_manager) return false;
                if (packageMgr !== 'Unknown' && tool.package_manager !== packageMgr) return false;
            }

            if (search) {
                // Support regex patterns
                let matches = false;
                const name = (tool.name || '').toLowerCase();
                const desc = (tool.description || '').toLowerCase();
                
                try {
                    // Use regex mode if enabled
                    if (typeof isRegexMode !== 'undefined' && isRegexMode) {
                        // Always treat search as regex when mode is enabled
                        const regexMatch = search.match(/\/(.+)\/([gimsuy]*)?/);
                        if (regexMatch) {
                            const pattern = regexMatch[1];
                            const flags = regexMatch[2] || 'i';
                            const regex = new RegExp(pattern, flags);
                            matches = regex.test(name) || regex.test(desc);
                        } else {
                            // If no delimiters, just search for the text
                            matches = name.includes(search) || desc.includes(search);
                        }
                    } else {
                        // Auto-detect regex patterns
                        if (search.includes('/') && search.length > 2) {
                            const regexMatch = search.match(/\/(.+)\/([gimsuy]*)?/);
                            if (regexMatch) {
                                const pattern = regexMatch[1];
                                const flags = regexMatch[2] || 'i';
                                const regex = new RegExp(pattern, flags);
                                matches = regex.test(name) || regex.test(desc);
                            } else {
                                matches = name.includes(search) || desc.includes(search);
                            }
                        } else {
                            // Simple substring search
                            matches = name.includes(search.toLowerCase()) || desc.includes(search.toLowerCase());
                        }
                    }
                } catch (e) {
                    // Fallback to simple search if regex is invalid
                    matches = name.includes(search.toLowerCase()) || desc.includes(search.toLowerCase());
                }
                
                if (!matches) return false;
            }

            return true;
        });

        toolsTable.draw();
    }
}

// Populate filter dropdowns
function populateFilters() {
    // Categories
    const categories = Object.keys(virometricsData.categories).sort();
    const catSelect = $('#filter-category');
    categories.forEach(cat => {
        catSelect.append(`<option value="${cat}">${cat} (${virometricsData.categories[cat]})</option>`);
    });

    // Languages (top ones)
    const langEntries = Object.entries(virometricsData.languages)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 20);
    const langSelect = $('#filter-language');
    langEntries.forEach(([lang, count]) => {
        langSelect.append(`<option value="${lang}">${lang} (${count})</option>`);
    });

    // Package managers
    const pkgSelect = $('#filter-pkgmgr');
    const pkgMgrs = Object.keys(virometricsData.packageManagers).sort();
    pkgMgrs.forEach(pkg => {
        pkgSelect.append(`<option value="${pkg}">${pkg} (${virometricsData.packageManagers[pkg]})</option>`);
    });
    pkgSelect.append(`<option value="Unknown">Unknown</option>`);
}

// Export table to CSV
function exportTableToCSV() {
    const filteredData = toolsTable ? toolsTable.rows({ search: 'applied' }).data() : [];

    if (filteredData.length === 0) {
        alert('No data to export');
        return;
    }

    const headers = ['Name', 'Category', 'Subcategory', 'Stars', 'DOI', 'License', 'URL'];
    const rows = [headers.join(',')];

    filteredData.each(function(row) {
        const escapedName = `"${(row.name || '').replace(/"/g, '""')}"`;
        const escapedURL = `"${(row.url || '').replace(/"/g, '""')}"`;
        rows.push([
            escapedName,
            row.category || '',
            row.subcategory || '',
            row.github_stars || 0,
            row.doi || '',
            row.license || '',
            escapedURL
        ].join(','));
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
