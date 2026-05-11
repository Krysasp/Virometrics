// custom-tool.js - Custom tool registration for Virometrics

// Initialize custom tool registration
function initCustomToolRegistration() {
    const container = document.getElementById('custom-tool-form');
    if (!container) return;
    
    setupCustomToolForm();
    loadCustomTools();
}

// Setup custom tool form
function setupCustomToolForm() {
    const form = document.getElementById('custom-tool-form');
    if (!form) return;
    
    // Load categories for dropdown
    const categorySelect = document.getElementById('custom-category');
    const subcategorySelect = document.getElementById('custom-subcategory');
    
    // Categories from existing data
    const categories = [...new Set(virometricsData.tools.map(t => t.category).filter(Boolean))].sort();
    categories.forEach(cat => {
        categorySelect.innerHTML += `<option value="${cat}">${cat}</option>`;
    });
    
    // Form submission
    const submitBtn = document.getElementById('submit-custom-tool');
    if (submitBtn) {
        submitBtn.addEventListener('click', handleCustomToolSubmit);
    }
    
    // Category change - update subcategories
    categorySelect.addEventListener('change', function() {
        const selectedCategory = this.value;
        const subcategories = [...new Set(
            virometricsData.tools
                .filter(t => t.category === selectedCategory)
                .map(t => t.subcategory)
                .filter(Boolean)
        )].sort();
        
        subcategorySelect.innerHTML = '<option value="">Select subcategory</option>';
        subcategories.forEach(sub => {
            subcategorySelect.innerHTML += `<option value="${sub}">${sub}</option>`;
        });
    });
}

// Handle custom tool form submission
async function handleCustomToolSubmit() {
    const form = document.getElementById('custom-tool-form');
    const submitBtn = document.getElementById('submit-custom-tool');
    
    // Gather form data
    const toolData = {
        name: document.getElementById('custom-name').value,
        description: document.getElementById('custom-description').value,
        category: document.getElementById('custom-category').value,
        subcategory: document.getElementById('custom-subcategory').value,
        url: document.getElementById('custom-url').value,
        package_manager: document.getElementById('custom-pkgmgr').value,
        setup_instructions: document.getElementById('custom-setup').value,
        input_formats: document.getElementById('custom-inputs').value.split(',').map(s => s.trim()).filter(Boolean),
        output_formats: document.getElementById('custom-outputs').value.split(',').map(s => s.trim()).filter(Boolean),
        languages: document.getElementById('custom-languages').value.split(',').map(s => s.trim()).filter(Boolean),
        license: document.getElementById('custom-license').value,
        is_custom: true,
        created_at: new Date().toISOString(),
        last_updated: new Date().toISOString()
    };
    
    // Validate required fields
    if (!toolData.name || !toolData.category) {
        alert('Please fill in Name and Category');
        return;
    }
    
    // Disable submit button
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Saving...';
    
    try {
        // Check if tool already exists
        const existing = virometricsData.tools.find(t => t.name === toolData.name);
        
        if (existing) {
            // Update existing
            const resp = await fetch('/api/tools/custom/update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    tool_name: toolData.name,
                    ...toolData
                })
            });
        } else {
            // Create new
            const resp = await fetch('/api/tools/custom', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(toolData)
            });
        }
        
        const result = await resp.json();
        
        if (result.success) {
            alert(`Tool "${toolData.name}" registered successfully!`);
            // Clear form
            form.reset();
            // Reload tools
            await loadToolData();
            // Refresh table and charts
            if (typeof renderAllCharts === 'function') {
                renderAllCharts();
            }
            if (typeof initToolsTable === 'function') {
                initToolsTable();
            }
        } else {
            alert(`Error: ${result.message || 'Failed to register tool'}`);
        }
        
    } catch (e) {
        console.error('Error saving custom tool:', e);
        alert('Error saving custom tool');
    } finally {
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<i class="bi bi-plus-circle"></i> Register Tool';
    }
}

// Load custom tools
function loadCustomTools() {
    const container = document.getElementById('custom-tools-list');
    if (!container) return;
    
    const customTools = virometricsData.tools.filter(t => t.is_custom);
    
    if (customTools.length === 0) {
        container.innerHTML = '<p class="text-muted small">No custom tools registered yet.</p>';
        return;
    }
    
    container.innerHTML = `
        <table class="table table-sm table-hover">
            <thead>
                <tr>
                    <th>Name</th>
                    <th>Category</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                ${customTools.map(t => `
                    <tr>
                        <td>${t.name}</td>
                        <td><span class="badge bg-primary">${t.category}</span></td>
                        <td>
                            <a href="tool.html?name=${encodeURIComponent(t.name)}" class="btn btn-sm btn-outline-primary">
                                <i class="bi bi-eye"></i>
                            </a>
                            <button class="btn btn-sm btn-outline-danger" onclick="deleteCustomTool('${t.name}')">
                                <i class="bi bi-trash"></i>
                            </button>
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}

// Delete custom tool
async function deleteCustomTool(toolName) {
    if (!confirm(`Delete custom tool "${toolName}"?`)) return;
    
    try {
        const resp = await fetch(`/api/tools/custom/${encodeURIComponent(toolName)}`, {
            method: 'DELETE'
        });
        
        const result = await resp.json();
        if (result.success) {
            alert(`Tool "${toolName}" deleted!`);
            await loadToolData();
            loadCustomTools();
        }
    } catch (e) {
        console.error('Error deleting tool:', e);
        alert('Error deleting tool');
    }
}

// Export for use in other modules
if (typeof window !== 'undefined') {
    window.initCustomToolRegistration = initCustomToolRegistration;
    window.handleCustomToolSubmit = handleCustomToolSubmit;
    window.loadCustomTools = loadCustomTools;
    window.deleteCustomTool = deleteCustomTool;
}
