"""Latest-submission contests must not turn unknown history into current peaks."""
import copy

import httpx
import pytest

from test_live_source import RULE_TEXT
from test_scoring import make_snapshot
from watcher.core import ContractError, scope_id, validate_snapshot
from watcher.profiles import get_profile
from watcher.scoring import RATIO_FORMULA, RATIO_RULE
from watcher.source import Client, collect_contest, scoring_context
from watcher.store import Store


PROFILE = get_profile('jingdong-final')
PID, = PROFILE.problem_ids


def jingdong(index, **kwargs):
    snapshot = make_snapshot(index, **kwargs)
    snapshot['scope'].update(contest_id=PROFILE.contest_id, stage=PROFILE.contest_slug,
                             ranking_scope='problem')
    snapshot['scope']['problems'][0]['id'] = PID
    snapshot['observations'][0]['problem_id'] = PID
    snapshot['payloads'][0]['problem_id'] = PID
    snapshot['scoring_context']['problem_ids'] = [PID]
    snapshot['scoring_context']['rule_source'] = 'https://cannjudge.cn/public/' + PROFILE.contest_slug + '/scoring-rules'
    return snapshot


def board(tmp_path, *snapshots):
    store = Store(str(tmp_path / 'live.sqlite3'))
    for snapshot in snapshots:
        store.ingest(snapshot)
    return store.board(scope_id(snapshots[-1]['scope']))


def test_hidden_latest_submission_has_unknown_peak_not_a_current_score_fallback(tmp_path):
    old = jingdong(1, score='90', submission='old', hidden=True)
    new = jingdong(2, score='70', submission='latest', hidden=True)
    new['scoring_context']['verified'] = False
    result = board(tmp_path, old, new)
    row, = result['rows']
    assert row['official_score'] == '70'
    assert row['observed_official_peak_score'] == '90'
    assert row['confirmed_peak_lower_bound'] == '70'
    assert row['current_baseline_history_peak_score'] is None
    assert row['history_peak_status'] == 'insufficient-data'
    assert row['history_peak_gap'] is None
    assert row['historical_submissions'] == 2 and row['unavailable_submissions'] == 1
    assert result['score_basis']['formula'] is None
    assert result['score_basis']['rule_source'].endswith('/op_challenge_jingdong_final/scoring-rules')
    assert not result['history_coverage']['all_contest_submissions_complete']


def test_first_snapshot_can_confirm_only_its_one_observed_submission(tmp_path):
    result = board(tmp_path, jingdong(1, score='70', hidden=True))
    row, = result['rows']
    assert row['current_baseline_history_peak_score'] == '70'
    assert row['history_peak_status'] == 'verified-observed'
    assert row['historical_submissions'] == 1
    assert result['history_coverage']['missed_between_polls_possible']
    assert not result['score_basis']['formula_recomputation_enabled']


def test_verified_log_history_still_can_exceed_latest_submission_without_stitching(tmp_path):
    result = board(tmp_path, jingdong(1, score='90', submission='a', times=[1, 2.25]),
                   jingdong(2, score='80', submission='b', times=[2.25, 1]),
                   jingdong(3, score='33.33', submission='latest', times=[2.25, 2.25]))
    row, = result['rows']
    assert row['current_baseline_history_peak_score'] == '66.67'
    assert row['history_peak_gap'] == '33.34'
    assert row['observed_official_peak_score'] == '90'
    assert row['history_peak_status'] == 'verified-observed'
    assert row['formula_rescored_submissions'] == 2


def test_ratio_rule_uses_whole_submissions_and_current_calibration(tmp_path):
    old = jingdong(1, score='90', submission='old', times=[1, 4])
    new = jingdong(2, score='25', submission='latest', times=[4, 4])
    for snapshot in (old, new):
        snapshot['scoring_context'].update(rule=RATIO_RULE, formula=RATIO_FORMULA)
    result = board(tmp_path, old, new)
    row, = result['rows']
    assert row['current_baseline_history_peak_score'] == '62.50'
    assert row['history_peak_gap'] == '37.50'
    assert result['score_basis']['formula'] == RATIO_FORMULA
    assert result['score_basis']['formula_recomputation_enabled']
    assert row['best'][0]['submission_id'] == 'old'


def test_ratio_rule_mismatch_does_not_borrow_a_logarithmic_formula(tmp_path):
    old = jingdong(1, score='90', submission='old', times=[1, 4])
    new = jingdong(2, score='33.33', submission='latest', times=[4, 4])
    new['scoring_context'].update(rule=RATIO_RULE, formula=RATIO_FORMULA)
    result = board(tmp_path, old, new)
    assert not result['score_basis']['formula_recomputation_enabled']
    assert result['rows'][0]['current_baseline_history_peak_score'] is None


def test_rule_verification_distinguishes_ratio_log_missing_and_conflicting_text():
    base = {'name': PROFILE.contest_slug, 'scoring_rules_enabled': True, 'scoring_rule': 'default'}
    ratio_text = ('测试点得分 = (TBest / 你的用时) × 100。'
                  'TBest：每个测试点在所有参赛者提交中的历史最快用时。'
                  '题目分是所有测试点得分的平均值（保留两位小数）。')
    context = scoring_context({**base, 'scoring_rules_content': ratio_text})
    assert context['verified'] and context['rule'] == RATIO_RULE
    assert context['formula'] == RATIO_FORMULA
    assert not scoring_context({**base, 'scoring_rules_content': '请按要求实现 AscendC 算子'})['verified']
    assert not scoring_context({**base, 'scoring_rules_content': ratio_text + RULE_TEXT})['verified']


def source_schema():
    snapshot = jingdong(1, score='70', hidden=True)
    raw = snapshot['observations'][0]['raw']
    contest = {'_id': PROFILE.contest_id, 'name': PROFILE.contest_slug, 'title': '京津东北决赛',
               'problems': [{'problem_id': PID}, {'problem_id': 'another-problem'}],
               'scoring_rules_enabled': True, 'scoring_rule': 'default',
               'scoring_rules_content': '请按要求实现 AscendC 算子', 'show_total_ranking': True}
    problem = {'_id': PID, 'name': 'varlenndrotaryposemb', 'title': 'VarLenNdRotaryPosEmb',
               'ranking_submission_mode': 'latest', 'score_mode': 1, 'use_baseline': False,
               'testcases': [{'testcase_id': {'_id': f'c{i}', 'type': 'default'}} for i in range(15)]}
    routes = {'/api/contests/' + PROFILE.contest_id: contest, '/api/problems/' + PID: problem,
              '/api/problems/' + PID + '/ranking': {'rows': [raw], 'total': 1,
               'testcases': snapshot['payloads'][0]['pages'][0]['data']['testcases']}}
    config = {'request_gap_seconds': 0, 'cookie_env': '', 'verify_scoring_rules': True,
              'problem_ids': [PID], 'ranking_scope': 'problem'}
    return routes, config, contest


def test_selected_problem_uses_its_own_official_rank_not_contest_totals():
    routes, config, contest = source_schema()
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=routes[request.url.path])
    client = Client(config, transport=httpx.MockTransport(handler))
    try:
        snapshot = validate_snapshot(collect_contest(client, contest, config))
    finally:
        client.close()
    assert {p['id'] for p in snapshot['scope']['problems']} == {PID}
    assert snapshot['totals'][0]['score'] == '70' and snapshot['totals'][0]['rank'] == 1
    assert snapshot['scope']['ranking_scope'] == 'problem'
    assert snapshot['scope']['ranking_url'].endswith('/varlenndrotaryposemb/ranking')
    assert snapshot['scoring_context']['problem_ids'] == [PID]
    assert not snapshot['scoring_context']['verified']
    assert all(request.method == 'GET' and 'cookie' not in request.headers for request in requests)
    assert not any('/stats' in request.url.path or 'another-problem' in request.url.path for request in requests)
    assert any('最新提交' in note for note in snapshot['notes'])


@pytest.mark.parametrize('ids', [[], [PID, PID], ['missing-problem'], 'a-string'])
def test_invalid_selected_problem_cannot_publish_a_different_problem(ids):
    routes, config, contest = source_schema()
    config['problem_ids'] = ids
    client = Client(config, transport=httpx.MockTransport(lambda request: httpx.Response(200, json=routes[request.url.path])))
    try:
        with pytest.raises(ContractError):
            collect_contest(client, contest, config)
    finally:
        client.close()


def test_failed_latest_submission_keeps_raw_history_but_cannot_confirm_peak(tmp_path):
    result = board(tmp_path, jingdong(1, score='90', submission='old', hidden=True),
                   jingdong(2, score='0', submission='latest', hidden=True, status='Wrong Answer'))
    row, = result['rows']
    assert row['current_baseline_history_peak_score'] is None
    assert row['confirmed_peak_lower_bound'] is None
    assert row['observed_official_peak_score'] == '90'

