# Virometrics - Viral Bioinformatics Tools Dashboard

An interactive dashboard designed to help users discover, evaluate, and compare bioinformatics tools used in viral research. Developed as an educational resource for bioinformatics students, the platform provides an accessible way to understand the functionality, applications, and intended use cases of various tools. It serves as a centralized hub for showcasing widely used and up-to-date software solutions that can be installed and operated within Linux-based environments, making it easier for learners and researchers to identify suitable tools for their analytical workflows.

Dashboard has been deployed and tested in ihcm-ngs lab at UNIMAS, Sarawak. Several releases are to be expected to improve integration, information retrieval and workflow management and execution.

## Features
<img width="1835" height="927" alt="Screenshot from 2026-05-13 17-36-15" src="https://github.com/user-attachments/assets/51833813-a785-4919-a014-da1ae9ae16f6" />

### Interactive Dashboard
- **Tool Browser**: Filter and search through 247+ viral bioinformatics tools
- **Visualizations**: Category treemaps, language distributions, package manager breakdowns
- **Tool Details**: Comprehensive information about each tool including:
  - Purpose and description
  - Setup instructions
  - Input/output file formats
  - Package dependencies
  - Programming languages
  - GitHub metrics (stars, forks, license)
  - Citations and DOIs

### Tool Comparison
- **Side-by-side comparison**: Compare up to 5 tools simultaneously
- **Radar charts**: Multi-dimensional comparison visualization
- **Export options**: CSV and JSON export for further analysis

### Research-Focused Features
- **Study type filtering**: Find tools suited for specific research domains
- **Citation browsing**: Direct links to papers and DOIs
- **Tool recommendations**: Discover tools based on research questions

### Containerized Deployment
- **Docker support**: Run the platform in isolated containers
- **Job queue**: Priority-based job queuing with Redis/RQ
- **Worker nodes**: Scalable parallel execution
- **Resource monitoring**: CPU/memory/disk tracking per job
- **Checkpointing**: Save and restore long-running jobs

## Categories Covered

| Category | Tool Count |
|-----------|------------|
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

Plus 35 subcategories including:
- Metagenome Analysis
- Genome Annotation
- Taxonomic Classification
- Host Prediction
- Functional Analysis

## Technology Stack

- **Frontend**: Pure HTML5 + JavaScript (no build tools required)
- **CSS Framework**: Bootstrap 5.3+
- **Visualization**: Plotly.js, Vis.js
- **Data Table**: DataTables with Bootstrap 5 styling
- **Backend**: Python (data enhancement pipeline)
- **Database**: SQLite for structured data storage
- **Queue**: Redis/RQ for job management
- **Monitoring**: psutil for resource tracking

## Quick Start

### View the Dashboard

1. Start the local server:
   ```bash
   cd Virometrics
   python3 serve.py
   ```

2. Open your browser to: http://localhost:8000/web/

### Run Data Enhancement Pipeline

1. Set up virtual environment:
   ```bash
   cd Virometrics
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. Run the enhancement pipeline:
   ```bash
   python3 scripts/enhance_metadata.py
   ```
   (Optional: pass a number to limit processing, e.g., `python3 scripts/enhance_metadata.py 10`)

## Docker Deployment

### Prerequisites
- Docker 20.10+
- Docker Compose 2.0+
- 4GB+ RAM recommended
- 10GB+ disk space

### Quick Start with Docker

1. Setup and build:
   ```bash
   cd Virometrics
   ./scripts/setup_docker.sh install
   ```

2. Manual setup:
   ```bash
   # Build images
   docker compose build
   
   # Start services
   docker compose up -d
   
   # Check status
   docker compose ps
   
   # View logs
   docker compose logs -f web
   ```

### Services

| Service | Port | Description |
|---------|------|-------------|
| web | 8000 | Main Flask application |
| redis | 6379 | Job queue broker |
| worker | - | Background job processors |
| worker-gpu | - | GPU-enabled workers |

### Configuration

Create a `.env` file in the project root:

```env
# Flask settings
FLASK_DEBUG=false
VIOMETRICS_SECRET=your-secret-key

# Redis settings
REDIS_URL=redis://redis:6379/0

# Worker settings
WORKER_NAME=worker1
WORKER_REPLICAS=2
GPU_ENABLED=false

# Resource limits
MAX_CONCURRENT_JOBS=5
JOB_TIMEOUT=3600
```

### Docker Configuration

Edit `config/docker.conf` for:
- Redis connection settings
- Worker configuration
- Queue priorities
- Checkpoint settings
- Resource limits
- GPU settings

### Process Stats

Get CPU/memory stats for a process:

```python
from core.storage_monitor import StorageMonitor

monitor = StorageMonitor()
stats = monitor.get_process_stats(pid=12345)
print(f"CPU: {stats['cpu_percent']}%")
print(f"Memory: {stats['memory_mb']} MB")
```

### Real-time Execution Monitoring

Monitor execution in real-time:

```python
from core.storage_monitor import StorageMonitor

monitor = StorageMonitor()
stats = monitor.monitor_execution(
    execution_id=1,
    pid=12345,
    callback=lambda s: print(f"CPU: {s['cpu_percent']}%"),
    interval=1.0
)
```

### Resource Limits

Set resource limits per tool:

```python
from core.resource_monitor import ResourceMonitor, ResourceLimit

monitor = ResourceMonitor()

# Set limits for tool
limit = ResourceLimit(
    tool_id=1,
    max_cpu_percent=80.0,
    max_memory_mb=4096.0,
    max_wall_time_seconds=3600.0,
)
monitor.set_limit(limit)

# Start monitoring
job_monitor = monitor.start_monitoring(
    execution_id=1,
    pid=12345,
    tool_id=1
)

# Check if should terminate
if job_monitor.should_terminate():
    print(f"Limit exceeded: {job_monitor.get_exceeded_limit()}")
```

### Resource Limit Configuration

Set limits in `config/docker.conf`:

```ini
[resource_limits]
max_cpu_percent = 80
max_memory_mb = 4096
max_disk_io_mb = 500
max_concurrent_jobs = 5
```

## Checkpointing Support

### Create Checkpoint

```python
from core.checkpoint import CheckpointManager

manager = CheckpointManager(
    db_path="data/virometrics.db",
    checkpoint_dir="data/checkpoints",
    max_checkpoints=10
)

# Create checkpoint
checkpoint = manager.create_checkpoint(
    execution_id=1,
    data={"progress": 0.5, "state": {...}},
    metadata={"stage": "alignment"}
)
```

### Restore from Checkpoint

```python
# Get latest checkpoint
data = manager.restore_from_checkpoint(execution_id=1)

# Or restore specific checkpoint
data = manager.restore_from_checkpoint(
    execution_id=1,
    sequence=5
)
```

### Auto-checkpointing

Enable auto-checkpointing in executor:

```python
from core.executor import ToolExecutor

executor = ToolExecutor(
    enable_checkpoint=True,
    checkpoint_interval=300  # Every 5 minutes
)

# Execute with checkpoint
execution_id = executor.execute(
    tool_id=1,
    command="tool input.fastq",
    checkpoint_data={"initial_state": {...}}
)
```

## Parallel Execution

### Scatter-Gather Pattern

```python
from core.parallel_executor import ParallelExecutor, merge_outputs

executor = ParallelExecutor(
    max_workers=8,
    result_aggregator=merge_outputs
)

# Execute in parallel
result = executor.scatter_execute(
    tool_id=1,
    input_files=["sample1.fastq", "sample2.fastq", "sample3.fastq"],
    base_command="bowtie2 -x index",
    parameters={"-U": "{input}"},
    output_dir="data/outputs"
)

# Wait for completion
executor.wait_for_completion(result.scatter_id, timeout=3600)

# Get results
print(f"Completed: {result.completed_tasks}/{result.total_tasks}")
```

### Pipeline with Multiple Stages

```python
from core.parallel_executor import ScatterGatherPipeline

pipeline = ScatterGatherPipeline(
    stages=[
        ("alignment", "bowtie2 -x index -U {input}", {}),
        ("sorting", "samtools sort -o {output} {input}", {}),
        ("indexing", "samtools index {output}", {}),
    ],
    max_workers=4
)

results = pipeline.run(
    input_files=["sample1.fastq", "sample2.fastq"],
    output_dir="data/pipeline_output"
)
```

## Data Sources

- **[awesome-virome](https://github.com/shandley/awesome-virome)**: 302+ curated viral bioinformatics tools
- **[bio.tools](https://bio.tools)**: Structured tool metadata including input/output formats
- **[Bioconda](https://bioconda.github.io)**: Package information and dependencies
- **GitHub API**: Repository metrics, README content
- **CrossRef API**: DOI metadata and citations

## Data Enhancement Pipeline

The `scripts/enhance_metadata.py` pipeline:

1. Loads existing tool data from awesome-virome
2. Fetches additional metadata from bio.tools API (input/output formats, operations)
3. Fetches package info from Bioconda (dependencies, installation commands)
4. Parses GitHub READMEs for installation/usage information
5. Stores everything in SQLite database
6. Exports to JSON for web dashboard


## License

This project uses data from github.

## Acknowledgments
- [bio.tools](https://bio.tools) for structured tool metadata
- [Bioconda](https://bioconda.github.io) for package information
