# 云端持续运行：京津东北决赛单题

当前唯一监控对象是 [2026 CANN 京津东北决赛 · VarLenNdRotaryPosEmb](https://cannjudge.cn/public/op_challenge_jingdong_final/varlenndrotaryposemb/ranking?page=1&size=20)。日常访问[在线榜单](https://richardssheik107-hub.github.io/CANNJudgeWatcher/)即可，无须本机、浏览器或 Codex 持续运行。

## 已上线的运行方式

现有 Cloudflare Worker `cannjudge-workflow-timer` 的 Cron 每十分钟触发 GitHub `monitor.yml` 的 `workflow_dispatch`。工作流显式使用 `--profile jingdong-final`：

1. 从 `watcher-state-jingdong-final` 恢复并校验 `jingdong-final.sqlite3`。
2. 使用 `config/monitor.jingdong-final.json` 公开只读采集指定单题；不登录比赛、不提交代码、不抓取选手私有源码。
3. 保存完整快照和退避状态，成功推送活动历史后生成静态看板。
4. 在仓库公开且 `ENABLE_GITHUB_PAGES=true` 时发布 GitHub Pages。

`ENABLE_GITHUB_PAGES` 只控制页面发布；停止定时采集需要停用 Cloudflare Cron。旧的 `ENABLE_GITHUB_MONITOR` 变量不控制当前链路，GitHub 原生 schedule 不作为采集入口。不要重新初始化或重置已有活动数据库；日常更新只追加历史。

云端调度、队列或源站限流可能延迟，十分钟是计划间隔，不保证精确到分钟。失败保留上次完整榜单。当前状态、初始化命令、容量与令牌维护统一见 [GITHUB_RUN.md](GITHUB_RUN.md)；已验收的版本与运行编号见 [VALIDATION.md](VALIDATION.md)。

固定身份：赛事 `6adac8e13ff2fef7e8929a9f`，题目 `6adb272d1dac5d235bd66d0b`，榜单模式 `latest`。当前分来自最新提交，历史最佳按最新 TBest 重新评价完整历史提交；基准刷新后可以下降。缺少隐藏数据或校准矛盾时显示未知，不能将旧时原始高分当作当前历史最佳。

## 日常检查

查看 `CANNJudge monitor` 的 collect/deploy 结果、状态分支 `state.json` 的 `last_status`、`failure_count`、`not_before`，以及页面的最近观测时间与快照数。`/health` 不参与静态 Pages 模式，也不能代替真实采集验收。

活动数据库达到 90 MiB 时保护性停止采集并保留已有历史，自动归档尚未实现；应在接近限制前安排保留原始证据的归档或存储迁移。预览 artifact 只在手动选择时保留一天，正常自动运行不额外保存预览；单次 Pages 归档成功发布后按本轮精确 ID 释放，不删除数据库历史。

专用 GitHub 调度令牌当前记录的到期日为 **2026-11-05**，到期前需更新 Worker 的同名 `GITHUB_DISPATCH_TOKEN` Secret。不要把凭据放入仓库、聊天、日志或截图。本次聚焦当前比赛不需要更改凭据或另建仓库。

## 可选：自行托管 Docker

现有免费云端链路已可运行，不需要为它购买常驻服务器。以下只是基于当前仓库 `Dockerfile` 与 `docker-compose.yml` 的自建替代步骤；本轮没有执行 Docker 构建、容器启动、服务器重启或长期稳定性验收。

现有 Compose 的行为是：

- 默认 `config/monitor.json` 仅监控当前题目，并以只读方式挂载到容器。
- Docker CMD 使用 `/data/live.sqlite3`；它是此 Compose 部署的本地活动库，不是 GitHub 状态分支中的文件名。
- 数据写入命名卷 `watcher-data`；端口只绑定服务器 `127.0.0.1:8088`，映射容器 8080。
- `restart: unless-stopped` 在 Docker 服务正常启动时恢复未被手动停止的容器。
- `WATCHER_TOKEN` 在现有 Compose 中允许为空；只在回环接口自行查看时可以不设，对外提供访问前应设置访问令牌并配置 HTTPS。当前公开比赛配置不使用 CANN Cookie。

首次自建时使用独立项目名，避免无意复用其他服务的数据卷；若该项目已存在，应先核对来源并保留原数据：

```bash
docker compose -p cannjudge-jingdong config --quiet
docker compose -p cannjudge-jingdong build
docker compose -p cannjudge-jingdong up -d
docker compose -p cannjudge-jingdong ps
docker compose -p cannjudge-jingdong logs --tail 80 watcher
curl --fail http://127.0.0.1:8088/health
```

`config --quiet` 仅检查配置，不打印完整令牌环境。需要认证时先在服务器安全地设置 `WATCHER_TOKEN` 环境变量或受保护的本地 `.env`，不要把值写进命令历史或提交 Git。保持单实例采集，不要让另一进程同时写该卷的数据库。不要删除或批量清理数据卷。

容器健康检查成功只能证明 HTTP 服务就绪。上线前还需确认真实榜单身份、连续完整采集、重启保留历史、备份恢复和实际服务器到源站的连通性。迁移既有 SQLite 时先使用项目 `backup` 命令生成一致副本，只迁入经核验的空目标；不能直接搬运运行中的库、WAL 和 SHM，也不能覆盖已经使用的活动卷。

远程查看可通过 SSH 隧道：

```bash
ssh -N -L 18088:127.0.0.1:8088 server-user@server-address
```

保持该隧道后打开 <http://127.0.0.1:18088>。关闭自己的电脑只断开查看，服务器仍可采集；服务器本身必须保持运行和联网。需要公网访问时再配置 HTTPS 反向代理并保留 `Authorization` 请求头，相关部署另行验收。
