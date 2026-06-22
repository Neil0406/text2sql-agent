from __future__ import annotations
"""
sql_validator.py — Validates generated SQL for safety and correctness.

Security rules enforced:
  1. Only SELECT statements allowed.
  2. Block dangerous DDL/DML keywords (word-boundary aware).
  3. Block multiple SQL statements (prevents stacked-query injection).
  4. Validate syntax via SQLite EXPLAIN.

# sql_validator_node(state) 流程
#     │
#     ├─ 讀取 state["sql_query"] + retry_count
#     ├─ 第一層：必須以 SELECT 開頭
#     ├─ 第二層：regex 掃描危險關鍵字黑名單（INSERT/DROP/DELETE 等）
#     ├─ 第三層：sqlparse 確認非多句 + SQLite EXPLAIN 驗證語法
#     │
#     ├─ 驗證通過                      → 清除 error，繼續往 sql_executor
#     ├─ 驗證失敗 + retry < MAX_RETRIES → 寫入 error，回到 text2sql 重試
#     └─ 驗證失敗 + retry >= MAX_RETRIES → 寫入 "max_retries_exceeded"
"""
import os
import re
import sqlite3

import sqlparse

# Maximum number of re-generation attempts before giving up
MAX_RETRIES = 3

# Keywords that must never appear in any generated SQL
_DANGEROUS = [
    "INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE",
    "GRANT", "REVOKE", "ATTACH", "DETACH", "VACUUM", "PRAGMA",
    "REPLACE", "MERGE", "CALL", "EXEC", "EXECUTE",
]


def validate_sql(sql: str, db_path: str) -> tuple[bool, str]:
    """
    Validate a SQL string for safety and SQLite syntax correctness.

    Returns
    -------
    (True, "")            — valid and safe
    (False, error_msg)    — invalid; error_msg explains the problem
    """
    if not sql or not sql.strip():
        return False, "Empty SQL query generated."

    sql_clean = sql.strip().rstrip(";").strip()
    sql_upper = sql_clean.upper()

    # 1. Must start with SELECT
    first_token = sql_upper.lstrip().split()[0] if sql_upper.lstrip() else ""
    if first_token != "SELECT":
        return False, f"Only SELECT queries are allowed. Got keyword: '{first_token}'"

    # 2. Block dangerous keywords (word-boundary check to avoid false positives)
    for kw in _DANGEROUS:
        if re.search(r"\b" + kw + r"\b", sql_upper):
            return False, f"Dangerous SQL keyword detected: '{kw}'"

    # 3. Block multiple statements (SQL injection via stacking)
    try:
        parsed = sqlparse.parse(sql_clean)
        # sqlparse may return multiple statements even for a single one,
        # so filter out empty ones
        real_stmts = [s for s in parsed if str(s).strip()]
        if len(real_stmts) > 1:
            return False, "Multiple SQL statements are not allowed."
    except Exception as exc:
        return False, f"SQL parse error: {exc}"

    # 4. SQLite EXPLAIN (syntax + table/column existence check)
    try:
        conn = sqlite3.connect(db_path)
        conn.execute(f"EXPLAIN {sql_clean}")
        conn.close()
    except sqlite3.Error as exc:
        return False, f"SQL syntax/execution error: {exc}"
    except Exception as exc:
        return False, f"Validation error: {exc}"

    return True, ""


def sql_validator_node(state: dict) -> dict:
    """LangGraph node — SQL Validator."""
    db_path = os.getenv("DB_PATH", "data/supermarket.db")
    intent = state.get("intent") or {}

    # Unsupported query types bypass SQL entirely
    if intent.get("query_type") == "unsupported" or intent.get("is_prediction"):
        return {"error": "unsupported_query"}

    sql = state.get("sql_query", "")
    retry_count = state.get("retry_count", 0)

    is_valid, error_msg = validate_sql(sql, db_path)

    if is_valid:
        return {"sql_error": None, "error": None}

    new_retry = retry_count + 1
    if new_retry >= MAX_RETRIES:
        return {
            "retry_count": new_retry,
            "sql_error": error_msg,
            "error": "max_retries_exceeded",
        }
    return {
        "retry_count": new_retry,
        "sql_error": error_msg,
        "error": "validation_failed",
    }
