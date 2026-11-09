# Self-hosted Charts Design server: remote MCP (Streamable HTTP) + browser previews.
# Build from the repository root:  docker build -f deploy/Dockerfile -t charts-design .
# Optional Seaborn statistics:     docker build -f deploy/Dockerfile --build-arg EXTRAS=statistics -t charts-design .

FROM node:22-bookworm-slim AS ui
# The UI build extracts the original component engine with Python's stdlib.
RUN apt-get update && apt-get install -y --no-install-recommends python3 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY runtime-ui/package.json runtime-ui/package-lock.json runtime-ui/
RUN npm --prefix runtime-ui ci --no-audit --no-fund
COPY runtime-ui/ runtime-ui/
COPY dashboard_runtime/ dashboard_runtime/
COPY skills/executive-charts/ skills/executive-charts/
COPY skills/analytical-reports/ skills/analytical-reports/
COPY bin/ bin/
COPY docs/ docs/
COPY package.json pyproject.toml README.md ./
RUN PYTHON=python3 npm --prefix runtime-ui run build && rm -rf runtime-ui/node_modules

FROM python:3.11-slim
ARG EXTRAS=""
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    MPLCONFIGDIR=/tmp/matplotlib \
    CHARTS_WORKSPACE=/data/projects \
    CHARTS_RUNTIME_ROOT=/data/runtime \
    CHARTS_HOST=0.0.0.0 \
    CHARTS_PORT=8000
WORKDIR /app
RUN pip install --no-cache-dir 'mcp>=1.28,<2' \
 && if [ "$EXTRAS" = "statistics" ]; then pip install --no-cache-dir 'seaborn>=0.13.2,<0.14' 'matplotlib>=3.8,<4' 'pandas>=2.1,<3'; fi
COPY --from=ui /app /app
RUN useradd --system --uid 10001 --home-dir /data charts \
 && mkdir -p /data/projects /data/runtime && chown -R charts /data
USER charts
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('CHARTS_PORT','8000')+'/health',timeout=4)"
CMD ["python", "-m", "dashboard_runtime", "server"]
