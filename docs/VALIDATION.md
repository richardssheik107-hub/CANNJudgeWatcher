# 验证记录 — 2026-10-06

## Cloudflare 自动更新与官方工具接入（已完成）

现行路径为 Cloudflare 免费十分钟 Cron → GitHub Actions 单轮公开采集和历史保存 → Pages 发布。两轮真实自动周期及持续打开页面的自动展示已验收；电脑和 Codex 无须常开。下面保留接入、失败定位和修复顺序的记录。

- 用户完成 Cloudflare 登录和官方 Wrangler OAuth 授权。Wrangler **4.147.0** 已核验目标账户，使用 account/user 读取、Worker 脚本写入和日志读取范围；未读取、复制或向 Cloudflare 上传本机现有 GitHub CLI 凭据。
- 已实际发布 `cannjudge-workflow-timer` 的引导版本 **e672b8b3-2c85-481d-ae27-6058cda17f6d**，使用仓库同一 `worker.mjs`，上传包 4.02 KiB / gzip 1.60 KiB，启动 1 ms。引导配置没有 Cron，没有 HTTP 路由，workers.dev 与预览 URL 关闭；用于接收随后由用户保存的 Secret，不能算自动调度已接通。
- 按用户指定的 [Cloudflare 官方 Agent Setup](https://developers.cloudflare.com/agent-setup/prompt.md) 安装 `cloudflare/skills` 的 **16 个**官方技能，固定来源提交 `41e0d19858946d18af9ee2c2feebbe2e11d829ff`，348 个文件哈希匹配；安装 staging 与证据全部保留，没有递归清理。用户级技能及配置不上传项目仓库。
- 官方 Cloudflare MCP 已添加为 `https://mcp.cloudflare.com/mcp`。用户明确批准所需 Worker 脚本读写、日志读取和观测读写权限；使用指定范围的 DCR OAuth 完成登录，**23:01:35** CLI 返回成功，后续只读检查确认 `auth_status=o_auth`。MCP 新工具须重启 Codex 后加载；本轮部署继续使用已授权 Wrangler，无须现在重启。
- **23:12:15** 再次核对：monitor 共 8 次成功运行，均为 workflow_dispatch，schedule 为 0；Pages 仍为 21 队、3 份快照，最近 **22:13:25**，历史起点仍 **21:17:00**。未新增人工补采或将人工记录当作自动恢复。
- GitHub 专用 fine-grained token 创建页已准备：仅 `CANNJudgeWatcher`、Actions 读写、必需 Metadata 读取、到期 **2026-11-05**；用户接手生成、复制并保存至生产 Worker 的 `GITHUB_DISPATCH_TOKEN` Secret。正式 `*/10` Cron 部署和两个连续无人操作周期的验收仍待该凭据接入后进行，当前未宣称自动刷新已修复。无凭据值的截图和安装报告保存在忽略目录 `data/github-validation/`。
- **23:20:46** 完成提交前验证：全量 **167 passed / 69.45s**，Python 编译和前端 JavaScript 语法检查通过；1 条已知第三方 Starlette/AnyIO 弃用警告。pytest 使用保留临时目录插件，不执行递归清理，证据目录为仓库外 `.upload-validation/cfs-231936884`。
- 随后用户确认专用令牌已生成并私密保存到 Cloudflare。Wrangler 只读取密钥列表，确认 `GITHUB_DISPATCH_TOKEN` 类型为 `secret_text`；仪表盘显示 **Value encrypted**。正式配置部署成功，版本 **439dcb20-adf2-438e-a2f7-1c2bb2b1a8c5**，上传 3.98 KiB / gzip 1.58 KiB，启动 4 ms，计划为 **`*/10 * * * *`**。**23:25** 仪表盘显示 Every 10 minutes、下次 UTC 15:30（北京时间 23:30）；已开始监听此版本的安全 Cron 日志，等待两轮真实自动采集与 Pages 更新，期间不人工 dispatch。
- **23:30:27** 收到首个真实 Cron：1 ms CPU / 2 ms wall time，安全报告为 `network-error`，GitHub 未产生新运行。官方原生 **workerd 1.20261001.1**、相同兼容日期下复现 `redirect: 'error'` 在请求构造时抛 TypeError；[官方运行时源码](https://github.com/cloudflare/workerd/blob/main/src/workerd/api/http.c%2B%2B#L447)只接受 follow/manual。改为 **manual**，所有 3xx 仍在状态校验处拒绝，不跟随携带凭据的跳转。默认裸 fetch 调用、AbortSignal、请求头和 payload 在真实运行时均通过，不凭合成 receiver 测试增加无关绑定修改。
- 修复通过 **23 项 Node 测试**及原生 workerd 完整 scheduled 路径 **6/6** 回归：204 接受；301/302/303/307/308 拒绝。globalOutbound 只路由纯本地 fixture，固定 GitHub 目标、一次 POST、输入 reset_history=false 均被校验，没有外网 dispatch 或真实凭据。修复已于约 **23:35** 发布，版本 **6af180d5-d3a4-4b10-bc24-b91e801cca7d**，上传 4.07 KiB / gzip 1.63 KiB，启动 2 ms；十分钟 Cron 不变，继续等待线上连续自动周期。
- 原生运行时回归已保存在 `integrations/cloudflare-scheduler/runtime-tests/`，直接 embed 实际源码而非镜像实现，internet 服务 allow=[]，只使用本地 fixture 和明确占位符。固定官方命令 `npx --yes workerd@1.20261001.1 test integrations/cloudflare-scheduler/runtime-tests/config.capnp` **6/6 通过**，已接入 CI；更新后的工作流 actionlint 通过。
- 修复后第一轮真实自动链路：Cloudflare **23:40:25** Cron → **23:40:28.807** GitHub 200 接受（2 ms CPU / 3047 ms wall time、1 请求、reset=false）→ [Actions 37489490941](https://github.com/richardssheik107-hub/CANNJudgeWatcher/actions/runs/37489490941) **23:40:28** 创建，collect / deploy 全成功，**23:41:08** 完成。Pages 21 队、快照 **3→4**，最近完整观测 **23:40:46.713571**，原观测起点和零失败数保持；JSONL 4 行。自 **23:27** 打开并保持可见的真实 Pages 标签页未重载、未点击检查按钮，**23:41** DOM 自行变为 4 快照 / 23:40:46，已核验前端自动展示。第二轮连续周期仍待验证；记录在忽略目录 `auto-refresh/cron-acceptance/`。
- 修复代码提交 `b2b4bbd` 的 [CI 37490085984](https://github.com/richardssheik107-hub/CANNJudgeWatcher/actions/runs/37490085984) 已在 Ubuntu 24.04 成功，于 **23:45:14** 完成：Python **167 passed**、Node **23/23**、官方原生 workerd **6/6**；编译和前端语法检查亦成功，人工 public-probe 未触发。
- 第二轮真实自动链路：同一 Worker 版本 **23:50:25** Cron → **23:50:27.402** GitHub 200 接受（1 ms CPU / 1659 ms wall time、1 请求、reset=false）→ [Actions 37490867533](https://github.com/richardssheik107-hub/CANNJudgeWatcher/actions/runs/37490867533) **23:50:27** 创建，collect / deploy 全成功，**23:51:17** 完成。Pages 21 队、快照 **4→5**、JSONL 5 行，最近完整观测 **23:50:47.466214**；活动 epoch 仍 **21:17:00.683856**，首次快照仍 **21:17:09.908611**，失败数 0。持续打开且可见的同一标签页再次自行变为 5 快照 / 23:50:47，期间未重载或点击检查按钮。
- 两轮均由真实 Cron 发起，未人工 dispatch。自动触发、完整采集、历史追加、Pages 发布和前端自动展示连续成功，完成验收后移除 monitor 原生 schedule，并将 collect 明确限制为 workflow_dispatch；Cloudflare 十分钟 Cron、手动入口、权限和 reset 默认 false 保留。专用 Secret 到期日 **2026-11-05**，到期前需更新；MCP 新工具重启 Codex 后加载，不影响已经运行的云端任务。

## 自动刷新修复继续排查

- 北京时间 **21:50:43** 对 monitor 执行一次禁用后启用，API 再次确认 active；21:57 检查仍无 schedule 记录。新 Actions execution policies 检查返回 0 条，未发现禁止 schedule 的策略。
- 用户提出算法修复前曾自动更新。对比初版 `11c5c2b` 与修复版 `81ddda7`：monitor.yml 是完全相同的 Git blob，触发器、条件、权限、并发与调用均不变；github_monitor.py 和 CI 亦零 diff，赛事配置仅增加规则核验。修复后的手动采集成功，未支持算法破坏触发器的推断。
- 本地一致备份有 33 份快照，19:12–20:21 的后段每 124–136 秒自动采集；本地 8088 进程于 20:21:49 停止。首次云初始化的 21 份与本地前 21 份时间/digest 完全相同，旧云库后来新增的 5 份逐一对应人工云采集。monitor 现有运行编号连续 1–7，均为 workflow_dispatch；另一自动工作流是 push CI，并不采集榜单。
- 增加独立 `Starcup schedule probe`，新 workflow ID、每 5 分钟只输出实际触发事件与 UTC 时间，无 job 条件、无仓库权限、无采集和发布，用于区别旧工作流登记与平台触发问题。探针成功本身不等于自动采集已恢复；实际结果待记录。
- 这轮完整回归 **167 passed / 60.68s**，编译、前端语法、actionlint 与 diff 检查通过。Cloudflare 免费定时触发器在忽略目录准备，用户已选择注册免费账号；尚未创建令牌或部署外部服务，须在用户完成账号注册后继续。
- Cloudflare 触发器经只读审查后纳入 `integrations/cloudflare-scheduler/`，**18 项离线 Node 测试**通过，并接入 CI。固定目标、禁止 reset、无公开 HTTP 入口、凭据及响应正文不进入日志；每次只请求一次，10 秒超时。Wrangler **4.147.0** 的真实 `deploy --dry-run` 成功，包 3.98 KiB / gzip 1.58 KiB，未进行云端部署或 GitHub dispatch。必需 Secret 已声明并核对官方配置支持；配置保持 workers_dev/preview_urls 关闭。
- 已打开 Cloudflare 注册页并交由用户完成账号注册、协议、人机和邮箱验证；本机未发现可用 Cloudflare 登录配置。当前仍须登录及配置仅此仓库的 Actions 写权限专用令牌后，才能完成两轮真实自动触发与 Pages 验收。22:04 检查独立探针和原 monitor 仍无 schedule 记录，尚未将自动恢复标记成功。
- Cloudflare 代码提交 `1b1f079` 的 [CI 37476055521](https://github.com/richardssheik107-hub/CANNJudgeWatcher/actions/runs/37476055521) 已成功，覆盖原项目测试及新增 18 项触发器测试。**22:11:52** 再查，独立探针和原 monitor 仍为零 schedule；诊断探针随后停用并确认 disabled_manually，保留文件及日志，不再消耗无目的周期。原采集工作流保持 active；新源站补采仍使用 reset_history=false，不能算外部定时验收。
- 临时补采 [37477109029](https://github.com/richardssheik107-hub/CANNJudgeWatcher/actions/runs/37477109029) 的 collect / deploy 均成功，网页与 JSONL 均为 **3 份**，首次仍 **21:17:09**，最近 **22:13:25**，21 支队伍；浏览器核验无页面错误。报告和实拍在 `data/github-validation/auto-refresh/latest-manual/`。这仍是维护时人工触发，Cloudflare 账号登录和专用 Secret 尚未接入，不能称为无人操作自动更新已解决。

## 定时更新未触发的排查

- 北京时间 **21:31:20** 检查时网页仍为 **21:17:09**，1 份快照。全仓库与 monitor 的 `event=schedule` 总数均为 **0**，已有成功运行均为 `workflow_dispatch`；不存在排队或失败的定时采集作业。这是触发层问题，尚未进入源站采集和 Pages 发布。
- 远端默认分支 `main` 的 workflow 含合法 cron；仓库公开、非 fork、未归档，Actions enabled / allowed all，workflow active，两个变量为 true；原 cron 提交账号与正常手动运行账号一致。未找到仓库配置或失活账号阻塞，不能确定 GitHub 调度内部的具体原因。官方状态页此时无未解决事故；这也不能证明该仓库调度正常。
- 尝试将分钟从 7/17/27/37/47/57 改为 **3/13/23/33/43/53**，保持十分钟计划间隔，用一次实际 cron 变更重新登记；只有随后真实 `event=schedule` 和新增页面快照才能认定恢复。没有进行禁用循环、常驻 runner 或重复重置。
- 改动后本地完整回归 **167 passed / 60.77s**，Python 编译、JavaScript 语法、actionlint 和 diff 检查通过；临时文件保留在短路径目录。
- 正常补采 [37471588558](https://github.com/richardssheik107-hub/CANNJudgeWatcher/actions/runs/37471588558) 明确 `reset_history=false`，collect 与 deploy 已成功；云数据库与实际 Pages 的 JSONL 均为 **2 份快照**，首次 **21:17:09** 不变，最新 **21:32:41**，元数据 epoch 仍为 **21:17:00**，没有旧历史回流。SHA-256、quick_check 与浏览器显示均通过，报告在 `data/github-validation/schedule-diagnosis/cloud-pages-37471588558.json`，实拍为同目录 `after-manual-update.png`。
- cron 变更提交 `c2ae181` 的 [CI 37472049171](https://github.com/richardssheik107-hub/CANNJudgeWatcher/actions/runs/37472049171) 已成功。截至 **21:38:12**，`event=schedule` 仍为 0；下一新计划点为 **21:43**。当前结论是手动补采恢复成功，自动调度仍未验收，不能宣称已解决。
- **21:46:54** 复查：新计划点 21:43 已过，仍为零 schedule 记录，最新 monitor 仍是成功的手动补采。一次 cron 重新登记未证实恢复；可定位为未生成定时触发事件，GitHub 内部原因不由仓库 API 提供。本次检查保留这一未解决结论，没有把手动更新冒充自动恢复。备用路径可用免费外部定时器调用现有 workflow dispatch，需要额外账号和仅此仓库的 Actions 写权限令牌，不需要新仓库或本机常开；本轮未创建外部服务。

## 用户请求清空活动历史并重新采集（已完成）

本次明确要求清空看板的历史数据并重新开始更新。操作使用新的活动数据库，旧数据退出看板、曲线和导出，保留可恢复备份，遵守禁止批量删除文件的约束。

- 重置前远端一致备份：`data/history-archive/20261006-210609/cloud-before.sqlite3`，26 份快照，SHA-256 与状态元数据一致，原状态提交 `d5bd487933c74643e245f312424223ce91e6837b`。
- 本地一致备份：同目录 `local-consistent.sqlite3`，33 份快照，SQLite quick_check 通过；本地无 8088/8089 监听服务。
- 手动 workflow 输入 `reset_history` 默认 false；定时采集仍继续追加。重置只在新一轮完整成功时更新活动状态，失败保留旧状态。
- 完整回归 **167 passed in 64.46s**，包括 34 项 monitor 测试；1 条已知第三方 AnyIO 弃用警告。首轮使用过长的 Windows 临时目录导致 4 项文件路径失败，缩短保留目录后全量通过。Python 编译、JavaScript 语法、actionlint 与 diff 检查通过。
- 无推送真实试采：`data/github-validation/history-reset/local-candidate-1/` 恢复旧 26 份后，在新库成功采集 **21:13:42（北京时间）** 的 1 份快照、21 队，规则核验成功；JSONL 恰好 1 行。9 条有效完整提交的当前分、当前基准确认值与新观测审计值一致，旧 83.1 未进入新榜。旧恢复库与线上页面未受试采影响。
- 重置代码 `554ec3a` 的 [CI 37469452854](https://github.com/richardssheik107-hub/CANNJudgeWatcher/actions/runs/37469452854) 成功，**167 passed / 6.20s**；[重置采集与部署 37469547229](https://github.com/richardssheik107-hub/CANNJudgeWatcher/actions/runs/37469547229) 的 collect / deploy 均成功。报告明确 `reset_history=true`、旧 26 份变为新 1 份、状态推送及网站就绪成功。
- 新状态提交 `78eb35774f7391ef42ed99dc465a8fc7760d983a` 的父提交仍为原 `d5bd487`，无强推。元数据记录重置起点 **21:17:00**，首份完整快照 **21:17:09.908611（北京时间）**；SHA-256、SQLite quick_check、单一作用域及零导入记录核验通过。21 队、9 条有效完整提交，主榜当前分与新观测确认值一致：南工工南 **93.60**、Controlvector **65.41**、All in AI **55.25**。
- 实际 Pages 的 JSONL 仅 1 行，首次/最近观测均为 **21:17:09**，无旧记录，线上 JavaScript 与本地一致。浏览器已打开新网页，显示 21 队、1 份快照与新起点；实拍 `data/github-validation/history-reset/online/overview.png`。真实 API 与导出核验证据保存在同目录及 `cloud-reset-1/`。
- 本地旧主库、WAL、SHM 按三个明确路径逐个移入备份目录，活动 `data/starcup-final.sqlite3` 复制已校验的新云端一致数据库；哈希相同、quick_check 通过，快照与运行记录各 1 份，首次证据时间为新起点。无本地采集服务运行；云端计划采集和 Pages 开关仍为 true，后续定时输入默认不重置。

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
