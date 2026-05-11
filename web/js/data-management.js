// data-management.js - Data management dashboard

// Load data summary
async function loadDataSummary() {
    try {
        const resp = await fetch('/api/data/summary');
        const summary = await resp.json();
        
        // Update summary cards
        document.getElementById('total-storage').textContent = summary.total_size_human || '0 B';
        document.getElementById('total-files').textContent = summary.total_files || 0;
        
        // Count directories
        const dirCount = Object.keys(summary.directories || {}).length;
        document.getElementById('dir-count').textContent = dirCount;
        
        // Count FASTA files
        let fastaCount = 0;
        if (summary.by_type && summary.by_type.fasta) {
            fastaCount = summary.by_type.fasta.count;
        }
        document.getElementById('fasta-files').textContent = fastaCount;
        
        // Render storage chart
        renderStorageChart(summary.directories);
        
        // Render file type list
        renderFileTypeList(summary.by_type);
        
        // Render directory table
        renderDirectoryTable(summary.directories);
        
        // Show content, hide loading
        document.getElementById('loading').style.display = 'none';
        document.getElementById('data-content').style.display = 'block';
        
    } catch (error) {
        console.error('Error loading data summary:', error);
        document.getElementById('loading').innerHTML = `
            <div class="alert alert-danger">
                <i class="bi bi-exclamation-triangle"></i> Error loading data summary
            </div>
        `;
    }
}

// Load workspace data
async function loadWorkspace() {
    try {
        const resp = await fetch('/api/data/workspace');
        const workspace = await resp.json();
        
        // Render uploads
        renderWorkspaceSection('workspace-uploads', workspace.uploads);
        
        // Render outputs
        renderWorkspaceSection('workspace-outputs', workspace.outputs);
        
        // Render tiered storage
        renderTieredStorage(workspace.tiered_storage);
        
    } catch (error) {
        console.error('Error loading workspace:', error);
    }
}

// Render storage chart
function renderStorageChart(directories) {
    const data = [];
    
    for (const [name, info] of Object.entries(directories || {})) {
        data.push({
            labels: [name],
            values: [info.total_size],
            name: info.path
        });
    }
    
    if (data.length === 0) {
        document.getElementById('storage-chart').innerHTML = `
            <div class="text-center py-5 text-muted">
                <i class="bi bi-hdd display-4"></i>
                <p class="mt-2">No storage data available</p>
            </div>
        `;
        return;
    }
    
    const trace = {
        labels: data.map(d => Object.keys(d.labels)[0]),
        values: data.map(d => Object.values(d.values)[0] / 1024 / 1024), // Convert to MB
        type: 'pie',
        marker: {
            colors: ['#0d6efd', '#198754', '#ffc107', '#dc3545', '#6f42c1', '#fd7e14']
        }
    };
    
    const layout = {
        title: 'Storage by Directory',
        showlegend: true,
        legend: {
            orientation: 'v',
            x: 1,
            xanchor: 'right'
        }
    };
    
    Plotly.newPlot('storage-chart', [trace], layout, {responsive: true});
}

// Render file type list
function renderFileTypeList(byType) {
    const container = document.getElementById('file-type-list');
    
    if (!byType || Object.keys(byType).length === 0) {
        container.innerHTML = '<p class="text-muted small">No files indexed</p>';
        return;
    }
    
    let html = '';
    
    for (const [ftype, info] of Object.entries(byType)) {
        html += `
            <div class="list-group-item d-flex justify-content-between align-items-center">
                <div>
                    <i class="bi bi-file-earmark-${getFileIcon(ftype)}"></i>
                    <strong>${ftype}</strong>
                </div>
                <span class="badge bg-secondary">${info.count}</span>
            </div>
        `;
    }
    
    container.innerHTML = html;
}

// Get icon for file type
function getFileIcon(ftype) {
    const iconMap = {
        'fasta': 'text',
        'fastq': 'text',
        'bam': 'binary',
        'vcf': 'text',
        'json': 'json',
        'csv': 'spreadsheet',
        'log': 'earphones',
        'archive': 'zip',
        'compressed': 'file-zip',
        'other': 'file'
    };
    return iconMap[ftype] || 'file';
}

// Render directory table
function renderDirectoryTable(directories) {
    const tbody = document.getElementById('directory-table');
    
    if (!directories || Object.keys(directories).length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">No directories found</td></tr>';
        return;
    }
    
    let html = '';
    
    for (const [name, info] of Object.entries(directories)) {
        const statusIcon = info.file_count > 0 ? 
            '<i class="bi bi-check-circle text-success"></i>' : 
            '<i class="bi bi-x-circle text-muted"></i>';
        
        html += `
            <tr>
                <td><strong>${name}</strong></td>
                <td><code class="small">${info.path}</code></td>
                <td>${info.file_count}</td>
                <td>${info.total_size_human}</td>
                <td>${statusIcon}</td>
            </tr>
        `;
    }
    
    tbody.innerHTML = html;
}

// Render workspace section
function renderWorkspaceSection(containerId, section) {
    const container = document.getElementById(containerId);
    
    if (!section || !section.exists) {
        container.innerHTML = '<p class="text-muted">Directory does not exist</p>';
        return;
    }
    
    let html = `
        <div class="d-flex justify-content-between mb-2">
            <span><i class="bi bi-folder"></i> ${section.path}</span>
            <span class="badge bg-secondary">${section.file_count} files</span>
        </div>
        <div class="mb-2">
            <div class="progress" style="height: 8px;">
                <div class="progress-bar" style="width: ${Math.min(section.file_count * 2, 100)}%"></div>
            </div>
            <small class="text-muted">${section.total_size_human}</small>
        </div>
    `;
    
    if (section.files && section.files.length > 0) {
        html += '<div class="mt-2 small"><strong>Recent files:</strong><ul class="mb-0">';
        section.files.slice(0, 3).forEach(f => {
            html += `<li><code>${f.name}</code> <span class="text-muted">(${f.size_human})</span></li>`;
        });
        if (section.files.length > 3) {
            html += `<li class="text-muted">+${section.files.length - 3} more</li>`;
        }
        html += '</ul></div>';
    }
    
    container.innerHTML = html;
}

// Render tiered storage
function renderTieredStorage(tieredStorage) {
    for (const [tier, info] of Object.entries(tieredStorage)) {
        const element = document.getElementById(`${tier}-storage`);
        if (element) {
            element.textContent = `${info.total_size_human} (${info.file_count} files)`;
        }
    }
}

// Scan directories
async function scanDirectories() {
    const btn = document.getElementById('btn-scan');
    const originalText = btn.innerHTML;
    
    btn.innerHTML = '<i class="bi bi-hourglass-split"></i> Scanning...';
    btn.disabled = true;
    
    try {
        const resp = await fetch('/api/data/scan', {method: 'POST'});
        const result = await resp.json();
        
        if (result.success) {
            alert(`Scanned ${result.scanned} directories successfully`);
            loadDataSummary();
            loadWorkspace();
        } else {
            alert(`Scan failed: ${result.error}`);
        }
        
    } catch (error) {
        console.error('Error scanning:', error);
        alert('Error scanning directories');
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

// Refresh statistics
async function refreshStatistics() {
    const btn = document.getElementById('btn-refresh');
    const originalIcon = btn.innerHTML;
    
    btn.innerHTML = '<i class="bi bi-arrow-clockwise spin"></i> Refreshing...';
    
    try {
        await loadDataSummary();
        await loadWorkspace();
    } catch (error) {
        console.error('Error refreshing:', error);
    } finally {
        btn.innerHTML = originalIcon;
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', function() {
    initTheme();
    loadDataSummary();
    loadWorkspace();
    
    // Event listeners
    document.getElementById('btn-scan').addEventListener('click', scanDirectories);
    document.getElementById('btn-refresh').addEventListener('click', refreshStatistics);
});
