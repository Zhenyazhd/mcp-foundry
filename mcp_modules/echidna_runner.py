
import subprocess
import time
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class EchidnaConfig:
    """Echidna test execution configuration"""
    def __init__(
        self,
        runs: int = 1000,
        seed: Optional[int] = None,
        timeout: int = 300,
        gas_limit: int = 30000000,
        verbosity: int = 2,
        contract: Optional[str] = None,
        test_limit: int = 1000000,
        shrink_limit: int = 5000,
        seq_len: int = 100,
        contract_addr: str = "0x00a329c0648769A73afAc7F9381E08FB43dBEA72",
        sender: List[str] = None,
        psender: int = 1,
        call_gas_limit: int = 100000,
        code_size: int = 0x6000,
        format: str = "text",
        corpus_dir: Optional[str] = None,
        coverage: bool = True,
        shrink_timeout: int = 0,
        test_mode: str = "property"
    ):
        self.runs = runs
        self.seed = seed
        self.timeout = timeout
        self.gas_limit = gas_limit
        self.verbosity = verbosity
        self.contract = contract
        self.test_limit = test_limit
        self.shrink_limit = shrink_limit
        self.seq_len = seq_len
        self.contract_addr = contract_addr
        self.sender = sender or ["0x10000", "0x20000"]
        self.psender = psender
        self.call_gas_limit = call_gas_limit
        self.code_size = code_size
        self.format = format
        self.corpus_dir = corpus_dir
        self.coverage = coverage
        self.shrink_timeout = shrink_timeout
        self.test_mode = test_mode 

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EchidnaResult:
    """Echidna test execution result"""
    success: bool
    total_tests: int
    passed_tests: int
    failed_tests: int
    coverage_percentage: float
    execution_time: float
    gas_used: int
    fuzzing_stats: Dict[str, Any]
    findings: List[Dict[str, Any]]
    output: str
    error_output: str
    config: EchidnaConfig

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "total_tests": self.total_tests,
            "passed_tests": self.passed_tests,
            "failed_tests": self.failed_tests,
            "coverage_percentage": self.coverage_percentage,
            "execution_time": self.execution_time,
            "gas_used": self.gas_used,
            "fuzzing_stats": self.fuzzing_stats,
            "findings": self.findings,
            "output": self.output,
            "error_output": self.error_output,
            "config": self.config.to_dict()
        }


class EchidnaRunner:
    """Manages Echidna test execution and result parsing"""
    
    def __init__(self, project_path: str):
        self.project_path = Path(project_path).resolve()
        
    def _check_echidna_installed(self) -> bool:
        """Check if Echidna is installed via pip3"""
        try:
            result = subprocess.run(
                ["echidna", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return True
            
            result = subprocess.run(
                ["python3", "-c", "import echidna; print('Echidna available')"],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def _create_echidna_config(self, config: EchidnaConfig) -> Path:
        """Create echidna.yaml configuration file"""
        config_path = self.project_path / "echidna.yaml"
        
        config_data = {
            "testMode": config.test_mode,
            "testLimit": config.test_limit,
            "shrinkLimit": config.shrink_limit,
            "seqLen": config.seq_len,
            "contractAddr": config.contract_addr,
            "sender": config.sender,
            "psender": str(config.psender),  
            "callGasLimit": config.call_gas_limit,
            "codeSize": config.code_size,
            "format": config.format,
            "coverage": config.coverage,
            "shrinkTimeout": config.shrink_timeout
        }
        
        if config.contract:
            config_data["contract"] = config.contract
        if config.corpus_dir:
            config_data["corpusDir"] = config.corpus_dir
        
        with open(config_path, 'w') as f:
            import yaml
            yaml.dump(config_data, f, default_flow_style=False)
        
        logger.info(f"Created Echidna config at {config_path}")
        return config_path
    
    def _build_echidna_command(self, config: EchidnaConfig) -> List[str]:
        """Build echidna test command"""
        cmd = ["echidna"]
        
        if config.contract:
            contract_files = []
            contract_files.extend(list(self.project_path.glob(f"src/**/{config.contract}.sol")))
            contract_files.extend(list(self.project_path.glob(f"contracts/**/{config.contract}.sol")))
            contract_files.extend(list(self.project_path.glob(f"test/**/{config.contract}.sol")))
            contract_files.extend(list(self.project_path.glob(f"{config.contract}.sol")))
            contract_files.extend(list(self.project_path.glob(f"**/{config.contract}.sol")))
            
            if contract_files:
                cmd.append(str(contract_files[0]))
                logger.info(f"Using specified contract file: {contract_files[0]}")
            else:
                raise FileNotFoundError(f"Contract {config.contract} not found in project directory")
        else:
            echidna_test_files = []            
            echidna_test_files.extend(list(self.project_path.glob("src/**/*EchidnaTest.sol")))            
            echidna_test_files.extend(list(self.project_path.glob("contracts/**/*EchidnaTest.sol")))
            echidna_test_files.extend(list(self.project_path.glob("test/**/*EchidnaTest.sol")))
            echidna_test_files.extend(list(self.project_path.glob("*EchidnaTest.sol")))
            echidna_test_files.extend(list(self.project_path.glob("**/*EchidnaTest.sol")))
            
            if echidna_test_files:
                cmd.append(str(echidna_test_files[0]))
                logger.info(f"Using Echidna test file: {echidna_test_files[0]}")
            else:
                raise FileNotFoundError("No EchidnaTest.sol files found in project directory")
        
        config_path = self._create_echidna_config(config)
        cmd.extend(["--config", str(config_path)])
        
        cmd.extend(["--test-limit", str(config.runs)])
        cmd.extend(["--timeout", str(config.timeout)])
        
        if config.seed:
            cmd.extend(["--seed", str(config.seed)])
        
        if config.verbosity > 0:
            cmd.extend(["--format", "text"])
        
        return cmd
    
    def _parse_echidna_output(self, output: str, error_output: str) -> Dict[str, Any]:
        """Parse Echidna output to extract test results and findings"""
        findings = []
        fuzzing_stats = {}
        
        lines = output.splitlines()
        
        total_tests = 0
        passed_tests = 0
        failed_tests = 0
        coverage_percentage = 0.0
        
        for line in lines:
            line = line.strip()
            if "coverage:" in line.lower():
                try:
                    coverage_str = line.split("coverage:")[-1].strip().replace("%", "")
                    coverage_percentage = float(coverage_str)
                except (ValueError, IndexError):
                    pass
            
            if "fuzzing:" in line.lower():
                try:
                    stats_part = line.split("fuzzing:")[-1].strip()
                    import re
                    numbers = re.findall(r'\d+', stats_part)
                    if len(numbers) >= 2:
                        fuzzing_stats["total_runs"] = int(numbers[0])
                        fuzzing_stats["successful_runs"] = int(numbers[1])
                except (ValueError, IndexError):
                    pass
            
            if "failed:" in line.lower():
                try:
                    failed_str = line.split("failed:")[-1].strip()
                    failed_tests = int(failed_str)
                except (ValueError, IndexError):
                    pass
            
            if "property" in line.lower() and "violated" in line.lower():
                findings.append({
                    "type": "property_violation",
                    "description": line,
                    "severity": "high"
                })
                failed_tests += 1
        
        error_lines = error_output.splitlines()
        for line in error_lines:
            line = line.strip()
            if "assertion" in line.lower() or "revert" in line.lower():
                findings.append({
                    "type": "assertion_failure",
                    "description": line,
                    "severity": "medium"
                })
        
        total_tests = max(total_tests, passed_tests + failed_tests)
        if total_tests == 0:
            total_tests = 1  
        
        return {
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": failed_tests,
            "coverage_percentage": coverage_percentage,
            "fuzzing_stats": fuzzing_stats,
            "findings": findings
        }
    
    def run_tests(self, config: EchidnaConfig) -> EchidnaResult:
        """Run Echidna tests with given configuration"""
        start_time = time.time()
        
        if not self._check_echidna_installed():
            return EchidnaResult(
                success=False,
                total_tests=0,
                passed_tests=0,
                failed_tests=0,
                coverage_percentage=0.0,
                execution_time=0.0,
                gas_used=0,
                fuzzing_stats={},
                findings=[{
                    "type": "installation_error",
                    "description": "Echidna is not installed. Please install it first.",
                    "severity": "high"
                }],
                output="",
                error_output="Echidna not found",
                config=config
            )
        
        try:
            cmd = self._build_echidna_command(config)
            logger.info(f"Running Echidna command: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=config.timeout + 30  
            )
            
            execution_time = time.time() - start_time
            parsed_results = self._parse_echidna_output(result.stdout, result.stderr)
            success = result.returncode == 0 and parsed_results["failed_tests"] == 0
            
            return EchidnaResult(
                success=success,
                total_tests=parsed_results["total_tests"],
                passed_tests=parsed_results["passed_tests"],
                failed_tests=parsed_results["failed_tests"],
                coverage_percentage=parsed_results["coverage_percentage"],
                execution_time=execution_time,
                gas_used=0,  
                fuzzing_stats=parsed_results["fuzzing_stats"],
                findings=parsed_results["findings"],
                output=result.stdout,
                error_output=result.stderr,
                config=config
            )
            
        except subprocess.TimeoutExpired:
            execution_time = time.time() - start_time
            return EchidnaResult(
                success=False,
                total_tests=0,
                passed_tests=0,
                failed_tests=0,
                coverage_percentage=0.0,
                execution_time=execution_time,
                gas_used=0,
                fuzzing_stats={},
                findings=[{
                    "type": "timeout",
                    "description": f"Echidna test execution timed out after {config.timeout} seconds",
                    "severity": "medium"
                }],
                output="",
                error_output="Test execution timeout",
                config=config
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Error running Echidna tests: {e}")
            return EchidnaResult(
                success=False,
                total_tests=0,
                passed_tests=0,
                failed_tests=0,
                coverage_percentage=0.0,
                execution_time=execution_time,
                gas_used=0,
                fuzzing_stats={},
                findings=[{
                    "type": "execution_error",
                    "description": f"Error running Echidna: {str(e)}",
                    "severity": "high"
                }],
                output="",
                error_output=str(e),
                config=config
            )
    
    def create_sample_property_test(self, contract_name: str) -> str:
        """Create a sample property test contract for Echidna"""
        test_content = f'''// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Test.sol";
import "../src/{contract_name}.sol";

contract {contract_name}EchidnaTest is Test {{
    {contract_name} public target;
    
    function setUp() public {{
        target = new {contract_name}();
    }}
    
    // Property: Contract should not revert on basic operations
    function echidna_basic_operation() public view returns (bool) {{
        // Add your property tests here
        // Example: target.someFunction() should not revert
        return true;
    }}
    
    // Property: State should be consistent
    function echidna_state_consistency() public view returns (bool) {{
        // Add state consistency checks here
        return true;
    }}
    
    // Property: No overflow/underflow
    function echidna_no_overflow() public view returns (bool) {{
        // Add overflow checks here
        return true;
    }}
}}'''
        
        return test_content
    
    def install_echidna(self) -> Dict[str, Any]:
        """Provide instructions for installing Echidna"""
        return {
            "success": False,
            "message": "Echidna installation required",
            "instructions": {
                "pip3": "pip3 install slither-analyzer crytic-compile",
                "pip": "pip install slither-analyzer crytic-compile",
                "ubuntu_debian": "sudo apt-get install echidna",
                "macos": "brew install echidna",
                "docker": "docker pull ghcr.io/crytic/echidna/echidna:latest",
                "manual": "Visit https://github.com/crytic/echidna for installation instructions"
            },
            "verification": "Run 'echidna --version' or 'python3 -c \"import echidna\"' to verify installation"
        }
    
    def auto_install_echidna(self, platform: str = None) -> Dict[str, Any]:
        """Automatically install Echidna using pip3 (recommended method)"""
        try:
            logger.info("Attempting to install Echidna via pip3...")
            
            pip3_result = self._install_echidna_pip3()
            if pip3_result["success"]:
                return pip3_result
            
            logger.info("pip3 failed, trying pip...")
            pip_result = self._install_echidna_pip()
            if pip_result["success"]:
                return pip_result
            
            logger.info("pip installation failed, falling back to platform-specific methods...")
            return self._install_echidna_platform_specific(platform)
                
        except Exception as e:
            logger.error(f"Error during automatic Echidna installation: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to install Echidna automatically",
                "instructions": self.install_echidna()["instructions"]
            }
    
    def _install_echidna_pip3(self) -> Dict[str, Any]:
        """Install Echidna using pip3"""
        try:
            logger.info("Installing Echidna and dependencies via pip3...")
            result = subprocess.run(
                ["pip3", "install", "slither-analyzer"],
                capture_output=True,
                text=True,
                timeout=600
            )
            
            if result.returncode != 0:
                return {
                    "success": False,
                    "error": "Failed to install slither-analyzer",
                    "output": result.stderr,
                    "message": "Please check pip3 installation and try manual installation"
                }
            
            logger.info("Installing crytic-compile...")
            result2 = subprocess.run(
                ["pip3", "install", "crytic-compile"],
                capture_output=True,
                text=True,
                timeout=600
            )
            
            if result2.returncode != 0:
                logger.warning(f"Failed to install crytic-compile: {result2.stderr}")
            
            if result.returncode == 0:
                if self._check_echidna_installed():
                    return {
                        "success": True,
                        "message": "Echidna installed successfully via pip3",
                        "method": "pip3",
                        "output": result.stdout,
                        "verification": "Echidna is now available"
                    }
                else:
                    return {
                        "success": False,
                        "error": "Installation completed but Echidna not accessible",
                        "output": result.stdout,
                        "message": "Please restart your shell or check Python environment"
                    }
            else:
                return {
                    "success": False,
                    "error": "Failed to install Echidna via pip3",
                    "output": result.stderr,
                    "message": "Please check pip3 installation and try manual installation"
                }
                
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "pip3 installation timeout",
                "message": "Installation took too long, please try manual installation"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to install Echidna via pip3"
            }
    
    def _install_echidna_pip(self) -> Dict[str, Any]:
        """Install Echidna using pip"""
        try:
            logger.info("Installing Echidna and dependencies via pip...")
            
            result = subprocess.run(
                ["pip", "install", "slither-analyzer"],
                capture_output=True,
                text=True,
                timeout=600
            )
            
            if result.returncode != 0:
                return {
                    "success": False,
                    "error": "Failed to install slither-analyzer",
                    "output": result.stderr,
                    "message": "Please check pip installation and try manual installation"
                }
            
            logger.info("Installing crytic-compile...")
            result2 = subprocess.run(
                ["pip", "install", "crytic-compile"],
                capture_output=True,
                text=True,
                timeout=600
            )
            
            if result2.returncode != 0:
                logger.warning(f"Failed to install crytic-compile: {result2.stderr}")
            
            if result.returncode == 0:
                if self._check_echidna_installed():
                    return {
                        "success": True,
                        "message": "Echidna installed successfully via pip",
                        "method": "pip",
                        "output": result.stdout,
                        "verification": "Echidna is now available"
                    }
                else:
                    return {
                        "success": False,
                        "error": "Installation completed but Echidna not accessible",
                        "output": result.stdout,
                        "message": "Please restart your shell or check Python environment"
                    }
            else:
                return {
                    "success": False,
                    "error": "Failed to install Echidna via pip",
                    "output": result.stderr,
                    "message": "Please check pip installation and try manual installation"
                }
                
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "pip installation timeout",
                "message": "Installation took too long, please try manual installation"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to install Echidna via pip"
            }
    
    def _install_echidna_platform_specific(self, platform: str = None) -> Dict[str, Any]:
        """Fallback to platform-specific installation methods"""
        import platform as platform_module
        
        try:
            if not platform:
                system = platform_module.system().lower()
                if system == "linux":
                    try:
                        with open("/etc/os-release", "r") as f:
                            os_release = f.read().lower()
                            if "ubuntu" in os_release or "debian" in os_release:
                                platform = "ubuntu_debian"
                            elif "fedora" in os_release or "rhel" in os_release or "centos" in os_release:
                                platform = "fedora"
                            else:
                                platform = "ubuntu_debian"  
                    except:
                        platform = "ubuntu_debian"  
                elif system == "darwin":
                    platform = "macos"
                elif system == "windows":
                    platform = "windows"
                else:
                    platform = "manual"
            
            logger.info(f"Attempting platform-specific installation for: {platform}")
            
            if platform == "ubuntu_debian":
                return self._install_echidna_apt()
            elif platform == "macos":
                return self._install_echidna_brew()
            elif platform == "fedora":
                return self._install_echidna_dnf()
            elif platform == "docker":
                return self._install_echidna_docker()
            elif platform == "windows":
                return self._install_echidna_windows()
            else:
                return {
                    "success": False,
                    "message": f"Platform-specific installation not supported for: {platform}",
                    "instructions": self.install_echidna()["instructions"]
                }
                
        except Exception as e:
            logger.error(f"Error during platform-specific installation: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to install Echidna using platform-specific methods",
                "instructions": self.install_echidna()["instructions"]
            }
    
    def _install_echidna_apt(self) -> Dict[str, Any]:
        """Install Echidna using apt (Ubuntu/Debian)"""
        try:
            logger.info("Updating package list...")
            result = subprocess.run(
                ["sudo", "apt-get", "update"],
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode != 0:
                return {
                    "success": False,
                    "error": "Failed to update package list",
                    "output": result.stderr,
                    "message": "Please run 'sudo apt-get update' manually and try again"
                }
            
            logger.info("Installing Echidna...")
            result = subprocess.run(
                ["sudo", "apt-get", "install", "-y", "echidna"],
                capture_output=True,
                text=True,
                timeout=600
            )
            
            if result.returncode == 0:
                if self._check_echidna_installed():
                    return {
                        "success": True,
                        "message": "Echidna installed successfully via apt",
                        "platform": "ubuntu_debian",
                        "output": result.stdout
                    }
                else:
                    return {
                        "success": False,
                        "error": "Installation completed but Echidna not found in PATH",
                        "output": result.stdout,
                        "message": "Please restart your shell or check PATH configuration"
                    }
            else:
                return {
                    "success": False,
                    "error": "Failed to install Echidna via apt",
                    "output": result.stderr,
                    "message": "Please check if you have sudo privileges and try manual installation"
                }
                
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Installation timeout",
                "message": "Installation took too long, please try manual installation"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to install Echidna via apt"
            }
    
    def _install_echidna_brew(self) -> Dict[str, Any]:
        """Install Echidna using Homebrew (macOS)"""
        try:
            brew_check = subprocess.run(
                ["which", "brew"],
                capture_output=True,
                text=True
            )
            
            if brew_check.returncode != 0:
                return {
                    "success": False,
                    "error": "Homebrew not found",
                    "message": "Please install Homebrew first: /bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
                }
            
            logger.info("Installing Echidna via Homebrew...")
            result = subprocess.run(
                ["brew", "install", "echidna"],
                capture_output=True,
                text=True,
                timeout=600
            )
            
            if result.returncode == 0:
                if self._check_echidna_installed():
                    return {
                        "success": True,
                        "message": "Echidna installed successfully via Homebrew",
                        "platform": "macos",
                        "output": result.stdout
                    }
                else:
                    return {
                        "success": False,
                        "error": "Installation completed but Echidna not found in PATH",
                        "output": result.stdout,
                        "message": "Please restart your shell or check PATH configuration"
                    }
            else:
                return {
                    "success": False,
                    "error": "Failed to install Echidna via Homebrew",
                    "output": result.stderr,
                    "message": "Please check Homebrew installation and try manual installation"
                }
                
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Installation timeout",
                "message": "Installation took too long, please try manual installation"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to install Echidna via Homebrew"
            }
    
    def _install_echidna_dnf(self) -> Dict[str, Any]:
        """Install Echidna using dnf (Fedora/RHEL/CentOS)"""
        try:
            # Install Echidna
            logger.info("Installing Echidna via dnf...")
            result = subprocess.run(
                ["sudo", "dnf", "install", "-y", "echidna"],
                capture_output=True,
                text=True,
                timeout=600
            )
            
            if result.returncode == 0:
                if self._check_echidna_installed():
                    return {
                        "success": True,
                        "message": "Echidna installed successfully via dnf",
                        "platform": "fedora",
                        "output": result.stdout
                    }
                else:
                    return {
                        "success": False,
                        "error": "Installation completed but Echidna not found in PATH",
                        "output": result.stdout,
                        "message": "Please restart your shell or check PATH configuration"
                    }
            else:
                return {
                    "success": False,
                    "error": "Failed to install Echidna via dnf",
                    "output": result.stderr,
                    "message": "Please check if you have sudo privileges and try manual installation"
                }
                
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Installation timeout",
                "message": "Installation took too long, please try manual installation"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to install Echidna via dnf"
            }
    
    def _install_echidna_docker(self) -> Dict[str, Any]:
        """Install Echidna using Docker"""
        try:
            docker_check = subprocess.run(
                ["which", "docker"],
                capture_output=True,
                text=True
            )
            
            if docker_check.returncode != 0:
                return {
                    "success": False,
                    "error": "Docker not found",
                    "message": "Please install Docker first"
                }
            
            logger.info("Pulling Echidna Docker image...")
            result = subprocess.run(
                ["docker", "pull", "ghcr.io/crytic/echidna/echidna:latest"],
                capture_output=True,
                text=True,
                timeout=600
            )
            
            if result.returncode == 0:
                return {
                    "success": True,
                    "message": "Echidna Docker image pulled successfully",
                    "platform": "docker",
                    "output": result.stdout,
                    "usage": "Use 'docker run --rm -v $(pwd):/src ghcr.io/crytic/echidna/echidna:latest' to run Echidna"
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to pull Echidna Docker image",
                    "output": result.stderr,
                    "message": "Please check Docker installation and network connection"
                }
                
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Docker pull timeout",
                "message": "Docker pull took too long, please try manual installation"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to install Echidna via Docker"
            }
    
    def _install_echidna_windows(self) -> Dict[str, Any]:
        """Install Echidna on Windows"""
        return {
            "success": False,
            "message": "Windows installation not yet implemented",
            "instructions": {
                "chocolatey": "choco install echidna",
                "manual": "Download from https://github.com/crytic/echidna/releases",
                "wsl": "Use WSL2 with Ubuntu and install via apt"
            }
        }
    
    def install_echidna_locally(self, project_path: str = None) -> Dict[str, Any]:
        """Install Echidna locally in the project directory using pip3"""
        try:
            if not project_path:
                project_path = self.project_path
            
            project_path = Path(project_path).resolve()
            
            logger.info(f"Installing Echidna locally in project: {project_path}")
            
            pip3_result = self._install_echidna_pip3()
            if pip3_result["success"]:
                return {
                    "success": True,
                    "message": "Echidna installed locally via pip3",
                    "method": "pip3",
                    "project_path": str(project_path),
                    "binary_path": "echidna (available in PATH)",
                    "usage": "Use 'echidna' command to run Echidna",
                    "verification": pip3_result.get("verification", "Echidna is now available")
                }
            
            pip_result = self._install_echidna_pip()
            if pip_result["success"]:
                return {
                    "success": True,
                    "message": "Echidna installed locally via pip",
                    "method": "pip",
                    "project_path": str(project_path),
                    "binary_path": "echidna (available in PATH)",
                    "usage": "Use 'echidna' command to run Echidna",
                    "verification": pip_result.get("verification", "Echidna is now available")
                }
            
            logger.info("pip installation failed, falling back to Docker...")
            return self.install_echidna_docker_locally(project_path)
                
        except Exception as e:
            logger.error(f"Error during local Echidna installation: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to install Echidna locally",
                "fallback": "Try manual installation: pip3 install slither-analyzer"
            }
    
    def _get_latest_echidna_release(self) -> Dict[str, Any]:
        """Get latest Echidna release information from GitHub"""
        try:
            import requests
            
            response = requests.get(
                "https://api.github.com/repos/crytic/echidna/releases/latest",
                timeout=30
            )
            
            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"Failed to get release info: HTTP {response.status_code}",
                    "message": "Could not fetch latest Echidna release information"
                }
            
            release_data = response.json()
            tag_name = release_data["tag_name"]
            
            assets = release_data.get("assets", [])
            
            return {
                "success": True,
                "tag_name": tag_name,
                "assets": assets,
                "message": f"Found latest release: {tag_name}"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to get latest release information"
            }
    
    def _download_echidna_binary(self, download_url: str, target_dir: Path, platform_info: str) -> Dict[str, Any]:
        """Download and extract Echidna binary"""
        try:
            import requests        
            return {
                "success": False,
                "error": "Binary download not implemented yet",
                "message": "Please use Docker installation for now",
                "fallback": "Use echidna_install_docker_locally() instead"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to download Echidna binary"
            }
    
    def install_echidna_docker_locally(self, project_path: str = None) -> Dict[str, Any]:
        """Install Echidna using Docker with local project integration"""
        try:
            if not project_path:
                project_path = self.project_path
            
            project_path = Path(project_path).resolve()
            
            docker_check = subprocess.run(
                ["which", "docker"],
                capture_output=True,
                text=True
            )
            
            if docker_check.returncode != 0:
                return {
                    "success": False,
                    "error": "Docker not found",
                    "message": "Please install Docker first"
                }
            
            docker_compose_content = f'''version: '3.8'
services:
  echidna:
    image: ghcr.io/crytic/echidna/echidna:latest
    volumes:
      - {project_path}:/src
    working_dir: /src
    command: ["--help"]  # Default command, will be overridden
'''
            
            docker_compose_path = project_path / "docker-compose.echidna.yml"
            with open(docker_compose_path, 'w') as f:
                f.write(docker_compose_content)
            
            wrapper_script = f'''#!/bin/bash
# Echidna Docker wrapper script
# Usage: ./echidna-docker.sh [echidna-arguments]

PROJECT_DIR="{project_path}"
DOCKER_IMAGE="ghcr.io/crytic/echidna/echidna:latest"

# Run Echidna in Docker with project mounted
docker run --rm -v "$PROJECT_DIR:/src" -w /src "$DOCKER_IMAGE" "$@"
'''
            
            wrapper_path = project_path / "echidna-docker.sh"
            with open(wrapper_path, 'w') as f:
                f.write(wrapper_script)
            
            wrapper_path.chmod(0o755)
            
            test_result = subprocess.run(
                [str(wrapper_path), "--version"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if test_result.returncode == 0:
                return {
                    "success": True,
                    "message": "Echidna Docker setup completed locally",
                    "project_path": str(project_path),
                    "wrapper_script": str(wrapper_path),
                    "docker_compose": str(docker_compose_path),
                    "version": test_result.stdout.strip(),
                    "usage": f"Use '{wrapper_path}' to run Echidna in this project",
                    "example": f"'{wrapper_path}' test/MyContract.sol"
                }
            else:
                return {
                    "success": False,
                    "error": "Docker setup verification failed",
                    "output": test_result.stderr,
                    "message": "Docker setup completed but verification failed"
                }
                
        except Exception as e:
            logger.error(f"Error setting up Echidna Docker locally: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to setup Echidna Docker locally"
            }
    
    def run_tests_with_command(self, config: EchidnaConfig, echidna_command: str) -> EchidnaResult:
        """Run Echidna tests using a specific command (local binary or Docker wrapper)"""
        try:
            config_path = self._create_echidna_config(config)
            
            cmd = [echidna_command]
            
            cmd.append(str(config_path))
            
            if config.contract:
                contract_files = []
                contract_files.extend(list(self.project_path.glob(f"src/**/{config.contract}.sol")))
                contract_files.extend(list(self.project_path.glob(f"contracts/**/{config.contract}.sol")))
                contract_files.extend(list(self.project_path.glob(f"test/**/{config.contract}.sol")))
                contract_files.extend(list(self.project_path.glob(f"{config.contract}.sol")))
                contract_files.extend(list(self.project_path.glob(f"**/{config.contract}.sol")))
                
                if contract_files:
                    cmd.append(str(contract_files[0]))
                else:
                    return EchidnaResult(
                        success=False,
                        total_tests=0,
                        passed_tests=0,
                        failed_tests=0,
                        coverage_percentage=0.0,
                        execution_time=0.0,
                        gas_used=0,
                        fuzzing_stats={},
                        findings=[],
                        config=config,
                        output="",
                        error_output=f"Contract {config.contract} not found in project"
                    )
            else:
                echidna_test_files = []
                echidna_test_files.extend(list(self.project_path.glob("test/**/*EchidnaTest.sol")))
                echidna_test_files.extend(list(self.project_path.glob("src/**/*EchidnaTest.sol")))
                echidna_test_files.extend(list(self.project_path.glob("contracts/**/*EchidnaTest.sol")))
                echidna_test_files.extend(list(self.project_path.glob("*EchidnaTest.sol")))
                echidna_test_files.extend(list(self.project_path.glob("**/*EchidnaTest.sol")))
                
                if echidna_test_files:
                    cmd.append(str(echidna_test_files[0]))
                else:
                    return EchidnaResult(
                        success=False,
                        total_tests=0,
                        passed_tests=0,
                        failed_tests=0,
                        coverage_percentage=0.0,
                        execution_time=0.0,
                        gas_used=0,
                        fuzzing_stats={},
                        findings=[],
                        config=config,
                        output="",
                        error_output="No EchidnaTest.sol files found in project"
                    )
            
            if config.runs:
                cmd.extend(["--test-limit", str(config.runs)])
            if config.timeout:
                cmd.extend(["--timeout", str(config.timeout)])
            if config.seed:
                cmd.extend(["--seed", str(config.seed)])
            if config.verbosity:
                cmd.extend(["--format", "text"])
            
            logger.info(f"Running Echidna with command: {' '.join(cmd)}")
            
            # Run the command
            start_time = time.time()
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=config.timeout + 60,  # Add buffer for timeout
                cwd=self.project_path
            )
            execution_time = time.time() - start_time
            
            if result.returncode == 0:
                output_lines = result.stdout.split('\n')
                total_tests = 0
                passed_tests = 0
                failed_tests = 0
                coverage_percentage = 0.0
                findings = []
                
                for line in output_lines:
                    if "test" in line.lower() and "passed" in line.lower():
                        passed_tests += 1
                        total_tests += 1
                    elif "test" in line.lower() and "failed" in line.lower():
                        failed_tests += 1
                        total_tests += 1
                    elif "coverage" in line.lower() and "%" in line:
                        try:
                            coverage_percentage = float(line.split('%')[0].split()[-1])
                        except:
                            pass
                
                return EchidnaResult(
                    success=True,
                    total_tests=total_tests,
                    passed_tests=passed_tests,
                    failed_tests=failed_tests,
                    coverage_percentage=coverage_percentage,
                    execution_time=execution_time,
                    gas_used=0, 
                    fuzzing_stats={
                        "runs": config.runs,
                        "timeout": config.timeout,
                        "gas_limit": config.gas_limit
                    },
                    findings=findings,
                    config=config,
                    output=result.stdout,
                    error_output=result.stderr
                )
            else:
                error_output = result.stderr or result.stdout
                findings = []
                
                for line in error_output.split('\n'):
                    if "failed" in line.lower() or "error" in line.lower():
                        findings.append(line.strip())
                
                return EchidnaResult(
                    success=False,
                    total_tests=0,
                    passed_tests=0,
                    failed_tests=len(findings),
                    coverage_percentage=0.0,
                    execution_time=execution_time,
                    gas_used=0,
                    fuzzing_stats={},
                    findings=findings,
                    config=config,
                    output=result.stdout,
                    error_output=error_output
                )
                
        except subprocess.TimeoutExpired:
            return EchidnaResult(
                success=False,
                total_tests=0,
                passed_tests=0,
                failed_tests=0,
                coverage_percentage=0.0,
                execution_time=config.timeout + 60,
                gas_used=0,
                fuzzing_stats={},
                findings=["Test execution timed out"],
                config=config,
                output="",
                error_output="Test execution timed out"
            )
        except Exception as e:
            logger.error(f"Error running Echidna tests: {e}")
            return EchidnaResult(
                success=False,
                total_tests=0,
                passed_tests=0,
                failed_tests=0,
                coverage_percentage=0.0,
                execution_time=0.0,
                gas_used=0,
                fuzzing_stats={},
                findings=[str(e)],
                config=config,
                output="",
                error_output=str(e)
            )