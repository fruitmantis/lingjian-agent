from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import get_jwt_secret_key
from .database import initialize_storage, get_db, recover_stale_tasks
from .routers import feedback, partners, cases, profile, match, documents, users, demand, capability_tags, system, model_config, enablement, enablement_workspace, development
from .auth import get_bootstrap_admin


def get_cors_origins() -> list[str]:
    import os
    configured_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    return [origin.strip() for origin in configured_origins.split(",") if origin.strip()]


def initialize_application() -> None:
    """Validate runtime security and initialize persistent application state."""
    get_jwt_secret_key()
    initialize_storage()
    with get_db() as conn:
        existing = conn.execute("SELECT COUNT(*) as cnt FROM users").fetchone()
        if existing["cnt"] == 0:
            admin = get_bootstrap_admin()
            conn.execute(
                "INSERT INTO users (id, username, hashed_password, display_name, role, status, must_change_password, token_version, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (admin["id"], admin["username"], admin["hashed_password"], admin["display_name"], admin["role"], admin["status"], admin["must_change_password"], admin["token_version"], admin["created_at"], admin["updated_at"]),
            )
    recover_stale_tasks()
    from .development_lifecycle import recover
    recover(startup=True)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    initialize_application()
    yield


class HealthResponse(BaseModel):
    status: str
    service: str


app = FastAPI(title="伴飞 Agent API", description="交付伙伴智能匹配智能体 MVP API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=get_cors_origins(), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.get("/health", response_model=HealthResponse, tags=["system"])
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service="lingjian-agent-api")


app.include_router(profile.router)
app.include_router(partners.router)
app.include_router(cases.router)
app.include_router(match.router)
app.include_router(match.admin_router)
app.include_router(documents.router)
app.include_router(users.router)
app.include_router(demand.router)
app.include_router(demand.admin_router)
app.include_router(capability_tags.router)
app.include_router(system.router)
app.include_router(model_config.router)

app.include_router(enablement.router)
app.include_router(enablement_workspace.router)

app.include_router(development.router)

app.include_router(feedback.router)
app.include_router(feedback.admin_router)
