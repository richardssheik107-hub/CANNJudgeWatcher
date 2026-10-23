"""One approved reset is consumed atomically, never inferred from capacity."""
import copy
import json
from datetime import datetime, timedelta, timezone

import pytest

from test_github_monitor import (git, initialize, install_source, no_client,
                                 remote_head, round_at, setup)
from test_static_export import public_snapshot
from watcher import github_monitor as monitor
from watcher.core import ContractError


def request_for(setup, *, name='request.json', **changes):
    head = remote_head(setup)
    meta = json.loads(git(setup['repo'], 'show', head + ':state.json'))
    ref = 'refs/heads/archive/test-reset'
    git(setup['repo'], 'push', 'origin', head + ':' + ref)
    request = {
        'schema': 1, 'request_id': 'approved-reset-1',
        'expected_state_commit': head, 'expected_db_sha256': meta['db_sha256'],
        'expected_db_bytes': int(git(setup['repo'], 'cat-file', '-s', head + ':starcup-final.sqlite3')),
        'expected_snapshot_count': meta['snapshot_count'], 'archive_ref': ref,
        'expires_at': (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(timespec='microseconds'),
    }
    request.update(changes)
    path = setup['root'] / name
    path.write_text(json.dumps(request), encoding='utf-8')
    return path, request


def test_request_resets_once_and_receipt_survives_expiry(setup, monkeypatch):
    initialize(setup)
    install_source(monkeypatch, score=70)
    previous = round_at(setup, 'before', push_state=True)
    old_bytes = git(setup['repo'], 'show', previous['candidate_commit'] + ':starcup-final.sqlite3')
    path, request = request_for(setup)
    install_source(monkeypatch, score=65)
    result = round_at(setup, 'reset', reset_request=path, push_state=True)
    assert result['reset_history'] and result['snapshot_count_before'] == 2
    assert result['snapshot_count_after'] == 1 and result['state_pushed']
    state = json.loads((setup['root'] / 'reset' / 'state.json').read_text())
    receipt = state['last_completed_reset']
    assert {key: receipt[key] for key in request} == request
    assert state['observation_epoch_started_at'] == result['reset_started_at']
    assert git(setup['origin'], 'show', request['archive_ref'] + ':starcup-final.sqlite3') == old_bytes
    assert git(setup['origin'], 'show', '-s', '--format=%P', result['candidate_commit']).decode().strip() == request['expected_state_commit']
    install_source(monkeypatch, score=60)
    later = (datetime.fromisoformat(request['expires_at']) + timedelta(seconds=1)).isoformat()
    continued = round_at(setup, 'continue', reset_request=path, push_state=True, now=later)
    assert not continued['reset_history'] and continued['snapshot_count_after'] == 2
    state2 = json.loads((setup['root'] / 'continue' / 'state.json').read_text())
    assert state2['last_completed_reset'] == receipt
    assert state2['observation_epoch_started_at'] == state['observation_epoch_started_at']


@pytest.mark.parametrize('change', [
    {'expected_state_commit': 'a' * 40}, {'expected_db_sha256': 'b' * 64},
    {'expected_db_bytes': 1}, {'expected_snapshot_count': 999},
    {'archive_ref': 'refs/heads/archive/missing'},
    {'expires_at': '2020-01-01T00:00:00.000000+00:00'},
])
def test_request_stale_or_unbacked_refuses_before_poll(setup, monkeypatch, change):
    original = initialize(setup)
    path, _ = request_for(setup, **change)
    monkeypatch.setattr(monitor, 'Client', no_client)
    with pytest.raises(ContractError):
        round_at(setup, 'refuse', reset_request=path, push_state=True)
    assert remote_head(setup) == original['candidate_commit']
    assert not (setup['root'] / 'srefuse').exists()


def test_archive_moved_refuses_before_poll(setup, monkeypatch):
    initialize(setup)
    path, request = request_for(setup)
    tree = git(setup['repo'], 'show', '-s', '--format=%T', request['expected_state_commit']).decode().strip()
    newer = monitor._git(setup['repo'], ['commit-tree', tree, '-p', request['expected_state_commit']], input_bytes=b'archive moved\n').decode().strip()
    git(setup['repo'], 'push', 'origin', newer + ':' + request['archive_ref'])
    monkeypatch.setattr(monitor, 'Client', no_client)
    with pytest.raises(ContractError):
        round_at(setup, 'moved', reset_request=path, push_state=True)
    assert remote_head(setup) == request['expected_state_commit']


def test_request_failure_keeps_receipt_unconsumed_then_retry_succeeds(setup, monkeypatch):
    original = initialize(setup)
    path, request = request_for(setup)
    requests = install_source(monkeypatch, limited=True)
    with pytest.raises(ContractError, match='successful complete fresh collection'):
        round_at(setup, 'limited', reset_request=path, push_state=True)
    assert len(requests) == 1 and remote_head(setup) == original['candidate_commit']
    assert 'last_completed_reset' not in json.loads(git(setup['repo'], 'show', remote_head(setup) + ':state.json'))
    assert not (setup['root'] / 'slimited').exists()
    install_source(monkeypatch, score=65)
    result = round_at(setup, 'retry', reset_request=path, push_state=True)
    assert result['reset_history'] and result['snapshot_count_after'] == 1


def test_request_dry_run_does_not_consume_remote(setup, monkeypatch):
    original = initialize(setup)
    path, _ = request_for(setup)
    install_source(monkeypatch, score=65)
    dry = round_at(setup, 'dry', reset_request=path)
    assert not dry['state_pushed'] and not dry['site_ready']
    assert remote_head(setup) == original['candidate_commit']
    live = round_at(setup, 'apply', reset_request=path, push_state=True)
    assert live['reset_history'] and live['state_pushed']


def test_request_conflicting_consumed_binding_refused(setup, monkeypatch):
    initialize(setup)
    path, request = request_for(setup)
    install_source(monkeypatch)
    result = round_at(setup, 'reset', reset_request=path, push_state=True)
    request['expected_snapshot_count'] += 1
    path.write_text(json.dumps(request))
    monkeypatch.setattr(monitor, 'Client', no_client)
    with pytest.raises(ContractError):
        round_at(setup, 'conflict', reset_request=path, push_state=True)
    assert remote_head(setup) == result['candidate_commit']


def test_request_does_not_relax_existing_capacity_guard(setup, monkeypatch):
    original = initialize(setup)
    path, request = request_for(setup)
    monkeypatch.setattr(monitor, 'Client', no_client)
    monkeypatch.setattr(monitor, 'MAX_DB_BYTES', request['expected_db_bytes'])
    with pytest.raises(ContractError, match='90 MiB'):
        round_at(setup, 'too-big', reset_request=path, push_state=True)
    assert remote_head(setup) == original['candidate_commit']


def test_oversize_fresh_candidate_is_not_committed_or_consumed(setup, monkeypatch):
    original = initialize(setup)
    path, request = request_for(setup)
    monkeypatch.setattr(monitor, 'MAX_DB_BYTES', request['expected_db_bytes'] + 4096)
    install_source(monkeypatch)

    def oversized(store, client, config):
        for index in range(50):
            snapshot = copy.deepcopy(setup['snapshot'])
            snapshot['observed_at'] = (datetime(2026, 1, 1, tzinfo=timezone.utc)
                                       + timedelta(minutes=index)).isoformat(timespec='microseconds')
            store.ingest(snapshot)
        return {'status': 'SUCCESS', 'published': [{'snapshot_id': 50}]}

    monkeypatch.setattr(monitor, 'poll', oversized)
    with pytest.raises(ContractError, match='90 MiB'):
        round_at(setup, 'new-too-big', reset_request=path, push_state=True)
    report = json.loads((setup['root'] / 'new-too-big' / 'report.json').read_text())
    assert report['phase'] == 'validating_candidate'
    assert not report['state_pushed'] and not report['site_ready']
    assert remote_head(setup) == original['candidate_commit']
    assert 'last_completed_reset' not in json.loads(git(setup['repo'], 'show', remote_head(setup) + ':state.json'))


@pytest.mark.parametrize('change', [
    {'schema': True}, {'schema': 2}, {'request_id': ''}, {'request_id': '../reset'},
    {'expected_state_commit': 'a' * 41}, {'expected_db_sha256': 'g' * 64},
    {'expected_db_bytes': True}, {'expected_snapshot_count': 0},
    {'archive_ref': monitor.STATE_REF}, {'archive_ref': 'refs/heads/a/../b'},
    {'unexpected': 'field'},
])
def test_invalid_request_schema_cannot_contact_source(setup, monkeypatch, change):
    original = initialize(setup)
    path, _ = request_for(setup, **change)
    monkeypatch.setattr(monitor, 'Client', no_client)
    with pytest.raises(ContractError):
        round_at(setup, 'malformed', reset_request=path, push_state=True)
    assert remote_head(setup) == original['candidate_commit']


def test_request_push_race_cannot_consume_or_replace_winner(setup, monkeypatch):
    initialize(setup)
    path, request = request_for(setup)
    install_source(monkeypatch)
    original_git = monitor._git
    competing = {}

    def race(repo, args, **kwargs):
        if args[:2] == ['push', 'origin'] and not competing:
            tree = git(setup['repo'], 'show', '-s', '--format=%T', request['expected_state_commit']).decode().strip()
            head = original_git(repo, ['commit-tree', tree, '-p', request['expected_state_commit']], input_bytes=b'competing writer\n').decode().strip()
            original_git(repo, ['push', 'origin', head + ':' + monitor.STATE_REF])
            competing['head'] = head
        return original_git(repo, args, **kwargs)

    monkeypatch.setattr(monitor, '_git', race)
    with pytest.raises(monitor.MonitorError):
        round_at(setup, 'race', reset_request=path, push_state=True)
    assert remote_head(setup) == competing['head']
    state = json.loads(git(setup['repo'], 'show', competing['head'] + ':state.json'))
    assert 'last_completed_reset' not in state
    monkeypatch.setattr(monitor, 'Client', no_client)
    with pytest.raises(ContractError):
        round_at(setup, 'stale-retry', reset_request=path, push_state=True)


@pytest.mark.parametrize('status', ['PARTIAL', 'FAILED', 'SKIPPED', 'SUCCESS'])
def test_request_incomplete_snapshot_never_consumes(setup, monkeypatch, status):
    original = initialize(setup)
    path, _ = request_for(setup)
    install_source(monkeypatch)

    def incomplete(store, client, config):
        if status == 'PARTIAL':
            store.ingest(copy.deepcopy(setup['snapshot']))
        return {'status': status, 'published': [{'snapshot_id': 1}] if status == 'PARTIAL' else []}

    monkeypatch.setattr(monitor, 'poll', incomplete)
    with pytest.raises(ContractError, match='successful complete fresh collection'):
        round_at(setup, 'incomplete', reset_request=path, push_state=True)
    assert remote_head(setup) == original['candidate_commit']
    assert not (setup['root'] / 'sincomplete').exists()
