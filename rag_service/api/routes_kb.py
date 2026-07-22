"""知识库路由。"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException

from rag_service.models.schemas import KnowledgeBaseCreate, KnowledgeBaseOut
from rag_service.services import kb as kb_service

router = APIRouter(tags=["kb"])


def _to_out(row: dict) -> KnowledgeBaseOut:
    created = row.get("created_at")
    created_dt = None
    if isinstance(created, str) and created:
        try:
            created_dt = datetime.fromisoformat(created)
        except ValueError:
            created_dt = None
    return KnowledgeBaseOut(
        kb_id=row["kb_id"],
        name=row["name"],
        description=row.get("description") or "",
        created_at=created_dt,
    )


@router.post("/v1/kb", response_model=KnowledgeBaseOut)
def create_knowledge_base(body: KnowledgeBaseCreate) -> KnowledgeBaseOut:
    try:
        row = kb_service.create_kb(name=body.name, description=body.description)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"创建知识库失败: {exc}") from exc
    return _to_out(row)


@router.get("/v1/kb", response_model=list[KnowledgeBaseOut])
def list_knowledge_bases() -> list[KnowledgeBaseOut]:
    kb_service.ensure_default_kb()
    return [_to_out(r) for r in kb_service.list_kbs()]


@router.get("/v1/kb/{kb_id}", response_model=KnowledgeBaseOut)
def get_knowledge_base(kb_id: str) -> KnowledgeBaseOut:
    row = kb_service.get_kb(kb_id)
    if row is None:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return _to_out(row)
