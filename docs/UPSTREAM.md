# 来源、复用方式与许可边界

核对日期：2026-10-06。该仓库最初为空，非 KaranocaVe 项目的 GitHub fork。

| 项目 | 核对版本 | 本版采用方式 | 不直接采用的部分 |
|---|---|---|---|
| [KaranocaVe/CANNJudgeWatcher](https://github.com/KaranocaVe/CANNJudgeWatcher) | `9fd0ce770ce09dd9f1cd8401508567c0297050f4` | 参考公开赛事发现、题目榜单分页、快照/历史/采集健康架构及公开接口协议 | 未找到明确 LICENSE，不整仓复制；其逐测试点最佳不能当单题完整最佳；纯名次变化的历史需要额外保留 |
| [WindustH/cannjudge-cli](https://github.com/WindustH/cannjudge-cli) | `680717f1217f042e6da1f982268d6397ff300ce6` | **实际外部进程接入**：`--no-cache --json api get`；由既有 CLI 管理授权凭据与 HTTP | 不复制其源码，不使用提交/自动换号；需要运行机器已安装相应 CLI |
| [spdc-elm/cannjudge-cli](https://github.com/spdc-elm/cannjudge-cli) | `8248b629ef07bde796a642d5a6c21d0abc28e1eb` | 核对公开 API、历史列表参数、封榜边界与赛事解析约定 | 当前 `ranking --json` 输出只保留 name 等展示字段，丢失稳定 team/user ID；不将该输出直接灌入归档核心 |
| [yunhanbb/huawei-ranking-tracker](https://github.com/yunhanbb/huawei-ranking-tracker) | README 在本轮之前已核对 | 参考采集与展示分离、可导出历史的工作方式 | 华为云比赛不是 CANNJudge；其每小时采集/静态发布不是本版实时采集后端，未复制源码或原站接口 |
| [Jiuxiao-yunwai/CannJudge-Better](https://github.com/Jiuxiao-yunwai/CannJudge-Better) | README 声明 MIT | 参考测试点结果便捷查看、复制/导出需求 | 不采用其自定义性能得分作为赛事官方分，不把浏览器临时状态作为历史库；本版未复制其源码 |

**复用级别必须说清楚**：外部 CLI 是实际运行时集成；其他上述条目主要是接口核对或架构参考，不是已 vendor 的代码。新增代码主要负责这些项目未直接满足的历史完整成绩聚合与审计。没有将不明许可代码换一个 MIT 标题重新发布。

运行时使用 FastAPI、Uvicorn、HTTPX 与 Python 标准库 SQLite；前端为轻量静态 HTML/CSS/JavaScript，无 CDN 或外部脚本依赖。依赖包的许可由其各自项目保留。后续直接引入第三方源码前，需要核实具体文件的许可证、保留声明，并记录提交 SHA。

## 核对的公开接口契约（仍需实际站点验收）

```text
GET /api/groups/public
GET /api/contests/group/{group_id}
GET /api/problems/{problem_id}
GET /api/problems/{problem_id}/ranking?page=1&size=100
GET /api/submissions/contest/{contest_id}/stats
GET /api/submissions/global/list?contestId=...&withCount=1&skip=0&limit=100
```

相关代码依据：

- [Watcher CannJudgeClient.java](https://github.com/KaranocaVe/CANNJudgeWatcher/blob/9fd0ce770ce09dd9f1cd8401508567c0297050f4/src/main/java/cn/cannjudge/watcher/source/CannJudgeClient.java)
- [Watcher RowNormalizer.java](https://github.com/KaranocaVe/CANNJudgeWatcher/blob/9fd0ce770ce09dd9f1cd8401508567c0297050f4/src/main/java/cn/cannjudge/watcher/source/RowNormalizer.java)
- [spdc CLI 排行榜/提交列表实现](https://github.com/spdc-elm/cannjudge-cli/blob/8248b629ef07bde796a642d5a6c21d0abc28e1eb/src/cli.ts)
- [Windust CLI README](https://github.com/WindustH/cannjudge-cli/blob/680717f1217f042e6da1f982268d6397ff300ce6/README.md)

`score`、`rank`、`team._id`、`user._id` 等字段必须从实际响应取得。缺字段时保留未知或拒绝发布，不把 README 的例子当作当日真实接口已通过的证明。
