#!/usr/bin/env python3
"""
Virometrics Galaxy-like Platform - Main Flask Application.

Extends the existing static dashboard with:
- Tool execution API with real-time SSE streaming
- Dependency management
- Data file management
- Storage monitoring
"""

import os
import sys
import logging
from pathlib import Path

# Add project root to path
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

import config
from flask import Flask, send_from_directory, jsonify, render_template_string
from flask_cors import CORS

# Import API blueprints
from api.execution import bp as execution_bp, init_executor
from api.dependencies import bp as deps_bp, init_checker
from api.data_mgmt import bp as data_bp, init_data_mgmt
from api.data_management import bp as data_mgmt2_bp
from api.workflows import bp as workflows_bp
from api.github import bp as github_bp

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(
    __name__,
    static_folder=str(BASE_DIR / 'web'),
    static_url_path='/web'
)

# Load config
app.config.from_mapping(
    SECRET_KEY=config.SECRET_KEY,
    DATABASE_PATH=config.DATABASE_PATH,
    UPLOAD_FOLDER=config.UPLOAD_FOLDER,
    OUTPUT_FOLDER=config.OUTPUT_FOLDER,
    MAX_CONTENT_LENGTH=config.MAX_CONTENT_LENGTH,
    DEBUG=config.DEBUG,
)

# Enable CORS
CORS(app, origins=config.CORS_ORIGINS)

# Register API blueprints
app.register_blueprint(execution_bp)
app.register_blueprint(deps_bp)
app.register_blueprint(data_bp)
app.register_blueprint(data_mgmt2_bp)
app.register_blueprint(workflows_bp)
app.register_blueprint(github_bp)

# Initialize core modules
init_executor(config.DATABASE_PATH)
init_checker(config.DATABASE_PATH)
init_data_mgmt(config.DATABASE_PATH, config.UPLOAD_FOLDER, config.OUTPUT_FOLDER)


# ---- Static Page Routes (backwards compatible) ----

@app.route('/')
def index():
    """Redirect to dashboard."""
    return send_from_directory(str(BASE_DIR / 'web'), 'index.html')


@app.route('/web/')
def web_index():
    """Serve web dashboard index."""
    return send_from_directory(str(BASE_DIR / 'web'), 'index.html')


@app.route('/web/<path:filename>')
def web_files(filename):
    """Serve web files (HTML, JS, CSS, etc.)."""
    return send_from_directory(str(BASE_DIR / 'web'), filename)


@app.route('/data/<path:filename>')
def data_files(filename):
    """Serve data files (JSON, etc.)."""
    return send_from_directory(str(BASE_DIR / 'data'), filename)


# ---- API Info ----

@app.route('/api')
def api_info():
    """API information endpoint."""
    return jsonify({
        'name': 'Virometrics API',
        'version': '2.0.0',
        'description': 'Galaxy-like platform for viral bioinformatics tools',
        'endpoints': {
            'execution': '/api/execute/<tool_id>',
            'streaming': '/api/execute/<exec_id>/stream',
            'dependencies': '/api/dependencies',
            'files': '/api/files',
            'storage': '/api/storage/metrics'
        }
    })


# ---- Health Check ----

@app.route('/health')
def health_check():
    """Health check endpoint."""
    import sqlite3
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        conn.execute('SELECT 1')
        conn.close()
        return jsonify({'status': 'healthy', 'database': 'connected'})
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500


# ---- Error Handlers ----

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500


# ---- Main ----

if __name__ == '__main__':
    # Ensure directories exist
    os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(config.OUTPUT_FOLDER, exist_ok=True)

    port = int(os.environ.get('PORT', 8000))
    debug = config.DEBUG

    logger.info(f"Starting Virometrics Platform on http://0.0.0.0:{port}")
    logger.info(f"Dashboard: http://localhost:{port}/web/")
    logger.info(f"API: http://localhost:{port}/api")
    logger.info(f"Debug mode: {debug}")

    app.run(host='0.0.0.0', port=port, debug=debug)
