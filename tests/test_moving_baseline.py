"""A competitor's record reprices past whole submissions; old 100s never freeze."""
import copy
from decimal import Decimal

import pytest

from test_jingdong_scoring import jingdong, PID
from watcher.core import observation, scope_id, total_row
from watcher.scoring import FORMULA, RULE, RATIO_FORMULA, RATIO_RULE
from watcher.store import Store


def entry(team, submission, score, times, status='Pass'):
    return {'team': team, 'submission': submission, 'score': score,
            'times': times, 'status': status}


def generation(index, rule, references, rows):
    """Explicit official scores are hand-derived fixtures, not calls to scoring."""
    snapshot = jingdong(index, score='100', times=references)
    for case, reference in zip(snapshot['payloads'][0]['pages'][0]['data']['testcases'], references):
        if reference is not None:
            case['tbest'] = reference
    snapshot['scoring_context'].update(
        rule=rule, formula=RATIO_FORMULA if rule == RATIO_RULE else FORMULA)
    snapshot['observations'], snapshot['totals'] = [], []
    for spec in rows:
        fixture = jingdong(index, score=spec['score'], times=spec['times'],
                           submission=spec['submission'], status=spec['status'])
        raw = copy.deepcopy(fixture['observations'][0]['raw'])
        raw['team'] = {'_id': spec['team'], 'team_name': '队伍' + spec['team']}
        snapshot['observations'].append(observation(PID, raw))
        snapshot['totals'].append(total_row(raw))
    return snapshot


@pytest.fixture
def store(tmp_path):
    return Store(str(tmp_path / 'moving.sqlite3'))


def ingest(store, snapshot):
    store.ingest(snapshot)
    return store.board(scope_id(snapshot['scope']))


def team(board, name='A'):
    return next(row for row in board['rows'] if row['team_key'] == 'team:' + name)


@pytest.mark.parametrize('rule,original,improved', [
    (RATIO_RULE, 4, 2), (RULE, 2.25, 1.5),
])
def test_a_does_not_need_a_new_submission_for_its_old_100_to_fall(store, rule, original, improved):
    first = generation(1, rule, [original, original], [
        entry('A', 'A-unchanged', '100', [original, original]),
    ])
    old = ingest(store, first)
    assert team(old)['current_baseline_history_peak_score'] == '100'
    latest = generation(2, rule, [improved, improved], [
        entry('A', 'A-unchanged', '50', [original, original]),
        entry('B', 'B-record', '100', [improved, improved]),
    ])
    assert scope_id(first['scope']) == scope_id(latest['scope'])
    current = ingest(store, latest)
    a = team(current)
    assert a['official_score'] == a['current_baseline_history_peak_score'] == '50'
    assert a['observed_official_peak_score'] == '100'
    assert a['historical_submissions'] == 1  # Same performance, repriced by B.
    assert a['best'][0]['submission_id'] == 'A-unchanged'
    assert current['score_basis']['formula_recomputation_enabled']
    assert current['snapshot_count'] == 2


@pytest.mark.parametrize('rule,old_time,middle_time,last_score', [
    (RATIO_RULE, 4, 2, '25'), (RULE, 2.25, 1.5, '33.33'),
])
def test_every_new_global_record_reprices_the_same_history_again(store, rule, old_time, middle_time, last_score):
    first = generation(1, rule, [old_time, old_time], [
        entry('A', 'A-old', '100', [old_time, old_time]),
    ])
    middle = generation(2, rule, [middle_time, middle_time], [
        entry('A', 'A-old', '50', [old_time, old_time]),
        entry('B', 'B-old', '100', [middle_time, middle_time]),
    ])
    last = generation(3, rule, [1, 1], [
        entry('A', 'A-old', last_score, [old_time, old_time]),
        entry('B', 'B-old', '50', [middle_time, middle_time]),
        entry('C', 'C-record', '100', [1, 1]),
    ])
    values = [Decimal(team(ingest(store, snapshot))['current_baseline_history_peak_score'])
              for snapshot in (first, middle, last)]
    assert values == [Decimal(100), Decimal(50), Decimal(last_score)]
    assert values[0] > values[1] > values[2]
    assert team(store.board(scope_id(last['scope'])))['observed_official_peak_score'] == '100'


@pytest.mark.parametrize('rule,old_time,slower_time,middle_reference,last_peak,last_current', [
    (RATIO_RULE, 4, 8, 2, '25.00', '12.5'),
    (RULE, 2.25, 5.0625, 1.5, '33.33', '20'),
])
def test_historical_best_can_beat_latest_but_still_falls_with_the_global_baseline(
        store, rule, old_time, slower_time, middle_reference, last_peak, last_current):
    first = generation(1, rule, [old_time, old_time], [
        entry('A', 'A-fast-old', '100', [old_time, old_time]),
    ])
    ingest(store, first)
    middle = generation(2, rule, [middle_reference, middle_reference], [
        entry('A', 'A-slower-new', '25', [slower_time, slower_time]),
        entry('B', 'B-record', '100', [middle_reference, middle_reference]),
    ])
    middle_board = ingest(store, middle)
    a = team(middle_board)
    assert a['official_score'] == '25'
    assert a['current_baseline_history_peak_score'] == '50.00'
    assert a['best'][0]['submission_id'] == 'A-fast-old'
    assert a['best'][0]['original_score'] == '100'
    last = generation(3, rule, [1, 1], [
        entry('A', 'A-slower-new', last_current, [slower_time, slower_time]),
        entry('B', 'B-record', '50', [middle_reference, middle_reference]),
        entry('C', 'C-record', '100', [1, 1]),
    ])
    last_board = ingest(store, last)
    a = team(last_board)
    assert a['current_baseline_history_peak_score'] == last_peak
    assert Decimal(a['current_baseline_history_peak_score']) > Decimal(a['official_score'])
    assert Decimal(a['current_baseline_history_peak_score']) < Decimal(50)
    assert a['observed_official_peak_score'] == '100'
    assert a['best'][0]['submission_id'] == 'A-fast-old'
    assert a['historical_submissions'] == 2 and a['unavailable_submissions'] == 0


@pytest.mark.parametrize('rule,initial_refs,first_times,second_times,last_refs,current_times,first_score,current_score,peak', [
    (RATIO_RULE, [1, 1], [1, 4], [2, 1], [1, 0.1], [4, 4], '62.50', '13.75', '51.25'),
    (RULE, [2.25, 2.25], [2.25, 5.0625], [3.375, 2.25], [2.25, 1], [5.0625, 5.0625], '66.67', '26.67', '60.00'),
])
def test_changed_testpoint_weights_can_change_the_winning_whole_submission(
        store, rule, initial_refs, first_times, second_times, last_refs, current_times,
        first_score, current_score, peak):
    ingest(store, generation(1, rule, initial_refs, [entry('A', 'first', first_score, first_times)]))
    before = ingest(store, generation(2, rule, initial_refs, [entry('A', 'second', '75', second_times)]))
    assert team(before)['best'][0]['submission_id'] == 'second'
    after = ingest(store, generation(3, rule, last_refs, [
        entry('A', 'latest-slow', current_score, current_times),
        entry('B', 'record', '100', last_refs),
    ]))
    a = team(after)
    assert a['current_baseline_history_peak_score'] == peak
    assert a['best'][0]['submission_id'] == 'first'
    assert [case['time'] for case in a['best'][0]['result']] == first_times
    assert a['observed_official_peak_score'] == '75'


@pytest.mark.parametrize('rule,old_time,new_reference', [(RATIO_RULE, 4, 2), (RULE, 2.25, 1.5)])
def test_a_cached_old_100_cannot_be_certified_against_a_contradicting_current_tbest(
        store, rule, old_time, new_reference):
    ingest(store, generation(1, rule, [old_time, old_time], [
        entry('A', 'unchanged', '100', [old_time, old_time]),
    ]))
    # A's upstream row is stale or the read straddled a benchmark update.
    # The official source score stays intact, but its claimed basis is not true.
    after = ingest(store, generation(2, rule, [new_reference, new_reference], [
        entry('A', 'unchanged', '100', [old_time, old_time]),
        entry('B', 'record', '100', [new_reference, new_reference]),
    ]))
    a = team(after)
    assert a['official_score'] == a['observed_official_peak_score'] == '100'
    assert not after['score_basis']['formula_recomputation_enabled']
    assert a['current_baseline_history_peak_score'] is None
    assert a['confirmed_peak_lower_bound'] is None
    assert a['history_peak_status'] == 'insufficient-data'
    assert a['unavailable_submissions'] == 1


def test_hidden_same_submission_tracks_new_official_score_without_freezing_its_old_100(store):
    ingest(store, generation(1, RATIO_RULE, [2, None], [
        entry('A', 'unchanged', '100', [2, None]),
    ]))
    after = ingest(store, generation(2, RATIO_RULE, [1, None], [
        entry('A', 'unchanged', '50', [2, None]),
        entry('B', 'record', '100', [1, None]),
    ]))
    a = team(after)
    assert a['current_baseline_history_peak_score'] == '50'
    assert a['observed_official_peak_score'] == '100'
    assert a['historical_submissions'] == 1
    assert not after['score_basis']['formula_recomputation_enabled']


def test_hidden_old_version_is_unknown_instead_of_retaining_its_old_100_as_current_best(store):
    ingest(store, generation(1, RATIO_RULE, [2, None], [
        entry('A', 'old-fast', '100', [2, None]),
    ]))
    after = ingest(store, generation(2, RATIO_RULE, [1, None], [
        entry('A', 'new-slower', '25', [4, None]),
        entry('B', 'record', '100', [1, None]),
    ]))
    a = team(after)
    assert a['official_score'] == a['confirmed_peak_lower_bound'] == '25'
    assert a['observed_official_peak_score'] == '100'
    assert a['current_baseline_history_peak_score'] is None
    assert a['history_peak_status'] == 'insufficient-data'


def test_invalidated_old_winner_is_not_resurrected_when_another_team_moves_tbest(store):
    ingest(store, generation(1, RATIO_RULE, [4, 4], [
        entry('A', 'revoked', '100', [4, 4]),
    ]))
    ingest(store, generation(2, RATIO_RULE, [2, 2], [
        entry('A', 'revoked', '0', [4, 4], status='Wrong Answer'),
        entry('B', 'record', '100', [2, 2]),
    ]))
    after = ingest(store, generation(3, RATIO_RULE, [1, 1], [
        entry('A', 'latest', '12.5', [8, 8]),
        entry('B', 'record', '50', [2, 2]),
        entry('C', 'record', '100', [1, 1]),
    ]))
    a = team(after)
    assert a['observed_official_peak_score'] == '100'
    assert a['best'][0]['submission_id'] == 'latest'
    assert a['confirmed_peak_lower_bound'] == '12.5'
    assert a['current_baseline_history_peak_score'] is None
    assert a['unavailable_submissions'] == 1
