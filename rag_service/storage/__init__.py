"""存储层。"""

from rag_service.storage.db import connect, ensure_data_dirs, init_db

__all__ = ["connect", "ensure_data_dirs", "init_db"]
