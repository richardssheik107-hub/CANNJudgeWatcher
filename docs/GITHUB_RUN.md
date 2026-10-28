# GitHub 自动监控京津东北决赛单题

当前目标：[VarLenNdRotaryPosEmb 排行榜](https://cannjudge.cn/public/op_challenge_jingdong_final/varlenndrotaryposemb/ranking?page=1&size=20)。在线页面地址保持 [CANNJudgeWatcher](https://richardssheik107-hub.github.io/CANNJudgeWatcher/)。

## 唯一监控目标与运行链路

Cloudflare Worker `cannjudge-workflow-timer` 每十分钟向现有 `monitor.yml` 发送 workflow_dispatch。工作流显式使用 `--profile jingdong-final`，公开 GET 采集完成并保存状态后才发布 Pages。无需用户电脑开机，不执行赛事提交、登录或选手源码抓取。固定并发组串行运行采集与发布。

| 项目 | 当前值 |
| --- | --- |
| Profile | `jingdong-final` |
| 配置 | `config/monitor.jingdong-final.json` |
| 持久状态分支 | `watcher-state-jingdong-final` |
| 状态文件 | `jingdong-final.sqlite3` |

固定赛事 ID `6adac8e13ff2fef7e8929a9f`、题目 ID `6adb272d1dac5d235bd66d0b`，严格要求单题榜和无凭据公开配置。仅此比赛进入当前采集、看板与导出；归档资料不参与活动状态。命令行未指定 profile 时同样默认当前比赛。诊断探针只保留手动入口，不另设自动计划。

## 首次初始化与常规更新

当前云端状态已经建立，日常更新直接运行常规轮次，不要重复初始化。只有全新部署且目标状态分支不存在时，才先采集一份真实完整快照，再显式初始化；已有状态会拒绝初始化。下面路径必须新建，不覆盖旧产物：

```bash
python -m watcher --config config/monitor.jingdong-final.json --db data/jingdong-seed.sqlite3 poll
python -m watcher.github_monitor --profile jingdong-final --initialize --seed data/jingdong-seed.sqlite3 --work-dir data/first-new-work --site-output data/first-new-site --push-state
```

初始化只备份和验证显式 seed，不额外接触源站，也不直接发布 Pages。之后由 `CANNJudge monitor` 的一次常规调度恢复该状态、增量采集、推送状态并发布。普通轮次没有初始化或重置参数，不会每轮丢失历史：

```bash
python -m watcher.github_monitor --profile jingdong-final --work-dir data/new-round --site-output data/new-site --poll-seconds 600 --push-state
```

`ENABLE_GITHUB_PAGES=true` 且仓库公开才发布。关闭该变量仅停止发布；停止自动采集应停用 Cloudflare Cron。GitHub 原生 schedule 入口仍未使用。手动 `reset_history` 只有获得一份新的完整公开快照才切换活动历史；默认 false。没有清理历史的明确请求时，不应开启。

## 分数解读

新题为 latest 模式。主表只比较当前官方分和最新基准历史最佳（仅已观测候选）：用本轮 TBest 重算每条历史完整有效提交，再取该队最大值。B 刷新基准后，A 即使没有新提交，它过去 100 分的版本也须按新基准降分；换成较慢最新提交时，历史最佳可以高于当前分，但依然随基准动态更新。旧原始分只留详情及 CSV 审计字段，不进入主表、排序或统计。缺少完整或一致的重算依据时显示未知，当前分仅作为详情中的可确认下界。初始只有一个有效版本时标明无旧版本可比较。

若规则已核验、全点 TBest/性能完整却无法复现官方本轮分数，则本轮可能有基准或规则口径矛盾：暂停该题全部当前锚点及旧提交的同基准认证，输出 calibration_status=conflict 与公开差异明细；不将旧官方 100 分重新认证为最新基准峰值，不猜算替代官方分。下一份一致快照可以恢复认证。

平台[通用计分文档](https://raw.gitcode.com/fuyangchenghu/cann-judge/raw/master/docs/%E5%8A%9F%E8%83%BD%E5%8F%82%E8%80%83/05-%E6%8E%92%E8%A1%8C%E6%A6%9C%E4%B8%8E%E8%AE%A1%E5%88%86.md)描述线性比率。本项目只依据当前赛事自身规则核验公式，不从其他赛事继承。当前赛事规则正文未包含可校准公式，15 个测试点有 10 个隐藏，所以不沿用旧公式，也不由可见点推断完整成绩。精确重算同时要求本赛规则明确、全点完整、所有本轮完整官方成绩一致复现；隐藏/缺失时保留不确定性。全部赛事历史是否完整始终另行标记，不把定时榜单观测当作完整提交历史。

## 历史容量和 artifact 保留

活动 SQLite 达 90 MiB 会停止采集并保留已有历史，自动归档尚未实现。归档资料不计入当前活动数据库。长期运行仍需定期检查容量；任何增长预测都是样本估计，不保证天数。

自动采集不会上传额外预览 artifact。只有显式手动勾选 `save_preview` 才保留一天；Pages 的单次部署归档成功发布后按当前运行的精确 artifact ID 释放。数据库和快照历史不因此删除。

公开仓库标准 GitHub Actions runner 分钟免费，但 artifact 存储受账户套餐约束，[以 GitHub 官方计费说明为准](https://docs.github.com/en/billing/concepts/product-billing/github-actions)。Cloudflare 调用和 CPU 免费限制与同账户其他 Worker 共享，[以官方限制为准](https://developers.cloudflare.com/workers/platform/limits/)。十分钟一次约 144 次/日，不能据此推断存储无限或整个账户余额。

GitHub 专用令牌预计 **2026-11-05** 到期；到期前更新 Worker 的 `GITHUB_DISPATCH_TOKEN` Secret，勿放入仓库、聊天或日志。当前迁移不需要读取或更改秘密值。

## 故障检查

查看 `CANNJudge monitor` 的 collect/deploy 结果、`watcher-state-jingdong-final/state.json` 的 failure_count/not_before/last_status、页面观测时间与快照数。公开采集失败会保留上次完整榜并保存退避，不清空历史。状态 SHA256、非演示来源、导入标记、赛事/题目和所有快照证据必须一致，未通过不发布。验证以真实 workflow 与 Pages 结果为准。
