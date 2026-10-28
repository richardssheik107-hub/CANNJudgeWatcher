"""One bounded GitHub Actions round with durable, non-forced state commits."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from .collector import poll
from .core import ContractError, dumps, utc
from .source import Client
from .profiles import PROFILES, get_profile
from .static_export import CONTEST_SLUG, ROOT, _collect, _write_site
from .store import Store

STATE_BRANCH = get_profile().state_branch  # Legacy import compatibility.
STATE_REF = 'refs/heads/' + STATE_BRANCH
MAX_DB_BYTES = 90 * 1024 * 1024
BOT_NAME = 'github-actions[bot]'
BOT_EMAIL = '41898282+github-actions[bot]@users.noreply.github.com'
STATE_README = '''# CANNJudgeWatcher persisted public observations

This branch is managed by the bounded GitHub Actions collector. It contains only
the consistent public contest database, its integrity/backoff metadata and this
notice. Snapshots are retained across runners. Updates never force-push or reset
Git history. An explicit successful history reset starts a fresh active database;
its parent commit remains recoverable. This is observed evidence, not an official
final ranking.
'''


class MonitorError(RuntimeError):
    """A safe diagnostic that excludes subprocess output and account details."""


def _git(repo, args, *, input_bytes=None):
    environment = os.environ.copy()
    environment.update({
        'GIT_TERMINAL_PROMPT': '0', 'GCM_INTERACTIVE': 'Never',
        'GIT_AUTHOR_NAME': BOT_NAME, 'GIT_AUTHOR_EMAIL': BOT_EMAIL,
        'GIT_COMMITTER_NAME': BOT_NAME, 'GIT_COMMITTER_EMAIL': BOT_EMAIL,
    })
    try:
        result = subprocess.run(
            ['git', '-c', 'user.name=' + BOT_NAME, '-c', 'user.email=' + BOT_EMAIL, *args],
            cwd=repo, input=input_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=environment, shell=False, timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise MonitorError('git operation unavailable or timed out; remote state was not changed') from error
    if result.returncode:
        raise MonitorError('git operation failed; remote state and published page were retained')
    return result.stdout


def _remote_head(repo, profile='starcup-final'):
    state_ref = get_profile(profile).state_ref
    output = _git(repo, ['ls-remote', '--heads', 'origin', state_ref]).decode('utf-8').strip()
    if not output:
        return None
    fields = output.split()
    if len(fields) != 2 or fields[1] != state_ref or not re.fullmatch(r'[0-9a-f]{40,64}', fields[0]):
        raise MonitorError('remote state ref could not be identified safely')
    _git(repo, ['fetch', '--depth=1', '--no-tags', 'origin', state_ref])
    head = _git(repo, ['rev-parse', '--verify', 'FETCH_HEAD^{commit}']).decode('ascii').strip()
    if not re.fullmatch(r'[0-9a-f]{40,64}', head):
        raise MonitorError('fetched state commit is invalid')
    return head


def _configuration(path, profile='starcup-final'):
    publication = get_profile(profile)
    config = json.loads(Path(path).read_text(encoding='utf-8'))
    if (not isinstance(config, dict) or config.get('transport') != 'http'
            or config.get('cookie_env') != '' or config.get('history_pages_per_poll') != 0
            or config.get('include') != [{'slug': publication.contest_slug}]
            or (publication.problem_ids and
                (config.get('problem_ids') != list(publication.problem_ids)
                 or config.get('verify_scoring_rules') is not True
                 or config.get('ranking_scope') != publication.ranking_scope))
            or (not publication.problem_ids and
                (config.get('problem_ids') or config.get('ranking_scope', 'contest') != 'contest'))):
        raise ContractError('GitHub collection requires the selected fixed public configuration without credentials/backfill')
    return config


def _reset_request_fields(raw):
    required = {'schema', 'request_id', 'expected_state_commit', 'expected_db_sha256', 'archive_ref'}
    optional = {'expected_db_bytes', 'expected_snapshot_count', 'expires_at'}
    if (not isinstance(raw, dict) or not required <= set(raw)
            or set(raw) - required - optional or type(raw.get('schema')) is not int or raw['schema'] != 1
            or not isinstance(raw.get('request_id'), str)
            or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', raw['request_id'])
            or not isinstance(raw.get('expected_state_commit'), str)
            or not re.fullmatch(r'(?:[0-9a-f]{40}|[0-9a-f]{64})', raw['expected_state_commit'])
            or not isinstance(raw.get('expected_db_sha256'), str)
            or not re.fullmatch(r'[0-9a-f]{64}', raw['expected_db_sha256'])
            or not isinstance(raw.get('archive_ref'), str)
            or not re.fullmatch(r'refs/(?:heads|tags)/[A-Za-z0-9][A-Za-z0-9._/-]*', raw['archive_ref'])
            or any(part in ('', '.', '..') or part.endswith('.lock')
                   for part in raw['archive_ref'].split('/'))
            or '..' in raw['archive_ref'] or raw['archive_ref'].endswith('.')
            or raw['archive_ref'] in {item.state_ref for item in PROFILES.values()}):
        raise ContractError('invalid one-shot reset request')
    for field in ('expected_db_bytes', 'expected_snapshot_count'):
        if field in raw and (type(raw[field]) is not int or raw[field] <= 0):
            raise ContractError('invalid one-shot reset request ' + field)
    out = dict(raw)
    if 'expires_at' in out:
        if not isinstance(out['expires_at'], str):
            raise ContractError('invalid one-shot reset request expiry')
        out['expires_at'] = utc(out['expires_at'])
    return out


def _load_reset_request(path):
    if path is None:
        return None
    with Path(path).open('rb') as stream:
        content = stream.read(16 * 1024 + 1)
    if len(content) > 16 * 1024:
        raise ContractError('one-shot reset request exceeds the size limit')
    try:
        return _reset_request_fields(json.loads(content))
    except (ValueError, UnicodeError) as error:
        if isinstance(error, ContractError):
            raise
        raise ContractError('invalid one-shot reset request JSON') from error


def _verify_reset_archive(repo, request):
    output = _git(repo, ['ls-remote', '--refs', 'origin', request['archive_ref']]).decode('ascii').strip()
    lines = output.splitlines()
    if len(lines) != 1 or lines[0].split() != [request['expected_state_commit'], request['archive_ref']]:
        raise ContractError('reset archive ref does not match the expected immutable state commit')


def _metadata(raw, *, now=None, profile='starcup-final'):
    publication = get_profile(profile)
    if (not isinstance(raw, dict) or type(raw.get('schema')) is not int or raw.get('schema') != 1
            or raw.get('contest_slug') != publication.contest_slug or 'not_before' not in raw
            or raw.get('profile', 'starcup-final') != publication.name
            or not isinstance(raw.get('db_sha256'), str)
            or not re.fullmatch(r'[0-9a-f]{64}', raw['db_sha256'])
            or type(raw.get('failure_count')) is not int or raw['failure_count'] < 0):
        raise ContractError('persisted state metadata is invalid')
    deadline = raw.get('not_before')
    if deadline is not None:
        if not isinstance(deadline, str) or utc(deadline) != deadline:
            raise ContractError('persisted backoff timestamp is invalid')
    if 'observation_epoch_started_at' in raw:
        started = raw['observation_epoch_started_at']
        try:
            if (not isinstance(started, str) or utc(started) != started
                    or started > utc(now)):
                raise ValueError('invalid observation epoch')
            if 'updated_at' in raw and (not isinstance(raw['updated_at'], str)
                    or utc(raw['updated_at']) != raw['updated_at'] or started > raw['updated_at']):
                raise ValueError('observation epoch exceeds its state update')
        except (ContractError, ValueError) as error:
            raise ContractError('persisted observation epoch timestamp is invalid or in the future') from error
    if 'last_completed_reset' in raw:
        receipt = raw['last_completed_reset']
        if not isinstance(receipt, dict) or not isinstance(receipt.get('completed_at'), str):
            raise ContractError('invalid completed reset receipt')
        _reset_request_fields({key: value for key, value in receipt.items() if key != 'completed_at'})
        completed = utc(receipt['completed_at'])
        if (completed != receipt['completed_at'] or completed > utc(now)
                or ('updated_at' in raw and completed > utc(raw['updated_at']))):
            raise ContractError('invalid completed reset receipt timestamp')
    return raw


def _readonly_backup(source: Path, destination: Path):
    if not source.is_file():
        raise ContractError('an existing live seed database is required')
    if destination.exists():
        raise ContractError('backup destination must be new')
    reader = sqlite3.connect('file:' + quote(source.resolve().as_posix(), safe='/:') + '?mode=ro', uri=True)
    writer = None
    try:
        reader.execute('PRAGMA query_only=ON')
        writer = sqlite3.connect(str(destination))
        reader.backup(writer)
    finally:
        if writer is not None:
            writer.close()
        reader.close()


def _checked_collection(path, poll_seconds, profile='starcup-final'):
    if path.stat().st_size >= MAX_DB_BYTES:
        raise ContractError('state database reached the 90 MiB safety limit')
    reader = sqlite3.connect('file:' + quote(path.resolve().as_posix(), safe='/:') + '?mode=ro', uri=True)
    try:
        reader.execute('PRAGMA query_only=ON')
        if reader.execute('SELECT COUNT(*) FROM snapshots WHERE imported<>0').fetchone()[0]:
            raise ContractError('operator-imported observations cannot initialize or enter automated public state')
    finally:
        reader.close()
    return (_collect(path, poll_seconds) if profile == 'starcup-final'
            else _collect(path, poll_seconds, profile=profile))


def _validate_database(path, poll_seconds, profile='starcup-final'):
    _, manifest, snapshot_count = _checked_collection(path, poll_seconds, profile)
    return snapshot_count, len(manifest['boards'])


def _candidate(repo, database, metadata_path, readme_path, parent, profile='starcup-final'):
    publication = get_profile(profile)
    blobs = []
    for name, path in [('README.md', readme_path), (publication.database_name, database), ('state.json', metadata_path)]:
        sha = _git(repo, ['hash-object', '-w', '--', str(path)]).decode('ascii').strip()
        if not re.fullmatch(r'[0-9a-f]{40,64}', sha):
            raise MonitorError('state blob could not be written safely')
        blobs.append(f'100644 blob {sha}\t{name}\n')
    tree = _git(repo, ['mktree'], input_bytes=''.join(blobs).encode('utf-8')).decode('ascii').strip()
    arguments = ['commit-tree', tree]
    if parent:
        arguments.extend(['-p', parent])
    message = ('Persist public ' + publication.name + ' observations and collector backoff\n').encode('ascii')
    commit = _git(repo, arguments, input_bytes=message).decode('ascii').strip()
    if not re.fullmatch(r'[0-9a-f]{40,64}', commit):
        raise MonitorError('state candidate commit is invalid')
    return commit


def monitor_round(work_dir, site_output, *, poll_seconds=600, push_state=False,
                  initialize=False, seed=None, reset_history=False, reset_request=None,
                  repo=None, config_path=None, now=None, profile='starcup-final') -> dict:
    """Prepare one round; publish readiness is granted only after state push succeeds.

    Initialization never contacts the contest. Its Git ref checks/push still use
    the configured origin so an existing persisted history cannot be replaced.
    Explicit history reset restores and validates that existing history, then
    polls a new database. Only a complete successful fresh collection can replace
    the active state; restored files and the Git parent remain recoverable.
    ``repo``, ``config_path`` and ``now`` support isolated, offline acceptance.
    """
    publication = get_profile(profile)
    work = Path(work_dir).resolve()
    site = Path(site_output).resolve()
    if work.exists() or work.is_symlink():
        raise ContractError('work directory must be new; previous round files are retained')
    if site.exists() or site.is_symlink():
        raise ContractError('site output must be new; the previous published site is retained')
    if (isinstance(poll_seconds, bool) or not isinstance(poll_seconds, int) or poll_seconds < 300):
        raise ContractError('poll_seconds must be an integer of at least 300')
    if not isinstance(reset_history, bool):
        raise ContractError('reset_history must be a boolean')
    if reset_history and (initialize or seed is not None):
        raise ContractError('history reset cannot be combined with initialization or a seed database')
    if reset_request is not None and (reset_history or initialize or seed is not None):
        raise ContractError('one-shot reset request cannot be combined with manual reset, initialization or a seed database')
    if bool(initialize) != bool(seed):
        raise ContractError('initialization requires both --initialize and an explicit --seed database')
    repository = Path(repo).resolve() if repo else ROOT
    config = _configuration(config_path or ROOT / 'config' / publication.config_name, profile)
    request = _load_reset_request(reset_request)
    current = utc(now) if now is not None else utc()
    work.mkdir(parents=True)
    report = {
        'status': 'PREPARING', 'snapshot_count_before': None, 'snapshot_count_after': None,
        'site_ready': False, 'state_changed': False, 'candidate_commit': None,
        'state_pushed': False, 'not_before': None, 'reset_history': reset_history,
        'reset_started_at': current if reset_history else None,
        'phase': 'restoring_state',
        'reset_request_id': request['request_id'] if request else None,
        'reset_request_status': 'pending' if request else None,
        'profile': publication.name, 'contest_slug': publication.contest_slug,
        'state_branch': publication.state_branch, 'database_name': publication.database_name,
    }

    def record():
        (work / 'report.json').write_text(dumps(report) + '\n', encoding='utf-8')

    try:
        parent = _remote_head(repository, profile)
        live = work / 'live.sqlite3'
        if initialize:
            if parent:
                raise ContractError('persisted state already exists; initialization cannot replace it')
            _readonly_backup(Path(seed).resolve(), live)
            metadata = {'failure_count': 0, 'not_before': None}
        else:
            if parent is None:
                raise ContractError('persisted state is missing; explicit initialization with a live seed is required')
            raw_meta = _git(repository, ['show', parent + ':state.json'])
            if len(raw_meta) > 64 * 1024:
                raise ContractError('persisted metadata exceeds the safety limit')
            metadata = _metadata(json.loads(raw_meta.decode('utf-8')), now=current, profile=profile)
            if request is not None:
                report['phase'] = 'validating_reset_request'
                receipt = metadata.get('last_completed_reset')
                if receipt and receipt['request_id'] == request['request_id']:
                    binding = {key: value for key, value in receipt.items() if key != 'completed_at'}
                    if binding != request:
                        raise ContractError('completed reset request ID has conflicting bindings')
                    report['reset_request_status'] = 'already-completed'
                else:
                    if request.get('expires_at') and current >= request['expires_at']:
                        raise ContractError('one-shot reset request has expired')
                    if (parent != request['expected_state_commit']
                            or metadata['db_sha256'] != request['expected_db_sha256']):
                        raise ContractError('one-shot reset request has stale state commit or database hash')
                    _verify_reset_archive(repository, request)
                    reset_history = True
                    report.update(reset_history=True, reset_started_at=current)
            report['phase'] = 'restoring_state'
            database_ref = parent + ':' + publication.database_name
            size = int(_git(repository, ['cat-file', '-s', database_ref]).decode('ascii').strip())
            if size >= MAX_DB_BYTES:
                raise ContractError('state database reached the 90 MiB safety limit')
            if request is not None and reset_history and request.get('expected_db_bytes', size) != size:
                raise ContractError('reset request database byte count does not match the archived state')
            restored = _git(repository, ['show', database_ref])
            if hashlib.sha256(restored).hexdigest() != metadata['db_sha256']:
                raise ContractError('persisted database SHA256 mismatch; previous state was not changed')
            restored_path = work / 'restored.sqlite3'
            with restored_path.open('xb') as stream:
                stream.write(restored)
            _readonly_backup(restored_path, live)

        report['phase'] = 'validating_restored'
        count, scope_count = _validate_database(live, poll_seconds, profile)
        if request is not None and reset_history:
            if request.get('expected_snapshot_count', count) != count:
                raise ContractError('reset request snapshot count does not match the archived state')
            # Recheck after complete archive validation, immediately before the
            # fresh poll. No mutable or mismatched archive can authorize reset.
            _verify_reset_archive(repository, request)
        report.update(snapshot_count_before=count, snapshot_count_after=count, scopes=scope_count)
        report.update(not_before=metadata['not_before'], failure_count=metadata['failure_count'])
        if not initialize and not reset_history and metadata['not_before'] and current < metadata['not_before']:
            report.update(status='WAITING', warning='durable retry/backoff deadline has not elapsed')
            report['phase'] = 'waiting'
            record()
            return report

        report['phase'] = 'polling'
        store = Store(str(work / 'reset.sqlite3' if reset_history else live))
        if initialize:
            outcome = {'status': 'INITIALIZED', 'retry_after': 0}
        else:
            client = Client(config)
            try:
                outcome = poll(store, client, config)
            finally:
                client.close()
        status = outcome['status']
        if status not in {'INITIALIZED', 'SUCCESS', 'PARTIAL', 'FAILED', 'SKIPPED'}:
            raise ContractError('collector returned an unknown round status')
        if reset_history:
            with store.connect() as db:
                fresh_count = db.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0]
            report.update(collection_status=status, snapshot_count_after=fresh_count)
            if status != 'SUCCESS' or not outcome.get('published') or fresh_count < 1:
                raise ContractError('history reset requires a successful complete fresh collection; previous state and page were retained')
            fresh_scopes = store.scopes()
            if len(fresh_scopes) != 1:
                raise ContractError('history reset requires exactly one complete public contest scope')
            fresh = store.snapshot(fresh_scopes[0]['id'])
            if fresh.get('source') != 'https://cannjudge.cn' or not fresh.get('observations'):
                raise ContractError('history reset requires nonempty public ranking evidence; previous state and page were retained')
        failures = 0 if status in {'INITIALIZED', 'SUCCESS', 'SKIPPED'} else metadata['failure_count'] + 1
        finished = utc(now) if now is not None else utc()
        if failures:
            retry = float(outcome.get('retry_after', 0))
            if not math.isfinite(retry) or retry < 0:
                raise ContractError('collector retry delay is invalid; previous persisted state was retained')
            delay = max(min(3600, poll_seconds * 2 ** min(failures, 5)), retry)
            deadline = (datetime.fromisoformat(finished) + timedelta(seconds=delay)).astimezone(timezone.utc).isoformat(timespec='microseconds')
        else:
            deadline = None
        backup = work / publication.database_name
        store.backup(str(backup))
        report['phase'] = 'validating_candidate'
        # Reuse this validated post-poll view for publication; do not render
        # the same immutable backup a third time. Never reuse the pre-poll view.
        collection = _checked_collection(backup, poll_seconds, profile)
        _, manifest, count = collection
        scope_count = len(manifest['boards'])
        state = {
            'schema': 1, 'contest_slug': publication.contest_slug, 'profile': publication.name,
            'db_sha256': hashlib.sha256(backup.read_bytes()).hexdigest(),
            'failure_count': failures, 'not_before': deadline,
            'updated_at': finished, 'last_status': status, 'snapshot_count': count,
        }
        if reset_history:
            state['observation_epoch_started_at'] = current
        elif 'observation_epoch_started_at' in metadata:
            state['observation_epoch_started_at'] = metadata['observation_epoch_started_at']
        if request is not None and reset_history:
            state['last_completed_reset'] = {**request, 'completed_at': finished}
        elif 'last_completed_reset' in metadata:
            state['last_completed_reset'] = metadata['last_completed_reset']
        state_path = work / 'state.json'
        state_path.write_text(dumps(state) + '\n', encoding='utf-8')
        readme = work / 'README.md'
        readme.write_text(STATE_README, encoding='utf-8')
        report['phase'] = 'preparing_site'
        _write_site(collection, site)
        commit = _candidate(repository, backup, state_path, readme, parent, profile)
        report.update(status=status, snapshot_count_after=count, scopes=scope_count,
                      state_changed=True, candidate_commit=commit, not_before=deadline,
                      failure_count=failures)
        if failures:
            report['warning'] = 'collection failed or was partial; previous complete boards were retained and retry/backoff was saved'
        if push_state:
            report['phase'] = 'pushing_state'
            _git(repository, ['push', 'origin', commit + ':' + publication.state_ref])
            report.update(state_pushed=True, site_ready=True)
            if request is not None and reset_history:
                report['reset_request_status'] = 'applied'
        report['phase'] = 'complete'
        record()
        return report
    except Exception as error:
        safe_message = str(error) if isinstance(error, (ContractError, MonitorError)) else type(error).__name__
        report.update(status='ERROR', site_ready=False, error=safe_message)
        record()
        raise


def main():
    parser = argparse.ArgumentParser(description='One durable public GitHub Actions collection round')
    parser.add_argument('--work-dir', required=True)
    parser.add_argument('--site-output', required=True)
    parser.add_argument('--poll-seconds', type=int, default=600)
    parser.add_argument('--push-state', action='store_true')
    parser.add_argument('--initialize', action='store_true')
    parser.add_argument('--seed')
    parser.add_argument('--reset-history', action='store_true', help='Start fresh active observations only after a successful public collection')
    parser.add_argument('--reset-request', help='Apply a guarded one-shot reset request, or append when its receipt already exists')
    parser.add_argument('--profile', choices=tuple(PROFILES), default='starcup-final')
    args = parser.parse_args()
    print(dumps(monitor_round(args.work_dir, args.site_output, poll_seconds=args.poll_seconds,
                             push_state=args.push_state, initialize=args.initialize, seed=args.seed,
                             reset_history=args.reset_history, reset_request=args.reset_request,
                             profile=args.profile)))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        safe_message = str(error) if isinstance(error, (ContractError, MonitorError)) else type(error).__name__
        print(dumps({'status': 'ERROR', 'site_ready': False, 'error': safe_message}), file=sys.stderr)
        raise SystemExit(1)
