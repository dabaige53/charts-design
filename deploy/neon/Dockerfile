FROM ghcr.io/astral-sh/uv:0.12.13 AS uv
FROM python:3.11-slim
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project --extra mcp --extra cloud --extra neon --extra statistics
COPY dashboard_runtime/ dashboard_runtime/
COPY skills/ skills/
COPY bin/ bin/
COPY docs/ docs/
COPY package.json ./
COPY cloudbase/migrations/ cloudbase/migrations/
COPY deploy/neon/ deploy/neon/
ENV PATH=/app/.venv/bin:$PATH PYTHON=/app/.venv/bin/python PYTHONPATH=/app PYTHONDONTWRITEBYTECODE=1 CHARTS_HOST=0.0.0.0 CHARTS_PORT=8000 CHARTS_STORAGE_BACKEND=neon CHARTS_WORKSPACE=/data/projects CHARTS_RUNTIME_ROOT=/data/runtime MPLCONFIGDIR=/tmp/matplotlib
RUN useradd --system --uid 10001 charts && mkdir -p /data/projects /data/runtime && chown -R charts /data
USER charts
ENV CHARTS_UNIFIED_MCP_MODE=model
EXPOSE 8000
CMD ["python", "-m", "dashboard_runtime", "server"]
