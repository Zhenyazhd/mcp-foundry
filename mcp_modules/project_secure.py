import subprocess
import json
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import logging
import time
import re

logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
MAX_TOTAL_FILES = 1000

class ProjectType(Enum):
    """Supported project types"""
    FOUNDRY = "foundry"

@dataclass
class ProjectConfig:
    """Project configuration"""
    project_id: str
    project_type: ProjectType
    project_path: str
    user_id: str = "default"
    solc_version: str = "0.8.19"
    optimization_enabled: bool = True
    optimizer_runs: int = 200
    evm_version: str = "london"
    created_at: float = 0.0
    
    def __post_init__(self):
        if self.created_at == 0.0:
            self.created_at = time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class SecurityError(Exception):
    """Custom exception for security violations"""
    pass

class ProjectManager:
    """Manages temporary projects with Foundry initialization and security"""
    
    @staticmethod
    def validate_and_resolve_path(requested_path: str, base_path: Path) -> Path:
        """Validate and resolve file path relative to base_path
        
        Args:
            requested_path: The requested file path (relative or absolute)
            base_path: The base directory that paths must be within
            
        Returns:
            Path: Validated absolute path
            
        Raises:
            SecurityError: If path is invalid or outside allowed directory
        """
        try:
            base_path_resolved = base_path.resolve()
        except (OSError, ValueError) as e:
            raise SecurityError(f"Invalid base path: {e}")
        
        try:
            requested_path_obj = Path(requested_path)
            
            if requested_path_obj.is_absolute():
                target_path = requested_path_obj.resolve()
            else:
                target_path = (base_path_resolved / requested_path).resolve()
            
            try:
                target_path.relative_to(base_path_resolved)
            except ValueError:
                raise SecurityError(f"Path outside allowed directory: {requested_path}")
            
            return target_path
        
        except (OSError, ValueError) as e:
            raise SecurityError(f"Invalid path: {e}")
    
    @staticmethod
    def validate_file_size(content: str) -> None:
        """Check if file content size is within limits
        
        Raises:
            SecurityError: If content exceeds MAX_FILE_SIZE
        """
        if len(content.encode('utf-8')) > MAX_FILE_SIZE:
            raise SecurityError("Content too large")
    
    def __init__(self, base_dir: str = None):
        self.base_dir = Path(base_dir) if base_dir else Path(tempfile.gettempdir()) / "mcp_projects"
        self.base_dir.mkdir(exist_ok=True)
        self.projects: Dict[str, Dict[str, ProjectConfig]] = {}
        self._load_projects()
    
    def _load_projects(self):
        """Load existing projects from metadata"""
        metadata_file = self.base_dir / ".projects_metadata.json"
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r') as f:
                    data = json.load(f)
                
                if isinstance(data, dict) and data:
                    first_key = list(data.keys())[0]
                    if first_key.startswith('project_') or len(first_key) == 8:
                        for project_id, project_data in data.items():
                            project_data['project_type'] = ProjectType(project_data['project_type'])
                            project_data.pop('auto_cleanup', None)
                            user_id = project_data.get('user_id', 'default')
                            if user_id not in self.projects:
                                self.projects[user_id] = {}
                            self.projects[user_id][project_id] = ProjectConfig(**project_data)
                    else:
                        for user_id, user_projects in data.items():
                            if user_id not in self.projects:
                                self.projects[user_id] = {}
                            for project_id, project_data in user_projects.items():
                                project_data['project_type'] = ProjectType(project_data['project_type'])
                                project_data.pop('auto_cleanup', None)
                                self.projects[user_id][project_id] = ProjectConfig(**project_data)
                
                total_projects = sum(len(projects) for projects in self.projects.values())
                logger.info(f"Loaded {total_projects} existing projects across {len(self.projects)} users")
            except Exception as e:
                logger.error(f"Error loading projects metadata: {e}")
                self.projects = {}
    
    def _save_projects(self):
        """Save projects metadata"""
        metadata_file = self.base_dir / ".projects_metadata.json"
        try:
            data = {}
            for user_id, user_projects in self.projects.items():
                data[user_id] = {}
                for project_id, project in user_projects.items():
                    project_dict = project.to_dict()
                    project_dict['project_type'] = project.project_type.value
                    data[user_id][project_id] = project_dict
            
            with open(metadata_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            total_projects = sum(len(projects) for projects in self.projects.values())
            logger.info(f"Saved {total_projects} projects metadata across {len(self.projects)} users")
        except Exception as e:
            logger.error(f"Error saving projects metadata: {e}")
    
    def create_project(
        self,
        user_id: str = "default",
        project_type: ProjectType = ProjectType.FOUNDRY,
        solc_version: str = "0.8.19",
        optimization_enabled: bool = True,
        optimizer_runs: int = 200,
        evm_version: str = "london"
    ) -> ProjectConfig:
        """Create a new temporary project for a specific user"""
        if not user_id or not isinstance(user_id, str):
            user_id = "default"
        
        user_id = re.sub(r'[^a-zA-Z0-9_-]', '_', user_id)
        if not user_id:
            user_id = "default"
        
        user_dir = self.base_dir / f"user_{user_id}"
        user_dir.mkdir(exist_ok=True)
        
        project_id = str(uuid.uuid4())[:8]
        project_path = user_dir / f"project_{project_id}"
        
        project_path.mkdir(exist_ok=True)
        
        if project_type == ProjectType.FOUNDRY:
            self._init_foundry_project(project_path, solc_version, optimization_enabled, optimizer_runs, evm_version)
        
        config = ProjectConfig(
            project_id=project_id,
            project_type=project_type,
            project_path=str(project_path),
            user_id=user_id,
            solc_version=solc_version,
            optimization_enabled=optimization_enabled,
            optimizer_runs=optimizer_runs,
            evm_version=evm_version
        )
        
        if user_id not in self.projects:
            self.projects[user_id] = {}
        self.projects[user_id][project_id] = config
        self._save_projects()
        
        logger.info(f"Created {project_type} project: {project_id} for user {user_id} at {project_path}")
        return config
    
    def _init_foundry_project(self, project_path: Path, solc_version: str, optimization_enabled: bool, optimizer_runs: int, evm_version: str):
        """Initialize Foundry project"""
        try:
            result = subprocess.run(
                ["forge", "init", "--no-git", str(project_path)],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                logger.warning(f"Forge init failed: {result.stderr}")
                self._create_foundry_structure(project_path)
            
            try:
                subprocess.run(
                    ["git", "init"],
                    cwd=project_path,
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                logger.info("Initialized git repository for dependency management")
            except Exception as e:
                logger.warning(f"Failed to initialize git repository: {e}")
            
            foundry_toml = project_path / "foundry.toml"
            foundry_config = f"""[profile.default]
                src = "src"
                out = "out"
                libs = ["lib"]
                solc = "{solc_version}"
                optimizer = {str(optimization_enabled).lower()}
                optimizer_runs = {optimizer_runs}
                evm_version = "{evm_version}"
                via_ir = false
                verbosity = 2
                fuzz = {{ runs = 1000 }}
                invariant = {{ runs = 256 }}
                gas_reports = ["*"]
                gas_reports_ignore = []

                [profile.ci]
                fuzz = {{ runs = 10000 }}
                invariant = {{ runs = 1000 }}

                [profile.lite]
                optimizer = false
                fuzz = {{ runs = 10 }}
                invariant = {{ runs = 10 }}
            """
            
            with open(foundry_toml, 'w') as f:
                f.write(foundry_config)
            
            self._cleanup_default_files(project_path)
            
            logger.info(f"Initialized Foundry project at {project_path}")
            
        except Exception as e:
            logger.error(f"Error initializing Foundry project: {e}")
            self._create_foundry_structure(project_path)
            self._cleanup_default_files(project_path)
    
    def _create_foundry_structure(self, project_path: Path):
        """Create basic Foundry project structure manually"""
        (project_path / "src").mkdir(exist_ok=True)
        (project_path / "test").mkdir(exist_ok=True)
        (project_path / "script").mkdir(exist_ok=True)
        (project_path / "lib").mkdir(exist_ok=True)
        
        logger.info("Created basic Foundry project structure")
    
    def _cleanup_default_files(self, project_path: Path):
        """Remove default files created by forge init"""
        try:
            files_to_remove = [
                "src/Counter.sol",
                "test/Counter.t.sol",
                "script/Counter.s.sol"
            ]
            
            removed_files = []
            for file_path in files_to_remove:
                full_path = project_path / file_path
                if full_path.exists():
                    full_path.unlink()
                    removed_files.append(file_path)
                    logger.debug(f"Removed default file: {file_path}")
            
            if removed_files:
                logger.info(f"Cleaned up {len(removed_files)} default files: {removed_files}")
            else:
                logger.debug("No default files found to clean up")
                
        except Exception as e:
            logger.warning(f"Error cleaning up default files: {e}")
    
    def get_project(self, project_id: str, user_id: str = "default") -> Optional[ProjectConfig]:
        """Get project by ID for a specific user"""
        if user_id not in self.projects:
            return None
        return self.projects[user_id].get(project_id)
    
    def list_projects(self, user_id: str = None) -> List[ProjectConfig]:
        """List all projects for a specific user, or all projects if user_id is None"""
        if user_id:
            return list(self.projects.get(user_id, {}).values())
        else:
            all_projects = []
            for user_projects in self.projects.values():
                all_projects.extend(user_projects.values())
            return all_projects
    
    def write_deployment_script(
        self,
        project_id: str,
        user_id: str,
        script_content: str,
        script_path: str = "script/Deploy.s.sol"
    ) -> Dict[str, Any]:
        """Write deployment script content to file
        
        Args:
            project_id: Project identifier
            user_id: User identifier
            script_content: Solidity code for the deployment script
            script_path: Relative path to script file (default: script/Deploy.s.sol)
        """
        project = self.get_project(project_id, user_id)
        if not project:
            return {"success": False, "error": f"Project {project_id} not found for user {user_id}"}
        
        project_path = Path(project.project_path)
        
        try:
            validated_path = self.validate_and_resolve_path(script_path, project_path)
            validated_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(validated_path, 'w', encoding='utf-8') as f:
                f.write(script_content)
            
            logger.info(f"Wrote deployment script to {validated_path.relative_to(project_path)}")
            
            return {
                "success": True,
                "script_path": script_path,
                "absolute_path": str(validated_path),
                "message": f"Deployment script written to {script_path}"
            }
        
        except SecurityError as e:
            return {"success": False, "error": f"Path validation failed: {e}"}
        except Exception as e:
            logger.error(f"Error writing deployment script: {e}")
            return {"success": False, "error": str(e)}
    
    def write_validated_files(
        self,
        project_id: str,
        files: Dict[str, str],
        user_id: str = "default"
    ) -> Dict[str, Any]:
        """Write multiple files to project with security validation
        
        Args:
            project_id: Project identifier
            files: Dictionary where keys are file paths (can include subdirectories) 
                   and values are file contents
            user_id: User identifier
        """
        project = self.get_project(project_id, user_id)
        if not project:
            return {"success": False, "error": f"Project {project_id} not found for user {user_id}"}
        project_path = Path(project.project_path)
        
        if len(files) > MAX_TOTAL_FILES:
            return {"success": False, "error": f"Too many files. Maximum allowed: {MAX_TOTAL_FILES}"}
        
        added_files = []
        errors = []
        
        for file_path_str, content in files.items():
            result = self._write_validated_file(
                project_id, user_id, file_path_str, content, must_exist=False
            )
            
            if result["success"]:
                file_info = {
                    "filename": Path(file_path_str).name,
                    "path": file_path_str,
                    "absolute_path": result.get("absolute_path", ""),
                    "original_path": file_path_str,
                    "size": result.get("file_size", len(content.encode('utf-8'))),
                    "created_at": time.time()
                }
                added_files.append(file_info)
                logger.info(f"Added file {file_path_str} to project {project_id}")
            else:
                error_msg = f"Failed to add {file_path_str}: {result.get('error', 'Unknown error')}"
                errors.append(error_msg)
                logger.error(error_msg)
        
        return {
            "success": len(errors) == 0,
            "files": added_files,
            "count": len(added_files),
            "total_files": len(files),
            "errors": errors if errors else None,
            "message": f"Added {len(added_files)}/{len(files)} files to project"
        }
    
    def cleanup_project(self, project_id: str, user_id: str = "default") -> bool:
        """Clean up project directory and runtime objects"""
        project = self.get_project(project_id, user_id)
        if not project:
            return False
        project_path = Path(project.project_path)
        
        try:
            from .chain import stop_project_anvil
            try:
                stop_project_anvil(project_id, user_id)
            except Exception as e:
                logger.warning(f"Error stopping Anvil during cleanup: {e}")
            
            if project_path.exists():
                shutil.rmtree(project_path)
            
            if user_id in self.projects and project_id in self.projects[user_id]:
                del self.projects[user_id][project_id]
                if not self.projects[user_id]:
                    del self.projects[user_id]
            self._save_projects()
            
            logger.info(f"Cleaned up project {project_id} for user {user_id}")
            return True
        
        except Exception as e:
            logger.error(f"Error cleaning up project {project_id}: {e}")
            return False
    
    def cleanup_all_projects(self, user_id: str = None):
        """Clean up all projects for a specific user, or all projects if user_id is None"""
        if user_id:
            if user_id in self.projects:
                for project_id in list(self.projects[user_id].keys()):
                    self.cleanup_project(project_id, user_id)
                logger.info(f"Cleaned up all projects for user {user_id}")
        else:
            for user_id_key in list(self.projects.keys()):
                for project_id in list(self.projects[user_id_key].keys()):
                    self.cleanup_project(project_id, user_id_key)
            logger.info("Cleaned up all projects for all users")
    
    def cleanup_old_projects(self, max_age_hours: int = 24, user_id: str = None):
        """Clean up projects older than specified hours for a specific user, or all users if user_id is None"""
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        
        old_projects = []
        users_to_check = [user_id] if user_id else list(self.projects.keys())
        
        for user_id_key in users_to_check:
            if user_id_key not in self.projects:
                continue
            for project_id, project in self.projects[user_id_key].items():
                if current_time - project.created_at > max_age_seconds:
                    old_projects.append((project_id, user_id_key))
        
        for project_id, user_id_key in old_projects:
            self.cleanup_project(project_id, user_id_key)
        
        logger.info(f"Cleaned up {len(old_projects)} old projects")
        return len(old_projects)
    
    def install_dependency(self, project_id: str, dependency_url: str, user_id: str = "default", branch: str = None) -> Dict[str, Any]:
        """Install external dependency using forge install"""
        project = self.get_project(project_id, user_id)
        if not project:
            return {"success": False, "error": f"Project {project_id} not found for user {user_id}"}
        project_path = Path(project.project_path)
        
        
        try:
            cmd = ["forge", "install"]
            
            if branch:
                if dependency_url.endswith('.git'):
                    dependency_url = dependency_url[:-4]
                cmd.append(f"{dependency_url}@{branch}")
            else:
                cmd.append(dependency_url)
            
            logger.info(f"Installing dependency: {dependency_url}")
            result = subprocess.run(
                cmd,
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode == 0:
                logger.info(f"Successfully installed dependency: {dependency_url}")
                return {
                    "success": True,
                    "dependency_url": dependency_url,
                    "branch": branch,
                    "output": result.stdout,
                    "message": f"Successfully installed {dependency_url}"
                }
            else:
                logger.error(f"Failed to install dependency: {result.stderr}")
                return {
                    "success": False,
                    "error": result.stderr,
                    "output": result.stdout
                }
        
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Dependency installation timeout"}
        except Exception as e:
            logger.error(f"Error installing dependency: {e}")
            return {"success": False, "error": str(e)}
    
    def get_file_content(self, project_id: str, file_path: str, user_id: str = "default") -> Dict[str, Any]:
        """Get content of any file from project directory with security validation
        
        Args:
            project_id: Project identifier
            file_path: Path to file relative to project root (e.g., "src/Contract.sol", "test/Test.t.sol")
            user_id: User identifier
        """
        project = self.get_project(project_id, user_id)
        if not project:
            return {"success": False, "error": f"Project {project_id} not found for user {user_id}"}
        project_path = Path(project.project_path)
        
        try:
            try:
                validated_path = self.validate_and_resolve_path(file_path, project_path)
            except SecurityError as e:
                return {"success": False, "error": str(e)}
            
            if not validated_path.exists():
                return {
                    "success": False,
                    "error": f"File not found: {file_path}"
                }
            
            if not validated_path.is_file():
                return {
                    "success": False,
                    "error": f"Path is not a file: {file_path}"
                }
            
            try:
                content = validated_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                return {
                    "success": False,
                    "error": f"File encoding error: {file_path}"
                }
            
            stat = validated_path.stat()
            
            return {
                "success": True,
                "file_path": file_path,
                "absolute_path": str(validated_path),
                "content": content,
                "metadata": {
                    "size_bytes": stat.st_size,
                    "created_at": stat.st_ctime,
                    "modified_at": stat.st_mtime,
                    "is_readable": True
                },
                "project_id": project_id
            }
            
        except Exception as e:
            logger.error(f"Error reading file {file_path} from project {project_id}: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def list_project_files(self, project_id: str, user_id: str = "default", directory: str = None, file_pattern: str = None) -> Dict[str, Any]:
        """List files in project directory with security validation
        
        Args:
            project_id: Project identifier
            user_id: User identifier
            directory: Subdirectory to list (e.g., "src", "test", "script"). If None, lists root directory
            file_pattern: File pattern to filter (e.g., "*.sol", "*.t.sol"). If None, lists all files
        """
        project = self.get_project(project_id, user_id)
        if not project:
            return {"success": False, "error": f"Project {project_id} not found for user {user_id}"}
        project_path = Path(project.project_path)
        
        try:
            if directory:
                try:
                    validated_dir = self.validate_and_resolve_path(directory, project_path)
                except SecurityError as e:
                    return {"success": False, "error": str(e)}
                
                target_dir = validated_dir
            else:
                target_dir = project_path
            
            if not target_dir.exists():
                return {
                    "success": False,
                    "error": f"Directory not found: {directory or 'root'}"
                }
            
            if not target_dir.is_dir():
                return {
                    "success": False,
                    "error": f"Path is not a directory: {directory or 'root'}"
                }
            
            files = []
            directories = []
            
            for item in target_dir.iterdir():
                try:
                    item.resolve().relative_to(project_path.resolve())
                except ValueError:
                    continue  # Skip items outside project directory
                
                relative_path = item.relative_to(project_path)
                
                if item.is_file():
                    if file_pattern and not item.match(file_pattern):
                        continue
                    
                    stat = item.stat()
                    files.append({
                        "name": item.name,
                        "path": str(relative_path),
                        "size_bytes": stat.st_size,
                        "modified_at": stat.st_mtime,
                        "extension": item.suffix,
                        "is_file": True
                    })
                
                elif item.is_dir():
                    directories.append({
                        "name": item.name,
                        "path": str(relative_path),
                        "is_file": False
                    })
            
            return {
                "success": True,
                "directory": directory or "root",
                "project_id": project_id,
                "files": sorted(files, key=lambda x: x["name"]),
                "directories": sorted(directories, key=lambda x: x["name"]),
                "total_files": len(files),
                "total_directories": len(directories),
                "file_pattern": file_pattern
            }
            
        except Exception as e:
            logger.error(f"Error listing files in project {project_id}: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def apply_file_modifications(self, content: str, modifications: Dict[str, Any]) -> str:
        """Apply file modifications - simplified to only replace_all_content
        
        This method supports ONLY "replace_all_content" modification type.
        Any other modification types in the `modifications` dict are ignored
        (this is intentional, not a bug).
        
        Agent responsibility:
        - Read the file content
        - Compute the diff and generate new content
        - Call this method with "replace_all_content" to validate and replace
        
        This method only performs:
        - Security validation (file size limits)
        - Content replacement
        
        Args:
            content: Original file content
            modifications: Dict with optional "replace_all_content" key containing
                          {"new_content": str}. All other keys are ignored.
        
        Returns:
            Modified content (or original if no replace_all_content provided)
        
        Raises:
            SecurityError: If new content exceeds size limits
        """
        modified_content = content
        
        if "replace_all_content" in modifications:
            new_content = modifications["replace_all_content"].get("new_content")
            if new_content is not None:
                self.validate_file_size(new_content)
                modified_content = new_content
        
        self.validate_file_size(modified_content)
        
        return modified_content
    
    def _write_validated_file(
        self,
        project_id: str,
        user_id: str,
        file_path: str,
        content: str,
        must_exist: bool = False
    ) -> Dict[str, Any]:
        """Internal helper to write file content with validation
        
        Args:
            project_id: Project identifier
            user_id: User identifier
            file_path: Path to file relative to project root
            content: File content to write
            must_exist: If True, file must exist (for modification). If False, file can be created.
        
        Returns:
            Dict with success status and file information or error
        """
        project = self.get_project(project_id, user_id)
        if not project:
            return {"success": False, "error": f"Project {project_id} not found for user {user_id}"}
        
        project_path = Path(project.project_path)
        
        try:
            validated_path = self.validate_and_resolve_path(file_path, project_path)
        except SecurityError as e:
            return {"success": False, "error": f"Security validation failed: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Path validation error: {e}"}
        
        if must_exist:
            if not validated_path.exists():
                return {"success": False, "error": f"File {file_path} not found in project"}
            if validated_path.is_dir():
                return {"success": False, "error": f"Path {file_path} is a directory, not a file"}
        
        try:
            self.validate_file_size(content)
        except SecurityError as e:
            return {"success": False, "error": f"Content validation failed: {e}"}
        
        if not must_exist:
            validated_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(validated_path, 'w', encoding='utf-8') as f:
                f.write(content)
        except Exception as e:
            return {"success": False, "error": f"Error writing file: {e}"}
        
        return {
            "success": True,
            "file_path": file_path,
            "absolute_path": str(validated_path),
            "file_size": len(content.encode('utf-8'))
        }


_project_manager = ProjectManager(base_dir=Path.home() / "mcp_projects")
def get_project_manager() -> ProjectManager:
    """Get global project manager"""
    return _project_manager
