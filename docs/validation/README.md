# 验证文档索引

更新日期：2026-09-26。当前正式工作区 main、PostgreSQL schema 17；运行与安全约束以根目录 [README](../../README.md) 和 [AGENTS](../../AGENTS.md) 为准。

## 当前入口

| 目的 | 文档 |
|---|---|
| 最新工程验证、提交范围、数据边界 | [2026-09-26 Git 收口](GIT_CLOSEOUT_20260926.md) |
| 新对话接续、已完成事项、不要重做的操作 | [项目交接](../handoff/CURRENT_HANDOFF_20260926.md) |
| 六类资料、单一案例展示、手动画像、统一后台 | [伙伴资料验证](PARTNER_MATERIALS_VALIDATION.md) |
| 真实供应商验证方法（不代表已执行） | [模型前检](REAL_MODEL_PRECHECK.md)、[验证计划](REAL_MODEL_VALIDATION_PLAN.md) |
| 人工效果验收空白模板 | [业务验收模板](REAL_BUSINESS_ACCEPTANCE_TEMPLATE.md) |

## 专项与历史证据

以下文档保留各阶段实现和结果；其中“未提交”、旧 HEAD、环境状态及通过数字只属于当时，不能作为当前 Git 状态或合计通过数。

| 范围 | 文档与适用边界 |
|---|---|
| 普通身份 | [身份 Key](IDENTITY_KEY_VALIDATION.md)；[本机身份旧记录](LOCAL_IDENTITY_VALIDATION.md) 中的 Passkey 方案已退出当前流程 |
| 账号删除 | [逻辑删除](ACCOUNT_DELETION_VALIDATION.md)，替代早期 90 天/凭据类型及历史清理规则 |
| 能力发展 | [current 与追问](DEVELOPMENT_CURRENT_VALIDATION.md)，confirmed 不参与业务 |
| 范围与错误 | [Scope Gate](SCOPE_GATE_VALIDATION.md)、[错误处理](ERROR_HANDLING_VALIDATION.md) |
| 课程与实验 | [资源精简](RESOURCE_CENTER_VALIDATION.md)、[华为云导入](HUAWEI_RESOURCE_IMPORT.md)；案例后续规则以 schema 17 资料文档为准 |
| 公共交互 | [分页](PAGINATION_VALIDATION.md)、[反馈](FEEDBACK_VALIDATION.md) |
| 平台兼容 | [ARM 验证](ARM_VALIDATION_REPORT.md)，只证明标注的历史提交；本轮没有部署或 ARM 验证 |
| 旧提交与 Pilot | [09-25 收口](GIT_CLOSEOUT_20260925.md)、[Pilot 归档](PILOT_ARCHIVE_20260925.md) |

## 统一口径

- 自动化只用专用 `banfei_agent_test` / `banfei_validation` 的临时 schema，上传及 SQLite 兼容夹具只用 `/tmp`；禁止使用正式库执行测试。
- 正式后端入口为 `.venv/bin/python scripts/run_postgres_validation.py backend -q`；先在当前进程私密加载 `BANFEI_TEST_DATABASE_URL`，不能打印连接串。
- PostgreSQL 验证入口包含项目原有 SQLite 兼容/迁移/进程测试，不能把所有用例都称作 PostgreSQL 原生测试。
- 88 项 archived Pilot 测试不属于当前支持范围，不计入正式通过数；历史失败不改写成通过。相关历史脚本和文档保留，不恢复旧业务流程。
- UI / replay / 真实模型请求分别记录；本轮工程收口不调用真实模型。测试通过不等于人工业务验收或部署授权。
- 当前库已完成 schema 17 迁移和授权的伙伴名单整理；文档中的迁移命令是其他旧环境升级说明，不是重复执行要求。
