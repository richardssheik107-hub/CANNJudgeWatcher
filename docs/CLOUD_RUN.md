# 星辰杯云端持续运行

把程序放到长期在线的 Linux 云服务器后，采集、SQLite 和网页看板都在服务器上运行。自己的电脑可以关机；用电脑或手机打开看板即可查看服务器已有结果。每轮采集完成后通常等待约 120 秒，失败会退避，因此不是严格每两分钟出现一份新数据。

当前已选择并完成 [GitHub Actions + Pages 免费部署](GITHUB_RUN.md)，无需购买云服务器。[在线榜单](https://richardssheik107-hub.github.io/CANNJudgeWatcher/) 已上线，本机停止后云端仍能采集并发布。本页的 Docker、Linux 和 Render 步骤保留为替代方案；容器启动、服务器重启和长期运行仍未验收。

## 选择运行环境

| 方案 | 官网费用参考（2026-10-06 核验） | 适用情况 |
| --- | --- | --- |
| 腾讯云中国内地 Linux 轻量应用服务器 | 入门型 2 核、2GB 内存、40GB SSD、2Mbps、100GB/月流量，35 元/月；国内套餐超额流量 0.8 元/GB | 优先推荐。单台服务器保留当前 Docker + SQLite，初始规格仍须实测。续费、系统更新和备份需要维护。 |
| Render 付费 Docker Web Service | 0.5 CPU、512MB 为 7 美元/月；持久盘 0.25 美元/GB/月，流量超额另计 | 较少系统维护。当前应用可用一个服务同时运行采集与看板；内存和访问中国源站的稳定性仍须实测。 |

费用以实际下单地区、套餐和控制台为准；新客促销不能代表续费价格。官方来源：[腾讯云价格总览](https://cloud.tencent.com/document/product/1207/73452/)、[Render 价格](https://render.com/pricing)。

免费 Render 在 15 分钟无入站访问后休眠，无法挂持久盘，休眠或重启会丢失本地 SQLite，因此不适合此常驻采集程序。采集向赛事发出的请求属于出站请求。[免费限制](https://render.com/docs/free)

Render 可选新加坡等区域，目前没有中国内地区域；部署前须从实际运行地区请求 CANN 源站，不能用本机连通来代替云端验收。[区域](https://render.com/docs/regions)

GitHub Actions 单次采集与静态页面方案已上线：每轮从 `watcher-state` 分支恢复完整历史，固定读取星辰杯决赛公开榜，再保存一致备份并生成 Pages 看板。用户已确认公开原仓库，`ENABLE_GITHUB_MONITOR` 和 `ENABLE_GITHUB_PAGES` 均开启，计划间隔为十分钟。公开标准 runner 的运行时间免费，Pages 使用免费域名；存储和容量限制仍适用。初始化、免费条件及数据保留见 [GitHub 运行说明](GITHUB_RUN.md)。[Actions 计费](https://docs.github.com/en/billing/concepts/product-billing/github-actions)、[Pages 适用范围](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages)

GitHub 定时任务可能延迟或丢弃排队运行，公开仓库无活动 60 天会停用计划，因此十分钟是计划频率，并非持续服务或严格实时保证。本项目跨 runner 保存 429 等待和失败退避，失败会保留旧榜；数据库达到 90 MiB 时停采而不自动删历史。[定时规则](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)

## Linux 服务器迁移步骤

1. 选择一台长期在线的 Linux 服务器，准备普通 SSH 账号。安装 Docker Engine 和 Compose 插件，按对应系统的[官方安装说明](https://docs.docker.com/engine/install/)操作。服务器需要保持联网、有剩余磁盘且按时续费；不配置空闲关机或休眠。
2. 上传本轮已核验的代码副本及 `config/monitor.starcup-final.json`、`docker-compose.starcup.yml`，或克隆已更新的 `main`。上传代码时排除 `.git`、`.env`、虚拟环境、演示数据库及日志；真实数据库按下一节单独迁移。
3. 在服务器代码根目录先验证公开接口可达。不要添加 Cookie，也不要请求私人提交、登录或代码接口：

   ```bash
   curl --fail --max-time 25 https://cannjudge.cn/api/groups/public
   ```

   必须得到有效 JSON。若返回 HTML、超时、拒绝访问或限流，先处理该服务器的连通性，不能把健康检查通过视为赛事采集成功。

4. 确认该服务器尚无其他服务使用 8088，也没有不相关的 `starcup-data` 卷。已存在的卷应先核对用途，不删除、不覆盖。启用 Docker 开机启动：

   ```bash
   sudo systemctl enable --now docker
   ```

5. 在服务器上生成访问令牌。它只保护自己的看板 API，不是 CANN 账号密码。以下输入不会回显，也不会把令牌写进命令文本：

   ```bash
   read -r -s -p 'WATCHER_TOKEN: ' WATCHER_TOKEN
   printf '\n'
   export WATCHER_TOKEN
   docker compose -f docker-compose.starcup.yml config --quiet
   docker compose -f docker-compose.starcup.yml build
   ```

   令牌为空时 Compose 会拒绝运行。用密码管理器保管；后续 Compose 操作需要再次设置环境变量。不要运行会打印完整环境的配置命令，不把令牌加入仓库或截图。

6. 可选：在首次启动前按下一节迁入本地一致备份。不迁移时会创建全新的真实观测库，云端峰值从首次完整采集开始积累。
7. 启动并检查：

   ```bash
   docker compose -f docker-compose.starcup.yml up -d
   docker compose -f docker-compose.starcup.yml ps
   docker compose -f docker-compose.starcup.yml logs --tail 80 watcher
   curl --fail http://127.0.0.1:8088/health
   ```

   `/health` 应返回 `collector_enabled: true`。这只证明服务启用了采集；仍须打开看板，看到此赛事、真实数据标识、完整榜单和采集记录中的 `SUCCESS`。保留单实例、单 worker，不能同时启动多个采集器写同一库。

## 迁移已有 SQLite 证据

不要直接复制运行中的 `starcup-final.sqlite3`，也不要把活动库与它的 `-wal`、`-shm` 文件分别搬过去。项目的 `backup` CLI 使用 SQLite backup API 生成一致的独立备份；网页 `/api/export` 是快照 JSONL 导出，不是完整数据库备份，导入后还会标记为人工导入来源。

在 Windows 仓库根目录，用现有 Python 环境生成一个从未使用过的备份文件名；原服务可以继续运行：

```powershell
$transferFile = Join-Path (Get-Location) ('data\starcup-final-transfer-{0}.sqlite3' -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
if (Test-Path -LiteralPath $transferFile) { throw '备份路径已存在，请使用新的文件名。' }
& '..\.validation-venv\Scripts\python.exe' -m watcher --db 'data\starcup-final.sqlite3' backup $transferFile
```

如果本机使用其他 Python，则替换可执行文件路径。确认命令成功后，通过 SCP/SFTP 将这份备份上传到服务器代码目录的 `transfer.sqlite3`；不要上传演示库。

**只对首次启动前的空云端卷执行迁入。**以下一次性迁移容器会保留，方便审计，不运行采集。它先检查完整性，再以独占新文件方式写入；目标库已存在时停止，不覆盖：

```bash
docker compose -f docker-compose.starcup.yml run --no-deps \
  --name starcup-initial-migration --user 0 --entrypoint python \
  --volume "$PWD/transfer.sqlite3:/imported.sqlite3:ro" watcher -c '
from pathlib import Path
import os, shutil, sqlite3
source = Path("/imported.sqlite3")
target = Path("/data/starcup-final.sqlite3")
if target.exists() or Path(str(target) + "-wal").exists() or Path(str(target) + "-shm").exists():
    raise SystemExit("Target database already exists; preserve it and stop.")
connection = sqlite3.connect("file:/imported.sqlite3?mode=ro", uri=True)
try:
    if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise SystemExit("Backup integrity check failed.")
finally:
    connection.close()
with source.open("rb") as original, target.open("xb") as destination:
    shutil.copyfileobj(original, destination)
os.chown(target, 10001, 10001)
target.chmod(0o600)
print("Consistent backup copied to a new target database.")
'
```

迁入后保留 Windows 原库、上传的备份和云端新库。首次启动完成后，在看板核对作用域、首份观测时间、已有快照数量和历史证据，确认它们与迁移前相符。

## 先通过 SSH 隧道查看

默认只监听服务器的 `127.0.0.1:8088`，不需要开放 8088 的公网入站规则。在自己的电脑打开终端，将以下账号和地址替换为实际值：

```powershell
ssh -N -L 18088:127.0.0.1:8088 server-user@server-address
```

保持该 SSH 窗口运行，浏览器打开 <http://127.0.0.1:18088>，在页面中输入 `WATCHER_TOKEN`。这个 HTTP 地址位于本机回环接口，跨网络段由 SSH 加密。关闭隧道或关闭自己的电脑只会断开查看，服务器仍继续采集。

需要从手机或任意电脑直接访问时，再配置 HTTPS 反向代理到服务器 `127.0.0.1:8088`，保持 API 令牌校验；由代理保留 `Authorization` 请求头。不要把 8088 裸露到公网，不在公网 HTTP 网页里输入令牌，也不要把令牌放到 URL 查询参数中。HTTPS、访问保护和实际远程访问均须另行验收。

## 数据保留、备份与重启验收

`starcup-data` 独立命名卷保存 `/data/starcup-final.sqlite3`。容器重启或重新构建不应清空它；不要执行删除数据卷、批量清理或自动递归清理命令。`restart: unless-stopped` 配合 Docker 开机启动可恢复未被手动停止的容器；手动停止后需要再次 `up -d`。

服务运行时可以生成一致备份，始终使用新文件名：

```bash
docker compose -f docker-compose.starcup.yml exec watcher \
  python -m watcher --db /data/starcup-final.sqlite3 backup /data/backup-20261006-210000.sqlite3
```

上面的日期只是示例，执行前换成新的时间。再用 `docker compose cp` 或安全文件传输把备份保存到独立位置；只存在同一块磁盘上的备份不能应对整盘丢失。

验收时依次检查：连续至少三轮完整采集成功；重启容器后原历史仍在且继续采集；服务器重启后容器自动恢复；自己的电脑关机期间服务器时间戳继续更新；一次备份可在另一份独立库恢复并通过完整性检查。健康检查没有连接到赛事数据，它不能代替这些验收。服务器长期运行、磁盘增长、外部接口变化和备份恢复仍未在本轮实测。

## Render 付费替代方案

使用一个 **付费 Docker Web Service**，上传或连接本轮代码版本，设置秘密环境变量 `WATCHER_TOKEN`，将 `PORT` 设为 `8080`，挂一块持久盘到 `/data`，启动命令明确使用此配置：

```bash
python -m watcher --db /data/starcup-final.sqlite3 --config /app/config/monitor.starcup-final.json serve --host 0.0.0.0 --port 8080 --poll
```

不设置 CANN Cookie。此赛事配置的 `cookie_env` 为空，只有公开只读接口。先验证源站可达，再迁入一致备份并核对历史。Render 为 Web Service 提供 HTTPS 地址；访问时继续输入看板令牌。[Web Service 文档](https://render.com/docs/web-services)

持久盘只能由一个服务实例使用，不能拆成一个采集 worker 和另一个看板服务共同访问同一盘，也不能横向扩展此 SQLite 部署。附盘部署会短暂中断服务；只有 `/data` 下的文件持久保存。官方磁盘快照不能代替项目 SQLite 一致备份和恢复验证。[持久盘说明](https://render.com/docs/disks)
