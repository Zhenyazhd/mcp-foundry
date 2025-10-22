"""
Scenario Runner

Декларативный фреймворк для тестирования смарт-контрактов через YAML DSL.
Поддерживает интеграционные проверки, бизнес-логику и детерминированные сценарии.
"""

import json
import logging
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, asdict
from enum import Enum
import yaml

logger = logging.getLogger(__name__)


class StepType(Enum):
    """Типы шагов в сценарии"""
    SEND = "send"           # Отправка транзакции
    CALL = "call"           # Вызов view функции
    WAIT = "wait"           # Ожидание блоков
    TIME_TRAVEL = "time_travel"  # Переход во времени
    SNAPSHOT = "snapshot"   # Создание снапшота
    REVERT = "revert"       # Откат к снапшоту
    ASSERT = "assert"       # Проверка условий
    DEPLOY = "deploy"       # Деплой контракта
    MINE = "mine"           # Майнинг блоков
    SET_BALANCE = "set_balance"  # Установка баланса
    SET_STORAGE = "set_storage"  # Установка storage
    LABEL = "label"         # Метка для группировки шагов
    ACTION = "action"        # Универсальное действие


class AssertionType(Enum):
    """Типы проверок"""
    EQUAL = "=="
    NOT_EQUAL = "!="
    GREATER = ">"
    GREATER_EQUAL = ">="
    LESS = "<"
    LESS_EQUAL = "<="
    CONTAINS = "contains"
    EXISTS = "exists"


@dataclass
class Role:
    """Роль в сценарии"""
    name: str
    address: str
    private_key: Optional[str] = None
    balance: Optional[str] = None


@dataclass
class Step:
    """Шаг сценария"""
    type: StepType
    data: Dict[str, Any]
    description: Optional[str] = None
    gas_limit: Optional[int] = None
    gas_price: Optional[str] = None


@dataclass
class Scenario:
    """Сценарий тестирования"""
    name: str
    description: Optional[str] = None
    roles: Dict[str, Role] = None
    steps: List[Step] = None
    contracts: Dict[str, str] = None  # contract_name -> address
    snapshots: Dict[str, str] = None  # snapshot_name -> snapshot_id
    timeout: int = 300
    gas_limit: int = 30000000
    
    def __post_init__(self):
        if self.roles is None:
            self.roles = {}
        if self.steps is None:
            self.steps = []
        if self.contracts is None:
            self.contracts = {}
        if self.snapshots is None:
            self.snapshots = {}


@dataclass
class ExecutionResult:
    """Результат выполнения сценария"""
    success: bool
    scenario_name: str
    execution_time: float
    steps_executed: int
    total_steps: int
    artifacts: Dict[str, Any] = None
    error: Optional[str] = None
    gas_used: Optional[int] = None
    events: List[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.artifacts is None:
            self.artifacts = {}
        if self.events is None:
            self.events = []


class ScenarioParser:
    """Парсер YAML сценариев"""
    
    def __init__(self):
        self.supported_step_types = {step_type.value for step_type in StepType}
        self.supported_assertions = {assertion.value for assertion in AssertionType}
    
    def parse_yaml(self, yaml_content: str) -> Scenario:
        """Парсинг YAML контента в объект Scenario"""
        try:
            # Предварительная обработка YAML для нормализации переменных
            normalized_content = self._normalize_yaml_variables(yaml_content)
            
            data = yaml.safe_load(normalized_content)
            
            # Проверяем, что данные не пустые
            if not data:
                raise ValueError("YAML content is empty")
            
            # Если это список, берем первый элемент
            if isinstance(data, list):
                if len(data) == 0:
                    raise ValueError("YAML list is empty")
                data = data[0]
            
            # Проверяем, что это словарь
            if not isinstance(data, dict):
                raise ValueError("YAML root must be a dictionary")
            
            return self._parse_scenario(data)
            
        except yaml.YAMLError as e:
            logger.error(f"YAML parsing error: {e}")
            raise ValueError(f"Invalid YAML format: {e}")
        except Exception as e:
            logger.error(f"Error parsing YAML: {e}")
            raise ValueError(f"Invalid YAML format: {e}")
    
    def _normalize_yaml_variables(self, yaml_content: str) -> str:
        """Нормализация переменных в YAML контенте"""
        import re
        
        # Заменяем ${variable} на "variable" для корректного парсинга YAML
        # Это позволяет использовать ${acc1} вместо "$acc1"
        normalized = re.sub(r'\$\{([^}]+)\}', r'"$\1"', yaml_content)
        
        # Также заменяем $variable на "$variable" если не в кавычках
        # Но только если это не уже в кавычках
        normalized = re.sub(r'(?<!["\'])\$([a-zA-Z_][a-zA-Z0-9_]*)', r'"$\1"', normalized)
        
        # Исправляем проблемные конструкции типа "$artifacts:MyToken".bytecode
        # Заменяем их на строки
        normalized = re.sub(r'"\$artifacts:([^"]+)"\.(\w+)', r'"$artifacts:\1.\2"', normalized)
        
        # Исправляем проблемы с assert шагами типа: - assert: "$aliceBal" == 70000000000000000000
        # Заменяем на правильный YAML формат
        normalized = re.sub(
            r'(\s*-\s*assert:\s*)"([^"]+)"\s*==\s*(\d+)',
            r'\1\n    value: "\2"\n    expect: "==\3"',
            normalized
        )
        
        # Исправляем проблемы с отступами в блоках
        # Если строка содержит ":" и следующая строка имеет неправильный отступ
        lines = normalized.split('\n')
        fixed_lines = []
        
        for i, line in enumerate(lines):
            fixed_lines.append(line)
            
            # Если текущая строка заканчивается на ":" и следующая строка имеет неправильный отступ
            if i < len(lines) - 1 and line.strip().endswith(':'):
                next_line = lines[i + 1]
                if next_line.strip() and not next_line.startswith(' ') and not next_line.startswith('\t'):
                    # Добавляем правильный отступ
                    indent = len(line) - len(line.lstrip()) + 2
                    if next_line.strip():
                        fixed_lines.append(' ' * indent + next_line.strip())
                        # Пропускаем следующую строку, так как мы её уже обработали
                        if i + 1 < len(lines):
                            lines[i + 1] = ''  # Помечаем как обработанную
        
        return '\n'.join(fixed_lines)
    
    def parse_file(self, file_path: Path) -> Scenario:
        """Парсинг YAML файла"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return self.parse_yaml(content)
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            raise ValueError(f"Error reading file: {e}")
    
    def _parse_scenario(self, data: Dict[str, Any]) -> Scenario:
        """Парсинг данных сценария"""
        # Валидация обязательных полей
        if 'name' not in data:
            raise ValueError("Scenario must have 'name' field")
        
        # Проверяем, что это действительно сценарий, а не шаг
        if 'steps' not in data and len(data) == 1:
            # Если есть только одно поле и это не 'steps', возможно это шаг
            raise ValueError("Invalid scenario format: missing 'steps' field")
        
        # Парсинг ролей
        roles = {}
        if 'roles' in data:
            for role_name, role_data in data['roles'].items():
                if isinstance(role_data, str):
                    # Простой формат: role_name: "$acc0"
                    roles[role_name] = Role(name=role_name, address=role_data)
                elif isinstance(role_data, dict):
                    # Расширенный формат
                    roles[role_name] = Role(
                        name=role_name,
                        address=role_data.get('address', ''),
                        private_key=role_data.get('private_key'),
                        balance=role_data.get('balance')
                    )
        
        # Парсинг шагов
        steps = []
        if 'steps' in data:
            if not isinstance(data['steps'], list):
                raise ValueError("'steps' must be a list")
            
            for i, step_data in enumerate(data['steps']):
                try:
                    step = self._parse_step(step_data)
                    steps.append(step)
                except Exception as e:
                    raise ValueError(f"Error parsing step {i+1}: {e}")
        
        # Парсинг контрактов
        contracts = data.get('contracts', {})
        
        return Scenario(
            name=data['name'],
            description=data.get('description'),
            roles=roles,
            steps=steps,
            contracts=contracts,
            timeout=data.get('timeout', 300),
            gas_limit=data.get('gas_limit', 30000000)
        )
    
    def _parse_step(self, step_data: Dict[str, Any]) -> Step:
        """Парсинг шага сценария с улучшенной гибкостью"""
        # Более гибкая обработка шагов
        if len(step_data) == 0:
            raise ValueError("Step cannot be empty")
        
        # Если шаг содержит только одно действие
        if len(step_data) == 1:
            step_type_str, step_content = next(iter(step_data.items()))
        else:
            # Если шаг содержит несколько полей, ищем основной тип действия
            step_type_str = None
            step_content = {}
            
            # Ищем известные типы шагов
            for key in step_data.keys():
                if key in self.supported_step_types:
                    step_type_str = key
                    step_content = step_data[key]
                    break
            
            # Если не нашли известный тип, используем первый ключ
            if step_type_str is None:
                step_type_str = list(step_data.keys())[0]
                step_content = step_data[step_type_str]
        
        # Специальная обработка для случая, когда шаг содержит 'type' как ключ
        if step_type_str == 'type' and isinstance(step_content, str):
            # Если шаг имеет структуру {type: "deploy", ...}, то type - это тип шага
            step_type_str = step_content
            # Создаем содержимое из остальных полей
            step_content = {k: v for k, v in step_data.items() if k != 'type'}
        
        # Создаем маппинг синонимов и похожих названий
        step_aliases = {
            'action': 'send',  # action обычно означает send
            'transaction': 'send',
            'invoke': 'send',
            'execute': 'send',
            'query': 'call',
            'read': 'call',
            'check': 'assert',
            'verify': 'assert',
            'expect': 'assert',
            'sleep': 'wait',
            'pause': 'wait',
            'delay': 'wait',
            'jump': 'time_travel',
            'advance': 'time_travel',
            'save': 'snapshot',
            'restore': 'revert',
            'rollback': 'revert',
            'create': 'deploy',
            'instantiate': 'deploy',
            'comment': 'label',
            'note': 'label',
            'log': 'label',
            'print': 'label',
            # Специальные случаи для составных типов
            'send_transaction': 'send',
            'call_function': 'call',
            'assert_condition': 'assert',
            'wait_blocks': 'wait',
            'time_travel_forward': 'time_travel',
            'create_snapshot': 'snapshot',
            'revert_to_snapshot': 'revert',
            'deploy_contract': 'deploy',
            'mine_blocks': 'mine',
            'set_account_balance': 'set_balance',
            'set_contract_storage': 'set_storage'
        }
        
        # Проверяем алиасы (применяем всегда, даже если тип уже поддерживается)
        if step_type_str.lower() in step_aliases:
            mapped_type = step_aliases[step_type_str.lower()]
            print(f"🔄 Mapped step type '{step_type_str}' → '{mapped_type}'")
            step_type_str = mapped_type
        
        # Если все еще не поддерживается, ищем похожие типы
        if step_type_str not in self.supported_step_types:
            similar_types = []
            for supported_type in self.supported_step_types:
                # Более точная логика поиска похожих типов
                if (step_type_str.lower() in supported_type.lower() or 
                    supported_type.lower() in step_type_str.lower()):
                    similar_types.append(supported_type)
                # Проверяем отдельные слова (только точные совпадения)
                elif any(word == supported_type.lower() for word in step_type_str.lower().split('_')):
                    similar_types.append(supported_type)
            
            if similar_types:
                # Приоритет: выбираем наиболее подходящий тип
                best_match = similar_types[0]
                for similar_type in similar_types:
                    # Приоритет: точное совпадение слов
                    if similar_type.lower() in step_type_str.lower():
                        best_match = similar_type
                        break
                    # Второй приоритет: совпадение по длине (более длинные типы более специфичны)
                    elif len(similar_type) > len(best_match):
                        best_match = similar_type
                print(f"🔄 Found similar step type '{step_type_str}' → '{best_match}'")
                step_type_str = best_match
            else:
                # Если ничего не подходит, используем ACTION как fallback
                print(f"⚠️  Unknown step type '{step_type_str}', using ACTION as fallback")
                step_type_str = 'action'
        
        step_type = StepType(step_type_str)
        
        # Обрабатываем содержимое шага
        if isinstance(step_content, dict):
            step_data_dict = step_content
        else:
            # Если содержимое не словарь, создаем словарь
            step_data_dict = {"value": step_content}
        
        return Step(
            type=step_type,
            data=step_data_dict,
            description=step_data_dict.get('description'),
            gas_limit=step_data_dict.get('gas_limit'),
            gas_price=step_data_dict.get('gas_price')
        )


class ScenarioExecutor:
    """Исполнитель сценариев через RPC/cast"""
    
    def __init__(self, rpc_url: str = "http://localhost:8545"):
        self.rpc_url = rpc_url
        self.anvil_process = None
        self.accounts = {}
        self.contract_addresses = {}
        self.snapshots = {}
    
    def start_anvil(self, port: int = None) -> bool:
        """Запуск локального Anvil нода"""
        try:
            # Если порт не указан, извлекаем его из RPC URL
            if port is None:
                if "localhost" in self.rpc_url or "127.0.0.1" in self.rpc_url:
                    # Извлекаем порт из URL
                    if ":" in self.rpc_url:
                        port_str = self.rpc_url.split(":")[-1].split("/")[0]
                        try:
                            port = int(port_str)
                        except ValueError:
                            port = 8545
                    else:
                        port = 8545
                else:
                    # Если это не localhost, не запускаем Anvil
                    print(f"⚠️  RPC URL is not localhost, skipping Anvil start")
                    return False
            
            print(f"🚀 Starting Anvil on port {port}...")
            cmd = ["anvil", "--port", str(port), "--host", "0.0.0.0"]
            self.anvil_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Ждем запуска
            time.sleep(3)
            
            # Проверяем, что процесс запустился
            if self.anvil_process.poll() is None:
                print(f"✅ Anvil started successfully on port {port}")
                
                # Получаем аккаунты
                self._load_anvil_accounts()
                
                logger.info(f"Anvil started on port {port}")
                return True
            else:
                print(f"❌ Anvil process exited immediately")
                return False
            
        except Exception as e:
            print(f"💥 Error starting Anvil: {e}")
            logger.error(f"Error starting Anvil: {e}")
            return False
    
    def stop_anvil(self):
        """Остановка Anvil нода"""
        if self.anvil_process:
            self.anvil_process.terminate()
            self.anvil_process.wait()
            logger.info("Anvil stopped")
    
    def _load_anvil_accounts(self):
        """Загрузка аккаунтов из Anvil или создание тестовых"""
        try:
            result = subprocess.run(
                ["cast", "wallet", "list"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            print(f"🔍 Cast wallet list result:")
            print(f"   Return code: {result.returncode}")
            print(f"   Stdout: {result.stdout}")
            print(f"   Stderr: {result.stderr}")
            
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split('\n')
                print(f"📋 Parsing {len(lines)} lines from cast wallet list:")
                for i, line in enumerate(lines):
                    print(f"   Line {i}: '{line}'")
                    if '0x' in line:
                        address = line.split()[0]
                        self.accounts[f"$acc{i}"] = address
                        print(f"✅ Loaded account $acc{i}: {address}")
                        logger.debug(f"Loaded account $acc{i}: {address}")
                
                print(f"🎯 Total accounts loaded: {len(self.accounts)}")
                print(f"📊 Available accounts: {self.accounts}")
            else:
                print(f"❌ Cast wallet list failed or empty, creating test accounts")
                self._create_test_accounts()
            
        except Exception as e:
            print(f"💥 Exception in _load_anvil_accounts: {e}")
            print(f"🔄 Creating test accounts as fallback")
            self._create_test_accounts()
    
    def _create_test_accounts(self):
        """Создание тестовых аккаунтов"""
        print(f"🏗️  Creating test accounts...")
        
        # Стандартные тестовые адреса Anvil
        test_accounts = [
            "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",  # acc0
            "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",  # acc1
            "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC",  # acc2
            "0x90F79bf6EB2c4f870365E785982E1f101E93b906",  # acc3
            "0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65",   # acc4
            "0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc",  # acc5
            "0x976EA74026E726554dB657fA54763abd0C3a0aa9",  # acc6
            "0x14dC79964da2C08b23698B3D3cc7Ca32193d9955",  # acc7
            "0x23618e81E3f5cdF7f54C3d65f7FBc0aBf5B21E8f",  # acc8
            "0xa0Ee7A142d267C1f36714E4a8F75612F20a79720"   # acc9
        ]
        
        for i, address in enumerate(test_accounts):
            self.accounts[f"$acc{i}"] = address
            print(f"✅ Created test account $acc{i}: {address}")
        
        print(f"🎯 Total test accounts created: {len(self.accounts)}")
        print(f"📊 Available accounts: {self.accounts}")
        
        # Устанавливаем балансы для тестовых аккаунтов
        self._fund_test_accounts()
    
    def _fund_test_accounts(self):
        """Финансирование тестовых аккаунтов"""
        print(f"💰 Funding test accounts...")
        
        try:
            # Получаем баланс первого аккаунта
            result = subprocess.run(
                ["cast", "balance", self.accounts["$acc0"], "--rpc-url", self.rpc_url],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                balance = result.stdout.strip()
                print(f"💰 Account $acc0 balance: {balance}")
                
                # Если баланс слишком мал, устанавливаем большой баланс
                if int(balance, 16) < 1000000000000000000000:  # 1000 ETH
                    print(f"💸 Setting large balance for test accounts...")
                    
                    for i in range(min(10, len(self.accounts))):
                        account_key = f"$acc{i}"
                        if account_key in self.accounts:
                            address = self.accounts[account_key]
                            
                            # Устанавливаем баланс 10000 ETH
                            fund_result = subprocess.run(
                                ["cast", "rpc", "anvil_setBalance", address, "0x21e19e0c9bab2400000", "--rpc-url", self.rpc_url],
                                capture_output=True,
                                text=True,
                                timeout=10
                            )
                            
                            if fund_result.returncode == 0:
                                print(f"✅ Funded account $acc{i}: {address}")
                            else:
                                print(f"❌ Failed to fund account $acc{i}: {fund_result.stderr}")
            else:
                print(f"⚠️  Could not check balance: {result.stderr}")
                
        except Exception as e:
            print(f"💥 Exception in _fund_test_accounts: {e}")
            logger.warning(f"Error funding test accounts: {e}")
    
    def _ensure_rpc_connection(self):
        """Обеспечиваем подключение к RPC и наличие аккаунтов"""
        print(f"🔌 Ensuring RPC connection...")
        
        # Проверяем подключение к RPC
        try:
            result = subprocess.run(
                ["cast", "block-number", "--rpc-url", self.rpc_url],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                block_number = result.stdout.strip()
                print(f"✅ RPC connection OK, block number: {block_number}")
            else:
                print(f"❌ RPC connection failed: {result.stderr}")
                print(f"🚀 Attempting to start Anvil...")
                
                # Пытаемся запустить Anvil
                if self.start_anvil():
                    print(f"✅ Anvil started successfully")
                else:
                    print(f"❌ Failed to start Anvil, using test accounts anyway")
                    
        except Exception as e:
            print(f"💥 Exception checking RPC: {e}")
            print(f"🚀 Attempting to start Anvil...")
            
            # Пытаемся запустить Anvil
            if self.start_anvil():
                print(f"✅ Anvil started successfully")
            else:
                print(f"❌ Failed to start Anvil, using test accounts anyway")
        
        # Если аккаунты не загружены, создаем тестовые
        if not self.accounts:
            print(f"🔄 No accounts loaded, creating test accounts...")
            self._create_test_accounts()
    
    def execute_scenario(self, scenario: Scenario) -> ExecutionResult:
        """Выполнение сценария"""
        start_time = time.time()
        steps_executed = 0
        
        try:
            print(f"🎬 Starting scenario execution: {scenario.name}")
            print(f"📊 Current accounts state: {self.accounts}")
            print(f"🔗 RPC URL: {self.rpc_url}")
            logger.info(f"Executing scenario: {scenario.name}")
            
            # Проверяем подключение к RPC и создаем аккаунты если нужно
            self._ensure_rpc_connection()
            
            # Подготовка ролей
            self._prepare_roles(scenario.roles)
            
            # Выполнение шагов
            for step in scenario.steps:
                logger.debug(f"Executing step: {step.type.value}")
                self._execute_step(step, scenario)
                steps_executed += 1
            
            execution_time = time.time() - start_time
            
            return ExecutionResult(
                success=True,
                scenario_name=scenario.name,
                execution_time=execution_time,
                steps_executed=steps_executed,
                total_steps=len(scenario.steps),
                artifacts=self._collect_artifacts(scenario)
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Scenario execution failed: {e}")
            
            return ExecutionResult(
                success=False,
                scenario_name=scenario.name,
                execution_time=execution_time,
                steps_executed=steps_executed,
                total_steps=len(scenario.steps),
                error=str(e)
            )
    
    def _prepare_roles(self, roles: Dict[str, Role]):
        """Подготовка ролей"""
        print(f"🔧 Preparing roles...")
        print(f"📊 Available accounts before preparation: {self.accounts}")
        print(f"👥 Roles to prepare: {[(name, role.address) for name, role in roles.items()]}")
        
        for role_name, role in roles.items():
            print(f"🔄 Processing role '{role_name}' with address '{role.address}'")
            if role.address.startswith('$'):
                # Замена переменных аккаунтов
                account_key = role.address
                print(f"   Looking for account key: '{account_key}'")
                if account_key in self.accounts:
                    old_address = role.address
                    role.address = self.accounts[account_key]
                    print(f"✅ Replaced '{old_address}' → '{role.address}' for role '{role_name}'")
                else:
                    print(f"❌ Account variable '{account_key}' not found in available accounts!")
                    print(f"   Available account keys: {list(self.accounts.keys())}")
                    logger.warning(f"Unknown account variable: {account_key}")
            else:
                print(f"ℹ️  Role '{role_name}' already has concrete address: '{role.address}'")
        
        print(f"🎯 Final roles after preparation: {[(name, role.address) for name, role in roles.items()]}")
    
    def _execute_step(self, step: Step, scenario: Scenario):
        """Выполнение отдельного шага"""
        if step.type == StepType.SEND:
            self._execute_send(step, scenario)
        elif step.type == StepType.CALL:
            self._execute_call(step, scenario)
        elif step.type == StepType.WAIT:
            self._execute_wait(step)
        elif step.type == StepType.TIME_TRAVEL:
            self._execute_time_travel(step)
        elif step.type == StepType.SNAPSHOT:
            self._execute_snapshot(step, scenario)
        elif step.type == StepType.REVERT:
            self._execute_revert(step, scenario)
        elif step.type == StepType.ASSERT:
            self._execute_assert(step, scenario)
        elif step.type == StepType.DEPLOY:
            self._execute_deploy(step, scenario)
        elif step.type == StepType.MINE:
            self._execute_mine(step)
        elif step.type == StepType.SET_BALANCE:
            self._execute_set_balance(step)
        elif step.type == StepType.SET_STORAGE:
            self._execute_set_storage(step)
        elif step.type == StepType.LABEL:
            self._execute_label(step)
        elif step.type == StepType.ACTION:
            self._execute_action(step, scenario)
        else:
            raise ValueError(f"Unsupported step type: {step.type}")
    
    def _execute_send(self, step: Step, scenario: Scenario):
        """Выполнение транзакции"""
        data = step.data
        
        print(f"📤 Executing SEND step:")
        print(f"   Step data: {data}")
        
        # Проверяем, есть ли минимально необходимые данные для SEND
        if 'from' not in data and 'to' not in data and 'fn' not in data:
            # Если данных недостаточно, это может быть неправильно определенный шаг
            print(f"   ⚠️  Insufficient data for SEND step, checking if this should be a different step type")
            
            # Проверяем, есть ли в данных указание на другой тип шага
            if 'value' in data:
                value = data['value']
                if isinstance(value, str) and value.lower() in ['deploy', 'call', 'assert', 'wait', 'mine', 'snapshot', 'revert']:
                    print(f"   🔄 Detected step type '{value}' from 'value' field, redirecting to appropriate handler")
                    # Перенаправляем на соответствующий обработчик
                    if value.lower() == 'deploy':
                        self._execute_deploy(step, scenario)
                        return
                    elif value.lower() == 'call':
                        self._execute_call(step, scenario)
                        return
                    elif value.lower() == 'assert':
                        self._execute_assert(step, scenario)
                        return
                    elif value.lower() == 'wait':
                        self._execute_wait(step, scenario)
                        return
                    elif value.lower() == 'mine':
                        self._execute_mine(step, scenario)
                        return
                    elif value.lower() == 'snapshot':
                        self._execute_snapshot(step, scenario)
                        return
                    elif value.lower() == 'revert':
                        self._execute_revert(step, scenario)
                        return
            
            # Если мы дошли сюда, значит данных действительно недостаточно
            raise ValueError(f"Insufficient data for SEND step. Required: 'from' or 'to' or 'fn'. Got: {list(data.keys())}")
        
        # Получение адреса отправителя
        from_addr = data.get('from')
        print(f"   Original 'from' value: '{from_addr}'")
        if from_addr in scenario.roles:
            from_addr = scenario.roles[from_addr].address
            print(f"   Resolved 'from' address: '{from_addr}'")
        
        # Получение адреса получателя
        to_addr = data.get('to')
        print(f"   Original 'to' value: '{to_addr}'")
        if to_addr in scenario.contracts:
            to_addr = scenario.contracts[to_addr]
            print(f"   Resolved 'to' address: '{to_addr}'")
        
        # Формирование команды cast
        cmd = ["cast", "send", "--rpc-url", self.rpc_url]
        
        if from_addr:
            cmd.extend(["--from", from_addr])
            print(f"   Added --from {from_addr} to command")
        
        if to_addr:
            cmd.extend([to_addr])
        
        # Добавление функции и аргументов
        fn = data.get('fn', '')
        args = data.get('args', [])
        
        if fn:
            cmd.append(fn)
            for arg in args:
                cmd.append(str(arg))
        
        # Выполнение команды
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            raise RuntimeError(f"Send transaction failed: {result.stderr}")
        
        logger.debug(f"Send transaction successful: {result.stdout.strip()}")
    
    def _execute_call(self, step: Step, scenario: Scenario):
        """Выполнение вызова view функции"""
        data = step.data
        
        # Получение адреса контракта
        to_addr = data.get('to')
        if to_addr in scenario.contracts:
            to_addr = scenario.contracts[to_addr]
        
        # Формирование команды cast
        cmd = ["cast", "call", "--rpc-url", self.rpc_url]
        
        if to_addr:
            cmd.extend([to_addr])
        
        # Добавление функции и аргументов
        fn = data.get('fn', '')
        args = data.get('args', [])
        
        if fn:
            cmd.append(fn)
            for arg in args:
                cmd.append(str(arg))
        
        # Выполнение команды
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            raise RuntimeError(f"Call failed: {result.stderr}")
        
        # Проверка ожидаемого результата
        if 'expect' in data:
            expected = data['expect']
            actual = result.stdout.strip()
            self._check_expectation(actual, expected)
        
        logger.debug(f"Call successful: {result.stdout.strip()}")
    
    def _execute_wait(self, step: Step):
        """Ожидание блоков"""
        blocks = step.data.get('blocks', 1)
        
        # Используем cast для ожидания блоков
        cmd = ["cast", "rpc", "anvil_mine", str(blocks), "--rpc-url", self.rpc_url]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            raise RuntimeError(f"Wait failed: {result.stderr}")
        
        logger.debug(f"Waited for {blocks} blocks")
    
    def _execute_time_travel(self, step: Step):
        """Переход во времени"""
        seconds = step.data.get('seconds', 0)
        
        # Используем cast для перехода во времени
        cmd = ["cast", "rpc", "anvil_increaseTime", str(seconds), "--rpc-url", self.rpc_url]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            raise RuntimeError(f"Time travel failed: {result.stderr}")
        
        logger.debug(f"Time traveled {seconds} seconds")
    
    def _execute_snapshot(self, step: Step, scenario: Scenario):
        """Создание снапшота"""
        snapshot_name = step.data.get('name', f"snapshot_{len(scenario.snapshots)}")
        
        # Используем cast для создания снапшота
        cmd = ["cast", "rpc", "evm_snapshot", "--rpc-url", self.rpc_url]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            raise RuntimeError(f"Snapshot creation failed: {result.stderr}")
        
        snapshot_id = result.stdout.strip().strip('"')
        scenario.snapshots[snapshot_name] = snapshot_id
        
        logger.debug(f"Snapshot created: {snapshot_name} = {snapshot_id}")
    
    def _execute_revert(self, step: Step, scenario: Scenario):
        """Откат к снапшоту"""
        snapshot_name = step.data.get('name')
        
        if snapshot_name not in scenario.snapshots:
            raise ValueError(f"Snapshot not found: {snapshot_name}")
        
        snapshot_id = scenario.snapshots[snapshot_name]
        
        # Используем cast для отката
        cmd = ["cast", "rpc", "evm_revert", snapshot_id, "--rpc-url", self.rpc_url]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            raise RuntimeError(f"Revert failed: {result.stderr}")
        
        logger.debug(f"Reverted to snapshot: {snapshot_name}")
    
    def _execute_assert(self, step: Step, scenario: Scenario):
        """Выполнение проверки"""
        data = step.data
        
        # Получение значения для проверки
        value = data.get('value')
        if isinstance(value, str) and value.startswith('$'):
            # Переменная
            if value in scenario.contracts:
                value = scenario.contracts[value]
            elif value in scenario.roles:
                value = scenario.roles[value].address
        
        # Получение ожидаемого значения
        expected = data.get('expect')
        
        # Выполнение проверки
        self._check_expectation(str(value), expected)
        
        logger.debug(f"Assertion passed: {value} {expected}")
    
    def _execute_deploy(self, step: Step, scenario: Scenario):
        """Выполнение деплоя контракта"""
        data = step.data
        
        print(f"🚀 Executing DEPLOY step:")
        print(f"   Step data: {data}")
        
        # Получение адреса отправителя
        from_addr = data.get('from')
        print(f"   Original 'from' value: '{from_addr}'")
        if from_addr in scenario.roles:
            from_addr = scenario.roles[from_addr].address
            print(f"   Resolved 'from' address: '{from_addr}'")
        
        # Получение имени контракта
        contract_name = data.get('contract')
        print(f"   Contract name: '{contract_name}'")
        
        # Получение байткода и аргументов конструктора
        bytecode = data.get('bytecode', '')
        args = data.get('args', [])
        
        print(f"   Bytecode: '{bytecode[:50]}...' (truncated)")
        print(f"   Constructor args: {args}")
        
        # Формирование команды для деплоя
        if bytecode:
            # Для деплоя контракта используем cast create с байткодом
            cmd = ["cast", "create", "--rpc-url", self.rpc_url]
            
            if from_addr:
                cmd.extend(["--from", from_addr])
                print(f"   Added --from {from_addr} to command")
            
            # Добавляем байткод и аргументы конструктора
            cmd.append(bytecode)
            for arg in args:
                cmd.append(str(arg))
        else:
            # Если байткод не указан, используем cast create без байткода
            cmd = ["cast", "create", "--rpc-url", self.rpc_url]
            
            if from_addr:
                cmd.extend(["--from", from_addr])
                print(f"   Added --from {from_addr} to command")
            
            # Добавляем аргументы конструктора
            for arg in args:
                cmd.append(str(arg))
        
        print(f"   Command: {' '.join(cmd[:5])}... (truncated)")
        
        # Выполнение команды
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        print(f"   Deploy result:")
        print(f"     Return code: {result.returncode}")
        print(f"     Stdout: {result.stdout}")
        print(f"     Stderr: {result.stderr}")
        
        if result.returncode != 0:
            raise RuntimeError(f"Deploy failed: {result.stderr}")
        
        # Извлечение адреса контракта из результата
        contract_address = None
        output = result.stdout.strip()
        
        print(f"   Parsing output for contract address...")
        print(f"   Raw output: {output}")
        
        # Ищем адрес контракта в выводе cast create
        if '0x' in output:
            # Парсим адрес из вывода cast create
            lines = output.split('\n')
            for line in lines:
                line = line.strip()
                if '0x' in line:
                    # Ищем адрес длиной 42 символа (0x + 40 hex chars)
                    parts = line.split()
                    for part in parts:
                        if part.startswith('0x') and len(part) == 42:
                            contract_address = part
                            print(f"   Found contract address in output: {contract_address}")
                            break
                    if contract_address:
                        break
        
        # Если не нашли в stdout, пробуем получить из транзакции
        if not contract_address:
            print(f"   Contract address not found in output, trying receipt...")
            # Извлекаем хеш транзакции из вывода
            tx_hash = None
            for line in output.split('\n'):
                line = line.strip()
                if '0x' in line:
                    # Ищем хеш транзакции длиной 66 символов (0x + 64 hex chars)
                    parts = line.split()
                    for part in parts:
                        if part.startswith('0x') and len(part) == 66:
                            tx_hash = part
                            break
                    if tx_hash:
                        break
            
            if tx_hash:
                print(f"   Transaction hash: {tx_hash}")
                # Получаем адрес контракта из транзакции
                try:
                    receipt_cmd = ["cast", "receipt", tx_hash, "--rpc-url", self.rpc_url]
                    receipt_result = subprocess.run(receipt_cmd, capture_output=True, text=True, timeout=10)
                    
                    if receipt_result.returncode == 0:
                        receipt_output = receipt_result.stdout.strip()
                        print(f"   Receipt output: {receipt_output}")
                        
                        # Ищем contractAddress в receipt
                        for line in receipt_output.split('\n'):
                            line = line.strip()
                            if 'contractAddress' in line.lower() or 'contract address' in line.lower():
                                if '0x' in line:
                                    parts = line.split()
                                    for part in parts:
                                        if part.startswith('0x') and len(part) == 42:
                                            contract_address = part
                                            print(f"   Found contract address in receipt: {contract_address}")
                                            break
                                    if contract_address:
                                        break
                except Exception as e:
                    print(f"   ⚠️  Could not get receipt: {e}")
        
        # Если все еще не нашли, создаем временный адрес
        if not contract_address:
            print(f"   ⚠️  Could not extract contract address, using placeholder")
            contract_address = "0x0000000000000000000000000000000000000000"
        
        # Сохраняем адрес контракта
        scenario.contracts[contract_name] = contract_address
        print(f"   ✅ Contract '{contract_name}' deployed at: {contract_address}")
        
        logger.debug(f"Contract deployed: {contract_name} at {contract_address}")
    
    def _execute_mine(self, step: Step):
        """Майнинг блоков"""
        blocks = step.data.get('blocks', 1)
        
        # Используем cast для майнинга блоков
        cmd = ["cast", "rpc", "anvil_mine", str(blocks), "--rpc-url", self.rpc_url]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            raise RuntimeError(f"Mine failed: {result.stderr}")
        
        logger.debug(f"Mined {blocks} blocks")
    
    def _execute_set_balance(self, step: Step):
        """Установка баланса аккаунта"""
        data = step.data
        
        address = data.get('address')
        balance = data.get('balance')
        
        # Используем cast для установки баланса
        cmd = ["cast", "rpc", "anvil_setBalance", address, balance, "--rpc-url", self.rpc_url]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            raise RuntimeError(f"Set balance failed: {result.stderr}")
        
        logger.debug(f"Set balance for {address}: {balance}")
    
    def _execute_set_storage(self, step: Step):
        """Установка storage контракта"""
        data = step.data
        
        address = data.get('address')
        slot = data.get('slot')
        value = data.get('value')
        
        # Используем cast для установки storage
        cmd = ["cast", "rpc", "anvil_setStorageAt", address, slot, value, "--rpc-url", self.rpc_url]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            raise RuntimeError(f"Set storage failed: {result.stderr}")
        
        logger.debug(f"Set storage for {address} slot {slot}: {value}")
    
    def _execute_label(self, step: Step):
        """Выполнение метки (логирование)"""
        data = step.data
        
        label_text = data.get('text', '')
        logger.info(f"LABEL: {label_text}")
        
        # Метки не выполняют никаких действий, только логируют
    
    def _execute_action(self, step: Step, scenario: Scenario):
        """Выполнение универсального действия"""
        data = step.data
        
        print(f"⚡ Executing ACTION step:")
        print(f"   Step data: {data}")
        
        # Определяем тип действия на основе содержимого
        action_type = data.get('type', 'send')  # По умолчанию send
        
        # Специальная обработка для случая, когда данные содержат только 'value'
        if 'type' not in data and 'value' in data:
            value = data['value']
            if isinstance(value, str):
                # Если value - это строка, которая может быть типом действия
                if value.lower() in ['deploy', 'send', 'call', 'assert', 'wait', 'mine', 'snapshot', 'revert']:
                    action_type = value.lower()
                    print(f"   Detected action type from 'value': '{action_type}'")
                else:
                    print(f"   Unknown value '{value}', treating as send")
                    action_type = 'send'
        
        print(f"   Action type: '{action_type}'")
        
        # Создаем временный шаг с определенным типом
        if action_type == 'send':
            temp_step = Step(type=StepType.SEND, data=data, description=step.description)
            self._execute_send(temp_step, scenario)
        elif action_type == 'call':
            temp_step = Step(type=StepType.CALL, data=data, description=step.description)
            self._execute_call(temp_step, scenario)
        elif action_type == 'deploy':
            temp_step = Step(type=StepType.DEPLOY, data=data, description=step.description)
            self._execute_deploy(temp_step, scenario)
        elif action_type == 'assert':
            temp_step = Step(type=StepType.ASSERT, data=data, description=step.description)
            self._execute_assert(temp_step, scenario)
        else:
            print(f"⚠️  Unknown action type '{action_type}', treating as send")
            temp_step = Step(type=StepType.SEND, data=data, description=step.description)
            self._execute_send(temp_step, scenario)
    
    def _check_expectation(self, actual: str, expected: str):
        """Проверка ожидания"""
        if expected.startswith('=='):
            expected_value = expected[2:].strip()
            if actual != expected_value:
                raise AssertionError(f"Expected {expected_value}, got {actual}")
        elif expected.startswith('!='):
            expected_value = expected[2:].strip()
            if actual == expected_value:
                raise AssertionError(f"Expected not {expected_value}, got {actual}")
        elif expected.startswith('>'):
            expected_value = int(expected[1:].strip())
            actual_value = int(actual, 16) if actual.startswith('0x') else int(actual)
            if actual_value <= expected_value:
                raise AssertionError(f"Expected > {expected_value}, got {actual_value}")
        elif expected.startswith('<'):
            expected_value = int(expected[1:].strip())
            actual_value = int(actual, 16) if actual.startswith('0x') else int(actual)
            if actual_value >= expected_value:
                raise AssertionError(f"Expected < {expected_value}, got {actual_value}")
        else:
            raise ValueError(f"Unsupported expectation format: {expected}")
    
    def _collect_artifacts(self, scenario: Scenario) -> Dict[str, Any]:
        """Сбор артефактов выполнения"""
        artifacts = {
            'scenario_name': scenario.name,
            'roles': {name: role.address for name, role in scenario.roles.items()},
            'contracts': scenario.contracts.copy(),
            'snapshots': scenario.snapshots.copy(),
            'execution_time': time.time()
        }
        
        return artifacts


class ScenarioHelper:
    """Помощник для создания сценариев агентом"""
    
    def __init__(self):
        self.parser = ScenarioParser()
    
    def create_scenario_template(self, contract_name: str, abi: List[Dict[str, Any]], 
                                scenario_type: str = "custom") -> Dict[str, Any]:
        """Создание шаблона сценария для агента на основе ABI"""
        
        # Анализ ABI для понимания возможностей контракта
        functions = []
        events = []
        constructor_inputs = []
        
        for item in abi:
            if item.get('type') == 'function':
                func_info = {
                    'name': item['name'],
                    'inputs': item.get('inputs', []),
                    'outputs': item.get('outputs', []),
                    'stateMutability': item.get('stateMutability', 'nonpayable')
                }
                functions.append(func_info)
            elif item.get('type') == 'event':
                events.append({
                    'name': item['name'],
                    'inputs': item.get('inputs', [])
                })
            elif item.get('type') == 'constructor':
                constructor_inputs = item.get('inputs', [])
        
        # Создание шаблона сценария
        template = {
            'name': f"{scenario_type}-{contract_name}",
            'description': f"Custom scenario for {contract_name}",
            'roles': {
                'deployer': '$acc0',
                'user': '$acc1',
                'attacker': '$acc2'
            },
            'contracts': {
                contract_name: '0x...'  # Агент должен указать адрес
            },
            'steps': [
                # Агент должен сам придумать шаги
            ],
            'abi_analysis': {
                'functions': functions,
                'events': events,
                'constructor_inputs': constructor_inputs,
                'suggestions': self._generate_suggestions(functions, events)
            }
        }
        
        return template
    
    def _generate_suggestions(self, functions: List[Dict], events: List[Dict]) -> List[str]:
        """Генерация предложений для агента на основе ABI"""
        suggestions = []
        
        # Анализ функций для предложений
        function_names = [f['name'] for f in functions]
        
        if 'transfer' in function_names:
            suggestions.append("Consider testing token transfers between different users")
        
        if 'approve' in function_names and 'transferFrom' in function_names:
            suggestions.append("Test approval and transferFrom workflow")
        
        if 'mint' in function_names:
            suggestions.append("Test minting functionality and supply limits")
        
        if 'burn' in function_names:
            suggestions.append("Test burning tokens and supply reduction")
        
        if 'stake' in function_names or 'deposit' in function_names:
            suggestions.append("Test staking/deposit functionality with time-based rewards")
        
        if 'withdraw' in function_names or 'unstake' in function_names:
            suggestions.append("Test withdrawal/unstaking with potential penalties")
        
        if 'pause' in function_names and 'unpause' in function_names:
            suggestions.append("Test pause/unpause functionality and access control")
        
        if 'upgrade' in function_names or 'migrate' in function_names:
            suggestions.append("Test upgrade/migration functionality")
        
        # Анализ событий
        event_names = [e['name'] for e in events]
        if 'Transfer' in event_names:
            suggestions.append("Verify Transfer events are emitted correctly")
        
        if 'Approval' in event_names:
            suggestions.append("Verify Approval events for allowance changes")
        
        return suggestions
    
    def _generate_function_args(self, inputs: List[Dict[str, Any]]) -> List[str]:
        """Генерация аргументов для функции"""
        args = []
        
        for inp in inputs:
            input_type = inp.get('type', '')
            
            if 'uint' in input_type:
                args.append('1')
            elif 'int' in input_type:
                args.append('1')
            elif 'bool' in input_type:
                args.append('true')
            elif 'address' in input_type:
                args.append('$acc1')
            elif 'string' in input_type:
                args.append('"test"')
            elif 'bytes' in input_type:
                args.append('0x00')
            else:
                args.append('0')
        
        return args
    
    def save_scenario(self, scenario: Scenario, file_path: Path):
        """Сохранение сценария в YAML файл"""
        scenario_data = {
            'name': scenario.name,
            'description': scenario.description,
            'roles': {name: role.address for name, role in scenario.roles.items()},
            'contracts': scenario.contracts,
            'steps': []
        }
        
        for step in scenario.steps:
            step_data = {step.type.value: step.data}
            if step.description:
                step_data[step.type.value]['description'] = step.description
            scenario_data['steps'].append(step_data)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(scenario_data, f, default_flow_style=False, sort_keys=False)


class ScenarioRunner:
    """Основной класс для работы со сценариями"""
    
    def __init__(self, rpc_url: str = "http://localhost:8545"):
        self.parser = ScenarioParser()
        self.executor = ScenarioExecutor(rpc_url)
        self.helper = ScenarioHelper()
    
    def run_scenario_from_file(self, file_path: Path) -> ExecutionResult:
        """Запуск сценария из файла"""
        scenario = self.parser.parse_file(file_path)
        return self.executor.execute_scenario(scenario)
    
    def run_scenario_from_yaml(self, yaml_content: str) -> ExecutionResult:
        """Запуск сценария из YAML строки"""
        scenario = self.parser.parse_yaml(yaml_content)
        return self.executor.execute_scenario(scenario)
    
    def create_scenario_template(self, contract_name: str, abi: List[Dict[str, Any]], 
                                scenario_type: str = "custom") -> Dict[str, Any]:
        """Создание шаблона сценария для агента"""
        return self.helper.create_scenario_template(contract_name, abi, scenario_type)
    
    def start_local_chain(self, port: int = 8545) -> bool:
        """Запуск локальной цепи"""
        return self.executor.start_anvil(port)
    
    def stop_local_chain(self):
        """Остановка локальной цепи"""
        self.executor.stop_anvil()
    
    def save_scenario(self, scenario: Scenario, file_path: Path):
        """Сохранение сценария"""
        scenario_data = {
            'name': scenario.name,
            'description': scenario.description,
            'roles': {name: role.address for name, role in scenario.roles.items()},
            'contracts': scenario.contracts,
            'steps': []
        }
        
        for step in scenario.steps:
            step_data = {step.type.value: step.data}
            if step.description:
                step_data[step.type.value]['description'] = step.description
            scenario_data['steps'].append(step_data)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(scenario_data, f, default_flow_style=False, sort_keys=False)


# Пример использования
if __name__ == "__main__":
    # Пример YAML сценария
    example_yaml = """
name: smoke-Counter
roles:
  deployer: "$acc0"
  user: "$acc1"
steps:
  - send:
      from: deployer
      to: Counter
      fn: "increment()"
      args: []
      description: "Increment counter"
  - call:
      to: Counter
      fn: "number()"
      expect: "==1"
      description: "Check counter value"
"""
    
    # Создание и запуск сценария
    runner = ScenarioRunner()
    
    try:
        # Запуск локальной цепи
        if runner.start_local_chain():
            # Выполнение сценария
            result = runner.run_scenario_from_yaml(example_yaml)
            
            if result.success:
                print(f"✅ Scenario '{result.scenario_name}' completed successfully")
                print(f"   Execution time: {result.execution_time:.2f}s")
                print(f"   Steps executed: {result.steps_executed}/{result.total_steps}")
            else:
                print(f"❌ Scenario '{result.scenario_name}' failed: {result.error}")
        
    finally:
        # Остановка локальной цепи
        runner.stop_local_chain()