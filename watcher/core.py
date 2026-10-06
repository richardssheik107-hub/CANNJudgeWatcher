"""Validated, complete-row evidence. Scores are never stitched across test cases."""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

class ContractError(ValueError):
    """An upstream response cannot safely be interpreted."""

PASS = frozenset({'Pass', 'Accepted', 'AC'})
SECRET_KEYS = frozenset({'cookie', 'authorization', 'token', 'password', 'files', 'code', 'code_template', 'access_token', 'refresh_token', 'api_key', 'secret', 'private_key', 'headers'})

def clean(value: Any) -> Any:
    """Drop credentials/source code; cap log strings. Not a lossless source archive."""
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items() if str(k).lower() not in SECRET_KEYS}
    if isinstance(value, list):
        return [clean(v) for v in value]
    if isinstance(value, str):
        return value[:4000]
    return value

def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)

def digest(value: Any) -> str:
    return hashlib.sha256(dumps(value).encode()).hexdigest()

def utc(value: str | None = None) -> str:
    try:
        dt = datetime.now(timezone.utc) if value is None else datetime.fromisoformat(value.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            raise ValueError('timezone required')
        return dt.astimezone(timezone.utc).isoformat(timespec='microseconds')
    except (TypeError, ValueError) as e:
        raise ContractError('invalid timestamp: an explicit timezone is required') from e

def number(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if isinstance(value, bool):
            raise ValueError('boolean is not a score')
        n = Decimal(str(value))
        if not n.is_finite() or n < 0:
            raise ValueError('score must be finite and nonnegative')
        return str(n)
    except (ValueError, InvalidOperation) as e:
        raise ContractError('invalid numeric score') from e

def rank(value: Any) -> int | None:
    if value is None:
        return None
    n = number(value)
    if Decimal(n) < 1 or Decimal(n) != Decimal(n).to_integral_value():
        raise ContractError('invalid rank')
    return int(Decimal(n))

def identity(row: dict) -> tuple[str, str]:
    for kind in ('team', 'user'):
        obj = row.get(kind) or {}
        if not isinstance(obj, dict):
            obj = {}
        key = obj.get('_id') or row.get(kind + '_id')
        if key is not None and str(key).strip():
            name = obj.get('team_name') or obj.get('name') or obj.get('nickname') or row.get('name') or str(key)
            return kind + ':' + str(key), str(name)
    raise ContractError('stable team/user ID missing; refuse to merge by nickname or rank')

def observation(problem_id: str, raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise ContractError('ranking row must be an object')
    key, name = identity(raw)
    result = raw.get('result', [])
    if not isinstance(result, list):
        raise ContractError('result must be an array')
    status = str(raw.get('status') or '')
    score = number(raw.get('score'))
    cases_ok = all(isinstance(c, dict) and (c.get('testcase_status') or c.get('status')) in PASS for c in result)
    return {'problem_id': problem_id, 'team_key': key, 'name': name,
            'score': score, 'rank': rank(raw.get('rank')), 'status': status,
            'eligible': status in PASS and score is not None and cases_ok,
            'submission_id': str(raw['submission_id']) if raw.get('submission_id') else None,
            'submitted_at': raw.get('create_time'), 'result': clean(result), 'raw': clean(raw)}

def total_row(raw: dict) -> dict:
    key, name = identity(raw)
    return {'team_key': key, 'name': name, 'score': number(raw.get('score')),
            'rank': rank(raw.get('rank')), 'raw': clean(raw)}

def scope_id(scope: dict) -> str:
    keys = ('contest_id', 'stage', 'group', 'epoch', 'problems', 'demo')
    return digest({k: scope[k] for k in keys})[:24]

def validate_snapshot(snapshot: dict) -> dict:
    """Canonical public import format; unknown scores stay unknown, not zero."""
    if snapshot.get('schema') != 1:
        raise ContractError('unsupported snapshot schema')
    scope = snapshot.get('scope', {})
    for k in ('contest_id', 'stage', 'group', 'epoch', 'problems', 'demo', 'title'):
        if k not in scope:
            raise ContractError('scope missing ' + k)
    if not isinstance(scope['demo'], bool) or not isinstance(scope['problems'], list) or not scope['problems']:
        raise ContractError('invalid scope')
    problems = set()
    for p in scope['problems']:
        if not isinstance(p, dict) or not p.get('id') or p['id'] in problems:
            raise ContractError('duplicate or missing problem ID')
        problems.add(p['id'])
        if Decimal(number(p.get('weight', 1)) or '0') <= 0:
            raise ContractError('problem weight must be positive')
    if not isinstance(snapshot.get('observations'), list) or not isinstance(snapshot.get('totals'), list):
        raise ContractError('observations and totals must be arrays')
    observed = utc(snapshot.get('observed_at')) if snapshot.get('observed_at') else None
    if observed is None:
        raise ContractError('observed_at required; submission time is not observation time')
    if observed > utc():
        raise ContractError('future observations are not allowed')
    seen = set()
    for row in snapshot.get('observations', []):
        if row.get('problem_id') not in problems or not row.get('team_key'):
            raise ContractError('unscoped observation')
        k = (row['problem_id'], row['team_key'])
        if k in seen:
            raise ContractError('duplicate team/problem in snapshot')
        seen.add(k)
        # Re-normalize from original row rather than trusting an imported eligible flag.
        expected = observation(row['problem_id'], row.get('raw', {}))
        if row != expected:
            raise ContractError('normalized observation does not match its evidence')
    seen = set()
    for row in snapshot.get('totals', []):
        if row.get('team_key') in seen or row != total_row(row.get('raw', {})):
            raise ContractError('invalid total-board evidence')
        seen.add(row['team_key'])
    out = clean(snapshot)
    out['observed_at'] = observed
    return out

def competition_ranks(rows: list[dict], score_key: str, rank_key: str) -> None:
    """Rank by unrounded Decimal scores, using shared ranks (1, 1, 3)."""
    eligible = sorted((r for r in rows if r.get(score_key) is not None),
                      key=lambda r: (-Decimal(r[score_key]), r['team_key']))
    previous, place = None, None
    for i, row in enumerate(eligible, 1):
        score = Decimal(row[score_key])
        if score != previous:
            place = i
        row[rank_key], previous = place, score
