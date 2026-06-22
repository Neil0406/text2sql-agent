from __future__ import annotations
"""
schema.py — Utilities for reading SQLite schema information.
The result is injected into every LLM prompt so the model knows
the exact table / column structure without hallucinating.

# get_schema_info(db_path) 流程
#     │
#     ├─ 讀取 SQLite PRAGMA table_info（欄位名稱 + 型別）
#     ├─ 加入 row count（讓 LLM 知道資料量）
#     ├─ （可選）抓取前幾筆範例資料
#     └─ 回傳純文字，直接注入 LLM prompt 的 HumanMessage
"""
import sqlite3
from typing import Optional


def get_schema_info(db_path: str, include_samples: bool = True, sample_rows: int = 3) -> str:
    """
    Return a human-readable schema description suitable for an LLM prompt.
    Includes table names, column names + types, row counts, and optional sample rows.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in cursor.fetchall()]

    parts: list[str] = ["=== Database Schema ==="]

    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM [{table}]")
        row_count = cursor.fetchone()[0]

        cursor.execute(f"PRAGMA table_info([{table}])")
        columns = cursor.fetchall()  # (cid, name, type, notnull, dflt, pk)

        parts.append(f"\nTable: {table}  ({row_count:,} rows)")
        parts.append("Columns:")
        for col in columns:
            _, name, col_type, notnull, dflt, pk = col
            flags = []
            if pk:
                flags.append("PRIMARY KEY")
            if notnull:
                flags.append("NOT NULL")
            flag_str = f"  [{', '.join(flags)}]" if flags else ""
            parts.append(f"  - \"{name}\" {col_type}{flag_str}")

        if include_samples and row_count > 0:
            cursor.execute(f"SELECT * FROM [{table}] LIMIT {sample_rows}")
            rows = cursor.fetchall()
            col_names = [c[1] for c in columns]
            parts.append(f"Sample rows (first {len(rows)}):")
            for row in rows:
                sample = {col_names[i]: row[i] for i in range(len(col_names))}
                parts.append(f"  {sample}")

    conn.close()
    return "\n".join(parts)


def get_column_names(db_path: str, table_name: str) -> list[str]:
    """Return a list of column names for the given table."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info([{table_name}])")
    cols = [row[1] for row in cursor.fetchall()]
    conn.close()
    return cols


def get_distinct_values(db_path: str, table_name: str, column: str, limit: int = 50) -> list:
    """Return distinct values for a column (useful for enum-like fields)."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        f'SELECT DISTINCT "{column}" FROM [{table_name}] LIMIT ?', (limit,)
    )
    vals = [row[0] for row in cursor.fetchall()]
    conn.close()
    return vals
