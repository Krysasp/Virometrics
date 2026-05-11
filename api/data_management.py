"""Data management API endpoints for Virometrics platform."""

import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Any
from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)

bp = Blueprint('data_mgmt2', __name__, url_prefix='/api/data')


def get_base_dirs():
    """Get base data directories."""
    from core import get_db_path
    base_dir = Path(get_db_path()).parent
    return {
        'base': base_dir,
        'uploads': base_dir / 'uploads',
        'outputs': base_dir / 'outputs',
        'tools': base_dir / 'tools',
        'hot': base_dir / 'hot',
        'warm': base_dir / 'warm',
        'cold': base_dir / 'cold',
    }


def scan_directory(directory: Path, file_type: str = None) -> List[Dict]:
    """Scan directory and collect file statistics."""
    files = []
    
    if not directory.exists():
        return files
    
    for root, dirs, filenames in os.walk(directory):
        for filename in filenames:
            filepath = Path(root) / filename
            
            try:
                stat = filepath.stat()
                files.append({
                    'name': filename,
                    'path': str(filepath.relative_to(directory)),
                    'size': stat.st_size,
                    'size_human': format_size(stat.st_size),
                    'modified': stat.st_mtime,
                    'type': file_type or get_file_type(filename)
                })
            except Exception as e:
                logger.debug(f"Error reading file {filepath}: {e}")
    
    return files


def format_size(size_bytes: int) -> str:
    """Format bytes to human readable size."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


def get_file_type(filename: str) -> str:
    """Determine file type based on extension."""
    ext = Path(filename).suffix.lower()
    
    type_map = {
        '.fasta': 'fasta',
        '.fa': 'fasta',
        '.faa': 'fasta',
        '.fna': 'fasta',
        '.fastq': 'fastq',
        '.fq': 'fastq',
        '.bam': 'bam',
        '.sam': 'sam',
        '.vcf': 'vcf',
        '.gff': 'gff',
        '.gff3': 'gff',
        '.gbk': 'gbk',
        '.gb': 'gbk',
        '.json': 'json',
        '.csv': 'csv',
        '.txt': 'text',
        '.log': 'log',
        '.tar': 'archive',
        '.tar.gz': 'archive',
        '.tgz': 'archive',
        '.zip': 'archive',
        '.gz': 'compressed',
    }
    
    return type_map.get(ext, 'other')


@bp.route('/summary', methods=['GET'])
def get_summary():
    """Get overall data summary."""
    dirs = get_base_dirs()
    
    summary = {
        'directories': {},
        'total_size': 0,
        'total_files': 0,
        'by_type': {}
    }
    
    for name, directory in dirs.items():
        if name == 'base':
            continue
            
        files = scan_directory(directory)
        total_size = sum(f['size'] for f in files)
        
        summary['directories'][name] = {
            'path': str(directory),
            'file_count': len(files),
            'total_size': total_size,
            'total_size_human': format_size(total_size)
        }
        
        summary['total_size'] += total_size
        summary['total_files'] += len(files)
        
        # Group by file type
        for f in files:
            ftype = f['type']
            if ftype not in summary['by_type']:
                summary['by_type'][ftype] = {'count': 0, 'size': 0}
            summary['by_type'][ftype]['count'] += 1
            summary['by_type'][ftype]['size'] += f['size']
    
    # Format by_type for response
    for ftype, data in summary['by_type'].items():
        data['size_human'] = format_size(data['size'])
    
    summary['total_size_human'] = format_size(summary['total_size'])
    
    return jsonify(summary)


@bp.route('/tools/<string:tool_name>', methods=['GET'])
def get_tool_data(tool_name):
    """Get data files for a specific tool."""
    dirs = get_base_dirs()
    
    tool_data = {
        'tool_name': tool_name,
        'files': [],
        'total_size': 0,
        'by_category': {}
    }
    
    # Scan each directory for tool files
    for category, directory in dirs.items():
        if category == 'base':
            continue
            
        files = scan_directory(directory, file_type=category)
        tool_files = [f for f in files if tool_name.lower() in f['path'].lower()]
        
        if tool_files:
            tool_data['files'].extend(tool_files)
            tool_data['total_size'] += sum(f['size'] for f in tool_files)
            
            # Group by category
            if category not in tool_data['by_category']:
                tool_data['by_category'][category] = []
            tool_data['by_category'][category] = tool_files
    
    tool_data['total_size_human'] = format_size(tool_data['total_size'])
    
    return jsonify(tool_data)


@bp.route('/fasta', methods=['GET'])
def get_fasta_repository():
    """Get FASTA repository statistics and files."""
    dirs = get_base_dirs()
    
    fasta_data = {
        'repositories': {},
        'total_fasta_files': 0,
        'total_fasta_size': 0,
        'sequences': []
    }
    
    # Scan for FASTA files
    for category, directory in dirs.items():
        if category == 'base':
            continue
            
        files = scan_directory(directory, file_type='fasta')
        fasta_files = [f for f in files if f['type'] == 'fasta']
        
        if fasta_files:
            fasta_data['repositories'][category] = {
                'directory': str(directory),
                'files': fasta_files,
                'count': len(fasta_files),
                'total_size': sum(f['size'] for f in fasta_files)
            }
            
            fasta_data['total_fasta_files'] += len(fasta_files)
            fasta_data['total_fasta_size'] += fasta_data['repositories'][category]['total_size']
    
    fasta_data['total_size_human'] = format_size(fasta_data['total_fasta_size'])
    
    return jsonify(fasta_data)


@bp.route('/workspace', methods=['GET'])
def get_workspace():
    """Get workspace utilization statistics."""
    dirs = get_base_dirs()
    
    workspace = {
        'uploads': {
            'path': str(dirs['uploads']),
            'exists': dirs['uploads'].exists(),
            'file_count': 0,
            'total_size': 0,
            'files': []
        },
        'outputs': {
            'path': str(dirs['outputs']),
            'exists': dirs['outputs'].exists(),
            'file_count': 0,
            'total_size': 0,
            'files': []
        },
        'tiered_storage': {
            'hot': {'path': str(dirs['hot']), 'file_count': 0, 'total_size': 0},
            'warm': {'path': str(dirs['warm']), 'file_count': 0, 'total_size': 0},
            'cold': {'path': str(dirs['cold']), 'file_count': 0, 'total_size': 0}
        }
    }
    
    # Scan uploads
    if workspace['uploads']['exists']:
        files = scan_directory(dirs['uploads'])
        workspace['uploads']['file_count'] = len(files)
        workspace['uploads']['total_size'] = sum(f['size'] for f in files)
        workspace['uploads']['files'] = files[:50]  # Limit to first 50
    
    # Scan outputs
    if workspace['outputs']['exists']:
        files = scan_directory(dirs['outputs'])
        workspace['outputs']['file_count'] = len(files)
        workspace['outputs']['total_size'] = sum(f['size'] for f in files)
        workspace['outputs']['files'] = files[:50]
    
    # Scan tiered storage
    for tier in ['hot', 'warm', 'cold']:
        if workspace['tiered_storage'][tier]['path']:
            files = scan_directory(dirs[tier])
            workspace['tiered_storage'][tier]['file_count'] = len(files)
            workspace['tiered_storage'][tier]['total_size'] = sum(f['size'] for f in files)
    
    # Add human readable sizes
    workspace['uploads']['total_size_human'] = format_size(workspace['uploads']['total_size'])
    workspace['outputs']['total_size_human'] = format_size(workspace['outputs']['total_size'])
    
    for tier in ['hot', 'warm', 'cold']:
        workspace['tiered_storage'][tier]['total_size_human'] = format_size(
            workspace['tiered_storage'][tier]['total_size']
        )
    
    return jsonify(workspace)


@bp.route('/storage/metrics', methods=['GET'])
def get_storage_metrics():
    """Get storage metrics for database tracking."""
    from core import get_db_path
    import sqlite3
    
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    
    try:
        cursor = conn.cursor()
        
        # Get current metrics from database
        cursor.execute("SELECT * FROM storage_metrics ORDER BY updated_at DESC LIMIT 1")
        db_metrics = cursor.fetchone()
        
        # Calculate current metrics
        dirs = get_base_dirs()
        current_metrics = {
            'uploads': {'size': 0, 'count': 0},
            'outputs': {'size': 0, 'count': 0},
            'tools': {'size': 0, 'count': 0}
        }
        
        for category, directory in dirs.items():
            if category in current_metrics and directory.exists():
                files = scan_directory(directory)
                current_metrics[category]['size'] = sum(f['size'] for f in files)
                current_metrics[category]['count'] = len(files)
        
        result = {
            'database_metrics': dict(db_metrics) if db_metrics else None,
            'current_metrics': {
                category: {
                    'size': data['size'],
                    'size_human': format_size(data['size']),
                    'file_count': data['count']
                }
                for category, data in current_metrics.items()
            },
            'total_size': sum(m['size'] for m in current_metrics.values()),
            'total_files': sum(m['count'] for m in current_metrics.values())
        }
        
        return jsonify(result)
        
    finally:
        conn.close()


@bp.route('/scan', methods=['POST'])
def scan_and_store():
    """Scan directories and store metrics in database."""
    from core import get_db_path
    import sqlite3
    
    dirs = get_base_dirs()
    
    conn = sqlite3.connect(get_db_path())
    try:
        cursor = conn.cursor()
        
        metrics = []
        
        for category, directory in dirs.items():
            if category == 'base':
                continue
                
            if directory.exists():
                files = scan_directory(directory)
                total_size = sum(f['size'] for f in files)
                
                metrics.append({
                    'category': category,
                    'total_size': total_size,
                    'file_count': len(files)
                })
                
                # Store in database
                cursor.execute("""
                    INSERT INTO storage_metrics (category, total_size, file_count, updated_at)
                    VALUES (?, ?, ?, datetime('now'))
                """, (category, total_size, len(files)))
        
        conn.commit()
        
        return jsonify({
            'success': True,
            'scanned': len(metrics),
            'metrics': metrics
        })
        
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()
