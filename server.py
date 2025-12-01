from mcp_modules.project_secure import (
    ProjectType, get_project_manager, SecurityError
)
from mcp.server.fastmcp import FastMCP
from pathlib import Path
from typing import Dict, Any, Optional, List
from mcp_modules.echidna_runner import EchidnaRunner
import logging

mcp = FastMCP("Smart Contract Project Manager")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
project_manager = get_project_manager()


########################################################
# MAIN TOOLS
########################################################
@mcp.tool(
    "project_create",
    description=(
        "Create a new Foundry project for a user.\n"
        "- This initializes a complete Foundry project structure.\n"
        "- The project_id is auto-generated and returned in the response.\n"
        "- Use this project_id for all subsequent operations."
    )
)
def project_create(
    user_id: str,
    project_type: str = "foundry",
    solc_version: str = "0.8.19",
    optimization_enabled: bool = True,
    optimizer_runs: int = 200,
    evm_version: str = "london"
) -> Dict[str, Any]:
    """Create a new temporary project with Foundry initialization for a specific user"""
    try:
        if project_type not in [t.value for t in ProjectType]:
            return {
                "success": False,
                "error": f"Invalid project type: {project_type}. Valid types: {[t.value for t in ProjectType]}"
            }
        
        project = project_manager.create_project(
            user_id=user_id,
            project_type=ProjectType(project_type),
            solc_version=solc_version,
            optimization_enabled=optimization_enabled,
            optimizer_runs=optimizer_runs,
            evm_version=evm_version
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

@mcp.tool(
    "project_list",
    description=(
        "List all projects for a user or all users.\n"
        "- If user_id is provided, returns only that user's projects.\n"
        "- If user_id is None, returns all projects from all users.\n"
        "- Use this to find existing project_ids before operations.\n"
        "\n"
        "Foundry project structure:\n"
        "- src/ - contract source files (*.sol)\n"
        "- test/ - test files (*.t.sol)\n"
        "- script/ - deployment scripts (*.s.sol)\n"
        "- lib/ - external dependencies (installed via project_install_dependency)\n"
        "- foundry.toml - project configuration"
    )
)
def project_list(user_id: str = None) -> Dict[str, Any]:
    """List all available projects for a specific user, or all projects if user_id is None"""
    try:
        projects = project_manager.list_projects(user_id)
        
        return {
            "success": True,
            "projects": [project.to_dict() for project in projects],
            "count": len(projects),
            "user_id": user_id or "all",
            "message": f"Found {len(projects)} projects" + (f" for user {user_id}" if user_id else " for all users")
        }
        
    except Exception as e:
        logger.error(f"Error listing projects: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": "Failed to list projects"
        }

@mcp.tool(
    "project_debug",
    description=(
        "Get detailed debug information about a project.\n"
        "- Returns project configuration, path, directory contents, and metadata.\n"
        "- Useful for troubleshooting project issues.\n"
        "- If project not found, returns list of available project_ids."
    )
)
def project_debug(project_id: str, user_id: str) -> Dict[str, Any]:
    """Debug project information and status"""
    try:
        project = project_manager.get_project(project_id, user_id)
        
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
                "created_at": project.created_at
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

@mcp.tool(
    "project_get_path",
    description=(
        "Get the absolute filesystem path to a project directory.\n"
        "- Returns both absolute and resolved paths.\n"
        "- Useful for debugging or when you need the exact file path.\n"
        "- Check directory_exists to verify the project directory exists."
    )
)
def project_get_path(project_id: str, user_id: str) -> Dict[str, Any]:
    """Get the absolute path to a project directory"""
    try:
        project = project_manager.get_project(project_id, user_id)
        
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
        
        return {
            "success": True,
            "project_id": project_id,
            "project_path": str(project_path.absolute()),
            "project_path_resolved": str(project_path.resolve()),
            "directory_exists": directory_exists,
            "project_type": project.project_type.value,
            "created_at": project.created_at,
            "message": f"Project path retrieved successfully"
        }
        
    except Exception as e:
        logger.error(f"Error getting project path for {project_id}: {e}")
        return {
            "success": False,
            "error": str(e),
            "project_id": project_id,
            "message": "Failed to get project path"
        }

@mcp.tool(
    "project_write_files",
    description=(
        "Write one or multiple files to a project.\n"
        "- For single file: provide file_path and content.\n"
        "- For multiple files: provide files dict with {path: content}.\n"
        "- Paths are relative to project root (e.g., 'src/Contract.sol').\n"
        "- Automatically creates parent directories if needed.\n"
        "\n"
        "Foundry project structure - where to place files:\n"
        "- src/ContractName.sol - contract source files\n"
        "- test/ContractName.t.sol - test files (Foundry tests)\n"
        "- script/Deploy.s.sol - deployment scripts\n"
        "- foundry.toml - project configuration (solc version, optimizer, etc.)\n"
        "- lib/ - dependencies (use project_install_dependency, don't write manually)\n"
        "- echidna.yaml - Echidna fuzzing configuration (if using Echidna)\n"
        "\n"
        "Echidna configuration (echidna.yaml) - key parameters:\n"
        "- testMode: 'property' (default), 'assertion', 'optimization', 'overflow', 'exploration'\n"
        "- testLimit: number of transaction sequences to generate (default: 50000)\n"
        "- seqLen: number of transactions per sequence (default: 100)\n"
        "- shrinkLimit: attempts to shrink failing sequences (default: 5000)\n"
        "- contractAddr: address to deploy contract (default: '0x00a329c0648769a73afac7f9381e08fb43dbea72')\n"
        "- coverage: enable coverage-guided fuzzing (default: true)\n"
        "- corpusDir: directory to save corpus (requires coverage: true)\n"
        "- sender: list of addresses for transactions (default: ['0x10000', '0x20000', '0x30000'])\n"
        "- prefix: prefix for property functions (default: 'echidna_')\n"
        "- format: output format - 'text', 'json', or 'none' (default: null, uses TUI)\n"
        "- stopOnFail: stop fuzzing on first failure (default: false)\n"
        "- allContracts: fuzz all deployed contracts with known ABI (default: false)\n"
        "- allowFFI: allow HEVM ffi cheatcode (default: false)"
    )
)
def project_write_files(
    project_id: str,
    user_id: str,
    file_path: str = None,
    content: str = None,
    files: Dict[str, str] = None
) -> Dict[str, Any]:
    """Write one or multiple files to project (contracts, tests, scripts, configs, etc.)
    
    Args:
        project_id: The project ID
        user_id: The user ID
        file_path: Path to a single file (use with content parameter)
        content: Content for a single file (use with file_path parameter)
        files: Dictionary where keys are file paths and values are file contents (for multiple files)
    
    Note: Either provide (file_path, content) for a single file, or files dict for multiple files.
    """
    try:
        # Handle single file case
        if file_path is not None and content is not None:
            if files is not None:
                return {
                    "success": False,
                    "error": "Cannot specify both single file (file_path/content) and multiple files (files) at the same time"
                }
            
        result = project_manager._write_validated_file(
            project_id, user_id, file_path, content, must_exist=False
        )
        
        if result["success"]:
            logger.info(f"Wrote file {file_path} in project {project_id}")
            result["message"] = f"Successfully wrote {file_path}"
        
        return result
        
        # Handle multiple files case
        elif files is not None:
            if file_path is not None or content is not None:
        return {
            "success": False,
                    "error": "Cannot specify both single file (file_path/content) and multiple files (files) at the same time"
                }
            
            result = project_manager.write_validated_files(project_id, files, user_id)
        
        return {
            "success": result["success"],
            "files": result.get("files", []),
            "count": result.get("count", 0),
            "total_files": result.get("total_files", 0),
            "errors": result.get("errors"),
            "message": result.get("message", f"Added {result.get('count', 0)}/{result.get('total_files', 0)} files to project")
        }
        
        else:
            return {
                "success": False,
                "error": "Must provide either (file_path, content) for a single file or files dict for multiple files"
            }
        
    except Exception as e:
        logger.error(f"Error writing files: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@mcp.tool(
    "project_delete_file",
    description=(
        "Delete a file or directory from a project.\n"
        "- Path is relative to project root (e.g., 'src/OldContract.sol').\n"
        "- For directories, set recursive=True to delete contents.\n"
        "- Use with caution: deleted files cannot be recovered."
    )
)
def project_delete_file(
    project_id: str,
    user_id: str,
    file_path: str,
    recursive: bool = False
) -> Dict[str, Any]:
    """Delete a file or directory from project
    
    Args:
        project_id: The project ID
        user_id: The user ID
        file_path: Path to the file or directory to delete
        recursive: If True, recursively delete directories and their contents
    """
    try:
        project = project_manager.get_project(project_id, user_id)
        if not project:
            return {
                "success": False,
                "error": f"Project {project_id} not found"
            }
        
        project_path = Path(project.project_path)
        
        # Security validation
        try:
            validated_path = project_manager.validate_and_resolve_path(file_path, project_path)
        except SecurityError as e:
            return {
                "success": False,
                "error": f"Security validation failed: {e}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Path validation error: {e}"
            }
        
        # Use validated path instead of full_path
        full_path = validated_path
        
        if not full_path.exists():
            return {
                "success": False,
                "error": f"File {file_path} not found in project"
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

@mcp.tool(
    "project_modify_file",
    description=(
        "Replace the entire content of an existing file.\n"
        "- File must already exist in the project.\n"
        "- For complex modifications: read file with project_get_file_content, "
        "modify content, then write with this function.\n"
        "- This is a full replacement, not a patch."
    )
)
def project_modify_file(
    project_id: str,
    user_id: str,
    file_path: str,
    new_content: str
) -> Dict[str, Any]:
    """Replace entire file content with new content
    
    For complex modifications, agent should:
    1. Read file with project_get_file_content()
    2. Modify content as needed
    3. Write new content with this function or project_write_files()
    """
    try:
        result = project_manager._write_validated_file(
            project_id, user_id, file_path, new_content, must_exist=True
        )
        
        if result["success"]:
            logger.info(f"Modified file {file_path} in project {project_id}")
            result["message"] = f"Successfully modified {file_path}"
        
        return result
        
    except Exception as e:
        logger.error(f"Error modifying file: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@mcp.tool(
    "project_compile",
    description=(
        "Compile a Foundry project for this user.\n"
        "- Always call this before running tests or Echidna.\n"
        "- If compilation fails with a solc version error, "
        "do NOT try to install solc yourself; instead, call `project_set_solc_version` "
        "or suggest a compatible pragma."
    )
)
def project_compile(project_id: str, user_id: str) -> Dict[str, Any]:
    """Compile project contracts"""
    try:
        from mcp_modules.build import BuildManager, BuildConfig, BuildToolchain
        
        project = project_manager.get_project(project_id, user_id)
        if not project:
            return {
            "success": False,
                "error": f"Project {project_id} not found for user {user_id}"
            }
        
        project_path = Path(project.project_path)
        build_manager = BuildManager(str(project_path))
        
        config = BuildConfig(
            toolchain=BuildToolchain.FOUNDRY,
            solc_version=project.solc_version,
            source_dir="src",
            output_dir="out",
            optimization_enabled=project.optimization_enabled,
            optimizer_runs=project.optimizer_runs,
            evm_version=project.evm_version
        )
        
        result = build_manager.compile(config)
        
        return {
            "success": result.success,
            "compilation_result": {
                "success": result.success,
                "artifacts": result.artifacts,
                "compilation_time": result.compilation_time,
                "errors": result.errors,
                "warnings": result.warnings,
                "project_type": project.project_type.value
            },
            "project_id": project_id
        }
        
    except Exception as e:
        logger.error(f"Error compiling project: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@mcp.tool(
    "project_run_tests",
    description=(
        "Run Foundry tests for a project.\n"
        "- Always compile the project first using project_compile.\n"
        "- Use pattern to filter tests by name (passed as -m pattern to forge test).\n"
        "- Use extra_args for advanced options like --ffi, -vvv, --match-contract, etc.\n"
        "- Parse stdout/stderr to see test results and failures."
    )
)
def project_run_tests(
    project_id: str,
    user_id: str,
    pattern: str = None,
    extra_args: List[str] = None
) -> Dict[str, Any]:
    """Run tests for the project
    
    Args:
        project_id: The project ID
        user_id: The user ID
        pattern: Test name pattern to filter (passed as `-m pattern` to forge test)
        extra_args: Extra CLI args to append (e.g., ["--ffi", "-vvv", "--match-contract", "MyTest"])
    
    Returns:
        Test results with stdout, stderr, duration, and success status
    """
    try:
        from mcp_modules.build import BuildManager
        
        project = project_manager.get_project(project_id, user_id)
        if not project:
            return {
                "success": False,
                "error": f"Project {project_id} not found for user {user_id}"
            }
        
        project_path = Path(project.project_path)
        build_manager = BuildManager(str(project_path))
        
        result = build_manager.run_tests(
            pattern=pattern,
            extra_args=extra_args
        )
        
        return {
            "success": result.success,
            "test_result": {
                "success": result.success,
                "return_code": result.return_code,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "duration": result.duration
            },
            "project_id": project_id,
            "message": "Tests completed successfully" if result.success else "Tests failed"
        }
        
    except Exception as e:
        logger.error(f"Error running tests: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@mcp.tool(
    "project_run_echidna",
    description=(
        "Run Echidna fuzzing tests for a project.\n"
        "- Always compile the project first using project_compile.\n"
        "- Command must be a full list: ['echidna', 'test/MyTest.sol', '--config', 'echidna.yaml', '--test-limit', '1000'].\n"
        "- Agent must construct the complete command including all flags.\n"
        "- Parse stdout/stderr to see fuzzing results and property violations.\n"
        "\n"
        "Echidna configuration (echidna.yaml):\n"
        "- testMode: 'property' (user-defined properties), 'assertion' (assert failures), "
        "'optimization' (find max value), 'overflow' (detect overflows), 'exploration' (no tests)\n"
        "- testLimit: number of transaction sequences (default: 50000, can override with --test-limit)\n"
        "- seqLen: transactions per sequence (default: 100)\n"
        "- shrinkLimit: attempts to minimize failing sequences (default: 5000)\n"
        "- contractAddr: deployment address (default: '0x00a329c0648769a73afac7f9381e08fb43dbea72')\n"
        "- coverage: enable coverage-guided fuzzing (default: true)\n"
        "- corpusDir: save corpus directory (requires coverage: true)\n"
        "- sender: list of addresses for transactions (default: ['0x10000', '0x20000', '0x30000'])\n"
        "- prefix: property function prefix (default: 'echidna_') - functions starting with this are tested\n"
        "- format: 'text', 'json', or 'none' (default: null uses TUI)\n"
        "- stopOnFail: stop on first failure (default: false)\n"
        "- allContracts: fuzz all deployed contracts (default: false)\n"
        "- allowFFI: allow HEVM ffi cheatcode (default: false)\n"
        "\n"
        "Property functions must start with the prefix (default 'echidna_') and return bool."
    )
)
def project_run_echidna(
    project_id: str,
    user_id: str,
    command: List[str],
    timeout: int = 300
) -> Dict[str, Any]:
    """Run Echidna fuzzing tests for the project.
    
    Args:
        project_id: The project ID
        user_id: The user ID
        command: List of command arguments for echidna (e.g., ["echidna", "test/MyTest.sol", "--config", "echidna.yaml", "--test-limit", "1000"])
        timeout: Command timeout in seconds (default: 300)
    
    Note: Agent should construct the full command including:
    - Target test file path
    - Config file path (if needed)
    - Test parameters (--test-limit, --seed, etc.)
    - Output format (--format text/json)
    """
    try:
        project = project_manager.get_project(project_id, user_id)
        if not project:
            return {
                "success": False,
                "error": f"Project {project_id} not found for user {user_id}"
            }

        runner = EchidnaRunner(project.project_path)
        result = runner.run(command, timeout=timeout)

        return {
            "success": result["success"],
            "return_code": result["return_code"],
            "stdout": result["stdout"],
            "stderr": result["stderr"],
            "project_id": project_id,
        }
    except Exception as e:
        logger.error(f"Error running Echidna for project {project_id}: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@mcp.tool(
    "project_cleanup_all",
    description=(
        "Delete all projects for a user or all users.\n"
        "- If user_id is provided, deletes only that user's projects.\n"
        "- If user_id is None, deletes ALL projects from ALL users.\n"
        "- This permanently removes project directories and cannot be undone."
    )
)
def project_cleanup_all(user_id: str = None) -> Dict[str, Any]:
    """Clean up all projects for a specific user, or all projects if user_id is None"""
    try:
        project_manager.cleanup_all_projects(user_id)
        
        message = f"All projects cleaned up successfully" + (f" for user {user_id}" if user_id else " for all users")
        return {
            "success": True,
            "message": message
        }
        
    except Exception as e:
        logger.error(f"Error cleaning up all projects: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@mcp.tool(
    "project_get_deployment_artifacts",
    description=(
        "Get compilation artifacts (ABI, bytecode) for deployment.\n"
        "- Automatically compiles the project if needed.\n"
        "- Returns artifacts with ABI, bytecode, and contract info.\n"
        "- Use this data to generate deployment script content, "
        "then write it with project_write_deployment_script."
    )
)
def project_get_deployment_artifacts(
    project_id: str,
    user_id: str
) -> Dict[str, Any]:
    """Get compilation artifacts for generating deployment script
    
    Returns artifacts with ABI, bytecode, and contract information.
    Agent should use this data to generate deployment script content,
    then use project_write_deployment_script() to write it.
    """
    try:
        from mcp_modules.build import BuildManager, BuildConfig, BuildToolchain
        
        project = project_manager.get_project(project_id, user_id)
        if not project:
            return {
                "success": False,
                "error": f"Project {project_id} not found for user {user_id}"
            }
        
        project_path = Path(project.project_path)
        build_manager = BuildManager(str(project_path))
        
        config = BuildConfig(
            toolchain=BuildToolchain.FOUNDRY,
            solc_version=project.solc_version,
            source_dir="src",
            output_dir="out",
            optimization_enabled=project.optimization_enabled,
            optimizer_runs=project.optimizer_runs,
            evm_version=project.evm_version
        )
        
        compile_result = build_manager.compile(config)
        
        if not compile_result.success:
            return {
            "success": False,
                "error": "Project compilation failed",
                "compilation_errors": compile_result.errors
            }
        
        artifacts = compile_result.artifacts
        if not artifacts:
            return {
                "success": False,
                "error": "No artifacts found. Make sure the project has contracts and has been compiled successfully."
            }
        
        return {
            "success": True,
            "artifacts": artifacts,
            "solc_version": project.solc_version,
            "project_path": project.project_path,
            "message": f"Found {len(artifacts)} contract artifacts"
        }
        
    except Exception as e:
        logger.error(f"Error getting deployment artifacts: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@mcp.tool(
    "project_write_deployment_script",
    description=(
        "Write a Foundry deployment script to the project.\n"
        "- Generate script content based on artifacts from project_get_deployment_artifacts.\n"
        "- Script must be valid Solidity code for Foundry Script.\n"
        "- Default path is 'script/Deploy.s.sol' but can be customized."
    )
)
def project_write_deployment_script(
    project_id: str,
    user_id: str,
    script_content: str,
    script_path: str = "script/Deploy.s.sol"
) -> Dict[str, Any]:
    """Write deployment script content to file
    
    Agent should generate the script content based on artifacts from
    project_get_deployment_artifacts(), then use this function to write it.
    """
    try:
        result = project_manager.write_deployment_script(
            project_id, user_id, script_content, script_path
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error writing deployment script: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@mcp.tool(
    "project_deploy",
    description=(
        "Deploy contracts using a Foundry deployment script.\n"
        "- Requires a deployment script (use project_write_deployment_script first).\n"
        "- Default RPC is localhost:8545 (Anvil).\n"
        "- If broadcast=True, transactions are actually sent to the chain.\n"
        "- Parse stdout/stderr to extract contract addresses and transaction hashes."
    )
)
def project_deploy(
    project_id: str,
    user_id: str,
    script_path: str = None,
    rpc_url: str = "http://localhost:8545",
    private_key: str = None,
    broadcast: bool = True,
    transaction_type: str = "1559",
    **kwargs
) -> Dict[str, Any]:
    """Deploy project contracts using forge script
    
    Agent should parse stdout/stderr to extract contract addresses and transaction hashes.
    """
    try:
        from mcp_modules.build import BuildManager
        
        if transaction_type not in ["legacy", "1559"]:
            return {
                "success": False,
                "error": "Transaction type must be 'legacy' or '1559'"
            }
        
        project = project_manager.get_project(project_id, user_id)
        if not project:
            return {
                "success": False,
                "error": f"Project {project_id} not found for user {user_id}"
            }
        
        if not script_path:
            script_path = "script/Deploy.s.sol"
        
        build_manager = BuildManager(project.project_path)
        result = build_manager.run_script(
            script_path=script_path,
            rpc_url=rpc_url,
            private_key=private_key,
            broadcast=broadcast,
            transaction_type=transaction_type,
            extra_args=kwargs.get("extra_args")
        )
        
        return {
            "success": result.success,
            "deployment_result": result.to_dict(),
            "project_id": project_id,
            "message": "Deployment completed. Parse stdout/stderr to extract contract addresses and transaction hashes."
        }
        
    except Exception as e:
        logger.error(f"Error deploying project: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@mcp.tool(
    "project_install_dependency",
    description=(
        "Install an external dependency in a Foundry project.\n"
        "- Use this to add libraries like OpenZeppelin.\n"
        "- Dependency URL can be a GitHub repo (e.g., 'OpenZeppelin/openzeppelin-contracts').\n"
        "- Optional branch parameter for specific versions.\n"
        "- Installs to lib/ directory using forge install."
    )
)
def project_install_dependency(
    project_id: str,
    user_id: str,
    dependency_url: str,
    branch: str = None
) -> Dict[str, Any]:
    """Install external dependency (e.g., OpenZeppelin) in Foundry project"""
    try:
        result = project_manager.install_dependency(project_id, dependency_url, user_id, branch)
        
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

@mcp.tool(
    "project_get_file_content",
    description=(
        "Read the content of any file from a project.\n"
        "- Use this to read contracts, tests, configs, or any project file.\n"
        "- Path is relative to project root (e.g., 'src/Contract.sol').\n"
        "- Returns file content, metadata (size, timestamps), and absolute path."
    )
)
def project_get_file_content(
    project_id: str,
    user_id: str,
    file_path: str
) -> Dict[str, Any]:
    """Get content of any file from project directory
    
    Args:
        project_id: Project identifier
        user_id: User identifier
        file_path: Path to file relative to project root (e.g., "src/Contract.sol", "test/Test.t.sol", "foundry.toml")
    
    Returns:
        File content with metadata including size, timestamps, and absolute path
    """
    try:
        result = project_manager.get_file_content(project_id, file_path, user_id)
        
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

@mcp.tool(
    "project_list_files",
    description=(
        "List files and directories in a project.\n"
        "- If directory is None, lists root directory.\n"
        "- Use file_pattern to filter (e.g., '*.sol', '*.t.sol', '*.toml').\n"
        "- Returns files with metadata (size, timestamps) and subdirectories.\n"
        "- Useful for exploring project structure."
    )
)
def project_list_files(
    project_id: str,
    user_id: str,
    directory: str = None,
    file_pattern: str = None
) -> Dict[str, Any]:
    """List files in project directory
    
    Args:
        project_id: Project identifier
        user_id: User identifier
        directory: Subdirectory to list (e.g., "src", "test", "script"). If None, lists root directory
        file_pattern: File pattern to filter (e.g., "*.sol", "*.t.sol", "*.toml"). If None, lists all files
    
    Returns:
        List of files and directories with metadata
    """
    try:
        result = project_manager.list_project_files(project_id, user_id, directory, file_pattern)
        
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




if __name__ == "__main__":
   #mcp.run(transport="stdio") 
   #mcp.run(transport="streamable-http") 
    mcp.settings.host = "0.0.0.0"
    mcp.run(transport="streamable-http")  