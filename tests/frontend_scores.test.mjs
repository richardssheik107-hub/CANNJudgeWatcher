import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

// Run the actual browser renderers with a minimal DOM, without the network loop.
function ui() {
  const nodes=new Map();
  function element(id) {
    if(!nodes.has(id)) nodes.set(id, {
      value:id==='sort'?'current':'', textContent:'', innerHTML:'', disabled:false,
      classList:{toggle(){},add(){},remove(){}},
      addEventListener(){}, closest(){return element('table');}, showModal(){},
    });
    return nodes.get(id);
  }
  const source=fs.readFileSync(new URL('../web/app.js',import.meta.url),'utf8');
  const startup=source.lastIndexOf('\nload(); setInterval(');
  assert.ok(startup>0,'isolate initialization, keeping the production render functions intact');
  const context=vm.createContext({
    document:{getElementById:element,documentElement:{dataset:{}},baseURI:'https://example.test/'},
    URL,Intl,console,
  });
  vm.runInContext(source.slice(0,startup)+
    ';globalThis.testing={renderBoard(board,sort="current"){state.board=board;state.meta={poll_seconds:600};$("sort").value=sort;render();},historyPeak,historyPeakText,historyExplanation,observedCoverage,basisExplanation,csvRows,chart};',context);
  return {...context.testing,element};
}
const row=(extra={})=>({
  team_key:'team:one',name:'一队',official_score:'70',official_rank:2,reference_rank:2,
  peak_score:'70',confirmed_peak_lower_bound:'70',peak_rank:99,gap:'0',present:true,
  observed_official_peak_score:'90',observed_official_best:[],best:[],current:[],
  historical_submissions:2,rescored_submissions:1,unavailable_submissions:1,
  official_anchor_submissions:1,formula_rescored_submissions:0,peak_status:'partial',
  current_baseline_history_peak_score:null,history_peak_status:'insufficient-data',
  observed_problems:1,total_problems:1,reasons:[],...extra,
});
const board=(rows=[row()],extra={})=>({
  scope:{demo:false,group:'公开组',epoch:'test',problems:[{id:'p'}]},scope_id:'scope',
  rows,notes:[],snapshot_count:2,first_seen:'2026-10-28T01:00:00Z',observed_at:'2026-10-28T02:00:00Z',
  score_basis:{kind:'current-baseline',as_of:'2026-10-28T02:00:00Z',status:'partial',
    formula_recomputation_enabled:false,total_testcase_count:15,visible_testcase_count:5},...extra,
});

test('hidden old 90 / current 70 keeps historical 90 and does not turn lower bound 70 into a history peak',()=>{
  const app=ui(), b=board(); app.renderBoard(b);
  assert.equal(app.historyPeak(b.rows[0],b),null);
  assert.equal(app.historyPeakText(b.rows[0],b),'无法确认');
  const html=app.element('rows').innerHTML;
  assert.match(html,/<td class="green">70\.00<\/td>/);
  assert.match(html,/<td class="amber">90\.00/);
  assert.match(html,/<td class="unknown-score">无法确认/);
  assert.doesNotMatch(html,/<td class="blue">70\.00/);
  assert.doesNotMatch(html,/#99/,'no synthetic historical rank in the official rank column');
  assert.match(app.element('score-columns').innerHTML,/当时基准 · 仅供参考/);
  assert.match(app.element('warning').textContent,/不以当前分代替/);
});

test('complete whole-submission recomputation may establish observed history 66.67 above current 33.33',()=>{
  const app=ui(), b=board([row({official_score:'33.33',peak_score:'66.67',
    current_baseline_history_peak_score:'66.67',history_peak_status:'verified-observed',history_peak_gap:'33.34',
    historical_submissions:3,rescored_submissions:3,unavailable_submissions:0,
    formula_rescored_submissions:2,peak_status:'complete'})]);
  b.score_basis.formula_recomputation_enabled=true;
  app.renderBoard(b);
  assert.equal(app.historyPeakText(b.rows[0],b),'66.67');
  assert.match(app.element('rows').innerHTML,/<td class="green">33\.33<\/td>/);
  assert.match(app.element('rows').innerHTML,/<td class="blue">66\.67/);
  assert.match(app.element('rows').innerHTML,/<td class="gap">\+33\.34<\/td>/);
  assert.match(app.observedCoverage(b.rows[0],b),/非完整赛事历史/);
  const csv=app.csvRows(b,b.rows);
  assert.equal(csv[1][csv[0].indexOf('同基准分差')],'33.34','preserve backend Decimal rather than exporting floating error');
});

test('one current version is explicitly distinguished from a recovered full contest history',()=>{
  const app=ui(), b=board([row({current_baseline_history_peak_score:'70',
    history_peak_status:'verified-observed',historical_submissions:1,rescored_submissions:1,
    unavailable_submissions:0,peak_status:'complete'})]);
  app.renderBoard(b);
  assert.match(app.element('rows').innerHTML,/仅已观测 1 条有效提交 · 非完整赛事历史/);
  assert.match(app.element('rows').innerHTML,/仅有当前一个有效版本，尚无旧版本可比较/);
  assert.match(app.basisExplanation(b),/未观测或未公开的提交不在覆盖范围内/);
});

test('current sorting is independent from old raw peaks and unknown strict peaks remain last',()=>{
  const app=ui(), lower=row(), higher=row({team_key:'team:two',name:'二队',official_score:'80',
    observed_official_peak_score:'80',current_baseline_history_peak_score:'80',history_peak_status:'verified-observed'});
  const b=board([lower,higher]);
  app.renderBoard(b);
  assert.ok(app.element('rows').innerHTML.indexOf('二队')<app.element('rows').innerHTML.indexOf('一队'));
  app.renderBoard(b,'audit');
  assert.ok(app.element('rows').innerHTML.indexOf('一队')<app.element('rows').innerHTML.indexOf('二队'));
  app.renderBoard(b,'peak');
  assert.ok(app.element('rows').innerHTML.indexOf('二队')<app.element('rows').innerHTML.indexOf('一队'));
});

test('CSV keeps unknown historical peak blank and labels the current anchor as a lower bound',()=>{
  const app=ui(), b=board(), csv=app.csvRows(b,b.rows);
  const record=Object.fromEntries(csv[0].map((name,index)=>[name,csv[1][index]]));
  assert.equal(record['官方当前分'],'70');
  assert.equal(record['观测历史最高(当时基准，非当前性能)'],'90');
  assert.equal(record['当前基准历史最高(仅已观测范围)'],null);
  assert.equal(record['当前基准历史最高状态'],'insufficient-data');
  assert.equal(record['当前基准可确认下界(非完整峰值)'],'70');
  assert.equal(record['同基准分差'],null);
});

test('legacy demo without new history fields remains a clearly separate raw-score view',()=>{
  const app=ui(), legacy=row({peak_score:'90',gap:'20'});
  delete legacy.history_peak_status;
  const b=board([legacy],{score_basis:undefined,scope:{demo:true,group:'A',epoch:'demo',problems:[{id:'p'}]}});
  app.renderBoard(b);
  assert.match(app.element('rows').innerHTML,/90\.00/);
  assert.match(app.element('board-title').textContent,/原始官方分峰值合计/);
  assert.match(app.element('score-columns').innerHTML,/排名（/);
});

test('the history chart remains an original official-score trace with changing benchmarks',()=>{
  const app=ui();
  const html=app.chart([{observed_at:'2026-10-28T02:00:00Z',total:{score:'70'}},
    {observed_at:'2026-10-28T01:00:00Z',total:{score:'90'}}]);
  assert.match(html,/当时官方分轨迹，基准随时间变化/);
  assert.match(html,/90\.00/);
  assert.match(html,/70\.00/);
});
