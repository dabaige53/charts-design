"""Tencent SCF timer entry point; credentials come from the cloud environment."""


def main_handler(event, context):
    # Use refreshed execution-role credentials or CloudBase credential exchange.
    import json
    import os
    import time
    from dashboard_runtime.cloud_shares import cleanup_due
    from dashboard_runtime.cloud_storage import CosShareStorage

    if os.environ.get('TENCENTCLOUD_RUNENV') != 'SCF':
        raise RuntimeError('This cleanup handler must run in Tencent SCF')
    storage = CosShareStorage.from_environment()
    result = cleanup_due(storage)
    if result['failed']:
        print({'removed': result['removed'], 'failed': result['failed']})
        raise RuntimeError('Cloud share cleanup failed; jobs retained for retry')
    storage.put('cleaner-status.json', json.dumps({
        'executor': 'tencent-scf', 'completedAt': int(time.time()),
    }).encode(), 'application/json')
    return result
