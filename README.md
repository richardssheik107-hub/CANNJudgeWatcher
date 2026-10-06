# CANNJudgeWatcher · Observed Peak

**官方当前榜 + 当前基准下可确认的历史完整提交成绩。** 星辰杯决赛使用最新一轮基准比较，避免把旧基准下的高分误当成今天的峰值；其他尚未核验评分规则的赛事仅展示原始官方分数记录。

> [在线榜单](https://richardssheik107-hub.github.io/CANNJudgeWatcher/) 已上线。Cloudflare 免费 Cron 每 10 分钟触发 GitHub Actions 采集、保存历史并发布 Pages；2026-10-06 23:40 / 23:50 连续两轮自动更新与页面自行刷新均已验证，电脑和 Codex 无须持续运行。21 支队伍，按用户请求重置后的活动历史从 2026-10-06 21:17:09（北京时间）开始；旧数据仅保留在恢复备份及 Git 先前提交中，不进入当前看板与导出。回归与部署证据见 [验证记录](docs/VALIDATION.md)。仓库与成绩历史按用户确认公开，演示数据与真实赛事数据分库保存。

> 本仓库包含 v0.1.0 交付包的主体源码、静态前端、测试、部署配置和演示预览。导入记录与后续验收步骤见 [交付说明](docs/DELIVERY.md)。

## 已实现

- **同基准比较**：星辰杯决赛以最新完整快照的官方提交分数为已确认值；仅在所有计分测试点耗时、TBest 和规则均公开且与当前官方分一致时，才重算旧完整提交。无法重算的历史提交明确标记，原始旧分另保留为审计记录。
- **双榜对照**：当前官方总分与峰值合计、排名差异、分数差值、题目覆盖、数据新鲜度。队伍离开当前榜后，其历史证据仍保留。
- **历史不被覆盖**：压缩保存每轮完整榜单快照，按完整成绩行去重索引；纯名次变化、同一提交重新评分、队伍改名都可追踪。
- **公开提交列表归档**：每轮默认读取最多 2 页、每页 100 条；另提供可控页数的 `backfill`。保留平台允许读取的记录，不请求选手源码。未公开 score 的提交不会被倒推成分数。
- **公开赛事发现**：标题包含“星辰杯”或同时包含“京津”“东北”时入选。来自公开元数据的赛事/题目 ID，不猜测地区赛 URL、分组编号或数组位置。
- **完整性保护**：分页总数、重复队伍、缺页、首页漂移、JSON 结构与身份校验；不完整的新一轮不会覆盖上一份完整榜单。HTTP 429 按 Retry-After 等待，轮询失败退避。
- **部署与导出**：FastAPI + SQLite + 静态前端；CSV、快照 JSONL、SQLite 一致性备份；Docker Compose；可选 Bearer 访问令牌；所有网页 API 只读。
- **免费云端托管路径**：Cloudflare Cron 每 10 分钟触发 Actions 读取所选星辰杯公开榜，独立 `watcher-state` 分支持久保存历史，Pages 展示静态快照。恢复和校验旧历史后才采集，推送历史成功后才发布页面；使用公开仓库，不依赖本机开机。

## GitHub 定时采集与网页

用户已确认全部公开，直接使用当前仓库。Cloudflare 定时触发、Actions 采集、跨任务历史保留、Pages 发布和页面自动展示均通过连续两轮真实验收。本机采集已停止；原生 GitHub schedule 已移除，保留 workflow_dispatch 手动入口。具体设置、费用条件、首次历史初始化与故障处理见 [GITHUB_RUN.md](docs/GITHUB_RUN.md)。公开仓库标准 Actions runner 无计算分钟费用，使用 GitHub 免费 Pages 地址和 Cloudflare Workers Free。云端队列可能延迟，不保证精确到分钟。专用 GitHub 令牌到期前须更新 Worker Secret，本次令牌到期日为 **2026-11-05**。

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

## 接入真实赛事

本机已核验用户提供的 [星辰杯决赛公开榜](https://cannjudge.cn/public/ct_starcup_aiop_final/ranking)。精确配置为 [`config/monitor.starcup-final.json`](config/monitor.starcup-final.json)，不发送登录 Cookie，轮询等待设为 120 秒，公开提交列表回补暂时关闭。Windows 可双击 `scripts\Start-StarcupLive.cmd` 启动网页和持续采集，双击 `scripts\Stop-StarcupLive.cmd` 停止；数据库为 `data/starcup-final.sqlite3`，运行方式见 [本地运行说明](docs/LOCAL_RUN.md)。本地运行期间电脑须保持开机且不休眠；GitHub 方案启用后由云端独立计划采集，无需本机常开。

首轮官方总分前三为 83.1、68.75、63.35。源站总榜未返回官方 rank，页面保留“—”并展示单独标注的总分参考排名。官方 Pass 成绩中的 Hidden 测试点是未公开结果占位：保留原值并使用官方给出的整条 score，不猜测其用时、精度或分数，也不从测试点拼出成绩。历史峰值只覆盖本地实际观测到的记录，不能追回采集前已经被覆盖的分数。

需要接入其他赛事时，先发现并核验其字段，再运行以下通用流程：

```bash
# 1. 查看实际公开赛事 ID、slug、标题、赛期和命中的筛选规则
python -m watcher discover

# 2. 首轮只读采集；只有完整通过校验的赛事快照才会发布
python -m watcher poll

# 3. 启动网页及持续采集（前台运行；常驻请用 Docker 或系统服务）
python -m watcher serve --poll
```

检查页面底部的采集运行记录。若接口不匹配、未开放、封榜、限流或网络失败，保留旧榜，不显示伪造的实时数据。`serve` 不带 `--poll` 时只浏览已有快照。

配置文件是 [`config/monitor.json`](config/monitor.json)。初次真实部署须确认 `discover` 选中了正确赛段；确认后推荐将关键词筛选替换为实际返回的精确 slug，例如 `{"slug":"实际发现的比赛slug"}`。不得自行猜测 B 组或地区赛 slug。

默认每轮完成后等待 120 秒并加入少量抖动，请求之间至少间隔 1 秒；实际刷新周期还包括采集耗时。源站的限流等待优先，不承诺每次提交都能捕获。`include_ended` 控制是否读取已结束的公开榜单。需要更精确的范围时使用明确 slug，而不是监控全部历史赛段。

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
