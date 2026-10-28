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

## 当前比赛的公开接口

当前唯一监控目标为 [VarLenNdRotaryPosEmb](https://cannjudge.cn/public/op_challenge_jingdong_final/varlenndrotaryposemb/ranking?page=1&size=20)。2026-10-28 已真实读取以下无登录 GET 接口：

```text
GET /api/groups/public
GET /api/contests/group/{group_id}
GET /api/contests/6adac8e13ff2fef7e8929a9f
GET /api/problems/6adb272d1dac5d235bd66d0b
GET /api/problems/6adb272d1dac5d235bd66d0b/ranking?page=1&size=100
```

题目榜直接给出 score、rank、稳定队伍/用户 ID、submission_id 和 result，以及同一响应的 testcases/TBest。当前采用单题榜分数与名次，不借用赛事总榜，不按昵称合并队伍。题目元数据为 `ranking_submission_mode=latest`、`score_mode=1`、`use_baseline=false`。

采集器每轮新 GET 并请求 `Cache-Control: no-cache`；这不能证明官方后端内部缓存即时更新。官方前端直接展示 API 的 score，不在浏览器重算。公开的[平台文档仓](https://gitcode.com/fuyangchenghu/cann-judge)只有文档，没有后端实现，不能声称已审查生产服务重评分代码。

## 当前基准与历史最佳

平台[计分说明](https://raw.gitcode.com/fuyangchenghu/cann-judge/raw/master/docs/%E5%8A%9F%E8%83%BD%E5%8F%82%E8%80%83/05-%E6%8E%92%E8%A1%8C%E6%A6%9C%E4%B8%8E%E8%AE%A1%E5%88%86.md)描述按全场最优耗时赋分；当前[赛事规则页](https://cannjudge.cn/public/op_challenge_jingdong_final/scoring-rules)正文没有可用于校准的分数公式。通用文档不能直接当作本赛已核验公式。

历史最佳必须对每条已观测完整有效提交采用最新 TBest 重新计分，再选最大值。基准变化不会新建作用域，也不会冻结旧分；最佳值和胜出的完整提交都可能变化。官方原始分不重写，保留审计证据。规则已核验、全点完整且本轮官方成绩一致时才允许公式重算；若出现矛盾，则暂停该题本轮全部同基准锚点及历史最佳认证，下一轮一致后恢复。

当前 15 个测试点只有 5 个可见、10 个 Hidden。公开历史列表此次返回 401，提交详情和管理导出需要相应权限；没有公开的指定历史提交当前重算分接口。不能猜隐藏耗时、用可见点均值替代完整分、缩放旧分或绕过权限。缺少依据时显示未知，不能以当前分或旧时最高分兜底。

当前取证文件、来源 URL、时间和 SHA256 保存在 Git 忽略的 `data/new-contest-validation/`、`data/current-basis-audit-20261028/`。真实样本中未发生可核对的可见基准刷新事件；移动基准降分与冲突恢复由隔离接口回归验证，生产采集/发布另有运行证据，二者不混称。
