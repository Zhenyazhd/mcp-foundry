from mcp_modules.project import ProjectType, get_project_manager, apply_file_modifications
from mcp_modules.tests_runner import TestRunner, TestConfig, TestResult
from mcp_modules.scenario import ScenarioRunner, ScenarioParser, ScenarioHelper
from mcp_modules.echidna_runner import EchidnaRunner, EchidnaConfig, EchidnaResult

from mcp.server.fastmcp import FastMCP
from pathlib import Path
import json, time, subprocess
from typing import Dict, List, Any, Optional
import logging

mcp = FastMCP("Smart Contract Project Manager")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
project_manager = get_project_manager()


########################################################
# MAIN TOOLS
########################################################
@mcp.tool()
def project_create(
    project_type: str = "foundry",
    solc_version: str = "0.8.19",
    optimization_enabled: bool = True,
    optimizer_runs: int = 200,
    evm_version: str = "london",
    auto_cleanup: bool = True
) -> Dict[str, Any]:
    """Create a new temporary project with Foundry initialization"""
    try:
        if project_type not in [t.value for t in ProjectType]:
            return {
                "success": False,
                "error": f"Invalid project type: {project_type}. Valid types: {[t.value for t in ProjectType]}"
            }
        
        project = project_manager.create_project(
            project_type=ProjectType(project_type),
            solc_version=solc_version,
            optimization_enabled=optimization_enabled,
            optimizer_runs=optimizer_runs,
            evm_version=evm_version,
            auto_cleanup=auto_cleanup
        )
        
        return {
            "success": True,
            "project": project.to_dict()
        }
        
    except Exception as e:
        logger.error(f"Error creating project: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@mcp.tool()
def project_list() -> Dict[str, Any]:
    """List all available projects"""
    try:
        projects = project_manager.list_projects()
        
        return {
            "success": True,
            "projects": [project.to_dict() for project in projects],
            "count": len(projects),
            "message": f"Found {len(projects)} projects"
        }
        
    except Exception as e:
        logger.error(f"Error listing projects: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": "Failed to list projects"
        }

@mcp.tool()
def project_debug(project_id: str) -> Dict[str, Any]:
    """Debug project information and status"""
    try:
        project = project_manager.get_project(project_id)
        
        if not project:
            all_projects = project_manager.list_projects()
            available_ids = [p.project_id for p in all_projects]
            
            return {
                "success": False,
                "error": f"Project {project_id} not found",
                "available_project_ids": available_ids,
                "total_projects": len(available_ids),
                "message": f"Project {project_id} not found. Available projects: {available_ids}"
            }
        
        project_path = Path(project.project_path)
        directory_exists = project_path.exists()
        
        directory_contents = []
        if directory_exists:
            try:
                directory_contents = [item.name for item in project_path.iterdir()]
            except Exception as e:
                directory_contents = [f"Error reading directory: {e}"]
        
        return {
            "success": True,
            "project": project.to_dict(),
            "debug_info": {
                "project_id": project.project_id,
                "project_path": str(project_path),
                "directory_exists": directory_exists,
                "directory_contents": directory_contents,
                "project_type": project.project_type.value,
                "created_at": project.created_at,
                "auto_cleanup": project.auto_cleanup
            },
            "message": f"Project {project_id} found and accessible"
        }
        
    except Exception as e:
        logger.error(f"Error debugging project {project_id}: {e}")
        return {
            "success": False,
            "error": str(e),
            "project_id": project_id,
            "message": "Failed to debug project"
        }

@mcp.tool()
def project_add_files(
    project_id: str,
    files: Dict[str, str]
) -> Dict[str, Any]:
    """Add multiple files to project (contracts, tests, scripts, configs, etc.)"""
    try:
        result = project_manager.add_files(project_id, files)
        
        return {
            "success": result["success"],
            "files": result.get("files", []),
            "count": result.get("count", 0),
            "total_files": result.get("total_files", 0),
            "errors": result.get("errors"),
            "message": result.get("message", f"Added {result.get('count', 0)}/{result.get('total_files', 0)} files to project")
        }
        
    except Exception as e:
        logger.error(f"Error adding files: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@mcp.tool()
def project_delete_file(
    project_id: str,
    file_path: str,
    recursive: bool = False
) -> Dict[str, Any]:
    """Delete a file or directory from project
    
    Args:
        project_id: The project ID
        file_path: Path to the file or directory to delete
        recursive: If True, recursively delete directories and their contents
    """
    try:
        project = project_manager.get_project(project_id)
        if not project:
            return {
                "success": False,
                "error": f"Project {project_id} not found"
            }
        
        project_path = Path(project.project_path)
        full_path = project_path / file_path
        
        if not full_path.exists():
            return {
                "success": False,
                "error": f"File {file_path} not found in project"
            }
        
        try:
            full_path.resolve().relative_to(project_path.resolve())
        except ValueError:
            return {
                "success": False,
                "error": "File path is outside project directory"
            }
        
        if full_path.is_dir():
            if recursive:
                import shutil
                shutil.rmtree(full_path)
                logger.info(f"Recursively deleted directory {file_path} from project {project_id}")
            else:
                return {
                    "success": False,
                    "error": f"Directory {file_path} cannot be deleted without recursive=True"
                }
        else:
            full_path.unlink()
            logger.info(f"Deleted file {file_path} from project {project_id}")
        
        return {
            "success": True,
            "file_path": file_path,
            "message": f"Successfully deleted {file_path}"
        }
        
    except Exception as e:
        logger.error(f"Error deleting file: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@mcp.tool()
def project_modify_file(
    project_id: str,
    file_path: str,
    modifications: Dict[str, Any]
) -> Dict[str, Any]:
    """Modify an existing file with specific changes"""
    try:
        project = project_manager.get_project(project_id)
        if not project:
            return {
                "success": False,
                "error": f"Project {project_id} not found"
            }
        
        project_path = Path(project.project_path)
        full_path = project_path / file_path
        
        if not full_path.exists():
            return {
                "success": False,
                "error": f"File {file_path} not found in project"
            }
        
        if full_path.is_dir():
            return {
                "success": False,
                "error": f"Path {file_path} is a directory, not a file. Please specify the full file path."
            }
        
        try:
            full_path.resolve().relative_to(project_path.resolve())
        except ValueError:
            return {
                "success": False,
                "error": "File path is outside project directory"
            }
        
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                current_content = f.read()
        except Exception as e:
            return {
                "success": False,
                "error": f"Error reading file: {e}"
            }
        
        modified_content = apply_file_modifications(current_content, modifications)
        try:
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(modified_content)
        except Exception as e:
            return {
                "success": False,
                "error": f"Error writing modified file: {e}"
            }
        
        logger.info(f"Modified file {file_path} in project {project_id}")
        
        return {
            "success": True,
            "file_path": file_path,
            "modifications_applied": list(modifications.keys()),
            "file_size": len(modified_content),
            "message": f"Successfully modified {file_path}"
        }
        
    except Exception as e:
        logger.error(f"Error modifying file: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@mcp.tool()
def project_modify_files_by_pattern(
    project_id: str,
    directory_path: str,
    file_pattern: str,
    modifications: Dict[str, Any]
) -> Dict[str, Any]:
    """Modify multiple files matching a pattern in a directory"""
    try:
        project = project_manager.get_project(project_id)
        if not project:
            return {
                "success": False,
                "error": f"Project {project_id} not found"
            }
        
        project_path = Path(project.project_path)
        target_dir = project_path / directory_path
        
        if not target_dir.exists() or not target_dir.is_dir():
            return {
                "success": False,
                "error": f"Directory {directory_path} not found in project"
            }
        
        try:
            target_dir.resolve().relative_to(project_path.resolve())
        except ValueError:
            return {
                "success": False,
                "error": "Directory path is outside project directory"
            }
        
        import glob
        pattern_path = target_dir / file_pattern
        matching_files = glob.glob(str(pattern_path), recursive=True)
        
        if not matching_files:
            return {
                "success": False,
                "error": f"No files found matching pattern {file_pattern} in {directory_path}"
            }
        
        modified_files = []
        errors = []
        
        for file_path in matching_files:
            try:
                file_path_obj = Path(file_path)
                
                if file_path_obj.is_dir():
                    continue
                
                with open(file_path_obj, 'r', encoding='utf-8') as f:
                    current_content = f.read()
                
                modified_content = apply_file_modifications(current_content, modifications)
                
                with open(file_path_obj, 'w', encoding='utf-8') as f:
                    f.write(modified_content)
                
                relative_path = file_path_obj.relative_to(project_path)
                modified_files.append(str(relative_path))
                
                logger.info(f"Modified file {relative_path} in project {project_id}")
                
            except Exception as e:
                error_msg = f"Failed to modify {file_path}: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)
        
        return {
            "success": len(errors) == 0,
            "modified_files": modified_files,
            "count": len(modified_files),
            "total_files": len(matching_files),
            "errors": errors if errors else None,
            "message": f"Modified {len(modified_files)}/{len(matching_files)} files matching pattern {file_pattern}"
        }
        
    except Exception as e:
        logger.error(f"Error modifying files by pattern: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@mcp.tool()
def project_download_file_from_github(
    project_id: str,
    github_url: str,
    target_path: str,
    branch: str = "main"
) -> Dict[str, Any]:
    """Download a single file from GitHub repository to project directory"""
    try:
        project = project_manager.get_project(project_id)
        if not project:
            return {
                "success": False,
                "error": f"Project {project_id} not found"
            }
        
        project_path = Path(project.project_path)
        
        github_info = _parse_github_url(github_url)
        if not github_info:
            return {
                "success": False,
                "error": "Invalid GitHub URL format. Expected: https://github.com/owner/repo/blob/branch/path/to/file"
            }
        
        file_content = _download_file_from_github(github_info["owner"], github_info["repo"], github_info["file_path"], branch)
        if not file_content:
            return {
                "success": False,
                "error": f"Failed to download file from GitHub: {github_url}"
            }
        
        target_path_obj = Path(target_path)
        if target_path_obj.parts[0] in ['src', 'test', 'script']:
            target_dir = project_path / target_path_obj.parent
        else:
            target_dir = project_path / "src" / target_path_obj.parent
        
        target_dir.mkdir(exist_ok=True, parents=True)
        final_file_path = target_dir / target_path_obj.name
        
        try:
            with open(final_file_path, 'w', encoding='utf-8') as f:
                f.write(file_content)
        except Exception as e:
            return {
                "success": False,
                "error": f"Error writing downloaded file: {e}"
            }
        
        logger.info(f"Downloaded file from GitHub to {final_file_path.relative_to(project_path)} in project {project_id}")
        
        return {
            "success": True,
            "file_path": str(final_file_path.relative_to(project_path)),
            "github_url": github_url,
            "file_size": len(file_content),
            "message": f"Successfully downloaded file from {github_url}"
        }
        
    except Exception as e:
        logger.error(f"Error downloading file from GitHub: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@mcp.tool()
def project_download_multiple_files_from_github(
    project_id: str,
    github_urls: List[Dict[str, str]]
) -> Dict[str, Any]:
    """Download multiple files from GitHub repositories to project directory
    
    Args:
        github_urls: List of dictionaries with keys: 'url', 'target_path', 'branch' (optional)
    """
    try:
        project = project_manager.get_project(project_id)
        if not project:
            return {
                "success": False,
                "error": f"Project {project_id} not found"
            }
        
        downloaded_files = []
        errors = []
        
        for file_info in github_urls:
            github_url = file_info.get("url")
            target_path = file_info.get("target_path")
            branch = file_info.get("branch", "main")
            
            if not github_url or not target_path:
                errors.append(f"Missing url or target_path in file info: {file_info}")
                continue
            
            result = project_download_file_from_github(project_id, github_url, target_path, branch)
            
            if result["success"]:
                downloaded_files.append({
                    "url": github_url,
                    "target_path": target_path,
                    "file_path": result["file_path"],
                    "file_size": result["file_size"]
                })
            else:
                errors.append(f"Failed to download {github_url}: {result['error']}")
        
        return {
            "success": len(errors) == 0,
            "downloaded_files": downloaded_files,
            "count": len(downloaded_files),
            "total_files": len(github_urls),
            "errors": errors if errors else None,
            "message": f"Downloaded {len(downloaded_files)}/{len(github_urls)} files from GitHub"
        }
        
    except Exception as e:
        logger.error(f"Error downloading multiple files from GitHub: {e}")
        return {
            "success": False,
            "error": str(e)
        }

def _parse_github_url(url: str) -> Optional[Dict[str, str]]:
    """Parse GitHub URL to extract owner, repo, and file path"""
    import re
    
    pattern = r'https://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+)'
    match = re.match(pattern, url)
    
    if match:
        return {
            "owner": match.group(1),
            "repo": match.group(2),
            "branch": match.group(3),
            "file_path": match.group(4)
        }
    
    pattern_raw = r'https://raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)/(.+)'
    match_raw = re.match(pattern_raw, url)
    
    if match_raw:
        return {
            "owner": match_raw.group(1),
            "repo": match_raw.group(2),
            "branch": match_raw.group(3),
            "file_path": match_raw.group(4)
        }
    
    return None

def _download_file_from_github(owner: str, repo: str, file_path: str, branch: str = "main") -> Optional[str]:
    """Download file content from GitHub using raw URL"""
    try:
        import requests
        
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{file_path}"
        
        logger.info(f"Downloading file from: {raw_url}")
        
        response = requests.get(raw_url, timeout=30)
        response.raise_for_status()
        
        return response.text
        
    except requests.RequestException as e:
        logger.error(f"Failed to download file from GitHub: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error downloading file: {e}")
        return None

@mcp.tool()
def project_list() -> Dict[str, Any]:
    """List all projects"""
    try:
        projects = project_manager.list_projects()
        
        return {
            "success": True,
            "projects": [p.to_dict() for p in projects],
            "count": len(projects)
        }
        
    except Exception as e:
        logger.error(f"Error listing projects: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@mcp.tool()
def project_compile(project_id: str) -> Dict[str, Any]:
    """Compile project contracts"""
    try:
        result = project_manager.compile_project(project_id)
        
        return {
            "success": result.get("success", False),
            "compilation_result": result,
            "project_id": project_id
        }
        
    except Exception as e:
        logger.error(f"Error compiling project: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@mcp.tool()
def project_start_anvil(project_id: str) -> Dict[str, Any]:
    """Start Anvil instance for specific project"""
    try:
        result = project_manager.start_project_anvil(project_id)
        
        return {
            "success": result["success"],
            "anvil_port": result.get("anvil_port"),
            "anvil_chain_id": result.get("anvil_chain_id"),
            "rpc_url": result.get("rpc_url"),
            "message": result.get("message"),
            "error": result.get("error")
        }
        
    except Exception as e:
        logger.error(f"Error starting Anvil for project: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@mcp.tool()
def project_stop_anvil(project_id: str) -> Dict[str, Any]:
    """Stop Anvil instance for specific project"""
    try:
        result = project_manager.stop_project_anvil(project_id)
        
        return {
            "success": result["success"],
            "message": result.get("message"),
            "error": result.get("error")
        }
        
    except Exception as e:
        logger.error(f"Error stopping Anvil for project: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@mcp.tool()
def project_cleanup_all() -> Dict[str, Any]:
    """Clean up all projects"""
    try:
        project_manager.cleanup_all_projects()
        
        return {
            "success": True,
            "message": "All projects cleaned up successfully"
        }
        
    except Exception as e:
        logger.error(f"Error cleaning up all projects: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@mcp.tool()
def test_run_all(
    project_id: str,
    timeout: int = 300,
    verbosity: int = 2
) -> Dict[str, Any]:
    """Run all tests for a project"""
    try:
        project = project_manager.get_project(project_id)
        if not project:
            return {
                "success": False,
                "error": f"Project {project_id} not found"
            }
        
        config = TestConfig(
            timeout=timeout,
            verbosity=verbosity,
            gas_reports=True
        )
        
        runner = TestRunner(project.project_path)        
        result = runner.run_all_tests(config)
        
        return {
            "success": result.success,
            "total_tests": result.total_tests,
            "passed_tests": result.passed_tests,
            "failed_tests": result.failed_tests,
            "skipped_tests": result.skipped_tests,
            "execution_time": result.execution_time,
            "output": result.output,
            "error_message": result.error_message
        }
        
    except Exception as e:
        logger.error(f"Error running all tests: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@mcp.tool()
def test_run_fuzz(
    project_id: str,
    runs: int = 1000,
    timeout: int = 300,
    verbosity: int = 2
) -> Dict[str, Any]:
    """Run fuzz tests for a project"""
    try:
        project = project_manager.get_project(project_id)
        if not project:
            return {
                "success": False,
                "error": f"Project {project_id} not found"
            }
        
        config = TestConfig(
            runs=runs,
            timeout=timeout,
            verbosity=verbosity,
            gas_reports=True
        )
        
        runner = TestRunner(project.project_path)
        result = runner.run_fuzz_tests(config)
        
        return {
            "success": result.success,
            "total_tests": result.total_tests,
            "passed_tests": result.passed_tests,
            "failed_tests": result.failed_tests,
            "skipped_tests": result.skipped_tests,
            "execution_time": result.execution_time,
            "output": result.output,
            "error_message": result.error_message
        }
        
    except Exception as e:
        logger.error(f"Error running fuzz tests: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@mcp.tool()
def test_run_coverage(
    project_id: str,
    timeout: int = 300,
    verbosity: int = 2
) -> Dict[str, Any]:
    """Run coverage analysis for a project"""
    try:
        project = project_manager.get_project(project_id)
        if not project:
            return {
                "success": False,
                "error": f"Project {project_id} not found"
            }
        
        config = TestConfig(
            timeout=timeout,
            verbosity=verbosity,
            gas_reports=True
        )
        
        runner = TestRunner(project.project_path)
        result = runner.run_coverage_analysis(config)
        
        return {
            "success": result["success"],
            "execution_time": result["execution_time"],
            "coverage_data": result["coverage_data"],
            "output": result["output"],
            "error_message": result["error_message"]
        }
        
    except Exception as e:
        logger.error(f"Error running coverage analysis: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@mcp.tool()
def test_get_gas_reports(
    project_id: str,
    timeout: int = 300,
    verbosity: int = 2
) -> Dict[str, Any]:
    """Get gas reports by running tests with gas reporting enabled"""
    try:
        project = project_manager.get_project(project_id)
        if not project:
            return {
                "success": False,
                "error": f"Project {project_id} not found"
            }
        
        config = TestConfig(
            timeout=timeout,
            verbosity=verbosity,
            gas_reports=True
        )
        
        runner = TestRunner(project.project_path)
        
        result = runner.run_all_tests(config)
        
        return {
            "success": result.success,
            "gas_report": result.gas_report,
            "execution_time": result.execution_time,
            "total_tests": result.total_tests,
            "passed_tests": result.passed_tests,
            "failed_tests": result.failed_tests,
            "output": result.output,
            "error_message": result.error_message
        }
        
    except Exception as e:
        logger.error(f"Error getting gas reports: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@mcp.tool()
def project_generate_deployment_script(
    project_id: str,
    deployment_requirements: str = None
) -> Dict[str, Any]:
    """Generate deployment script for project based on artifacts"""
    try:
        from mcp_modules.project import generate_deployment_script
        
        result = generate_deployment_script(project_id, deployment_requirements)
        
        return {
            "success": result.get("success", False),
            "script_path": result.get("script_path"),
            "artifacts_analyzed": result.get("artifacts_analyzed", 0),
            "contracts": result.get("contracts", []),
            "error": result.get("error")
        }
        
    except Exception as e:
        logger.error(f"Error generating deployment script: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@mcp.tool()
def project_analyze_artifacts(project_id: str) -> Dict[str, Any]:
    """Analyze contract artifacts for deployment information"""
    try:
        from mcp_modules.project import analyze_contract_artifacts
        
        result = analyze_contract_artifacts(project_id)
        
        return {
            "success": result.get("success", False),
            "contracts": result.get("contracts", {}),
            "total_contracts": result.get("total_contracts", 0),
            "analysis_summary": result.get("analysis_summary", {}),
            "error": result.get("error")
        }
        
    except Exception as e:
        logger.error(f"Error analyzing artifacts: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@mcp.tool()
def project_deploy(
    project_id: str,
    script_path: str = None,
    rpc_url: str = "http://localhost:8545",
    private_key: str = None,
    broadcast: bool = True,
    transaction_type: str = "1559",
    **kwargs
) -> Dict[str, Any]:
    """Deploy project contracts"""
    try:
        if transaction_type not in ["legacy", "1559"]:
            return {
                "success": False,
                "error": "Transaction type must be 'legacy' or '1559'"
            }
        
        result = project_manager.deploy_project(
            project_id=project_id,
            script_path=script_path,
            rpc_url=rpc_url,
            private_key=private_key,
            broadcast=broadcast,
            transaction_type=transaction_type,
            **kwargs
        )
        
        return {
            "success": result.get("success", False),
            "deployment_result": result,
            "project_id": project_id
        }
        
    except Exception as e:
        logger.error(f"Error deploying project: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@mcp.tool()
def project_install_dependency(
    project_id: str,
    dependency_url: str,
    branch: str = None
) -> Dict[str, Any]:
    """Install external dependency (e.g., OpenZeppelin) in Foundry project"""
    try:
        result = project_manager.install_dependency(project_id, dependency_url, branch)
        
        return {
            "success": result["success"],
            "project_id": project_id,
            "dependency_url": dependency_url,
            "branch": branch,
            "message": result.get("message", "Dependency installation completed"),
            "output": result.get("output", ""),
            "error": result.get("error")
        }
        
    except Exception as e:
        logger.error(f"Error installing dependency: {e}")
        return {
            "success": False,
            "error": str(e)
        }



########################################################
# SCENARIO TOOLS (NOT IMPLEMENTED)
########################################################

@mcp.tool()
def scenario_run_from_file(
    project_id: str,
    scenario_file: str,
    rpc_url: Optional[str] = None
) -> Dict[str, Any]:
    """Run a scenario from YAML file"""
    try:
        project = project_manager.get_project(project_id)
        if not project:
            return {
                "success": False,
                "error": f"Project {project_id} not found"
            }
        
        project_path = Path(project.project_path)
        scenario_path = project_path / scenario_file
        
        if not scenario_path.exists():
            return {
                "success": False,
                "error": f"Scenario file not found: {scenario_file}"
            }
        
        runner = ScenarioRunner(rpc_url or "http://localhost:8545")
        result = runner.run_scenario_from_file(scenario_path)
        
        return {
            "success": result.success,
            "scenario_name": result.scenario_name,
            "execution_time": result.execution_time,
            "steps_executed": result.steps_executed,
            "total_steps": result.total_steps,
            "artifacts": result.artifacts,
            "error": result.error,
            "gas_used": result.gas_used,
            "events": result.events
        }
        
    except Exception as e:
        logger.error(f"Error running scenario: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@mcp.tool()
def scenario_run_from_yaml(
    project_id: str,
    yaml_content: str,
    rpc_url: Optional[str] = None
) -> Dict[str, Any]:
    """Run a scenario from YAML content"""
    try:
        project = project_manager.get_project(project_id)
        if not project:
            return {
                "success": False,
                "error": f"Project {project_id} not found"
            }
        
        runner = ScenarioRunner(rpc_url or "http://localhost:8545")
        result = runner.run_scenario_from_yaml(yaml_content)
        
        return {
            "success": result.success,
            "scenario_name": result.scenario_name,
            "execution_time": result.execution_time,
            "steps_executed": result.steps_executed,
            "total_steps": result.total_steps,
            "artifacts": result.artifacts,
            "error": result.error,
            "gas_used": result.gas_used,
            "events": result.events
        }
        
    except Exception as e:
        logger.error(f"Error running scenario: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@mcp.tool()
def scenario_create_template(
    project_id: str,
    contract_name: str,
    scenario_type: str = "custom"
) -> Dict[str, Any]:
    """Create scenario template for agent based on contract ABI"""
    try:
        project = project_manager.get_project(project_id)
        if not project:
            return {
                "success": False,
                "error": f"Project {project_id} not found"
            }
        
        compile_result = project_manager.compile_project(project_id)
        
        if not compile_result.get("success", False):
            return {
                "success": False,
                "error": f"Compilation failed: {compile_result.get('errors', 'Unknown error')}"
            }
        
        artifacts = compile_result.get("artifacts", [])
        contract_abi = None
        for artifact in artifacts:
            if artifact["name"] == contract_name:
                contract_abi = artifact.get("abi", [])
                break
        
        if not contract_abi:
            return {
                "success": False,
                "error": f"Contract {contract_name} not found in artifacts"
            }
        
        helper = ScenarioHelper()
        template = helper.create_scenario_template(contract_name, contract_abi, scenario_type)
        
        return {
            "success": True,
            "template": template,
            "message": f"Scenario template created for {contract_name}"
        }
        
    except Exception as e:
        logger.error(f"Error creating scenario template: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@mcp.tool()
def scenario_parse_yaml(
    yaml_content: str
) -> Dict[str, Any]:
    """Parse YAML scenario and return structured data"""
    try:
        parser = ScenarioParser()
        scenario = parser.parse_yaml(yaml_content)
        
        return {
            "success": True,
            "scenario": {
                "name": scenario.name,
                "description": scenario.description,
                "roles": {name: role.address for name, role in scenario.roles.items()},
                "contracts": scenario.contracts,
                "steps": [
                    {
                        "type": step.type.value,
                        "data": step.data,
                        "description": step.description
                    }
                    for step in scenario.steps
                ],
                "timeout": scenario.timeout,
                "gas_limit": scenario.gas_limit
            }
        }
        
    except Exception as e:
        logger.error(f"Error parsing YAML: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@mcp.tool()
def scenario_save_to_file(
    project_id: str,
    scenario_name: str,
    yaml_content: str
) -> Dict[str, Any]:
    """Save scenario YAML to project file"""
    try:
        project = project_manager.get_project(project_id)
        if not project:
            return {
                "success": False,
                "error": f"Project {project_id} not found"
            }
        
        project_path = Path(project.project_path)
        scenarios_dir = project_path / "scenarios"
        scenarios_dir.mkdir(exist_ok=True)
        
        scenario_file = scenarios_dir / f"{scenario_name}.yaml"
        
        with open(scenario_file, 'w', encoding='utf-8') as f:
            f.write(yaml_content)
        
        return {
            "success": True,
            "scenario_file": str(scenario_file.relative_to(project_path)),
            "message": f"Scenario saved to {scenario_file.name}"
        }
        
    except Exception as e:
        logger.error(f"Error saving scenario: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@mcp.tool()
def scenario_start_local_chain(
    port: int = 8545
) -> Dict[str, Any]:
    """Start local Anvil chain for scenario testing"""
    try:
        runner = ScenarioRunner()
        success = runner.start_local_chain(port)
        
        if success:
            return {
                "success": True,
                "rpc_url": f"http://localhost:{port}",
                "message": f"Local chain started on port {port}"
            }
        else:
            return {
                "success": False,
                "error": "Failed to start local chain"
            }
        
    except Exception as e:
        logger.error(f"Error starting local chain: {e}")
        return {
            "success": False,
            "error": str(e)
        }



@mcp.tool()
def project_install_multiple_dependencies(
    project_id: str,
    dependencies: List[Dict[str, str]]
) -> Dict[str, Any]:
    """Install multiple dependencies at once"""
    try:
        result = project_manager.install_multiple_dependencies(project_id, dependencies)
        
        return {
            "success": result["success"],
            "project_id": project_id,
            "total_dependencies": result["total_dependencies"],
            "successful_installs": result["successful_installs"],
            "failed_installs": result["failed_installs"],
            "results": result["results"],
            "message": f"Installed {result['successful_installs']}/{result['total_dependencies']} dependencies"
        }
        
    except Exception as e:
        logger.error(f"Error installing multiple dependencies: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@mcp.tool()
def project_get_file_content(
    project_id: str,
    file_path: str
) -> Dict[str, Any]:
    """Get content of any file from project directory
    
    Args:
        project_id: Project identifier
        file_path: Path to file relative to project root (e.g., "src/Contract.sol", "test/Test.t.sol", "foundry.toml")
    
    Returns:
        File content with metadata including size, timestamps, and absolute path
    """
    try:
        result = project_manager.get_file_content(project_id, file_path)
        
        if result["success"]:
            return {
                "success": True,
                "project_id": project_id,
                "file_path": result["file_path"],
                "absolute_path": result["absolute_path"],
                "content": result["content"],
                "metadata": result["metadata"],
                "message": f"Successfully read file {file_path}"
            }
        else:
            return {
                "success": False,
                "error": result["error"],
                "project_id": project_id,
                "file_path": file_path
            }
        
    except Exception as e:
        logger.error(f"Error getting file content: {e}")
        return {
            "success": False,
            "error": str(e),
            "project_id": project_id,
            "file_path": file_path
        }

@mcp.tool()
def project_list_files(
    project_id: str,
    directory: str = None,
    file_pattern: str = None
) -> Dict[str, Any]:
    """List files in project directory
    
    Args:
        project_id: Project identifier
        directory: Subdirectory to list (e.g., "src", "test", "script"). If None, lists root directory
        file_pattern: File pattern to filter (e.g., "*.sol", "*.t.sol", "*.toml"). If None, lists all files
    
    Returns:
        List of files and directories with metadata
    """
    try:
        result = project_manager.list_project_files(project_id, directory, file_pattern)
        
        if result["success"]:
            return {
                "success": True,
                "project_id": project_id,
                "directory": result["directory"],
                "files": result["files"],
                "directories": result["directories"],
                "total_files": result["total_files"],
                "total_directories": result["total_directories"],
                "file_pattern": result["file_pattern"],
                "message": f"Found {result['total_files']} files and {result['total_directories']} directories"
            }
        else:
            return {
                "success": False,
                "error": result["error"],
                "project_id": project_id,
                "directory": directory,
                "file_pattern": file_pattern
            }
        
    except Exception as e:
        logger.error(f"Error listing project files: {e}")
        return {
            "success": False,
            "error": str(e),
            "project_id": project_id,
            "directory": directory,
            "file_pattern": file_pattern
        }

@mcp.tool()
def echidna_run_tests(
    project_id: str,
    runs: int = 1000,
    timeout: int = 300,
    gas_limit: int = 30000000,
    contract: str = None,
    test_mode: str = "property",
    seed: int = None,
    verbosity: int = 2,
    coverage: bool = True,
    corpus_dir: str = None
) -> Dict[str, Any]:
    """Run Echidna fuzz tests on project contracts
    
    Args:
        project_id: Project identifier
        runs: Number of fuzzing runs (default: 1000)
        timeout: Test timeout in seconds (default: 300)
        gas_limit: Gas limit for transactions (default: 30000000)
        contract: Specific contract to test (optional)
        test_mode: Test mode - "property" or "assertion" (default: "property")
        seed: Random seed for reproducible results (optional)
        verbosity: Output verbosity level 0-4 (default: 2)
        coverage: Enable coverage analysis (default: True)
        corpus_dir: Directory for corpus files (optional)
    """
    try:
        project = project_manager.get_project(project_id)
        if not project:
            return {
                "success": False,
                "error": f"Project {project_id} not found"
            }
        
        config = EchidnaConfig(
            runs=runs,
            timeout=timeout,
            gas_limit=gas_limit,
            contract=contract,
            test_mode=test_mode,
            seed=seed,
            verbosity=verbosity,
            coverage=coverage,
            corpus_dir=corpus_dir
        )
        
        runner = EchidnaRunner(project.project_path)
        result = runner.run_tests(config)
        
        return {
            "success": result.success,
            "project_id": project_id,
            "total_tests": result.total_tests,
            "passed_tests": result.passed_tests,
            "failed_tests": result.failed_tests,
            "coverage_percentage": result.coverage_percentage,
            "execution_time": result.execution_time,
            "fuzzing_stats": result.fuzzing_stats,
            "findings": result.findings,
            "config": result.config.to_dict(),
            "output": result.output,
            "error_output": result.error_output,
            "message": f"Echidna tests completed: {result.passed_tests}/{result.total_tests} passed"
        }
        
    except Exception as e:
        logger.error(f"Error running Echidna tests: {e}")
        return {
            "success": False,
            "error": str(e),
            "project_id": project_id
        }

@mcp.tool()
def echidna_create_property_test(
    project_id: str,
    contract_name: str,
    test_file_name: str = None
) -> Dict[str, Any]:
    """Create a sample property test contract for Echidna
    
    Args:
        project_id: Project identifier
        contract_name: Name of the contract to test
        test_file_name: Name for the test file (optional, defaults to {ContractName}EchidnaTest.sol)
    """
    try:
        project = project_manager.get_project(project_id)
        if not project:
            return {
                "success": False,
                "error": f"Project {project_id} not found"
            }
        
        runner = EchidnaRunner(project.project_path)
        
        test_content = runner.create_sample_property_test(contract_name)
        
        if not test_file_name:
            test_file_name = f"{contract_name}EchidnaTest.sol"
        
        test_files = {
            test_file_name: test_content
        }
        
        add_result = project_manager.add_files(project_id, test_files)
        
        if add_result["success"]:
            return {
                "success": True,
                "project_id": project_id,
                "contract_name": contract_name,
                "test_file": test_file_name,
                "test_content": test_content,
                "message": f"Created Echidna property test for {contract_name}"
            }
        else:
            return {
                "success": False,
                "error": add_result["error"],
                "project_id": project_id
            }
        
    except Exception as e:
        logger.error(f"Error creating Echidna property test: {e}")
        return {
            "success": False,
            "error": str(e),
            "project_id": project_id
        }

@mcp.tool()
def echidna_check_installation() -> Dict[str, Any]:
    """Check if Echidna is installed and available"""
    try:
        runner = EchidnaRunner("/tmp")  
        is_installed = runner._check_echidna_installed()
        
        if is_installed:
            try:
                result = subprocess.run(
                    ["echidna", "--version"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                version_info = result.stdout.strip()
            except:
                version_info = "Unknown version"
            
            return {
                "success": True,
                "installed": True,
                "version": version_info,
                "message": "Echidna is installed and available"
            }
        else:
            install_info = runner.install_echidna()
            return {
                "success": False,
                "installed": False,
                "message": "Echidna is not installed",
                "installation_instructions": install_info["instructions"]
            }
        
    except Exception as e:
        logger.error(f"Error checking Echidna installation: {e}")
        return {
            "success": False,
            "installed": False,
            "error": str(e),
            "message": "Error checking Echidna installation"
        }

@mcp.tool()
def echidna_auto_install(platform: str = None) -> Dict[str, Any]:
    """Automatically install Echidna based on detected platform
    
    Args:
        platform: Target platform for installation (optional, auto-detected if not provided)
                 Supported platforms: ubuntu_debian, macos, fedora, docker, windows
    """
    try:
        runner = EchidnaRunner("/tmp")  
        
        if runner._check_echidna_installed():
            return {
                "success": True,
                "installed": True,
                "message": "Echidna is already installed",
                "action": "skipped"
            }
        
        logger.info(f"Starting automatic Echidna installation for platform: {platform or 'auto-detect'}")
        result = runner.auto_install_echidna(platform)
        
        result["action"] = "install"
        result["timestamp"] = time.time()
        
        return result
        
    except Exception as e:
        logger.error(f"Error during automatic Echidna installation: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": "Failed to install Echidna automatically",
            "action": "failed",
            "timestamp": time.time(),
            "fallback": "Use echidna_check_installation() to get manual installation instructions"
        }

@mcp.tool()
def echidna_install_in_project(project_id: str, method: str = "docker") -> Dict[str, Any]:
    """Install Echidna locally in the project directory
    
    Args:
        project_id: Project identifier
        method: Installation method - "docker" (recommended) or "binary" (experimental)
    """
    try:
        project = project_manager.get_project(project_id)
        if not project:
            return {
                "success": False,
                "error": f"Project {project_id} not found"
            }
        
        runner = EchidnaRunner(project.project_path)
        
        if method == "docker":
            result = runner.install_echidna_docker_locally(project.project_path)
        elif method == "binary":
            result = runner.install_echidna_locally(project.project_path)
        else:
            return {
                "success": False,
                "error": f"Unsupported installation method: {method}",
                "message": "Supported methods: 'docker', 'binary'"
            }
        
        result["project_id"] = project_id
        result["project_path"] = str(project.project_path)
        result["method"] = method
        result["timestamp"] = time.time()
        
        return result
        
    except Exception as e:
        logger.error(f"Error installing Echidna in project {project_id}: {e}")
        return {
            "success": False,
            "error": str(e),
            "project_id": project_id,
            "message": "Failed to install Echidna in project"
        }

'''@mcp.tool()
def echidna_run_tests_local(project_id: str, runs: int = 1000, timeout: int = 300, gas_limit: int = 30000000, contract: str = None, test_mode: str = "property", seed: int = None, verbosity: int = 2, coverage: bool = True, corpus_dir: str = None) -> Dict[str, Any]:
    """Run Echidna fuzz tests using local installation in project
    
    Args:
        project_id: Project identifier
        runs: Number of fuzzing runs (default: 1000)
        timeout: Test timeout in seconds (default: 300)
        gas_limit: Gas limit for transactions (default: 30000000)
        contract: Specific contract to test (optional)
        test_mode: Test mode - "property" or "assertion" (default: "property")
        seed: Random seed for reproducible results (optional)
        verbosity: Output verbosity level 0-4 (default: 2)
        coverage: Enable coverage analysis (default: True)
        corpus_dir: Directory for corpus files (optional)
    """
    try:
        project = project_manager.get_project(project_id)
        if not project:
            return {
                "success": False,
                "error": f"Project {project_id} not found"
            }
        
        runner = EchidnaRunner(project.project_path)
        
        # Check for local installation
        project_path = Path(project.project_path)
        docker_wrapper = project_path / "echidna-docker.sh"
        binary_path = project_path / "tools" / "echidna" / "echidna"
        
        if docker_wrapper.exists():
            # Use Docker wrapper
            echidna_command = str(docker_wrapper)
            installation_method = "docker"
        elif binary_path.exists():
            # Use local binary
            echidna_command = str(binary_path)
            installation_method = "binary"
        else:
            return {
                "success": False,
                "error": "No local Echidna installation found",
                "message": "Please run echidna_install_in_project() first",
                "project_id": project_id
            }
        
        # Create Echidna configuration
        config = EchidnaConfig(
            runs=runs,
            timeout=timeout,
            gas_limit=gas_limit,
            contract=contract,
            test_mode=test_mode,
            seed=seed,
            verbosity=verbosity,
            coverage=coverage,
            corpus_dir=corpus_dir
        )
        
        # Run tests with local installation
        result = runner.run_tests_with_command(config, echidna_command)
        
        # Convert EchidnaResult to dictionary and add project context
        result_dict = result.to_dict()
        result_dict["project_id"] = project_id
        result_dict["installation_method"] = installation_method
        result_dict["echidna_command"] = echidna_command
        
        return result_dict
        
    except Exception as e:
        logger.error(f"Error running Echidna tests locally in project {project_id}: {e}")
        return {
            "success": False,
            "error": str(e),
            "project_id": project_id,
            "message": "Failed to run Echidna tests locally"
        }
'''
@mcp.tool()
def echidna_create_config(
    project_id: str,
    runs: int = 1000,
    timeout: int = 300,
    gas_limit: int = 30000000,
    contract: str = None,
    test_mode: str = "property",
    seed: int = None,
    coverage: bool = True,
    corpus_dir: str = None
) -> Dict[str, Any]:
    """Create echidna.yaml configuration file for project
    
    Args:
        project_id: Project identifier
        runs: Number of fuzzing runs
        timeout: Test timeout in seconds
        gas_limit: Gas limit for transactions
        contract: Specific contract to test
        test_mode: Test mode - "property" or "assertion"
        seed: Random seed for reproducible results
        coverage: Enable coverage analysis
        corpus_dir: Directory for corpus files
    """
    try:
        project = project_manager.get_project(project_id)
        if not project:
            return {
                "success": False,
                "error": f"Project {project_id} not found"
            }
        
        config = EchidnaConfig(
            runs=runs,
            timeout=timeout,
            gas_limit=gas_limit,
            contract=contract,
            test_mode=test_mode,
            seed=seed,
            coverage=coverage,
            corpus_dir=corpus_dir
        )
        
        runner = EchidnaRunner(project.project_path)
        config_path = runner._create_echidna_config(config)
        
        return {
            "success": True,
            "project_id": project_id,
            "config_path": str(config_path.relative_to(project.project_path)),
            "config": config.to_dict(),
            "message": f"Created echidna.yaml configuration file"
        }
        
    except Exception as e:
        logger.error(f"Error creating Echidna config: {e}")
        return {
            "success": False,
            "error": str(e),
            "project_id": project_id
        }

@mcp.tool()
def scenario_stop_local_chain() -> Dict[str, Any]:
    """Stop local Anvil chain"""
    try:
        runner = ScenarioRunner()
        runner.stop_local_chain()
        
        return {
            "success": True,
            "message": "Local chain stopped"
        }
        
    except Exception as e:
        logger.error(f"Error stopping local chain: {e}")
        return {
            "success": False,
            "error": str(e)
        }



if __name__ == "__main__":
   mcp.run(transport="stdio") 
   #mcp.run(transport="streamable-http") 