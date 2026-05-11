#!/usr/bin/env python3
"""
Database migration script for Virometrics Galaxy-like platform.
Extends the existing virometrics.db with new tables for:
- Tool execution tracking
- Dependency management
- Data file management
- Storage metrics
"""

import sqlite3
import os
import sys
from pathlib import Path

# Default paths
DEFAULT_DB_PATH = "/home/ihcm-ubuntu/Virometrics/data/virometrics.db"
WAL_MODE = True


def get_connection(db_path):
    """Create a database connection with WAL mode if requested."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    if WAL_MODE:
        conn.execute("PRAGMA journal_mode=WAL")
    return conn


def table_exists(conn, table_name):
    """Check if a table exists in the database."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    return cursor.fetchone() is not None


def create_tool_executions_table(conn):
    """Create tool_executions table for tracking tool runs."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tool_executions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_id INTEGER NOT NULL,
            execution_name TEXT,
            command TEXT NOT NULL,
            working_dir TEXT,
            status TEXT DEFAULT 'pending',
            pid INTEGER,
            return_code INTEGER,
            started_at TEXT DEFAULT (datetime('now')),
            completed_at TEXT,
            created_by TEXT,
            FOREIGN KEY(tool_id) REFERENCES tools(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_executions_tool ON tool_executions(tool_id);
        CREATE INDEX IF NOT EXISTS idx_executions_status ON tool_executions(status);
    """)
    print("  Created tool_executions table")


def create_execution_outputs_table(conn):
    """Create execution_outputs table for streaming output."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS execution_outputs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            execution_id INTEGER NOT NULL,
            output_type TEXT NOT NULL,
            content TEXT NOT NULL,
            sequence_num INTEGER NOT NULL,
            timestamp TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(execution_id) REFERENCES tool_executions(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_outputs_execution ON execution_outputs(execution_id, sequence_num);
    """)
    print("  Created execution_outputs table")


def create_tool_parameters_table(conn):
    """Create tool_parameters table for parameter definitions."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tool_parameters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_id INTEGER NOT NULL,
            param_name TEXT NOT NULL,
            param_type TEXT NOT NULL,
            param_label TEXT,
            param_description TEXT,
            default_value TEXT,
            required BOOLEAN DEFAULT 0,
            choices TEXT,
            validation_regex TEXT,
            position INTEGER,
            group_name TEXT,
            FOREIGN KEY(tool_id) REFERENCES tools(id) ON DELETE CASCADE,
            UNIQUE(tool_id, param_name)
        );
    """)
    print("  Created tool_parameters table")


def create_dependencies_table(conn):
    """Create dependencies table for dependency registry."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS dependencies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            version TEXT,
            package_manager TEXT NOT NULL,
            install_command TEXT,
            check_command TEXT,
            description TEXT,
            url TEXT,
            UNIQUE(name, version, package_manager)
        );
    """)
    print("  Created dependencies table")


def create_tool_dependencies_table(conn):
    """Create tool_dependencies mapping table."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tool_dependencies (
            tool_id INTEGER NOT NULL,
            dependency_id INTEGER NOT NULL,
            is_optional BOOLEAN DEFAULT 0,
            install_hint TEXT,
            FOREIGN KEY(tool_id) REFERENCES tools(id) ON DELETE CASCADE,
            FOREIGN KEY(dependency_id) REFERENCES dependencies(id) ON DELETE CASCADE,
            PRIMARY KEY(tool_id, dependency_id)
        );
    """)
    print("  Created tool_dependencies table")


def create_installed_dependencies_table(conn):
    """Create installed_dependencies table."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS installed_dependencies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dependency_id INTEGER NOT NULL,
            installed_version TEXT,
            install_path TEXT,
            installed_at TEXT DEFAULT (datetime('now')),
            last_verified TEXT,
            status TEXT DEFAULT 'unknown',
            FOREIGN KEY(dependency_id) REFERENCES dependencies(id) ON DELETE CASCADE
        );
    """)
    print("  Created installed_dependencies table")


def create_data_files_table(conn):
    """Create data_files table for managing data files."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS data_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            filepath TEXT NOT NULL UNIQUE,
            file_type TEXT,
            file_size INTEGER,
            md5_hash TEXT,
            workflow_id INTEGER,
            tool_execution_id INTEGER,
            created_at TEXT DEFAULT (datetime('now')),
            metadata_json TEXT,
            FOREIGN KEY(tool_execution_id) REFERENCES tool_executions(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_files_type ON data_files(file_type);
    """)
    print("  Created data_files table")


def create_storage_metrics_table(conn):
    """Create storage_metrics table for periodic snapshots."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS storage_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL,
            total_space BIGINT,
            used_space BIGINT,
            free_space BIGINT,
            file_count INTEGER,
            measured_at TEXT DEFAULT (datetime('now'))
        );
    """)
    print("  Created storage_metrics table")


def create_workflows_table(conn):
    """Create workflows table for storing workflow definitions."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS workflows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            created_by TEXT,
            is_public BOOLEAN DEFAULT 0,
            workflow_json TEXT NOT NULL  -- JSON representation of the workflow
        );
        CREATE INDEX IF NOT EXISTS idx_workflows_created_by ON workflows(created_by);
        CREATE INDEX IF NOT EXISTS idx_workflows_is_public ON workflows(is_public);
    """)
    print("  Created workflows table")


def create_workflow_steps_table(conn):
    """Create workflow_steps table for storing individual steps in a workflow."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS workflow_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_id INTEGER NOT NULL,
            step_id TEXT NOT NULL,  -- Unique identifier for the step within the workflow
            tool_id INTEGER NOT NULL,
            position INTEGER NOT NULL,  -- Order of execution in the workflow
            config_json TEXT,  -- Tool-specific configuration for this step
            FOREIGN KEY(workflow_id) REFERENCES workflows(id) ON DELETE CASCADE,
            FOREIGN KEY(tool_id) REFERENCES tools(id) ON DELETE CASCADE,
            UNIQUE(workflow_id, step_id)
        );
        CREATE INDEX IF NOT EXISTS idx_workflow_steps_workflow ON workflow_steps(workflow_id);
        CREATE INDEX IF NOT EXISTS idx_workflow_steps_position ON workflow_steps(workflow_id, position);
    """)
    print("  Created workflow_steps table")


def create_workflow_executions_table(conn):
    """Create workflow_executions table for tracking workflow runs."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS workflow_executions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_id INTEGER NOT NULL,
            execution_name TEXT,
            status TEXT DEFAULT 'pending',
            started_at TEXT DEFAULT (datetime('now')),
            completed_at TEXT,
            created_by TEXT,
            FOREIGN KEY(workflow_id) REFERENCES workflows(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_workflow_executions_workflow ON workflow_executions(workflow_id);
        CREATE INDEX IF NOT EXISTS idx_workflow_executions_status ON workflow_executions(status);
    """)
    print("  Created workflow_executions table")


def create_workflow_step_executions_table(conn):
    """Create workflow_step_executions table for tracking executions of individual steps."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS workflow_step_executions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_execution_id INTEGER NOT NULL,
            workflow_step_id INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            started_at TEXT,
            completed_at TEXT,
            return_code INTEGER,
            FOREIGN KEY(workflow_execution_id) REFERENCES workflow_executions(id) ON DELETE CASCADE,
            FOREIGN KEY(workflow_step_id) REFERENCES workflow_steps(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_workflow_step_executions_workflow ON workflow_step_executions(workflow_execution_id);
        CREATE INDEX IF NOT EXISTS idx_workflow_step_executions_step ON workflow_step_executions(workflow_step_id);
        CREATE INDEX IF NOT EXISTS idx_workflow_step_executions_status ON workflow_step_executions(status);
    """)
    print("  Created workflow_step_executions table")


def create_workflow_nodes_table(conn):
    """Create workflow_nodes table for storing visual workflow node positions and configurations."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS workflow_nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_id INTEGER NOT NULL,
            node_id TEXT NOT NULL,
            tool_id INTEGER NOT NULL,
            node_name TEXT,
            config_json TEXT,
            position_x INTEGER DEFAULT 0,
            position_y INTEGER DEFAULT 0,
            FOREIGN KEY(workflow_id) REFERENCES workflows(id) ON DELETE CASCADE,
            FOREIGN KEY(tool_id) REFERENCES tools(id) ON DELETE CASCADE,
            UNIQUE(workflow_id, node_id)
        );
        CREATE INDEX IF NOT EXISTS idx_workflow_nodes_workflow ON workflow_nodes(workflow_id);
        CREATE INDEX IF NOT EXISTS idx_workflow_nodes_node ON workflow_nodes(node_id);
    """)
    print("  Created workflow_nodes table")


def create_workflow_connections_table(conn):
    """Create workflow_connections table for storing workflow node connections."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS workflow_connections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_id INTEGER NOT NULL,
            connection_id TEXT NOT NULL,
            source_node_id TEXT NOT NULL,
            source_output TEXT DEFAULT 'output',
            target_node_id TEXT NOT NULL,
            target_input TEXT DEFAULT 'input',
            FOREIGN KEY(workflow_id) REFERENCES workflows(id) ON DELETE CASCADE,
            UNIQUE(workflow_id, connection_id)
        );
        CREATE INDEX IF NOT EXISTS idx_workflow_connections_workflow ON workflow_connections(workflow_id);
        CREATE INDEX IF NOT EXISTS idx_workflow_connections_source ON workflow_connections(source_node_id);
        CREATE INDEX IF NOT EXISTS idx_workflow_connections_target ON workflow_connections(target_node_id);
    """)
    print("  Created workflow_connections table")


def create_execution_history_table(conn):
    """Create execution_history table for detailed audit trail."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS execution_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            execution_id INTEGER NOT NULL,
            execution_type TEXT NOT NULL,
            tool_id INTEGER,
            workflow_id INTEGER,
            workflow_step_id INTEGER,
            command TEXT,
            status TEXT DEFAULT 'pending',
            status_message TEXT,
            return_code INTEGER,
            started_at TEXT DEFAULT (datetime('now')),
            completed_at TEXT,
            output_files_json TEXT,
            metadata_json TEXT,
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(tool_id) REFERENCES tools(id) ON DELETE SET NULL,
            FOREIGN KEY(workflow_id) REFERENCES workflows(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_exec_history_execution ON execution_history(execution_id);
        CREATE INDEX IF NOT EXISTS idx_exec_history_tool ON execution_history(tool_id);
        CREATE INDEX IF NOT EXISTS idx_exec_history_workflow ON execution_history(workflow_id);
        CREATE INDEX IF NOT EXISTS idx_exec_history_status ON execution_history(status);
        CREATE INDEX IF NOT EXISTS idx_exec_history_started ON execution_history(started_at);
    """)
    print("  Created execution_history table")


def create_audit_events_table(conn):
    """Create audit_events table for detailed event logging."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            execution_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            details_json TEXT,
            occurred_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(execution_id) REFERENCES execution_history(execution_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_audit_execution ON audit_events(execution_id);
        CREATE INDEX IF NOT EXISTS idx_audit_event_type ON audit_events(event_type);
        CREATE INDEX IF NOT EXISTS idx_audit_occurred ON audit_events(occurred_at);
    """)
    print("  Created audit_events table")


def create_storage_quotas_table(conn):
    """Create storage_quotas table for quota management."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS storage_quotas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL UNIQUE,
            quota_bytes BIGINT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_quota_path ON storage_quotas(path);
    """)
    print("  Created storage_quotas table")


def create_quota_snapshots_table(conn):
    """Create quota_snapshots table for tracking quota usage over time."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS quota_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL,
            used_bytes BIGINT,
            quota_bytes BIGINT,
            percent_used REAL,
            within_quota BOOLEAN DEFAULT 1,
            snapshot_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_quota_snap_path ON quota_snapshots(path);
        CREATE INDEX IF NOT EXISTS idx_quota_snap_time ON quota_snapshots(snapshot_at);
    """)
    print("  Created quota_snapshots table")


def create_cleanup_policies_table(conn):
    """Create cleanup_policies table for cleanup policy management."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS cleanup_policies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            path_pattern TEXT NOT NULL,
            retention TEXT NOT NULL,
            min_age_days INTEGER DEFAULT 7,
            file_type_patterns TEXT,
            exclude_patterns TEXT,
            dry_run BOOLEAN DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_cleanup_name ON cleanup_policies(name);
    """)
    print("  Created cleanup_policies table")


def create_tool_definitions_table(conn):
    """Create tool_definitions table for tool registry."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tool_definitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            version TEXT NOT NULL,
            description TEXT,
            source TEXT NOT NULL,
            source_url TEXT,
            install_path TEXT,
            compatibility_json TEXT,
            dependencies_json TEXT,
            parameters_json TEXT,
            input_formats_json TEXT,
            output_formats_json TEXT,
            is_active BOOLEAN DEFAULT 1,
            registered_at TEXT DEFAULT (datetime('now')),
            metadata_json TEXT,
            UNIQUE(tool_id, name, version)
        );
        CREATE INDEX IF NOT EXISTS idx_tool_defs_name ON tool_definitions(name);
        CREATE INDEX IF NOT EXISTS idx_tool_defs_version ON tool_definitions(version);
    """)
    print("  Created tool_definitions table")


def create_tool_installations_table(conn):
    """Create tool_installations table for installed tool instances."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tool_installations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_definition_id INTEGER NOT NULL,
            version TEXT NOT NULL,
            install_path TEXT NOT NULL,
            installed_at TEXT DEFAULT (datetime('now')),
            last_verified TEXT,
            status TEXT DEFAULT 'installed',
            checksum TEXT,
            metadata_json TEXT,
            FOREIGN KEY(tool_definition_id) REFERENCES tool_definitions(id) ON DELETE CASCADE,
            UNIQUE(tool_definition_id, version, install_path)
        );
        CREATE INDEX IF NOT EXISTS idx_installations_def ON tool_installations(tool_definition_id);
    """)
    print("  Created tool_installations table")


def create_tool_validations_table(conn):
    """Create tool_validations table for validation results."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tool_validations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_definition_id INTEGER NOT NULL,
            test_dataset TEXT NOT NULL,
            status TEXT NOT NULL,
            execution_time REAL,
            output_checksum TEXT,
            expected_output TEXT,
            actual_output TEXT,
            errors_json TEXT,
            warnings_json TEXT,
            validated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(tool_definition_id) REFERENCES tool_definitions(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_validations_def ON tool_validations(tool_definition_id);
        CREATE INDEX IF NOT EXISTS idx_validations_status ON tool_validations(status);
    """)
    print("  Created tool_validations table")


def create_plugins_table(conn):
    """Create plugins table for plugin management."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS plugins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            version TEXT NOT NULL,
            description TEXT,
            author TEXT,
            license TEXT,
            plugin_type TEXT NOT NULL,
            entry_point TEXT,
            dependencies_json TEXT,
            config_schema_json TEXT,
            tags_json TEXT,
            module_path TEXT,
            status TEXT DEFAULT 'discovered',
            loaded_at TEXT,
            initialized_at TEXT,
            error_message TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_plugins_name ON plugins(name);
        CREATE INDEX IF NOT EXISTS idx_plugins_type ON plugins(plugin_type);
    """)
    print("  Created plugins table")


def create_api_clients_table(conn):
    """Create api_clients table for API authentication."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS api_clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id TEXT NOT NULL UNIQUE,
            client_name TEXT,
            api_key TEXT NOT NULL,
            api_secret TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            last_used TEXT,
            is_active BOOLEAN DEFAULT 1,
            rate_limit INTEGER DEFAULT 100,
            allowed_ips TEXT,
            metadata_json TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_clients_key ON api_clients(api_key);
        CREATE INDEX IF NOT EXISTS idx_clients_active ON api_clients(is_active);
    """)
    print("  Created api_clients table")


def create_api_requests_table(conn):
    """Create api_requests table for API request logging."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS api_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            method TEXT NOT NULL,
            path TEXT NOT NULL,
            version TEXT,
            status_code INTEGER,
            request_size INTEGER,
            response_size INTEGER,
            duration_ms REAL,
            client_ip TEXT,
            user_agent TEXT,
            request_body_hash TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(client_id) REFERENCES api_clients(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_requests_client ON api_requests(client_id);
        CREATE INDEX IF NOT EXISTS idx_requests_path ON api_requests(path);
        CREATE INDEX IF NOT EXISTS idx_requests_created ON api_requests(created_at);
    """)
    print("  Created api_requests table")


def create_tutorials_table(conn):
    """Create tutorials table for interactive tutorials."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tutorials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tutorial_id TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            description TEXT,
            duration_minutes INTEGER,
            difficulty TEXT,
            prerequisites_json TEXT,
            steps_json TEXT NOT NULL,
            output_files_json TEXT,
            tools_used_json TEXT,
            tags_json TEXT,
            next_tutorial TEXT,
            related_tutorials_json TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_tutorials_id ON tutorials(tutorial_id);
        CREATE INDEX IF NOT EXISTS idx_tutorials_difficulty ON tutorials(difficulty);
    """)
    print("  Created tutorials table")


def populate_default_dependencies(conn):
    """Populate common bioinformatics dependencies."""
    cursor = conn.cursor()

    # Check if already populated
    cursor.execute("SELECT COUNT(*) FROM dependencies")
    if cursor.fetchone()[0] > 0:
        print("  Dependencies table already populated, skipping")
        return

    defaults = [
        ('python3', None, 'system', 'apt-get install python3', 'python3 --version', 'Python 3 interpreter', 'https://python.org'),
        ('perl', None, 'system', 'apt-get install perl', 'perl --version', 'Perl interpreter', 'https://perl.org'),
        ('R', None, 'system', 'apt-get install r-base', 'R --version', 'R statistical language', 'https://r-project.org'),
        ('conda', None, 'conda', 'wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh', 'conda --version', 'Conda package manager', 'https://conda.io'),
        ('samtools', None, 'conda', 'conda install -c bioconda samtools', 'samtools --version', 'SAM/BAM file manipulation', 'http://samtools.sourceforge.net/'),
        ('bwa', None, 'conda', 'conda install -c bioconda bwa', 'bwa', 'Burrows-Wheeler Aligner', 'https://github.com/lh3/bwa'),
        ('spades', None, 'conda', 'conda install -c bioconda spades', 'spades.py --version', 'SPAdes genome assembler', 'http://cab.spbu.ru/software/spades/'),
        ('fastqc', None, 'conda', 'conda install -c bioconda fastqc', 'fastqc --version', 'Quality control for FASTQ files', 'https://www.bioinformatics.babraham.ac.uk/projects/fastqc/'),
        ('bowtie2', None, 'conda', 'conda install -c bioconda bowtie2', 'bowtie2 --version', 'Bowtie2 read aligner', 'http://bowtie-bio.sourceforge.net/bowtie2/'),
        ('blast', None, 'conda', 'conda install -c bioconda blast', 'blastn -version', 'BLAST sequence alignment', 'https://blast.ncbi.nlm.nih.gov/'),
    ]

    cursor.executemany("""
        INSERT OR IGNORE INTO dependencies (name, version, package_manager, install_command, check_command, description, url)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, defaults)
    conn.commit()
    print(f"  Populated {len(defaults)} default dependencies")


def populate_default_tutorials(conn):
    """Populate tutorial definitions."""
    cursor = conn.cursor()

    # Check if already populated
    cursor.execute("SELECT COUNT(*) FROM tutorials")
    if cursor.fetchone()[0] > 0:
        print("  Tutorials table already populated, skipping")
        return

    import json

    tutorials = [
        (
            'getting_started',
            'Getting Started with Virometrics',
            'Learn the basics of the Virometrics platform',
            10,
            'beginner',
            json.dumps([]),
            json.dumps([{'index': 0, 'title': 'Welcome'}, {'index': 1, 'title': 'Loading Data'}, {'index': 2, 'title': 'Running Analysis'}, {'index': 3, 'title': 'Viewing Results'}, {'index': 4, 'title': 'Exporting'}]),
            json.dumps([]),
            json.dumps([]),
            json.dumps(['basics', 'workflow', 'beginner']),
            'variant_calling',
            json.dumps([])
        ),
        (
            'variant_calling',
            'Variant Calling Pipeline',
            'Learn how to call variants from sequencing data',
            25,
            'intermediate',
            json.dumps(['getting_started']),
            json.dumps([{'index': 0, 'title': 'Overview'}, {'index': 1, 'title': 'Quality Control'}, {'index': 2, 'title': 'Read Alignment'}, {'index': 3, 'title': 'BAM Processing'}, {'index': 4, 'title': 'Variant Calling'}]),
            json.dumps(['/variants/called_variants.vcf', '/reports/qc_report.html']),
            json.dumps(['fastqc', 'bwa', 'samtools', 'freebayes']),
            json.dumps(['variants', 'snp', 'pipeline', 'intermediate']),
            'custom_workflow',
            json.dumps([])
        ),
        (
            'custom_workflow',
            'Building Custom Workflows',
            'Create your own analysis workflows by combining tools',
            30,
            'advanced',
            json.dumps(['getting_started', 'variant_calling']),
            json.dumps([{'index': 0, 'title': 'Workflow Overview'}, {'index': 1, 'title': 'Define Inputs'}, {'index': 2, 'title': 'Add Tools'}, {'index': 3, 'title': 'Configure Parameters'}, {'index': 4, 'title': 'Save Workflow'}]),
            json.dumps(['/workflows/custom_workflow.json']),
            json.dumps(['workflow_engine', 'tool_registry']),
            json.dumps(['workflow', 'automation', 'advanced', 'customization']),
            None,
            json.dumps(['variant_calling', 'getting_started'])
        )
    ]

    cursor.executemany("""
        INSERT OR IGNORE INTO tutorials (
            tutorial_id, title, description, duration_minutes, difficulty,
            prerequisites_json, steps_json, output_files_json, tools_used_json,
            tags_json, next_tutorial, related_tutorials_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, tutorials)
    conn.commit()
    print(f"  Populated {len(tutorials)} default tutorials")


def run_migration(db_path=None):
    """Run the full database migration."""
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}")
        print("Please run enhance_metadata.py first to create the database.")
        sys.exit(1)

    print(f"Migrating database: {db_path}")
    print("=" * 50)

    conn = get_connection(db_path)
    cursor = conn.cursor()

    try:
        # Check existing tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing = {row['name'] for row in cursor.fetchall()}
        print(f"Existing tables: {', '.join(sorted(existing))}")

        # Create new tables
        print("\nCreating new tables...")
        create_tool_executions_table(conn)
        create_execution_outputs_table(conn)
        create_tool_parameters_table(conn)
        create_dependencies_table(conn)
        create_tool_dependencies_table(conn)
        create_installed_dependencies_table(conn)
        create_data_files_table(conn)
        create_storage_metrics_table(conn)
        create_workflows_table(conn)
        create_workflow_steps_table(conn)
        create_workflow_executions_table(conn)
        create_workflow_step_executions_table(conn)
        create_workflow_nodes_table(conn)
        create_workflow_connections_table(conn)
        create_execution_history_table(conn)
        create_audit_events_table(conn)
        create_storage_quotas_table(conn)
        create_quota_snapshots_table(conn)
        create_cleanup_policies_table(conn)
        create_tool_definitions_table(conn)
        create_tool_installations_table(conn)
        create_tool_validations_table(conn)
        create_plugins_table(conn)
        create_api_clients_table(conn)
        create_api_requests_table(conn)
        create_tutorials_table(conn)

        # Populate default data
        print("\nPopulating default data...")
        populate_default_dependencies(conn)
        populate_default_tutorials(conn)

        conn.commit()

        # Verify
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        all_tables = {row['name'] for row in cursor.fetchall()}
        print(f"\nFinal tables: {', '.join(sorted(all_tables))}")

        print("\nMigration completed successfully!")

    except sqlite3.Error as e:
        print(f"Database error: {e}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == '__main__':
    db_path = sys.argv[1] if len(sys.argv) > 1 else None
    run_migration(db_path)
