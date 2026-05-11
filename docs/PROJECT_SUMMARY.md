# Virometrics Project Summary

## Overview
Virometrics is an interactive dashboard for exploring and comparing viral bioinformatics tools. It builds upon the [awesome-virome](https://github.com/shandley/awesome-virome) database of 302+ curated tools, enhancing the metadata and presenting it in a user-friendly interface.

## Achievements

### 1. Data Enhancement Pipeline
- **Location**: `scripts/enhance_metadata.py`
- **Features**:
  - Loads tool data from awesome-virome's `data.json`
  - Fetches additional metadata from bio.tools API (input/output formats, operations)
  - Fetches package info from Bioconda API (dependencies, installation commands)
  - Parses GitHub READMEs for installation/usage information
  - Stores everything in SQLite database

### 2. Database
- **Location**: `data/virometrics.db`
- **Schema**: Tools, categories, tool_categories tables
- **Statistics**:
  - 244 tools enhanced
  - 244 tools with descriptions
  - 142 tools with GitHub stars
  - 110 tools with DOIs
  - 139 tools with programming languages identified

### 3. Interactive Dashboard
- **Technology**: Pure HTML/JS (no build tools required)
- **Pages**:
  1. **Dashboard** (`web/index.html`): Main statistics, visualizations, tool browser
  2. **Tool Detail** (`web/tool.html`): Individual tool information
  3. **Comparison** (`web/comparison.html`): Compare 2-5 tools side-by-side
  4. **Browse** (`web/browse.html`): Card-based tool browser

- **Features**:
  - Dark/light mode toggle
  - Responsive design (Bootstrap 5)
  - Interactive charts (Plotly.js)
  - DataTables with filtering and search
  - Export to CSV/JSON
  - Bookmarkable filters

### 4. Tool Categorization
Tools are categorized by:
- **Primary Category** (11): Virus and Phage Identification, Host Prediction, Genome Analysis, etc.
- **Subcategory** (35): Metagenome Analysis, Taxonomic Classification, etc.
- **Programming Language**: Python (124), Shell (55), R (31), etc.
- **Package Manager**: Conda, Pip, Docker, Source, Unknown
- **Input/Output Formats**: FASTA, FASTQ, BAM, etc.

## Tool Categories Summary

| User Category | Tool Count |
|---------------|------------|
| Virus and Phage Identification | 78 |
| Other Tools | 58 |
| Host Prediction | 30 |
| Genome Analysis | 24 |
| Functional Analysis | 14 |
| Taxonomy | 12 |
| Databases | 12 |
| Sequence Databases | 11 |
| Visualization and Infrastructure | 4 |
| CRISPR Analysis | 2 |
| Sequence Analysis | 2 |

## Research-Focused Features

1. **Study Type Filtering**: Filter tools by research domain
2. **Citation Browsing**: Direct links to DOIs, PubMed
3. **Tool Recommendations**: Find tools based on research questions
4. **Cross-Comparison**: Radar charts and side-by-side comparison tables
5. **Research Workflows**: Suggested tool chains for common research goals

## How to Use

### View the Dashboard
```bash
cd ~/Virometrics
python3 serve.py
# Open http://localhost:8000/web/ in your browser
```

### Enhance More Tools
```bash
cd ~/Virometrics
source venv/bin/activate
python3 scripts/enhance_metadata.py  # Process all 244 tools
```

### Export Data
- Dashboard: Use "Export CSV" buttons
- Comparison page: Export selected tools to CSV or JSON

## File Structure

```
Virometrics/
├── data/
│   ├── virometrics.db           # SQLite database (244 tools)
│   ├── tools_enhanced.json      # JSON for web dashboard
│   └── cache/                   # API response cache
├── scripts/
│   ├── enhance_metadata.py      # Main pipeline
│   ├── fetch_biotools.py        # bio.tools API
│   ├── fetch_bioconda.py        # Bioconda API
│   ├── parse_github_readme.py  # GitHub README parser
│   └── generate_dashboard_data.py
├── web/
│   ├── index.html               # Main dashboard
│   ├── tool.html                # Tool detail page
│   ├── comparison.html          # Tool comparison
│   ├── browse.html              # Card-based browser
│   ├── css/style.css           # Custom styles
│   └── js/
│       ├── data.js               # Data loading
│       ├── charts.js             # Plotly charts
│       ├── table.js              # DataTable
│       ├── app.js                # Main logic
│       ├── tool-detail.js        # Tool detail logic
│       ├── comparison.js         # Comparison logic
│       └── browse.js             # Browse page logic
├── docs/
│   ├── methodology.md
│   └── PROJECT_SUMMARY.md      # This file
├── serve.py                      # Local test server
├── requirements.txt              # Python dependencies
└── README.md                    # Project documentation
```

## Next Steps / Improvements

1. **Enhanced Metadata**: Run more comprehensive API queries to fill in missing input/output formats
2. **Tool Recommendations**: Implement ML-based tool suggestion engine
3. **Network Visualization**: Add tool relationship graphs (Vis.js)
4. **User Reviews**: Add rating and review system
5. **Workflow Builder**: Drag-and-drop tool chain builder
6. **Docker Deployment**: Containerize for easy deployment

## Data Sources

- **awesome-virome**: Base tool list and GitHub metrics
- **bio.tools API**: Structured metadata (input/output formats, operations)
- **Bioconda API**: Package information and dependencies
- **GitHub API**: Repository data, READMEs
- **CrossRef API**: DOI metadata and citations

## Conclusion

Virometrics successfully transforms the incomplete awesome-virome metadata into a comprehensive, interactive dashboard. The data-first approach ensures the dashboard has rich, useful content, while the pure HTML/JS stack ensures compatibility and ease of deployment.
