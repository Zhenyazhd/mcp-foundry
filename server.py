from mcp_modules.project import ProjectType, get_project_manager, apply_file_modifications
from mcp_modules.tests_runner import TestRunner, TestConfig, TestResult
from mcp_modules.scenario import ScenarioRunner, ScenarioParser, ScenarioHelper

from mcp.server.fastmcp import FastMCP
from pathlib import Path
import json, time
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
    file_path: str
) -> Dict[str, Any]:
    """Delete a file from project"""
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
        
        # Check if file is within project directory (security check)
        try:
            full_path.resolve().relative_to(project_path.resolve())
        except ValueError:
            return {
                "success": False,
                "error": "File path is outside project directory"
            }
        
        # Delete the file
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
        
        # Check if file is within project directory (security check)
        try:
            full_path.resolve().relative_to(project_path.resolve())
        except ValueError:
            return {
                "success": False,
                "error": "File path is outside project directory"
            }
        
        # Read current content
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                current_content = f.read()
        except Exception as e:
            return {
                "success": False,
                "error": f"Error reading file: {e}"
            }
        
        # Apply modifications
        modified_content = apply_file_modifications(current_content, modifications)
        
        # Write modified content back
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
        
        # Create test config
        config = TestConfig(
            timeout=timeout,
            verbosity=verbosity,
            gas_reports=True
        )
        
        # Create test runner
        runner = TestRunner(project.project_path)
        
        # Run all tests
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
        
        # Create test config for coverage analysis
        config = TestConfig(
            timeout=timeout,
            verbosity=verbosity,
            gas_reports=True
        )
        
        # Create test runner
        runner = TestRunner(project.project_path)
        
        # Run coverage analysis
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
        
        # Create test config with gas reports enabled
        config = TestConfig(
            timeout=timeout,
            verbosity=verbosity,
            gas_reports=True
        )
        
        # Create test runner
        runner = TestRunner(project.project_path)
        
        # Run tests to get gas reports
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
        # Validate transaction type
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
        
        # Compile project to get artifacts
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
    mcp.run(transport="streamable-http")  