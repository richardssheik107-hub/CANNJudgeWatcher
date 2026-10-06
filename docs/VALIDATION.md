# 验证记录 — 2026-10-06

## 用户请求清空活动历史并重新采集（验收进行中）

本次明确要求清空看板的历史数据并重新开始更新。操作使用新的活动数据库，旧数据退出看板、曲线和导出，保留可恢复备份，遵守禁止批量删除文件的约束。

- 重置前远端一致备份：`data/history-archive/20261006-210609/cloud-before.sqlite3`，26 份快照，SHA-256 与状态元数据一致，原状态提交 `d5bd487933c74643e245f312424223ce91e6837b`。
- 本地一致备份：同目录 `local-consistent.sqlite3`，33 份快照，SQLite quick_check 通过；本地无 8088/8089 监听服务。
- 手动 workflow 输入 `reset_history` 默认 false；定时采集仍继续追加。重置只在新一轮完整成功时更新活动状态，失败保留旧状态。
- 完整回归 **167 passed in 64.46s**，包括 34 项 monitor 测试；1 条已知第三方 AnyIO 弃用警告。首轮使用过长的 Windows 临时目录导致 4 项文件路径失败，缩短保留目录后全量通过。Python 编译、JavaScript 语法、actionlint 与 diff 检查通过。
- 无推送真实试采：`data/github-validation/history-reset/local-candidate-1/` 恢复旧 26 份后，在新库成功采集 **21:13:42（北京时间）** 的 1 份快照、21 队，规则核验成功；JSONL 恰好 1 行。9 条有效完整提交的当前分、当前基准确认值与新观测审计值一致，旧 83.1 未进入新榜。旧恢复库与线上页面未受试采影响。
- 云端部署与本地替换结果待本轮验收完成后填写。

## 最新基准与完整提交口径修复

此前主榜直接比较跨时间保存的官方 score；全场 TBest 变化后，旧高分不能直接作为今天同一基准下的最高分。本轮主榜改为“最新基准下可确认完整提交最佳”，旧官方峰值仅保留作历史审计。以下较早阶段的 83.1 等峰值记录是原始历史证据，不能沿用为修复后主榜值。

| 检查 | 已取得的证据 |
|---|---|
| 官方规则来源 | [赛事详情 API](https://cannjudge.cn/api/contests/6abcb2fa694b590c3c300a2e) 无登录 GET 返回 200，ID/slug 一致、规则启用；`scoring_rules_content` 与保存正文一致 |
| 官方规则页面 | [公开评分规则页](https://cannjudge.cn/public/ct_starcup_aiop_final/scoring-rules) 已核实；官方前端具有对应公开路由 |
| 计分与可见性 | 公式为 `100/(1+log(time/TBest)/log(1.5))`，15 个普通测试点平均并保留两位小数；代表提交模式为 `best`，公开完整 Pass 行为 10 个 Pass 点、5 个 Hidden 占位 |
| 评分来源回归 | 此阶段 source 回归 **13 项通过**，核验完整赛事详情、规则正文及作用域保护；完整集成结果待下一行验收 |
| 新真实快照 | 2026-10-06 **20:42:03（北京时间）**，`scoring_context.verified=true`，21 队、原作用域不变；此轮最高官方总分 91.12，Controlvector 官方总分 66.49 |
| 历史访问边界 | 匿名全局提交列表为 401，提交详情为 403；未绕过访问限制，回补仍关闭 |
| 完整回归、编译及前端语法 | **150 passed in 41.29s**；1 条已知第三方 AnyIO 弃用警告。Python 编译、`node --check`、`git diff --check` 均通过；33 项新增覆盖规则校验、移动基准、完整提交禁止拼点、Hidden 缺失、严格两位小数校准、原始证据不变 |
| 修复后的远端 CI / monitor / Pages | 修复提交 `81ddda7` 的 [CI 37466770407](https://github.com/richardssheik107-hub/CANNJudgeWatcher/actions/runs/37466770407) 通过 **150 项 / 5.50s**；[采集部署 37466866230](https://github.com/richardssheik107-hub/CANNJudgeWatcher/actions/runs/37466866230) 的 collect 与 deploy 均成功。实际 Pages 最近观测 **20:56:05**，共 26 份快照；线上 JavaScript 与本地修复文件 SHA-256 相同 |
| 修复后的主榜、详情、CSV 与覆盖标识 | 真实云端历史备份 25 份加新只读采集，得到 26 份静态预览；浏览器核验 21 行、10/15 公开点与部分覆盖。Controlvector 主分 **66.36**、旧官方审计 **83.1**、同基准差 **0.00**；最新依据与旧原始证据可分别查看。实际浏览器下载 CSV 21 行，已读取确认新旧分数和覆盖列正确分开 |
| 线上界面与历史完整性 | 已刷新实际 Pages 标签页，主标题和部分覆盖说明正确、21 行、26 快照、无页面错误，Controlvector **66.36 / 66.36**。线上完整 JSONL 的前 25 份与部署前云端 SQLite 原始快照逐字一致，新增第 26 份；首次观测仍为 **19:12:23**。实拍为 `data/github-validation/current-baseline-fix/online/overview.png` |

只有本轮官方完整成绩，或所有测试点性能与当前基准均可获得且公式复现官方分数的历史完整提交，才能进入当前基准最佳。公开信息不足的旧提交保留并显示部分覆盖，不能按可见点平均补齐隐藏分数。旧官方快照、提交证据和首次观测时间继续保留；“已观测集合全部可确认”不表示拥有开赛以来全部历史。源响应与规则证据保存在 Git 忽略的 `data/github-validation/current-baseline-fix/`。

下面各节记录此前阶段已完成的验证，包含真实部署及历史保留证据；它们不替代本轮修复的最终验收。

## GitHub 方案本地验收

新增 `watcher/static_export.py`、`watcher/github_monitor.py` 与 `Starcup monitor` 工作流，固定读取所选星辰杯决赛的公开数据，不使用账号或 Cookie。用户已确认全部公开，原仓库已公开；Pages 和计划采集开关已启用。两轮试采、随后两次公开采集/部署及网页访问已完成。

| 检查 | 结果 |
|---|---|
| 完整回归 | **117 passed in 31.95s**；1 条已知第三方 AnyIO 弃用警告 |
| 静态导出新增 17 项 | 单一只读事务、完整历史/证据校验、并发写入一致视图、501 条归档分页、敏感字段剔除、路径安全、失败保留产物 |
| GitHub 采集新增 17 项 | 真实本地 bare Git origin；首次初始化、两轮历史恢复、SHA 校验、失败保留历史、429 跨任务等待、普通推送竞态拒绝、90MiB 停止保护 |
| Python 编译 / JavaScript 语法 | 通过 |
| Actions 定义 | actionlint 1.7.12 通过；依赖 action 固定已核对的提交 SHA |
| 静态实库导出 | 14 份已观测完整快照、1 个真实作用域；94 个网站文件，输出目录保留 |
| 浏览器部署子路径 | `/CANNJudgeWatcher/` 下展示 21 队；搜索、排序、详情、14 点历史曲线、原始证据通过，error/warn 为 0 |
| 页面刷新失败 | 关闭本次静态预览服务后刷新报错，已有 21 行及 14 份快照仍保留 |

静态网站不依赖 FastAPI API 或浏览器直接访问赛事站点。验证请求均位于部署子路径内的 `static/` 和 `_data/`，实拍保存于 Git 忽略的 `data/github-validation/static-overview.jpg`。导出不会修改原库或覆盖已存在目标目录；测试通过 `tests/retain_tmp.py` 保留临时数据库并禁止递归清理。

计划周期为 10 分钟；GitHub 调度可能延迟或丢弃。网站显示最近发布及实际观测时间，而不是宣称正在实时采集。完整观测历史保存在独立状态分支，单个 SQLite 达到 90MiB 时停止，人工处理容量；不自动删减历史。

## 星辰杯决赛公开接口联调

### GitHub 云端实际验收

源码提交 `11c5c2b7e17b2216d21dbe6714a52a7a10558fa3` 已普通推送。对应 [CI 运行](https://github.com/richardssheik107-hub/CANNJudgeWatcher/actions/runs/37459691905) 为 SUCCESS，Ubuntu / Python 3.12.14 的测试为 **117 passed in 5.12s**，编译及 JavaScript 语法通过。

已有真实数据库通过只读一致备份初始化 `watcher-state`：21 份快照、无演示或人工导入记录、SQLite integrity_check=ok，首份时间仍为 2026-10-06 19:12:23（北京时间）。初始化状态提交为 `aa86c51c83b39027b228da5a9792a573df48380e`。

| 云端检查 | 结果 |
|---|---|
| [手动第 1 轮](https://github.com/richardssheik107-hub/CANNJudgeWatcher/actions/runs/37459744067) | SUCCESS，21 → 22 份快照；状态普通推送成功，源站无需登录可达 |
| [手动第 2 轮](https://github.com/richardssheik107-hub/CANNJudgeWatcher/actions/runs/37459860894) | SUCCESS，恢复 22 份后增至 23 份；状态普通推送成功 |
| 跨 runner 历史一致性 | 第二轮 JSONL 以第一轮完整 22 份的原始字节为前缀；最初时间及峰值证据保留 |
| 云端静态产物浏览器 | 下载第一轮 artifact 后通过真实 localhost 静态 HTTP 浏览；21 队、22 份快照、error/warn 为 0 |
| 静态浏览器实际导出 | CSV 21 队；JSONL 22 份完整快照及原始起始时间，文件下载后重新读取核对 |
| 公开发布和计划采集 | 此试采阶段暂未启用；随后已按用户确认公开并发布，见下方 |

两轮均 `state_pushed=true`、`failure_count=0`、`not_before=null`。状态提交依次为 `81cd2b57f3795444d2d5547050fbbb37e8ae4a7b` 和 `916a3fb4829f3d7d12f70a91ccb1ea0415e09ce9`。原首条峰值 83.1 的证据 ID 保持为 `3f491774ce129f616424fea7f1b9971d417778423b40c5a1202ebf67cf16dd2e`。报告与云端实拍位于 Git 忽略的 `data/github-validation/`。

### Pages 上线与本机停止后的云端更新

2026-10-06 用户明确确认“全部公开，不用新建仓库”。原仓库设为公开，Pages 发布源为 GitHub Actions，HTTPS 开启，两个运行变量均为 `true`；没有新建仓库。

| 检查 | 结果 |
|---|---|
| [首次公开采集及部署](https://github.com/richardssheik107-hub/CANNJudgeWatcher/actions/runs/37461811849) | collect / deploy 均 SUCCESS；23 → 24 份快照，20:14:25 完整观测，20:14:46 发布完成（北京时间） |
| 实际网站 HTTP | [Pages 地址](https://richardssheik107-hub.github.io/CANNJudgeWatcher/) 为 200；真实榜单、manifest、CSS、JS 和完整 JSONL 正常读取 |
| 实际网站浏览器 | 项目子路径渲染 21 行、24 份快照，无页面错误提示；搜索后准确显示 Controlvector 一队，实拍保存 |
| 历史保持 | 初始 19:12:23 时间及 Controlvector 83.1 旧峰值保持，完整 JSONL 可读取 |
| 本机停止 | `Stop-StarcupLive.ps1` 正常停止登记进程；8088、8089 均无监听，数据库、日志和进程记录保留 |
| [停止后的云端采集/发布](https://github.com/richardssheik107-hub/CANNJudgeWatcher/actions/runs/37462797020) | collect / deploy 均 SUCCESS；恢复 24 份并增至 25 份，证明采集不依赖本地服务 |
| 部署归档 | 两次部署成功后，只删除本次精确 ID 的 `github-pages` 归档；手动预览 artifact 与状态历史仍保留 |
| 定时开关 | workflow 为 active；计划每小时 7/17/27/37/47/57 分钟运行，实际计划触发与长期稳定性后续观察 |

真实公网 HTTP 报告及实拍保存在 Git 忽略的 `data/github-validation/pages-http-1/` 和 `pages-online.jpg`。公开仓库标准 runner 计算免费；artifact、网站和 Git 数据有容量限额。没有购买服务、保存 CANN 凭据或把本地密钥、运行日志上传。

### 本地接口与持续采集

使用无登录、无 Cookie 的只读 HTTP 请求读取用户指定的 [公开榜单](https://cannjudge.cn/public/ct_starcup_aiop_final/ranking)。精确 slug 为 `ct_starcup_aiop_final`，赛事标题为“中国电信星辰杯高校AI算子开发挑战赛-决赛”，赛事 ID 为 `6abcb2fa694b590c3c300a2e`，题目 ID 为 `6abcb4fd694b590c3c315c0e`。首次本地观测时间为 **2026-10-06 19:12:23（北京时间）**。

| 检查 | 结果 |
|---|---|
| 公开发现与首轮真实 `poll` | SUCCESS，21 支队伍；无需登录或 Cookie |
| 官方状态与有效成绩 | 9 支 Pass、9 支 Wrong Answer、2 支 Runtime Error、1 支 Compile Error；9 条官方 Pass 成绩进入已观测峰值 |
| 首轮官方总分前三 | 83.1、68.75、63.35；仅代表该次采集时公开的成绩 |
| 总榜官方 rank | 源站未返回；保留未知，参考排序不标为官方名次 |
| Hidden 测试点 | 官方 Pass 行有 10 个公开 Pass 点及 5 个 Hidden 占位；未公开用时、精度保留为 null，使用整条官方 score |
| 测试集版本元数据 | 按实际嵌套 `testcase_id` 提取稳定 ID、类型和基准字段；可见版本字段进入作用域指纹 |
| 回归测试 | 原有 72 项 + 11 项公开源回归，**83 passed**；仍有 1 条第三方 AnyIO 弃用警告 |
| 数据隔离与备份 | 真实库 `data/starcup-final.sqlite3` 与演示库分离；首轮数据已做 SQLite 一致性备份 |
| 本地持续采集入口 | `Start-StarcupLive.cmd` / `Stop-StarcupLive.cmd`；精确赛事配置，轮询等待 120 秒，公开历史列表回补关闭 |
| 自动轮询真实验收 | 首轮手动抓取后，后台连续两轮均 SUCCESS；自动轮次启动间隔 129.32 秒（120 秒等待加少量抖动），快照累计至 3 份 |
| 真实服务启停与历史保留 | 重复启动复用实例；停止后两个登记进程均退出、8088 释放；重新启动新增第 4 份快照，起始时间及已有证据不变 |
| 真实 HTTP / 浏览器 | 21 行、9 队有效峰值、详情、5 个 Hidden 未知值、历史与 JSONL 一致；无 DEMO 标记，控制台 error/warn 为 0 |
| 真实库一致性备份 | 在线 SQLite backup、源库 quick_check 及备份 integrity_check 均为 ok；报告、备份和实拍截图保存于 `data/live-validation/` |

后续抓取中，“南工工南”的公开总分由首轮 63.35 变为 63.83；网页及队伍历史同步反映变化，首次观测与此前快照仍保留。这里记录的是公开分数变化，不能仅据此判断为新提交或排除平台重算。

真实联调发现原版把官方 Pass 行内的 Hidden 占位判为失败，已修复为保留 Hidden 原始证据，并要求整条成绩的官方状态通过且 score 有效。公开测试点失败、未知状态、缺失状态或结构异常仍阻止进入峰值。新增脱敏公开结构 fixture 与回归覆盖，确认 83.1 采用官方整条 score，不由测试点猜分或求和。

真实接口响应与首轮榜单保存在 Git 忽略的 `data/live-validation/`。采集开始前未保存的历史成绩不能由当前榜单补回；多接口顺序读取也不保证平台瞬间原子一致。此结果仅验证所选星辰杯决赛的当前公开接口，不代表京津东北或其他赛段全部完成联调。Docker、云服务器、生产反向代理和连续 24 小时稳定性仍未验证。该阶段验收时本地修改尚未推送，导入提交的远端 CI 不作为该阶段修改的 CI 结论；后续推送结果另见上方阶段记录。

## 此前本地运行验收

环境：Windows、Python 3.11.9、FastAPI 0.128.2、Uvicorn 0.48.0、HTTPX 0.28.1、pytest 9.0.2。演示服务只监听 `127.0.0.1:8088`，采集器关闭，现有演示数据库按只读核验后复用。

| 检查 | 结果 |
|---|---|
| 原有 56 项测试 + 16 项运行回归 | **72 passed** |
| Python 编译、JavaScript 语法、差异空白检查 | 通过 |
| 真实 Uvicorn HTTP 验收 | 27 项检查通过，覆盖静态资源、健康、双榜、历史分页、证据、404/400/405、导出和令牌认证 |
| 4 个并发读取线程、100 次双榜请求 | 全部响应一致；本机中位 30.10ms、P95 38.92ms，仅为小型演示库检查 |
| 真实 localhost 浏览器交互 | A 组 11 行、B 组 12 行；切换、搜索、排序、刷新、详情、历史曲线和原始证据通过 |
| CSV、JSONL 实际浏览器下载 | CSV 12 支 B 组队伍、中文 UTF-8 与演示标记正确；JSONL 8 份完整演示快照 |
| 桌面默认窗口与 390px 手机窗口 | 渲染通过；手机页面无整体横向溢出，宽表可在表格内部滚动 |
| 浏览器控制台 error/warn | 0 |
| CLI 导出/导入、备份/恢复、重复 demo、重启读取 | 通过；2 个作用域、8 份快照、276 条证据，A/B 组 11/12 队 |
| SQLite 数据与外键检查 | 5 个验收数据库 integrity_check=ok、foreign_key_check 为空 |
| 模拟真实适配器的 7 种失败 | HTTP 错误、非 JSON、空发现、封榜、缺页、权限和限流后均保留原完整榜；429 的 7200 秒等待值保留 |
| Windows PowerShell 5.1 / `.cmd` 启停 | 首次启动、重复启动、停止和重启通过，重启后榜单及证据不变；未登记服务不会被停止 |
| SQLite 写锁造成启动超时 | 27.2 秒后明确失败，启动器及未监听子进程均退出、端口释放，8 份快照与完整性保留 |

该阶段最终复验为 **72 passed in 2.26s**，另有 1 条第三方 AnyIO 弃用警告。运行回归修复了无效配置下的启动就绪误报、异常关闭清理、同一应用二次启动、serve 重复初始化数据库和自定义演示库启动提示。启动脚本兼容 Windows PowerShell 5.1 在命令尾部追加空格的行为；核验时仅移除尾空白，身份记录仍保存完整原始命令，并核对可执行文件和创建时间。Windows 虚拟环境启动器及实际 Python 子进程均被登记，包含尚未监听的子进程失败清理。

本机浏览器经真实 HTTP 连接 Uvicorn，没有注入 fixture transport。CSV/JSONL 文件在浏览器下载后读取核验；桌面、手机与证据截图以及 HTTP 报告保存在 Git 忽略的 `data/local-validation/`。离线数据库验收脚本与完整记录保存在仓库旁 `.local-acceptance-data/`，不会作为真实赛事证据上传。

pytest 继续使用仓库外的保留产物插件，禁用内建临时目录清理；数据库、日志和测试目录全部保留。该阶段没有执行 CANNJudge 网络采集、Docker 或外部 CLI，不把这些本地结果解释为生产部署、24 小时稳定性或真实赛事字段验证；后续公开源联调单独记录在上方。

## 本次 Windows 导入复验

日期：2026-10-06。环境：Python 3.11、包内固定版本依赖（pytest 9.0.2），独立虚拟环境。

| 检查 | 结果 |
|---|---|
| 原包 SHA-256 清单 | 34 个内容文件全部匹配，共导入 35 个文件 |
| `python -m pytest -q` | **56 passed**，2.37 秒；1 条第三方 AnyIO 弃用警告 |
| `python -m compileall -q watcher` | 通过 |
| `node --check web/app.js` | 通过 |

为遵守本机禁止批量删除的工作区约束，测试使用仓库外的保留产物插件提供 `tmp_path`，通过 `PYTEST_ADDOPTS` 关闭内建 `tmpdir` 和缓存插件，并禁用第三方插件自动加载。测试进程中的 `shutil.rmtree` 被禁止；所有测试数据库和目录均保留。测试文件与断言未修改，检查覆盖仍为包内原有 56 项。

导入阶段没有运行真实采集、Docker、浏览器交互或外部 CLI 联调；以下浏览器结果及原始 `test-output.txt`、预览图片来自交付包的既有验证记录。导入提交的 GitHub CI 已通过；该阶段验收时后续本地修改尚未推送，不能沿用导入 CI 结果作为后续修改的远端验证。后续验收见上方记录。

## 交付包原有验证记录

| 检查 | 结果 |
|---|---|
| `python -m pytest -q` | **56 passed** |
| `python -m compileall -q watcher` | 通过 |
| `node --check web/app.js` | 通过 |
| FastAPI 读接口、令牌、405/404、证据与 JSONL | 自动化测试通过 |
| Chromium 桌面 1440px / 手机 390px | 完成页面渲染检查 |
| A/B 组切换、队伍搜索、详情、证据查看 | 浏览器交互通过；A 组 11 行、B 组 12 行合成数据 |
| 浏览器 JavaScript 未捕获错误 | 0 |

浏览器校验以 Playwright 注入 fixture transport，实际请求通过 FastAPI TestClient 执行。原因是当前浏览器环境阻止 localhost 网络导航。该检查验证真实前端与后端响应的配合，但**不是生产 HTTP/反向代理端到端验证**。演示界面包含明确 DEMO 标记，队伍名称均为合成名称。

## 回归覆盖

单题完整记录、不拼测试点、逐题峰值跨时间合计、缺失分数、失败/部分通过、同名与稳定 ID、改名、榜单消失、纯名次变化、同一提交重新评分、精确 Decimal 并列、规则版本/组别/赛段隔离、乱序导入不倒退当前、幂等/冲突、JSONL 迁移、SQLite 备份、公开历史列表独立归档与去重、敏感字段/源码剔除、缺页/重复/总数漂移/首页漂移、只读 GET、401/403/429/500/重定向失败、封榜不读取、失败保留旧榜；新增官方 Pass 与 Hidden 占位组合、未知测试点阻断、嵌套测试集版本隔离、无 Cookie 公开读取和原始证据往返。

## 尚未验证 / 不应对外宣称完成

- 交付包曾记录 CANNJudge 域名/公开入口访问失败；本机现已成功读取所选星辰杯决赛。京津东北及其他赛段的具体分组 ID、字段、排序与评分规则仍待逐项联调；不能将一个赛段的结果推广到所有赛事。
- Docker 镜像构建、生产 HTTP 访问、连续 24 小时稳定性、历史覆盖完整性和大规模性能尚未验证。
- 外部 Windust CLI 命令调用经过 mock 测试，没有在本机安装/登录后实测。没有读取或提交用户凭据。
- 原包与 `data/local-validation/` 的演示截图使用合成数据；真实赛事库和 `data/live-validation/` 单独保存，不能混用证据来源。

GitHub CI 定义包含基础测试与可选的手动公开接口探测。是否实际运行、通过，以 GitHub Actions 的运行记录为准；不能仅因为存在 workflow 文件就声称 CI 已通过。
