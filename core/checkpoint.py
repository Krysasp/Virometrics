"""Checkpointing support for Virometrics job execution.

Saves intermediate results for long-running jobs and supports checkpoint
recovery with configurable checkpoint intervals.
"""

import os
import sys
import json
import uuid
import time
import hashlib
import sqlite3
import logging
import threading
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CheckpointStatus(Enum):
    """Checkpoint status."""
    PENDING = "pending"
    SAVED = "saved"
    RESTORED = "restored"
    FAILED = "failed"


@dataclass
class Checkpoint:
    """Represents a checkpoint for a job."""
    
    checkpoint_id: str
    execution_id: int
    sequence: int
    timestamp: datetime
    data: Dict[str, Any]
    checksum: Optional[str] = None
    size_bytes: int = 0
    status: CheckpointStatus = CheckpointStatus.PENDING
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert checkpoint to dictionary."""
        return {
            'checkpoint_id': self.checkpoint_id,
            'execution_id': self.execution_id,
            'sequence': self.sequence,
            'timestamp': self.timestamp.isoformat(),
            'data': self.data,
            'checksum': self.checksum,
            'size_bytes': self.size_bytes,
            'status': self.status.value,
            'metadata': self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Checkpoint':
        """Create checkpoint from dictionary."""
        return cls(
            checkpoint_id=data['checkpoint_id'],
            execution_id=data['execution_id'],
            sequence=data['sequence'],
            timestamp=datetime.fromisoformat(data['timestamp']),
            data=data.get('data', {}),
            checksum=data.get('checksum'),
            size_bytes=data.get('size_bytes', 0),
            status=CheckpointStatus(data.get('status', 'pending')),
            metadata=data.get('metadata', {}),
        )


class CheckpointManager:
    """Manages checkpoints for job execution."""
    
    def __init__(
        self,
        db_path: Optional[str] = None,
        checkpoint_dir: Optional[str] = None,
        auto_save: bool = True,
        max_checkpoints: int = 10,
    ):
        self.db_path = db_path or os.path.join(
            os.path.dirname(__file__), '..', 'data', 'virometrics.db'
        )
        self.checkpoint_dir = checkpoint_dir or os.path.join(
            os.path.dirname(self.db_path), 'checkpoints'
        )
        self.auto_save = auto_save
        self.max_checkpoints = max_checkpoints
        
        # In-memory checkpoint cache
        self._cache: Dict[int, List[Checkpoint]] = {}
        self._lock = threading.Lock()
        
        # Ensure checkpoint directory exists
        os.makedirs(self.checkpoint_dir, exist_ok=True)
        
        logger.info(f"CheckpointManager initialized with dir: {self.checkpoint_dir}")
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn
    
    def _compute_checksum(self, data: Dict[str, Any]) -> str:
        """Compute checksum for data."""
        json_str = json.dumps(data, sort_keys=True)
        return hashlib.md5(json_str.encode()).hexdigest()
    
    def create_checkpoint(
        self,
        execution_id: int,
        data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Checkpoint:
        """Create a new checkpoint for an execution."""
        # Get sequence number
        with self._lock:
            if execution_id not in self._cache:
                self._cache[execution_id] = []
            sequence = len(self._cache[execution_id]) + 1
        
        checkpoint_id = str(uuid.uuid4())
        
        # Compute checksum
        checksum = self._compute_checksum(data)
        
        # Estimate size
        size_bytes = len(json.dumps(data).encode())
        
        checkpoint = Checkpoint(
            checkpoint_id=checkpoint_id,
            execution_id=execution_id,
            sequence=sequence,
            timestamp=datetime.now(),
            data=data,
            checksum=checksum,
            size_bytes=size_bytes,
            status=CheckpointStatus.PENDING,
            metadata=metadata or {},
        )
        
        # Save to database
        self._save_to_db(checkpoint)
        
        # Save to file if auto_save is enabled
        if self.auto_save:
            self._save_to_file(checkpoint)
        
        # Update status
        checkpoint.status = CheckpointStatus.SAVED
        
        # Add to cache
        with self._lock:
            self._cache[execution_id].append(checkpoint)
            
            # Enforce max checkpoints
            if len(self._cache[execution_id]) > self.max_checkpoints:
                old_checkpoint = self._cache[execution_id].pop(0)
                self._prune_file(old_checkpoint)
                logger.debug(f"Pruned old checkpoint {old_checkpoint.checkpoint_id}")
        
        logger.info(
            f"Created checkpoint {checkpoint_id} for execution {execution_id} "
            f"(sequence: {sequence}, size: {size_bytes} bytes)"
        )
        
        return checkpoint
    
    def _save_to_db(self, checkpoint: Checkpoint):
        """Save checkpoint to database."""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Insert main checkpoint record
            cursor.execute(
                """INSERT INTO checkpoints
                   (checkpoint_id, execution_id, sequence, timestamp, 
                    checksum, size_bytes, status, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    checkpoint.checkpoint_id,
                    checkpoint.execution_id,
                    checkpoint.sequence,
                    checkpoint.timestamp.isoformat(),
                    checkpoint.checksum,
                    checkpoint.size_bytes,
                    checkpoint.status.value,
                    json.dumps(checkpoint.metadata),
                )
            )
            
            # Insert checkpoint data
            cursor.execute(
                """INSERT INTO checkpoint_data
                   (checkpoint_id, data)
                   VALUES (?, ?)""",
                (checkpoint.checkpoint_id, json.dumps(checkpoint.data))
            )
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error saving checkpoint to DB: {e}")
            conn.rollback()
            conn.close()
            raise
    
    def _save_to_file(self, checkpoint: Checkpoint):
        """Save checkpoint to file."""
        try:
            # Create subdirectory for execution
            exec_dir = os.path.join(self.checkpoint_dir, str(checkpoint.execution_id))
            os.makedirs(exec_dir, exist_ok=True)
            
            # Save checkpoint file
            file_path = os.path.join(
                exec_dir,
                f"checkpoint_{checkpoint.sequence:04d}.json"
            )
            
            with open(file_path, 'w') as f:
                json.dump(checkpoint.to_dict(), f, indent=2)
            
            logger.debug(f"Saved checkpoint to {file_path}")
            
        except Exception as e:
            logger.error(f"Error saving checkpoint to file: {e}")
    
    def _prune_file(self, checkpoint: Checkpoint):
        """Remove old checkpoint file."""
        try:
            file_path = os.path.join(
                self.checkpoint_dir,
                str(checkpoint.execution_id),
                f"checkpoint_{checkpoint.sequence:04d}.json"
            )
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.debug(f"Pruned checkpoint file: {file_path}")
        except Exception as e:
            logger.debug(f"Error pruning checkpoint file: {e}")
    
    def get_checkpoints(self, execution_id: int) -> List[Checkpoint]:
        """Get all checkpoints for an execution."""
        # Check cache first
        with self._lock:
            if execution_id in self._cache:
                return list(self._cache[execution_id])
        
        # Load from database
        checkpoints = []
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute(
                """SELECT c.*, cd.data
                   FROM checkpoints c
                   JOIN checkpoint_data cd ON c.checkpoint_id = cd.checkpoint_id
                   WHERE c.execution_id = ?
                   ORDER BY c.sequence ASC""",
                (execution_id,)
            )
            
            for row in cursor.fetchall():
                checkpoint = Checkpoint(
                    checkpoint_id=row['checkpoint_id'],
                    execution_id=row['execution_id'],
                    sequence=row['sequence'],
                    timestamp=datetime.fromisoformat(row['timestamp']),
                    data=json.loads(row['data']),
                    checksum=row['checksum'],
                    size_bytes=row['size_bytes'],
                    status=CheckpointStatus(row['status']),
                    metadata=json.loads(row['metadata']) if row['metadata'] else {},
                )
                checkpoints.append(checkpoint)
            
            # Update cache
            with self._lock:
                self._cache[execution_id] = checkpoints
            
            conn.close()
            
        except Exception as e:
            logger.error(f"Error loading checkpoints: {e}")
        
        return checkpoints
    
    def get_latest_checkpoint(self, execution_id: int) -> Optional[Checkpoint]:
        """Get the latest checkpoint for an execution."""
        checkpoints = self.get_checkpoints(execution_id)
        return checkpoints[-1] if checkpoints else None
    
    def get_checkpoint(self, execution_id: int, sequence: int) -> Optional[Checkpoint]:
        """Get a specific checkpoint by sequence number."""
        checkpoints = self.get_checkpoints(execution_id)
        for checkpoint in checkpoints:
            if checkpoint.sequence == sequence:
                return checkpoint
        return None
    
    def restore_from_checkpoint(
        self,
        execution_id: int,
        sequence: Optional[int] = None,
        checkpoint_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Restore state from a checkpoint."""
        # Determine which checkpoint to restore
        if checkpoint_id:
            # Find checkpoint by ID
            checkpoints = self.get_checkpoints(execution_id)
            for checkpoint in checkpoints:
                if checkpoint.checkpoint_id == checkpoint_id:
                    break
            else:
                logger.warning(f"Checkpoint {checkpoint_id} not found")
                return None
        elif sequence:
            checkpoint = self.get_checkpoint(execution_id, sequence)
            if not checkpoint:
                logger.warning(f"Checkpoint with sequence {sequence} not found")
                return None
        else:
            # Use latest
            checkpoint = self.get_latest_checkpoint(execution_id)
            if not checkpoint:
                logger.warning(f"No checkpoints found for execution {execution_id}")
                return None
        
        # Update status
        checkpoint.status = CheckpointStatus.RESTORED
        
        # Save status to database
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE checkpoints SET status = ? WHERE checkpoint_id = ?""",
                (CheckpointStatus.RESTORED.value, checkpoint.checkpoint_id)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error updating checkpoint status: {e}")
        
        logger.info(
            f"Restored from checkpoint {checkpoint.checkpoint_id} "
            f"(sequence: {checkpoint.sequence})"
        )
        
        return checkpoint.data
    
    def delete_checkpoints(
        self,
        execution_id: int,
        keep_last: int = 1,
    ) -> int:
        """Delete old checkpoints, keeping the most recent ones."""
        checkpoints = self.get_checkpoints(execution_id)
        
        if len(checkpoints) <= keep_last:
            return 0
        
        to_delete = checkpoints[:-keep_last]
        deleted = 0
        
        for checkpoint in to_delete:
            try:
                conn = self._get_connection()
                cursor = conn.cursor()
                
                cursor.execute(
                    "DELETE FROM checkpoint_data WHERE checkpoint_id = ?",
                    (checkpoint.checkpoint_id,)
                )
                cursor.execute(
                    "DELETE FROM checkpoints WHERE checkpoint_id = ?",
                    (checkpoint.checkpoint_id,)
                )
                conn.commit()
                conn.close()
                
                # Remove file
                self._prune_file(checkpoint)
                
                deleted += 1
            except Exception as e:
                logger.error(f"Error deleting checkpoint {checkpoint.checkpoint_id}: {e}")
        
        # Update cache
        with self._lock:
            if execution_id in self._cache:
                self._cache[execution_id] = self._cache[execution_id][-keep_last:]
        
        logger.info(f"Deleted {deleted} old checkpoints for execution {execution_id}")
        return deleted
    
    def cleanup_old_executions(self, max_age_days: int = 7) -> int:
        """Clean up checkpoints for old executions."""
        cutoff = datetime.now().timestamp() - (max_age_days * 86400)
        
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute(
                """SELECT DISTINCT execution_id FROM checkpoints
                   WHERE timestamp < datetime('now', ?)""",
                (f'-{max_age_days} days',)
            )
            
            old_executions = [row['execution_id'] for row in cursor.fetchall()]
            deleted = 0
            
            for exec_id in old_executions:
                deleted += self.delete_checkpoints(exec_id, keep_last=1)
            
            conn.close()
            logger.info(f"Cleaned up checkpoints for {len(old_executions)} old executions")
            return deleted
            
        except Exception as e:
            logger.error(f"Error cleaning up old checkpoints: {e}")
            return 0


class CheckpointedExecutor:
    """Executor that supports automatic checkpointing."""
    
    def __init__(
        self,
        checkpoint_manager: Optional[CheckpointManager] = None,
        checkpoint_interval: int = 300,
        checkpoint_on_progress: bool = True,
    ):
        self.checkpoint_manager = checkpoint_manager or CheckpointManager()
        self.checkpoint_interval = checkpoint_interval
        self.checkpoint_on_progress = checkpoint_on_progress
        
        self._execution_data: Dict[int, Dict[str, Any]] = {}
        self._last_checkpoint_time: Dict[int, datetime] = {}
        self._progress_callbacks: List[Callable] = []
    
    def register_progress_callback(self, callback: Callable):
        """Register a callback for progress updates."""
        self._progress_callbacks.append(callback)
    
    def update_progress(
        self,
        execution_id: int,
        progress: float,
        data: Optional[Dict[str, Any]] = None,
    ):
        """Update progress and optionally checkpoint."""
        # Store execution data
        if execution_id not in self._execution_data:
            self._execution_data[execution_id] = {}
        
        self._execution_data[execution_id]['progress'] = progress
        if data:
            self._execution_data[execution_id].update(data)
        
        # Call progress callbacks
        for callback in self._progress_callbacks:
            try:
                callback(execution_id, progress, data)
            except Exception as e:
                logger.debug(f"Error in progress callback: {e}")
        
        # Check if we should checkpoint
        if self.checkpoint_on_progress:
            now = datetime.now()
            last_time = self._last_checkpoint_time.get(execution_id)
            
            if last_time is None or (now - last_time).total_seconds() >= self.checkpoint_interval:
                self.checkpoint(execution_id)
                self._last_checkpoint_time[execution_id] = now
    
    def checkpoint(self, execution_id: int) -> Checkpoint:
        """Create a checkpoint for an execution."""
        data = self._execution_data.get(execution_id, {}).copy()
        data['execution_id'] = execution_id
        
        return self.checkpoint_manager.create_checkpoint(
            execution_id=execution_id,
            data=data,
            metadata={'auto': True},
        )
    
    def restore(self, execution_id: int) -> Optional[Dict[str, Any]]:
        """Restore execution state from checkpoint."""
        data = self.checkpoint_manager.restore_from_checkpoint(execution_id)
        if data:
            self._execution_data[execution_id] = data
        return data


# Default checkpoint manager instance
_default_manager: Optional[CheckpointManager] = None


def get_default_checkpoint_manager() -> CheckpointManager:
    """Get or create the default checkpoint manager."""
    global _default_manager
    if _default_manager is None:
        _default_manager = CheckpointManager()
    return _default_manager


def init_checkpoint_manager(
    db_path: Optional[str] = None,
    checkpoint_dir: Optional[str] = None,
    max_checkpoints: int = 10,
) -> CheckpointManager:
    """Initialize and return a checkpoint manager."""
    return CheckpointManager(
        db_path=db_path,
        checkpoint_dir=checkpoint_dir,
        max_checkpoints=max_checkpoints,
    )
