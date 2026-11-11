"""Short-lived CloudBase credentials, refreshed in memory before expiry."""
import json
import re
import threading
import time
from functools import lru_cache
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .model import DashboardError, require


@lru_cache(maxsize=8)
def cloudbase_cos_client(region, environment, api_key, gateway_region):
    return CloudBaseCosClient(region, environment, api_key, gateway_region)


class CloudBaseCosClient:
    def __init__(self, region, environment, api_key, gateway_region):
        self.region = region
        self.environment, self.api_key, self.gateway_region = environment, api_key, gateway_region
        self.lock = threading.Lock()
        self.client = None
        self.refresh_at = 0

    def _current(self):
        with self.lock:
            if self.client is not None and time.monotonic() < self.refresh_at:
                return self.client
            environment, region = self.environment, self.gateway_region
            require(re.fullmatch(r'[a-zA-Z0-9-]+', environment) and
                    re.fullmatch(r'[a-z0-9-]+', region),
                    'Configure CloudBase environment and region', 'INVALID_CONFIG')
            request = Request(
                f'https://{environment}.{region}.tcb-api.tencentcloudapi.com/capi/credential',
                data=json.dumps({'env': environment}).encode(),
                headers={'Authorization': 'Bearer ' + self.api_key,
                         'Content-Type': 'application/json'})
            try:
                with urlopen(request, timeout=20) as response:
                    result = json.load(response)
            except (HTTPError, URLError, TimeoutError):
                raise DashboardError('CLOUD_CREDENTIAL_UNAVAILABLE',
                                     'CloudBase credential exchange failed', 503) from None
            require(result.get('code') == 0, 'CloudBase credential exchange was rejected',
                    'CLOUD_CREDENTIAL_UNAVAILABLE')
            from qcloud_cos import CosConfig, CosS3Client
            credential = result['data']
            self.client = CosS3Client(CosConfig(
                Region=self.region, SecretId=credential['TmpSecretId'],
                SecretKey=credential['TmpSecretKey'], Token=credential['Token'],
                Scheme='https', Timeout=30))
            # The documented credential lifetime is 30 minutes. Refresh at 20
            # minutes; requests already running keep their original client.
            self.refresh_at = time.monotonic() + 1200
            return self.client

    def __getattr__(self, name):
        return getattr(self._current(), name)
