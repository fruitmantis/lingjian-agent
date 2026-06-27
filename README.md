# 灵鉴 Agent

灵鉴 Agent 是一个交付伙伴智能匹配智能体，用于归集伙伴档案、项目案例、交付物等资料，并通过 AI 生成伙伴能力画像，辅助一线根据项目需求快速匹配合适的交付伙伴。

## MVP 技术栈

- Frontend: Next.js
- Backend: FastAPI
- Database: SQLite
- Vector Store: Chroma
- File Storage: local data/uploads
- AI: external LLM and embedding APIs

## MVP 范围

第一期聚焦三个核心页面：

1. Agent 工作台
2. 伙伴资料管理
3. 伙伴画像详情页

暂不引入 Docker、PostgreSQL、Redis、复杂权限和生产部署。
