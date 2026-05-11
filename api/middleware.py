"""
Middleware for Virometrics API.
Provides CORS, authentication, logging, and compression.
"""

import json
import zlib
import threading
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable, Tuple
from dataclasses import dataclass, field


@dataclass
class Request:
    """Represents an API request."""
    method: str
    path: str
    headers: Dict[str, str]
    body: Optional[Dict[str, Any]] = None
    client_ip: str = 'unknown'
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass
class Response:
    """Represents an API response."""
    status_code: int
    headers: Dict[str, str]
    body: Any
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class CorsMiddleware:
    """CORS handling middleware."""
    
    def __init__(self, 
                 allowed_origins: List[str] = None,
                 allowed_methods: List[str] = None,
                 allowed_headers: List[str] = None,
                 max_age: int = 86400):
        """
        Initialize CORS middleware.
        
        Args:
            allowed_origins: Allowed origin URLs
            allowed_methods: Allowed HTTP methods
            allowed_headers: Allowed request headers
            max_age: Pre-flight cache duration (seconds)
        """
        self.allowed_origins = allowed_origins or ['*']
        self.allowed_methods = allowed_methods or ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS']
        self.allowed_headers = allowed_headers or ['Content-Type', 'Authorization', 'X-Request-ID']
        self.max_age = max_age
    
    def process_request(self, request: Request) -> Optional[Response]:
        """Handle pre-flight OPTIONS request."""
        if request.method == 'OPTIONS':
            headers = {
                'Access-Control-Allow-Origin': self._get_origin(request),
                'Access-Control-Allow-Methods': ', '.join(self.allowed_methods),
                'Access-Control-Allow-Headers': ', '.join(self.allowed_headers),
                'Access-Control-Max-Age': str(self.max_age),
                'Content-Type': 'application/json'
            }
            return Response(
                status_code=200,
                headers=headers,
                body={'message': 'CORS pre-flight OK'}
            )
        return None
    
    def add_cors_headers(self, response: Response, request: Request) -> Response:
        """Add CORS headers to response."""
        response.headers['Access-Control-Allow-Origin'] = self._get_origin(request)
        return response
    
    def _get_origin(self, request: Request) -> str:
        """Get the allowed origin for a request."""
        request_origin = request.headers.get('Origin', '*')
        if '*' in self.allowed_origins:
            return request_origin
        return request_origin if request_origin in self.allowed_origins else '*'


class AuthMiddleware:
    """Authentication middleware."""
    
    def __init__(self, 
                 api_keys: Dict[str, str] = None,
                 auth_header: str = 'Authorization',
                 token_prefix: str = 'Bearer '):
        """
        Initialize auth middleware.
        
        Args:
            api_keys: Dictionary mapping client IDs to API keys
            auth_header: Header name for auth token
            token_prefix: Prefix for Bearer tokens
        """
        self.api_keys = api_keys or {}
        self.auth_header = auth_header
        self.token_prefix = token_prefix
        self._lock = threading.Lock()
    
    def authenticate(self, request: Request) -> Tuple[bool, Optional[str]]:
        """
        Authenticate a request.
        
        Returns:
            Tuple of (is_authenticated, client_id)
        """
        auth_header = request.headers.get(self.auth_header, '')
        
        # Extract token
        if auth_header.startswith(self.token_prefix):
            token = auth_header[len(self.token_prefix):]
        else:
            token = auth_header
        
        if not token:
            return False, None
        
        # Validate token
        with self._lock:
            for client_id, api_key in self.api_keys.items():
                if token == api_key:
                    return True, client_id
        
        return False, None
    
    def require_auth(self, request: Request, 
                     required_scopes: List[str] = None) -> Tuple[bool, Optional[str]]:
        """
        Require authentication with optional scope check.
        
        Returns:
            Tuple of (is_authorized, client_id)
        """
        is_auth, client_id = self.authenticate(request)
        
        if not is_auth:
            return False, None
        
        return True, client_id


class LoggingMiddleware:
    """Request logging middleware."""
    
    def __init__(self, 
                 log_file: Optional[str] = None,
                 json_format: bool = True,
                 log_body: bool = False):
        """
        Initialize logging middleware.
        
        Args:
            log_file: Optional file path for logs
            json_format: Use JSON formatting
            log_body: Include request body in logs
        """
        self.log_file = log_file
        self.json_format = json_format
        self.log_body = log_body
        self._logs: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
    
    def log_request(self, request: Request, 
                    response: Response,
                    duration_ms: float) -> Dict[str, Any]:
        """Log a request-response pair."""
        log_entry = {
            'timestamp': request.timestamp,
            'method': request.method,
            'path': request.path,
            'client_ip': request.client_ip,
            'status_code': response.status_code,
            'response_time_ms': round(duration_ms, 2),
            'request_size': len(json.dumps(request.body or {})),
            'response_size': len(json.dumps(response.body)),
            'user_agent': request.headers.get('User-Agent', ''),
            'content_type': request.headers.get('Content-Type', '')
        }
        
        if self.log_body and request.body:
            log_entry['request_body'] = request.body
        
        with self._lock:
            self._logs.append(log_entry)
            
            if self.log_file:
                with open(self.log_file, 'a') as f:
                    if self.json_format:
                        f.write(json.dumps(log_entry) + '\n')
                    else:
                        f.write(f"{log_entry['timestamp']} {log_entry['method']} {log_entry['path']} -> {log_entry['status_code']} ({log_entry['response_time_ms']}ms)\n")
        
        return log_entry
    
    def get_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent log entries."""
        with self._lock:
            return self._logs[-limit:][::-1]


class CompressionMiddleware:
    """Response compression middleware."""
    
    def __init__(self, 
                 compression_threshold: int = 1024,
                 min_compression_ratio: float = 0.8):
        """
        Initialize compression middleware.
        
        Args:
            compression_threshold: Minimum response size to compress (bytes)
            min_compression_ratio: Minimum compression ratio to use compression
        """
        self.compression_threshold = compression_threshold
        self.min_compression_ratio = min_compression_ratio
    
    def should_compress(self, body: Any, 
                        content_type: str) -> bool:
        """Check if response should be compressed."""
        if 'application/json' not in content_type:
            return False
        
        body_size = len(json.dumps(body).encode('utf-8'))
        return body_size >= self.compression_threshold
    
    def compress_response(self, response: Response) -> Response:
        """Compress response body if beneficial."""
        content_type = response.headers.get('Content-Type', 'application/json')
        
        if not self.should_compress(response.body, content_type):
            return response
        
        # Compress body
        body_json = json.dumps(response.body)
        compressed = zlib.compress(body_json.encode('utf-8'))
        
        # Check compression ratio
        ratio = len(compressed) / len(body_json.encode('utf-8'))
        
        if ratio >= self.min_compression_ratio:
            response.body = compressed
            response.headers['Content-Encoding'] = 'gzip'
            response.headers['Content-Length'] = str(len(compressed))
        
        return response
    
    def decompress_request(self, request: Request) -> Request:
        """Decompress request body if compressed."""
        encoding = request.headers.get('Content-Encoding', '')
        
        if encoding == 'gzip' and request.body:
            if isinstance(request.body, bytes):
                request.body = zlib.decompress(request.body).decode('utf-8')
        
        return request


def create_middleware_stack() -> Dict[str, Any]:
    """Create a standard middleware stack."""
    return {
        'cors': CorsMiddleware(),
        'auth': AuthMiddleware(),
        'logging': LoggingMiddleware(),
        'compression': CompressionMiddleware()
    }
