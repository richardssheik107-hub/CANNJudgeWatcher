import copy
import json
from types import SimpleNamespace
import httpx
import pytest
from fastapi.testclient import TestClient
from watcher.app import create_app
from watcher.collector import archive_rows, backfill, poll
from watcher.core import ContractError, clean, number, observation, scope_id, total_row, utc
from watcher.demo import seed
from watcher.source import Client, SourceError, collect_contest, frozen, matches
from watcher.store import Store


def raw(score='80', team='one', rank=1, status='Pass', sid='s1', name='队伍一'):
    return {'team': {'_id': team, 'team_name': name}, 'score': score, 'rank': rank, 'status': status,
            'submission_id': sid, 'result': [{'testcase_id': 'c1', 'testcase_status': 'Pass', 'time': 2.0}]}


def snapshot(at='2026-01-01T01:00:00Z', scores=('80','70'), team='one', group='A', epoch='v1'):
    scope = {'contest_id': 'contest', 'stage': 'stage', 'group': group, 'epoch': epoch, 'demo': False,
             'title': '测试赛事', 'problems': [{'id':'p','title':'题目一','weight':1}, {'id':'q','title':'题目二','weight':1}]}
    return {'schema': 1, 'scope': scope, 'observed_at': at,
            'observations': [observation(p,raw(score,team,sid=p+at)) for p,score in zip(('p','q'),scores)],
            'totals': [total_row(raw(str(sum(float(s) for s in scores)),team))], 'payloads':[], 'notes':[]}

@pytest.fixture
def store(tmp_path):
    return Store(str(tmp_path/'test.sqlite3'))

@pytest.mark.parametrize('value', [True, False, 'NaN', 'Infinity', '-1', 'bad', '', float('inf')])
def test_invalid_scores(value):
    with pytest.raises(ContractError): number(value)

@pytest.mark.parametrize('value,expected', [(None,None),(0,'0'),('0.01','0.01'),('90.005','90.005')])
def test_valid_scores(value,expected): assert number(value)==expected


def test_stable_id_required():
    with pytest.raises(ContractError): observation('p', {'name':'same','rank':1,'score':90})


def test_failed_or_partial_run_not_peak():
    assert not observation('p',raw(status='Wrong Answer'))['eligible']
    r=raw(); r['result'][0]['testcase_status']='Wrong Answer'
    assert not observation('p',r)['eligible']
    assert not observation('p',raw(score=None))['eligible']


def test_redaction():
    r=raw(); r.update(cookie='secret',files=[{'code':'secret'}],headers={'Authorization':'secret'})
    assert 'secret' not in json.dumps(observation('p',r))
    assert len(clean({'msg':'a'*5000})['msg'])==4000


def test_peak_is_sum_of_per_problem_maxima(store):
    a=snapshot(scores=('90','60')); b=snapshot('2026-01-01T02:00:00Z',('70','95'))
    store.ingest(a);store.ingest(b)
    row=store.board(scope_id(a['scope']))['rows'][0]
    assert row['peak_score']=='185' and row['official_score']=='165.0'
    assert {r['score'] for r in row['best']}=={'90','95'}


def test_no_case_stitching(store):
    a=snapshot(scores=('70','50')); b=snapshot('2026-01-01T02:00:00Z',('71','50'))
    for s,times in [(a,[2,10]),(b,[10,2])]:
        r=s['observations'][0]['raw'];r['result']=[{'testcase_id':str(i),'testcase_status':'Pass','time':t} for i,t in enumerate(times)]
        s['observations'][0]=observation('p',r);store.ingest(s)
    best=next(r for r in store.board(scope_id(a['scope']))['rows'][0]['best'] if r['problem_id']=='p')
    assert [r['time'] for r in best['result']]==[10,2]


def test_out_of_order_import_does_not_rewind(store):
    later=snapshot('2026-01-01T03:00:00Z',('60','60')); early=snapshot(scores=('99','99'))
    store.ingest(later);store.ingest(early,imported=True)
    b=store.board(scope_id(early['scope']))
    assert b['rows'][0]['official_score']=='120.0' and b['rows'][0]['peak_score']=='198'
    assert b['observed_at']==utc(later['observed_at'])


def test_idempotency_and_conflict(store):
    s=snapshot(); first=store.ingest(s)
    assert store.ingest(s)==first
    altered=copy.deepcopy(s);altered['notes']=['different']
    with pytest.raises(ContractError):store.ingest(altered)
    assert store.scopes()[0]['snapshot_count']==1


def test_rank_only_changes_saved(store):
    a=snapshot(); b=copy.deepcopy(a);b['observed_at']='2026-01-01T02:00:00Z'
    for r in b['observations']:
        r['raw']['rank']=7;r['rank']=7
    b['totals'][0]=total_row(raw('150',rank=7))
    store.ingest(a);store.ingest(b)
    h=store.history(scope_id(a['scope']),'team:one')
    assert [p['total']['rank'] for p in h['points']]==[7,1]


def test_missing_current_and_dropout_are_not_zero(store):
    a=snapshot();store.ingest(a)
    b=copy.deepcopy(a);b.update(observed_at='2026-01-01T02:00:00Z',observations=[],totals=[]);store.ingest(b)
    r=store.board(scope_id(a['scope']))['rows'][0]
    assert not r['present'] and r['official_score'] is None and r['current_sum'] is None and r['peak_score']=='150'


def test_rename_uses_stable_id(store):
    a=snapshot();b=snapshot('2026-01-01T02:00:00Z')
    for r in b['observations']:
        r['raw']['team']['team_name']='改名后';r['name']='改名后'
    b['totals'][0]=total_row(raw('150',name='改名后'))
    store.ingest(a);store.ingest(b)
    rows=store.board(scope_id(a['scope']))['rows']
    assert len(rows)==1 and rows[0]['name']=='改名后'


@pytest.mark.parametrize('field,value',[('epoch','v2'),('group','B'),('stage','final'),('demo',True)])
def test_scope_isolation(store,field,value):
    a=snapshot();b=copy.deepcopy(a);b['scope'][field]=value
    store.ingest(a);store.ingest(b)
    assert len(store.scopes())==2


def test_no_official_rank_fabricated(store):
    a=snapshot();a['totals'][0]=total_row(raw('150',rank=None));store.ingest(a)
    r=store.board(scope_id(a['scope']))['rows'][0]
    assert r['official_rank'] is None and r['reference_rank']==1


def test_decimal_ties_not_display_rounding(store):
    a=snapshot(scores=('80.004','0'));other=snapshot(scores=('80.003','0'),team='two')
    a['observations']+=other['observations'];a['totals']+=other['totals'];store.ingest(a)
    assert [r['peak_rank'] for r in store.board(scope_id(a['scope']))['rows']]==[1,2]


def test_true_ties_share_rank(store):
    a=snapshot();b=snapshot(team='two');a['observations']+=b['observations'];a['totals']+=b['totals'];store.ingest(a)
    assert [r['peak_rank'] for r in store.board(scope_id(a['scope']))['rows']]==[1,1]


def test_cannot_tamper_eligibility(store):
    a=snapshot();a['observations'][0]['eligible']=False
    with pytest.raises(ContractError):store.ingest(a)
    assert store.scopes()==[]


def test_duplicate_team_and_invalid_batch_atomic(store):
    a=snapshot();a['observations'].append(copy.deepcopy(a['observations'][0]))
    with pytest.raises(ContractError):store.ingest(a)
    assert store.scopes()==[]


def test_export_import_backup(store,tmp_path):
    a=snapshot();store.ingest(a)
    other=Store(str(tmp_path/'other.sqlite3'))
    for line in store.export():other.ingest(json.loads(line),imported=True)
    sid=scope_id(a['scope']);assert other.board(sid)['imported']
    store.backup(str(tmp_path/'backup.sqlite3'))
    assert Store(str(tmp_path/'backup.sqlite3')).board(sid)['rows'][0]['peak_score']=='150'


def test_history_cursor(store):
    a=snapshot();store.ingest(a);store.ingest(snapshot('2026-01-01T02:00:00Z'))
    h=store.history(scope_id(a['scope']),'team:one',limit=1)
    h2=store.history(scope_id(a['scope']),'team:one',limit=1,before=h['next_before'])
    assert h2['points'][0]['observed_at']==utc(a['observed_at'])
    assert h2['next_before'] is None


def client_for(handler,**config):
    return Client({'request_gap_seconds':0,'page_size':1,**config},transport=httpx.MockTransport(handler))


def test_pagination_complete():
    def handler(req):
        page=int(req.url.params['page'])
        return httpx.Response(200,json={'rows':[raw(team=str(page))],'total':2})
    c=client_for(handler)
    try: assert len(c.ranking('p')[0])==2
    finally:c.close()


@pytest.mark.parametrize('mode',['truncated','duplicates','drift','cap'])
def test_bad_pagination_fails_closed(mode):
    def handler(req):
        p=int(req.url.params['page'])
        return httpx.Response(200,json={'rows':[] if mode=='truncated' and p==2 else [raw(team='one' if mode=='duplicates' else str(p))],
                                        'total':3 if mode=='drift' and p==2 else 2})
    c=client_for(handler,max_ranking_pages=1 if mode=='cap' else 10)
    try:
        with pytest.raises(ContractError):c.ranking('p')
    finally:c.close()


@pytest.mark.parametrize('status',[401,403,500,302])
def test_http_errors_not_empty_boards(status):
    c=client_for(lambda r:httpx.Response(status,json={}))
    try:
        with pytest.raises(SourceError):c.get('/api/groups/public')
    finally:c.close()


def test_rate_limit_respected():
    c=client_for(lambda r:httpx.Response(429,headers={'Retry-After':'7200'}))
    try:
        with pytest.raises(SourceError) as e:c.get('/api/groups/public')
        assert e.value.retry_after>=7200
    finally:c.close()


def test_cli_reuses_raw_json_no_shell(monkeypatch):
    captured=[]
    def run(args,**kwargs):
        captured.append((args,kwargs));return SimpleNamespace(returncode=0,stdout='{"rows":[],"total":0}')
    monkeypatch.setattr('watcher.source.subprocess.run',run)
    c=Client({'transport':'windust-cli','request_gap_seconds':0})
    try:assert c.get('/api/problems/p/ranking',page=1)['total']==0
    finally:c.close()
    args,kw=captured[0]
    assert '--no-cache' in args and '--json' in args and not kw['shell']
    assert 'submit' not in args


def test_frozen_and_selector():
    assert frozen({'freeze_ranking':True,'end_time':'2026-01-01T02:00:00Z','freeze_duration':60},'2026-01-01T01:30:00Z')
    assert not frozen({'freeze_ranking':False})
    assert matches({'_id':'x','title':'京津及东北挑战赛'},{'include':[{'all_title_keywords':['京津','东北']}]})
    assert not matches({'_id':'x','title':'东北大学内部赛'},{'include':[{'all_title_keywords':['京津','东北']}]})


def test_poll_failure_retains_last_success(store):
    a=snapshot();store.ingest(a)
    class Broken:
        def discover(self):raise SourceError('offline')
    result=poll(store,Broken(),{})
    assert result['status']=='FAILED'
    assert store.board(scope_id(a['scope']))['rows'][0]['peak_score']=='150'
    assert store.runs()[0]['status']=='FAILED'


def test_public_backfill_separate_from_peak(store):
    a=snapshot();store.ingest(a);sid=scope_id(a['scope'])
    row={'_id':'old','problem_id':'p','team_id':'one','status':'Pass','score':'999','files':[{'content':'DO NOT STORE'}]}
    class Archive:
        def get(self,path,**query):return {'list':[row],'total':1}
    r=backfill(store,Archive(),sid)
    assert r['complete'] and r['saved']==1
    assert backfill(store,Archive(),sid)['saved']==0
    assert store.board(sid)['rows'][0]['peak_score']=='150'
    assert 'DO NOT STORE' not in json.dumps(archive_rows(store,sid))


def test_api_token_and_read_only(store,monkeypatch):
    a=snapshot();store.ingest(a);monkeypatch.setenv('WATCHER_TOKEN','test-secret')
    with TestClient(create_app(store.path,'not-present.json')) as c:
        assert c.get('/health').status_code==200
        assert c.get('/api/scopes').status_code==401
        auth={'Authorization':'Bearer test-secret'}
        assert c.get('/api/scopes',headers=auth).status_code==200
        assert c.post('/api/scopes',headers=auth).status_code==405
        assert c.get('/api/board/missing',headers=auth).status_code==404
        assert 'script-src' in c.get('/').headers['content-security-policy']


def test_api_evidence_export_and_demo(tmp_path,monkeypatch):
    monkeypatch.delenv('WATCHER_TOKEN',raising=False)
    db=Store(str(tmp_path/'demo.sqlite3'));seed(db)
    assert len(db.scopes())==2
    with pytest.raises(ValueError):seed(db)
    with TestClient(create_app(db.path,'none.json')) as c:
        meta=c.get('/api/scopes').json();assert all(s['demo'] for s in meta['scopes'])
        board=c.get('/api/board/'+meta['scopes'][0]['id']).json()
        eid=board['rows'][0]['best'][0]['evidence_id']
        assert c.get('/api/evidence/'+eid).status_code==200
        assert len(c.get('/api/export').text.splitlines())==8
        assert c.get('/static/app.js').status_code==200


def test_full_public_contract_fixture(store):
    paths=[]
    contest={'_id':'cid','name':'starcup-a','title':'星辰杯（A组）','problems':[{'problem_id':'p'}]}
    def handler(req):
        paths.append((req.method,req.url.path))
        path=req.url.path
        if path=='/api/groups/public':data={'_id':'public'}
        elif path=='/api/contests/group/public':data=[contest]
        elif path=='/api/problems/p':data={'_id':'p','title':'算子','cann_version':'8.x'}
        elif path=='/api/problems/p/ranking':data={'rows':[raw()],'total':1}
        elif path=='/api/submissions/contest/cid/stats':data=[raw()]
        elif path=='/api/submissions/global/list':data={'list':[{'_id':'s1','problem_id':'p','team_id':'one','status':'Pass'}],'total':1}
        else:raise AssertionError(path)
        return httpx.Response(200,json=data)
    config={'include':[{'all_title_keywords':['星辰杯']}],'history_pages_per_poll':2}
    c=client_for(handler)
    try:r=poll(store,c,config)
    finally:c.close()
    assert r['status']=='SUCCESS' and r['history'][0]['saved']==1
    assert all(method=='GET' for method,_ in paths)
    scope=store.scopes()[0]; assert scope['group']=='A' and not scope['demo']
    assert store.board(scope['id'])['rows'][0]['peak_score']=='80'


def test_first_page_anchor_race():
    calls=0
    def handler(req):
        nonlocal calls
        calls+=1; page=int(req.url.params['page'])
        return httpx.Response(200,json={'rows':[raw(team=str(page),score='81' if calls>2 else '80')],'total':2})
    c=client_for(handler)
    try:
        with pytest.raises(ContractError):c.ranking('p')
    finally:c.close()


def test_no_requests_for_frozen_contest():
    class NoRequests:
        def get(self,*a,**k):raise AssertionError('must not read hidden board')
    with pytest.raises(SourceError):collect_contest(NoRequests(),{'_id':'x','frozen':True},{})


def test_unknown_scores_are_partial_not_zero(store):
    a=snapshot();a['observations'][0]=observation('p',raw(score=None));store.ingest(a)
    r=store.board(scope_id(a['scope']))['rows'][0]
    assert r['peak_score']=='70' and r['observed_problems']==1 and r['current_sum'] is None


def test_negative_weight_and_future_timestamp_rejected(store):
    a=snapshot();a['scope']['problems'][0]['weight']=-1
    with pytest.raises(ContractError):store.ingest(a)
    a=snapshot('2099-01-01T00:00:00Z')
    with pytest.raises(ContractError):store.ingest(a)
    with pytest.raises(ContractError):utc('2026-01-01T00:00:00')


def test_rule_context_version_separates_peaks(store):
    a=snapshot(scores=('99','99'));store.ingest(a)
    b=snapshot('2026-01-01T02:00:00Z',('1','1'));b['scope']['problems'][0]['version']='new-cases';store.ingest(b)
    assert store.board(scope_id(b['scope']))['rows'][0]['peak_score']=='2'


def test_same_submission_rescore_retained(store):
    a=snapshot();b=copy.deepcopy(a);b['observed_at']='2026-01-01T02:00:00Z'
    for r in b['observations']:
        r['raw']['score']='50';r['score']='50'
    b['totals'][0]=total_row(raw('100'))
    store.ingest(a);store.ingest(b)
    board=store.board(scope_id(a['scope']))
    assert board['rows'][0]['peak_score']=='150' and board['rows'][0]['official_score']=='100'
    assert '官方最终榜' in board['warning']
