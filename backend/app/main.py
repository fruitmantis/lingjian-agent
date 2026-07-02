import os
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .database import PROJECT_ROOT, initialize_storage, get_db
from .routers import partners, cases, profile, match, documents, users, demand, capability_tags
from .auth import get_default_admin


load_dotenv(PROJECT_ROOT / ".env")


def get_cors_origins() -> list[str]:
    configured_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    return [origin.strip() for origin in configured_origins.split(",") if origin.strip()]


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    initialize_storage()
    with get_db() as conn:
        existing = conn.execute("SELECT COUNT(*) as cnt FROM users").fetchone()
        if existing["cnt"] == 0:
            admin = get_default_admin()
            conn.execute("INSERT INTO users (id, username, hashed_password, display_name, role, created_at) VALUES (?, ?, ?, ?, ?, ?)", (admin["id"], admin["username"], admin["hashed_password"], admin["display_name"], admin["role"], admin["created_at"]))
    yield


class HealthResponse(BaseModel):
    status: str
    service: str


app = FastAPI(title="灵鉴 Agent API", description="交付伙伴智能匹配智能体 MVP API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=get_cors_origins(), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.get("/health", response_model=HealthResponse, tags=["system"])
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service="lingjian-agent-api")


app.include_router(profile.router)
app.include_router(partners.router)
app.include_router(cases.router)
app.include_router(match.router)
app.include_router(documents.router)
app.include_router(users.router)
app.include_router(demand.router)
app.include_router(capability_tags.router)
