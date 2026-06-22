"""
query_cache.py — Simple in-memory LRU-style cache for SQL query results.

Keyed by the normalised SQL string.  Prevents redundant DB round-trips
for repeated questions (e.g., follow-up questions that reuse prior queries).

# QueryCache 運作方式
#     │
#     ├─ get(sql)：正規化 SQL（統一空白）→ 查 OrderedDict
#     │             命中 → 移到尾端（標記為最近使用）→ 回傳結果
#     │             未命中 → 回傳 None
#     ├─ set(sql, results)：存入 → 若超過 max_size=128
#     │                             → 移除最舊的一筆（LRU 淘汰）
#     └─ clear()：清空所有快取
"""
from collections import OrderedDict
from typing import Optional


class QueryCache:
    """Thread-safe (single-process) in-memory cache with a max-size eviction."""

    def __init__(self, max_size: int = 128):
        self._store: OrderedDict[str, list] = OrderedDict()
        self._max_size = max_size

    @staticmethod
    def _key(sql: str) -> str:
        return " ".join(sql.lower().split())  # normalise whitespace

    def get(self, sql: str) -> Optional[list]:
        key = self._key(sql)
        if key in self._store:
            self._store.move_to_end(key)  # mark as recently used
            return self._store[key]
        return None

    def set(self, sql: str, results: list) -> None:
        key = self._key(sql)
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = results
        if len(self._store) > self._max_size:
            self._store.popitem(last=False)  # evict oldest

    def clear(self) -> None:
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)
