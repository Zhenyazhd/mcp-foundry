# MCP Foundry Anvil

Smart Contract Project Manager with MCP (Model Context Protocol) integration for Ethereum development.


## Deployed MCP

https://steadfast-miracle-production.up.railway.app/mcp

## Current Status

**Project for Foundry workflow**

### What's Working

- **Project Management**: Create, manage, and cleanup temporary Foundry projects
- **File Operations**: Add, modify, and delete contract files
- **Compilation**: Unified compilation using project settings (solc version, optimization)
- **Testing**: Run tests, fuzz tests, coverage analysis, gas reports
- **Fuzzing**: Echidna integration for property-based testing and vulnerability discovery
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
├── requirements.txt         # Python requirements
├── Dockerfile               # Docker container definition
├── docker-compose.yml       # Docker Compose configuration
├── .dockerignore            # Docker ignore file
└── README.md                # This file
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

### Option 1: Local Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Run MCP server
python server.py
```

### Option 2: Docker Installation

```bash
# Build and run with Docker Compose
docker-compose up --build

# Run in detached mode
docker-compose up -d --build

# View logs
docker-compose logs -f

# Stop the container
docker-compose down
```

### Option 3: Direct Docker

```bash
# Build the image
docker build -t mcp-foundry-anvil .

# Run the container
docker run -p 8000:8000 -v foundry_projects:/tmp/foundry_projects mcp-foundry-anvil
```

## Requirements

### Local Development
- Python 3.11+
- Foundry (forge, anvil, cast)
- Echidna (optional, for fuzzing)
- Git

### Docker Development
- Docker
- Docker Compose (optional, for easier management)

## Docker Configuration

The project includes comprehensive Docker support with Foundry pre-installed:

### Dockerfile Features
- **Base Image**: Python 3.11 slim for optimal size
- **Foundry Integration**: Pre-installed Foundry tools (forge, anvil, cast, chisel)
- **Echidna Integration**: Pre-installed Echidna fuzzing tool for smart contract testing
- **System Dependencies**: Includes build tools for Solidity compilation
- **Package Management**: Uses `uv` for fast dependency resolution
- **Cache Management**: Persistent volumes for Foundry projects and build artifacts
- **Health Checks**: Built-in container health monitoring

### Docker Compose Features
- **Service Management**: Easy start/stop/restart
- **Volume Persistence**: Foundry projects and cache survive container restarts
- **Port Mapping**: MCP server accessible on port 8000
- **Development Mode**: Source code mounting for live development
- **Health Monitoring**: Automatic health checks and restart policies

### Container Volumes
- `foundry_projects`: Persistent storage for Foundry project files
- `build_cache`: Build artifacts cache
- `deploy_cache`: Deployment scripts cache
- Source code mounting for development (optional)


## License

MIT License
