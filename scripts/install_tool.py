#!/usr/bin/env python3
"""
Tool Installer for Virometrics.
Installs tools with dependency resolution and version control.
"""

import os
import sys
import json
import sqlite3
import subprocess
import hashlib
import shutil
import tarfile
import zipfile
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ToolInstallationSpec:
    """Specification for tool installation."""
    name: str
    version: str
    source: str  # bioconda, system, git, tarball
    source_url: Optional[str] = None
    install_path: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)
    post_install_commands: List[str] = field(default_factory=list)
    environment_vars: Dict[str, str] = field(default_factory=dict)


@dataclass
class ToolInstallation:
    """Result of tool installation."""
    installation_id: int
    tool_definition_id: int
    name: str
    version: str
    install_path: str
    installed_at: str
    status: str  # installed, error, rollback
    checksum: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    rollback_version: Optional[str] = None


class ToolInstaller:
    """Installer for bioinformatics tools with version control."""
    
    # Default installation directory
    DEFAULT_INSTALL_DIR = '/home/ihcm-ubuntu/Virometrics/data/tools'
    
    def __init__(self, db_path: str, 
                 install_dir: Optional[str] = None):
        """
        Initialize tool installer.
        
        Args:
            db_path: Path to the Virometrics database
            install_dir: Base directory for tool installations
        """
        self.db_path = db_path
        self.install_dir = Path(install_dir or self.DEFAULT_INSTALL_DIR)
        self._ensure_install_dir()
    
    def _ensure_install_dir(self) -> None:
        """Ensure installation directory exists."""
        self.install_dir.mkdir(parents=True, exist_ok=True)
    
    def _calculate_checksum(self, file_path: str) -> str:
        """Calculate SHA256 checksum of a file."""
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b''):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    def _calculate_dir_checksum(self, dir_path: str) -> str:
        """Calculate checksum of directory contents."""
        sha256 = hashlib.sha256()
        for root, dirs, files in os.walk(dir_path):
            for filename in sorted(files):
                file_path = os.path.join(root, filename)
                sha256.update(filename.encode())
                sha256.update(self._calculate_checksum(file_path).encode())
        return sha256.hexdigest()
    
    def resolve_dependencies(self, tool_name: str, 
                             tool_version: str) -> List[str]:
        """
        Resolve tool dependencies from the database.
        
        Returns:
            List of dependency names in installation order
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            
            # Get tool definition
            cursor.execute("""
                SELECT id, dependencies_json 
                FROM tool_definitions 
                WHERE name = ? AND version = ?
            """, (tool_name, tool_version))
            
            row = cursor.fetchone()
            if not row:
                return []
            
            dependencies = json.loads(row['dependencies_json'] or '[]')
            return dependencies
        finally:
            conn.close()
    
    def check_installation(self, tool_name: str, 
                           version: str) -> Optional[Dict[str, Any]]:
        """
        Check if a tool version is already installed.
        
        Returns:
            Installation info dict if found, None otherwise
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT ti.*, td.name as tool_name
                FROM tool_installations ti
                JOIN tool_definitions td ON ti.tool_definition_id = td.id
                WHERE td.name = ? AND ti.version = ?
            """, (tool_name, version))
            
            row = cursor.fetchone()
            if row:
                return {
                    'installation_id': row['id'],
                    'tool_definition_id': row['tool_definition_id'],
                    'name': row['tool_name'],
                    'version': row['version'],
                    'install_path': row['install_path'],
                    'status': row['status'],
                    'installed_at': row['installed_at']
                }
            return None
        finally:
            conn.close()
    
    def install_tool(self, spec: ToolInstallationSpec) -> ToolInstallation:
        """
        Install a tool with the given specification.
        
        Args:
            spec: Installation specification
            
        Returns:
            ToolInstallation result
        """
        # Check for existing installation
        existing = self.check_installation(spec.name, spec.version)
        
        if existing:
            return ToolInstallation(
                installation_id=existing['installation_id'],
                tool_definition_id=existing['tool_definition_id'],
                name=spec.name,
                version=spec.version,
                install_path=existing['install_path'],
                installed_at=existing['installed_at'],
                status='already_installed',
                metadata={'duplicate': True}
            )
        
        # Resolve and install dependencies first
        installed_deps = []
        for dep_name in spec.dependencies:
            # Simple dependency resolution (could be enhanced)
            dep_spec = ToolInstallationSpec(
                name=dep_name,
                version='latest',
                source='bioconda'
            )
            try:
                dep_install = self.install_tool(dep_spec)
                installed_deps.append(dep_install.install_path)
            except Exception as e:
                metadata = {'dependency_error': str(e)}
        
        # Determine install path
        install_path = spec.install_path or str(
            self.install_dir / spec.name / spec.version
        )
        
        # Install tool based on source
        try:
            if spec.source == 'bioconda':
                install_path = self._install_bioconda(spec)
            elif spec.source == 'system':
                install_path = self._install_system(spec)
            elif spec.source == 'git':
                install_path = self._install_git(spec)
            elif spec.source == 'tarball':
                install_path = self._install_tarball(spec)
            else:
                raise ValueError(f"Unknown source type: {spec.source}")
            
            # Run post-install commands
            post_install_results = []
            for cmd in spec.post_install_commands:
                result = subprocess.run(
                    cmd.format(install_path=install_path, **spec.environment_vars),
                    shell=True,
                    capture_output=True,
                    text=True
                )
                post_install_results.append({
                    'command': cmd,
                    'return_code': result.returncode,
                    'stdout': result.stdout,
                    'stderr': result.stderr
                })
            
            # Calculate checksum
            checksum = self._calculate_dir_checksum(install_path)
            
            # Create installation record
            metadata = {
                'source': spec.source,
                'source_url': spec.source_url,
                'dependencies': installed_deps,
                'environment_vars': spec.environment_vars,
                'post_install': post_install_results
            }
            
            installation = self._create_installation_record(
                tool_name=spec.name,
                version=spec.version,
                install_path=install_path,
                checksum=checksum,
                metadata=metadata
            )
            
            return installation
            
        except Exception as e:
            # Rollback installation
            rollback_version = self._rollback_installation(spec.name, spec.version)
            
            return ToolInstallation(
                installation_id=0,
                tool_definition_id=0,
                name=spec.name,
                version=spec.version,
                install_path=install_path,
                installed_at=datetime.utcnow().isoformat(),
                status='error',
                metadata={'error': str(e)},
                rollback_version=rollback_version
            )
    
    def _install_bioconda(self, spec: ToolInstallationSpec) -> str:
        """Install tool from bioconda."""
        install_path = str(self.install_dir / spec.name / spec.version)
        
        # Create conda environment
        cmd = f"conda create -y -p {install_path} -c bioconda {spec.name}={spec.version}"
        
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode != 0:
            raise RuntimeError(f"Conda install failed: {result.stderr}")
        
        return install_path
    
    def _install_system(self, spec: ToolInstallationSpec) -> str:
        """Install tool from system package manager."""
        install_path = str(self.install_dir / spec.name / spec.version)
        
        # Install system package
        cmd = f"apt-get install -y {spec.name}"
        
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode != 0:
            raise RuntimeError(f"System install failed: {result.stderr}")
        
        return install_path
    
    def _install_git(self, spec: ToolInstallationSpec) -> str:
        """Install tool from git repository."""
        install_path = str(self.install_dir / spec.name / spec.version)
        
        # Clone repository
        cmd = f"git clone {spec.source_url} {install_path}"
        if spec.version != 'main' and spec.version != 'master':
            cmd += f" --branch {spec.version}"
        
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode != 0:
            raise RuntimeError(f"Git clone failed: {result.stderr}")
        
        return install_path
    
    def _install_tarball(self, spec: ToolInstallationSpec) -> str:
        """Install tool from tarball."""
        install_path = str(self.install_dir / spec.name / spec.version)
        os.makedirs(install_path, exist_ok=True)
        
        # Extract tarball
        with tarfile.open(spec.source_url, 'r:*') as tar:
            tar.extractall(path=install_path)
        
        return install_path
    
    def _create_installation_record(self, tool_name: str,
                                     version: str,
                                     install_path: str,
                                     checksum: str,
                                     metadata: Dict[str, Any]) -> ToolInstallation:
        """Create installation record in database."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            
            # Get or create tool definition
            cursor.execute("""
                SELECT id FROM tool_definitions
                WHERE name = ? AND version = ?
            """, (tool_name, version))
            
            row = cursor.fetchone()
            if row:
                tool_definition_id = row['id']
            else:
                # Create new tool definition
                cursor.execute("""
                    INSERT INTO tool_definitions (
                        tool_id, name, version, source, source_url,
                        install_path, is_active, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                """, (
                    len(cursor.execute("SELECT * FROM tool_definitions").fetchall()) + 1,
                    tool_name,
                    version,
                    'custom',
                    None,
                    install_path,
                    json.dumps(metadata)
                ))
                tool_definition_id = cursor.lastrowid
            
            # Create installation record
            cursor.execute("""
                INSERT INTO tool_installations (
                    tool_definition_id, version, install_path,
                    checksum, metadata_json
                ) VALUES (?, ?, ?, ?, ?)
            """, (
                tool_definition_id,
                version,
                install_path,
                checksum,
                json.dumps(metadata)
            ))
            
            installation_id = cursor.lastrowid
            conn.commit()
            
            return ToolInstallation(
                installation_id=installation_id,
                tool_definition_id=tool_definition_id,
                name=tool_name,
                version=version,
                install_path=install_path,
                installed_at=datetime.utcnow().isoformat(),
                status='installed',
                checksum=checksum,
                metadata=metadata
            )
        finally:
            conn.close()
    
    def _rollback_installation(self, tool_name: str, 
                                version: str) -> Optional[str]:
        """Rollback to previous version of tool."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT version, install_path
                FROM tool_installations ti
                JOIN tool_definitions td ON ti.tool_definition_id = td.id
                WHERE td.name = ? AND ti.status = 'installed'
                ORDER BY ti.installed_at DESC
                LIMIT 1
            """, (tool_name,))
            
            row = cursor.fetchone()
            if row and row['version'] != version:
                return row['version']
            return None
        finally:
            conn.close()
    
    def list_installations(self, tool_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all tool installations, optionally filtered by name."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            
            if tool_name:
                cursor.execute("""
                    SELECT ti.*, td.name as tool_name
                    FROM tool_installations ti
                    JOIN tool_definitions td ON ti.tool_definition_id = td.id
                    WHERE td.name = ?
                    ORDER BY ti.installed_at DESC
                """, (tool_name,))
            else:
                cursor.execute("""
                    SELECT ti.*, td.name as tool_name
                    FROM tool_installations ti
                    JOIN tool_definitions td ON ti.tool_definition_id = td.id
                    ORDER BY ti.installed_at DESC
                """)
            
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()
    
    def uninstall_tool(self, tool_name: str, 
                       version: str,
                       remove_files: bool = True) -> bool:
        """
        Uninstall a tool.
        
        Args:
            tool_name: Name of the tool
            version: Version to uninstall
            remove_files: Whether to remove installation files
            
        Returns:
            True if successful
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            
            # Get installation info
            cursor.execute("""
                SELECT id, install_path
                FROM tool_installations ti
                JOIN tool_definitions td ON ti.tool_definition_id = td.id
                WHERE td.name = ? AND ti.version = ?
            """, (tool_name, version))
            
            row = cursor.fetchone()
            if not row:
                return False
            
            install_path = row['install_path']
            
            # Update status
            cursor.execute("""
                UPDATE tool_installations
                SET status = 'removed'
                WHERE id = ?
            """, (row['id'],))
            
            conn.commit()
            
            # Remove files if requested
            if remove_files and os.path.exists(install_path):
                shutil.rmtree(install_path)
            
            return True
        finally:
            conn.close()


def main():
    """Main function for tool installation."""
    db_path = sys.argv[1] if len(sys.argv) > 1 else '/home/ihcm-ubuntu/Virometrics/data/virometrics.db'
    
    print(f"Tool Installer for Virometrics")
    print(f"Database: {db_path}")
    print("=" * 50)
    
    installer = ToolInstaller(db_path)
    
    # Example: Install a tool
    spec = ToolInstallationSpec(
        name='fastqc',
        version='0.11.9',
        source='bioconda',
        dependencies=['jdk']
    )
    
    print(f"\nInstalling {spec.name} {spec.version}...")
    installation = installer.install_tool(spec)
    
    print(f"Installation status: {installation.status}")
    print(f"Install path: {installation.install_path}")
    print(f"Checksum: {installation.checksum}")
    
    # List all installations
    print("\nAll installations:")
    installations = installer.list_installations()
    for inst in installations:
        print(f"  {inst['tool_name']} {inst['version']} - {inst['status']}")


if __name__ == '__main__':
    main()
