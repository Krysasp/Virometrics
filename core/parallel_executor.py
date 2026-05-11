"""Parallel execution support for Virometrics platform.

Implements scatter-gather patterns for processing multiple input files
concurrently and aggregating results.
"""

import os
import sys
import uuid
import time
import json
import logging
import threading
import subprocess
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable, Tuple
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ScatterTask:
    """A single task in a scatter operation."""
    task_id: str
    input_file: str
    parameters: Dict[str, Any]
    index: int
    status: str = "pending"
    output_file: Optional[str] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


@dataclass
class ScatterResult:
    """Result of a scatter-gather operation."""
    scatter_id: str
    tool_id: int
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    results: List[ScatterTask]
    aggregated_result: Optional[Any] = None
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    status: str = "pending"


class ParallelExecutor:
    """Executes tasks in parallel using scatter-gather pattern."""
    
    def __init__(
        self,
        max_workers: int = 4,
        db_path: Optional[str] = None,
        result_aggregator: Optional[Callable[[List[Any]], Any]] = None,
    ):
        self.max_workers = max_workers
        self.db_path = db_path or os.path.join(
            os.path.dirname(__file__), '..', 'data', 'virometrics.db'
        )
        self.result_aggregator = result_aggregator
        
        self._scatter_results: Dict[str, ScatterResult] = {}
        self._lock = threading.Lock()
    
    def _get_connection(self):
        """Get database connection."""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn
    
    def scatter_execute(
        self,
        tool_id: int,
        input_files: List[str],
        base_command: str,
        parameters: Optional[Dict[str, Any]] = None,
        output_dir: Optional[str] = None,
        aggregator: Optional[Callable[[List[Any]], Any]] = None,
    ) -> ScatterResult:
        """
        Execute a scatter operation on multiple input files.
        
        Args:
            tool_id: ID of the tool to execute
            input_files: List of input files to process
            base_command: Base command template
            parameters: Common parameters for all tasks
            output_dir: Output directory
            aggregator: Function to aggregate results
            
        Returns:
            ScatterResult with all task results
        """
        scatter_id = str(uuid.uuid4())
        tasks = []
        
        # Create scatter tasks
        for idx, input_file in enumerate(input_files):
            task_id = f"{scatter_id}_task_{idx}"
            
            # Prepare task-specific parameters
            task_params = parameters.copy() if parameters else {}
            task_params['input'] = input_file
            task_params['index'] = idx
            
            task = ScatterTask(
                task_id=task_id,
                input_file=input_file,
                parameters=task_params,
                index=idx,
            )
            tasks.append(task)
        
        # Create scatter result
        result = ScatterResult(
            scatter_id=scatter_id,
            tool_id=tool_id,
            total_tasks=len(tasks),
            completed_tasks=0,
            failed_tasks=0,
            results=tasks,
        )
        
        with self._lock:
            self._scatter_results[scatter_id] = result
        
        # Execute tasks in parallel
        self._execute_scatter(result, base_command, output_dir, aggregator or self.result_aggregator)
        
        return result
    
    def _execute_scatter(
        self,
        result: ScatterResult,
        base_command: str,
        output_dir: Optional[str],
        aggregator: Optional[Callable],
    ):
        """Execute scatter tasks in parallel."""
        result.status = "running"
        result.start_time = datetime.now()
        
        # Ensure output directory exists
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        
        def execute_task(task: ScatterTask) -> ScatterTask:
            """Execute a single task."""
            task.started_at = datetime.now()
            task.status = "running"
            
            try:
                # Build command
                command = self._build_command(base_command, task.parameters)
                
                # Execute
                output_file = self._run_command(command, task.input_file, output_dir)
                
                task.output_file = output_file
                task.result = {
                    'input': task.input_file,
                    'output': output_file,
                    'index': task.index,
                }
                task.status = "completed"
                
            except Exception as e:
                task.error = str(e)
                task.status = "failed"
                logger.error(f"Task {task.task_id} failed: {e}")
            
            task.completed_at = datetime.now()
            return task
        
        # Execute tasks in parallel
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(execute_task, task): task for task in result.results}
            
            for future in as_completed(futures):
                task = futures[future]
                try:
                    completed_task = future.result()
                    
                    # Update result
                    with self._lock:
                        if completed_task.status == "completed":
                            result.completed_tasks += 1
                        else:
                            result.failed_tasks += 1
                
                except Exception as e:
                    logger.error(f"Error in task {task.task_id}: {e}")
                    with self._lock:
                        result.failed_tasks += 1
        
        # Aggregate results
        if aggregator:
            try:
                successful_results = [
                    t.result for t in result.results if t.status == "completed"
                ]
                result.aggregated_result = aggregator(successful_results)
            except Exception as e:
                logger.error(f"Error aggregating results: {e}")
                result.aggregated_result = None
        
        result.end_time = datetime.now()
        result.status = "completed" if result.failed_tasks == 0 else "partial"
        
        logger.info(
            f"Scatter {result.scatter_id} completed: "
            f"{result.completed_tasks}/{result.total_tasks} successful"
        )
    
    def _build_command(self, base_command: str, parameters: Dict[str, Any]) -> str:
        """Build command string from parameters."""
        cmd_parts = [base_command]
        
        for key, value in sorted(parameters.items()):
            if value is None or value == '':
                continue
            
            if isinstance(value, bool):
                if value:
                    cmd_parts.append(f"--{key}")
            elif isinstance(value, (list, tuple)):
                cmd_parts.append(f"--{key}")
                cmd_parts.extend(str(v) for v in value)
            else:
                cmd_parts.append(f"--{key}")
                cmd_parts.append(str(value))
        
        return ' '.join(cmd_parts)
    
    def _run_command(
        self,
        command: str,
        input_file: str,
        output_dir: Optional[str],
    ) -> str:
        """Execute command and return output file path."""
        # Generate output filename
        base_name = os.path.splitext(os.path.basename(input_file))[0]
        output_file = os.path.join(output_dir or os.getcwd(), f"{base_name}_output.txt")
        
        try:
            # Run command
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=output_dir or os.getcwd(),
            )
            
            stdout, stderr = process.communicate()
            
            if process.returncode == 0:
                # Write output to file
                with open(output_file, 'w') as f:
                    f.write(stdout.decode('utf-8'))
            else:
                raise RuntimeError(f"Command failed: {stderr.decode('utf-8')}")
            
        except Exception as e:
            logger.error(f"Error running command: {e}")
            raise
        
        return output_file
    
    def gather_results(
        self,
        scatter_id: str,
        aggregator: Optional[Callable[[List[Any]], Any]] = None,
    ) -> Optional[Any]:
        """
        Gather results from completed scatter operation.
        
        Args:
            scatter_id: ID of scatter operation
            aggregator: Function to aggregate results
            
        Returns:
            Aggregated result
        """
        result = self.get_scatter_result(scatter_id)
        if not result:
            return None
        
        if aggregator:
            successful_results = [
                t.result for t in result.results if t.status == "completed"
            ]
            return aggregator(successful_results)
        
        return result.aggregated_result
    
    def get_scatter_result(self, scatter_id: str) -> Optional[ScatterResult]:
        """Get scatter result by ID."""
        with self._lock:
            return self._scatter_results.get(scatter_id)
    
    def list_scatter_operations(self) -> List[Dict[str, Any]]:
        """List all scatter operations."""
        with self._lock:
            return [
                {
                    'scatter_id': r.scatter_id,
                    'tool_id': r.tool_id,
                    'total_tasks': r.total_tasks,
                    'completed_tasks': r.completed_tasks,
                    'failed_tasks': r.failed_tasks,
                    'status': r.status,
                    'start_time': r.start_time.isoformat(),
                    'end_time': r.end_time.isoformat() if r.end_time else None,
                }
                for r in self._scatter_results.values()
            ]
    
    def wait_for_completion(
        self,
        scatter_id: str,
        timeout: Optional[float] = None,
    ) -> bool:
        """Wait for scatter operation to complete."""
        result = self.get_scatter_result(scatter_id)
        if not result:
            return False
        
        start = time.time()
        while result.status in ("pending", "running"):
            if timeout and (time.time() - start) > timeout:
                return False
            time.sleep(0.1)
            result = self.get_scatter_result(scatter_id)
        
        return result.status == "completed"


class ScatterGatherPipeline:
    """High-level scatter-gather pipeline for complex workflows."""
    
    def __init__(
        self,
        stages: List[Tuple[str, str, Dict[str, Any]]],
        max_workers: int = 4,
    ):
        """
        Initialize pipeline with stages.
        
        Args:
            stages: List of (name, command_template, parameters) tuples
            max_workers: Maximum parallel workers
        """
        self.stages = stages
        self.max_workers = max_workers
        self._executors: Dict[str, ParallelExecutor] = {}
        self._results: Dict[str, ScatterResult] = {}
    
    def run(self, input_files: List[str], output_dir: str) -> Dict[str, ScatterResult]:
        """
        Run scatter-gather pipeline on input files.
        
        Args:
            input_files: Input files to process
            output_dir: Output directory
            
        Returns:
            Dictionary of stage results
        """
        os.makedirs(output_dir, exist_ok=True)
        
        current_files = input_files
        
        for stage_idx, (stage_name, command, params) in enumerate(self.stages):
            # Create stage output directory
            stage_output_dir = os.path.join(output_dir, stage_name)
            
            # Create executor for this stage
            executor = ParallelExecutor(
                max_workers=self.max_workers,
                result_aggregator=self._create_aggregator(stage_idx),
            )
            self._executors[stage_name] = executor
            
            # Run scatter
            result = executor.scatter_execute(
                tool_id=stage_idx,
                input_files=current_files,
                base_command=command,
                parameters=params,
                output_dir=stage_output_dir,
            )
            
            self._results[stage_name] = result
            
            # Prepare input files for next stage
            current_files = [
                task.output_file
                for task in result.results
                if task.status == "completed" and task.output_file
            ]
            
            if not current_files:
                logger.warning(f"Stage {stage_name} produced no output files")
                break
        
        return self._results
    
    def _create_aggregator(self, stage_idx: int) -> Callable[[List[Any]], Any]:
        """Create aggregator function for a stage."""
        def aggregator(results: List[Any]) -> Dict[str, Any]:
            return {
                'stage': stage_idx,
                'result_count': len(results),
                'results': results,
            }
        return aggregator
    
    def get_results(self) -> Dict[str, ScatterResult]:
        """Get all pipeline results."""
        return self._results


# Default aggregator functions
def merge_outputs(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate results by merging output files."""
    merged = {
        'files': [],
        'total_count': len(results),
    }
    
    for result in results:
        if 'output' in result:
            merged['files'].append(result['output'])
    
    return merged


def summarize_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Summarize results with statistics."""
    return {
        'total': len(results),
        'files': results,
    }
