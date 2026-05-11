"""
Tool Interface for Virometrics.
Provides standardized abstract base class for bioinformatics tools.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union
from enum import Enum


class InputFormat(Enum):
    """Supported input formats for bioinformatics tools."""
    FASTA = 'fasta'
    FASTQ = 'fastq'
    BAM = 'bam'
    SAM = 'sam'
    VCF = 'vcf'
    GFF = 'gff'
    GTF = 'gtf'
    JSON = 'json'
    TSV = 'tsv'
    CSV = 'csv'


class OutputFormat(Enum):
    """Supported output formats from bioinformatics tools."""
    FASTA = 'fasta'
    FASTQ = 'fastq'
    BAM = 'bam'
    SAM = 'sam'
    VCF = 'vcf'
    GFF = 'gff'
    JSON = 'json'
    TSV = 'tsv'
    CSV = 'csv'
    LOG = 'log'


@dataclass
class ValidationResult:
    """Result of input validation."""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    normalized_inputs: Optional[Dict[str, Any]] = None


@dataclass
class ExecutionResult:
    """Result of tool execution."""
    success: bool
    return_code: int
    output: Any
    stderr: str = ''
    stdout: str = ''
    execution_time: float = 0.0
    memory_usage_mb: float = 0.0


@dataclass
class ToolMetrics:
    """Performance metrics from tool execution."""
    total_runtime_seconds: float = 0.0
    peak_memory_mb: float = 0.0
    input_size_bytes: int = 0
    output_size_bytes: int = 0
    cpu_percent: float = 0.0
    threads_used: int = 1
    additional_metrics: Dict[str, Any] = field(default_factory=dict)


class BioinformaticsTool(ABC):
    """
    Abstract base class for all bioinformatics tools in Virometrics.
    Enforces standard interface for validation, execution, and metrics extraction.
    """
    
    # Class attributes to be set by subclasses
    TOOL_NAME: str = ''
    TOOL_VERSION: str = ''
    DESCRIPTION: str = ''
    INPUT_FORMATS: List[InputFormat] = []
    OUTPUT_FORMATS: List[OutputFormat] = []
    REQUIRED_PARAMETERS: List[str] = []
    OPTIONAL_PARAMETERS: Dict[str, Any] = field(default_factory=dict)
    
    def __init__(self, **kwargs):
        """Initialize tool with parameters."""
        self._parameters: Dict[str, Any] = {}
        self._set_parameters(**kwargs)
        self._last_result: Optional[ExecutionResult] = None
        self._last_metrics: Optional[ToolMetrics] = None
    
    def _set_parameters(self, **kwargs) -> None:
        """Set tool parameters from keyword arguments."""
        for key, value in kwargs.items():
            if key.startswith('_'):
                setattr(self, key, value)
            else:
                self._parameters[key] = value
    
    def get_parameter(self, name: str, default: Any = None) -> Any:
        """Get a parameter value."""
        return self._parameters.get(name, default)
    
    def set_parameter(self, name: str, value: Any) -> None:
        """Set a parameter value."""
        self._parameters[name] = value
    
    def get_parameters(self) -> Dict[str, Any]:
        """Get all parameters."""
        return self._parameters.copy()
    
    @abstractmethod
    def validate_inputs(self, inputs: Dict[str, Any]) -> ValidationResult:
        """
        Validate input formats and values.
        
        Args:
            inputs: Dictionary of input file paths and parameters
            
        Returns:
            ValidationResult with validation status and any errors/warnings
        """
        pass
    
    @abstractmethod
    def execute(self, inputs: Dict[str, Any], 
                output_dir: str,
                **kwargs) -> ExecutionResult:
        """
        Execute the tool with validated inputs.
        
        Args:
            inputs: Dictionary of validated input file paths
            output_dir: Directory for output files
            **kwargs: Additional execution parameters
            
        Returns:
            ExecutionResult with tool output and execution info
        """
        pass
    
    @abstractmethod
    def parse_outputs(self, output_dir: str,
                      execution_result: ExecutionResult) -> Dict[str, Any]:
        """
        Parse tool outputs into structured data.
        
        Args:
            output_dir: Directory containing output files
            execution_result: Result from the execute() call
            
        Returns:
            Dictionary of parsed outputs
        """
        pass
    
    @abstractmethod
    def get_metrics(self, execution_result: ExecutionResult,
                    inputs: Dict[str, Any],
                    outputs: Dict[str, Any]) -> ToolMetrics:
        """
        Extract performance metrics from execution.
        
        Args:
            execution_result: Result from the execute() call
            inputs: Input files used
            outputs: Parsed outputs
            
        Returns:
            ToolMetrics with performance data
        """
        pass
    
    def run(self, inputs: Dict[str, Any], 
            output_dir: str,
            **kwargs) -> Tuple[ExecutionResult, Dict[str, Any], ToolMetrics]:
        """
        Run complete tool execution pipeline.
        
        Args:
            inputs: Dictionary of input file paths and parameters
            output_dir: Directory for output files
            **kwargs: Additional parameters
            
        Returns:
            Tuple of (ExecutionResult, parsed_outputs, ToolMetrics)
        """
        # Validate inputs
        validation = self.validate_inputs(inputs)
        if not validation.is_valid:
            raise ValueError(f"Input validation failed: {validation.errors}")
        
        # Execute tool
        result = self.execute(validation.normalized_inputs or inputs, output_dir, **kwargs)
        self._last_result = result
        
        # Parse outputs
        parsed_outputs = self.parse_outputs(output_dir, result)
        
        # Extract metrics
        metrics = self.get_metrics(result, inputs, parsed_outputs)
        self._last_metrics = metrics
        
        return result, parsed_outputs, metrics
    
    @classmethod
    def get_info(cls) -> Dict[str, Any]:
        """Get tool information."""
        return {
            'name': cls.TOOL_NAME,
            'version': cls.TOOL_VERSION,
            'description': cls.DESCRIPTION,
            'input_formats': [f.value for f in cls.INPUT_FORMATS],
            'output_formats': [f.value for f in cls.OUTPUT_FORMATS],
            'required_parameters': cls.REQUIRED_PARAMETERS,
            'optional_parameters': cls.OPTIONAL_PARAMETERS
        }
    
    @classmethod
    def is_compatible_input(cls, format_str: str) -> bool:
        """Check if input format is supported."""
        return format_str.lower() in [f.value.lower() for f in cls.INPUT_FORMATS]
    
    @classmethod
    def is_compatible_output(cls, format_str: str) -> bool:
        """Check if output format is supported."""
        return format_str.lower() in [f.value.lower() for f in cls.OUTPUT_FORMATS]


class LoggingMixin:
    """Mixin for adding structured logging to tools."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._log_entries: List[Dict[str, Any]] = []
    
    def log(self, level: str, message: str, **kwargs) -> None:
        """Add a log entry."""
        entry = {
            'level': level,
            'message': message,
            'timestamp': self._get_timestamp(),
            **kwargs
        }
        self._log_entries.append(entry)
    
    def debug(self, message: str, **kwargs) -> None:
        """Add debug log entry."""
        self.log('DEBUG', message, **kwargs)
    
    def info(self, message: str, **kwargs) -> None:
        """Add info log entry."""
        self.log('INFO', message, **kwargs)
    
    def warning(self, message: str, **kwargs) -> None:
        """Add warning log entry."""
        self.log('WARNING', message, **kwargs)
    
    def error(self, message: str, **kwargs) -> None:
        """Add error log entry."""
        self.log('ERROR', message, **kwargs)
    
    def _get_timestamp(self) -> str:
        """Get current timestamp string."""
        from datetime import datetime
        return datetime.utcnow().isoformat()
    
    def get_logs(self, level: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get log entries, optionally filtered by level."""
        if level:
            return [e for e in self._log_entries if e['level'] == level]
        return self._log_entries.copy()
    
    def clear_logs(self) -> None:
        """Clear all log entries."""
        self._log_entries = []


class ErrorHandlingMixin:
    """Mixin for standardized error handling in tools."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._error_count: int = 0
        self._warning_count: int = 0
        self._last_error: Optional[Exception] = None
    
    def handle_error(self, error: Exception, 
                     context: Optional[str] = None,
                     recoverable: bool = True) -> None:
        """Handle a tool error."""
        self._error_count += 1
        self._last_error = error
        
        error_info = {
            'error_type': type(error).__name__,
            'message': str(error),
            'context': context,
            'recoverable': recoverable,
            'timestamp': self._get_timestamp()
        }
        
        # Log the error using parent's log method if available
        if hasattr(self, 'error'):
            self.error(f"Error: {error}", **error_info)
    
    def handle_warning(self, warning: str, context: Optional[str] = None) -> None:
        """Handle a tool warning."""
        self._warning_count += 1
        
        warning_info = {
            'message': warning,
            'context': context,
            'timestamp': self._get_timestamp()
        }
        
        if hasattr(self, 'warning'):
            self.warning(warning, **warning_info)
    
    def get_error_count(self) -> int:
        """Get total error count."""
        return self._error_count
    
    def get_warning_count(self) -> int:
        """Get total warning count."""
        return self._warning_count
    
    def get_last_error(self) -> Optional[Exception]:
        """Get the last error that occurred."""
        return self._last_error
    
    def _get_timestamp(self) -> str:
        """Get current timestamp."""
        from datetime import datetime
        return datetime.utcnow().isoformat()
    
    def reset_counts(self) -> None:
        """Reset error and warning counts."""
        self._error_count = 0
        self._warning_count = 0
        self._last_error = None


class FileValidationMixin:
    """Mixin for common file validation operations."""
    
    def _validate_file_exists(self, filepath: str) -> bool:
        """Check if file exists."""
        from pathlib import Path
        return Path(filepath).exists()
    
    def _validate_file_not_empty(self, filepath: str) -> bool:
        """Check if file is not empty."""
        from pathlib import Path
        return Path(filepath).stat().st_size > 0
    
    def _validate_extension(self, filepath: str, 
                            allowed_extensions: List[str]) -> bool:
        """Validate file extension."""
        from pathlib import Path
        ext = Path(filepath).suffix.lower()
        return ext in [e.lower() for e in allowed_extensions]
    
    def _get_file_size(self, filepath: str) -> int:
        """Get file size in bytes."""
        from pathlib import Path
        return Path(filepath).stat().st_size
    
    def _calculate_md5(self, filepath: str) -> str:
        """Calculate MD5 checksum of file."""
        import hashlib
        md5 = hashlib.md5()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                md5.update(chunk)
        return md5.hexdigest()
