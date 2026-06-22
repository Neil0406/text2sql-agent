"""
response_composer.py — Generate a natural, conversational response.

The composer uses the LLM to produce human-friendly text regardless of
whether the final format is verbal, table, or chart.  It also appends
the new turn to conversation_history for multi-turn support.

# response_composer_node(state) 流程
#     │
#     ├─ 讀取 query_results + response_format + intent + language
#     │   有 error → 直接用 verbal_response（不呼叫 LLM）
#     ├─ 組合 HumanMessage（含查詢結果摘要 + 格式指示 + 語言要求）
#     ├─ 呼叫 LLM 生成自然語言回覆
#     ├─ 將本輪對話追加到 conversation_history（多輪支援）
#     └─ 寫入 state["final_response"]
"""
import os

# LangChain imports are lazy (inside functions).

_SYSTEM = """\
You are a helpful data analyst assistant for a supermarket sales chatbot.
Your job is to write a concise, natural, conversational reply based on the
SQL query results provided.

Rules:
1. Reply in the SAME language as the user's question (Chinese or English).
2. Be conversational — do not just repeat raw numbers.
3. Highlight the most important insight (e.g., which branch is highest).
4. For "verbal" format: give a direct, complete sentence answer.
5. For "table"/"chart" format: write 1-3 sentences as an introduction/summary;
   mention that a table or chart is displayed below.
6. Keep the response under 150 words.
7. Do NOT include SQL code in your reply.\
"""


def _error_reply(error: str, language: str) -> str:
    zh = language == "zh"
    if "unsupported" in error or "prediction" in error.lower():
        return (
            "抱歉，目前資料集僅包含歷史交易紀錄，無法進行預測分析。\n"
            "我可以協助您查看過去的銷售趨勢，您想了解哪方面的歷史數據呢？"
            if zh else
            "Sorry, the dataset only contains historical records and cannot be used for predictions. "
            "I can help you analyse past sales trends — what would you like to explore?"
        )
    if "max_retries" in error:
        return (
            "抱歉，我無法正確理解您的問題，請換個方式提問。\n"
            "例如：「各分店的總銷售額」或「最暢銷的產品線是什麼」。"
            if zh else
            "Sorry, I couldn't generate a valid query for your question. "
            "Please try rephrasing — e.g., 'Total sales by branch' or 'Best-selling product line'."
        )
    return (
        f"抱歉，查詢過程中發生錯誤，請稍後再試。（{error}）"
        if zh else
        f"Sorry, an error occurred while processing your query. ({error})"
    )


def _summarise(results: list[dict], fmt: str) -> str:
    if not results:
        return "No results returned."
    keys = list(results[0].keys())
    if len(results) == 1 and len(keys) == 1:
        k, v = keys[0], results[0][keys[0]]
        return f"Single value: {k} = {v}"
    summary = f"Result rows: {len(results)}, columns: {keys}\n"
    for row in results[:5]:
        summary += f"  {row}\n"
    if len(results) > 5:
        summary += f"  … and {len(results) - 5} more rows"
    return summary.strip()


def compose_response(
    user_input: str,
    intent: dict,
    query_results: list,
    sql_query: str,
    response_format: str,
    error: str,
    conversation_history: list,
    llm,
) -> str:
    from langchain_core.messages import HumanMessage, SystemMessage
    language = (intent or {}).get("language", "zh")

    if error:
        return _error_reply(error, language)

    data_summary = _summarise(query_results, response_format)
    fmt_instruction = {
        "verbal": "Give a direct, concise verbal answer.",
        "table":  "Write a brief intro (1-2 sentences) then say 'See the table below for details.'",
        "chart":  "Write a brief intro/insight (1-2 sentences) then say 'See the chart below.'",
    }.get(response_format, "Give a direct verbal answer.")

    prompt = (
        f"User question: {user_input}\n\n"
        f"Response format: {response_format}\n"
        f"Query results summary:\n{data_summary}\n\n"
        f"Instruction: {fmt_instruction}\n"
        f"Language: {'Traditional Chinese (繁體中文)' if language == 'zh' else 'English'}"
    )

    messages = [SystemMessage(content=_SYSTEM), HumanMessage(content=prompt)]
    resp = llm.invoke(messages)
    return resp.content.strip()


def response_composer_node(state: dict) -> dict:
    """LangGraph node — Response Composer."""
    from langchain_ollama import ChatOllama
    model = os.getenv("OLLAMA_MODEL", "gemma4:e4b")
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    # Slightly higher temperature for more natural prose
    llm = ChatOllama(model=model, base_url=base_url, temperature=0.3)

    verbal = compose_response(
        user_input=state.get("user_input", ""),
        intent=state.get("intent") or {},
        query_results=state.get("query_results") or [],
        sql_query=state.get("sql_query", ""),
        response_format=state.get("response_format", "verbal"),
        error=state.get("error", ""),
        conversation_history=state.get("conversation_history") or [],
        llm=llm,
    )

    return {
        "verbal_response": verbal,
        "final_response": verbal,
        # Append this turn to conversation history
        "conversation_history": [
            {"role": "user",      "content": state.get("user_input", "")},
            {"role": "assistant", "content": verbal},
        ],
    }
