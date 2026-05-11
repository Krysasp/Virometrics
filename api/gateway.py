"""
API Gateway for Virometrics.
Provides versioned API endpoints with routing and rate limiting.
"""

import json
import threading
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum


class ApiVersion(Enum):
    """API versions."""
    V1 = 'v1'
    V2 = 'v2'


@dataclass
class ApiRoute:
    """Represents an API route."""
    method: str  # GET, POST, PUT, DELETE
    path: str
    handler: Callable
    version: ApiVersion
    rate_limit: int = 100  # requests per minute
    auth_required: bool = False


@dataclass
class RateLimitState:
    """Rate limit state for a client."""
    client_id: str
    requests: List[float] = field(default_factory=list)
    limit: int = 100
    window_seconds: int = 60


class ApiGateway:
    """
    API Gateway with versioning, routing, and rate limiting.
    """
    
    def __init__(self, base_url: str = '/api'):
        """
        Initialize API gateway.
        
        Args:
            base_url: Base URL path for API
        """
        self.base_url = base_url
        self._routes: Dict[str, ApiRoute] = {}
        self._version_routes: Dict[ApiVersion, Dict[str, ApiRoute]] = {
            ApiVersion.V1: {},
            ApiVersion.V2: {}
        }
        self._rate_limits: Dict[str, RateLimitState] = {}
        self._rate_limit_lock = threading.Lock()
        self._default_rate_limit = 100
        self._rate_window_seconds = 60
    
    def register_route(self, method: str, 
                       path: str,
                       handler: Callable,
                       version: ApiVersion = ApiVersion.V1,
                       rate_limit: Optional[int] = None,
                       auth_required: bool = False) -> None:
        """
        Register an API route.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            path: URL path pattern
            handler: Request handler function
            version: API version
            rate_limit: Rate limit (requests per minute)
            auth_required: Whether authentication is required
        """
        route_key = f"{version.value}.{method}.{path}"
        
        route = ApiRoute(
            method=method,
            path=path,
            handler=handler,
            version=version,
            rate_limit=rate_limit or self._default_rate_limit,
            auth_required=auth_required
        )
        
        self._routes[route_key] = route
        self._version_routes[version][f"{method}.{path}"] = route
    
    def register_versioned_route(self, 
                                 method: str,
                                 path: str,
                                 v1_handler: Callable,
                                 v2_handler: Callable,
                                 rate_limit: Optional[int] = None,
                                 auth_required: bool = False) -> None:
        """
        Register a route with different handlers per version.
        
        Args:
            method: HTTP method
            path: URL path
            v1_handler: Handler for v1
            v2_handler: Handler for v2
            rate_limit: Rate limit
            auth_required: Auth requirement
        """
        self.register_route(
            method, path, v1_handler,
            ApiVersion.V1, rate_limit, auth_required
        )
        self.register_route(
            method, path, v2_handler,
            ApiVersion.V2, rate_limit, auth_required
        )
    
    def get_route(self, method: str, 
                  path: str,
                  version: ApiVersion) -> Optional[ApiRoute]:
        """Get route for a method, path, and version."""
        route_key = f"{method}.{path}"
        return self._version_routes[version].get(route_key)
    
    def check_rate_limit(self, client_id: str, 
                         route: ApiRoute) -> Tuple[bool, int]:
        """
        Check if client has exceeded rate limit.
        
        Returns:
            Tuple of (allowed, remaining_requests)
        """
        with self._rate_limit_lock:
            if client_id not in self._rate_limits:
                self._rate_limits[client_id] = RateLimitState(
                    client_id=client_id,
                    limit=route.rate_limit,
                    window_seconds=self._rate_window_seconds
                )
            
            state = self._rate_limits[client_id]
            now = time.time()
            window_start = now - state.window_seconds
            
            # Clean old requests
            state.requests = [t for t in state.requests if t > window_start]
            
            # Check limit
            request_count = len(state.requests)
            remaining = max(0, state.limit - request_count)
            allowed = request_count < state.limit
            
            return allowed, remaining
    
    def record_request(self, client_id: str) -> None:
        """Record a request from client."""
        with self._rate_limit_lock:
            if client_id in self._rate_limits:
                self._rate_limits[client_id].requests.append(time.time())
    
    def route_request(self, method: str, 
                      path: str,
                      version: ApiVersion,
                      client_id: str = 'anonymous',
                      **kwargs) -> Dict[str, Any]:
        """
        Route a request to the appropriate handler.
        
        Args:
            method: HTTP method
            path: Request path
            version: API version
            client_id: Client identifier
            **kwargs: Request parameters
            
        Returns:
            Response dictionary
        """
        route = self.get_route(method, path, version)
        
        if not route:
            return {
                'status': 404,
                'error': 'Route not found',
                'path': f"{version.value}/{method} {path}"
            }
        
        # Check rate limit
        allowed, remaining = self.check_rate_limit(client_id, route)
        
        if not allowed:
            return {
                'status': 429,
                'error': 'Rate limit exceeded',
                'retry_after': self._rate_window_seconds
            }
        
        # Record request
        self.record_request(client_id)
        
        # Call handler
        try:
            result = route.handler(path=path, version=version, **kwargs)
            return {
                'status': 200,
                'data': result,
                'version': version.value,
                'rate_limit_remaining': remaining
            }
        except Exception as e:
            return {
                'status': 500,
                'error': str(e),
                'version': version.value
            }
    
    def get_routes_for_version(self, version: ApiVersion) -> List[Dict[str, Any]]:
        """Get list of routes for a specific version."""
        routes = []
        for key, route in self._version_routes[version].items():
            method, path = key.split('.', 1)
            routes.append({
                'method': method,
                'path': f"/{version.value}/{path}",
                'auth_required': route.auth_required,
                'rate_limit': route.rate_limit
            })
        return routes
    
    def list_api_versions(self) -> List[str]:
        """List available API versions."""
        return [v.value for v in ApiVersion]


def create_gateway() -> ApiGateway:
    """Factory function to create a configured gateway."""
    gateway = ApiGateway(base_url='/api')
    return gateway
