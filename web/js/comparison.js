// comparison.js - Tool comparison logic for Virometrics

let selectedTools = [];

// Initialize comparison page
document.addEventListener('DOMContentLoaded', async function() {
    initTheme();

    // Load tool data
    await loadToolData();

    // Populate tool selector
    populateToolSelector();

    // Check URL params for pre-selected tools
    const params = new URLSearchParams(window.location.search);
    const preSelected = params.get('tools');
    if (preSelected) {
        selectedTools = preSelected.split(',').map(t => decodeURIComponent(t));
        updateSelectedPreview();
        runComparison();
    }

    // Event listeners
    document.getElementById('btn-compare').addEventListener('click', runComparison);
    document.getElementById('tool-selector').addEventListener('change', updateSelectedPreview);
    document.getElementById('export-comparison-csv').addEventListener('click', exportComparisonCSV);
    document.getElementById('export-comparison-json').addEventListener('click', exportComparisonJSON);
});

// Populate tool selector dropdown
function populateToolSelector() {
    const selector = document.getElementById('tool-selector');
    selector.innerHTML = '';

    // Sort tools by name
    const sorted = [...virometricsData.tools].sort((a, b) =>
        (a.name || '').localeCompare(b.name || '')
    );

    sorted.forEach(tool => {
        const option = document.createElement('option');
        option.value = tool.name;
        option.textContent = `${tool.name} (${tool.category || 'Unknown'})`;
        selector.appendChild(option);
    });
}

// Update preview of selected tools
function updateSelectedPreview() {
    const selector = document.getElementById('tool-selector');
    const preview = document.getElementById('selected-tools-preview');

    // Get selected options
    selectedTools = Array.from(selector.selectedOptions).map(opt => opt.value);

    if (selectedTools.length === 0) {
        preview.innerHTML = '<p class="text-muted">No tools selected yet.</p>';
        return;
    }

    let html = '<div class="d-flex flex-wrap gap-2 mb-2">';
    selectedTools.forEach(name => {
        html += `<span class="badge bg-primary p-2">${name} <i class="bi bi-x-circle ms-1" style="cursor:pointer" onclick="removeTool('${name}')"></i></span>`;
    });
    html += '</div>';
    html += `<small class="text-muted">${selectedTools.length} tool(s) selected for comparison</small>`;

    preview.innerHTML = html;
}

// Remove a tool from selection
window.removeTool = function(name) {
    selectedTools = selectedTools.filter(t => t !== name);
    updateSelectedPreview();

    // Update selector
    const selector = document.getElementById('tool-selector');
    Array.from(selector.options).forEach(opt => {
        opt.selected = selectedTools.includes(opt.value);
    });
};

// Run comparison
function runComparison() {
    if (selectedTools.length < 2) {
        alert('Please select at least 2 tools to compare.');
        return;
    }

    if (selectedTools.length > 5) {
        alert('Maximum 5 tools can be compared at once.');
        selectedTools = selectedTools.slice(0, 5);
    }

    // Get tool objects
    const tools = selectedTools.map(name => getTool(name)).filter(t => t);

    if (tools.length < 2) {
        alert('Could not find the selected tools. Please try again.');
        return;
    }

    // Show results, hide empty state
    document.getElementById('empty-state').style.display = 'none';
    document.getElementById('comparison-results').style.display = 'block';

    // Render radar chart
    renderRadarChart(tools);

    // Render comparison table
    renderComparisonTable(tools);
}

// Render radar chart
function renderRadarChart(tools) {
    const data = [];

    tools.forEach((tool, idx) => {
        const colors = ['#109b81', '#2C4B7C', '#9D5EB0', '#3498db', '#e74c3c'];

        // Prepare metrics (normalize to 0-1 scale)
        const stars = Math.min((tool.github_stars || 0) / 100, 1);
        const forks = Math.min((tool.github_forks || 0) / 50, 1);
        const hasDOI = tool.doi ? 1 : 0;
        const langCount = Array.isArray(tool.languages) ? Math.min(tool.languages.length / 3, 1) : 0;

        // Input format diversity
        let inputCount = 0;
        try {
            const inputs = typeof tool.input_formats === 'string' ?
                JSON.parse(tool.input_formats) : tool.input_formats;
            inputCount = Array.isArray(inputs) ? Math.min(inputs.length / 5, 1) : 0;
        } catch(e) {}

        data.push({
            type: 'scatterpolar',
            r: [stars, forks, hasDOI, langCount, inputCount, stars],
            theta: ['GitHub Stars', 'Forks', 'Has DOI', 'Languages', 'Input Formats', 'GitHub Stars'],
            fill: 'toself',
            name: tool.name,
            line: { color: colors[idx % colors.length] }
        });
    });

    const layout = {
        polar: {
            radialaxis: {
                visible: true,
                range: [0, 1]
            }
        },
        showlegend: true,
        paper_bgcolor: 'transparent',
        plot_bgcolor: 'transparent',
        font: { family: 'Inter, system-ui, sans-serif' }
    };

    Plotly.newPlot('radar-chart', data, layout, { responsive: true });
}

// Render comparison table
function renderComparisonTable(tools) {
    const table = document.getElementById('comparison-table');
    const thead = table.querySelector('thead tr');
    const tbody = table.querySelector('tbody');

    // Clear existing
    thead.innerHTML = '<th>Feature</th>';
    tbody.innerHTML = '';

    // Add tool columns
    tools.forEach(tool => {
        thead.innerHTML += `<th>${tool.name}</th>`;
    });

    // Define comparison rows
    const rows = [
        { feature: 'Category', field: 'category' },
        { feature: 'Subcategory', field: 'subcategory' },
        { feature: 'Description', field: 'description', truncate: 100 },
        { feature: 'Package Manager', field: 'package_manager' },
        { feature: 'License', field: 'license' },
        { feature: 'GitHub Stars', field: 'github_stars', default: 0 },
        { feature: 'GitHub Forks', field: 'github_forks', default: 0 },
        { feature: 'DOI', field: 'doi', format: v => v ? `<a href="https://doi.org/${v}">${v}</a>` : '-' },
        { feature: 'URL', field: 'url', format: v => v ? `<a href="${v}" target="_blank">Link</a>` : '-' },
    ];

    // Add language row
    rows.splice(4, 0, {
        feature: 'Languages',
        field: 'languages',
        format: v => {
            if (!Array.isArray(v)) return '-';
            return v.map(l => `<span class="badge bg-info">${l}</span>`).join(' ');
        }
    });

    // Add input formats row
    rows.splice(8, 0, {
        feature: 'Input Formats',
        field: 'input_formats',
        format: v => {
            let formats = v;
            if (typeof v === 'string') {
                try { formats = JSON.parse(v); } catch(e) { return '-'; }
            }
            if (!Array.isArray(formats)) return '-';
            return formats.map(f => `<span class="badge bg-primary">${f}</span>`).join(' ');
        }
    });

    // Render rows
    rows.forEach(rowDef => {
        const tr = document.createElement('tr');
        let td = `<td class="fw-bold">${rowDef.feature}</td>`;

        tools.forEach(tool => {
            let value = tool[rowDef.field];
            if (value === undefined || value === null) {
                value = rowDef.default !== undefined ? rowDef.default : '-';
            }
            if (rowDef.truncate && typeof value === 'string' && value.length > rowDef.truncate) {
                value = value.substring(0, rowDef.truncate) + '...';
            }
            if (rowDef.format) {
                value = rowDef.format(value);
            }
            td += `<td>${value}</td>`;
        });

        tr.innerHTML = td;
        tbody.appendChild(tr);
    });
}

// Export functions
function exportComparisonCSV() {
    if (selectedTools.length === 0) return;

    const tools = selectedTools.map(name => getTool(name)).filter(t => t);
    const headers = ['Feature', ...tools.map(t => t.name)];

    const rows = [
        ['Category', ...tools.map(t => t.category || '')],
        ['Subcategory', ...tools.map(t => t.subcategory || '')],
        ['Package Manager', ...tools.map(t => t.package_manager || '')],
        ['License', ...tools.map(t => t.license || '')],
        ['GitHub Stars', ...tools.map(t => t.github_stars || 0)],
        ['DOI', ...tools.map(t => t.doi || '')],
    ];

    let csv = headers.join(',') + '\n';
    rows.forEach(row => {
        csv += row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(',') + '\n';
    });

    downloadFile(csv, 'virometrics_comparison.csv', 'text/csv');
}

function exportComparisonJSON() {
    if (selectedTools.length === 0) return;

    const tools = selectedTools.map(name => getTool(name)).filter(t => t);
    const json = JSON.stringify(tools, null, 2);
    downloadFile(json, 'virometrics_comparison.json', 'application/json');
}

function downloadFile(content, filename, type) {
    const blob = new Blob([content], { type: type });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
}
