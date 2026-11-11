"""CloudBase PostgreSQL access through its shared-instance HTTP gateway."""
from __future__ import annotations

import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .model import DashboardError, require


def cloud_enabled():
    backend = os.environ.get('CHARTS_STORAGE_BACKEND', 'local')
    require(backend in ('local', 'cloudbase'), 'Unknown CHARTS_STORAGE_BACKEND', 'INVALID_CONFIG')
    return backend == 'cloudbase'


class CloudDatabase:
    def __init__(self):
        environment = os.environ.get('CLOUDBASE_ENV_ID', '')
        require(re.fullmatch(r'[a-zA-Z0-9-]+', environment) is not None,
                'Configure CLOUDBASE_ENV_ID', 'INVALID_CONFIG')
        self.key = os.environ.get('CLOUDBASE_API_KEY', '')
        require(bool(self.key), 'Configure the server CloudBase API Key', 'INVALID_CONFIG')
        self.url = f'https://{environment}.api.tcloudbasegateway.com/v1/rdb/rest/rpc/charts_runtime'

    def call(self, action, project='', **payload):
        body = json.dumps({'action': action, 'project': project, 'payload': payload},
                          ensure_ascii=False, allow_nan=False).encode()
        request = Request(self.url, data=body, headers={
            'Authorization': 'Bearer ' + self.key, 'Content-Type': 'application/json'})
        try:
            with urlopen(request, timeout=60) as response:
                return json.load(response)
        except HTTPError as error:
            # Never expose gateway bodies, query data, or credential headers.
            raw = error.read()
            codes = {'REVISION_CONFLICT': 409, 'ANNOTATION_CONFLICT': 409,
                     'ALREADY_EXISTS': 409, 'NOT_FOUND': 404,
                     'DATA_CONFLICT': 409, 'DATA_INCOMPLETE': 409,
                     'INVALID_BATCH': 400}
            try:
                message = json.loads(raw).get('message', '')
            except (ValueError, AttributeError):
                message = ''
            if message in codes:
                raise DashboardError(message, message, codes[message]) from None
            raise DashboardError('CLOUD_DATABASE_FAILED',
                                 f'PostgreSQL gateway returned HTTP {error.code}', 503) from None
        except (URLError, TimeoutError):
            raise DashboardError('CLOUD_DATABASE_UNAVAILABLE',
                                 'PostgreSQL gateway is unavailable; no local fallback was used', 503) from None
