"""
Logging Mixin for Virometrics tools.
Provides structured logging with JSON formatting.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum


class LogLevel(Enum):
    """Standard log levels for tools."""
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50


class StructuredFormatter(logging.Formatter):
    """JSON-formatted log formatter for machine parsing."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Add extra fields if present
        if hasattr(record, 'extra_data'):
            log_entry['data'] = record.extra_data
        
        # Add exception info if present
        if record.exc_info:
            log_entry['exception'] = {
                'type': record.exc_info[0].__name__,
                'message': str(record.exc_info[1]),
                'traceback': self.formatException(record.exc_info)
            }
        
        return json.dumps(log_entry)


class TextFormatter(logging.Formatter):
    """Human-readable text formatter."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as human-readable text."""
        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        return f"[{timestamp}] {record.levelname:8} {record.name}: {record.getMessage()}"


class ToolLogger:
    """Logger for bioinformatics tools with structured output."""
    
    def __init__(self, name: str, 
                 log_level: LogLevel = LogLevel.INFO,
                 json_format: bool = False,
                 log_file: Optional[str] = None):
        """
        Initialize tool logger.
        
        Args:
            name: Logger name (typically tool name)
            log_level: Minimum log level to capture
            json_format: Whether to use JSON formatting
            log_file: Optional file path for log output
        """
        self.name = name
        self._logger = logging.getLogger(name)
        self._logger.setLevel(log_level.value)
        self._logger.handlers = []  # Clear existing handlers
        
        # Create formatter
        if json_format:
            formatter = StructuredFormatter()
        else:
            formatter = TextFormatter()
        
        # Add console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self._logger.addHandler(console_handler)
        
        # Add file handler if specified
        if log_file:
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(formatter)
            self._logger.addHandler(file_handler)
    
    def _log(self, level: LogLevel, message: str, **extra) -> None:
        """Internal log method."""
        record = self._logger.makeRecord(
            self.name, level.value, '', 0, message, (), None
        )
        if extra:
            record.extra_data = extra
        self._logger.handle(record)
    
    def debug(self, message: str, **extra) -> None:
        """Log debug message."""
        self._log(LogLevel.DEBUG, message, **extra)
    
    def info(self, message: str, **extra) -> None:
        """Log info message."""
        self._log(LogLevel.INFO, message, **extra)
    
    def warning(self, message: str, **extra) -> None:
        """Log warning message."""
        self._log(LogLevel.WARNING, message, **extra)
    
    def error(self, message: str, **extra) -> None:
        """Log error message."""
        self._log(LogLevel.ERROR, message, **extra)
    
    def critical(self, message: str, **extra) -> None:
        """Log critical message."""
        self._log(LogLevel.CRITICAL, message, **extra)
    
    def exception(self, message: str, exc_info: tuple, **extra) -> None:
        """Log exception with traceback."""
        record = self._logger.makeRecord(
            self.name, LogLevel.ERROR.value, '', 0, message, (), exc_info
        )
        if extra:
            record.extra_data = extra
        self._logger.handle(record)
    
    def set_level(self, level: LogLevel) -> None:
        """Set minimum log level."""
        self._logger.setLevel(level.value)
    
    def add_file_handler(self, log_file: str, 
                         json_format: bool = False) -> None:
        """Add file handler to logger."""
        if json_format:
            formatter = StructuredFormatter()
        else:
            formatter = TextFormatter()
        
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        self._logger.addHandler(file_handler)
    
    def remove_handlers(self) -> None:
        """Remove all handlers."""
        self._logger.handlers = []


class LoggingMixin:
    """
    Mixin class that adds logging capabilities to tools.
    Can be combined with BioinformaticsTool for standardized logging.
    """
    
    def __init__(self, *args, 
                 log_level: LogLevel = LogLevel.INFO,
                 json_format: bool = False,
                 log_file: Optional[str] = None,
                 **kwargs):
        """Initialize logging mixin."""
        super().__init__(*args, **kwargs)
        
        tool_name = getattr(self, 'TOOL_NAME', self.__class__.__name__)
        self._logger = ToolLogger(
            name=tool_name,
            log_level=log_level,
            json_format=json_format,
            log_file=log_file
        )
        
        # Log initialization
        self._logger.info(f"Initialized {tool_name} v{getattr(self, 'TOOL_VERSION', 'unknown')}")
    
    @property
    def logger(self) -> ToolLogger:
        """Get the tool logger."""
        return self._logger
    
    def set_log_level(self, level: LogLevel) -> None:
        """Set log level for this tool."""
        self._logger.set_level(level)
    
    def add_log_file(self, log_file: str, json_format: bool = False) -> None:
        """Add file output to logger."""
        self._logger.add_file_handler(log_file, json_format)
