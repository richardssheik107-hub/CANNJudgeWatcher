"""Static publication preserves live evidence and cannot overwrite source/history."""
import copy
import hashlib
import json
import re
from pathlib import Path

import httpx
import pytest

from watcher.core import ContractError, scope_id
from watcher.source import Client, collect_contest
from watcher.static_export import export_site, public_data
from watcher.store import Store


@pytest.fixture
def public_snapshot():
    schema = json.loads((Path(__file__).parent / 'fixtures' / 'public_starcup_schema.json').read_text(encoding='utf-8'))
    routes = {
        '/api/problems/public-problem': schema['problem'],
        '/api/problems/public-problem/ranking': schema['ranking'],
        '/api/submissions/contest/public-final/stats': schema['totals'],
    }
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=routes[request.url.path]))) as http:
        client = Client({'request_gap_seconds': 0, 'cookie_env': ''})
        client.http.close()
        client.http = http
        snapshot = collect_contest(client, schema['contests'][0], {})
    snapshot['observed_at'] = '2026-01-01T00:00:00.000000+00:00'
    return snapshot


def read_json(site, path):
    return json.loads((site / path).read_text(encoding='utf-8'))


def make_store(path, snapshot):
    store = Store(str(path))
    store.ingest(snapshot)
    return store


def test_real_schema(public_snapshot, tmp_path):
    database = tmp_path / 'live.sqlite3'
    store = make_store(database, public_snapshot)
    newer = copy.deepcopy(public_snapshot)
    newer['observed_at'] = '2026-01-01T00:10:00.000000+00:00'
    newer['observations'][0]['score'] = '70'
    newer['observations'][0]['raw']['score'] = 70
    newer['observations'][0]['submission_id'] = 'public-later-submission'
    newer['observations'][0]['raw']['submission_id'] = 'public-later-submission'
    newer['totals'][0]['score'] = '70'
    newer['totals'][0]['raw']['score'] = 70
    store.ingest(newer)
    run = store.start_run()
    store.finish_run(run, 'FAILED', {'errors': [{'error': 'public source HTTP 429; previous snapshot retained'}]})
    sid = scope_id(public_snapshot['scope'])
    expected = store.board(sid)
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    site = tmp_path / 'site'
    result = export_site(database, site)
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before
    manifest = read_json(site, '_data/manifest.json')
    assert result['snapshots'] == 2 and result['scopes'] == 1
    assert manifest['schema'] == 1 and manifest['poll_seconds'] == 600
    meta = read_json(site, manifest['scopes'])
    assert meta['scopes'] == store.scopes() and meta['collector_enabled'] is False
    board = read_json(site, manifest['boards'][sid])
    assert board == expected
    row, = board['rows']
    assert row['official_score'] == '70' and row['peak_score'] == '83.1' and row['gap'] == '13.1'
    assert row['official_rank'] is None
    history = read_json(site, manifest['history'][sid][row['team_key']])
    assert [p['total']['score'] for p in history['points']] == ['70', '83.1']
    assert history['next_before'] is None and history['total_points'] == 2
    assert read_json(site, manifest['archives'][sid][row['team_key']]) == {'rows': [], 'total': 0}
    evidence = read_json(site, manifest['evidence'][row['best'][0]['evidence_id']])
    assert evidence['observation']['result'][1]['testcase_status'] == 'Hidden'
    assert evidence['observation']['result'][1]['time'] is None
    assert evidence['observation']['score'] == '83.1'
    assert read_json(site, manifest['runs'])['runs'][0]['status'] == 'FAILED'
    lines = (site / manifest['export']).read_text(encoding='utf-8').splitlines()
    assert [json.loads(line) for line in lines] == [public_data(public_snapshot), public_data(newer)]
    assert 'data-mode="static"' in (site / 'index.html').read_text(encoding='utf-8')
    assert (site / 'static' / 'app.js').is_file() and (site / 'static' / 'style.css').is_file()


def test_safe_public_ids(public_snapshot, tmp_path):
    snapshot = copy.deepcopy(public_snapshot)
    raw_key = '../outside/队伍?query#fragment'
    marker = 'DO_NOT_PUBLISH_PRIVATE_PAYLOAD_99593'
    for row in snapshot['observations'] + snapshot['totals']:
        row['team_key'] = 'team:' + raw_key
        row['raw']['team']['_id'] = raw_key
        row['raw']['source_code'] = marker
        row['raw']['credentials'] = {'session_id': marker}
        row['raw']['team']['email'] = marker
    snapshot['payloads'].append({'source_code': marker, 'nested': {'solution_code': marker}})
    database = tmp_path / 'live.sqlite3'
    store = make_store(database, snapshot)
    site = tmp_path / 'site'
    export_site(database, site)
    manifest = read_json(site, '_data/manifest.json')
    sid = scope_id(snapshot['scope'])
    key = 'team:' + raw_key
    for group in ('history', 'archives'):
        relative = manifest[group][sid][key]
        assert re.fullmatch(r'_data/' + group + r'/[0-9a-f]{24}/[0-9a-f]{64}\.json', relative)
        assert (site / relative).resolve().is_relative_to(site.resolve())
    assert marker in json.dumps(store.board(sid))  # Source remains intact; publication is redacted.
    for file in site.rglob('*'):
        if file.is_file():
            assert marker.encode() not in file.read_bytes()
    assert read_json(site, manifest['boards'][sid])['rows'][0]['team_key'] == key


@pytest.mark.parametrize('change', ['demo', 'other_contest', 'corrupt_evidence', 'corrupt_snapshot'],
                         ids=['demo', 'other', 'evidence', 'snapshot'])
def test_input_retained(public_snapshot, tmp_path, change):
    database = tmp_path / 'live.sqlite3'
    store = make_store(database, public_snapshot)
    previous = tmp_path / 'previous'
    export_site(database, previous)
    old_files = {str(p.relative_to(previous)): p.read_bytes() for p in previous.rglob('*') if p.is_file()}
    if change in ('demo', 'other_contest'):
        invalid = copy.deepcopy(public_snapshot)
        if change == 'demo':
            invalid['scope']['demo'] = True
        else:
            invalid['scope']['stage'] = 'unselected-contest'
        store.ingest(invalid)
    elif change == 'corrupt_evidence':
        with store.connect() as db:
            db.execute("UPDATE evidence SET team_key='tampered-test-identity'")
    else:
        with store.connect() as db:
            db.execute("UPDATE snapshots SET digest='corrupt'")
    source_before = database.read_bytes()
    new = tmp_path / 'new-site'
    with pytest.raises(ContractError):
        export_site(database, new)
    assert not new.exists()
    assert database.read_bytes() == source_before
    assert {str(p.relative_to(previous)): p.read_bytes() for p in previous.rglob('*') if p.is_file()} == old_files
    assert not list(tmp_path.glob('.new-site-building-*'))


def test_paths_retained(public_snapshot, tmp_path):
    missing = tmp_path / 'missing.sqlite3'
    destination = tmp_path / 'site'
    with pytest.raises(ContractError):
        export_site(missing, destination)
    assert not missing.exists() and not destination.exists()
    database = tmp_path / 'live.sqlite3'
    make_store(database, public_snapshot)
    destination.mkdir()
    sentinel = destination / 'keep.txt'
    sentinel.write_text('retain this export', encoding='utf-8')
    before = database.read_bytes()
    with pytest.raises(ContractError, match='must not exist'):
        export_site(database, destination)
    assert sentinel.read_text(encoding='utf-8') == 'retain this export'
    assert database.read_bytes() == before


def test_history_full(public_snapshot, tmp_path):
    from datetime import datetime, timedelta, timezone
    store = Store(str(tmp_path / 'live.sqlite3'))
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(205):
        snapshot = copy.deepcopy(public_snapshot)
        snapshot['observed_at'] = (base + timedelta(minutes=i)).isoformat(timespec='microseconds')
        store.ingest(snapshot)
    site = tmp_path / 'site'
    export_site(store.path, site)
    manifest = read_json(site, '_data/manifest.json')
    sid = scope_id(public_snapshot['scope'])
    history = read_json(site, manifest['history'][sid]['team:public-team'])
    assert len(history['points']) == 200 and history['total_points'] == 205
    assert history['next_before'] == (base + timedelta(minutes=5)).isoformat(timespec='microseconds')
    assert history['full_export'] == manifest['export']
    assert len((site / manifest['export']).read_text(encoding='utf-8').splitlines()) == 205


def test_stage_retained(public_snapshot, tmp_path, monkeypatch):
    database = tmp_path / 'live.sqlite3'
    make_store(database, public_snapshot)
    before = database.read_bytes()
    destination = tmp_path / 'site'

    def failed_rename(self, target):
        raise OSError('simulated publication interruption')

    monkeypatch.setattr(Path, 'rename', failed_rename)
    with pytest.raises(OSError, match='interruption'):
        export_site(database, destination)
    assert not destination.exists() and database.read_bytes() == before
    staging, = tmp_path.glob('.site-building-*')
    assert (staging / '_data' / 'manifest.json').is_file()
    assert (staging / '_data' / 'snapshots.jsonl').is_file()


def test_archive_full(public_snapshot, tmp_path):
    database = tmp_path / 'live.sqlite3'
    store = make_store(database, public_snapshot)
    sid = scope_id(public_snapshot['scope'])
    with store.connect() as db:
        db.execute('''CREATE TABLE submission_archive(
          id TEXT PRIMARY KEY,scope_id TEXT NOT NULL,submission_id TEXT NOT NULL,
          team_key TEXT,problem_id TEXT,observed_at TEXT NOT NULL,data TEXT NOT NULL)''')
        for i in range(501):
            raw = {'_id': f'public-archived-{i}', 'status': 'Pass', 'source_code': 'PRIVATE_ARCHIVE_CODE_14683'}
            db.execute('INSERT INTO submission_archive VALUES(?,?,?,?,?,?,?)', (
                str(i), sid, raw['_id'], 'team:public-team', 'public-problem',
                '2026-01-01T00:00:00.000000+00:00', json.dumps(raw),
            ))
    before = database.read_bytes()
    site = tmp_path / 'site'
    export_site(database, site)
    manifest = read_json(site, '_data/manifest.json')
    archived = read_json(site, manifest['archives'][sid]['team:public-team'])
    assert archived['total'] == 501 and len(archived['rows']) == 501
    assert len({r['submission_id'] for r in archived['rows']}) == 501
    assert all('source_code' not in r['data'] for r in archived['rows'])
    assert database.read_bytes() == before


def test_consistent_view(public_snapshot, tmp_path, monkeypatch):
    from watcher.static_export import _ReadOnlyStore
    database = tmp_path / 'live.sqlite3'
    store = make_store(database, public_snapshot)
    newer = copy.deepcopy(public_snapshot)
    newer['observed_at'] = '2026-01-01T00:10:00.000000+00:00'
    newer['observations'][0]['score'] = '90'
    newer['observations'][0]['raw']['score'] = 90
    newer['totals'][0]['score'] = '90'
    newer['totals'][0]['raw']['score'] = 90
    original = _ReadOnlyStore.board

    def concurrent_poll(self, sid):
        store.ingest(newer)
        return original(self, sid)

    monkeypatch.setattr(_ReadOnlyStore, 'board', concurrent_poll)
    site = tmp_path / 'site'
    result = export_site(database, site)
    sid = scope_id(public_snapshot['scope'])
    manifest = read_json(site, '_data/manifest.json')
    board = read_json(site, manifest['boards'][sid])
    history = read_json(site, manifest['history'][sid]['team:public-team'])
    assert result['snapshots'] == board['snapshot_count'] == len(history['points']) == 1
    assert board['rows'][0]['peak_score'] == '83.1'
    assert store.board(sid)['rows'][0]['peak_score'] == '90'


@pytest.mark.parametrize('interval', [False, 0, 299, 300.0, '600'])
def test_poll_interval(tmp_path, interval):
    with pytest.raises(ContractError, match='poll_seconds'):
        export_site(tmp_path / 'absent.sqlite3', tmp_path / 'site', poll_seconds=interval)


def test_public_filter():
    assert public_data({'result': [{'testcase_status': 'Hidden', 'time': None}], 'score': '83.1',
                        'nested': {'Authorization': 'secret', 'source_code': 'private'}}) == {
        'result': [{'testcase_status': 'Hidden', 'time': None}], 'score': '83.1', 'nested': {},
    }
