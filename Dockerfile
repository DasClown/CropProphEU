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

# Default: stdio mode (for MCP clients)
# Override with --http for remote/SSE connectivity
CMD ["crop-mcp"]
