
import subprocess
import json
import os
import hashlib
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import logging
import time
import re

logger = logging.getLogger(__name__)


class BuildToolchain(Enum):
    """Supported build toolchains"""
    FOUNDRY = "foundry"
    UNKNOWN = "unknown"


@dataclass
class BuildConfig:
    """Build configuration"""
    toolchain: BuildToolchain
    solc_version: str
    source_dir: str
    output_dir: str
    cache_enabled: bool = True
    optimization_enabled: bool = True
    optimizer_runs: int = 200
    evm_version: str = "london"
    
    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result['toolchain'] = self.toolchain.value
        return result


@dataclass
class CompilationResult:
    """Compilation result"""
    success: bool
    artifacts: List[Dict[str, Any]]
    solc_version: str
    compilation_time: float
    errors: List[str]
    warnings: List[str]
    gas_report: Optional[Dict[str, Any]] = None
    coverage: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ScriptRunResult:
    """Result of running a Foundry script"""
    success: bool
    return_code: int
    stdout: str
    stderr: str
    rpc_url: str
    broadcast: bool
    transaction_type: str
    script_target: str
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TestResult:
    """Result of running tests"""
    success: bool
    return_code: int
    stdout: str
    stderr: str
    duration: float
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ArtifactCache:
    """Artifact cache entry"""
    hash: str
    timestamp: float
    artifacts: List[Dict[str, Any]]
    solc_version: str
    build_config: Dict[str, Any]


class BuildManager:
    """Manages build processes and toolchain detection"""
    
    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root).resolve()
        self.cache_dir = self.project_root / ".build_cache"
        self.cache_dir.mkdir(exist_ok=True)
        
        self.toolchain_patterns = {
            BuildToolchain.FOUNDRY: [
                "foundry.toml",
                "forge.toml",
                "lib/",
                "script/",
                "test/"
            ]
        }
    
    def detect_toolchain(self) -> BuildToolchain:
        """Auto-detect build toolchain (Foundry only)"""
        logger.info("Detecting build toolchain...")
        
        if self._check_toolchain_patterns(BuildToolchain.FOUNDRY):
            logger.info("Foundry toolchain detected")
            return BuildToolchain.FOUNDRY
        
        logger.warning("No supported toolchain detected")
        return BuildToolchain.UNKNOWN
    
    def _check_toolchain_patterns(self, toolchain: BuildToolchain) -> bool:
        """Check if toolchain patterns exist in project"""
        patterns = self.toolchain_patterns[toolchain]
        found_patterns = 0
        
        for pattern in patterns:
            if (self.project_root / pattern).exists():
                found_patterns += 1
        
        return found_patterns >= 2
    
    def get_solc_version(self) -> Optional[str]:
        """Get current solc version from solc-select"""
        try:
            result = subprocess.run(
                ["solc-select", "current"],
                capture_output=True,
                text=True,
                cwd=self.project_root
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                logger.info(f"Current solc version: {version}")
                return version
        except FileNotFoundError:
            logger.warning("solc-select not found")
        except Exception as e:
            logger.error(f"Error getting solc version: {e}")
        return None
    
    def set_solc_version(self, version: str) -> bool:
        """Set solc version using solc-select"""
        try:
            logger.info(f"Setting solc version to {version}")
            result = subprocess.run(
                ["solc-select", "install", version],
                capture_output=True,
                text=True,
                cwd=self.project_root
            )
            if result.returncode != 0:
                logger.error(f"Failed to install solc {version}: {result.stderr}")
                return False
            
            result = subprocess.run(
                ["solc-select", "use", version],
                capture_output=True,
                text=True,
                cwd=self.project_root
            )
            if result.returncode == 0:
                logger.info(f"Successfully set solc version to {version}")
                return True
            else:
                logger.error(f"Failed to set solc version: {result.stderr}")
                return False
        except FileNotFoundError:
            logger.error("solc-select not found")
            return False
        except Exception as e:
            logger.error(f"Error setting solc version: {e}")
            return False
    
    def get_available_solc_versions(self) -> List[str]:
        """Get list of available solc versions"""
        try:
            result = subprocess.run(
                ["solc-select", "versions"],
                capture_output=True,
                text=True,
                cwd=self.project_root
            )
            if result.returncode == 0:
                versions = result.stdout.strip().split('\n')
                return [v.strip() for v in versions if v.strip()]
        except Exception as e:
            logger.error(f"Error getting solc versions: {e}")
        return []
    
    def _calculate_source_hash(self, source_files: List[Path]) -> str:
        """Calculate hash of source files for caching"""
        hasher = hashlib.sha256()
        
        for file_path in sorted(source_files):
            if file_path.exists():
                hasher.update(str(file_path).encode())
                hasher.update(file_path.read_bytes())
        
        return hasher.hexdigest()
    
    def _get_cache_key(self, config: BuildConfig, source_files: List[Path]) -> str:
        """Generate cache key for build configuration and sources"""
        source_hash = self._calculate_source_hash(source_files)
        config_str = json.dumps(config.to_dict(), sort_keys=True)
        return hashlib.sha256(f"{config_str}:{source_hash}".encode()).hexdigest()
    
    def _load_from_cache(self, cache_key: str) -> Optional[CompilationResult]:
        """Load compilation result from cache"""
        cache_file = self.cache_dir / f"{cache_key}.json"
        
        if not cache_file.exists():
            return None
        
        try:
            with open(cache_file, 'r') as f:
                cache_data = json.load(f)
            
            if time.time() - cache_data['timestamp'] > 86400:
                logger.info("Cache expired, removing")
                cache_file.unlink()
                return None
            
            logger.info("Using cached compilation result")
            return CompilationResult(**cache_data['result'])
        except Exception as e:
            logger.error(f"Error loading from cache: {e}")
            return None
    
    def run_script(
        self,
        script_path: str = "script/Deploy.s.sol",
        rpc_url: str = "http://localhost:8545",
        private_key: Optional[str] = None,
        broadcast: bool = True,
        transaction_type: str = "1559",
        extra_args: Optional[List[str]] = None,
    ) -> ScriptRunResult:
        """
        Run a Foundry script using `forge script`.
        
        Args:
            script_path: Path to script file, relative to project root, e.g. "script/Deploy.s.sol"
            rpc_url: RPC endpoint
            private_key: Private key for signing txs (optional)
            broadcast: Whether to add `--broadcast`
            transaction_type: "legacy" or "1559"
            extra_args: Extra CLI args to append (e.g. ["--verify", ...])
        """
        start_time = time.time()
        
        toolchain = self.detect_toolchain()
        if toolchain != BuildToolchain.FOUNDRY:
            return ScriptRunResult(
                success=False,
                return_code=1,
                stdout="",
                stderr=f"Unsupported toolchain for scripts: {toolchain.value}",
                rpc_url=rpc_url,
                broadcast=broadcast,
                transaction_type=transaction_type,
                script_target="",
            )
        
        script_full_path = (self.project_root / script_path).resolve()
        if not script_full_path.exists():
            return ScriptRunResult(
                success=False,
                return_code=1,
                stdout="",
                stderr=f"Script not found: {script_path}",
                rpc_url=rpc_url,
                broadcast=broadcast,
                transaction_type=transaction_type,
                script_target="",
            )
        
        script_target = str(script_full_path.relative_to(self.project_root))
        contract_name = script_full_path.stem.replace(".s", "")
        script_target_with_contract = f"{script_target}:{contract_name}"
        
        cmd = ["forge", "script", script_target_with_contract, "--rpc-url", rpc_url]
        
        if broadcast:
            cmd.append("--broadcast")
        
        if private_key:
            cmd.extend(["--private-key", private_key])
        
        if transaction_type == "legacy":
            cmd.append("--legacy")
        elif transaction_type == "1559":
            cmd.append("--with-gas-price")
        
        if extra_args:
            cmd.extend(extra_args)
        
        cmd.append("-vvv")
        
        try:
            logger.info(f"Running script: {' '.join(cmd[:10])}... (truncated)")
            
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=300,
            )
            
            duration = time.time() - start_time
            logger.info(f"Script finished with code {result.returncode} in {duration:.2f}s")
            
            return ScriptRunResult(
                success=result.returncode == 0,
                return_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                rpc_url=rpc_url,
                broadcast=broadcast,
                transaction_type=transaction_type,
                script_target=script_target_with_contract,
            )
        
        except subprocess.TimeoutExpired:
            return ScriptRunResult(
                success=False,
                return_code=124,
                stdout="",
                stderr="Script timeout (exceeded 5 minutes)",
                rpc_url=rpc_url,
                broadcast=broadcast,
                transaction_type=transaction_type,
                script_target=script_target_with_contract,
            )
        
        except Exception as e:
            return ScriptRunResult(
                success=False,
                return_code=1,
                stdout="",
                stderr=str(e),
                rpc_url=rpc_url,
                broadcast=broadcast,
                transaction_type=transaction_type,
                script_target=script_target_with_contract,
            )
    
    def _save_to_cache(self, cache_key: str, result: CompilationResult, config: BuildConfig):
        """Save compilation result to cache"""
        if not config.cache_enabled:
            return
        
        cache_file = self.cache_dir / f"{cache_key}.json"
        
        try:
            cache_data = {
                'timestamp': time.time(),
                'result': result.to_dict(),
                'config': config.to_dict()
            }
            
            with open(cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)
            
            logger.info(f"Cached compilation result: {cache_file}")
        except Exception as e:
            logger.error(f"Error saving to cache: {e}")
    
    def find_source_files(self, toolchain: BuildToolchain) -> List[Path]:
        """Find source files based on toolchain (Foundry only)"""
        source_files = []
        
        for sol_file in self.project_root.rglob("*.sol"):
            relative_path = str(sol_file.relative_to(self.project_root))
            if "out/" not in relative_path:
                source_files.append(sol_file)
        
        source_files = sorted(source_files)
        logger.info(f"Found {len(source_files)} source files")
        
        return source_files
    
    def normalize_path(self, path: Path) -> str:
        """Normalize path for consistent handling"""
        return str(path.relative_to(self.project_root))
    
    def normalize_abi(self, abi: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalize ABI for consistent processing"""
        normalized = []
        
        for item in abi:
            normalized_item = item.copy()
            
            if 'type' in normalized_item:
                normalized_item['type'] = normalized_item['type'].lower()
            
            if normalized_item.get('type') == 'function':
                if 'inputs' in normalized_item:
                    normalized_item['inputs'] = sorted(
                        normalized_item['inputs'],
                        key=lambda x: x.get('name', '')
                    )
            
            normalized.append(normalized_item)
        
        return normalized
    
    def compile_foundry(self, config: BuildConfig) -> CompilationResult:
        """Compile using Foundry"""
        logger.info("Compiling with Foundry...")
        start_time = time.time()
        
        try:
            result = subprocess.run(
                ["forge", "build"],
                capture_output=True,
                text=True,
                cwd=self.project_root
            )
            
            compilation_time = time.time() - start_time
            
            if result.returncode != 0:
                return CompilationResult(
                    success=False,
                    artifacts=[],
                    solc_version=config.solc_version,
                    compilation_time=compilation_time,
                    errors=[result.stderr],
                    warnings=[]
                )
            
            artifacts = self._parse_foundry_artifacts()
            
            return CompilationResult(
                success=True,
                artifacts=artifacts,
                solc_version=config.solc_version,
                compilation_time=compilation_time,
                errors=[],
                warnings=[]
            )
            
        except Exception as e:
            logger.error(f"Error compiling with Foundry: {e}")
            return CompilationResult(
                success=False,
                artifacts=[],
                solc_version=config.solc_version,
                compilation_time=time.time() - start_time,
                errors=[str(e)],
                warnings=[]
            )
    
    
    def _parse_foundry_artifacts(self) -> List[Dict[str, Any]]:
        """Parse Foundry artifacts from out/ directory"""
        artifacts = []
        out_dir = self.project_root / "out"
        
        if not out_dir.exists():
            return artifacts
        
        for artifact_file in out_dir.rglob("*.json"):
            try:
                with open(artifact_file, 'r') as f:
                    artifact_data = json.load(f)
                
                if 'abi' in artifact_data and 'bytecode' in artifact_data:
                    contract_name = self._extract_contract_name(artifact_file, artifact_data)
                    
                    artifact = {
                        'name': contract_name,
                        'path': self.normalize_path(artifact_file),
                        'abi': self.normalize_abi(artifact_data['abi']),
                        'bytecode': artifact_data['bytecode'],
                        'deployedBytecode': artifact_data.get('deployedBytecode', ''),
                        'sourceMap': artifact_data.get('sourceMap', ''),
                        'metadata': artifact_data.get('metadata', {})
                    }
                    artifacts.append(artifact)
            except Exception as e:
                logger.warning(f"Error parsing artifact {artifact_file}: {e}")
        
        return artifacts
    
    def _extract_contract_name(self, artifact_file: Path, artifact_data: Dict[str, Any]) -> str:
        """Extract contract name from Foundry artifact"""
        if 'contractName' in artifact_data:
            return artifact_data['contractName']
        
        metadata = artifact_data.get('metadata', {})
        settings = metadata.get('settings', {})
        compilation_target = settings.get('compilationTarget', {})
        
        if compilation_target:
            for file_path, contract_name in compilation_target.items():
                if contract_name and contract_name != 'Unknown':
                    return contract_name
        
        file_path_parts = artifact_file.parts
        if len(file_path_parts) >= 3:
            dir_name = file_path_parts[-2]
            if dir_name.endswith('.sol'):
                contract_name = dir_name[:-4]
                if contract_name and contract_name != 'Unknown':
                    return contract_name
        
        filename = artifact_file.stem
        if filename and filename != 'Unknown':
            return filename
        
        abi = artifact_data.get('abi', [])
        for item in abi:
            if item.get('type') == 'constructor':
                pass
        
        return artifact_file.stem if artifact_file.stem else 'Unknown'
    
    
    def compile(self, config: Optional[BuildConfig] = None) -> CompilationResult:
        """Main compilation method with caching"""
        if config is None:
            toolchain = self.detect_toolchain()
            solc_version = self.get_solc_version() or "0.8.19"
            
            config = BuildConfig(
                toolchain=toolchain,
                solc_version=solc_version,
                source_dir="src" if toolchain == BuildToolchain.FOUNDRY else "contracts",
                output_dir="out" if toolchain == BuildToolchain.FOUNDRY else "artifacts"
            )
        
        source_files = self.find_source_files(config.toolchain)
        
        if not source_files:
            return CompilationResult(
                success=False,
                artifacts=[],
                solc_version=config.solc_version,
                compilation_time=0.0,
                errors=["No source files found"],
                warnings=[]
            )
        
        cache_key = self._get_cache_key(config, source_files)
        cached_result = self._load_from_cache(cache_key)
        if cached_result:
            return cached_result
        
        if config.toolchain == BuildToolchain.FOUNDRY:
            result = self.compile_foundry(config)
        else:
            result = CompilationResult(
                success=False,
                artifacts=[],
                solc_version=config.solc_version,
                compilation_time=0.0,
                errors=[f"Unsupported toolchain: {config.toolchain.value}"],
                warnings=[]
            )
        
        if result.success:
            self._save_to_cache(cache_key, result, config)
        
        return result
    
    def clean_cache(self):
        """Clean build cache"""
        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
            self.cache_dir.mkdir()
            logger.info("Build cache cleaned")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        if not self.cache_dir.exists():
            return {"files": 0, "size": 0}
        
        files = list(self.cache_dir.glob("*.json"))
        total_size = sum(f.stat().st_size for f in files)
        
        return {
            "files": len(files),
            "size": total_size,
            "size_mb": round(total_size / 1024 / 1024, 2)
        }
    
    def run_tests(
        self,
        pattern: Optional[str] = None,
        toolchain: Optional[BuildToolchain] = None,
        extra_args: Optional[List[str]] = None
    ) -> TestResult:
        """
        Run tests for the project.
        
        For Foundry:
        - uses `forge test`
        - optional `pattern` passed as `-m pattern` (to filter by test name)
        - optional `extra_args` for additional flags (e.g., ["--ffi", "-vvv", "--match-path", "test/MyTest.t.sol"])
        
        Args:
            pattern: Test name pattern to filter (passed as `-m pattern`)
            toolchain: Build toolchain (auto-detected if not provided)
            extra_args: Extra CLI args to append (e.g., ["--ffi", "-vvv", "--match-contract", "MyTest"])
        """
        start_time = time.time()
        
        # Auto-detect toolchain if not provided
        if toolchain is None:
            toolchain = self.detect_toolchain()
        
        if toolchain != BuildToolchain.FOUNDRY:
            return TestResult(
                success=False,
                return_code=1,
                stdout="",
                stderr=f"Unsupported toolchain for tests: {toolchain.value}",
                duration=0.0,
            )
        
        cmd = ["forge", "test"]
        
        if pattern:
            cmd.extend(["-m", pattern])
        
        if extra_args:
            cmd.extend(extra_args)
        
        try:
            logger.info(f"Running tests: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=300,
            )
            
            duration = time.time() - start_time
            
            return TestResult(
                success=result.returncode == 0,
                return_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                duration=duration,
            )
        
        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            return TestResult(
                success=False,
                return_code=124,
                stdout="",
                stderr="Tests timeout (exceeded 5 minutes)",
                duration=duration,
            )
        
        except Exception as e:
            duration = time.time() - start_time
            return TestResult(
                success=False,
                return_code=1,
                stdout="",
                stderr=str(e),
                duration=duration,
            )


def detect_toolchain(project_root: str = ".") -> BuildToolchain:
    """Detect build toolchain for a project directory"""
    build_manager = BuildManager(project_root)
    return build_manager.detect_toolchain()


def compile_project(config: Optional[BuildConfig] = None, project_root: str = ".") -> CompilationResult:
    """Compile project with auto-detection"""
    build_manager = BuildManager(project_root)
    return build_manager.compile(config)


def get_solc_version(project_root: str = ".") -> Optional[str]:
    """Get current solc version"""
    build_manager = BuildManager(project_root)
    return build_manager.get_solc_version()


def set_solc_version(version: str, project_root: str = ".") -> bool:
    """Set solc version"""
    build_manager = BuildManager(project_root)
    return build_manager.set_solc_version(version)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("=== Build Manager Test ===")
    
    toolchain = detect_toolchain()
    print(f"Detected toolchain: {toolchain.value}")
    
    solc_version = get_solc_version()
    print(f"Current solc version: {solc_version}")
    
    result = compile_project()
    print(f"Compilation success: {result.success}")
    print(f"Artifacts: {len(result.artifacts)}")
    print(f"Compilation time: {result.compilation_time:.2f}s")
    
    if result.errors:
        print(f"Errors: {result.errors}")
    
    build_manager = BuildManager()
    cache_stats = build_manager.get_cache_stats()
    print(f"Cache stats: {cache_stats}")
