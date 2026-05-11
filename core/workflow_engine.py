"""Workflow composition engine for Virometrics platform.

Supports tool chaining, workflow DAG structure, and JSON serialization.
"""

import json
import uuid
import sqlite3
import os
import logging
from typing import Dict, Any, List, Optional, Set
from collections import deque

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'virometrics.db')


class WorkflowNode:
    """Represents a node in the workflow DAG."""

    def __init__(self, node_id: str, tool_id: int, name: Optional[str] = None,
                 config: Optional[Dict[str, Any]] = None,
                 x: int = 0, y: int = 0):
        self.node_id = node_id
        self.tool_id = tool_id
        self.name = name or f"Node_{node_id}"
        self.config = config or {}
        self.x = x
        self.y = y
        self.inputs: List[str] = []
        self.outputs: List[str] = []

    def to_dict(self) -> Dict[str, Any]:
        """Convert node to dictionary for serialization."""
        return {
            'node_id': self.node_id,
            'tool_id': self.tool_id,
            'name': self.name,
            'config': self.config,
            'x': self.x,
            'y': self.y,
            'inputs': self.inputs,
            'outputs': self.outputs
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WorkflowNode':
        """Create node from dictionary."""
        node = cls(
            node_id=data['node_id'],
            tool_id=data['tool_id'],
            name=data.get('name'),
            config=data.get('config', {}),
            x=data.get('x', 0),
            y=data.get('y', 0)
        )
        node.inputs = data.get('inputs', [])
        node.outputs = data.get('outputs', [])
        return node


class WorkflowConnection:
    """Represents a connection between two workflow nodes."""

    def __init__(self, connection_id: str, source_node_id: str,
                 source_output: str, target_node_id: str,
                 target_input: str):
        self.connection_id = connection_id
        self.source_node_id = source_node_id
        self.source_output = source_output
        self.target_node_id = target_node_id
        self.target_input = target_input

    def to_dict(self) -> Dict[str, Any]:
        """Convert connection to dictionary for serialization."""
        return {
            'connection_id': self.connection_id,
            'source_node_id': self.source_node_id,
            'source_output': self.source_output,
            'target_node_id': self.target_node_id,
            'target_input': self.target_input
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WorkflowConnection':
        """Create connection from dictionary."""
        return cls(
            connection_id=data['connection_id'],
            source_node_id=data['source_node_id'],
            source_output=data['source_output'],
            target_node_id=data['target_node_id'],
            target_input=data['target_input']
        )


class WorkflowDAG:
    """Directed Acyclic Graph representation of a workflow."""

    def __init__(self, workflow_id: Optional[int] = None,
                 name: str = "Untitled Workflow",
                 description: Optional[str] = None):
        self.workflow_id = workflow_id
        self.name = name
        self.description = description or ""
        self.nodes: Dict[str, WorkflowNode] = {}
        self.connections: List[WorkflowConnection] = []
        self.created_at: Optional[str] = None
        self.updated_at: Optional[str] = None

    def add_node(self, node: WorkflowNode) -> None:
        """Add a node to the workflow DAG."""
        if node.node_id in self.nodes:
            logger.warning(f"Node {node.node_id} already exists, updating")
        self.nodes[node.node_id] = node
        self.updated_at = None

    def remove_node(self, node_id: str) -> None:
        """Remove a node and its connections from the workflow DAG."""
        if node_id not in self.nodes:
            raise KeyError(f"Node {node_id} not found")
        
        # Remove connections involving this node
        self.connections = [
            c for c in self.connections
            if c.source_node_id != node_id and c.target_node_id != node_id
        ]
        
        del self.nodes[node_id]
        self.updated_at = None

    def add_connection(self, connection: WorkflowConnection) -> None:
        """Add a connection between nodes."""
        # Validate nodes exist
        if connection.source_node_id not in self.nodes:
            raise ValueError(f"Source node {connection.source_node_id} not found")
        if connection.target_node_id not in self.nodes:
            raise ValueError(f"Target node {connection.target_node_id} not found")
        
        self.connections.append(connection)
        self.updated_at = None

    def remove_connection(self, connection_id: str) -> None:
        """Remove a connection from the workflow DAG."""
        self.connections = [
            c for c in self.connections
            if c.connection_id == connection_id
        ]
        self.updated_at = None

    def get_successors(self, node_id: str) -> List[WorkflowNode]:
        """Get all successor nodes (nodes that receive output from this node)."""
        successors = []
        for conn in self.connections:
            if conn.source_node_id == node_id:
                successors.append(self.nodes[conn.target_node_id])
        return successors

    def get_predecessors(self, node_id: str) -> List[WorkflowNode]:
        """Get all predecessor nodes (nodes that send input to this node)."""
        predecessors = []
        for conn in self.connections:
            if conn.target_node_id == node_id:
                predecessors.append(self.nodes[conn.source_node_id])
        return predecessors

    def get_root_nodes(self) -> List[WorkflowNode]:
        """Get all root nodes (nodes with no predecessors)."""
        return [node for node in self.nodes.values() 
                if not self.get_predecessors(node.node_id)]

    def get_leaf_nodes(self) -> List[WorkflowNode]:
        """Get all leaf nodes (nodes with no successors)."""
        return [node for node in self.nodes.values()
                if not self.get_successors(node.node_id)]

    def is_acyclic(self) -> bool:
        """Check if the DAG is acyclic using topological sort."""
        visited = set()
        rec_stack = set()
        
        def has_cycle(node_id: str) -> bool:
            visited.add(node_id)
            rec_stack.add(node_id)
            
            for successor in self.get_successors(node_id):
                if successor.node_id not in visited:
                    if has_cycle(successor.node_id):
                        return True
                elif successor.node_id in rec_stack:
                    return True
            
            rec_stack.remove(node_id)
            return False
        
        for node_id in self.nodes:
            if node_id not in visited:
                if has_cycle(node_id):
                    return False
        return True

    def topological_sort(self) -> List[WorkflowNode]:
        """Return nodes in topological order (execution order)."""
        if not self.is_acyclic():
            raise ValueError("Workflow contains cycles")
        
        in_degree = {node_id: 0 for node_id in self.nodes}
        for conn in self.connections:
            in_degree[conn.target_node_id] += 1
        
        queue = deque([node_id for node_id, degree in in_degree.items() if degree == 0])
        result = []
        
        while queue:
            node_id = queue.popleft()
            result.append(self.nodes[node_id])
            
            for successor in self.get_successors(node_id):
                in_degree[successor.node_id] -= 1
                if in_degree[successor.node_id] == 0:
                    queue.append(successor.node_id)
        
        return result

    def to_dict(self) -> Dict[str, Any]:
        """Convert workflow DAG to dictionary for serialization."""
        return {
            'workflow_id': self.workflow_id,
            'name': self.name,
            'description': self.description,
            'nodes': [node.to_dict() for node in self.nodes.values()],
            'connections': [conn.to_dict() for conn in self.connections],
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WorkflowDAG':
        """Create workflow DAG from dictionary."""
        workflow = cls(
            workflow_id=data.get('workflow_id'),
            name=data.get('name', 'Untitled Workflow'),
            description=data.get('description')
        )
        workflow.created_at = data.get('created_at')
        workflow.updated_at = data.get('updated_at')
        
        for node_data in data.get('nodes', []):
            workflow.add_node(WorkflowNode.from_dict(node_data))
        
        for conn_data in data.get('connections', []):
            workflow.add_connection(WorkflowConnection.from_dict(conn_data))
        
        return workflow

    def to_json(self, indent: int = 2) -> str:
        """Serialize workflow DAG to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, json_str: str) -> 'WorkflowDAG':
        """Deserialize workflow DAG from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)


class WorkflowEngine:
    """Main workflow composition and execution engine."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.path.abspath(DB_PATH)
        self.workflows: Dict[int, WorkflowDAG] = {}

    def _get_connection(self):
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def create_workflow(self, name: str, 
                       description: Optional[str] = None) -> WorkflowDAG:
        """Create a new workflow DAG."""
        workflow = WorkflowDAG(name=name, description=description)
        self.workflows[id(workflow)] = workflow
        return workflow

    def save_workflow(self, workflow: WorkflowDAG) -> int:
        """Save workflow to database. Returns workflow ID."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Insert workflow
            cursor.execute(
                """INSERT INTO workflows (name, description, workflow_json, created_at, updated_at)
                   VALUES (?, ?, ?, datetime('now'), datetime('now'))""",
                (workflow.name, workflow.description, workflow.to_json())
            )
            workflow_id = cursor.lastrowid
            workflow.workflow_id = workflow_id
            
            # Save nodes
            for node in workflow.nodes.values():
                cursor.execute(
                    """INSERT INTO workflow_nodes 
                       (workflow_id, node_id, tool_id, node_name, config_json, position_x, position_y)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (workflow_id, node.node_id, node.tool_id, node.name,
                     json.dumps(node.config), node.x, node.y)
                )
            
            # Save connections
            for conn in workflow.connections:
                cursor.execute(
                    """INSERT INTO workflow_connections
                       (workflow_id, connection_id, source_node_id, source_output,
                        target_node_id, target_input)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (workflow_id, conn.connection_id, conn.source_node_id,
                     conn.source_output, conn.target_node_id, conn.target_input)
                )
            
            conn.commit()
            return workflow_id
        finally:
            conn.close()

    def load_workflow(self, workflow_id: int) -> Optional[WorkflowDAG]:
        """Load workflow from database by ID."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Get workflow
            cursor.execute("SELECT * FROM workflows WHERE id=?", (workflow_id,))
            row = cursor.fetchone()
            if not row:
                return None
            
            workflow = WorkflowDAG.from_json(row['workflow_json'])
            workflow.workflow_id = row['id']
            workflow.created_at = row['created_at']
            workflow.updated_at = row['updated_at']
            
            return workflow
        finally:
            conn.close()

    def list_workflows(self) -> List[Dict[str, Any]]:
        """List all workflows in the database."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id, name, description, created_at, updated_at, 
                          created_by, is_public
                   FROM workflows ORDER BY created_at DESC"""
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def delete_workflow(self, workflow_id: int) -> bool:
        """Delete workflow from database."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM workflows WHERE id=?", (workflow_id,))
            conn.commit()
            
            if workflow_id in self.workflows:
                del self.workflows[workflow_id]
            
            return cursor.rowcount > 0
        finally:
            conn.close()

    def validate_workflow(self, workflow: WorkflowDAG) -> List[str]:
        """Validate workflow DAG and return list of errors."""
        errors = []
        
        if not workflow.nodes:
            errors.append("Workflow has no nodes")
        
        if not workflow.is_acyclic():
            errors.append("Workflow contains cycles")
        
        # Check all referenced nodes exist
        for conn in workflow.connections:
            if conn.source_node_id not in workflow.nodes:
                errors.append(f"Connection references missing source node: {conn.source_node_id}")
            if conn.target_node_id not in workflow.nodes:
                errors.append(f"Connection references missing target node: {conn.target_node_id}")
        
        return errors

    def export_workflow(self, workflow: WorkflowDAG, filepath: str) -> None:
        """Export workflow to JSON file."""
        with open(filepath, 'w') as f:
            f.write(workflow.to_json())

    def import_workflow(self, filepath: str) -> WorkflowDAG:
        """Import workflow from JSON file."""
        with open(filepath, 'r') as f:
            return WorkflowDAG.from_json(f.read())
