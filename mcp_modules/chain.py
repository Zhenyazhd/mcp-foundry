"""
Chain Management Module

Модуль для управления Anvil локальными блокчейнами.
Поддерживает devnet и fork режимы с автоматическим управлением портами и процессами.
"""

import subprocess
import time
import logging
import json
import requests
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass, field
from enum import Enum
from contextlib import contextmanager
import psutil
import socket

logger = logging.getLogger(__name__)


class AnvilMode(Enum):
    """Anvil operation modes"""
    DEVNET = "devnet"
    FORK = "fork"


@dataclass
class AnvilConfig:
    """Configuration for Anvil instance"""
    mode: AnvilMode = AnvilMode.DEVNET
    port: int = 8545
    chain_id: int = 31337
    host: str = "127.0.0.1"
    
    # Fork-specific settings
    fork_url: Optional[str] = None
    fork_block_number: Optional[int] = None
    
    # Devnet settings
    accounts: int = 10
    balance: int = 10000  # ETH balance per account
    gas_limit: int = 30000000
    gas_price: int = 0  # 0 for EIP-1559
    
    # Advanced settings
    block_time: Optional[int] = None  # Seconds between blocks (None for instant)
    timestamp: Optional[int] = None  # Initial timestamp
    code_size_limit: int = 24576  # Max contract code size
    
    # Security settings
    allow_unlimited_contract_size: bool = False
    allow_paths: Optional[List[str]] = None
    
    # Logging
    verbosity: int = 2  # 0-4, higher = more verbose
    
    # Process management
    auto_start: bool = True
    auto_cleanup: bool = True
    
    def __post_init__(self):
        """Validate configuration after initialization"""
        if self.mode == AnvilMode.FORK and not self.fork_url:
            raise ValueError("Fork mode requires fork_url to be specified")
        
        if self.port < 1024 or self.port > 65535:
            raise ValueError(f"Port {self.port} is not valid (1024-65535)")
        
        if self.chain_id < 1:
            raise ValueError(f"Chain ID {self.chain_id} must be positive")


@dataclass
class AnvilMetrics:
    """Metrics for Anvil instance"""
    startup_time: float = 0.0
    uptime: float = 0.0
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    blocks_mined: int = 0
    transactions_processed: int = 0
    gas_used: int = 0
    last_block_time: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "startup_time": self.startup_time,
            "uptime": self.uptime,
            "cpu_usage": self.cpu_usage,
            "memory_usage": self.memory_usage,
            "blocks_mined": self.blocks_mined,
            "transactions_processed": self.transactions_processed,
            "gas_used": self.gas_used,
            "last_block_time": self.last_block_time
        }


class AnvilWrapper:
    """Wrapper for managing Anvil process"""
    
    def __init__(self, config: AnvilConfig):
        self.config = config
        self.process: Optional[subprocess.Popen] = None
        self.metrics = AnvilMetrics()
        self.start_time: Optional[float] = None
        self.snapshots: Dict[str, str] = {}  # name -> snapshot_id
        self._lock = threading.Lock()
        
    def _is_port_available(self, port: int) -> bool:
        """Check if port is available"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1', port))
                return True
        except OSError:
            return False
    
    def _find_available_port(self, start_port: int = 8545) -> int:
        """Find an available port starting from start_port"""
        port = start_port
        while port < start_port + 1000:  # Search up to 1000 ports
            if self._is_port_available(port):
                return port
            port += 1
        raise RuntimeError(f"No available ports found starting from {start_port}")
    
    def _build_command(self) -> List[str]:
        """Build Anvil command line arguments"""
        cmd = ["anvil"]
        
        # Basic settings
        cmd.extend(["--port", str(self.config.port)])
        cmd.extend(["--chain-id", str(self.config.chain_id)])
        cmd.extend(["--host", self.config.host])
        
        # Account settings
        cmd.extend(["--accounts", str(self.config.accounts)])
        cmd.extend(["--balance", str(self.config.balance)])
        
        # Gas settings
        cmd.extend(["--gas-limit", str(self.config.gas_limit)])
        if self.config.gas_price > 0:
            cmd.extend(["--gas-price", str(self.config.gas_price)])
        
        # Fork settings
        if self.config.mode == AnvilMode.FORK:
            cmd.extend(["--fork-url", self.config.fork_url])
            if self.config.fork_block_number:
                cmd.extend(["--fork-block-number", str(self.config.fork_block_number)])
        
        # Block time
        if self.config.block_time:
            cmd.extend(["--block-time", str(self.config.block_time)])
        
        # Timestamp
        if self.config.timestamp:
            cmd.extend(["--timestamp", str(self.config.timestamp)])
        
        # Code size limit
        cmd.extend(["--code-size-limit", str(self.config.code_size_limit)])
        
        # Security settings
        if self.config.allow_unlimited_contract_size:
            cmd.append("--allow-unlimited-contract-size")
        
        if self.config.allow_paths:
            for path in self.config.allow_paths:
                cmd.extend(["--allow-path", path])
        
        # Verbosity (Anvil uses -v flag multiple times)
        if self.config.verbosity > 0:
            for _ in range(min(self.config.verbosity, 5)):  # Max 5 verbosity levels
                cmd.append("-v")
        
        return cmd
    
    def start(self) -> bool:
        """Start Anvil process"""
        with self._lock:
            if self.process and self.process.poll() is None:
                logger.warning("Anvil is already running")
                return True
            
            # Find available port if current one is taken
            if not self._is_port_available(self.config.port):
                self.config.port = self._find_available_port(self.config.port)
                logger.info(f"Port {self.config.port} was busy, using port {self.config.port}")
            
            try:
                cmd = self._build_command()
                logger.info(f"Starting Anvil with command: {' '.join(cmd)}")
                
                self.start_time = time.time()
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    universal_newlines=True
                )
                
                # Wait for Anvil to start
                if self._wait_for_startup():
                    self.metrics.startup_time = time.time() - self.start_time
                    logger.info(f"Anvil started successfully on port {self.config.port}")
                    return True
                else:
                    logger.error("Anvil failed to start")
                    self.stop()
                    return False
                    
            except Exception as e:
                logger.error(f"Error starting Anvil: {e}")
                return False
    
    def _wait_for_startup(self, timeout: int = 30) -> bool:
        """Wait for Anvil to start up"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if self.process.poll() is not None:
                # Process has terminated
                stdout, stderr = self.process.communicate()
                logger.error(f"Anvil process terminated: stdout={stdout}, stderr={stderr}")
                return False
            
            # Check if RPC endpoint is responding
            try:
                response = requests.post(
                    f"http://{self.config.host}:{self.config.port}",
                    json={"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1},
                    timeout=1
                )
                if response.status_code == 200:
                    return True
            except requests.RequestException:
                pass
            
            time.sleep(0.5)
        
        logger.error(f"Anvil startup timeout after {timeout} seconds")
        return False
    
    def stop(self) -> bool:
        """Stop Anvil process"""
        with self._lock:
            if not self.process or self.process.poll() is not None:
                logger.warning("Anvil is not running")
                return True
            
            try:
                logger.info("Stopping Anvil process")
                self.process.terminate()
                
                # Wait for graceful shutdown
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    logger.warning("Anvil didn't stop gracefully, forcing kill")
                    self.process.kill()
                    self.process.wait()
                
                self.process = None
                self.start_time = None
                self.snapshots.clear()
                
                logger.info("Anvil stopped successfully")
                return True
                
            except Exception as e:
                logger.error(f"Error stopping Anvil: {e}")
                return False
    
    def is_running(self) -> bool:
        """Check if Anvil is running"""
        return self.process is not None and self.process.poll() is None
    
    def get_rpc_url(self) -> str:
        """Get RPC URL for this Anvil instance"""
        return f"http://{self.config.host}:{self.config.port}"
    
    def make_request(self, method: str, params: List[Any] = None) -> Dict[str, Any]:
        """Make JSON-RPC request to Anvil"""
        if not self.is_running():
            raise RuntimeError("Anvil is not running")
        
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or [],
            "id": 1
        }
        
        try:
            response = requests.post(
                self.get_rpc_url(),
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise RuntimeError(f"RPC request failed: {e}")
    
    def snapshot(self, name: Optional[str] = None) -> str:
        """Create a snapshot of current state"""
        if not self.is_running():
            raise RuntimeError("Anvil is not running")
        
        try:
            result = self.make_request("evm_snapshot")
            snapshot_id = result.get("result")
            
            if snapshot_id:
                if name:
                    self.snapshots[name] = snapshot_id
                logger.info(f"Snapshot created: {snapshot_id}")
                return snapshot_id
            else:
                raise RuntimeError("Failed to create snapshot")
                
        except Exception as e:
            logger.error(f"Error creating snapshot: {e}")
            raise
    
    def revert(self, snapshot_id: str) -> bool:
        """Revert to a snapshot"""
        if not self.is_running():
            raise RuntimeError("Anvil is not running")
        
        try:
            result = self.make_request("evm_revert", [snapshot_id])
            success = result.get("result", False)
            
            if success:
                logger.info(f"Reverted to snapshot: {snapshot_id}")
                return True
            else:
                logger.error(f"Failed to revert to snapshot: {snapshot_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error reverting snapshot: {e}")
            return False
    
    def revert_by_name(self, name: str) -> bool:
        """Revert to a snapshot by name"""
        if name not in self.snapshots:
            raise ValueError(f"Snapshot '{name}' not found")
        
        return self.revert(self.snapshots[name])
    
    def advance_time(self, seconds: int) -> bool:
        """Advance blockchain time by seconds"""
        if not self.is_running():
            raise RuntimeError("Anvil is not running")
        
        try:
            result = self.make_request("evm_increaseTime", [seconds])
            success = result.get("result") is not None
            
            if success:
                logger.info(f"Advanced time by {seconds} seconds")
                return True
            else:
                logger.error(f"Failed to advance time by {seconds} seconds")
                return False
                
        except Exception as e:
            logger.error(f"Error advancing time: {e}")
            return False
    
    def advance_block(self) -> bool:
        """Advance to next block"""
        if not self.is_running():
            raise RuntimeError("Anvil is not running")
        
        try:
            result = self.make_request("evm_mine")
            success = result.get("result") is not None
            
            if success:
                self.metrics.blocks_mined += 1
                logger.info("Advanced to next block")
                return True
            else:
                logger.error("Failed to advance block")
                return False
                
        except Exception as e:
            logger.error(f"Error advancing block: {e}")
            return False
    
    def set_balance(self, address: str, balance: int) -> bool:
        """Set balance for an address (in wei)"""
        if not self.is_running():
            raise RuntimeError("Anvil is not running")
        
        try:
            result = self.make_request("anvil_setBalance", [address, hex(balance)])
            success = result.get("result") is not None
            
            if success:
                logger.info(f"Set balance for {address} to {balance} wei")
                return True
            else:
                logger.error(f"Failed to set balance for {address}")
                return False
                
        except Exception as e:
            logger.error(f"Error setting balance: {e}")
            return False
    
    def impersonate_account(self, address: str) -> bool:
        """Impersonate an account for testing"""
        if not self.is_running():
            raise RuntimeError("Anvil is not running")
        
        try:
            result = self.make_request("anvil_impersonateAccount", [address])
            success = result.get("result") is not None
            
            if success:
                logger.info(f"Impersonating account: {address}")
                return True
            else:
                logger.error(f"Failed to impersonate account: {address}")
                return False
                
        except Exception as e:
            logger.error(f"Error impersonating account: {e}")
            return False
    
    def stop_impersonating(self, address: str) -> bool:
        """Stop impersonating an account"""
        if not self.is_running():
            raise RuntimeError("Anvil is not running")
        
        try:
            result = self.make_request("anvil_stopImpersonatingAccount", [address])
            success = result.get("result") is not None
            
            if success:
                logger.info(f"Stopped impersonating account: {address}")
                return True
            else:
                logger.error(f"Failed to stop impersonating account: {address}")
                return False
                
        except Exception as e:
            logger.error(f"Error stopping impersonation: {e}")
            return False
    
    def get_metrics(self) -> AnvilMetrics:
        """Get current metrics"""
        if self.start_time:
            self.metrics.uptime = time.time() - self.start_time
        
        if self.process and self.process.poll() is None:
            try:
                process = psutil.Process(self.process.pid)
                self.metrics.cpu_usage = process.cpu_percent()
                self.metrics.memory_usage = process.memory_info().rss / 1024 / 1024  # MB
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        return self.metrics
    
    def get_accounts(self) -> List[Dict[str, Any]]:
        """Get list of available accounts"""
        if not self.is_running():
            raise RuntimeError("Anvil is not running")
        
        try:
            result = self.make_request("eth_accounts")
            accounts = result.get("result", [])
            
            account_info = []
            for account in accounts:
                balance_result = self.make_request("eth_getBalance", [account, "latest"])
                balance = int(balance_result.get("result", "0x0"), 16)
                
                account_info.append({
                    "address": account,
                    "balance": balance,
                    "balance_eth": balance / 10**18
                })
            
            return account_info
            
        except Exception as e:
            logger.error(f"Error getting accounts: {e}")
            return []
    
    def get_latest_block(self) -> Dict[str, Any]:
        """Get latest block information"""
        if not self.is_running():
            raise RuntimeError("Anvil is not running")
        
        try:
            result = self.make_request("eth_getBlockByNumber", ["latest", False])
            return result.get("result", {})
        except Exception as e:
            logger.error(f"Error getting latest block: {e}")
            return {}


@contextmanager
def anvil_context(config: AnvilConfig):
    """Context manager for automatic Anvil lifecycle management"""
    wrapper = AnvilWrapper(config)
    
    try:
        if config.auto_start:
            if not wrapper.start():
                raise RuntimeError("Failed to start Anvil")
        
        yield wrapper
        
    finally:
        if config.auto_cleanup:
            wrapper.stop()


class AnvilManager:
    """Manager for multiple Anvil instances"""
    
    def __init__(self):
        self.instances: Dict[str, AnvilWrapper] = {}
        self._lock = threading.Lock()
    
    def create_instance(self, name: str, config: AnvilConfig) -> AnvilWrapper:
        """Create a new Anvil instance"""
        with self._lock:
            if name in self.instances:
                raise ValueError(f"Instance '{name}' already exists")
            
            wrapper = AnvilWrapper(config)
            self.instances[name] = wrapper
            return wrapper
    
    def get_instance(self, name: str) -> Optional[AnvilWrapper]:
        """Get an Anvil instance by name"""
        return self.instances.get(name)
    
    def remove_instance(self, name: str) -> bool:
        """Remove an Anvil instance"""
        with self._lock:
            if name not in self.instances:
                return False
            
            wrapper = self.instances[name]
            wrapper.stop()
            del self.instances[name]
            return True
    
    def list_instances(self) -> List[str]:
        """List all instance names"""
        return list(self.instances.keys())
    
    def cleanup_all(self):
        """Stop and remove all instances"""
        with self._lock:
            for wrapper in self.instances.values():
                wrapper.stop()
            self.instances.clear()


# Global manager instance
_anvil_manager = AnvilManager()


def get_anvil_manager() -> AnvilManager:
    """Get the global Anvil manager instance"""
    return _anvil_manager


def create_devnet(port: int = 8545, chain_id: int = 31337) -> AnvilWrapper:
    """Create a devnet Anvil instance"""
    config = AnvilConfig(
        mode=AnvilMode.DEVNET,
        port=port,
        chain_id=chain_id
    )
    return AnvilWrapper(config)


def create_fork(fork_url: str, port: int = 8545, chain_id: int = 31337, 
                fork_block_number: Optional[int] = None) -> AnvilWrapper:
    """Create a fork Anvil instance"""
    config = AnvilConfig(
        mode=AnvilMode.FORK,
        port=port,
        chain_id=chain_id,
        fork_url=fork_url,
        fork_block_number=fork_block_number
    )
    return AnvilWrapper(config)
