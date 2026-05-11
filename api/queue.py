"""Job Queue API endpoints for Virometrics platform."""

import json
import logging
from typing import Optional
from flask import Blueprint, request, jsonify, current_app
from datetime import datetime

from core.job_queue import (
    QueueManager,
    Job,
    JobPriority,
    JobStatus,
    JobGroup,
)

logger = logging.getLogger(__name__)

bp = Blueprint('queue', __name__, url_prefix='/api')

# Global queue manager instance
_queue_manager: Optional[QueueManager] = None


def init_queue_manager(db_path: str, redis_url: str = None):
    """Initialize the queue manager."""
    global _queue_manager
    _queue_manager = QueueManager(
        redis_url=redis_url or "redis://localhost:6379/0",
        db_path=db_path,
    )
    logger.info(f"QueueManager initialized with Redis URL: {_queue_manager.redis_url}")
    return _queue_manager


def get_queue_manager() -> QueueManager:
    """Get the queue manager instance."""
    global _queue_manager
    if _queue_manager is None:
        # Lazy initialization
        db_path = current_app.config.get('DATABASE_PATH', 'data/virometrics.db')
        redis_url = current_app.config.get('REDIS_URL', 'redis://localhost:6379/0')
        _queue_manager = QueueManager(redis_url=redis_url, db_path=db_path)
    return _queue_manager


@bp.route('/jobs', methods=['POST'])
def submit_job():
    """Submit a new job to the queue."""
    try:
        data = request.get_json(silent=True) or {}
        
        # Required fields
        tool_id = data.get('tool_id')
        command = data.get('command')
        
        if not tool_id:
            return jsonify({'error': 'tool_id is required'}), 400
        
        if not command:
            return jsonify({'error': 'command is required'}), 400
        
        # Optional fields
        priority_str = data.get('priority', 'DEFAULT')
        try:
            priority = JobPriority[priority_str.upper()]
        except KeyError:
            priority = JobPriority.DEFAULT
        
        working_dir = data.get('working_dir')
        env_vars = data.get('env_vars')
        timeout = data.get('timeout', 3600)
        metadata = data.get('metadata', {})
        dependencies = data.get('dependencies', [])
        group_id = data.get('group_id')
        
        # Submit job
        queue_mgr = get_queue_manager()
        job = queue_mgr.submit_job(
            tool_id=tool_id,
            command=command,
            priority=priority,
            working_dir=working_dir,
            env_vars=env_vars,
            timeout=timeout,
            metadata=metadata,
            dependencies=dependencies,
            group_id=group_id,
        )
        
        return jsonify({
            'job_id': job.job_id,
            'status': job.status.value,
            'priority': job.priority.name,
            'message': 'Job submitted successfully',
            'estimated_queue_position': len(queue_mgr.list_jobs(status=JobStatus.QUEUED)),
        }), 201
    
    except Exception as e:
        logger.error(f"Error submitting job: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/jobs', methods=['GET'])
def list_jobs():
    """List all jobs with optional filters."""
    try:
        # Query parameters
        status_str = request.args.get('status')
        priority_str = request.args.get('priority')
        group_id = request.args.get('group_id')
        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        # Parse status filter
        status = None
        if status_str:
            try:
                status = JobStatus[status_str.upper()]
            except KeyError:
                pass
        
        # Parse priority filter
        priority = None
        if priority_str:
            try:
                priority = JobPriority[priority_str.upper()]
            except KeyError:
                pass
        
        # Get jobs
        queue_mgr = get_queue_manager()
        jobs = queue_mgr.list_jobs(
            status=status,
            priority=priority,
            group_id=group_id,
            limit=limit,
            offset=offset,
        )
        
        return jsonify({
            'jobs': [job.to_dict() for job in jobs],
            'total': len(jobs),
            'limit': limit,
            'offset': offset,
            'filters': {
                'status': status_str,
                'priority': priority_str,
                'group_id': group_id,
            },
        })
    
    except Exception as e:
        logger.error(f"Error listing jobs: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/jobs/<job_id>', methods=['GET'])
def get_job(job_id: str):
    """Get job status and details."""
    try:
        queue_mgr = get_queue_manager()
        job = queue_mgr.get_job(job_id)
        
        if not job:
            return jsonify({
                'error': 'Job not found',
                'job_id': job_id,
            }), 404
        
        return jsonify({
            'job': job.to_dict(),
        })
    
    except Exception as e:
        logger.error(f"Error getting job {job_id}: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/jobs/<job_id>', methods=['DELETE'])
def cancel_job(job_id: str):
    """Cancel a job."""
    try:
        queue_mgr = get_queue_manager()
        success = queue_mgr.cancel_job(job_id)
        
        if success:
            return jsonify({
                'message': 'Job cancelled successfully',
                'job_id': job_id,
            })
        else:
            return jsonify({
                'error': 'Could not cancel job',
                'job_id': job_id,
                'reason': 'Job not in cancellable state',
            }), 400
    
    except Exception as e:
        logger.error(f"Error cancelling job {job_id}: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/jobs/<job_id>/retry', methods=['POST'])
def retry_job(job_id: str):
    """Retry a failed job."""
    try:
        data = request.get_json(silent=True) or {}
        queue_mgr = get_queue_manager()
        
        job = queue_mgr.get_job(job_id)
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
        if job.status != JobStatus.FAILED:
            return jsonify({'error': 'Job not in failed state'}), 400
        
        # Increment retry count
        if job.retry_count >= job.max_retries:
            return jsonify({
                'error': 'Max retries exceeded',
                'retry_count': job.retry_count,
                'max_retries': job.max_retries,
            }), 400
        
        # Resubmit job
        new_job = queue_mgr.submit_job(
            tool_id=job.tool_id,
            command=job.command,
            priority=job.priority,
            working_dir=job.working_dir,
            env_vars=job.env_vars,
            timeout=job.timeout,
            metadata=job.metadata,
            group_id=job.group_id,
        )
        
        # Update retry count
        job.retry_count += 1
        
        return jsonify({
            'message': 'Job retried successfully',
            'original_job_id': job_id,
            'new_job_id': new_job.job_id,
            'retry_count': job.retry_count,
        })
    
    except Exception as e:
        logger.error(f"Error retrying job {job_id}: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/jobs/group', methods=['POST'])
def submit_job_group():
    """Submit a group of jobs."""
    try:
        data = request.get_json(silent=True) or {}
        
        name = data.get('name', f"Group {datetime.now().isoformat()}")
        jobs = data.get('jobs', [])
        metadata = data.get('metadata', {})
        depends_on = data.get('depends_on', [])
        
        if not jobs:
            return jsonify({'error': 'jobs list is required'}), 400
        
        queue_mgr = get_queue_manager()
        group = queue_mgr.submit_job_group(
            name=name,
            jobs=jobs,
            metadata=metadata,
            depends_on=depends_on,
        )
        
        return jsonify({
            'group_id': group.group_id,
            'name': group.name,
            'job_count': len(group.job_ids),
            'job_ids': group.job_ids,
            'message': 'Job group submitted successfully',
        }), 201
    
    except Exception as e:
        logger.error(f"Error submitting job group: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/jobs/group/<group_id>', methods=['GET'])
def get_job_group(group_id: str):
    """Get job group details."""
    try:
        queue_mgr = get_queue_manager()
        
        group = queue_mgr.get_group(group_id)
        if not group:
            return jsonify({'error': 'Group not found', 'group_id': group_id}), 404
        
        stats = queue_mgr.get_group_stats(group_id)
        jobs = queue_mgr.get_group_jobs(group_id)
        
        return jsonify({
            'group': group.to_dict(),
            'stats': stats,
            'jobs': [job.to_dict() for job in jobs],
        })
    
    except Exception as e:
        logger.error(f"Error getting job group {group_id}: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/queues/stats', methods=['GET'])
def get_queue_stats():
    """Get queue statistics."""
    try:
        queue_mgr = get_queue_manager()
        stats = queue_mgr.get_queue_stats()
        
        return jsonify({
            'queues': stats['queues'],
            'total_jobs': stats['total_jobs'],
            'by_status': stats['by_status'],
            'by_priority': stats['by_priority'],
            'timestamp': datetime.now().isoformat(),
        })
    
    except Exception as e:
        logger.error(f"Error getting queue stats: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/queues/cleanup', methods=['POST'])
def cleanup_old_jobs():
    """Clean up old job metadata."""
    try:
        data = request.get_json(silent=True) or {}
        max_age_hours = data.get('max_age_hours', 24)
        
        queue_mgr = get_queue_manager()
        cleaned = queue_mgr.cleanup(max_age_hours=max_age_hours)
        
        return jsonify({
            'message': f'Cleaned up {cleaned} old job records',
            'cleaned_count': cleaned,
            'max_age_hours': max_age_hours,
        })
    
    except Exception as e:
        logger.error(f"Error cleaning up jobs: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/queues/priority/<job_id>', methods=['PUT'])
def update_job_priority(job_id: str):
    """Update job priority."""
    try:
        data = request.get_json(silent=True) or {}
        priority_str = data.get('priority', 'DEFAULT')
        
        try:
            new_priority = JobPriority[priority_str.upper()]
        except KeyError:
            return jsonify({'error': f'Invalid priority: {priority_str}'}), 400
        
        queue_mgr = get_queue_manager()
        job = queue_mgr.get_job(job_id)
        
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
        old_priority = job.priority
        job.priority = new_priority
        
        return jsonify({
            'message': 'Job priority updated',
            'job_id': job_id,
            'old_priority': old_priority.name,
            'new_priority': new_priority.name,
        })
    
    except Exception as e:
        logger.error(f"Error updating job priority: {e}")
        return jsonify({'error': str(e)}), 500
