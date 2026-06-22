"""
response_router.py — Decide the response format based on:
  1. Intent's visualization_hint (from LLM analysis)
  2. Semantic keywords in the user's question
  3. Structure of the query results (row count, column count, numeric cols)

Output: sets  state["response_format"]  and  state["chart_type"]

# response_router_node(state) 流程
#     │
#     ├─ 有 error 或結果為空          → verbal
#     ├─ 結果只有一個單一數值         → verbal
#     │
#     ├─ 關鍵字判斷（最高優先）
#     │   含「比較/趨勢/圖/佔比」等  → chart（依關鍵字選 bar/line/pie）
#     │   含「列出/哪些/明細」等     → table
#     │
#     ├─ 採用 LLM 的 visualization_hint 建議
#     │
#     └─ 資料結構兜底判斷
#         n_rows == 1              → verbal
#         n_rows <= 6 + 有數值欄  → chart
#         n_rows <= 20             → table
#         n_rows > 20              → chart（太多列用圖比較好讀）
"""

# Keyword lists (Chinese + English)
_CHART_KW = [
    "趨勢", "trend", "比較", "compare", "comparison",
    "分佈", "distribution", "佔比", "percentage", "proportion",
    "圖", "chart", "plot", "視覺化", "visualize", "breakdown",
]
_TABLE_KW = [
    "列出", "list", "哪些", "which", "顯示", "show",
    "明細", "detail", "清單", "all", "every",
]


def _count_numeric_cols(row: dict) -> int:
    return sum(1 for v in row.values() if isinstance(v, (int, float)))


def route_response(state: dict) -> dict:
    """Core routing logic — pure function, easily unit-testable."""
    intent = state.get("intent") or {}
    results = state.get("query_results") or []
    user_input = (state.get("user_input") or "").lower()
    error = state.get("error")

    # Error / empty results → always verbal
    if error or not results:
        return {"response_format": "verbal", "chart_type": None}

    # Single-value result → always verbal
    if len(results) == 1 and len(results[0]) == 1:
        return {"response_format": "verbal", "chart_type": None}

    # Pull hints from intent (may be overridden below)
    viz_hint = intent.get("visualization_hint", "verbal")
    chart_type = intent.get("chart_type")  # may be None

    # ── Keyword overrides ──────────────────────────────────────────────────
    has_chart_kw = any(k in user_input for k in _CHART_KW)
    has_table_kw = any(k in user_input for k in _TABLE_KW)

    if has_chart_kw:
        viz_hint = "chart"
        if not chart_type:
            if any(k in user_input for k in ["趨勢", "trend", "monthly", "每月", "time"]):
                chart_type = "line"
            elif any(k in user_input for k in ["佔比", "percentage", "proportion", "分佈"]):
                chart_type = "pie"
            else:
                chart_type = "bar"
    elif has_table_kw:
        viz_hint = "table"

    # ── Result-structure heuristics ────────────────────────────────────────
    n_rows = len(results)
    n_numeric = _count_numeric_cols(results[0])

    if viz_hint == "chart" and n_numeric > 0 and n_rows >= 2:
        return {"response_format": "chart", "chart_type": chart_type or "bar"}

    if viz_hint == "table":
        if n_rows <= 20:
            return {"response_format": "table", "chart_type": None}
        # Too many rows → chart is more readable
        return {"response_format": "chart", "chart_type": chart_type or "bar"}

    # Default heuristics
    if n_rows == 1:
        return {"response_format": "verbal", "chart_type": None}
    if n_rows <= 6 and n_numeric >= 1:
        return {"response_format": "chart", "chart_type": chart_type or "bar"}
    if n_rows <= 20:
        return {"response_format": "table", "chart_type": None}
    return {"response_format": "chart", "chart_type": chart_type or "bar"}


def response_router_node(state: dict) -> dict:
    """LangGraph node — Response Router."""
    return route_response(state)
