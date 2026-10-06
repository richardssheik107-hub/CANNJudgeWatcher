"""Publish a consistent public SQLite view as a new, self-contained static site.

The source is opened read-only. Existing destinations and failed staging folders
are retained; no cleanup, database initialization, or network access is performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import tempfile
import zlib
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote

from .collector import archive_rows
from .core import ContractError, clean, digest, dumps, observation, scope_id, utc, validate_snapshot
from .store import Store

CONTEST_SLUG = 'ct_starcup_aiop_final'
ROOT = Path(__file__).resolve().parent.parent
EXTRA_PRIVATE_KEYS = frozenset({
    'source_code', 'sourcecode', 'solution', 'solution_code', 'original_code',
    'file_content', 'credentials', 'credential', 'session_id', 'csrf_token',
    'cookie_header', 'email', 'phone', 'mobile', 'telephone',
})


def public_data(value):
    """Recheck stored evidence before putting it on a publicly accessible site."""
    value = clean(value)
    if isinstance(value, dict):
        return {k: public_data(v) for k, v in value.items() if str(k).lower() not in EXTRA_PRIVATE_KEYS}
    if isinstance(value, list):
        return [public_data(v) for v in value]
    return value


class _SharedView:
    """Let existing Store read methods share one SQLite read transaction."""
    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, parameters=()):
        # Store.board begins its own read transaction. Our outer transaction is
        # already pinned, so avoid restarting it or committing between methods.
        if sql.strip().upper() == 'BEGIN' and self.connection.in_transaction:
            return self.connection.execute('SELECT 1')
        return self.connection.execute(sql, parameters)


class _ReadOnlyStore(Store):
    def __init__(self, path, connection):
        self.path = str(path)
        self.view = _SharedView(connection)

    @contextmanager
    def connect(self):
        yield self.view


def _json_file(files, path, value):
    files[path] = (dumps(public_data(value)) + '\n').encode('utf-8')


def _collect(db_path: Path, poll_seconds: int):
    if not db_path.is_file():
        raise ContractError('existing live database is required; no database was created')
    connection = sqlite3.connect('file:' + quote(db_path.as_posix(), safe='/:') + '?mode=ro', uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute('PRAGMA query_only=ON')
        connection.execute('BEGIN')
        if connection.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise ContractError('database integrity check failed')
        if connection.execute('PRAGMA user_version').fetchone()[0] != 1:
            raise ContractError('unsupported database version')
        store = _ReadOnlyStore(db_path, connection)
        scopes = store.scopes()
        if not scopes:
            raise ContractError('at least one complete live snapshot is required')
        if connection.execute('SELECT COUNT(*) FROM scopes').fetchone()[0] != len(scopes):
            raise ContractError('scope without complete snapshots cannot be published')
        by_scope = {}
        for scope in scopes:
            sid = scope['id']
            if (scope.get('demo') is not False or scope.get('stage') != CONTEST_SLUG
                    or not re.fullmatch(r'[0-9a-f]{24}', sid) or scope_id(scope) != sid):
                raise ContractError('only non-demo ct_starcup_aiop_final scopes may be published')
            by_scope[sid] = scope

        snapshots = []
        expected_evidence = {}
        for row in connection.execute('SELECT * FROM snapshots ORDER BY observed_at,id'):
            snapshot = validate_snapshot(json.loads(zlib.decompress(row['data'])))
            sid = scope_id(snapshot['scope'])
            if (sid not in by_scope or sid != row['scope_id'] or digest(snapshot) != row['digest']
                    or snapshot['observed_at'] != row['observed_at']
                    or snapshot['scope'].get('demo') is not False
                    or snapshot['scope'].get('stage') != CONTEST_SLUG):
                raise ContractError('invalid or unrelated stored snapshot; nothing was published')
            snapshots.append(snapshot)
            for record in snapshot['observations']:
                eid = digest({'scope': sid, 'row': record})
                expected = expected_evidence.setdefault(eid, {
                    'scope_id': sid, 'record': record, 'snapshot_id': row['id'],
                    'first_seen': row['observed_at'], 'last_seen': row['observed_at'],
                })
                expected['last_seen'] = row['observed_at']
        if not snapshots:
            raise ContractError('at least one complete live snapshot is required')

        evidences = []
        for row in connection.execute('SELECT * FROM evidence ORDER BY id'):
            record = json.loads(row['data'])
            expected = expected_evidence.pop(row['id'], None)
            if (expected is None or row['scope_id'] not in by_scope
                    or not re.fullmatch(r'[0-9a-f]{64}', row['id'])
                    or row['id'] != digest({'scope': row['scope_id'], 'row': record})
                    or record != observation(row['problem_id'], record.get('raw', {}))
                    or record['team_key'] != row['team_key']
                    or row['problem_id'] not in {p['id'] for p in by_scope[row['scope_id']]['problems']}
                    or record != expected['record'] or row['scope_id'] != expected['scope_id']
                    or row['snapshot_id'] != expected['snapshot_id']
                    or row['first_seen'] != expected['first_seen'] or row['last_seen'] != expected['last_seen']):
                raise ContractError('invalid stored evidence; nothing was published')
            evidences.append(store.evidence(row['id']))
        if expected_evidence:
            raise ContractError('stored snapshot evidence is incomplete; nothing was published')

        manifest = {
            'schema': 1, 'generated_at': utc(), 'contest_slug': CONTEST_SLUG,
            'collector_enabled': False, 'poll_seconds': poll_seconds,
            'hosting': 'github-actions-static',
            'scopes': '_data/scopes.json', 'runs': '_data/runs.json',
            'export': '_data/snapshots.jsonl',
            'boards': {}, 'history': {}, 'archives': {}, 'evidence': {},
        }
        files = {}
        _json_file(files, manifest['scopes'], {
            'scopes': scopes, 'collector_enabled': False, 'poll_seconds': poll_seconds,
            'hosting': 'github-actions-static',
        })
        _json_file(files, manifest['runs'], {'runs': store.runs()})
        files[manifest['export']] = ''.join(dumps(public_data(s)) + '\n' for s in snapshots).encode('utf-8')
        for sid, scope in by_scope.items():
            board = store.board(sid)
            if scope_id(board['scope']) != sid or board['scope'].get('demo') is not False:
                raise ContractError('latest board scope disagrees with its stored definition')
            path = f'_data/boards/{sid}.json'
            manifest['boards'][sid] = path
            _json_file(files, path, board)
            manifest['history'][sid] = {}
            manifest['archives'][sid] = {}
            for team in board['rows']:
                key = team['team_key']
                team_hash = hashlib.sha256(key.encode('utf-8')).hexdigest()
                path = f'_data/history/{sid}/{team_hash}.json'
                manifest['history'][sid][key] = path
                history = store.history(sid, key, limit=200)
                history.update(total_points=scope['snapshot_count'], full_export=manifest['export'])
                _json_file(files, path, history)
                archived = archive_rows(store, sid, key, limit=500)
                rows = list(archived['rows'])
                while len(rows) < archived['total']:
                    batch = archive_rows(store, sid, key, limit=500, offset=len(rows))
                    if not batch['rows'] or batch['total'] != archived['total']:
                        raise ContractError('archive pagination is incomplete')
                    rows.extend(batch['rows'])
                path = f'_data/archives/{sid}/{team_hash}.json'
                manifest['archives'][sid][key] = path
                _json_file(files, path, {'rows': rows, 'total': archived['total']})
        for evidence in evidences:
            path = f"_data/evidence/{evidence['id']}.json"
            manifest['evidence'][evidence['id']] = path
            _json_file(files, path, evidence)
        _json_file(files, '_data/manifest.json', manifest)
        return files, manifest, len(snapshots)
    finally:
        connection.close()


def export_site(db_path: str | Path, output: str | Path, *, poll_seconds: int = 600,
                web_dir: str | Path | None = None) -> dict:
    """Export only to a new destination, publishing it after every read succeeds."""
    if isinstance(poll_seconds, bool) or not isinstance(poll_seconds, int) or poll_seconds < 300:
        raise ContractError('scheduled poll_seconds must be an integer of at least 300')
    destination = Path(output).resolve()
    if destination.exists() or destination.is_symlink():
        raise ContractError('destination must not exist; old exports are never overwritten or deleted')
    source = Path(db_path).resolve()
    files, manifest, snapshot_count = _collect(source, poll_seconds)
    assets = Path(web_dir) if web_dir is not None else ROOT / 'web'
    index = (assets / 'index.html').read_text(encoding='utf-8')
    marker = '<html lang="zh-CN">'
    if marker not in index:
        raise ContractError('web index must expose the expected static-mode marker')
    files['index.html'] = index.replace(marker, '<html lang="zh-CN" data-mode="static">', 1).encode('utf-8')
    for name in ('app.js', 'style.css'):
        files['static/' + name] = (assets / name).read_bytes()
    files['.nojekyll'] = b''
    # Serialization and source validation completed before creating any output.
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.' + destination.name + '-building-', dir=destination.parent))
    for relative, content in files.items():
        target = staging / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(content)
    # A second existence check protects an output created while export was running.
    if destination.exists() or destination.is_symlink():
        raise ContractError('destination appeared during export; completed staging folder retained')
    staging.rename(destination)
    return {'output': str(destination), 'files': len(files), 'scopes': len(manifest['boards']),
            'snapshots': snapshot_count, 'generated_at': manifest['generated_at']}


def main():
    parser = argparse.ArgumentParser(description='Read-only public GitHub Pages site export')
    parser.add_argument('--db', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--poll-seconds', type=int, default=600)
    args = parser.parse_args()
    print(dumps(export_site(args.db, args.output, poll_seconds=args.poll_seconds)))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, RuntimeError, sqlite3.Error) as error:
        print(f'{type(error).__name__}: {error}', file=sys.stderr)
        raise SystemExit(1)
