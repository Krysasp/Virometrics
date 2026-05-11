"""
Plugin Manager for Virometrics.
Handles plugin discovery, loading, and lifecycle management.
"""

import os
import sys
import json
import importlib
import importlib.util
from pathlib import Path
from typing import Dict, List, Optional, Any, Type
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class PluginMetadata:
    """Metadata for a plugin."""
    name: str
    version: str
    description: str
    author: str
    license: str
    plugin_type: str  # e.g., 'tool', 'workflow', 'exporter'
    dependencies: List[str] = field(default_factory=list)
    entry_point: str = 'Plugin'
    config_schema: Optional[Dict[str, Any]] = None
    tags: List[str] = field(default_factory=list)


@dataclass
class PluginInstance:
    """Loaded plugin instance."""
    metadata: PluginMetadata
    instance: Any
    module_path: str
    load_time: str
    status: str = 'loaded'  # loaded, initialized, error, unloaded
    error_message: Optional[str] = None


class PluginManager:
    """
    Manages plugin discovery, loading, and lifecycle.
    """
    
    def __init__(self, plugin_dir: str):
        """
        Initialize plugin manager.
        
        Args:
            plugin_dir: Directory containing plugins
        """
        self.plugin_dir = Path(plugin_dir)
        self._plugins: Dict[str, PluginInstance] = {}
        self._metadata_cache: Dict[str, PluginMetadata] = {}
    
    def discover_plugins(self) -> List[str]:
        """
        Discover available plugins in the plugin directory.
        Returns list of plugin names.
        """
        plugin_names = []
        
        if not self.plugin_dir.exists():
            return plugin_names
        
        # Scan for plugin directories and Python files
        for item in self.plugin_dir.iterdir():
            if item.is_dir() and not item.name.startswith('_'):
                # Check for plugin.py or __init__.py in directory
                plugin_py = item / 'plugin.py'
                init_py = item / '__init__.py'
                
                if plugin_py.exists():
                    plugin_names.append(item.name)
                elif init_py.exists():
                    plugin_names.append(item.name)
            elif item.suffix == '.py' and item.stem != '__init__':
                # Single Python file plugin
                plugin_names.append(item.stem)
        
        return plugin_names
    
    def load_metadata(self, plugin_name: str) -> Optional[PluginMetadata]:
        """
        Load plugin metadata from JSON/YAML file.
        """
        if plugin_name in self._metadata_cache:
            return self._metadata_cache[plugin_name]
        
        plugin_path = self.plugin_dir / plugin_name
        
        # Look for metadata file
        metadata_file = None
        for ext in ['.json', '.yaml', '.yml']:
            potential = plugin_path / f"metadata{ext}"
            if potential.exists():
                metadata_file = potential
                break
        
        # Also check for metadata in parent directory
        if not metadata_file:
            for ext in ['.json', '.yaml', '.yml']:
                potential = self.plugin_dir / f"{plugin_name}_metadata{ext}"
                if potential.exists():
                    metadata_file = potential
                    break
        
        if not metadata_file:
            # Return default metadata if none found
            metadata = PluginMetadata(
                name=plugin_name,
                version='1.0.0',
                description=f'Plugin: {plugin_name}',
                author='Virometrics',
                license='MIT',
                plugin_type='generic'
            )
        else:
            with open(metadata_file, 'r') as f:
                data = json.load(f)
                metadata = PluginMetadata(
                    name=data.get('name', plugin_name),
                    version=data.get('version', '1.0.0'),
                    description=data.get('description', ''),
                    author=data.get('author', 'Unknown'),
                    license=data.get('license', 'MIT'),
                    plugin_type=data.get('plugin_type', 'generic'),
                    dependencies=data.get('dependencies', []),
                    entry_point=data.get('entry_point', 'Plugin'),
                    config_schema=data.get('config_schema'),
                    tags=data.get('tags', [])
                )
        
        self._metadata_cache[plugin_name] = metadata
        return metadata
    
    def load_plugin(self, plugin_name: str) -> PluginInstance:
        """
        Load a plugin from the plugin directory.
        """
        if plugin_name in self._plugins:
            return self._plugins[plugin_name]
        
        plugin_path = self.plugin_dir / plugin_name
        
        # Determine module path
        if plugin_path.is_dir():
            module_path = str(plugin_path / 'plugin.py')
            if not os.path.exists(module_path):
                module_path = str(plugin_path / '__init__.py')
        else:
            module_path = str(plugin_path.with_suffix('.py'))
        
        if not os.path.exists(module_path):
            raise FileNotFoundError(f"Plugin module not found: {module_path}")
        
        # Load module
        spec = importlib.util.spec_from_file_location(plugin_name, module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load spec for {plugin_name}")
        
        module = importlib.util.module_from_spec(spec)
        sys.modules[plugin_name] = module
        spec.loader.exec_module(module)
        
        # Get plugin class
        metadata = self.load_metadata(plugin_name)
        plugin_class = getattr(module, metadata.entry_point, None)
        
        if plugin_class is None:
            raise AttributeError(
                f"Entry point '{metadata.entry_point}' not found in {plugin_name}"
            )
        
        # Create instance
        try:
            instance = plugin_class()
            load_time = datetime.utcnow().isoformat()
            
            plugin_instance = PluginInstance(
                metadata=metadata,
                instance=instance,
                module_path=module_path,
                load_time=load_time
            )
            
            self._plugins[plugin_name] = plugin_instance
            return plugin_instance
            
        except Exception as e:
            plugin_instance = PluginInstance(
                metadata=metadata,
                instance=None,
                module_path=module_path,
                load_time=datetime.utcnow().isoformat(),
                status='error',
                error_message=str(e)
            )
            self._plugins[plugin_name] = plugin_instance
            return plugin_instance
    
    def initialize_plugin(self, plugin_name: str, 
                          config: Optional[Dict[str, Any]] = None) -> PluginInstance:
        """
        Initialize a loaded plugin with configuration.
        """
        if plugin_name not in self._plugins:
            self.load_plugin(plugin_name)
        
        plugin = self._plugins[plugin_name]
        
        if plugin.status == 'error':
            return plugin
        
        try:
            # Call initialize method if available
            if hasattr(plugin.instance, 'initialize'):
                plugin.instance.initialize(config=config)
            plugin.status = 'initialized'
        except Exception as e:
            plugin.status = 'error'
            plugin.error_message = str(e)
        
        return plugin
    
    def unload_plugin(self, plugin_name: str) -> bool:
        """
        Unload a plugin.
        Returns True if successful.
        """
        if plugin_name not in self._plugins:
            return False
        
        plugin = self._plugins[plugin_name]
        
        try:
            # Call cleanup method if available
            if hasattr(plugin.instance, 'cleanup'):
                plugin.instance.cleanup()
            
            plugin.status = 'unloaded'
            return True
            
        except Exception:
            plugin.status = 'error'
            return False
    
    def reload_plugin(self, plugin_name: str) -> PluginInstance:
        """Reload a plugin."""
        self.unload_plugin(plugin_name)
        return self.load_plugin(plugin_name)
    
    def get_plugin(self, plugin_name: str) -> Optional[PluginInstance]:
        """Get a loaded plugin instance."""
        return self._plugins.get(plugin_name)
    
    def list_plugins(self, plugin_type: Optional[str] = None) -> List[str]:
        """List loaded plugin names, optionally filtered by type."""
        if plugin_type:
            return [
                name for name, plugin in self._plugins.items()
                if plugin.metadata.plugin_type == plugin_type
            ]
        return list(self._plugins.keys())
    
    def get_all_metadata(self) -> List[PluginMetadata]:
        """Get metadata for all discovered plugins."""
        plugin_names = self.discover_plugins()
        return [
            self.load_metadata(name) 
            for name in plugin_names
        ]
    
    def resolve_dependencies(self, plugin_name: str) -> List[str]:
        """
        Resolve dependencies for a plugin.
        Returns list of dependency plugin names in load order.
        """
        if plugin_name not in self._plugins:
            self.load_plugin(plugin_name)
        
        plugin = self._plugins[plugin_name]
        dependencies = []
        
        def resolve_deps(name: str, visited: set) -> None:
            if name in visited:
                return
            visited.add(name)
            
            if name not in self._plugins:
                try:
                    self.load_plugin(name)
                except Exception:
                    return
            
            plugin = self._plugins[name]
            for dep in plugin.metadata.dependencies:
                resolve_deps(dep, visited)
                if dep not in dependencies:
                    dependencies.append(dep)
        
        resolve_deps(plugin_name, set())
        return dependencies
    
    def load_with_dependencies(self, plugin_name: str) -> List[str]:
        """
        Load a plugin with all its dependencies.
        Returns list of loaded plugin names in order.
        """
        dependencies = self.resolve_dependencies(plugin_name)
        
        # Load dependencies first
        for dep_name in dependencies:
            if dep_name not in self._plugins:
                self.load_plugin(dep_name)
        
        # Load main plugin
        self.load_plugin(plugin_name)
        
        return dependencies + [plugin_name]
