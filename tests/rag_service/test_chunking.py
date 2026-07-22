"""切片策略单测（RAGFlow-aligned naive）。"""

from __future__ import annotations

from rag_service.services.chunking import num_tokens, split_text


def test_short_header_merged_into_body() -> None:
    text = "# 支持政策\n\n## 退款政策\n\n订阅类服务 7 天内可全额退款。\n"
    pieces = split_text(text, max_tokens=512, overlap_percent=0)
    assert pieces
    # 短标题不应单独成空块；退款内容块应带标题上下文
    assert all(p.text.strip() not in {"# 支持政策", "## 退款政策"} for p in pieces)
    assert any("退款政策" in p.text and "7 天" in p.text for p in pieces)


def test_long_text_respects_token_budget() -> None:
    # 构造多段，迫使产生多块
    paras = [f"## 章节{i}\n\n{'退款政策条款内容。' * 40}" for i in range(8)]
    text = "# 手册\n\n" + "\n\n".join(paras)
    pieces = split_text(text, max_tokens=128, overlap_percent=0)
    assert len(pieces) > 1
    # 允许末块更小；中间块不应远超预算（overlap=0 时约 ≤128+一段余量）
    for p in pieces[:-1]:
        assert num_tokens(p.text) <= 128 * 2


def test_overlap_shares_suffix_prefix() -> None:
    paras = [f"段落{i}：" + ("重要说明。" * 20) for i in range(6)]
    text = "\n\n".join(paras)
    pieces = split_text(text, max_tokens=64, overlap_percent=20)
    assert len(pieces) >= 2
    # 后一块应包含前一块的部分后缀字符
    prev = pieces[0].text
    nxt = pieces[1].text
    suffix = prev[int(len(prev) * 0.8) :]
    assert suffix.strip()
    assert suffix in nxt or any(suffix[i : i + 12] in nxt for i in range(0, max(1, len(suffix) - 12), 8))
