"""Build and install this MCP into an already configured local workspace."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import tomllib


def replace_entry(text: str, entry: Path) -> str:
    config = tomllib.loads(text)
    current = config['mcp_servers']['charts-design']
    args = list(current['args'])
    if not args or Path(args[0]).name != 'dashboard-runtime.js':
        raise ValueError('现有 charts-design 入口不受支持，配置未修改')
    args[0] = str(entry)
    section = re.search(r'(?m)^\[mcp_servers\.charts-design\][^\n]*\n', text)
    if not section:
        raise ValueError('未找到 charts-design 配置段')
    following = re.search(r'(?m)^\[', text[section.end():])
    end = section.end() + following.start() if following else len(text)
    body = text[section.end():end]
    updated, count = re.subn(r'(?m)^args\s*=\s*\[[\s\S]*?\]', lambda _: 'args = ' + json.dumps(args, ensure_ascii=False), body, count=1)
    if count != 1:
        raise ValueError('无法安全更新入口，配置未修改')
    result = text[:section.end()] + updated + text[end:]
    parsed = tomllib.loads(result)
    expected = dict(current, args=args)
    if parsed['mcp_servers']['charts-design'] != expected:
        raise ValueError('更新影响了其他 MCP 字段，配置未修改')
    parsed['mcp_servers']['charts-design'] = current
    if parsed != config:
        raise ValueError('更新影响了其他配置，配置未修改')
    return result


async def smoke(entry: Path):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    with tempfile.TemporaryDirectory(prefix='charts-mcp-check-') as state:
        params = StdioServerParameters(command='node', args=[str(entry), '--root', state, 'mcp'], env=dict(os.environ))
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            if not {'dashboard_preview', 'dashboard_export'} <= names:
                raise ValueError('新安装包缺少必要的 MCP 工具')
            resources = await session.list_resources()
            app = next(item for item in resources.resources if str(item.uri).startswith('ui://'))
            contents = await session.read_resource(app.uri)
            if not contents.contents:
                raise ValueError('新安装包没有预览资源')
            return {'toolCount': len(names), 'resourceUri': str(app.uri)}


def update(workspace: Path):
    source = Path(__file__).resolve().parents[1]
    config_path = workspace.resolve() / '.codex/config.toml'
    previous = config_path.read_text()
    settings = tomllib.loads(previous)['mcp_servers']['charts-design']
    old_entry = Path(settings['args'][0]).resolve(strict=True)
    old_package = old_entry.parent.parent
    if json.loads((old_package / 'package.json').read_text())['name'] != 'charts-design':
        raise ValueError('现有安装目录不是 charts-design')
    if old_package == source:
        raise ValueError('当前 MCP 直接引用源码，不需要更新安装包')
    def run(*args):
        subprocess.run(list(args), cwd=source, check=True)
    run('npm', 'run', 'check')
    run('npm', '--prefix', 'runtime-ui', 'run', 'build')
    version = json.loads((source / 'package.json').read_text())['version']
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    release = old_package.parent.parent / ('charts-design-' + version + '-' + stamp)
    release.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix='charts-pack-') as staging:
        run('npm', 'pack', '--ignore-scripts', '--pack-destination', staging)
        archive = next(Path(staging).glob('*.tgz'))
        run('tar', '-xzf', str(archive), '-C', str(release))
    installed = release / 'package'
    environment = json.loads((source / '.charts-runtime-env.json').read_text())
    for key in ('dependencies', 'cache', 'browsers'):
        if environment.get(key):
            environment[key] = str((source / environment[key]).resolve())
    (installed / '.charts-runtime-env.json').write_text(json.dumps(environment, indent=2) + '\n')
    entry = installed / 'bin/dashboard-runtime.js'
    result = asyncio.run(smoke(entry))
    # Do not overwrite a concurrent edit to the target configuration.
    if config_path.read_text() != previous:
        raise ValueError('MCP 配置在构建时发生变化，已停止切换')
    updated = replace_entry(previous, entry)
    temporary = config_path.with_name('config.toml.charts-update-' + stamp)
    try:
        temporary.write_text(updated)
        temporary.chmod(config_path.stat().st_mode & 0o777)
        os.replace(temporary, config_path)
    finally:
        temporary.unlink(missing_ok=True)
    receipt = {'workspace': str(workspace.resolve()), 'oldEntry': str(old_entry), 'newEntry': str(entry),
               'mcpSmokeTest': result,
               'hostReload': 'pending; reconnect MCP and reopen preview'}
    (release / 'install-receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    update(parser.parse_args().workspace)
