#!/usr/bin/env python3
"""
Tool Validator for Virometrics.
Automated testing of tools with standard datasets.
"""

import os
import sys
import json
import sqlite3
import hashlib
import time
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime


@dataclass
class TestDataset:
    """Represents a test dataset for tool validation."""
    name: str
    file_path: str
    file_type: str
    size_bytes: int
    md5_hash: str
    description: str = ''
    expected_output: Optional[str] = None
    expected_metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """Result of tool validation."""
    tool_definition_id: int
    tool_name: str
    tool_version: str
    test_dataset: str
    status: str  # passed, failed, warning
    execution_time: float
    output_checksum: Optional[str] = None
    expected_output: Optional[str] = None
    actual_output: Optional[str] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    validated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class ToolValidator:
    """Automated validator for bioinformatics tools."""
    
    # Standard test datasets
    STANDARD_DATASETS = {
        'fasta_small': {
            'name': 'Small FASTA',
            'description': 'Small FASTA file for basic testing',
            'file_type': 'fasta',
            'content': '>seq1\nATCGATCG\n>seq2\nGCTAGCTA\n'
        },
        'fastq_small': {
            'name': 'Small FASTQ',
            'description': 'Small FASTQ file with quality scores',
            'file_type': 'fastq',
            'content': '@seq1\nATCGATCG\n+\nIIIIIIII\n'
        },
        'vcf_simple': {
            'name': 'Simple VCF',
            'description': 'Simple VCF file with one variant',
            'file_type': 'vcf',
            'content': '##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\nchr1\t100\trs1\tA\tG\t30\tPASS\tDP=100\n'
        },
        'empty': {
            'name': 'Empty File',
            'description': 'Empty file for edge case testing',
            'file_type': 'any',
            'content': ''
        }
    }
    
    def __init__(self, db_path: str, test_dir: Optional[str] = None):
        """
        Initialize tool validator.
        
        Args:
            db_path: Path to the Virometrics database
            test_dir: Directory for test datasets (default: data/test_datasets)
        """
        self.db_path = db_path
        self.test_dir = Path(test_dir or os.path.join(os.path.dirname(db_path), 'test_datasets'))
        self._ensure_test_dir()
    
    def _ensure_test_dir(self) -> None:
        """Ensure test directory exists."""
        self.test_dir.mkdir(parents=True, exist_ok=True)
    
    def _calculate_md5(self, data: str) -> str:
        """Calculate MD5 hash of string data."""
        return hashlib.md5(data.encode()).hexdigest()
    
    def _calculate_file_md5(self, file_path: str) -> str:
        """Calculate MD5 hash of file."""
        md5 = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                md5.update(chunk)
        return md5.hexdigest()
    
    def prepare_test_dataset(self, dataset_name: str, 
                             content: Optional[str] = None) -> TestDataset:
        """
        Prepare a test dataset file.
        
        Args:
            dataset_name: Name of the dataset
            content: Optional custom content (uses standard if not provided)
            
        Returns:
            TestDataset object
        """
        # Use standard dataset or custom content
        if dataset_name in self.STANDARD_DATASETS:
            dataset_info = self.STANDARD_DATASETS[dataset_name]
            file_content = content or dataset_info['content']
        else:
            file_content = content or ''
            dataset_info = {
                'name': dataset_name,
                'description': 'Custom test dataset',
                'file_type': 'custom'
            }
        
        # Write to test file
        file_path = self.test_dir / f"{dataset_name}.test"
        with open(file_path, 'w') as f:
            f.write(file_content)
        
        # Create TestDataset
        return TestDataset(
            name=dataset_info['name'],
            file_path=str(file_path),
            file_type=dataset_info['file_type'],
            size_bytes=len(file_content.encode()),
            md5_hash=self._calculate_md5(file_content),
            description=dataset_info['description'],
            expected_output=dataset_info.get('expected_output'),
            expected_metrics=dataset_info.get('expected_metrics', {})
        )
    
    def validate_tool(self, tool_definition_id: int,
                      tool_name: str,
                      tool_version: str,
                      test_datasets: Optional[List[str]] = None,
                      custom_command: Optional[str] = None) -> List[ValidationResult]:
        """
        Validate a tool with standard datasets.
        
        Args:
            tool_definition_id: ID of the tool definition
            tool_name: Name of the tool
            tool_version: Version of the tool
            test_datasets: List of dataset names to test (default: all standard)
            custom_command: Optional custom command to run
            
        Returns:
            List of ValidationResult objects
        """
        results = []
        datasets = test_datasets or list(self.STANDARD_DATASETS.keys())
        
        for dataset_name in datasets:
            # Prepare test dataset
            test_dataset = self.prepare_test_dataset(dataset_name)
            
            # Run validation
            result = self._run_validation(
                tool_definition_id=tool_definition_id,
                tool_name=tool_name,
                tool_version=tool_version,
                test_dataset=test_dataset,
                custom_command=custom_command
            )
            
            results.append(result)
            
            # Save result to database
            self._save_validation_result(result)
        
        return results
    
    def _run_validation(self, tool_definition_id: int,
                        tool_name: str,
                        tool_version: str,
                        test_dataset: TestDataset,
                        custom_command: Optional[str]) -> ValidationResult:
        """Run validation for a single test dataset."""
        start_time = time.time()
        
        errors = []
        warnings = []
        status = 'passed'
        actual_output = None
        
        try:
            # Build command
            if custom_command:
                cmd = custom_command.format(
                    tool=tool_name,
                    input=test_dataset.file_path,
                    output=str(self.test_dir / f"{tool_name}_output")
                )
            else:
                # Default validation command
                cmd = self._build_validation_command(tool_name, test_dataset)
            
            # Run tool
            process = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            execution_time = time.time() - start_time
            actual_output = process.stdout
            
            # Check return code
            if process.returncode == 0:
                status = 'passed'
            elif process.returncode == 1:
                status = 'warning'
                warnings.append(f"Non-zero exit code: {process.returncode}")
            else:
                status = 'failed'
                errors.append(f"Exit code: {process.returncode}")
            
            # Check stderr for warnings/errors
            if process.stderr:
                stderr_lines = process.stderr.strip().split('\n')
                for line in stderr_lines:
                    if 'warning' in line.lower() or 'warn' in line.lower():
                        warnings.append(line)
                    elif 'error' in line.lower():
                        errors.append(line)
            
            # Validate output if expected
            if test_dataset.expected_output:
                expected_checksum = self._calculate_md5(test_dataset.expected_output)
                actual_checksum = self._calculate_md5(actual_output or '')
                
                if expected_checksum != actual_checksum:
                    warnings.append("Output checksum mismatch")
        
        except subprocess.TimeoutExpired:
            execution_time = 60
            status = 'failed'
            errors.append('Execution timeout')
        except Exception as e:
            execution_time = time.time() - start_time
            status = 'failed'
            errors.append(str(e))
        
        return ValidationResult(
            tool_definition_id=tool_definition_id,
            tool_name=tool_name,
            tool_version=tool_version,
            test_dataset=test_dataset.name,
            status=status,
            execution_time=execution_time,
            output_checksum=self._calculate_md5(actual_output or ''),
            expected_output=test_dataset.expected_output,
            actual_output=actual_output,
            errors=errors,
            warnings=warnings
        )
    
    def _build_validation_command(self, tool_name: str, 
                                   test_dataset: TestDataset) -> str:
        """Build validation command for a tool."""
        # Simple validation commands based on file type
        if test_dataset.file_type == 'fasta':
            return f"grep -c '^>' {test_dataset.file_path}"
        elif test_dataset.file_type == 'fastq':
            return f"grep -c '^@' {test_dataset.file_path}"
        elif test_dataset.file_type == 'vcf':
            return f"grep -v '^#' {test_dataset.file_path} | wc -l"
        else:
            return f"test -f {test_dataset.file_path} && echo 'OK'"
    
    def _save_validation_result(self, result: ValidationResult) -> None:
        """Save validation result to database."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO tool_validations (
                    tool_definition_id, test_dataset, status, execution_time,
                    output_checksum, expected_output, actual_output,
                    errors_json, warnings_json, validated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                result.tool_definition_id,
                result.test_dataset,
                result.status,
                result.execution_time,
                result.output_checksum,
                result.expected_output,
                result.actual_output,
                json.dumps(result.errors),
                json.dumps(result.warnings),
                result.validated_at
            ))
            conn.commit()
        finally:
            conn.close()
    
    def validate_all_registered_tools(self) -> Dict[str, List[ValidationResult]]:
        """
        Validate all registered tools in the database.
        
        Returns:
            Dictionary mapping tool names to their validation results
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, name, version 
                FROM tool_definitions 
                WHERE is_active = 1
            """)
            
            tools = cursor.fetchall()
            all_results = {}
            
            for tool in tools:
                results = self.validate_tool(
                    tool_definition_id=tool['id'],
                    tool_name=tool['name'],
                    tool_version=tool['version']
                )
                all_results[tool['name']] = results
            
            return all_results
        finally:
            conn.close()
    
    def get_validation_summary(self) -> Dict[str, Any]:
        """Get summary of all validation results."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    td.name as tool_name,
                    COUNT(*) as total_tests,
                    SUM(CASE WHEN tv.status = 'passed' THEN 1 ELSE 0 END) as passed,
                    SUM(CASE WHEN tv.status = 'failed' THEN 1 ELSE 0 END) as failed,
                    SUM(CASE WHEN tv.status = 'warning' THEN 1 ELSE 0 END) as warnings,
                    AVG(tv.execution_time) as avg_time
                FROM tool_validations tv
                JOIN tool_definitions td ON tv.tool_definition_id = td.id
                GROUP BY td.name
            """)
            
            summary = {}
            for row in cursor.fetchall():
                summary[row['tool_name']] = {
                    'total_tests': row['total_tests'],
                    'passed': row['passed'],
                    'failed': row['failed'],
                    'warnings': row['warnings'],
                    'avg_execution_time': row['avg_time']
                }
            
            return summary
        finally:
            conn.close()


def main():
    """Main function for running tool validation."""
    db_path = sys.argv[1] if len(sys.argv) > 1 else '/home/ihcm-ubuntu/Virometrics/data/virometrics.db'
    
    print(f"Tool Validator for Virometrics")
    print(f"Database: {db_path}")
    print("=" * 50)
    
    validator = ToolValidator(db_path)
    
    # Validate all registered tools
    print("\nValidating registered tools...")
    results = validator.validate_all_registered_tools()
    
    # Print summary
    summary = validator.get_validation_summary()
    print("\nValidation Summary:")
    print("-" * 50)
    for tool_name, stats in summary.items():
        print(f"\n{tool_name}:")
        print(f"  Total tests: {stats['total_tests']}")
        print(f"  Passed: {stats['passed']}")
        print(f"  Failed: {stats['failed']}")
        print(f"  Warnings: {stats['warnings']}")
        print(f"  Avg time: {stats['avg_execution_time']:.2f}s")
    
    print("\n" + "=" * 50)
    print("Validation complete!")


if __name__ == '__main__':
    main()
