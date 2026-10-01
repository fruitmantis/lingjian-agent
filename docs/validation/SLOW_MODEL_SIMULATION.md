# WSL 模型慢响应模拟

本工具只做一件事：**收到真实模型的完整响应后，额外等待指定秒数，再原样返回响应正文和 HTTP 状态**。

系统的超时与重试由管理员自行配置。脚本不连接数据库、不读取私有配置、不修改模型参数或场景绑定、不设置模型请求时限，也不自动重试。

## 启动

在 WSL 正式工作区运行：

```bash
cd /home/yuan/project/lingjian-agent-enablement
.venv/bin/python scripts/simulate_slow_model.py \
  --upstream https://api.deepseek.com --delay-seconds 180 --port 18181
```

- `--delay-seconds`：额外延迟，默认 180 秒；修改后重启该代理。
- `--upstream`：原模型 Base URL，必填。现用 DeepSeek 地址已经只读核验为 `https://api.deepseek.com`，其他上游按实际值填写。
- `--port`：本机监听端口，默认 18181；占用时直接失败，不终止其他服务。
- 只监听 `127.0.0.1`；用 `Ctrl+C` 或 `SIGTERM` 停止，不影响 3000/8000/Caddy。

## 当前 WSL 接入

2026-10-01 已按用户要求**取消模型延迟，恢复真实供应商直连**。当前私有配置与运行中的后端进程均不含下述两个测试传输开关；模型、Key、场景绑定、参数及超时重试设置保持不变。

2026-09-30 曾按用户明确要求启用**本机伙伴匹配**的延迟，覆盖需求理解、全量初选、候选详评三次请求。启用时，正常完成的每次请求额外等待 180 秒，整条任务增加约 9 分钟；如果系统超时或重试，以管理员自行保存的策略为准。其他场景仍走原地址。

重新启用测试须有明确授权。为保留原供应商参数和输入预算，**不修改数据库中的模型 Base URL**；启用时在私有 `.isolation/runtime/dev/environment.json` 增加以下测试传输开关，并通过既有脚本重启生效：

```text
BANFEI_MATCH_DELAY_PROXY_URL=http://127.0.0.1:18181/v1
BANFEI_MATCH_DELAY_UPSTREAM=https://api.deepseek.com
```

仅匹配调用显式标记使用该传输；模型身份、Key、场景绑定、参数、DeepSeek 请求选项、输入预算和配置指纹继续按原模型计算。系统超时仍包围完整 HTTP 等待（包括代理延迟）。代理上游须与当前模型原地址一致，仅允许本机 `127.0.0.1` 的 HTTP 代理；不匹配时明确报错，不绕过代理默默直连。

代理把收到的请求正文与 Authorization 转发到上游，不保存 Key；原上游返回成功、认证错误或限流状态时都会等待指定时长再返回。

当前应用使用非流式 chat completions，代理仅提供 `POST /v1/chat/completions`，拒绝 `stream=true`。总耗时约为“真实供应商耗时 + 指定延迟”；若系统提前超时，是否重试完全由系统决定。每个到达代理的请求只转发一次，系统重试产生的新请求仍会调用真实供应商并产生相应费用。下游断开不会保证取消已发出的上游请求。

本次接入仅用于用户授权的本机 WSL 人工测试，不延伸到 ARM 或其他环境。配置修改前已在同一私有目录保留 `environment.before-match-delay-*.json`，权限 0600；未修改数据库或系统超时设置。

测试结束时，从当前私有配置中移除上述两个字段，再执行 `bash enablement-dev.sh stop` 和 `bash enablement-dev.sh start` 即可恢复直连。停止前确认没有运行中任务；不要直接覆盖整份旧备份，以免丢失期间的其他配置变动。恢复直连后可停止独立延迟代理。

延迟代理是独立临时进程，不由 `enablement-dev.sh` 启停。WSL 重启或该进程退出后，持久配置中的开关仍可能存在，此时匹配请求会连接失败，不会自动恢复直连。重新启用测试前应先启动代理并确认 `/health`；停用时必须移除两个开关并重启应用。

2026-10-01 取消时已在同一私有目录保留 `environment.before-disable-match-delay-*.json`（0600），仅删除两个开关并重启既有服务。已核对后端实际进程环境和匹配路由恢复 `https://api.deepseek.com`，单次超时 300 秒、重试 3 次未变；WSL 实际 IP 的登录页与 `/api/health` 均返回 200。没有重跑业务任务或发送模型生成请求，未验证 Windows 或 ARM。

## 查看状态

```bash
curl http://127.0.0.1:18181/health
```

健康检查立即返回当前延迟，不请求供应商。启动时显示过程日志位置 `/tmp/banfei-slow-model-*/events.jsonl`。日志仅含请求序号、耗时、状态等元数据，不记录请求正文、响应正文或凭据。

## 验证范围（2026-09-30）

```bash
.venv/bin/python -m unittest discover -s scripts/tests -p test_slow_model_simulation.py -v
```

当前版本使用本机合成上游验证响应延迟、请求/响应正文及状态透传、日志不含合成敏感内容、调用方自行超时且代理不重试、停止时中断等待。未向真实供应商发送验证请求，未验证产品页面或 ARM。

应用接入另通过 8 项专用 PostgreSQL 定向检查：三阶段接入、DeepSeek 参数与大输入预算保持、其他场景不受影响、错误代理地址/上游拒绝，以及原本机 HTTP 超时回归。仅使用合成数据和本机上游；没有为了验证接入而替用户创建业务任务或发送真实模型请求。

此前版本曾在临时 PostgreSQL schema 中自动配置超时并跑四类场景；该机制已按用户要求移除。此前 65 秒及四场景报告只属于旧版工具，不能作为当前代理版本的验证结果。
