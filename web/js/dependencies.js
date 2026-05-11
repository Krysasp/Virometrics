/**
 * dependencies.js - Dependency management interface.
 */

let dependenciesData = [];
let toolsData = [];

document.addEventListener('DOMContentLoaded', function() {
    initTheme();
    loadDependencies();
    loadToolsForScan();
    setupEventListeners();
});

function initTheme() {
    const savedTheme = localStorage.getItem('virometrics-theme');
    if (savedTheme === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark');
        document.body.classList.add('dark-mode');
        const btn = document.getElementById('themeToggle');
        if (btn) btn.innerHTML = '<i class="bi bi-sun"></i>';
    }
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
            document.documentElement.setAttribute('data-theme', 'dark');
            document.body.classList.add('dark-mode');
            localStorage.setItem('virometrics-theme', 'dark');
            document.getElementById('themeToggle').innerHTML = '<i class="bi bi-sun"></i>';
        }
    }
});

function setupEventListeners() {
    const btnRefresh = document.getElementById('btn-refresh-deps');
    if (btnRefresh) btnRefresh.addEventListener('click', loadDependencies);

    const btnScan = document.getElementById('btn-scan-deps');
    if (btnScan) btnScan.addEventListener('click', scanToolDependencies);

    const filterMgr = document.getElementById('filter-pkg-mgr');
    if (filterMgr) filterMgr.addEventListener('change', filterDependencies);

    const btnInstall = document.getElementById('btn-do-install');
    if (btnInstall) btnInstall.addEventListener('click', doInstall);
}

async function loadDependencies() {
    try {
        const resp = await fetch('/api/dependencies');
        dependenciesData = await resp.json();
        renderDependencies(dependenciesData);
        updateStats(dependenciesData);
    } catch (e) {
        console.error('Error loading dependencies:', e);
        document.getElementById('dependencies-list').innerHTML =
            '<p class="text-danger">Error loading dependencies.</p>';
    }
}

function renderDependencies(deps) {
    const container = document.getElementById('dependencies-list');
    if (!container) return;

    if (deps.length === 0) {
        container.innerHTML = '<p class="text-muted text-center py-3">No dependencies registered.</p>';
        return;
    }

    let html = '';
    deps.forEach(dep => {
        const statusClass = dep.installed ? 'installed' : 'missing';
        const badgeClass = dep.installed ? 'bg-success' : 'bg-danger';
        const statusText = dep.installed ? `Installed${dep.installed_version ? ' (' + dep.installed_version + ')' : ''}` : 'Missing';

        html += `
        <div class="card dep-card ${statusClass} mb-2">
            <div class="card-body py-2 px-3">
                <div class="d-flex justify-content-between align-items-center">
                    <div>
                        <strong>${dep.name}</strong>
                        ${dep.version ? `<span class="badge bg-secondary status-badge">${dep.version}</span>` : ''}
                        <span class="badge bg-info status-badge">${dep.package_manager}</span>
                        ${dep.description ? `<small class="text-muted ms-2">${dep.description}</small>` : ''}
                    </div>
                    <div class="d-flex gap-2 align-items-center">
                        <span class="badge ${badgeClass} status-badge">${statusText}</span>
                        ${!dep.installed ? `
                            <button class="btn btn-sm btn-outline-primary" onclick="showInstallModal(${dep.id}, '${dep.name}', '${dep.install_command || ''}')">
                                <i class="bi bi-download"></i> Install
                            </button>
                        ` : ''}
                        ${dep.url ? `<a href="${dep.url}" target="_blank" class="btn btn-sm btn-outline-secondary"><i class="bi bi-box-arrow-up-right"></i></a>` : ''}
                    </div>
                </div>
            </div>
        </div>`;
    });

    container.innerHTML = html;
}

function updateStats(deps) {
    const total = deps.length;
    const installed = deps.filter(d => d.installed).length;
    const missing = total - installed;

    setText('stat-total-deps', total);
    setText('stat-installed', installed);
    setText('stat-missing', missing);
}

function filterDependencies() {
    const filter = document.getElementById('filter-pkg-mgr').value;
    if (!filter) {
        renderDependencies(dependenciesData);
        return;
    }
    const filtered = dependenciesData.filter(d => d.package_manager === filter);
    renderDependencies(filtered);
}

async function loadToolsForScan() {
    try {
        const resp = await fetch('../data/tools_enhanced.json');
        toolsData = await resp.json();

        const select = document.getElementById('scan-tool-select');
        if (!select) return;

        const sorted = [...toolsData].sort((a, b) =>
            (a.name || '').localeCompare(b.name || '')
        );

        sorted.forEach(tool => {
            const opt = document.createElement('option');
            opt.value = tool.id || 0;
            opt.textContent = `${tool.name} (${tool.category || 'Unknown'})`;
            select.appendChild(opt);
        });
    } catch (e) {
        console.error('Error loading tools:', e);
    }
}

async function scanToolDependencies() {
    const select = document.getElementById('scan-tool-select');
    const toolId = select.value;

    if (!toolId) {
        alert('Please select a tool first.');
        return;
    }

    const resultEl = document.getElementById('scan-result');
    resultEl.innerHTML = '<div class="alert alert-info">Scanning...</div>';

    try {
        const resp = await fetch(`/api/dependencies/scan/${toolId}`, {
            method: 'POST'
        });
        const data = await resp.json();

        if (data.registered && data.registered.length > 0) {
            resultEl.innerHTML = `
                <div class="alert alert-success">
                    Registered ${data.registered.length} dependencies:
                    <ul class="mb-0 mt-1">
                        ${data.registered.map(r => `<li>${r.name} (from ${r.source})</li>`).join('')}
                    </ul>
                </div>
            `;
            loadDependencies(); // Refresh list
        } else {
            resultEl.innerHTML = '<div class="alert alert-warning">No new dependencies found.</div>';
        }
    } catch (e) {
        resultEl.innerHTML = `<div class="alert alert-danger">Error: ${e.message}</div>`;
    }
}

let currentInstallDepId = null;

function showInstallModal(depId, depName, installCmd) {
    currentInstallDepId = depId;
    document.getElementById('install-dep-name').textContent = `Installing: ${depName}`;
    document.getElementById('install-command').textContent = installCmd || 'No install command available';
    document.getElementById('install-output').style.display = 'none';

    const modal = new bootstrap.Modal(document.getElementById('installModal'));
    modal.show();
}

async function doInstall() {
    if (!currentInstallDepId) return;

    const outputDiv = document.getElementById('install-output');
    const outputContainer = outputDiv.querySelector('.output-container');
    outputDiv.style.display = 'block';
    outputContainer.innerHTML = '<em>Starting installation...</em>';

    try {
        const resp = await fetch(`/api/dependencies/install/${currentInstallDepId}`, {
            method: 'POST'
        });
        const data = await resp.json();

        if (data.success) {
            outputContainer.innerHTML += `\n<div class="text-success">${data.message}</div>`;
            setTimeout(() => {
                bootstrap.Modal.getInstance(document.getElementById('installModal')).hide();
                loadDependencies();
            }, 1500);
        } else {
            outputContainer.innerHTML += `\n<div class="text-danger">Failed: ${data.message}</div>`;
        }
    } catch (e) {
        outputContainer.innerHTML += `\n<div class="text-danger">Error: ${e.message}</div>`;
    }
}

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}
