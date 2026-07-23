"""HTTP RAG 客户端：调用自研 rag_service `POST /v1/retrieve`。

统一入口同端口时禁止 HTTP 自调用（会占满线程池导致整站卡死），改为进程内直调。
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

import httpx

from customer_service.config.settings import get_settings

logger = logging.getLogger(__name__)


class RagClientError(RuntimeError):
    """RAG HTTP 调用失败。"""


def _is_loopback_self(base_url: str) -> bool:
    """本机回环地址：统一进程内直调，避免 HTTP 自调用占满线程池。"""
    try:
        parsed = urlparse(base_url if "://" in base_url else f"http://{base_url}")
        host = (parsed.hostname or "").lower()
        return host in {"127.0.0.1", "localhost", "::1"}
    except Exception:  # noqa: BLE001
        return False


def _retrieve_inprocess(
    query: str,
    *,
    top_k: int,
    kb_id: str,
    rerank: bool,
) -> list[str]:
    """同进程调用 rag_service.retrieve，避免 HTTP 回环死锁。"""
    from rag_service.services.retrieve import retrieve as rag_retrieve

    hits = rag_retrieve(
        kb_id=kb_id,
        query=query,
        top_k=top_k,
        methods=["keyword", "vector"],
        rerank=rerank,
    )
    docs: list[str] = []
    for h in hits:
        source = (h.source or "").strip() or "unknown"
        text = (h.text or "").strip()
        if not text:
            continue
        docs.append(f"[{source}]\n{text}")
    return docs


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
    kb = (kb_id or settings.rag_kb_id).strip()
    k = int(top_k if top_k is not None else settings.rag_top_k)
    do_rerank = bool(settings.rag_rerank if rerank is None else rerank)
    q = (query or "").strip()
    if not q:
        return []

    if _is_loopback_self(base):
        logger.info(
            "RAG in-process retrieve (avoid self-HTTP deadlock) kb=%s top_k=%s",
            kb,
            k,
        )
        try:
            return _retrieve_inprocess(q, top_k=k, kb_id=kb, rerank=do_rerank)
        except Exception as exc:  # noqa: BLE001
            raise RagClientError(f"RAG 进程内召回失败: {exc}") from exc

    url = f"{base}/v1/retrieve"
    payload = {
        "kb_id": kb,
        "query": q,
        "top_k": k,
        "methods": ["keyword", "vector"],
        "rerank": do_rerank,
    }

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
