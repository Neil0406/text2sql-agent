"""
app.py — Streamlit Web UI for the Text2SQL AI Agent.

Run with:  streamlit run src/app.py

# streamlit run src/app.py
#     │
#     ├─ 載入 .env（LangSmith 等環境變數）
#     ├─ 初始化 session_state（對話歷史、DB 路徑）
#     ├─ 確認資料庫，若不存在則自動初始化
#     │
#     └─ 渲染聊天介面
#         顯示歷史訊息（st.chat_message）
#         使用者輸入 → run_agent()
#           ├─ 口語回覆 → 顯示文字
#           ├─ 表格     → st.dataframe()
#           └─ 圖表     → st.image()
"""
import os
import sys
from pathlib import Path

# Must come before any LangChain import
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")  # 明確指定根目錄的 .env
if os.getenv("LANGSMITH_API_KEY"):
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ.setdefault("LANGCHAIN_PROJECT", os.getenv("LANGSMITH_PROJECT", "text2sql-agent"))

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import streamlit as st
import pandas as pd

from src.agent.graph import run_agent
from src.db.init_db import init_database


# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Text2SQL Agent — Supermarket Sales",
    page_icon="🛒",
    layout="wide",
)

# ── Session state ─────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []          # displayed chat history
if "conv_history" not in st.session_state:
    st.session_state.conv_history = []      # LangGraph conversation_history


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ Settings")

    debug_mode = st.toggle("Show SQL query", value=False)
    if st.button("🗑️ Clear conversation"):
        st.session_state.messages = []
        st.session_state.conv_history = []
        st.rerun()

    st.divider()
    st.markdown("**DB Status**")
    db_path = os.getenv("DB_PATH", "data/supermarket.db")
    csv_path = str(ROOT / "data" / "SuperMarket Analysis.csv")

    if not os.path.exists(db_path):
        if os.path.exists(csv_path):
            with st.spinner("Initialising database …"):
                init_database(csv_path, db_path)
            st.success("Database ready ✅")
        else:
            st.error("Dataset not found.\nPlace CSV at:\n`data/SuperMarket Analysis.csv`")
    else:
        st.success("Database ready ✅")

    st.divider()
    st.markdown(
        "**Sample questions**\n"
        "- 這個超市總共有多少筆交易？\n"
        "- 各分店的總銷售額是多少？\n"
        "- 比較各產品線的銷售佔比\n"
        "- 列出所有評分高於 9 分的會員交易\n"
        "- 每月的銷售趨勢為何？"
    )


# ── Main chat area ────────────────────────────────────────────────────────────
st.title("🛒 Text2SQL AI Agent")
st.caption("Ask questions about supermarket sales data in Chinese or English.")

# Render existing messages
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("table") is not None:
            st.dataframe(pd.DataFrame(msg["table"]), use_container_width=True)
        if msg.get("chart_path") and os.path.exists(msg["chart_path"]):
            st.image(msg["chart_path"], use_column_width=True)
        if debug_mode and msg.get("sql"):
            with st.expander("SQL"):
                st.code(msg["sql"], language="sql")

# Input box
user_input = st.chat_input("Ask a question about the sales data …")

if user_input:
    # Show user bubble
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # Run agent
    with st.chat_message("assistant"):
        with st.spinner("Thinking …"):
            result = run_agent(user_input, st.session_state.conv_history)

        response_text = result.get("final_response", "Sorry, I could not generate a response.")
        fmt = result.get("response_format", "verbal")
        query_results = result.get("query_results") or []
        chart_path = result.get("chart_path")
        sql = result.get("sql_query", "")

        st.markdown(response_text)

        if fmt == "table" and query_results:
            df = pd.DataFrame(query_results)
            st.dataframe(df, use_container_width=True)

        if fmt == "chart" and chart_path and os.path.exists(chart_path):
            st.image(chart_path, use_column_width=True)

        if debug_mode and sql:
            with st.expander("Generated SQL"):
                st.code(sql, language="sql")

    # Persist to session state
    st.session_state.messages.append({
        "role": "assistant",
        "content": response_text,
        "table": query_results if fmt == "table" else None,
        "chart_path": chart_path if fmt == "chart" else None,
        "sql": sql,
    })
    st.session_state.conv_history = result.get("conversation_history") or st.session_state.conv_history
