// tool-detail.js - Load and display tool details

// Get tool name from URL
function getToolName() {
    const params = new URLSearchParams(window.location.search);
    return params.get('name') || params.get('id');
}

// Load tool details
async function loadToolDetails() {
    const toolName = getToolName();

    if (!toolName) {
        showError('No tool specified. Please go back to the <a href="index.html">dashboard</a>.');
        return;
    }

    try {
        // Load tool data if not already loaded
        if (virometricsData.tools.length === 0) {
            await loadToolData();
        }

        // Find the tool
        const tool = getTool(toolName);
        if (!tool) {
            showError(`Tool "${toolName}" not found. <a href="index.html">Browse all tools</a>.`);
            return;
        }

        displayToolDetails(tool);
        loadRelatedTools(tool);
        loadToolDependencies(tool.name);
        loadGithubReleaseInfo(tool);
        loadGithubReadme(tool);

    } catch (error) {
        console.error('Error loading tool details:', error);
        showError('Error loading tool data. Please try again.');
    }
}

// Display tool details
function displayToolDetails(tool) {
    // Show content, hide loading
    document.getElementById('loading').style.display = 'none';
    document.getElementById('tool-content').style.display = 'block';

    // Set Execute button
    const btnExecute = document.getElementById('btn-execute');
    if (btnExecute) {
        btnExecute.href = `execute.html?tool=${encodeURIComponent(tool.name)}`;
    }

    // Header
    document.getElementById('tool-name').textContent = tool.name || 'Unknown Tool';
    document.getElementById('breadcrumb-name').textContent = tool.name || 'Tool Details';
    document.title = `${tool.name} - Virometrics`;

    // Description
    document.getElementById('tool-description').textContent = tool.description || 'No description available';

    // Stats
    document.getElementById('tool-stars').textContent = tool.github_stars || 0;
    document.getElementById('tool-forks').textContent = tool.github_forks || 0;

    // Dates
    const updated = tool.last_updated ? new Date(tool.last_updated).toLocaleDateString() : 'Unknown';
    document.getElementById('tool-updated').textContent = updated;

    // URL
    const urlEl = document.getElementById('tool-url');
    if (tool.url) {
        urlEl.href = tool.url;
    } else {
        urlEl.style.display = 'none';
    }

    // DOI
    const doiEl = document.getElementById('tool-doi');
    if (tool.doi) {
        doiEl.href = `https://doi.org/${tool.doi}`;
        doiEl.style.display = 'inline-block';
    }

    // Badges
    const badgesEl = document.getElementById('tool-badges');
    let badges = '';
    if (tool.category) {
        badges += `<span class="badge bg-primary">${tool.category}</span>`;
    }
    if (tool.subcategory) {
        badges += `<span class="badge bg-secondary">${tool.subcategory}</span>`;
    }
    if (tool.package_manager) {
        badges += `<span class="badge bg-success">${tool.package_manager}</span>`;
    }
    if (tool.license) {
        badges += `<span class="badge bg-info">${tool.license}</span>`;
    }
    badgesEl.innerHTML = badges;

    // Full description
    document.getElementById('tool-desc-full').textContent = tool.description || 'No description available';

    // Purpose
    document.getElementById('tool-purpose').textContent = tool.purpose || 'Not specified';

    // Studies
    let studies = tool.studies_suited;
    if (typeof studies === 'string') {
        try { studies = JSON.parse(studies); } catch(e) { studies = []; }
    }
    if (Array.isArray(studies) && studies.length > 0) {
        document.getElementById('tool-studies').innerHTML = studies.map(s =>
            `<span class="badge bg-light text-dark me-1">${s}</span>`
        ).join('');
    } else {
        document.getElementById('tool-studies').textContent = 'Not specified';
    }

    // Setup instructions
    document.getElementById('tool-setup').textContent = tool.setup_instructions || 'No setup instructions available';

    // Input formats
    let inputs = tool.input_formats;
    if (typeof inputs === 'string') {
        try { inputs = JSON.parse(inputs); } catch(e) { inputs = []; }
    }
    if (Array.isArray(inputs) && inputs.length > 0) {
        document.getElementById('tool-inputs').innerHTML = inputs.map(f =>
            `<span class="badge bg-primary me-1">${f}</span>`
        ).join('');
    } else {
        document.getElementById('tool-inputs').textContent = 'Not specified';
    }

    // Output formats
    let outputs = tool.output_formats;
    if (typeof outputs === 'string') {
        try { outputs = JSON.parse(outputs); } catch(e) { outputs = []; }
    }
    if (Array.isArray(outputs) && outputs.length > 0) {
        document.getElementById('tool-outputs').innerHTML = outputs.map(f =>
            `<span class="badge bg-success me-1">${f}</span>`
        ).join('');
    } else {
        document.getElementById('tool-outputs').textContent = 'Not specified';
    }

    // Info table
    document.getElementById('tool-category').textContent = tool.category || '-';
    document.getElementById('tool-subcategory').textContent = tool.subcategory || '-';
    document.getElementById('tool-pkgmgr').textContent = tool.package_manager || 'Unknown';
    document.getElementById('tool-license').textContent = tool.license || '-';

    const created = tool.created_at ? new Date(tool.created_at).toLocaleDateString() : 'Unknown';
    document.getElementById('tool-created').textContent = created;
    document.getElementById('tool-last-updated').textContent = updated;

    // Languages
    let langs = tool.languages;
    if (typeof langs === 'string') {
        try { langs = JSON.parse(langs); } catch(e) { langs = []; }
    }
    if (Array.isArray(langs) && langs.length > 0) {
        document.getElementById('tool-languages').innerHTML = langs.map(l =>
            `<span class="badge bg-info me-1">${l}</span>`
        ).join('');
    } else {
        document.getElementById('tool-languages').textContent = 'Not specified';
    }

    // Packages needed
    let packages = tool.packages_needed;
    if (typeof packages === 'string') {
        try { packages = JSON.parse(packages); } catch(e) { packages = null; }
    }
    if (packages && typeof packages === 'object') {
        let html = '<ul class="mb-0">';
        if (packages.bioconda) {
            html += `<li><strong>Bioconda:</strong> ${packages.bioconda}</li>`;
        }
        if (packages.version) {
            html += `<li><strong>Version:</strong> ${packages.version}</li>`;
        }
        if (Array.isArray(packages.dependencies)) {
            html += `<li><strong>Dependencies:</strong> ${packages.dependencies.join(', ')}</li>`;
        }
        html += '</ul>';
        document.getElementById('tool-packages').innerHTML = html;
    } else {
        document.getElementById('tool-packages').textContent = 'Not specified';
    }

    // GitHub metrics
    let ghMetrics = tool.github_metrics;
    if (typeof ghMetrics === 'string') {
        try { ghMetrics = JSON.parse(ghMetrics); } catch(e) { ghMetrics = null; }
    }
    if (ghMetrics && typeof ghMetrics === 'object') {
        let html = '<table class="table table-sm">';
        if (ghMetrics.language) {
            html += `<tr><td>Primary Language</td><td>${ghMetrics.language}</td></tr>`;
        }
        if (ghMetrics.topics && Array.isArray(ghMetrics.topics)) {
            html += `<tr><td>Topics</td><td>${ghMetrics.topics.slice(0, 5).join(', ')}</td></tr>`;
        }
        html += '</table>';
        document.getElementById('tool-github-metrics').innerHTML = html;
    }

    // Ratings and reviews
    displayToolRatings(tool);

    // Compare button
    document.getElementById('btn-compare').href = `comparison.html?tools=${encodeURIComponent(tool.name)}`;
}

// Load tool dependencies
async function loadToolDependencies(toolName) {
    const container = document.getElementById('tool-dependencies');
    if (!container) return;

    try {
        const resp = await fetch(`/api/dependencies?search=${encodeURIComponent(toolName)}`);
        const deps = await resp.json();

        if (!deps || deps.length === 0) {
            container.innerHTML = '<p class="text-muted small">No dependencies registered for this tool.</p>';
            return;
        }

        let html = '<div class="small">';
        deps.forEach(dep => {
            const badge = dep.installed ? 'bg-success' : 'bg-warning';
            const status = dep.installed ? 'Installed' : 'Missing';
            html += `
                <div class="d-flex justify-content-between align-items-center mb-1">
                    <span>
                        <strong>${dep.name}</strong>
                        <span class="badge bg-info">${dep.package_manager}</span>
                    </span>
                    <span class="badge ${badge}">${status}</span>
                </div>
            `;
        });
        html += '</div>';
        container.innerHTML = html;

    } catch (e) {
        container.innerHTML = '<p class="text-danger small">Error loading dependencies.</p>';
        console.error('Error loading dependencies:', e);
    }
}

// Load related tools
function loadRelatedTools(currentTool) {
    const related = virometricsData.tools.filter(t =>
        t.name !== currentTool.name &&
        (t.category === currentTool.category ||
         t.subcategory === currentTool.subcategory)
    ).slice(0, 10);

    const container = document.getElementById('related-tools');

    if (related.length === 0) {
        container.innerHTML = '<p class="text-muted">No related tools found.</p>';
        return;
    }

    container.innerHTML = related.map(t => `
        <a href="tool.html?name=${encodeURIComponent(t.name)}" class="btn btn-outline-primary btn-sm me-2 mb-2">
            ${t.name}
        </a>
    `).join('');
}

// Show error
function showError(message) {
    document.getElementById('loading').style.display = 'none';
    document.getElementById('tool-content').style.display = 'block';
    document.getElementById('tool-content').innerHTML = `
        <div class="alert alert-warning">
            ${message}
        </div>
    `;
}

// Display tool ratings
function displayToolRatings(tool) {
    const ratingEl = document.getElementById('tool-ratings');
    if (!ratingEl) return;
    
    const avgRating = parseFloat(tool.avg_rating) || 0;
    const ratingCount = parseInt(tool.rating_count) || 0;
    
    // Update rating display
    const ratingScore = ratingEl.querySelector('.rating-score');
    const ratingStars = ratingEl.querySelectorAll('.rating-stars i');
    const ratingCountEl = document.getElementById('rating-count');
    
    if (ratingScore) {
        ratingScore.textContent = avgRating > 0 ? avgRating.toFixed(1) : '—';
    }
    
    if (ratingStars) {
        ratingStars.forEach((star, index) => {
            star.className = index < avgRating 
                ? 'bi bi-star-fill text-warning' 
                : 'bi bi-star text-muted';
        });
    }
    
    if (ratingCountEl) {
        ratingCountEl.textContent = ratingCount;
    }
}

// Setup rating event listeners
function setupRatingListeners() {
    const ratingBtns = document.querySelectorAll('.rating-input button');
    const stars = document.querySelectorAll('.rating-input button i');
    
    ratingBtns.forEach(btn => {
        btn.addEventListener('mouseenter', function() {
            const rating = parseInt(this.dataset.rating);
            stars.forEach((star, idx) => {
                star.className = idx < rating 
                    ? 'bi bi-star-fill text-warning' 
                    : 'bi bi-star text-muted';
            });
        });
        
        btn.addEventListener('mouseleave', function() {
            const currentRating = parseInt(document.getElementById('user-rating-form')?.dataset?.rating || 0);
            stars.forEach((star, idx) => {
                star.className = idx < currentRating 
                    ? 'bi bi-star-fill text-warning' 
                    : 'bi bi-star text-muted';
            });
        });
    });
    
    // Submit review
    const submitBtn = document.getElementById('submit-review');
    if (submitBtn) {
        submitBtn.addEventListener('click', async function() {
            const toolName = getToolName();
            const ratingEl = document.querySelector('.rating-input');
            const selectedRating = parseInt(ratingEl.dataset.rating) || 0;
            const reviewText = document.getElementById('user-review').value;
            
            if (selectedRating === 0) {
                alert('Please select a star rating');
                return;
            }
            
            try {
                const resp = await fetch('/api/tools/rating', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        tool_name: toolName,
                        rating: selectedRating,
                        review: reviewText,
                        user: 'anonymous'
                    })
                });
                
                const data = await resp.json();
                if (data.success) {
                    alert('Review submitted successfully!');
                    ratingEl.dataset.rating = selectedRating;
                    displayToolRatings(virometricsData.tools.find(t => t.name === toolName));
                }
            } catch (e) {
                console.error('Error submitting review:', e);
                alert('Error submitting review');
            }
        });
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', function() {
    initTheme();
    loadToolDetails();
    setupRatingListeners();
});

// Load GitHub release information
async function loadGithubReleaseInfo(tool) {
    const container = document.getElementById('tool-release-info');
    if (!container || !tool.url || tool.url.indexOf('github.com') === -1) {
        if (container) container.style.display = 'none';
        return;
    }
    
    try {
        const toolId = tool.id || 0;
        const resp = await fetch(`/api/github/tool/${toolId}/release`);
        const data = await resp.json();
        
        if (data.error && data.error === 'Tool not found') {
            container.style.display = 'none';
            return;
        }
        
        const releaseName = data.release_name || data.latest_version || 'Unknown';
        const releaseDate = data.release_date ? new Date(data.release_date).toLocaleDateString() : 'Unknown';
        const prerelease = data.prerelease ? '<span class="badge bg-warning">Pre-release</span>' : '<span class="badge bg-success">Stable</span>';
        const assetCount = data.asset_count || 0;
        
        let html = `
            <div class="d-flex justify-content-between align-items-center mb-2">
                <span><strong>Latest Release:</strong> ${releaseName}</span>
                ${prerelease}
            </div>
            <div class="small text-muted mb-2">
                <i class="bi bi-calendar"></i> Released: ${releaseDate}
                ${assetCount > 0 ? `<span class="ms-3"><i class="bi bi-download"></i> ${assetCount} asset(s)</span>` : ''}
            </div>
        `;
        
        if (data.release_notes) {
            const notes = data.release_notes.substring(0, 200) + (data.release_notes.length > 200 ? '...' : '');
            html += `<div class="small"><strong>Notes:</strong> <em>${notes}</em></div>`;
        }
        
        if (data.assets && data.assets.length > 0) {
            html += `<div class="mt-2"><strong>Assets:</strong>
                <ul class="list-unstyled mb-0 small">`;
            data.assets.slice(0, 5).forEach(asset => {
                const size = asset.size ? (asset.size / 1024 / 1024).toFixed(2) + ' MB' : 'N/A';
                html += `<li><a href="${asset.browser_download_url}" target="_blank">${asset.name}</a> <span class="text-muted">(${size})</span></li>`;
            });
            if (data.assets.length > 5) {
                html += `<li class="text-muted">+${data.assets.length - 5} more assets</li>`;
            }
            html += `</ul></div>`;
        }
        
        container.innerHTML = html;
        container.style.display = 'block';
        
    } catch (e) {
        console.error('Error loading GitHub release info:', e);
        container.innerHTML = '<div class="text-muted">Release info unavailable</div>';
    }
}

// Load GitHub README from database
async function loadGithubReadme(tool) {
    const container = document.getElementById('tool-readme-sections');
    if (!container || !tool.url || tool.url.indexOf('github.com') === -1) {
        if (container) container.style.display = 'none';
        return;
    }
    
    try {
        const toolId = tool.id || 0;
        const resp = await fetch(`/api/github/tool/${toolId}/readme`);
        const data = await resp.json();
        
        if (data.error && data.error === 'Tool not found') {
            container.style.display = 'none';
            return;
        }
        
        // Use stored sections from database
        const sections = data.sections || {};
        
        // Check if we have any sections
        const hasSections = Object.values(sections).some(v => v && v.trim().length > 0);
        
        if (!hasSections) {
            container.innerHTML = `
                <div class="text-muted mb-2">README documentation not yet fetched</div>
                <button class="btn btn-sm btn-outline-primary" onclick="fetchReadme(${toolId})">
                    <i class="bi bi-cloud-download"></i> Fetch README
                </button>
            `;
            container.style.display = 'block';
            return;
        }
        
        let html = '';
        
        // Overview section
        if (sections.overview) {
            html += `<div class="mb-3"><h6><i class="bi bi-info-circle"></i> Overview</h6><p class="small">${sections.overview.substring(0, 400)}${sections.overview.length > 400 ? '...' : ''}</p></div>`;
        }
        
        // Installation section
        if (sections.installation) {
            html += `<div class="mb-3"><h6><i class="bi bi-download"></i> Installation</h6><pre class="bg-light p-2 rounded small" style="white-space: pre-wrap;">${sections.installation.substring(0, 500)}${sections.installation.length > 500 ? '...' : ''}</pre></div>`;
        }
        
        // Usage section
        if (sections.usage) {
            html += `<div class="mb-3"><h6><i class="bi bi-terminal"></i> Usage</h6><pre class="bg-light p-2 rounded small" style="white-space: pre-wrap;">${sections.usage.substring(0, 500)}${sections.usage.length > 500 ? '...' : ''}</pre></div>`;
        }
        
        // Requirements section
        if (sections.requirements && (!sections.installation || !html.includes('Installation'))) {
            html += `<div class="mb-3"><h6><i class="bi bi-box-seam"></i> Requirements</h6><div class="small">${sections.requirements.substring(0, 300)}${sections.requirements.length > 300 ? '...' : ''}</div></div>`;
        }
        
        // Documentation section
        if (sections.documentation) {
            html += `<div class="mb-3"><h6><i class="bi bi-book"></i> Documentation</h6><div class="small">${sections.documentation.substring(0, 300)}${sections.documentation.length > 300 ? '...' : ''}</div></div>`;
        }
        
        if (!html) {
            html = '<div class="text-muted">No README documentation available</div>';
        }
        
        container.innerHTML = html;
        container.style.display = 'block';
        
    } catch (e) {
        console.error('Error loading GitHub README:', e);
        container.innerHTML = '<div class="text-muted">README sections unavailable</div>';
    }
}

// Fetch README on demand
async function fetchReadme(toolId) {
    const container = document.getElementById('tool-readme-sections');
    
    try {
        container.innerHTML = '<div class="text-muted"><div class="spinner-border spinner-border-sm" role="status"></div> Fetching README...</div>';
        
        const resp = await fetch(`/api/github/tool/${toolId}/readme?refresh=true`, {
            method: 'POST'
        });
        const data = await resp.json();
        
        if (data.success) {
            // Reload the page to show new content
            const tool = virometricsData.tools.find(t => t.id === toolId);
            if (tool) {
                loadGithubReadme(tool);
            }
        } else {
            container.innerHTML = `<div class="text-danger"><i class="bi bi-exclamation-circle"></i> ${data.error || 'Failed to fetch README'}</div>`;
        }
        
    } catch (e) {
        console.error('Error fetching README:', e);
        container.innerHTML = '<div class="text-danger">Error fetching README</div>';
    }
}

// Theme functions (same as app.js - could be in a shared file)
function initTheme() {
    const savedTheme = localStorage.getItem('virometrics-theme');
    if (savedTheme === 'dark') {
        enableDarkMode();
    }
}

function enableDarkMode() {
    document.documentElement.setAttribute('data-theme', 'dark');
    document.body.classList.add('dark-mode');
}
