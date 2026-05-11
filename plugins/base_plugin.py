"""
Base Plugin class for Virometrics.
Provides common functionality for all plugins.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime


class BasePlugin(ABC):
    """
    Abstract base class for all Virometrics plugins.
    Defines the standard plugin interface.
    """
    
    # Plugin metadata (to be overridden by subclasses)
    PLUGIN_NAME: str = 'BasePlugin'
    PLUGIN_VERSION: str = '1.0.0'
    PLUGIN_TYPE: str = 'generic'
    DESCRIPTION: str = 'Base plugin for Virometrics'
    AUTHOR: str = 'Virometrics'
    LICENSE: str = 'MIT'
    DEPENDENCIES: List[str] = []
    TAGS: List[str] = []
    
    def __init__(self):
        """Initialize the plugin."""
        self._is_initialized: bool = False
        self._config: Dict[str, Any] = {}
        self._status: str = 'created'
        self._created_at: str = datetime.utcnow().isoformat()
    
    @abstractmethod
    def initialize(self, config: Optional[Dict[str, Any]] = None) -> None:
        """
        Initialize the plugin with configuration.
        
        Args:
            config: Plugin configuration dictionary
        """
        pass
    
    @abstractmethod
    def execute(self, *args, **kwargs) -> Any:
        """
        Execute the plugin's main functionality.
        
        Returns:
            Plugin execution result
        """
        pass
    
    def cleanup(self) -> None:
        """Clean up plugin resources."""
        self._status = 'cleaned'
        self._is_initialized = False
    
    def get_info(self) -> Dict[str, Any]:
        """Get plugin information."""
        return {
            'name': self.PLUGIN_NAME,
            'version': self.PLUGIN_VERSION,
            'type': self.PLUGIN_TYPE,
            'description': self.DESCRIPTION,
            'author': self.AUTHOR,
            'license': self.LICENSE,
            'dependencies': self.DEPENDENCIES,
            'tags': self.TAGS,
            'status': self._status,
            'initialized': self._is_initialized,
            'created_at': self._created_at
        }
    
    def get_config(self) -> Dict[str, Any]:
        """Get current configuration."""
        return self._config.copy()
    
    def set_config(self, config: Dict[str, Any]) -> None:
        """Set plugin configuration."""
        self._config = config.copy()
    
    def get_config_value(self, key: str, default: Any = None) -> Any:
        """Get a configuration value."""
        return self._config.get(key, default)
    
    @property
    def is_initialized(self) -> bool:
        """Check if plugin is initialized."""
        return self._is_initialized
    
    @property
    def status(self) -> str:
        """Get plugin status."""
        return self._status
