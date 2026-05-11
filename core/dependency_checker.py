"""Dependency checking and management for Virometrics platform."""

import subprocess
import logging
import os
from typing import Optional, Dict, List, Tuple

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Path to database
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'virometrics.db')


class DependencyChecker:
    """Check and manage tool dependencies."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.path.abspath(DB_PATH)

    def _get_connection(self):
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def check_dependency(self, dep_id: int) -> Dict[str, any]:
        """
        Check if a dependency is installed.
        Returns: {installed: bool, version: str, path: str, status: str}
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM dependencies WHERE id=?",
                (dep_id,)
            )
            dep = cursor.fetchone()
            if not dep:
                return {'installed': False, 'status': 'not_found'}

            # Try check command first
            check_cmd = dep['check_command']
            if check_cmd:
                try:
                    result = subprocess.run(
                        check_cmd,
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    if result.returncode == 0:
                        version = self._extract_version(result.stdout + result.stderr)
                        return {
                            'installed': True,
                            'version': version,
                            'path': self._find_path(dep['name']),
                            'status': 'installed',
                            'raw_output': result.stdout[:200]
                        }
                except Exception as e:
                    logger.warning(f"Check command failed for {dep['name']}: {e}")

            # Fallback: try which/command -v
            found = self._find_path(dep['name'])
            if found:
                return {
                    'installed': True,
                    'version': 'unknown',
                    'path': found,
                    'status': 'installed'
                }

            return {'installed': False, 'status': 'missing'}

        finally:
            conn.close()

    def _find_path(self, name: str) -> Optional[str]:
        """Find the path of an executable."""
        try:
            result = subprocess.run(
                f"which {name}",
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except:
            pass

        # Try command -v as fallback
        try:
            result = subprocess.run(
                f"command -v {name}",
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except:
            pass

        return None

    def _extract_version(self, output: str) -> str:
        """Extract version string from command output."""
        import re
        # Common version patterns
        patterns = [
            r'version\s*[:\s]\s*([0-9]\S*)',
            r'([0-9]+\.[0-9]+\.[0-9]+)',
            r'([0-9]+\.[0-9]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, output, re.IGNORECASE)
            if match:
                return match.group(1)
        return 'unknown'

    def install_dependency(self, dep_id: int) -> Tuple[bool, str]:
        """
        Install a dependency using its package manager.
        Returns: (success, message)
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM dependencies WHERE id=?",
                (dep_id,)
            )
            dep = cursor.fetchone()
            if not dep:
                return False, "Dependency not found"

            install_cmd = dep['install_command']
            if not install_cmd:
                return False, f"No install command for {dep['name']}"

            # Check if already installed
            check = self.check_dependency(dep_id)
            if check['installed']:
                return True, f"{dep['name']} is already installed"

            # Run install command
            logger.info(f"Installing {dep['name']}: {install_cmd}")
            try:
                result = subprocess.run(
                    install_cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 min timeout for installs
                )

                if result.returncode == 0:
                    # Update installed_dependencies table
                    self._update_installed(conn, dep_id, check.get('version', 'unknown'))
                    return True, f"Successfully installed {dep['name']}"
                else:
                    return False, f"Install failed: {result.stderr[:200]}"

            except subprocess.TimeoutExpired:
                return False, "Install timed out (5 minutes)"
            except Exception as e:
                return False, f"Install error: {str(e)}"

        finally:
            conn.close()

    def _update_installed(self, conn, dep_id: int, version: str):
        """Update the installed_dependencies table."""
        cursor = conn.cursor()
        cursor.execute(
            """SELECT id FROM installed_dependencies WHERE dependency_id=?""",
            (dep_id,)
        )
        existing = cursor.fetchone()

        if existing:
            cursor.execute(
                """UPDATE installed_dependencies
                   SET installed_version=?, installed_at=datetime('now'),
                       status='installed'
                   WHERE dependency_id=?""",
                (version, dep_id)
            )
        else:
            cursor.execute(
                """INSERT INTO installed_dependencies
                   (dependency_id, installed_version, status)
                   VALUES (?, ?, 'installed')""",
                (dep_id, version)
            )
        conn.commit()

    def scan_tool_dependencies(self, tool_id: int) -> List[Dict]:
        """
        Scan a tool's metadata and register its dependencies.
        Returns list of registered dependencies.
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # Get tool info
            cursor.execute("SELECT * FROM tools WHERE id=?", (tool_id,))
            tool = cursor.fetchone()
            if not tool:
                return []

            registered = []

            # Check packages_needed field
            packages = tool['packages_needed']
            if packages:
                try:
                    import json
                    pkgs = json.loads(packages) if isinstance(packages, str) else packages
                    if isinstance(pkgs, dict):
                        # Handle different formats
                        if 'bioconda' in pkgs:
                            dep_id = self._register_dependency(conn, {
                                'name': pkgs['bioconda'],
                                'package_manager': 'bioconda',
                                'install_command': f"conda install -y -c bioconda {pkgs['bioconda']}"
                            })
                            if dep_id:
                                self._link_tool_dep(conn, tool_id, dep_id)
                                registered.append({'name': pkgs['bioconda'], 'source': 'bioconda'})
                        if 'pip' in pkgs:
                            for pkg in (pkgs['pip'] if isinstance(pkgs['pip'], list) else [pkgs['pip']]):
                                dep_id = self._register_dependency(conn, {
                                    'name': pkg,
                                    'package_manager': 'pip',
                                    'install_command': f"pip install {pkg}"
                                })
                                if dep_id:
                                    self._link_tool_dep(conn, tool_id, dep_id)
                                    registered.append({'name': pkg, 'source': 'pip'})
                except Exception as e:
                    logger.error(f"Error parsing packages for tool {tool['name']}: {e}")

            # Check package_manager field
            pkg_mgr = tool['package_manager']
            if pkg_mgr and pkg_mgr.lower() == 'conda':
                # Try to find in dependencies table
                cursor.execute(
                    "SELECT id FROM dependencies WHERE name=? AND package_manager='conda'",
                    (tool['name'],)
                )
                if not cursor.fetchone():
                    dep_id = self._register_dependency(conn, {
                        'name': tool['name'],
                        'package_manager': 'conda',
                        'install_command': f"conda install -y -c bioconda {tool['name']}",
                        'description': tool['description']
                    })
                    if dep_id:
                        self._link_tool_dep(conn, tool_id, dep_id)
                        registered.append({'name': tool['name'], 'source': 'package_manager'})

            conn.commit()
            return registered

        finally:
            conn.close()

    def _register_dependency(self, conn, dep_info: Dict) -> Optional[int]:
        """Register a dependency in the database. Returns dependency ID."""
        cursor = conn.cursor()
        try:
            cursor.execute(
                """INSERT OR IGNORE INTO dependencies
                   (name, version, package_manager, install_command, description)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    dep_info['name'],
                    dep_info.get('version'),
                    dep_info['package_manager'],
                    dep_info.get('install_command'),
                    dep_info.get('description', '')
                )
            )
            if cursor.lastrowid:
                return cursor.lastrowid

            # Get existing ID
            cursor.execute(
                "SELECT id FROM dependencies WHERE name=? AND package_manager=?",
                (dep_info['name'], dep_info['package_manager'])
            )
            row = cursor.fetchone()
            return row['id'] if row else None

        except Exception as e:
            logger.error(f"Error registering dependency: {e}")
            return None

    def _link_tool_dep(self, conn, tool_id: int, dep_id: int):
        """Link a tool to a dependency."""
        try:
            conn.execute(
                """INSERT OR IGNORE INTO tool_dependencies (tool_id, dependency_id)
                   VALUES (?, ?)""",
                (tool_id, dep_id)
            )
        except Exception as e:
            logger.error(f"Error linking tool {tool_id} to dep {dep_id}: {e}")
