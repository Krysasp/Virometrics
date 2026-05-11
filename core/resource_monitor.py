"""Resource monitoring for Virometrics job execution.

Tracks CPU, memory, disk I/O per job and implements automatic termination
if resource limits are exceeded.
"""

import os
import time
import json
import sqlite3
import logging
import threading
from datetime import datetime
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logging.getLogger(__name__).warning("psutil not available")


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ResourceExceededError(Exception):
    """Raised when a resource limit is exceeded."""
    
    def __init__(self, resource_type: str, limit: Any, current: Any):
        self.resource_type = resource_type
        self.limit = limit
        self.current = current
        super().__init__(f"{resource_type} limit exceeded: {current} > {limit}")


class ResourceType(Enum):
    """Types of resources that can be monitored."""
    CPU = "cpu"
    MEMORY = "memory"
    DISK_IO = "disk_io"
    DISK_SPACE = "disk_space"
    WALL_TIME = "wall_time"


@dataclass
class ResourceLimit:
    """Resource limit configuration for a tool."""
    
    tool_id: int
    max_cpu_percent: float = 80.0
    max_memory_mb: float = 4096.0
    max_disk_io_mb: float = 500.0
    max_wall_time_seconds: float = 3600.0
    max_disk_space_mb: float = 1024.0
    check_interval: float = 1.0
    warning_threshold: float = 0.8
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ResourceLimit':
        """Create from dictionary."""
        return cls(
            tool_id=data['tool_id'],
            max_cpu_percent=data.get('max_cpu_percent', 80.0),
            max_memory_mb=data.get('max_memory_mb', 4096.0),
            max_disk_io_mb=data.get('max_disk_io_mb', 500.0),
            max_wall_time_seconds=data.get('max_wall_time_seconds', 3600.0),
            max_disk_space_mb=data.get('max_disk_space_mb', 1024.0),
            check_interval=data.get('check_interval', 1.0),
            warning_threshold=data.get('warning_threshold', 0.8),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'tool_id': self.tool_id,
            'max_cpu_percent': self.max_cpu_percent,
            'max_memory_mb': self.max_memory_mb,
            'max_disk_io_mb': self.max_disk_io_mb,
            'max_wall_time_seconds': self.max_wall_time_seconds,
            'max_disk_space_mb': self.max_disk_space_mb,
            'check_interval': self.check_interval,
            'warning_threshold': self.warning_threshold,
        }


@dataclass
class ResourceUsage:
    """Resource usage snapshot."""
    
    timestamp: datetime
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    memory_percent: float = 0.0
    disk_read_mb: float = 0.0
    disk_write_mb: float = 0.0
    wall_time_seconds: float = 0.0
    disk_space_used_mb: float = 0.0


class ResourceMonitor:
    """Monitor resource usage for job execution."""
    
    def __init__(
        self,
        db_path: Optional[str] = None,
        default_limits: Optional[ResourceLimit] = None,
    ):
        self.db_path = db_path or os.path.join(
            os.path.dirname(__file__), '..', 'data', 'virometrics.db'
        )
        self.default_limits = default_limits or ResourceLimit(tool_id=0)
        
        self._monitors: Dict[int, '_JobMonitor'] = {}
        self._lock = threading.Lock()
        
        # Load resource limits from database
        self._limits: Dict[int, ResourceLimit] = {}
        self._load_limits()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn
    
    def _load_limits(self):
        """Load resource limits from database."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM resource_limits")
            
            for row in cursor.fetchall():
                limit = ResourceLimit.from_dict(dict(row))
                self._limits[limit.tool_id] = limit
            
            conn.close()
            logger.info(f"Loaded {len(self._limits)} resource limits")
        except Exception as e:
            logger.warning(f"Error loading resource limits: {e}")
    
    def set_limit(self, limit: ResourceLimit):
        """Set resource limit for a tool."""
        self._limits[limit.tool_id] = limit
        
        # Update in database
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """INSERT OR REPLACE INTO resource_limits
                   (tool_id, max_cpu_percent, max_memory_mb, max_disk_io_mb,
                    max_wall_time_seconds, max_disk_space_mb, check_interval,
                    warning_threshold)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    limit.tool_id,
                    limit.max_cpu_percent,
                    limit.max_memory_mb,
                    limit.max_disk_io_mb,
                    limit.max_wall_time_seconds,
                    limit.max_disk_space_mb,
                    limit.check_interval,
                    limit.warning_threshold,
                )
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error saving resource limit: {e}")
    
    def get_limit(self, tool_id: int) -> ResourceLimit:
        """Get resource limit for a tool."""
        return self._limits.get(tool_id, self.default_limits)
    
    def start_monitoring(
        self,
        execution_id: int,
        pid: int,
        working_dir: Optional[str] = None,
        tool_id: Optional[int] = None,
        callback: Optional[Callable[[ResourceUsage, ResourceLimit], None]] = None,
    ) -> '_JobMonitor':
        """Start monitoring a job's resource usage."""
        if not PSUTIL_AVAILABLE:
            logger.warning("psutil not available, monitoring disabled")
            return _JobMonitor(execution_id, pid)
        
        with self._lock:
            monitor = _JobMonitor(
                execution_id=execution_id,
                pid=pid,
                working_dir=working_dir,
                tool_id=tool_id,
                resource_limits=self.get_limit(tool_id) if tool_id else self.default_limits,
                db_path=self.db_path,
                callback=callback,
            )
            self._monitors[execution_id] = monitor
            monitor.start()
            
            logger.info(f"Started monitoring execution {execution_id} (PID: {pid})")
            return monitor
    
    def stop_monitoring(self, execution_id: int):
        """Stop monitoring a job."""
        with self._lock:
            if execution_id in self._monitors:
                self._monitors[execution_id].stop()
                del self._monitors[execution_id]
                logger.debug(f"Stopped monitoring execution {execution_id}")
    
    def get_usage_history(
        self,
        execution_id: int,
        limit: int = 100,
    ) -> List[ResourceUsage]:
        """Get resource usage history for a job."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM resource_usage
                   WHERE execution_id = ?
                   ORDER BY timestamp DESC
                   LIMIT ?""",
                (execution_id, limit)
            )
            
            history = []
            for row in cursor.fetchall():
                usage = ResourceUsage(
                    timestamp=datetime.fromisoformat(row['timestamp']),
                    cpu_percent=row['cpu_percent'] or 0.0,
                    memory_mb=row['memory_mb'] or 0.0,
                    memory_percent=row['memory_percent'] or 0.0,
                    disk_read_mb=row['disk_read_mb'] or 0.0,
                    disk_write_mb=row['disk_write_mb'] or 0.0,
                    wall_time_seconds=row['wall_time_seconds'] or 0.0,
                    disk_space_used_mb=row['disk_space_used_mb'] or 0.0,
                )
                history.append(usage)
            
            conn.close()
            return history
        
        except Exception as e:
            logger.error(f"Error getting usage history: {e}")
            return []
    
    def get_aggregated_stats(self, execution_id: int) -> Dict[str, Any]:
        """Get aggregated resource statistics for a job."""
        history = self.get_usage_history(execution_id)
        
        if not history:
            return {'execution_id': execution_id, 'sample_count': 0}
        
        cpu_values = [h.cpu_percent for h in history]
        memory_values = [h.memory_mb for h in history]
        disk_read_values = [h.disk_read_mb for h in history]
        disk_write_values = [h.disk_write_mb for h in history]
        
        return {
            'execution_id': execution_id,
            'sample_count': len(history),
            'cpu': {
                'avg': round(sum(cpu_values) / len(cpu_values), 2),
                'max': round(max(cpu_values), 2),
                'min': round(min(cpu_values), 2),
            },
            'memory': {
                'avg_mb': round(sum(memory_values) / len(memory_values), 2),
                'max_mb': round(max(memory_values), 2),
                'min_mb': round(min(memory_values), 2),
            },
            'disk_io': {
                'total_read_mb': round(sum(disk_read_values), 2),
                'total_write_mb': round(sum(disk_write_values), 2),
            },
            'duration_seconds': max(h.wall_time_seconds for h in history),
        }


class _JobMonitor:
    """Internal job monitor that runs in a background thread."""
    
    def __init__(
        self,
        execution_id: int,
        pid: int,
        working_dir: Optional[str] = None,
        tool_id: Optional[int] = None,
        resource_limits: Optional[ResourceLimit] = None,
        db_path: Optional[str] = None,
        callback: Optional[Callable[[ResourceUsage, ResourceLimit], None]] = None,
    ):
        self.execution_id = execution_id
        self.pid = pid
        self.working_dir = working_dir
        self.tool_id = tool_id
        self.resource_limits = resource_limits
        self.db_path = db_path
        self.callback = callback
        
        self._process: Optional[psutil.Process] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._start_time = time.time()
        self._last_io_counters = None
        self._exceeded_limit: Optional[ResourceExceededError] = None
        
        self._usage_history: List[ResourceUsage] = []
    
    def _record_usage(self):
        """Record a single usage snapshot."""
        try:
            if not self._process:
                self._process = psutil.Process(self.pid)
            
            # Check if process still exists
            if not self._process.is_running():
                return None
            
            # Collect metrics
            cpu_percent = self._process.cpu_percent()
            memory_info = self._process.memory_info()
            
            # Calculate disk I/O
            current_io = self._process.io_counters()
            if self._last_io_counters:
                disk_read = (current_io.read_bytes - self._last_io_counters.read_bytes) / (1024 * 1024)
                disk_write = (current_io.write_bytes - self._last_io_counters.write_bytes) / (1024 * 1024)
            else:
                disk_read = current_io.read_bytes / (1024 * 1024)
                disk_write = current_io.write_bytes / (1024 * 1024)
            self._last_io_counters = current_io
            
            # Calculate disk space used
            disk_space = 0.0
            if self.working_dir and os.path.isdir(self.working_dir):
                for dirpath, dirnames, filenames in os.walk(self.working_dir):
                    for f in filenames:
                        try:
                            disk_space += os.path.getsize(os.path.join(dirpath, f))
                        except:
                            pass
                disk_space /= (1024 * 1024)
            
            usage = ResourceUsage(
                timestamp=datetime.now(),
                cpu_percent=round(cpu_percent, 2),
                memory_mb=round(memory_info.rss / (1024 * 1024), 2),
                memory_percent=round(self._process.memory_percent(), 2),
                disk_read_mb=round(disk_read, 2),
                disk_write_mb=round(disk_write, 2),
                wall_time_seconds=round(time.time() - self._start_time, 2),
                disk_space_used_mb=round(disk_space, 2),
            )
            
            # Store in database
            conn = sqlite3.connect(self.db_path or os.path.join(
                os.path.dirname(__file__), '..', 'data', 'virometrics.db'
            ))
            try:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT INTO resource_usage
                       (execution_id, timestamp, cpu_percent, memory_mb, 
                        memory_percent, disk_read_mb, disk_write_mb, 
                        wall_time_seconds, disk_space_used_mb)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        self.execution_id,
                        usage.timestamp.isoformat(),
                        usage.cpu_percent,
                        usage.memory_mb,
                        usage.memory_percent,
                        usage.disk_read_mb,
                        usage.disk_write_mb,
                        usage.wall_time_seconds,
                        usage.disk_space_used_mb,
                    )
                )
                conn.commit()
            finally:
                conn.close()
            
            # Check limits
            self._check_limits(usage)
            
            # Store in history
            self._usage_history.append(usage)
            
            # Call callback
            if self.callback:
                try:
                    self.callback(usage, self.resource_limits)
                except Exception as e:
                    logger.debug(f"Error in monitoring callback: {e}")
            
            return usage
        
        except psutil.NoSuchProcess:
            return None
        except Exception as e:
            logger.error(f"Error recording usage: {e}")
            return None
    
    def _check_limits(self, usage: ResourceUsage):
        """Check if any resource limits are exceeded."""
        if not self.resource_limits:
            return
        
        # Check CPU
        if usage.cpu_percent > self.resource_limits.max_cpu_percent:
            self._exceeded_limit = ResourceExceededError(
                'cpu', self.resource_limits.max_cpu_percent, usage.cpu_percent
            )
        
        # Check memory
        if usage.memory_mb > self.resource_limits.max_memory_mb:
            self._exceeded_limit = ResourceExceededError(
                'memory', self.resource_limits.max_memory_mb, usage.memory_mb
            )
        
        # Check wall time
        if usage.wall_time_seconds > self.resource_limits.max_wall_time_seconds:
            self._exceeded_limit = ResourceExceededError(
                'wall_time', self.resource_limits.max_wall_time_seconds,
                usage.wall_time_seconds
            )
        
        # Check disk space
        if usage.disk_space_used_mb > self.resource_limits.max_disk_space_mb:
            self._exceeded_limit = ResourceExceededError(
                'disk_space', self.resource_limits.max_disk_space_mb,
                usage.disk_space_used_mb
            )
    
    def start(self):
        """Start the monitoring thread."""
        self._start_time = time.time()
        self._last_io_counters = None
        
        # Initialize CPU percent
        try:
            self._process = psutil.Process(self.pid)
            self._process.cpu_percent()
        except psutil.NoSuchProcess:
            logger.warning(f"Process {self.pid} not found")
            return
        
        # Start monitoring thread
        self._thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
        )
        self._thread.start()
    
    def _monitor_loop(self):
        """Main monitoring loop."""
        interval = self.resource_limits.check_interval if self.resource_limits else 1.0
        
        while not self._stop_event.is_set():
            try:
                usage = self._record_usage()
                
                # Check if we should terminate
                if self._exceeded_limit:
                    logger.warning(
                        f"Execution {self.execution_id} exceeded {self._exceeded_limit.resource_type} "
                        f"limit: {self._exceeded_limit.current} > {self._exceeded_limit.limit}"
                    )
                    break
                
                if usage is None:
                    # Process ended
                    break
                
                time.sleep(interval)
            
            except Exception as e:
                logger.error(f"Monitoring error: {e}")
                time.sleep(interval)
    
    def stop(self):
        """Stop the monitoring thread."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
    
    def get_exceeded_limit(self) -> Optional[ResourceExceededError]:
        """Get the resource limit that was exceeded."""
        return self._exceeded_limit
    
    def should_terminate(self) -> bool:
        """Check if the monitored process should be terminated."""
        return self._exceeded_limit is not None
    
    def get_latest_usage(self) -> Optional[ResourceUsage]:
        """Get the most recent usage snapshot."""
        if self._usage_history:
            return self._usage_history[-1]
        return None
