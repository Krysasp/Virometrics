/**
 * data-manager.js - Data management interface logic.
 */

document.addEventListener('DOMContentLoaded', function() {
    initTheme();
    loadStorageMetrics();
    loadFileTypeStats();
    loadDirectorySizes();
    loadFiles();
    setupEventListeners();
});

function initTheme() {
    const savedTheme = localStorage.getItem('virometrics-theme');
    if (savedTheme === 'dark') {
        enableDarkMode();
    }
}

function enableDarkMode() {
    document.documentElement.setAttribute('data-theme', 'dark');
    document.body.classList.add('dark-mode');
    const btn = document.getElementById('themeToggle');
    if (btn) btn.innerHTML = '<i class="bi bi-sun"></i>';
}

// Theme toggle
document.addEventListener('click', function(e) {
    if (e.target.closest('#themeToggle')) {
        if (document.documentElement.getAttribute('data-theme') === 'dark') {
            document.documentElement.removeAttribute('data-theme');
            document.body.classList.remove('dark-mode');
            localStorage.setItem('virometrics-theme', 'light');
            document.getElementById('themeToggle').innerHTML = '<i class="bi bi-moon"></i>';
        } else {
            enableDarkMode();
            localStorage.setItem('virometrics-theme', 'dark');
        }
    }
});

function setupEventListeners() {
    // File upload
    const uploadZone = document.getElementById('upload-zone');
    const fileInput = document.getElementById('file-input');

    if (uploadZone && fileInput) {
        uploadZone.addEventListener('click', () => fileInput.click());
        uploadZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadZone.classList.add('dragover');
        });
        uploadZone.addEventListener('dragleave', () => {
            uploadZone.classList.remove('dragover');
        });
        uploadZone.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadZone.classList.remove('dragover');
            handleFiles(e.dataTransfer.files);
        });
        fileInput.addEventListener('change', () => {
            handleFiles(fileInput.files);
        });
    }

    // Directory refresh
    const btnRefresh = document.getElementById('btn-refresh-dirs');
    if (btnRefresh) {
        btnRefresh.addEventListener('click', loadDirectorySizes);
    }

    // File type filter
    const filterType = document.getElementById('filter-type');
    if (filterType) {
        filterType.addEventListener('change', loadFiles);
    }
}

async function loadStorageMetrics() {
    try {
        const resp = await fetch('/api/storage/metrics');
        const data = await resp.json();

        setText('stat-total', formatBytes(data.total || 0));
        setText('stat-used', formatBytes(data.used || 0));
        setText('stat-free', formatBytes(data.free || 0));
        setText('stat-files', data.file_count || 0);
    } catch (e) {
        console.error('Error loading storage metrics:', e);
    }
}

async function loadFileTypeStats() {
    try {
        const resp = await fetch('/api/storage/filetypes');
        const stats = await resp.json();

        const labels = Object.keys(stats).filter(k => k !== '_total');
        const values = labels.map(l => stats[l]);

        const colors = [
            '#4682B4', '#20B2AA', '#DB7093', '#9370DB',
            '#FF6347', '#3CB371', '#1E90FF', '#FF8C00'
        ];

        const data = [{
            labels: labels,
            values: values,
            type: 'pie',
            hole: 0.4,
            marker: { colors: colors.slice(0, labels.length) },
            textinfo: 'label+value',
            automargin: true
        }];

        const layout = {
            margin: { t: 20, b: 20, l: 20, r: 20 },
            paper_bgcolor: 'transparent',
            plot_bgcolor: 'transparent',
            font: { family: 'Inter, system-ui, sans-serif' }
        };

        Plotly.newPlot('filetype-chart', data, layout, { responsive: true });
    } catch (e) {
        console.error('Error loading file type stats:', e);
    }
}

async function loadDirectorySizes() {
    const container = document.getElementById('dir-sizes');
    if (!container) return;

    try {
        const resp = await fetch('/api/storage/directories');
        const dirs = await resp.json();

        if (dirs.length === 0) {
            container.innerHTML = '<p class="text-muted text-center py-3">No directories found.</p>';
            return;
        }

        let html = '<div class="list-group">';
        dirs.forEach(d => {
            html += `
                <div class="list-group-item d-flex justify-content-between align-items-center">
                    <div>
                        <strong>${d.name}</strong>
                        <small class="text-muted ms-2">${d.file_count || 0} files</small>
                    </div>
                    <span class="badge bg-primary rounded-pill">${formatBytes(d.size || 0)}</span>
                </div>
            `;
        });
        html += '</div>';
        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = '<p class="text-danger">Error loading directories.</p>';
        console.error('Error loading directory sizes:', e);
    }
}

async function loadFiles() {
    const tbody = document.getElementById('files-tbody');
    if (!tbody) return;

    const fileType = document.getElementById('filter-type')?.value;
    let url = '/api/files?limit=100';
    if (fileType) url += `&file_type=${fileType}`;

    try {
        const resp = await fetch(url);
        const files = await resp.json();

        if (files.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted py-3">No files found.</td></tr>';
            return;
        }

        tbody.innerHTML = files.map(f => `
            <tr>
                <td><i class="bi bi-file-earmark"></i> ${escapeHtml(f.filename || 'Unknown')}</td>
                <td><span class="badge bg-info">${f.file_type || 'other'}</span></td>
                <td>${formatBytes(f.file_size || 0)}</td>
                <td>${f.created_at ? new Date(f.created_at).toLocaleDateString() : 'Unknown'}</td>
                <td>
                    ${f.id ? `<button class="btn btn-sm btn-outline-danger" onclick="deleteFile(${f.id})"><i class="bi bi-trash"></i></button>` : ''}
                </td>
            </tr>
        `).join('');
    } catch (e) {
        tbody.innerHTML = '<tr><td colspan="5" class="text-danger">Error loading files.</td></tr>';
        console.error('Error loading files:', e);
    }
}

async function handleFiles(files) {
    if (!files || files.length === 0) return;

    const resultsDiv = document.getElementById('upload-results');
    resultsDiv.innerHTML = `<p>Uploading ${files.length} file(s)...</p>`;

    let successCount = 0;

    for (const file of files) {
        const formData = new FormData();
        formData.append('file', file);

        try {
            const resp = await fetch('/api/files/upload', {
                method: 'POST',
                body: formData
            });

            if (resp.ok) {
                successCount++;
            } else {
                const err = await resp.json();
                console.error(`Upload failed for ${file.name}:`, err);
            }
        } catch (e) {
            console.error(`Upload error for ${file.name}:`, e);
        }
    }

    resultsDiv.innerHTML = `<div class="alert alert-success">Uploaded ${successCount} of ${files.length} files.</div>`;

    // Refresh file list and stats
    setTimeout(() => {
        loadFiles();
        loadStorageMetrics();
        loadFileTypeStats();
    }, 1000);
}

async function deleteFile(fileId) {
    if (!confirm('Delete this file?')) return;

    try {
        const resp = await fetch(`/api/files/${fileId}`, {
            method: 'DELETE'
        });

        if (resp.ok) {
            loadFiles();
            loadStorageMetrics();
        }
    } catch (e) {
        console.error('Error deleting file:', e);
    }
}

function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}
