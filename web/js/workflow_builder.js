/**
 * Workflow Builder JavaScript for Virometrics
 * Handles drag-and-drop interface, node connections, and workflow construction
 */

let network = null;
let nodes = null;
let edges = null;
let selectedNodeId = null;
let toolsData = [];
let categories = [];

// Initialize workflow builder
document.addEventListener('DOMContentLoaded', function() {
    initNetwork();
    loadTools();
    loadRecentWorkflows();
    setupEventHandlers();
});

/**
 * Initialize the Vis.js network for the workflow canvas
 */
function initNetwork() {
    const container = document.getElementById('workflow-network');
    
    nodes = new vis.DataSet([]);
    edges = new vis.DataSet([]);
    
    const data = {
        nodes: nodes,
        edges: edges
    };
    
    const options = {
        nodes: {
            shape: 'box',
            font: {
                size: 12,
                face: 'Arial'
            },
            margin: 10,
            borderWidth: 2,
            shadow: true
        },
        edges: {
            shape: 'straight',
            arrows: 'to',
            smooth: {
                type: 'cubic',
                roundness: 0.2
            },
            color: {
                color: '#848484',
                highlight: '#0d6efd'
            }
        },
        layout: {
            randomSeed: 2
        },
        interaction: {
            dragNodes: true,
            dragView: true,
            zoomView: true
        },
        physics: {
            enabled: true,
            solver: 'forceAtlas2Based',
            forceAtlas2Based: {
                gravitationalConstant: -50,
                centralGravity: 0.01,
                springLength: 100,
                springConstant: 0.08
            },
            stabilization: {
                iterations: 100
            }
        }
    };
    
    network = new vis.Network(container, data, options);
    
    // Handle node selection
    network.on("selectNode", function(params) {
        selectedNodeId = params.nodes[0];
        showNodeConfig(selectedNodeId);
    });
    
    network.on("deselectNode", function(params) {
        selectedNodeId = null;
        updateNodeConfigDisplay();
    });
    
    // Handle double-click on node
    network.on("doubleClick", function(params) {
        if (params.nodes.length > 0) {
            deleteNode(params.nodes[0]);
        }
    });
}

/**
 * Load available tools from the API
 */
function loadTools() {
    fetch('/api/tools?limit=100')
        .then(response => response.json())
        .then(data => {
            toolsData = data.tools || [];
            populateToolPalette();
            populateCategoryFilter();
        })
        .catch(error => {
            console.error('Error loading tools:', error);
            // Use sample data if API fails
            toolsData = getSampleTools();
            populateToolPalette();
            populateCategoryFilter();
        });
}

/**
 * Get sample tools for demo purposes
 */
function getSampleTools() {
    return [
        { id: 1, name: 'FastQC', category: 'Quality Control', language: 'Perl' },
        { id: 2, name: 'Trimmomatic', category: 'Quality Control', language: 'Java' },
        { id: 3, name: 'BWA', category: 'Alignment', language: 'C' },
        { id: 4, name: 'Bowtie2', category: 'Alignment', language: 'C++' },
        { id: 5, name: 'SAMtools', category: 'Processing', language: 'C' },
        { id: 6, name: 'iVar', category: 'Variant Calling', language: 'C' },
        { id: 7, name: 'BCFtools', category: 'Variant Calling', language: 'C' },
        { id: 8, name: 'SPAdes', category: 'Assembly', language: 'C++' },
        { id: 9, name: 'MEGAHIT', category: 'Assembly', language: 'C++' },
        { id: 10, name: 'Prokka', category: 'Annotation', language: 'Perl' },
        { id: 11, name: 'BLAST', category: 'Annotation', language: 'C' },
        { id: 12, name: 'HMMER', category: 'Annotation', language: 'C' }
    ];
}

/**
 * Populate the tool palette with available tools
 */
function populateToolPalette() {
    const palette = document.getElementById('tool-palette');
    const filter = document.getElementById('categoryFilter').value;
    
    let filteredTools = toolsData;
    if (filter) {
        filteredTools = toolsData.filter(tool => tool.category === filter);
    }
    
    palette.innerHTML = filteredTools.map(tool => `
        <div class="tool-node" data-tool-id="${tool.id}" data-tool-name="${tool.name}" 
             data-tool-category="${tool.category}" draggable="true">
            <small class="text-muted">${tool.category || 'Uncategorized'}</small>
            <div class="fw-bold">${tool.name}</div>
            <small>${tool.language || 'Unknown'}</small>
        </div>
    `).join('');
    
    // Add drag events
    palette.querySelectorAll('.tool-node').forEach(node => {
        node.addEventListener('dragstart', handleDragStart);
    });
}

/**
 * Populate category filter dropdown
 */
function populateCategoryFilter() {
    categories = [...new Set(toolsData.map(tool => tool.category))].filter(Boolean);
    const filter = document.getElementById('categoryFilter');
    
    categories.forEach(cat => {
        const option = document.createElement('option');
        option.value = cat;
        option.textContent = cat;
        filter.appendChild(option);
    });
}

/**
 * Handle drag start from palette
 */
function handleDragStart(event) {
    const toolId = event.target.dataset.toolId;
    const toolName = event.target.dataset.toolName;
    const toolCategory = event.target.dataset.toolCategory;
    
    event.dataTransfer.setData('toolId', toolId);
    event.dataTransfer.setData('toolName', toolName);
    event.dataTransfer.setData('toolCategory', toolCategory);
    event.dataTransfer.effectAllowed = 'copy';
}

/**
 * Handle drop on network canvas
 */
function initNetworkDragDrop() {
    const container = document.getElementById('workflow-network');
    
    container.addEventListener('dragover', function(e) {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'copy';
    });
    
    container.addEventListener('drop', function(e) {
        e.preventDefault();
        
        const toolId = parseInt(e.dataTransfer.getData('toolId'));
        const toolName = e.dataTransfer.getData('toolName');
        const toolCategory = e.dataTransfer.getData('toolCategory');
        
        // Get drop position relative to canvas
        const rect = container.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        
        // Convert to Vis.js coordinates
        const point = network.pointToGraph({ x: x, y: y });
        
        // Add node
        const nodeId = 'node_' + Date.now();
        nodes.add({
            id: nodeId,
            label: toolName,
            title: `${toolName} (${toolCategory})\nID: ${toolId}`,
            tool_id: toolId,
            x: point.x,
            y: point.y,
            color: {
                background: getCategoryColor(toolCategory)
            }
        });
        
        updateNodeCount();
    });
}

/**
 * Get color for category
 */
function getCategoryColor(category) {
    const colors = {
        'Quality Control': '#4caf50',
        'Alignment': '#2196f3',
        'Processing': '#ff9800',
        'Variant Calling': '#9c27b0',
        'Assembly': '#f44336',
        'Annotation': '#00bcd4'
    };
    return colors[category] || '#e0e0e0';
}

/**
 * Show node configuration panel
 */
function showNodeConfig(nodeId) {
    const node = nodes.get(nodeId);
    const configPanel = document.getElementById('node-config');
    
    if (!node) return;
    
    configPanel.innerHTML = `
        <div class="mb-3">
            <label class="form-label small">Node ID</label>
            <input type="text" class="form-control form-control-sm" value="${node.id}" readonly>
        </div>
        <div class="mb-3">
            <label class="form-label small">Tool Name</label>
            <input type="text" class="form-control form-control-sm" value="${node.label}" readonly>
        </div>
        <div class="mb-3">
            <label class="form-label small">Tool ID</label>
            <input type="number" class="form-control form-control-sm" id="nodeToolId" value="${node.tool_id}">
        </div>
        <div class="mb-3">
            <label class="form-label small">Position</label>
            <div class="row">
                <div class="col-6">
                    <small>X: ${Math.round(node.x)}</small>
                </div>
                <div class="col-6">
                    <small>Y: ${Math.round(node.y)}</small>
                </div>
            </div>
        </div>
        <button class="btn btn-sm btn-outline-primary w-100" onclick="editNodeParams(${node.id})">
            <i class="bi bi-sliders"></i> Edit Parameters
        </button>
    `;
}

/**
 * Update node configuration display
 */
function updateNodeConfigDisplay() {
    const configPanel = document.getElementById('node-config');
    if (!selectedNodeId) {
        configPanel.innerHTML = '<p class="text-muted small">Select a node to configure</p>';
    }
}

/**
 * Edit node parameters
 */
function editNodeParams(nodeId) {
    const node = nodes.get(nodeId);
    const modal = new bootstrap.Modal(document.getElementById('nodeParamsModal'));
    const body = document.getElementById('nodeParamsBody');
    
    body.innerHTML = `
        <div class="mb-3">
            <label class="form-label">Node Label</label>
            <input type="text" class="form-control" id="paramLabel" value="${node.label}">
        </div>
        <div class="mb-3">
            <label class="form-label">Tool ID</label>
            <input type="number" class="form-control" id="paramToolId" value="${node.tool_id}">
        </div>
    `;
    
    document.getElementById('saveNodeParams').onclick = function() {
        const newLabel = document.getElementById('paramLabel').value;
        const newToolId = parseInt(document.getElementById('paramToolId').value);
        
        nodes.update({
            id: nodeId,
            label: newLabel,
            tool_id: newToolId
        });
        
        modal.hide();
    };
    
    modal.show();
}

/**
 * Delete a node
 */
function deleteNode(nodeId) {
    if (confirm(`Delete node "${nodes.get(nodeId).label}"?`)) {
        nodes.remove(nodeId);
        edges.remove(edges.get({
            filter: function(edge) {
                return edge.from === nodeId || edge.to === nodeId;
            }
        }));
        updateNodeCount();
        updateConnectionCount();
    }
}

/**
 * Setup event handlers
 */
function setupEventHandlers() {
    // Category filter
    document.getElementById('categoryFilter').addEventListener('change', populateToolPalette);
    
    // Save workflow
    document.getElementById('saveWorkflow').addEventListener('click', saveWorkflow);
    
    // Template buttons
    document.querySelectorAll('[data-template]').forEach(btn => {
        btn.addEventListener('click', function() {
            loadTemplate(this.dataset.template);
        });
    });
    
    // Initialize drag-drop on network
    setTimeout(initNetworkDragDrop, 500);
}

/**
 * Save workflow to API
 */
function saveWorkflow() {
    const workflowName = document.getElementById('workflowName').value || 'Untitled Workflow';
    const workflowDescription = document.getElementById('workflowDescription').value;
    
    const workflowData = {
        name: workflowName,
        description: workflowDescription,
        nodes: nodes.get(),
        connections: edges.get().map(edge => ({
            source_node_id: edge.from,
            target_node_id: edge.to,
            source_output: 'output',
            target_input: 'input'
        }))
    };
    
    fetch('/api/workflows', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(workflowData)
    })
    .then(response => response.json())
    .then(data => {
        alert(`Workflow "${workflowName}" saved with ID: ${data.workflow_id}`);
        loadRecentWorkflows();
    })
    .catch(error => {
        console.error('Error saving workflow:', error);
        alert('Error saving workflow: ' + error.message);
    });
}

/**
 * Load workflow template
 */
function loadTemplate(templateName) {
    const templates = {
        'variant_calling': {
            name: 'Variant Calling Pipeline',
            description: 'Standard variant calling workflow',
            nodes: [
                { id: 'node_1', label: 'FastQC', tool_id: 1, x: 100, y: 200 },
                { id: 'node_2', label: 'Trimmomatic', tool_id: 2, x: 300, y: 200 },
                { id: 'node_3', label: 'BWA', tool_id: 3, x: 500, y: 200 },
                { id: 'node_4', label: 'SAMtools', tool_id: 5, x: 700, y: 200 },
                { id: 'node_5', label: 'iVar', tool_id: 6, x: 900, y: 200 }
            ],
            edges: [
                { from: 'node_1', to: 'node_2' },
                { from: 'node_2', to: 'node_3' },
                { from: 'node_3', to: 'node_4' },
                { from: 'node_4', to: 'node_5' }
            ]
        },
        'assembly': {
            name: 'Assembly Pipeline',
            description: 'De novo assembly workflow',
            nodes: [
                { id: 'node_1', label: 'FastQC', tool_id: 1, x: 100, y: 200 },
                { id: 'node_2', label: 'SPAdes', tool_id: 8, x: 350, y: 200 },
                { id: 'node_3', label: 'QUAST', tool_id: 1, x: 600, y: 200 }
            ],
            edges: [
                { from: 'node_1', to: 'node_2' },
                { from: 'node_2', to: 'node_3' }
            ]
        },
        'annotation': {
            name: 'Annotation Pipeline',
            description: 'Genome annotation workflow',
            nodes: [
                { id: 'node_1', label: 'Prokka', tool_id: 10, x: 200, y: 200 },
                { id: 'node_2', label: 'BLAST', tool_id: 11, x: 450, y: 200 },
                { id: 'node_3', label: 'HMMER', tool_id: 12, x: 700, y: 200 }
            ],
            edges: [
                { from: 'node_1', to: 'node_2' },
                { from: 'node_2', to: 'node_3' }
            ]
        }
    };
    
    const template = templates[templateName];
    if (!template) return;
    
    // Clear existing
    nodes.clear();
    edges.clear();
    
    // Set workflow name and description
    document.getElementById('workflowName').value = template.name;
    document.getElementById('workflowDescription').value = template.description;
    
    // Add nodes
    template.nodes.forEach(node => {
        nodes.add(node);
    });
    
    // Add edges
    template.edges.forEach(edge => {
        edges.add(edge);
    });
    
    updateNodeCount();
    updateConnectionCount();
}

/**
 * Load recent workflows
 */
function loadRecentWorkflows() {
    fetch('/api/workflows?limit=5')
        .then(response => response.json())
        .then(data => {
            const container = document.getElementById('recent-workflows');
            const workflows = data.workflows || [];
            
            if (workflows.length === 0) {
                container.innerHTML = '<p class="text-muted small">No recent workflows</p>';
                return;
            }
            
            container.innerHTML = `
                <table class="table table-sm table-hover">
                    <thead>
                        <tr>
                            <th>Name</th>
                            <th>Created</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${workflows.map(wf => `
                            <tr>
                                <td>${wf.name}</td>
                                <td>${new Date(wf.created_at).toLocaleDateString()}</td>
                                <td>
                                    <button class="btn btn-sm btn-outline-primary" onclick="loadWorkflow(${wf.id})">
                                        <i class="bi bi-folder-open"></i>
                                    </button>
                                </td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            `;
        })
        .catch(error => {
            console.error('Error loading recent workflows:', error);
            document.getElementById('recent-workflows').innerHTML = 
                '<p class="text-muted small">Error loading workflows</p>';
        });
}

/**
 * Load workflow from API
 */
function loadWorkflow(workflowId) {
    fetch(`/api/workflows/${workflowId}`)
        .then(response => response.json())
        .then(data => {
            const workflow = data.workflow;
            
            // Clear existing
            nodes.clear();
            edges.clear();
            
            // Set workflow info
            document.getElementById('workflowName').value = workflow.name;
            document.getElementById('workflowDescription').value = workflow.description || '';
            
            // Add nodes
            workflow.nodes.forEach(node => {
                nodes.add({
                    id: node.node_id,
                    label: node.name,
                    tool_id: node.tool_id,
                    x: node.x,
                    y: node.y
                });
            });
            
            // Add edges
            workflow.connections.forEach(conn => {
                edges.add({
                    from: conn.source_node_id,
                    to: conn.target_node_id
                });
            });
            
            updateNodeCount();
            updateConnectionCount();
        })
        .catch(error => {
            console.error('Error loading workflow:', error);
        });
}

/**
 * Update node count display
 */
function updateNodeCount() {
    document.getElementById('nodeCount').textContent = nodes.length;
}

/**
 * Update connection count display
 */
function updateConnectionCount() {
    document.getElementById('connectionCount').textContent = edges.length;
}
