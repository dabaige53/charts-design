import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.request import Request, urlopen

import pytest

from dashboard_runtime.lifecycle import IdleLifetime
from dashboard_runtime.http_server import RuntimeHTTPServer
from dashboard_runtime.service import Service


# @wu-test type=behavior | scope=空闲生命周期 | protects=长请求结束后立即超时
def test_busy_request_gets_full_idle_grace_after_completion():
    now = [0]
    lifetime = IdleLifetime(60, lambda: now[0])
    with lifetime.activity():
        now[0] = 100
        assert not lifetime.expired()
    now[0] = 159
    assert not lifetime.expired()
    now[0] = 160
    assert lifetime.expired()


# @wu-test type=boundary | scope=空闲超时 | protects=非正数非有限超时使清理失效
@pytest.mark.parametrize('timeout', [0, -1, float('nan'), float('inf')])
def test_timeout_cannot_disable_default_cleanup(timeout):
    with pytest.raises(ValueError):
        IdleLifetime(timeout)


# @wu-test type=integration | scope=HTTP保活 | protects=保活时过早退出或退出丢数据 | debt=D9
def test_http_keepalive_then_shutdown_preserves_saved_state(tmp_path):
    service = Service(tmp_path)
    service.call('dashboard_create', {'dashboardId': 'retained'})
    server = RuntimeHTTPServer(service, 0, 'test', idle_timeout=0.3)
    thread = threading.Thread(target=lambda: server.serve_forever(0.01), daemon=True)
    thread.start()
    try:
        for _ in range(5):
            time.sleep(0.1)
            request = Request(f'http://127.0.0.1:{server.server_port}/api/tools/runtime_keepalive',
                              data=b'{}', headers={'Authorization': 'Bearer test', 'Content-Type': 'application/json'})
            with urlopen(request, timeout=2) as response:
                assert response.status == 200
            assert thread.is_alive()
        thread.join(2)
        assert not thread.is_alive()
        assert Service(tmp_path).store.get('retained')['revision'] == 1
    finally:
        if thread.is_alive():
            server.shutdown()
        server.server_close()
        thread.join()


# @wu-test type=integration | scope=MCP空闲退出 | protects=无请求MCP进程持续运行 | debt=D1
def test_real_mcp_process_exits_without_calls(tmp_path):
    pytest.importorskip('mcp')
    process = subprocess.Popen([sys.executable, '-m', 'dashboard_runtime', '--root', str(tmp_path),
                                'mcp', '--idle-timeout', '0.2'],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               cwd=Path(__file__).resolve().parents[2])
    try:
        assert process.wait(timeout=10) == 0
        assert process.stderr is not None and process.stdout is not None
        assert b'idle timeout' in process.stderr.read()
        assert process.stdout.read() == b''
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate()
