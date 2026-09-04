# 灵鉴 Agent 发布前验证计划

## 1. 目标与范围

本轮验证面向当前单体 MVP，覆盖安全、用户隔离、任务可靠性、SQLite 迁移、文件处理、前端异常收敛、浏览器 E2E、视觉回归、生产构建和启动验证。保持 Next.js 15、React 19、FastAPI、Python 与 SQLite，不引入额外基础设施。

不在范围内：生产部署编排、复杂 RBAC、多实例共享限流、正式伙伴健康度算法、模型配置或业务场景绑定调整。

## 2. 数据与工作区保护

- 真实数据库 `data/app.db` 只做只读基线与终检。
- migration replay 使用 `data/app.db.bak-before-task-hardening-v9-20260904` 的临时副本。
- pytest 每个用例使用独立临时数据库和上传目录。
- Playwright 固定使用 `/tmp/lingjian-agent-e2e`，运行前带路径安全检查并重新建库。
- crash injection 只终止测试自身启动的 Uvicorn PID，使用随机端口。
- 真实模型验收使用真实库的 `/tmp` 副本及合成账号，不写真实库。
- 不修改模型地址、模型名、API Key、默认模型或业务场景绑定，不输出任何真实密钥。
- 开始前记录 branch、HEAD、工作区状态；无法提交 checkpoint 时保留 binary diff、未跟踪清单和源码归档。

## 3. 风险分级

| 级别 | 风险 | 发布要求 |
|---|---|---|
| P0 | 固定或弱 JWT secret、默认管理员密码、后端权限绕过 | 必须修复并自动验证 |
| P0 | A/B 任务及关联数据越权 | 必须通过完整权限矩阵 |
| P0 | v9 迁移丢数据或新增 FK 异常 | 必须通过副本回放及幂等检查 |
| P0 | matching/enriching 崩溃后永久锁死、失败任务不能重试 | 必须通过状态机及真实进程故障注入 |
| P1 | 账号申请造成批量 bcrypt/SQLite 写入 | 单实例内存限流、重复与 pending 上限 |
| P1 | 上传无限读入、伪造 Office 文件、删除不一致、预览注入 | 流式上限、签名检查、删除顺序、HTML/CSP |
| P1 | 断网/5xx 导致永久 loading、空白页或未处理 Promise | 请求超时、错误提示、重试入口、浏览器验证 |
| P2 | 多实例共享限流、可信代理 IP、历史 case 外键孤儿 | 记录限制，不扩大 MVP 架构 |

## 4. 测试身份与数据

测试库创建以下合成身份，统一使用测试专用强密码和 JWT secret：

| 身份 | 角色/状态 | 验证用途 |
|---|---|---|
| admin1 / admin2 | 管理员、启用 | 全量视图、并发审批、最后管理员保护 |
| user_a / user_b | 普通用户、启用 | A/B 隔离矩阵、会话失效、任务重试 |
| user_first_login | 普通用户、强制改密 | 首次登录门禁 |
| user_disabled | 普通用户、停用 | 登录和 Token 失效 |
| user_locked | 普通用户、锁定 | 锁定与管理员解锁 |

A/B 各创建 ready、failed、partial、archived 四类任务，并建立需求画像与项目机会关联数据。

## 5. 自动化矩阵

### 5.1 认证与账号

- AUTH-001～005：密钥加载/轮换、历史密钥伪造失败、缺失密钥拒绝启动、无默认管理员、bootstrap 首次改密。
- AUTH-010～021：登录、五次失败锁定、锁定期拒绝、解锁、首次改密门禁、改密/重置/停用/改角色后的旧 Token 失效、自操作保护、最后管理员保护。
- APPLICATION-001～007：公开申请、bcrypt 且无明文、用户名/联系方式重复、批准/驳回、并发批准、频率限制。
- pending application 数量上限额外覆盖。

### 5.2 授权与 OpenAPI

| 操作 | A 自己 | A 访问 B | 管理员 |
|---|---:|---:|---:|
| active/archived task list | 200，仅本人 | 不出现 | 200，全部 |
| task detail + demand/opportunity | 200 | 404 | 200 |
| archive / restore | 成功 | 404 | 按管理员权限成功 |
| failed / partial retry | 成功 | 404 | 按管理员权限成功 |
| opportunity edit | 成功 | 404 | 按管理员权限成功 |

扫描 OpenAPI 全部 operation；公开面仅允许 `GET /health`、`POST /auth/login`、`POST /auth/user-applications`。普通用户逐一请求所有 `/admin/*` operation，必须返回 403。

### 5.3 任务与进程故障

- partner match 首次失败后任务保留为 failed 且可重试。
- enrichment 局部失败后推荐保留、任务为 partial。
- failed retry 完成；partial retry 复用有效推荐，只补后续阶段。
- retry 不重复产生需求画像、项目机会和建议垃圾数据。
- 10 路并发 retry 只有一个取得执行权，其余合理冲突。
- archive 与 retry 并发后状态一致。
- 空推荐 partial 及推荐持久化失败均强制重新 matching。
- 用 slow fake LLM 分别在 matching/enriching 阶段 kill 测试后端，重启后恢复为 `failed + interrupted`，随后 retry 完成。

### 5.4 数据库迁移

1. 复制 v8 备份到 pytest 临时目录。
2. 记录核心表数量、integrity、foreign key violations。
3. 执行当前初始化迁移，验证 schema v9、48 条任务 owner 非空、核心数量不变。
4. 再次初始化，验证完全幂等。
5. 任务相关表不得出现 FK 异常；历史 `cases` rowid 3/4 孤儿单列为 existing violations。

### 5.5 文件接口

- 正常 DOCX 上传、解析及磁盘落盘。
- 上传上限边界：等于上限成功，超过 1 byte 返回 413 且清理部分文件。
- 伪造 PPTX 扩展名拒绝进入解析器。
- DB 有记录但磁盘文件缺失时，下载/预览返回 404、删除可收敛。
- 注入 DB 删除失败时磁盘文件保留，避免形成悬挂 DB 记录。
- PPTX 文本中的 `<script>` / `<img onerror>` 被 HTML escape，预览返回限制性 CSP。

### 5.6 前端 E2E 与异常状态

- 登录页；账号申请 → 审批 → 首次登录 → 强制改密。
- A/B 各自任务、A 直输 B URL、普通用户访问管理后台、管理员查看 A/B 与用户管理。
- 停用和改密后的旧 session 失效；failed task retry；ready retry 返回 409。
- 401、403、404、409、500、502、network error、timeout/backend unavailable。
- 检查工作台、任务列表/详情、后台概览、用户/伙伴/项目机会/模型配置页：错误可见、loading 结束、存在重试入口、无 pageerror。

### 5.7 视觉、构建与真实模型

- 1920×1080、1440×900、1366×768、1024×768。
- 登录、普通用户首页、场景广场、我的任务、任务详情、后台首页、用户管理、伙伴管理，共 32 张截图。
- 断言 document 无页面级横向溢出，并人工抽检侧栏、卡片、表格和文本截断。
- 执行 `compileall`、`pytest`、`tsc --noEmit`、Next.js production build、FastAPI startup、`/health`、OpenAPI。
- 所有 mock 测试通过后，仅执行一次真实模型业务 E2E；检查 owner、状态、推荐及三类衍生数据，并验证 B=404、admin=200。

## 6. Release Gate

以下任一真实 FAIL 均为 NO-GO：JWT/默认管理员安全、A/B 列表/详情/写操作隔离、普通用户 admin API 拒绝、旧 Token 失效、v9 迁移与 FK、failed/partial retry、matching/enriching crash recovery、空推荐修复、并发 retry、production build、后端启动/health、核心 E2E。

仅真实模型等外部环境受阻且其它核心项通过时可为 CONDITIONAL GO；全部核心项和真实模型受控验收通过时可为 GO。
