"""召回路由。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from rag_service.models.schemas import (
    RetrieveRequest,
    RetrieveResponse,
    RetrievedChunkOut,
    ScoreDetail,
)
from rag_service.services.retrieve import retrieve

router = APIRouter(tags=["retrieve"])


@router.post("/v1/retrieve", response_model=RetrieveResponse)
def retrieve_api(body: RetrieveRequest) -> RetrieveResponse:
    if not body.query.strip():
        raise HTTPException(status_code=400, detail="query 不能为空")

    doc_ids = None
    if body.filters and body.filters.doc_ids:
        doc_ids = [d for d in body.filters.doc_ids if d]

    hits = retrieve(
        kb_id=body.kb_id.strip(),
        query=body.query.strip(),
        top_k=body.top_k,
        recall_top_n=body.recall_top_n,
        methods=body.methods,
        rerank=body.rerank,
        doc_ids=doc_ids,
        vector_similarity_weight=body.vector_similarity_weight,
    )
    chunks = [
        RetrievedChunkOut(
            chunk_id=h.chunk_id,
            doc_id=h.doc_id,
            kb_id=h.kb_id,
            source=h.source,
            text=h.text,
            score=h.score,
            score_detail=ScoreDetail(
                keyword=h.score_detail.get("keyword"),
                vector=h.score_detail.get("vector"),
                rerank=h.score_detail.get("rerank"),
            ),
        )
        for h in hits
    ]
    return RetrieveResponse(query=body.query.strip(), chunks=chunks)
