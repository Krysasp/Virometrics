"""Job queue engine for Virometrics platform.

Implements priority-based job queuing using Redis/RQ with support for
job dependencies, job groups, and metadata tracking.
"""

import json
import logging
import uuid
import time
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List, Set
from dataclasses import dataclass, field, asdict

try:
    import redis
    from rq import Queue, Job as RQJob, get_current_job
    from rq.job import JobStatus as RQJobStatus
    RQ_AVAILABLE = True
except ImportError:
    RQ_AVAILABLE = False
    logging.getLogger(__name__).warning("Redis/RQ not available, using in-memory queue")


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class JobPriority(Enum):
    """Job priority levels."""
    CRITICAL = 0
    HIGH = 1
    DEFAULT = 2
    LOW = 3
    BACKGROUND = 4


class JobStatus(Enum):
    """Job execution status."""
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    WAITING_DEPS = "waiting_deps"
    PARTIAL = "partial"


@dataclass
class Job:
    """Represents a job in the queue."""
    
    job_id: str
    tool_id: int
    command: str
    priority: JobPriority = JobPriority.DEFAULT
    status: JobStatus = JobStatus.PENDING
    working_dir: Optional[str] = None
    env_vars: Optional[Dict[str, str]] = None
    timeout: int = 3600
    metadata: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    group_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Any] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    worker_id: Optional[str] = None
    progress: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert job to dictionary."""
        return {
            'job_id': self.job_id,
            'tool_id': self.tool_id,
            'command': self.command,
            'priority': self.priority.name if self.priority else None,
            'priority_value': self.priority.value if self.priority else 999,
            'status': self.status.value if self.status else None,
            'working_dir': self.working_dir,
            'env_vars': self.env_vars,
            'timeout': self.timeout,
            'metadata': self.metadata,
            'dependencies': self.dependencies,
            'group_id': self.group_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'result': self.result,
            'error_message': self.error_message,
            'retry_count': self.retry_count,
            'max_retries': self.max_retries,
            'worker_id': self.worker_id,
            'progress': self.progress,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Job':
        """Create job from dictionary."""
        # Parse priority
        if isinstance(data.get('priority'), str):
            priority = JobPriority[data['priority']]
        else:
            priority = JobPriority(data.get('priority_value', 2))
        
        # Parse status
        if isinstance(data.get('status'), str):
            status = JobStatus(data['status'])
        else:
            status = JobStatus.PENDING
        
        # Parse datetime fields
        def parse_dt(dt_str):
            return datetime.fromisoformat(dt_str) if dt_str else None
        
        return cls(
            job_id=data['job_id'],
            tool_id=data['tool_id'],
            command=data['command'],
            priority=priority,
            status=status,
            working_dir=data.get('working_dir'),
            env_vars=data.get('env_vars'),
            timeout=data.get('timeout', 3600),
            metadata=data.get('metadata', {}),
            dependencies=data.get('dependencies', []),
            group_id=data.get('group_id'),
            created_at=parse_dt(data.get('created_at')),
            started_at=parse_dt(data.get('started_at')),
            completed_at=parse_dt(data.get('completed_at')),
            result=data.get('result'),
            error_message=data.get('error_message'),
            retry_count=data.get('retry_count', 0),
            max_retries=data.get('max_retries', 3),
            worker_id=data.get('worker_id'),
            progress=data.get('progress', 0.0),
        )


class JobGroup:
    """Represents a group of related jobs."""
    
    def __init__(
        self,
        group_id: str,
        name: str,
        jobs: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        created_at: Optional[datetime] = None
    ):
        self.group_id = group_id
        self.name = name
        self.job_ids = jobs or []
        self.metadata = metadata or {}
        self.created_at = created_at or datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert group to dictionary."""
        return {
            'group_id': self.group_id,
            'name': self.name,
            'job_ids': self.job_ids,
            'job_count': len(self.job_ids),
            'metadata': self.metadata,
            'created_at': self.created_at.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'JobGroup':
        """Create group from dictionary."""
        return cls(
            group_id=data['group_id'],
            name=data['name'],
            jobs=data.get('job_ids', []),
            metadata=data.get('metadata', {}),
            created_at=datetime.fromisoformat(data.get('created_at')) if data.get('created_at') else None,
        )


class QueueManager:
    """Manages job queue operations."""
    
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        db_path: Optional[str] = None,
        default_timeout: int = 3600,
        max_jobs_in_memory: int = 10000
    ):
        self.redis_url = redis_url
        self.db_path = db_path
        self.default_timeout = default_timeout
        self.max_jobs_in_memory = max_jobs_in_memory
        
        # Initialize queues by priority
        self.queues = {
            JobPriority.CRITICAL: Queue("critical", connection=self._get_redis()) if RQ_AVAILABLE else [],
            JobPriority.HIGH: Queue("high", connection=self._get_redis()) if RQ_AVAILABLE else [],
            JobPriority.DEFAULT: Queue("default", connection=self._get_redis()) if RQ_AVAILABLE else [],
            JobPriority.LOW: Queue("low", connection=self._get_redis()) if RQ_AVAILABLE else [],
            JobPriority.BACKGROUND: Queue("background", connection=self._get_redis()) if RQ_AVAILABLE else [],
        }
        
        # In-memory storage for job metadata
        self._job_registry: Dict[str, Job] = {}
        self._group_registry: Dict[str, JobGroup] = {}
        
        logger.info(f"QueueManager initialized with Redis URL: {redis_url}")
    
    def _get_redis(self):
        """Get Redis connection."""
        if not RQ_AVAILABLE:
            return None
        try:
            return redis.from_url(self.redis_url)
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}")
            return None
    
    def submit_job(
        self,
        tool_id: int,
        command: str,
        priority: JobPriority = JobPriority.DEFAULT,
        working_dir: Optional[str] = None,
        env_vars: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
        dependencies: Optional[List[str]] = None,
        group_id: Optional[str] = None,
    ) -> Job:
        """Submit a new job to the queue."""
        job_id = str(uuid.uuid4())
        
        job = Job(
            job_id=job_id,
            tool_id=tool_id,
            command=command,
            priority=priority,
            working_dir=working_dir,
            env_vars=env_vars,
            timeout=timeout or self.default_timeout,
            metadata=metadata or {},
            dependencies=dependencies or [],
            group_id=group_id,
        )
        
        # Check dependencies
        if job.dependencies:
            job.status = JobStatus.WAITING_DEPS
        
        # Store job metadata
        self._job_registry[job_id] = job
        
        # Add to group if specified
        if group_id:
            self._add_job_to_group(group_id, job_id)
        
        # Enqueue job
        if RQ_AVAILABLE:
            queue = self.queues.get(priority, self.queues[JobPriority.DEFAULT])
            
            # Define the work function
            def execute_job(job_job, tool_id, command, working_dir, env_vars, timeout):
                return {
                    'job_id': job_job.id,
                    'tool_id': tool_id,
                    'command': command,
                    'working_dir': working_dir,
                    'env_vars': env_vars,
                    'status': 'completed',
                }
            
            # Create job with dependencies
            if job.dependencies:
                rq_jobs = [
                    RQJob(id=dep_id, connection=queue.connection)
                    for dep_id in job.dependencies
                ]
                rq_job = queue.enqueue(
                    execute_job,
                    tool_id,
                    command,
                    working_dir,
                    env_vars,
                    timeout,
                    depends_on=rq_jobs,
                    job_id=job_id,
                    timeout=timeout,
                )
            else:
                rq_job = queue.enqueue(
                    execute_job,
                    tool_id,
                    command,
                    working_dir,
                    env_vars,
                    timeout,
                    job_id=job_id,
                    timeout=timeout,
                )
            
            job.status = JobStatus.QUEUED
            logger.info(f"Job {job_id} queued with priority {priority.name}")
        else:
            # In-memory queue
            self.queues[priority].append(job)
            job.status = JobStatus.QUEUED
            logger.info(f"Job {job_id} queued in memory with priority {priority.name}")
        
        return job
    
    def submit_job_group(
        self,
        name: str,
        jobs: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
        depends_on: Optional[List[str]] = None,
    ) -> JobGroup:
        """Submit a group of jobs."""
        group_id = str(uuid.uuid4())
        
        group = JobGroup(
            group_id=group_id,
            name=name,
            metadata=metadata or {},
        )
        
        # Create jobs in sequence with dependencies
        created_jobs = []
        for i, job_data in enumerate(jobs):
            dependencies = [job_data.get('job_id')] if job_data.get('job_id') else []
            if depends_on:
                dependencies.extend(dep for dep in depends_on if dep not in dependencies)
            
            # Add dependency on previous job in group for sequential execution
            if i > 0 and jobs[i-1].get('sequential', True):
                dependencies.append(created_jobs[-1].job_id)
            
            job = self.submit_job(
                tool_id=job_data['tool_id'],
                command=job_data['command'],
                priority=JobPriority[job_data.get('priority', 'DEFAULT')] if isinstance(job_data.get('priority'), str) else JobPriority(job_data.get('priority', 2)),
                working_dir=job_data.get('working_dir'),
                env_vars=job_data.get('env_vars'),
                timeout=job_data.get('timeout'),
                metadata=job_data.get('metadata'),
                dependencies=dependencies,
                group_id=group_id,
            )
            created_jobs.append(job)
        
        self._group_registry[group_id] = group
        logger.info(f"Job group {group_id} '{name}' created with {len(created_jobs)} jobs")
        
        return group
    
    def get_job(self, job_id: str) -> Optional[Job]:
        """Get job by ID."""
        if job_id in self._job_registry:
            return self._job_registry[job_id]
        
        if RQ_AVAILABLE:
            try:
                redis_conn = self._get_redis()
                if redis_conn:
                    rq_job = RQJob.fetch(job_id, connection=redis_conn)
                    # Update our registry
                    job = self._job_registry.get(job_id)
                    if job:
                        job.status = JobStatus(rq_job.status)
                        job.result = rq_job.result
                        job.started_at = rq_job.started_at
                        job.completed_at = rq_job.ended_at
            except Exception:
                pass
        
        return self._job_registry.get(job_id)
    
    def list_jobs(
        self,
        status: Optional[JobStatus] = None,
        priority: Optional[JobPriority] = None,
        group_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Job]:
        """List jobs with optional filters."""
        jobs = list(self._job_registry.values())
        
        if status:
            jobs = [j for j in jobs if j.status == status]
        
        if priority:
            jobs = [j for j in jobs if j.priority == priority]
        
        if group_id:
            jobs = [j for j in jobs if j.group_id == group_id]
        
        # Sort by priority and created_at
        jobs.sort(key=lambda j: (j.priority.value, j.created_at))
        
        return jobs[offset:offset + limit]
    
    def cancel_job(self, job_id: str) -> bool:
        """Cancel a job."""
        job = self.get_job(job_id)
        if not job:
            return False
        
        if job.status in (JobStatus.PENDING, JobStatus.QUEUED, JobStatus.WAITING_DEPS):
            job.status = JobStatus.CANCELLED
            job.completed_at = datetime.now()
            
            if RQ_AVAILABLE:
                try:
                    redis_conn = self._get_redis()
                    if redis_conn:
                        rq_job = RQJob.fetch(job_id, connection=redis_conn)
                        rq_job.cancel()
                except Exception:
                    pass
            
            logger.info(f"Job {job_id} cancelled")
            return True
        
        logger.warning(f"Cannot cancel job {job_id} in status {job.status}")
        return False
    
    def get_queue_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        stats = {
            'queues': {},
            'total_jobs': len(self._job_registry),
            'by_status': {},
            'by_priority': {},
        }
        
        for priority, queue in self.queues.items():
            if RQ_AVAILABLE:
                stats['queues'][priority.name] = {
                    'queued': len(queue),
                    'scheduled': len(queue.scheduled_jobs),
                }
        
        # Count by status
        for job in self._job_registry.values():
            status_key = job.status.value
            stats['by_status'][status_key] = stats['by_status'].get(status_key, 0) + 1
            
            priority_key = job.priority.name if job.priority else 'UNKNOWN'
            stats['by_priority'][priority_key] = stats['by_priority'].get(priority_key, 0) + 1
        
        return stats
    
    def _add_job_to_group(self, group_id: str, job_id: str):
        """Add job ID to a group."""
        if group_id not in self._group_registry:
            self._group_registry[group_id] = JobGroup(
                group_id=group_id,
                name=f"Group {group_id[:8]}",
            )
        self._group_registry[group_id].job_ids.append(job_id)
    
    def get_group(self, group_id: str) -> Optional[JobGroup]:
        """Get job group by ID."""
        return self._group_registry.get(group_id)
    
    def get_group_jobs(self, group_id: str) -> List[Job]:
        """Get all jobs in a group."""
        group = self.get_group(group_id)
        if not group:
            return []
        return [self.get_job(jid) for jid in group.job_ids if self.get_job(jid)]
    
    def get_group_stats(self, group_id: str) -> Dict[str, Any]:
        """Get statistics for a job group."""
        jobs = self.get_group_jobs(group_id)
        if not jobs:
            return {'group_id': group_id, 'total_jobs': 0}
        
        stats = {
            'group_id': group_id,
            'total_jobs': len(jobs),
            'completed': sum(1 for j in jobs if j.status == JobStatus.COMPLETED),
            'failed': sum(1 for j in jobs if j.status == JobStatus.FAILED),
            'running': sum(1 for j in jobs if j.status == JobStatus.RUNNING),
            'pending': sum(1 for j in jobs if j.status in (JobStatus.PENDING, JobStatus.QUEUED)),
            'average_progress': sum(j.progress for j in jobs) / len(jobs),
        }
        return stats
    
    def cleanup(self, max_age_hours: int = 24):
        """Clean up old job metadata."""
        cutoff = datetime.now().timestamp() - (max_age_hours * 3600)
        to_remove = []
        
        for job_id, job in self._job_registry.items():
            if job.completed_at and job.completed_at.timestamp() < cutoff:
                to_remove.append(job_id)
        
        for job_id in to_remove:
            del self._job_registry[job_id]
        
        logger.info(f"Cleaned up {len(to_remove)} old job records")
        return len(to_remove)
