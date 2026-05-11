"""Workflow API endpoints for Virometrics platform."""

import json
import logging
from flask import Blueprint, request, jsonify
from core import get_db_path

logger = logging.getLogger(__name__)

bp = Blueprint('workflows', __name__, url_prefix='/api')

@bp.route('/workflows', methods=['GET'])
def list_workflows():
    """List workflows with optional filters."""
    import sqlite3
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()

        # Build query with filters
        query = "SELECT * FROM workflows WHERE 1=1"
        params = []

        is_public = request.args.get('is_public', type=int)
        if is_public is not None:
            query += " AND is_public = ?"
            params.append(is_public)

        created_by = request.args.get('created_by')
        if created_by:
            query += " AND created_by = ?"
            params.append(created_by)

        query += " ORDER BY updated_at DESC"

        cursor.execute(query, params)
        workflows = [dict(r) for r in cursor.fetchall()]

        # Parse JSON workflow definition for each
        for wf in workflows:
            try:
                wf['workflow_json'] = json.loads(wf['workflow_json'])
            except:
                wf['workflow_json'] = {}

        return jsonify(workflows)
    finally:
        conn.close()


@bp.route('/workflows/<int:wf_id>', methods=['GET'])
def get_workflow(wf_id):
    """Get workflow details."""
    import sqlite3
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM workflows WHERE id=?", (wf_id,))
        wf = cursor.fetchone()
        if not wf:
            return jsonify({'error': 'Workflow not found'}), 404

        result = dict(wf)
        try:
            result['workflow_json'] = json.loads(result['workflow_json'])
        except:
            result['workflow_json'] = {}

        # Get workflow steps
        cursor.execute("""
            SELECT ws.*, t.name as tool_name
            FROM workflow_steps ws
            JOIN tools t ON ws.tool_id = t.id
            WHERE ws.workflow_id=?
            ORDER BY ws.position
        """, (wf_id,))
        steps = [dict(r) for r in cursor.fetchall()]

        for step in steps:
            try:
                step['config_json'] = json.loads(step['config_json']) if step['config_json'] else {}
            except:
                step['config_json'] = {}

        result['steps'] = steps
        return jsonify(result)
    finally:
        conn.close()


@bp.route('/workflows', methods=['POST'])
def create_workflow():
    """Create a new workflow."""
    import sqlite3
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Invalid JSON'}), 400

    required_fields = ['name', 'workflow_json']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400

    conn = sqlite3.connect(get_db_path())
    try:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO workflows
               (name, description, created_by, is_public, workflow_json)
               VALUES (?, ?, ?, ?, ?)""",
            (
                data['name'],
                data.get('description', ''),
                data.get('created_by', 'anonymous'),
                data.get('is_public', 0),
                json.dumps(data['workflow_json'])
            )
        )
        wf_id = cursor.lastrowid
        conn.commit()

        return jsonify({
            'message': 'Workflow created successfully',
            'workflow_id': wf_id
        }), 201
    except Exception as e:
        conn.rollback()
        logger.error(f"Error creating workflow: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@bp.route('/workflows/<int:wf_id>', methods=['PUT'])
def update_workflow(wf_id):
    """Update an existing workflow."""
    import sqlite3
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Invalid JSON'}), 400

    conn = sqlite3.connect(get_db_path())
    try:
        cursor = conn.cursor()
        cursor.execute(
            """UPDATE workflows SET
               name=?, description=?, updated_at=datetime('now'),
               created_by=?, is_public=?, workflow_json=?
               WHERE id=?""",
            (
                data.get('name'),
                data.get('description'),
                data.get('created_by', 'anonymous'),
                data.get('is_public', 0),
                json.dumps(data.get('workflow_json', {})),
                wf_id
            )
        )
        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({'error': 'Workflow not found'}), 404

        return jsonify({'message': 'Workflow updated successfully'})
    except Exception as e:
        conn.rollback()
        logger.error(f"Error updating workflow: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@bp.route('/workflows/<int:wf_id>', methods=['DELETE'])
def delete_workflow(wf_id):
    """Delete a workflow."""
    import sqlite3
    conn = sqlite3.connect(get_db_path())
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM workflows WHERE id=?", (wf_id,))
        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({'error': 'Workflow not found'}), 404

        return jsonify({'message': 'Workflow deleted successfully'})
    except Exception as e:
        conn.rollback()
        logger.error(f"Error deleting workflow: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@bp.route('/workflows/<int:wf_id>/execute', methods=['POST'])
def execute_workflow(wf_id):
    """Start execution of a workflow."""
    from core.workflow_executor import WorkflowExecutor

    data = request.get_json(silent=True) or {}
    execution_name = data.get('execution_name')
    parallel = data.get('parallel', False)

    workflow_executor = WorkflowExecutor(
        db_path=get_db_path(),
        parallel_execution=parallel
    )

    try:
        wf_exec_id = workflow_executor.execute_workflow(
            workflow_id=wf_id,
            execution_name=execution_name,
            created_by=data.get('created_by', 'anonymous'),
            parameters=data.get('parameters', {})
        )

        return jsonify({
            'message': 'Workflow execution started',
            'workflow_execution_id': wf_exec_id,
            'parallel': parallel
        }), 202

    except Exception as e:
        logger.error(f"Error executing workflow: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/workflows/executions/<int:wf_exec_id>', methods=['GET'])
def get_workflow_execution(wf_exec_id):
    """Get workflow execution status."""
    import sqlite3
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT we.*, w.name as workflow_name
            FROM workflow_executions we
            JOIN workflows w ON we.workflow_id = w.id
            WHERE we.id=?
        """, (wf_exec_id,))
        we = cursor.fetchone()
        if not we:
            return jsonify({'error': 'Workflow execution not found'}), 404

        result = dict(we)

        # Get step executions
        cursor.execute("""
            SELECT wse.*, ws.step_id, ws.position, t.name as tool_name
            FROM workflow_step_executions wse
            JOIN workflow_steps ws ON wse.workflow_step_id = ws.id
            JOIN tools t ON ws.tool_id = t.id
            WHERE wse.workflow_execution_id=?
            ORDER BY ws.position
        """, (wf_exec_id,))
        step_execs = [dict(r) for r in cursor.fetchall()]

        result['step_executions'] = step_execs
        return jsonify(result)
    finally:
        conn.close()


@bp.route('/workflows/templates', methods=['GET'])
def get_workflow_templates():
    """Get predefined workflow templates."""
    # Return some common viral analysis workflow templates
    templates = [
        {
            'id': 'variant_calling',
            'name': 'Variant Calling Pipeline',
            'description': 'Standard variant calling workflow: QC -> Alignment -> Variant Calling -> Annotation',
            'steps': [
                {
                    'tool_name': 'fastqc',
                    'config': {'description': 'Quality control of raw reads'},
                    'position': 0
                },
                {
                    'tool_name': 'bwa',
                    'config': {'description': 'Align reads to reference genome'},
                    'position': 1
                },
                {
                    'tool_name': 'samtools',
                    'config': {'description': 'Sort and index BAM file'},
                    'position': 2
                },
                {
                    'tool_name': 'bcftools',
                    'config': {'description': 'Call variants from aligned reads'},
                    'position': 3
                },
                {
                    'tool_name': 'annovar',
                    'config': {'description': 'Annotate variants with functional impact'},
                    'position': 4
                }
            ]
        },
        {
            'id': 'assembly_qc',
            'name': 'Genome Assembly QC',
            'description': 'Quality control for genome assemblies',
            'steps': [
                {
                    'tool_name': 'quast',
                    'config': {'description': 'Assembly quality assessment'},
                    'position': 0
                },
                {
                    'tool_name': 'busco',
                    'config': {'description': 'Benchmarking Universal Single-Copy Orthologs'},
                    'position': 1
                },
                {
                    'tool_name': 'checkm',
                    'config': {'description': 'Assess genome completeness and contamination'},
                    'position': 2
                }
            ]
        }
    ]

    return jsonify(templates)