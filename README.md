# 伴飞 Agent

伴飞 Agent 面向公司内部业务人员，提供“项目找伙伴”和“能力发展”两条主线。当前主干为 `main`，正式工作区为 `/home/yuan/project/lingjian-agent-enablement`。工程名、模块名、API 和 `LINGJIAN_*` 环境变量保留原技术标识。

## 当前入口与能力

左侧导航：开启新任务、场景广场、伙伴洞察、资源中心、全部任务与历史任务、个人中心、管理后台。

- **开启新任务**：两个显式 Tab“项目找伙伴 / 能力发展”，不自动猜测业务模式。
- **项目找伙伴**：输入项目需求，自动使用伙伴已有能力标签、标准行业/区域、AI 画像摘要、案例标题/简短摘要和交付物名称。缺资料时降级，不要求人工补录；现有交付物没有独立摘要字段，不读取原附件或增加字段。画像截取上限 3000 字符、单案例摘要上限 500 字符。输出推荐、匹配分、理由、归属校验后的证据和风险，并沉淀需求画像、项目机会。
- **能力发展**：伙伴 + 自然语言方向即可生成建议；结合画像和真实候选资源，支持解释、比较和自然语言调整。解释不创建新版本，成功调整创建新 Version；失败不覆盖已有可用建议。历史版本、采用版本、运行记录为二级操作。
- **场景广场**：“伙伴能力短板分析”直接进入能力发展；伙伴能力/画像/案例查询是伙伴洞察的快捷入口，不是三套新 Agent。需求画像、项目机会随匹配生成。
- **资源中心**：独立浏览课程、实验、已发布共享案例，提供搜索、筛选、详情与来源跳转；跳转不代表学习完成或能力提升。
- **统一任务**：项目匹配与能力发展共用任务历史。每个 Plan 只计一项任务，多次 Run 不重复计数。后台累计/本月任务同时给出两类数量，保留归档任务在累计统计中；月份沿用 UTC 创建时间口径。
- **管理后台**：伙伴及资料维护、案例共享、课程实验发布/人工核验、任务、需求画像、项目机会、现有运营报表、标签、用户、模型和系统状态。
- **系统状态**：只读检查配置与数据。能力发展使用实际执行的模型选择规则，并读取最近一次 Run 状态和可计算的起止耗时；无记录显示“暂无运行记录”。不主动调用模型，不以历史成功保证当前模型连通。

## 页面

| 路径 | 功能 |
|---|---|
| `/login` | 登录；点击“注册”进入公司内部账号申请表 |
| `/` | 开启新任务：项目找伙伴 / 能力发展 |
| `/?mode=development` | 直接激活能力发展，可携带伙伴、项目、共享案例上下文 |
| `/scenes` | 场景快捷入口 |
| `/partners`、`/partners/{id}` | 伙伴洞察与详情 |
| `/resources`、`/resources/{type}/{id}` | 资源中心与详情 |
| `/tasks`、`/tasks/{id}` | 两类任务的统一历史与详情 |
| `/account`、`/403` | 个人中心、无权限提示 |
| `/admin`、`/admin/tasks` | 后台概览、全量任务 |
| `/admin/partners`、`/admin/partners/{id}` | 伙伴、资料、案例、交付物与画像维护 |
| `/admin/resources` | 课程/实验管理 |
| `/admin/demands`、`/admin/opportunities`、`/admin/reports` | 需求画像、机会与现有运营统计 |
| `/admin/tags`、`/admin/users`、`/admin/users/{id}` | 能力标签、用户与审批审计 |
| `/admin/models`、`/admin/system` | 模型场景绑定、只读系统状态 |

`/enablement` 只保留书签兼容，跳转至统一任务入口或资源中心，不提供第二套用户工作台。案例共享维护复用伙伴管理中的案例入口。

## 技术与业务边界

- Next.js 15 / React 19 / TypeScript；FastAPI / Python；PostgreSQL 16 / SQLAlchemy Core / psycopg；本地上传存储；OpenAI-compatible 模型接口。
- 当前未接入 Embedding、Chroma、RAG、向量检索；Chroma 路径只是历史预留。
- 不包含 Redis、队列、微服务、复杂 RBAC、多租户或通用 Planner/Multi-Agent。
- 课程/实验只做目录与跳转，不提供 LMS、实验执行、完成率或能力认证。
- 健康度仍是临时实现，正式健康度等待外部平台，不自行扩展评分。
- 黑白灰为主、华为红 `#C7000B` 小面积强调，保留红色图标与“伴飞 Agent”字标。

## 权限与数据保护

- 仅 `GET /health`、`POST /auth/login`、`POST /auth/user-applications` 为公开业务 API；其他业务接口要求有效 Token，管理写接口在后端校验 admin。
- 保留 user/admin 两角色。匹配任务归属为 `match_records.owner_user_id`，能力发展归属为 `development_plans.owner_user_id`；普通用户越权访问任务及关联数据返回 404。
- 系统可见、模型可发送、伙伴可外发分别校验，不互相推导。能力发展原始附件/内部材料默认不发送模型，共享案例只使用当前获授权的已发布共享版本。
- 伙伴可传递视图只取 confirmed 版本，输出时重新校验授权、版本、资源状态并应用允许字段白名单。撤权不会改写审计历史。
- Plan / Run / Version、current / confirmed、幂等、并发冲突、事务原子性、超时、中断恢复和失败保留旧版本继续保留。
- 不删除、清空、重建或替换已有数据库；不清理上传资料。测试仅用 `/tmp` 隔离文件和独立 `banfei_validation` PostgreSQL 临时 schema，不在运行库执行 E2E。
- 不提交数据库、上传材料、私有快照、`.env`、密钥、Token 或原始敏感日志。

## 账号

登录页默认只展示登录；点击“注册”填写姓名、工号、部门、邮箱、用户名、密码、确认密码，申请说明选填。公司内部账号继续由管理员审批，审批后首次登录必须改密。管理员直接创建的临时密码仅展示一次。

保留密码不可逆哈希、审批后清除申请密码哈希、连续 5 次失败锁定 15 分钟、管理员解锁、最后一个有效管理员保护和会话即时失效。没有固定默认登录凭据。`JWT_SECRET_KEY` 必须显式配置且至少 32 位；空库首位管理员仅通过 `BOOTSTRAP_ADMIN_USERNAME` / 强 `BOOTSTRAP_ADMIN_PASSWORD` 引导，已有运行库不要重新引导。

## 当前本地环境

| 项目 | 当前值 |
|---|---|
| 工作区/分支 | `/home/yuan/project/lingjian-agent-enablement` / `main` |
| 前端 | http://localhost:3000 |
| 后端 | http://localhost:8000；匿名健康检查 `/health` |
| 本地 mock | `127.0.0.1:18180` |
| 数据库 | PostgreSQL 16：`banfei_agent`，应用账号 `banfei_app`；连接由私有 `DATABASE_URL` 提供 |
| SQLite 回退文件 | `.isolation/runtime/dev/app.db`（保留，不参与正常运行） |
| 上传目录 | `.isolation/runtime/dev/uploads` |
| 私有运行配置 | `.isolation/runtime/dev/environment.json` |
| 运行日志 | `.isolation/logs/` |

从当前工作区执行：

```bash
bash enablement-dev.sh status
bash enablement-dev.sh start
bash enablement-dev.sh stop
```

启动器继续使用已有私有配置和运行库；不得用通用 `dev.sh` 或手动启动方式绕过当前隔离配置，不重新安装/初始化环境。启动前确认本地 mock 可用；启动器不负责重新创建 mock 数据。

旧环境仅作为 legacy 保留，服务保持停止；保留 `legacy/pre-v1.2-main` 和 `v1.1-legacy`，不修改其目录、数据库或指针。

当前数据库由私有配置中的 `DATABASE_URL` 显式指定；缺失或连接失败直接报错，不自动回退 SQLite。`LINGJIAN_UPLOADS_DIR` 保留现有上传路径；`LINGJIAN_DATABASE_PATH` 仅供显式 SQLite 兼容测试或人工回退，不是 PostgreSQL 的数据路径。

### PostgreSQL 与一次性迁移

PostgreSQL 16 来自 Ubuntu 24.04 官方 apt 源，使用专用非超级用户 `banfei_app`。连接串形如 `postgresql+psycopg://banfei_app:<密码>@127.0.0.1:5432/banfei_agent`，实际值仅存在被忽略的私有运行配置中。现有 32 张表由 `backend/app/storage_models.py` 映射；保留 v12 字段、ID、约束、JSON 文本、ISO 时间和 0/1 标志，不引入 Alembic。

`scripts/migrate_sqlite_to_postgres.py --source <SQLite路径> --evidence-dir <新的私有证据目录> --apply` 使用进程环境中的 PostgreSQL `DATABASE_URL`，仅接受空目标库。工具先用 SQLite backup API 保存快照，检查完整性/外键，再在一个 PostgreSQL 事务中建表、按依赖导入、校正已有 identity sequence（如有）并逐表对账行数和内容 SHA-256；失败回滚目标事务，不覆盖已有 PostgreSQL 表，不写源 SQLite。当前业务主键都是 UUID 文本，没有需要重新编号的业务 sequence。

SQLite 原文件与 `.isolation/postgres-migration/` 下的一致性备份保留。回退必须先停服务并确认 PostgreSQL 切换后是否产生新增数据，不能直接切回旧快照丢弃新数据。经确认后才可显式设置 `DATABASE_URL=sqlite://` 和指定保留的 SQLite 路径；启动器不会自行回退。

## 模型

当前开发环境使用本地 mock，隔离启动器阻止外部模型网络请求。没有新的明确授权，不调用真实模型、不更改场景绑定或真实模型配置。

- 原匹配等场景：场景绑定 → 默认场景绑定 → 启用的默认模型 → 首个启用模型 → 环境变量；显式绑定无效时报错。
- 能力发展：场景绑定 → 默认场景绑定 → 唯一启用的默认模型；没有有效选择时报错，不回退到首个启用模型。外部调用另受 `LINGJIAN_ALLOW_REAL_DEVELOPMENT_MODEL` 门禁约束，不能擅自开启。
- 模型候选 ID、版本、URL、权限与结构化输出仍由程序校验。画像摘要不等于新的可信证据，资料缺失不等于没有能力。
- 不向用户展示 Prompt、原始模型 JSON、密钥或异常堆栈。

## 主要代码与接口

- `backend/app/routers/match.py`：项目匹配、统一任务查询、后台任务统计。
- `backend/app/development_*.py`：能力发展执行、上下文、版本、权限、超时与模型适配。
- `backend/app/enablement*.py`：资源、共享案例、发布核验、目录检索与引用。
- `frontend/lib/scenes.ts` / `skills.ts`：轻量场景和能力描述，不是执行编排平台。
- `scripts/validate_pilot_data.py` / `import_pilot_data.py`：历史 SQLite Pilot 预检与原子导入工具，不可对当前 PostgreSQL 运行库使用；本轮未扩大这些工具范围。机器导入通过不等于业务签审通过。
- `POST /agent/tasks`：创建匹配任务；`GET /agent/tasks`：统一任务列表；`GET /agent/tasks/{id}`：任务详情；原同步匹配接口保留兼容。
- `/development/plans`：能力发展生成、解释/调整、确认、历史与归档。
- `/enablement/resources`：资源目录；`/admin/dashboard`、`/admin/system/status`：统计与状态。
- 完整接口契约以当前 FastAPI `/docs`、`/openapi.json` 和代码为准，不沿用历史文档中的接口数量。

## 验证

沿用现有 `.venv` 和 `frontend/node_modules`。测试必须使用合成数据与 mock，不调用真实模型。全量 pytest 的进程恢复测试及 Playwright 共用服务端口；开发服务、构建与 Playwright 共用 `.next`，不能并行运行。

先确认当前项目进程归属，再停止当前前后端和测试端口上的本地 mock。按顺序执行：

```bash
.venv/bin/python -m pytest -q
cd frontend
npm run typecheck
npm run build
cd ..
.venv/bin/python scripts/run_postgres_validation.py browser
```

后端全量测试中，普通业务测试使用 PostgreSQL 临时 schema；原 SQLite 原生迁移、Pilot 文件工具和 SQLite 故障注入测试保留临时 SQLite，JUnit 标记实际后端。直接运行 pytest 未配置验证库时只覆盖 SQLite 兼容路径，不能据此声称 PostgreSQL 验收通过。

Playwright 使用独立 PostgreSQL 临时 schema，`/tmp/lingjian-enablement-e2e` 仅存合成数据中间文件、临时凭据与上传。验证脚本仅接受本机 `banfei_validation`，为浏览器创建独立 schema 并在退出后清理该 schema，不触碰 `banfei_agent`。必须启动测试库对应的服务，不复用日常运行库。验证完成后恢复本地 mock 和当前 main 的 3000/8000，不启动 legacy。

## 交付状态与历史资料

两条主业务线及资源/权限/版本底座已实现；真实业务资源、真实模型效果和业务验收需分别确认，不能用合成测试数据或 mock 结果代替。历史阶段报告仅记录当时的状态与验证，不是当前配置说明。

- [V1.2 交付记录](V12_REFACTOR_DELIVERY_REPORT.md)
- [Phase D 工程记录](PHASE_D_DELIVERY_REPORT.md)
- [Pilot 导入准备](PILOT_IMPORT_READINESS_REPORT.md)
- [最早 MVP 说明](docs/product-spec.md)（历史范围）

本地直接在 main 迭代。未经明确要求不提交、不 push、不部署，不创建分支或 worktree。
