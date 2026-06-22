#!/usr/bin/env python3
"""
main.py — CLI entry-point for the Text2SQL AI Agent.

Usage:
    python3 src/main.py
    DEBUG=true python3 src/main.py        # show SQL queries

# python3 src/main.py
#     │
#     ├─ 載入 .env（設定 LangSmith 等環境變數）
#     │
#     ├─ 確認資料庫存在
#     │   CSV 存在但 DB 不存在 → 自動初始化 DB
#     │   兩者都不存在         → 印出下載提示，中止
#     │
#     └─ 進入互動迴圈
#         使用者輸入問題
#           └─► run_agent(user_input) → 取得回覆
#                 顯示口語回覆 / 表格 / 圖表路徑
#         輸入 'quit' → 結束
"""
import os
import sys
from pathlib import Path

# ── Environment variables must be set BEFORE any LangChain import ────────────
from dotenv import load_dotenv
load_dotenv()

if os.getenv("LANGSMITH_API_KEY"):
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGSMITH_API_KEY"] = os.getenv("LANGSMITH_API_KEY")
    os.environ.setdefault("LANGCHAIN_PROJECT", os.getenv("LANGSMITH_PROJECT", "text2sql-agent"))
    print("[INFO] LangSmith tracing enabled")

# ── Path fix so `src.*` imports work regardless of cwd ───────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.agent.graph import run_agent       # noqa: E402
from src.db.init_db import init_database    # noqa: E402


# ── Helpers ───────────────────────────────────────────────────────────────────
def _ascii_table(results: list[dict]) -> str:
    if not results:
        return "(no data)"
    headers = list(results[0].keys())
    widths = [len(h) for h in headers]
    for row in results:
        for i, h in enumerate(headers):
            widths[i] = max(widths[i], len(str(row.get(h, ""))))

    sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    hdr = "|" + "|".join(f" {h:<{widths[i]}} " for i, h in enumerate(headers)) + "|"
    lines = [sep, hdr, sep]
    for row in results[:20]:
        lines.append("|" + "|".join(f" {str(row.get(h,'')):<{widths[i]}} " for i, h in enumerate(headers)) + "|")
    lines.append(sep)
    if len(results) > 20:
        lines.append(f"  … {len(results) - 20} more rows not shown")
    return "\n".join(lines)


def _ensure_db() -> bool:
    db_path = os.getenv("DB_PATH", "data/supermarket.db")
    csv_path = str(ROOT / "data" / "SuperMarket Analysis.csv")
    if os.path.exists(db_path):
        return True
    if os.path.exists(csv_path):
        print("[INFO] Initialising database …")
        init_database(csv_path, db_path)
        return True
    print(f"[ERROR] Dataset not found: {csv_path}")
    print("  Download from: https://www.kaggle.com/datasets/faresashraf1001/supermarket-sales")
    print(f"  Place the CSV at: {csv_path}")
    return False


# ── Main loop ─────────────────────────────────────────────────────────────────
def main() -> None:
    print("=" * 58)
    print("  Text2SQL AI Agent  — Supermarket Sales Analyser")
    print("=" * 58)

    if not _ensure_db():
        sys.exit(1)

    print("\nType your question (or 'quit' to exit).")
    print("Examples:")
    print("  • 這個超市總共有多少筆交易？")
    print("  • 各分店的總銷售額是多少？")
    print("  • 比較各產品線的銷售佔比")
    print("  • 列出所有評分高於 9 分的會員交易")
    print()

    conversation_history: list = []
    debug = os.getenv("DEBUG", "false").lower() == "true"

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye! / 再見！")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "退出", "離開", "q"):
            print("Goodbye! / 再見！")
            break

        print("  [thinking …]")
        result = run_agent(user_input, conversation_history)

        print(f"\nAgent: {result.get('final_response', '(no response)')}\n")

        fmt = result.get("response_format")

        if fmt == "table" and result.get("query_results"):
            print(_ascii_table(result["query_results"]))
            print()

        if fmt == "chart" and result.get("chart_path"):
            chart_path = result["chart_path"]
            print(f"  [Chart saved → {chart_path}]")
            if sys.platform == "darwin":
                os.system(f"open '{chart_path}'")
            print()

        if debug:
            print(f"  [SQL]    {result.get('sql_query', 'N/A')}")
            print(f"  [Format] {fmt}  |  [Retries] {result.get('retry_count', 0)}")
            print()

        # Carry conversation history forward for multi-turn support
        conversation_history = result.get("conversation_history") or conversation_history


if __name__ == "__main__":
    main()
