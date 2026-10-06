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
from .static_export import CONTEST_SLUG, ROOT, _collect, export_site
from .store import Store

STATE_BRANCH = 'watcher-state'
STATE_REF = 'refs/heads/' + STATE_BRANCH
MAX_DB_BYTES = 90 * 1024 * 1024
BOT_NAME = 'github-actions[bot]'
BOT_EMAIL = '41898282+github-actions[bot]@users.noreply.github.com'
STATE_README = '''# CANNJudgeWatcher persisted public observations

This branch is managed by the bounded GitHub Actions collector. It contains only
the consistent public contest database, its integrity/backoff metadata and this
notice. Snapshots are retained across runners. Updates never force-push or reset
history. This is observed evidence, not an official final ranking.
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


def _remote_head(repo):
    output = _git(repo, ['ls-remote', '--heads', 'origin', STATE_REF]).decode('utf-8').strip()
    if not output:
        return None
    fields = output.split()
    if len(fields) != 2 or fields[1] != STATE_REF or not re.fullmatch(r'[0-9a-f]{40,64}', fields[0]):
        raise MonitorError('remote state ref could not be identified safely')
    _git(repo, ['fetch', '--depth=1', '--no-tags', 'origin', STATE_REF])
    head = _git(repo, ['rev-parse', '--verify', 'FETCH_HEAD^{commit}']).decode('ascii').strip()
    if not re.fullmatch(r'[0-9a-f]{40,64}', head):
        raise MonitorError('fetched state commit is invalid')
    return head


def _configuration(path):
    config = json.loads(Path(path).read_text(encoding='utf-8'))
    if (not isinstance(config, dict) or config.get('transport') != 'http'
            or config.get('cookie_env') != '' or config.get('history_pages_per_poll') != 0
            or config.get('include') != [{'slug': CONTEST_SLUG}]):
        raise ContractError('GitHub collection requires the fixed public starcup configuration without credentials/backfill')
    return config


def _metadata(raw):
    if (not isinstance(raw, dict) or type(raw.get('schema')) is not int or raw.get('schema') != 1
            or raw.get('contest_slug') != CONTEST_SLUG or 'not_before' not in raw
            or not isinstance(raw.get('db_sha256'), str)
            or not re.fullmatch(r'[0-9a-f]{64}', raw['db_sha256'])
            or type(raw.get('failure_count')) is not int or raw['failure_count'] < 0):
        raise ContractError('persisted state metadata is invalid')
    deadline = raw.get('not_before')
    if deadline is not None:
        if not isinstance(deadline, str) or utc(deadline) != deadline:
            raise ContractError('persisted backoff timestamp is invalid')
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


def _validate_database(path, poll_seconds):
    if path.stat().st_size >= MAX_DB_BYTES:
        raise ContractError('state database reached the 90 MiB safety limit; collection stopped before polling')
    reader = sqlite3.connect('file:' + quote(path.resolve().as_posix(), safe='/:') + '?mode=ro', uri=True)
    try:
        reader.execute('PRAGMA query_only=ON')
        if reader.execute('SELECT COUNT(*) FROM snapshots WHERE imported<>0').fetchone()[0]:
            raise ContractError('operator-imported observations cannot initialize or enter automated public state')
    finally:
        reader.close()
    _, manifest, snapshot_count = _collect(path, poll_seconds)
    return snapshot_count, len(manifest['boards'])


def _candidate(repo, database, metadata_path, readme_path, parent):
    blobs = []
    for name, path in [('README.md', readme_path), ('starcup-final.sqlite3', database), ('state.json', metadata_path)]:
        sha = _git(repo, ['hash-object', '-w', '--', str(path)]).decode('ascii').strip()
        if not re.fullmatch(r'[0-9a-f]{40,64}', sha):
            raise MonitorError('state blob could not be written safely')
        blobs.append(f'100644 blob {sha}\t{name}\n')
    tree = _git(repo, ['mktree'], input_bytes=''.join(blobs).encode('utf-8')).decode('ascii').strip()
    arguments = ['commit-tree', tree]
    if parent:
        arguments.extend(['-p', parent])
    commit = _git(repo, arguments, input_bytes=b'Persist public starcup observations and collector backoff\n').decode('ascii').strip()
    if not re.fullmatch(r'[0-9a-f]{40,64}', commit):
        raise MonitorError('state candidate commit is invalid')
    return commit


def monitor_round(work_dir, site_output, *, poll_seconds=600, push_state=False,
                  initialize=False, seed=None, repo=None, config_path=None, now=None) -> dict:
    """Prepare one round; publish readiness is granted only after state push succeeds.

    Initialization never contacts the contest. Its Git ref checks/push still use
    the configured origin so an existing persisted history cannot be replaced.
    ``repo``, ``config_path`` and ``now`` support isolated, offline acceptance.
    """
    work = Path(work_dir).resolve()
    site = Path(site_output).resolve()
    if work.exists() or work.is_symlink():
        raise ContractError('work directory must be new; previous round files are retained')
    if site.exists() or site.is_symlink():
        raise ContractError('site output must be new; the previous published site is retained')
    if (isinstance(poll_seconds, bool) or not isinstance(poll_seconds, int) or poll_seconds < 300):
        raise ContractError('poll_seconds must be an integer of at least 300')
    if bool(initialize) != bool(seed):
        raise ContractError('initialization requires both --initialize and an explicit --seed database')
    repository = Path(repo).resolve() if repo else ROOT
    config = _configuration(config_path or ROOT / 'config' / 'monitor.starcup-final.json')
    current = utc(now) if now is not None else utc()
    work.mkdir(parents=True)
    report = {
        'status': 'PREPARING', 'snapshot_count_before': None, 'snapshot_count_after': None,
        'site_ready': False, 'state_changed': False, 'candidate_commit': None,
        'state_pushed': False, 'not_before': None,
    }

    def record():
        (work / 'report.json').write_text(dumps(report) + '\n', encoding='utf-8')

    try:
        parent = _remote_head(repository)
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
            metadata = _metadata(json.loads(raw_meta.decode('utf-8')))
            size = int(_git(repository, ['cat-file', '-s', parent + ':starcup-final.sqlite3']).decode('ascii').strip())
            if size >= MAX_DB_BYTES:
                raise ContractError('state database reached the 90 MiB safety limit; collection stopped before polling')
            restored = _git(repository, ['show', parent + ':starcup-final.sqlite3'])
            if hashlib.sha256(restored).hexdigest() != metadata['db_sha256']:
                raise ContractError('persisted database SHA256 mismatch; previous state was not changed')
            restored_path = work / 'restored.sqlite3'
            with restored_path.open('xb') as stream:
                stream.write(restored)
            _readonly_backup(restored_path, live)

        count, scope_count = _validate_database(live, poll_seconds)
        report.update(snapshot_count_before=count, snapshot_count_after=count, scopes=scope_count)
        report.update(not_before=metadata['not_before'], failure_count=metadata['failure_count'])
        if not initialize and metadata['not_before'] and current < metadata['not_before']:
            report.update(status='WAITING', warning='durable retry/backoff deadline has not elapsed')
            record()
            return report

        store = Store(str(live))
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
        backup = work / 'starcup-final.sqlite3'
        store.backup(str(backup))
        count, scope_count = _validate_database(backup, poll_seconds)
        state = {
            'schema': 1, 'contest_slug': CONTEST_SLUG,
            'db_sha256': hashlib.sha256(backup.read_bytes()).hexdigest(),
            'failure_count': failures, 'not_before': deadline,
            'updated_at': finished, 'last_status': status, 'snapshot_count': count,
        }
        state_path = work / 'state.json'
        state_path.write_text(dumps(state) + '\n', encoding='utf-8')
        readme = work / 'README.md'
        readme.write_text(STATE_README, encoding='utf-8')
        export_site(backup, site, poll_seconds=poll_seconds)
        commit = _candidate(repository, backup, state_path, readme, parent)
        report.update(status=status, snapshot_count_after=count, scopes=scope_count,
                      state_changed=True, candidate_commit=commit, not_before=deadline,
                      failure_count=failures)
        if failures:
            report['warning'] = 'collection failed or was partial; previous complete boards were retained and retry/backoff was saved'
        if push_state:
            _git(repository, ['push', 'origin', commit + ':' + STATE_REF])
            report.update(state_pushed=True, site_ready=True)
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
    args = parser.parse_args()
    print(dumps(monitor_round(args.work_dir, args.site_output, poll_seconds=args.poll_seconds,
                             push_state=args.push_state, initialize=args.initialize, seed=args.seed)))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        safe_message = str(error) if isinstance(error, (ContractError, MonitorError)) else type(error).__name__
        print(dumps({'status': 'ERROR', 'site_ready': False, 'error': safe_message}), file=sys.stderr)
        raise SystemExit(1)
