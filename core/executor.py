"""Tool execution engine for Virometrics platform."""

import subprocess
import threading
import sqlite3
import os
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Callable

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'virometrics.db')

# Try to import checkpoint support
try:
    from core.checkpoint import CheckpointManager
    CHECKPOINT_AVAILABLE = True
except ImportError:
    CHECKPOINT_AVAILABLE = False
    logger.warning("Checkpoint module not available")


class ToolExecutor:
    """Execute bioinformatics tools with real-time output capture."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        enable_checkpoint: bool = False,
        checkpoint_interval: int = 300,
    ):
        self.db_path = db_path or os.path.abspath(DB_PATH)
        self.active_processes: Dict[int, subprocess.Popen] = {}
        self._lock = threading.Lock()
        self.enable_checkpoint = enable_checkpoint
        self.checkpoint_interval = checkpoint_interval
        
        # Initialize checkpoint manager
        if enable_checkpoint and CHECKPOINT_AVAILABLE:
            self.checkpoint_manager = CheckpointManager(db_path=self.db_path)
        else:
            self.checkpoint_manager = None
        
        # Progress callbacks
        self._progress_callbacks: List[Callable] = []

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def execute(
        self,
        tool_id: int,
        command: str,
        working_dir: Optional[str] = None,
        env_vars: Optional[Dict[str, str]] = None,
        execution_name: Optional[str] = None,
        timeout: int = 3600,
        checkpoint_data: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Start execution, return execution ID."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO tool_executions (tool_id, execution_name, command, working_dir, status) VALUES (?,?,?,?,'pending')",
                (tool_id, execution_name, command, working_dir)
            )
            conn.commit()
            execution_id = cursor.lastrowid
        finally:
            try:
                conn.close()
            except:
                pass

        thread = threading.Thread(
            target=self._run_command,
            args=(execution_id, command, working_dir, env_vars, timeout, checkpoint_data),
            daemon=True
        )
        thread.start()
        return execution_id

    def _run_command(
        self,
        execution_id: int,
        command: str,
        working_dir: Optional[str],
        env_vars: Optional[Dict],
        timeout: int,
        checkpoint_data: Optional[Dict[str, Any]] = None,
    ):
        """Run command in background thread with checkpoint support."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("UPDATE tool_executions SET status='running' WHERE id=?", (execution_id,))
            conn.commit()

            env = os.environ.copy()
            if env_vars:
                env.update(env_vars)

            if working_dir and not os.path.isdir(working_dir):
                os.makedirs(working_dir, exist_ok=True)

            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=working_dir or os.getcwd(),
                env=env,
                bufsize=1,
                universal_newlines=True
            )

            with self._lock:
                self.active_processes[execution_id] = process

            cursor.execute("UPDATE tool_executions SET pid=? WHERE id=?", (process.pid, execution_id))
            conn.commit()

            # Start checkpoint timer if enabled
            checkpoint_timer = None
            if self.enable_checkpoint and self.checkpoint_manager:
                checkpoint_timer = threading.Timer(
                    self.checkpoint_interval,
                    self._auto_checkpoint,
                    args=(execution_id, process.pid, checkpoint_data)
                )
                checkpoint_timer.start()

            seq_num = [0]
            stdout_thread = threading.Thread(
                target=self._read_stream,
                args=(execution_id, process.stdout, 'stdout', seq_num),
                daemon=True
            )
            stderr_thread = threading.Thread(
                target=self._read_stream,
                args=(execution_id, process.stderr, 'stderr', seq_num),
                daemon=True
            )
            stdout_thread.start()
            stderr_thread.start()

            try:
                return_code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                logger.warning(f"Execution {execution_id} timed out")
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                return_code = -1

            # Cancel checkpoint timer on completion
            if checkpoint_timer:
                checkpoint_timer.cancel()

            stdout_thread.join(timeout=10)
            stderr_thread.join(timeout=10)

            # Create final checkpoint if enabled
            if self.enable_checkpoint and self.checkpoint_manager and return_code == 0:
                self._save_final_checkpoint(execution_id, checkpoint_data or {})

            cursor.execute(
                "UPDATE tool_executions SET status=?, return_code=?, completed_at=datetime('now') WHERE id=?",
                ('completed' if return_code == 0 else 'failed', return_code, execution_id)
            )
            conn.commit()

            self._log_output(execution_id, 'info', f"Execution completed with return code {return_code}", seq_num[0])
            seq_num[0] += 1

        except Exception as e:
            logger.error(f"Error in execution {execution_id}: {e}")
            try:
                cursor.execute("UPDATE tool_executions SET status='failed', completed_at=datetime('now') WHERE id=?", (execution_id,))
                conn.commit()
            except:
                pass
        finally:
            try:
                conn.close()
            except:
                pass
            with self._lock:
                self.active_processes.pop(execution_id, None)

    def _read_stream(self, execution_id: int, stream, output_type: str, seq_num: list):
        """Read lines from stream and store in database."""
        try:
            for line in iter(stream.readline, ''):
                if not line:
                    break
                line = line.rstrip('\n').rstrip('\r')
                if line:
                    self._log_output(execution_id, output_type, line, seq_num[0])
                    seq_num[0] += 1
            stream.close()
        except Exception as e:
            logger.error(f"Error reading {output_type}: {e}")

    def _log_output(self, execution_id: int, output_type: str, content: str, sequence: int):
        """Store output line using a new connection."""
        conn = None
        try:
            conn = self._get_connection()
            conn.execute(
                "INSERT INTO execution_outputs (execution_id, output_type, content, sequence_num) VALUES (?,?,?,?)",
                (execution_id, output_type, content, sequence)
            )
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to log output: {e}")
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass

    def cancel(self, execution_id: int) -> bool:
        """Cancel a running execution."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT status, pid FROM tool_executions WHERE id=?", (execution_id,))
            row = cursor.fetchone()
            if not row or row['status'] != 'running':
                return False

            with self._lock:
                process = self.active_processes.get(execution_id)

            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()

            cursor.execute(
                "UPDATE tool_executions SET status='cancelled', completed_at=datetime('now') WHERE id=?",
                (execution_id,)
            )
            cursor.execute(
                "INSERT INTO execution_outputs (execution_id, output_type, content, sequence_num) VALUES (?,?,?, (SELECT COALESCE(MAX(sequence_num),0)+1 FROM execution_outputs WHERE execution_id=?))",
                (execution_id, 'info', 'Execution cancelled by user', execution_id)
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error cancelling: {e}")
            return False
        finally:
            try:
                conn.close()
            except:
                pass

    def get_status(self, execution_id: int) -> Optional[Dict[str, Any]]:
        """Get execution status."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT t.id, t.tool_id, t.command, t.status, t.return_code,
                          t.started_at, t.completed_at, t.pid, tools.name as tool_name
                   FROM tool_executions t LEFT JOIN tools ON tools.id = t.tool_id
                   WHERE t.id=?""",
                (execution_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {
                'execution_id': row['id'], 'tool_id': row['tool_id'],
                'tool_name': row['tool_name'], 'command': row['command'],
                'status': row['status'], 'return_code': row['return_code'],
                'started_at': row['started_at'], 'completed_at': row['completed_at'],
                'pid': row['pid']
            }
        finally:
            try:
                conn.close()
            except:
                pass

    def get_new_outputs(self, execution_id: int, last_sequence: int = -1):
        """Get new output lines."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, output_type, content, sequence_num, timestamp FROM execution_outputs WHERE execution_id=? AND sequence_num>? ORDER BY sequence_num ASC",
                (execution_id, last_sequence)
            )
            return [
                {'id': r['id'], 'type': r['output_type'], 'content': r['content'],
                 'sequence': r['sequence_num'], 'timestamp': r['timestamp']}
                for r in cursor.fetchall()
            ]
        finally:
            try:
                conn.close()
            except:
                pass
    
    def _auto_checkpoint(
        self,
        execution_id: int,
        pid: int,
        data: Optional[Dict[str, Any]] = None,
    ):
        """Automatically create a checkpoint."""
        if not self.checkpoint_manager:
            return
        
        try:
            checkpoint_data = data or {}
            checkpoint_data['execution_id'] = execution_id
            checkpoint_data['auto'] = True
            checkpoint_data['pid'] = pid
            checkpoint_data['timestamp'] = datetime.now().isoformat()
            
            self.checkpoint_manager.create_checkpoint(
                execution_id=execution_id,
                data=checkpoint_data,
                metadata={'auto': True},
            )
            
            # Restart timer
            timer = threading.Timer(
                self.checkpoint_interval,
                self._auto_checkpoint,
                args=(execution_id, pid, data)
            )
            timer.start()
            
            logger.debug(f"Auto checkpoint created for execution {execution_id}")
        except Exception as e:
            logger.error(f"Error in auto checkpoint: {e}")
    
    def _save_final_checkpoint(
        self,
        execution_id: int,
        data: Optional[Dict[str, Any]] = None,
    ):
        """Save final checkpoint on successful completion."""
        if not self.checkpoint_manager:
            return
        
        try:
            checkpoint_data = data or {}
            checkpoint_data['execution_id'] = execution_id
            checkpoint_data['final'] = True
            checkpoint_data['status'] = 'completed'
            checkpoint_data['timestamp'] = datetime.now().isoformat()
            
            self.checkpoint_manager.create_checkpoint(
                execution_id=execution_id,
                data=checkpoint_data,
                metadata={'final': True},
            )
            
            logger.info(f"Final checkpoint saved for execution {execution_id}")
        except Exception as e:
            logger.error(f"Error saving final checkpoint: {e}")
    
    def create_checkpoint(
        self,
        execution_id: int,
        data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Manually create a checkpoint."""
        if not self.checkpoint_manager:
            raise RuntimeError("Checkpointing not enabled")
        
        return self.checkpoint_manager.create_checkpoint(
            execution_id=execution_id,
            data=data,
            metadata=metadata,
        )
    
    def restore_checkpoint(self, execution_id: int) -> Optional[Dict[str, Any]]:
        """Restore execution from checkpoint."""
        if not self.checkpoint_manager:
            raise RuntimeError("Checkpointing not enabled")
        
        return self.checkpoint_manager.restore_from_checkpoint(execution_id)
    
    def get_checkpoints(self, execution_id: int):
        """Get all checkpoints for an execution."""
        if not self.checkpoint_manager:
            return []
        
        return self.checkpoint_manager.get_checkpoints(execution_id)

    def list_executions(self, tool_id: Optional[int] = None, limit: int = 50):
        """List recent executions."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            if tool_id:
                cursor.execute(
                    """SELECT t.id, t.tool_id, t.command, t.status, t.started_at, tools.name as tool_name
                       FROM tool_executions t LEFT JOIN tools ON tools.id = t.tool_id
                       WHERE t.tool_id=? ORDER BY t.started_at DESC LIMIT ?""",
                    (tool_id, limit)
                )
            else:
                cursor.execute(
                    """SELECT t.id, t.tool_id, t.command, t.status, t.started_at, tools.name as tool_name
                       FROM tool_executions t LEFT JOIN tools ON tools.id = t.tool_id
                       ORDER BY t.started_at DESC LIMIT ?""",
                    (limit,)
                )
            return [
                {'execution_id': r['id'], 'tool_id': r['tool_id'],
                 'tool_name': r['tool_name'], 'command': r['command'][:100],
                 'status': r['status'], 'started_at': r['started_at']}
                for r in cursor.fetchall()
            ]
        finally:
            try:
                conn.close()
            except:
                pass
    
    def _auto_checkpoint(
        self,
        execution_id: int,
        pid: int,
        data: Optional[Dict[str, Any]] = None,
    ):
        """Automatically create a checkpoint."""
        if not self.checkpoint_manager:
            return
        
        try:
            checkpoint_data = data or {}
            checkpoint_data['execution_id'] = execution_id
            checkpoint_data['auto'] = True
            checkpoint_data['pid'] = pid
            checkpoint_data['timestamp'] = datetime.now().isoformat()
            
            self.checkpoint_manager.create_checkpoint(
                execution_id=execution_id,
                data=checkpoint_data,
                metadata={'auto': True},
            )
            
            # Restart timer
            timer = threading.Timer(
                self.checkpoint_interval,
                self._auto_checkpoint,
                args=(execution_id, pid, data)
            )
            timer.start()
            
            logger.debug(f"Auto checkpoint created for execution {execution_id}")
        except Exception as e:
            logger.error(f"Error in auto checkpoint: {e}")
    
    def _save_final_checkpoint(
        self,
        execution_id: int,
        data: Optional[Dict[str, Any]] = None,
    ):
        """Save final checkpoint on successful completion."""
        if not self.checkpoint_manager:
            return
        
        try:
            checkpoint_data = data or {}
            checkpoint_data['execution_id'] = execution_id
            checkpoint_data['final'] = True
            checkpoint_data['status'] = 'completed'
            checkpoint_data['timestamp'] = datetime.now().isoformat()
            
            self.checkpoint_manager.create_checkpoint(
                execution_id=execution_id,
                data=checkpoint_data,
                metadata={'final': True},
            )
            
            logger.info(f"Final checkpoint saved for execution {execution_id}")
        except Exception as e:
            logger.error(f"Error saving final checkpoint: {e}")
    
    def create_checkpoint(
        self,
        execution_id: int,
        data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Manually create a checkpoint."""
        if not self.checkpoint_manager:
            raise RuntimeError("Checkpointing not enabled")
        
        return self.checkpoint_manager.create_checkpoint(
            execution_id=execution_id,
            data=data,
            metadata=metadata,
        )
    
    def restore_checkpoint(self, execution_id: int) -> Optional[Dict[str, Any]]:
        """Restore execution from checkpoint."""
        if not self.checkpoint_manager:
            raise RuntimeError("Checkpointing not enabled")
        
        return self.checkpoint_manager.restore_from_checkpoint(execution_id)
    
    def get_checkpoints(self, execution_id: int):
        """Get all checkpoints for an execution."""
        if not self.checkpoint_manager:
            return []
        
        return self.checkpoint_manager.get_checkpoints(execution_id)
