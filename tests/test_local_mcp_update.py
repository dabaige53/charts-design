import importlib.util
from pathlib import Path
import tomllib

import pytest

spec = importlib.util.spec_from_file_location('update_local_mcp', Path(__file__).parents[1] / 'bin/update_local_mcp.py')
assert spec is not None and spec.loader is not None
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


@pytest.mark.parametrize('multiline', [False, True])
def test_only_chart_entry_changes(multiline):
    text = '''# Preserve comments and other servers
[mcp_servers.charts-design]
command = "/usr/local/bin/node"
args = ["/old/package/bin/dashboard-runtime.js", "--root", "/data/看板", "mcp"]
enabled = true

[mcp_servers.other]
command = "keep-me"
'''
    if multiline:
        text = text.replace('args = [', 'args = [\n').replace(', "--root"', ',\n"--root"')
    result = updater.replace_entry(text, Path('/new folder/package/bin/dashboard-runtime.js'))
    old, new = tomllib.loads(text), tomllib.loads(result)
    new['mcp_servers']['charts-design']['args'][0] = old['mcp_servers']['charts-design']['args'][0]
    assert old == new
    assert result.startswith('# Preserve comments')
    assert '/data/看板' in result


def test_unknown_entry_is_rejected():
    with pytest.raises(ValueError):
        updater.replace_entry('[mcp_servers.charts-design]\nargs=["other.js"]\n', Path('/new/bin/dashboard-runtime.js'))


