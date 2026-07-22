"""流式输出：FAQ LLM token 回调总线（contextvars，按请求隔离）。"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Callable, Iterator

TokenCallback = Callable[[str], None]

_token_cb: ContextVar[TokenCallback | None] = ContextVar("cs_token_cb", default=None)


def get_token_callback() -> TokenCallback | None:
    return _token_cb.get()


@contextmanager
def token_callback(cb: TokenCallback | None) -> Iterator[None]:
    token = _token_cb.set(cb)
    try:
        yield
    finally:
        _token_cb.reset(token)
