// execute-workflow.js - Workflow execution logic

let currentWorkflowId = null;
let currentExecutionId = null;
let workflowPollingInterval = null;
let elapsedTime = 0;
let elapsedTimeInterval = null;

// Initialize workflow executor page
document.addEventListener('DOMContentLoaded', function() {
    loadWorkflows();
    setupEventListeners();
    initTheme();
});

// Load available workflows
async function loadWorkflows() {
    try {
        const resp = await fetch('/api/workflows?is_public=1');
        const data = await resp.json();
        const workflows = data.workflows || [];
        
        const select = document.getElementById('workflow-select');
        select.innerHTML = '<option value="">-- Select a workflow --</option>';
        
        workflows.forEach(workflow => {
            const option = document.createElement('option');
            option.value = workflow.id;
            option.textContent = workflow.name;
            select.appendChild(option);
        });
        
        if (workflows.length === 0) {
            select.disabled = true;
            select.parentElement.parentElement.classList.add('opacity-50');
        }
    } catch (error) {
        console.error('Error loading workflows:', error);
        showError('Failed to load workflows');
    }
}

// Setup event listeners
function setupEventListeners() {
    const select = document.getElementById('workflow-select');
    select.addEventListener('change', handleWorkflowSelect);
    
    document.getElementById('btn-execute-workflow').addEventListener('click', executeWorkflow);
    document.getElementById('btn-stop-workflow').addEventListener('click', stopWorkflow);
    document.getElementById('btn-clear-output').addEventListener('click', clearOutput);
}

// Handle workflow selection
async function handleWorkflowSelect(event) {
    const workflowId = event.target.value;
    
    if (!workflowId) {
        hideWorkflowDetails();
        return;
    }
    
    try {
        const resp = await fetch(`/api/workflows/${workflowId}`);
        const workflow = await resp.json();
        
        if (workflow.error) {
            showError(workflow.error);
            return;
        }
        
        displayWorkflowDetails(workflow);
        currentWorkflowId = workflowId;
        
    } catch (error) {
        console.error('Error loading workflow:', error);
        showError('Failed to load workflow details');
    }
}

// Display workflow details
function displayWorkflowDetails(workflow) {
    // Show details card
    document.getElementById('workflow-details-card').style.display = 'block';
    document.getElementById('workflow-steps-card').style.display = 'block';
    document.getElementById('execution-params-card').style.display = 'block';
    document.getElementById('btn-execute-workflow').disabled = false;
    
    // Set workflow info
    document.getElementById('workflow-name').textContent = workflow.name;
    document.getElementById('workflow-description').textContent = workflow.description || 'No description';
    document.getElementById('workflow-created').textContent = formatDate(workflow.created_at);
    document.getElementById('workflow-created-by').textContent = workflow.created_by || 'Unknown';
    
    // Display workflow steps
    displayWorkflowSteps(workflow.workflow_json);
    
    // Display execution parameters
    displayExecutionParams(workflow.workflow_json);
}

// Hide workflow details
function hideWorkflowDetails() {
    document.getElementById('workflow-details-card').style.display = 'none';
    document.getElementById('workflow-steps-card').style.display = 'none';
    document.getElementById('execution-params-card').style.display = 'none';
    document.getElementById('btn-execute-workflow').disabled = true;
    currentWorkflowId = null;
}

// Display workflow steps
function displayWorkflowSteps(workflowJson) {
    const container = document.getElementById('workflow-steps-preview');
    const steps = workflowJson?.nodes || [];
    
    if (steps.length === 0) {
        container.innerHTML = '<p class="text-muted small">No steps defined</p>';
        return;
    }
    
    let html = '<ul class="list-unstyled mb-0">';
    steps.forEach((step, index) => {
        html += `
            <li class="small mb-2">
                <i class="bi bi-box-seam text-primary"></i>
                <strong>Step ${index + 1}:</strong> ${step.label || step.name}
                <span class="text-muted">(${getToolName(step.tool_id)})</span>
            </li>
        `;
    });
    html += '</ul>';
    
    container.innerHTML = html;
}

// Display execution parameters
function displayExecutionParams(workflowJson) {
    const container = document.getElementById('execution-params');
    const nodes = workflowJson?.nodes || [];
    
    if (nodes.length === 0) {
        container.innerHTML = '<p class="text-muted small">No parameters required</p>';
        return;
    }
    
    let html = '<div class="param-form">';
    nodes.forEach((node, index) => {
        html += `
            <fieldset class="mb-3 pb-3">
                <legend class="small text-primary">Step ${index + 1}: ${node.label || node.name}</legend>
                <div class="mb-2">
                    <label class="form-label small">Working Directory</label>
                    <input type="text" class="form-control form-control-sm" 
                           id="param-working-dir-${node.id}" 
                           placeholder="/home/user/workflow_output">
                </div>
                <div class="mb-2">
                    <label class="form-label small">Execution Name</label>
                    <input type="text" class="form-control form-control-sm" 
                           id="param-exec-name-${node.id}" 
                           value="${node.label || node.name}_execution">
                </div>
            </fieldset>
        `;
    });
    html += '</div>';
    
    container.innerHTML = html;
}

// Get tool name by ID
function getToolName(toolId) {
    if (typeof virometricsData !== 'undefined' && virometricsData.tools) {
        const tool = virometricsData.tools.find(t => t.id === parseInt(toolId));
        return tool ? tool.name : `Tool ${toolId}`;
    }
    return `Tool ${toolId}`;
}

// Format date
function formatDate(dateString) {
    if (!dateString) return 'Unknown';
    const date = new Date(dateString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
}

// Execute workflow
async function executeWorkflow() {
    if (!currentWorkflowId) {
        showError('Please select a workflow first');
        return;
    }
    
    const btnExecute = document.getElementById('btn-execute-workflow');
    const btnStop = document.getElementById('btn-stop-workflow');
    
    btnExecute.disabled = true;
    btnStop.disabled = false;
    btnExecute.innerHTML = '<i class="bi bi-hourglass-split"></i> Executing...';
    
    try {
        const resp = await fetch('/api/workflows/execute', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                workflow_id: parseInt(currentWorkflowId),
                execution_name: `Execution_${Date.now()}`,
                created_by: 'user'
            })
        });
        
        const result = await resp.json();
        
        if (result.workflow_exec_id) {
            currentExecutionId = result.workflow_exec_id;
            startWorkflowMonitoring(currentExecutionId);
            showSuccess('Workflow execution started!');
        } else {
            showError(result.error || 'Failed to start workflow');
            btnExecute.disabled = false;
            btnExecute.innerHTML = '<i class="bi bi-play-fill"></i> Execute Workflow';
            btnStop.disabled = true;
        }
    } catch (error) {
        console.error('Error executing workflow:', error);
        showError('Network error while executing workflow');
        btnExecute.disabled = false;
        btnExecute.innerHTML = '<i class="bi bi-play-fill"></i> Execute Workflow';
        btnStop.disabled = true;
    }
}

// Start workflow monitoring
function startWorkflowMonitoring(executionId) {
    // Show status cards
    document.getElementById('execution-status-card').style.display = 'block';
    document.getElementById('step-status-card').style.display = 'block';
    document.getElementById('execution-output-card').style.display = 'block';
    
    // Update status badge
    document.getElementById('execution-status-badge').textContent = 'Running';
    document.getElementById('execution-status-badge').className = 'badge bg-warning';
    
    // Set execution ID
    document.getElementById('execution-id').textContent = executionId;
    document.getElementById('execution-started').textContent = new Date().toLocaleString();
    
    // Start elapsed time counter
    elapsedTime = 0;
    elapsedTimeInterval = setInterval(updateElapsedTime, 1000);
    
    // Poll for status updates
    workflowPollingInterval = setInterval(() => {
        pollWorkflowStatus(executionId);
    }, 2000);
}

// Poll workflow status
async function pollWorkflowStatus(executionId) {
    try {
        const resp = await fetch(`/api/workflows/execute/${executionId}`);
        const status = await resp.json();
        
        updateExecutionStatus(status);
        
        // Check if completed
        if (status.status === 'completed' || status.status === 'failed') {
            stopWorkflowMonitoring(status);
        }
    } catch (error) {
        console.error('Error polling workflow status:', error);
    }
}

// Update execution status display
function updateExecutionStatus(status) {
    // Update status badge
    const badge = document.getElementById('execution-status-badge');
    badge.textContent = status.status.charAt(0).toUpperCase() + status.status.slice(1);
    
    if (status.status === 'running') {
        badge.className = 'badge bg-warning';
    } else if (status.status === 'completed') {
        badge.className = 'badge bg-success';
    } else if (status.status === 'failed') {
        badge.className = 'badge bg-danger';
    }
    
    // Update progress
    if (status.steps) {
        const totalSteps = status.steps.length;
        const completedSteps = status.steps.filter(s => s.status === 'completed').length;
        const progress = (completedSteps / totalSteps) * 100;
        
        document.getElementById('execution-progress-bar').style.width = `${progress}%`;
        document.getElementById('execution-progress-bar').className = 
            `progress-bar ${status.status === 'completed' ? 'bg-success' : 'bg-warning'}`;
        document.getElementById('execution-progress-text').textContent = 
            `${completedSteps}/${totalSteps} steps completed`;
    }
    
    // Update step status list
    updateStepStatusList(status.steps);
}

// Update step status list
function updateStepStatusList(steps) {
    if (!steps) return;
    
    const container = document.getElementById('step-status-list');
    let html = '<ul class="list-unstyled mb-0">';
    
    steps.forEach((step, index) => {
        const statusClass = step.status === 'completed' ? 'completed' : 
                           step.status === 'running' ? 'running' : 
                           step.status === 'failed' ? 'failed' : 'pending';
        
        html += `
            <li class="workflow-step ${statusClass} mb-2">
                <span class="step-status ${statusClass}"></span>
                <strong>Step ${index + 1}:</strong> ${step.tool_name || 'Unknown'}
                <span class="text-muted small ms-2">(${step.status})</span>
                ${step.execution_time ? `<small class="text-muted d-block">Duration: ${formatDuration(step.execution_time)}</small>` : ''}
            </li>
        `;
    });
    
    html += '</ul>';
    container.innerHTML = html;
}

// Format duration
function formatDuration(seconds) {
    if (!seconds) return '0s';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

// Update elapsed time
function updateElapsedTime() {
    elapsedTime++;
    const mins = Math.floor(elapsedTime / 60);
    const secs = elapsedTime % 60;
    document.getElementById('execution-elapsed').textContent = 
        `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

// Stop workflow monitoring
function stopWorkflowMonitoring(status) {
    clearInterval(workflowPollingInterval);
    clearInterval(elapsedTimeInterval);
    
    const btnExecute = document.getElementById('btn-execute-workflow');
    const btnStop = document.getElementById('btn-stop-workflow');
    
    btnExecute.disabled = false;
    btnStop.disabled = true;
    btnExecute.innerHTML = '<i class="bi bi-play-fill"></i> Execute Workflow';
    
    // Update status badge
    const badge = document.getElementById('execution-status-badge');
    badge.className = status.status === 'completed' ? 'badge bg-success' : 'badge bg-danger';
    
    if (status.status === 'completed') {
        showSuccess(`Workflow completed successfully in ${document.getElementById('execution-elapsed').textContent}`);
    } else {
        showError(`Workflow failed: ${status.error || 'Unknown error'}`);
    }
}

// Stop workflow
async function stopWorkflow() {
    if (!currentExecutionId) return;
    
    try {
        const resp = await fetch(`/api/workflows/execute/${currentExecutionId}/cancel`, {
            method: 'POST'
        });
        
        const result = await resp.json();
        
        if (result.success) {
            stopWorkflowMonitoring({ status: 'cancelled' });
            showSuccess('Workflow cancelled');
        } else {
            showError(result.error || 'Failed to stop workflow');
        }
    } catch (error) {
        console.error('Error stopping workflow:', error);
        showError('Network error while stopping workflow');
    }
}

// Clear output
function clearOutput() {
    const output = document.getElementById('workflow-output');
    output.innerHTML = `
        <div class="text-muted text-center py-4">
            <i class="bi bi-terminal display-6"></i>
            <p class="mt-2">Output cleared</p>
        </div>
    `;
}

// Show success message
function showSuccess(message) {
    const alert = document.createElement('div');
    alert.className = 'alert alert-success alert-dismissible fade show';
    alert.innerHTML = `
        <i class="bi bi-check-circle"></i> ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    const container = document.querySelector('.dashboard-container');
    container.insertBefore(alert, container.firstChild);
    
    setTimeout(() => alert.classList.remove('show'), 5000);
}

// Show error message
function showError(message) {
    const alert = document.createElement('div');
    alert.className = 'alert alert-danger alert-dismissible fade show';
    alert.innerHTML = `
        <i class="bi bi-exclamation-circle"></i> ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    const container = document.querySelector('.dashboard-container');
    container.insertBefore(alert, container.firstChild);
    
    setTimeout(() => alert.classList.remove('show'), 5000);
}

// Initialize theme
function initTheme() {
    const savedTheme = localStorage.getItem('virometrics-theme');
    if (savedTheme === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark');
        document.body.classList.add('dark-mode');
        $('#themeToggle i').removeClass('bi-moon').addClass('bi-sun');
    }
}
