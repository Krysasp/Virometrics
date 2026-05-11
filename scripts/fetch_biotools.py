#!/usr/bin/env python3
"""
Fetch tool metadata from bio.tools API.
bio.tools provides structured information about bioinformatics tools including:
- Input/output formats
- Operations performed
- Topics
- Tool descriptions
"""

import requests
import json
import time
from typing import Optional, Dict, Any

class BioToolsFetcher:
    """Fetch tool information from bio.tools API."""

    BASE_URL = "https://bio.tools/api/tool"

    def __init__(self, cache_dir: str = "../data/cache"):
        self.cache_dir = cache_dir
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
            'User-Agent': 'Virometrics/1.0'
        })

    def search_tool(self, name: str) -> Optional[str]:
        """Search for a tool by name and return the tool ID if found."""
        try:
            # Clean up tool name for search
            search_name = name.lower().replace(' ', '-').replace('_', '-')
            response = self.session.get(
                f"{self.BASE_URL}",
                params={'q': search_name, 'format': 'json', 'page': 1}
            )
            response.raise_for_status()
            data = response.json()

            if data.get('list'):
                # Try to find best match
                for tool in data['list']:
                    if (search_name in tool.get('name', '').lower() or
                        search_name in tool.get('toolID', '').lower()):
                        return tool.get('toolID')
            return None
        except Exception as e:
            print(f"Error searching for {name}: {e}")
            return None

    def get_tool_details(self, tool_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a tool by its ID."""
        try:
            response = self.session.get(f"{self.BASE_URL}/{tool_id}", params={'format': 'json'})
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching details for {tool_id}: {e}")
            return None

    def extract_relevant_info(self, tool_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract relevant information from bio.tools data."""
        if not tool_data:
            return {}

        info = {
            'biotools_id': tool_data.get('toolID'),
            'biotools_name': tool_data.get('name'),
            'description': tool_data.get('description', ''),
            'homepage': tool_data.get('homepage', ''),
            'input_formats': [],
            'output_formats': [],
            'operations': [],
            'topics': [],
        }

        # Extract input formats
        for inp in tool_data.get('input', []):
            for fmt in inp.get('format', []):
                if fmt not in info['input_formats']:
                    info['input_formats'].append(fmt)

        # Extract output formats
        for out in tool_data.get('output', []):
            for fmt in out.get('format', []):
                if fmt not in info['output_formats']:
                    info['output_formats'].append(fmt)

        # Extract operations
        for op in tool_data.get('operation', []):
            if op.get('term') not in info['operations']:
                info['operations'].append(op.get('term'))

        # Extract topics
        for topic in tool_data.get('topic', []):
            if topic.get('term') not in info['topics']:
                info['topics'].append(topic.get('term'))

        return info

    def fetch_for_tool(self, tool_name: str) -> Dict[str, Any]:
        """Fetch and extract information for a tool by name."""
        tool_id = self.search_tool(tool_name)
        if not tool_id:
            return {}

        tool_data = self.get_tool_details(tool_id)
        if not tool_data:
            return {}

        return self.extract_relevant_info(tool_data)


if __name__ == '__main__':
    # Test the fetcher
    fetcher = BioToolsFetcher()
    test_tools = ['VirSorter2', 'CheckV', 'Kraken2']

    for tool in test_tools:
        print(f"\nFetching data for {tool}...")
        info = fetcher.fetch_for_tool(tool)
        if info:
            print(json.dumps(info, indent=2))
        else:
            print(f"No data found for {tool}")
        time.sleep(1)  # Be nice to the API
