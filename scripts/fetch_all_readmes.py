#!/usr/bin/env python3
"""
Batch README fetcher for Virometrics tools.
Fetches READMEs from GitHub and stores parsed sections in the database.
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import List, Dict

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.readme_processor import ReadmeProcessor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


def fetch_all_readmes(limit: int = 100, force_refresh: bool = False):
    """Fetch READMEs for all GitHub tools."""
    base_dir = Path(__file__).parent.parent
    db_path = base_dir / 'data' / 'virometrics.db'
    
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    try:
        cursor = conn.cursor()
        
        # Build query based on force_refresh flag
        if force_refresh:
            query = """
                SELECT id, name, url, repo_path 
                FROM tools 
                WHERE url LIKE '%github.com%'
                LIMIT ?
            """
        else:
            query = """
                SELECT id, name, url, repo_path 
                FROM tools 
                WHERE url LIKE '%github.com%'
                AND (readme_fetched_at IS NULL OR readme_fetched_at = '')
                LIMIT ?
            """
        
        cursor.execute(query, (limit,))
        tools = cursor.fetchall()
        
        logger.info(f"Found {len(tools)} tools to process")
        
        # Initialize processor
        token = os.environ.get('GITHUB_TOKEN')
        processor = ReadmeProcessor(db_path=str(db_path), github_token=token)
        
        # Process tools
        results = {
            'total': len(tools),
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'errors': []
        }
        
        for i, tool in enumerate(tools):
            tool_id = tool['id']
            tool_name = tool['name']
            url = tool['url']
            
            progress = (i + 1) / len(tools) * 100
            logger.info(f"[{i+1}/{len(tools)}] ({progress:.0f}%) Processing {tool_name}...")
            
            try:
                result = processor.fetch_and_store(tool_id, url)
                
                if result['success']:
                    results['success'] += 1
                    logger.debug(f"  ✓ Fetched {result['sections_found']} sections")
                else:
                    results['failed'] += 1
                    error_msg = result.get('error', 'Unknown error')
                    results['errors'].append({
                        'tool_id': tool_id,
                        'tool_name': tool_name,
                        'error': error_msg
                    })
                    logger.warning(f"  ✗ Failed: {error_msg}")
                    
            except Exception as e:
                results['failed'] += 1
                results['errors'].append({
                    'tool_id': tool_id,
                    'tool_name': tool_name,
                    'error': str(e)
                })
                logger.error(f"  ✗ Error: {e}")
        
        return results
        
    finally:
        conn.close()


def fetch_single_readme(tool_id: int):
    """Fetch README for a single tool."""
    base_dir = Path(__file__).parent.parent
    db_path = base_dir / 'data' / 'virometrics.db'
    
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, url FROM tools WHERE id = ?", (tool_id,))
        tool = cursor.fetchone()
        
        if not tool:
            logger.error(f"Tool {tool_id} not found")
            return None
        
        token = os.environ.get('GITHUB_TOKEN')
        processor = ReadmeProcessor(db_path=str(db_path), github_token=token)
        
        result = processor.fetch_and_store(tool_id, tool['url'])
        
        if result['success']:
            logger.info(f"Successfully fetched README for {tool['name']}")
            logger.info(f"Sections: {list(result['sections'].keys())}")
        else:
            logger.error(f"Failed to fetch README: {result.get('error')}")
        
        return result
        
    finally:
        conn.close()


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Fetch READMEs for Virometrics tools')
    parser.add_argument('--limit', type=int, default=100, help='Max tools to process')
    parser.add_argument('--force', action='store_true', help='Force refresh all READMEs')
    parser.add_argument('--tool-id', type=int, help='Process single tool by ID')
    
    args = parser.parse_args()
    
    if args.tool_id:
        result = fetch_single_readme(args.tool_id)
    else:
        result = fetch_all_readmes(limit=args.limit, force_refresh=args.force)
    
    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total tools: {result['total']}")
    print(f"Success: {result['success']}")
    print(f"Failed: {result['failed']}")
    
    if result.get('errors'):
        print(f"\nErrors ({len(result['errors'])}):")
        for err in result['errors'][:10]:
            print(f"  - {err['tool_name']}: {err['error']}")
        if len(result['errors']) > 10:
            print(f"  ... and {len(result['errors']) - 10} more")
    
    return result


if __name__ == '__main__':
    main()
