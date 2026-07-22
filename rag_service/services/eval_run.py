"""黄金集评测：对固定问句检查是否命中期望 source/文本关键词。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from rag_service.services.retrieve import retrieve

DEFAULT_GOLDEN = Path(__file__).resolve().parents[1] / "eval" / "golden.json"


@dataclass
class CaseResult:
    id: str
    query: str
    passed: bool
    reason: str = ""
    hit_sources: list[str] = field(default_factory=list)


@dataclass
class EvalReport:
    total: int
    passed: int
    failed: int
    cases: list[CaseResult]

    @property
    def all_passed(self) -> bool:
        return self.failed == 0 and self.total > 0


def load_golden(path: Path | None = None) -> dict[str, Any]:
    p = path or DEFAULT_GOLDEN
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data.get("cases"), list):
        raise ValueError("golden 文件缺少 cases 数组")
    return data


def run_eval(
    *,
    kb_id: str | None = None,
    golden_path: Path | None = None,
    db_path: Path | None = None,
) -> EvalReport:
    """对黄金集逐条召回并判定通过/失败。"""
    golden = load_golden(golden_path)
    results: list[CaseResult] = []

    for raw in golden["cases"]:
        case_id = str(raw.get("id") or raw.get("query") or "case")
        query = str(raw.get("query") or "").strip()
        if not query:
            results.append(
                CaseResult(id=case_id, query="", passed=False, reason="缺少 query")
            )
            continue

        case_kb = str(kb_id or raw.get("kb_id") or "kb_default").strip()
        top_k = int(raw.get("top_k") or 5)
        methods = raw.get("methods") or ["keyword"]
        expect_src = [str(x) for x in (raw.get("expect_any_source_contains") or [])]
        expect_txt = [str(x) for x in (raw.get("expect_any_text_contains") or [])]

        hits = retrieve(
            kb_id=case_kb,
            query=query,
            top_k=top_k,
            methods=list(methods),
            rerank=False,
            db_path=db_path,
        )
        sources = [h.source for h in hits]
        texts = [h.text for h in hits]
        blob_src = "\n".join(sources)
        blob_txt = "\n".join(texts)

        if not hits:
            results.append(
                CaseResult(
                    id=case_id,
                    query=query,
                    passed=False,
                    reason="无召回结果",
                    hit_sources=[],
                )
            )
            continue

        ok = True
        reasons: list[str] = []
        if expect_src and not any(tok in blob_src for tok in expect_src):
            ok = False
            reasons.append(f"source 未含任一 {expect_src}")
        if expect_txt and not any(tok in blob_txt for tok in expect_txt):
            ok = False
            reasons.append(f"text 未含任一 {expect_txt}")
        if not expect_src and not expect_txt:
            # 无期望字段时：至少召回到一条即通过
            pass

        results.append(
            CaseResult(
                id=case_id,
                query=query,
                passed=ok,
                reason="; ".join(reasons) if reasons else ("ok" if ok else "未通过"),
                hit_sources=sources[:5],
            )
        )

    passed_n = sum(1 for r in results if r.passed)
    return EvalReport(
        total=len(results),
        passed=passed_n,
        failed=len(results) - passed_n,
        cases=results,
    )


def report_to_dict(report: EvalReport) -> dict[str, Any]:
    return {
        "total": report.total,
        "passed": report.passed,
        "failed": report.failed,
        "all_passed": report.all_passed,
        "cases": [asdict(c) for c in report.cases],
    }
