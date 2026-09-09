# 伴飞 Agent

面向公司内部人员的伙伴智能助手，提供“项目找伙伴”和“能力发展”两条主线。正式工作目录为 `/home/yuan/project/lingjian-agent-enablement`，直接在 `main` 开发。工程名、模块名、API 和 `LINGJIAN_*` 环境变量保留技术标识。

## 主要功能与入口

| 入口 | 当前功能 |
|---|---|
| `/` 开启新任务 | 显式“项目找伙伴 / 能力发展”两个 Tab；不自动猜测业务模式 |
| 项目找伙伴 | 项目需求 → 使用现有标签、行业/区域、画像摘要、案例摘要及交付物名称匹配 → 推荐/理由/证据/风险 → 需求画像、项目机会 |
| `/?mode=development` 能力发展 | 伙伴 + 自然语言方向 → 顾问式建议、资源与缺口 → 解释、比较或自然语言调整 |
| `/scenes` 场景广场 | 发现并进入已有能力；能力短板分析进入能力发展，伙伴能力/画像/案例查询进入伙伴洞察 |
| `/partners`、`/partners/{id}` | 伙伴洞察、画像与资料；制定发展建议时带入伙伴上下文 |
| `/resources`、`/resources/{type}/{id}` | 独立课程/实验/共享案例目录，搜索、筛选、详情和发起来源跳转 |
| `/tasks`、`/tasks/{id}` | 两类任务共用历史；创建后即出现，真实状态更新，首批 10 条、独立滚动与加载更多 |
| `/login`、`/account` | 登录、内部账号申请与个人中心 |
| `/admin/*` | 任务、伙伴/资料/案例共享、资源发布核验、需求画像、项目机会、运营报表、标签、用户、模型、系统状态 |

伙伴详情、匹配结果和共享案例中的发展入口都汇入统一新任务页，并带入允许的来源上下文。`/enablement` 仅保留兼容跳转，不提供另一套用户工作台。

- 匹配资料有多少用多少，不要求人工整理或补齐；交付物使用已有名称，不新增摘要字段。画像上下文最多 3000 字符，单案例摘要最多 500 字符。
- 能力发展解释/讨论不生成版本；修改成功产生新 Version。草稿可直接查看、打开资源和继续问伴飞。历史、采用版本、运行记录为二级操作，不展示普通用户高级编辑入口。
- 失败调整保留已有建议；任务原因区分超时、配置、结构、保存和中断等问题。项目机会抽取兼容常见格式差异，无法提取的字段记“未知”，不把未知计为完整信息。机会库支持紧凑多选筛选、重置和展开详情。
- 伙伴启用/停用保留历史；管理员仅可删除无业务历史的误建伙伴，有关联时返回阻止原因及数量。
- 行业与区域使用 [唯一标准字典](shared/business-taxonomy.json)，支持多选及同时覆盖国内/海外；未知旧分类保留待确认。
- 统计同时包含两类任务，一份 Plan 只算一项；系统状态读取配置和最近执行记录，不主动调用模型。

## 技术与安全边界

Next.js 15 / React 19 / TypeScript；FastAPI / Python；**PostgreSQL 16 / SQLAlchemy Core / psycopg，schema version 12**；本地上传存储；OpenAI-compatible 模型接口。无 Alembic；未接入 Chroma、Embedding、向量库、RAG 检索、队列或微服务。

保留 `user/admin`、后端管理权限和任务 owner 隔离。内部注册仍须管理员审批、首次改密；没有固定默认凭据。系统可见、模型可发送、伙伴可外发分别校验；共享案例使用当前授权共享版本。伙伴可传递视图只取 confirmed 版本并实时重检权限，不输出内部诊断或备注。

Plan / Run / Version、current / confirmed、幂等、版本冲突、事务、超时、中断及撤权保护继续保留。资源跳转不等于学习完成；没有 LMS 或正式能力认证。健康度仍等待外部平台，不自行扩展评分。

视觉保持黑白灰 + 华为红 `#C7000B`、现有红色图标和伴飞 Agent 字标；Latin/数字 Web Font 从本地加载，中文按系统 fallback。字体二进制不进 Git，换机器按 [字体来源与复现说明](docs/design/HUAWEI_CLOUD_FONT_SOURCES.md) 获取；不要重新设计 Logo。

## 当前本地运行

| 项目 | 当前配置 |
|---|---|
| 系统 / 工作区 / 分支 | WSL Ubuntu 24.04 / `/home/yuan/project/lingjian-agent-enablement` / `main` |
| 前端 / 后端 | http://localhost:3000 / http://localhost:8000 |
| 后端健康检查 | `GET /health` |
| PostgreSQL 库 / 用户 | `banfei_agent` / `banfei_app`（PostgreSQL 16） |
| 私有配置 | `.isolation/runtime/dev/environment.json`，包含 `DATABASE_URL` |
| 上传 / 日志 | `.isolation/runtime/dev/uploads` / `.isolation/logs/` |
| 原 SQLite 与备份 | `.isolation/runtime/dev/app.db`、`.isolation/postgres-migration/`，保留、不参与正常运行 |

```bash
cd /home/yuan/project/lingjian-agent-enablement
bash enablement-dev.sh status
bash enablement-dev.sh start
# 需要停止当前服务时：
bash enablement-dev.sh stop
```

复用已有 `.venv`、`frontend/node_modules`、配置和运行数据，不重新初始化。legacy 目录、旧 feature 分支及历史 worktree 不得作为正式开发环境，legacy 服务保持停止。

同一代码已做 ARM64 兼容：可用 `NEXT_PUBLIC_API_BASE_URL=/api` 配合 `BANFEI_API_PROXY_TARGET` 使用同源代理，`BANFEI_BUILD_CPUS=1` 限制小机器构建并发；本地当前仍直连后端。见 [ARM 验证范围](docs/validation/ARM_VALIDATION_REPORT.md)。Git push 不自动更新 ARM 服务。

## 数据库与迁移

- `DATABASE_URL` 显式选择 PostgreSQL，缺失或连接失败直接报错；不自动回退 SQLite。不要用旧 SQLite 快照覆盖切换后的新增数据。
- 32 张表的映射位于 [storage_models.py](backend/app/storage_models.py)。保留现有 UUID、外键、JSON 文本、时间和标志字段；当前 schema version 为 12。
- `match_records.last_error_details` 是 v12 内已落地的可空增量列；当前环境已完成迁移，不因阅读文档再次执行。
- [SQLite → PostgreSQL 工具](scripts/migrate_sqlite_to_postgres.py) 只用于经授权的一次性迁移：SQLite backup API、原库只读、空目标库、事务导入和逐表对账。
- [任务错误详情迁移工具](scripts/migrate_task_failure_details.py) 先 `pg_dump`，再事务加列和校验；不能替代业务数据备份策略。
- 禁止删除、清空、重建、重新 seed、随意替换任何现有数据库、上传目录或私有备份。必要变更须先核验实际目标，提供备份、事务与回退方案。
- 历史 Pilot 文件工具只兼容 SQLite，不能对当前 PostgreSQL 运行库使用；见 [兼容工具说明](pilot-data/README.md)。

## 模型配置

日常业务及人工体验使用已批准的 **`api.deepseek.com` / `deepseek-v4-flash`**。七个场景：`default`、`partner_profile`、`partner_match`、`demand_profile`、`tag_suggestion`、`recommendation_summary`、`partner_development`，均显式绑定现有启用配置。

用户已授权按现有权限发送所需伙伴资料/画像、案例说明、项目需求、对话及授权资源，伙伴画像生成包括上传文档提取文本。能力发展仍按最小上下文排除内部附件和案例原文。不擅自改模型、Key、默认绑定或供应商，不自动批量处理业务材料。

本地 mock 不参与日常运行；历史配置已停用但因历史 Run 引用保留。仅隔离单元故障注入和显式 replay 使用测试桩。

原匹配等场景保留既有 default/环境兼容回退；显式无效绑定报错。能力发展按场景绑定 → default 场景绑定 → 唯一启用默认模型选择，不取首个启用模型。DeepSeek 当前适配为 `json_object` + 完整 schema 提示，关闭该模型思考输出；最终仍做程序结构、ID/URL、权限及强结论来源校验。不展示 Prompt、原始响应或凭据。

真实模型已获授权并已有调用；不沿用早期零调用结论。每次新增验证须限定范围、记录次数；普通 UI/文档工作不调用模型。执行前检查和验证计划见 [模型前检](docs/validation/REAL_MODEL_PRECHECK.md)、[真实模型验证](docs/validation/REAL_MODEL_VALIDATION_PLAN.md)。

## 测试

私有 `BANFEI_TEST_DATABASE_URL` 必须指向本机专用 `banfei_validation`，不能使用运行库连接串。PostgreSQL 用临时 schema；SQLite 兼容/迁移测试和上传夹具仅在 `/tmp`。全量或进程恢复/E2E 测试会占服务端口，先核对并停止当前服务，结束后只恢复 main，不启动 legacy 或遗留模型夹具。

```bash
# 私有 BANFEI_TEST_DATABASE_URL 已由环境提供后，在仓库根目录：
.venv/bin/python scripts/run_postgres_validation.py backend -q
npm --prefix frontend run typecheck
npm --prefix frontend run build

# 无模型的默认 UI 子集（不是完整浏览器套件）：
.venv/bin/python scripts/run_postgres_validation.py browser

# 完整隔离生命周期/故障回放：
PLAYWRIGHT_MODEL_MODE=replay .venv/bin/python scripts/run_postgres_validation.py browser
```

- 开发、build、Playwright 不得同时写同一 `.next`；可在独立构建目录验证。
- 默认 UI 子集以 [Playwright 配置](frontend/playwright.config.ts) 的 `testMatch` 为准，不在文档写固定数量。`opportunity-ui.spec.ts` 已单独验证，尚不在默认子集中；完整 replay 会包含它。
- 未配置 PostgreSQL 验证库的普通 pytest 可能仅验证 SQLite 兼容路径，不能据此宣布 PostgreSQL 全量通过。
- 真实接口 smoke 使用现有 `scripts/verify_real_model.py`，最多两次合成请求；不读伙伴附件，不建业务任务。故障回放与真实供应商测试分别记录。
- 版本化测试记录仅证明对应提交/范围；工程、真实模型兼容、真实资源与业务验收分别判断，不相互替代。业务样例填写 [现行业务验收模板](docs/validation/REAL_BUSINESS_ACCEPTANCE_TEMPLATE.md)，不由工具代填结论。

## 文档边界

[AGENTS.md](AGENTS.md) 是当前开发约束；`docs/validation/` 是当前验证方法/模板及明确标注基线的兼容记录，`docs/design/` 是设计与字体取证。`docs/archive/v1.1/` 保存早期 MVP、Phase A–D、RC/Pilot 历史；`docs/archive/v1.2/` 保存 V1.2 改版与归档记录。历史中的品牌、端口、分支、数据库、授权与测试数字不是当前状态，旧报告生成脚本也不是现行运行入口。

默认只在 main 做最小改动；未经明确要求不 commit、push、部署、创建分支或 worktree，不丢弃已有修改，不提交数据或凭据。
