"""Core business logic modules for Virometrics platform."""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB_PATH = os.path.join(BASE_DIR, 'data', 'virometrics.db')


def get_db_path():
    """Get the database path."""
    return DEFAULT_DB_PATH
