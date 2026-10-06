# v0.1.0 导入记录与接续操作

日期：2026-10-06。

本次从 `CANNJudgeWatcher-v0.1.0.zip` 导入主体源码、静态前端、测试、部署配置、说明文档与演示预览。原包共 35 个文件；导入前已核对 `MANIFEST.sha256.json` 中的 34 个内容文件，全部匹配。原始压缩包 SHA-256 为 `6a5884e3c93fff16e9f9f882b08ee56fea5d23521221b440a31277e07566892c`。

远端仓库：https://github.com/richardssheik107-hub/CANNJudgeWatcher

导入基于初始化提交 `87cad593c901dabbbdb64858864024bc2923ed07`，该提交只有 `AGENTS.md`。本次完整源码提交保留其 Git 历史与项目约束，使用普通提交和推送，不强制覆盖历史。包内没有 `.git/`、凭据、运行数据库或第三方源码目录。

本次仅更新 README 的旧交付状态、本记录与验证记录，并重新生成当前文件清单；应用源码、配置、测试和预览按原包导入。Windows 本机复验结果为 **56 passed**，Python 编译与 JavaScript 语法检查通过，具体环境和限制见 [VALIDATION.md](VALIDATION.md)。原始压缩包和解压副本保留在本地。

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

首要任务是在能访问 CANNJudge 的环境中验证 `discover` 与一次只读 `poll`，确认两场赛事的精确 ID/赛段/分组、题目权重、稳定队伍 ID、score/rank 字段和公开历史权限。将真实响应脱敏制成小型回归 fixture，修复适配器并新增测试，不以猜测的 URL/身份/分数使测试通过。不得读取选手私有源码或绕过访问控制。

源接口 score 缺失时要保留测试点证据和未知分数，不套用浏览器插件的自定义分数。历史提交归档不等于已经按统一基准重评分；是否能把旧成绩补入峰值榜需先验证来源和规则。完成后再启动常驻采集，核验重启不丢历史、失败不清榜、24 小时稳定性；只按真实执行结果更新验收记录。
