'use strict';
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = value => value == null ? '—' : Number(value).toLocaleString('en-US', {minimumFractionDigits:2, maximumFractionDigits:2});
const when = (value, date = false) => value ? new Intl.DateTimeFormat('zh-CN', {timeZone:'Asia/Shanghai', ...(date ? {month:'2-digit',day:'2-digit'} : {}), hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(new Date(value)) : '—';
const staticMode = document.documentElement.dataset.mode === 'static';
const siteRoot = new URL('./', document.baseURI);
const state = {board:null, scopes:[], rows:[], request:0, meta:null, manifest:null, detailManifest:null, detailBoard:null, detailRow:null};
const currentBasis = board => board?.score_basis?.kind === 'current-baseline';
const auditPeak = (row, board) => currentBasis(board) ? row.observed_official_peak_score : row.peak_score;
const auditBest = (row, board) => currentBasis(board) ? (row.observed_official_best || []) : row.best;
const originalScore = (best, board) => currentBasis(board) ? best?.original_score : best?.score;
const historyModel = board => currentBasis(board) && board.rows.some(row=>Object.hasOwn(row,'history_peak_status'));
const historyPeak = (row, board) => historyModel(board) ? (row.history_peak_status==='verified-observed' ? row.current_baseline_history_peak_score ?? null : null) : row.peak_score;
const historyPeakText = (row, board) => historyModel(board) && historyPeak(row,board)==null ? (row.history_peak_status==='no-valid-history' ? '尚无有效记录' : '无法确认') : fmt(historyPeak(row,board));
const historyGap = (row, board) => historyPeak(row,board)==null || row.official_score==null ? null : historyModel(board) && Object.hasOwn(row,'history_peak_gap') ? row.history_peak_gap : Number(historyPeak(row,board))-Number(row.official_score);
const coverageStatus = value => ({complete:'已记录有效提交均可确认',partial:'部分覆盖',unavailable:'无法确认'}[value] || '覆盖待核验');
const reasonsText = value => Array.isArray(value) ? value.map(String).join('；') : typeof value === 'string' ? value : '';
function submissionCoverage(row) {
  const count=value => Number.isInteger(value) && value >= 0 ? value : '—';
  return '当前基准可确认 '+count(row.rescored_submissions)+' / 已记录 '+count(row.historical_submissions)+' 条 · '+count(row.unavailable_submissions)+' 条缺少重算条件';
}
function observedCoverage(row, board) {
  if(!historyModel(board)) return submissionCoverage(row);
  const count=Number.isInteger(row.historical_submissions) && row.historical_submissions>=0 ? row.historical_submissions : '—';
  return '仅已观测 '+count+' 条有效提交 · 非完整赛事历史';
}
function historyExplanation(row, board) {
  if(!historyModel(board)) return coverageStatus(row.peak_status)+' · '+submissionCoverage(row);
  if(row.history_peak_status==='no-valid-history') return '尚无已观测有效提交可用于比较';
  if(row.history_peak_status!=='verified-observed') return '缺少完整或一致的重算依据，当前分不能代替历史最佳';
  if(Number(row.historical_submissions)===1 && board.score_basis.formula_recomputation_enabled===false) return '仅有当前一个有效版本，尚无旧版本可比较';
  return '已观测有效提交均可按当前基准确认';
}
function basisExplanation(board) {
  const basis=board.score_basis;
  const calibrationNotice=basis.calibration_status==='conflict' ? '本轮存在同基准矛盾，暂停该题历史最佳认证。' : '';
  const hidden=Number(basis.total_testcase_count)-Number(basis.visible_testcase_count);
  const rows=Array.isArray(board.rows) ? board.rows : [];
  const officialOnly=currentBasis(board) && basis.formula_recomputation_enabled===false
    && rows.some(row=>Number.isInteger(row.official_anchor_submissions) && row.official_anchor_submissions>0)
    && rows.every(row=>row.formula_rescored_submissions===0);
  if(historyModel(board)) return calibrationNotice+'历史最佳按最新全场测试点最优用时，对每条历史完整提交重算后取最大值；其他队伍刷新基准时，历史最佳也可能下降。'+(Number.isInteger(hidden) && hidden>0 ? hidden+' 个计分测试点的耗时和基准未公开。' : '')+(officialOnly ? '当前没有历史提交的完整公式重算结果。' : '')+'缺少重算条件时显示“无法确认”，不沿用旧分，也不以当前分兜底。若仅有当前一个有效版本，相等只代表尚无旧版本可比较。未观测或未公开的提交不在覆盖范围内。';
  return (officialOnly ? '当前仅采用本轮官方成绩；完整历史重算 0 条，真实历史最高分无法独立确认。当前分与可确认最高分相等，不证明真实历史最高分也相等。' : '')+(Number.isInteger(hidden) && hidden > 0 ? hidden+' 个计分测试点的耗时和基准未公开，部分历史提交无法重算。' : '只比较公开数据足以确认的完整提交，缺少重算条件的历史提交单独标注。')+'旧高分保留用于审计，不参与当前同基准比较。当前可确认结果不代表未公开历史提交中的真实最高分。';
}
function staticPath(path) {
  if(typeof path !== 'string' || !/^\.?\/?_data\/[A-Za-z0-9._/-]+$/.test(path) || path.split('/').includes('..')) throw new Error('静态快照路径无效，保留上一份显示。');
  const url = new URL(path, siteRoot);
  if(url.origin !== siteRoot.origin || !url.pathname.startsWith(siteRoot.pathname + '_data/')) throw new Error('静态快照路径无效，保留上一份显示。');
  return url.href;
}
function mapped(object, key) {
  if(!object || !Object.hasOwn(object, key)) throw new Error('这份静态快照缺少所选记录，保留上一份显示。');
  return object[key];
}
function resource(kind, values = {}, manifest = state.manifest) {
  if(staticMode) {
    if(!manifest) throw new Error('尚未读取静态快照目录。');
    let path;
    if(kind === 'board') path = mapped(manifest.boards, values.scope);
    else if(kind === 'history' || kind === 'archive') path = mapped(mapped(kind === 'history' ? manifest.history : manifest.archives, values.scope), values.team);
    else if(kind === 'evidence') path = mapped(manifest.evidence, values.id);
    else path = mapped(manifest, kind);
    return staticPath(path);
  }
  if(kind === 'board') return '/api/board/' + encodeURIComponent(values.scope);
  if(kind === 'history') return '/api/history/' + encodeURIComponent(values.scope) + '?team=' + encodeURIComponent(values.team);
  if(kind === 'archive') return '/api/archive/' + encodeURIComponent(values.scope) + '?team=' + encodeURIComponent(values.team) + '&limit=20';
  if(kind === 'evidence') return '/api/evidence/' + encodeURIComponent(values.id);
  return '/api/' + kind;
}
async function api(path) {
  const token = staticMode ? null : sessionStorage.getItem('watcher-token');
  const response = await fetch(path, {headers:token ? {Authorization:'Bearer ' + token} : {}, cache:'no-store'});
  if (!response.ok) throw new Error(!staticMode && response.status === 401 ? '请输入访问令牌，再刷新看板。' : '读取失败（HTTP ' + response.status + '），保留上一份显示。');
  return response;
}
async function json(path) {return (await api(path)).json();}
async function readManifest() {
  const manifest=await json(staticPath('_data/manifest.json'));
  if(manifest?.schema !== 1 || !Number.isFinite(Date.parse(manifest.generated_at)) || manifest.collector_enabled !== false || !Number.isFinite(Number(manifest.poll_seconds)) || Number(manifest.poll_seconds) <= 0) throw new Error('静态快照目录格式无效，保留上一份显示。');
  return manifest;
}
function error(message) {$('error').textContent=message; $('error').classList.toggle('hidden', !message);}
function download(content, name, type) {
  const url=URL.createObjectURL(new Blob([content], {type}));
  const a=document.createElement('a'); a.href=url; a.download=name; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
}
async function load() {
  const ticket=++state.request;
  const old=$('scope').value;
  $('refresh').disabled=true;
  try {
    const manifest=staticMode ? await readManifest() : null;
    const [meta, runs]=await Promise.all([json(resource('scopes', {}, manifest)), json(resource('runs', {}, manifest))]);
    if(!Array.isArray(meta.scopes) || !Array.isArray(runs.runs)) throw new Error('快照内容格式无效，保留上一份显示。');
    const selected=meta.scopes.some(s=>s.id===old) ? old : meta.scopes[0]?.id;
    const board=selected ? await json(resource('board', {scope:selected}, manifest)) : null;
    if(board && (board.scope_id !== selected || !board.scope || !Array.isArray(board.rows))) throw new Error('所选榜单内容无效，保留上一份显示。');
    if(ticket !== state.request) return;
    state.meta=staticMode ? {...meta, collector_enabled:false, poll_seconds:manifest.poll_seconds} : meta;
    state.manifest=manifest; state.scopes=meta.scopes;
    $('scope').innerHTML=meta.scopes.map(s=>`<option value="${esc(s.id)}">${esc(s.title)} · ${esc(s.stage)} · ${esc(s.epoch)}</option>`).join('');
    if(selected) $('scope').value=selected;
    if(board) {
      state.board=board; render();
    } else {
      state.board=null; state.rows=[]; $('rows').innerHTML=''; $('empty').classList.remove('hidden');
      $('live-status').textContent=staticMode ? 'GitHub 定时快照 · 等待首份完整数据' : meta.collector_enabled ? '采集已启用 · 等待首份完整数据' : '暂无数据 · 采集器未启用';
    }
    if(staticMode) {
      $('hosting-banner').classList.remove('hidden');
      $('hosting-banner').textContent='GitHub 定时快照 · 计划每 '+Math.round(Number(manifest.poll_seconds)/60)+' 分钟采集；最近发布 '+when(manifest.generated_at,true)+'（北京时间）。定时任务可能延迟，页面会检查最新快照。';
    }
    error('');
    $('runs').innerHTML=runs.runs.length ? runs.runs.map(r=>`<pre>${esc(when(r.started_at,true))} · ${esc(r.status)}\n${esc(JSON.stringify(r.detail,null,2))}</pre>`).join('') : '<p>尚无采集运行。演示数据与真实采集相互隔离。</p>';
  } catch(e) {if(ticket===state.request) {if(state.board) $('scope').value=state.board.scope_id; error(e.message);}}
  finally {if(ticket===state.request) $('refresh').disabled=false;}
}
function render() {
  const b=state.board; if(!b) return;
  const query=$('search').value.trim().toLowerCase();
  const rows=b.rows.filter(r=>(r.name+' '+r.team_key).toLowerCase().includes(query));
  const modern=historyModel(b), mode=$('sort').value;
  const sortValue=row=>mode==='peak' ? (modern ? historyPeak(row,b) : row.peak_score) : row.official_score;
  rows.sort((a,b)=>{
    const left=sortValue(a), right=sortValue(b);
    return left==null && right!=null ? 1 : right==null && left!=null ? -1 : left!=null && right!=null && Number(right)!==Number(left) ? Number(right)-Number(left) : a.team_key.localeCompare(b.team_key);
  });
  state.rows=rows;
  $('demo-banner').classList.toggle('hidden', !b.scope.demo);
  const comparable=currentBasis(b);
  $('score-columns').innerHTML=modern ? '<th><span id="rank-basis-label">官方</span>名次</th><th>队伍</th><th class="green">官方当前</th><th id="peak-score-label" class="blue">最新基准历史最佳</th><th id="gap-label">同基准分差</th><th>观测覆盖</th>' : '<th>排名（<span id="rank-basis-label" class="purple">原始峰值</span> / <span class="amber">官方</span>）</th><th>队伍</th><th>总分（<span class="green">官方当前</span> / <span id="peak-score-label" class="blue">原始官方峰值</span>）</th><th id="gap-label">原始官方分差</th><th>题目覆盖</th>';
  $('score-columns').closest('table').classList.toggle('current-basis-scores',modern);
  const scoreLabel=modern ? '当前分与动态历史最佳' : comparable ? '当前基准可确认最高分' : '原始官方分峰值合计';
  $('board-title').textContent=b.scope.group+(/^[A-D]$/.test(b.scope.group)?' 组':'')+' · '+scoreLabel;
  $('peak-sort-label').textContent=modern ? '最新基准历史最佳（已确认）' : scoreLabel;
  $('peak-score-label').textContent=modern ? '最新基准历史最佳' : comparable ? '当前基准可确认最高分' : '原始官方峰值';
  $('rank-basis-label').textContent=modern ? '官方' : comparable ? '可确认' : '原始峰值';
  $('gap-label').textContent=modern ? '同基准分差' : comparable ? '当前基准分差' : '原始官方分差';
  $('comparison-label').textContent=modern ? '同基准历史最佳高于当前' : comparable ? '同基准高于当前官方分' : '旧记录高于当前官方分';
  $('comparison-note').textContent=modern ? '只统计当前基准下可完整确认的结果' : comparable ? '仅统计当前基准可确认结果' : '原始官方分差，基准可能不同';
  $('warning').textContent=modern ? '动态历史最佳 = 对已观测的每条完整有效历史提交，按最新全场测试点最优用时重算后取最大值。其他队伍刷新基准时，该值也可能下降。存在无法重算的旧提交时显示“无法确认”，不沿用旧时高分、不以当前分代替。单题只选择一条完整提交，不拼接测试点。' : comparable ? '当前基准可确认最高分 = 每道题采用最近完整快照的官方成绩，或公开数据足够时对完整历史提交按同一基准重算，再选择其中最大值。单题只选择一条完整提交，不拼接不同提交的测试点。' : '原始官方分峰值合计 = 每道题已记录的完整有效官方分数取最大值后求和。原始分数可能使用不同基准，不表示统一基准下的真实最高性能。';
  $('basis-explanation').textContent=(comparable ? basisExplanation(b)+' ' : '历史分数可能使用不同的全场基准。')+'本榜不是官方最终榜，也不推断未提交、未公开或漏采的成绩。缺少官方名次时显示“—”，参考排名不冒充官方排名。';
  $('basis-summary').classList.toggle('hidden',!comparable);
  if(comparable) {
    $('basis-summary').textContent='比较基准截至 '+when(b.score_basis.as_of,true)+'（北京时间） · '+coverageStatus(b.score_basis.status)+'。'+basisExplanation(b);
    $('basis-summary').classList.toggle('partial',b.score_basis.status !== 'complete');
  }
  $('epoch').textContent=b.scope.epoch;
  $('teams').textContent=b.rows.length;
  $('regressions').textContent=b.rows.filter(r=>modern ? historyGap(r,b)!=null && Number(historyGap(r,b))>0 : r.gap!==null && Number(r.gap)>0).length;
  $('snapshots').textContent=b.snapshot_count;
  $('coverage').textContent='起始于 '+when(b.first_seen,true)+'（北京时间）';
  $('latest').textContent=when(b.observed_at);
  const age=Math.max(0,(Date.now()-Date.parse(b.observed_at))/1000);
  const stale=age>Math.max(300,Number(state.meta?.poll_seconds||120)*3);
  $('freshness').textContent=(staticMode ? 'GitHub 定时采集 · ' : b.imported ? '导入快照 · ' : '') + (stale ? '数据已过时 · '+Math.floor(age/60)+' 分钟前' : '北京时间 · '+Math.floor(age)+' 秒前');
  $('live-status').textContent=b.scope.demo ? 'DEMO · 合成数据' : staticMode ? (stale ? 'GitHub 定时快照 · 观测已过时' : 'GitHub 定时快照 · '+when(b.observed_at)) : stale ? '观测已过时 · 检查采集记录' : state.meta?.collector_enabled ? '采集器运行中' : '快照只读 · 采集器未启用';
  $('source-notes').innerHTML=b.notes.map(n=>'<p>'+esc(n)+'</p>').join('');
  $('rows').innerHTML=rows.map(r=>modern ? `<tr>
    <td><span class="amber">${r.official_rank==null?'—':'#'+r.official_rank}</span>${r.official_rank==null && r.reference_rank!=null ? `<span class="subtext">按当前分参考 #${r.reference_rank}<br>非官方名次</span>` : ''}</td>
    <td><button class="team-button" data-team="${esc(r.team_key)}">${esc(r.name)}</button><span class="subtext score-state">${esc(observedCoverage(r,b))}</span>${!r.present?'<span class="subtext">未在最新榜单中 · 历史仍保留</span>':''}${r.sum_mismatch?'<span class="subtext">逐题合计与官方总分不一致 · 待核对</span>':''}</td>
    <td class="green">${fmt(r.official_score)}${r.current_score_consistency==='conflict'?'<span class="subtext score-state partial">与公开基准/规则不一致，待核对</span>':''}</td>
    <td class="${historyPeak(r,b)==null?'unknown-score':'blue'}">${esc(historyPeakText(r,b))}<span class="subtext score-state">${esc(historyExplanation(r,b))}</span></td>
    <td class="gap">${historyGap(r,b)==null?'—':(historyGap(r,b)>0?'+':'')+fmt(historyGap(r,b))}</td>
    <td class="coverage">${r.observed_problems} / ${r.total_problems}<span class="subtext">可确认题目<br>${esc(submissionCoverage(r))}</span></td></tr>` : `<tr>
    <td><span class="purple">${r.peak_rank==null?'—':'#'+r.peak_rank}</span><span class="slash">/</span><span class="amber">${r.official_rank==null?'—':'#'+r.official_rank}</span>${r.official_rank==null && r.reference_rank!=null ? `<span class="subtext">总分参考 #${r.reference_rank} · 非官方</span>` : ''}</td>
    <td><button class="team-button" data-team="${esc(r.team_key)}">${esc(r.name)}</button>${comparable ? `<span class="subtext score-state ${r.peak_status==='complete'?'':'partial'}">${esc(coverageStatus(r.peak_status))} · ${esc(submissionCoverage(r))}</span>` : ''}${!r.present?'<span class="subtext">未在最新榜单中 · 历史仍保留</span>':''}${r.sum_mismatch?'<span class="subtext">逐题合计与官方总分不一致 · 待核对</span>':''}</td>
    <td><span class="green">${fmt(r.official_score)}</span><span class="slash">/</span><span class="blue">${fmt(r.peak_score)}</span></td>
    <td class="gap ${Number(r.gap)>10?'notice':''}">${r.gap==null?'—':(Number(r.gap)>0?'+':'')+fmt(r.gap)}</td>
    <td class="coverage">${r.observed_problems} / ${r.total_problems}<span class="subtext">${comparable?'当前基准可确认题目':'已记录有效题目'}</span></td></tr>`).join('');
  $('empty').textContent=query ? '没有匹配的队伍，请调整搜索内容。' : '当前已保存榜单中没有队伍记录。';
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
  return `<svg class="chart" viewBox="0 0 880 170" role="img" aria-label="当时官方分轨迹，基准随时间变化"><text x="14" y="18">${fmt(hi)}</text><text x="14" y="160">${fmt(lo)}</text>${segments.map(s=>'<polyline points="'+s.join(' ')+'"/>').join('')}</svg><div class="timeline"><span>${esc(when(ordered[0].observed_at,true))}</span><span>${esc(when(ordered.at(-1).observed_at,true))}</span></div>`;
}
async function showTeam(key) {
  const b=state.board, row=b?.rows.find(r=>r.team_key===key); if(!row) return;
  const comparable=currentBasis(b), modern=historyModel(b);
  const label=modern ? '当前基准已确认下界（诊断）' : comparable ? '当前基准可确认最高分' : '原始官方分峰值合计';
  const manifest=state.manifest;
  state.detailManifest=manifest; state.detailBoard=b; state.detailRow=row;
  $('team-title').textContent=row.name;
  $('team-content').innerHTML='<p class="detail-note">读取完整提交证据…</p>';
  $('team-dialog').showModal();
  try {
    const [history, archived]=await Promise.all([json(resource('history',{scope:b.scope_id,team:key},manifest)), json(resource('archive',{scope:b.scope_id,team:key},manifest))]);
    $('team-content').innerHTML=`<p class="detail-note">${esc(key)} · 官方当前 ${fmt(row.official_score)}${modern ? ' / 最新基准历史最佳 '+esc(historyPeakText(row,b)) : ' / '+esc(label)+' '+fmt(row.peak_score)}<br>本次详情对应 ${esc(when(b.observed_at,true))} 的榜单。单题只选择一条完整有效提交。</p>
      ${comparable ? `<div class="basis-note ${row.peak_status==='complete'?'':'partial'}"><b>${esc(modern ? historyExplanation(row,b) : coverageStatus(row.peak_status))}</b> · ${esc(observedCoverage(row,b))}<br>${modern ? esc(submissionCoverage(row))+'<br>' : ''}比较基准截至 ${esc(when(b.score_basis.as_of,true))}（北京时间）。${esc(basisExplanation(b))}${reasonsText(row.reasons)?'<br>'+esc(reasonsText(row.reasons)):''}</div>` : '<p class="detail-note">以下原始官方分可能使用不同基准，只用于记录当时公布的成绩。</p>'}
      <div class="audit-summary"><b>旧时官方分最大值（审计，非当前历史最佳） · ${fmt(auditPeak(row,b))}</b><p>这里只保留当时公布过的原始分数；即使曾为 100 分，也不表示按最新基准仍为 100 分，不参与主榜、同基准分差或排序。</p></div>
      ${modern ? '<p class="detail-note">以下只列出当前基准下已确认部分的下界 '+fmt(row.confirmed_peak_lower_bound ?? row.peak_score)+'，用于核查证据。只要存在无法重算的旧提交，这个值就不能代替当前基准历史最高分。</p>' : ''}
      <h3>${esc(label)} · 逐题证据</h3><div class="table-wrap"><table><thead><tr><th>题目</th><th>官方当前 / ${esc(label)}</th><th>选中提交当时官方分</th><th>原始官方最高（审计）</th><th>首次观测时间</th><th>确认依据</th></tr></thead><tbody>${b.scope.problems.map(p=>{
        const best=row.best.find(x=>x.problem_id===p.id), cur=row.current.find(x=>x.problem_id===p.id), audit=auditBest(row,b).find(x=>x.problem_id===p.id);
        const basisKind=best?.score_basis_kind==='official-current' ? '最新官方成绩锚点' : best?.score_basis_kind==='recomputed-current' ? '当前基准完整重算' : '原始官方记录';
        return `<tr><td>${esc(p.title)}</td><td><span class="green">${fmt(cur?.score)}</span> / <span class="blue">${fmt(best?.score)}</span></td><td>${fmt(originalScore(best,b))}</td><td>${fmt(audit?.score)}${audit?`<br><button class="quiet evidence-button" data-evidence="${esc(audit.evidence_id)}" data-evidence-kind="audit">查看旧记录</button>`:''}</td><td>${esc(when(best?.observed_at,true))}</td><td>${best ? `<button class="quiet evidence-button" data-evidence="${esc(best.evidence_id)}" data-evidence-kind="current">查看确认依据</button><span class="subtext">${esc(basisKind)} · ${esc(best.submission_id||'源站未公开提交 ID')}</span>` : comparable ? '缺少完整提交数据，无法确认' : '尚未记录有效分数'}</td></tr>`;}).join('')}</tbody></table></div>
      <h3>旧时官方分轨迹（审计） · 最近 ${history.points.length} 份已加载快照</h3><p class="detail-note">这条审计曲线保留当时公布的官方分，不是按最新基准重算的历史最佳轨迹。</p>${chart(history.points)}${history.next_before?'<p class="detail-note">还有更早快照。完整榜单观测记录可使用页面下方的 JSONL 导出获取。</p>':''}
      <h3>已归档的公开提交列表 · ${archived.total} 条已关联版本</h3><p class="detail-note">提交列表与榜单观测分开保存。未公开 score 的历史提交不能被倒推成历史最高分；用户 ID 与队伍 ID 无明确映射时不强行关联。此处展示最近 20 条已关联记录。</p>
      ${archived.rows.length?`<pre>${esc(JSON.stringify(archived.rows.slice(0,20).map(r=>({id:r.submission_id,problem:r.problem_id,status:r.data.status,created:r.data.create_time})),null,2))}</pre>`:'<p class="detail-note">尚无关联的公开历史列表归档；这不代表该队没有提交历史。</p>'}
      <h3>分数口径与原始成绩证据</h3><pre id="evidence-content">点击“查看确认依据”或“查看旧记录”，分别查看当前比较口径与保留的原始官方分。</pre>`;
  } catch(e) {$('team-content').textContent=e.message;}
}
$('rows').addEventListener('click',e=>{const b=e.target.closest('[data-team]');if(b)showTeam(b.dataset.team);});
$('team-content').addEventListener('click',async e=>{const button=e.target.closest('[data-evidence]');if(!button)return;try{
  const record=await json(resource('evidence',{id:button.dataset.evidence},state.detailManifest));
  const board=state.detailBoard, row=state.detailRow, audit=button.dataset.evidenceKind==='audit';
  const selected=(audit?auditBest(row,board):row.best).find(item=>item.evidence_id===button.dataset.evidence);
  const context=currentBasis(board) ? audit ? {purpose:'historical-original-official-audit',recorded_official_score:selected?.score} : {purpose:historyModel(board)?'current-baseline-confirmed-lower-bound':'current-baseline-confirmed',score:selected?.score,current_baseline_history_peak_score:historyModel(board)?historyPeak(row,board):undefined,history_peak_status:row.history_peak_status,original_official_score:selected?.original_score,kind:selected?.score_basis_kind,as_of:selected?.score_basis_as_of,source:selected?.score_basis_source,basis:board.score_basis} : null;
  $('evidence-content').textContent=JSON.stringify(context ? {comparison_context:context,original_evidence:record} : record,null,2);
}catch(err){$('evidence-content').textContent=err.message;}});
$('close-dialog').addEventListener('click',()=>$('team-dialog').close());
$('refresh').addEventListener('click',load); $('scope').addEventListener('change',load); $('search').addEventListener('input',render); $('sort').addEventListener('change',render);
$('token-button').addEventListener('click',()=>{const value=prompt('输入看板访问令牌（仅保存在本标签页会话中，不会放入 URL）');if(value!==null){value?sessionStorage.setItem('watcher-token',value):sessionStorage.removeItem('watcher-token');load();}});
function csvRows(board, rows) {
  const comparable=currentBasis(board), modern=historyModel(board);
  return [['队伍','队伍ID','官方名次','按当前分参考名次(非官方)','官方当前分','最新基准历史最佳(仅已观测范围)','当前基准历史最高状态','同基准分差','比较基准时间','观测范围','当前基准可确认下界(非完整峰值)','已记录完整有效提交数','当前基准可确认提交数','最新官方成绩锚点数','完整公式重算数','缺少重算条件提交数','缺失原因','已确认或记录有效题数','总题数','观测时间','演示数据','旧时官方分最大值(审计，非当前历史最佳)','当前官方分一致性'],...rows.map(row=>[
    row.name,row.team_key,row.official_rank,row.reference_rank,row.official_score,
    comparable?historyPeak(row,board):null,modern?row.history_peak_status:comparable?coverageStatus(row.peak_status):'未统一基准',
    comparable?historyGap(row,board):null,comparable?board.score_basis.as_of:null,
    modern?observedCoverage(row,board):'已观测记录，不代表完整赛事历史',
    comparable?(row.confirmed_peak_lower_bound ?? row.peak_score):null,
    row.historical_submissions,row.rescored_submissions,row.official_anchor_submissions,row.formula_rescored_submissions,
    row.unavailable_submissions,reasonsText(row.reasons),row.observed_problems,row.total_problems,board.observed_at,board.scope.demo,
    auditPeak(row,board),row.current_score_consistency ?? null
  ])];
}
$('export-csv').addEventListener('click',()=>{
  const b=state.board; if(!b) return;
  const cell=x=>'"'+String(x??'').replace(/^[=+\-@\t\r]/,m=>"'"+m).replace(/"/g,'""')+'"';
  const data=csvRows(b,state.rows);
  download('\ufeff'+data.map(r=>r.map(cell).join(',')).join('\r\n'),'observed-peak.csv','text/csv;charset=utf-8');
});
$('export-json').addEventListener('click',async()=>{try{download(await (await api(resource('export'))).text(),'observed-snapshots.jsonl','application/x-ndjson');}catch(e){error(e.message);}});
if(staticMode) {
  $('token-button').classList.add('hidden');
  $('refresh').textContent='检查最新快照';
  $('empty').textContent='尚无已发布的完整榜单快照，请稍后检查采集运行记录。';
  $('live-status').textContent='GitHub 定时快照 · 正在读取';
}
load(); setInterval(()=>{if(!document.hidden && !$('team-dialog').open)load();},60000);
