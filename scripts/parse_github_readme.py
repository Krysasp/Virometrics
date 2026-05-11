#!/usr/bin/env python3
"""
Parse GitHub repository READMEs to extract:
- Installation instructions
- Usage examples
- Expected input/output files
- Directory structure conventions
"""

import requests
import re
from typing import Optional, Dict, Any, List
from bs4 import BeautifulSoup
import json

class GitHubReadmeParser:
    """Parse GitHub README files for installation and usage info."""

    def __init__(self, github_token: Optional[str] = None):
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'Virometrics/1.0'
        })
        if github_token:
            self.session.headers.update({
                'Authorization': f'token {github_token}'
            })

    def fetch_readme(self, repo_path: str) -> Optional[str]:
        """Fetch README content from GitHub API."""
        try:
            # Try different README filenames
            for readme_name in ['README.md', 'README', 'README.txt', 'readme.md']:
                response = self.session.get(
                    f"https://api.github.com/repos/{repo_path}/readme",
                    params={'ref': 'main'}
                )
                if response.status_code == 200:
                    import base64
                    content = response.json().get('content', '')
                    return base64.b64decode(content).decode('utf-8', errors='ignore')
            return None
        except Exception as e:
            print(f"Error fetching README for {repo_path}: {e}")
            return None

    def extract_installation(self, readme: str) -> str:
        """Extract installation instructions from README."""
        if not readme:
            return ""

        # Look for installation section
        patterns = [
            r'#+\s*installation.*?(?=\n#+|\Z)',
            r'#+\s*install.*?(?=\n#+|\Z)',
            r'#+\s*setup.*?(?=\n#+|\Z)',
            r'#+\s*getting started.*?(?=\n#+|\Z)',
            r'#+\s*requirements.*?(?=\n#+|\Z)',
        ]

        for pattern in patterns:
            match = re.search(pattern, readme, re.IGNORECASE | re.DOTALL)
            if match:
                section = match.group(0)
                # Clean up markdown
                lines = section.split('\n')[1:]  # Skip header
                return '\n'.join(lines).strip()

        return ""

    def extract_usage(self, readme: str) -> str:
        """Extract usage examples from README."""
        if not readme:
            return ""

        patterns = [
            r'#+\s*usage.*?(?=\n#+|\Z)',
            r'#+\s*quick start.*?(?=\n#+|\Z)',
            r'#+\s*example.*?(?=\n#+|\Z)',
            r'#+\s*running.*?(?=\n#+|\Z)',
        ]

        for pattern in patterns:
            match = re.search(pattern, readme, re.IGNORECASE | re.DOTALL)
            if match:
                section = match.group(0)
                lines = section.split('\n')[1:]
                return '\n'.join(lines).strip()

        return ""

    def extract_input_formats(self, readme: str) -> List[str]:
        """Try to extract input file formats mentioned in README."""
        if not readme:
            return []

        formats = []
        # Common bioinformatics file extensions
        file_patterns = [
            r'\.fasta\b', r'\.fa\b', r'\.fastq\b', r'\.fq\b',
            r'\.bam\b', r'\.sam\b', r'\.vcf\b', r'\.gff\b',
            r'\.gbk\b', r'\.genbank\b', r'\.fna\b', r'\.faa\b',
            r'\.fast5\b', r'\.h5\b', r'\.csv\b', r'\.tsv\b',
            r'\.json\b', r'\.txt\b', r'\.html\b', r'\.pdf\b'
        ]

        for pattern in file_patterns:
            if re.search(pattern, readme, re.IGNORECASE):
                fmt = pattern.replace(r'\.', '.').replace(r'\b', '')
                if fmt not in formats:
                    formats.append(fmt)

        return formats

    def extract_output_formats(self, readme: str) -> List[str]:
        """Try to extract output file formats mentioned in README."""
        return self.extract_input_formats(readme)  # Same logic applies

    def parse_repo(self, repo_path: str) -> Dict[str, Any]:
        """Parse a GitHub repository's README."""
        result = {
            'installation': '',
            'usage': '',
            'input_formats': [],
            'output_formats': [],
            'dependencies': [],
            'example_commands': [],
        }

        readme = self.fetch_readme(repo_path)
        if not readme:
            return result

        result['installation'] = self.extract_installation(readme)
        result['usage'] = self.extract_usage(readme)
        result['input_formats'] = self.extract_input_formats(readme)
        result['output_formats'] = self.extract_output_formats(readme)

        # Extract example commands (lines starting with $, code blocks)
        code_blocks = re.findall(r'```[\w]*\n(.*?)```', readme, re.DOTALL)
        for block in code_blocks:
            for line in block.split('\n'):
                if line.strip().startswith('$') or line.strip().startswith('>'):
                    result['example_commands'].append(line.strip())

        return result


if __name__ == '__main__':
    import os
    token = os.environ.get('GITHUB_TOKEN')

    parser = GitHubReadmeParser(token)
    test_repos = ['mtisza1/Cenote-Taker2', 'AnantharamanLab/VIBRANT']

    for repo in test_repos:
        print(f"\nParsing README for {repo}...")
        info = parser.parse_repo(repo)
        print("Installation:", info['installation'][:200] if info['installation'] else "Not found")
        print("Input formats:", info['input_formats'])
        print("Example commands:", len(info['example_commands']))
