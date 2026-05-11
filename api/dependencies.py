"""Dependencies API endpoints for Virometrics platform."""

import json
import logging
from flask import Blueprint, request, jsonify
from core.dependency_checker import DependencyChecker
from core import get_db_path

logger = logging.getLogger(__name__)

bp = Blueprint('dependencies', __name__, url_prefix='/api')

checker = None


def init_checker(db_path):
    """Initialize the dependency checker."""
    global checker
    checker = DependencyChecker(db_path)


@bp.route('/dependencies', methods=['GET'])
def list_dependencies():
    """List all dependencies with install status."""
    import sqlite3
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM dependencies ORDER BY name")
        deps = [dict(r) for r in cursor.fetchall()]

        # Add install status for each
        for dep in deps:
            status = checker.check_dependency(dep['id'])
            dep['installed'] = status['installed']
            dep['installed_version'] = status.get('version')
            dep['install_status'] = status['status']

        return jsonify(deps)
    finally:
        conn.close()


@bp.route('/dependencies/<int:dep_id>', methods=['GET'])
def get_dependency(dep_id):
    """Get dependency details."""
    import sqlite3
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM dependencies WHERE id=?", (dep_id,))
        dep = cursor.fetchone()
        if not dep:
            return jsonify({'error': 'Not found'}), 404

        result = dict(dep)
        status = checker.check_dependency(dep_id)
        result['status'] = status
        return jsonify(result)
    finally:
        conn.close()


@bp.route('/dependencies/check/<int:dep_id>', methods=['POST'])
def check_dependency(dep_id):
    """Check if a dependency is installed."""
    status = checker.check_dependency(dep_id)
    return jsonify(status)


@bp.route('/dependencies/install/<int:dep_id>', methods=['POST'])
def install_dependency(dep_id):
    """Install a dependency."""
    success, message = checker.install_dependency(dep_id)
    return jsonify({'success': success, 'message': message})


@bp.route('/tools/<int:tool_id>/dependencies', methods=['GET'])
def get_tool_dependencies(tool_id):
    """Get dependencies for a tool."""
    import sqlite3
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT d.*, td.is_optional, td.install_hint
               FROM dependencies d
               JOIN tool_dependencies td ON td.dependency_id = d.id
               WHERE td.tool_id=?""",
            (tool_id,)
        )
        deps = [dict(r) for r in cursor.fetchall()]

        # Add install status
        for dep in deps:
            status = checker.check_dependency(dep['id'])
            dep['installed'] = status['installed']
            dep['status'] = status['status']

        return jsonify(deps)
    finally:
        conn.close()


@bp.route('/tools/<int:tool_id>/dependencies', methods=['POST'])
def add_tool_dependency(tool_id):
    """Add a dependency to a tool."""
    import sqlite3
    data = request.get_json(silent=True)
    if not data or 'dependency_id' not in data:
        return jsonify({'error': 'dependency_id required'}), 400

    conn = sqlite3.connect(get_db_path())
    try:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT OR IGNORE INTO tool_dependencies
               (tool_id, dependency_id, is_optional, install_hint)
               VALUES (?, ?, ?, ?)""",
            (tool_id, data['dependency_id'],
             data.get('is_optional', False), data.get('install_hint', ''))
        )
        conn.commit()
        return jsonify({'message': 'Dependency added'})
    finally:
        conn.close()


@bp.route('/dependencies/scan/<int:tool_id>', methods=['POST'])
def scan_tool_deps(tool_id):
    """Scan and register dependencies for a tool."""
    result = checker.scan_tool_dependencies(tool_id)
    return jsonify({'registered': result})
