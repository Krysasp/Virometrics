#!/usr/bin/env python3
"""
Fetch package information from Bioconda via Anaconda API.
Bioconda packages can be queried at: https://api.anaconda.org/package/bioconda/{package_name}
"""

import requests
import json
from typing import Optional, Dict, Any, List

class BiocondaFetcher:
    """Fetch package information from Bioconda."""

    BASE_URL = "https://api.anaconda.org/package"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
            'User-Agent': 'Virometrics/1.0'
        })

    def search_package(self, tool_name: str) -> Optional[str]:
        """Search for a Bioconda package by tool name."""
        # Common name variations
        variations = [
            tool_name.lower(),
            tool_name.lower().replace('-', ''),
            tool_name.lower().replace('_', ''),
            tool_name.lower().replace(' ', ''),
        ]

        # Try exact match first
        for name in set(variations):
            try:
                response = self.session.get(f"{self.BASE_URL}/bioconda/{name}")
                if response.status_code == 200:
                    return name
            except:
                pass

        # Try searching
        try:
            response = self.session.get(
                f"{self.BASE_URL}/search/{tool_name.lower()}",
                params={'type': 'conda'}
            )
            if response.status_code == 200:
                results = response.json()
                for result in results:
                    if result.get('owner') == 'bioconda':
                        return result.get('name')
        except:
            pass

        return None

    def get_package_info(self, package_name: str) -> Optional[Dict[str, Any]]:
        """Get detailed package information."""
        try:
            response = self.session.get(f"{self.BASE_URL}/bioconda/{package_name}")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching Bioconda package {package_name}: {e}")
            return None

    def get_latest_version(self, package_name: str) -> Optional[Dict[str, Any]]:
        """Get the latest version of a package."""
        try:
            response = self.session.get(f"{self.BASE_URL}/bioconda/{package_name}/latest")
            response.raise_for_status()
            return response.json()
        except:
            return None

    def extract_dependencies(self, package_data: Dict[str, Any]) -> List[str]:
        """Extract dependencies from package data."""
        deps = []
        for file_data in package_data.get('files', []):
            for dep in file_data.get('dependencies', []):
                if isinstance(dep, dict):
                    dep_name = dep.get('name', '')
                else:
                    dep_name = str(dep).split(' ')[0]
                if dep_name and dep_name not in deps:
                    deps.append(dep_name)
        return deps

    def get_installation_command(self, package_name: str, version: Optional[str] = None) -> str:
        """Generate installation command."""
        if version:
            return f"conda install -c bioconda {package_name}={version}"
        return f"conda install -c bioconda {package_name}"

    def fetch_for_tool(self, tool_name: str) -> Dict[str, Any]:
        """Fetch and extract information for a tool."""
        result = {
            'bioconda_package': None,
            'version': None,
            'dependencies': [],
            'installation': None,
            'license': None,
            'home_url': None,
            'summary': None,
        }

        package_name = self.search_package(tool_name)
        if not package_name:
            return result

        result['bioconda_package'] = package_name

        # Get latest version info
        latest = self.get_latest_version(package_name)
        if latest:
            result['version'] = latest.get('version')
            result['license'] = latest.get('license')
            result['home_url'] = latest.get('home_url')

        # Get full package info for dependencies
        pkg_info = self.get_package_info(package_name)
        if pkg_info:
            result['dependencies'] = self.extract_dependencies(pkg_info)
            result['summary'] = pkg_info.get('summary', '')
            result['installation'] = self.get_installation_command(package_name, result['version'])

        return result


if __name__ == '__main__':
    fetcher = BiocondaFetcher()
    test_tools = ['kraken2', 'blast', 'samtools', 'checkv']

    for tool in test_tools:
        print(f"\nFetching Bioconda data for {tool}...")
        info = fetcher.fetch_for_tool(tool)
        print(json.dumps(info, indent=2))
