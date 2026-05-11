// recommendation.js - Tool recommendation engine for Virometrics

// Research question templates
const RESEARCH_QUESTIONS = {
    'metagenome': {
        title: 'Metagenome Analysis',
        description: 'Analyze complex microbial communities from environmental samples',
        recommended_categories: ['Metagenome Analysis', 'Taxonomic Classification', 'Functional Analysis'],
        keywords: ['metagenome', 'microbiome', 'community', 'environmental', 'mixed']
    },
    'variant_calling': {
        title: 'Variant Calling',
        description: 'Identify genetic variants and mutations in viral genomes',
        recommended_categories: ['Variant Calling', 'Sequence Analysis', 'Alignment'],
        keywords: ['variant', 'mutation', 'SNP', 'indel', 'polymorphism']
    },
    'assembly': {
        title: 'Genome Assembly',
        description: 'Reconstruct complete viral genomes from sequencing reads',
        recommended_categories: ['Assembly', 'Metagenome Analysis', 'Sequence Assembly'],
        keywords: ['assembly', 'contig', 'reconstruct', 'genome', 'reads']
    },
    'host_prediction': {
        title: 'Host Prediction',
        description: 'Predict bacterial hosts for bacteriophages',
        recommended_categories: ['Host Prediction', 'Taxonomic Classification'],
        keywords: ['host', 'phage', 'bacteriophage', 'infection', 'CRISPR']
    },
    'annotation': {
        title: 'Genome Annotation',
        description: 'Annotate genes and functional elements in viral genomes',
        recommended_categories: ['Genome Annotation', 'Functional Analysis', 'Gene Prediction'],
        keywords: ['annotate', 'gene', 'ORF', 'function', 'protein']
    },
    'quality_control': {
        title: 'Quality Control',
        description: 'Assess and improve quality of sequencing data',
        recommended_categories: ['Quality Control', 'Preprocessing'],
        keywords: ['quality', 'filter', 'trim', 'clean', 'fastqc']
    },
    'taxonomy': {
        title: 'Taxonomic Classification',
        description: 'Classify viral sequences into taxonomic groups',
        recommended_categories: ['Taxonomic Classification', 'Virus Identification'],
        keywords: ['taxonomy', 'classification', 'identify', 'virus', 'phage']
    },
    'expression': {
        title: 'Expression Analysis',
        description: 'Analyze gene expression patterns in viral infections',
        recommended_categories: ['Functional Analysis', 'Expression Analysis'],
        keywords: ['expression', 'transcriptome', 'RNA-seq', 'differential', 'expression']
    }
};

// Initialize recommendation engine
function initRecommendationEngine() {
    loadRecommendedTools();
    setupRecommendationUI();
}

// Load recommended tools based on research question
async function loadRecommendedTools(questionType) {
    const question = RESEARCH_QUESTIONS[questionType];
    if (!question) {
        console.warn(`Unknown research question type: ${questionType}`);
        return [];
    }

    const recommendations = [];
    
    // Find tools matching recommended categories
    const categoryTools = virometricsData.tools.filter(tool => {
        if (!tool.category) return false;
        return question.recommended_categories.some(cat => 
            tool.category.toLowerCase().includes(cat.toLowerCase())
        );
    });

    // Score tools based on relevance
    categoryTools.forEach(tool => {
        let score = 0;
        
        // Category match (high priority)
        if (question.recommended_categories.includes(tool.category)) {
            score += 10;
        }
        
        // Keyword match in description
        const desc = (tool.description || '').toLowerCase();
        const keywords = question.keywords;
        keywords.forEach(kw => {
            if (desc.includes(kw.toLowerCase())) {
                score += 3;
            }
        });
        
        // Keyword match in name
        const name = (tool.name || '').toLowerCase();
        keywords.forEach(kw => {
            if (name.includes(kw.toLowerCase())) {
                score += 5;
            }
        });
        
        // GitHub stars (popularity indicator)
        if (tool.github_stars) {
            score += Math.min(5, Math.floor(tool.github_stars / 100));
        }
        
        // Has DOI (research quality indicator)
        if (tool.doi) {
            score += 2;
        }
        
        if (score > 0) {
            recommendations.push({
                ...tool,
                relevance_score: score,
                reason: generateRecommendationReason(tool, question)
            });
        }
    });

    // Sort by relevance score
    recommendations.sort((a, b) => b.relevance_score - a.relevance_score);
    
    // Return top 10 recommendations
    return recommendations.slice(0, 10);
}

// Generate human-readable recommendation reason
function generateRecommendationReason(tool, question) {
    const reasons = [];
    const desc = (tool.description || '').toLowerCase();
    const name = (tool.name || '').toLowerCase();
    
    if (question.recommended_categories.includes(tool.category)) {
        reasons.push(`Popular ${tool.category} tool`);
    }
    
    question.keywords.forEach(kw => {
        if (desc.includes(kw.toLowerCase())) {
            reasons.push(`Suitable for ${kw} analysis`);
        }
        if (name.includes(kw.toLowerCase())) {
            reasons.push(`Specialized for ${kw} tasks`);
        }
    });
    
    if (tool.github_stars && tool.github_stars > 500) {
        reasons.push(`Widely adopted (${tool.github_stars}+ stars)`);
    }
    
    if (tool.doi) {
        reasons.push('Peer-reviewed');
    }
    
    return reasons.slice(0, 2).join(', ');
}

// Setup recommendation UI
function setupRecommendationUI() {
    const container = document.getElementById('recommendation-container');
    if (!container) return;
    
    // Create research question cards
    const grid = document.createElement('div');
    grid.className = 'row g-3';
    
    Object.entries(RESEARCH_QUESTIONS).forEach(([key, question]) => {
        const col = document.createElement('div');
        col.className = 'col-md-4';
        col.innerHTML = `
            <div class="card recommendation-card" data-question="${key}">
                <div class="card-body">
                    <h6 class="card-title">${question.title}</h6>
                    <p class="card-text small text-muted">${question.description}</p>
                    <button class="btn btn-sm btn-outline-primary" onclick="showRecommendations('${key}')">
                        <i class="bi bi-lightbulb"></i> Get Recommendations
                    </button>
                </div>
            </div>
        `;
        grid.appendChild(col);
    });
    
    container.appendChild(grid);
}

// Show recommendations for a specific research question
async function showRecommendations(questionType) {
    const modal = document.getElementById('recommendationModal');
    const body = document.getElementById('recommendationModalBody');
    
    body.innerHTML = '<div class="text-center"><div class="spinner-border text-primary"></div><p class="mt-2">Loading recommendations...</p></div>';
    
    const recommendations = await loadRecommendedTools(questionType);
    const question = RESEARCH_QUESTIONS[questionType];
    
    if (recommendations.length === 0) {
        body.innerHTML = '<p class="text-muted">No recommendations available for this research question.</p>';
        return;
    }
    
    let html = `
        <div class="mb-3">
            <h6>${question.title}</h6>
            <p class="small text-muted">${question.description}</p>
        </div>
        <div class="recommendation-list">
    `;
    
    recommendations.forEach((tool, idx) => {
        const categoryColor = getCategoryColor(tool.category);
        html += `
            <div class="recommendation-item mb-2 p-2" style="border-left: 3px solid ${categoryColor}">
                <div class="d-flex justify-content-between align-items-start">
                    <div class="flex-grow-1">
                        <h6 class="mb-1">${idx + 1}. ${tool.name}</h6>
                        <small class="text-muted">${tool.category || 'Uncategorized'}</small>
                        <p class="small mt-1 mb-0">${tool.description || 'No description available'}</p>
                    </div>
                    <div class="text-end ms-2">
                        <span class="badge bg-primary">${tool.relevance_score}</span>
                        <br>
                        <small class="text-muted">${tool.github_stars || 0} stars</small>
                    </div>
                </div>
                <div class="mt-2">
                    <span class="badge bg-light text-dark" title="Reason">${tool.reason}</span>
                </div>
            </div>
        `;
    });
    
    html += '</div>';
    body.innerHTML = html;
    
    if (modal) {
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
    }
}

// Get color for category (matching charts.js)
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

// Export for use in other modules
if (typeof window !== 'undefined') {
    window.showRecommendations = showRecommendations;
    window.loadRecommendedTools = loadRecommendedTools;
    window.RESEARCH_QUESTIONS = RESEARCH_QUESTIONS;
}
