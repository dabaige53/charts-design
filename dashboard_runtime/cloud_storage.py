"""Private Tencent COS storage for separately published, disposable shares."""
from __future__ import annotations

import json
import os

from .model import DashboardError, require


class CosShareStorage:
    def __init__(self, client, bucket, prefix='charts-shares/'):
        self.client, self.bucket = client, bucket
        self.prefix = prefix.rstrip('/') + '/'
        require(bool(prefix.strip('/')) and '..' not in prefix.split('/'),
                'Configure a dedicated non-empty COS share prefix', 'INVALID_CONFIG')

    @classmethod
    def from_environment(cls):
        names = ('CHARTS_COS_REGION', 'CHARTS_COS_BUCKET')
        require(all(os.environ.get(name) for name in names),
                'Configure CHARTS_COS_REGION and CHARTS_COS_BUCKET',
                'CLOUD_SHARE_NOT_CONFIGURED')
        try:
            from qcloud_cos import CosConfig, CosS3Client
        except ImportError as error:
            raise DashboardError('COS_NOT_INSTALLED', 'Install charts-design-runtime[cloud]') from error
        if os.environ.get('CLOUDBASE_API_KEY') and (
                not os.environ.get('TENCENTCLOUD_SECRETID') or os.environ.get('CHARTS_COS_AUTH') == 'cloudbase'):
            from .cloud_credentials import cloudbase_cos_client
            return cls(cloudbase_cos_client(os.environ['CHARTS_COS_REGION'],
                       os.environ.get('CLOUDBASE_ENV_ID', ''), os.environ['CLOUDBASE_API_KEY'],
                       os.environ.get('CLOUDBASE_REGION', os.environ['CHARTS_COS_REGION'])),
                       os.environ['CHARTS_COS_BUCKET'],
                       os.environ.get('CHARTS_COS_SHARE_PREFIX', 'charts-shares/'))
        require(os.environ.get('TENCENTCLOUD_SECRETID') and os.environ.get('TENCENTCLOUD_SECRETKEY'),
                'Configure Tencent runtime credentials or CloudBase service credentials',
                'CLOUD_SHARE_NOT_CONFIGURED')
        config = CosConfig(Region=os.environ['CHARTS_COS_REGION'],
                           SecretId=os.environ['TENCENTCLOUD_SECRETID'],
                           SecretKey=os.environ['TENCENTCLOUD_SECRETKEY'],
                           Token=os.environ.get('TENCENTCLOUD_SESSIONTOKEN'),
                           Scheme='https', Timeout=30)
        return cls(CosS3Client(config), os.environ['CHARTS_COS_BUCKET'],
                   os.environ.get('CHARTS_COS_SHARE_PREFIX', 'charts-shares/'))

    def check_private(self):
        """Do not publish a code-protected share into a publicly readable bucket."""
        acl = self.client.get_bucket_acl(Bucket=self.bucket)
        require(acl.get('CannedACL') == 'private',
                'Cloud shares require a private COS bucket', 'COS_BUCKET_NOT_PRIVATE')
        from qcloud_cos.cos_exception import CosServiceError
        try:
            policy = self.client.get_bucket_policy(Bucket=self.bucket)
        except CosServiceError as error:
            if error.get_error_code() != 'NoSuchBucketPolicy':
                raise
            return
        policy = policy.get('Policy', policy)
        if isinstance(policy, str):
            policy = json.loads(policy)
        statements = policy.get('Statement', policy.get('statement', []))
        for statement in statements:
            if statement.get('Effect', statement.get('effect', '')).lower() != 'allow':
                continue
            principal = statement.get('Principal', statement.get('principal', {}))
            values = principal.values() if isinstance(principal, dict) else [principal]
            public = any(value == '*' or isinstance(value, list) and '*' in value for value in values)
            require(not public, 'Remove public allow policies from the share bucket',
                    'COS_BUCKET_NOT_PRIVATE')

    def put(self, key, content, content_type='application/octet-stream'):
        self.client.put_object(Bucket=self.bucket, Key=self.prefix + key, Body=content,
                               ACL='private', ContentType=content_type,
                               CacheControl='private, no-store, max-age=0',
                               ServerSideEncryption='AES256')

    def get(self, key):
        from qcloud_cos.cos_exception import CosServiceError
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=self.prefix + key)
        except CosServiceError as error:
            if error.get_error_code() in ('NoSuchKey', 'NoSuchVersion'):
                return None
            raise
        stream = response['Body'].get_raw_stream()
        try:
            return stream.read()
        finally:
            stream.close()

    def list(self, prefix):
        marker = ''
        while True:
            response = self.client.list_objects(Bucket=self.bucket, Prefix=self.prefix + prefix,
                                                Marker=marker, MaxKeys=1000)
            for entry in response.get('Contents', []):
                yield entry['Key'][len(self.prefix):]
            if str(response.get('IsTruncated', 'false')).lower() != 'true':
                break
            marker = response['NextMarker']

    def delete_prefix(self, prefix):
        """Delete physical versions and delete markers, not only visible objects."""
        full = self.prefix + prefix
        while True:
            response = self.client.list_objects_versions(Bucket=self.bucket, Prefix=full, MaxKeys=1000)
            entries = [*response.get('Version', []), *response.get('DeleteMarker', [])]
            if not entries:
                break
            objects = [{'Key': entry['Key'], 'VersionId': entry['VersionId']} for entry in entries]
            result = self.client.delete_objects(Bucket=self.bucket, Delete={'Quiet': 'true', 'Object': objects})
            require(not result.get('Error'), 'COS version deletion failed; cleanup will retry', 'COS_DELETE_FAILED')
        # Unversioned buckets can return an empty version listing. Check visible
        # objects too; the prefix remains confined to this publication.
        while True:
            response = self.client.list_objects(Bucket=self.bucket, Prefix=full, MaxKeys=1000)
            objects = [{'Key': entry['Key']} for entry in response.get('Contents', [])]
            if not objects:
                break
            result = self.client.delete_objects(Bucket=self.bucket, Delete={'Quiet': 'true', 'Object': objects})
            require(not result.get('Error'), 'COS object deletion failed; cleanup will retry', 'COS_DELETE_FAILED')

    def size_prefix(self, prefix):
        total, marker = 0, ''
        while True:
            response = self.client.list_objects(Bucket=self.bucket, Prefix=self.prefix + prefix,
                                                Marker=marker, MaxKeys=1000)
            total += sum(int(entry.get('Size', 0)) for entry in response.get('Contents', []))
            if str(response.get('IsTruncated', 'false')).lower() != 'true':
                return total
            marker = response['NextMarker']
