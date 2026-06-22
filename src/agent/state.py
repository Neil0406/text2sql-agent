from __future__ import annotations
"""
state.py — LangGraph AgentState definition for the Text2SQL agent.

All nodes read from and write into this TypedDict.
conversation_history uses Annotated[list, operator.add] so each node
can append messages without knowing the full history.

# AgentState 是所有節點共用的資料結構（類似 request context）
#     │
#     ├─ Input   : user_input（使用者問題）
#     ├─ History : conversation_history（多輪對話記錄，自動 append）
#     ├─ Middle  : intent, schema_info, sql_query,
#     │            retry_count, sql_error, query_results
#     └─ Output  : response_format, chart_type,
#                  verbal_response, chart_path, final_response
"""
import operator
from typing import Annotated, Optional, TypedDict


class AgentState(TypedDict):
    # ── Input ────────────────────────────────────────────────────────────────
    user_input: str

    # ── Multi-turn conversation history ──────────────────────────────────────
    # operator.add means each node's return value is APPENDED (not replaced)
    conversation_history: Annotated[list, operator.add]

    # ── Intent parsing ───────────────────────────────────────────────────────
    intent: Optional[dict]
    # Shape: {
    #   "query_type":        "aggregation" | "detail" | "trend" | "comparison" | "unsupported"
    #   "entities":          dict  (date_range, branch, product_line, …)
    #   "visualization_hint":"verbal" | "table" | "chart"
    #   "chart_type":        "bar" | "line" | "pie" | "scatter" | null
    #   "language":          "zh" | "en"
    #   "is_prediction":     bool
    # }

    # ── Schema context ────────────────────────────────────────────────────────
    schema_info: Optional[str]

    # ── SQL generation ────────────────────────────────────────────────────────
    sql_query: Optional[str]
    retry_count: int           # how many re-generation attempts so far
    sql_error: Optional[str]   # last validation / execution error message

    # ── Query results ─────────────────────────────────────────────────────────
    query_results: Optional[list]   # list[dict]

    # ── Response formatting ───────────────────────────────────────────────────
    response_format: Optional[str]  # "verbal" | "table" | "chart"
    chart_type: Optional[str]       # "bar" | "line" | "pie" | "scatter"

    # ── Output ────────────────────────────────────────────────────────────────
    verbal_response: Optional[str]
    chart_path: Optional[str]
    final_response: Optional[str]

    # ── Error sentinel ────────────────────────────────────────────────────────
    error: Optional[str]
    # "unsupported_query" | "max_retries_exceeded" | "validation_failed"
    # | "execution_error:<msg>" | None
