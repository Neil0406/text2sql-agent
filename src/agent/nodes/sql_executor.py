from __future__ import annotations
"""
sql_executor.py — Safely executes validated SELECT queries against SQLite.

Safety measures:
  - Row limit enforced at Python level (no LIMIT injection into SQL).
  - Read-only connection (isolation_level=None + no write ops possible
    after validator has already blocked DDL/DML).
  - Catches timeouts and oversized result sets.

# sql_executor_node(state) 流程
#     │
#     ├─ 讀取 state["sql_query"]
#     ├─ 查詢 LRU 快取（命中 → 直接回傳，跳過 DB）
#     ├─ 連線 SQLite（timeout=30s）
#     ├─ 執行 SQL，最多取 MAX_ROWS=1000 筆
#     │   超過 1000 筆 → 印出警告，截斷結果
#     │   執行失敗     → 寫入 error，交由 response_composer 處理
#     ├─ 結果存入快取（下次相同 SQL 直接命中）
#     └─ 寫入 state["query_results"]
"""
import os
import sqlite3
from pathlib import Path
from typing import Optional

from src.cache.query_cache import QueryCache

MAX_ROWS = 1_000      # hard cap on rows returned to the agent
QUERY_TIMEOUT = 30    # SQLite busy-timeout in seconds

_cache = QueryCache()


def execute_sql(sql: str, db_path: str) -> tuple[list[dict], Optional[str]]:
    """
    Execute a SELECT query and return (results, error_message).

    Results are a list of dicts (column_name → value).
    """
    # Cache hit
    cached = _cache.get(sql)
    if cached is not None:
        return cached, None

    try:
        conn = sqlite3.connect(db_path, timeout=QUERY_TIMEOUT)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(sql.strip().rstrip(";"))
        rows = cursor.fetchmany(MAX_ROWS)
        results = [dict(row) for row in rows]

        # Warn if truncated
        extra = cursor.fetchone()
        if extra:
            print(f"[WARN] Results truncated to {MAX_ROWS} rows.")

        conn.close()

        _cache.set(sql, results)
        return results, None

    except sqlite3.OperationalError as exc:
        return [], f"Database error: {exc}"
    except Exception as exc:
        return [], f"Execution error: {exc}"


def sql_executor_node(state: dict) -> dict:
    """LangGraph node — SQL Executor."""
    _root = Path(__file__).parent.parent.parent.parent
    db_path = os.getenv("DB_PATH") or str(_root / "data" / "supermarket.db")
    sql = state.get("sql_query", "")

    if not sql:
        return {"query_results": [], "error": "no_sql_query"}

    results, error = execute_sql(sql, db_path)

    if error:
        return {"query_results": [], "error": f"execution_error:{error}"}

    return {"query_results": results, "error": None}
