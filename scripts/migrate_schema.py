#!/usr/bin/env python3
"""
Migration script for Virometrics database schema updates.
Handles schema versioning and incremental migrations.
"""

import sqlite3
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

# Default paths
DEFAULT_DB_PATH = "/home/ihcm-ubuntu/Virometrics/data/virometrics.db"


def get_connection(db_path: str):
    """Create database connection."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    """Check if a table exists."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    return cursor.fetchone() is not None


def column_exists(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = {row['name'] for row in cursor.fetchall()}
    return column_name in columns


def create_schema_version_table(conn: sqlite3.Connection):
    """Create schema_version table if it doesn't exist."""
    if not table_exists(conn, 'schema_version'):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS schema_version (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version INTEGER NOT NULL UNIQUE,
                applied_at TEXT DEFAULT (datetime('now')),
                description TEXT
            );
        """)
        print("  Created schema_version table")


def get_current_version(conn: sqlite3.Connection) -> int:
    """Get current schema version."""
    if not table_exists(conn, 'schema_version'):
        return 0
    
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(version) as version FROM schema_version")
    row = cursor.fetchone()
    return row['version'] if row and row['version'] else 0


def record_version(conn: sqlite3.Connection, version: int, description: str):
    """Record applied schema version."""
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO schema_version (version, applied_at, description) VALUES (?, ?, ?)",
        (version, datetime.now().isoformat(), description)
    )
    conn.commit()


def migrate_v1_to_v2(conn: sqlite3.Connection):
    """Migration from v1 to v2: Add workflow_nodes and workflow_connections tables."""
    print("  Migrating v1 -> v2: Adding workflow visualization tables")
    
    if not table_exists(conn, 'workflow_nodes'):
        conn.executescript("""
            CREATE TABLE workflow_nodes (
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
            CREATE INDEX idx_workflow_nodes_workflow ON workflow_nodes(workflow_id);
        """)
    
    if not table_exists(conn, 'workflow_connections'):
        conn.executescript("""
            CREATE TABLE workflow_connections (
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
            CREATE INDEX idx_workflow_connections_workflow ON workflow_connections(workflow_id);
        """)
    
    record_version(conn, 2, "Added workflow_nodes and workflow_connections tables")


def migrate_v2_to_v3(conn: sqlite3.Connection):
    """Migration from v2 to v3: Add execution_history and audit_events tables."""
    print("  Migrating v2 -> v3: Adding execution history tables")
    
    if not table_exists(conn, 'execution_history'):
        conn.executescript("""
            CREATE TABLE execution_history (
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
            CREATE INDEX idx_exec_history_execution ON execution_history(execution_id);
            CREATE INDEX idx_exec_history_status ON execution_history(status);
        """)
    
    if not table_exists(conn, 'audit_events'):
        conn.executescript("""
            CREATE TABLE audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                execution_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                details_json TEXT,
                occurred_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY(execution_id) REFERENCES execution_history(execution_id) ON DELETE CASCADE
            );
            CREATE INDEX idx_audit_execution ON audit_events(execution_id);
        """)
    
    record_version(conn, 3, "Added execution_history and audit_events tables")


def migrate_v3_to_v4(conn: sqlite3.Connection):
    """Migration from v3 to v4: Add storage quota management tables."""
    print("  Migrating v3 -> v4: Adding storage quota management tables")
    
    if not table_exists(conn, 'storage_quotas'):
        conn.executescript("""
            CREATE TABLE storage_quotas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL UNIQUE,
                quota_bytes BIGINT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );
        """)
    
    if not table_exists(conn, 'quota_snapshots'):
        conn.executescript("""
            CREATE TABLE quota_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL,
                used_bytes BIGINT,
                quota_bytes BIGINT,
                percent_used REAL,
                within_quota BOOLEAN DEFAULT 1,
                snapshot_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX idx_quota_snap_path ON quota_snapshots(path);
        """)
    
    record_version(conn, 4, "Added storage quota management tables")


def migrate_v4_to_v5(conn: sqlite3.Connection):
    """Migration from v4 to v5: Add cleanup policies table."""
    print("  Migrating v4 -> v5: Adding cleanup policies table")
    
    if not table_exists(conn, 'cleanup_policies'):
        conn.executescript("""
            CREATE TABLE cleanup_policies (
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
        """)
    
    record_version(conn, 5, "Added cleanup_policies table")


def migrate_v5_to_v6(conn: sqlite3.Connection):
    """Migration from v5 to v6: Add columns to storage_metrics for detailed stats."""
    print("  Migrating v5 -> v6: Adding storage metrics enhancement")
    
    if table_exists(conn, 'storage_metrics'):
        # Add columns if they don't exist
        if not column_exists(conn, 'storage_metrics', 'file_type_stats'):
            cursor = conn.cursor()
            cursor.execute("ALTER TABLE storage_metrics ADD COLUMN file_type_json TEXT")
        
        if not column_exists(conn, 'storage_metrics', 'directory_sizes'):
            cursor = conn.cursor()
            cursor.execute("ALTER TABLE storage_metrics ADD COLUMN directory_sizes_json TEXT")
    
    record_version(conn, 6, "Enhanced storage_metrics with file type and directory stats")


def run_migration(db_path: Optional[str] = None, target_version: Optional[int] = None):
    """Run incremental migrations to target version."""
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    
    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}")
        sys.exit(1)
    
    print(f"Migrating database: {db_path}")
    print("=" * 50)
    
    conn = get_connection(db_path)
    
    try:
        # Ensure schema_version table exists
        create_schema_version_table(conn)
        
        # Get current version
        current_version = get_current_version(conn)
        print(f"Current schema version: {current_version}")
        
        # Default target is latest (6)
        if target_version is None:
            target_version = 6
        
        print(f"Target schema version: {target_version}")
        
        # Run migrations
        migrations = {
            (1, 2): migrate_v1_to_v2,
            (2, 3): migrate_v2_to_v3,
            (3, 4): migrate_v3_to_v4,
            (4, 5): migrate_v4_to_v5,
            (5, 6): migrate_v5_to_v6,
        }
        
        for (from_ver, to_ver), migration_func in migrations.items():
            if from_ver <= current_version < to_ver:
                migration_func(conn)
                conn.commit()
        
        # Verify
        final_version = get_current_version(conn)
        print(f"\nFinal schema version: {final_version}")
        
        # List all tables
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row['name'] for row in cursor.fetchall()]
        print(f"\nTotal tables: {len(tables)}")
        print(f"Tables: {', '.join(tables)}")
        
        print("\nMigration completed successfully!")
        
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()


def rollback_migration(db_path: Optional[str] = None, to_version: int = 0):
    """Rollback migrations to specified version."""
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    
    print(f"Rolling back database: {db_path}")
    print(f"Target version: {to_version}")
    
    conn = get_connection(db_path)
    
    try:
        # Get current version
        current_version = get_current_version(conn)
        print(f"Current version: {current_version}")
        
        if current_version <= to_version:
            print("Database already at or below target version")
            return
        
        # Simple rollback: drop tables added in later versions
        if to_version < 6:
            for table in ['cleanup_policies']:
                if table_exists(conn, table):
                    conn.execute(f"DROP TABLE {table}")
                    print(f"  Dropped {table}")
        
        if to_version < 4:
            for table in ['quota_snapshots', 'storage_quotas']:
                if table_exists(conn, table):
                    conn.execute(f"DROP TABLE {table}")
                    print(f"  Dropped {table}")
        
        if to_version < 3:
            for table in ['audit_events', 'execution_history']:
                if table_exists(conn, table):
                    conn.execute(f"DROP TABLE {table}")
                    print(f"  Dropped {table}")
        
        if to_version < 2:
            for table in ['workflow_connections', 'workflow_nodes']:
                if table_exists(conn, table):
                    conn.execute(f"DROP TABLE {table}")
                    print(f"  Dropped {table}")
        
        # Update version
        cursor = conn.cursor()
        cursor.execute("DELETE FROM schema_version WHERE version > ?", (to_version,))
        conn.commit()
        
        print(f"\nRolled back to version {to_version}")
        
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()


def main():
    """Main entry point."""
    action = sys.argv[1] if len(sys.argv) > 1 else 'migrate'
    db_path = sys.argv[2] if len(sys.argv) > 2 else None
    version = int(sys.argv[3]) if len(sys.argv) > 3 else None
    
    if action == 'migrate':
        run_migration(db_path, version)
    elif action == 'rollback':
        rollback_migration(db_path, version or 0)
    elif action == 'version':
        conn = get_connection(db_path or DEFAULT_DB_PATH)
        print(f"Current version: {get_current_version(conn)}")
        conn.close()
    else:
        print(f"Unknown action: {action}")
        print("Usage: migrate_schema.py [migrate|rollback|version] [db_path] [version]")


if __name__ == '__main__':
    main()
