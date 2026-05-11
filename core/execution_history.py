"""Execution history and audit trail for Virometrics platform.

Provides detailed tracking of all tool and workflow executions.
"""

import os
import sqlite3
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from enum import Enum


# Default paths
BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / 'data' / 'virometrics.db'


class ExecutionStatus(Enum):
    """Execution status values."""
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class ExecutionType(Enum):
    """Type of execution."""
    TOOL = "tool"
    WORKFLOW = "workflow"
    WORKFLOW_STEP = "workflow_step"


class AuditEvent(Enum):
    """Audit event types."""
    EXECUTION_STARTED = "execution_started"
    EXECUTION_COMPLETED = "execution_completed"
    EXECUTION_FAILED = "execution_failed"
    EXECUTION_CANCELLED = "execution_cancelled"
    OUTPUT_WRITTEN = "output_written"
    ERROR_OCCURRED = "error_occurred"
    CHECKPOINT_REACHED = "checkpoint_reached"


class ExecutionHistory:
    """Track and query execution history and audit trail."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or str(DB_PATH)

    def _get_connection(self):
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def record_execution_start(self, execution_id: int, execution_type: ExecutionType,
                               tool_id: Optional[int] = None,
                               workflow_id: Optional[int] = None,
                               workflow_step_id: Optional[int] = None,
                               command: Optional[str] = None,
                               metadata: Optional[Dict[str, Any]] = None) -> int:
        """Record the start of an execution."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO execution_history
                (execution_id, execution_type, tool_id, workflow_id, workflow_step_id,
                 command, status, started_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                execution_id, execution_type.value, tool_id, workflow_id, workflow_step_id,
                command, ExecutionStatus.PENDING.value, datetime.now().isoformat(),
                json.dumps(metadata or {})
            ))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def update_execution_status(self, execution_id: int, status: ExecutionStatus,
                                message: Optional[str] = None) -> None:
        """Update execution status."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE execution_history
                SET status = ?, status_message = ?, updated_at = ?
                WHERE execution_id = ?
            """, (
                status.value, message, datetime.now().isoformat(), execution_id
            ))
            conn.commit()
        finally:
            conn.close()

    def record_execution_end(self, execution_id: int, status: ExecutionStatus,
                             return_code: Optional[int] = None,
                             output_files: Optional[List[str]] = None,
                             error_message: Optional[str] = None) -> None:
        """Record the end of an execution."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Get current record
            cursor.execute("SELECT * FROM execution_history WHERE execution_id = ?",
                          (execution_id,))
            row = cursor.fetchone()
            
            if not row:
                # Create new record if doesn't exist
                cursor.execute("""
                    INSERT INTO execution_history
                    (execution_id, status, status_message, return_code,
                     started_at, completed_at, output_files_json)
                    VALUES (?, ?, ?, ?, datetime('now'), datetime('now'), ?)
                """, (
                    execution_id, status.value, error_message, return_code,
                    json.dumps(output_files or [])
                ))
            else:
                # Update existing record
                output_list = json.loads(row['output_files_json'] or '[]')
                if output_files:
                    output_list.extend(output_files)
                
                cursor.execute("""
                    UPDATE execution_history
                    SET status = ?, status_message = ?, return_code = ?,
                        completed_at = ?, output_files_json = ?
                    WHERE execution_id = ?
                """, (
                    status.value, error_message, return_code,
                    datetime.now().isoformat(),
                    json.dumps(output_list),
                    execution_id
                ))
            
            conn.commit()
        finally:
            conn.close()

    def add_audit_event(self, execution_id: int, event_type: AuditEvent,
                        details: Optional[Dict[str, Any]] = None) -> None:
        """Add an audit event to an execution."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO audit_events
                (execution_id, event_type, details_json, occurred_at)
                VALUES (?, ?, ?, ?)
            """, (
                execution_id, event_type.value,
                json.dumps(details or {}),
                datetime.now().isoformat()
            ))
            conn.commit()
        finally:
            conn.close()

    def get_execution_history(self, execution_id: int) -> Optional[Dict[str, Any]]:
        """Get complete history for a specific execution."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Get execution record
            cursor.execute("SELECT * FROM execution_history WHERE execution_id = ?",
                          (execution_id,))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            # Get audit events
            cursor.execute("""
                SELECT event_type, details_json, occurred_at
                FROM audit_events
                WHERE execution_id = ?
                ORDER BY occurred_at ASC
            """, (execution_id,))
            audit_events = [
                {
                    'event_type': event['event_type'],
                    'details': json.loads(event['details_json'] or '{}'),
                    'occurred_at': event['occurred_at']
                }
                for event in cursor.fetchall()
            ]
            
            return {
                'execution_id': row['execution_id'],
                'execution_type': row['execution_type'],
                'tool_id': row['tool_id'],
                'workflow_id': row['workflow_id'],
                'workflow_step_id': row['workflow_step_id'],
                'command': row['command'],
                'status': row['status'],
                'status_message': row['status_message'],
                'return_code': row['return_code'],
                'started_at': row['started_at'],
                'completed_at': row['completed_at'],
                'output_files': json.loads(row['output_files_json'] or '[]'),
                'metadata': json.loads(row['metadata_json'] or '{}'),
                'audit_events': audit_events
            }
        finally:
            conn.close()

    def list_executions(self, tool_id: Optional[int] = None,
                        workflow_id: Optional[int] = None,
                        status: Optional[str] = None,
                        limit: int = 50,
                        offset: int = 0) -> List[Dict[str, Any]]:
        """List executions with optional filters."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            query = """
                SELECT execution_id, execution_type, tool_id, workflow_id,
                       command, status, started_at, completed_at
                FROM execution_history
                WHERE 1=1
            """
            params = []
            
            if tool_id:
                query += " AND tool_id = ?"
                params.append(tool_id)
            
            if workflow_id:
                query += " AND workflow_id = ?"
                params.append(workflow_id)
            
            if status:
                query += " AND status = ?"
                params.append(status)
            
            query += " ORDER BY started_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            
            return [
                {
                    'execution_id': row['execution_id'],
                    'execution_type': row['execution_type'],
                    'tool_id': row['tool_id'],
                    'workflow_id': row['workflow_id'],
                    'command': row['command'],
                    'status': row['status'],
                    'started_at': row['started_at'],
                    'completed_at': row['completed_at']
                }
                for row in cursor.fetchall()
            ]
        finally:
            conn.close()

    def get_execution_stats(self, days: int = 30) -> Dict[str, Any]:
        """Get execution statistics for specified period."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Get stats by status
            cursor.execute("""
                SELECT 
                    status,
                    COUNT(*) as count,
                    SUM(CASE WHEN status = 'completed' 
                        THEN (julianday(completed_at) - julianday(started_at)) * 24 
                        ELSE 0 END) as total_hours
                FROM execution_history
                WHERE started_at >= datetime('now', ?)
                GROUP BY status
            """, (f'-{days} days',))
            
            status_stats = {row['status']: {'count': row['count']} 
                           for row in cursor.fetchall()}
            
            # Get execution duration stats
            cursor.execute("""
                SELECT 
                    AVG((julianday(completed_at) - julianday(started_at)) * 24) as avg_hours,
                    MIN((julianday(completed_at) - julianday(started_at)) * 24) as min_hours,
                    MAX((julianday(completed_at) - julianday(started_at)) * 24) as max_hours
                FROM execution_history
                WHERE status = 'completed' 
                  AND started_at >= datetime('now', ?)
            """, (f'-{days} days',))
            
            duration_stats = cursor.fetchone()
            
            # Get top tools by execution count
            cursor.execute("""
                SELECT tool_id, COUNT(*) as execution_count
                FROM execution_history
                WHERE execution_type = 'tool'
                  AND started_at >= datetime('now', ?)
                GROUP BY tool_id
                ORDER BY execution_count DESC
                LIMIT 10
            """, (f'-{days} days',))
            
            top_tools = [{'tool_id': row['tool_id'], 'count': row['execution_count']}
                        for row in cursor.fetchall()]
            
            return {
                'period_days': days,
                'total_executions': sum(s['count'] for s in status_stats.values()),
                'by_status': status_stats,
                'duration_stats': {
                    'avg_hours': round(duration_stats['avg_hours'] or 0, 2),
                    'min_hours': round(duration_stats['min_hours'] or 0, 2),
                    'max_hours': round(duration_stats['max_hours'] or 0, 2)
                } if duration_stats else {},
                'top_tools': top_tools
            }
        finally:
            conn.close()

    def get_audit_trail(self, execution_id: int,
                        event_types: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Get audit trail for an execution."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            query = """
                SELECT event_type, details_json, occurred_at
                FROM audit_events
                WHERE execution_id = ?
            """
            params = [execution_id]
            
            if event_types:
                placeholders = ','.join(['?' for _ in event_types])
                query += f" AND event_type IN ({placeholders})"
                params.extend(event_types)
            
            query += " ORDER BY occurred_at ASC"
            
            cursor.execute(query, params)
            
            return [
                {
                    'event_type': row['event_type'],
                    'details': json.loads(row['details_json'] or '{}'),
                    'occurred_at': row['occurred_at']
                }
                for row in cursor.fetchall()
            ]
        finally:
            conn.close()

    def get_recent_failures(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent failed executions."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT execution_id, execution_type, tool_id, workflow_id,
                       command, status_message, started_at, completed_at
                FROM execution_history
                WHERE status IN ('failed', 'timeout')
                ORDER BY started_at DESC
                LIMIT ?
            """, (limit,))
            
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def search_executions(self, search_term: str,
                          limit: int = 20) -> List[Dict[str, Any]]:
        """Search executions by command or metadata."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT execution_id, execution_type, tool_id, workflow_id,
                       command, status, started_at
                FROM execution_history
                WHERE command LIKE ? 
                   OR metadata_json LIKE ?
                ORDER BY started_at DESC
                LIMIT ?
            """, (f'%{search_term}%', f'%{search_term}%', limit))
            
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()


def main():
    """Demo execution history functionality."""
    history = ExecutionHistory()
    
    print("Execution History Demo")
    print("=" * 50)
    
    # Get recent executions
    print("\nRecent Executions:")
    executions = history.list_executions(limit=5)
    for exec_info in executions:
        print(f"  {exec_info['execution_id']}: {exec_info['status']} "
              f"(Type: {exec_info['execution_type']})")
    
    # Get stats
    print("\nExecution Stats (30 days):")
    stats = history.get_execution_stats(days=30)
    print(f"  Total: {stats['total_executions']}")
    print(f"  By Status: {stats['by_status']}")
    
    # Get recent failures
    print("\nRecent Failures:")
    failures = history.get_recent_failures(limit=3)
    for failure in failures:
        print(f"  {failure['execution_id']}: {failure['status_message']}")


if __name__ == '__main__':
    main()
