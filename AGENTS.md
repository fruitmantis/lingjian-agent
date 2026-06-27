# AGENTS.md

## Project

This project is "灵鉴 Agent：交付伙伴智能匹配智能体".

## Goal

Build an MVP system that helps users upload partner profiles, delivery cases and deliverables, then uses AI to generate partner capability profiles and recommend suitable delivery partners for project requirements.

## Tech Stack

- Frontend: Next.js
- Backend: FastAPI
- Database: SQLite
- Vector Store: Chroma
- File Storage: local data/uploads
- AI: external LLM and embedding APIs

## MVP Scope

Only implement the MVP. Do not add Docker, PostgreSQL, Redis, Kubernetes, complex authentication, microservices, or production deployment unless explicitly requested.

## Required Pages

1. Agent 工作台
2. 伙伴资料管理
3. 伙伴画像详情页

## Backend Rules

- Use FastAPI.
- Store SQLite database at `data/app.db`.
- Store uploaded files under `data/uploads`.
- Keep API design simple and readable.
- Do not hardcode API keys.
- Use `.env` for secrets.

## Frontend Rules

- Use Next.js.
- Use a clean enterprise SaaS style.
- Main visual theme should use Huawei-style red, white and light gray.
- Keep pages simple and focused.

## AI Rules

- AI recommendations must include:
  - matched partner
  - match score
  - recommendation reason
  - supporting cases
  - supporting deliverables
  - risk or gap notes

- Do not generate unsupported conclusions.
- When evidence is insufficient, say what is missing.
