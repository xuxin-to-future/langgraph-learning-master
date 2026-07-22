"""召回：关键词 + 可选向量 + 加权混合（对齐 RAGFlow hybrid_similarity）。"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from rag_service.config.settings import get_settings
from rag_service.services.embedding import (
    cosine_similarity,
    embed_texts,
    unpack_embedding,
)
from rag_service.services.fts import (
    build_fts_match_query,
    ensure_fts,
    extract_query_terms,
)
from rag_service.services.rerank import try_rerank
from rag_service.storage.db import connect, init_db

logger = logging.getLogger(__name__)

Method = Literal["keyword", "vector"]


@dataclass
class Hit:
    chunk_id: str
    doc_id: str
    kb_id: str
    source: str
    text: str
    score: float = 0.0
    score_detail: dict[str, float | None] = field(default_factory=dict)


def retrieve(
    *,
    kb_id: str,
    query: str,
    top_k: int = 5,
    recall_top_n: int = 20,
    methods: list[str] | None = None,
    rerank: bool = False,
    doc_ids: list[str] | None = None,
    vector_similarity_weight: float | None = None,
    db_path: Path | None = None,
) -> list[Hit]:
    q = (query or "").strip()
    if not q:
        return []

    top_k = max(1, min(int(top_k), 50))
    recall_top_n = max(top_k, min(int(recall_top_n), 100))
    selected = _normalize_methods(methods)

    settings = get_settings()
    if vector_similarity_weight is None:
        vw = settings.vector_similarity_weight
    else:
        vw = float(vector_similarity_weight)
    vw = max(0.0, min(1.0, vw))

    kw_hits: list[Hit] = []
    vec_hits: list[Hit] = []
    if "keyword" in selected:
        kw_hits = _keyword_search(
            kb_id=kb_id,
            query=q,
            top_n=recall_top_n,
            doc_ids=doc_ids,
            db_path=db_path,
        )
    if "vector" in selected:
        vec_hits = _vector_search(
            kb_id=kb_id,
            query=q,
            top_n=recall_top_n,
            doc_ids=doc_ids,
            db_path=db_path,
        )

    fused = _weighted_fuse(
        keyword_hits=kw_hits,
        vector_hits=vec_hits,
        query=q,
        methods=selected,
        vector_weight=vw,
    )
    candidates = fused[:recall_top_n]

    if rerank and candidates:
        reranked = try_rerank(q, candidates)
        if reranked is not None:
            return reranked[:top_k]
        logger.info("rerank unavailable, degrading to fused top_k without rerank")

    return candidates[:top_k]


def _normalize_methods(methods: list[str] | None) -> list[str]:
    if not methods:
        return ["keyword", "vector"]
    out: list[str] = []
    for m in methods:
        name = (m or "").strip().lower()
        if name in {"keyword", "vector"} and name not in out:
            out.append(name)
    return out or ["keyword", "vector"]


def _keyword_search(
    *,
    kb_id: str,
    query: str,
    top_n: int,
    doc_ids: list[str] | None,
    db_path: Path | None,
) -> list[Hit]:
    """FTS 扩召回 + token_similarity 打分（对齐 RAGFlow 词项相似思路）。"""
    init_db(db_path)
    terms = extract_query_terms(query)
    match_expr = build_fts_match_query(terms)
    candidate_ids: set[str] = set()

    with connect(db_path) as conn:
        ensure_fts(conn)
        if match_expr:
            try:
                sql = """
                    SELECT c.chunk_id
                    FROM chunks_fts
                    JOIN chunks c ON c.chunk_id = chunks_fts.chunk_id
                    WHERE chunks_fts.kb_id = ?
                      AND chunks_fts MATCH ?
                """
                params: list[Any] = [kb_id, match_expr]
                if doc_ids:
                    placeholders = ",".join("?" * len(doc_ids))
                    sql += f" AND c.doc_id IN ({placeholders})"
                    params.extend(doc_ids)
                sql += " LIMIT ?"
                params.append(top_n * 3)
                for row in conn.execute(sql, params).fetchall():
                    candidate_ids.add(row["chunk_id"])
            except Exception as exc:  # noqa: BLE001
                logger.warning("FTS search failed, fallback to scan: %s", exc)

        sql = """
            SELECT chunk_id, doc_id, kb_id, source, text
            FROM chunks
            WHERE kb_id = ?
        """
        params = [kb_id]
        if doc_ids:
            placeholders = ",".join("?" * len(doc_ids))
            sql += f" AND doc_id IN ({placeholders})"
            params.extend(doc_ids)
        rows = conn.execute(sql, params).fetchall()

    scored: list[Hit] = []
    for row in rows:
        text = row["text"] or ""
        # FTS 命中的一定保留；其余用词项相似筛选
        sim = token_similarity(query, text, terms=terms)
        if sim <= 0 and row["chunk_id"] not in candidate_ids:
            continue
        if row["chunk_id"] in candidate_ids and sim <= 0:
            # FTS 命中但 token 分为 0：给极小分，避免丢候选
            sim = 0.01
        scored.append(
            Hit(
                chunk_id=row["chunk_id"],
                doc_id=row["doc_id"],
                kb_id=row["kb_id"],
                source=row["source"] or "",
                text=text,
                score=sim,
                score_detail={"keyword": sim, "vector": None, "rerank": None},
            )
        )

    scored.sort(key=lambda h: (-h.score, h.chunk_id))
    return scored[:top_n]


def token_similarity(
    query: str,
    text: str,
    *,
    terms: list[str] | None = None,
) -> float:
    """简化版 RAGFlow token_similarity：查询词权重覆盖率 ∈ [0,1]。"""
    q_terms = terms if terms is not None else extract_query_terms(query)
    weights = _query_term_weights(query, q_terms)
    if not weights:
        return 0.0

    hay = text or ""
    hay_lower = hay.lower()
    hay_compact = re.sub(r"[\s\W_]+", "", hay_lower, flags=re.UNICODE)

    hit = 0.0
    total = 0.0
    for term, w in weights.items():
        total += w
        t = term.lower()
        t_compact = re.sub(r"[\s\W_]+", "", t, flags=re.UNICODE)
        if (
            (t and t in hay_lower)
            or (term and term in hay)
            or (len(t_compact) >= 2 and t_compact in hay_compact)
        ):
            hit += w
    if total <= 0:
        return 0.0
    return max(0.0, min(1.0, hit / total))


def _query_term_weights(query: str, terms: list[str]) -> dict[str, float]:
    """单字/词 0.4，相邻 CJK bigram 0.6（贴近 RAGFlow tw 思路）。"""
    weights: dict[str, float] = {}
    for t in terms:
        if not t:
            continue
        # bigram 优先更高权重
        if len(t) >= 2 and re.fullmatch(r"[\u4e00-\u9fff]{2}", t):
            weights[t] = max(weights.get(t, 0.0), 0.6)
        else:
            weights[t] = max(weights.get(t, 0.0), 0.4)

    # 整句去标点 compact 作为强特征
    q_compact = re.sub(r"[\s\W_]+", "", (query or "").strip().lower(), flags=re.UNICODE)
    if len(q_compact) >= 2:
        weights[q_compact] = max(weights.get(q_compact, 0.0), 1.0)
    return weights


def _vector_search(
    *,
    kb_id: str,
    query: str,
    top_n: int,
    doc_ids: list[str] | None,
    db_path: Path | None,
) -> list[Hit]:
    q_vecs = embed_texts([query])
    if not q_vecs:
        return []
    q_vec = q_vecs[0]

    init_db(db_path)
    with connect(db_path) as conn:
        sql = """
            SELECT chunk_id, doc_id, kb_id, source, text, embedding
            FROM chunks
            WHERE kb_id = ? AND embedding IS NOT NULL
        """
        params: list[Any] = [kb_id]
        if doc_ids:
            placeholders = ",".join("?" * len(doc_ids))
            sql += f" AND doc_id IN ({placeholders})"
            params.extend(doc_ids)
        rows = conn.execute(sql, params).fetchall()

    scored: list[Hit] = []
    for row in rows:
        vec = unpack_embedding(row["embedding"])
        if not vec:
            continue
        sim = cosine_similarity(q_vec, vec)
        if sim <= 0:
            continue
        scored.append(
            Hit(
                chunk_id=row["chunk_id"],
                doc_id=row["doc_id"],
                kb_id=row["kb_id"],
                source=row["source"] or "",
                text=row["text"] or "",
                score=sim,
                score_detail={"keyword": None, "vector": sim, "rerank": None},
            )
        )
    scored.sort(key=lambda h: (-h.score, h.chunk_id))
    return scored[:top_n]


def _weighted_fuse(
    *,
    keyword_hits: list[Hit],
    vector_hits: list[Hit],
    query: str,
    methods: list[str],
    vector_weight: float,
) -> list[Hit]:
    """对齐 RAGFlow：score = vt_weight * vector + tk_weight * keyword。"""
    use_kw = "keyword" in methods
    use_vec = "vector" in methods
    fused: dict[str, Hit] = {}

    for hit in keyword_hits:
        fused[hit.chunk_id] = Hit(
            chunk_id=hit.chunk_id,
            doc_id=hit.doc_id,
            kb_id=hit.kb_id,
            source=hit.source,
            text=hit.text,
            score=0.0,
            score_detail={
                "keyword": hit.score_detail.get("keyword"),
                "vector": None,
                "rerank": None,
            },
        )

    for hit in vector_hits:
        if hit.chunk_id not in fused:
            fused[hit.chunk_id] = Hit(
                chunk_id=hit.chunk_id,
                doc_id=hit.doc_id,
                kb_id=hit.kb_id,
                source=hit.source,
                text=hit.text,
                score=0.0,
                score_detail={
                    "keyword": None,
                    "vector": hit.score_detail.get("vector"),
                    "rerank": None,
                },
            )
        else:
            fused[hit.chunk_id].score_detail["vector"] = hit.score_detail.get("vector")

    tk_weight = 1.0 - vector_weight
    out: list[Hit] = []
    for hit in fused.values():
        if use_kw and hit.score_detail.get("keyword") is None:
            hit.score_detail["keyword"] = token_similarity(query, hit.text)
        if use_vec and hit.score_detail.get("vector") is None:
            hit.score_detail["vector"] = 0.0

        kw = float(hit.score_detail.get("keyword") or 0.0) if use_kw else 0.0
        vt = float(hit.score_detail.get("vector") or 0.0) if use_vec else 0.0

        if use_kw and use_vec:
            # 仅有一侧有效时避免被另一侧权重拖垮过多：无向量库时退化为关键词
            if not vector_hits and keyword_hits:
                hit.score = kw
            elif not keyword_hits and vector_hits:
                hit.score = vt
            else:
                hit.score = vector_weight * vt + tk_weight * kw
        elif use_kw:
            hit.score = kw
        else:
            hit.score = vt
        out.append(hit)

    out.sort(key=lambda h: (-h.score, h.chunk_id))
    return out
