# 灵鉴 Agent

灵鉴 Agent 是一个交付伙伴智能匹配智能体，用于归集伙伴档案、项目案例和交付物，通过 AI 生成伙伴能力画像，并根据项目需求推荐合适的交付伙伴。

## 技术栈

- Frontend: Next.js 15、React 19、TypeScript
- Backend: FastAPI、Python 3.11+
- Database: SQLite（`data/app.db`）
- File Storage: `data/uploads`
- AI: OpenAI 兼容 LLM API（`ai_client.py` 经 httpx 调用，支持按业务场景配置模型）

## 项目结构

```text
.
├── backend/                       # FastAPI 应用
│   ├── app/
│   │   ├── ai_client.py           # LLM 客户端（OpenAI 兼容，httpx）
│   │   ├── model_resolver.py      # 按场景解析模型配置（DB → env 回退）
│   │   ├── database.py            # SQLite 与本地目录初始化
│   │   ├── main.py                # API 入口 + lifespan 初始化
│   │   ├── models.py              # Pydantic 模型
│   │   ├── auth.py                # JWT + bcrypt 认证
│   │   ├── doc_extractor.py       # PDF/DOCX/PPTX/XLSX 文本抽取
│   │   └── routers/
│   │       ├── partners.py        # 伙伴 CRUD + 画像卡片 + 健康分
│   │       ├── profile.py         # AI 画像生成（单个 / 批量）
│   │       ├── cases.py           # 案例与交付物
│   │       ├── documents.py       # 伙伴文档上传 / 预览
│   │       ├── match.py           # 智能匹配推荐 + 匹配记录
│   │       ├── demand.py          # 需求画像 + 项目机会 + 运营报表
│   │       ├── capability_tags.py # 能力标签字典 + 分类 + AI 建议
│   │       ├── model_config.py    # 多场景模型配置管理
│   │       ├── system.py          # 系统状态监控
│   │       └── users.py           # 用户与登录
│   ├── scripts/seed_huawei_service_partners.py  # 种子数据
│   └── requirements.txt
├── frontend/                      # Next.js 应用
│   ├── app/
│   │   ├── layout.tsx             # 根布局
│   │   ├── page.tsx               # 智能匹配（Agent 工作台）
│   │   ├── partners/page.tsx      # 伙伴资料管理
│   │   ├── partners/[id]/page.tsx # 伙伴画像详情
│   │   ├── profiles/page.tsx      # 伙伴画像总览
│   │   ├── demands/page.tsx       # 需求画像 / 项目机会库 / 运营报表
│   │   ├── admin/page.tsx         # 用户 / 标签 / 模型配置 / 系统状态
│   │   ├── users/page.tsx         # 用户管理
│   │   └── login/page.tsx         # 登录
│   ├── components/
│   │   ├── app-shell.tsx          # 导航外壳
│   │   └── health-status.tsx      # 后端连接状态
│   └── package.json
├── data/
│   ├── app.db                     # SQLite 数据库
│   ├── chroma/                    # 预留向量库目录（当前未接入）
│   └── uploads/                   # 上传文件目录
├── dev.sh                         # 一键启动前后端
├── docs/product-spec.md
└── AGENTS.md
```

## 环境要求

- Node.js 18.18 或更高版本
- npm 9 或更高版本
- Python 3.11 或更高版本

## 本地运行

### 1. 配置环境变量

```bash
cp .env.example .env
cp frontend/.env.local.example frontend/.env.local
```

在 `.env` 中配置 JWT 密钥和 LLM API 信息。`JWT_SECRET_KEY` 必须是至少 32 位、不可预测的随机值；缺失或使用历史默认值时后端会拒绝启动：

```
JWT_SECRET_KEY=使用安全随机源生成的至少32位密钥
LLM_API_KEY=你的key
LLM_BASE_URL=https://your-llm-endpoint/v1
LLM_MODEL=模型名称
```

仅当数据库完全为空、需要首次创建管理员时，再设置 `BOOTSTRAP_ADMIN_USERNAME` 和强密码 `BOOTSTRAP_ADMIN_PASSWORD`。该管理员首次登录必须修改密码；项目不再内置固定管理员密码。

### 2. 启动后端

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
python -m uvicorn app.main:app --app-dir backend --reload --host 0.0.0.0 --port 8000
```

### 3. 启动前端

另开一个终端：

```bash
cd frontend
npm install
npm run dev
```

访问 http://localhost:3000 。使用已有内部账号登录；没有账号的员工可在登录页提交申请，由管理员在“用户管理 → 账号申请”中审批。

### 一键启动

也可用项目根目录的 `dev.sh` 一条命令起前后端：

```bash
bash dev.sh
```

> 在 Codex 桌面端内运行时，需将 agent 模式切到 Full Access（完全访问）以放开网络端口绑定；否则沙箱会禁用网络，导致服务无法监听端口。

## 自动化验证

后端测试使用临时 SQLite 数据库，不会修改 `data/app.db`：

```bash
source .venv/bin/activate
pip install -r backend/requirements-dev.txt
pytest -q
```

前端类型检查、生产构建和 Playwright E2E：

```bash
cd frontend
npm install
npm run typecheck
npm run build
npm run test:e2e
```

Playwright 会在 `/tmp/lingjian-agent-e2e` 创建隔离数据，并启动测试专属端口。完整发布验收范围与结果见 `docs/validation/`。

## API 接口

### 系统

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/system/status` | 系统状态监控 |

### 认证与用户（`/auth`）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/auth/login` | 登录，返回 JWT |
| GET | `/auth/me` | 当前登录用户 |
| GET | `/auth/users` | 用户列表（需登录） |
| POST | `/auth/users` | 新增用户（需登录） |
| DELETE | `/auth/users/{user_id}` | 删除用户（需登录） |

### 伙伴（`/partners`，均需登录）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/partners` | 伙伴列表 |
| GET | `/partners/{id}` | 伙伴详情 |
| POST | `/partners` | 新增伙伴 |
| PUT | `/partners/{id}` | 更新伙伴 |
| DELETE | `/partners/{id}` | 删除伙伴 |
| GET | `/partners/profiles` | 伙伴画像卡片（含健康分） |
| POST | `/partners/{id}/profile` | 生成 AI 能力画像 |
| POST | `/partners/batch-profile` | 批量生成画像 |
| GET | `/partners/{id}/documents` | 伙伴文档列表 |
| POST | `/partners/{id}/documents` | 上传伙伴文档 |
| GET | `/partners/{id}/documents/{doc_id}/preview` | 文档预览 |
| DELETE | `/partners/{id}/documents/{doc_id}` | 删除文档 |

### 案例与交付物（`/cases`）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/cases/by-partner/{partner_id}` | 按伙伴查案例 |
| POST | `/cases` | 新增案例 |
| GET | `/cases/{case_id}/deliverables` | 案例交付物列表 |
| POST | `/cases/{case_id}/deliverables` | 上传交付物文件 |

### 智能匹配与需求（`/agent`）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/agent/match` | 智能匹配推荐 |
| GET | `/agent/match-records` | 匹配记录列表 |
| GET | `/agent/match-records/{id}` | 匹配记录详情 |
| DELETE | `/agent/match-records/{id}` | 删除匹配记录 |
| GET | `/agent/demand-profiles` | 需求画像总览 |
| GET | `/agent/report` | 运营报表 |
| GET | `/agent/opportunities` | 项目机会列表 |
| GET | `/agent/opportunities/{id}` | 项目机会详情 |
| PUT | `/agent/opportunities/{id}` | 更新项目机会 |
| DELETE | `/agent/demand-profiles/{id}` | 删除需求画像 |
| DELETE | `/agent/opportunities/{id}` | 删除项目机会 |

### 能力标签（`/capability-tags`）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/capability-tags` | 标签列表 |
| POST | `/capability-tags` | 新增标签 |
| PUT | `/capability-tags/{tag_id}` | 更新标签 |
| POST | `/capability-tags/seed` | 种子标签 |
| GET | `/capability-tags/categories` | 分类列表 |
| POST | `/capability-tags/categories` | 新增分类 |
| GET | `/capability-tags/suggestions` | AI 标签建议列表 |
| POST | `/capability-tags/suggestions/scan` | 扫描生成建议 |
| POST | `/capability-tags/suggestions/{sug_id}/adopt` | 采纳建议 |

### 模型配置（`/model-configs`）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/model-configs` | 模型配置列表 |
| POST | `/model-configs` | 新增模型配置 |
| PUT | `/model-configs/{mc_id}` | 更新模型配置 |
| POST | `/model-configs/{mc_id}/test` | 测试模型连通性 |
| GET | `/model-configs/usage` | 场景用途配置 |
| PUT | `/model-configs/usage/{scene_key}` | 设置某场景使用的模型 |

## 功能说明

### 智能匹配 / Agent 工作台（`/`）

输入自然语言项目需求，AI 基于伙伴资料、案例和画像进行匹配，返回推荐伙伴、匹配评分、推荐理由、支撑案例、支撑交付物和风险提示；匹配结果可查看历史记录。

### 伙伴资料管理（`/partners`）

维护伙伴基础信息（名称、简介、能力标签、服务区域、行业经验），支持新增、编辑、删除和列表查看。

### 伙伴画像总览（`/profiles`）

按健康分排序展示所有伙伴的能力画像卡片，含案例数、交付物数和健康等级。

### 伙伴画像详情（`/partners/{id}`）

展示伙伴基础信息、AI 能力画像、案例列表、交付物与上传文档。支持生成 / 重新生成 AI 画像、批量生成、新增案例、上传交付物与文档。

### 需求画像（`/demands`）

三个 Tab：
- **需求画像**：每次匹配自动生成的需求结构化标签与供需状态。
- **项目机会库**：从匹配中抽取的项目机会，可编辑与筛选。
- **运营报表**：伙伴活跃度、能力分布、供需缺口等统计。

### 系统管理（`/admin`）

多 Tab：用户管理、能力标签配置（含 AI 标签建议）、模型配置（按场景绑定）、系统状态监控。

## AI 规则

- 推荐结果包含：匹配伙伴、匹配评分、推荐理由、支撑案例、支撑交付物、风险或缺口提示。
- 不生成无证据支撑的结论；证据不足时显式说明缺失项。
- 能力标签、服务区域、行业等结构化字段限定在标准字典内，LLM 不得创造新标签。

## MVP 边界

当前项目不包含 Docker、PostgreSQL、Redis、Kubernetes、复杂权限、审核流、多租户、微服务或生产部署配置。

## 已知限制

- **向量检索未接入**：`data/chroma/` 仅为预留目录，`chromadb` 未加入依赖；当前匹配采用全量伙伴摘要塞入单条 LLM prompt，伙伴规模较大时可能超出 token 上限。
- **认证范围不统一**：`partners` / `profile` / `documents` / `users` 需登录，`cases` / `match` / `demand` / `capability_tags` / `system` / `model_config` 暂未加鉴权。
- **登录安全**：无内置默认凭据；`JWT_SECRET_KEY` 为强制配置，空库管理员只能通过 bootstrap 环境变量创建并要求首次改密。
- **演示数据偏薄**：35 个伙伴中仅少数生成画像，交付物为 0，推荐中「支撑交付物」可能为空。
