# Windows 本地演示

在资源管理器中双击 `scripts\Start-LocalDemo.cmd`，成功后浏览器自动打开 <http://127.0.0.1:8088>。双击 `scripts\Stop-LocalDemo.cmd` 可停止此次演示服务。

也可以在仓库根目录的 PowerShell 中运行：

```powershell
.\scripts\Start-LocalDemo.ps1
.\scripts\Stop-LocalDemo.ps1
```

若 PowerShell 的执行策略阻止直接运行，使用上面的 `.cmd`，或运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-LocalDemo.ps1
```

脚本优先使用仓库 `.venv\Scripts\python.exe`，其次使用本机已配置的邻接环境 `..\.validation-venv\Scripts\python.exe`。需要 Python 3.11 或更新版本以及 `requirements.txt` 中的依赖；脚本会核验环境，不自动下载或安装软件。其他机器可指定已经安装好依赖的 Python：

```powershell
.\scripts\Start-LocalDemo.ps1 -PythonPath 'C:\path\to\python.exe'
```

8088 被占用时，脚本会报出占用 PID，不会停止占用服务。可以另选端口；停止时使用相同端口：

```powershell
.\scripts\Start-LocalDemo.ps1 -Port 8089 -NoBrowser
.\scripts\Stop-LocalDemo.ps1 -Port 8089
```

首次运行且 `data\demo.sqlite3` 不存在时才生成演示库。已有数据库必须通过 SQLite 完整性检查，并且所有作用域和快照均明确属于 A/B 组合成演示；通过后复用现有记录，失败则保留原库并停止启动。脚本不会重复灌入、覆盖或删除已有数据库。

本地演示仅监听 `127.0.0.1`，没有 `--poll`，`/health` 返回 `collector_enabled: false`。启动的子进程使用 UTF-8 输出，演示子进程不继承真实部署的 `WATCHER_TOKEN`；调用方的环境变量在启动后恢复。页面展示黄色演示标识。它可以验证双榜、A/B 组切换、队伍详情、证据查看及导出；所选星辰杯真实联调结果单独记录在 `docs/VALIDATION.md`。

启动成功前会核验服务健康状态及监听端口所属进程；重复启动同一已验证实例会复用它。PID 记录和运行日志位于 Git 忽略的 `data\` 目录。停止脚本先核验仓库路径、启动参数、可执行文件路径和进程创建时间，再停止记录中的本次服务进程；Windows 虚拟环境的 Python 启动器及其匹配启动参数的子进程在监听前便会登记，启动失败时也会在停止启动器之前刷新记录，避免初始化超时留下后台进程。遇到 PID 被复用或记录不匹配会报错，不会停止该进程。停止后保留数据库、日志和 PID 记录，不删除文件。

排障时先查看 `data\local-demo-8088-*.stderr.log` 与 `*.stdout.log`；健康检查地址为 <http://127.0.0.1:8088/health>。缺少依赖时，先在所选 Python 环境中安装 `requirements.txt`，再重新启动。演示数据检查失败时请检查记录和数据库来源，不要重新生成或覆盖已有库。

## 星辰杯公开决赛真实榜单

`Start-StarcupLive` 使用已确认的公开赛事 [`ct_starcup_aiop_final`](https://cannjudge.cn/public/ct_starcup_aiop_final/ranking)，固定读取 `config\monitor.starcup-final.json` 并保存到独立的 `data\starcup-final.sqlite3`。运行前配置必须仅选择这个精确 slug、使用 HTTP、`cookie_env` 为空字符串、`history_pages_per_poll` 为 0；不发送登录 Cookie，不请求历史提交列表。脚本只做离线配置/已有库检查，不生成合成数据，不清空或覆盖现有记录。

在仓库根目录运行，或双击同名 `.cmd` 文件：

```powershell
.\scripts\Start-StarcupLive.ps1
.\scripts\Stop-StarcupLive.ps1
```

默认地址仍为 <http://127.0.0.1:8088>。如果演示服务正在占用 8088，真实启动脚本会明确报错；先用 `Stop-LocalDemo.ps1` 停止演示，再启动真实服务。也可以保留演示并为真实服务另选端口：

```powershell
.\scripts\Start-StarcupLive.ps1 -Port 8089 -NoBrowser
.\scripts\Stop-StarcupLive.ps1 -Port 8089
```

Python 环境选择及 `-PythonPath` 参数与演示脚本相同。真实服务启用 `--poll`，`/health` 的 `collector_enabled` 为 `true`；健康检查成功表示网页服务已启动，采集结果以页面底部运行记录及榜单时间为准。首次采集完成前可能暂时没有作用域。接口失败、限流或榜单不完整时保留此前完整榜单。

真实服务继承调用环境中的 `WATCHER_TOKEN`。本机没有设置它时可以直接查看页面；设置后须在网页输入令牌，脚本不会打印令牌。所有 API、数据库、日志和 PID 记录与演示配置分离；真实日志为 `data\starcup-live-<端口>-*.log`，PID 记录为 `data\starcup-live-<端口>.process.json`。停止脚本沿用经过核验的路径、命令行、创建时间及父子进程身份保护，只停止此真实配置记录的进程。

真实峰值表示从本地监控开始后观测到的逐题官方分数最高值，随着采集积累；它不是对开赛以来全部成绩的追溯，也不是官方最终排名。

配置等待间隔为 120 秒，另有少量随机抖动及本轮请求时间；失败时增加等待，避免高频请求。关闭浏览器或结束 Codex 对话不会停止已启动的服务。电脑关机、睡眠或断网时，本地采集不能继续；电脑重启后须重新运行启动脚本。要独立于本机持续运行，按 `docs/CLOUD_RUN.md` 将程序迁移到在线服务器。
