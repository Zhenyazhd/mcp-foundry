import subprocess
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class SecurityError(Exception):
    """Custom exception for security violations"""
    pass


class EchidnaRunner:
    """Simple runner for Echidna fuzzing tool.
    
    Provides only:
    - Check if echidna is installed
    - Path validation within project boundaries
    - Command execution with stdout/stderr return
    """

    def __init__(self, project_root: str):
        self.project_root = Path(project_root).resolve()
        self._echidna_checked: Optional[bool] = None

    def check_echidna_installed(self) -> bool:
        """Check if echidna is available in PATH."""
        if self._echidna_checked is not None:
            return self._echidna_checked

        try:
            result = subprocess.run(
                ["echidna", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                logger.info(f"Echidna detected: {result.stdout.strip()}")
                self._echidna_checked = True
            else:
                logger.error(f"Echidna check failed: {result.stderr}")
                self._echidna_checked = False
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            logger.error(f"Echidna availability check failed: {e}")
            self._echidna_checked = False

        return self._echidna_checked

    def _looks_like_path(self, arg: str) -> bool:
        """Check if argument looks like a file or directory path.
        
        Args:
            arg: Command argument to check
            
        Returns:
            True if argument looks like a path (contains / or \\, ends with file extension, or is . or ..)
        """
        if arg in (".", ".."):
            return True
        if "/" in arg or "\\" in arg:
            return True
        if any(arg.endswith(ext) for ext in (".sol", ".yaml", ".yml", ".json")):
            return True
        return False

    def validate_path(self, requested_path: str) -> Path:
        """Validate and resolve file path relative to project root.
        
        Args:
            requested_path: The requested file path (relative or absolute)
            
        Returns:
            Path: Validated absolute path within project root
            
        Raises:
            SecurityError: If path is invalid or outside project directory
        """
        try:
            requested_path_obj = Path(requested_path)
            
            if requested_path_obj.is_absolute():
                target_path = requested_path_obj.resolve()
            else:
                target_path = (self.project_root / requested_path).resolve()
            
            try:
                target_path.relative_to(self.project_root)
            except ValueError:
                raise SecurityError(f"Path outside project directory: {requested_path}")
            
            return target_path
        
        except (OSError, ValueError) as e:
            raise SecurityError(f"Invalid path: {e}")

    def run(
        self,
        command: List[str],
        timeout: int = 300
    ) -> Dict[str, Any]:
        """Run echidna command and return stdout/stderr.
        
        Args:
            command: List of command arguments (e.g., ["echidna", "test/MyTest.sol", "--config", "echidna.yaml"])
            timeout: Command timeout in seconds (default: 300)
            
        Returns:
            Dict with:
                - success: bool (True if return_code == 0)
                - return_code: int
                - stdout: str
                - stderr: str
        """
        if not self.check_echidna_installed():
            return {
                "success": False,
                "return_code": 1,
                "stdout": "",
                "stderr": "Echidna is not installed or not available in PATH",
                "command": command,
                "cwd": str(self.project_root),
            }
        
        validated_command = []
        for i, arg in enumerate(command):
            if i == 0:
                validated_command.append(arg)
                continue
            
            if arg.startswith("-"):
                validated_command.append(arg)
                continue
            
            if self._looks_like_path(arg):
                try:
                    validated_path = self.validate_path(arg)
                    validated_command.append(str(validated_path.relative_to(self.project_root)))
                except SecurityError as e:
                    return {
                        "success": False,
                        "return_code": 1,
                        "stdout": "",
                        "stderr": f"Security error: path outside project: {arg}",
                        "command": validated_command + [arg],
                        "cwd": str(self.project_root),
                    }
            else:
                validated_command.append(arg)
        
        try:
            logger.info(f"Running Echidna: {' '.join(validated_command)}")

            result = subprocess.run(
                validated_command,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            
            return {
                "success": result.returncode == 0,
                "return_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "command": validated_command,
                "cwd": str(self.project_root),
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "return_code": 124,
                "stdout": "",
                "stderr": f"Echidna command timeout (exceeded {timeout} seconds)",
                "command": validated_command,
                "cwd": str(self.project_root),
            }
        
        except Exception as e:
            logger.error(f"Error running Echidna: {e}")
            return {
                "success": False,
                "return_code": 1,
                "stdout": "",
                "stderr": str(e),
                "command": validated_command,
                "cwd": str(self.project_root),
            }
