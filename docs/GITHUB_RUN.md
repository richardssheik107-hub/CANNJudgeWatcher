# 使用 GitHub 自动采集和展示星辰杯榜单

本方案由 GitHub Actions 每次运行一轮公开采集，将完整 SQLite 历史保存到 `watcher-state` 分支，再生成可供 GitHub Pages 展示的静态看板。启用并通过云端验收后，采集不依赖自己的电脑开机，也不需要常驻进程、服务器或 CANN 账号密码。

固定比赛是 [星辰杯决赛公开榜](https://cannjudge.cn/public/ct_starcup_aiop_final/ranking)。程序使用 `config/monitor.starcup-final.json`：精确匹配 `ct_starcup_aiop_final`、`cookie_env` 为空、公开提交列表回补关闭。只读取公开榜单、题目元信息及完整赛事详情中的评分规则，不执行提交、登录或选手源码抓取。

**当前交付状态：用户已确认全部公开，直接使用当前仓库。定时采集和 Pages 发布开关均为 true；手动云端采集、历史恢复与部署成功，自动触发尚未通过验收。** 2026-10-06 21:31（北京时间）检查发现全仓库 `event=schedule` 运行数量为 0，不能把已启用配置或手动成功视为自动更新已验证。已安排正常补采，并尝试一次 cron 分钟变更；必须以实际 schedule 运行和新增网页快照确认恢复，具体结果见 [验证记录](VALIDATION.md)。

在线地址：[CANNJudgeWatcher 看板](https://richardssheik107-hub.github.io/CANNJudgeWatcher/)。无需本机开机或输入 CANN 账号密码。

## 免费条件与运行开关

公开仓库使用标准 GitHub 托管 runner 时，Actions 运行时间免费；私有仓库按账户套餐使用分钟数与存储额度，超出额度可能收费或停止运行。当前账户剩余额度尚未核验，因此私有阶段只进行有限的手动试运行，不开启循环任务。[GitHub Actions 计费说明](https://docs.github.com/en/billing/concepts/product-billing/github-actions)

GitHub Free 的 Pages 适用于公开仓库；私有仓库 Pages 需要 Pro、Team 或相应企业套餐。[Pages 可用范围](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages)

公开仓库意味着代码、`watcher-state` 的公开成绩历史及提交记录都可以被访问。本次已获得用户“全部公开，不用新建仓库”的明确确认，并将原仓库设为公开；没有创建新仓库。

在仓库 `Settings → Secrets and variables → Actions → Variables` 配置以下变量，值须为小写 `true`：

| 仓库状态／变量 | 实际行为 |
| --- | --- |
| 私有仓库 | 允许 `workflow_dispatch` 手动试运行；计划采集和 Pages 发布均关闭 |
| 公开仓库，`ENABLE_GITHUB_MONITOR=true` | 启用十分钟计划采集 |
| 公开仓库，`ENABLE_GITHUB_PAGES=true` | 成功保存本轮状态后，允许发布生成的静态页面 |
| 变量为空或不等于 `true` | 对应计划／页面开关关闭；手动试运行仍可以使用 |

两个变量分别控制采集与发布。只开启 Pages 不会开启定时采集，只开启采集则不会发布网页。手动运行仍可能消耗私有仓库额度。

## 一次性迁入本机真实历史

首次初始化必须由操作人员显式指定真实数据库。缺少 `watcher-state` 时，后续采集会停止，不会默默创建空库并丢失既有历史。已有状态分支时，初始化也会停止，不能重复播种或替换它。

在包含本轮代码的仓库根目录运行下例。先确认 Git 的 `origin` 指向目标仓库、当前 Git 登录具有写入权限；路径存在时换一个新编号，不删除旧目录。本机可使用 `..\.validation-venv\Scripts\python.exe`，其他环境替换为自己的 Python：

```powershell
& '..\.validation-venv\Scripts\python.exe' -m watcher.github_monitor `
  --work-dir 'data\gh-init-1' `
  --site-output 'data\gh-site-1' `
  --poll-seconds 600 `
  --initialize `
  --seed 'data\starcup-final.sqlite3' `
  --push-state
```

初始化不会联系 CANN 源站。它通过只读 SQLite backup API 生成一致备份，因此本地原服务可以继续运行；Git 的远端检查与可选状态推送仍需联网。输入必须完整、无演示数据、无人工 JSONL 导入标记，并且所有作用域都属于该比赛。运行后的本地原库、备份和静态页面都会保留。

`watcher-state` 只含三个文件：

| 文件 | 作用 |
| --- | --- |
| `starcup-final.sqlite3` | 榜单快照、完整成绩证据、公开归档及运行记录的一致备份 |
| `state.json` | 数据库 SHA256、赛事标识、失败次数、下一次允许采集时间 |
| `README.md` | 状态分支用途与成绩口径说明 |

代码仍在 `main`，状态分支不包含源码工作目录、账号或虚拟环境。每轮以远端最新状态提交为父提交，用普通 Git push 更新分支；不使用强制推送。哈希不符、数据库损坏、来源不符或推送冲突都会停止当前发布。

省略 `--push-state` 可以生成本地候选提交和预览以供审阅，此时报告中的 `site_ready` 为 `false`，不会修改远端。不要手动改写数据库或元状态来绕过初始化、身份或完整性校验。

## 按操作人员请求重新开始

需要清空当前看板的观测历史时，在手动运行 `Starcup monitor` 时勾选 `reset_history`。默认值为 false，定时任务不会重置。CLI 对应参数是 `--reset-history`，不能与 `--initialize` 或 `--seed` 同用。

程序先恢复并校验旧状态，再用一个新的空数据库采集最新公开榜。只有完整、非空的一轮采集成功，才通过普通 Git 提交替换活动数据库并发布网页；限流、失败或缺页会保留原状态。之后普通任务继续追加新历史。重置报告保留重置前后快照数量，`state.json` 保存新的观测起点。

重置后的看板、队伍曲线及 JSONL 导出只包含新一轮开始后的数据。旧数据库保留在本地备份和状态分支的旧 Git 提交中，可恢复；本操作不批量删除文件，不清除 Git 提交记录，也不改变源站比赛成绩。

## 先手动验证，再启用计划和页面

1. 把本轮代码及 `.github/workflows/monitor.yml` 放到默认分支，并完成上面的显式初始化。仓库须允许 Actions 使用工作流所声明的 `contents: write` 权限保存状态；授权来自 GitHub 提供的工作流令牌，无须保存 CANN 密码。
2. 打开 `Actions → Starcup monitor → Run workflow`，选择默认分支。先保持两个运行变量关闭。
3. 查看运行摘要中的 `status`、`snapshot_count_before`、`snapshot_count_after` 和 `state_pushed`。完整采集应为 `SUCCESS`，新快照数增加；`state_pushed=true` 表示历史已保存，但不代表 Pages 已上线。
4. 再手动运行一次。核对第二轮恢复了第一轮的快照、原首份观测时间及峰值证据。手动成功试运行会提供 `starcup-preview-运行ID` 预览 artifact，保留一天。
5. 确认公开范围及免费条件后，将仓库设为公开；在 `Settings → Pages → Build and deployment` 将发布来源设为 `GitHub Actions`，再开启两个变量。
6. 手动运行一次发布，打开 `deploy` 作业实际返回的 Pages 地址。核对完整榜单、队伍详情、原始成绩证据、CSV 和 JSONL 导出，以及项目子路径下的资源加载。随后核验至少两次计划任务持续恢复和增加历史。

只有源站真实采集、跨 runner 恢复和网页访问均通过，才能宣布在线运行完成。确定云端正常后可用本地 `Stop-StarcupLive.cmd` 停止本机采集；迁入后继续产生的本地新历史不会自动合并到云端。

## 十分钟更新及失败行为

工作流在每小时第 3、13、23、33、43、53 分钟计划运行，使用默认分支上的代码。这次分钟变更用于尝试重新登记调度，不能单独证明自动触发已恢复。GitHub 调度可能延迟，繁忙时甚至丢弃排队任务；公开仓库无活动 60 天会停用定时工作流。当前计划不能承诺严格每十分钟捕获一次成绩，更不能捕获源站每次瞬间变化。[官方定时规则](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)

排查时先查看 Actions 的触发事件：没有 `event=schedule` 的运行表示尚未进入采集作业；有运行但失败则检查 collect 的报告、源站状态与退避；collect 成功且网页未更新则检查 deploy。正常手动补采必须保持 `reset_history=false`，避免再次清空历史。仅有绿色手动运行不能关闭定时故障。

每次 runner 都从远端状态恢复，运行最多一轮，然后结束。固定并发组避免两个工作流同时修改状态，SQLite 快照和页面导出也使用一致视图。页面每分钟重新读取已发布文件，只刷新展示；采集频率由 Actions 决定。

| 报告状态 | 行为 |
| --- | --- |
| `INITIALIZED` | 显式迁入种子，未访问比赛 |
| `SUCCESS` | 完整新快照已通过校验，保存历史后可发布 |
| `SKIPPED` | 本轮没有新快照，保留已有榜单和运行记录 |
| `FAILED`／`PARTIAL` | 保留上一份完整榜单，保存本轮运行记录及失败退避；页面可显示旧榜与错误记录 |
| `WAITING` | 上轮持久等待时间尚未到；不采集、不提交状态、不发布新页面 |
| `ERROR` | 完整性、容量或 Git 操作失败；保留已发布页面，本轮产物留在新的本地工作目录供检查 |

429 的 `Retry-After` 和连续失败次数保存在 `state.json`，因此更换 runner 不会重置等待。首次失败的常规等待为 20 分钟，继续失败增长至 60 分钟；源站要求更长等待时优先遵守。成功后清除失败次数。Actions 作业显示绿色也可能对应已妥善保存旧榜的 `FAILED` 或 `WAITING`，须查看摘要中的采集状态和页面观测时间。

只有状态推送成功，程序才返回 `site_ready=true`；只有公开仓库且 Pages 开关开启，工作流才发布网页。普通推送被拒绝时不会覆盖远端新状态，也不会把未保存历史的候选网页部署出去。

## 历史、容量和 artifact 保留

原生 schedule 持续不触发时，可使用 [`integrations/cloudflare-scheduler/`](../integrations/cloudflare-scheduler/README.md) 中的免费 Cloudflare Cron 触发器。每 10 分钟向固定仓库的 `monitor.yml` 发送 `workflow_dispatch`，输入始终为 `reset_history=false`，采集和 Pages 发布仍复用现有工作流。源码和离线测试已准备；只有 Cloudflare 日志、对应 Actions 采集部署及网页时间连续两轮均增加，才能确认此路径自动运行。账号注册及专用令牌配置尚需用户完成，不能把离线通过当作已部署。

静态页面保留完整当前榜及可追溯成绩证据；队伍图表默认加载最近 200 份快照，更早的完整快照由页面 JSONL 导出提供。星辰杯主榜从全部已保存的候选中，只比较当前基准下可确认的完整提交成绩，并显示可确认覆盖；本轮官方完整成绩可作锚点，旧提交缺少隐藏测试点等必要数据时不能重算，也不沿用旧分。历史审计仍保留原始官方分数和旧峰值。公开总榜没有官方名次时继续显示未知值，参考排名和可确认最高分不会被称为官方最终榜，已观测候选的完整覆盖也不表示覆盖开赛以来全部提交。

数据库达到 **90 MiB** 时明确停采；每轮结束后的备份也会再次检查。这个保护早于 GitHub 对大于 **100 MiB** 普通文件的阻止规则。程序不会自动删除历史、压缩掉证据、切换到空库或重写状态分支来腾空间。[GitHub 文件和仓库大小规则](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)

此方案适合当前小规模、有限赛期的观察，不能承诺无限历史永久免费保存。除了当前 SQLite 文件，还须关注状态分支的累积 Git 对象、静态导出大小和 Actions 存储用量。接近限制时先保存独立一致备份，再由操作人员规划存储迁移；不要批量删除文件、状态提交或历史证据。

手动预览和 Pages 部署 artifact 均设置为保留 **一天**；数据库持久状态在 Git 分支，不依赖 artifact 或缓存存活。Pages 部署成功后，工作流只按上传步骤返回的**本次 artifact 精确 ID**删除本次 `github-pages` 部署归档，并再次核验归档名和所属运行 ID。它不批量清理其他运行、不删除预览 artifact，也不删除 `watcher-state` 或成绩记录；部署失败则保留归档至平台保留期到期。

需要恢复时，先保存当前状态的独立备份并核验 SHA256 和 SQLite 完整性。不要将恢复操作伪装为首次初始化，不把演示库或人工导入库替换成正式云端状态。恢复方案应保证原证据可审计且不会丢失未迁出的历史。
