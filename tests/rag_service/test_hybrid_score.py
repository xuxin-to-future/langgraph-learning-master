"""混合召回打分单测（对齐 RAGFlow weighted hybrid）。"""

from __future__ import annotations

from rag_service.services.retrieve import Hit, _weighted_fuse, token_similarity


def test_token_similarity_not_always_one() -> None:
    q = "离职交接给谁？"
    relevant = "客户分配人指离职销售的直属上级、二级/一级部门负责人"
    weak = "外呼内容符合业务沟通场景，探寻需求与交付情况"
    s_rel = token_similarity(q, relevant)
    s_weak = token_similarity(q, weak)
    assert 0 < s_rel <= 1
    assert s_weak < s_rel
    # 不应因部分 bigram 命中就顶满 1.0（整句 compact 未命中时）
    assert s_rel < 1.0 or "离职交接给谁" in relevant.replace("？", "")


def test_weighted_fuse_blends_scores() -> None:
    kw = [
        Hit(
            chunk_id="a",
            doc_id="d1",
            kb_id="kb",
            source="a.md",
            text="离职交接",
            score=0.8,
            score_detail={"keyword": 0.8, "vector": None, "rerank": None},
        )
    ]
    vec = [
        Hit(
            chunk_id="a",
            doc_id="d1",
            kb_id="kb",
            source="a.md",
            text="离职交接",
            score=0.5,
            score_detail={"keyword": None, "vector": 0.5, "rerank": None},
        )
    ]
    out = _weighted_fuse(
        keyword_hits=kw,
        vector_hits=vec,
        query="离职交接",
        methods=["keyword", "vector"],
        vector_weight=0.7,
    )
    assert len(out) == 1
    # 0.7*0.5 + 0.3*0.8 = 0.35 + 0.24 = 0.59
    assert abs(out[0].score - 0.59) < 1e-6
    assert out[0].score_detail["keyword"] == 0.8
    assert out[0].score_detail["vector"] == 0.5
