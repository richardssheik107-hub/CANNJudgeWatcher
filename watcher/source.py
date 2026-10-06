"""Read-only CANNJudge adapter. Optional Windust CLI reuses its auth/HTTP code."""
from __future__ import annotations
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode, quote
import httpx
from .core import ContractError, clean, digest, observation, total_row, utc

ORIGIN = 'https://cannjudge.cn'

class SourceError(RuntimeError):
    def __init__(self, message: str, retry_after: float = 0):
        super().__init__(message)
        self.retry_after = retry_after

class Client:
    def __init__(self, config: dict, transport=None):
        self.config = config
        self.last_request = 0.0
        self.http = httpx.Client(timeout=float(config.get('timeout_seconds', 25)),
                                 follow_redirects=False, transport=transport)

    def close(self):
        self.http.close()

    def get(self, path: str, **query):
        if not path.startswith('/api/') or '..' in path or '?' in path or '#' in path:
            raise ContractError('invalid read-only source path')
        gap = max(0, float(self.config.get('request_gap_seconds', 1)))
        time.sleep(max(0, self.last_request + gap - time.monotonic()))
        self.last_request = time.monotonic()
        if self.config.get('transport') == 'windust-cli':
            prefix = self.config.get('cli_command', ['cannjudge'])
            if not isinstance(prefix, list) or not prefix or not all(isinstance(x, str) for x in prefix):
                raise ContractError('cli_command must be an argument array, never a shell string')
            args = prefix + ['--no-cache', '--json', 'api', 'get', path + ('?' + urlencode(query) if query else '')]
            if self.config.get('cli_auth', False):
                args.append('--auth')
            try:
                result = subprocess.run(args, capture_output=True, text=True, shell=False,
                                        timeout=float(self.config.get('timeout_seconds', 25)))
            except (OSError, subprocess.TimeoutExpired) as e:
                raise SourceError('CLI unavailable or timed out') from e
            if result.returncode:
                raise SourceError(f'CLI failed (exit {result.returncode}); no account switching or submission attempted')
            try:
                return json.loads(result.stdout)
            except ValueError as e:
                raise ContractError('CLI output is not raw JSON') from e
        headers = {'Accept': 'application/json', 'User-Agent': 'CANNJudgeWatcher-ObservedPeak/0.1 (public-read-only)',
                   'Origin': ORIGIN, 'Referer': ORIGIN + '/'}
        cookie = os.environ.get(self.config.get('cookie_env', 'CANNJUDGE_COOKIE'), '')
        if cookie:
            headers['Cookie'] = cookie
        try:
            with self.http.stream('GET', ORIGIN + path, params=query, headers=headers) as response:
                if response.status_code == 429:
                    value = response.headers.get('Retry-After', '120')
                    try:
                        delay = float(value)
                    except ValueError:
                        try:
                            delay = (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()
                        except (TypeError, ValueError):
                            delay = 120
                    raise SourceError('HTTP 429; waiting before another poll', max(120, delay))
                if response.status_code != 200:
                    raise SourceError(f'public source HTTP {response.status_code}; previous snapshot retained')
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > 16 * 1024 * 1024:
                        raise ContractError('response exceeds 16 MiB safety limit')
                data = json.loads(body)
        except (httpx.HTTPError, ValueError) as e:
            if isinstance(e, ContractError):
                raise
            raise SourceError('network failure or non-JSON source response') from e
        if isinstance(data, dict) and data.get('code') not in (None, 0, 200):
            raise SourceError('source returned an application error')
        return data

    def discover(self) -> list[dict]:
        group = self.get('/api/groups/public')
        if not isinstance(group, dict) or not group.get('_id'):
            raise ContractError('public group has no stable ID')
        contests = self.get('/api/contests/group/' + quote(str(group['_id']), safe=''))
        if not isinstance(contests, list):
            raise ContractError('contest discovery must return an array')
        return contests

    def ranking(self, problem_id: str) -> tuple[list[dict], list[dict]]:
        all_rows, pages, expected, first = [], [], None, None
        size = min(100, max(1, int(self.config.get('page_size', 100))))
        path = '/api/problems/' + quote(problem_id, safe='') + '/ranking'
        for page in range(1, int(self.config.get('max_ranking_pages', 100)) + 1):
            data = self.get(path, page=page, size=size)
            if not isinstance(data, dict) or not isinstance(data.get('rows'), list) or type(data.get('total')) is not int or data['total'] < 0:
                raise ContractError('ranking requires rows[] and nonnegative integer total')
            if expected is not None and data['total'] != expected:
                raise ContractError('ranking changed during pagination; retry next poll')
            expected = data['total']
            if first is None:
                first = digest(clean(data))
            pages.append({'page': page, 'fetched_at': utc(), 'data': clean(data)})
            all_rows.extend(data['rows'])
            if len(all_rows) > expected:
                raise ContractError('ranking pagination exceeded total')
            if len(all_rows) == expected:
                # Catch a common page-shift race; this is not server-side snapshot isolation.
                if page > 1 and self.config.get('verify_first_page', True):
                    if digest(clean(self.get(path, page=1, size=size))) != first:
                        raise ContractError('first page moved during pagination')
                keys = [observation(problem_id, row)['team_key'] for row in all_rows]
                if len(set(keys)) != len(keys):
                    raise ContractError('duplicate team across ranking pages')
                return all_rows, pages
            if not data['rows']:
                raise ContractError('truncated ranking: empty page before total')
        raise ContractError('ranking page limit reached; incomplete snapshot was not published')


def matches(contest: dict, config: dict) -> bool:
    if not isinstance(contest, dict) or not contest.get('_id'):
        return False
    title, slug = str(contest.get('title', '')), str(contest.get('name', ''))
    for selector in config.get('include', []):
        if selector.get('slug') == slug:
            return True
        terms = selector.get('all_title_keywords', [])
        if terms and all(x in title for x in terms):
            return True
    return False


def frozen(contest: dict, now: str | None = None) -> bool:
    if contest.get('frozen') is True:
        return True
    if not contest.get('freeze_ranking'):
        return False
    try:
        end = datetime.fromisoformat(utc(contest['end_time']))
        current = datetime.fromisoformat(utc(now))
        return end - timedelta(minutes=float(contest.get('freeze_duration', 0))) <= current < end
    except (KeyError, TypeError, ValueError):
        # Unknown freeze metadata must not become a way around a frozen board.
        return True


def scoring_context(contest: dict) -> dict:
    """Record the public rule, without assuming hidden timings are available."""
    text = str(contest.get('scoring_rules_content') or '')
    compact = re.sub(r'\s+', '', text)
    verified = (contest.get('scoring_rules_enabled') is True
                and contest.get('scoring_rule') == 'default'
                and '100/(1+log(你的用时/该测试点最优用时)/log(1.5))' in compact
                and '全部测试点得分的**平均值**（保留两位小数）' in compact
                and '每个测试点在所有参赛者提交中的历史最快用时' in compact)
    return {'rule': 'cann-default-time-log-v1', 'verified': verified,
            'rule_source': ORIGIN + '/public/' + quote(str(contest.get('name') or ''), safe='') + '/scoring-rules',
            'formula': '100/(1+log(time/TBest)/log(1.5))',
            'rule_digest': digest(text), 'rule_text': text,
            'problem_ids': sorted(str(p['problem_id']) for p in contest.get('problems', [])
                                  if isinstance(p, dict) and p.get('problem_id')),
            'visible_testcase_count': contest.get('visible_testcase_count')}


def collect_contest(client: Client, contest: dict, config: dict) -> dict:
    start = utc(); cid = str(contest['_id'])
    context = None
    if config.get('verify_scoring_rules'):
        full = client.get('/api/contests/' + quote(cid, safe=''))
        if not isinstance(full, dict) or str(full.get('_id')) != cid or full.get('name') != contest.get('name'):
            raise ContractError('scoring-rule contest identity mismatch')
        # The detail endpoint includes the rule text; discovery omits it.
        contest = full
        context = scoring_context(contest)
    if frozen(contest):
        raise SourceError('contest is frozen; public snapshots remain unchanged')
    if contest.get('start_time') and utc(contest['start_time']) > start:
        raise SourceError('contest has not started')
    problems = contest.get('problems')
    if not isinstance(problems, list) or not problems:
        raise ContractError('contest has no public problem-ID list')
    title = str(contest.get('title') or contest.get('name') or cid)
    group_match = re.search(r'([A-D])\s*组', title, re.I)
    group = group_match.group(1).upper() if group_match else '公开组'
    descriptors, observations, payloads = [], [], []
    for item in problems:
        pid = item.get('problem_id') if isinstance(item, dict) else None
        if not pid:
            raise ContractError('missing problem_id; refusing to infer it from table position')
        pid = str(pid)
        meta = client.get('/api/problems/' + quote(pid, safe=''))
        if not isinstance(meta, dict) or str(meta.get('_id')) != pid:
            raise ContractError('problem identity mismatch')
        version = {k: meta.get(k) for k in ('cann_version', 'code_template', 'ranking_submission_mode',
                                          'judge_version', 'version_root_id', 'version_no',
                                          'score_mode', 'use_baseline', 'iterations')}
        cases = meta.get('testcases', [])
        if isinstance(cases, list):
            version['testcases'] = []
            for case in cases:
                if not isinstance(case, dict):
                    raise ContractError('public testcase metadata must be an object')
                ref = case.get('testcase_id', case)
                if isinstance(ref, dict):
                    baseline = ref.get('baseline_id', ref.get('baseline'))
                    version['testcases'].append({'_id': ref.get('_id'), 'type': ref.get('type'),
                                                 'baseline_id': baseline.get('_id') if isinstance(baseline, dict) else baseline})
                elif isinstance(ref, str):
                    version['testcases'].append({'_id': ref, 'type': case.get('type'),
                                                 'baseline_id': case.get('baseline_id')})
                else:
                    raise ContractError('public testcase has no valid identity reference')
        descriptors.append({'id': pid, 'title': str(meta.get('title') or pid),
                            'weight': config.get('problem_weights', {}).get(pid, 1), 'version': digest(version)})
        rows, pages = client.ranking(pid)
        observations.extend(observation(pid, r) for r in rows)
        payloads.append({'problem_id': pid, 'metadata': {'id': pid, 'version': version}, 'pages': pages})
    totals, notes = [], []
    if contest.get('show_total_ranking') is False:
        notes.append('源站未公开赛事总榜；官方总分及名次显示为空。')
    else:
        raw_totals = client.get('/api/submissions/contest/' + quote(cid, safe='') + '/stats')
        if not isinstance(raw_totals, list):
            raise ContractError('contest total board must return an array')
        totals = [total_row(r) for r in raw_totals]
        payloads.append({'contest_totals': clean(raw_totals)})
    if totals and any(r['rank'] is None for r in totals):
        notes.append('总榜接口没有完整 rank 字段；参考名次仅按总分排序，不能当成官方并列规则。')
    if any(r['score'] is None for r in observations):
        notes.append('部分题目未公开 score：保留结果，但不猜测分数或用耗时拼分。')
    if any(c.get('testcase_status') == 'Hidden' or c.get('status') == 'Hidden'
           for r in observations for c in r['result'] if isinstance(c, dict)):
        notes.append('部分测试点为公开 Hidden 占位；保留未知详情，使用官方完整提交状态与 score，不按测试点猜分。')
    notes.append('不同题目顺序采集，非服务端原子快照；历史分数可能采用移动基准。')
    scope = {'contest_id': cid, 'title': title, 'stage': str(contest.get('name') or cid), 'group': group,
             'epoch': str(config.get('rule_epoch', 'observed-source-score-v1')),
             'problems': sorted(descriptors, key=lambda p: p['id']), 'demo': False}
    out = {'schema': 1, 'scope': scope, 'observed_at': utc(), 'collection_started_at': start,
           'source': ORIGIN, 'observations': observations, 'totals': totals, 'payloads': payloads, 'notes': notes}
    if context is not None:
        out['scoring_context'] = context
    return out
