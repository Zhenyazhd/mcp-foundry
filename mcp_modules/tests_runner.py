"""
Test Runner Module

Модуль для запуска и анализа результатов тестов смарт-контрактов.
Поддерживает fuzz тесты, smoke тесты, negative тесты с детальным парсингом результатов.
"""

import subprocess
import time
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TestConfig:
    """Test execution configuration"""
    def __init__(
        self,
        runs: int = 1000,
        seed: Optional[int] = None,
        timeout: int = 300,
        gas_limit: int = 30000000,
        verbosity: int = 2,
        match_path: Optional[str] = None,
        match_test: Optional[str] = None,
        ffi: bool = False,
        enable_coverage: bool = True,
        gas_reports: bool = True
    ):
        self.runs = runs
        self.seed = seed
        self.timeout = timeout
        self.gas_limit = gas_limit
        self.verbosity = verbosity
        self.match_path = match_path
        self.match_test = match_test
        self.ffi = ffi
        self.enable_coverage = enable_coverage
        self.gas_reports = gas_reports


@dataclass
class TestResult:
    """Test execution result"""
    success: bool
    total_tests: int
    passed_tests: int
    failed_tests: int
    skipped_tests: int
    execution_time: float
    gas_report: Optional[Dict[str, Any]] = None
    coverage_report: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    output: str = ""
    test_details: Optional[List[Dict[str, Any]]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "success": self.success,
            "total_tests": self.total_tests,
            "passed_tests": self.passed_tests,
            "failed_tests": self.failed_tests,
            "skipped_tests": self.skipped_tests,
            "execution_time": self.execution_time,
            "gas_report": self.gas_report,
            "coverage_report": self.coverage_report,
            "error_message": self.error_message,
            "output": self.output,
            "test_details": self.test_details
        }


class TestRunner:
    """Manages test execution and result parsing"""
    
    def __init__(self, project_path: str):
        self.project_path = Path(project_path).resolve()
        
    def _build_test_command(self, config: TestConfig) -> List[str]:
        """Build forge test command"""
        cmd = ["forge", "test"]
        
        if config.verbosity == 2:
            cmd.append("-vv")
        elif config.verbosity == 3:
            cmd.append("-vvv")
        elif config.verbosity == 4:
            cmd.append("-vvvv")
        elif config.verbosity == 5:
            cmd.append("-vvvvv")
        elif config.verbosity > 0:
            cmd.append(f"-v{'v' * (config.verbosity - 1)}")
        
        cmd.extend(["--gas-limit", str(config.gas_limit)])
        
        if config.match_path:
            cmd.extend(["--match-path", config.match_path])
        if config.match_test:
            cmd.extend(["--match-test", config.match_test])
        
        if config.ffi:
            cmd.append("--ffi")
        
        if config.gas_reports:
            cmd.extend(["--gas-report"])
        
        return cmd
    
    def _build_fuzz_command(self, config: TestConfig) -> List[str]:
        """Build forge test command for fuzz tests"""
        cmd = self._build_test_command(config)
        
        cmd.extend(["--fuzz-runs", str(config.runs)])
        
        if config.seed:
            cmd.extend(["--fuzz-seed", str(config.seed)])
        
        cmd.extend(["--match-test", "testFuzz"])
        
        return cmd
      
    def _parse_test_output(self, result: subprocess.CompletedProcess, execution_time: float) -> TestResult:
        """Parse forge test output with detailed analysis"""
        output = result.stdout + result.stderr
        
        test_data = self._parse_test_summary(output)
        
        gas_report = self._parse_gas_report(output)
        
        coverage_data = self._parse_coverage_data(output)
        
        test_details = self._parse_test_details(output)
        
        success = result.returncode == 0
        
        return TestResult(
            success=success,
            total_tests=test_data['total'],
            passed_tests=test_data['passed'],
            failed_tests=test_data['failed'],
            skipped_tests=test_data['skipped'],
            execution_time=execution_time,
            output=output,
            gas_report=gas_report,
            coverage_report=coverage_data,
            error_message=None if success else self._extract_error_message(output),
            test_details=test_details
        )

    def _parse_test_summary(self, output: str) -> Dict[str, int]:
        """Parse test summary from forge output"""
        lines = output.split('\n')
        
        total_tests = 0
        passed_tests = 0
        failed_tests = 0
        skipped_tests = 0
        
        for line in lines:
            if "test suites" in line and "tests passed" in line:
                import re
                numbers = re.findall(r'\d+', line)
                if len(numbers) >= 4:
                    total_tests = int(numbers[2]) + int(numbers[3]) + int(numbers[4])
                    passed_tests = int(numbers[2])
                    failed_tests = int(numbers[3])
                    skipped_tests = int(numbers[4])
                    break
            
            elif "Suite result:" in line:
                if "ok" in line.lower():
                    passed_tests += 1
                elif "FAIL" in line.upper():
                    failed_tests += 1
                total_tests += 1
        
        if total_tests == 0:
            for line in lines:
                if "[PASS]" in line:
                    passed_tests += 1
                    total_tests += 1
                elif "[FAIL]" in line:
                    failed_tests += 1
                    total_tests += 1
                elif "[SKIP]" in line:
                    skipped_tests += 1
                    total_tests += 1
        
        return {
            'total': total_tests,
            'passed': passed_tests,
            'failed': failed_tests,
            'skipped': skipped_tests
        }
    
    def _parse_gas_report(self, output: str) -> Optional[Dict[str, Any]]:
        """Parse gas report from forge output"""
        lines = output.split('\n')
        gas_report = {
            'contracts': {},
            'summary': {}
        }
        
        in_gas_table = False
        current_contract = None
        
        for line in lines:
            if "┌─" in line and "Contract" in line:
                in_gas_table = True
                continue
            
            if "└─" in line and in_gas_table:
                in_gas_table = False
                continue
            
            if in_gas_table:
                if "│" in line and "Contract" in line and "│" in line:
                    parts = [p.strip() for p in line.split("│") if p.strip()]
                    if len(parts) >= 2:
                        current_contract = parts[1]
                        gas_report['contracts'][current_contract] = {
                            'deployment_cost': None,
                            'deployment_size': None,
                            'functions': {}
                        }
                
                elif "│" in line and current_contract and "│" in line:
                    parts = [p.strip() for p in line.split("│") if p.strip()]
                    if len(parts) >= 6 and parts[0] != "Function Name":
                        func_name = parts[0]
                        try:
                            gas_report['contracts'][current_contract]['functions'][func_name] = {
                                'min': int(parts[1]) if parts[1].isdigit() else None,
                                'avg': int(parts[2]) if parts[2].isdigit() else None,
                                'median': int(parts[3]) if parts[3].isdigit() else None,
                                'max': int(parts[4]) if parts[4].isdigit() else None,
                                'calls': int(parts[5]) if parts[5].isdigit() else None
                            }
                        except (ValueError, IndexError):
                            continue
        
        return gas_report if gas_report['contracts'] else None
    
    def _parse_coverage_data(self, output: str) -> Optional[Dict[str, Any]]:
        """Parse coverage data from forge output"""
        lines = output.split('\n')
        coverage_data = {
            'files': {},
            'summary': {}
        }
        
        for line in lines:
            if "Coverage" in line and "%" in line:
                import re
                coverage_match = re.search(r'(\d+(?:\.\d+)?)%', line)
                if coverage_match:
                    coverage_data['summary']['total_coverage'] = float(coverage_match.group(1))
                    break
        
        return coverage_data if coverage_data['summary'] else None
    
    def _parse_test_details(self, output: str) -> List[Dict[str, Any]]:
        """Parse individual test details"""
        lines = output.split('\n')
        test_details = []
        
        for line in lines:
            if "[PASS]" in line or "[FAIL]" in line or "[SKIP]" in line:
                import re
                
                test_match = re.search(r'\[(\w+)\]\s+(\w+)(?:\s+\(([^)]+)\))?', line)
                if test_match:
                    status = test_match.group(1)
                    test_name = test_match.group(2)
                    details = test_match.group(3) or ""
                    
                    test_detail = {
                        'name': test_name,
                        'status': status.lower(),
                        'details': details
                    }
                    
                    runs_match = re.search(r'runs:\s*(\d+)', details)
                    if runs_match:
                        test_detail['runs'] = int(runs_match.group(1))
                    
                    gas_match = re.search(r'μ:\s*(\d+)', details)
                    if gas_match:
                        test_detail['gas_used'] = int(gas_match.group(1))
                    
                    test_details.append(test_detail)
        
        return test_details
    
    def _extract_error_message(self, output: str) -> str:
        """Extract meaningful error message from output"""
        lines = output.split('\n')
        
        for line in lines:
            if "Error:" in line:
                return line.strip()
            elif "FAIL" in line and "test" in line.lower():
                return line.strip()
            elif "revert" in line.lower():
                return line.strip()
        
        return "Test execution failed"

    def _parse_coverage_output(self, output: str) -> Dict[str, Any]:
        """Parse coverage analysis output"""
        lines = output.split('\n')
        coverage_data = {
            'files': {},
            'summary': {
                'total_lines': 0,
                'covered_lines': 0,
                'coverage_percentage': 0.0
            }
        }
        
        for line in lines:
            if "Coverage" in line and "%" in line:
                import re
                coverage_match = re.search(r'(\d+(?:\.\d+)?)%', line)
                if coverage_match:
                    coverage_data['summary']['coverage_percentage'] = float(coverage_match.group(1))
            
            elif "|" in line and ".sol" in line:
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if len(parts) >= 4:
                    file_name = parts[0]
                    try:
                        coverage_data['files'][file_name] = {
                            'lines': int(parts[1]) if parts[1].isdigit() else 0,
                            'covered': int(parts[2]) if parts[2].isdigit() else 0,
                            'percentage': float(parts[3].replace('%', '')) if '%' in parts[3] else 0.0
                        }
                    except (ValueError, IndexError):
                        continue
        
        return coverage_data
    
    def run_coverage_analysis(self, config: TestConfig) -> Dict[str, Any]:
        """Run coverage analysis using forge coverage"""
        try:
            start_time = time.time()
            cmd = ["forge", "coverage", "--report", "lcov"]
            cmd.extend(["-vv" if config.verbosity == 2 else f"-v" * config.verbosity])
            
            logger.info(f"Running coverage analysis with command: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=config.timeout
            )
            
            execution_time = time.time() - start_time
            
            coverage_data = self._parse_coverage_output(result.stdout + result.stderr)
            return {
                "success": result.returncode == 0,
                "execution_time": execution_time,
                "coverage_data": coverage_data,
                "output": result.stdout + result.stderr,
                "error_message": None if result.returncode == 0 else "Coverage analysis failed"
            }
            
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "execution_time": config.timeout,
                "coverage_data": None,
                "output": "",
                "error_message": "Coverage analysis timed out"
            }
        except Exception as e:
            logger.error(f"Error running coverage analysis: {e}")
            return {
                "success": False,
                "execution_time": 0,
                "coverage_data": None,
                "output": "",
                "error_message": str(e)
            }
    
    def run_fuzz_tests(self, config: TestConfig) -> TestResult:
        """Run fuzz tests only"""
        try:
            start_time = time.time()
            
            # Build command for fuzz tests only
            cmd = self._build_fuzz_command(config)
            
            logger.info(f"Running fuzz tests with command: {' '.join(cmd)}")
            
            # Execute fuzz tests
            result = subprocess.run(
                cmd,
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=config.timeout
            )
            
            execution_time = time.time() - start_time
            
            # Parse results
            test_result = self._parse_test_output(result, execution_time)
            
            return test_result
            
        except subprocess.TimeoutExpired:
            return TestResult(
                success=False,
                total_tests=0,
                passed_tests=0,
                failed_tests=0,
                skipped_tests=0,
                execution_time=config.timeout,
                output="",
                error_message="Fuzz tests timed out"
            )
        except Exception as e:
            logger.error(f"Error running fuzz tests: {e}")
            return TestResult(
                success=False,
                total_tests=0,
                passed_tests=0,
                failed_tests=0,
                skipped_tests=0,
                execution_time=0,
                output="",
                error_message=str(e)
            )
    
    def run_all_tests(self, config: TestConfig) -> TestResult:
        """Run all tests in the project"""
        try:
            start_time = time.time()
            
            cmd = self._build_test_command(config)
            
            logger.info(f"Running tests with command: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=config.timeout
            )
            
            execution_time = time.time() - start_time
            test_result = self._parse_test_output(result, execution_time)
            return test_result
            
        except subprocess.TimeoutExpired:
            return TestResult(
                success=False,
                total_tests=0,
                passed_tests=0,
                failed_tests=0,
                skipped_tests=0,
                execution_time=config.timeout,
                output="",
                error_message="Tests timed out"
            )
        except Exception as e:
            logger.error(f"Error running tests: {e}")
            return TestResult(
                success=False,
                total_tests=0,
                passed_tests=0,
                failed_tests=0,
                skipped_tests=0,
                execution_time=0,
                output="",
                error_message=str(e)
            )
