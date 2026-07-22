"""命令行跑 RAG 黄金集评测。

用法（仓库根目录）::

    python -m rag_service.eval.run_cli
    python -m rag_service.eval.run_cli --kb-id kb_default
"""

from __future__ import annotations

import argparse
import json
import sys

from rag_service.services.eval_run import report_to_dict, run_eval


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="自研 RAG 黄金集评测")
    parser.add_argument("--kb-id", default=None, help="覆盖用例 kb_id")
    parser.add_argument("--golden", default=None, help="自定义黄金集 JSON 路径")
    parser.add_argument("--json", action="store_true", help="仅输出 JSON")
    args = parser.parse_args(argv)

    from pathlib import Path

    golden = Path(args.golden) if args.golden else None
    report = run_eval(kb_id=args.kb_id, golden_path=golden)
    payload = report_to_dict(report)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"评测合计 {payload['total']} · 通过 {payload['passed']} · 失败 {payload['failed']}")
        for c in payload["cases"]:
            mark = "PASS" if c["passed"] else "FAIL"
            print(f"  [{mark}] {c['id']}: {c['query']} — {c['reason']}")
            if c.get("hit_sources"):
                print(f"         sources={c['hit_sources']}")

    return 0 if report.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
