# Build from the repository root; all dependency versions come from lockfiles.
FROM ghcr.io/astral-sh/uv:0.12.13 AS uv

FROM python:3.11-slim AS dependencies
COPY --from=uv /uv /usr/local/bin/uv
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
ARG EXTRAS=""
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
RUN if [ -n "$EXTRAS" ]; then \
      uv sync --locked --no-dev --no-install-project --extra mcp --extra cloud --extra "$EXTRAS"; \
    else \
      uv sync --locked --no-dev --no-install-project --extra mcp --extra cloud; \
    fi

FROM oven/bun:1.3.8 AS ui
WORKDIR /build/runtime-ui
COPY runtime-ui/package.json runtime-ui/bun.lock ./
RUN bun install --frozen-lockfile
COPY runtime-ui/ ./
COPY dashboard_runtime/web/ /build/dashboard_runtime/web/
RUN bun run build && bun run package:runtime

FROM python:3.11-slim
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PYTHON=/app/.venv/bin/python \
    MPLCONFIGDIR=/tmp/matplotlib \
    CHARTS_WORKSPACE=/data/projects \
    CHARTS_RUNTIME_ROOT=/data/runtime \
    CHARTS_HOST=0.0.0.0 \
    CHARTS_PORT=8000
WORKDIR /app
COPY --from=dependencies /app/.venv/ /app/.venv/
COPY dashboard_runtime/ dashboard_runtime/
COPY --from=ui /build/dashboard_runtime/web/dist/ dashboard_runtime/web/dist/
COPY skills/executive-charts/ skills/executive-charts/
COPY skills/analytical-reports/ skills/analytical-reports/
COPY bin/ bin/
COPY docs/ docs/
COPY package.json pyproject.toml uv.lock README.md ./
RUN useradd --system --uid 10001 --home-dir /data charts \
 && mkdir -p /data/projects /data/runtime && chown -R charts /data
USER charts
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('CHARTS_PORT','8000')+'/health',timeout=4)"
CMD ["python", "-m", "dashboard_runtime", "server"]
