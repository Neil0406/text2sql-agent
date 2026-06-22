from __future__ import annotations
"""
text2sql.py — Convert natural-language question + schema → SQLite SELECT query.

Prompt strategy
---------------
- System prompt enforces SELECT-only rules (defence-in-depth alongside validator).
- User prompt includes: schema, conversation history, intent analysis, prior error.
- SQL is extracted from the LLM response with a regex cascade.

# text2sql_node(state) 流程
#     │
#     ├─ 讀取 intent + schema_info + conversation_history
#     │   重試時額外帶入 sql_error（告知 LLM 上次哪裡錯）
#     ├─ 組合 HumanMessage prompt（Schema + 意圖分析 + 錯誤回饋）
#     ├─ 呼叫 LLM 生成 SQL
#     ├─ 用 regex 從回應中提取 SQL
#     │   優先抓 ```sql ... ``` → 裸 SELECT → 原始文字
#     └─ 寫入 state["sql_query"]
"""
import os
import re

# LangChain imports are lazy (inside functions) so this module can be
# imported in tests without requiring langchain to be installed.

# ── Prompt ───────────────────────────────────────────────────────────────────
_SYSTEM = """\
You are an expert SQLite SQL writer for a supermarket sales analytics system.

STRICT RULES — violating any rule makes the query invalid:
1. Generate ONLY a single SELECT statement.
2. NEVER use INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, TRUNCATE, PRAGMA,
   ATTACH, DETACH, VACUUM, GRANT, REVOKE, EXEC, EXECUTE, or any DDL/DML.
3. NEVER use sub-queries that modify data (e.g. CTEs with INSERT).
4. Column names that contain spaces MUST be wrapped in double-quotes:
   e.g.  "Product line",  "Unit price",  "Tax 5%",  "Customer type"
5. The only table is: supermarket_sales
6. Use SQLite syntax only (strftime, date(), julianday(), etc.).
7. Dates in the table are stored as TEXT in ISO-8601 format: YYYY-MM-DD.
8. Always wrap your final answer in a ```sql ... ``` code block.

Think step-by-step silently, then output ONLY the SQL code block.\
"""


def _extract_sql(text: str) -> str:
    """Extract the first SQL statement from the LLM response."""
    # 1. Explicit ```sql … ``` block
    m = re.search(r"```sql\s*([\s\S]+?)\s*```", text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # 2. Generic ``` … ``` block containing SELECT
    m = re.search(r"```\s*(SELECT[\s\S]+?)\s*```", text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # 3. Bare SELECT … ; or end-of-string
    m = re.search(r"(SELECT\s[\s\S]+?)(?:;|$)", text, re.IGNORECASE)
    if m:
        return m.group(1).strip().rstrip(";")
    return text.strip()


def generate_sql(
    user_input: str,
    intent: dict,
    schema_info: str,
    conversation_history: list,
    sql_error: str | None,
    retry_count: int,
    llm,
) -> str:
    from langchain_core.messages import HumanMessage, SystemMessage
    history_ctx = ""
    if conversation_history:
        recent = conversation_history[-4:]
        history_ctx = "\nConversation context:\n" + "\n".join(
            f"{m.get('role','user').capitalize()}: {m.get('content','')}"
            for m in recent
        ) + "\n"

    error_ctx = ""
    if sql_error and retry_count > 0:
        error_ctx = (
            f"\n\n⚠️  Previous attempt (#{retry_count}) FAILED with error:\n"
            f"    {sql_error}\n"
            "Please fix the issue and generate a corrected SQL query."
        )

    prompt = f"""\
{schema_info}
{history_ctx}
User question: {user_input}

Intent analysis:
  - query_type       : {intent.get('query_type', 'unknown')}
  - entities         : {intent.get('entities', {})}
  - visualization    : {intent.get('visualization_hint', 'verbal')}
{error_ctx}

Write a SQLite SELECT query to answer the user's question.
Wrap it in ```sql ... ```.
"""

    messages = [SystemMessage(content=_SYSTEM), HumanMessage(content=prompt)]
    resp = llm.invoke(messages)
    return _extract_sql(resp.content)


def text2sql_node(state: dict) -> dict:
    """LangGraph node — Text2SQL Generator."""
    from langchain_ollama import ChatOllama
    model = os.getenv("OLLAMA_MODEL", "gemma4:e4b")
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    llm = ChatOllama(model=model, base_url=base_url, temperature=0)

    sql = generate_sql(
        user_input=state["user_input"],
        intent=state.get("intent") or {},
        schema_info=state.get("schema_info") or "",
        conversation_history=state.get("conversation_history") or [],
        sql_error=state.get("sql_error"),
        retry_count=state.get("retry_count", 0),
        llm=llm,
    )
    return {"sql_query": sql, "sql_error": None}
