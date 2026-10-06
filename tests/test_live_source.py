"""Offline contract checks using the public final-board response shape, without identifiers."""
import copy
import json
from pathlib import Path

import httpx
import pytest

from watcher.core import observation, scope_id, validate_snapshot
from watcher.source import Client, collect_contest, matches, scoring_context
from watcher.store import Store


@pytest.fixture
def public_schema():
    return json.loads((Path(__file__).parent / 'fixtures' / 'public_starcup_schema.json').read_text(encoding='utf-8'))


def collect_public(schema):
    requests = []
    routes = {
        '/api/groups/public': schema['group'],
        '/api/contests/group/public-group': schema['contests'],
        '/api/problems/public-problem': schema['problem'],
        '/api/problems/public-problem/ranking': schema['ranking'],
        '/api/submissions/contest/public-final/stats': schema['totals'],
    }

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=routes[request.url.path])

    config = {'request_gap_seconds': 0, 'cookie_env': '', 'include': [{'slug': 'ct_starcup_aiop_final'}]}
    client = Client(config, transport=httpx.MockTransport(handler))
    try:
        contest, = [c for c in client.discover() if matches(c, config)]
        snapshot = collect_contest(client, contest, config)
    finally:
        client.close()
    assert all(r.method == 'GET' and 'cookie' not in r.headers for r in requests)
    return validate_snapshot(snapshot)


def test_public_pass_with_hidden_retains_official_score_and_roundtrips(public_schema, tmp_path):
    snapshot = collect_public(public_schema)
    row, = snapshot['observations']
    assert row['eligible'] and row['score'] == '83.1' and row['rank'] == 1
    assert row['result'][0]['score'] == 0  # The submission score is not a test-case sum.
    assert row['result'][1] == public_schema['ranking']['rows'][0]['result'][1]
    assert snapshot['totals'][0]['rank'] is None
    assert any('Hidden' in note and 'score' in note for note in snapshot['notes'])
    store = Store(str(tmp_path / 'public.sqlite3'))
    store.ingest(snapshot)
    board = store.board(scope_id(snapshot['scope']))
    assert board['rows'][0]['peak_score'] == '83.1'
    assert board['rows'][0]['official_rank'] is None
    other = Store(str(tmp_path / 'reimport.sqlite3'))
    for item in store.export():
        other.ingest(json.loads(item), imported=True)
    assert other.board(scope_id(snapshot['scope']))['rows'][0]['best'][0]['result'] == row['result']


@pytest.mark.parametrize('status', ['Pass', 'Accepted', 'AC'])
def test_only_official_pass_accepts_undisclosed_case(public_schema, status):
    row = copy.deepcopy(public_schema['ranking']['rows'][0])
    row['status'] = status
    assert observation('public-problem', row)['eligible']


@pytest.mark.parametrize('change', ['top_failure', 'score_unknown', 'visible_failure', 'unknown_case', 'missing_case_status', 'invalid_case'])
def test_hidden_never_overrides_invalid_or_failed_submission(public_schema, change):
    row = copy.deepcopy(public_schema['ranking']['rows'][0])
    if change == 'top_failure':
        row['status'] = 'Wrong Answer'
    elif change == 'score_unknown':
        row['score'] = None
    elif change == 'visible_failure':
        row['result'][0]['testcase_status'] = 'Wrong Answer'
    elif change == 'unknown_case':
        row['result'][0]['testcase_status'] = 'Judging'
    elif change == 'missing_case_status':
        row['result'][0].pop('testcase_status')
    elif change == 'invalid_case':
        row['result'][0] = None
    assert not observation('public-problem', row)['eligible']


def test_nested_testcase_and_rule_versions_isolate_scopes(public_schema):
    initial = collect_public(public_schema)
    changed = copy.deepcopy(public_schema)
    changed['problem']['testcases'][1]['testcase_id']['_id'] = 'replacement-case'
    assert scope_id(initial['scope']) != scope_id(collect_public(changed)['scope'])
    changed = copy.deepcopy(public_schema)
    changed['problem']['score_mode'] = 'another-mode'
    assert scope_id(initial['scope']) != scope_id(collect_public(changed)['scope'])
    cases = initial['payloads'][0]['metadata']['version']['testcases']
    assert cases[0] == {'_id': 'visible-case', 'type': 'default', 'baseline_id': None}


RULE_TEXT = '''测试点得分公式：`得分 = 100 / (1 + log(你的用时 / 该测试点最优用时) / log(1.5))`
最优用时：每个测试点在所有参赛者提交中的历史最快用时。
题目得分：全部测试点得分的**平均值**（保留两位小数）。'''


def test_scoring_rule_verification_does_not_assume_a_changed_formula():
    contest = {'name': 'ct_starcup_aiop_final', 'scoring_rules_enabled': True,
               'scoring_rule': 'default', 'scoring_rules_content': RULE_TEXT, 'visible_testcase_count': 10}
    context = scoring_context(contest)
    assert context['verified'] and context['visible_testcase_count'] == 10
    assert context['rule_source'].endswith('/ct_starcup_aiop_final/scoring-rules')
    changed = {**contest, 'scoring_rules_content': RULE_TEXT.replace('1.5', '2')}
    assert not scoring_context(changed)['verified']
    assert scoring_context(changed)['rule_digest'] != context['rule_digest']


def test_full_contest_rule_is_collected_without_splitting_moving_baselines(public_schema):
    schema = copy.deepcopy(public_schema)
    full = {**schema['contests'][0], 'scoring_rules_enabled': True, 'scoring_rule': 'default',
            'scoring_rules_content': RULE_TEXT, 'visible_testcase_count': 1}
    routes = {'/api/contests/public-final': full, '/api/problems/public-problem': schema['problem'],
              '/api/problems/public-problem/ranking': schema['ranking'],
              '/api/submissions/contest/public-final/stats': schema['totals']}
    config = {'request_gap_seconds': 0, 'cookie_env': '', 'verify_scoring_rules': True}
    client = Client(config, transport=httpx.MockTransport(lambda r: httpx.Response(200, json=routes[r.url.path])))
    try:
        snap = validate_snapshot(collect_contest(client, schema['contests'][0], config))
        assert snap['scoring_context']['verified']
        assert snap['scoring_context']['rule_text'] == RULE_TEXT
        prior_id = scope_id(snap['scope'])
        schema['ranking']['testcases'] = [{'_id': 'visible-case', 'tbest': 1.2}]
        assert scope_id(collect_contest(client, schema['contests'][0], config)['scope']) == prior_id
    finally:
        client.close()
