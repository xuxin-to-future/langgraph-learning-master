"""Pydantic / DTO。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str = ""


class KnowledgeBaseOut(BaseModel):
    kb_id: str
    name: str
    description: str = ""
    created_at: datetime | None = None


class DocumentOut(BaseModel):
    doc_id: str
    kb_id: str
    title: str
    source_name: str = ""
    status: str
    error: str | None = None
    chunk_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RetrieveFilters(BaseModel):
    doc_ids: list[str] | None = None


class RetrieveRequest(BaseModel):
    kb_id: str = Field(..., min_length=1)
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)
    recall_top_n: int = Field(default=20, ge=1, le=100)
    methods: list[str] = Field(default_factory=lambda: ["keyword", "vector"])
    rerank: bool = False
    # 对齐 RAGFlow：score = w*vector + (1-w)*keyword；None 则用服务端默认
    vector_similarity_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    filters: RetrieveFilters | None = None


class ScoreDetail(BaseModel):
    vector: float | None = None
    keyword: float | None = None
    rerank: float | None = None


class RetrievedChunkOut(BaseModel):
    chunk_id: str
    doc_id: str
    kb_id: str
    source: str = ""
    text: str
    score: float
    score_detail: ScoreDetail | None = None


class RetrieveResponse(BaseModel):
    query: str
    chunks: list[RetrievedChunkOut]


class HealthOut(BaseModel):
    status: str
    version: str = "0.1.0"


class EvalCaseResultOut(BaseModel):
    id: str
    query: str
    passed: bool
    reason: str = ""
    hit_sources: list[str] = Field(default_factory=list)


class EvalReportOut(BaseModel):
    total: int
    passed: int
    failed: int
    all_passed: bool
    cases: list[EvalCaseResultOut]
