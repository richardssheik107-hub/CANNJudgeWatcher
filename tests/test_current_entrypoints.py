"""User-facing commands without a profile select only the active contest."""
import json
import sys

from watcher import github_monitor, static_export


def test_monitor_cli_defaults_to_current_contest(monkeypatch, capsys):
    calls = []
    def prepare(work, site, **options):
        calls.append(options)
        return {'profile': options['profile'], 'site_ready': False}
    monkeypatch.setattr(github_monitor, 'monitor_round', prepare)
    monkeypatch.setattr(sys, 'argv', ['watcher.github_monitor', '--work-dir', 'new-work',
                                    '--site-output', 'new-site'])
    github_monitor.main()
    assert calls[0]['profile'] == 'jingdong-final'
    assert calls[0]['reset_history'] is False and calls[0]['initialize'] is False
    assert json.loads(capsys.readouterr().out)['profile'] == 'jingdong-final'


def test_static_export_cli_defaults_to_current_contest(monkeypatch, capsys):
    calls = []
    def publish(database, output, **options):
        calls.append(options)
        return {'profile': options['profile'], 'output': output}
    monkeypatch.setattr(static_export, 'export_site', publish)
    monkeypatch.setattr(sys, 'argv', ['watcher.static_export', '--db', 'current.sqlite3',
                                    '--output', 'new-site'])
    static_export.main()
    assert calls[0]['profile'] == 'jingdong-final'
    assert json.loads(capsys.readouterr().out)['profile'] == 'jingdong-final'
