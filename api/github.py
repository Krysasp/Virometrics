"""GitHub API endpoints for Virometrics platform."""

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional
from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)

bp = Blueprint('github', __name__, url_prefix='/api/github')

# Cache for GitHub data
_release_cache = {}
_readme_cache = {}
_metadata_cache = {}


def _get_cache_path() -> Path:
    """Get path to cache directory."""
    return Path(__file__).parent.parent.parent / 'data' / 'cache'


def _load_cached_data(cache_type: str, tool_id: int) -> Optional[Dict]:
    """Load cached GitHub data for a tool."""
    cache_dir = _get_cache_path()
    cache_file = cache_dir / f"{cache_type}_tool_{tool_id}.json"
    
    if cache_file.exists():
        try:
            with open(cache_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.debug(f"Error loading cache for tool {tool_id}: {e}")
    return None


def _save_cached_data(cache_type: str, tool_id: int, data: Dict):
    """Save GitHub data to cache."""
    cache_dir = _get_cache_path()
    cache_dir.mkdir(exist_ok=True)
    cache_file = cache_dir / f"{cache_type}_tool_{tool_id}.json"
    
    with open(cache_file, 'w') as f:
        json.dump(data, f, indent=2)


@bp.route('/tool/<int:tool_id>/release', methods=['GET'])
def get_tool_release(tool_id: int):
    """Get GitHub release information for a tool."""
    # Check cache first
    cached = _load_cached_data('release', tool_id)
    if cached:
        return jsonify({'source': 'cache', **cached})
    
    # Try to load from tools file
    try:
        tools_file = Path(__file__).parent.parent.parent / 'data' / 'tools_enhanced.json'
        with open(tools_file, 'r') as f:
            tools = json.load(f)
        
        tool = next((t for t in tools if t.get('id') == tool_id), None)
        if not tool:
            return jsonify({'error': 'Tool not found'}), 404
        
        release_data = json.loads(tool.get('github_release', '{}'))
        _save_cached_data('release', tool_id, release_data)
        
        return jsonify({'source': 'file', **release_data})
    
    except Exception as e:
        logger.error(f"Error fetching release for tool {tool_id}: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/tool/<int:tool_id>/readme', methods=['GET'])
def get_tool_readme(tool_id: int):
    """Get GitHub README content for a tool."""
    # Check cache first
    cached = _load_cached_data('readme', tool_id)
    if cached:
        return jsonify({'source': 'cache', **cached})
    
    # Try to load from tools file
    try:
        tools_file = Path(__file__).parent.parent.parent / 'data' / 'tools_enhanced.json'
        with open(tools_file, 'r') as f:
            tools = json.load(f)
        
        tool = next((t for t in tools if t.get('id') == tool_id), None)
        if not tool:
            return jsonify({'error': 'Tool not found'}), 404
        
        readme_data = json.loads(tool.get('github_readme', '{}'))
        _save_cached_data('readme', tool_id, readme_data)
        
        return jsonify({'source': 'file', **readme_data})
    
    except Exception as e:
        logger.error(f"Error fetching README for tool {tool_id}: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/tool/<int:tool_id>/metadata', methods=['GET'])
def get_tool_metadata(tool_id: int):
    """Get GitHub repository metadata for a tool."""
    # Check cache first
    cached = _load_cached_data('metadata', tool_id)
    if cached:
        return jsonify({'source': 'cache', **cached})
    
    # Try to load from tools file
    try:
        tools_file = Path(__file__).parent.parent.parent / 'data' / 'tools_enhanced.json'
        with open(tools_file, 'r') as f:
            tools = json.load(f)
        
        tool = next((t for t in tools if t.get('id') == tool_id), None)
        if not tool:
            return jsonify({'error': 'Tool not found'}), 404
        
        metadata = json.loads(tool.get('github_metadata', '{}'))
        _save_cached_data('metadata', tool_id, metadata)
        
        return jsonify({'source': 'file', **metadata})
    
    except Exception as e:
        logger.error(f"Error fetching metadata for tool {tool_id}: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/refresh/<int:tool_id>', methods=['POST'])
def refresh_tool_github_data(tool_id: int):
    """Refresh GitHub data for a tool from live API."""
    # This would require the GitHubReleaseFetcher to be called
    # For now, just invalidate cache
    cache_dir = _get_cache_path()
    for prefix in ['release', 'readme', 'metadata']:
        cache_file = cache_dir / f"{prefix}_tool_{tool_id}.json"
        if cache_file.exists():
            cache_file.unlink()
    
    return jsonify({'message': f'Cache invalidated for tool {tool_id}'})


@bp.route('/bulk/refresh', methods=['POST'])
def bulk_refresh():
    """Refresh GitHub data for multiple tools."""
    data = request.get_json(silent=True) or {}
    tool_ids = data.get('tool_ids', [])
    max_count = data.get('max_count', 50)
    
    if not tool_ids:
        return jsonify({'error': 'No tool IDs provided'}), 400
    
    # Limit batch size
    tool_ids = tool_ids[:max_count]
    
    # Invalidate cache for all specified tools
    cache_dir = _get_cache_path()
    invalidated = 0
    
    for tool_id in tool_ids:
        for prefix in ['release', 'readme', 'metadata']:
            cache_file = cache_dir / f"{prefix}_tool_{tool_id}.json"
            if cache_file.exists():
                cache_file.unlink()
                invalidated += 1
    
    return jsonify({
        'message': f'Invalidated cache for {len(tool_ids)} tools',
        'tool_ids': tool_ids,
        'files_invalidated': invalidated
    })


@bp.route('/stats', methods=['GET'])
def get_github_stats():
    """Get statistics about GitHub data availability."""
    try:
        tools_file = Path(__file__).parent.parent.parent / 'data' / 'tools_enhanced.json'
        with open(tools_file, 'r') as f:
            tools = json.load(f)
        
        stats = {
            'total_tools': len(tools),
            'with_github_url': 0,
            'with_release_data': 0,
            'with_readme_data': 0,
            'with_metadata': 0,
        }
        
        for tool in tools:
            if tool.get('url') and 'github.com' in tool.get('url', ''):
                stats['with_github_url'] += 1
            if tool.get('github_release'):
                stats['with_release_data'] += 1
            if tool.get('github_readme'):
                stats['with_readme_data'] += 1
            if tool.get('github_metadata'):
                stats['with_metadata'] += 1
        
        return jsonify(stats)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500
