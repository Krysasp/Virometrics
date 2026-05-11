#!/usr/bin/env python3
"""
Simple HTTP server for testing the Virometrics dashboard locally.
Run: python3 serve.py
Then visit: http://localhost:8000/web/
"""

import http.server
import socketserver
import os

PORT = 8000
project_dir = os.path.dirname(os.path.abspath(__file__))

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=project_dir, **kwargs)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        self.send_header('Expires', '0')
        super().end_headers()

if __name__ == '__main__':
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"Virometrics dashboard serving at:")
        print(f"  http://localhost:{PORT}/web/")
        print(f"\nPress Ctrl+C to stop")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")
