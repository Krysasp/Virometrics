// register-tool.js - Custom tool registration logic

let currentToolId = null;

// Initialize form
document.addEventListener('DOMContentLoaded', function() {
    loadExistingTools();
    setupFormValidation();
    setupLivePreview();
});

// Load existing tools for reference
async function loadExistingTools() {
    try {
        const resp = await fetch('/api/tools?limit=50');
        const data = await resp.json();
        window.existingTools = data.tools || [];
    } catch (error) {
        console.error('Error loading tools:', error);
    }
}

// Setup form validation
function setupFormValidation() {
    const form = document.getElementById('register-tool-form');
    
    form.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const formData = collectFormData();
        
        try {
            const response = await fetch('/api/tools/register', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(formData)
            });
            
            const result = await response.json();
            
            if (result.success || result.tool_id) {
                currentToolId = result.tool_id || result.id;
                showSuccessMessage(`Tool "${formData.name}" registered successfully!`);
                
                // Redirect to tool detail page after delay
                setTimeout(() => {
                    window.location.href = `tool.html?name=${encodeURIComponent(formData.name)}`;
                }, 2000);
            } else {
                showErrorMessage(result.error || 'Failed to register tool');
            }
        } catch (error) {
            console.error('Error registering tool:', error);
            showErrorMessage('Network error while registering tool');
        }
    });
    
    // Setup live preview
    form.addEventListener('input', updateLivePreview);
}

// Collect form data
function collectFormData() {
    return {
        name: document.getElementById('tool-name').value.trim(),
        version: document.getElementById('tool-version').value.trim(),
        description: document.getElementById('tool-description').value.trim(),
        category: document.getElementById('tool-category').value,
        subcategory: document.getElementById('tool-subcategory').value.trim(),
        language: document.getElementById('tool-language').value,
        package_manager: document.getElementById('tool-pkgmgr').value,
        license: document.getElementById('tool-license').value.trim(),
        url: document.getElementById('tool-url').value.trim(),
        doi: document.getElementById('tool-doi').value.trim(),
        docs_url: document.getElementById('tool-docs-url').value.trim(),
        input_formats: document.getElementById('tool-input-formats').value.split(',').map(s => s.trim()).filter(Boolean),
        output_formats: document.getElementById('tool-output-formats').value.split(',').map(s => s.trim()).filter(Boolean),
        install_command: document.getElementById('tool-install-cmd').value.trim(),
        created_by: 'admin', // Could be from authentication
        is_public: true
    };
}

// Update live preview
function updateLivePreview() {
    const preview = document.getElementById('tool-preview');
    
    const name = document.getElementById('tool-name').value;
    const description = document.getElementById('tool-description').value;
    const category = document.getElementById('tool-category').value;
    const language = document.getElementById('tool-language').value;
    const pkgmgr = document.getElementById('tool-pkgmgr').value;
    const license = document.getElementById('tool-license').value;
    const url = document.getElementById('tool-url').value;
    
    if (!name) {
        preview.innerHTML = `
            <div class="text-center text-muted py-4">
                <i class="bi bi-tools display-4"></i>
                <p class="mt-2">Fill in the form to see preview</p>
            </div>
        `;
        return;
    }
    
    let badges = '';
    if (category) badges += `<span class="badge bg-primary me-1">${category}</span>`;
    if (subcategory) badges += `<span class="badge bg-secondary me-1">${subcategory}</span>`;
    if (language) badges += `<span class="badge bg-info me-1">${language}</span>`;
    if (pkgmgr) badges += `<span class="badge bg-success me-1">${pkgmgr}</span>`;
    
    preview.innerHTML = `
        <div class="tool-detail-preview">
            <h5 class="mb-1">${name}</h5>
            ${badges ? `<div class="mb-2">${badges}</div>` : ''}
            <p class="text-muted small mb-2">${description || 'No description'}</p>
            ${license ? `<small class="text-muted"><i class="bi bi-copyright"></i> ${license}</small>` : ''}
            ${url ? `<a href="${url}" target="_blank" class="btn btn-sm btn-outline-primary mt-2"><i class="bi bi-github"></i> View Repository</a>` : ''}
        </div>
    `;
}

// Show success message
function showSuccessMessage(message) {
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
function showErrorMessage(message) {
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

// Validate GitHub URL format
function validateGithubUrl(url) {
    if (!url) return true;
    const githubRegex = /^https:\/\/github\.com\/[a-zA-Z0-9_-]+\/[a-zA-Z0-9_-]+/;
    return githubRegex.test(url);
}

// Validate DOI format
function validateDOI(doi) {
    if (!doi) return true;
    const doiRegex = /^10\.\d{4,}\/.+/;
    return doiRegex.test(doi);
}

// Export functions for use in other modules
if (typeof window !== 'undefined') {
    window.collectFormData = collectFormData;
    window.validateGithubUrl = validateGithubUrl;
    window.validateDOI = validateDOI;
}
