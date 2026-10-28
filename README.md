# CANNJudgeWatcher · 分数与历史证据

当前监控 [2026 CANN 京津东北决赛 · VarLenNdRotaryPosEmb](https://cannjudge.cn/public/op_challenge_jingdong_final/varlenndrotaryposemb/ranking?page=1&size=20)。[在线榜单](https://richardssheik107-hub.github.io/CANNJudgeWatcher/)由现有 Cloudflare Cron 每十分钟触发 GitHub Actions 更新，无须本机持续开机。仓库和所保存的公开成绩历史均公开。

## 当前监控与分数口径

- **官方当前分**来自所选题目榜。该题采用 `ranking_submission_mode=latest`，显示最新提交，不能把它当作历史最优提交。
- **最新基准历史最佳（仅已观测提交）**先用本轮全场测试点最优用时 TBest 对每一条历史完整有效提交重新评分，再取该队最大值；它会随他队刷新基准而下降。主表、排序、统计与分差只使用这项动态结果。有任一候选缺少完整或一致的重算依据，就显示“无法确认”，不以旧 100 分或当前下界兜底。首次只有一个有效版本时，相等只说明尚无旧版本可比较。
- **原始分审计记录**只在详情与 CSV 审计字段保留曾公布过的分数。它采用当时基准，可能仍记载 100；这个旧值不参与当前历史最佳的计算、主表、排序或统计。
- 单题选择一条完整提交，不拼接不同版本的最佳测试点。公式需在本赛规则中明确，并与本轮全部完整官方成绩精确校准后才能用于历史重算。分别支持已核验的线性比率、对数公式，不跨比赛继承规则。本轮完整公开公式与官方分矛盾时，隔离该题本轮锚点、暂停历史最佳认证，官方原始分仍保留并标待核对，不能再将矛盾旧分认证为动态峰值。
- 新比赛有 15 个测试点，其中 10 个隐藏，规则正文未给出可校准的赋分公式；当前不能独立完整重算旧提交。平台通用文档与旧星辰杯使用的公式不同，不按名称猜选公式，也不拿 5 个可见点均值替代完整分。
- 只覆盖实际采集到的榜单，十分钟之间被替换的提交可能漏采。公开全历史接口需要权限，不能恢复监控前其他队伍的完整历史，也不抓取选手私有源码。

固定配置为 [`config/monitor.jingdong-final.json`](config/monitor.jingdong-final.json)，默认 [`config/monitor.json`](config/monitor.json) 同样指向新题。新状态单独保存在 `watcher-state-jingdong-final` 分支的 `jingdong-final.sqlite3`；原星辰杯 `watcher-state` 分支及既有归档完整保留，不进入新看板或导出。云端工作流显式使用 `--profile jingdong-final`，旧比赛配置和接口仍可用于查看旧证据。

本地查看新题：

```bash
python -m watcher --config config/monitor.jingdong-final.json --db data/jingdong-final.sqlite3 poll
python -m watcher --config config/monitor.jingdong-final.json --db data/jingdong-final.sqlite3 serve
```

浏览器访问 `http://127.0.0.1:8088`。不带 `--poll` 只浏览现有证据；本地持续采集需要电脑保持运行。云端操作、首次隔离初始化、容量与令牌维护见 [运行说明](docs/GITHUB_RUN.md)，本次检查记录见 [验证记录](docs/VALIDATION.md)。

活动数据库达到 90 MiB 时会保护性停止采集并保留已有数据；自动归档尚未实现。预览 artifact 仅在手动勾选 `save_preview` 时保存一天，自动运行只保存数据库并发布网页。当前 GitHub 调度令牌到期日为 **2026-11-05**，需在到期前更新 Cloudflare Worker 的同名 Secret。

本仓库来自 v0.1.0 交付包，保留演示、只读 FastAPI、本地脚本、Docker、CSV/JSONL、SQLite 备份、身份/版本隔离、失败保留旧榜与限流退避。历史阶段记录见 [交付说明](docs/DELIVERY.md)。

## 先看本地演示

Windows 本机已配置环境时，可双击 `scripts\Start-LocalDemo.cmd` 打开演示，双击 `scripts\Stop-LocalDemo.cmd` 停止。脚本会保留并复用已核验的演示库，重复启动不会重复生成数据，采集器保持关闭。其他 Python 路径、端口和日志位置见 [本地运行说明](docs/LOCAL_RUN.md)。

需要 Python 3.11+。在仓库根目录运行：

```bash
python -m pip install -r requirements.txt
python -m watcher demo
python -m watcher --db data/demo.sqlite3 serve
```

浏览器打开 `http://127.0.0.1:8088`。下拉框切换 A/B 组，点击队伍查看逐题最佳和历史证据。黄色横幅与右上角始终标记 DEMO。`demo` 只接受空数据库，避免重复灌入或污染已有记录。

演示库默认 `data/demo.sqlite3`，真实采集默认 `data/live.sqlite3`。不要将演示库用作生产数据源。

## 旧比赛与通用接入

星辰杯旧配置 `config/monitor.starcup-final.json`、`Start-StarcupLive.cmd` 与旧数据库独立保留；这些明确标有 Starcup 的入口仍用于旧赛事。当前默认配置已切换京津东北决赛单题。

新增比赛应先通过 `discover` 核实公开 ID 和规则，再使用精确配置。源站封榜、缺页、权限、限流或网络失败时保留上一份完整榜，不生成伪造实时值。`problem_ids` 只接受属于该赛事的稳定 ID，单题榜的分数及名次来自对应题榜，不借用赛事总榜。不同规则版本、题目和比赛隔离保存。

## 历史回补、导出、备份

```bash
# 列出本地作用域 ID（不是源站 contest_id）
python -m watcher scopes

# 回补当前可访问的公开提交列表，最多读取 20 页
python -m watcher backfill SCOPE_ID --max-pages 20

# 返回 next_skip 时可继续；若列表持续变化，重从零扫描更安全，已有条目自动去重
python -m watcher backfill SCOPE_ID --start-skip NEXT_SKIP --max-pages 20

# 快照可互相导入，导入更早记录不会倒退“当前榜”
python -m watcher export snapshots.jsonl
python -m watcher import snapshots.jsonl

# 一致性备份含榜单快照、索引、公开提交列表归档、运行记录
python -m watcher backup backups/watcher.sqlite3
```

`complete=true` 仅表示本次从起点读完了接口当时公开的列表，不证明拥有开赛以来全部提交。达到页数上限会返回 `complete=false` 和游标；断流/权限限制可能造成缺口。历史列表若发生位移会要求重扫，不假装已经完整抓取。

**JSONL 导出的是榜单快照，不包括独立的提交列表归档**；迁移全部数据应使用 SQLite 备份。跨人共享的导入记录标记为 imported，不证明主办方认证；同一作用域、同一时间但内容冲突时拒绝覆盖。单次 JSONL 导入按行提交，失败前已导入行仍保留，修复后可幂等重试。

## 复用现有 CLI，而不是重写登录流程

将 `transport` 设置为 `windust-cli`，并在 `cli_command` 中填写已安装的 [WindustH/cannjudge-cli](https://github.com/WindustH/cannjudge-cli) 可执行文件参数数组，例如：

```json
{
  "transport": "windust-cli",
  "cli_command": ["/absolute/path/to/cannjudge"],
  "cli_auth": false
}
```

把这些键合并进原配置，不要丢掉赛事筛选。接入层仅调用 `--no-cache --json api get`，复用 CLI 的 HTTP/凭据能力，不触发提交或自动换号。需要自己的合法登录态时，用 CLI 的登录功能，确认后设置 `cli_auth=true`。默认 `http` 模式只读取同一组公开接口，不需要安装 Rust。

**没有把多个第三方仓库整仓复制过来。** 上轮候选中多个仓库缺少明确许可证，而且部分 CLI 的格式化榜单丢掉稳定 ID。具体复用层级、固定版本和不能直接复用的部分见 [`docs/UPSTREAM.md`](docs/UPSTREAM.md)。

## Docker 常驻运行

所选星辰杯决赛已准备独立的 [`docker-compose.starcup.yml`](docker-compose.starcup.yml)，固定公开赛事配置、独立数据卷并要求设置看板令牌。服务器选择、代码与真实历史迁移、SSH 查看、HTTPS 和重启验收见 [云端运行说明](docs/CLOUD_RUN.md)。下面命令仍为通用配置；本机尚未实跑 Docker 或部署云服务器。

将 `.env.example` 复制为 `.env`，需要远程访问时先设置足够长的随机 `WATCHER_TOKEN`。

```bash
docker compose up -d --build
docker compose logs -f --tail=100
```

默认仅发布 `127.0.0.1:8088`，数据库保存在 `watcher-data` 卷；删除容器不删除卷。**不要执行 `docker compose down -v`，那会删除历史数据卷。** 远程访问应增加 HTTPS 反向代理、认证与防火墙；不要把未设令牌的监听端口直接暴露到公网。令牌在页面右上角输入，仅存在本标签页会话，不进入 URL。

Docker 环境没有自带 Rust CLI，镜像默认走只读 HTTP 接口。采用外部 CLI 时，应由运行机器安装并配置其路径，不能直接把不兼容的宿主机二进制挂到镜像中。

## 排名口径与移动基准

星辰杯决赛的[官方评分规则](https://cannjudge.cn/public/ct_starcup_aiop_final/scoring-rules)规定：每个测试点得分为 `100 / (1 + log(用时 / TBest) / log(1.5))`，题目分为全部测试点得分的平均值，保留两位小数。TBest 是全场所有提交的历史最快用时；其他人刷新 TBest 会使未改动的提交降分，旧官方分与最新官方分不能直接取最大值。

该题有 15 个计分测试点，其中 5 个隐藏；公开接口没有它们的耗时或 TBest，无法精确重算所有历史提交。主榜显示**当前基准可确认最高分**和可确认提交覆盖，当前官方完整提交可作为本轮锚点；其他旧提交不沿用过去的分数、不按整体比例缩放、不只用 10 个公开点估算。覆盖不完整时，它是可确认范围内的结果，不能声称是该队全部历史的真实峰值。

每轮保存公开评分规则文本和校验结果，原始快照、证据和当时官方分保持不变。完整数据下重算也只选择一条完整提交，禁止逐测试点拼接。分数并列排名是看板参考排名；官方总榜未返回 rank 时仍显示“—”。

尚未核验规则的其他赛事保留以下原始观测口径，页面明确标注跨基准记录：

记 `s(i,p,t)` 为在时刻 t 观测到的队伍 i 的题目 p 官方完整成绩。合计为：

```text
ObservedPeak(i) = Σ_p weight(p) × max_t s(i,p,t)
```

单题最佳不是逐测试点取最小用时拼接；不同题目的最佳值可以来自不同时间，因此也不一定是该队在某个瞬间达到的总分。排序使用未四舍五入的 Decimal 分数，显示时才保留两位小数，峰值并列按 1、1、3 排。

源站若不提供官方 rank，页面保留“—”；按当前官方总分排出的只是“总分参考排名”，不会冒充官方并列规则。未知的当前题目分数不填 0；峰值合计仅覆盖实际观测到有效成绩的题目，并显示覆盖题数。

**历史记录限制**：旧官方峰值仅用于回看当时记录，不参与星辰杯当前基准主榜的比较。看板无法追回未观测或未公开的完整提交，也不能作为最终晋级承诺或判定选手故意藏分的依据。

自动隔离键包含赛事 ID、赛段、组别、人工规则 epoch、题目列表/权重及可见环境/测试元数据指纹。不可见的测试集或评分规则变更仍需人工更新 `rule_epoch`。发现成绩被主办方撤销时，不应直接删除证据；后续需增加显式失效/撤销标记再调整可用峰值。

## 测试与开发

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m compileall -q watcher
node --check web/app.js
```

本地验证记录见 [`docs/VALIDATION.md`](docs/VALIDATION.md)，下一步验收清单见 [`docs/NEXT_STEPS.md`](docs/NEXT_STEPS.md)，自动化修改约束见 [`AGENTS.md`](AGENTS.md)。

```text
watcher/core.py       规范化、身份/分数/时间校验、作用域与并列排名
watcher/store.py      完整快照、去重证据、双榜聚合、导出与备份
watcher/scoring.py    当前基准完整提交确认、重算校验与覆盖审计
watcher/source.py     公开 API / 外部 CLI 只读接入、分页与封榜检查
watcher/collector.py  轮询、失败记录、公开提交列表回补
watcher/app.py        只读 Web API、后台轮询、认证与静态文件
watcher/demo.py       明确隔离的 A/B 组合成演示
watcher/github_monitor.py  云端单轮采集、跨任务历史与限流等待保存
watcher/static_export.py   一致性只读视图、静态榜单/详情/证据导出
web/                 看板、队伍详情、原始证据、CSV 导出
```

没有官方历史接口或既有存档时，系统不能追回监控启动前已被覆盖的成绩，也不能知道从未公开的成绩。越早启动可靠的持续采集，未来的观测覆盖才越充分。
