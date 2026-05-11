"""Tool installer for autonomous setup of Virometrics tools."""

import os
import json
import logging
import subprocess
import shutil
from pathlib import Path
from typing import Optional, Dict, List, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class ToolInstaller:
    """Handle autonomous installation of bioinformatics tools."""

    def __init__(self, db_path: Optional[str] = None, base_dir: Optional[str] = None):
        self.db_path = db_path
        self.base_dir = Path(base_dir) if base_dir else Path(__file__).parent.parent
        self.tools_dir = self.base_dir / 'data' / 'tools'
        
        # Ensure tools directory exists
        self.tools_dir.mkdir(parents=True, exist_ok=True)

    def _get_connection(self):
        """Get database connection."""
        import sqlite3
        conn = sqlite3.connect(self.db_path or os.path.join(self.base_dir, 'data', 'virometrics.db'))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def get_tool_install_path(self, tool_id: int, tool_name: str) -> Path:
        """Get installation path for a tool."""
        safe_name = tool_name.replace(' ', '_').lower()
        tool_dir = self.tools_dir / safe_name
        tool_dir.mkdir(parents=True, exist_ok=True)
        return tool_dir

    def get_installation_status(self, tool_id: int) -> Dict[str, Any]:
        """Check if a tool is installed and its status."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, name, package_manager, packages_needed FROM tools WHERE id = ?",
                (tool_id,)
            )
            tool = cursor.fetchone()
            
            if not tool:
                return {'exists': False, 'error': 'Tool not found'}
            
            tool_name = tool['name']
            safe_name = tool_name.replace(' ', '_').lower()
            tool_dir = self.tools_dir / safe_name
            
            # Check if tool directory exists and has content
            is_installed = tool_dir.exists() and any(tool_dir.iterdir())
            
            # Check package manager availability
            pkg_manager = tool['package_manager'] or 'unknown'
            pkg_info = json.loads(tool['packages_needed'] or '{}')
            
            status = {
                'tool_id': tool_id,
                'tool_name': tool_name,
                'package_manager': pkg_manager,
                'is_installed': is_installed,
                'install_path': str(tool_dir),
                'packages': pkg_info,
                'can_auto_install': self._can_auto_install(pkg_manager, pkg_info)
            }
            
            # Check if packages are actually installed
            if is_installed:
                status['packages_installed'] = self._check_packages_installed(pkg_manager, pkg_info)
            else:
                status['packages_installed'] = []
            
            return status
            
        finally:
            conn.close()

    def _can_auto_install(self, pkg_manager: str, pkg_info: Dict) -> bool:
        """Determine if tool can be auto-installed."""
        if not pkg_manager or pkg_manager.lower() == 'unknown':
            return False
        
        # Check if we have installation information
        if pkg_manager.lower() == 'conda':
            return bool(pkg_info.get('bioconda') or pkg_info.get('dependencies'))
        elif pkg_manager.lower() == 'pip':
            return bool(pkg_info.get('pip_package'))
        elif pkg_manager.lower() == 'source':
            return bool(pkg_info.get('repository') or pkg_info.get('install_command'))
        
        return False

    def _check_packages_installed(self, pkg_manager: str, pkg_info: Dict) -> List[str]:
        """Check which packages are currently installed."""
        installed = []
        
        if pkg_manager.lower() == 'conda':
            # Check conda packages
            if pkg_info.get('bioconda'):
                pkg_name = pkg_info['bioconda']
                result = subprocess.run(
                    ['conda', 'list', '-n', 'base', pkg_name],
                    capture_output=True, text=True
                )
                if result.returncode == 0 and pkg_name in result.stdout:
                    installed.append(pkg_name)
        
        elif pkg_manager.lower() == 'pip':
            # Check pip packages
            if pkg_info.get('pip_package'):
                pkg_name = pkg_info['pip_package']
                result = subprocess.run(
                    ['pip', 'show', pkg_name],
                    capture_output=True, text=True
                )
                if result.returncode == 0:
                    installed.append(pkg_name)
        
        return installed

    def install_tool(self, tool_id: int, auto_install: bool = True) -> Dict[str, Any]:
        """Install a tool autonomously."""
        status = self.get_installation_status(tool_id)
        
        if status.get('is_installed'):
            return {
                'success': True,
                'tool_id': tool_id,
                'tool_name': status['tool_name'],
                'message': 'Tool already installed',
                'install_path': status['install_path'],
                'action': 'skipped'
            }
        
        if not status.get('can_auto_install'):
            return {
                'success': False,
                'tool_id': tool_id,
                'tool_name': status['tool_name'],
                'message': 'Auto-install not available for this tool',
                'package_manager': status['package_manager'],
                'packages': status['packages'],
                'action': 'manual'
            }
        
        pkg_manager = status['package_manager'].lower()
        packages = status['packages']
        
        try:
            install_path = self.get_tool_install_path(tool_id, status['tool_name'])
            
            if pkg_manager == 'conda':
                result = self._install_conda(packages, install_path)
            elif pkg_manager == 'pip':
                result = self._install_pip(packages, install_path)
            elif pkg_manager == 'source':
                result = self._install_source(packages, install_path)
            else:
                result = {
                    'success': False,
                    'message': f'Unknown package manager: {pkg_manager}'
                }
            
            if result.get('success'):
                # Update database with installation info
                self._update_installation_record(tool_id, install_path, result)
            
            return {
                'success': result.get('success', False),
                'tool_id': tool_id,
                'tool_name': status['tool_name'],
                'install_path': str(install_path),
                'action': 'installed' if result.get('success') else 'failed',
                'message': result.get('message', ''),
                'command': result.get('command', '')
            }
            
        except Exception as e:
            logger.error(f"Error installing tool {tool_id}: {e}")
            return {
                'success': False,
                'tool_id': tool_id,
                'tool_name': status['tool_name'],
                'message': str(e),
                'action': 'error'
            }

    def _install_conda(self, packages: Dict, install_path: Path) -> Dict[str, Any]:
        """Install tool via conda."""
        bioconda_pkg = packages.get('bioconda')
        
        if not bioconda_pkg:
            return {'success': False, 'message': 'No bioconda package specified'}
        
        try:
            # Create conda environment for tool
            env_name = f"virometrics_{bioconda_pkg}"
            command = f"conda create -y -n {env_name} {bioconda_pkg}"
            
            logger.info(f"Installing {bioconda_pkg} via conda")
            result = subprocess.run(
                command.split(),
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                # Create symlink to tool
                tool_dir = install_path / 'envs' / env_name
                if tool_dir.exists():
                    return {
                        'success': True,
                        'message': f'Installed {bioconda_pkg} in conda environment',
                        'command': command,
                        'env_name': env_name
                    }
            
            return {
                'success': False,
                'message': result.stderr or 'Installation failed',
                'command': command
            }
            
        except subprocess.TimeoutExpired:
            return {'success': False, 'message': 'Installation timed out'}
        except Exception as e:
            return {'success': False, 'message': str(e)}

    def _install_pip(self, packages: Dict, install_path: Path) -> Dict[str, Any]:
        """Install tool via pip."""
        pip_pkg = packages.get('pip_package')
        
        if not pip_pkg:
            return {'success': False, 'message': 'No pip package specified'}
        
        try:
            command = f"pip install {pip_pkg}"
            
            logger.info(f"Installing {pip_pkg} via pip")
            result = subprocess.run(
                command.split(),
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                return {
                    'success': True,
                    'message': f'Installed {pip_pkg} via pip',
                    'command': command
                }
            
            return {
                'success': False,
                'message': result.stderr or 'Installation failed',
                'command': command
            }
            
        except subprocess.TimeoutExpired:
            return {'success': False, 'message': 'Installation timed out'}
        except Exception as e:
            return {'success': False, 'message': str(e)}

    def _install_source(self, packages: Dict, install_path: Path) -> Dict[str, Any]:
        """Install tool from source."""
        repo_url = packages.get('repository') or packages.get('git_url')
        
        if not repo_url:
            return {'success': False, 'message': 'No repository URL specified'}
        
        try:
            # Extract repo name from URL
            repo_name = repo_url.split('/')[-1].replace('.git', '')
            target_dir = install_path / repo_name
            
            if target_dir.exists():
                return {
                    'success': True,
                    'message': f'{repo_name} already cloned',
                    'command': 'git clone (skipped)',
                    'path': str(target_dir)
                }
            
            command = f"git clone {repo_url} {target_dir}"
            
            logger.info(f"Cloning {repo_name} from {repo_url}")
            result = subprocess.run(
                command.split(),
                capture_output=True,
                text=True,
                timeout=600
            )
            
            if result.returncode == 0:
                # Try to install dependencies if requirements.txt exists
                req_file = target_dir / 'requirements.txt'
                if req_file.exists():
                    pip_install = subprocess.run(
                        ['pip', 'install', '-r', str(req_file)],
                        capture_output=True,
                        text=True,
                        timeout=300
                    )
                    if pip_install.returncode == 0:
                        return {
                            'success': True,
                            'message': f'Cloned {repo_name} and installed dependencies',
                            'command': command,
                            'path': str(target_dir)
                        }
                
                return {
                    'success': True,
                    'message': f'Cloned {repo_name} from source',
                    'command': command,
                    'path': str(target_dir)
                }
            
            return {
                'success': False,
                'message': result.stderr or 'Clone failed',
                'command': command
            }
            
        except subprocess.TimeoutExpired:
            return {'success': False, 'message': 'Clone timed out'}
        except Exception as e:
            return {'success': False, 'message': str(e)}

    def _update_installation_record(self, tool_id: int, install_path: Path, result: Dict):
        """Update installation record in database."""
        import sqlite3
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE tools 
                   SET repo_path = ?, 
                       last_installed = datetime('now')
                   WHERE id = ?""",
                (str(install_path), tool_id)
            )
            conn.commit()
        finally:
            conn.close()

    def uninstall_tool(self, tool_id: int) -> Dict[str, Any]:
        """Uninstall a tool."""
        status = self.get_installation_status(tool_id)
        
        if not status.get('is_installed'):
            return {
                'success': False,
                'message': 'Tool not installed'
            }
        
        tool_dir = Path(status['install_path'])
        
        try:
            # Remove tool directory
            if tool_dir.exists():
                shutil.rmtree(tool_dir)
            
            # Update database
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE tools SET repo_path = NULL, last_installed = NULL WHERE id = ?",
                    (tool_id,)
                )
                conn.commit()
            finally:
                conn.close()
            
            return {
                'success': True,
                'message': f'Tool uninstalled from {tool_dir}'
            }
            
        except Exception as e:
            return {
                'success': False,
                'message': str(e)
            }

    def list_installed_tools(self) -> List[Dict[str, Any]]:
        """List all installed tools."""
        if not self.tools_dir.exists():
            return []
        
        installed = []
        
        for tool_dir in self.tools_dir.iterdir():
            if tool_dir.is_dir():
                # Find corresponding tool in database
                conn = self._get_connection()
                try:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT id, name FROM tools WHERE REPLACE(REPLACE(name, ' ', '_'), '.', '_') = ?",
                        (tool_dir.name,)
                    )
                    tool = cursor.fetchone()
                    
                    if tool:
                        installed.append({
                            'tool_id': tool['id'],
                            'tool_name': tool['name'],
                            'install_path': str(tool_dir),
                            'size': sum(f.stat().st_size for f in tool_dir.rglob('*') if f.is_file())
                        })
                finally:
                    conn.close()
        
        return installed
