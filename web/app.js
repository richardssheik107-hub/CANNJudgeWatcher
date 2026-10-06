'use strict';
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = value => value == null ? '—' : Number(value).toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2});
const when = (value, date = false) => value ? new Intl.DateTimeFormat('zh-CN', {timeZone:'Asia/Shanghai', ...(date ? {month:'2-digit',day:'2-digit'} : {}), hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(new Date(value)) : '—';
const state = {board:null, scopes:[], rows:[], request:0, meta:null};
async function api(path) {
  const token = sessionStorage.getItem('watcher-token');
  const response = await fetch(path, {headers:token ? {Authorization:'Bearer ' + token} : {}, cache:'no-store'});
  if (!response.ok) throw new Error(response.status === 401 ? '请输入访问令牌，再刷新看板。' : '读取失败（HTTP ' + response.status + '），保留上一份显示。');
  return response;
}
async function json(path) {return (await api(path)).json();}
function error(message) {$('error').textContent=message; $('error').classList.toggle('hidden', !message);}
function download(content, name, type) {
  const url=URL.createObjectURL(new Blob([content], {type}));
  const a=document.createElement('a'); a.href=url; a.download=name; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
}
async function load() {
  const ticket=++state.request;
  $('refresh').disabled=true;
  try {
    const meta=await json('/api/scopes');
    if(ticket !== state.request) return;
    state.meta=meta; state.scopes=meta.scopes;
    const old=$('scope').value;
    $('scope').innerHTML=meta.scopes.map(s=>`<option value="${esc(s.id)}">${esc(s.title)} · ${esc(s.stage)} · ${esc(s.epoch)}</option>`).join('');
    if(meta.scopes.some(s=>s.id===old)) $('scope').value=old;
    if(meta.scopes.length) {
      const board=await json('/api/board/'+encodeURIComponent($('scope').value));
      if(ticket !== state.request) return;
      state.board=board; render();
    } else {
      state.board=null; $('rows').innerHTML=''; $('empty').classList.remove('hidden');
      $('live-status').textContent=meta.collector_enabled ? '采集已启用 · 等待首份完整数据' : '暂无数据 · 采集器未启用';
    }
    error('');
    const runs=await json('/api/runs');
    if(ticket !== state.request) return;
    $('runs').innerHTML=runs.runs.length ? runs.runs.map(r=>`<pre>${esc(when(r.started_at,true))} · ${esc(r.status)}\n${esc(JSON.stringify(r.detail,null,2))}</pre>`).join('') : '<p>尚无采集运行。演示数据与真实采集相互隔离。</p>';
  } catch(e) {if(ticket===state.request) error(e.message);}
  finally {if(ticket===state.request) $('refresh').disabled=false;}
}
function render() {
  const b=state.board; if(!b) return;
  const query=$('search').value.trim().toLowerCase();
  const rows=b.rows.filter(r=>(r.name+' '+r.team_key).toLowerCase().includes(query));
  if($('sort').value==='current') rows.sort((a,b)=>(b.official_score==null ? -Infinity : Number(b.official_score))-(a.official_score==null ? -Infinity : Number(a.official_score)) || a.team_key.localeCompare(b.team_key));
  state.rows=rows;
  $('demo-banner').classList.toggle('hidden', !b.scope.demo);
  $('board-title').textContent=b.scope.group+(/^[A-D]$/.test(b.scope.group)?' 组':'')+' · 各队逐题最高分合计';
  $('epoch').textContent=b.scope.epoch;
  $('teams').textContent=b.rows.length;
  $('regressions').textContent=b.rows.filter(r=>r.gap!==null && Number(r.gap)>0).length;
  $('snapshots').textContent=b.snapshot_count;
  $('coverage').textContent='起始于 '+when(b.first_seen,true)+'（北京时间）';
  $('latest').textContent=when(b.observed_at);
  const age=Math.max(0,(Date.now()-Date.parse(b.observed_at))/1000);
  const stale=age>Math.max(300,Number(state.meta?.poll_seconds||120)*3);
  $('freshness').textContent=(b.imported ? '导入快照 · ' : '') + (stale ? '数据已过时 · '+Math.floor(age/60)+' 分钟前' : '北京时间 · '+Math.floor(age)+' 秒前');
  $('live-status').textContent=b.scope.demo ? 'DEMO · 合成数据' : stale ? '观测已过时 · 检查采集记录' : state.meta?.collector_enabled ? '采集器运行中' : '快照只读 · 采集器未启用';
  $('source-notes').innerHTML=b.notes.map(n=>'<p>'+esc(n)+'</p>').join('');
  $('rows').innerHTML=rows.map(r=>`<tr>
    <td><span class="purple">${r.peak_rank==null?'—':'#'+r.peak_rank}</span><span class="slash">/</span><span class="amber">${r.official_rank==null?'—':'#'+r.official_rank}</span>${r.official_rank==null && r.reference_rank!=null ? `<span class="subtext">总分参考 #${r.reference_rank} · 非官方</span>` : ''}</td>
    <td><button class="team-button" data-team="${esc(r.team_key)}">${esc(r.name)}</button>${!r.present?'<span class="subtext">未在最新榜单中 · 历史仍保留</span>':''}${r.sum_mismatch?'<span class="subtext">逐题合计与官方总分不一致 · 待核对</span>':''}</td>
    <td><span class="green">${fmt(r.official_score)}</span><span class="slash">/</span><span class="blue">${fmt(r.peak_score)}</span></td>
    <td class="gap ${Number(r.gap)>10?'notice':''}">${r.gap==null?'—':(Number(r.gap)>0?'+':'')+fmt(r.gap)}</td>
    <td class="coverage">${r.observed_problems} / ${r.total_problems}<span class="subtext">已观测有效题目</span></td></tr>`).join('');
  $('empty').classList.toggle('hidden',rows.length>0);
  $('row-count').textContent='显示 '+rows.length+' / '+b.rows.length+' 支队伍';
}
function chart(points) {
  const ordered=[...points].reverse(), valid=ordered.filter(p=>p.total?.score!=null);
  if(!valid.length) return '<p class="detail-note">这些快照没有公开的官方总分，不能生成分数曲线。</p>';
  const vals=valid.map(p=>Number(p.total.score)), lo=Math.min(...vals), hi=Math.max(...vals);
  const t0=Date.parse(ordered[0].observed_at), span=Math.max(1,Date.parse(ordered.at(-1).observed_at)-t0);
  const segments=[]; let segment=[];
  for(const p of ordered) {
    if(p.total?.score==null) {if(segment.length) segments.push(segment); segment=[]; continue;}
    const x=30+(Date.parse(p.observed_at)-t0)/span*820, y=135-(Number(p.total.score)-lo)/Math.max(1,hi-lo)*105;
    segment.push(x.toFixed(1)+','+y.toFixed(1));
  }
  if(segment.length) segments.push(segment);
  return `<svg class="chart" viewBox="0 0 880 170" role="img" aria-label="已加载快照中的官方总分轨迹"><text x="14" y="18">${fmt(hi)}</text><text x="14" y="160">${fmt(lo)}</text>${segments.map(s=>'<polyline points="'+s.join(' ')+'"/>').join('')}</svg><div class="timeline"><span>${esc(when(ordered[0].observed_at,true))}</span><span>${esc(when(ordered.at(-1).observed_at,true))}</span></div>`;
}
async function showTeam(key) {
  const b=state.board, row=b?.rows.find(r=>r.team_key===key); if(!row) return;
  $('team-title').textContent=row.name;
  $('team-content').innerHTML='<p class="detail-note">读取完整提交证据…</p>';
  $('team-dialog').showModal();
  try {
    const history=await json('/api/history/'+b.scope_id+'?team='+encodeURIComponent(key));
    const archived=await json('/api/archive/'+b.scope_id+'?team='+encodeURIComponent(key)+'&limit=20');
    $('team-content').innerHTML=`<p class="detail-note">${esc(key)} · 当前 ${fmt(row.official_score)} / 已观测峰值合计 ${fmt(row.peak_score)}<br>本次详情对应 ${esc(when(b.observed_at,true))} 的榜单。逐题最佳可来自不同时间，单题只取一条完整有效成绩。</p>
      <h3>逐题最佳 · 可追溯证据</h3><div class="table-wrap"><table><thead><tr><th>题目</th><th>当前 / 峰值</th><th>首次观测时间</th><th>原始证据</th></tr></thead><tbody>${b.scope.problems.map(p=>{
        const best=row.best.find(x=>x.problem_id===p.id), cur=row.current.find(x=>x.problem_id===p.id);
        return `<tr><td>${esc(p.title)}</td><td><span class="green">${fmt(cur?.score)}</span> / <span class="blue">${fmt(best?.score)}</span></td><td>${esc(when(best?.observed_at,true))}</td><td>${best ? `<button class="quiet evidence-button" data-evidence="${best.evidence_id}">查看记录</button><span class="subtext">${esc(best.submission_id||'源站未公开提交 ID')}</span>` : '尚未观测到有效分数'}</td></tr>`;}).join('')}</tbody></table></div>
      <h3>官方总分轨迹 · 最近 ${history.points.length} 份已加载快照</h3>${chart(history.points)}${history.next_before?'<p class="detail-note">还有更早快照。完整记录可使用下方 JSONL 导出或带 before 游标的历史 API 获取。</p>':''}
      <h3>已归档的公开提交列表 · ${archived.total} 条已关联版本</h3><p class="detail-note">提交列表与榜单观测分开保存。未公开 score 的历史提交不能被倒推成历史最高分；用户 ID 与队伍 ID 无明确映射时不强行关联。完整归档可通过 /api/archive/赛事作用域 查询。</p>
      ${archived.rows.length?`<pre>${esc(JSON.stringify(archived.rows.map(r=>({id:r.submission_id,problem:r.problem_id,status:r.data.status,created:r.data.create_time})),null,2))}</pre>`:'<p class="detail-note">尚无关联的公开历史列表归档；这不代表该队没有提交历史。运行 backfill 命令可尝试补录平台允许读取的记录。</p>'}
      <h3>原始成绩证据</h3><pre id="evidence-content">点击“查看记录”，显示提交 ID、原始分数、测试点结果、采集时间及快照编号。</pre>`;
  } catch(e) {$('team-content').textContent=e.message;}
}
$('rows').addEventListener('click',e=>{const b=e.target.closest('[data-team]');if(b)showTeam(b.dataset.team);});
$('team-content').addEventListener('click',async e=>{const b=e.target.closest('[data-evidence]');if(!b)return;try{$('evidence-content').textContent=JSON.stringify(await json('/api/evidence/'+b.dataset.evidence),null,2);}catch(err){$('evidence-content').textContent=err.message;}});
$('close-dialog').addEventListener('click',()=>$('team-dialog').close());
$('refresh').addEventListener('click',load); $('scope').addEventListener('change',load); $('search').addEventListener('input',render); $('sort').addEventListener('change',render);
$('token-button').addEventListener('click',()=>{const value=prompt('输入看板访问令牌（仅保存在本标签页会话中，不会放入 URL）');if(value!==null){value?sessionStorage.setItem('watcher-token',value):sessionStorage.removeItem('watcher-token');load();}});
$('export-csv').addEventListener('click',()=>{
  const cell=x=>'"'+String(x??'').replace(/^[=+\-@\t\r]/,m=>"'"+m).replace(/"/g,'""')+'"';
  const data=[['队伍','队伍ID','峰值合计排名','官方名次','官方总分','已观测逐题峰值合计','已观测有效题数','总题数','观测时间','演示数据'],...state.rows.map(r=>[r.name,r.team_key,r.peak_rank,r.official_rank,r.official_score,r.peak_score,r.observed_problems,r.total_problems,state.board.observed_at,state.board.scope.demo])];
  download('\ufeff'+data.map(r=>r.map(cell).join(',')).join('\r\n'),'observed-peak.csv','text/csv;charset=utf-8');
});
$('export-json').addEventListener('click',async()=>{try{download(await (await api('/api/export')).text(),'observed-snapshots.jsonl','application/x-ndjson');}catch(e){error(e.message);}});
load(); setInterval(()=>{if(!document.hidden && !$('team-dialog').open)load();},60000);
