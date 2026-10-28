# GitHub 自动监控京津东北决赛单题

当前目标：[VarLenNdRotaryPosEmb 排行榜](https://cannjudge.cn/public/op_challenge_jingdong_final/varlenndrotaryposemb/ranking?page=1&size=20)。在线页面地址保持 [CANNJudgeWatcher](https://richardssheik107-hub.github.io/CANNJudgeWatcher/)。

## 运行链路与历史隔离

Cloudflare Worker `cannjudge-workflow-timer` 每十分钟向现有 `monitor.yml` 发送 workflow_dispatch。工作流显式使用 `--profile jingdong-final`，公开 GET 采集完成并保存状态后才发布 Pages。无需用户电脑开机，不执行赛事提交、登录或选手源码抓取。并发组沿用旧键以避免迁移时在途旧任务与新任务并行发布。

| 项目 | 当前京津东北决赛 | 保留的旧星辰杯 |
| --- | --- | --- |
| Profile | `jingdong-final` | `starcup-final` |
| 配置 | `config/monitor.jingdong-final.json` | `config/monitor.starcup-final.json` |
| 持久状态分支 | `watcher-state-jingdong-final` | `watcher-state` |
| 状态文件 | `jingdong-final.sqlite3` | `starcup-final.sqlite3` |

新 profile 固定赛事 ID `6adac8e13ff2fef7e8929a9f`、题目 ID `6adb272d1dac5d235bd66d0b`，严格要求单题榜和无凭据公开配置。新旧数据库不能交叉初始化或导出。切换没有删除、重置或覆盖原比赛历史。旧的一次性 reset 请求文件保留作审计，已从当前工作流入口移除。

## 首次初始化与常规更新

新比赛先得到一份真实、完整的公开采集，再显式初始化独立分支；已有状态拒绝再次初始化。下面路径必须新建，不覆盖旧产物：

```bash
python -m watcher --config config/monitor.jingdong-final.json --db data/jingdong-seed.sqlite3 poll
python -m watcher.github_monitor --profile jingdong-final --initialize --seed data/jingdong-seed.sqlite3 --work-dir data/first-new-work --site-output data/first-new-site --push-state
```

初始化只备份和验证显式 seed，不额外接触源站，也不直接发布 Pages。之后由 `CANNJudge monitor` 的一次常规调度恢复该状态、增量采集、推送状态并发布。普通轮次没有初始化或重置参数，不会每轮丢失历史：

```bash
python -m watcher.github_monitor --profile jingdong-final --work-dir data/new-round --site-output data/new-site --poll-seconds 600 --push-state
```

`ENABLE_GITHUB_PAGES=true` 且仓库公开才发布。关闭该变量仅停止发布；停止自动采集应停用 Cloudflare Cron。GitHub 原生 schedule 入口仍未使用。手动 `reset_history` 只有获得一份新的完整公开快照才切换活动历史；默认 false，不用于比赛迁移。不要把旧比赛 reset 请求用于新 profile。

## 分数解读

新题为 latest 模式。主表分为当前官方分、观测原始历史最高（当时基准）、当前基准历史最高（仅已观测候选）。缺少重算条件时第三列为未知，当前分仅作为详情中的可确认下界。初始只有一个有效提交版本时，标明无旧版本可比较。

平台[通用计分文档](https://raw.gitcode.com/fuyangchenghu/cann-judge/raw/master/docs/%E5%8A%9F%E8%83%BD%E5%8F%82%E8%80%83/05-%E6%8E%92%E8%A1%8C%E6%A6%9C%E4%B8%8E%E8%AE%A1%E5%88%86.md)描述线性比率；旧星辰杯公布对数公式。当前赛事规则正文未包含可校准公式，15 个测试点有 10 个隐藏，所以不沿用旧公式，也不由可见点推断完整成绩。精确重算同时要求本赛规则明确、全点完整、所有本轮完整官方成绩一致复现；隐藏/缺失时保留不确定性。全部赛事历史是否完整始终另行标记，不把定时榜单观测当作完整提交历史。

## 历史容量和 artifact 保留

活动 SQLite 达 90 MiB 会停止采集并保留已有历史，自动归档尚未实现。旧比赛历史另留原分支，不计入新活动数据库。长期运行仍需定期检查容量；任何增长预测都是样本估计，不保证天数。

自动采集不会上传额外预览 artifact。只有显式手动勾选 `save_preview` 才保留一天；Pages 的单次部署归档成功发布后按当前运行的精确 artifact ID 释放。数据库和快照历史不因此删除。

公开仓库标准 GitHub Actions runner 分钟免费，但 artifact 存储受账户套餐约束，[以 GitHub 官方计费说明为准](https://docs.github.com/en/billing/concepts/product-billing/github-actions)。Cloudflare 调用和 CPU 免费限制与同账户其他 Worker 共享，[以官方限制为准](https://developers.cloudflare.com/workers/platform/limits/)。十分钟一次约 144 次/日，不能据此推断存储无限或整个账户余额。

GitHub 专用令牌预计 **2026-11-05** 到期；到期前更新 Worker 的 `GITHUB_DISPATCH_TOKEN` Secret，勿放入仓库、聊天或日志。当前迁移不需要读取或更改秘密值。

## 故障检查

查看 `CANNJudge monitor` 的 collect/deploy 结果、`watcher-state-jingdong-final/state.json` 的 failure_count/not_before/last_status、页面观测时间与快照数。公开采集失败会保留上次完整榜并保存退避，不清空历史。状态 SHA256、非演示来源、导入标记、赛事/题目和所有快照证据必须一致，未通过不发布。验证以真实 workflow 与 Pages 结果为准。
