"""文本切片：对齐 RAGFlow naive 语义（标题段 + token 打包 + overlap）。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

import tiktoken

_HEADER_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_SHORT_HEADER_MAX_TOKENS = 50


@dataclass(frozen=True)
class TextPiece:
    text: str
    heading: str
    position: int


@lru_cache(maxsize=1)
def _encoder() -> tiktoken.Encoding:
    return tiktoken.get_encoding("cl100k_base")


def num_tokens(text: str) -> int:
    if not text:
        return 0
    return len(_encoder().encode(text))


def split_text(
    text: str,
    *,
    max_tokens: int = 512,
    overlap_percent: int = 10,
    max_chars: int = 8000,
) -> list[TextPiece]:
    """按 MD 标题/段落拆段 → 短标题合并 → token 打包（可 overlap）。

    ``max_chars`` 仅作超长单段硬切兜底（deprecated 字符上限）。
    """
    raw = (text or "").replace("\r\n", "\n").strip()
    if not raw:
        return []

    max_tokens = max(1, int(max_tokens))
    overlap_percent = max(0, min(90, int(overlap_percent)))
    max_chars = max(1, int(max_chars))

    segments = _merge_short_headers(_to_segments(raw))
    # 字符兜底：极端长段先按字符切开，再进入 token 打包
    flat: list[str] = []
    for seg in segments:
        flat.extend(_hard_split_chars(seg, max_chars))

    packed = _pack_by_tokens(flat, max_tokens=max_tokens, overlap_percent=overlap_percent)

    return [
        TextPiece(text=chunk, heading=_infer_heading(chunk), position=i)
        for i, chunk in enumerate(packed)
    ]


def _to_segments(text: str) -> list[str]:
    """拆成小段：标题行单独成段，其余按空行拆段落。"""
    segments: list[str] = []
    buf: list[str] = []

    def flush_buf() -> None:
        nonlocal buf
        if not buf:
            return
        block = "\n".join(buf).strip()
        buf = []
        if not block:
            return
        for para in re.split(r"\n\s*\n", block):
            p = para.strip()
            if p:
                segments.append(p)

    for line in text.split("\n"):
        if _HEADER_RE.match(line.strip()):
            flush_buf()
            segments.append(line.strip())
        else:
            buf.append(line)
    flush_buf()
    return segments


def _is_short_header(segment: str) -> bool:
    s = segment.strip()
    if "\n" in s:
        first, *rest = s.split("\n")
        if any(line.strip() for line in rest):
            return False
        s = first.strip()
    if not _HEADER_RE.match(s):
        return False
    return num_tokens(s) < _SHORT_HEADER_MAX_TOKENS


def _merge_short_headers(segments: list[str]) -> list[str]:
    if not segments:
        return []
    out: list[str] = []
    i = 0
    while i < len(segments):
        cur = segments[i]
        if _is_short_header(cur) and i + 1 < len(segments):
            out.append(f"{cur.strip()}\n{segments[i + 1]}")
            i += 2
            continue
        out.append(cur)
        i += 1
    return out


def _pack_by_tokens(
    segments: list[str],
    *,
    max_tokens: int,
    overlap_percent: int,
) -> list[str]:
    """对齐 RAGFlow naive_merge：按 token 阈值打包，新块带字符后缀 overlap。"""
    if not segments:
        return []

    cks: list[str] = [""]
    tk_nums: list[int] = [0]
    threshold = max_tokens * (100 - overlap_percent) / 100.0

    for sec in segments:
        for part in _hard_split_tokens(sec.strip(), max_tokens):
            t = f"\n{part}"
            tnum = num_tokens(t)
            if cks[-1] == "" or tk_nums[-1] > threshold:
                if cks[-1] and overlap_percent > 0:
                    prev = cks[-1]
                    t = prev[int(len(prev) * (100 - overlap_percent) / 100.0) :] + t
                cks.append(t)
                tk_nums.append(tnum)
            else:
                cks[-1] += t
                tk_nums[-1] += tnum

    return [c.strip() for c in cks if c and c.strip()]


def _hard_split_tokens(text: str, max_tokens: int) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    if num_tokens(text) <= max_tokens:
        return [text]

    enc = _encoder()
    tokens = enc.encode(text)
    chunks: list[str] = []
    start = 0
    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        piece = enc.decode(tokens[start:end]).strip()
        if piece:
            chunks.append(piece)
        start = end
    return chunks


def _hard_split_chars(text: str, max_chars: int) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            nl = text.rfind("\n", start, end)
            if nl > start + max_chars // 2:
                end = nl
        part = text[start:end].strip()
        if part:
            chunks.append(part)
        start = end if end > start else start + max_chars
    return chunks


def _infer_heading(text: str) -> str:
    for line in text.split("\n"):
        m = _HEADER_RE.match(line.strip())
        if m:
            return m.group(2).strip()
    return ""
