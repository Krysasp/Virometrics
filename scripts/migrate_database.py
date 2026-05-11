#!/usr/bin/env python3
"""
Database migration script to add README support.
Adds readme_sections and readme_fetched_at columns to tools table.
"""

import sqlite3
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def add_readme_columns(db_path: str) -> bool:
    """Add readme_sections and readme_fetched_at columns to tools table."""
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(tools)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'readme_sections' in columns and 'readme_fetched_at' in columns:
            logger.info("README columns already exist")
            return True
        
        # Add readme_sections column
        if 'readme_sections' not in columns:
            logger.info("Adding readme_sections column...")
            cursor.execute("ALTER TABLE tools ADD COLUMN readme_sections TEXT")
        
        # Add readme_fetched_at column
        if 'readme_fetched_at' not in columns:
            logger.info("Adding readme_fetched_at column...")
            cursor.execute("ALTER TABLE tools ADD COLUMN readme_fetched_at TEXT")
        
        conn.commit()
        logger.info("Database schema updated successfully")
        return True
        
    except Exception as e:
        logger.error(f"Error updating schema: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def add_data_management_tables(db_path: str) -> bool:
    """Add data management tables for tracking storage."""
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        
        # Check if tables already exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='data_assets'")
        if not cursor.fetchone():
            cursor.execute("""
                CREATE TABLE data_assets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_id INTEGER,
                    file_path TEXT NOT NULL,
                    file_type TEXT,
                    file_size INTEGER DEFAULT 0,
                    created_at TEXT
                )
            """)
            logger.info("Created data_assets table")
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='storage_metrics'")
        if not cursor.fetchone():
            cursor.execute("""
                CREATE TABLE storage_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    total_size INTEGER DEFAULT 0,
                    file_count INTEGER DEFAULT 0,
                    updated_at TEXT
                )
            """)
            logger.info("Created storage_metrics table")
        
        # Create indexes for better performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_data_assets_tool ON data_assets(tool_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_data_assets_type ON data_assets(file_type)")
        
        conn.commit()
        logger.info("Data management tables created successfully")
        return True
        
    except Exception as e:
        logger.error(f"Error creating tables: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def migrate():
    """Run all migrations."""
    base_dir = Path(__file__).parent.parent
    db_path = base_dir / 'data' / 'virometrics.db'
    
    if not db_path.exists():
        logger.error(f"Database not found at {db_path}")
        return False
    
    logger.info(f"Migrating database at {db_path}")
    
    success = True
    
    # Run migrations
    success &= add_readme_columns(str(db_path))
    success &= add_data_management_tables(str(db_path))
    
    if success:
        logger.info("All migrations completed successfully")
    else:
        logger.warning("Some migrations failed")
    
    return success


if __name__ == '__main__':
    migrate()
