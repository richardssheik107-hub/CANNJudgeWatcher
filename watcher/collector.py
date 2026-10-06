"""One bounded polling round; separate archive backfill never rewrites current boards."""
from __future__ import annotations
import json
from .core import ContractError, clean, digest, dumps, identity, scope_id, utc
from .source import Client, SourceError, collect_contest, matches
from .store import Store


def poll(store: Store, client: Client, config: dict) -> dict:
    run_id = store.start_run()
    detail = {'published': [], 'errors': [], 'history': [], 'retry_after': 0}
    try:
        contests = [c for c in client.discover() if matches(c, config)]
        if not contests:
            raise ContractError('no selected contests discovered; previous data retained')
        for contest in contests:
            try:
                if not config.get('include_ended', True) and contest.get('end_time') and utc(contest['end_time']) < utc():
                    continue
                snap = collect_contest(client, contest, config)
                sid = store.ingest(snap)
                detail['published'].append({'contest_id': contest['_id'], 'snapshot_id': sid})
                if int(config.get('history_pages_per_poll', 0)) > 0:
                    archive = backfill(store, client, scope_id(snap['scope']), int(config['history_pages_per_poll']))
                    detail['history'].append({'contest_id': contest['_id'], **archive})
            except (ContractError, SourceError) as e:
                detail['errors'].append({'contest_id': contest.get('_id'), 'error': str(e)})
                detail['retry_after'] = max(detail['retry_after'], getattr(e, 'retry_after', 0))
                if detail['retry_after']:
                    break
        status = 'PARTIAL' if detail['errors'] and detail['published'] else 'FAILED' if detail['errors'] else 'SUCCESS' if detail['published'] else 'SKIPPED'
    except Exception as e:
        # Do not log response bodies, cookie values or subprocess stderr.
        detail['errors'].append({'error': str(e) if isinstance(e, (ContractError, SourceError)) else type(e).__name__})
        detail['retry_after'] = max(detail['retry_after'], getattr(e, 'retry_after', 0))
        status = 'FAILED'
    store.finish_run(run_id, status, detail)
    return {'status': status, **detail}


def backfill(store: Store, client: Client, sid: str, max_pages: int = 10, start_skip: int = 0) -> dict:
    """Archive public submission-list metadata only; no source-code/detail scraping.

    A public history list is not proof of historic official scores. Such rows are
    kept separate from ranking evidence and never silently promoted to peak scores.
    """
    snap = store.snapshot(sid); scope = snap['scope']
    if scope['demo']:
        raise ContractError('cannot backfill a demo scope')
    size = 100; skip = max(0, start_skip); saved = 0; total = None; seen = set()
    known_problems = {p['id'] for p in scope['problems']}
    with store.connect() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS submission_archive(
          id TEXT PRIMARY KEY,scope_id TEXT NOT NULL,submission_id TEXT NOT NULL,
          team_key TEXT,problem_id TEXT,observed_at TEXT NOT NULL,data TEXT NOT NULL)''')
    for _ in range(max(1, min(max_pages, 1000))):
        data = client.get('/api/submissions/global/list', contestId=scope['contest_id'], withCount=1, skip=skip, limit=size)
        if not isinstance(data, dict) or not isinstance(data.get('list'), list) or type(data.get('total')) is not int or data['total'] < 0:
            raise ContractError('submission history requires list[] and integer total')
        if total is not None and total != data['total']:
            return {'saved': saved, 'complete': False, 'next_skip': 0, 'reason': 'history shifted; restart from zero (deduplication is safe)'}
        total = data['total']
        for raw in data['list']:
            if not isinstance(raw, dict):
                raise ContractError('historical submission must be an object')
            if raw.get('_id') in seen:
                raise ContractError('history repeated an ID across pages; coverage is incomplete')
            seen.add(raw.get('_id'))
            if not raw.get('_id') or str(raw.get('problem_id')) not in known_problems:
                raise ContractError('unscoped or unidentified historical submission')
        with store.connect() as db:
            for raw in data['list']:
                row = clean(raw)
                try:
                    team_key, _ = identity(row)
                except ContractError:
                    team_key = None  # Never fabricate team ownership from a display name.
                cur = db.execute('INSERT OR IGNORE INTO submission_archive VALUES(?,?,?,?,?,?,?)',
                     (digest({'scope': sid, 'row': row}), sid, str(row['_id']), team_key,
                      str(row.get('problem_id')), utc(), dumps(row)))
                saved += cur.rowcount
        skip += len(data['list'])
        if skip >= total:
            return {'saved': saved, 'complete': start_skip == 0, 'range_complete': True, 'next_skip': None, 'total': total,
                    'reason': 'requested range exhausted; not proof of all contest history' }
        if not data['list']:
            raise ContractError('history truncated before total')
    return {'saved': saved, 'complete': False, 'next_skip': skip, 'total': total, 'reason': 'page budget reached'}


def archive_rows(store: Store, sid: str, team_key: str | None = None, limit: int = 100, offset: int = 0) -> dict:
    with store.connect() as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='submission_archive'").fetchone():
            return {'rows': [], 'total': 0}
        clause = 'scope_id=?'; args = [sid]
        if team_key:
            clause += ' AND team_key=?'; args.append(team_key)
        total = db.execute('SELECT COUNT(*) FROM submission_archive WHERE ' + clause, args).fetchone()[0]
        rows = db.execute('SELECT * FROM submission_archive WHERE ' + clause + ' ORDER BY observed_at DESC LIMIT ? OFFSET ?',
                          args + [max(1, min(limit, 500)), max(0, offset)]).fetchall()
    return {'rows': [{**dict(r), 'data': json.loads(r['data'])} for r in rows], 'total': total}
