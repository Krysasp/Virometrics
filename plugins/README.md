# Plugin Development Guide for Virometrics

## Overview

Plugins in Virometrics extend the platform's functionality by adding new tools, 
workflows, data exporters, and other capabilities.

## Plugin Structure

### Directory Layout

```
plugins/
├── my_plugin/
│   ├── plugin.py          # Main plugin code
│   ├── metadata.json      # Plugin metadata
│   └── __init__.py        # Package initializer
```

### Metadata File (metadata.json)

```json
{
    "name": "my_plugin",
    "version": "1.0.0",
    "description": "My custom plugin",
    "author": "Author Name",
    "license": "MIT",
    "plugin_type": "tool",
    "entry_point": "MyPlugin",
    "dependencies": ["base_plugin"],
    "tags": ["bioinformatics", "analysis"],
    "config_schema": {
        "type": "object",
        "properties": {
            "parameter1": {"type": "string"},
            "parameter2": {"type": "integer"}
        }
    }
}
```

## Plugin Types

- **tool**: Bioinformatics tool wrappers
- **workflow**: Workflow definitions
- **exporter**: Data export formats
- **connector**: External service integrations
- **validator**: Input/output validators

## Implementing a Plugin

### 1. Create Plugin Class

```python
from plugins.base_plugin import BasePlugin

class MyPlugin(BasePlugin):
    PLUGIN_NAME = 'my_tool'
    PLUGIN_VERSION = '1.0.0'
    PLUGIN_TYPE = 'tool'
    DESCRIPTION = 'My custom bioinformatics tool'
    
    def initialize(self, config=None):
        self.set_config(config or {})
        self._is_initialized = True
        self._status = 'initialized'
    
    def execute(self, input_file, output_dir):
        # Tool implementation
        pass
```

### 2. Implement Required Methods

- `initialize(config)`: Setup plugin with configuration
- `execute(*args, **kwargs)`: Main functionality
- `cleanup()`: Resource cleanup (optional override)

### 3. Register with PluginManager

```python
from core.plugin_manager import PluginManager

manager = PluginManager('/path/to/plugins')
manager.load_with_dependencies('my_plugin')
```

## Best Practices

1. **Error Handling**: Use try-except blocks and log errors
2. **Configuration**: Validate config in initialize()
3. **Resources**: Clean up in cleanup()
4. **Logging**: Use the LoggingMixin for consistent logging
5. **Dependencies**: Declare dependencies in metadata

## Example Plugins

See `plugins/examples/` for working examples:
- `fastq_plugin.py`: FASTQ file processor
- `vcf_exporter.py`: VCF export functionality
- `workflow_builder.py`: Custom workflow builder
