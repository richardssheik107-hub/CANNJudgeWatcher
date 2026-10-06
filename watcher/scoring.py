"""Current-baseline evidence for the verified Starcup final scoring rule.

Official scores stay immutable. Historical results are evaluated as whole
submissions, and inaccessible test points never become inferred performances.
"""
from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext

from .core import PASS, digest, scope_id

CONTEST_ID = '6abcb2fa694b590c3c300a2e'
PROBLEM_ID = '6abcb4fd694b590c3c315c0e'
CONTEST_SLUG = 'ct_starcup_aiop_final'
RULE = 'cann-default-time-log-v1'
FORMULA = '100/(1+log(time/TBest)/log(1.5))'
RULE_SOURCE = 'https://cannjudge.cn/public/ct_starcup_aiop_final/scoring-rules'


def _positive(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = Decimal(str(value))
        return number if number.is_finite() and number > 0 else None
    except (InvalidOperation, ValueError):
        return None


def _testcases(snapshot):
    ranking_lists, metadata = [], []
    payloads = snapshot.get('payloads', [])
    if not isinstance(payloads, list):
        return {}, False
    for payload in payloads:
        if not isinstance(payload, dict):
            return {}, False
        if payload.get('problem_id') != PROBLEM_ID:
            continue
        problem_metadata = payload.get('metadata')
        version = problem_metadata.get('version') if isinstance(problem_metadata, dict) else None
        metadata = version.get('testcases', []) if isinstance(version, dict) else []
        pages = payload.get('pages', [])
        if not isinstance(pages, list):
            return {}, False
        for page in pages:
            data = page.get('data') if isinstance(page, dict) else None
            if not isinstance(data, dict):
                return {}, False
            cases = data.get('testcases')
            if isinstance(cases, list) and cases:
                ranking_lists.append(cases)
    cases = ranking_lists[0] if ranking_lists else metadata
    if not isinstance(cases, list):
        return {}, False
    by_id = {}
    for case in cases:
        if not isinstance(case, dict):
            return {}, False
        cid = case.get('_id') or case.get('id')
        if not isinstance(cid, str) or not cid or cid in by_id:
            return {}, False
        by_id[cid] = case
    if not isinstance(metadata, list) or not metadata:
        return by_id, False
    metadata_ids = [c.get('_id') for c in metadata if isinstance(c, dict)]
    consistent = (bool(by_id) and len(metadata_ids) == len(metadata)
                  and all(isinstance(cid, str) and cid for cid in metadata_ids)
                  and len(set(metadata_ids)) == len(metadata_ids)
                  and set(by_id) == set(metadata_ids))
    # Different ranking pages must not supply different benchmark generations.
    consistent = consistent and all(digest(c) == digest(cases) for c in ranking_lists)
    return by_id, consistent


def _performance(row):
    result = row.get('result')
    if not isinstance(result, list) or not result:
        return None
    cases = {}
    for case in result:
        if not isinstance(case, dict):
            return None
        cid = case.get('testcase_id')
        if not isinstance(cid, str) or not cid or cid in cases:
            return None
        # Case scores are derived from a benchmark and are not performance data.
        cases[cid] = {name: case.get(name) for name in ('time', 'precision_ratio')}
        cases[cid]['status'] = case.get('testcase_status') or case.get('status')
    return cases


def _candidate_key(row, evidence_id):
    performance = _performance(row)
    if row.get('submission_id') and performance is not None:
        return (row['team_key'], row['submission_id'], digest(performance))
    return (row['team_key'], 'unidentified', evidence_id)


def _complete(row, cases, metadata_consistent):
    performance = _performance(row)
    return (row.get('eligible') is True and bool(row.get('submission_id'))
            and metadata_consistent and performance is not None and set(performance) == set(cases))


def _recompute(row, cases):
    performance = _performance(row)
    if performance is None or set(performance) != set(cases):
        return None
    scores = []
    with localcontext() as context:
        context.prec = 50
        for cid, case in cases.items():
            result = performance[cid]
            reference = _positive(case.get('tbest'))
            elapsed = _positive(result.get('time'))
            if (case.get('hidden') is True or case.get('type') != 'default'
                    or result['status'] not in PASS or reference is None or elapsed is None):
                return None
            # A faster old result than the asserted global best needs validity
            # clarification; do not invent a cap or silently include revoked data.
            if elapsed < reference:
                return None
            denominator = Decimal(1) + (elapsed / reference).ln() / Decimal('1.5').ln()
            if denominator <= 0:
                return None
            scores.append(Decimal(100) / denominator)
        if not scores:
            return None
        return str((sum(scores) / Decimal(len(scores))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def apply_current_basis(snapshot, teams, evidences):
    """Replace primary peaks for this contest only; retain old official peaks for audit."""
    scope = snapshot['scope']
    if (scope.get('demo') is not False or scope.get('contest_id') != CONTEST_ID
            or scope.get('stage') != CONTEST_SLUG
            or {p['id'] for p in scope['problems']} != {PROBLEM_ID}):
        return None
    cases, consistent = _testcases(snapshot)
    context = snapshot.get('scoring_context', {})
    verified = (isinstance(context, dict) and context.get('verified') is True
                and context.get('rule') == RULE and context.get('formula') == FORMULA
                and context.get('problem_ids') == [PROBLEM_ID])
    visible = sum(c.get('hidden') is not True for c in cases.values())
    baseline_complete = (consistent and all(c.get('hidden') is not True and c.get('type') == 'default'
                                           and _positive(c.get('tbest')) is not None for c in cases.values()))
    reasons = []
    if not consistent:
        reasons.append('当前测试点元数据不完整或不同分页的基准不一致。')
    if not baseline_complete:
        reasons.append('当前公开 TBest 有隐藏或缺失测试点，不能按可见测试点代替完整计分。')
    if not verified:
        reasons.append('当前快照未核验官方评分规则，未对旧提交套用公式。')

    by_team, evidence_by_id = {}, {}
    for evidence in sorted(evidences, key=lambda e: (e['first_seen'], e['id'])):
        row = json.loads(evidence['data'])
        evidence_by_id[evidence['id']] = evidence
        if row.get('eligible') is not True:
            continue
        key = _candidate_key(row, evidence['id'])
        by_team.setdefault(row['team_key'], {}).setdefault(key, (row, evidence))

    anchors = {}
    for row in snapshot['observations']:
        if row['problem_id'] == PROBLEM_ID and _complete(row, cases, consistent):
            eid = digest({'scope': scope_id(scope), 'row': row})
            evidence = evidence_by_id.get(eid)
            if evidence is not None:
                anchors[_candidate_key(row, eid)] = (row, evidence)

    can_recompute = verified and baseline_complete
    if can_recompute:
        # Verify this exact benchmark/rule against every current official anchor.
        calibration = [(row, _recompute(row, cases)) for row, _ in anchors.values()]
        if not calibration or any(score is None or Decimal(score) != Decimal(row['score'])
                                  for row, score in calibration):
            can_recompute = False
            reasons.append('公式与本轮完整官方成绩不能一致复现，历史重算已停止。')

    any_confirmed, any_missing = False, False
    for team in teams.values():
        team['observed_official_best'] = dict(team['best'])
        team['best'] = {}
        candidates = by_team.get(team['team_key'], {})
        confirmed, anchor_count, local_count = 0, 0, 0
        row_reasons = []
        for key, (row, evidence) in candidates.items():
            anchor = anchors.get(key)
            if anchor is not None:
                row, evidence = anchor
                score, kind = row['score'], 'official-current'
                anchor_count += 1
            elif can_recompute and _complete(row, cases, consistent):
                score, kind = _recompute(row, cases), 'recomputed-current'
                if score is None:
                    continue
                local_count += 1
            else:
                continue
            confirmed += 1
            derived = {**row, 'score': score, 'original_score': row['score'],
                       'evidence_id': evidence['id'], 'observed_at': evidence['first_seen'],
                       'score_basis_kind': kind, 'score_basis_as_of': snapshot['observed_at'],
                       'score_basis_source': RULE_SOURCE}
            old = team['best'].get(PROBLEM_ID)
            if old is None or Decimal(score) > Decimal(old['score']):
                team['best'][PROBLEM_ID] = derived
        missing = len(candidates) - confirmed
        if missing:
            row_reasons.extend(reasons)
            if not row_reasons:
                row_reasons.append('部分旧提交缺少完整测试点性能、有效身份或可核验计分数据。')
            row_reasons.append('当前值仅是已观测历史中可确认部分的下界，不是完整历史最高分。')
        if not confirmed:
            row_reasons.append('当前基准下尚无可确认的完整有效提交。')
        status = 'unavailable' if not confirmed else 'partial' if missing else 'complete'
        team.update(historical_submissions=len(candidates), rescored_submissions=confirmed,
                    unavailable_submissions=missing, official_anchor_submissions=anchor_count,
                    formula_rescored_submissions=local_count, peak_status=status, reasons=row_reasons)
        any_confirmed = any_confirmed or bool(confirmed)
        any_missing = any_missing or bool(missing)

    return {'kind': 'current-baseline', 'status': 'unavailable' if not any_confirmed else 'partial' if any_missing else 'complete',
            'as_of': snapshot['observed_at'], 'rule_source': RULE_SOURCE, 'formula': FORMULA,
            'coverage_scope': 'observed-eligible-submissions',
            'formula_verified': verified, 'rule_digest': context.get('rule_digest') if isinstance(context, dict) else None,
            'baseline_complete': baseline_complete,
            'formula_recomputation_enabled': can_recompute, 'visible_testcase_count': visible,
            'total_testcase_count': len(cases), 'reasons': reasons}
