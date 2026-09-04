# 灵鉴 Agent

灵鉴 Agent 是面向公司内部人员的伙伴能力洞察与项目需求匹配平台。普通用户可以提交项目需求、获得有证据支撑的伙伴推荐并持续跟进自己的任务；管理员在独立后台维护伙伴、用户、需求运营数据、能力标签、模型配置和系统状态。

当前版本为单机 MVP，运行于 WSL Ubuntu，采用 Next.js + FastAPI + SQLite，不包含面向外部伙伴的开放访问能力。

## 当前能力

- **灵鉴助手工作台**：输入自然语言项目需求，生成伙伴推荐、匹配分、推荐理由、支撑案例、支撑交付物及风险或缺口。
- **用户级任务隔离**：普通用户只能查看和操作自己创建的任务及其需求画像、项目机会；管理员可以查看全部用户任务。
- **任务生命周期**：支持匹配中、信息补全中、已完成、部分完成、失败状态，以及归档、恢复和失败重试。
- **场景广场**：提供按行业找伙伴、按能力找伙伴、伙伴能力查询、伙伴案例查询等预置入口。
- **伙伴洞察**：普通用户只读查看伙伴资料、AI 能力画像、案例和交付证据。
- **独立管理后台**：集中管理伙伴、任务、需求画像、项目机会、运营报表、能力标签、用户、模型和系统状态。
- **完整用户管理**：支持登录页申请账号、管理员审批或驳回、管理员直接创建、角色与状态管理、密码重置、账号解锁和审计日志。
- **运行安全加固**：强制 JWT 密钥、首次改密、登录失败锁定、会话失效、上传大小限制、文件类型校验和异常任务恢复。

## 技术栈

- Frontend：Next.js 15、React 19、TypeScript
- Backend：FastAPI、Python 3.11+
- Database：SQLite（默认 `data/app.db`）
- File Storage：本地目录（默认 `data/uploads`）
- AI：OpenAI 兼容接口，由 `httpx` 调用，支持按业务场景绑定模型
- Test：pytest、Playwright

## 页面与角色

### 公共页面

| 路径 | 功能 |
|---|---|
| `/login` | 账号登录、公司内部账号申请 |
| `/403` | 无权限提示 |

### 普通用户工作区

| 路径 | 功能 |
|---|---|
| `/` | 开启新的伙伴匹配任务 |
| `/scenes` | 浏览和进入业务场景 |
| `/tasks` | 查看、筛选、归档和恢复自己的任务 |
| `/tasks/{id}` | 查看自己的推荐结果、需求画像和项目机会，处理失败重试 |
| `/partners` | 只读浏览伙伴能力与画像 |
| `/partners/{id}` | 只读查看伙伴详情、案例与交付物摘要 |
| `/account` | 查看账号信息、修改显示名称和密码、注销全部会话 |

### 管理后台

| 路径 | 功能 |
|---|---|
| `/admin` | 管理概览 |
| `/admin/tasks` | 查看全部用户任务 |
| `/admin/partners` | 伙伴资料管理 |
| `/admin/partners/{id}` | 伙伴详情、案例、交付物、文档和 AI 画像维护 |
| `/admin/demands` | 全量需求画像 |
| `/admin/opportunities` | 项目机会运营 |
| `/admin/reports` | 运营报表 |
| `/admin/tags` | 能力标签、分类和 AI 标签建议 |
| `/admin/users` | 用户、账号申请和审计日志管理 |
| `/admin/users/{id}` | 用户详情 |
| `/admin/models` | 模型连接与业务场景绑定 |
| `/admin/system` | 数据库、模型和业务能力状态 |

管理员也可以返回普通用户工作区使用灵鉴助手；普通用户访问 `/admin/*` 时会被拒绝。

## 权限与数据隔离

- 除健康检查、登录和账号申请外，所有 API 都要求 Bearer Token。
- 所有 `/admin/*` API 都在后端执行管理员权限校验，前端隐藏菜单不是安全边界。
- 匹配任务通过 `owner_user_id` 归属用户；普通用户的列表、详情、归档、恢复、重试及项目机会更新均校验所有权。
- 普通用户越权访问其他用户任务时返回 404，避免泄露任务是否存在；管理员可通过后台查看全量数据。
- 普通用户只能读取启用状态的伙伴及其案例、交付物摘要；伙伴、案例、交付物、文档和画像写操作仅限管理员。
- 用户停用、角色变更、密码修改、管理员重置密码或“注销全部会话”后，旧 Token 会立即失效。
- 连续 5 次密码错误会锁定账号 15 分钟，管理员可在用户管理中解锁。
- 系统禁止管理员停用或降级自己，也禁止停用或降级最后一个有效管理员。

## 账号申请与首次登录

1. 公司内部人员在 `/login` 切换到“申请账号”，填写姓名、用户名、部门、企业邮箱或工号及密码。
2. 系统只保存密码的不可逆哈希，并限制同一来源的申请频率、重复用户名或联系方式以及待审批总量。
3. 管理员在“用户管理 → 账号申请”中批准或驳回申请。
4. 审批通过后，申请人使用申请时设置的密码登录，并按提示完成一次密码更新。
5. 管理员也可以直接创建账号；系统仅在创建结果中展示一次临时密码，用户首次登录后必须修改。

## 项目结构

```text
.
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI 入口、CORS、启动初始化
│   │   ├── config.py               # JWT、数据库与存储路径配置
│   │   ├── auth.py                 # 密码、JWT、用户与管理员依赖
│   │   ├── database.py             # SQLite schema、迁移与中断任务恢复
│   │   ├── ai_client.py            # OpenAI 兼容模型客户端
│   │   ├── model_resolver.py       # 业务场景模型解析（数据库优先、环境变量回退）
│   │   ├── file_storage.py         # 流式上传、大小和文件内容校验
│   │   ├── doc_extractor.py        # PDF、DOCX、PPTX、XLSX 文本抽取
│   │   ├── models.py               # Pydantic 数据模型
│   │   └── routers/                # 认证、伙伴、匹配、需求和管理接口
│   ├── tests/                      # 后端、权限、迁移、文件与故障恢复测试
│   ├── scripts/                    # 测试支持与伙伴种子数据脚本
│   ├── requirements.txt
│   └── requirements-dev.txt
├── frontend/
│   ├── app/                        # 普通用户、登录和 /admin 管理页面
│   ├── components/                 # 导航、认证、任务列表和后台面板
│   ├── e2e/                        # Playwright 发布验收用例
│   ├── lib/scenes.ts               # 场景注册表
│   ├── lib/skills.ts               # 业务能力注册表
│   ├── package.json
│   └── playwright.config.ts
├── data/
│   ├── app.db                      # 真实 SQLite 数据库，请勿覆盖
│   ├── uploads/                    # 上传文件，请勿清理
│   └── chroma/                     # 预留目录，当前未接入 Chroma
├── docs/
│   ├── product-spec.md
│   └── validation/                 # 发布验证计划与报告
├── artifacts/validation/           # 多分辨率界面验收截图
├── dev.sh                          # 本地服务生命周期脚本
├── pytest.ini
└── AGENTS.md
```

## 环境要求

- WSL Ubuntu 24.04 或兼容 Linux 环境
- Node.js 18.18 或更高版本
- npm 9 或更高版本
- Python 3.11 或更高版本
- `curl`、`fuser`、`setsid`（使用 `dev.sh` 时需要）

## 首次配置

### 1. 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

cd frontend
npm install
cd ..
```

### 2. 创建环境文件

```bash
cp .env.example .env
cp frontend/.env.local.example frontend/.env.local
```

`.env` 至少需要配置安全的 JWT 密钥和实际使用的模型连接信息：

```dotenv
JWT_SECRET_KEY=使用安全随机源生成的至少32位密钥
LLM_API_KEY=你的模型API密钥
LLM_BASE_URL=https://your-openai-compatible-endpoint/v1
LLM_MODEL=模型名称
```

可以使用下面的命令生成 JWT 密钥：

```bash
openssl rand -hex 32
```

不得提交 `.env` 或任何真实 API Key。项目会拒绝空值、短于 32 位或历史默认值形式的 `JWT_SECRET_KEY`。

### 3. 仅为空数据库创建首位管理员

仅当 `users` 表完全为空时，在 `.env` 中临时配置：

```dotenv
BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_PASSWORD=至少12位且同时包含字母和数字的强密码
```

后端首次初始化后会创建管理员并要求首次改密。已有用户的数据库不需要这两个变量，项目也不再内置固定管理员密码。

## 启动与停止

推荐在项目根目录使用服务脚本：

```bash
bash dev.sh start
bash dev.sh status
bash dev.sh logs
bash dev.sh restart
bash dev.sh stop
```

`bash dev.sh` 等价于 `bash dev.sh start`。脚本只复用或停止工作目录属于本项目的 3000/8000 端口进程，不会直接清理其他项目进程。

启动成功后访问：

- 前端：http://localhost:3000
- 后端健康检查：http://localhost:8000/health
- Swagger API 文档：http://localhost:8000/docs

也可以分别启动：

```bash
source .venv/bin/activate
python -m uvicorn app.main:app --app-dir backend --reload --host 0.0.0.0 --port 8000
```

另开终端：

```bash
cd frontend
npm run dev
```

> 在受限沙箱中，端口绑定或本机健康检查可能被禁止；这属于运行环境限制，并不代表应用启动失败。应在允许本机网络访问的 WSL 会话中运行服务。

## 主要 API

FastAPI 的 `/docs` 和 `/openapi.json` 是完整接口清单。当前接口按职责分为：

| 范围 | 主要接口 | 权限 |
|---|---|---|
| 健康检查 | `GET /health` | 公开 |
| 登录与申请 | `POST /auth/login`、`POST /auth/user-applications` | 公开 |
| 个人账号 | `GET/PATCH /auth/me`、`POST /auth/change-password`、`POST /auth/logout-all` | 已登录用户 |
| 个人任务 | `POST /agent/match`、`GET /agent/tasks`、任务详情、重试、归档、恢复、机会更新 | 本人或管理员 |
| 伙伴洞察 | `GET /partners`、`GET /partners/{id}`、`GET /partners/profiles`、案例与交付物查询 | 已登录用户 |
| 全量运营 | `/admin/dashboard`、`/admin/tasks`、`/admin/demand-profiles`、`/admin/opportunities`、`/admin/reports` | 管理员 |
| 用户管理 | `/admin/users`、`/admin/user-applications`、`/admin/user-audit-logs` | 管理员 |
| 伙伴维护 | 伙伴写接口、案例与交付物写接口、文档接口、AI 画像生成 | 管理员 |
| 系统配置 | `/admin/capability-tags`、`/admin/model-configs`、`/admin/system/status` | 管理员 |

当前 OpenAPI 公开面严格限定为 `GET /health`、`POST /auth/login` 和 `POST /auth/user-applications`。

## 数据与运行配置

默认运行数据位于：

- 数据库：`data/app.db`
- 上传文件：`data/uploads`
- Chroma 预留目录：`data/chroma`

测试或隔离环境可以通过以下变量覆盖路径，不应指向真实运行数据：

```dotenv
LINGJIAN_DATABASE_PATH=/tmp/lingjian-test/app.db
LINGJIAN_UPLOADS_DIR=/tmp/lingjian-test/uploads
LINGJIAN_CHROMA_DIR=/tmp/lingjian-test/chroma
```

其他可调参数见 `.env.example`，包括 CORS、上传上限、中断任务判定时间、账号申请频率和待审批数量上限。默认上传上限为 20 MiB；伙伴文档支持 PDF、DOCX、PPTX 和 XLSX。

## 自动化验证

### 后端

后端测试使用 pytest 临时目录，不会修改 `data/app.db` 或 `data/uploads`：

```bash
source .venv/bin/activate
pip install -r backend/requirements-dev.txt
pytest -q
```

### 前端

```bash
cd frontend
npm run typecheck
npm run build
npx playwright install chromium   # 首次运行 Playwright 时执行
npm run test:e2e
```

生产构建和开发服务共用 `.next` 目录。运行 `npm run build` 或 Playwright 发布验收前，建议先执行 `bash dev.sh stop`，验证完成后再执行 `bash dev.sh start`，避免并行构建造成缓存冲突。

Playwright 使用 3100/18000/18080 测试专属端口，并将隔离数据写入 `/tmp/lingjian-agent-e2e`。发布验证不会写入真实数据库或上传目录。

2026-09-04 的发布前验证结果：

- pytest：50/50 通过
- Playwright E2E：12/12 通过
- TypeScript 类型检查、Next.js 生产构建、FastAPI 启动和健康检查通过
- OpenAPI：60 paths / 71 operations，仅 3 个公开操作
- A/B 用户隔离、管理员权限、迁移回放、任务故障恢复、文件安全和真实模型受控 E2E 通过

详细范围与证据：

- [发布验证计划](docs/validation/VALIDATION_PLAN.md)
- [发布验证报告](docs/validation/RELEASE_VALIDATION_REPORT.md)

## AI 规则

- 推荐必须包含匹配伙伴、匹配分、推荐理由、支撑案例、支撑交付物以及风险或缺口。
- 证据不足时明确说明缺失内容，不生成无依据结论。
- 正式能力标签由管理员维护；AI 只生成“待采纳”建议，管理员采纳后才进入正式标签。
- 业务场景优先使用后台绑定的模型配置，未配置时回退到环境变量；不得在前端展示 Prompt、原始模型 JSON 或调试过程。

## MVP 边界与已知限制

- 当前仅面向公司内部人员，不开放外部伙伴注册或访问。
- 使用单机 SQLite 和本地文件存储，不包含 Docker、PostgreSQL、Redis、消息队列、微服务或生产部署编排。
- `data/chroma` 只是预留目录，当前未接入 Chroma 或向量检索；匹配仍会汇总伙伴摘要进入模型上下文，伙伴规模扩大后需重新设计检索链路。
- 账号申请限流为单进程内存实现，未处理多实例共享限流或可信代理 IP；这符合当前单机 MVP 范围。
- 伙伴健康度仍为临时展示能力，正式健康度后续由外部平台提供。
- “伙伴能力短板分析”尚无独立执行接口，目前仅在匹配结果中提供风险或缺口提示。
- 真实数据库中保留两条历史案例外键孤儿记录；发布验证确认迁移未新增外键异常，且不影响任务所有权隔离链路。
