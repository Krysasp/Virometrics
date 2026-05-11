"""Execution API endpoints for Virometrics platform."""

import json
import logging
from flask import Blueprint, request, jsonify, Response, current_app
from core.executor import ToolExecutor
from core.sse_stream import SSEStream, create_sse_response
from core import get_db_path

logger = logging.getLogger(__name__)

bp = Blueprint('execution', __name__, url_prefix='/api')

executor = None


def init_executor(db_path):
    """Initialize the executor instance."""
    global executor
    executor = ToolExecutor(db_path)


@bp.route('/execute/<int:tool_id>', methods=['POST'])
def start_execution(tool_id):
    """Start tool execution with parameters."""
    try:
        data = request.get_json(silent=True) or {}
        command = data.get('command')
        working_dir = data.get('working_dir')
        execution_name = data.get('execution_name')
        timeout = data.get('timeout', 3600)
        auto_install = data.get('auto_install', True)

        # Auto-install tool if requested and not already installed
        install_info = None
        if auto_install:
            from core.tool_installer import ToolInstaller
            installer = ToolInstaller(db_path=get_db_path())
            install_info = installer.install_tool(tool_id, auto_install=True)
            
            if not install_info.get('success') and install_info.get('action') != 'skipped':
                logger.warning(f"Tool installation skipped: {install_info.get('message')}")

        if not command:
            # Build command from parameters
            params = data.get('parameters', {})
            command = build_command_from_params(tool_id, params, working_dir)

        if not command:
            return jsonify({'error': 'No command provided'}), 400

        execution_id = executor.execute(
            tool_id=tool_id,
            command=command,
            working_dir=working_dir or current_app.config.get('OUTPUT_FOLDER'),
            execution_name=execution_name,
            timeout=timeout
        )

        response = {
            'execution_id': execution_id,
            'status': 'pending',
            'message': 'Execution started'
        }
        
        if install_info:
            response['installation'] = {
                'action': install_info.get('action'),
                'message': install_info.get('message'),
                'install_path': install_info.get('install_path')
            }

        return jsonify(response)

    except Exception as e:
        logger.error(f"Error starting execution: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/execute/<int:execution_id>/stream')
def stream_execution(execution_id):
    """SSE stream for real-time execution output."""
    stream = SSEStream(executor, execution_id)

    def generator():
        yield ": connected\n\n"
        for event in stream.stream():
            yield event

    return Response(
        generator(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        }
    )


@bp.route('/execute/<int:execution_id>', methods=['GET'])
def get_execution(execution_id):
    """Get execution status."""
    status = executor.get_status(execution_id)
    if not status:
        return jsonify({'error': 'Execution not found'}), 404
    return jsonify(status)


@bp.route('/execute/<int:execution_id>', methods=['DELETE'])
def cancel_execution(execution_id):
    """Cancel a running execution."""
    success = executor.cancel(execution_id)
    if success:
        return jsonify({'message': 'Execution cancelled'})
    return jsonify({'error': 'Could not cancel execution'}), 400


@bp.route('/executions', methods=['GET'])
def list_executions():
    """List recent executions."""
    tool_id = request.args.get('tool_id', type=int)
    limit = request.args.get('limit', 50, type=int)
    executions = executor.list_executions(tool_id=tool_id, limit=limit)
    return jsonify(executions)


@bp.route('/tools/<int:tool_id>/parameters', methods=['GET'])
def get_tool_parameters(tool_id):
    """Get tool parameter definitions."""
    import sqlite3
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM tool_parameters WHERE tool_id=? ORDER BY position",
            (tool_id,)
        )
        params = [dict(r) for r in cursor.fetchall()]
        return jsonify(params)
    finally:
        conn.close()


@bp.route('/tools/<int:tool_id>/parameters', methods=['POST'])
def save_tool_parameters(tool_id):
    """Save tool parameter definitions."""
    import sqlite3
    data = request.get_json(silent=True)
    if not data or not isinstance(data, list):
        return jsonify({'error': 'Expected list of parameters'}), 400

    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        # Clear existing
        cursor.execute("DELETE FROM tool_parameters WHERE tool_id=?", (tool_id,))

        # Insert new
        for i, param in enumerate(data):
            cursor.execute(
                """INSERT INTO tool_parameters
                   (tool_id, param_name, param_type, param_label,
                    param_description, default_value, required,
                    choices, validation_regex, position, group_name)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    tool_id,
                    param.get('name'),
                    param.get('type', 'string'),
                    param.get('label'),
                    param.get('description'),
                    param.get('default'),
                    param.get('required', False),
                    json.dumps(param.get('choices', [])),
                    param.get('validation'),
                    param.get('position', i),
                    param.get('group')
                )
            )
        conn.commit()
        return jsonify({'message': f'Saved {len(data)} parameters'})
    finally:
        conn.close()


def build_command_from_params(tool_id, params, working_dir: str = None):
    """Build a command string from tool parameters."""
    import sqlite3
    conn = sqlite3.connect(get_db_path())
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, repo_path, packages_needed FROM tools WHERE id=?", (tool_id,)
        )
        tool = cursor.fetchone()
        if not tool:
            return None

        # Start with tool name
        tool_name = tool[1]
        repo_path = tool[2]
        packages = json.loads(tool[3] or '{}')
        
        # Determine executable path
        if repo_path and packages.get('package_manager') == 'source':
            # Use installed source path
            cmd_parts = [str(Path(repo_path) / tool_name)]
        else:
            cmd_parts = [tool_name]

        # Add parameters
        for name, value in params.items():
            if value is None or value == '':
                continue
            if isinstance(value, bool):
                if value:
                    cmd_parts.append(f"--{name}")
            elif isinstance(value, (list, tuple)):
                cmd_parts.append(f"--{name}")
                cmd_parts.extend(str(v) for v in value)
            else:
                cmd_parts.append(f"--{name}")
                cmd_parts.append(str(value))

        return ' '.join(cmd_parts)
    finally:
        conn.close()
