"""可选重排：优先硅基流动 /rerank（BAAI/bge-reranker-v2-m3）；不可用则降级。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx

from rag_service.config.settings import get_settings

if TYPE_CHECKING:
    from rag_service.services.retrieve import Hit

logger = logging.getLogger(__name__)


def try_rerank(query: str, hits: list[Hit]) -> list[Hit] | None:
    """对初召 hits 重排。

    Returns:
        重排后的列表（含 score_detail.rerank）；不可用时返回 None（调用方降级）。
    """
    if not hits:
        return []

    settings = get_settings()
    if not settings.has_rerank_key:
        logger.info("rerank skipped: no rerank/embedding API key configured")
        return None

    scores = _score_with_siliconflow_rerank(query, [h.text for h in hits], settings)
    if scores is None:
        return None
    if len(scores) != len(hits):
        logger.warning(
            "rerank skipped: score count mismatch (%s vs %s)",
            len(scores),
            len(hits),
        )
        return None

    ranked: list[Hit] = []
    for hit, score in zip(hits, scores, strict=True):
        detail = dict(hit.score_detail)
        detail["rerank"] = score
        ranked.append(
            type(hit)(
                chunk_id=hit.chunk_id,
                doc_id=hit.doc_id,
                kb_id=hit.kb_id,
                source=hit.source,
                text=hit.text,
                score=score,
                score_detail=detail,
            )
        )
    ranked.sort(key=lambda h: (-(h.score_detail.get("rerank") or 0.0), h.chunk_id))
    return ranked


def _score_with_siliconflow_rerank(query: str, texts: list[str], settings) -> list[float] | None:
    """调用 OpenAI 兼容厂商的 POST /rerank（硅基流动）。"""
    base = (settings.rerank_base_url or "https://api.siliconflow.cn/v1").rstrip("/")
    url = f"{base}/rerank"
    headers = {
        "Authorization": f"Bearer {settings.rerank_api_key}",
        "Content-Type": "application/json",
    }
    docs = [_clip(t, 2000) for t in texts]
    payload = {
        "model": settings.rerank_model,
        "query": query,
        "documents": docs,
        "top_n": len(docs),
        "return_documents": False,
    }
    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code >= 400:
                logger.warning(
                    "rerank skipped: HTTP %s %s",
                    resp.status_code,
                    (resp.text or "")[:300],
                )
                return None
            data = resp.json()
            return _parse_rerank_results(data, expected=len(texts))
    except Exception as exc:  # noqa: BLE001
        logger.warning("rerank skipped: %s", exc)
        return None


def _parse_rerank_results(data: dict, *, expected: int) -> list[float] | None:
    results = data.get("results")
    if not isinstance(results, list) or not results:
        logger.warning("rerank skipped: empty results")
        return None

    scores = [0.0] * expected
    seen = 0
    for item in results:
        if not isinstance(item, dict):
            continue
        try:
            idx = int(item.get("index"))
            raw = item.get("relevance_score", item.get("score"))
            score = float(raw)
        except (TypeError, ValueError):
            continue
        if idx < 0 or idx >= expected:
            continue
        # 多数 rerank 分已在 [0,1]；偶发超出则截断
        scores[idx] = max(0.0, min(1.0, score))
        seen += 1

    if seen == 0:
        logger.warning("rerank skipped: no valid scored indices")
        return None
    return scores


def _clip(text: str, max_chars: int) -> str:
    t = (text or "").replace("\n", " ").strip()
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 1] + "…"
