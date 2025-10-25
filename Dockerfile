# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies required for Foundry and Solidity compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    wget \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Install Foundry
RUN curl -L https://foundry.paradigm.xyz | bash && \
    /root/.foundry/bin/foundryup && \
    ln -s /root/.foundry/bin/forge /usr/local/bin/forge && \
    ln -s /root/.foundry/bin/anvil /usr/local/bin/anvil && \
    ln -s /root/.foundry/bin/cast /usr/local/bin/cast && \
    ln -s /root/.foundry/bin/chisel /usr/local/bin/chisel

# Install Echidna (fuzzing tool) - alternative method
RUN pip install echidna-parade || \
    (wget -O echidna.tar.gz "https://github.com/crytic/echidna/releases/download/v2.2.0/echidna-test-2.2.0-Ubuntu-20.04.tar.gz" && \
     tar -xzf echidna.tar.gz && \
     mv echidna-test /usr/local/bin/echidna && \
     chmod +x /usr/local/bin/echidna && \
     rm echidna.tar.gz)

# Install uv package manager
RUN pip install uv

# Copy project files
COPY pyproject.toml uv.lock ./
COPY mcp_modules/ ./mcp_modules/
COPY server.py ./
COPY main.py ./
COPY README.md ./
COPY SETUP.md ./

# Install Python dependencies using uv
RUN uv sync --frozen

# Create cache directories for Foundry projects
RUN mkdir -p /tmp/foundry_projects /tmp/build_cache /tmp/deploy_cache

# Expose port for MCP server
EXPOSE 8000

# Set environment variables
ENV PYTHONPATH=/app
ENV FOUNDRY_CACHE_DIR=/tmp/foundry_projects
ENV BUILD_CACHE_DIR=/tmp/build_cache
ENV DEPLOY_CACHE_DIR=/tmp/deploy_cache

# Default command to run the MCP server
CMD ["uv", "run", "server.py"]
