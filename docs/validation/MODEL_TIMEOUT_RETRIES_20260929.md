# 模型超时与重试归口验证（2026-09-29）

基线：main `b894d19b35d4900aa791db2914f3a1475147945a`。保留此前 UI 文案与导航样式改动，未提交、push 或部署。

## 最终实现

用户最后确认全部归口前台配置，取代本轮较早的环境变量方案。

- 唯一管理入口：“管理后台 → 模型配置 → 超时与重试”。默认单次 300 秒，最多重试 3 次（首次请求之外，共最多 4 次）；0 关闭重试。
- 设置以一条 JSON 原子保存到现有 `app_metadata` 的 `model_timeout_settings` 配置项，仅管理员可写。新调用立即读取；同一调用及其重试固定开始时的策略，不混用更新前后的秒数和次数。无需重启、重新构建或修改私有环境文件。
- 删除环境变量入口、旧单模型 API/数据库字段、场景短时限参数、测试用运行环境覆盖、待重启逻辑、前端编译注入和旧固定代理时限。数据库升级脚本仅保留完成清理所必需的旧列识别。
- `GET/PUT /admin/model-configs/timeout-settings` 为管理员配置接口；`GET /model-timeout-settings` 为已认证用户读取两项非敏感设置的接口。普通用户没有写入口。前端根据实时设置和现有调用数计算等待预算，不重发业务 POST；普通读取仍为 30 秒。
- 两条模型适配路径仅对 `TimeoutError` / `httpx.TimeoutException` 自动重试。认证、限流、其他 HTTP/网络异常及返回校验失败不重试。重试使用同一模型和请求体，发送前重新检查原模型是否停用、删除或参数改变。
- 超时耗尽保留原异常类型、堆栈、尝试次数和重试次数，并继续脱敏；用户沿用原错误提示。业务保存仍只在成功后发生，失败不覆盖当前版本，不生成中间 Run/Version/结果。
- Run 与任务回收的保护时限从同一设置推导。同源 `/api` 使用原生 HTTP 流式转发，保留 Origin、认证、Cookie、上传字节、重定向及客户端取消，模型时限交由 API 控制，不再受独立固定代理超时截断。

## 本地数据与服务

确认运行中匹配任务、发展 Run 均为 0 后，使用现有脚本停服。先 `pg_dump` 全库备份、`pg_restore --list` 校验，再由 `scripts/migrate_model_timeouts.py` 在事务内：

1. 删除 `model_configs.timeout_seconds`。
2. 在已有配置表保存 300 秒 / 3 次默认策略。
3. schema 17 升至 18；所有受检业务表行数保持不变。

私有备份在 `.isolation/backups/model-timeout-settings-20260929/`，包含迁移前数据库、迁移前环境配置及结果。只删除现用环境文件中的两个废弃超时键，其他连接、凭据、路径和配置保留。不自动恢复、覆盖或重建运行库。回退需停服，将备份恢复至独立库核验后由管理员决定切换。

构建独占 `.next` 完成后恢复本项目开发服务，受信任的 HTTPS 检查：`/api/health` 200、`/admin/models` 200、未认证 `/api/model-timeout-settings` 401。运行库只读核实 schema 18、旧列数量 0、全局设置 300 / 3。ARM 未迁移、未部署。

## 实际验证

- 超时配置及重试专项：**77 项全部通过**（专用 PostgreSQL 临时 schema）。覆盖管理员权限、非法/额外字段、原子保存与并发、持久化、失败回滚、迁移成功/回滚、0/1/3 次重试、各类超时、非超时不重试、输入一致、版本保持、真实错误记录、保存后下一次调用立即生效以及进行中的重试保持原策略。文本和结构化适配器各通过真实本地 HTTP 超时重试测试，没有调用真实供应商。
- 最终复核上述 77 项并加入已有客户端参数检查，**78/78 通过**，证据：`/tmp/banfei-timeout-settings-backend.xml`。
- 扩大相关回归：**188 通过、6 失败**（179 项 PostgreSQL，15 项既有 SQLite 兼容测试）。6 项失败均已出现在本轮此前的只读 HEAD 基线验证中，主要为旧匹配测试对统一流程前错误提示/路径的假设；该组无新增失败，不宣称全量通过。证据：`/tmp/banfei-timeout-final-backend.xml`、`.log`；此前基线 `/tmp/banfei-timeout-baseline.xml`。
- 前端请求与代理：**10 项通过**。验证读取实时策略、默认和自定义预算、短读取、调用方取消、仅发送一次业务 POST、Origin/认证/多个 Cookie/二进制上传/重定向保持、31 秒响应不被旧代理时限截断、客户端取消关闭上游。证据：`/tmp/banfei-timeout-unit.json`。
- 页面：**8 项通过**。1366×768 与 390×844 下的保存、刷新保留、写失败保留输入、非法值阻止提交和现有模型删除交互；检查无横向溢出。所有业务 API 均使用合成响应，不向运行库做 E2E 写入。
- `typecheck`、生产 `build` 和 `git diff --check` 通过。生产构建与开发服务、浏览器验证顺序执行，不并发写 `.next`。
- 本轮浏览器为 WSL Chromium，不声称 Windows Edge 或 ARM 已验证。测试日志、SQLite、上传夹具与截图仅在 `/tmp`；PostgreSQL 测试仅在专用验证库临时 schema。

页面证据：`/tmp/banfei-timeout-settings-ui/result.json`；截图位于其 `results/model-timeout-settings-tim-a6657-nd-takes-effect-immediately-desktop/timeout-settings.png` 与对应 `narrow` 目录，内容均为合成设置。
