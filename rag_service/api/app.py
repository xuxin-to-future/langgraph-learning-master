"""FastAPI 应用工厂。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from rag_service import __version__
from rag_service.api.routes_documents import router as documents_router
from rag_service.api.routes_eval import router as eval_router
from rag_service.api.routes_kb import router as kb_router
from rag_service.api.routes_retrieve import router as retrieve_router
from rag_service.models.schemas import HealthOut
from rag_service.services import kb as kb_service
from rag_service.storage.db import ensure_data_dirs, init_db

_WEB_DIR = Path(__file__).resolve().parents[1] / "web"


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    ensure_data_dirs()
    init_db()
    kb_service.ensure_default_kb()
    yield


def create_app() -> FastAPI:
    """创建 RAG FastAPI 应用。"""
    app = FastAPI(
        title="自研 RAG 中台",
        version=__version__,
        description="知识库 · 入库 · 召回（P0/P1）",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", response_model=HealthOut)
    def health() -> HealthOut:
        return HealthOut(status="ok", version=__version__)

    app.include_router(kb_router)
    app.include_router(documents_router)
    app.include_router(retrieve_router)
    app.include_router(eval_router)

    if _WEB_DIR.is_dir():
        index = _WEB_DIR / "index.html"

        @app.get("/admin")
        @app.get("/admin/")
        def admin_page() -> FileResponse:
            return FileResponse(index)

        # 静态前端须挂在 API 路由之后；html=True 使 / 落到 index.html
        app.mount(
            "/",
            StaticFiles(directory=str(_WEB_DIR), html=True),
            name="web",
        )

    return app
