# 验证文档索引

更新日期：2026-10-01。当前正式工作区 main、本地 PostgreSQL schema 18；运行与安全约束以根目录 [README](../../README.md) 和 [AGENTS](../../AGENTS.md) 为准。

## 当前入口

| 目的 | 文档 |
|---|---|
| PostgreSQL-only 清理、完整测试收口及 8 次真实模型补测 | [PostgreSQL-only 验证](POSTGRES_ONLY_20261001.md) |
| 任务先落库、后台执行、真实进度与渐进展示 | [任务执行与恢复验证](DURABLE_TASK_EXECUTION_20261001.md) |
| WSL 模型响应延迟代理（超时由系统自行配置） | [慢响应模拟使用说明](SLOW_MODEL_SIMULATION.md) |
| 本轮改动提交范围、最新回归及发布边界 | [2026-09-29 Git 收口](GIT_CLOSEOUT_20260929.md) |
| 伙伴选择搜索、500 家伙伴及三种视口验证 | [伙伴搜索选择验证](PARTNER_SELECT_SEARCH_20260929.md) |
| 模型超时失败、原任务重试与提交恢复 | [超时任务恢复验证](TASK_TIMEOUT_RECOVERY_20260929.md) |
| 模型超时配置归口、重试与 schema 18 清理 | [超时与重试验证](MODEL_TIMEOUT_RETRIES_20260929.md) |
| Coze UI 提交边界与合并验证 | [Coze UI 合并验证](COZE_UI_MERGE_20260929.md) |
| 当前统一理解、局部修改、固定模型及 11 次真实调用 | [统一任务流程验证](UNIFIED_TASK_FLOW_20260928.md) |
| 最新工程验证、提交范围、数据边界 | [2026-09-26 Git 收口](GIT_CLOSEOUT_20260926.md) |
| 新对话接续、已完成事项、不要重做的操作 | [项目交接](../handoff/CURRENT_HANDOFF_20260926.md) |
| 最新公网 ARM 部署、近三天兼容检查、数据保留 | [ARM HTTPS 验证](ARM_HTTPS_VALIDATION_20260927.md) |
| 当前 HTTP 80 入口、Origin 与身份回退 | [HTTP 运行说明](../HTTP_SETUP.md)；[此前 HTTPS 验证](HTTPS_VALIDATION_20260926.md) 仅作历史记录 |
| 六类资料、单一案例展示、手动画像、统一后台 | [伙伴资料验证](PARTNER_MATERIALS_VALIDATION.md) |
| 伙伴/课程/实验 Excel 导入导出、空白模板、资源批量上下架 | [导入导出验证](RESOURCE_TRANSFER_VALIDATION.md) |
| 官网能力逐家采集、30 家增量补充、备份及数据边界 | [官网能力补充](PARTNER_CAPABILITIES_20260926.md) |
| 真实供应商验证方法（不代表已执行） | [模型前检](REAL_MODEL_PRECHECK.md)、[验证计划](REAL_MODEL_VALIDATION_PLAN.md) |
| 人工效果验收空白模板 | [业务验收模板](REAL_BUSINESS_ACCEPTANCE_TEMPLATE.md) |

## 专项与历史证据

以下文档保留各阶段实现和结果；其中“未提交”、旧 HEAD、环境状态及通过数字只属于当时，不能作为当前 Git 状态或合计通过数。

| 范围 | 文档与适用边界 |
|---|---|
| 普通身份 | [身份 Key](IDENTITY_KEY_VALIDATION.md)；[本机身份旧记录](LOCAL_IDENTITY_VALIDATION.md) 中的 Passkey 方案已退出当前流程 |
| 账号删除 | [逻辑删除](ACCOUNT_DELETION_VALIDATION.md)，替代早期 90 天/凭据类型及历史清理规则 |
| 能力发展 | [current 与追问](DEVELOPMENT_CURRENT_VALIDATION.md)，confirmed 不参与业务 |
| 范围与错误 | [旧独立 Scope Gate](SCOPE_GATE_VALIDATION.md) 仅作历史；现为 [统一理解](UNIFIED_TASK_FLOW_20260928.md)，沿用 [错误处理](ERROR_HANDLING_VALIDATION.md) |
| 课程与实验 | [资源精简](RESOURCE_CENTER_VALIDATION.md)、[华为云导入](HUAWEI_RESOURCE_IMPORT.md)；案例后续规则以 schema 17 资料文档为准 |
| 公共交互 | [分页](PAGINATION_VALIDATION.md)、[反馈](FEEDBACK_VALIDATION.md) |
| 平台兼容 | [此前 ARM HTTPS 验证](ARM_HTTPS_VALIDATION_20260927.md) 仅为历史部署结果；[当前 HTTP 更新步骤](../HTTP_SETUP.md) 尚未在 ARM 执行；Windows 与内网 ARM 未实测 |
| 旧提交与 Pilot | [09-25 收口](GIT_CLOSEOUT_20260925.md)、[Pilot 归档](PILOT_ARCHIVE_20260925.md) |

## 统一口径

- 自动化只用专用 `banfei_agent_test` / `banfei_validation` 的独立临时 schema，上传夹具只用本轮 `/tmp` 目录；禁止使用正式库或 public 执行测试。
- 正式后端入口为 `.venv/bin/python scripts/run_postgres_validation.py backend -q`；先在当前进程私密加载 `BANFEI_TEST_DATABASE_URL`，不能打印连接串。
- pytest、浏览器与夹具均直接使用本轮专用 PG 临时 schema，不使用中转数据库。缺少配置直接报错；临时 schema 只由创建它的本轮进程删除。
- 经用户确认，旧 Pilot 和历史修复工具及其专用测试已删除，不计入当前通过数；历史报告中的混合验证数字保留原口径，不改写成 PG 通过。
- UI / replay / 真实模型请求分别记录，最新真实调用次数与结果见对应专项记录。测试通过不等于人工业务验收或部署授权。
- 当前库已完成 schema 17 迁移和授权的伙伴名单整理；文档中的迁移命令是其他旧环境升级说明，不是重复执行要求。
