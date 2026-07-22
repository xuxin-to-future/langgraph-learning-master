"""HTTP RAG 客户端：调用自研 rag_service `POST /v1/retrieve`。"""

from __future__ import annotations

import logging

import httpx

from customer_service.config.settings import get_settings

logger = logging.getLogger(__name__)


class RagClientError(RuntimeError):
    """RAG HTTP 调用失败。"""


def retrieve(
    query: str,
    *,
    top_k: int | None = None,
    kb_id: str | None = None,
    rerank: bool | None = None,
    timeout: float = 30.0,
) -> list[str]:
    """召回知识片段，格式与本地 `Passage.as_doc()` 一致：`[source]\\ntext`。"""
    settings = get_settings()
    base = settings.rag_base_url.rstrip("/")
    url = f"{base}/v1/retrieve"
    payload = {
        "kb_id": (kb_id or settings.rag_kb_id).strip(),
        "query": (query or "").strip(),
        "top_k": int(top_k if top_k is not None else settings.rag_top_k),
        "methods": ["keyword", "vector"],
        "rerank": bool(settings.rag_rerank if rerank is None else rerank),
    }
    if not payload["query"]:
        return []

    headers = {"Content-Type": "application/json"}
    if settings.rag_api_key:
        headers["Authorization"] = f"Bearer {settings.rag_api_key}"

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code >= 400:
                raise RagClientError(
                    f"RAG HTTP {resp.status_code}: {(resp.text or '')[:300]}"
                )
            data = resp.json()
    except RagClientError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise RagClientError(f"RAG 请求失败: {exc}") from exc

    chunks = data.get("chunks") or []
    docs: list[str] = []
    for ch in chunks:
        if not isinstance(ch, dict):
            continue
        source = (ch.get("source") or "").strip() or "unknown"
        text = (ch.get("text") or "").strip()
        if not text:
            continue
        docs.append(f"[{source}]\n{text}")
    return docs
