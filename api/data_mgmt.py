"""Data Management API endpoints for Virometrics platform."""

import logging
from flask import Blueprint, request, jsonify, send_file
from core.file_manager import FileManager
from core.storage_monitor import StorageMonitor
from core import get_db_path
from werkzeug.utils import secure_filename
import os

logger = logging.getLogger(__name__)

bp = Blueprint('data_mgmt', __name__, url_prefix='/api')

file_mgr = None
storage_mon = None


def init_data_mgmt(db_path, upload_folder, output_folder):
    """Initialize data management modules."""
    global file_mgr, storage_mon
    file_mgr = FileManager(db_path)
    storage_mon = StorageMonitor(db_path)


@bp.route('/files', methods=['GET'])
def list_files():
    """List files with optional filters."""
    file_type = request.args.get('file_type')
    directory = request.args.get('directory')
    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)

    files = file_mgr.list_files(
        directory=directory, file_type=file_type,
        limit=limit, offset=offset
    )
    return jsonify(files)


@bp.route('/files/upload', methods=['POST'])
def upload_file():
    """Upload a file."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Empty filename'}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(file_mgr.UPLOAD_DIR, filename)

    try:
        file.save(filepath)
        file_id = file_mgr.register_file(filepath)
        return jsonify({
            'file_id': file_id,
            'filename': filename,
            'filepath': filepath,
            'message': 'File uploaded successfully'
        })
    except Exception as e:
        logger.error(f"Upload error: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/files/<int:file_id>', methods=['GET'])
def get_file_info(file_id):
    """Get file info."""
    info = file_mgr.get_file_info(file_id)
    if not info:
        return jsonify({'error': 'File not found'}), 404
    return jsonify(info)


@bp.route('/files/<int:file_id>', methods=['DELETE'])
def delete_file(file_id):
    """Delete a file."""
    success = file_mgr.delete_file(file_id)
    if success:
        return jsonify({'message': 'File deleted'})
    return jsonify({'error': 'Could not delete file'}), 400


@bp.route('/files/<int:file_id>/download')
def download_file(file_id):
    """Download a file."""
    info = file_mgr.get_file_info(file_id)
    if not info:
        return jsonify({'error': 'File not found'}), 404

    return send_file(
        info['filepath'],
        as_attachment=True,
        download_name=info['filename']
    )


@bp.route('/storage/metrics', methods=['GET'])
def get_storage_metrics():
    """Get current storage metrics."""
    path = request.args.get('path') or storage_mon.data_dir
    metrics = storage_mon.get_disk_usage(path)
    return jsonify(metrics)


@bp.route('/storage/filetypes', methods=['GET'])
def get_file_type_stats():
    """Get file type statistics."""
    directory = request.args.get('directory') or storage_mon.data_dir
    stats = storage_mon.get_file_type_stats(directory)
    return jsonify(stats)


@bp.route('/storage/directories', methods=['GET'])
def get_directory_sizes():
    """Get directory sizes."""
    base_path = request.args.get('path') or storage_mon.data_dir
    max_depth = request.args.get('max_depth', 2, type=int)
    sizes = storage_mon.get_directory_sizes(base_path, max_depth)
    return jsonify(sizes)


@bp.route('/validate/outputs', methods=['POST'])
def validate_outputs():
    """Check if expected output files exist."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Expected JSON body'}), 400

    expected = data.get('expected_files', [])
    directory = data.get('directory')

    if not expected or not directory:
        return jsonify({'error': 'expected_files and directory required'}), 400

    result = file_mgr.validate_outputs(expected, directory)
    return jsonify(result)
