"""File management for Virometrics platform.

Handles data file operations: upload, listing, metadata, validation.
"""

import os
import sqlite3
import hashlib
import logging
from pathlib import Path
from typing import Optional, Dict, List, Any
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Default data directory
DATA_DIR = Path(__file__).parent.parent / 'data'
UPLOAD_DIR = DATA_DIR / 'uploads'
OUTPUT_DIR = DATA_DIR / 'outputs'

# Ensure directories exist
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Known file type extensions
FILE_TYPE_MAP = {
    'fastq': ['.fastq', '.fq', '.fastq.gz', '.fq.gz'],
    'bam': ['.bam', '.sam'],
    'vcf': ['.vcf', '.vcf.gz'],
    'fasta': ['.fasta', '.fa', '.fna', '.fa.gz', '.fasta.gz'],
    'csv': ['.csv'],
    'tsv': ['.tsv', '.tab'],
    'json': ['.json'],
    'txt': ['.txt'],
    'pdf': ['.pdf'],
    'html': ['.html', '.htm'],
}


class FileManager:
    """Manage data files for bioinformatics workflows."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            self.db_path = str(Path(__file__).parent.parent / 'data' / 'virometrics.db')
        else:
            self.db_path = db_path
        self.upload_dir = str(UPLOAD_DIR)
        self.output_dir = str(OUTPUT_DIR)

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _detect_file_type(self, filename: str) -> str:
        """Detect file type from extension."""
        filename_lower = filename.lower()
        for ftype, extensions in FILE_TYPE_MAP.items():
            if any(filename_lower.endswith(ext) for ext in extensions):
                return ftype
        return 'other'

    def _calc_md5(self, filepath: str, chunk_size: int = 8192) -> str:
        """Calculate MD5 hash of a file."""
        md5 = hashlib.md5()
        try:
            with open(filepath, 'rb') as f:
                while chunk := f.read(chunk_size):
                    md5.update(chunk)
            return md5.hexdigest()
        except Exception:
            return ''

    def register_file(self, filepath: str, tool_execution_id: Optional[int] = None,
                     workflow_id: Optional[int] = None) -> Optional[int]:
        """Register a file in the database. Returns file ID."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            filename = os.path.basename(filepath)
            file_type = self._detect_file_type(filename)
            file_size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
            md5_hash = self._calc_md5(filepath) if file_size > 0 else ''

            cursor.execute(
                """INSERT OR REPLACE INTO data_files
                   (filename, filepath, file_type, file_size, md5_hash,
                    tool_execution_id, workflow_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (filename, filepath, file_type, file_size, md5_hash,
                 tool_execution_id, workflow_id)
            )
            conn.commit()
            return cursor.lastrowid

        except Exception as e:
            logger.error(f"Error registering file {filepath}: {e}")
            return None
        finally:
            conn.close()

    def list_files(self, directory: Optional[str] = None,
                  file_type: Optional[str] = None,
                  limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """List files with optional filtering."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            query = "SELECT * FROM data_files WHERE 1=1"
            params = []

            if file_type:
                query += " AND file_type=?"
                params.append(file_type)

            if directory:
                query += " AND filepath LIKE ?"
                params.append(f"{directory}%")

            query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor.execute(query, params)
            rows = cursor.fetchall()

            return [dict(r) for r in rows]

        finally:
            conn.close()

    def get_file_info(self, file_id: int) -> Optional[Dict[str, Any]]:
        """Get file metadata."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM data_files WHERE id=?", (file_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def delete_file(self, file_id: int) -> bool:
        """Delete a file record (and optionally the file itself)."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT filepath FROM data_files WHERE id=?", (file_id,))
            row = cursor.fetchone()

            if row:
                # Try to delete the actual file
                try:
                    if os.path.exists(row['filepath']):
                        os.remove(row['filepath'])
                except Exception as e:
                    logger.warning(f"Could not delete file {row['filepath']}: {e}")

            cursor.execute("DELETE FROM data_files WHERE id=?", (file_id,))
            conn.commit()
            return True

        except Exception as e:
            logger.error(f"Error deleting file {file_id}: {e}")
            return False
        finally:
            conn.close()

    def validate_outputs(self, expected_files: List[str],
                        actual_dir: str) -> Dict[str, any]:
        """
        Check if expected output files exist.
        Returns: {missing: [...], found: [...], all_present: bool}
        """
        found = []
        missing = []

        for pattern in expected_files:
            import glob
            full_pattern = os.path.join(actual_dir, pattern)
            matches = glob.glob(full_pattern)

            if matches:
                for match in matches:
                    found.append({
                        'pattern': pattern,
                        'path': match,
                        'size': os.path.getsize(match)
                    })
            else:
                missing.append(pattern)

        return {
            'found': found,
            'missing': missing,
            'all_present': len(missing) == 0,
            'found_count': len(found),
            'missing_count': len(missing)
        }

    def scan_directory(self, directory: str,
                       tool_execution_id: Optional[int] = None) -> int:
        """Scan a directory and register all files. Returns count of files registered."""
        if not os.path.isdir(directory):
            return 0

        count = 0
        for root, dirs, files in os.walk(directory):
            for filename in files:
                filepath = os.path.join(root, filename)
                try:
                    self.register_file(filepath, tool_execution_id)
                    count += 1
                except Exception as e:
                    logger.error(f"Error registering {filepath}: {e}")

        return count
