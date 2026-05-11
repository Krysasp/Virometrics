"""Storage monitoring for Virometrics platform.

Tracks disk usage, file type statistics, and directory sizes.
"""

import os
import sys
import time
import json
import sqlite3
import logging
import threading
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable
from collections import defaultdict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Default paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / 'data'
DB_PATH = BASE_DIR / 'data' / 'virometrics.db'

# Try to import psutil for process monitoring
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logger.warning("psutil not available, some features disabled")


class StorageQuota:
    """Manage storage quotas for users and projects."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or str(DB_PATH)

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def set_quota(self, path: str, quota_bytes: int) -> bool:
        """Set storage quota for a path."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT OR REPLACE INTO storage_quotas (path, quota_bytes, updated_at)
                   VALUES (?, ?, datetime('now'))""",
                (path, quota_bytes)
            )
            conn.commit()
            return True
        finally:
            conn.close()

    def get_quota(self, path: str) -> Optional[Dict[str, Any]]:
        """Get quota for a path."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM storage_quotas WHERE path=?", (path,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_usage(self, path: str) -> Dict[str, Any]:
        """Get current usage for a path."""
        total = 0
        file_count = 0
        for root, dirs, files in os.walk(path):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                    file_count += 1
                except:
                    pass
        return {'path': path, 'used_bytes': total, 'file_count': file_count}

    def check_quota(self, path: str) -> Dict[str, Any]:
        """Check if path is within quota. Returns status info."""
        usage = self.get_usage(path)
        quota = self.get_quota(path)
        
        if not quota:
            return {
                'path': path,
                'used_bytes': usage['used_bytes'],
                'quota_bytes': None,
                'percent_used': None,
                'within_quota': True,
                'warning': False
            }
        
        quota_bytes = quota['quota_bytes']
        percent_used = (usage['used_bytes'] / quota_bytes * 100) if quota_bytes > 0 else 0
        
        return {
            'path': path,
            'used_bytes': usage['used_bytes'],
            'quota_bytes': quota_bytes,
            'percent_used': round(percent_used, 2),
            'within_quota': percent_used <= 100,
            'warning': percent_used > 80,
            'remaining_bytes': max(0, quota_bytes - usage['used_bytes'])
        }


class StorageMonitor:
    """Monitor storage usage and file statistics."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or str(DB_PATH)
        self.data_dir = str(DATA_DIR)
        self.quota_manager = StorageQuota(db_path)

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def get_disk_usage(self, path: Optional[str] = None) -> Dict[str, Any]:
        """
        Get disk usage for a path.
        Returns: {total, used, free, percent_used, path}
        """
        import shutil
        target = path or str(DATA_DIR)
        try:
            usage = shutil.disk_usage(target)
            return {
                'path': target,
                'total': usage.total,
                'used': usage.used,
                'free': usage.free,
                'percent_used': round(usage.used / usage.total * 100, 1)
            }
        except Exception as e:
            logger.error(f"Error getting disk usage for {target}: {e}")
            return {'path': target, 'error': str(e)}

    def get_file_type_stats(self, directory: Optional[str] = None) -> Dict[str, int]:
        """
        Count files by type in a directory.
        Returns: {file_type: count}
        """
        target = directory or str(DATA_DIR)
        if not os.path.isdir(target):
            return {}

        stats = defaultdict(int)
        total_files = 0

        for root, dirs, files in os.walk(target):
            for filename in files:
                total_files += 1
                ext = os.path.splitext(filename)[1].lower()
                if ext:
                    # Normalize extension
                    ext = ext.lstrip('.')
                    if ext in ('gz', 'bz2'):
                        # Get the real extension
                        base = os.path.splitext(filename)[0]
                        real_ext = os.path.splitext(base)[1].lower().lstrip('.')
                        ext = f"{real_ext}.{ext}"
                    stats[ext] += 1
                else:
                    stats['no_extension'] += 1

        # Add total
        stats['_total'] = total_files
        return dict(stats)

    def get_directory_sizes(self, base_path: Optional[str] = None,
                           max_depth: int = 2) -> List[Dict[str, Any]]:
        """
        Get sizes of subdirectories.
        Returns: [{name, path, size, file_count}]
        """
        target = base_path or str(DATA_DIR)
        if not os.path.isdir(target):
            return []

        results = []
        try:
            for entry in os.scandir(target):
                if entry.is_dir():
                    size = 0
                    file_count = 0
                    for root, dirs, files in os.walk(entry.path):
                        depth = root[len(target):].count(os.sep)
                        if depth > max_depth:
                            dirs.clear()
                            continue
                        for f in files:
                            try:
                                size += os.path.getsize(os.path.join(root, f))
                                file_count += 1
                            except:
                                pass

                    results.append({
                        'name': entry.name,
                        'path': entry.path,
                        'size': size,
                        'size_mb': round(size / (1024 * 1024), 2),
                        'file_count': file_count
                    })

            return sorted(results, key=lambda x: x['size'], reverse=True)

        except Exception as e:
            logger.error(f"Error scanning directories in {target}: {e}")
            return []

    def record_metrics(self, path: Optional[str] = None):
        """Record current storage metrics to database."""
        conn = self._get_connection()
        try:
            target = path or str(DATA_DIR)
            usage = self.get_disk_usage(target)
            file_stats = self.get_file_type_stats(target)
            dir_sizes = self.get_directory_sizes(target)

            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO storage_metrics
                   (path, total_space, used_space, free_space, file_count,
                    file_type_stats, directory_sizes)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (usage['path'], usage['total'], usage['used'],
                 usage['free'], file_stats.get('_total', 0),
                 json.dumps(file_stats), json.dumps(dir_sizes))
            )
            metric_id = cursor.lastrowid
            
            # Check and record quota status
            quota_status = self.quota_manager.check_quota(target)
            cursor.execute(
                """INSERT INTO quota_snapshots
                   (path, used_bytes, quota_bytes, percent_used, within_quota, snapshot_at)
                   VALUES (?, ?, ?, ?, ?, datetime('now'))""",
                (quota_status['path'], quota_status['used_bytes'],
                 quota_status['quota_bytes'], quota_status['percent_used'],
                 quota_status['within_quota'])
            )
            conn.commit()
            return metric_id

        except Exception as e:
            logger.error(f"Error recording metrics: {e}")
            return None
        finally:
            conn.close()

    def get_latest_metrics(self, path: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get the most recent storage metrics."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            query = "SELECT * FROM storage_metrics"
            params = []
            if path:
                query += " WHERE path=?"
                params.append(path)
            query += " ORDER BY measured_at DESC LIMIT 1"

            cursor.execute(query, params)
            row = cursor.fetchone()
            return dict(row) if row else None

        finally:
            conn.close()

    def format_size(self, size_bytes: int) -> str:
        """Format bytes to human readable string."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"
    
    def get_process_stats(self, pid: int) -> Optional[Dict[str, Any]]:
        """
        Get CPU and memory usage for a specific process.
        
        Args:
            pid: Process ID
            
        Returns:
            Dictionary with cpu_percent, memory_info, num_threads, status
        """
        if not PSUTIL_AVAILABLE:
            return {
                'pid': pid,
                'error': 'psutil not available',
                'cpu_percent': None,
                'memory_mb': None,
            }
        
        try:
            process = psutil.Process(pid)
            cpu_percent = process.cpu_percent(interval=0.1)
            memory_info = process.memory_info()
            
            return {
                'pid': pid,
                'name': process.name(),
                'cpu_percent': round(cpu_percent, 2),
                'memory_rss': memory_info.rss,
                'memory_mb': round(memory_info.rss / (1024 * 1024), 2),
                'memory_percent': round(process.memory_percent(), 2),
                'num_threads': process.num_threads(),
                'status': process.status(),
                'create_time': process.create_time(),
                'num_fds': process.num_fds(),
                'io_counters': process.io_counters()._asdict() if hasattr(process.io_counters(), '_asdict') else None,
            }
        except psutil.NoSuchProcess:
            return {
                'pid': pid,
                'name': None,
                'error': 'Process not found',
                'cpu_percent': None,
                'memory_mb': None,
            }
        except psutil.AccessDenied:
            return {
                'pid': pid,
                'error': 'Access denied',
                'cpu_percent': None,
                'memory_mb': None,
            }
        except Exception as e:
            logger.error(f"Error getting stats for process {pid}: {e}")
            return {
                'pid': pid,
                'error': str(e),
                'cpu_percent': None,
                'memory_mb': None,
            }
    
    def monitor_execution(
        self,
        execution_id: int,
        pid: int,
        callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        interval: float = 1.0,
    ) -> Dict[str, Any]:
        """
        Monitor execution in real-time, collecting stats during execution.
        
        Args:
            execution_id: Execution ID to monitor
            pid: Process ID of the running process
            callback: Optional callback function for each stats update
            interval: Sampling interval in seconds
            
        Returns:
            Dictionary with aggregated statistics
        """
        stats_history = []
        start_time = time.time()
        last_cpu = 0
        cpu_samples = []
        
        while True:
            try:
                # Check if process is still running
                if not PSUTIL_AVAILABLE:
                    process = psutil.Process(pid)
                if not psutil.pid_exists(pid):
                    break
                
                stats = self.get_process_stats(pid)
                stats['timestamp'] = datetime.now().isoformat()
                stats['execution_id'] = execution_id
                stats['duration'] = time.time() - start_time
                
                if 'cpu_percent' in stats and stats['cpu_percent'] is not None:
                    cpu_samples.append(stats['cpu_percent'])
                
                stats_history.append(stats)
                
                # Record to database
                conn = self._get_connection()
                try:
                    cursor = conn.cursor()
                    cursor.execute(
                        """INSERT INTO execution_monitoring
                           (execution_id, pid, timestamp, cpu_percent, memory_mb, 
                            memory_percent, num_threads)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (
                            execution_id,
                            pid,
                            stats['timestamp'],
                            stats.get('cpu_percent'),
                            stats.get('memory_mb'),
                            stats.get('memory_percent'),
                            stats.get('num_threads'),
                        )
                    )
                    conn.commit()
                except Exception as e:
                    logger.debug(f"Error recording monitoring data: {e}")
                finally:
                    conn.close()
                
                # Call callback if provided
                if callback:
                    try:
                        callback(stats)
                    except Exception as e:
                        logger.debug(f"Error in monitoring callback: {e}")
                
                time.sleep(interval)
                
            except Exception as e:
                logger.debug(f"Monitoring error for execution {execution_id}: {e}")
                break
        
        # Calculate aggregated stats
        if cpu_samples:
            avg_cpu = sum(cpu_samples) / len(cpu_samples)
            max_cpu = max(cpu_samples)
        else:
            avg_cpu = max_cpu = 0
        
        memory_samples = [s['memory_mb'] for s in stats_history if s.get('memory_mb')]
        
        return {
            'execution_id': execution_id,
            'total_samples': len(stats_history),
            'duration_seconds': time.time() - start_time,
            'avg_cpu_percent': round(avg_cpu, 2),
            'max_cpu_percent': round(max_cpu, 2),
            'avg_memory_mb': round(sum(memory_samples) / len(memory_samples), 2) if memory_samples else None,
            'max_memory_mb': round(max(memory_samples), 2) if memory_samples else None,
            'samples': stats_history[-10:],  # Last 10 samples
        }
