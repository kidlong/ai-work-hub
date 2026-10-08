from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import ai, alerts, auth, settings, sim, work
from app.core.config import get_settings
from app.db.session import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    s = get_settings()
    if s.app_env != "dev" and s.jwt_secret.startswith("dev-only"):
        raise RuntimeError("JWT_SECRET chưa được cấu hình cho môi trường production")
    init_db()
    yield


app = FastAPI(
    title="AI Work Hub API",
    version="0.1.0",
    description="BFF / Integration Gateway: Exchange on-prem, Jira/Confluence DC, ServiceDesk Plus, Teams + AI on-prem",
    lifespan=lifespan,
)

_origins = [o.strip() for o in get_settings().cors_origins.split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_methods=["*"], allow_headers=["*"])

API_PREFIX = "/api/v1"
for r in (auth.router, work.router, alerts.router, ai.router, settings.router, sim.router):
    app.include_router(r, prefix=API_PREFIX)


@app.get("/health", tags=["ops"])
def health() -> dict:
    s = get_settings()
    return {"status": "ok", "mock_connectors": s.mock_connectors, "llm_enabled": s.llm_enabled}
