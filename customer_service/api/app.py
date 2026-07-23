"""FastAPI 应用工厂。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from customer_service.api.routes_admin import router as admin_router
from customer_service.api.routes_chat import router as chat_router
from customer_service.graph.builder import get_compiled_graph

_WEB_DIR = Path(__file__).resolve().parents[1] / "web"


def create_app(*, graph: Any | None = None) -> FastAPI:
    """创建 FastAPI app 并挂载路由。

    Args:
        graph: 可选，注入已编译图（测试用）；默认懒加载 `get_compiled_graph()`。
    """
    app = FastAPI(
        title="智服助手 · 智能客服",
        version="0.1.0",
        description="LangGraph Supervisor 客服演示 API",
    )
    app.state.graph = graph if graph is not None else get_compiled_graph(force_reload=True)

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
        # 契约：缺 sessionId / 空消息 → 400（而非默认 422）
        return JSONResponse(
            status_code=400,
            content={"detail": "请求参数无效：需要非空的 sessionId 与 message"},
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(chat_router)
    app.include_router(admin_router)

    # 静态前端：须挂在 API 路由之后；html=True 使 / 落到 index.html
    if _WEB_DIR.is_dir():
        app.mount(
            "/",
            StaticFiles(directory=str(_WEB_DIR), html=True),
            name="web",
        )

    return app
