"""可选向量嵌入（OpenAI 兼容 /embeddings）；失败则跳过。"""

from __future__ import annotations

import logging
import math
import struct
from typing import Sequence

import httpx

from rag_service.config.settings import get_settings

logger = logging.getLogger(__name__)


def pack_embedding(vector: Sequence[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *[float(x) for x in vector])


def unpack_embedding(blob: bytes | None) -> list[float] | None:
    if not blob:
        return None
    if len(blob) % 4 != 0:
        return None
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b, strict=True):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def embed_texts(texts: list[str]) -> list[list[float]] | None:
    """批量嵌入；无 Key / 接口不可用时返回 None（不抛错）。"""
    settings = get_settings()
    if not settings.has_embedding_key:
        return None
    if not texts:
        return []

    base = (settings.embedding_base_url or "https://api.openai.com/v1").rstrip("/")
    url = f"{base}/embeddings"
    headers = {
        "Authorization": f"Bearer {settings.embedding_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.embedding_model,
        "input": texts,
    }
    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code >= 400:
                logger.warning(
                    "embedding skipped: HTTP %s %s",
                    resp.status_code,
                    (resp.text or "")[:200],
                )
                return None
            data = resp.json()
            items = data.get("data") or []
            items = sorted(items, key=lambda x: int(x.get("index", 0)))
            vectors = [list(map(float, it["embedding"])) for it in items]
            if len(vectors) != len(texts):
                logger.warning("embedding skipped: size mismatch")
                return None
            return vectors
    except Exception as exc:  # noqa: BLE001
        logger.warning("embedding skipped: %s", exc)
        return None
