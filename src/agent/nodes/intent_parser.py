"""
intent_parser.py — Analyse the user's natural-language question and
extract structured intent metadata used by downstream nodes.

Output (intent dict):
  query_type        : "aggregation" | "detail" | "trend" | "comparison" | "unsupported"
  entities          : { date_range, branch, product_line, customer_type, … }
  visualization_hint: "verbal" | "table" | "chart"
  chart_type        : "bar" | "line" | "pie" | "scatter" | null
  language          : "zh" | "en"
  is_prediction     : bool

# intent_parser_node(state) 流程
#     │
#     ├─ 讀取 user_input + conversation_history
#     ├─ 呼叫 LLM（SystemMessage 定義格式 + HumanMessage 帶入問題）
#     ├─ 解析 LLM 回應為 JSON（intent dict）
#     │   解析失敗 → 回傳 fallback intent（query_type: unsupported）
#     └─ 寫入 state["intent"]
"""
import json
import os
import re

# LangChain imports are lazy (inside functions) to support import without langchain installed.

# ── Prompt ───────────────────────────────────────────────────────────────────
_SYSTEM = """\
You are an intent parser for a supermarket sales analytics chatbot.
Given the user's question (and optional conversation history for context),
output ONLY a valid JSON object with this exact structure:

{
  "query_type": "aggregation|detail|trend|comparison|unsupported",
  "entities": {
    "date_range": null | {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"},
    "branch": null | ["Alex","Giza","Cairo"],
    "product_line": null | ["Health and beauty", ...],
    "customer_type": null | ["Member","Normal"],
    "gender": null | ["Male","Female"],
    "payment": null | ["Ewallet","Cash","Credit card"],
    "rating_min": null | <number>,
    "rating_max": null | <number>,
    "other": null | "<free text>"
  },
  "visualization_hint": "verbal|table|chart",
  "chart_type": null | "bar|line|pie|scatter",
  "language": "zh|en",
  "is_prediction": false,
  "reasoning": "<one sentence>"
}

Guidelines
----------
query_type:
  aggregation  → single numeric answer  ("how many", "total", "average", "最高", "共")
  detail       → row-level listing      ("list", "show", "列出", "哪些")
  trend        → time-series            ("trend", "monthly", "over time", "趨勢", "每月")
  comparison   → cross-group comparison ("compare", "比較", "vs", "各分店", "各產品線")
  unsupported  → prediction / mutation  ("predict", "forecast", "預測", "update")

visualization_hint:
  verbal  → single value or direct question
  table   → multi-row detail (≤20 rows typical)
  chart   → grouped/aggregated numeric data (≥2 groups)

chart_type:
  bar     → categorical comparison
  line    → time-series trend
  pie     → proportion / share ("佔比", "percentage", "分佈")
  scatter → correlation

Output ONLY the JSON. No markdown fences, no extra text.\
"""


def _extract_json(text: str) -> dict:
    """Robustly extract a JSON object from LLM output."""
    # 1. Direct parse
    try:
        return json.loads(text.strip())
    except (json.JSONDecodeError, ValueError):
        pass
    # 2. JSON inside code fences
    for pattern in (r"```json\s*([\s\S]+?)\s*```", r"```\s*([\s\S]+?)\s*```"):
        m = re.search(pattern, text)
        if m:
            try:
                return json.loads(m.group(1))
            except (json.JSONDecodeError, ValueError):
                pass
    # 3. First { … } block
    m = re.search(r"\{[\s\S]+\}", text)
    if m:
        try:
            return json.loads(m.group())
        except (json.JSONDecodeError, ValueError):
            pass
    return {}


def _rule_based_fallback(user_input: str) -> dict:
    """Deterministic fallback when JSON parsing fails."""
    text = user_input.lower()
    has_chinese = bool(re.search(r"[\u4e00-\u9fff]", user_input))
    lang = "zh" if has_chinese else "en"

    unsupported = ["預測", "forecast", "predict", "下個月", "next month", "未來", "future"]
    if any(k in text for k in unsupported):
        return {
            "query_type": "unsupported", "entities": {},
            "visualization_hint": "verbal", "chart_type": None,
            "language": lang, "is_prediction": True, "reasoning": "prediction detected",
        }

    chart_kw = ["趨勢", "trend", "比較", "compare", "分佈", "distribution",
                "佔比", "percentage", "proportion", "圖", "chart", "plot"]
    table_kw = ["列出", "list", "哪些", "which", "顯示", "show", "明細", "detail"]

    if any(k in text for k in chart_kw):
        ctype = "line" if ("趨勢" in text or "trend" in text) else (
            "pie" if ("佔比" in text or "percentage" in text or "proportion" in text) else "bar"
        )
        return {
            "query_type": "trend" if "trend" in text or "趨勢" in text else "comparison",
            "entities": {}, "visualization_hint": "chart", "chart_type": ctype,
            "language": lang, "is_prediction": False, "reasoning": "chart keyword",
        }
    if any(k in text for k in table_kw):
        return {
            "query_type": "detail", "entities": {},
            "visualization_hint": "table", "chart_type": None,
            "language": lang, "is_prediction": False, "reasoning": "table keyword",
        }
    return {
        "query_type": "aggregation", "entities": {},
        "visualization_hint": "verbal", "chart_type": None,
        "language": lang, "is_prediction": False, "reasoning": "default aggregation",
    }


def parse_intent(user_input: str, conversation_history: list, llm) -> dict:
    from langchain_core.messages import HumanMessage, SystemMessage
    # Build a short history snippet for context (last 2 exchanges = 4 messages)
    history_ctx = ""
    if conversation_history:
        recent = conversation_history[-4:]
        history_ctx = "\nRecent conversation:\n" + "\n".join(
            f"{m.get('role','user').capitalize()}: {m.get('content','')}" for m in recent
        ) + "\n"

    user_msg = f"{history_ctx}\nUser question: {user_input}"
    messages = [SystemMessage(content=_SYSTEM), HumanMessage(content=user_msg)]

    try:
        resp = llm.invoke(messages)
        intent = _extract_json(resp.content)
        if intent and "query_type" in intent:
            return intent
    except Exception as exc:
        print(f"[WARN] Intent parser LLM error: {exc}")

    # Fallback
    return _rule_based_fallback(user_input)


def intent_parser_node(state: dict) -> dict:
    """LangGraph node — Intent Parser."""
    from langchain_ollama import ChatOllama
    model = os.getenv("OLLAMA_MODEL", "gemma4:e4b")
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    llm = ChatOllama(model=model, base_url=base_url, temperature=0, format="json")

    intent = parse_intent(
        user_input=state["user_input"],
        conversation_history=state.get("conversation_history") or [],
        llm=llm,
    )
    return {"intent": intent}
