"""知识库检索与 FAQ 回答（关键词检索 + 可选大模型生成）。"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from customer_service.config.settings import get_settings

logger = logging.getLogger(__name__)

_CJK_RUN = re.compile("[\u4e00-\u9fff]+")
_LATIN = re.compile(r"[A-Za-z0-9_]{2,}")


@dataclass(frozen=True)
class Passage:
    source: str
    text: str
    score: float

    def as_doc(self) -> str:
        return f"[{self.source}]\n{self.text}"


def _tokenize(text: str) -> list[str]:
    """英文按词；中文按连续片段 + 2/3/4 字滑动窗口，便于短问命中。"""
    text = text or ""
    tokens: list[str] = []
    for word in _LATIN.findall(text):
        tokens.append(word.lower())
    for run in _CJK_RUN.findall(text):
        if len(run) <= 4:
            tokens.append(run)
        else:
            for n in (2, 3, 4):
                for i in range(0, len(run) - n + 1):
                    tokens.append(run[i : i + n])
    # 去重保序
    seen: set[str] = set()
    out: list[str] = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out

def _split_chunks(text: str, *, source: str) -> list[tuple[str, str]]:
    """按二级标题切块；无标题时按空行分段。"""
    text = text.strip()
    if not text:
        return []

    parts = re.split(r"(?m)^##\s+", text)
    chunks: list[tuple[str, str]] = []
    if len(parts) == 1:
        for block in re.split(r"\n\s*\n", text):
            block = block.strip()
            if block:
                chunks.append((source, block))
        return chunks

    intro = parts[0].strip()
    if intro:
        chunks.append((source, intro))
    for part in parts[1:]:
        part = part.strip()
        if not part:
            continue
        chunks.append((source, "## " + part))
    return chunks


@lru_cache(maxsize=4)
def _load_corpus(knowledge_dir: str) -> tuple[Passage, ...]:
    root = Path(knowledge_dir)
    if not root.is_dir():
        return ()

    raw: list[tuple[str, str]] = []
    for path in sorted(root.glob("*.md")):
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue
        raw.extend(_split_chunks(content, source=path.name))

    return tuple(Passage(source=src, text=body, score=0.0) for src, body in raw)


def clear_corpus_cache() -> None:
    _load_corpus.cache_clear()


def _score(query_tokens: list[str], chunk_text: str, query: str) -> float:
    if not query_tokens and not query.strip():
        return 0.0

    lower = chunk_text.lower()
    score = 0.0

    # 整句子串加分（适合「退款政策」这类短问）
    q = query.strip().lower()
    if len(q) >= 2 and q in lower:
        score += 5.0

    for tok in query_tokens:
        if tok in lower:
            score += 1.0
            # 标题命中额外加分
            head = chunk_text.split("\n", 1)[0].lower()
            if tok in head:
                score += 0.5

    return score


def retrieve_passages(
    query: str,
    *,
    top_k: int = 4,
    knowledge_dir: Path | None = None,
) -> list[Passage]:
    """关键词打分检索，返回带来源的片段（按分数降序）。"""
    root = Path(knowledge_dir) if knowledge_dir is not None else get_settings().knowledge_dir
    corpus = _load_corpus(str(root.resolve()))
    tokens = _tokenize(query)

    scored: list[Passage] = []
    for p in corpus:
        s = _score(tokens, p.text, query)
        if s > 0:
            scored.append(Passage(source=p.source, text=p.text, score=s))

    scored.sort(key=lambda x: (-x.score, x.source))
    return scored[: max(0, top_k)]


def retrieve(
    query: str,
    *,
    top_k: int = 4,
    knowledge_dir: Path | None = None,
) -> list[str]:
    """检索知识片段，每条含来源文件名。"""
    return [
        p.as_doc()
        for p in retrieve_passages(query, top_k=top_k, knowledge_dir=knowledge_dir)
    ]


def retrieve_docs(
    query: str,
    *,
    top_k: int | None = None,
    knowledge_dir: Path | None = None,
) -> list[str]:
    """按 `RAG_PROVIDER` 选择本地或 HTTP 召回。"""
    settings = get_settings()
    k = settings.rag_top_k if top_k is None else top_k
    if settings.rag_provider == "http":
        from customer_service.services import rag_client

        logger.info(
            "RAG provider=http base=%s kb=%s top_k=%s",
            settings.rag_base_url,
            settings.rag_kb_id,
            k,
        )
        return rag_client.retrieve(query, top_k=k)
    return retrieve(query, top_k=k, knowledge_dir=knowledge_dir)


def answer_with_context(query: str, docs: list[str]) -> str:
    """离线模板回答：拼接检索片段（无模型时的降级）。"""
    q = (query or "").strip() or "（空问题）"
    if not docs:
        return (
            f"关于「{q}」，知识库中暂未找到相关内容。"
            "您可以换种问法，或创建工单 / 转人工进一步处理。"
        )

    lines = [
        f"关于「{q}」，根据知识库检索到以下说明：",
        "",
    ]
    for i, doc in enumerate(docs, start=1):
        lines.append(f"—— 参考 {i} ——")
        lines.append(doc.strip())
        lines.append("")
    lines.append("（离线降级：未调用大模型。）")
    return "\n".join(lines).strip()


@lru_cache(maxsize=1)
def _load_faq_prompt() -> str:
    path = Path(__file__).resolve().parents[1] / "prompts" / "faq.md"
    return path.read_text(encoding="utf-8")


def answer_with_llm(
    query: str,
    docs: list[str],
    *,
    on_token: Callable[[str], None] | None = None,
) -> str | None:
    """用检索片段 + 规范提示词调用大模型生成回答；失败返回 None。

    ``on_token`` 若提供，则走 ``llm.stream`` 并逐段回调，便于 SSE 流式输出。
    """
    settings = get_settings()
    if not settings.has_openai_key:
        return None

    q = (query or "").strip() or "（空问题）"
    if not docs:
        context_block = "（未检索到相关知识库片段）"
    else:
        context_block = "\n\n".join(
            f"### 片段 {i}\n{doc.strip()}" for i, doc in enumerate(docs, start=1)
        )

    user_block = (
        f"## 用户问题\n{q}\n\n"
        f"## 知识库检索片段\n{context_block}\n\n"
        "## 请作答"
    )

    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            temperature=0.2,
            streaming=bool(on_token),
        )
        messages = [
            SystemMessage(content=_load_faq_prompt()),
            HumanMessage(content=user_block),
        ]
        if on_token is None:
            resp = llm.invoke(messages)
            text = str(getattr(resp, "content", "") or "").strip()
            return text or None

        parts: list[str] = []
        for chunk in llm.stream(messages):
            delta = getattr(chunk, "content", None)
            if not delta:
                continue
            piece = delta if isinstance(delta, str) else str(delta)
            if not piece:
                continue
            parts.append(piece)
            on_token(piece)
        text = "".join(parts).strip()
        return text or None
    except Exception:
        logger.exception("FAQ LLM 生成失败，将尝试离线降级")
        return None


def answer_faq(
    query: str,
    *,
    top_k: int | None = None,
    knowledge_dir: Path | None = None,
    use_llm: bool = True,
) -> tuple[str, list[str]]:
    """检索知识库并生成回答：优先大模型，失败/无 Key 时离线模板。"""
    from customer_service.services.stream_bus import get_token_callback

    docs = retrieve_docs(query, top_k=top_k, knowledge_dir=knowledge_dir)
    settings = get_settings()
    on_token = get_token_callback()
    if use_llm and settings.has_openai_key:
        llm_answer = answer_with_llm(query, docs, on_token=on_token)
        if llm_answer:
            return llm_answer, docs
        if not settings.allow_offline_fallback:
            return (
                "暂时无法生成回答，请稍后重试，或转人工处理。",
                docs,
            )
    offline = answer_with_context(query, docs)
    # 非流式 LLM 路径（寒暄外的离线 FAQ）也推一次完整文本，方便前端统一渲染
    if on_token and offline:
        on_token(offline)
    return offline, docs
