"""Atomic compressed snapshots plus deduplicated, indexed complete-row evidence."""
from __future__ import annotations
import json
import sqlite3
import zlib
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from .core import ContractError, competition_ranks, digest, dumps, scope_id, utc, validate_snapshot
from .scoring import apply_current_basis

class Store:
    def __init__(self, path: str):
        self.path = str(Path(path).resolve())
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
            CREATE TABLE IF NOT EXISTS scopes(id TEXT PRIMARY KEY, definition TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS snapshots(
              id INTEGER PRIMARY KEY, scope_id TEXT NOT NULL REFERENCES scopes(id),
              observed_at TEXT NOT NULL, digest TEXT NOT NULL, data BLOB NOT NULL,
              imported INTEGER NOT NULL, UNIQUE(scope_id, observed_at));
            CREATE INDEX IF NOT EXISTS snapshots_time ON snapshots(scope_id,observed_at DESC);
            CREATE TABLE IF NOT EXISTS evidence(
              id TEXT PRIMARY KEY, scope_id TEXT NOT NULL REFERENCES scopes(id),
              team_key TEXT NOT NULL, problem_id TEXT NOT NULL, first_seen TEXT NOT NULL,
              last_seen TEXT NOT NULL, snapshot_id INTEGER NOT NULL REFERENCES snapshots(id), data TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS evidence_team ON evidence(scope_id,team_key,problem_id);
            CREATE TABLE IF NOT EXISTS runs(
              id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT,
              status TEXT NOT NULL, detail TEXT NOT NULL);
            PRAGMA user_version=1;
            ''')
        Path(self.path).chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def ingest(self, snapshot: dict, imported: bool = False) -> int:
        snapshot = validate_snapshot(snapshot)
        scope = snapshot['scope']; sid = scope_id(scope); at = snapshot['observed_at']
        text = dumps(snapshot); sha = digest(snapshot)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT id,digest FROM snapshots WHERE scope_id=? AND observed_at=?', (sid, at)).fetchone()
            if old:
                if old['digest'] != sha:
                    raise ContractError('conflicting snapshot at same time; original evidence was not overwritten')
                return old['id']
            db.execute('INSERT INTO scopes VALUES(?,?) ON CONFLICT(id) DO NOTHING', (sid, dumps(scope)))
            db.execute('UPDATE scopes SET definition=? WHERE id=? AND NOT EXISTS (SELECT 1 FROM snapshots WHERE scope_id=? AND observed_at>?)',
                       (dumps(scope), sid, sid, at))
            cur = db.execute('INSERT INTO snapshots(scope_id,observed_at,digest,data,imported) VALUES(?,?,?,?,?)',
                             (sid, at, sha, zlib.compress(text.encode()), int(imported)))
            snap_id = cur.lastrowid
            for row in snapshot['observations']:
                eid = digest({'scope': sid, 'row': row})
                db.execute('''INSERT INTO evidence VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                  snapshot_id=CASE WHEN excluded.first_seen<evidence.first_seen THEN excluded.snapshot_id ELSE evidence.snapshot_id END,
                  first_seen=MIN(evidence.first_seen,excluded.first_seen),last_seen=MAX(evidence.last_seen,excluded.last_seen)''',
                  (eid, sid, row['team_key'], row['problem_id'], at, at, snap_id, dumps(row)))
            return snap_id

    def scopes(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute('''SELECT s.*,MIN(p.observed_at) first_seen,MAX(p.observed_at) last_seen,
               COUNT(p.id) snapshot_count FROM scopes s JOIN snapshots p ON p.scope_id=s.id GROUP BY s.id
               ORDER BY last_seen DESC''').fetchall()
        return [dict(json.loads(r['definition']), id=r['id'], first_seen=r['first_seen'],
                     last_seen=r['last_seen'], snapshot_count=r['snapshot_count']) for r in rows]

    def snapshot(self, sid: str) -> dict:
        with self.connect() as db:
            r = db.execute('SELECT * FROM snapshots WHERE scope_id=? ORDER BY observed_at DESC LIMIT 1', (sid,)).fetchone()
        if not r:
            raise KeyError(sid)
        out = json.loads(zlib.decompress(r['data']))
        out.update(snapshot_id=r['id'], imported=bool(r['imported']))
        return out

    def board(self, sid: str) -> dict:
        # A single DB read transaction prevents a poll/import from mixing board generations.
        with self.connect() as db:
            db.execute('BEGIN')
            head = db.execute('SELECT * FROM snapshots WHERE scope_id=? ORDER BY observed_at DESC LIMIT 1', (sid,)).fetchone()
            if not head:
                raise KeyError(sid)
            snap = json.loads(zlib.decompress(head['data']))
            evidences = db.execute('SELECT * FROM evidence WHERE scope_id=?', (sid,)).fetchall()
            coverage = db.execute('SELECT MIN(observed_at),COUNT(*) FROM snapshots WHERE scope_id=?', (sid,)).fetchone()
        scope = snap['scope']; tasks = scope['problems']; teams: dict = {}
        def team(key, name):
            return teams.setdefault(key, {'team_key': key, 'name': name, 'best': {}, 'current': {},
                                         'official_rank': None, 'official_score': None, 'peak_rank': None,
                                         'reference_rank': None, 'present': False})
        for e in sorted(evidences, key=lambda e: (e['first_seen'], e['id'])):
            r = json.loads(e['data']); t = team(r['team_key'], r['name'])
            if r['eligible']:
                old = t['best'].get(r['problem_id'])
                if old is None or Decimal(r['score']) > Decimal(old['score']):
                    t['best'][r['problem_id']] = {**r, 'evidence_id': e['id'], 'observed_at': e['first_seen']}
        for r in snap['observations']:
            t = team(r['team_key'], r['name']); t['name'] = r['name']; t['present'] = True
            t['current'][r['problem_id']] = r
        for r in snap.get('totals', []):
            t = team(r['team_key'], r['name']); t.update(name=r['name'], present=True,
                                                       official_score=r['score'], official_rank=r['rank'])
        basis = apply_current_basis(snap, teams, evidences)
        for t in teams.values():
            # A never-observed problem contributes nothing to the OBSERVED subtotal.
            # Unknown/missing current evidence is never silently assigned score 0.
            t['observed_problems'] = len(t['best']); t['total_problems'] = len(tasks)
            t['peak_score'] = str(sum((Decimal(t['best'][p['id']]['score']) * Decimal(str(p.get('weight', 1)))
                                      for p in tasks if p['id'] in t['best']), Decimal(0))) if t['best'] else None
            complete = all(p['id'] in t['current'] and t['current'][p['id']]['score'] is not None for p in tasks)
            t['current_sum'] = str(sum((Decimal(t['current'][p['id']]['score']) * Decimal(str(p.get('weight', 1)))
                                       for p in tasks), Decimal(0))) if complete else None
            t['gap'] = str(Decimal(t['peak_score']) - Decimal(t['official_score'])) if t['peak_score'] is not None and t['official_score'] is not None else None
            t['sum_mismatch'] = (t['current_sum'] is not None and t['official_score'] is not None
                                 and abs(Decimal(t['current_sum']) - Decimal(t['official_score'])) > Decimal('0.02'))
            if basis is not None:
                audit = t['observed_official_best']
                t['observed_official_peak_score'] = str(sum((Decimal(audit[p['id']]['score']) * Decimal(str(p.get('weight', 1)))
                                                           for p in tasks if p['id'] in audit), Decimal(0))) if audit else None
                t['observed_official_best'] = list(audit.values())
            t['best'] = list(t['best'].values()); t['current'] = list(t['current'].values())
        rows = list(teams.values())
        competition_ranks(rows, 'peak_score', 'peak_rank')
        competition_ranks(rows, 'official_score', 'reference_rank')
        rows.sort(key=lambda r: (r['peak_rank'] is None, r['peak_rank'] or 0, r['team_key']))
        result = {'scope': scope, 'scope_id': sid, 'observed_at': snap['observed_at'], 'first_seen': coverage[0],
                'snapshot_count': coverage[1], 'imported': bool(head['imported']), 'rows': rows,
                'notes': snap.get('notes', []), 'semantics': 'sum_of_observed_problem_score_maxima',
                'warning': '历史分数可能采用不同全场基准；合计榜不是官方最终榜、统一基准重评分榜或藏分判定。'}
        if basis is not None:
            result.update(score_basis=basis, semantics='current_baseline_confirmed_submission_maxima',
                          warning='当前值仅覆盖本轮基准下可确认的完整提交；Hidden 或缺失数据不会被推测补齐。旧官方分数仅保留作审计。')
        return result

    def history(self, sid: str, team_key: str, limit: int = 200, before: str | None = None) -> dict:
        limit = max(1, min(limit, 500))
        with self.connect() as db:
            rows = db.execute('''SELECT observed_at,data,imported FROM snapshots WHERE scope_id=? AND observed_at<?
                  ORDER BY observed_at DESC LIMIT ?''', (sid, utc(before) if before else '9999', limit + 1)).fetchall()
        points = []
        for row in rows[:limit]:
            s = json.loads(zlib.decompress(row['data']))
            points.append({'observed_at': row['observed_at'], 'imported': bool(row['imported']),
                           'total': next((r for r in s.get('totals', []) if r['team_key'] == team_key), None),
                           'problems': [r for r in s['observations'] if r['team_key'] == team_key]})
        return {'points': points, 'next_before': rows[limit-1]['observed_at'] if len(rows) > limit else None}

    def evidence(self, eid: str) -> dict:
        with self.connect() as db:
            row = db.execute('SELECT e.*,s.imported FROM evidence e JOIN snapshots s ON s.id=e.snapshot_id WHERE e.id=?', (eid,)).fetchone()
        if not row:
            raise KeyError(eid)
        return {'id': eid, 'scope_id': row['scope_id'], 'first_seen': row['first_seen'], 'last_seen': row['last_seen'],
                'snapshot_id': row['snapshot_id'], 'imported': bool(row['imported']), 'observation': json.loads(row['data'])}

    def export(self):
        with self.connect() as db:
            for r in db.execute('SELECT data FROM snapshots ORDER BY observed_at,id'):
                yield zlib.decompress(r['data']).decode() + '\n'

    def backup(self, destination: str):
        dest = Path(destination).resolve()
        if dest == Path(self.path):
            raise ValueError('backup must use a different path')
        dest.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as source, sqlite3.connect(str(dest)) as target:
            source.backup(target)
        dest.chmod(0o600)

    def start_run(self) -> int:
        with self.connect() as db:
            return db.execute('INSERT INTO runs(started_at,status,detail) VALUES(?,?,?)', (utc(), 'RUNNING', '{}')).lastrowid

    def finish_run(self, run_id: int, status: str, detail: dict):
        with self.connect() as db:
            db.execute('UPDATE runs SET finished_at=?,status=?,detail=? WHERE id=?', (utc(), status, dumps(detail), run_id))

    def runs(self):
        with self.connect() as db:
            return [{**dict(r), 'detail': json.loads(r['detail'])} for r in db.execute('SELECT * FROM runs ORDER BY id DESC LIMIT 30')]
