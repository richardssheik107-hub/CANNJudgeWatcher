# CANNJudgeWatcher · 京津东北决赛单题监控

仅监控 [2026 CANN 京津东北决赛 · VarLenNdRotaryPosEmb](https://cannjudge.cn/public/op_challenge_jingdong_final/varlenndrotaryposemb/ranking?page=1&size=20)。[在线榜单](https://richardssheik107-hub.github.io/CANNJudgeWatcher/)由 Cloudflare Cron 每十分钟触发 GitHub Actions 采集、保存历史并发布，无须本机持续开机。源码与保存的公开成绩历史均公开。

## 当前配置

| 项目 | 当前值 |
| --- | --- |
| 赛事 | `op_challenge_jingdong_final` |
| 题目 | `varlenndrotaryposemb` / `VarLenNdRotaryPosEmb` |
| Profile | `jingdong-final` |
| 配置 | [`config/monitor.jingdong-final.json`](config/monitor.jingdong-final.json)，默认 `config/monitor.json` 内容相同 |
| 持久状态 | `watcher-state-jingdong-final` 分支的 `jingdong-final.sqlite3` |
| 自动采集 | `.github/workflows/monitor.yml`，`CANNJudge monitor`，每十分钟 |

当前命令行采集与静态导出默认选择 `jingdong-final`，工作流也显式指定该 profile。其他赛事不再作为监控、运行或后续维护对象；已保存的归档资料不进入当前榜单或导出。

## 如何理解当前分与历史最佳

官方当前分来自该题公开榜。该题采用 `latest` 模式，榜上是每队最新提交。

```text
历史最佳(t) = max{每条已观测完整有效提交按最新 TBest(t) 重算的分数}
```

其他队伍刷新测试点最优用时后，历史最佳也可能下降。若最新提交仍是该队最优版本，当前分与历史最佳会一起下降，仍然相等。曾经公布的 100 分只在审计详情保留，不参与主表、排序、统计和同基准分差。

重算要求本赛规则明确、全点性能和 TBest 完整，并能复现本轮完整官方成绩；单题只选一条完整提交，不拼接各版本的最优测试点。官方分与公开基准矛盾时暂停该题的同基准认证，保留原始值并标记待核对；下一轮一致时恢复。未知值不由当前分或旧高分兜底。

当前题有 **15 个测试点，10 个隐藏**，赛事规则正文未给出可校准的赋分公式，公开接口也不提供其他队伍的完整历史提交。因此部分历史最佳显示“无法确认”；不能将五个可见点平均、按比例缩放旧分或套用通用公式冒充完整结果。定时榜单只覆盖实际观测，可能漏掉两轮之间被替换的提交。

## 运行与导出

需要 Python 3.11+，在仓库根目录执行：

```bash
python -m pip install -r requirements.txt
python -m watcher --config config/monitor.jingdong-final.json --db data/jingdong-final.sqlite3 poll
python -m watcher --config config/monitor.jingdong-final.json --db data/jingdong-final.sqlite3 serve
```

访问 `http://127.0.0.1:8088`。`serve` 只浏览已保存数据；加 `--poll` 才持续采集，本地运行期间电脑需要保持运行。云端已经独立采集，查看在线榜不需要本地启动服务。

```bash
python -m watcher --db data/jingdong-final.sqlite3 export snapshots.jsonl
python -m watcher --db data/jingdong-final.sqlite3 backup backups/jingdong-backup.sqlite3
```

页面提供 CSV、队伍详情、原始证据与 JSONL 导出。SQLite backup 用于完整一致备份，执行前将目标文件名改为尚未使用的名称。失败、缺页、封榜、权限或限流时保留上一份完整榜，不清空历史。当前自动采集不使用 Cookie，也不回填需要权限的历史列表。

## 文档与维护

- [GitHub 定时采集与发布](docs/GITHUB_RUN.md)：当前配置、状态分支、手动运行与故障检查。
- [本地运行](docs/LOCAL_RUN.md)：当前题目采集、浏览与独立演示。
- [云端运行](docs/CLOUD_RUN.md)：已上线链路与可选 Docker 方式。
- [接口与来源](docs/UPSTREAM.md)：当前接口、规则核验和许可边界。
- [当前维护清单](docs/NEXT_STEPS.md)、[验证记录](docs/VALIDATION.md)、[修改约束](AGENTS.md)。

活动数据库到 90 MiB 会保护性停止采集，自动归档尚未实现。额外预览仅在手动勾选 `save_preview` 时保留一天；每轮 Pages 部署归档成功后按精确 ID 释放，成绩数据库与历史不因此删除。GitHub 调度令牌预计 **2026-11-05** 到期，须在到期前更新 Cloudflare 同名 Secret。

## 开发验证

运行 pytest 前先按 [Windows 安全测试](docs/LOCAL_RUN.md#windows-安全测试) 设置保留产物环境，关闭自动临时目录清理；CI 已配置相同插件。

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m compileall -q watcher
node --check web/app.js
node --test tests/frontend_scores.test.mjs
```

本工作区测试禁止递归清理，Windows 安全测试环境见 [本地运行说明](docs/LOCAL_RUN.md)。测试覆盖移动基准降分、最佳完整提交切换、校准冲突与恢复、未知不兜底、身份隔离、历史保留和静态发布。来源包及过去阶段记录作为归档保留，不代表当前监控目标。
