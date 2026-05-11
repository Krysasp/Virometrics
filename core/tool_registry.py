"""
Tool Registry for Virometrics.
Provides tool definition, registration, and tracking capabilities.
"""

import sqlite3
import json
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path


@dataclass
class ToolDefinition:
    """Represents a tool definition with version, source, and compatibility info."""
    
    tool_id: int
    name: str
    version: str
    description: str
    source: str  # e.g., 'bioconda', 'system', 'git'
    source_url: Optional[str] = None
    install_path: Optional[str] = None
    compatibility: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    parameters: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    input_formats: List[str] = field(default_factory=list)
    output_formats: List[str] = field(default_factory=list)
    is_active: bool = True
    registered_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ToolDefinition':
        """Create from dictionary representation."""
        return cls(**data)


@dataclass
class ToolInstallation:
    """Represents an installed tool instance."""
    
    installation_id: int
    tool_definition_id: int
    version: str
    install_path: str
    installed_at: str
    last_verified: Optional[str] = None
    status: str = 'installed'  # installed, active, deprecated, removed
    checksum: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """Represents validation result for a tool."""
    
    validation_id: int
    tool_definition_id: int
    test_dataset: str
    status: str  # passed, failed, warning
    execution_time: float
    output_checksum: Optional[str] = None
    expected_output: Optional[str] = None
    actual_output: Optional[str] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    validated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class ToolRegistry:
    """Registry for tracking installed tools with version control and validation."""
    
    def __init__(self, db_path: str):
        """Initialize the tool registry with a database path."""
        self.db_path = db_path
        self._ensure_tables()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _ensure_tables(self) -> None:
        """Ensure required tables exist in the database."""
        conn = self._get_connection()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS tool_definitions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    version TEXT NOT NULL,
                    description TEXT,
                    source TEXT NOT NULL,
                    source_url TEXT,
                    install_path TEXT,
                    compatibility_json TEXT,
                    dependencies_json TEXT,
                    parameters_json TEXT,
                    input_formats_json TEXT,
                    output_formats_json TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    registered_at TEXT DEFAULT (datetime('now')),
                    metadata_json TEXT,
                    UNIQUE(tool_id, name, version)
                );
                CREATE INDEX IF NOT EXISTS idx_tool_defs_name ON tool_definitions(name);
                CREATE INDEX IF NOT EXISTS idx_tool_defs_version ON tool_definitions(version);
                
                CREATE TABLE IF NOT EXISTS tool_installations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_definition_id INTEGER NOT NULL,
                    version TEXT NOT NULL,
                    install_path TEXT NOT NULL,
                    installed_at TEXT DEFAULT (datetime('now')),
                    last_verified TEXT,
                    status TEXT DEFAULT 'installed',
                    checksum TEXT,
                    metadata_json TEXT,
                    FOREIGN KEY(tool_definition_id) REFERENCES tool_definitions(id) ON DELETE CASCADE,
                    UNIQUE(tool_definition_id, version, install_path)
                );
                CREATE INDEX IF NOT EXISTS idx_installations_def ON tool_installations(tool_definition_id);
                
                CREATE TABLE IF NOT EXISTS tool_validations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_definition_id INTEGER NOT NULL,
                    test_dataset TEXT NOT NULL,
                    status TEXT NOT NULL,
                    execution_time REAL,
                    output_checksum TEXT,
                    expected_output TEXT,
                    actual_output TEXT,
                    errors_json TEXT,
                    warnings_json TEXT,
                    validated_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY(tool_definition_id) REFERENCES tool_definitions(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_validations_def ON tool_validations(tool_definition_id);
                CREATE INDEX IF NOT EXISTS idx_validations_status ON tool_validations(status);
            """)
        finally:
            conn.close()
    
    def register_tool(self, definition: ToolDefinition) -> int:
        """
        Register a new tool definition.
        Returns the tool_definition_id.
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO tool_definitions (
                    tool_id, name, version, description, source, source_url,
                    install_path, compatibility_json, dependencies_json, parameters_json,
                    input_formats_json, output_formats_json, is_active, registered_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                definition.tool_id,
                definition.name,
                definition.version,
                definition.description,
                definition.source,
                definition.source_url,
                definition.install_path,
                json.dumps(definition.compatibility),
                json.dumps(definition.dependencies),
                json.dumps(definition.parameters),
                json.dumps(definition.input_formats),
                json.dumps(definition.output_formats),
                1 if definition.is_active else 0,
                definition.registered_at,
                json.dumps(definition.metadata)
            ))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()
    
    def unregister_tool(self, tool_definition_id: int, version: Optional[str] = None) -> bool:
        """
        Unregister a tool definition.
        If version is provided, only deprecate that version.
        Returns True if successful.
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            if version:
                cursor.execute("""
                    UPDATE tool_definitions
                    SET is_active = 0
                    WHERE id = ? AND version = ?
                """, (tool_definition_id, version))
            else:
                cursor.execute("""
                    UPDATE tool_definitions
                    SET is_active = 0
                    WHERE id = ?
                """, (tool_definition_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    
    def list_tools(self, name: Optional[str] = None, 
                   source: Optional[str] = None,
                   is_active: Optional[bool] = None) -> List[ToolDefinition]:
        """
        List registered tools with optional filters.
        Returns a list of ToolDefinition objects.
        """
        conn = self._get_connection()
        try:
            query = "SELECT * FROM tool_definitions WHERE 1=1"
            params = []
            
            if name:
                query += " AND name LIKE ?"
                params.append(f"%{name}%")
            if source:
                query += " AND source = ?"
                params.append(source)
            if is_active is not None:
                query += " AND is_active = ?"
                params.append(1 if is_active else 0)
            
            query += " ORDER BY name, version"
            
            cursor = conn.execute(query, params)
            tools = []
            for row in cursor.fetchall():
                definition = ToolDefinition(
                    tool_id=row['tool_id'],
                    name=row['name'],
                    version=row['version'],
                    description=row['description'],
                    source=row['source'],
                    source_url=row['source_url'],
                    install_path=row['install_path'],
                    compatibility=json.loads(row['compatibility_json'] or '{}'),
                    dependencies=json.loads(row['dependencies_json'] or '[]'),
                    parameters=json.loads(row['parameters_json'] or '{}'),
                    input_formats=json.loads(row['input_formats_json'] or '[]'),
                    output_formats=json.loads(row['output_formats_json'] or '[]'),
                    is_active=bool(row['is_active']),
                    registered_at=row['registered_at'],
                    metadata=json.loads(row['metadata_json'] or '{}')
                )
                tools.append(definition)
            return tools
        finally:
            conn.close()
    
    def get_tool_info(self, tool_definition_id: int, 
                      version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a tool.
        Returns tool definition with installation history and validation results.
        """
        conn = self._get_connection()
        try:
            # Get tool definition
            if version:
                cursor = conn.execute("""
                    SELECT * FROM tool_definitions
                    WHERE id = ? AND version = ?
                """, (tool_definition_id, version))
            else:
                cursor = conn.execute("""
                    SELECT * FROM tool_definitions
                    WHERE id = ?
                """, (tool_definition_id,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            # Get installations
            cursor = conn.execute("""
                SELECT * FROM tool_installations
                WHERE tool_definition_id = ?
                ORDER BY installed_at DESC
            """, (tool_definition_id,))
            installations = [
                {
                    'installation_id': r['id'],
                    'version': r['version'],
                    'install_path': r['install_path'],
                    'installed_at': r['installed_at'],
                    'status': r['status'],
                    'checksum': r['checksum']
                }
                for r in cursor.fetchall()
            ]
            
            # Get validation results
            cursor = conn.execute("""
                SELECT * FROM tool_validations
                WHERE tool_definition_id = ?
                ORDER BY validated_at DESC
                LIMIT 10
            """, (tool_definition_id,))
            validations = [
                {
                    'validation_id': r['id'],
                    'test_dataset': r['test_dataset'],
                    'status': r['status'],
                    'execution_time': r['execution_time'],
                    'validated_at': r['validated_at']
                }
                for r in cursor.fetchall()
            ]
            
            return {
                'definition': {
                    'tool_definition_id': row['id'],
                    'tool_id': row['tool_id'],
                    'name': row['name'],
                    'version': row['version'],
                    'description': row['description'],
                    'source': row['source'],
                    'source_url': row['source_url'],
                    'install_path': row['install_path'],
                    'compatibility': json.loads(row['compatibility_json'] or '{}'),
                    'dependencies': json.loads(row['dependencies_json'] or '[]'),
                    'parameters': json.loads(row['parameters_json'] or '{}'),
                    'input_formats': json.loads(row['input_formats_json'] or '[]'),
                    'output_formats': json.loads(row['output_formats_json'] or '[]'),
                    'is_active': bool(row['is_active']),
                    'registered_at': row['registered_at'],
                    'metadata': json.loads(row['metadata_json'] or '{}')
                },
                'installations': installations,
                'validations': validations
            }
        finally:
            conn.close()
    
    def add_validation_result(self, tool_definition_id: int, 
                              validation: ValidationResult) -> int:
        """Add a validation result for a tool."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO tool_validations (
                    tool_definition_id, test_dataset, status, execution_time,
                    output_checksum, expected_output, actual_output,
                    errors_json, warnings_json, validated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                tool_definition_id,
                validation.test_dataset,
                validation.status,
                validation.execution_time,
                validation.output_checksum,
                validation.expected_output,
                validation.actual_output,
                json.dumps(validation.errors),
                json.dumps(validation.warnings),
                validation.validated_at
            ))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()
    
    def add_installation(self, tool_definition_id: int,
                         installation: ToolInstallation) -> int:
        """Add a tool installation record."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO tool_installations (
                    tool_definition_id, version, install_path, installed_at,
                    last_verified, status, checksum, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                tool_definition_id,
                installation.version,
                installation.install_path,
                installation.installed_at,
                installation.last_verified,
                installation.status,
                installation.checksum,
                json.dumps(installation.metadata)
            ))
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()
    
    def validate_tool(self, tool_definition_id: int) -> ValidationResult:
        """
        Validate a tool with standard test datasets.
        Returns the validation result.
        """
        # This is a stub - actual validation logic would run here
        # For now, return a placeholder result
        return ValidationResult(
            validation_id=0,
            tool_definition_id=tool_definition_id,
            test_dataset='standard_test',
            status='pending',
            execution_time=0.0
        )
