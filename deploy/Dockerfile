# Self-hosted Charts Design server with the shared React MCP application.
# Build from the repository root:  docker build -f deploy/Dockerfile -t charts-design .
# Optional Seaborn statistics:     docker build -f deploy/Dockerfile --build-arg EXTRAS=statistics -t charts-design .

FROM node:22-slim AS ui
WORKDIR /build
RUN corepack enable
COPY runtime-ui/package.json runtime-ui/pnpm-lock.yaml ./runtime-ui/
WORKDIR /build/runtime-ui
RUN pnpm install --frozen-lockfile
COPY runtime-ui/ ./
COPY dashboard_runtime/web/ /build/dashboard_runtime/web/
RUN pnpm build && pnpm package:runtime

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
COPY dashboard_runtime/ dashboard_runtime/
COPY --from=ui /build/dashboard_runtime/web/dist/ dashboard_runtime/web/dist/
COPY skills/executive-charts/ skills/executive-charts/
COPY skills/analytical-reports/ skills/analytical-reports/
COPY bin/ bin/
COPY docs/ docs/
COPY package.json pyproject.toml README.md ./
RUN useradd --system --uid 10001 --home-dir /data charts \
 && mkdir -p /data/projects /data/runtime && chown -R charts /data
USER charts
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('CHARTS_PORT','8000')+'/health',timeout=4)"
CMD ["python", "-m", "dashboard_runtime", "server"]
