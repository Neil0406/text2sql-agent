"""
init_db.py — Import SuperMarket Analysis.csv into SQLite

# init_database(csv_path, db_path) 流程
#     │
#     ├─ 用 pandas 讀取 CSV（1000 筆）
#     ├─ 欄位型別轉換
#     │   Date → TEXT（ISO-8601 YYYY-MM-DD）
#     │   數值欄位（Unit price, Sales 等）→ REAL
#     ├─ 建立 SQLite table（supermarket_sales）
#     ├─ 寫入全部資料
#     └─ 建立索引（Branch, Product line, Date）加速查詢
"""
import os
import sys
import sqlite3
import pandas as pd


def init_database(csv_path: str, db_path: str) -> None:
    if not os.path.exists(csv_path):
        print(f"[ERROR] CSV not found: {csv_path}")
        sys.exit(1)

    print(f"[INFO] Loading: {csv_path}")
    df = pd.read_csv(csv_path)

    # ── Normalise column names ──────────────────────────────────────────────
    # Keep original names but strip surrounding whitespace
    df.columns = [c.strip() for c in df.columns]

    # ── Type coercions ──────────────────────────────────────────────────────
    # Date → ISO-8601 string (YYYY-MM-DD) for easy SQLite date functions
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], dayfirst=False, errors="coerce").dt.strftime("%Y-%m-%d")

    # Numeric columns
    numeric_cols = [
        "Unit price", "Quantity", "Tax 5%", "Total", "cogs",
        "gross margin percentage", "gross income", "Rating",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # ── Write to SQLite ─────────────────────────────────────────────────────
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path)
    df.to_sql("supermarket_sales", conn, if_exists="replace", index=False)

    # Create an index on common filter columns for faster queries
    conn.execute("CREATE INDEX IF NOT EXISTS idx_branch ON supermarket_sales (Branch)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_date   ON supermarket_sales (Date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_product ON supermarket_sales ([Product line])")
    conn.commit()

    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM supermarket_sales")
    count = cursor.fetchone()[0]
    conn.close()

    print(f"[OK] Database ready: {db_path}  ({count} rows)")


if __name__ == "__main__":
    BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    init_database(
        csv_path=os.path.join(BASE, "data", "SuperMarket Analysis.csv"),
        db_path=os.path.join(BASE, "data", "supermarket.db"),
    )
