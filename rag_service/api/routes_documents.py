"""文档上传与查询路由。"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from rag_service.models.schemas import DocumentOut
from rag_service.services.ingest import (
    IngestError,
    delete_document,
    get_document,
    ingest_upload,
    list_documents,
    reindex_document,
)

router = APIRouter(tags=["documents"])


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _to_out(row: dict) -> DocumentOut:
    return DocumentOut(
        doc_id=row["doc_id"],
        kb_id=row["kb_id"],
        title=row["title"],
        source_name=row.get("source_name") or "",
        status=row["status"],
        error=row.get("error"),
        chunk_count=int(row.get("chunk_count") or 0),
        created_at=_parse_dt(row.get("created_at")),
        updated_at=_parse_dt(row.get("updated_at")),
    )


@router.post("/v1/kb/{kb_id}/documents", response_model=DocumentOut)
async def upload_document(
    kb_id: str,
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
) -> DocumentOut:
    raw = await file.read()
    try:
        row = ingest_upload(
            kb_id=kb_id,
            filename=file.filename or "upload.bin",
            content=raw,
            title=title,
        )
    except IngestError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"入库失败: {exc}") from exc
    return _to_out(row)


@router.get("/v1/documents/{doc_id}", response_model=DocumentOut)
def get_document_api(doc_id: str) -> DocumentOut:
    row = get_document(doc_id)
    if row is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return _to_out(row)


@router.delete("/v1/documents/{doc_id}")
def delete_document_api(doc_id: str) -> dict[str, str]:
    if not delete_document(doc_id):
        raise HTTPException(status_code=404, detail="文档不存在")
    return {"doc_id": doc_id, "status": "deleted"}


@router.post("/v1/documents/{doc_id}/reindex", response_model=DocumentOut)
def reindex_document_api(doc_id: str) -> DocumentOut:
    try:
        row = reindex_document(doc_id)
    except IngestError as exc:
        msg = str(exc)
        if msg.startswith("文档不存在"):
            raise HTTPException(status_code=404, detail=msg) from exc
        raise HTTPException(status_code=400, detail=msg) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"重索引失败: {exc}") from exc
    return _to_out(row)


@router.get("/v1/kb/{kb_id}/documents", response_model=list[DocumentOut])
def list_documents_api(kb_id: str) -> list[DocumentOut]:
    return [_to_out(r) for r in list_documents(kb_id)]
