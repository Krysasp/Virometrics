"""Cleanup policy management for Virometrics platform.

Implements automatic cleanup with configurable retention policies.
"""

import os
import sqlite3
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Callable
from enum import Enum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RetentionPolicy(Enum):
    """Retention policy types."""
    NEVER = "never"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"
    CUSTOM = "custom"


class FileAgePolicy(Enum):
    """File age-based cleanup policies."""
    LAST_24_HOURS = "last_24_hours"
    LAST_7_DAYS = "last_7_days"
    LAST_30_DAYS = "last_30_days"
    LAST_90_DAYS = "last_90_days"
    LAST_365_DAYS = "last_365_days"
    OLDER_THAN_1_YEAR = "older_than_1_year"
    OLDER_THAN_2_YEARS = "older_than_2_years"


class CleanupPolicy:
    """Define cleanup policy for files and directories."""

    def __init__(self, name: str, path_pattern: str,
                 retention: RetentionPolicy = RetentionPolicy.WEEKLY,
                 min_age_days: int = 7,
                 file_type_patterns: Optional[List[str]] = None,
                 exclude_patterns: Optional[List[str]] = None,
                 dry_run: bool = False):
        self.name = name
        self.path_pattern = path_pattern
        self.retention = retention
        self.min_age_days = min_age_days
        self.file_type_patterns = file_type_patterns or []
        self.exclude_patterns = exclude_patterns or []
        self.dry_run = dry_run
        self.created_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """Convert policy to dictionary."""
        return {
            'name': self.name,
            'path_pattern': self.path_pattern,
            'retention': self.retention.value,
            'min_age_days': self.min_age_days,
            'file_type_patterns': self.file_type_patterns,
            'exclude_patterns': self.exclude_patterns,
            'dry_run': self.dry_run,
            'created_at': self.created_at.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CleanupPolicy':
        """Create policy from dictionary."""
        policy = cls(
            name=data['name'],
            path_pattern=data['path_pattern'],
            retention=RetentionPolicy(data.get('retention', 'weekly')),
            min_age_days=data.get('min_age_days', 7),
            file_type_patterns=data.get('file_type_patterns', []),
            exclude_patterns=data.get('exclude_patterns', []),
            dry_run=data.get('dry_run', False)
        )
        if 'created_at' in data:
            policy.created_at = datetime.fromisoformat(data['created_at'])
        return policy


class CleanupManager:
    """Manage cleanup policies and execute cleanup operations."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or str(Path(__file__).parent.parent / 'data' / 'virometrics.db')
        self.policies: List[CleanupPolicy] = []
        self.cleanup_history: List[Dict[str, Any]] = []

    def _get_connection(self):
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def add_policy(self, policy: CleanupPolicy) -> None:
        """Add a cleanup policy."""
        self.policies.append(policy)
        self._save_policy_to_db(policy)
        logger.info(f"Added cleanup policy: {policy.name}")

    def remove_policy(self, policy_name: str) -> bool:
        """Remove a cleanup policy by name."""
        for i, policy in enumerate(self.policies):
            if policy.name == policy_name:
                del self.policies[i]
                self._delete_policy_from_db(policy_name)
                logger.info(f"Removed cleanup policy: {policy_name}")
                return True
        return False

    def list_policies(self) -> List[Dict[str, Any]]:
        """List all cleanup policies."""
        return [policy.to_dict() for policy in self.policies]

    def _save_policy_to_db(self, policy: CleanupPolicy) -> None:
        """Save policy to database."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT OR REPLACE INTO cleanup_policies
                   (name, path_pattern, retention, min_age_days,
                    file_type_patterns, exclude_patterns, dry_run, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (policy.name, policy.path_pattern, policy.retention.value,
                 policy.min_age_days,
                 '|'.join(policy.file_type_patterns),
                 '|'.join(policy.exclude_patterns),
                 policy.dry_run, policy.created_at.isoformat())
            )
            conn.commit()
        finally:
            conn.close()

    def _delete_policy_from_db(self, policy_name: str) -> None:
        """Delete policy from database."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM cleanup_policies WHERE name=?", (policy_name,))
            conn.commit()
        finally:
            conn.close()

    def load_policies_from_db(self) -> None:
        """Load cleanup policies from database."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM cleanup_policies")
            for row in cursor.fetchall():
                policy = CleanupPolicy(
                    name=row['name'],
                    path_pattern=row['path_pattern'],
                    retention=RetentionPolicy(row['retention']),
                    min_age_days=row['min_age_days'],
                    file_type_patterns=row['file_type_patterns'].split('|') if row['file_type_patterns'] else [],
                    exclude_patterns=row['exclude_patterns'].split('|') if row['exclude_patterns'] else [],
                    dry_run=bool(row['dry_run'])
                )
                if row['created_at']:
                    policy.created_at = datetime.fromisoformat(row['created_at'])
                self.policies.append(policy)
        finally:
            conn.close()
        
        logger.info(f"Loaded {len(self.policies)} cleanup policies from database")

    def _matches_file(self, filepath: str, policy: CleanupPolicy) -> bool:
        """Check if file matches cleanup policy."""
        from fnmatch import fnmatch
        
        # Check path pattern
        if not fnmatch(filepath, policy.path_pattern):
            return False
        
        # Check file type patterns
        if policy.file_type_patterns:
            ext = os.path.splitext(filepath)[1].lower()
            if ext not in [p.lower() for p in policy.file_type_patterns]:
                return False
        
        # Check exclude patterns
        for exclude_pattern in policy.exclude_patterns:
            if fnmatch(filepath, exclude_pattern):
                return False
        
        return True

    def _get_file_age_days(self, filepath: str) -> float:
        """Get file age in days."""
        try:
            mtime = os.path.getmtime(filepath)
            age_seconds = (datetime.now() - datetime.fromtimestamp(mtime)).total_seconds()
            return age_seconds / (24 * 3600)
        except OSError:
            return 0

    def _should_delete_file(self, filepath: str, policy: CleanupPolicy) -> bool:
        """Check if file should be deleted based on policy."""
        file_age_days = self._get_file_age_days(filepath)
        return file_age_days >= policy.min_age_days

    def scan_for_cleanup(self, policy: CleanupPolicy) -> List[Dict[str, Any]]:
        """
        Scan for files matching cleanup policy.
        Returns list of files that would be cleaned up.
        """
        candidates = []
        base_path = Path(policy.path_pattern.replace('*', ''))
        
        if not base_path.exists():
            return candidates
        
        for root, dirs, files in os.walk(base_path):
            for f in files:
                filepath = os.path.join(root, f)
                if self._matches_file(filepath, policy):
                    if self._should_delete_file(filepath, policy):
                        stat = os.stat(filepath)
                        candidates.append({
                            'path': filepath,
                            'size': stat.st_size,
                            'size_mb': round(stat.st_size / (1024 * 1024), 2),
                            'modified': datetime.fromtimestamp(stat.st_mtime),
                            'age_days': round(self._get_file_age_days(filepath), 1),
                            'policy': policy.name
                        })
        
        return candidates

    def execute_cleanup(self, policy_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Execute cleanup for specified policy or all policies.
        Returns cleanup summary.
        """
        policies = self.policies if not policy_name else [
            p for p in self.policies if p.name == policy_name
        ]
        
        summary = {
            'total_files': 0,
            'total_size': 0,
            'total_size_mb': 0,
            'by_policy': {},
            'errors': []
        }
        
        for policy in policies:
            policy_summary = {
                'files_deleted': 0,
                'size_freed': 0,
                'files_skipped': 0,
                'errors': []
            }
            
            candidates = self.scan_for_cleanup(policy)
            policy_summary['total_candidates'] = len(candidates)
            
            for candidate in candidates:
                try:
                    filepath = candidate['path']
                    size = candidate['size']
                    
                    if policy.dry_run:
                        logger.info(f"[DRY RUN] Would delete: {filepath}")
                    else:
                        os.remove(filepath)
                        logger.debug(f"Deleted: {filepath}")
                    
                    policy_summary['files_deleted'] += 1
                    policy_summary['size_freed'] += size
                    
                except Exception as e:
                    error_msg = f"Error deleting {filepath}: {e}"
                    policy_summary['errors'].append(error_msg)
                    summary['errors'].append(error_msg)
            
            # Record cleanup history
            self.cleanup_history.append({
                'policy_name': policy.name,
                'timestamp': datetime.now(),
                'files_deleted': policy_summary['files_deleted'],
                'size_freed': policy_summary['size_freed'],
                'dry_run': policy.dry_run
            })
            
            summary['by_policy'][policy.name] = policy_summary
            summary['total_files'] += policy_summary['files_deleted']
            summary['total_size'] += policy_summary['size_freed']
        
        summary['total_size_mb'] = round(summary['total_size'] / (1024 * 1024), 2)
        return summary

    def get_cleanup_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent cleanup history."""
        return self.cleanup_history[-limit:]

    def get_storage_freed(self, days: int = 30) -> int:
        """Get total storage freed in last N days."""
        cutoff = datetime.now() - timedelta(days=days)
        total = sum(
            entry['size_freed']
            for entry in self.cleanup_history
            if entry['timestamp'] >= cutoff
        )
        return total


def create_default_policies() -> List[CleanupPolicy]:
    """Create default cleanup policies."""
    return [
        CleanupPolicy(
            name="temp_files_cleanup",
            path_pattern="*/tmp/*",
            retention=RetentionPolicy.DAILY,
            min_age_days=1,
            file_type_patterns=[".tmp", ".temp", ".tmp.*"],
            dry_run=True
        ),
        CleanupPolicy(
            name="old_logs_cleanup",
            path_pattern="*/logs/*",
            retention=RetentionPolicy.WEEKLY,
            min_age_days=7,
            file_type_patterns=[".log", ".log.*", ".gz"],
            dry_run=False
        ),
        CleanupPolicy(
            name="old_cache_cleanup",
            path_pattern="*/cache/*",
            retention=RetentionPolicy.MONTHLY,
            min_age_days=30,
            file_type_patterns=[".cache", ".pkl"],
            dry_run=False
        ),
        CleanupPolicy(
            name="qc_reports_cleanup",
            path_pattern="*/qc_reports/*",
            retention=RetentionPolicy.MONTHLY,
            min_age_days=30,
            exclude_patterns=["*_important.*"],
            dry_run=True
        ),
        CleanupPolicy(
            name="assembly_intermediate_cleanup",
            path_pattern="*/assembly_work/*",
            retention=RetentionPolicy.WEEKLY,
            min_age_days=7,
            file_type_patterns=[".intermediate", ".temp", ".partial"],
            dry_run=False
        )
    ]


def main():
    """Demo cleanup manager functionality."""
    manager = CleanupManager()
    
    # Load existing policies
    manager.load_policies_from_db()
    
    # Add default policies if none exist
    if not manager.policies:
        for policy in create_default_policies():
            manager.add_policy(policy)
    
    print("Cleanup Policies:")
    print("=" * 50)
    for policy in manager.list_policies():
        print(f"\n{policy['name']}:")
        print(f"  Path: {policy['path_pattern']}")
        print(f"  Retention: {policy['retention']}")
        print(f"  Min Age: {policy['min_age_days']} days")
        print(f"  Dry Run: {policy['dry_run']}")
    
    print("\n" + "=" * 50)
    print("Executing cleanup...")
    
    summary = manager.execute_cleanup()
    print(f"\nTotal files deleted: {summary['total_files']}")
    print(f"Total space freed: {summary['total_size_mb']} MB")


if __name__ == '__main__':
    main()
