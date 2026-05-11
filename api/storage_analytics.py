"""Storage analytics API for Virometrics platform.

Provides usage visualization and API endpoints for storage metrics.
"""

import os
import sqlite3
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from collections import defaultdict

# Default paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / 'data'
DB_PATH = DATA_DIR / 'virometrics.db'


class StorageAnalytics:
    """Provide analytics and visualization for storage usage."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or str(DB_PATH)

    def _get_connection(self):
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def get_usage_by_tool(self, days: int = 30) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get storage usage grouped by tool.
        Returns: {tool_name: [{date, size, file_count}]}
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Get execution metrics by tool
            cursor.execute("""
                SELECT 
                    tools.name as tool_name,
                    DATE(t.started_at) as date,
                    COUNT(DISTINCT t.id) as execution_count,
                    COUNT(DISTINCT df.id) as output_files,
                    COALESCE(SUM(df.file_size), 0) as total_size
                FROM tool_executions t
                LEFT JOIN tools ON tools.id = t.tool_id
                LEFT JOIN data_files df ON df.tool_execution_id = t.id
                WHERE t.started_at >= datetime('now', ?)
                GROUP BY tool_name, date
                ORDER BY date DESC
            """, (f'-{days} days',))
            
            result = defaultdict(list)
            for row in cursor.fetchall():
                result[row['tool_name']].append({
                    'date': row['date'],
                    'execution_count': row['execution_count'],
                    'output_files': row['output_files'],
                    'total_size': row['total_size'] or 0,
                    'total_size_mb': round((row['total_size'] or 0) / (1024 * 1024), 2)
                })
            
            return dict(result)
        finally:
            conn.close()

    def get_usage_by_user(self, days: int = 30) -> Dict[str, Dict[str, Any]]:
        """
        Get storage usage grouped by user.
        Returns: {user: {total_size, file_count, execution_count}}
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    created_by as user,
                    COUNT(DISTINCT id) as execution_count,
                    (SELECT COUNT(*) FROM data_files df 
                     WHERE df.tool_execution_id = t.id) as output_files,
                    (SELECT COALESCE(SUM(file_size), 0) FROM data_files df 
                     WHERE df.tool_execution_id = t.id) as total_size
                FROM tool_executions t
                WHERE created_by IS NOT NULL
                    AND started_at >= datetime('now', ?)
                GROUP BY created_by
                ORDER BY total_size DESC
            """, (f'-{days} days',))
            
            result = {}
            for row in cursor.fetchall():
                result[row['user']] = {
                    'total_size': row['total_size'] or 0,
                    'total_size_mb': round((row['total_size'] or 0) / (1024 * 1024), 2),
                    'file_count': row['output_files'] or 0,
                    'execution_count': row['execution_count']
                }
            
            return result
        finally:
            conn.close()

    def get_usage_by_file_type(self, days: int = 30) -> Dict[str, Dict[str, Any]]:
        """
        Get storage usage grouped by file type.
        Returns: {file_type: {total_size, file_count}}
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    file_type,
                    COUNT(*) as file_count,
                    COALESCE(SUM(file_size), 0) as total_size
                FROM data_files
                WHERE created_at >= datetime('now', ?)
                GROUP BY file_type
                ORDER BY total_size DESC
            """, (f'-{days} days',))
            
            result = {}
            for row in cursor.fetchall():
                result[row['file_type'] or 'unknown'] = {
                    'total_size': row['total_size'] or 0,
                    'total_size_mb': round((row['total_size'] or 0) / (1024 * 1024), 2),
                    'file_count': row['file_count']
                }
            
            return result
        finally:
            conn.close()

    def get_usage_by_time(self, days: int = 30) -> List[Dict[str, Any]]:
        """
        Get storage usage over time.
        Returns: [{date, total_size, file_count, execution_count}]
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    DATE(started_at) as date,
                    COUNT(*) as execution_count,
                    (SELECT COUNT(*) FROM data_files df 
                     WHERE DATE(df.created_at) = DATE(t.started_at)) as output_files,
                    (SELECT COALESCE(SUM(df.file_size), 0) FROM data_files df 
                     WHERE DATE(df.created_at) = DATE(t.started_at)) as total_size
                FROM tool_executions t
                WHERE started_at >= datetime('now', ?)
                GROUP BY date
                ORDER BY date ASC
            """, (f'-{days} days',))
            
            return [
                {
                    'date': row['date'],
                    'execution_count': row['execution_count'],
                    'output_files': row['output_files'] or 0,
                    'total_size': row['total_size'] or 0,
                    'total_size_mb': round((row['total_size'] or 0) / (1024 * 1024), 2)
                }
                for row in cursor.fetchall()
            ]
        finally:
            conn.close()

    def get_top_storage_consumers(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get top storage consumers by file.
        Returns: [{filepath, size, file_type, created_at}]
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    filepath,
                    file_type,
                    file_size,
                    created_at,
                    workflow_id,
                    tool_execution_id
                FROM data_files
                ORDER BY file_size DESC
                LIMIT ?
            """, (limit,))
            
            return [
                {
                    'filepath': row['filepath'],
                    'file_type': row['file_type'] or 'unknown',
                    'size': row['file_size'] or 0,
                    'size_mb': round((row['file_size'] or 0) / (1024 * 1024), 2),
                    'created_at': row['created_at'],
                    'workflow_id': row['workflow_id'],
                    'tool_execution_id': row['tool_execution_id']
                }
                for row in cursor.fetchall()
            ]
        finally:
            conn.close()

    def get_quota_status(self) -> List[Dict[str, Any]]:
        """Get quota status for all paths with quotas."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    path,
                    quota_bytes,
                    (SELECT COALESCE(SUM(file_size), 0) FROM data_files 
                     WHERE filepath LIKE path || '%%') as used_bytes,
                    updated_at
                FROM storage_quotas
                ORDER BY path
            """)
            
            result = []
            for row in cursor.fetchall():
                used = row['used_bytes'] or 0
                quota = row['quota_bytes'] or 0
                percent = (used / quota * 100) if quota > 0 else 0
                
                result.append({
                    'path': row['path'],
                    'used_bytes': used,
                    'used_mb': round(used / (1024 * 1024), 2),
                    'quota_bytes': quota,
                    'quota_mb': round(quota / (1024 * 1024), 2),
                    'percent_used': round(percent, 2),
                    'remaining_bytes': max(0, quota - used),
                    'remaining_mb': round(max(0, quota - used) / (1024 * 1024), 2),
                    'warning': percent > 80,
                    'critical': percent > 95,
                    'updated_at': row['updated_at']
                })
            
            return result
        finally:
            conn.close()

    def get_storage_trends(self, days: int = 30) -> Dict[str, Any]:
        """
        Get storage usage trends.
        Returns trend analysis with growth rate and projections.
        """
        usage_data = self.get_usage_by_time(days)
        
        if len(usage_data) < 2:
            return {
                'days': days,
                'data_points': len(usage_data),
                'trend': 'insufficient_data',
                'growth_rate': 0,
                'current_usage_mb': usage_data[-1]['total_size_mb'] if usage_data else 0,
                'projected_30d_mb': usage_data[-1]['total_size_mb'] if usage_data else 0
            }
        
        # Calculate growth rate
        first = usage_data[0]['total_size'] or 0
        last = usage_data[-1]['total_size'] or 0
        
        if first > 0:
            growth_rate = ((last - first) / first) * 100
        else:
            growth_rate = 100 if last > 0 else 0
        
        # Determine trend
        if growth_rate > 50:
            trend = 'rapid_growth'
        elif growth_rate > 20:
            trend = 'moderate_growth'
        elif growth_rate > 0:
            trend = 'slow_growth'
        elif growth_rate > -20:
            trend = 'stable'
        else:
            trend = 'declining'
        
        # Project 30 days ahead
        daily_growth = (last - first) / len(usage_data) if len(usage_data) > 1 else 0
        projected_30d = last + (daily_growth * 30)
        
        return {
            'days': days,
            'data_points': len(usage_data),
            'trend': trend,
            'growth_rate': round(growth_rate, 2),
            'current_usage_mb': round(last / (1024 * 1024), 2),
            'daily_growth_mb': round(daily_growth / (1024 * 1024), 2),
            'projected_30d_mb': round(projected_30d / (1024 * 1024), 2),
            'history': usage_data
        }

    def get_execution_summary(self, days: int = 30) -> Dict[str, Any]:
        """
        Get summary of executions and storage metrics.
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Get basic stats
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_executions,
                    COUNT(DISTINCT tool_id) as unique_tools,
                    COUNT(DISTINCT created_by) as unique_users,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                    SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) as running
                FROM tool_executions
                WHERE started_at >= datetime('now', ?)
            """, (f'-{days} days',))
            
            exec_stats = cursor.fetchone()
            
            # Get storage stats
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_files,
                    COALESCE(SUM(file_size), 0) as total_size
                FROM data_files
                WHERE created_at >= datetime('now', ?)
            """, (f'-{days} days',))
            
            storage_stats = cursor.fetchone()
            
            return {
                'period_days': days,
                'executions': {
                    'total': exec_stats['total_executions'] or 0,
                    'unique_tools': exec_stats['unique_tools'] or 0,
                    'unique_users': exec_stats['unique_users'] or 0,
                    'completed': exec_stats['completed'] or 0,
                    'failed': exec_stats['failed'] or 0,
                    'running': exec_stats['running'] or 0,
                    'success_rate': round(
                        ((exec_stats['completed'] or 0) / (exec_stats['total_executions'] or 1)) * 100, 2
                    )
                },
                'storage': {
                    'total_files': storage_stats['total_files'] or 0,
                    'total_size': storage_stats['total_size'] or 0,
                    'total_size_mb': round((storage_stats['total_size'] or 0) / (1024 * 1024), 2)
                }
            }
        finally:
            conn.close()

    def generate_report(self, days: int = 30) -> Dict[str, Any]:
        """
        Generate comprehensive storage analytics report.
        """
        return {
            'generated_at': datetime.now().isoformat(),
            'period_days': days,
            'summary': self.get_execution_summary(days),
            'usage_by_tool': self.get_usage_by_tool(days),
            'usage_by_user': self.get_usage_by_user(days),
            'usage_by_file_type': self.get_usage_by_file_type(days),
            'usage_by_time': self.get_usage_by_time(days),
            'top_consumers': self.get_top_storage_consumers(),
            'quota_status': self.get_quota_status(),
            'trends': self.get_storage_trends(days)
        }


def get_api_endpoints() -> List[Dict[str, str]]:
    """Return list of API endpoints for storage analytics."""
    return [
        {'method': 'GET', 'path': '/api/storage/usage', 'description': 'Get storage usage summary'},
        {'method': 'GET', 'path': '/api/storage/usage/by-tool', 'description': 'Get usage grouped by tool'},
        {'method': 'GET', 'path': '/api/storage/usage/by-user', 'description': 'Get usage grouped by user'},
        {'method': 'GET', 'path': '/api/storage/usage/by-type', 'description': 'Get usage grouped by file type'},
        {'method': 'GET', 'path': '/api/storage/usage/trends', 'description': 'Get storage usage trends'},
        {'method': 'GET', 'path': '/api/storage/top-consumers', 'description': 'Get top storage consumers'},
        {'method': 'GET', 'path': '/api/storage/quotas', 'description': 'Get quota status'},
        {'method': 'GET', 'path': '/api/storage/report', 'description': 'Get comprehensive analytics report'}
    ]


def main():
    """Demo storage analytics functionality."""
    analytics = StorageAnalytics()
    
    print("Storage Analytics Report")
    print("=" * 50)
    
    report = analytics.generate_report(days=30)
    
    print(f"\nGenerated at: {report['generated_at']}")
    print(f"\nSummary:")
    print(f"  Executions (30 days): {report['summary']['executions']['total']}")
    print(f"  Storage (30 days): {report['summary']['storage']['total_size_mb']} MB")
    print(f"  Success rate: {report['summary']['executions']['success_rate']}%")
    
    print(f"\nTrends:")
    print(f"  Trend: {report['trends']['trend']}")
    print(f"  Growth rate: {report['trends']['growth_rate']}%")
    print(f"  Projected 30d usage: {report['trends']['projected_30d_mb']} MB")
    
    print(f"\nTop Storage Consumers:")
    for i, consumer in enumerate(report['top_consumers'][:5], 1):
        print(f"  {i}. {consumer['filepath']}: {consumer['size_mb']} MB")


if __name__ == '__main__':
    main()
