"""README processor for extracting and storing tool documentation."""

import re
import json
import logging
import requests
import base64
from typing import Optional, Dict, List, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class ReadmeProcessor:
    """Process GitHub READMEs to extract installation, usage, and documentation sections."""

    def __init__(self, db_path: Optional[str] = None, github_token: Optional[str] = None):
        self.db_path = db_path
        self.github_token = github_token
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Create authenticated requests session."""
        session = requests.Session()
        session.headers.update({
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'Virometrics/1.0'
        })
        if self.github_token:
            session.headers.update({'Authorization': f'token {self.github_token}'})
        return session

    def _get_connection(self):
        """Get database connection."""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def extract_repo_info(self, url: str) -> Optional[tuple]:
        """Extract owner and repo from GitHub URL."""
        if not url:
            return None
        
        patterns = [
            r'github\.com/([^/]+)/([^/]+?)(?:\.git)?$',
            r'github\.com/([^/]+)/([^/]+?)/?(?:tree|releases|blob)?',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1), match.group(2)
        
        return None

    def fetch_readme(self, url: str) -> Optional[str]:
        """Fetch README content from GitHub."""
        repo_info = self.extract_repo_info(url)
        if not repo_info:
            return None
        
        owner, repo = repo_info
        repo_path = f"{owner}/{repo}"
        
        try:
            for readme_name in ['README.md', 'README', 'readme.md']:
                response = self.session.get(
                    f"https://api.github.com/repos/{repo_path}/readme",
                    timeout=10
                )
                
                if response.status_code == 200:
                    content = response.json().get('content', '')
                    return base64.b64decode(content).decode('utf-8', errors='ignore')
            
            return None
            
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout fetching README for {repo_path}")
            return None
        except Exception as e:
            logger.error(f"Error fetching README for {repo_path}: {e}")
            return None

    def extract_sections(self, readme: str) -> Dict[str, str]:
        """Extract relevant sections from README."""
        if not readme:
            return {
                'installation': '',
                'usage': '',
                'requirements': '',
                'documentation': '',
                'overview': ''
            }

        sections = {}
        
        # Extract installation section
        sections['installation'] = self._extract_section(
            readme, 
            ['installation', 'install', 'setup', 'getting started', 'quick install']
        )
        
        # Extract usage section
        sections['usage'] = self._extract_section(
            readme,
            ['usage', 'quick start', 'example', 'examples', 'running', 'command']
        )
        
        # Extract requirements section
        sections['requirements'] = self._extract_section(
            readme,
            ['requirements', 'dependencies', 'prerequisites', 'installation']
        )
        
        # Extract documentation section
        sections['documentation'] = self._extract_section(
            readme,
            ['documentation', 'docs', 'api', 'configuration', 'advanced']
        )
        
        # Extract overview/description
        sections['overview'] = self._extract_overview(readme)
        
        return sections

    def _extract_section(self, readme: str, headers: List[str]) -> str:
        """Extract content under matching headers."""
        for header in headers:
            # Pattern to match markdown headers
            pattern = rf'#+\s*{header}\s*\n(.*?)(?=\n#+\s|\Z)'
            match = re.search(pattern, readme, re.IGNORECASE | re.DOTALL)
            
            if match:
                content = match.group(1).strip()
                # Clean up markdown formatting
                content = self._clean_markdown(content)
                return content[:2000]  # Limit length
        
        return ""

    def _extract_overview(self, readme: str) -> str:
        """Extract the main description/overview from README."""
        if not readme:
            return ""
        
        # Look for first paragraph before any section header
        pattern = r'^(.*?)(?=\n#+\s|\Z)'
        match = re.search(pattern, readme, re.DOTALL)
        
        if match:
            content = match.group(1).strip()
            # Remove title if present
            lines = content.split('\n')
            if lines and lines[0].startswith('#'):
                lines = lines[1:]
            return self._clean_markdown('\n'.join(lines))[:1000]
        
        return ""

    def _clean_markdown(self, text: str) -> str:
        """Clean markdown formatting from text."""
        if not text:
            return ""
        
        # Remove code blocks but keep content
        text = re.sub(r'```[\w]*\n?(.*?)```', r'\1', text, flags=re.DOTALL)
        
        # Remove inline code markers
        text = re.sub(r'`([^`]+)`', r'\1', text)
        
        # Remove bold/italic markers
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
        text = re.sub(r'\*([^*]+)\*', r'\1', text)
        
        # Remove image references but keep alt text
        text = re.sub(r'!\[([^\]]*)\]\([^)]+\)', r'\1', text)
        
        # Remove link markers but keep text
        text = re.sub(r'\[([^\]]*)\]\([^)]+\)', r'\1', text)
        
        # Clean up multiple newlines
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text.strip()

    def fetch_and_store(self, tool_id: int, url: str) -> Dict[str, Any]:
        """Fetch README and store sections in database."""
        readme = self.fetch_readme(url)
        
        if not readme:
            return {'success': False, 'message': 'Could not fetch README'}
        
        sections = self.extract_sections(readme)
        
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Update tools table with readme_sections
            cursor.execute(
                """UPDATE tools 
                   SET readme_sections = ?, 
                       readme_fetched_at = datetime('now')
                   WHERE id = ?""",
                (json.dumps(sections), tool_id)
            )
            
            conn.commit()
            
            return {
                'success': True,
                'tool_id': tool_id,
                'sections_found': len([s for s in sections.values() if s]),
                'sections': sections
            }
            
        except Exception as e:
            logger.error(f"Error storing README for tool {tool_id}: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            conn.close()

    def get_tool_readme_sections(self, tool_id: int) -> Optional[Dict[str, str]]:
        """Get stored README sections for a tool."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT readme_sections FROM tools WHERE id = ?",
                (tool_id,)
            )
            result = cursor.fetchone()
            
            if result and result['readme_sections']:
                return json.loads(result['readme_sections'])
            
            return None
            
        finally:
            conn.close()

    def refresh_all_readmes(self, limit: int = 100) -> Dict[str, int]:
        """Refresh README sections for all tools."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, url FROM tools WHERE url LIKE '%github.com%' LIMIT ?",
                (limit,)
            )
            tools = cursor.fetchall()
            
            results = {
                'total': len(tools),
                'success': 0,
                'failed': 0,
                'skipped': 0
            }
            
            for tool in tools:
                tool_id = tool['id']
                url = tool['url']
                
                # Check if already has recent README
                cursor.execute(
                    "SELECT readme_fetched_at FROM tools WHERE id = ?",
                    (tool_id,)
                )
                existing = cursor.fetchone()
                
                if existing and existing['readme_fetched_at']:
                    results['skipped'] += 1
                    continue
                
                result = self.fetch_and_store(tool_id, url)
                
                if result['success']:
                    results['success'] += 1
                else:
                    results['failed'] += 1
            
            return results
            
        finally:
            conn.close()
