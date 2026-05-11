/**
 * Execute.js - Tool execution interface logic.
 * Handles parameter forms, SSE streaming, and execution management.
 */

let currentTool = null;
let currentExecution = null;
let sseHandler = null;
let lastSequence = -1;

// Available tools cache
let toolsCache = null;

document.addEventListener('DOMContentLoaded', function() {
    initTheme();
    loadToolsList();
    setupEventListeners();
    checkUrlParams();
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
    if (btn) {
        btn.innerHTML = '<i class="bi bi-sun"></i>';
    }
}

function loadToolsList() {
    fetch('../data/tools_enhanced.json')
        .then(r => r.json())
        .then(tools => {
            toolsCache = tools;
            const select = document.getElementById('tool-select');
            if (!select) return;

            // Sort by name
            const sorted = [...tools].sort((a, b) =>
                (a.name || '').localeCompare(b.name || '')
            );

            sorted.forEach(tool => {
                const opt = document.createElement('option');
                opt.value = tool.name;
                opt.textContent = `${tool.name} (${tool.category || 'Unknown'})`;
                opt.dataset.toolId = tool.id || 0;
                select.appendChild(opt);
            });
        })
        .catch(err => console.error('Error loading tools:', err));
}

function setupEventListeners() {
    // Tool selection
    const toolSelect = document.getElementById('tool-select');
    if (toolSelect) {
        toolSelect.addEventListener('change', onToolSelected);
    }

    // Execute button
    const btnExecute = document.getElementById('btn-execute');
    if (btnExecute) {
        btnExecute.addEventListener('click', startExecution);
    }

    // Cancel button
    const btnCancel = document.getElementById('btn-cancel');
    if (btnCancel) {
        btnCancel.addEventListener('click', cancelExecution);
    }

    // Command input toggle
    const cmdToggle = document.getElementById('cmd-toggle');
    if (cmdToggle) {
        cmdToggle.addEventListener('change', toggleCommandInput);
    }

    // Theme toggle
    const themeBtn = document.getElementById('themeToggle');
    if (themeBtn) {
        themeBtn.addEventListener('click', function() {
            if (document.documentElement.getAttribute('data-theme') === 'dark') {
                document.documentElement.removeAttribute('data-theme');
                document.body.classList.remove('dark-mode');
                themeBtn.innerHTML = '<i class="bi bi-moon"></i>';
                localStorage.setItem('virometrics-theme', 'light');
            } else {
                enableDarkMode();
                localStorage.setItem('virometrics-theme', 'dark');
            }
        });
    }
}

function checkUrlParams() {
    const params = new URLSearchParams(window.location.search);
    const toolName = params.get('tool');
    if (toolName) {
        const select = document.getElementById('tool-select');
        if (select) {
            // Find and select the tool
            for (const opt of select.options) {
                if (opt.value === toolName) {
                    opt.selected = true;
                    onToolSelected();
                    break;
                }
            }
        }
    }
}

async function onToolSelected() {
    const select = document.getElementById('tool-select');
    const toolName = select.value;
    if (!toolName) {
        hideToolPanel();
        return;
    }

    // Find tool data
    currentTool = toolsCache
        ? toolsCache.find(t => t.name === toolName)
        : null;

    if (!currentTool) {
        // Try to fetch from API
        try {
            const resp = await fetch(`/api/tools?search=${encodeURIComponent(toolName)}`);
            const tools = await resp.json();
            currentTool = tools.find(t => t.name === toolName);
        } catch (e) {
            console.error('Error fetching tool:', e);
        }
    }

    if (currentTool) {
        showToolPanel(currentTool);
        loadToolParameters(currentTool);
    }
}

function showToolPanel(tool) {
    const panel = document.getElementById('tool-panel');
    if (panel) {
        document.getElementById('selected-tool-name').textContent = tool.name;
        document.getElementById('selected-tool-category').textContent = tool.category || 'Unknown';
        panel.style.display = 'block';
    }
}

function hideToolPanel() {
    const panel = document.getElementById('tool-panel');
    if (panel) panel.style.display = 'none';
}

async function loadToolParameters(tool) {
    const formContainer = document.getElementById('parameter-form');
    if (!formContainer) return;

    try {
        // Try to get parameters from API
        const resp = await fetch(`/api/tools/${tool.id || 0}/parameters`);
        const params = await resp.json();

        if (Array.isArray(params) && params.length > 0) {
            buildParameterForm(params, formContainer);
            document.getElementById('param-section').style.display = 'block';
        } else {
            // No parameters defined - show simple command input
            formContainer.innerHTML = `
                <div class="alert alert-info">
                    No parameter definitions found for this tool.
                    You can enter a command directly below.
                </div>
            `;
        }
    } catch (e) {
        console.error('Error loading parameters:', e);
        formContainer.innerHTML = `
            <div class="alert alert-warning">
                Could not load parameters. You can enter a command directly.
            </div>
        `;
    }
}

function buildParameterForm(params, container) {
    let html = '';

    // Group parameters
    const groups = {};
    params.forEach(p => {
        const group = p.group_name || 'General';
        if (!groups[group]) groups[group] = [];
        groups[group].push(p);
    });

    // Build form HTML
    Object.entries(groups).forEach(([groupName, groupParams]) => {
        html += `<fieldset class="border p-3 mb-3"><legend class="w-auto px-2">${groupName}</legend>`;

        groupParams.forEach(p => {
            html += buildFormField(p);
        });

        html += '</fieldset>';
    });

    container.innerHTML = html;
}

function buildFormField(param) {
    const name = param.param_name || 'unknown';
    const label = param.param_label || name;
    const type = param.param_type || 'string';
    const required = param.required ? 'required' : '';
    const defaultValue = param.default_value || '';
    const description = param.param_description || '';

    let html = '<div class="mb-3">';
    html += `<label class="form-label">${label}${param.required ? ' <span class="text-danger">*</span>' : ''}</label>`;

    if (description) {
        html += `<div class="form-text text-muted small mb-1">${description}</div>`;
    }

    switch (type) {
        case 'string':
        case 'text':
            html += `<input type="text" class="form-control" name="${name}" value="${defaultValue}" ${required}>`;
            break;

        case 'integer':
        case 'float':
        case 'number':
            html += `<input type="number" class="form-control" name="${name}" value="${defaultValue}" step="${type === 'integer' ? '1' : 'any'}" ${required}>`;
            break;

        case 'boolean':
        case 'bool':
            html += `
                <div class="form-check">
                    <input class="form-check-input" type="checkbox" name="${name}" id="check-${name}" ${defaultValue === 'true' ? 'checked' : ''}>
                    <label class="form-check-label" for="check-${name}">Enable</label>
                </div>
            `;
            break;

        case 'choice':
            html += `<select class="form-select" name="${name}" ${required}>`;
            html += `<option value="">-- Select --</option>`;
            try {
                const choices = typeof param.choices === 'string'
                    ? JSON.parse(param.choices) : param.choices;
                if (Array.isArray(choices)) {
                    choices.forEach(c => {
                        html += `<option value="${c}" ${c === defaultValue ? 'selected' : ''}>${c}</option>`;
                    });
                }
            } catch (e) {}
            html += '</select>';
            break;

        case 'file':
            html += `<input type="file" class="form-control" name="${name}" ${required}>`;
            break;

        default:
            html += `<input type="text" class="form-control" name="${name}" value="${defaultValue}" ${required}>`;
    }

    html += '</div>';
    return html;
}

async function startExecution() {
    if (!currentTool) {
        alert('Please select a tool first.');
        return;
    }

    // Collect parameters
    const form = document.getElementById('parameter-form');
    const formData = new FormData(form);
    const params = {};
    for (const [key, value] of formData.entries()) {
        params[key] = value;
    }

    // Get command (either from form or custom input)
    let command = '';
    const customCmd = document.getElementById('custom-command');
    if (customCmd && customCmd.value.trim()) {
        command = customCmd.value.trim();
    }

    // Show output panel
    document.getElementById('output-panel').style.display = 'block';
    document.getElementById('output-content').innerHTML = '';
    updateStatus('running');

    try {
        const payload = {
            tool_id: currentTool.id || 0,
            command: command,
            parameters: params,
            working_dir: document.getElementById('working-dir')?.value || ''
        };

        const resp = await fetch(`/api/execute/${currentTool.id || 0}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.error || 'Failed to start execution');
        }

        const data = await resp.json();
        currentExecution = data.execution_id;

        // Connect SSE stream
        connectSSE(currentExecution);

        // Add to history
        addToHistory(data.execution_id, currentTool.name, 'running');

    } catch (e) {
        console.error('Execution error:', e);
        appendOutput('error', `Failed to start execution: ${e.message}`);
        updateStatus('failed');
    }
}

function connectSSE(executionId) {
    if (sseHandler) {
        sseHandler.disconnect();
    }

    const url = `/api/execute/${executionId}/stream`;
    sseHandler = new SSEHandler(url, { maxRetries: 3 });

    sseHandler.on('stdout', data => {
        appendOutput('stdout', data.content);
    });

    sseHandler.on('stderr', data => {
        appendOutput('stderr', data.content);
    });

    sseHandler.on('status', data => {
        updateStatus(data.status);
        if (data.status === 'completed' || data.status === 'failed') {
            updateReturnCode(data.return_code);
        }
    });

    sseHandler.on('complete', data => {
        updateStatus(data.status);
        sseHandler.disconnect();
        sseHandler = null;
    });

    sseHandler.on('error', data => {
        appendOutput('error', data.message || 'Unknown error');
    });

    sseHandler.on('open', () => {
        console.log('SSE connected');
    });

    sseHandler.on('close', () => {
        console.log('SSE closed');
    });

    sseHandler.connect();
}

function appendOutput(type, content) {
    const outputEl = document.getElementById('output-content');
    if (!outputEl) return;

    const line = document.createElement('div');
    line.className = `output-line output-${type}`;

    const timestamp = new Date().toLocaleTimeString();
    line.innerHTML = `<span class="output-time">[${timestamp}]</span> <span class="output-text">${escapeHtml(content)}</span>`;

    outputEl.appendChild(line);
    outputEl.scrollTop = outputEl.scrollHeight;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function updateStatus(status) {
    const badge = document.getElementById('execution-status');
    if (!badge) return;

    const statusMap = {
        'pending': { text: 'Pending', class: 'bg-secondary' },
        'running': { text: 'Running', class: 'bg-primary' },
        'completed': { text: 'Completed', class: 'bg-success' },
        'failed': { text: 'Failed', class: 'bg-danger' },
        'cancelled': { text: 'Cancelled', class: 'bg-warning' }
    };

    const info = statusMap[status] || { text: status, class: 'bg-secondary' };
    badge.textContent = info.text;
    badge.className = `badge ${info.class}`;
}

function updateReturnCode(code) {
    const el = document.getElementById('return-code');
    if (el) {
        el.textContent = code;
    }
}

async function cancelExecution() {
    if (!currentExecution) return;

    if (!confirm('Cancel this execution?')) return;

    try {
        const resp = await fetch(`/api/execute/${currentExecution}`, {
            method: 'DELETE'
        });

        if (resp.ok) {
            updateStatus('cancelled');
            if (sseHandler) {
                sseHandler.disconnect();
                sseHandler = null;
            }
        }
    } catch (e) {
        console.error('Error cancelling:', e);
    }
}

function toggleCommandInput() {
    const customSection = document.getElementById('custom-command-section');
    if (customSection) {
        customSection.style.display = customSection.style.display === 'none' ? 'block' : 'none';
    }
}

function addToHistory(execId, toolName, status) {
    const historyEl = document.getElementById('execution-history');
    if (!historyEl) return;

    const item = document.createElement('div');
    item.className = 'history-item border-bottom p-2';
    item.innerHTML = `
        <div class="d-flex justify-content-between">
            <span><strong>${toolName}</strong> (ID: ${execId})</span>
            <span class="badge bg-primary">${status}</span>
        </div>
        <small class="text-muted">${new Date().toLocaleString()}</small>
    `;
    historyEl.prepend(item);
}

function loadExecutionHistory() {
    fetch('/api/executions?limit=20')
        .then(r => r.json())
        .then(execs => {
            const historyEl = document.getElementById('execution-history');
            if (!historyEl) return;

            historyEl.innerHTML = '';
            execs.forEach(exec => {
                addToHistory(exec.execution_id, exec.tool_name, exec.status);
            });
        })
        .catch(err => console.error('Error loading history:', err));
}
