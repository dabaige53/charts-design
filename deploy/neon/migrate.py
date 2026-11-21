"""Apply the CloudBase migrations to a dedicated Neon database.

Set DATABASE_URL to a direct owner connection and CHARTS_NEON_RUNTIME_ROLE
to an existing, separate login role before running this file.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re

import psycopg
from psycopg import sql


MIGRATIONS = Path(__file__).resolve().parents[2] / 'cloudbase' / 'migrations'


def adapt(source, role):
    if not re.fullmatch(r'[a-z_][a-z0-9_]{0,62}', role) or role in ('public', 'anon', 'authenticated', 'service_role'):
        raise ValueError('CHARTS_NEON_RUNTIME_ROLE must name a separate PostgreSQL login role')
    source = source.replace("auth.role() IS DISTINCT FROM 'service_role'",
                            f"session_user IS DISTINCT FROM '{role}'")
    source = re.sub(r',\s*anon,\s*authenticated', '', source)
    source = re.sub(r'\bservice_role\b', role, source)
    return source


def migrate(connection, role):
    adapt('', role)
    with connection.transaction():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended('charts:neon:migrations', 0))")
            cursor.execute("""
                SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole,
                       pg_has_role(%s, current_user, 'MEMBER'), current_user = %s
                FROM pg_roles WHERE rolname = %s
            """, (role, role, role))
            role_info = cursor.fetchone()
            if not role_info or not role_info[0] or any(role_info[1:]):
                raise ValueError('Runtime role must be an existing unprivileged login, separate from the migration owner')
            cursor.execute('CREATE SCHEMA IF NOT EXISTS charts')
            cursor.execute('REVOKE ALL ON SCHEMA charts FROM PUBLIC')
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS charts.neon_migrations (
                    name text PRIMARY KEY, digest text NOT NULL, runtime_role text NOT NULL
                )
            """)
            cursor.execute('REVOKE ALL ON charts.neon_migrations FROM PUBLIC')
            cursor.execute('SELECT name, digest, runtime_role FROM charts.neon_migrations')
            applied = {name: (digest, runtime_role) for name, digest, runtime_role in cursor.fetchall()}
            files = sorted(MIGRATIONS.glob('*.sql'))
            if not files or set(applied) - {path.name for path in files}:
                raise ValueError('Migration files do not match the applied migration history')
            for path in files:
                source = path.read_text(encoding='utf-8')
                digest = hashlib.sha256(source.encode()).hexdigest()
                if path.name in applied:
                    if applied[path.name] != (digest, role):
                        raise ValueError(f'Migration or runtime role changed: {path.name}')
                    continue
                cursor.execute(adapt(source, role), prepare=False)
                cursor.execute('INSERT INTO charts.neon_migrations VALUES (%s, %s, %s)',
                               (path.name, digest, role))
            cursor.execute(sql.SQL('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA charts FROM PUBLIC'))


def main():
    database_url = os.environ['DATABASE_URL']
    role = os.environ['CHARTS_NEON_RUNTIME_ROLE']
    with psycopg.connect(database_url) as connection:
        migrate(connection, role)


if __name__ == '__main__':
    main()
