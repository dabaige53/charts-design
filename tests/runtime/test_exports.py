from unittest.mock import patch

import pytest

from dashboard_runtime.exports import open_export
from dashboard_runtime.model import DashboardError


def test_open_only_a_managed_export(tmp_path):
    export_id = 'a' * 32
    file = tmp_path / 'exports' / export_id / 'board.pdf'
    file.parent.mkdir(parents=True)
    file.write_bytes(b'%PDF-1.4')
    with patch('dashboard_runtime.exports.sys.platform', 'darwin'), patch('dashboard_runtime.exports.subprocess.run') as run:
        for action, args in [('open', ['open', str(file)]), ('reveal', ['open', '-R', str(file)])]:
            assert open_export(tmp_path, 'board', export_id, 'pdf', action)['ok']
            assert run.call_args.args[0] == args
        run.reset_mock()
        for key in ('../' + export_id, '/tmp/file', '', export_id + ';open'):
            with pytest.raises(DashboardError):
                open_export(tmp_path, 'board', key, 'pdf', 'open')
        with pytest.raises(DashboardError):
            open_export(tmp_path, 'board', export_id, 'pdf', 'execute')
        run.assert_not_called()


def test_symlink_cannot_escape_export_directory(tmp_path):
    outside = tmp_path / 'private'
    outside.mkdir()
    (outside / 'board.pdf').write_bytes(b'%PDF-1.4')
    base = tmp_path / 'exports'
    base.mkdir()
    (base / ('b' * 32)).symlink_to(outside, target_is_directory=True)
    with patch('dashboard_runtime.exports.subprocess.run') as run, pytest.raises(DashboardError):
        open_export(tmp_path, 'board', 'b' * 32, 'pdf', 'open')
    run.assert_not_called()
