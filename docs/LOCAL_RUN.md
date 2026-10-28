# 本地运行：京津东北决赛 VarLenNdRotaryPosEmb

当前只监控 [VarLenNdRotaryPosEmb 单题公开榜](https://cannjudge.cn/public/op_challenge_jingdong_final/varlenndrotaryposemb/ranking?page=1&size=20)。日常查看可直接打开[在线榜单](https://richardssheik107-hub.github.io/CANNJudgeWatcher/)，云端每十分钟计划采集，不需要本机开机。下面命令用于本地查看、调试或备份当前比赛。

## Python 环境

在仓库根目录使用 Python 3.11+。本机已经验证的环境是邻接目录 `..\.validation-venv\Scripts\python.exe`；其他机器可换成装有 `requirements.txt` 依赖的 Python。需要自行安装环境时，可在新的虚拟环境中执行：

```powershell
python -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
```

本机命令示例使用已配置的邻接环境，并启用 UTF-8：

```powershell
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
```

## 采集一次并查看

固定配置是 `config/monitor.jingdong-final.json`；默认 `config/monitor.json` 同样只选择当前赛事和题目。下面显式使用独立的当前比赛数据库，避免混入演示数据：

```powershell
& '..\.validation-venv\Scripts\python.exe' -m watcher --config config/monitor.jingdong-final.json --db data/jingdong-final.sqlite3 poll
& '..\.validation-venv\Scripts\python.exe' -m watcher --config config/monitor.jingdong-final.json --db data/jingdong-final.sqlite3 serve
```

浏览器打开 <http://127.0.0.1:8088>。`poll` 执行一轮只读公开采集；`serve` 不带 `--poll` 时只浏览已保存的快照，不自动采集。空数据库需要先成功采集一轮，才能出现真实榜单。

若 8088 已被其他服务使用，可在 `serve` 后加 `--port 8089`，再打开对应端口。不要停止不属于本任务的进程。

## 本地持续采集

需要本机持续采集时，在同一个命令中启用 `--poll`：

```powershell
& '..\.validation-venv\Scripts\python.exe' -m watcher --config config/monitor.jingdong-final.json --db data/jingdong-final.sqlite3 serve --poll
```

当前配置每轮结束后等待约 600 秒，并加入少量抖动；采集耗时、失败退避和源站限流会延长实际间隔。电脑必须保持开机、联网且不休眠；关闭浏览器不会停止前台服务，在启动服务的终端按 `Ctrl+C` 可正常结束。不要同时启动多个采集器写入同一数据库。

健康检查 <http://127.0.0.1:8088/health> 中的 `collector_enabled=true` 只表示已启用采集；是否采集成功，应查看页面底部运行记录中的 `SUCCESS`、所选题目及最近观测时间。失败、封榜、限流或缺页不会清空上次完整榜单。

采集无需 CANN 账号、Cookie 或密码。`WATCHER_TOKEN` 是可选的本地看板 API 访问令牌，与比赛登录无关；设置后需要在网页输入它，不要把值写进命令、仓库或截图。服务默认只监听 `127.0.0.1`。

## 分数与证据

主表比较官方当前分与按最新全场 TBest 重算的历史最佳。其他队伍刷新基准时，历史最佳也可以下降；当前提交仍为历史最优时，两列可以一起下降后继续相等。旧时公布的原始高分只在详情和 CSV 审计字段中保留，不参与主榜计算。

当前题目 15 个计分测试点中有 10 个隐藏，部分历史提交无法完整重算。缺少完整或一致依据时显示“无法确认”，不会用旧 100 分或当前下界兜底。完整公开规则与官方当前分发生矛盾时暂停该题同基准认证，下一份一致快照可恢复。更多口径见 [README](../README.md) 与 [验证记录](VALIDATION.md)。

备份始终使用新的目标文件名，不要直接分别复制运行中数据库及其 WAL/SHM：

```powershell
& '..\.validation-venv\Scripts\python.exe' -m watcher --db data/jingdong-final.sqlite3 backup data/jingdong-backup-20261028-163000.sqlite3
```

示例时间执行前须换为未使用的文件名。不要删除、覆盖或将演示数据导入当前比赛数据库。

## 可选演示

只验证界面时，可双击 `scripts\Start-LocalDemo.cmd`，结束后双击 `scripts\Stop-LocalDemo.cmd`。演示使用独立 `data/demo.sqlite3`，有明确 DEMO 标识且不采集真实赛事。演示与真实服务默认同用 8088；需要同时运行时，为其中一个指定不同端口。演示结果不能作为当前比赛的真实成绩证据。

## Windows 安全测试

本工作区禁止递归清理。使用保留产物插件，关闭 pytest 自带临时目录和缓存清理；测试产物使用短路径，避免 Windows 长路径限制：

```powershell
$env:PYTHONUTF8 = '1'
$env:PYTHONPATH = 'tests'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:PYTEST_ADDOPTS = '-p no:tmpdir -p no:cacheprovider -p retain_tmp'
$env:CANNWATCHER_TEST_ARTIFACTS = [System.IO.Path]::GetFullPath('..\.upload-validation\v-now')
& '..\.validation-venv\Scripts\python.exe' -m pytest -q
& '..\.validation-venv\Scripts\python.exe' -m compileall -q watcher
node --check web/app.js
node --test tests/frontend_scores.test.mjs
```

测试目录、数据库和日志全部保留，不自动清理；其他机器须先安装 `requirements-dev.txt`。测试通过和真实源站采集、网页发布分别验收。
