"""Public API -> polling -> evidence -> current-basis board -> static export."""
import hashlib
import json
from pathlib import Path

import httpx

from watcher.collector import poll
from watcher.profiles import get_profile
from watcher.scoring import RATIO_FORMULA, RATIO_RULE
from watcher.source import Client
from watcher.static_export import export_site
from watcher.store import Store


PROFILE = get_profile('jingdong-final')
PID, = PROFILE.problem_ids
CID = PROFILE.contest_id
CASES = ('public-case-one', 'public-case-two')
RULE_TEXT = '''测试点得分 = (TBest / 你的用时) × 100。
TBest：每个测试点在所有参赛者提交中的历史最快用时。
题目分是所有测试点得分的平均值（保留两位小数）。'''


def public_row(team, submission, score, elapsed, rank):
    return {
        'team': {'_id': team, 'team_name': '队伍' + team},
        'submission_id': submission, 'status': 'Pass', 'score': score, 'rank': rank,
        'create_time': '2026-01-01T00:00:00Z',
        'result': [{'testcase_id': case, 'time': elapsed, 'precision_ratio': 1,
                    'testcase_status': 'Pass', 'score': 0} for case in CASES],
    }


def team(board, name='A'):
    return next(row for row in board['rows'] if row['team_key'] == 'team:' + name)


def test_poll_reprices_history_quarantines_an_incoherent_round_and_recovers_export(tmp_path):
    # All totals below are hand-derived for the linear rule. The test does not
    # call the scoring implementation to manufacture its own expected answers.
    rounds = [
        (4, [public_row('A', 'A-fast-old', 100, 4, 1)]),
        (2, [public_row('B', 'B-record', 100, 2, 1),
             public_row('A', 'A-slower-latest', 25, 8, 2)]),
        # Source A still says 100 although the new baseline requires 12.5.
        (1, [public_row('C', 'C-record', 100, 1, 1),
             public_row('A', 'A-slower-latest', 100, 8, 1),
             public_row('B', 'B-record', 50, 2, 3)]),
        (1, [public_row('C', 'C-record', 100, 1, 1),
             public_row('B', 'B-record', 50, 2, 2),
             public_row('A', 'A-slower-latest', 12.5, 8, 3)]),
    ]
    contest = {
        '_id': CID, 'name': PROFILE.contest_slug, 'title': '离线模拟京津东北决赛',
        'problems': [{'problem_id': PID}], 'show_total_ranking': True,
        'scoring_rules_enabled': True, 'scoring_rule': 'default',
        'scoring_rules_content': RULE_TEXT, 'visible_testcase_count': 2,
    }
    problem = {
        '_id': PID, 'name': 'varlenndrotaryposemb', 'title': 'VarLenNdRotaryPosEmb',
        'ranking_submission_mode': 'latest', 'score_mode': 1, 'use_baseline': False,
        'testcases': [{'testcase_id': {'_id': case, 'type': 'default'}} for case in CASES],
    }
    config = json.loads((Path(__file__).resolve().parents[1] / 'config' /
                         'monitor.jingdong-final.json').read_text(encoding='utf-8'))
    config['request_gap_seconds'] = 0
    config['timeout_seconds'] = 5
    requests, cursor = [], {'round': 0}

    def handler(request):
        requests.append(request)
        path = request.url.path
        if path == '/api/groups/public':
            data = {'_id': 'public-group'}
        elif path == '/api/contests/group/public-group':
            # Discovery omits the text; the real collector must obtain details.
            data = [{key: value for key, value in contest.items()
                     if key not in ('scoring_rules_content', 'scoring_rules_enabled')}]
        elif path == '/api/contests/' + CID:
            data = contest
        elif path == '/api/problems/' + PID:
            data = problem
        elif path == '/api/problems/' + PID + '/ranking':
            reference, rows = rounds[cursor['round']]
            assert request.url.params['page'] == '1'
            data = {'rows': rows, 'total': len(rows),
                    'testcases': [{'_id': case, 'type': 'default', 'tbest': reference}
                                  for case in CASES]}
        else:
            raise AssertionError('unexpected source endpoint: ' + path)
        return httpx.Response(200, json=data)

    store = Store(str(tmp_path / 'observed.sqlite3'))
    client = Client(config, transport=httpx.MockTransport(handler))
    boards, scopes = [], []
    try:
        for index in range(4):
            cursor['round'] = index
            outcome = poll(store, client, config)
            assert outcome['status'] == 'SUCCESS' and outcome['errors'] == []
            scope, = store.scopes()
            scopes.append(scope['id'])
            board = store.board(scope['id'])
            assert board['snapshot_count'] == index + 1
            # Verification comes from the actual public rule-text parser.
            assert board['score_basis']['formula_verified']
            assert board['score_basis']['formula'] == RATIO_FORMULA
            snapshot = store.snapshot(scope['id'])
            assert snapshot['scoring_context']['rule'] == RATIO_RULE
            assert snapshot['scoring_context']['rule_text'] == RULE_TEXT
            boards.append(board)
    finally:
        client.close()

    assert len(set(scopes)) == 1  # A changing TBest is not a new rule/problem.
    first, refreshed, conflict, recovered = boards
    assert team(first)['current_baseline_history_peak_score'] == '100'
    assert team(refreshed)['official_score'] == '25'
    assert team(refreshed)['current_baseline_history_peak_score'] == '50.00'
    assert team(refreshed)['best'][0]['submission_id'] == 'A-fast-old'
    assert team(refreshed)['observed_official_peak_score'] == '100'

    assert team(conflict)['official_score'] == '100'  # Never rewrite the source.
    assert conflict['score_basis']['calibration_status'] == 'conflict'
    assert not conflict['score_basis']['formula_recomputation_enabled']
    assert team(conflict)['current_baseline_history_peak_score'] is None
    assert team(conflict)['confirmed_peak_lower_bound'] is None
    assert team(conflict)['current_score_consistency'] == 'conflict'

    assert recovered['score_basis']['calibration_status'] == 'verified'
    assert recovered['score_basis']['formula_recomputation_enabled']
    assert team(recovered)['official_score'] == '12.5'
    assert team(recovered)['current_baseline_history_peak_score'] == '25.00'
    assert team(recovered)['best'][0]['submission_id'] == 'A-fast-old'
    assert team(recovered)['best'][0]['original_score'] == '100'
    assert team(recovered)['historical_submissions'] == 2
    assert team(recovered)['unavailable_submissions'] == 0
    assert team(recovered)['observed_official_peak_score'] == '100'
    assert team(recovered, 'B')['current_baseline_history_peak_score'] == '50'
    assert team(recovered, 'C')['current_baseline_history_peak_score'] == '100'
    assert len(list(store.export())) == 4
    assert len(store.runs()) == 4 and all(run['status'] == 'SUCCESS' for run in store.runs())
    with store.connect() as database:
        assert database.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
    assert len(requests) == 20  # Five actual read-only calls per round.
    assert all(request.method == 'GET' and 'cookie' not in request.headers
               and 'authorization' not in request.headers
               and request.headers.get('cache-control') == 'no-cache' for request in requests)

    # Publish a consistent backup using the real strict publication profile.
    backup = tmp_path / 'published.sqlite3'
    store.backup(str(backup))
    before = hashlib.sha256(backup.read_bytes()).hexdigest()
    output = tmp_path / 'site'
    result = export_site(backup, output, profile='jingdong-final')
    assert result['snapshots'] == 4
    assert hashlib.sha256(backup.read_bytes()).hexdigest() == before
    manifest = json.loads((output / '_data/manifest.json').read_text(encoding='utf-8'))
    assert manifest['profile'] == 'jingdong-final'
    published = json.loads((output / manifest['boards'][scopes[0]]).read_text(encoding='utf-8'))
    assert published['snapshot_count'] == 4
    assert team(published)['official_score'] == '12.5'
    assert team(published)['current_baseline_history_peak_score'] == '25.00'
    assert team(published)['observed_official_peak_score'] == '100'
    archived = [json.loads(line) for line in (output / '_data/snapshots.jsonl').read_text(encoding='utf-8').splitlines()]
    assert len(archived) == 4
    assert archived[0]['observations'][0]['score'] == '100'
    assert next(row for row in archived[2]['observations'] if row['team_key'] == 'team:A')['score'] == '100'
