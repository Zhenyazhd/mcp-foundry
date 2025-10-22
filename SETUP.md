# Quick Setup Guide

## Prerequisites

```bash
# Install Foundry
curl -L https://foundry.paradigm.xyz | bash
foundryup

# Verify installation
forge --version
anvil --version
cast --version
```

## Installation

```bash
# Clone and setup
git clone <repository-url>
cd mcp-foundry-anvil

# Install Python dependencies
pip install -r requirements.txt
# or using uv
uv sync
```

## Running

```bash
# Start MCP server
python server.py
```

## Testing

```bash
# Test project creation
python -c "
from mcp_modules.project import get_project_manager
pm = get_project_manager()
project = pm.create_project(solc_version='0.8.20')
print(f'Project created: {project.project_id}')
pm.cleanup_project(project.project_id)
"
```

## Verification

```bash
# Check all modules
python -c "
from mcp_modules.project import ProjectManager; print('✅ Project module')
from mcp_modules.build import BuildManager; print('✅ Build module')
from mcp_modules.tests_runner import TestRunner; print('✅ Test module')
from mcp_modules.scenario import ScenarioRunner; print('✅ Scenario module')
print('All modules loaded successfully!')
"
```

## Troubleshooting

### Foundry not found
- Install Foundry: `curl -L https://foundry.paradigm.xyz | bash && foundryup`
- Ensure `forge`, `anvil`, `cast` are in PATH

### Python dependencies
- Use Python 3.11+
- Install dependencies: `pip install -r requirements.txt`

### Permission errors
- Ensure write permissions to temp directory
- Check file system permissions
