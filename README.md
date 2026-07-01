# 灵鉴 Agent

灵鉴 Agent 是一个交付伙伴智能匹配智能体，用于归集伙伴档案、项目案例和交付物，通过 AI 生成伙伴能力画像，并根据项目需求推荐合适的交付伙伴。

## 技术栈

- Frontend: Next.js 15、React 19、TypeScript
- Backend: FastAPI、Python 3.11+
- Database: SQLite（`data/app.db`）
- File Storage: `data/uploads`
- AI: OpenAI 兼容 LLM API（阿里云 MaaS / GLM-5.2）

## 项目结构

```text
.
├── backend/                    # FastAPI 应用
│   ├── app/
│   │   ├── ai_client.py        # LLM 客户端（OpenAI 兼容）
│   │   ├── database.py         # SQLite 与本地目录初始化
│   │   ├── main.py             # API 入口
│   │   ├── models.py           # Pydantic 模型
│   │   └── routers/
│   │       ├── partners.py     # 伙伴 CRUD
│   │       ├── cases.py        # 案例与交付物
│   │       ├── profile.py      # AI 画像生成
│   │       └── match.py        # 智能匹配推荐
│   └── requirements.txt
├── frontend/                   # Next.js 应用
│   ├── app/
│   │   ├── layout.tsx          # 根布局 + 导航
│   │   ├── page.tsx            # Agent 工作台（需求输入 + 推荐结果）
│   │   └── partners/
│   │       ├── page.tsx        # 伙伴资料管理
│   │       └── [id]/page.tsx   # 伙伴画像详情
│   └── components/
│       └── health-status.tsx   # 后端连接状态
├── data/
│   ├── app.db                  # SQLite 数据库
│   ├── chroma/                 # Chroma 向量库目录
│   └── uploads/                # 上传文件目录
└── docs/product-spec.md
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

在 `.env` 中填入你的 LLM API 信息：

```
LLM_API_KEY=你的key
LLM_BASE_URL=https://your-llm-endpoint/v1
LLM_MODEL=模型名称
```

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

访问 http://localhost:3000

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/partners` | 伙伴列表 |
| GET | `/partners/{id}` | 伙伴详情 |
| POST | `/partners` | 新增伙伴 |
| POST | `/partners/{id}/profile` | 生成 AI 能力画像 |
| GET | `/cases/by-partner/{partner_id}` | 按伙伴查案例 |
| POST | `/cases` | 新增案例 |
| GET | `/cases/{case_id}/deliverables` | 案例交付物列表 |
| POST | `/cases/{case_id}/deliverables` | 上传交付物文件 |
| POST | `/match` | 智能匹配推荐 |

## 功能说明

### Agent 工作台（`/`）

输入自然语言项目需求，AI 基于伙伴资料、案例和画像进行匹配，返回推荐伙伴、匹配评分、推荐理由、支撑案例、支撑交付物和风险提示。

### 伙伴资料管理（`/partners`）

维护伙伴基础信息（名称、简介、能力标签、服务区域、行业经验），支持新增和列表查看。

### 伙伴画像详情（`/partners/{id}`）

展示伙伴基础信息、AI 能力画像、案例列表与交付物。支持生成/重新生成 AI 画像、新增案例、上传交付物文件。

## MVP 边界

当前项目不包含 Docker、PostgreSQL、Redis、Kubernetes、复杂认证、微服务或生产部署配置。
