# 当前比赛维护清单

唯一目标：[京津东北决赛 VarLenNdRotaryPosEmb](https://cannjudge.cn/public/op_challenge_jingdong_final/varlenndrotaryposemb/ranking?page=1&size=20)。不再跟踪其他赛事，不开展其他赛段接入。操作以 README、GITHUB_RUN 和当前配置为准；过去阶段资料仅归档。

## 已上线

- Cloudflare 每十分钟触发当前 `CANNJudge monitor`，显式 `jingdong-final`，保存状态后发布 Pages。
- 当前配置与命令行默认均选择固定赛事、固定题目、单题榜、公开无凭据读取。
- 最新 TBest 下逐条完整提交重算并选择动态最佳；主表仅比较当前分与同基准历史最佳，原始分只留审计。
- 校准冲突暂停认证、下一轮一致恢复；隐藏或缺失条件显示未知；历史跨轮保留，失败不清空旧榜。

## 当前需要持续维护的事项

1. 检查 `CANNJudge monitor` 的 collect/deploy 状态、当前状态分支 failure_count/not_before、页面观测时间和快照数。只开启 Pages 不会产生定时采集，定时入口仍是 Cloudflare Cron。
2. GitHub 调度令牌预计 **2026-11-05** 到期，需在到期前更新 Worker 的 `GITHUB_DISPATCH_TOKEN` Secret，不将令牌放入代码或日志。
3. 检查当前 SQLite 大小，90 MiB 达到保护阈值会停止采集。自动归档尚未实现；长期保存应在阈值前实现不丢原始证据的归档或迁移。
4. 当前 10 个测试点隐藏，公开接口无法补齐其他队伍完整历史。只有赛事方合法公开完整数据或提供官方重算分接口，才可扩大动态历史最佳覆盖；普通账号密码不保证具备这些权限。
5. 对真实发生的 TBest 刷新保留前后快照，核对固定提交随基准降分、最优版本切换和页面更新。已有受控回归不冒充生产中实际发生的基准变化。

## 修改与验收

先读 `AGENTS.md`，保持当前固定配置、公开只读边界与演示隔离。修改计算逻辑时验证完整提交、动态降分、冲突恢复、未知不兜底和证据不变；修改默认入口时确认不会选择其他赛事。更新 `docs/VALIDATION.md` 和 `MANIFEST.sha256.json`，测试通过后普通提交至 main，不强推、不批量删除、不清理数据库或测试产物。

Docker、外部 CLI、生产反向代理等未执行的验收保持未验证，不为当前已运行的 GitHub 路径增加无关部署工作。
