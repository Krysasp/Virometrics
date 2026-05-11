// network.js - Tool relationship network visualization for Virometrics

let networkVisualization = null;
let networkNodes = null;
let networkEdges = null;

// Initialize network visualization
function initNetworkVisualization() {
    const container = document.getElementById('network-chart');
    if (!container) return;

    // Build nodes and edges
    const { nodes, edges } = buildToolNetwork();
    
    networkNodes = new vis.DataSet(nodes);
    networkEdges = new vis.DataSet(edges);
    
    const data = {
        nodes: networkNodes,
        edges: networkEdges
    };
    
    const options = {
        nodes: {
            shape: 'dot',
            size: 16,
            font: {
                size: 12,
                face: 'Arial',
                color: '#333'
            },
            borderWidth: 2,
            shadow: true
        },
        edges: {
            width: 1,
            color: {
                color: '#888',
                opacity: 0.4
            },
            smooth: {
                type: 'continuous'
            }
        },
        groups: getCategoryGroups(),
        layout: {
            randomSeed: 2,
            improvedLayout: true
        },
        interaction: {
            hover: true,
            tooltipDelay: 200
        },
        physics: {
            enabled: true,
            solver: 'forceAtlas2Based',
            forceAtlas2Based: {
                gravitationalConstant: -50,
                centralGravity: 0.01,
                springLength: 150,
                springConstant: 0.08
            },
            stabilization: {
                iterations: 200
            }
        }
    };
    
    networkVisualization = new vis.Network(container, data, options);
    
    // Handle node click
    networkVisualization.on("selectNode", function(params) {
        const node = networkNodes.get(params.nodes[0]);
        showNetworkNodeDetails(node);
    });
    
    networkVisualization.on("deselectNode", function(params) {
        hideNetworkNodeDetails();
    });
    
    // Setup layout buttons
    setupNetworkLayoutButtons();
}

// Build tool network from data
function buildToolNetwork() {
    const nodes = [];
    const edges = [];
    const categoryMap = new Map();
    const formatMap = new Map();
    
    // Group tools by category
    virometricsData.tools.forEach(tool => {
        const category = tool.category || 'Uncategorized';
        if (!categoryMap.has(category)) {
            categoryMap.set(category, []);
        }
        categoryMap.get(category).push(tool);
    });
    
    // Create nodes for each tool
    virometricsData.tools.forEach(tool => {
        const category = tool.category || 'Uncategorized';
        const color = getCategoryColor(category);
        
        nodes.push({
            id: tool.id || tool.name,
            label: tool.name,
            title: `${tool.name}\n${category}\n${tool.github_stars || 0} stars`,
            group: category,
            color: color,
            tool_data: tool
        });
    });
    
    // Create edges based on shared categories
    categoryMap.forEach((tools, category) => {
        if (tools.length > 1) {
            // Connect tools in the same category
            for (let i = 0; i < tools.length; i++) {
                for (let j = i + 1; j < tools.length; j++) {
                    // Only create edge if tools don't have too many connections
                    const tool1 = tools[i];
                    const tool2 = tools[j];
                    edges.push({
                        from: tool1.id || tool1.name,
                        to: tool2.id || tool2.name,
                        category: category,
                        type: 'same_category'
                    });
                }
            }
        }
    });
    
    // Create edges based on input/output format compatibility
    virometricsData.tools.forEach(tool1 => {
        let inputs = tool1.input_formats;
        if (typeof inputs === 'string') {
            try { inputs = JSON.parse(inputs); } catch(e) { inputs = []; }
        }
        
        if (!Array.isArray(inputs)) inputs = [];
        
        inputs.forEach(inputFormat => {
            virometricsData.tools.forEach(tool2 => {
                if (tool1.id === tool2.id) return;
                
                let outputs = tool2.output_formats;
                if (typeof outputs === 'string') {
                    try { outputs = JSON.parse(outputs); } catch(e) { outputs = []; }
                }
                
                if (!Array.isArray(outputs)) outputs = [];
                
                if (outputs.includes(inputFormat)) {
                    edges.push({
                        from: tool2.id || tool2.name,
                        to: tool1.id || tool1.name,
                        format: inputFormat,
                        type: 'format_compatible',
                        dashes: true
                    });
                }
            });
        });
    });
    
    // Limit edges for performance
    const maxEdges = 500;
    if (edges.length > maxEdges) {
        // Prioritize format compatibility edges
        const compatEdges = edges.filter(e => e.type === 'format_compatible');
        const categoryEdges = edges.filter(e => e.type === 'same_category');
        
        const finalEdges = [
            ...compatEdges.slice(0, Math.min(200, compatEdges.length)),
            ...categoryEdges.slice(0, Math.min(300, categoryEdges.length))
        ];
        
        return { nodes, edges: finalEdges };
    }
    
    return { nodes, edges };
}

// Get color for category
function getCategoryColor(category) {
    const colors = {
        'Virus and Phage Identification': '#4682B4',
        'Host Prediction': '#6A5ACD',
        'Genome Analysis': '#20B2AA',
        'Functional Analysis': '#DB7093',
        'Taxonomy': '#9370DB',
        'Databases': '#4169E1',
        'Sequence Databases': '#FF6347',
        'Visualization and Infrastructure': '#3CB371',
        'CRISPR Analysis': '#1E90FF',
        'Sequence Analysis': '#FF8C00',
        'Metagenome Analysis': '#4682B4',
        'Assembly': '#20B2AA',
        'Quality Control': '#DB7093',
        'Alignment': '#6A5ACD',
        'Variant Calling': '#FF6347'
    };
    return colors[category] || '#6c757d';
}

// Get category groups for Vis.js
function getCategoryGroups() {
    const groups = {};
    const colors = {
        'Virus and Phage Identification': '#4682B4',
        'Host Prediction': '#6A5ACD',
        'Genome Analysis': '#20B2AA',
        'Functional Analysis': '#DB7093',
        'Taxonomy': '#9370DB',
        'Databases': '#4169E1',
        'Sequence Databases': '#FF6347',
        'Visualization and Infrastructure': '#3CB371',
        'CRISPR Analysis': '#1E90FF',
        'Sequence Analysis': '#FF8C00',
        'Metagenome Analysis': '#4682B4',
        'Assembly': '#20B2AA',
        'Quality Control': '#DB7093',
        'Alignment': '#6A5ACD',
        'Variant Calling': '#FF6347'
    };
    
    Object.keys(colors).forEach(category => {
        groups[category] = { color: colors[category] };
    });
    
    return groups;
}

// Setup network layout buttons
function setupNetworkLayoutButtons() {
    document.getElementById('network-layout-force').onclick = function() {
        networkVisualization.setOptions({
            physics: {
                enabled: true,
                solver: 'forceAtlas2Based'
            }
        });
    };
    
    document.getElementById('network-layout-hierarchical').onclick = function() {
        networkVisualization.setOptions({
            layout: {
                hierarchy: {
                    level: 'degree',
                    direction: 'LR'
                }
            },
            physics: {
                enabled: true,
                solver: 'hierarchicalRepulsion'
            }
        });
    };
    
    document.getElementById('network-layout-circle').onclick = function() {
        networkVisualization.setOptions({
            layout: {
                randomSeed: 2
            },
            physics: {
                enabled: true,
                solver: 'circleLayout'
            }
        });
    };
}

// Show node details in a panel
function showNetworkNodeDetails(node) {
    let panel = document.getElementById('network-details-panel');
    if (!panel) {
        panel = document.createElement('div');
        panel.id = 'network-details-panel';
        panel.className = 'mt-3 p-3 border rounded bg-light';
        document.getElementById('network-chart').parentNode.appendChild(panel);
    }
    
    const tool = node.tool_data;
    panel.innerHTML = `
        <div class="d-flex justify-content-between align-items-start">
            <div>
                <h6 class="mb-1">${tool.name}</h6>
                <small class="text-muted">${tool.category || 'Uncategorized'}</small>
                <p class="small mt-1 mb-0">${tool.description || 'No description'}</p>
            </div>
            <div class="text-end">
                <span class="badge bg-primary">${tool.github_stars || 0} stars</span>
                ${tool.doi ? '<br><small class="text-success"><i class="bi bi-journal-text"></i> DOI</small>' : ''}
            </div>
        </div>
        <div class="mt-2">
            <a href="${tool.url || '#'}" target="_blank" class="btn btn-sm btn-outline-primary">
                <i class="bi bi-github"></i> View Repository
            </a>
        </div>
    `;
    panel.style.display = 'block';
}

// Hide node details panel
function hideNetworkNodeDetails() {
    const panel = document.getElementById('network-details-panel');
    if (panel) {
        panel.style.display = 'none';
    }
}

// Export for use in other modules
if (typeof window !== 'undefined') {
    window.initNetworkVisualization = initNetworkVisualization;
    window.buildToolNetwork = buildToolNetwork;
}
