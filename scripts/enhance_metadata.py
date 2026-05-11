#!/usr/bin/env python3
"""
Main metadata enhancement pipeline for Virometrics.
This script:
1. Loads existing tool data from awesome-virome
2. Fetches additional metadata from bio.tools API
3. Fetches package info from Bioconda
4. Parses GitHub READMEs for installation/usage info
5. Stores everything in SQLite database
"""

import json
import os
import sys
import sqlite3
from typing import Dict, Any, List, Optional
from pathlib import Path
import time

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from fetch_biotools import BioToolsFetcher
from fetch_bioconda import BiocondaFetcher
from parse_github_readme import GitHubReadmeParser

class MetadataEnhancer:
    """Main class for enhancing tool metadata."""

    def __init__(self, awesome_virome_path: str, db_path: str, github_token: Optional[str] = None):
        self.awesome_virome_path = Path(awesome_virome_path)
        self.db_path = db_path

        # Initialize fetchers
        self.biotools_fetcher = BioToolsFetcher()
        self.bioconda_fetcher = BiocondaFetcher()
        self.github_parser = GitHubReadmeParser(github_token)

        # Initialize database
        self.init_database()

    def init_database(self):
        """Initialize database connection."""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        
        # Add rating and review columns if they don't exist
        self.cursor.execute("PRAGMA table_info(tools)")
        columns = [col[1] for col in self.cursor.fetchall()]
        
        if 'avg_rating' not in columns:
            self.cursor.execute("ALTER TABLE tools ADD COLUMN avg_rating REAL DEFAULT 0")
        if 'rating_count' not in columns:
            self.cursor.execute("ALTER TABLE tools ADD COLUMN rating_count INTEGER DEFAULT 0")
        if 'last_reviewed' not in columns:
            self.cursor.execute("ALTER TABLE tools ADD COLUMN last_reviewed TEXT")
        
        self.conn.commit()

    def load_awesome_virome_data(self) -> List[Dict[str, Any]]:
        """Load tool data from awesome-virome data.json."""
        data_json_path = self.awesome_virome_path / 'data.json'

        if not data_json_path.exists():
            print(f"Error: {data_json_path} not found!")
            return []

        with open(data_json_path, 'r') as f:
            data = json.load(f)

        # Extract tool nodes
        tools = [n for n in data.get('nodes', []) if n.get('type') == 'tool']
        print(f"Loaded {len(tools)} tools from awesome-virome")
        return tools

    def load_metadata_files(self) -> Dict[str, Dict[str, Any]]:
        """Load individual metadata files from metadata/bioinformatics/."""
        metadata_dir = self.awesome_virome_path / 'metadata' / 'bioinformatics'
        metadata = {}

        if not metadata_dir.exists():
            print(f"Warning: {metadata_dir} not found!")
            return metadata

        for json_file in metadata_dir.glob('*.json'):
            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)
                    tool_name = data.get('name', json_file.stem.replace('.json', ''))
                    metadata[tool_name] = data
            except Exception as e:
                print(f"Error loading {json_file}: {e}")

        print(f"Loaded {len(metadata)} metadata files")
        return metadata

   def enhance_tool(self, tool: Dict[str, Any], metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Enhance a single tool with additional metadata."""
        enhanced = {
            'name': tool.get('name'),
            'url': tool.get('url'),
            'description': tool.get('description', ''),
            'category': tool.get('category'),
            'subcategory': tool.get('subcategory'),
            'purpose': '',
            'setup_instructions': '',
            'usage_examples': '',
            'studies_suited': json.dumps([]),
            'input_formats': json.dumps([]),
            'output_formats': json.dumps([]),
            'package_manager': tool.get('package_manager'),
            'packages_needed': json.dumps({}),
            'languages': json.dumps(tool.get('all_languages', [])),
            'directory_structure': '',
            'github_stars': tool.get('stars', 0),
            'github_forks': tool.get('forks', 0),
            'doi': tool.get('doi', ''),
            'citations': tool.get('citation_count', 0),
            'license': tool.get('license', ''),
            'last_updated': tool.get('lastUpdated', ''),
            'created_at': tool.get('createdAt', ''),
            'repo_path': tool.get('repo_path', ''),
            'provider': tool.get('provider', ''),
            'is_archived': tool.get('is_archived', False),
            'github_metrics': json.dumps(tool.get('github_metrics', {})),
            'metadata_json': json.dumps(metadata) if metadata else None,
            'example_commands': json.dumps([]),
            'dependencies': json.dumps([]),
        }

        # Try to enhance with bio.tools data
        try:
            biotools_info = self.biotools_fetcher.fetch_for_tool(tool.get('name', ''))
            if biotools_info:
                if biotools_info.get('description') and not enhanced['description']:
                    enhanced['description'] = biotools_info['description']
                if biotools_info.get('input_formats'):
                    enhanced['input_formats'] = json.dumps(biotools_info['input_formats'])
                if biotools_info.get('output_formats'):
                    enhanced['output_formats'] = json.dumps(biotools_info['output_formats'])
                if biotools_info.get('operations'):
                    enhanced['purpose'] = ', '.join(biotools_info['operations'])
        except Exception as e:
            print(f"  bio.tools error for {tool.get('name')}: {e}")

        # Try to enhance with Bioconda data
        try:
            bioconda_info = self.bioconda_fetcher.fetch_for_tool(tool.get('name', ''))
            if bioconda_info and bioconda_info.get('bioconda_package'):
                enhanced['packages_needed'] = json.dumps({
                    'bioconda': bioconda_info['bioconda_package'],
                    'version': bioconda_info.get('version'),
                    'dependencies': bioconda_info.get('dependencies', []),
                })
                if bioconda_info.get('installation'):
                    enhanced['setup_instructions'] = bioconda_info['installation']
                if not enhanced['package_manager']:
                    enhanced['package_manager'] = 'conda'
                if bioconda_info.get('dependencies'):
                    enhanced['dependencies'] = json.dumps(bioconda_info['dependencies'])
        except Exception as e:
            print(f"  Bioconda error for {tool.get('name')}: {e}")

        # Try to parse GitHub README
        if tool.get('repo_path') and tool.get('provider') == 'github':
            try:
                readme_info = self.github_parser.parse_repo(tool['repo_path'])
                if readme_info:
                    if readme_info.get('installation') and not enhanced['setup_instructions']:
                        enhanced['setup_instructions'] = readme_info['installation'][:1000]
                    if readme_info.get('usage'):
                        enhanced['usage_examples'] = readme_info['usage'][:1000]
                    if readme_info.get('input_formats'):
                        existing_inputs = json.loads(enhanced['input_formats'])
                        for fmt in readme_info['input_formats']:
                            if fmt not in existing_inputs:
                                existing_inputs.append(fmt)
                        enhanced['input_formats'] = json.dumps(existing_inputs)
                    if readme_info.get('output_formats'):
                        existing_outputs = json.loads(enhanced['output_formats'])
                        for fmt in readme_info['output_formats']:
                            if fmt not in existing_outputs:
                                existing_outputs.append(fmt)
                        enhanced['output_formats'] = json.dumps(existing_outputs)
                    if readme_info.get('example_commands'):
                        enhanced['example_commands'] = json.dumps(readme_info['example_commands'][:5])
            except Exception as e:
                print(f"  GitHub README error for {tool.get('name')}: {e}")

        # Use existing metadata file if available
        if metadata:
            biotools = metadata.get('biotools', {})
            if biotools.get('description') and not enhanced['description']:
                enhanced['description'] = biotools['description']
            if biotools.get('input_formats'):
                existing = json.loads(enhanced['input_formats'])
                for fmt in biotools['input_formats']:
                    if fmt not in existing:
                        existing.append(fmt)
                enhanced['input_formats'] = json.dumps(existing)
            if biotools.get('output_formats'):
                existing = json.loads(enhanced['output_formats'])
                for fmt in biotools['output_formats']:
                    if fmt not in existing:
                        existing.append(fmt)
                enhanced['output_formats'] = json.dumps(existing)

            bioconda = metadata.get('bioconda', {})
            if bioconda.get('package') and not enhanced['packages_needed']:
                enhanced['packages_needed'] = json.dumps({
                    'bioconda': bioconda['package'],
                    'version': bioconda.get('version'),
                    'dependencies': bioconda.get('dependencies', {}),
                })
                if not enhanced['setup_instructions']:
                    enhanced['setup_instructions'] = f"conda install -c bioconda {bioconda['package']}"

        return enhanced

    def insert_tool(self, tool_data: Dict[str, Any]):
        """Insert or update tool in database."""
        try:
            columns = [
                'name', 'url', 'description', 'category', 'subcategory', 'purpose',
                'setup_instructions', 'studies_suited', 'input_formats', 'output_formats',
                'package_manager', 'packages_needed', 'languages', 'directory_structure',
                'github_stars', 'github_forks', 'doi', 'citations', 'license',
                'last_updated', 'created_at', 'repo_path', 'provider', 'is_archived',
                'github_metrics', 'metadata_json'
            ]
            # Ensure all keys exist in tool_data
            for col in columns:
                if col not in tool_data:
                    tool_data[col] = None

            placeholders = ', '.join(['?'] * len(columns))
            query = f"INSERT OR REPLACE INTO tools ({', '.join(columns)}) VALUES ({placeholders})"

            values = tuple(tool_data[col] for col in columns)
            self.cursor.execute(query, values)
            self.conn.commit()
        except Exception as e:
            print(f"Error inserting {tool_data.get('name', 'Unknown')}: {e}")

    def update_category_counts(self):
        """Update tool counts in categories table."""
        self.cursor.execute('''
            UPDATE categories
            SET tool_count = (
                SELECT COUNT(*)
                FROM tools
                WHERE tools.category = categories.name
            )
        ''')
        self.conn.commit()

    def run(self, limit: Optional[int] = None):
        """Run the full enhancement pipeline."""
        print("Starting metadata enhancement pipeline...")
        print(f"Source: {self.awesome_virome_path}")
        print(f"Database: {self.db_path}\n")

        # Load data
        tools = self.load_awesome_virome_data()
        metadata_files = self.load_metadata_files()

        if not tools:
            print("No tools found. Exiting.")
            return

        # Process tools
        total = min(len(tools), limit) if limit else len(tools)
        print(f"Processing {total} tools...\n")

        for i, tool in enumerate(tools[:total], 1):
            tool_name = tool.get('name', 'Unknown')
            print(f"[{i}/{total}] Processing {tool_name}...")

            # Get corresponding metadata file
            tool_metadata = None
            for key, meta in metadata_files.items():
                if tool_name in key or key in tool_name:
                    tool_metadata = meta
                    break

            # Enhance tool
            enhanced = self.enhance_tool(tool, tool_metadata)

            # Insert into database
            self.insert_tool(enhanced)

            # Rate limiting
            if i % 10 == 0:
                time.sleep(1)

        # Update category counts
        self.update_category_counts()

        # Summary
        self.cursor.execute("SELECT COUNT(*) FROM tools")
        count = self.cursor.fetchone()[0]
        print(f"\nDone! Enhanced {count} tools in database.")

        self.conn.close()


if __name__ == '__main__':
    # Configuration
    AWESOME_VIROME_PATH = "/home/ihcm-ubuntu/.local/bin/awesome-virome"
    DB_PATH = "/home/ihcm-ubuntu/Virometrics/data/virometrics.db"
    GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')

    # Run with optional limit (for testing)
    limit = None
    if len(sys.argv) > 1:
        try:
            limit = int(sys.argv[1])
        except ValueError:
            pass

    enhancer = MetadataEnhancer(AWESOME_VIROME_PATH, DB_PATH, GITHUB_TOKEN)
    enhancer.run(limit=limit)
