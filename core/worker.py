"""Worker module for Virometrics job processing.

Implements worker processes that consume jobs from the queue with support
for multiple workers, heartbeat mechanism, and graceful shutdown.
"""

import os
import sys
import time
import uuid
import signal
import logging
import threading
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from enum import Enum

try:
    import redis
    from rq import Worker, Queue
    from rq.job import Job as RQJob
    RQ_AVAILABLE = True
except ImportError:
    RQ_AVAILABLE = False
    logging.getLogger(__name__).warning("Redis/RQ not available")

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logging.getLogger(__name__).warning("psutil not available")


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WorkerStatus(Enum):
    """Worker status states."""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"


@dataclass
class WorkerStats:
    """Statistics for a worker."""
    worker_id: str
    status: WorkerStatus
    jobs_processed: int = 0
    jobs_failed: int = 0
    current_job_id: Optional[str] = None
    uptime_seconds: float = 0.0
    last_heartbeat: Optional[datetime] = None
    avg_job_duration: float = 0.0
    total_job_duration: float = 0.0


class WorkerProcess:
    """A worker process that consumes jobs from the queue."""
    
    def __init__(
        self,
        worker_id: Optional[str] = None,
        redis_url: str = "redis://localhost:6379/0",
        db_path: Optional[str] = None,
        queues: Optional[List[str]] = None,
        heartbeat_interval: int = 10,
        graceful_shutdown_timeout: int = 30,
    ):
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self.redis_url = redis_url
        self.db_path = db_path
        self.queues = queues or ["high", "default", "low"]
        self.heartbeat_interval = heartbeat_interval
        self.graceful_shutdown_timeout = graceful_shutdown_timeout
        
        self._status = WorkerStatus.IDLE
        self._stats = WorkerStats(
            worker_id=self.worker_id,
            status=WorkerStatus.IDLE,
        )
        self._start_time = datetime.now()
        self._current_job: Optional[RQJob] = None
        self._stop_event = threading.Event()
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._db_connection: Optional[sqlite3.Connection] = None
        
        # Job hooks
        self._before_job: Optional[Callable] = None
        self._after_job: Optional[Callable] = None
        self._on_failure: Optional[Callable] = None
        
        logger.info(f"WorkerProcess {self.worker_id} initialized")
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        if self._db_connection is None:
            db_path = self.db_path or os.path.join(
                os.path.dirname(__file__), '..', 'data', 'virometrics.db'
            )
            self._db_connection = sqlite3.connect(db_path)
            self._db_connection.row_factory = sqlite3.Row
        return self._db_connection
    
    def _record_heartbeat(self):
        """Record heartbeat to database."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT OR REPLACE INTO worker_heartbeats
                   (worker_id, status, jobs_processed, jobs_failed, 
                    current_job_id, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    self._stats.worker_id,
                    self._stats.status.value,
                    self._stats.jobs_processed,
                    self._stats.jobs_failed,
                    self._stats.current_job_id,
                    datetime.now().isoformat(),
                )
            )
            conn.commit()
        except Exception as e:
            logger.error(f"Error recording heartbeat: {e}")
            conn.rollback()
    
    def _heartbeat_loop(self):
        """Background thread for heartbeat."""
        while not self._stop_event.is_set():
            self._record_heartbeat()
            self._stop_event.wait(self.heartbeat_interval)
    
    def _register_worker(self):
        """Register worker in database."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT OR REPLACE INTO workers
                   (worker_id, name, status, started_at, queues)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    self.worker_id,
                    f"{self.worker_id}",
                    WorkerStatus.RUNNING.value,
                    datetime.now().isoformat(),
                    ','.join(self.queues),
                )
            )
            conn.commit()
        except Exception as e:
            logger.error(f"Error registering worker: {e}")
            conn.rollback()
    
    def _unregister_worker(self):
        """Unregister worker from database."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE workers 
                   SET status = ?, last_heartbeat = ?
                   WHERE worker_id = ?""",
                (
                    WorkerStatus.STOPPED.value,
                    datetime.now().isoformat(),
                    self.worker_id,
                )
            )
            conn.commit()
        except Exception as e:
            logger.error(f"Error unregistering worker: {e}")
            conn.rollback()
    
    def _handle_job_started(self, job):
        """Handle job start event."""
        self._stats.status = WorkerStatus.RUNNING
        self._stats.current_job_id = job.id
        self._stats.last_heartbeat = datetime.now()
        
        logger.info(f"Worker {self.worker_id} starting job {job.id}")
        
        # Call before_job hook
        if self._before_job:
            try:
                self._before_job(job)
            except Exception as e:
                logger.error(f"Error in before_job hook: {e}")
    
    def _handle_job_finished(self, job):
        """Handle job completion event."""
        duration = (job.ended_at - job.started_at).total_seconds() if job.ended_at else 0
        
        self._stats.jobs_processed += 1
        self._stats.total_job_duration += duration
        self._stats.avg_job_duration = (
            self._stats.total_job_duration / self._stats.jobs_processed
            if self._stats.jobs_processed > 0 else 0
        )
        self._stats.current_job_id = None
        self._stats.status = WorkerStatus.IDLE
        
        logger.info(f"Worker {self.worker_id} completed job {job.id} in {duration:.2f}s")
        
        # Call after_job hook
        if self._after_job:
            try:
                self._after_job(job)
            except Exception as e:
                logger.error(f"Error in after_job hook: {e}")
    
    def _handle_job_failed(self, job, exception: Exception):
        """Handle job failure event."""
        self._stats.jobs_failed += 1
        self._stats.current_job_id = None
        self._stats.status = WorkerStatus.IDLE
        
        logger.error(f"Worker {self.worker_id} failed job {job.id}: {exception}")
        
        # Call on_failure hook
        if self._on_failure:
            try:
                self._on_failure(job, exception)
            except Exception as e:
                logger.error(f"Error in on_failure hook: {e}")
    
    def _get_rq_worker(self):
        """Get RQ Worker instance."""
        if not RQ_AVAILABLE:
            return None
        
        try:
            redis_conn = redis.from_url(self.redis_url)
            queues = [Queue(name, connection=redis_conn) for name in self.queues]
            return Worker(queues, name=self.worker_id, connection=redis_conn)
        except Exception as e:
            logger.error(f"Error creating RQ worker: {e}")
            return None
    
    def _execute_job(self, tool_id: int, command: str, working_dir: Optional[str],
                     env_vars: Optional[Dict[str, str]], timeout: int) -> Dict[str, Any]:
        """Execute a job - main work function."""
        job_id = str(uuid.uuid4())
        start_time = datetime.now()
        
        logger.info(f"Executing job {job_id}: {command}")
        
        result = {
            'job_id': job_id,
            'tool_id': tool_id,
            'command': command,
            'working_dir': working_dir,
            'status': 'completed',
            'start_time': start_time.isoformat(),
        }
        
        # Simulate execution
        try:
            time.sleep(min(timeout, 1))  # Simulate work
            result['end_time'] = datetime.now().isoformat()
            result['duration'] = (result['end_time'] - start_time).total_seconds()
        except Exception as e:
            result['status'] = 'failed'
            result['error'] = str(e)
            result['end_time'] = datetime.now().isoformat()
        
        return result
    
    def start(self, blocking: bool = True):
        """Start the worker."""
        self._status = WorkerStatus.RUNNING
        self._start_time = datetime.now()
        
        # Register worker
        self._register_worker()
        
        # Start heartbeat thread
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True,
        )
        self._heartbeat_thread.start()
        
        if RQ_AVAILABLE:
            rq_worker = self._get_rq_worker()
            if rq_worker:
                logger.info(f"Starting RQ worker {self.worker_id}")
                
                # Register job hooks
                rq_worker.register_job_decorator(
                    status=JobStatus.RUNNING,
                    on_started=self._handle_job_started,
                    on_finished=self._handle_job_finished,
                    on_failed=self._handle_job_failed,
                )
                
                if blocking:
                    rq_worker.work()
                else:
                    # Non-blocking mode - run in thread
                    self._worker_thread = threading.Thread(
                        target=rq_worker.work,
                        daemon=True,
                    )
                    self._worker_thread.start()
            else:
                logger.error("Failed to create RQ worker")
        else:
            logger.warning("Running in simulation mode (no RQ)")
    
    def stop(self, graceful: bool = True):
        """Stop the worker."""
        self._status = WorkerStatus.STOPPING
        self._stop_event.set()
        
        if graceful:
            logger.info(f"Waiting for graceful shutdown (timeout: {self.graceful_shutdown_timeout}s)")
            time.sleep(min(self.graceful_shutdown_timeout, 10))
        
        # Stop heartbeat thread
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=5)
        
        self._status = WorkerStatus.STOPPED
        self._unregister_worker()
        
        logger.info(f"Worker {self.worker_id} stopped")
    
    def pause(self):
        """Pause the worker."""
        self._status = WorkerStatus.PAUSED
        self._record_heartbeat()
        logger.info(f"Worker {self.worker_id} paused")
    
    def resume(self):
        """Resume the worker."""
        self._status = WorkerStatus.RUNNING
        self._record_heartbeat()
        logger.info(f"Worker {self.worker_id} resumed")
    
    def get_stats(self) -> WorkerStats:
        """Get worker statistics."""
        self._stats.uptime_seconds = (datetime.now() - self._start_time).total_seconds()
        return self._stats
    
    def set_hooks(
        self,
        before_job: Optional[Callable] = None,
        after_job: Optional[Callable] = None,
        on_failure: Optional[Callable] = None,
    ):
        """Set job lifecycle hooks."""
        self._before_job = before_job
        self._after_job = after_job
        self._on_failure = on_failure


class WorkerPool:
    """Manages a pool of worker processes."""
    
    def __init__(
        self,
        num_workers: int = 4,
        redis_url: str = "redis://localhost:6379/0",
        db_path: Optional[str] = None,
        queues: Optional[List[str]] = None,
    ):
        self.num_workers = num_workers
        self.redis_url = redis_url
        self.db_path = db_path
        self.queues = queues or ["high", "default", "low"]
        
        self._workers: List[WorkerProcess] = []
        self._threads: List[threading.Thread] = []
        self._running = False
    
    def start(self):
        """Start all workers in the pool."""
        logger.info(f"Starting worker pool with {self.num_workers} workers")
        
        for i in range(self.num_workers):
            worker_id = f"pool-worker-{i+1}"
            worker = WorkerProcess(
                worker_id=worker_id,
                redis_url=self.redis_url,
                db_path=self.db_path,
                queues=self.queues,
            )
            self._workers.append(worker)
            
            thread = threading.Thread(
                target=worker.start,
                args=(False,),  # Non-blocking
                daemon=True,
            )
            self._threads.append(thread)
            thread.start()
        
        self._running = True
        logger.info(f"Worker pool started with {len(self._workers)} workers")
    
    def stop(self, graceful: bool = True):
        """Stop all workers."""
        logger.info("Stopping worker pool...")
        self._running = False
        
        for worker in self._workers:
            worker.stop(graceful=graceful)
        
        # Wait for threads to finish
        for thread in self._threads:
            thread.join(timeout=10)
        
        logger.info("Worker pool stopped")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics for all workers."""
        return {
            'total_workers': len(self._workers),
            'running': sum(1 for w in self._workers if w._status == WorkerStatus.RUNNING),
            'idle': sum(1 for w in self._workers if w._status == WorkerStatus.IDLE),
            'paused': sum(1 for w in self._workers if w._status == WorkerStatus.PAUSED),
            'workers': [w.get_stats() for w in self._workers],
        }


# Default worker instances
_default_worker: Optional[WorkerProcess] = None


def get_default_worker() -> WorkerProcess:
    """Get or create the default worker instance."""
    global _default_worker
    if _default_worker is None:
        _default_worker = WorkerProcess()
    return _default_worker


def init_worker(
    worker_id: Optional[str] = None,
    redis_url: str = "redis://localhost:6379/0",
    db_path: Optional[str] = None,
    queues: Optional[List[str]] = None,
) -> WorkerProcess:
    """Initialize and return a worker instance."""
    worker = WorkerProcess(
        worker_id=worker_id,
        redis_url=redis_url,
        db_path=db_path,
        queues=queues,
    )
    return worker
