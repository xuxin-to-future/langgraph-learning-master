"""对话相关路由。

POST /v1/chat
POST /v1/chat/stream  (SSE)
"""

from __future__ import annotations

import json
import logging
from queue import Empty, Queue
from threading import Thread
from typing import Any, Iterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage

from customer_service.api.mapping import graph_result_to_chat_response
from customer_service.models.schemas import ChatRequest, ChatResponse
from customer_service.services.memory import thread_config
from customer_service.services.stream_bus import token_callback

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


@router.post("/v1/chat", response_model=ChatResponse)
def chat(body: ChatRequest, request: Request) -> ChatResponse:
    """同步对话：sessionId → thread_id → graph.invoke。"""
    graph = request.app.state.graph
    config = thread_config(body.session_id)

    try:
        result = graph.invoke(
            {"messages": [HumanMessage(content=body.message)]},
            config,
        )
    except Exception:
        logger.exception("graph.invoke failed session_id=%s", body.session_id)
        raise HTTPException(status_code=502, detail="对话服务暂时不可用，请稍后重试") from None

    # 工单写库失败：节点写入 error 且无 ticket_id
    if (
        result.get("intent") == "ticket"
        and not result.get("ticket_id")
        and result.get("error")
        and "__interrupt__" not in result
    ):
        raise HTTPException(status_code=500, detail="工单创建失败，请稍后重试")

    return graph_result_to_chat_response(body.session_id, result)


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/v1/chat/stream")
def chat_stream(body: ChatRequest, request: Request) -> StreamingResponse:
    """SSE 流式对话：FAQ 路径推送 LLM token；其它意图在 done 中返回完整 answer。"""
    graph = request.app.state.graph
    config = thread_config(body.session_id)
    q: Queue[tuple[str, Any]] = Queue()

    def on_token(delta: str) -> None:
        if delta:
            q.put(("token", delta))

    def worker() -> None:
        try:
            with token_callback(on_token):
                result = graph.invoke(
                    {"messages": [HumanMessage(content=body.message)]},
                    config,
                )
            q.put(("result", result))
        except Exception as exc:  # noqa: BLE001
            logger.exception("graph.invoke(stream) failed session_id=%s", body.session_id)
            q.put(("error", str(exc) or "对话服务暂时不可用"))
        finally:
            q.put(("end", None))

    Thread(target=worker, daemon=True).start()

    def event_gen() -> Iterator[str]:
        yield _sse({"type": "start", "sessionId": body.session_id})
        result: dict[str, Any] | None = None
        saw_token = False

        while True:
            try:
                kind, payload = q.get(timeout=120)
            except Empty:
                yield _sse({"type": "error", "message": "生成超时，请重试"})
                return

            if kind == "token":
                saw_token = True
                yield _sse({"type": "token", "delta": payload})
            elif kind == "result":
                result = payload
            elif kind == "error":
                yield _sse({"type": "error", "message": payload})
                return
            elif kind == "end":
                break

        if result is None:
            yield _sse({"type": "error", "message": "未获得对话结果"})
            return

        if (
            result.get("intent") == "ticket"
            and not result.get("ticket_id")
            and result.get("error")
            and "__interrupt__" not in result
        ):
            yield _sse({"type": "error", "message": "工单创建失败，请稍后重试"})
            return

        resp = graph_result_to_chat_response(body.session_id, result)
        # 非 FAQ（无 token）时，把完整答案作为一次 delta，便于前端统一流式渲染
        if not saw_token and resp.answer:
            yield _sse({"type": "token", "delta": resp.answer})

        yield _sse(
            {
                "type": "done",
                "sessionId": resp.session_id,
                "intent": resp.intent,
                "answer": resp.answer,
                "ticket_id": resp.ticket_id,
                "needs_human": resp.needs_human,
                "citations": resp.citations,
                "error": resp.error,
            }
        )

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
