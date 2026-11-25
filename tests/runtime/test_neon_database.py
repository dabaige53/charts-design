import asyncio
from contextlib import contextmanager
import types

import psycopg
import pytest

from deploy.neon import migrate
from dashboard_runtime.cloud_assets import AssetDatabase
from dashboard_runtime.cloud_database import CloudDatabase, cloud_enabled, neon_view_connections
from dashboard_runtime.model import DashboardError


@pytest.fixture
def driver(monkeypatch):
    monkeypatch.setenv('CHARTS_STORAGE_BACKEND', 'neon')
    monkeypatch.setenv('DATABASE_URL', 'postgresql://example.invalid/test')
    monkeypatch.delenv('CHARTS_DATABASE_BACKEND', raising=False)
    return monkeypatch


# @wu-test type=integration | scope=CloudDatabase/AssetDatabase | protects=数据库函数路由或参数被错误传递
def test_neon_function_routes_and_payload(driver):
    calls = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, query, params):
            action, project, payload = params
            calls.append((query.as_string(), (action, project, payload.obj)))

        def fetchone(self):
            return ({'ok': True},)

    class Connection(Cursor):
        def cursor(self):
            return Cursor()

    driver.setattr(psycopg, 'connect', lambda *args, **kwargs: Connection())
    assert cloud_enabled()
    assert CloudDatabase().call('ensure', 'project', config={'x': 1}) == {'ok': True}
    assert AssetDatabase().call('inventory', 'project') == {'ok': True}
    assert calls == [
        ('SELECT public."charts_runtime"(%s, %s, %s)', ('ensure', 'project', {'config': {'x': 1}})),
        ('SELECT public."charts_assets"(%s, %s, %s)', ('inventory', 'project', {})),
    ]


# @wu-test type=integration | scope=Neon 批注连接 | protects=鉴权和批注工作线程绕过连接池重新建连，或退出后使用已关闭连接池
def test_neon_view_pool_is_shared_through_worker_threads(driver):
    import psycopg_pool

    checkouts = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def cursor(self):
            return self

        def execute(self, query, params):
            self.result = 7 if "'readable'" in query else True

        def fetchone(self):
            return (self.result,)

    class Pool:
        def __init__(self, *args, **kwargs):
            self.connection_object = Connection()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.connection_object = None

        @contextmanager
        def connection(self):
            checkouts.append(self.connection_object)
            yield self.connection_object

    driver.setattr(psycopg_pool, 'ConnectionPool', Pool)
    direct = []
    driver.setattr(psycopg, 'connect', lambda *args, **kwargs: direct.append(True) or Connection())
    database = CloudDatabase()

    async def check():
        assert await asyncio.to_thread(database.call, 'generations_match', 'project', pages={'board': 0}) is True
        assert await asyncio.to_thread(database.call, 'display_revision', 'project', board='board') == 7

    with neon_view_connections():
        asyncio.run(check())
    assert len(checkouts) == 2 and checkouts[0] is checkouts[1]
    assert not direct
    assert database.call('display_revision', 'project', board='board') == 7
    assert len(direct) == 1


# @wu-test type=boundary | scope=CloudDatabase._call_neon | protects=暴露数据库错误和改变已有冲突错误语义
@pytest.mark.parametrize('exception,code,status', [
    ('REVISION_CONFLICT', 'REVISION_CONFLICT', 409),
    ('secret database detail', 'CLOUD_DATABASE_FAILED', 503),
])
def test_neon_errors_are_sanitized(driver, exception, code, status):
    def connect(*args, **kwargs):
        raise psycopg.Error(exception)

    driver.setattr(psycopg.Error, 'diag', property(lambda error: types.SimpleNamespace(message_primary=str(error))))
    driver.setattr(psycopg, 'connect', connect)
    with pytest.raises(DashboardError) as result:
        CloudDatabase().call('get', 'project')
    assert result.value.code == code
    assert result.value.status == status
    assert 'secret' not in str(result.value)


# @wu-test type=boundary | scope=deploy/neon/migrate | protects=迁移向 PUBLIC 授予执行权或依赖 CloudBase 角色
def test_migrations_preserve_isolated_runtime_role():
    for migration in migrate.MIGRATIONS.glob('*.sql'):
        converted = migrate.adapt(migration.read_text(), 'charts_app')
        assert 'auth.role()' not in converted
        assert 'anon,' not in converted
        assert 'authenticated' not in converted
        assert 'TO PUBLIC' not in converted.upper()
    with pytest.raises(ValueError):
        migrate.adapt('', 'public')
