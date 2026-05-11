#!/usr/bin/env python3
"""
Workflow documentation generator for Virometrics platform.
Auto-generates markdown documentation for workflows from the database.
"""

import os
import sys
import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

# Default paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / 'data'
DB_PATH = DATA_DIR / 'virometrics.db'
DOCS_DIR = DATA_DIR / 'workflows' / 'docs'


def get_connection(db_path: Optional[str] = None):
    """Create database connection."""
    db_path = db_path or str(DB_PATH)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def get_workflows(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Get all workflows from database."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, description, created_at, updated_at, created_by, is_public
        FROM workflows ORDER BY created_at DESC
    """)
    return [dict(row) for row in cursor.fetchall()]


def get_workflow_nodes(conn: sqlite3.Connection, workflow_id: int) -> List[Dict[str, Any]]:
    """Get nodes for a specific workflow."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT node_id, tool_id, node_name, config_json, position_x, position_y
        FROM workflow_nodes WHERE workflow_id=? ORDER BY position_x, position_y
    """, (workflow_id,))
    return [dict(row) for row in cursor.fetchall()]


def get_workflow_connections(conn: sqlite3.Connection, workflow_id: int) -> List[Dict[str, Any]]:
    """Get connections for a specific workflow."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT connection_id, source_node_id, target_node_id, source_output, target_input
        FROM workflow_connections WHERE workflow_id=?
    """, (workflow_id,))
    return [dict(row) for row in cursor.fetchall()]


def get_tool_info(conn: sqlite3.Connection, tool_id: int) -> Optional[Dict[str, Any]]:
    """Get tool information from database."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, category, language, description, input_formats, output_formats
        FROM tools WHERE id=?
    """, (tool_id,))
    row = cursor.fetchone()
    return dict(row) if row else None


def generate_workflow_doc(conn: sqlite3.Connection, workflow: Dict[str, Any]) -> str:
    """Generate markdown documentation for a workflow."""
    workflow_id = workflow['id']
    nodes = get_workflow_nodes(conn, workflow_id)
    connections = get_workflow_connections(conn, workflow_id)
    
    doc_lines = [
        f"# {workflow['name']}",
        "",
        f"**Workflow ID:** `{workflow_id}`",
        "",
        f"**Description:** {workflow.get('description', 'No description available')}",
        "",
        "---",
        "",
        "## Overview",
        "",
    ]
    
    # Add metadata table
    doc_lines.extend([
        "| Property | Value |",
        "|----------|-------|",
        f"| **Created** | {workflow.get('created_at', 'N/A')} |",
        f"| **Updated** | {workflow.get('updated_at', 'N/A')} |",
        f"| **Created By** | {workflow.get('created_by', 'N/A')} |",
        f"| **Public** | {'Yes' if workflow.get('is_public') else 'No'} |",
        f"| **Nodes** | {len(nodes)} |",
        f"| **Connections** | {len(connections)} |",
        "",
    ])
    
    # Add workflow diagram (ASCII art)
    doc_lines.extend([
        "## Workflow Diagram",
        "",
        "```",
    ])
    
    if nodes:
        # Simple ASCII representation
        if len(nodes) == 1:
            doc_lines.append(f"  [{nodes[0]['node_name']}]")
        elif len(nodes) <= 5:
            arrow = " --> "
            nodes_str = arrow.join([f"[{n['node_name']}]" for n in nodes])
            doc_lines.append(f"  {nodes_str}")
        else:
            # Multi-line for larger workflows
            for i, node in enumerate(nodes):
                if i == 0:
                    doc_lines.append(f"  [{node['node_name']}]")
                else:
                    doc_lines.append(f"       |")
                    doc_lines.append(f"       v")
                    doc_lines.append(f"  [{node['node_name']}]")
    else:
        doc_lines.append("  (No nodes defined)")
    
    doc_lines.extend([
        "```",
        "",
    ])
    
    # Add tools used
    doc_lines.extend([
        "## Tools Used",
        "",
    ])
    
    for i, node in enumerate(nodes, 1):
        tool_info = get_tool_info(conn, node['tool_id'])
        doc_lines.append(f"### {i}. {node['node_name']}")
        doc_lines.append("")
        doc_lines.append(f"- **Tool ID:** {node['tool_id']}")
        if tool_info:
            doc_lines.append(f"- **Category:** {tool_info.get('category', 'N/A')}")
            doc_lines.append(f"- **Language:** {tool_info.get('language', 'N/A')}")
            desc = tool_info.get('description', '')
            if desc and len(desc) > 100:
                desc = desc[:100] + "..."
            doc_lines.append(f"- **Description:** {desc or 'N/A'}")
        doc_lines.append("")
    
    # Add connections
    if connections:
        doc_lines.extend([
            "## Data Flow",
            "",
            "| Source | Target | Output | Input |",
            "|--------|--------|--------|-------|",
        ])
        
        for conn in connections:
            source_name = next((n['node_name'] for n in nodes if n['node_id'] == conn['source_node_id']), conn['source_node_id'])
            target_name = next((n['node_name'] for n in nodes if n['node_id'] == conn['target_node_id']), conn['target_node_id'])
            doc_lines.append(f"| {source_name} | {target_name} | {conn.get('source_output', 'output')} | {conn.get('target_input', 'input')} |")
        
        doc_lines.append("")
    
    # Add execution examples
    doc_lines.extend([
        "## Execution Example",
        "",
        "```bash",
        "# Example execution command",
        f"# python -m virometrics execute --workflow {workflow_id} --input input.fastq --output results/",
        "```",
        "",
        "---",
        "",
        f"*Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
    ])
    
    return "\n".join(doc_lines)


def generate_overview_doc(conn: sqlite3.Connection) -> str:
    """Generate overview documentation for all workflows."""
    workflows = get_workflows(conn)
    
    doc_lines = [
        "# Virometrics Workflows Overview",
        "",
        "This document provides an overview of all available workflows in the Virometrics platform.",
        "",
        "---",
        "",
        "## Workflow Summary",
        "",
        "| ID | Name | Description | Created | Public |",
        "|----|------|-------------|---------|--------|",
    ]
    
    for workflow in workflows:
        desc = workflow.get('description', '')[:50]
        if len(workflow.get('description', '')) > 50:
            desc += "..."
        doc_lines.append(
            f"| {workflow['id']} | {workflow['name']} | {desc} | {workflow.get('created_at', 'N/A')[:10]} | {'Yes' if workflow.get('is_public') else 'No'} |"
        )
    
    doc_lines.extend([
        "",
        "## Detailed Documentation",
        "",
    ])
    
    for workflow in workflows:
        doc_lines.append(f"### {workflow['name']}")
        doc_lines.append("")
        doc_lines.append(f"[View full documentation](./workflow_{workflow['id']}.md)")
        doc_lines.append("")
    
    doc_lines.append("---")
    doc_lines.append("")
    doc_lines.append(f"*Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
    
    return "\n".join(doc_lines)


def generate_workflow_docs(db_path: Optional[str] = None, output_dir: Optional[str] = None):
    """Generate documentation for all workflows."""
    conn = get_connection(db_path)
    
    try:
        # Ensure output directory exists
        output_dir = output_dir or str(DOCS_DIR)
        os.makedirs(output_dir, exist_ok=True)
        
        workflows = get_workflows(conn)
        
        if not workflows:
            print("No workflows found in database.")
            # Create sample documentation
            print(f"Created overview documentation at: {output_dir}/index.md")
            with open(os.path.join(output_dir, 'index.md'), 'w') as f:
                f.write(generate_overview_doc(conn))
            return
        
        # Generate overview
        overview_path = os.path.join(output_dir, 'index.md')
        with open(overview_path, 'w') as f:
            f.write(generate_overview_doc(conn))
        print(f"Created overview documentation: {overview_path}")
        
        # Generate individual workflow docs
        for workflow in workflows:
            doc_path = os.path.join(output_dir, f"workflow_{workflow['id']}.md")
            with open(doc_path, 'w') as f:
                f.write(generate_workflow_doc(conn, workflow))
            print(f"  - {workflow['name']}: {doc_path}")
        
        print(f"\nDocumentation generated for {len(workflows)} workflows.")
        print(f"Output directory: {output_dir}")
        
    except Exception as e:
        print(f"Error generating documentation: {e}")
        raise
    finally:
        conn.close()


def main():
    """Main entry point."""
    db_path = sys.argv[1] if len(sys.argv) > 1 else None
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None
    
    print("Generating workflow documentation...")
    print("=" * 50)
    
    generate_workflow_docs(db_path, output_dir)
    
    print("=" * 50)
    print("Done!")


if __name__ == '__main__':
    main()
