FROM ghcr.io/astral-sh/uv:0.12.13 AS uv
FROM python:3.10-slim AS package
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /build
COPY pyproject.toml uv.lock README.md ./
ENV UV_PYTHON_DOWNLOADS=never
RUN apt-get update && apt-get install -y --no-install-recommends gcc
RUN uv export --locked --no-dev --extra cloud --no-emit-project --format requirements-txt --output-file /build/requirements.txt \
 && uv pip install --python /usr/local/bin/python --target /package --require-hashes -r /build/requirements.txt
WORKDIR /package
COPY deploy/tencent-cleaner/index.py /package/index.py
COPY dashboard_runtime/__init__.py dashboard_runtime/model.py dashboard_runtime/cloud_storage.py dashboard_runtime/cloud_shares.py dashboard_runtime/cloud_credentials.py /package/dashboard_runtime/
RUN python -c 'import pathlib,zipfile; output=zipfile.ZipFile("/cleaner.zip","w",zipfile.ZIP_DEFLATED); [output.write(path,path.relative_to("/package")) for path in pathlib.Path("/package").rglob("*") if path.is_file() and "__pycache__" not in path.parts]; output.close()'
FROM scratch
COPY --from=package /cleaner.zip /cleaner.zip
