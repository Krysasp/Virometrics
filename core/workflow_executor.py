"""Workflow execution engine for Virometrics platform."""

import json
import logging
import threading
import sqlite3
from typing import Optional, Dict, List, Any
from datetime import datetime

from core.executor import ToolExecutor

logger = logging.getLogger(__name__)


class WorkflowExecutor:
    """Execute workflows with sequential/parallel step execution."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        enable_checkpoint: bool = False,
        parallel_execution: bool = False,
    ):
        self.db_path = db_path
        self.tool_executor = ToolExecutor(
            db_path=self.db_path,
            enable_checkpoint=enable_checkpoint
        )
        self.parallel_execution = parallel_execution
        self._lock = threading.Lock()
        self.active_workflows: Dict[int, threading.Thread] = {}

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def execute_workflow(
        self,
        workflow_id: int,
        execution_name: Optional[str] = None,
        created_by: str = 'anonymous',
        parameters: Optional[Dict[int, Dict]] = None,
    ) -> int:
        """Start workflow execution, return execution ID."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Create workflow execution record
            cursor.execute(
                """INSERT INTO workflow_executions
                   (workflow_id, execution_name, created_by, status)
                   VALUES (?, ?, ?, 'pending')""",
                (workflow_id, execution_name, created_by)
            )
            workflow_exec_id = cursor.lastrowid
            conn.commit()
            
            # Get workflow steps
            cursor.execute("""
                SELECT ws.*, t.id as tool_id, t.name as tool_name
                FROM workflow_steps ws
                JOIN tools t ON ws.tool_id = t.id
                WHERE ws.workflow_id=?
                ORDER BY ws.position
            """, (workflow_id,))
            steps = [dict(r) for r in cursor.fetchall()]
            
            logger.info(f"Starting workflow {workflow_id} execution {workflow_exec_id} with {len(steps)} steps")
            
        finally:
            try:
                conn.close()
            except:
                pass

        # Start execution thread
        thread = threading.Thread(
            target=self._run_workflow,
            args=(workflow_exec_id, workflow_id, steps, parameters),
            daemon=True
        )
        thread.start()
        
        with self._lock:
            self.active_workflows[workflow_exec_id] = thread
        
        return workflow_exec_id

    def _run_workflow(
        self,
        workflow_exec_id: int,
        workflow_id: int,
        steps: List[Dict],
        parameters: Optional[Dict[int, Dict]],
    ):
        """Execute workflow steps sequentially or in parallel."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("UPDATE workflow_executions SET status='running' WHERE id=?", (workflow_exec_id,))
            conn.commit()
            
            parameters = parameters or {}
            
            if self.parallel_execution:
                self._run_parallel(conn, cursor, workflow_exec_id, workflow_id, steps, parameters)
            else:
                self._run_sequential(conn, cursor, workflow_exec_id, workflow_id, steps, parameters)
            
        except Exception as e:
            logger.error(f"Error executing workflow {workflow_exec_id}: {e}")
            try:
                cursor.execute("UPDATE workflow_executions SET status='failed' WHERE id=?", (workflow_exec_id,))
                conn.commit()
            except:
                pass
        finally:
            try:
                conn.close()
            except:
                pass

    def _run_sequential(
        self,
        conn,
        cursor,
        workflow_exec_id: int,
        workflow_id: int,
        steps: List[Dict],
        parameters: Dict[int, Dict],
    ):
        """Execute steps sequentially."""
        all_success = True
        
        for step in steps:
            step_id = step['id']
            tool_id = step['tool_id']
            position = step['position']
            config = json.loads(step.get('config_json') or '{}')
            
            # Create step execution record
            cursor.execute(
                """INSERT INTO workflow_step_executions
                   (workflow_execution_id, workflow_step_id, status)
                   VALUES (?, ?, 'pending')""",
                (workflow_exec_id, step_id)
            )
            step_exec_id = cursor.lastrowid
            conn.commit()
            
            try:
                # Build command
                command = self._build_command(tool_id, config, parameters.get(tool_id, {}))
                
                # Execute tool
                tool_exec_id = self.tool_executor.execute(
                    tool_id=tool_id,
                    command=command,
                    working_dir=config.get('working_dir'),
                    execution_name=f"{step['step_id']}_step",
                    timeout=config.get('timeout', 3600),
                )
                
                # Update step execution
                cursor.execute(
                    """UPDATE workflow_step_executions
                       SET status='running', started_at=datetime('now')
                       WHERE id=?""",
                    (step_exec_id,)
                )
                conn.commit()
                
                # Wait for completion
                status = self.tool_executor.get_status(tool_exec_id)
                while status.get('status') in ('pending', 'running'):
                    import time
                    time.sleep(0.5)
                    status = self.tool_executor.get_status(tool_exec_id)
                
                # Update final status
                step_status = 'completed' if status.get('return_code', -1) == 0 else 'failed'
                cursor.execute(
                    """UPDATE workflow_step_executions
                       SET status=?, completed_at=datetime('now'),
                           return_code=?
                       WHERE id=?""",
                    (step_status, status.get('return_code'), step_exec_id)
                )
                conn.commit()
                
                if step_status == 'failed':
                    all_success = False
                    logger.warning(f"Step {step_id} failed with exit code {status.get('return_code')}")
                    break
                    
            except Exception as e:
                logger.error(f"Error executing step {step_id}: {e}")
                cursor.execute(
                    "UPDATE workflow_step_executions SET status='failed', completed_at=datetime('now') WHERE id=?",
                    (step_exec_id,)
                )
                conn.commit()
                all_success = False
                break
        
        # Update workflow execution status
        final_status = 'completed' if all_success else 'failed'
        cursor.execute(
            "UPDATE workflow_executions SET status=?, completed_at=datetime('now') WHERE id=?",
            (final_status, workflow_exec_id)
        )
        conn.commit()
        
        logger.info(f"Workflow {workflow_exec_id} {final_status}")

    def _run_parallel(
        self,
        conn,
        cursor,
        workflow_exec_id: int,
        workflow_id: int,
        steps: List[Dict],
        parameters: Dict[int, Dict],
    ):
        """Execute independent steps in parallel."""
        def execute_step(step):
            step_conn = self._get_connection()
            try:
                step_cursor = step_conn.cursor()
                step_id = step['id']
                tool_id = step['tool_id']
                config = json.loads(step.get('config_json') or '{}')
                
                # Create step execution record
                step_cursor.execute(
                    """INSERT INTO workflow_step_executions
                       (workflow_execution_id, workflow_step_id, status)
                       VALUES (?, ?, 'running')""",
                    (workflow_exec_id, step_id)
                )
                step_exec_id = step_cursor.lastrowid
                step_conn.commit()
                
                try:
                    command = self._build_command(tool_id, config, parameters.get(tool_id, {}))
                    
                    tool_exec_id = self.tool_executor.execute(
                        tool_id=tool_id,
                        command=command,
                        working_dir=config.get('working_dir'),
                        execution_name=f"{step['step_id']}_step",
                        timeout=config.get('timeout', 3600),
                    )
                    
                    status = self.tool_executor.get_status(tool_exec_id)
                    while status.get('status') in ('pending', 'running'):
                        import time
                        time.sleep(0.5)
                        status = self.tool_executor.get_status(tool_exec_id)
                    
                    step_status = 'completed' if status.get('return_code', -1) == 0 else 'failed'
                    step_cursor.execute(
                        """UPDATE workflow_step_executions
                           SET status=?, completed_at=datetime('now'), return_code=?
                           WHERE id=?""",
                        (step_status, status.get('return_code'), step_exec_id)
                    )
                    step_conn.commit()
                    
                    return step_id, step_status
                    
                except Exception as e:
                    logger.error(f"Error executing step {step_id}: {e}")
                    step_cursor.execute(
                        "UPDATE workflow_step_executions SET status='failed', completed_at=datetime('now') WHERE id=?",
                        (step_exec_id,)
                    )
                    step_conn.commit()
                    return step_id, 'failed'
            finally:
                step_conn.close()

        # Execute all steps in parallel threads
        threads = []
        for step in steps:
            t = threading.Thread(target=execute_step, args=(step,))
            threads.append(t)
            t.start()
        
        # Wait for all threads
        for t in threads:
            t.join()
        
        # Update workflow status
        conn.execute(
            "UPDATE workflow_executions SET status='completed', completed_at=datetime('now') WHERE id=?",
            (workflow_exec_id,)
        )
        conn.commit()

    def _build_command(
        self,
        tool_id: int,
        step_config: Dict,
        override_params: Dict,
    ) -> str:
        """Build command from tool metadata and parameters."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT name, packages_needed, repo_path FROM tools WHERE id=?", (tool_id,))
            result = cursor.fetchone()
            
            if not result:
                return ""
            
            tool_name = result[0]
            packages = result[1]
            repo_path = result[2]
            
            # Merge step config with override params
            params = {**json.loads(step_config.get('parameters') or '{}'), **override_params}
            
            # Build command from tool name and parameters
            cmd_parts = [tool_name]
            for param_name, param_value in params.items():
                if param_value is not None and param_value != '':
                    cmd_parts.append(f"--{param_name}")
                    cmd_parts.append(str(param_value))
            
            return ' '.join(cmd_parts)
            
        finally:
            try:
                conn.close()
            except:
                pass

    def get_workflow_status(self, workflow_exec_id: int) -> Optional[Dict]:
        """Get workflow execution status."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT we.*, w.name as workflow_name
                FROM workflow_executions we
                JOIN workflows w ON we.workflow_id = w.id
                WHERE we.id=?
            """, (workflow_exec_id,))
            
            result = cursor.fetchone()
            if not result:
                return None
            
            status = dict(result)
            
            # Get step executions
            cursor.execute("""
                SELECT wse.*, ws.step_id, ws.position, t.name as tool_name
                FROM workflow_step_executions wse
                JOIN workflow_steps ws ON wse.workflow_step_id = ws.id
                JOIN tools t ON ws.tool_id = t.id
                WHERE wse.workflow_execution_id=?
                ORDER BY wse.workflow_step_id
            """, (workflow_exec_id,))
            
            status['steps'] = [dict(r) for r in cursor.fetchall()]
            return status
            
        finally:
            try:
                conn.close()
            except:
                pass

    def cancel_workflow(self, workflow_exec_id: int) -> bool:
        """Cancel a running workflow."""
        with self._lock:
            thread = self.active_workflows.get(workflow_exec_id)
        
        if thread and thread.is_alive():
            # Note: threading doesn't support true cancellation
            # Just mark as cancelled in database
            conn = self._get_connection()
            try:
                conn.execute(
                    "UPDATE workflow_executions SET status='cancelled' WHERE id=?",
                    (workflow_exec_id,)
                )
                conn.commit()
            finally:
                conn.close()
            return True
        
        return False
