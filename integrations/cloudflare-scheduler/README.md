# Cloudflare 免费定时触发器

源码和离线测试随仓库保存，真实令牌仅保存在用户 Cloudflare Worker Secret 中。离线测试不会触发真实工作流；实际部署、Secret 接入和自动更新验收状态见仓库 `docs/VALIDATION.md`。

每 10 分钟由 Cloudflare Cron 调用现有 GitHub 工作流：固定 `richardssheik107-hub/CANNJudgeWatcher`、`main`、`monitor.yml`，输入固定为 `{"reset_history":false}`。采集、保存历史与 Pages 发布仍由现有 GitHub 工作流执行。Worker 没有 `fetch` 处理器；`workers.dev`、预览 URL 和自定义路由均关闭。

## 本地检查

在本目录执行（Node 内置测试，无第三方依赖、无网络请求）：

```powershell
node --check worker.mjs
node --test worker.test.mjs
```

测试凭据只是内存中的明确占位符；不会创建或读取真实令牌。23 项 Node 测试验证固定请求、200/204、3xx/401/429/5xx、网络异常、超时、缺失凭据以及拒绝意外计划。成功日志仅表示 GitHub 接受触发，不表示采集或发布完成。

从仓库根目录运行官方原生 Workers 运行时回归，CI 也执行同一命令：

```powershell
npx --yes workerd@1.20261001.1 test integrations/cloudflare-scheduler/runtime-tests/config.capnp
```

6 个测试直接嵌入实际 `worker.mjs`，使用原生 fetch，globalOutbound 仅路由本地 fixture，明确禁止所有互联网访问。204 接受，301/302/303/307/308 拒绝；校验固定目标、输入和每次只有一条请求。首次使用 npx 会下载固定版本官方运行时，测试请求本身离线且无真实凭据。

## 用户登录后如何启用

1. 注册或登录自己的 Cloudflare 账户，使用 Workers Free，无需银行卡。不用新建 GitHub 仓库，不用提供 GitHub 密码。
2. 在 GitHub 的 Settings → Developer settings → Personal access tokens → Fine-grained tokens 中创建专用令牌：Resource owner 为 `richardssheik107-hub`；Repository access 选择 **Only select repositories**，仅 `CANNJudgeWatcher`；仓库权限 **Actions: Read and write**，保留自动要求的 Metadata 读取权限，其他权限不授予。设合理到期日（例如 30 天，到期前更换）。预填入口只设置名称、所有者、权限和到期日，仍须手动仅选择该仓库：
   <https://github.com/settings/personal-access-tokens/new?name=CANNJudgeWatcher-scheduler&target_name=richardssheik107-hub&expires_in=30&actions=write>
3. 在 Cloudflare Workers & Pages 中先建立名为 `cannjudge-workflow-timer` 的 Worker，暂不添加 Cron。到该 Worker 的 Settings → Runtime → Variables and secrets → Add variable，Key 填 `GITHUB_DISPATCH_TOKEN`，Value 私密输入上一步令牌，保持 **Secret** 勾选，只选择 Production，点击 **Add 1 variable and deploy**。令牌只存 Worker Secret；不要发到聊天、写入代码/配置/日志、放网页或截图中。新增凭据的生成、复制、输入和保存由用户本人完成。
4. 确认 Worker Secret 已存在后，通过官方 Wrangler 登录自己的 Cloudflare 账户，再在本目录部署配置和代码。已经登录同一账户时无需重复授权。仅请求此次部署所需的账户、用户读取及 Worker 脚本写入、日志读取范围；脚本权限覆盖所选账户的 Workers，并非只限单个 Worker：

   ```powershell
   npx --yes wrangler@4.147.0 login --device --scopes account:read user:read workers_scripts:write workers_tail:read
   npx --yes wrangler@4.147.0 secret list
   npx --yes wrangler@4.147.0 deploy
   ```

   配置声明必需 Secret，缺失时应拒绝正式部署。正式配置关闭 HTTP 路由，仅保留每 10 分钟 Cron。Cron 新增或修改最多需要约 15 分钟传播。
5. 验收两个连续的真实 Cron：Worker 日志出现 `dispatch-accepted`，对应 GitHub Actions 的 `workflow_dispatch` 完成采集和 Pages 发布，网页的快照时间和观测记录增加。验收完成前不能称为自动刷新已解决。

本地已使用上述固定版本完成 `deploy --dry-run`。首次接入可先发布同一代码但不带 Cron 的引导版本，再由用户保存 Secret；这不代表自动更新已启用。正式部署必须使用本目录配置中的必需 Secret 和 `*/10 * * * *`。外部触发验收成功后再移除原生 schedule，保留 workflow_dispatch，避免两个时钟同时运行。

Cloudflare 会保存这个专用 GitHub 授权；它不是“凭据完全不离开 GitHub”的方案。Actions 写权限允许的操作多于单纯触发一次任务，所以只选本仓库并使用独立令牌。撤销专用令牌或移除 Cron 可停止该备用触发器。

## 运行边界

- 一次 Cron 只发一次 POST；401、429、5xx、网络失败或 10 秒超时会记录固定字段的安全 JSON 并抛出异常，不立即重试。未知超时可能已经被 GitHub 接受，因此不用重试制造重复任务。
- 成功仅认可官方新版 200 和旧版 204；不读取响应内容。日志不包含令牌、Authorization、响应正文或外部错误文本。
- 请求使用 Workers 原生运行时支持的 `redirect: 'manual'`；每个 3xx 都失败，绝不跟随跳转或发出第二次请求。不能使用 `redirect: 'error'`，原生 workerd 会在联网前拒绝该值。
- 固定 payload 的 `reset_history` 是布尔 `false`，不受环境变量或调用方覆盖。现有工作流的手动触发路径会绕过原生 `schedule` 开关，因此启用这个 Cron 后就是另一条采集触发路径。
- 外部 Cron 替代 GitHub 原生调度触发，不保证整点完成。GitHub 队列和现有串行工作流仍可能延迟；现有 collect/deploy 超时上限为 8/12 分钟。
- Free 额度为每日 100,000 调用、每次 10 ms CPU、每账户 5 个 Cron。每 10 分钟约 144 次/日；网络等待不计 CPU，但实际云端 CPU 和联网情况仍需部署后核验。

## 官方依据

- [Cloudflare Workers 免费及免银行卡](https://www.cloudflare.com/products/workers/)
- [Cron、UTC 与传播时间](https://developers.cloudflare.com/workers/configuration/cron-triggers/)
- [Free 额度](https://developers.cloudflare.com/workers/platform/limits/)
- [Secret 设置](https://developers.cloudflare.com/workers/configuration/secrets/)
- [关闭 workers.dev](https://developers.cloudflare.com/workers/configuration/routing/workers-dev/)
- [关闭 Version URLs（preview_urls）](https://developers.cloudflare.com/workers/versions-and-deployments/version-urls/)
- [GitHub workflow_dispatch 权限与响应](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event)
- [Fine-grained token 创建](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
