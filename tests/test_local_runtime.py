import asyncio
import json
import threading

import pytest

from watcher.app import create_app
from watcher.__main__ import main


def config_file(tmp_path, value):
    path = tmp_path / 'monitor.json'
    path.write_text(json.dumps(value), encoding='utf-8')
    return str(path)


@pytest.mark.parametrize('value', [[], ['monitor'], 'monitor', 1, None])
def test_config_must_be_an_object_before_database_creation(tmp_path, value):
    db = tmp_path / 'invalid.sqlite3'
    with pytest.raises(ValueError, match='configuration must be a JSON object'):
        create_app(str(db), config_file(tmp_path, value))
    assert not db.exists()


@pytest.mark.parametrize('value', ['broken', 'NaN', 'Infinity', 0, -1, True])
def test_invalid_poll_interval_fails_before_database_creation(tmp_path, value):
    db = tmp_path / 'invalid.sqlite3'
    with pytest.raises(ValueError, match='poll_seconds must be a finite positive number'):
        create_app(str(db), config_file(tmp_path, {'poll_seconds': value}), polling=True)
    assert not db.exists()


def test_serve_cli_does_not_create_database_for_invalid_configuration(tmp_path, monkeypatch):
    db = tmp_path / 'invalid-cli.sqlite3'
    config = config_file(tmp_path, ['invalid'])
    monkeypatch.setattr('sys.argv', ['watcher', '--db', str(db), '--config', config, 'serve'])
    with pytest.raises(ValueError, match='configuration must be a JSON object'):
        main()
    assert not db.exists()


def test_demo_cli_start_hint_uses_custom_database(tmp_path, monkeypatch, capsys):
    db = tmp_path / 'custom demo.sqlite3'
    monkeypatch.setattr('sys.argv', ['watcher', '--db', str(db), 'demo'])
    main()
    hint = capsys.readouterr().out
    assert f'python -m watcher --db "{db}" serve' in hint
    assert 'data/demo.sqlite3' not in hint


def test_invalid_client_configuration_fails_during_startup(tmp_path):
    app = create_app(str(tmp_path / 'startup.sqlite3'),
                     config_file(tmp_path, {'timeout_seconds': 'invalid'}), polling=True)
    reached_ready = []

    async def run():
        with pytest.raises(ValueError):
            async with app.router.lifespan_context(app):
                reached_ready.append(True)

    asyncio.run(run())
    assert not reached_ready


def test_collector_is_closed_when_lifespan_body_raises(tmp_path, monkeypatch):
    polled = threading.Event()
    closed = []

    class LocalClient:
        def __init__(self, config):
            pass

        def close(self):
            closed.append(True)

    def local_poll(store, client, config):
        polled.set()
        return {'status': 'SUCCESS', 'retry_after': 0}

    monkeypatch.setattr('watcher.app.Client', LocalClient)
    monkeypatch.setattr('watcher.app.poll', local_poll)
    app = create_app(str(tmp_path / 'lifespan.sqlite3'),
                     config_file(tmp_path, {'poll_seconds': 120}), polling=True)

    async def run():
        with pytest.raises(RuntimeError, match='lifespan body failed'):
            async with app.router.lifespan_context(app):
                assert await asyncio.to_thread(polled.wait, 2)
                raise RuntimeError('lifespan body failed')
        assert closed == [True]

    asyncio.run(run())


def test_same_app_can_start_collector_after_a_previous_shutdown(tmp_path, monkeypatch):
    calls = []
    closed = []

    class LocalClient:
        def __init__(self, config):
            pass

        def close(self):
            closed.append(True)

    def local_poll(store, client, config):
        calls.append(True)
        return {'status': 'SUCCESS', 'retry_after': 0}

    monkeypatch.setattr('watcher.app.Client', LocalClient)
    monkeypatch.setattr('watcher.app.poll', local_poll)
    app = create_app(str(tmp_path / 'restart.sqlite3'),
                     config_file(tmp_path, {'poll_seconds': 120}), polling=True)

    async def run():
        for expected in (1, 2):
            async with app.router.lifespan_context(app):
                async def wait_for_poll():
                    while len(calls) != expected:
                        await asyncio.sleep(.01)
                await asyncio.wait_for(wait_for_poll(), timeout=2)
        assert closed == [True, True]

    asyncio.run(run())
