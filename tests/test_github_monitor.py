"""Offline Git state acceptance: local origins and mocked public HTTP only."""
import copy
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from test_static_export import public_snapshot
from watcher import github_monitor as monitor
from watcher.core import ContractError, scope_id
from watcher.source import Client
from watcher.store import Store


def git(repo, *args):
    result = subprocess.run(['git', '-C', str(repo), *args], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, check=True, shell=False)
    return result.stdout


@pytest.fixture
def setup(tmp_path, public_snapshot):
    origin = tmp_path / 'o'
    repo = tmp_path / 'r'
    subprocess.run(['git', 'init', '--bare', str(origin)], capture_output=True, check=True)
    subprocess.run(['git', 'init', str(repo)], capture_output=True, check=True)
    git(repo, 'remote', 'add', 'origin', str(origin))
    seed = tmp_path / 'seed.sqlite3'
    Store(str(seed)).ingest(public_snapshot)
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({
        'transport': 'http', 'cookie_env': '', 'history_pages_per_poll': 0,
        'include': [{'slug': 'ct_starcup_aiop_final'}], 'request_gap_seconds': 0,
    }), encoding='utf-8')
    return {'root': tmp_path, 'repo': repo, 'origin': origin, 'seed': seed, 'config': config,
            'snapshot': public_snapshot}


def round_at(setup, name, **options):
    return monitor.monitor_round(setup['root'] / name, setup['root'] / ('s' + name),
                                 repo=setup['repo'], config_path=setup['config'], **options)


def initialize(setup, **options):
    return round_at(setup, 'w0', initialize=True, seed=setup['seed'], push_state=True, **options)


def no_client(config):
    raise AssertionError('public source must not be contacted')


def install_source(monkeypatch, *, score=70, limited=False):
    schema = json.loads((Path(__file__).parent / 'fixtures' / 'public_starcup_schema.json').read_text(encoding='utf-8'))
    schema['ranking']['rows'][0]['score'] = score
    schema['ranking']['rows'][0]['submission_id'] = 'public-score-' + str(score)
    schema['totals'][0]['score'] = score
    routes = {
        '/api/groups/public': schema['group'],
        '/api/contests/group/public-group': schema['contests'],
        '/api/problems/public-problem': schema['problem'],
        '/api/problems/public-problem/ranking': schema['ranking'],
        '/api/submissions/contest/public-final/stats': schema['totals'],
    }
    requests = []

    def handler(request):
        requests.append(request)
        assert request.method == 'GET' and 'cookie' not in request.headers
        if limited:
            return httpx.Response(429, headers={'Retry-After': '7200'})
        return httpx.Response(200, json=routes[request.url.path])

    monkeypatch.setattr(monitor, 'Client', lambda config: Client(config, transport=httpx.MockTransport(handler)))
    return requests


def remote_head(setup):
    return git(setup['repo'], 'ls-remote', '--heads', 'origin', monitor.STATE_REF).decode().split()[0]


def test_init_no_poll(setup, monkeypatch):
    monkeypatch.setattr(monitor, 'Client', no_client)
    before = setup['seed'].read_bytes()
    result = initialize(setup)
    assert result['status'] == 'INITIALIZED' and result['site_ready'] and result['state_pushed']
    assert result['snapshot_count_before'] == result['snapshot_count_after'] == 1
    assert setup['seed'].read_bytes() == before
    head = remote_head(setup)
    assert head == result['candidate_commit']
    assert git(setup['repo'], 'ls-tree', '--name-only', head).decode().splitlines() == [
        'README.md', 'starcup-final.sqlite3', 'state.json',
    ]
    assert git(setup['repo'], 'show', '-s', '--format=%an|%ae', head).decode().strip() == monitor.BOT_NAME + '|' + monitor.BOT_EMAIL


def test_two_rounds(setup, monkeypatch):
    initialize(setup)
    requests1 = install_source(monkeypatch, score=70)
    first = round_at(setup, 'w1', push_state=True)
    requests2 = install_source(monkeypatch, score=65)
    second = round_at(setup, 'w2', push_state=True)
    assert first['status'] == second['status'] == 'SUCCESS'
    assert first['snapshot_count_before'] == 1 and first['snapshot_count_after'] == 2
    assert second['snapshot_count_before'] == 2 and second['snapshot_count_after'] == 3
    assert first['site_ready'] and second['site_ready'] and len(requests1) == len(requests2) == 5
    store = Store(str(setup['root'] / 'w2' / 'starcup-final.sqlite3'))
    sid = scope_id(setup['snapshot']['scope'])
    board = store.board(sid)
    row, = board['rows']
    assert row['official_score'] == '65' and row['peak_score'] == '83.1'
    assert [p['total']['score'] for p in store.history(sid, row['team_key'])['points']] == ['65', '70', '83.1']
    # Runners fetch only the latest state boundary; the durable origin retains
    # the full parent chain after ordinary, non-forced pushes.
    assert git(setup['repo'], 'rev-parse', '--is-shallow-repository').decode().strip() == 'true'
    assert git(setup['repo'], 'rev-list', '--count', first['candidate_commit']).decode().strip() == '1'
    assert git(setup['origin'], 'rev-list', '--count', monitor.STATE_REF).decode().strip() == '3'
    assert json.loads((setup['root'] / 'w2' / 'state.json').read_text())['not_before'] is None


def test_initial_exists(setup, monkeypatch):
    initial = initialize(setup)
    monkeypatch.setattr(monitor, 'Client', no_client)
    with pytest.raises(ContractError, match='already exists'):
        round_at(setup, 'w1', initialize=True, seed=setup['seed'], push_state=True)
    assert remote_head(setup) == initial['candidate_commit']
    assert not (setup['root'] / 'sw1').exists()
    assert json.loads((setup['root'] / 'w1' / 'report.json').read_text())['site_ready'] is False


def test_missing_state(setup, monkeypatch):
    monkeypatch.setattr(monitor, 'Client', no_client)
    with pytest.raises(ContractError, match='explicit initialization'):
        round_at(setup, 'w0', push_state=True)
    assert git(setup['repo'], 'ls-remote', '--heads', 'origin', monitor.STATE_REF) == b''
    assert not (setup['root'] / 'sw0').exists()


@pytest.mark.parametrize('reset', [False, True], ids=['keep', 'reset'])
def test_hash_mismatch(setup, monkeypatch, reset):
    initial = initialize(setup)
    state_path = setup['root'] / 'bad-state.json'
    state = json.loads((setup['root'] / 'w0' / 'state.json').read_text())
    state['db_sha256'] = '0' * 64
    state_path.write_text(json.dumps(state), encoding='utf-8')
    commit = monitor._candidate(setup['repo'], setup['root'] / 'w0' / 'starcup-final.sqlite3',
                                state_path, setup['root'] / 'w0' / 'README.md', initial['candidate_commit'])
    git(setup['repo'], 'push', 'origin', commit + ':' + monitor.STATE_REF)
    monkeypatch.setattr(monitor, 'Client', no_client)
    with pytest.raises(ContractError, match='SHA256 mismatch'):
        round_at(setup, 'w1', push_state=True, reset_history=reset)
    assert remote_head(setup) == commit
    assert not (setup['root'] / 'w1' / 'live.sqlite3').exists()


def test_push_retained(setup, monkeypatch):
    first = initialize(setup)
    old_page = (setup['root'] / 'sw0' / 'index.html').read_bytes()
    install_source(monkeypatch, score=70)
    original = monitor._git
    attempted = []

    def refused(repo, args, **kwargs):
        if args[0] == 'push':
            attempted.append(args)
            raise monitor.MonitorError('simulated push rejection')
        return original(repo, args, **kwargs)

    monkeypatch.setattr(monitor, '_git', refused)
    with pytest.raises(monitor.MonitorError, match='rejection'):
        round_at(setup, 'w1', push_state=True)
    report = json.loads((setup['root'] / 'w1' / 'report.json').read_text())
    assert report['status'] == 'ERROR' and not report['site_ready'] and not report['state_pushed']
    assert report['candidate_commit'] and report['snapshot_count_after'] == 2
    assert attempted == [['push', 'origin', report['candidate_commit'] + ':' + monitor.STATE_REF]]
    assert remote_head(setup) == first['candidate_commit']
    assert (setup['root'] / 'sw0' / 'index.html').read_bytes() == old_page
    assert (setup['root'] / 'w1' / 'starcup-final.sqlite3').is_file()


def test_push_race(setup, monkeypatch):
    first = initialize(setup)
    install_source(monkeypatch, score=70)
    original = monitor._git
    competing = {}

    def concurrent_push(repo, args, **kwargs):
        if args[0] == 'push' and not competing:
            state = json.loads((setup['root'] / 'w0' / 'state.json').read_text())
            state['last_status'] = 'COMPETING_ROUND'
            path = setup['root'] / 'race-state.json'
            path.write_text(json.dumps(state), encoding='utf-8')
            competing['head'] = monitor._candidate(
                repo, setup['root'] / 'w0' / 'starcup-final.sqlite3', path,
                setup['root'] / 'w0' / 'README.md', first['candidate_commit'],
            )
            original(repo, ['push', 'origin', competing['head'] + ':' + monitor.STATE_REF])
        return original(repo, args, **kwargs)

    monkeypatch.setattr(monitor, '_git', concurrent_push)
    with pytest.raises(monitor.MonitorError, match='retained'):
        round_at(setup, 'w1', push_state=True)
    assert remote_head(setup) == competing['head']
    report = json.loads((setup['root'] / 'w1' / 'report.json').read_text())
    assert not report['site_ready'] and not report['state_pushed']
    assert report['candidate_commit'] != competing['head']


def test_durable_429(setup, monkeypatch):
    initial = initialize(setup)
    requests = install_source(monkeypatch, limited=True)
    current = datetime.now(timezone.utc)
    failed = round_at(setup, 'w1', push_state=True, now=current.isoformat())
    assert failed['status'] == 'FAILED' and failed['snapshot_count_after'] == 1 and failed['site_ready']
    assert len(requests) == 1 and failed['failure_count'] == 1
    assert datetime.fromisoformat(failed['not_before']) == current + timedelta(seconds=7200)
    head = remote_head(setup)
    assert head != initial['candidate_commit']
    monkeypatch.setattr(monitor, 'Client', no_client)
    waiting = round_at(setup, 'w2', push_state=True, now=(current + timedelta(seconds=3600)).isoformat())
    assert waiting['status'] == 'WAITING' and not waiting['site_ready'] and not waiting['state_changed']
    assert waiting['candidate_commit'] is None and waiting['snapshot_count_after'] == 1
    assert not (setup['root'] / 'sw2').exists() and remote_head(setup) == head
    install_source(monkeypatch, score=70)
    recovered = round_at(setup, 'w3', push_state=True, now=(current + timedelta(seconds=7201)).isoformat())
    assert recovered['status'] == 'SUCCESS' and recovered['snapshot_count_after'] == 2
    assert recovered['failure_count'] == 0 and recovered['not_before'] is None


def test_local_candidate(setup, monkeypatch):
    monkeypatch.setattr(monitor, 'Client', no_client)
    result = round_at(setup, 'w0', initialize=True, seed=setup['seed'])
    assert result['candidate_commit'] and result['state_changed']
    assert not result['site_ready'] and not result['state_pushed']
    assert git(setup['repo'], 'ls-remote', '--heads', 'origin', monitor.STATE_REF) == b''
    assert (setup['root'] / 'sw0' / 'index.html').is_file()


def test_import_rejected(setup, monkeypatch):
    seed = setup['root'] / 'imported.sqlite3'
    Store(str(seed)).ingest(setup['snapshot'], imported=True)
    monkeypatch.setattr(monitor, 'Client', no_client)
    with pytest.raises(ContractError, match='operator-imported'):
        round_at(setup, 'w0', initialize=True, seed=seed, push_state=True)
    assert git(setup['repo'], 'ls-remote', '--heads', 'origin', monitor.STATE_REF) == b''


@pytest.mark.parametrize('reset', [False, True], ids=['keep', 'reset'])
def test_size_stops_poll(setup, monkeypatch, reset):
    first = initialize(setup)
    monkeypatch.setattr(monitor, 'Client', no_client)
    monkeypatch.setattr(monitor, 'MAX_DB_BYTES', (setup['root'] / 'w0' / 'starcup-final.sqlite3').stat().st_size)
    with pytest.raises(ContractError, match='90 MiB'):
        round_at(setup, 'w1', push_state=True, reset_history=reset)
    assert remote_head(setup) == first['candidate_commit'] and not (setup['root'] / 'sw1').exists()


def test_config_rejected(setup, monkeypatch):
    config = json.loads(setup['config'].read_text())
    config['cookie_env'] = 'PRIVATE_ACCOUNT_COOKIE'
    setup['config'].write_text(json.dumps(config), encoding='utf-8')
    monkeypatch.setattr(monitor, 'Client', no_client)
    with pytest.raises(ContractError, match='without credentials'):
        initialize(setup)
    assert not (setup['root'] / 'w0').exists()


def test_old_paths_kept(setup, monkeypatch):
    initial = initialize(setup)
    before = (setup['root'] / 'w0' / 'report.json').read_bytes()
    monkeypatch.setattr(monitor, 'Client', no_client)
    with pytest.raises(ContractError, match='must be new'):
        round_at(setup, 'w0', push_state=True)
    assert (setup['root'] / 'w0' / 'report.json').read_bytes() == before
    assert remote_head(setup) == initial['candidate_commit']


@pytest.mark.parametrize('change', ['schema', 'count', 'deadline', 'missing'], ids=['s', 'c', 'd', 'm'])
def test_metadata(change):
    state = {'schema': 1, 'contest_slug': 'ct_starcup_aiop_final', 'db_sha256': 'a' * 64,
             'failure_count': 0, 'not_before': None}
    if change == 'schema':
        state['schema'] = True
    elif change == 'count':
        state['failure_count'] = -1
    elif change == 'deadline':
        state['not_before'] = 'tomorrow'
    else:
        state.pop('not_before')
    with pytest.raises(ContractError):
        monitor._metadata(state)


def test_reset_then_continue(setup, monkeypatch):
    initialize(setup)
    install_source(monkeypatch, score=70)
    previous = round_at(setup, 'w1', push_state=True)
    previous_db = git(setup['repo'], 'show', previous['candidate_commit'] + ':starcup-final.sqlite3')
    original_seed = setup['seed'].read_bytes()
    old_page = (setup['root'] / 'sw1' / 'index.html').read_bytes()
    install_source(monkeypatch, score=65)
    reset = round_at(setup, 'w2', reset_history=True, push_state=True)
    assert reset['status'] == 'SUCCESS' and reset['reset_history']
    assert reset['snapshot_count_before'] == 2 and reset['snapshot_count_after'] == 1
    assert reset['site_ready'] and reset['state_pushed']
    assert (setup['root'] / 'w2' / 'restored.sqlite3').read_bytes() == previous_db
    assert (setup['root'] / 'w2' / 'live.sqlite3').is_file()
    assert (setup['root'] / 'w2' / 'reset.sqlite3').is_file()
    assert setup['seed'].read_bytes() == original_seed
    assert (setup['root'] / 'sw1' / 'index.html').read_bytes() == old_page
    assert git(setup['origin'], 'show', previous['candidate_commit'] + ':starcup-final.sqlite3') == previous_db
    assert git(setup['origin'], 'show', '-s', '--format=%P', reset['candidate_commit']).decode().strip() == previous['candidate_commit']
    state = json.loads((setup['root'] / 'w2' / 'state.json').read_text())
    assert state['observation_epoch_started_at'] == reset['reset_started_at']
    fresh = Store(str(setup['root'] / 'w2' / 'starcup-final.sqlite3'))
    sid = fresh.scopes()[0]['id']
    assert [point['total']['score'] for point in fresh.history(sid, 'team:public-team')['points']] == ['65']
    assert fresh.board(sid)['rows'][0]['peak_score'] == '65'
    install_source(monkeypatch, score=60)
    continued = round_at(setup, 'w3', push_state=True)
    assert not continued['reset_history'] and continued['reset_started_at'] is None
    assert continued['snapshot_count_before'] == 1 and continued['snapshot_count_after'] == 2
    active = Store(str(setup['root'] / 'w3' / 'starcup-final.sqlite3'))
    sid = active.scopes()[0]['id']
    assert [point['total']['score'] for point in active.history(sid, 'team:public-team')['points']] == ['60', '65']
    assert active.board(sid)['rows'][0]['peak_score'] == '65'
    state2 = json.loads((setup['root'] / 'w3' / 'state.json').read_text())
    assert state2['observation_epoch_started_at'] == state['observation_epoch_started_at']


def test_reset_bypasses_old_backoff(setup, monkeypatch):
    initialize(setup)
    requests = install_source(monkeypatch, limited=True)
    current = datetime.now(timezone.utc)
    failed = round_at(setup, 'w1', push_state=True, now=current.isoformat())
    assert failed['failure_count'] == 1 and len(requests) == 1
    monkeypatch.setattr(monitor, 'Client', no_client)
    waiting = round_at(setup, 'w2', push_state=True, now=(current + timedelta(seconds=60)).isoformat())
    assert waiting['status'] == 'WAITING'
    requests = install_source(monkeypatch, score=65)
    reset = round_at(setup, 'w3', reset_history=True, push_state=True,
                     now=(current + timedelta(seconds=61)).isoformat())
    assert len(requests) == 5 and reset['status'] == 'SUCCESS'
    assert reset['not_before'] is None and reset['failure_count'] == 0
    assert reset['snapshot_count_before'] == reset['snapshot_count_after'] == 1


@pytest.mark.parametrize('status', ['FAILED', 'PARTIAL', 'SKIPPED'], ids=['f', 'p', 's'])
def test_reset_failure_keeps_state(setup, monkeypatch, status):
    original = initialize(setup)
    previous_db = git(setup['repo'], 'show', original['candidate_commit'] + ':starcup-final.sqlite3')
    old_page = (setup['root'] / 'sw0' / 'index.html').read_bytes()
    calls = []

    class OfflineClient:
        def __init__(self, config):
            pass

        def close(self):
            calls.append('closed')

    def incomplete_poll(store, client, config):
        calls.append('poll')
        if status == 'PARTIAL':
            # Even an accepted individual snapshot must not replace history if
            # the overall reset collection was only partial.
            store.ingest(copy.deepcopy(setup['snapshot']))
        return {'status': status, 'published': [{'snapshot_id': 1}] if status == 'PARTIAL' else [],
                'retry_after': 7200}

    monkeypatch.setattr(monitor, 'Client', OfflineClient)
    monkeypatch.setattr(monitor, 'poll', incomplete_poll)
    with pytest.raises(ContractError, match='successful complete fresh collection'):
        round_at(setup, 'w1', reset_history=True, push_state=True)
    assert calls == ['poll', 'closed']
    report = json.loads((setup['root'] / 'w1' / 'report.json').read_text())
    assert report['status'] == 'ERROR' and report['collection_status'] == status
    assert report['snapshot_count_before'] == 1
    assert report['snapshot_count_after'] == (1 if status == 'PARTIAL' else 0)
    assert not report['state_changed'] and not report['site_ready'] and not report['state_pushed']
    assert report['candidate_commit'] is None and report['reset_history']
    assert remote_head(setup) == original['candidate_commit']
    assert (setup['root'] / 'w1' / 'restored.sqlite3').read_bytes() == previous_db
    assert (setup['root'] / 'w1' / 'reset.sqlite3').is_file()
    assert not (setup['root'] / 'sw1').exists()
    assert (setup['root'] / 'sw0' / 'index.html').read_bytes() == old_page


def test_reset_actual_429(setup, monkeypatch):
    initial = initialize(setup)
    requests = install_source(monkeypatch, limited=True)
    with pytest.raises(ContractError, match='successful complete fresh collection'):
        round_at(setup, 'w1', reset_history=True, push_state=True)
    assert len(requests) == 1 and remote_head(setup) == initial['candidate_commit']
    report = json.loads((setup['root'] / 'w1' / 'report.json').read_text())
    assert report['snapshot_count_after'] == 0 and report['collection_status'] == 'FAILED'
    assert not report['site_ready'] and not (setup['root'] / 'sw1').exists()


@pytest.mark.parametrize('kind', ['empty', 'no-snapshot', 'no-publication', 'wrong-source'], ids=['e', 'n', 'p', 'o'])
def test_reset_false_success(setup, monkeypatch, kind):
    initial = initialize(setup)
    install_source(monkeypatch)

    def false_success(store, client, config):
        if kind != 'no-snapshot':
            snapshot = copy.deepcopy(setup['snapshot'])
            if kind == 'empty':
                snapshot.update(observations=[], totals=[])
            if kind == 'wrong-source':
                snapshot['source'] = 'https://example.invalid'
            store.ingest(snapshot)
        return {'status': 'SUCCESS', 'published': [] if kind == 'no-publication' else [{'snapshot_id': 1}]}

    monkeypatch.setattr(monitor, 'poll', false_success)
    with pytest.raises(ContractError, match='history reset requires'):
        round_at(setup, 'w1', reset_history=True, push_state=True)
    assert remote_head(setup) == initial['candidate_commit']
    assert not (setup['root'] / 'sw1').exists()


@pytest.mark.parametrize('options', [{'initialize': True, 'seed': 'unused'}, {'seed': 'unused'}], ids=['i', 's'])
def test_reset_conflicts(setup, monkeypatch, options):
    monkeypatch.setattr(monitor, 'Client', no_client)
    with pytest.raises(ContractError, match='cannot be combined'):
        round_at(setup, 'w0', reset_history=True, **options)
    assert not (setup['root'] / 'w0').exists()
    assert git(setup['repo'], 'ls-remote', '--heads', 'origin', monitor.STATE_REF) == b''


def test_reset_needs_state(setup, monkeypatch):
    monkeypatch.setattr(monitor, 'Client', no_client)
    with pytest.raises(ContractError, match='explicit initialization'):
        round_at(setup, 'w0', reset_history=True, push_state=True)
    assert not (setup['root'] / 'w0' / 'reset.sqlite3').exists()


def test_reset_push_failure(setup, monkeypatch):
    initial = initialize(setup)
    install_source(monkeypatch, score=65)
    original = monitor._git

    def refusal(repo, arguments, **options):
        if arguments[0] == 'push':
            assert arguments == ['push', 'origin', report_commit[0] + ':' + monitor.STATE_REF]
            raise monitor.MonitorError('reset candidate push rejected')
        result = original(repo, arguments, **options)
        if arguments[0] == 'commit-tree':
            report_commit.append(result.decode('ascii').strip())
        return result

    report_commit = []
    monkeypatch.setattr(monitor, '_git', refusal)
    with pytest.raises(monitor.MonitorError, match='push rejected'):
        round_at(setup, 'w1', reset_history=True, push_state=True)
    report = json.loads((setup['root'] / 'w1' / 'report.json').read_text())
    assert report['status'] == 'ERROR' and not report['site_ready'] and not report['state_pushed']
    assert report['candidate_commit'] == report_commit[0] and report['snapshot_count_after'] == 1
    assert remote_head(setup) == initial['candidate_commit']


def test_epoch_metadata():
    state = {'schema': 1, 'contest_slug': 'ct_starcup_aiop_final', 'db_sha256': 'a' * 64,
             'failure_count': 0, 'not_before': None}
    assert monitor._metadata(state) is state  # Older state remains supported.
    state['observation_epoch_started_at'] = '2026-01-01T00:00:00.000000+00:00'
    assert monitor._metadata(state) is state
    state['observation_epoch_started_at'] = 'tomorrow'
    with pytest.raises(ContractError, match='observation epoch'):
        monitor._metadata(state)
    state['observation_epoch_started_at'] = '2999-01-01T00:00:00.000000+00:00'
    with pytest.raises(ContractError, match='future'):
        monitor._metadata(state)
    state['observation_epoch_started_at'] = '2026-01-01T02:00:00.000000+00:00'
    state['updated_at'] = '2026-01-01T01:00:00.000000+00:00'
    with pytest.raises(ContractError, match='observation epoch'):
        monitor._metadata(state)
