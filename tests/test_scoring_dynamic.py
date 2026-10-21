"""A replaced or additional live problem must never restore stale raw peaks."""
import copy
from decimal import Decimal

import pytest

from test_scoring import make_snapshot
from watcher.core import observation, scope_id, total_row
from watcher.store import Store


NEW_PROBLEM = '6ac8bc7c694b590c3c96728a'
SECOND_PROBLEM = 'another-current-problem'


def single(index, problem=NEW_PROBLEM, **kwargs):
    snapshot = make_snapshot(index, **kwargs)
    snapshot['scope']['problems'][0]['id'] = problem
    snapshot['scope']['problems'][0]['title'] = problem
    snapshot['observations'][0]['problem_id'] = problem
    snapshot['payloads'][0]['problem_id'] = problem
    snapshot['scoring_context']['problem_ids'] = [problem]
    return snapshot


def together(*snapshots):
    """Combine same-generation fixtures without changing any row evidence."""
    out = copy.deepcopy(snapshots[0])
    out['scope']['problems'] = [copy.deepcopy(problem) for snapshot in snapshots
                                for problem in snapshot['scope']['problems']]
    out['observations'] = [copy.deepcopy(row) for snapshot in snapshots
                           for row in snapshot['observations']]
    out['payloads'] = [copy.deepcopy(payload) for snapshot in snapshots
                      for payload in snapshot['payloads']]
    out['scoring_context']['problem_ids'] = sorted(problem['id'] for problem in out['scope']['problems'])
    by_team = {}
    for row in out['observations']:
        by_team.setdefault(row['team_key'], []).append(row)
    out['totals'] = []
    for rows in by_team.values():
        raw = copy.deepcopy(rows[0]['raw'])
        raw['score'] = str(sum((Decimal(row['score']) for row in rows), Decimal(0)))
        out['totals'].append(total_row(raw))
    return out


@pytest.fixture
def store(tmp_path):
    return Store(str(tmp_path / 'dynamic-scores.sqlite3'))


def board(store, *snapshots):
    for snapshot in snapshots:
        store.ingest(snapshot)
    return store.board(scope_id(snapshots[-1]['scope']))


def per_problem(out):
    return {basis['problem_id']: basis for basis in out['score_basis']['problems']}


def test_replaced_problem_hidden_same_submission_uses_current_official_score(store):
    out = board(store, single(1, score='90', hidden=True),
                single(2, score='70', hidden=True))
    row, = out['rows']
    assert out['semantics'] == 'current_baseline_confirmed_submission_maxima'
    assert row['peak_score'] == '70' and row['observed_official_peak_score'] == '90'
    assert row['historical_submissions'] == row['official_anchor_submissions'] == 1
    assert row['formula_rescored_submissions'] == row['unavailable_submissions'] == 0
    assert row['best'][0]['problem_id'] == NEW_PROBLEM
    assert row['best'][0]['score_basis_kind'] == 'official-current'
    assert not out['score_basis']['formula_recomputation_enabled']
    assert not out['score_basis']['baseline_complete']
    assert out['score_basis']['formula_verified']
    assert set(per_problem(out)) == {NEW_PROBLEM}
    assert (out['score_basis']['visible_testcase_count'], out['score_basis']['total_testcase_count']) == (10, 15)


def test_replaced_problem_hidden_old_submission_is_not_a_current_peak(store):
    out = board(store, single(1, score='90', submission='old', hidden=True),
                single(2, score='70', submission='new', hidden=True))
    row, = out['rows']
    assert row['peak_score'] == '70' and row['observed_official_peak_score'] == '90'
    assert row['historical_submissions'] == 2
    assert row['rescored_submissions'] == row['official_anchor_submissions'] == 1
    assert row['unavailable_submissions'] == 1 and row['peak_status'] == 'partial'


def test_two_problems_with_identical_submission_and_performance_do_not_collide(store):
    current = together(single(1, score='66.67', submission='same-id'),
                       single(1, problem=SECOND_PROBLEM, score='66.67', submission='same-id'))
    out = board(store, current)
    row, = out['rows']
    assert row['peak_score'] == '133.34'
    assert {best['problem_id'] for best in row['best']} == {NEW_PROBLEM, SECOND_PROBLEM}
    assert row['historical_submissions'] == row['rescored_submissions'] == 2
    assert row['official_anchor_submissions'] == 2 and row['formula_rescored_submissions'] == 0
    assert out['score_basis']['formula_recomputation_enabled']
    assert out['score_basis']['baseline_complete'] and out['score_basis']['formula_verified']
    assert (out['score_basis']['visible_testcase_count'], out['score_basis']['total_testcase_count']) == (4, 4)


def test_each_problem_calibrates_independently(store):
    old = together(single(1, score='66.67', submission='old'),
                   single(1, problem=SECOND_PROBLEM, score='90', submission='old'))
    current = together(single(2, score='33.33', submission='new', times=[2.25, 2.25]),
                       single(2, problem=SECOND_PROBLEM, score='35', submission='new', times=[2.25, 2.25]))
    out = board(store, old, current)
    row, = out['rows']
    best = {item['problem_id']: item for item in row['best']}
    assert best[NEW_PROBLEM]['score'] == '66.67'
    assert best[NEW_PROBLEM]['score_basis_kind'] == 'recomputed-current'
    assert best[SECOND_PROBLEM]['score'] == '35'
    assert best[SECOND_PROBLEM]['score_basis_kind'] == 'official-current'
    assert row['peak_score'] == '101.67' and row['observed_official_peak_score'] == '156.67'
    assert row['historical_submissions'] == 4 and row['rescored_submissions'] == 3
    assert row['official_anchor_submissions'] == 2 and row['formula_rescored_submissions'] == 1
    assert row['unavailable_submissions'] == 1 and row['peak_status'] == 'partial'
    assert per_problem(out)[NEW_PROBLEM]['formula_recomputation_enabled']
    assert not per_problem(out)[SECOND_PROBLEM]['formula_recomputation_enabled']
    assert out['score_basis']['formula_recomputation_enabled']
    assert out['score_basis']['baseline_complete'] and out['score_basis']['formula_verified']


def test_hidden_problem_does_not_disable_another_problem_recomputation(store):
    old = together(single(1, score='66.67', submission='old'),
                   single(1, problem=SECOND_PROBLEM, score='90', submission='old', hidden=True))
    current = together(single(2, score='33.33', submission='new', times=[2.25, 2.25]),
                       single(2, problem=SECOND_PROBLEM, score='70', submission='new', hidden=True))
    out = board(store, old, current)
    row, = out['rows']
    assert row['peak_score'] == '136.67'
    assert row['formula_rescored_submissions'] == 1 and row['official_anchor_submissions'] == 2
    assert row['unavailable_submissions'] == 1
    assert out['score_basis']['formula_recomputation_enabled']
    assert not out['score_basis']['baseline_complete']
    assert out['score_basis']['formula_verified']
    assert (out['score_basis']['visible_testcase_count'], out['score_basis']['total_testcase_count']) == (12, 17)


def test_rule_problem_ids_are_an_order_independent_exact_set(store):
    current = together(single(1, score='66.67'),
                       single(1, problem=SECOND_PROBLEM, score='66.67'))
    current['scoring_context']['problem_ids'].reverse()
    out = board(store, current)
    assert out['score_basis']['formula_verified']
    assert all(basis['formula_verified'] for basis in per_problem(out).values())


@pytest.mark.parametrize('problem_ids', [[], [NEW_PROBLEM], [NEW_PROBLEM, SECOND_PROBLEM, 'unscoped'],
                                        [NEW_PROBLEM, SECOND_PROBLEM, NEW_PROBLEM], None, NEW_PROBLEM])
def test_inexact_rule_problem_ids_do_not_enable_historical_recomputation(store, problem_ids):
    old = together(single(1, score='90', submission='old'),
                   single(1, problem=SECOND_PROBLEM, score='90', submission='old'))
    current = together(single(2, score='33.33', submission='new', times=[2.25, 2.25]),
                       single(2, problem=SECOND_PROBLEM, score='33.33', submission='new', times=[2.25, 2.25]))
    current['scoring_context']['problem_ids'] = problem_ids
    out = board(store, old, current)
    row, = out['rows']
    assert not out['score_basis']['formula_verified']
    assert not out['score_basis']['formula_recomputation_enabled']
    assert all(not basis['formula_verified'] for basis in per_problem(out).values())
    assert row['peak_score'] == '66.66'
    assert row['official_anchor_submissions'] == row['unavailable_submissions'] == 2
    assert row['formula_rescored_submissions'] == 0


def test_tbest_change_can_change_which_whole_historical_submission_is_best(store):
    first = single(1, score='66.67', submission='a', times=[1, 2.25])
    second = single(2, score='57.15', submission='b', times=[2.25, 1.1])
    current = single(3, score='22.43', submission='c', times=[2.25, 2.25])
    current['payloads'][0]['pages'][0]['data']['testcases'][0]['tbest'] = 0.1
    out = board(store, first, second, current)
    row, = out['rows']
    # Old baseline: A=66.67 > B=57.15. New baseline: A=24.15 < B=46.24.
    assert row['peak_score'] == '46.24' and row['observed_official_peak_score'] == '66.67'
    assert row['best'][0]['submission_id'] == 'b'
    assert row['best'][0]['original_score'] == '57.15'
    assert row['best'][0]['score_basis_kind'] == 'recomputed-current'
    assert row['historical_submissions'] == row['rescored_submissions'] == 3
    assert row['formula_rescored_submissions'] == 2 and row['official_anchor_submissions'] == 1
    assert row['unavailable_submissions'] == 0 and row['peak_status'] == 'complete'
    assert out['score_basis']['formula_recomputation_enabled']


def test_missing_current_problem_retains_only_confirmable_partial_score(store):
    old = together(single(1, score='90', submission='old', hidden=True),
                   single(1, problem=SECOND_PROBLEM, score='80', submission='old', hidden=True))
    current = together(single(2, score='70', submission='new', hidden=True),
                       single(2, problem=SECOND_PROBLEM, score='60', submission='new', hidden=True))
    current['observations'] = [row for row in current['observations'] if row['problem_id'] == NEW_PROBLEM]
    current['totals'] = []
    out = board(store, old, current)
    row, = out['rows']
    assert row['peak_score'] == '70' and row['current_sum'] is None
    assert row['observed_problems'] == 1 and row['total_problems'] == 2
    assert row['historical_submissions'] == 3 and row['rescored_submissions'] == 1
    assert row['unavailable_submissions'] == 2
    assert row['peak_status'] == out['score_basis']['status'] == 'partial'
    assert {best['problem_id'] for best in row['best']} == {NEW_PROBLEM}
    assert row['observed_official_peak_score'] == '170'


def with_calibrator(snapshot, submission='calibrator'):
    """A different team's complete Pass keeps the formula branch enabled."""
    problem = snapshot['scope']['problems'][0]['id']
    raw = single(1, problem=problem, score='33.33', submission=submission,
                 times=[2.25, 2.25])['observations'][0]['raw']
    raw['team'] = {'_id': 'two', 'team_name': '校准队伍'}
    snapshot['observations'].append(observation(problem, raw))
    snapshot['totals'].append(total_row(raw))
    return snapshot


def invalidated(snapshot, mode='failed'):
    row = snapshot['observations'][0]
    raw = row['raw']
    if mode == 'failed':
        raw['status'] = 'Wrong Answer'
        raw['score'] = '0'
        raw['result'][0]['testcase_status'] = 'Wrong Answer'
    elif mode == 'unknown-score':
        raw['score'] = None
    else:
        raw['result'][0]['testcase_status'] = 'Wrong Answer'
    snapshot['observations'][0] = observation(row['problem_id'], raw)
    snapshot['totals'][0] = total_row(raw)
    return snapshot


@pytest.mark.parametrize('mode', ['failed', 'unknown-score', 'invalid-case'])
def test_latest_ineligible_same_submission_cannot_be_rescored_as_an_old_pass(store, mode):
    old = single(1, score='66.67', submission='rejudged')
    current = with_calibrator(invalidated(single(2, score='66.67', submission='rejudged'), mode))
    out = board(store, old, current)
    row = next(row for row in out['rows'] if row['team_key'] == 'team:one')
    assert out['score_basis']['formula_recomputation_enabled']
    assert row['peak_score'] is None and row['best'] == []
    assert row['observed_official_peak_score'] == '66.67'
    assert row['historical_submissions'] == row['unavailable_submissions'] == 1
    assert row['rescored_submissions'] == row['formula_rescored_submissions'] == 0
    assert row['peak_status'] == 'unavailable' and out['score_basis']['status'] == 'partial'
    assert any('资格' in reason for reason in row['reasons'])
    # The old Pass is still available as unchanged audit evidence.
    evidence = store.evidence(row['observed_official_best'][0]['evidence_id'])
    assert evidence['observation']['eligible'] and evidence['observation']['score'] == '66.67'
    assert len(list(store.export())) == 2


def test_latest_pass_restores_formula_eligibility_using_last_seen_not_first_seen(store):
    old = single(1, score='66.67', submission='rejudged')
    failed = invalidated(single(2, score='66.67', submission='rejudged'))
    restored = copy.deepcopy(old)
    restored['observed_at'] = '2026-01-01T03:00:00Z'
    current = with_calibrator(single(4, score='33.33', submission='different', times=[2.25, 2.25]))
    out = board(store, old, failed, restored, current)
    row = next(row for row in out['rows'] if row['team_key'] == 'team:one')
    assert row['peak_score'] == '66.67'
    assert row['best'][0]['submission_id'] == 'rejudged'
    assert row['best'][0]['score_basis_kind'] == 'recomputed-current'
    assert row['formula_rescored_submissions'] == row['official_anchor_submissions'] == 1
    assert row['unavailable_submissions'] == 0 and row['peak_status'] == 'complete'
    evidence = store.evidence(row['best'][0]['evidence_id'])
    assert evidence['first_seen'].startswith('2026-01-01T01:')
    assert evidence['last_seen'].startswith('2026-01-01T03:')


def test_repeated_failure_overrides_a_pass_by_last_seen_even_after_out_of_order_ingestion(store):
    failed = invalidated(single(1, score='66.67', submission='rejudged'))
    passed = single(2, score='66.67', submission='rejudged')
    failed_again = copy.deepcopy(failed)
    failed_again['observed_at'] = '2026-01-01T03:00:00Z'
    current = with_calibrator(single(4, score='33.33', submission='different', times=[2.25, 2.25]))
    out = board(store, failed_again, current, passed, failed)
    row = next(row for row in out['rows'] if row['team_key'] == 'team:one')
    assert out['score_basis']['formula_recomputation_enabled']
    assert row['peak_score'] == '33.33'
    assert row['best'][0]['submission_id'] == 'different'
    assert row['official_anchor_submissions'] == 1 and row['formula_rescored_submissions'] == 0
    assert row['historical_submissions'] == 2 and row['unavailable_submissions'] == 1
    assert row['peak_status'] == 'partial'


def test_failed_other_submission_does_not_invalidate_an_older_distinct_submission(store):
    old = single(1, score='66.67', submission='still-valid')
    current = with_calibrator(invalidated(single(2, score='66.67', submission='different-failed')))
    out = board(store, old, current)
    row = next(row for row in out['rows'] if row['team_key'] == 'team:one')
    assert out['score_basis']['formula_recomputation_enabled']
    assert row['peak_score'] == '66.67'
    assert row['best'][0]['submission_id'] == 'still-valid'
    assert row['formula_rescored_submissions'] == 1 and row['unavailable_submissions'] == 0


def test_failed_same_submission_id_on_other_problem_or_team_does_not_spread(store):
    old = together(with_calibrator(single(1, score='66.67', submission='shared')),
                   with_calibrator(single(1, problem=SECOND_PROBLEM, score='66.67', submission='shared')))
    first = with_calibrator(invalidated(single(2, score='66.67', submission='shared')), submission='shared')
    second = with_calibrator(single(2, problem=SECOND_PROBLEM, score='33.33',
                                    submission='different', times=[2.25, 2.25]))
    out = board(store, old, together(first, second))
    row = next(row for row in out['rows'] if row['team_key'] == 'team:one')
    assert row['peak_score'] == '66.67'
    assert row['best'][0]['problem_id'] == SECOND_PROBLEM
    assert row['best'][0]['submission_id'] == 'shared'
    assert row['formula_rescored_submissions'] == 1 and row['unavailable_submissions'] == 1
    other = next(row for row in out['rows'] if row['team_key'] == 'team:two')
    assert other['peak_score'] == '66.66' and other['unavailable_submissions'] == 0


def test_current_pass_anchor_takes_priority_after_historical_failure(store):
    old = invalidated(single(1, score='66.67', submission='rejudged'))
    current = with_calibrator(single(2, score='66.67', submission='rejudged'))
    out = board(store, old, current)
    row = next(row for row in out['rows'] if row['team_key'] == 'team:one')
    assert row['peak_score'] == '66.67'
    assert row['best'][0]['score_basis_kind'] == 'official-current'
    assert row['official_anchor_submissions'] == 1 and row['formula_rescored_submissions'] == 0
    assert row['unavailable_submissions'] == 0


def test_another_teams_failed_same_id_does_not_block_historical_recomputation(store):
    old = with_calibrator(single(1, score='66.67', submission='shared'), submission='shared')
    other_raw = copy.deepcopy(old['observations'][0]['raw'])
    other_raw['team'] = {'_id': 'two', 'team_name': '校准队伍'}
    old['observations'][1] = observation(NEW_PROBLEM, other_raw)
    old['totals'][1] = total_row(other_raw)
    current = with_calibrator(invalidated(single(2, score='66.67', submission='shared')),
                              submission='different')
    out = board(store, old, current)
    other = next(row for row in out['rows'] if row['team_key'] == 'team:two')
    assert out['score_basis']['formula_recomputation_enabled']
    assert other['peak_score'] == '66.67'
    assert other['best'][0]['submission_id'] == 'shared'
    assert other['best'][0]['score_basis_kind'] == 'recomputed-current'
    assert other['formula_rescored_submissions'] == 1 and other['unavailable_submissions'] == 0
