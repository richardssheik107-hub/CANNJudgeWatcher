"""Contest switches keep state refs, whole histories and publication identities apart."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from test_github_monitor import setup, git, initialize, no_client
from test_static_export import public_snapshot
from watcher import github_monitor as monitor
from watcher.core import ContractError
from watcher.profiles import get_profile
from watcher.static_export import export_site
from watcher.store import Store


@pytest.fixture
def jingdong_snapshot(public_snapshot):
    snapshot = copy.deepcopy(public_snapshot)
    profile = get_profile('jingdong-final')
    snapshot['scope'].update(contest_id=profile.contest_id, stage=profile.contest_slug,
                             ranking_scope='problem', epoch='jingdong-test')
    snapshot['scope']['problems'][0]['id'] = profile.problem_ids[0]
    for row in snapshot['observations']:
        row['problem_id'] = profile.problem_ids[0]
    for payload in snapshot['payloads']:
        if 'problem_id' in payload:
            payload['problem_id'] = profile.problem_ids[0]
    return snapshot


def new_config(root):
    path = root / 'jingdong-config.json'
    source = Path(__file__).resolve().parents[1] / 'config' / 'monitor.jingdong-final.json'
    path.write_bytes(source.read_bytes())
    return path


def new_seed(root, snapshot):
    seed = root / 'jingdong-seed.sqlite3'
    Store(str(seed)).ingest(snapshot)
    return seed


def new_round(setup, name, **options):
    return monitor.monitor_round(setup['root'] / name, setup['root'] / ('site-' + name),
                                 profile='jingdong-final', repo=setup['repo'],
                                 config_path=setup['root'] / 'jingdong-config.json', **options)


def test_separate_initialization_and_append_never_change_legacy_state(setup, jingdong_snapshot, monkeypatch):
    monkeypatch.setattr(monitor, 'Client', no_client)
    legacy = initialize(setup)
    old_bytes = git(setup['repo'], 'show', legacy['candidate_commit'] + ':starcup-final.sqlite3')
    new_config(setup['root'])
    seed = new_seed(setup['root'], jingdong_snapshot)
    original_seed = hashlib.sha256(seed.read_bytes()).hexdigest()
    first = new_round(setup, 'new-first', initialize=True, seed=seed, push_state=True)
    profile = get_profile('jingdong-final')
    assert first['snapshot_count_after'] == 1 and first['site_ready']
    assert git(setup['repo'], 'ls-tree', '--name-only', first['candidate_commit']).decode().splitlines() == [
        'README.md', 'jingdong-final.sqlite3', 'state.json',
    ]
    assert hashlib.sha256(seed.read_bytes()).hexdigest() == original_seed
    state = json.loads(git(setup['repo'], 'show', first['candidate_commit'] + ':state.json'))
    assert state['contest_slug'] == profile.contest_slug and state['profile'] == profile.name

    class OfflineClient:
        def __init__(self, config):
            assert config['problem_ids'] == list(profile.problem_ids)

        def close(self):
            pass

    def collect(store, client, config):
        later = copy.deepcopy(jingdong_snapshot)
        later['observed_at'] = '2026-01-01T00:10:00.000000+00:00'
        store.ingest(later)
        return {'status': 'SUCCESS', 'published': [{'snapshot_id': 2}], 'retry_after': 0}

    monkeypatch.setattr(monitor, 'Client', OfflineClient)
    monkeypatch.setattr(monitor, 'poll', collect)
    second = new_round(setup, 'new-second', push_state=True)
    assert second['snapshot_count_before'] == 1 and second['snapshot_count_after'] == 2
    assert git(setup['origin'], 'rev-list', '--count', profile.state_ref).strip() == b'2'
    assert git(setup['repo'], 'ls-remote', '--heads', 'origin', monitor.STATE_REF).decode().split()[0] == legacy['candidate_commit']
    assert git(setup['repo'], 'show', legacy['candidate_commit'] + ':starcup-final.sqlite3') == old_bytes
    manifest = json.loads((setup['root'] / 'site-new-second' / '_data' / 'manifest.json').read_text())
    assert manifest['contest_slug'] == profile.contest_slug and manifest['profile'] == profile.name
    reset = new_round(setup, 'new-reset', reset_history=True, push_state=True)
    assert reset['snapshot_count_before'] == 2 and reset['snapshot_count_after'] == 1
    assert git(setup['repo'], 'show', '-s', '--format=%P', reset['candidate_commit']).decode().strip() == second['candidate_commit']
    assert git(setup['repo'], 'ls-remote', '--heads', 'origin', monitor.STATE_REF).decode().split()[0] == legacy['candidate_commit']


def test_new_profile_cannot_initialize_from_old_contest_or_replace_existing_state(setup, jingdong_snapshot, monkeypatch):
    monkeypatch.setattr(monitor, 'Client', no_client)
    new_config(setup['root'])
    with pytest.raises(ContractError, match='selected non-demo'):
        new_round(setup, 'wrong-seed', initialize=True, seed=setup['seed'], push_state=True)
    profile = get_profile('jingdong-final')
    assert git(setup['repo'], 'ls-remote', '--heads', 'origin', profile.state_ref) == b''
    seed = new_seed(setup['root'], jingdong_snapshot)
    first = new_round(setup, 'first', initialize=True, seed=seed, push_state=True)
    with pytest.raises(ContractError, match='already exists'):
        new_round(setup, 'again', initialize=True, seed=seed, push_state=True)
    assert git(setup['repo'], 'ls-remote', '--heads', 'origin', profile.state_ref).decode().split()[0] == first['candidate_commit']


@pytest.mark.parametrize('change', ['slug', 'problem', 'ranking', 'rules', 'cookie', 'backfill'])
def test_fixed_new_profile_configuration_cannot_widen_selection(tmp_path, change):
    config_path = new_config(tmp_path)
    config = json.loads(config_path.read_text())
    changes = {
        'slug': {'include': [{'slug': 'ct_starcup_aiop_final'}]},
        'problem': {'problem_ids': ['6adb272d1dac5d235bd66d0b', 'another-problem']},
        'ranking': {'ranking_scope': 'contest'},
        'rules': {'verify_scoring_rules': False},
        'cookie': {'cookie_env': 'PRIVATE_COOKIE'},
        'backfill': {'history_pages_per_poll': 1},
    }
    config.update(changes[change])
    config_path.write_text(json.dumps(config))
    with pytest.raises(ContractError, match='selected fixed public configuration'):
        monitor._configuration(config_path, 'jingdong-final')


@pytest.mark.parametrize('change', ['contest', 'problem', 'ranking', 'mixed'])
def test_new_publication_rejects_other_identities_and_retains_database(tmp_path, jingdong_snapshot, public_snapshot, change):
    snapshot = copy.deepcopy(jingdong_snapshot)
    if change == 'contest':
        snapshot['scope']['contest_id'] = 'another-contest'
    elif change == 'problem':
        snapshot['scope']['problems'][0]['id'] = 'another-problem'
        for row in snapshot['observations']:
            row['problem_id'] = 'another-problem'
    elif change == 'ranking':
        snapshot['scope']['ranking_scope'] = 'contest'
    database = tmp_path / 'input.sqlite3'
    store = Store(str(database))
    store.ingest(snapshot)
    if change == 'mixed':
        store.ingest(public_snapshot)
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    site = tmp_path / 'site'
    with pytest.raises(ContractError, match='selected non-demo'):
        export_site(database, site, profile='jingdong-final')
    assert not site.exists()
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before


def test_metadata_and_unknown_profile_cannot_cross_contests(tmp_path):
    state = {'schema': 1, 'contest_slug': 'ct_starcup_aiop_final', 'db_sha256': 'a' * 64,
             'failure_count': 0, 'not_before': None}
    with pytest.raises(ContractError, match='metadata'):
        monitor._metadata(state, profile='jingdong-final')
    for unknown in ('../../watcher-state', '', None):
        with pytest.raises(ContractError, match='unknown public monitoring profile'):
            monitor.monitor_round(tmp_path / 'work', tmp_path / 'site', profile=unknown)
    assert not (tmp_path / 'work').exists()
