FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY . .

# Install package with HTTP extras
RUN pip install --no-cache-dir .[http]

# Expose HTTP/SME port
EXPOSE 8080

# Default: HTTP/SSE mode for remote/Smithery connectivity
# Override with just "crop-mcp" for stdio mode (local MCP clients)
CMD ["crop-mcp", "--http", "--port", "8080"]
