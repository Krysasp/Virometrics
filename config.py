"""Configuration for Virometrics Flask application."""

import os

# Base directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Database
DATABASE_PATH = os.path.join(BASE_DIR, 'data', 'virometrics.db')

# Directories
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'data', 'uploads')
OUTPUT_FOLDER = os.path.join(BASE_DIR, 'data', 'outputs')
DATA_FOLDER = os.path.join(BASE_DIR, 'data')

# Flask config
SECRET_KEY = os.environ.get('VIOMETRICS_SECRET', 'dev-secret-key-change-in-production')
DEBUG = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'

# SSE settings
SSE_HEARTBEAT_INTERVAL = 15  # seconds between heartbeat comments
SSE_MAX_RETRIES = 3

# Tool execution
MAX_CONCURRENT_EXECUTIONS = 5
EXECUTION_TIMEOUT = 3600  # 1 hour default timeout
ALLOWED_COMMANDS = None  # None = allow all; or list of allowed commands

# CORS
CORS_ORIGINS = ['*']

# File upload
MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 500MB max file size
ALLOWED_EXTENSIONS = {'fastq', 'fq', 'bam', 'sam', 'vcf', 'csv', 'tsv', 'txt', 'json', 'fasta', 'fa', 'fna', 'gz', 'bz2'}
