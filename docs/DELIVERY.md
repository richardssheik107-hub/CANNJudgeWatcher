# v0.1.0 导入记录与接续操作

日期：2026-10-06。

本次从 `CANNJudgeWatcher-v0.1.0.zip` 导入主体源码、静态前端、测试、部署配置、说明文档与演示预览。原包共 35 个文件；导入前已核对 `MANIFEST.sha256.json` 中的 34 个内容文件，全部匹配。原始压缩包 SHA-256 为 `6a5884e3c93fff16e9f9f882b08ee56fea5d23521221b440a31277e07566892c`。

远端仓库：https://github.com/richardssheik107-hub/CANNJudgeWatcher

导入基于初始化提交 `87cad593c901dabbbdb64858864024bc2923ed07`，该提交只有 `AGENTS.md`。本次完整源码提交保留其 Git 历史与项目约束，使用普通提交和推送，不强制覆盖历史。包内没有 `.git/`、凭据、运行数据库或第三方源码目录。

导入提交仅更新 README 的旧交付状态、本记录与验证记录，并重新生成文件清单；应用源码、配置、测试和预览按原包导入。该提交为 `ea3943296b753994272f6353c68b56580ecab06b`，已普通推送到 `main`，GitHub CI 通过。原始压缩包和解压副本保留在本地。

随后按用户“先在本地完成”的要求完成运行修复、Windows 演示启停脚本与本地验收，该阶段 **72 项回归通过**。用户提供星辰杯决赛公开链接后，又完成无登录、无 Cookie 的只读真实采集：精确 slug `ct_starcup_aiop_final`，21 支队伍、9 条官方 Pass 有效成绩，首轮前三总分 83.1、68.75、63.35。首次本地观测为 2026-10-06 19:12:23（北京时间），未观测的更早成绩不能补回。

真实联调修复了 Hidden 占位误判和嵌套测试集元数据提取，新增 11 项公开源回归，该阶段 **83 项通过**。总榜未公开官方 rank，保留未知，不把参考排序冒充官方名次。专用精确配置、独立真实数据库和 StarcupLive 启停脚本已增加，轮询等待为 120 秒。详细范围见 [VALIDATION.md](VALIDATION.md)，运行方式见 [LOCAL_RUN.md](LOCAL_RUN.md)。

用户随后选择 GitHub 免费运行方式。本次增加 Actions 单轮采集、独立状态分支持久保存与限流等待、Pages 静态前端导出及 34 项回归，完整测试 **117 项通过**。代码与状态分别保存于 `main` 和 `watcher-state`，运行数据库不进入源码提交。仓库目前保持私有，公开范围尚需用户确认；自动采集与 Pages 门控默认关闭。真实云端验证结果以 [VALIDATION.md](VALIDATION.md) 中记录为准，使用方法见 [GITHUB_RUN.md](GITHUB_RUN.md)。Docker、其他云服务器与 24 小时稳定运行仍未验收。

## 后续重新导入交付包

先克隆上述仓库，再把压缩包内 `CANNJudgeWatcher/` 的内容复制到克隆目录。保留克隆产生的 `.git/`；包中没有 `.git/`、凭据、运行数据库或第三方未授权源码。不要覆盖其他人已新增的代码，若远端已经变化，先比较再整合。

在仓库根目录测试、检查差异后提交：

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m compileall -q watcher
node --check web/app.js
git status --short
git diff --check
git add AGENTS.md README.md watcher web config tests docs requirements.txt requirements-dev.txt Dockerfile docker-compose.yml .github .gitignore .dockerignore .env.example pytest.ini
git diff --cached --stat
git commit -m "feat: add evidence-backed observed peak dashboard"
git push origin main
```

推送前检查暂存区，不包含 Cookie、令牌、`.env`、数据库或运行日志。不得 force push。如远端有新提交，正常拉取整合后再推送。

## 交给 Codex 的接续任务

请先阅读 `AGENTS.md`、`README.md`、`docs/UPSTREAM.md`、`docs/VALIDATION.md` 与 `docs/NEXT_STEPS.md`。保留已有测试与证据口径，不重写整套系统。

所选星辰杯决赛已完成公开发现、首轮只读采集、脱敏结构 fixture 与适配回归。接续时先核验其本地运行记录与实际数据，再按目标部署环境完成常驻运行；若扩展京津东北或其他赛段，重新确认精确 ID/赛段/分组、题目权重、稳定队伍 ID、score/rank 字段和公开历史权限。将真实响应脱敏制成小型回归 fixture，修复适配器并新增测试，不以猜测的 URL/身份/分数使测试通过。不得读取选手私有源码或绕过访问控制。

源接口 score 缺失时要保留测试点证据和未知分数，不套用浏览器插件的自定义分数。历史提交归档不等于已经按统一基准重评分；是否能把旧成绩补入峰值榜需先验证来源和规则。完成后再启动常驻采集，核验重启不丢历史、失败不清榜、24 小时稳定性；只按真实执行结果更新验收记录。
