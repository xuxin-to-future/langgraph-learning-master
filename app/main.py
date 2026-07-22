"""智服助手 · 统一应用入口（客服 + 知识库，单端口）。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from customer_service.api.routes_admin import router as cs_admin_router
from customer_service.api.routes_chat import router as cs_chat_router
from customer_service.graph.builder import get_compiled_graph
from rag_service import __version__ as rag_version
from rag_service.api.routes_documents import router as rag_documents_router
from rag_service.api.routes_eval import router as rag_eval_router
from rag_service.api.routes_kb import router as rag_kb_router
from rag_service.api.routes_retrieve import router as rag_retrieve_router
from rag_service.services import kb as kb_service
from rag_service.storage.db import ensure_data_dirs, init_db

_CS_WEB = Path(__file__).resolve().parents[1] / "customer_service" / "web"
_RAG_WEB = Path(__file__).resolve().parents[1] / "rag_service" / "web"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    ensure_data_dirs()
    init_db()
    kb_service.ensure_default_kb()
    yield


def create_app(*, graph: Any | None = None) -> FastAPI:
    """组装客服 + RAG 的统一 FastAPI 应用。"""
    app = FastAPI(
        title="智服助手",
        version="0.2.0",
        description="智能客服对话 · 知识库管理（单端口）",
        lifespan=lifespan,
    )
    app.state.graph = graph if graph is not None else get_compiled_graph()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"detail": "请求参数无效：需要非空的 sessionId 与 message"},
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "rag_version": rag_version, "app": "unified"}

    # --- APIs（须在静态 mount 之前注册）---
    app.include_router(cs_chat_router)
    app.include_router(cs_admin_router)
    app.include_router(rag_kb_router)
    app.include_router(rag_documents_router)
    app.include_router(rag_retrieve_router)
    app.include_router(rag_eval_router)

    # --- 知识库管理页 /kb ---
    if _RAG_WEB.is_dir():
        index = _RAG_WEB / "index.html"

        @app.get("/kb")
        def kb_admin_redirect() -> RedirectResponse:
            return RedirectResponse(url="/kb/", status_code=307)

        @app.get("/kb/")
        def kb_admin_page() -> FileResponse:
            return FileResponse(
                index,
                headers={"Cache-Control": "no-store"},
            )

        app.mount(
            "/kb",
            StaticFiles(directory=str(_RAG_WEB), html=True),
            name="kb_web",
        )

    # --- 客服对话页 /（最后挂，避免吞掉其它路径）---
    if _CS_WEB.is_dir():
        app.mount(
            "/",
            StaticFiles(directory=str(_CS_WEB), html=True),
            name="cs_web",
        )

    return app
