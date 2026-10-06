"""Only whole, verifiable submissions can define a current-baseline peak."""
import copy
import json

import pytest

from watcher.core import observation, scope_id, total_row
from watcher.scoring import CONTEST_ID, CONTEST_SLUG, FORMULA, PROBLEM_ID, RULE, RULE_SOURCE
from watcher.store import Store


def make_snapshot(index, score='70', submission='s1', times=None, hidden=False, status='Pass'):
    times = times or ([2] * 10 + [None] * 5 if hidden else [1, 2.25])
    cases = [{'_id': f'c{i}', 'hidden': True} if value is None else
             {'_id': f'c{i}', 'type': 'default', 'tbest': 1}
             for i, value in enumerate(times)]
    results = [{'testcase_id': f'c{i}', 'time': value,
                'precision_ratio': None if value is None else 1,
                'testcase_status': 'Hidden' if value is None else 'Pass', 'score': 0}
               for i, value in enumerate(times)]
    raw = {'team': {'_id': 'one', 'team_name': '一队'}, 'score': score, 'rank': 1,
           'status': status, 'submission_id': submission, 'result': results}
    scope = {'contest_id': CONTEST_ID, 'stage': CONTEST_SLUG, 'group': 'public',
             'epoch': 'version1', 'demo': False, 'title': '公开决赛',
             'problems': [{'id': PROBLEM_ID, 'title': '性能题', 'weight': 1}]}
    return {'schema': 1, 'scope': scope, 'observed_at': f'2026-01-01T{index:02}:00:00Z',
            'observations': [observation(PROBLEM_ID, raw)], 'totals': [total_row(raw)],
            'payloads': [{'problem_id': PROBLEM_ID,
                          'metadata': {'version': {'testcases': [{'_id': c['_id'], 'type': 'default'} for c in cases]}},
                          'pages': [{'data': {'testcases': cases}}]}], 'notes': [],
            'scoring_context': {'verified': True, 'rule': RULE, 'formula': FORMULA,
                                'problem_ids': [PROBLEM_ID], 'rule_source': RULE_SOURCE,
                                'rule_digest': 'a' * 64}}


@pytest.fixture
def store(tmp_path):
    return Store(str(tmp_path / 'scores.sqlite3'))


def board(store, *snapshots):
    for snapshot in snapshots:
        store.ingest(snapshot)
    return store.board(scope_id(snapshots[-1]['scope']))


def test_hidden_same_submission(store):
    old = make_snapshot(1, '83.1', hidden=True)
    new = make_snapshot(2, '66.49', hidden=True)
    new['observations'][0]['raw']['rank'] = 3
    for result in new['observations'][0]['raw']['result']:
        result['score'] = 7  # Derived testcase scores do not define a new performance.
    new['observations'][0] = observation(PROBLEM_ID, new['observations'][0]['raw'])
    out = board(store, old, new)
    row = out['rows'][0]
    assert row['peak_score'] == '66.49' and row['gap'] == '0.00'
    assert row['observed_official_peak_score'] == '83.1'
    assert row['historical_submissions'] == row['rescored_submissions'] == 1
    assert row['unavailable_submissions'] == row['formula_rescored_submissions'] == 0
    assert row['official_anchor_submissions'] == 1 and row['peak_status'] == 'complete'
    assert row['best'][0]['original_score'] == '66.49'
    assert row['best'][0]['score_basis_kind'] == 'official-current'
    assert store.evidence(row['best'][0]['evidence_id'])['observation']['score'] == '66.49'
    basis = out['score_basis']
    assert (basis['visible_testcase_count'], basis['total_testcase_count']) == (10, 15)
    assert basis['coverage_scope'] == 'observed-eligible-submissions'
    assert basis['rule_digest'] == 'a' * 64 and basis['formula_verified']
    assert not basis['formula_recomputation_enabled']


def test_hidden_changed_submission(store):
    out = board(store, make_snapshot(1, '90', submission='old', hidden=True),
                make_snapshot(2, '70', submission='new', hidden=True))
    row = out['rows'][0]
    assert row['peak_score'] == '70' and row['observed_official_peak_score'] == '90'
    assert row['historical_submissions'] == 2 and row['rescored_submissions'] == 1
    assert row['unavailable_submissions'] == 1
    assert row['peak_status'] == out['score_basis']['status'] == 'partial'
    assert any('下界' in reason for reason in row['reasons'])


def test_same_id_changed_performance(store):
    old = make_snapshot(1, '90', hidden=True)
    new = make_snapshot(2, '70', times=[3] * 10 + [None] * 5)
    out = board(store, old, new)
    row = out['rows'][0]
    assert row['peak_score'] == '70' and row['historical_submissions'] == 2
    assert row['unavailable_submissions'] == 1


def test_no_current_anchor(store):
    out = board(store, make_snapshot(1, '90', hidden=True),
                make_snapshot(2, '0', submission='bad', hidden=True, status='Wrong Answer'))
    row = out['rows'][0]
    assert row['peak_score'] is None and row['peak_rank'] is None and row['gap'] is None
    assert row['observed_official_peak_score'] == '90' and row['best'] == []
    assert row['historical_submissions'] == row['unavailable_submissions'] == 1
    assert row['peak_status'] == out['score_basis']['status'] == 'unavailable'


def test_whole_history_rescore(store):
    first = make_snapshot(1, '90', submission='a', times=[1, 2.25])
    second = make_snapshot(2, '80', submission='b', times=[2.25, 1])
    current = make_snapshot(3, '33.33', submission='c', times=[2.25, 2.25])
    out = board(store, first, second, current)
    row = out['rows'][0]
    # Two complementary submissions each score 66.67; stitching would wrongly give 100.
    assert row['peak_score'] == '66.67' and row['gap'] == '33.34'
    assert row['observed_official_peak_score'] == '90'
    assert row['historical_submissions'] == row['rescored_submissions'] == 3
    assert row['formula_rescored_submissions'] == 2 and row['official_anchor_submissions'] == 1
    assert row['peak_status'] == out['score_basis']['status'] == 'complete'
    assert out['score_basis']['formula_recomputation_enabled']
    best = row['best'][0]
    assert best['original_score'] == '90' and best['submission_id'] == 'a'
    assert best['score_basis_kind'] == 'recomputed-current'
    assert [result['time'] for result in best['result']] == [1, 2.25]
    assert store.evidence(best['evidence_id'])['observation']['score'] == '90'


def test_exact_calibration_required(store):
    out = board(store, make_snapshot(1, '90', submission='old'),
                make_snapshot(2, '66.68', submission='new'))
    row = out['rows'][0]
    assert row['peak_score'] == '66.68' and row['unavailable_submissions'] == 1
    assert not out['score_basis']['formula_recomputation_enabled']
    assert any('一致复现' in reason for reason in out['score_basis']['reasons'])


@pytest.mark.parametrize('mode', ['none', 'unverified', 'wrong-rule', 'wrong-problem'])
def test_unverified_rule(store, mode):
    current = make_snapshot(2, '66.67', submission='new')
    if mode == 'none':
        del current['scoring_context']
    elif mode == 'unverified':
        current['scoring_context']['verified'] = False
    elif mode == 'wrong-rule':
        current['scoring_context']['rule'] = 'other-rule'
    else:
        current['scoring_context']['problem_ids'] = ['other']
    out = board(store, make_snapshot(1, '90', submission='old'), current)
    assert out['rows'][0]['peak_score'] == '66.67'
    assert out['rows'][0]['unavailable_submissions'] == 1
    assert not out['score_basis']['formula_verified']


@pytest.mark.parametrize('mode', ['missing-case', 'duplicate-case', 'metadata-missing', 'version-missing', 'metadata-duplicate', 'other-page'])
def test_incomplete_metadata(store, mode):
    current = make_snapshot(1, '70', hidden=True)
    payload = current['payloads'][0]
    if mode == 'missing-case':
        payload['pages'][0]['data']['testcases'].pop()
    elif mode == 'duplicate-case':
        payload['pages'][0]['data']['testcases'].append(copy.deepcopy(payload['pages'][0]['data']['testcases'][0]))
    elif mode == 'metadata-missing':
        payload['metadata']['version']['testcases'] = None
    elif mode == 'version-missing':
        payload['metadata']['version'] = None
    elif mode == 'metadata-duplicate':
        payload['metadata']['version']['testcases'].append(copy.deepcopy(payload['metadata']['version']['testcases'][0]))
    else:
        page = copy.deepcopy(payload['pages'][0])
        page['data']['testcases'][0]['tbest'] = 2
        payload['pages'].append(page)
    out = board(store, current)
    assert out['rows'][0]['peak_score'] is None
    assert out['rows'][0]['observed_official_peak_score'] == '70'
    assert out['score_basis']['status'] == 'unavailable'


@pytest.mark.parametrize('value', [None, 0, -1, 'NaN', 'Infinity', True])
def test_invalid_baseline(store, value):
    current = make_snapshot(2, '66.67', submission='new')
    current['payloads'][0]['pages'][0]['data']['testcases'][0]['tbest'] = value
    out = board(store, make_snapshot(1, '90', submission='old'), current)
    assert out['rows'][0]['peak_score'] == '66.67'
    assert out['rows'][0]['unavailable_submissions'] == 1
    assert not out['score_basis']['baseline_complete']


@pytest.mark.parametrize('mode', ['missing-case', 'duplicate-case', 'invalid-time', 'faster-than-best'])
def test_unusable_history(store, mode):
    old = make_snapshot(1, '90', submission='old')
    raw = old['observations'][0]['raw']
    if mode == 'missing-case':
        raw['result'].pop()
    elif mode == 'duplicate-case':
        raw['result'].append(copy.deepcopy(raw['result'][0]))
    else:
        raw['result'][0]['time'] = 0 if mode == 'invalid-time' else 0.5
    old['observations'][0] = observation(PROBLEM_ID, raw)
    out = board(store, old, make_snapshot(2, '66.67', submission='new'))
    assert out['rows'][0]['peak_score'] == '66.67'
    assert out['rows'][0]['unavailable_submissions'] == 1
    assert out['rows'][0]['formula_rescored_submissions'] == 0


def test_read_only_scores(store):
    old = make_snapshot(1, '90', submission='old')
    new = make_snapshot(2, '66.67', submission='new')
    store.ingest(old)
    store.ingest(new)
    original_export = ''.join(store.export())
    with store.connect() as db:
        original_evidence = [tuple(row) for row in db.execute('SELECT * FROM evidence ORDER BY id')]
        original_snapshots = [tuple(row) for row in db.execute('SELECT * FROM snapshots ORDER BY id')]
    out = store.board(scope_id(new['scope']))
    assert out['rows'][0]['best'][0]['score'] == '66.67'
    assert ''.join(store.export()) == original_export
    with store.connect() as db:
        assert [tuple(row) for row in db.execute('SELECT * FROM evidence ORDER BY id')] == original_evidence
        assert [tuple(row) for row in db.execute('SELECT * FROM snapshots ORDER BY id')] == original_snapshots
    assert json.loads(original_export.splitlines()[0])['observations'][0]['score'] == '90'


@pytest.mark.parametrize('mode', ['demo', 'contest', 'stage', 'problem'])
def test_other_scopes_unchanged(store, mode):
    old = make_snapshot(1, '90', hidden=True)
    new = make_snapshot(2, '70', hidden=True)
    for snapshot in (old, new):
        if mode == 'demo':
            snapshot['scope']['demo'] = True
        elif mode == 'contest':
            snapshot['scope']['contest_id'] = 'another-contest'
        elif mode == 'stage':
            snapshot['scope']['stage'] = 'another-stage'
        else:
            snapshot['scope']['problems'][0]['id'] = 'other-problem'
            snapshot['observations'][0]['problem_id'] = 'other-problem'
    out = board(store, old, new)
    assert out['rows'][0]['peak_score'] == '90' and out['rows'][0]['gap'] == '20'
    assert 'score_basis' not in out and 'observed_official_peak_score' not in out['rows'][0]
    assert out['semantics'] == 'sum_of_observed_problem_score_maxima'
