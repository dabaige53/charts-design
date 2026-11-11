FROM python:3.10-slim AS package
WORKDIR /package
COPY deploy/tencent-cleaner/requirements.txt /build/requirements.txt
RUN apt-get update && apt-get install -y --no-install-recommends gcc
RUN pip install --no-cache-dir --target /package -r /build/requirements.txt
COPY deploy/tencent-cleaner/index.py /package/index.py
COPY dashboard_runtime/__init__.py dashboard_runtime/model.py dashboard_runtime/cloud_storage.py dashboard_runtime/cloud_shares.py dashboard_runtime/cloud_credentials.py /package/dashboard_runtime/
RUN python -c 'import pathlib,zipfile; output=zipfile.ZipFile("/cleaner.zip","w",zipfile.ZIP_DEFLATED); [output.write(path,path.relative_to("/package")) for path in pathlib.Path("/package").rglob("*") if path.is_file() and "__pycache__" not in path.parts]; output.close()'
FROM scratch
COPY --from=package /cleaner.zip /cleaner.zip
