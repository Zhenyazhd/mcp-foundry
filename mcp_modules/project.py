import subprocess
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import logging
import time

logger = logging.getLogger(__name__)

class ProjectType(Enum):
    """Supported project types"""
    FOUNDRY = "foundry"

@dataclass
class ProjectConfig:
    """Project configuration"""
    project_id: str
    project_type: ProjectType
    project_path: str
    solc_version: str = "0.8.19"
    optimization_enabled: bool = True
    optimizer_runs: int = 200
    evm_version: str = "london"
    auto_cleanup: bool = True
    created_at: float = 0.0
    
    def __post_init__(self):
        if self.created_at == 0.0:
            self.created_at = time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class ProjectManager:
    """Manages temporary projects with Foundry initialization"""
    
    def __init__(self, base_dir: str = None):
        self.base_dir = Path(base_dir) if base_dir else Path(tempfile.gettempdir()) / "mcp_projects"
        self.base_dir.mkdir(exist_ok=True)
        self.projects: Dict[str, ProjectConfig] = {}
        self._load_projects()
    
    def _load_projects(self):
        """Load existing projects from metadata"""
        metadata_file = self.base_dir / ".projects_metadata.json"
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r') as f:
                    data = json.load(f)
                
                for project_id, project_data in data.items():
                    project_data['project_type'] = ProjectType(project_data['project_type'])
                    self.projects[project_id] = ProjectConfig(**project_data)
                
                logger.info(f"Loaded {len(self.projects)} existing projects")
            except Exception as e:
                logger.error(f"Error loading projects metadata: {e}")
                self.projects = {}
    
    def _save_projects(self):
        """Save projects metadata"""
        metadata_file = self.base_dir / ".projects_metadata.json"
        try:
            data = {}
            for project_id, project in self.projects.items():
                project_dict = project.to_dict()
                project_dict['project_type'] = project.project_type.value
                data[project_id] = project_dict
            
            with open(metadata_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.info(f"Saved {len(self.projects)} projects metadata")
        except Exception as e:
            logger.error(f"Error saving projects metadata: {e}")
    
    def create_project(
        self,
        project_type: ProjectType = ProjectType.FOUNDRY,
        solc_version: str = "0.8.19",
        optimization_enabled: bool = True,
        optimizer_runs: int = 200,
        evm_version: str = "london",
        auto_cleanup: bool = True
    ) -> ProjectConfig:
        """Create a new temporary project"""
        project_id = str(uuid.uuid4())[:8]
        project_path = self.base_dir / f"project_{project_id}"
        
        project_path.mkdir(exist_ok=True)
        
        if project_type == ProjectType.FOUNDRY:
            self._init_foundry_project(project_path, solc_version, optimization_enabled, optimizer_runs, evm_version)
        
        config = ProjectConfig(
            project_id=project_id,
            project_type=project_type,
            project_path=str(project_path),
            solc_version=solc_version,
            optimization_enabled=optimization_enabled,
            optimizer_runs=optimizer_runs,
            evm_version=evm_version,
            auto_cleanup=auto_cleanup
        )
        
        self.projects[project_id] = config
        self._save_projects()
        
        logger.info(f"Created {project_type} project: {project_id} at {project_path}")
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
            
            # Initialize git repository for dependency management
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
    
    def _is_test_file(self, filename: str, content: str) -> bool:
        """Determine if a file is a test file"""
        filename_lower = filename.lower()
        
        test_patterns = [
            '.t.sol',  # Foundry test pattern
            'test_',   # Test prefix
            '_test.sol',  # Test suffix
            'test/',   # Test directory
            'tests/'   # Tests directory
        ]
        
        for pattern in test_patterns:
            if pattern in filename_lower:
                return True
        
        if filename_lower.endswith('test.sol'):
            return True
        
        content_lower = content.lower()
        test_content_patterns = [
            'import {test}',
            'import {console}',
            'contract test',
            'function test',
            'is test',
            'forge-std/test'
        ]
        
        for pattern in test_content_patterns:
            if pattern in content_lower:
                return True
        
        return False

    def add_files(self, project_id: str, files: Dict[str, str]) -> Dict[str, Any]:
        """Add multiple files to project (contracts, tests, scripts, configs, etc.)
        
        Args:
            project_id: Project identifier
            files: Dictionary where keys are file paths (can include subdirectories) 
                   and values are file contents
        """
        if project_id not in self.projects:
            return {"success": False, "error": f"Project {project_id} not found"}
        
        project = self.projects[project_id]
        project_path = Path(project.project_path)
        
        added_files = []
        errors = []
        
        for file_path_str, content in files.items():
            try:
                file_path_obj = Path(file_path_str)
                
                if file_path_obj.parts[0] in ['test', 'tests']:
                    target_dir = project_path / file_path_obj.parent
                elif file_path_obj.parts[0] in ['script', 'scripts']:
                    target_dir = project_path / file_path_obj.parent
                elif file_path_obj.parts[0] in ['src', 'source']:
                    target_dir = project_path / file_path_obj.parent
                elif file_path_obj.name == 'foundry.toml':
                    target_dir = project_path
                elif self._is_test_file(file_path_str, content):
                    target_dir = project_path / "test"
                elif file_path_str.endswith('.sol'):
                    target_dir = project_path / "src"
                elif file_path_str.endswith('.s.sol'):
                    target_dir = project_path / "script"
                elif file_path_str.endswith('.t.sol'):
                    target_dir = project_path / "test"
                else:
                    target_dir = project_path 
                    
                
                target_dir.mkdir(exist_ok=True, parents=True)
                
                if len(file_path_obj.parts) > 1 and file_path_obj.parts[0] not in ['test', 'tests', 'script', 'scripts', 'src', 'source']:
                    full_target_dir = project_path / file_path_obj.parent
                    full_target_dir.mkdir(exist_ok=True, parents=True)
                    final_file_path = full_target_dir / file_path_obj.name
                else:
                    final_file_path = target_dir / file_path_obj.name
                
                with open(final_file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                file_info = {
                    "filename": file_path_obj.name,
                    "content": content,
                    "path": str(final_file_path.relative_to(project_path)),
                    "original_path": file_path_str,
                    "size": len(content.encode('utf-8')),
                    "created_at": time.time()
                }
                
                added_files.append(file_info)
                
                file_type = "test" if self._is_test_file(file_path_str, content) else "file"
                logger.info(f"Added {file_type} {file_path_obj.name} to project {project_id} at {final_file_path.relative_to(project_path)}")
                
            except Exception as e:
                error_msg = f"Failed to add {file_path_str}: {str(e)}"
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
    
    def get_project(self, project_id: str) -> Optional[ProjectConfig]:
        """Get project by ID"""
        return self.projects.get(project_id)
    
    def list_projects(self) -> List[ProjectConfig]:
        """List all projects"""
        return list(self.projects.values())
    
    def compile_project(self, project_id: str) -> Dict[str, Any]:
        """Compile project using BuildManager"""
        if project_id not in self.projects:
            return {"success": False, "error": f"Project {project_id} not found"}
        
        project = self.projects[project_id]
        project_path = Path(project.project_path)
        
        try:
            from .build import BuildManager, BuildConfig, BuildToolchain
            build_manager = BuildManager(str(project_path))
            
            toolchain_map = {
                ProjectType.FOUNDRY: BuildToolchain.FOUNDRY
            }
            
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
                "artifacts": [artifact for artifact in result.artifacts],
                "compilation_time": result.compilation_time,
                "errors": result.errors,
                "warnings": result.warnings,
                "project_type": project.project_type.value
            }
        
        except Exception as e:
            logger.error(f"Error compiling project {project_id}: {e}")
            return {"success": False, "error": str(e)}
    
    def deploy_project(
        self,
        project_id: str,
        script_path: str = None,
        rpc_url: str = "http://localhost:8545",
        private_key: str = None,
        deployment_requirements: str = None,
        generate_script: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """Deploy project contracts using DeployManager with optional smart script generation"""
        if project_id not in self.projects:
            return {"success": False, "error": f"Project {project_id} not found"}
        
        project = self.projects[project_id]
        project_path = Path(project.project_path)
        
        try:
            artifacts = None
            if generate_script and not script_path:
                compile_result = self.compile_project(project_id)
                if compile_result.get("success", False):
                    artifacts = compile_result.get("artifacts", [])
                    logger.info(f"Using {len(artifacts)} artifacts for script generation")
                else:
                    logger.warning("Compilation failed, using basic deployment script")
            
            if not script_path:
                script_path = self._create_deployment_script(
                    project_path, 
                    artifacts=artifacts,
                    deployment_requirements=deployment_requirements
                )
            
            return {
                "success": True,
                "script_path": script_path,
                "script_generated": generate_script and not script_path,
                "artifacts_used": len(artifacts) if artifacts else 0,
                "message": "Deployment script generated successfully"
            }
        
        except Exception as e:
            logger.error(f"Error deploying project {project_id}: {e}")
            return {"success": False, "error": str(e)}
    
    def _analyze_artifacts_for_deployment(self, artifacts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze compilation artifacts to extract deployment information"""
        contract_info = {}
        
        for artifact in artifacts:
            contract_name = artifact.get('name', 'Unknown')
            abi = artifact.get('abi', [])
            
            constructor_params = []
            for item in abi:
                if item.get('type') == 'constructor':
                    constructor_params = item.get('inputs', [])
                    break
            
            functions = []
            for item in abi:
                if item.get('type') == 'function':
                    functions.append({
                        'name': item.get('name', ''),
                        'inputs': item.get('inputs', []),
                        'stateMutability': item.get('stateMutability', 'nonpayable')
                    })
            
            contract_info[contract_name] = {
                'constructor_params': constructor_params,
                'functions': functions,
                'abi': abi,
                'bytecode': artifact.get('bytecode', ''),
                'path': artifact.get('path', '')
            }
        
        return contract_info
    
    def _generate_deployment_script_with_llm(self, artifacts: List[Dict[str, Any]], 
                                           deployment_requirements: str = None, solc_version: str = "0.8.19") -> str:
        """Generate deployment script using LLM agent based on artifacts"""
        try:
            contract_info = self._analyze_artifacts_for_deployment(artifacts)
            
            prompt = self._create_deployment_prompt(contract_info, deployment_requirements)
    
            return self._generate_smart_deployment_template(contract_info, deployment_requirements, solc_version)
            
        except Exception as e:
            logger.error(f"Error generating deployment script with LLM: {e}")
            return self._create_basic_deployment_template(solc_version)
    
    def _create_deployment_prompt(self, contract_info: Dict[str, Any], 
                                deployment_requirements: str = None) -> str:
        """Create prompt for LLM agent to generate deployment script"""
        prompt = f"""Generate a Foundry deployment script for the following contracts:

        Contract Information:
        """
        
        for contract_name, info in contract_info.items():
            prompt += f"\nContract: {contract_name}\n"
            prompt += f"Constructor Parameters: {info['constructor_params']}\n"
            prompt += f"Available Functions: {[f['name'] for f in info['functions']]}\n"
        
        if deployment_requirements:
            prompt += f"\nDeployment Requirements: {deployment_requirements}\n"
        
        prompt += """
            Please generate a complete Foundry deployment script that:
            1. Imports necessary dependencies
            2. Deploys all contracts with appropriate constructor parameters
            3. Includes any necessary initialization calls
            4. Uses proper Foundry script structure with vm.startBroadcast() and vm.stopBroadcast()
            5. Includes console logging for deployed addresses

            Return only the Solidity code without explanations.
        """
        
        return prompt
    
    def _generate_smart_deployment_template(self, contract_info: Dict[str, Any], 
                                          deployment_requirements: str = None, solc_version: str = "0.8.19") -> str:
        """Generate smart deployment template based on artifacts analysis"""
        
        script_content = f"""// SPDX-License-Identifier: MIT
            pragma solidity ^{solc_version};

            import {{Script, console}} from "forge-std/Script.sol";
        """
        
        for contract_name in contract_info.keys():
            script_content += f'import {{{contract_name}}} from "../src/{contract_name}.sol";\n'
        
        script_content += """
        contract DeployScript is Script {
            function setUp() public {}

            function run() public {
                vm.startBroadcast();
                
                console.log("Starting deployment...");
        """
        
        for contract_name, info in contract_info.items():
            constructor_params = info['constructor_params']
            
            if constructor_params:
                param_names = [param['name'] for param in constructor_params]
                param_types = [param['type'] for param in constructor_params]
                
                script_content += f"""
                    // Deploy {contract_name}
                    console.log("Deploying {contract_name}...");
                    {contract_name} {contract_name.lower()} = new {contract_name}("""
                            
                for i, (name, param_type) in enumerate(zip(param_names, param_types)):
                    default_value = self._get_default_value_for_type(param_type)
                    if i > 0:
                        script_content += ", "
                    script_content += default_value
                
                script_content += f""");
                    console.log("{contract_name} deployed at:", address({contract_name.lower()}));
                """
            else:
                script_content += f"""
                    // Deploy {contract_name}
                    console.log("Deploying {contract_name}...");
                    {contract_name} {contract_name.lower()} = new {contract_name}();
                    console.log("{contract_name} deployed at:", address({contract_name.lower()}));
            """
                    
        script_content += """
                vm.stopBroadcast();
                console.log("Deployment completed!");
            }
        }"""
                
        return script_content
    
    def _get_default_value_for_type(self, param_type: str) -> str:
        """Get default value for Solidity type"""
        type_mapping = {
            'address': 'address(0)',
            'uint256': '0',
            'uint128': '0',
            'uint64': '0',
            'uint32': '0',
            'uint8': '0',
            'int256': '0',
            'int128': '0',
            'int64': '0',
            'int32': '0',
            'int8': '0',
            'bool': 'false',
            'string': '""',
            'bytes': '""',
            'bytes32': 'bytes32(0)',
            'bytes16': 'bytes16(0)',
            'bytes8': 'bytes8(0)',
            'bytes4': 'bytes4(0)',
            'bytes2': 'bytes2(0)',
            'bytes1': 'bytes1(0)'
        }
        
        if '[]' in param_type:
            return '[]'
        
        if 'mapping' in param_type:
            return 'mapping()'
        
        return type_mapping.get(param_type, '0')
    
    def _create_basic_deployment_template(self, solc_version: str = "0.8.19") -> str:
        """Create basic deployment template as fallback"""
        return f"""// SPDX-License-Identifier: MIT
        pragma solidity ^{solc_version};

        import {{Script, console}} from "forge-std/Script.sol";

        contract DeployScript is Script {{
            function setUp() public {{}}

            function run() public {{
                vm.startBroadcast();
                
                console.log("Starting deployment...");
                
                // Deploy contracts here
                // Example: MyContract myContract = new MyContract();
                
                vm.stopBroadcast();
                console.log("Deployment completed!");
            }}
        }}"""

    def _create_deployment_script(self, project_path: Path, artifacts: List[Dict[str, Any]] = None, 
                                deployment_requirements: str = None, solc_version: str = "0.8.19") -> str:
        """Create deployment script with optional LLM generation"""
        script_dir = project_path / "script"
        script_dir.mkdir(exist_ok=True)
        
        if artifacts and len(artifacts) > 0:
            script_content = self._generate_deployment_script_with_llm(artifacts, deployment_requirements, solc_version)
        else:
            script_content = self._create_basic_deployment_template(solc_version)
        
        script_path = script_dir / "Deploy.s.sol"
        with open(script_path, 'w') as f:
            f.write(script_content)
        
        logger.info(f"Generated deployment script at {script_path}")
        return str(script_path.relative_to(project_path))
    
    def cleanup_project(self, project_id: str) -> bool:
        """Clean up project directory"""
        if project_id not in self.projects:
            return False
        
        project = self.projects[project_id]
        project_path = Path(project.project_path)
        
        try:
            if project_path.exists():
                shutil.rmtree(project_path)
            
            del self.projects[project_id]
            self._save_projects()
            
            logger.info(f"Cleaned up project {project_id}")
            return True
        
        except Exception as e:
            logger.error(f"Error cleaning up project {project_id}: {e}")
            return False
    
    def cleanup_all_projects(self):
        """Clean up all projects"""
        for project_id in list(self.projects.keys()):
            self.cleanup_project(project_id)
        
        logger.info("Cleaned up all projects")
    
    def cleanup_old_projects(self, max_age_hours: int = 24):
        """Clean up projects older than specified hours"""
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        
        old_projects = []
        for project_id, project in self.projects.items():
            if current_time - project.created_at > max_age_seconds:
                old_projects.append(project_id)
        
        for project_id in old_projects:
            self.cleanup_project(project_id)
        
        logger.info(f"Cleaned up {len(old_projects)} old projects")
        return len(old_projects)
    
    def get_project_managers(self, project_id: str) -> Dict[str, Any]:
        """Get BuildManager, DeployManager, and AnvilWrapper for specific project"""
        if project_id not in self.projects:
            return {"error": f"Project {project_id} not found"}
        
        project = self.projects[project_id]
        project_path = Path(project.project_path)
        
        try:
            from .build import BuildManager, BuildConfig, BuildToolchain
            from .deploy import DeployManager, DeployConfig, TransactionType
            from .chain import AnvilWrapper, AnvilConfig, AnvilMode
            
            build_manager = BuildManager(str(project_path))
            deploy_manager = DeployManager(str(project_path))
            
            anvil_config = AnvilConfig(
                mode=AnvilMode.DEVNET,
                port=8545 + hash(project_id) % 1000,  
                chain_id=31337 + hash(project_id) % 1000 
            )
            anvil_wrapper = AnvilWrapper(anvil_config)
            
            build_config = BuildConfig(
                toolchain=BuildToolchain.FOUNDRY,
                solc_version=project.solc_version,
                source_dir="src",
                output_dir="out",
                optimization_enabled=project.optimization_enabled,
                optimizer_runs=project.optimizer_runs,
                evm_version=project.evm_version
            )
            
            return {
                "project": project.to_dict(),
                "build_manager": build_manager,
                "deploy_manager": deploy_manager,
                "anvil_wrapper": anvil_wrapper,
                "build_config": build_config,
                "project_path": str(project_path)
            }
        
        except Exception as e:
            logger.error(f"Error getting project managers: {e}")
            return {"error": str(e)}
    
    def start_project_anvil(self, project_id: str) -> Dict[str, Any]:
        """Start Anvil instance for specific project"""
        if project_id not in self.projects:
            return {"success": False, "error": f"Project {project_id} not found"}
        
        project = self.projects[project_id]
        
        try:
            from .chain import AnvilWrapper, AnvilConfig, AnvilMode
            
            anvil_config = AnvilConfig(
                mode=AnvilMode.DEVNET,
                port=8545 + hash(project_id) % 1000,  
                chain_id=31337 + hash(project_id) % 1000 
            )
            anvil_wrapper = AnvilWrapper(anvil_config)
            
            if anvil_wrapper.start():
                project.metadata = getattr(project, 'metadata', {})
                project.metadata['anvil_wrapper'] = anvil_wrapper
                project.metadata['anvil_port'] = anvil_wrapper.config.port
                project.metadata['anvil_chain_id'] = anvil_wrapper.config.chain_id
                
                return {
                    "success": True,
                    "anvil_port": anvil_wrapper.config.port,
                    "anvil_chain_id": anvil_wrapper.config.chain_id,
                    "rpc_url": f"http://localhost:{anvil_wrapper.config.port}",
                    "message": f"Anvil started for project {project_id}"
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to start Anvil"
                }
        
        except Exception as e:
            logger.error(f"Error starting Anvil for project {project_id}: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def stop_project_anvil(self, project_id: str) -> Dict[str, Any]:
        """Stop Anvil instance for specific project"""
        if project_id not in self.projects:
            return {"success": False, "error": f"Project {project_id} not found"}
        
        project = self.projects[project_id]
        
        try:
            if hasattr(project, 'metadata') and 'anvil_wrapper' in project.metadata:
                anvil_wrapper = project.metadata['anvil_wrapper']
                anvil_wrapper.stop()
                
                project.metadata.pop('anvil_wrapper', None)
                project.metadata.pop('anvil_port', None)
                project.metadata.pop('anvil_chain_id', None)
                
                return {
                    "success": True,
                    "message": f"Anvil stopped for project {project_id}"
                }
            else:
                return {
                    "success": False,
                    "error": "No Anvil instance found for this project"
                }
        
        except Exception as e:
            logger.error(f"Error stopping Anvil for project {project_id}: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def install_dependency(self, project_id: str, dependency_url: str, branch: str = None) -> Dict[str, Any]:
        """Install external dependency using forge install"""
        if project_id not in self.projects:
            return {"success": False, "error": f"Project {project_id} not found"}
        
        project = self.projects[project_id]
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
                if not hasattr(project, 'metadata'):
                    project.metadata = {}
                if 'dependencies' not in project.metadata:
                    project.metadata['dependencies'] = []
                
                dependency_info = {
                    'url': dependency_url,
                    'branch': branch,
                    'installed_at': time.time()
                }
                project.metadata['dependencies'].append(dependency_info)
                self._save_projects()
                
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
    
    def install_multiple_dependencies(self, project_id: str, dependencies: List[Dict[str, str]]) -> Dict[str, Any]:
        """Install multiple dependencies at once"""
        if project_id not in self.projects:
            return {"success": False, "error": f"Project {project_id} not found"}
        
        results = []
        successful_installs = 0
        
        for dep in dependencies:
            url = dep.get('url')
            branch = dep.get('branch')
            
            if not url:
                results.append({
                    "dependency": dep,
                    "success": False,
                    "error": "Missing dependency URL"
                })
                continue
            
            result = self.install_dependency(project_id, url, branch)
            results.append({
                "dependency": dep,
                "success": result["success"],
                "error": result.get("error"),
                "output": result.get("output")
            })
            
            if result["success"]:
                successful_installs += 1
        
        return {
            "success": successful_installs > 0,
            "total_dependencies": len(dependencies),
            "successful_installs": successful_installs,
            "failed_installs": len(dependencies) - successful_installs,
            "results": results
        }
    
    def get_file_content(self, project_id: str, file_path: str) -> Dict[str, Any]:
        """Get content of any file from project directory
        
        Args:
            project_id: Project identifier
            file_path: Path to file relative to project root (e.g., "src/Contract.sol", "test/Test.t.sol")
        """
        if project_id not in self.projects:
            return {"success": False, "error": f"Project {project_id} not found"}
        
        project = self.projects[project_id]
        project_path = Path(project.project_path)
        
        try:
            full_file_path = project_path / file_path
            
            try:
                full_file_path.resolve().relative_to(project_path.resolve())
            except ValueError:
                return {
                    "success": False, 
                    "error": "File path is outside project directory"
                }
            
            if not full_file_path.exists():
                return {
                    "success": False,
                    "error": f"File not found: {file_path}"
                }
            
            if not full_file_path.is_file():
                return {
                    "success": False,
                    "error": f"Path is not a file: {file_path}"
                }
            
            try:
                content = full_file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                return {
                    "success": False,
                    "error": f"File encoding error: {file_path}"
                }
            
            stat = full_file_path.stat()
            
            return {
                "success": True,
                "file_path": file_path,
                "absolute_path": str(full_file_path),
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
    
    def list_project_files(self, project_id: str, directory: str = None, file_pattern: str = None) -> Dict[str, Any]:
        """List files in project directory
        
        Args:
            project_id: Project identifier
            directory: Subdirectory to list (e.g., "src", "test", "script"). If None, lists root directory
            file_pattern: File pattern to filter (e.g., "*.sol", "*.t.sol"). If None, lists all files
        """
        if project_id not in self.projects:
            return {"success": False, "error": f"Project {project_id} not found"}
        
        project = self.projects[project_id]
        project_path = Path(project.project_path)
        
        try:
            if directory:
                target_dir = project_path / directory
            else:
                target_dir = project_path
            
            try:
                target_dir.resolve().relative_to(project_path.resolve())
            except ValueError:
                return {
                    "success": False,
                    "error": "Directory path is outside project directory"
                }
            
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

def generate_deployment_script(project_id: str, deployment_requirements: str = None) -> Dict[str, Any]:
    """Generate deployment script for project based on artifacts"""
    if project_id not in _project_manager.projects:
        return {"success": False, "error": f"Project {project_id} not found"}
    
    try:
        compile_result = _project_manager.compile_project(project_id)
        if not compile_result.get("success", False):
            return {"success": False, "error": "Project compilation failed"}
        
        artifacts = compile_result.get("artifacts", [])
        if not artifacts:
            return {"success": False, "error": "No artifacts found for script generation"}
        
        project = _project_manager.projects[project_id]
        project_path = Path(project.project_path)
        
        script_path = _project_manager._create_deployment_script(
            project_path,
            artifacts=artifacts,
            deployment_requirements=deployment_requirements,
            solc_version=project.solc_version
        )
        
        return {
            "success": True,
            "script_path": script_path,
            "artifacts_analyzed": len(artifacts),
            "contracts": [artifact.get('name', 'Unknown') for artifact in artifacts]
        }
        
    except Exception as e:
        logger.error(f"Error generating deployment script: {e}")
        return {"success": False, "error": str(e)}


def apply_file_modifications(content: str, modifications: Dict[str, Any]) -> str:
    """Apply specific modifications to file content"""
    modified_content = content
    
    # Modification types
    for modification_type, modification_data in modifications.items():
        if modification_type == "replace_text":
            # Replace specific text
            old_text = modification_data.get("old_text")
            new_text = modification_data.get("new_text")
            if old_text and new_text is not None:
                modified_content = modified_content.replace(old_text, new_text)
        
        elif modification_type == "find" and "replace" in modifications:
            find_text = modification_data
            replace_text = modifications.get("replace")
            all_occurrences = modifications.get("all_occurrences", False)
            
            if find_text and replace_text is not None:
                if all_occurrences:
                    modified_content = modified_content.replace(find_text, replace_text)
                else:
                    modified_content = modified_content.replace(find_text, replace_text, 1)
        
        elif modification_type == "replace_line":
            line_number = modification_data.get("line_number")
            new_line = modification_data.get("new_line")
            if line_number is not None and new_line is not None:
                lines = modified_content.split('\n')
                if 0 <= line_number < len(lines):
                    lines[line_number] = new_line
                    modified_content = '\n'.join(lines)
        
        elif modification_type == "insert_line":
            line_number = modification_data.get("line_number")
            new_line = modification_data.get("new_line")
            if line_number is not None and new_line is not None:
                lines = modified_content.split('\n')
                lines.insert(line_number, new_line)
                modified_content = '\n'.join(lines)
        
        elif modification_type == "delete_line":
            line_number = modification_data.get("line_number")
            if line_number is not None:
                lines = modified_content.split('\n')
                if 0 <= line_number < len(lines):
                    lines.pop(line_number)
                    modified_content = '\n'.join(lines)
        
        elif modification_type == "replace_regex":
            pattern = modification_data.get("pattern")
            replacement = modification_data.get("replacement")
            if pattern and replacement is not None:
                import re
                modified_content = re.sub(pattern, replacement, modified_content)
        
        elif modification_type == "replace_between_markers":
            start_marker = modification_data.get("start_marker")
            end_marker = modification_data.get("end_marker")
            new_content = modification_data.get("new_content")
            if start_marker and end_marker and new_content is not None:
                start_index = modified_content.find(start_marker)
                end_index = modified_content.find(end_marker)
                if start_index >= 0 and end_index >= 0 and end_index > start_index:
                    modified_content = (
                        modified_content[:start_index] +
                        start_marker + new_content + end_marker +
                        modified_content[end_index + len(end_marker):]
                    )
        
        elif modification_type == "add_import":
            import_statement = modification_data.get("import_statement")
            if import_statement:
                lines = modified_content.split('\n')
                last_import_index = -1
                for i, line in enumerate(lines):
                    if line.strip().startswith('import '):
                        last_import_index = i
                
                if last_import_index >= 0:
                    lines.insert(last_import_index + 1, import_statement)
                    modified_content = '\n'.join(lines)
                else:
                    pragma_index = -1
                    for i, line in enumerate(lines):
                        if line.strip().startswith('pragma '):
                            pragma_index = i
                            break
                    
                    if pragma_index >= 0:
                        lines.insert(pragma_index + 1, import_statement)
                        lines.insert(pragma_index + 2, "")  
                        modified_content = '\n'.join(lines)
        
        elif modification_type == "add_function":
            function_code = modification_data.get("function_code")
            if function_code:
                lines = modified_content.split('\n')
                for i in range(len(lines) - 1, -1, -1):
                    if lines[i].strip() == '}':
                        lines.insert(i, function_code)
                        break
                modified_content = '\n'.join(lines)
        
        elif modification_type == "replace_function":
            function_name = modification_data.get("function_name")
            new_function_code = modification_data.get("new_function_code")
            if function_name and new_function_code:
                import re
                pattern = rf'function\s+{function_name}\s*\([^)]*\)\s*[^{{]*\{{[^}}]*\}}'
                modified_content = re.sub(pattern, new_function_code, modified_content, flags=re.DOTALL)
    
    return modified_content


def analyze_contract_artifacts(project_id: str) -> Dict[str, Any]:
    """Analyze contract artifacts for deployment information"""
    try:
        project_manager = get_project_manager()
        project = project_manager.get_project(project_id)
        
        if not project:
            return {
                "success": False,
                "error": f"Project {project_id} not found"
            }
        
        artifacts = project.get_artifacts()
        
        if not artifacts:
            return {
                "success": False,
                "error": "No artifacts found in project"
            }
        
        contract_info = {}
        total_contracts = 0
        
        for artifact in artifacts:
            contract_name = artifact.get('name', 'Unknown')
            abi = artifact.get('abi', [])
            
            constructor_params = []
            for item in abi:
                if item.get('type') == 'constructor':
                    constructor_params = item.get('inputs', [])
                    break
            
            functions = []
            for item in abi:
                if item.get('type') == 'function':
                    functions.append({
                        'name': item.get('name', ''),
                        'inputs': item.get('inputs', []),
                        'stateMutability': item.get('stateMutability', 'nonpayable')
                    })
            
            contract_info[contract_name] = {
                'constructor_params': constructor_params,
                'functions': functions,
                'abi': abi,
                'bytecode': artifact.get('bytecode', ''),
                'path': artifact.get('path', ''),
                'has_constructor': len(constructor_params) > 0,
                'function_count': len(functions)
            }
            total_contracts += 1
        
        analysis_summary = {
            'total_contracts': total_contracts,
            'contracts_with_constructors': sum(1 for info in contract_info.values() if info['has_constructor']),
            'total_functions': sum(info['function_count'] for info in contract_info.values()),
            'contract_names': list(contract_info.keys())
        }
        
        return {
            "success": True,
            "contracts": contract_info,
            "total_contracts": total_contracts,
            "analysis_summary": analysis_summary
        }
        
    except Exception as e:
        logger.error(f"Error analyzing contract artifacts: {e}")
        return {
            "success": False,
            "error": str(e)
        }


_project_manager = ProjectManager()
def get_project_manager() -> ProjectManager:
    """Get global project manager"""
    return _project_manager



