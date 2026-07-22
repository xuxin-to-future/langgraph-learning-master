"""评测 API：POST /v1/eval/run。"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from rag_service.services.eval_run import (
    DEFAULT_GOLDEN,
    report_to_dict,
    run_eval,
)

router = APIRouter(tags=["eval"])


class EvalRunRequest(BaseModel):
    kb_id: str | None = Field(
        default=None, description="覆盖黄金集中的 kb_id；默认用各用例自身配置"
    )
    golden_path: str | None = Field(
        default=None, description="可选；自定义黄金集 JSON 路径"
    )


@router.post("/v1/eval/run")
def eval_run(body: EvalRunRequest | None = None) -> dict:
    body = body or EvalRunRequest()
    path: Path | None = None
    if body.golden_path:
        path = Path(body.golden_path)
        if not path.is_file():
            raise HTTPException(status_code=400, detail=f"黄金集不存在: {path}")
    elif not DEFAULT_GOLDEN.is_file():
        raise HTTPException(status_code=500, detail="内置黄金集缺失")

    report = run_eval(kb_id=body.kb_id, golden_path=path)
    return report_to_dict(report)
