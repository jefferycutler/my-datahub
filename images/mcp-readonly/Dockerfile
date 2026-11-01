# Read-only MCP server for the my-datahub lab.
# Build (arm64 cluster; amd64 for local testing):
#   docker buildx build --platform linux/arm64,linux/amd64 \
#     -t northamerica-northeast2-docker.pkg.dev/cutlernet-datahub/datahub-pr/mcp-readonly:0.1.0 --push .
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src \
    HOME=/tmp

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src

# Matches runAsUser/runAsGroup in k8s/mcp/50-mcp-server.yaml.
USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "mcp_readonly"]
