"""Current-baseline evidence for explicitly supported public contests.

Official scores stay immutable. Historical results are evaluated as whole
submissions, and inaccessible test points never become inferred performances.
"""
from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext

from .core import PASS, digest, scope_id
from .profiles import get_profile

CONTEST_ID = '6abcb2fa694b590c3c300a2e'
CONTEST_SLUG = 'ct_starcup_aiop_final'
RULE = 'cann-default-time-log-v1'
FORMULA = '100/(1+log(time/TBest)/log(1.5))'
RATIO_RULE = 'cann-default-time-ratio-v1'
RATIO_FORMULA = '100*TBest/time'
VERIFIED_FORMULAS = {RULE: FORMULA, RATIO_RULE: RATIO_FORMULA}
RULE_SOURCE = 'https://cannjudge.cn/public/ct_starcup_aiop_final/scoring-rules'


def _positive(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = Decimal(str(value))
        return number if number.is_finite() and number > 0 else None
    except (InvalidOperation, ValueError):
        return None


def _testcases(snapshot, problem_id):
    ranking_lists, metadata = [], []
    payloads = snapshot.get('payloads', [])
    if not isinstance(payloads, list):
        return {}, False
    for payload in payloads:
        if not isinstance(payload, dict):
            return {}, False
        if payload.get('problem_id') != problem_id:
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
        return (row['problem_id'], row['team_key'], row['submission_id'], digest(performance))
    return (row['problem_id'], row['team_key'], 'unidentified', evidence_id)


def _complete(row, cases, metadata_consistent):
    performance = _performance(row)
    return (row.get('eligible') is True and bool(row.get('submission_id'))
            and metadata_consistent and performance is not None and set(performance) == set(cases))


def _recompute(row, cases, rule=RULE):
    if rule not in VERIFIED_FORMULAS:
        return None
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
            if rule == RATIO_RULE:
                scores.append(Decimal(100) * reference / elapsed)
            else:
                denominator = Decimal(1) + (elapsed / reference).ln() / Decimal('1.5').ln()
                if denominator <= 0:
                    return None
                scores.append(Decimal(100) / denominator)
        if not scores:
            return None
        return str((sum(scores) / Decimal(len(scores))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def _apply_problem_basis(snapshot, teams, evidences, problem_id):
    """Evaluate one problem without mixing testcase sets or score calibrations."""
    scope = snapshot['scope']
    cases, consistent = _testcases(snapshot, problem_id)
    context = snapshot.get('scoring_context', {})
    rule_source = ('https://cannjudge.cn/public/' + scope['stage'] + '/scoring-rules')
    rule = context.get('rule') if isinstance(context, dict) else None
    verified = (isinstance(context, dict) and context.get('verified') is True
                and rule in VERIFIED_FORMULAS and context.get('formula') == VERIFIED_FORMULAS[rule]
                and isinstance(context.get('problem_ids'), list)
                and all(isinstance(pid, str) for pid in context['problem_ids'])
                and sorted(context['problem_ids']) == sorted(p['id'] for p in scope['problems']))
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

    by_team, evidence_by_id, latest_submissions = {}, {}, {}
    for evidence in sorted(evidences, key=lambda e: (e['first_seen'], e['id'])):
        row = json.loads(evidence['data'])
        evidence_by_id[evidence['id']] = evidence
        if row.get('problem_id') != problem_id:
            continue
        if row.get('submission_id'):
            identity = (row['problem_id'], row['team_key'], row['submission_id'])
            latest = latest_submissions.get(identity)
            # Evidence is deduplicated: an old row may have been observed again
            # after a failure, so first_seen cannot decide its current validity.
            if latest is None or evidence['last_seen'] > latest[0]:
                latest_submissions[identity] = (evidence['last_seen'], row.get('eligible') is True)
        if row.get('eligible') is not True:
            continue
        key = _candidate_key(row, evidence['id'])
        by_team.setdefault(row['team_key'], {}).setdefault(key, (row, evidence))

    anchors = {}
    for row in snapshot['observations']:
        if row['problem_id'] == problem_id and _complete(row, cases, consistent):
            eid = digest({'scope': scope_id(scope), 'row': row})
            evidence = evidence_by_id.get(eid)
            if evidence is not None:
                anchors[_candidate_key(row, eid)] = (row, evidence)

    can_recompute = verified and baseline_complete
    if can_recompute:
        # Verify this exact benchmark/rule against every current official anchor.
        calibration = [(row, _recompute(row, cases, rule)) for row, _ in anchors.values()]
        if not calibration or any(score is None or Decimal(score) != Decimal(row['score'])
                                  for row, score in calibration):
            can_recompute = False
            reasons.append('公式与本轮完整官方成绩不能一致复现，历史重算已停止。')

    any_confirmed, any_missing = False, False
    for team in teams.values():
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
                identity = (row['problem_id'], row['team_key'], row['submission_id'])
                if not latest_submissions[identity][1]:
                    # Keep the former Pass as audit/unavailable evidence, but do
                    # not turn a subsequently invalidated submission into a peak.
                    reason = '部分历史提交的最新观测已失去有效成绩资格，旧通过版本不参与公式重算。'
                    if reason not in row_reasons:
                        row_reasons.append(reason)
                    continue
                score, kind = _recompute(row, cases, rule), 'recomputed-current'
                if score is None:
                    continue
                local_count += 1
            else:
                continue
            confirmed += 1
            derived = {**row, 'score': score, 'original_score': row['score'],
                       'evidence_id': evidence['id'], 'observed_at': evidence['first_seen'],
                       'score_basis_kind': kind, 'score_basis_as_of': snapshot['observed_at'],
                       'score_basis_source': rule_source}
            old = team['best'].get(problem_id)
            if old is None or Decimal(score) > Decimal(old['score']):
                team['best'][problem_id] = derived
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
            'as_of': snapshot['observed_at'], 'rule_source': rule_source,
            'formula': VERIFIED_FORMULAS[rule] if verified else None,
            'coverage_scope': 'observed-eligible-submissions',
            'formula_verified': verified, 'rule_digest': context.get('rule_digest') if isinstance(context, dict) else None,
            'baseline_complete': baseline_complete,
            'formula_recomputation_enabled': can_recompute, 'visible_testcase_count': visible,
            'total_testcase_count': len(cases), 'reasons': reasons}


def apply_current_basis(snapshot, teams, evidences):
    """Use the current problem list, never a remembered problem ID, as the boundary.

    A problem replacement must not silently fall back to cross-baseline maxima.
    Each problem has its own testcase metadata, calibration and best whole
    submission; only their derived scores and coverage counts are aggregated.
    """
    scope = snapshot['scope']
    starcup = (scope.get('demo') is False and scope.get('contest_id') == CONTEST_ID
               and scope.get('stage') == CONTEST_SLUG)
    if not starcup and not get_profile('jingdong-final').accepts_scope(scope):
        return None
    counters = ('historical_submissions', 'rescored_submissions', 'unavailable_submissions',
                'official_anchor_submissions', 'formula_rescored_submissions')
    for team in teams.values():
        team['observed_official_best'] = dict(team['best'])
        team['best'] = {}
        team['reasons'] = []
        for key in counters:
            team[key] = 0
    problems = []
    multiple = len(scope['problems']) > 1
    for problem in scope['problems']:
        pid = problem['id']
        local_teams = {key: {'team_key': key, 'best': {}} for key in teams}
        basis = _apply_problem_basis(snapshot, local_teams, evidences, pid)
        problems.append({'problem_id': pid, **basis})
        for key, local in local_teams.items():
            target = teams[key]
            target['best'].update(local['best'])
            for counter in counters:
                target[counter] += local[counter]
            prefix = str(problem.get('title') or pid) + '：' if multiple else ''
            target['reasons'].extend(prefix + reason for reason in local['reasons'])
    for team in teams.values():
        team['peak_status'] = ('unavailable' if not team['rescored_submissions'] else
                               'partial' if team['unavailable_submissions'] or
                               len(team['best']) < len(scope['problems']) else 'complete')
    # Keep the original top-level shape for clients and expose per-problem
    # details so a mixed public/hidden contest does not imply a shared TBest.
    result = dict(problems[0])
    result.pop('problem_id')
    result.update(
        problems=problems,
        status=('unavailable' if not any(t['rescored_submissions'] for t in teams.values()) else
                'partial' if any(t['unavailable_submissions'] or
                                 (t['rescored_submissions'] and len(t['best']) < len(scope['problems']))
                                 for t in teams.values()) else 'complete'),
        formula_verified=all(p['formula_verified'] for p in problems),
        baseline_complete=all(p['baseline_complete'] for p in problems),
        formula_recomputation_enabled=any(p['formula_recomputation_enabled'] for p in problems),
        visible_testcase_count=sum(p['visible_testcase_count'] for p in problems),
        total_testcase_count=sum(p['total_testcase_count'] for p in problems),
        reasons=list(dict.fromkeys(reason for p in problems for reason in p['reasons'])),
    )
    return result
