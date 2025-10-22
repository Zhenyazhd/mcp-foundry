# MCP Foundry Anvil

Smart Contract Project Manager with MCP (Model Context Protocol) integration for Ethereum development.

## ⚠️ Work in Progress

**This project is currently under active development and is not yet ready for production use.** The codebase is being cleaned up, optimized, and prepared for GitHub. Some features may be incomplete or subject to change.

## Current Status

**Project for Foundry workflow**

### What's Working

- **Project Management**: Create, manage, and cleanup temporary Foundry projects
- **File Operations**: Add, modify, and delete contract files
- **Compilation**: Unified compilation using project settings (solc version, optimization)
- **Testing**: Run tests, fuzz tests, coverage analysis, gas reports
- **Deployment**: Generate smart deployment scripts based on artifacts
- **Dependencies**: Install external dependencies (OpenZeppelin, etc.)
- **Scenario Testing**: YAML-based declarative testing framework

### Architecture

```
mcp-foundry-anvil/
├── server.py                 # Main MCP server (898 lines)
├── mcp_modules/              # Core modules
│   ├── project.py           # Project management (1105 lines)
│   ├── build.py             # Build management (553 lines)
│   ├── tests_runner.py      # Test execution (488 lines)
│   ├── scenario.py          # Scenario testing (1424 lines)
│   └── chain.py             # Chain management (604 lines)
├── pyproject.toml           # Dependencies
└── requirements.txt         # Python requirements
```

### Key Features

- **Foundry-Only**: Removed Hardhat/Truffle support for simplicity
- **Unified Compilation**: All compilation goes through `project_manager.compile_project()`
- **Smart Deployment**: Auto-generates deployment scripts with correct Solidity versions
- **Caching**: Build artifacts cached for performance
- **Security**: File operations restricted to project directories

### MCP Tools

#### Project Management
- `project_create()` - Create Foundry project
- `project_add_files()` - Add contract files
- `project_compile()` - Compile contracts
- `project_deploy()` - Deploy contracts
- `project_cleanup_all()` - Cleanup all projects

#### Testing
- `test_run_all()` - Run all tests
- `test_run_fuzz()` - Run fuzz tests
- `test_run_coverage()` - Coverage analysis
- `test_get_gas_reports()` - Gas reports

#### Dependencies
- `project_install_dependency()` - Install single dependency
- `project_install_multiple_dependencies()` - Install multiple dependencies

#### Scenarios
- `scenario_run_from_file()` - Run scenario from YAML
- `scenario_create_template()` - Create scenario template
- `scenario_start_local_chain()` - Start Anvil chain

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run MCP server
python server.py
```

## Requirements

- Python 3.11+
- Foundry (forge, anvil, cast)
- Git


## License

MIT License
