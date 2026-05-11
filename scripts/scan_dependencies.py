#!/usr/bin/env python3
"""
Scan tools and populate the dependency registry.
Can be run to auto-detect and register dependencies for all tools.
"""

import sqlite3
import json
import sys
import os
from pathlib import Path

# Default paths
DEFAULT_DB_PATH = "/home/ihcm-ubuntu/Virometrics/data/virometrics.db"


def get_connection(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def scan_all_tools(db_path=None):
    """Scan all tools and register their dependencies."""
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    conn = get_connection(db_path)
    cursor = conn.cursor()

    # Get all tools
    cursor.execute("SELECT id, name, package_manager, packages_needed, description FROM tools")
    tools = cursor.fetchall()

    print(f"Scanning {len(tools)} tools for dependencies...\n")

    total_registered = 0

    for tool in tools:
        tool_id = tool['id']
        tool_name = tool['name']

        print(f"[{tool_id}] {tool_name}...", end=' ')

        # Check packages_needed field
        packages = tool['packages_needed']
        registered = []

        if packages:
            try:
                pkgs = json.loads(packages) if isinstance(packages, str) else packages
                if isinstance(pkgs, dict):
                    if 'bioconda' in pkgs:
                        dep_id = register_dependency(conn, {
                            'name': pkgs['bioconda'],
                            'package_manager': 'bioconda',
                            'install_command': f"conda install -y -c bioconda {pkgs['bioconda']}",
                            'description': tool['description']
                        })
                        if dep_id:
                            link_tool(conn, tool_id, dep_id)
                            registered.append(pkgs['bioconda'])

                    if 'pip' in pkgs:
                        pip_pkgs = pkgs['pip'] if isinstance(pkgs['pip'], list) else [pkgs['pip']]
                        for pkg in pip_pkgs:
                            dep_id = register_dependency(conn, {
                                'name': pkg,
                                'package_manager': 'pip',
                                'install_command': f"pip install {pkg}",
                            })
                            if dep_id:
                                link_tool(conn, tool_id, dep_id)
                                registered.append(pkg)

            except Exception as e:
                print(f"error parsing packages: {e}")

        # Check package_manager field
        pkg_mgr = tool['package_manager']
        if pkg_mgr and pkg_mgr.lower() in ('conda', 'bioconda'):
            cursor.execute(
                "SELECT id FROM dependencies WHERE name=? AND package_manager='conda'",
                (tool_name,)
            )
            if not cursor.fetchone():
                dep_id = register_dependency(conn, {
                    'name': tool_name,
                    'package_manager': 'conda',
                    'install_command': f"conda install -y -c bioconda {tool_name}",
                    'description': tool['description']
                })
                if dep_id:
                    link_tool(conn, tool_id, dep_id)
                    registered.append(tool_name)

        if registered:
            print(f"registered: {', '.join(registered)}")
            total_registered += len(registered)
        else:
            print("no new dependencies")

    conn.commit()
    conn.close()

    print(f"\nTotal dependencies registered: {total_registered}")
    return total_registered


def register_dependency(conn, dep_info):
    """Register a dependency if not already present."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT OR IGNORE INTO dependencies
               (name, version, package_manager, install_command, description)
               VALUES (?, ?, ?, ?, ?)""",
            (
                dep_info['name'],
                dep_info.get('version'),
                dep_info['package_manager'],
                dep_info.get('install_command'),
                dep_info.get('description', '')
            )
        )
        if cursor.lastrowid:
            return cursor.lastrowid

        # Get existing
        cursor.execute(
            "SELECT id FROM dependencies WHERE name=? AND package_manager=?",
            (dep_info['name'], dep_info['package_manager'])
        )
        row = cursor.fetchone()
        return row['id'] if row else None
    except Exception as e:
        print(f"  Error registering: {e}")
        return None


def link_tool(conn, tool_id, dep_id):
    """Link tool to dependency."""
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT OR IGNORE INTO tool_dependencies (tool_id, dependency_id)
               VALUES (?, ?)""",
            (tool_id, dep_id)
        )
    except Exception as e:
        print(f"  Error linking: {e}")


if __name__ == '__main__':
    db_path = sys.argv[1] if len(sys.argv) > 1 else None
    scan_all_tools(db_path)
