# Text2SQL AI Agent — 超市銷售分析助理

以 **LangGraph** + **Ollama（Gemma 4 E4B）** 打造的 **Text2SQL AI Agent**，讓使用者能用自然語言查詢超市銷售資料。

## 功能特色

| 功能 | 說明 |
|---|---|
| 地端模型 | Gemma 4 E4B via Ollama — 不依賴雲端 API |
| 框架 | LangGraph StateGraph，共 8 個節點 |
| 可觀測性 | LangSmith 追蹤（選填） |
| 多輪對話 | 跨問題保留對話歷史 |
| 雙語支援 | 繁體中文與英文 |
| 回覆格式 | 口語 / 列表 / 圖表（自動選擇） |
| 圖表 | 長條圖 / 折線圖 / 圓餅圖 / 散點圖（matplotlib） |
| 安全性 | SELECT-only SQL，三層驗證防護 |
| 快取 | 記憶體內 LRU 查詢快取 |
| Web UI | Streamlit 聊天介面（加分項） |

---

## 運作流程

使用者輸入一個自然語言問題後，依序經過以下節點處理：

```
使用者輸入：「比較各產品線的銷售佔比」
    │
    ▼
[1] intent_parser.py          ← 呼叫 LLM
    │  分析問題類型（comparison）、語言（zh）、
    │  建議格式（chart / pie）
    ▼
[2] graph.py → schema_fetcher
    │  讀取 SQLite 的 table schema 與範例資料
    │  組成純文字，供下一步 LLM 參考
    ▼
[3] text2sql.py               ← 呼叫 LLM
    │  將「意圖 + schema + 問題」組成 prompt
    │  LLM 生成 SQL：
    │  SELECT "Product line", SUM(Sales) FROM supermarket_sales
    │  GROUP BY "Product line"
    ▼
[4] sql_validator.py          ← 純程式
    │  三層驗證：SELECT 開頭？危險關鍵字？語法正確？
    │  驗證失敗 → 帶錯誤訊息回到 [3] 重試（最多 3 次）
    ▼
[5] sql_executor.py           ← 純程式
    │  查 LRU 快取 → 未命中則打 SQLite 執行
    │  回傳 list[dict] 查詢結果
    ▼
[6] response_router.py        ← 純程式
    │  判斷「比較」關鍵字 + 多筆數值資料
    │  → 決定用 chart（pie）
    ▼
[7] chart_generator.py        ← 純程式
    │  用 matplotlib 畫圓餅圖
    │  存成 PNG 至 data/charts/
    ▼
[8] response_composer.py      ← 呼叫 LLM
    │  將查詢結果轉成自然語言回覆
    │  追加本輪到 conversation_history（多輪支援）
    ▼
輸出：口語文字 + 圓餅圖
```

> 整個流程由 `graph.py` 用 LangGraph StateGraph 串接，所有節點共用 `state.py` 定義的 `AgentState` 資料結構傳遞資料。

---

## 系統需求

- **Python 3.11+**
- macOS 或 Linux
- 至少 6 GB 可用記憶體（供 Ollama 執行 Gemma 4 E4B）

建議使用獨立環境：
```bash
python -m venv text2sql-agent-env
source ./text2sql-agent-env/bin/activate  
```
OR
```bash
conda create -n text2sql-agent-env python=3.11 -y
conda activate text2sql-agent-env
```

---

## 快速開始

### 1. 複製專案並進入目錄
```bash
git clone <your-repo>
cd text2sql-agent
```

### 2. 下載資料集
從 Kaggle 下載 **SuperMarket Analysis.csv**：
https://www.kaggle.com/datasets/faresashraf1001/supermarket-sales

放置於：`data/SuperMarket Analysis.csv`

### 3. 執行環境安裝腳本
```bash
chmod +x setup.sh
./setup.sh
```

腳本將自動完成：
1. 偵測作業系統（macOS / Linux）
2. 若未安裝則自動安裝 Ollama
3. 拉取 `gemma4:e4b`（或以 `gemma3:4b` 作為備案）
4. 驗證模型可正常推論
5. 安裝 Python 相依套件
6. 初始化 SQLite 資料庫

### 4. 設定環境變數（選填）
```bash
# 加入 LangSmith API Key 以啟用追蹤功能
echo "LANGSMITH_API_KEY=your_key_here" >> .env
```

### 5. 啟動

**CLI：**
```bash
python3 src/main.py
```

**Web UI（Streamlit）：**
```bash
streamlit run src/app.py
```

**除錯模式（顯示 SQL）：**
```bash
DEBUG=true python3 src/main.py
```

---

## 專案結構

```
text2sql-agent/
├── setup.sh                    # 自動環境安裝腳本
├── requirements.txt
├── .env.example
├── README.md
├── data/
│   ├── SuperMarket Analysis.csv  # （需另行下載）
│   ├── supermarket.db            # （自動產生）
│   └── charts/                   # （自動產生的 PNG 圖表）
├── src/
│   ├── db/
│   │   ├── init_db.py           # CSV → SQLite 匯入
│   │   └── schema.py            # Schema 讀取工具
│   ├── agent/
│   │   ├── state.py             # AgentState TypedDict
│   │   ├── graph.py             # LangGraph 工作流程
│   │   └── nodes/
│   │       ├── intent_parser.py      # 自然語言 → 意圖 JSON
│   │       ├── text2sql.py           # 意圖 + Schema → SQL
│   │       ├── sql_validator.py      # 安全性與語法驗證
│   │       ├── sql_executor.py       # 安全執行 SQL
│   │       ├── response_router.py    # 口語 / 列表 / 圖表決策
│   │       └── response_composer.py  # 自然語言回覆組合
│   ├── visualization/
│   │   └── chart_generator.py   # matplotlib 圖表生成
│   ├── cache/
│   │   └── query_cache.py       # LRU 記憶體快取
│   ├── main.py                  # CLI 入口
│   └── app.py                   # Streamlit Web UI
├── tests/
│   ├── test_sql_validator.py
│   ├── test_response_router.py
│   └── test_text2sql.py
└── docs/
    └── architecture.md
```

---

## 問答範例

```
使用者：這個超市總共有多少筆交易？
Agent：這個超市在 2019 年 1 月到 3 月期間，總共有 1,000 筆交易紀錄。

使用者：各分店的總銷售額是多少？
Agent：以下是各分店的銷售統計，Cairo 分店略為領先。
[顯示表格]

使用者：比較各產品線的銷售佔比
Agent：根據資料分析，各產品線的銷售分佈如下：
[顯示圓餅圖]

使用者：predict next month sales
Agent：Sorry, the dataset only contains historical records and cannot be used
       for predictions. I can help you analyse past sales trends instead.
```

---

## 執行測試

```bash
pytest tests/ -v
```

---

## LangSmith 追蹤

1. 至 https://smith.langchain.com 註冊帳號（免費方案即可）
2. 將 `LANGSMITH_API_KEY=<your_key>` 加入 `.env`
3. 啟動 Agent — 追蹤記錄將自動出現在 LangSmith 儀表板

追蹤內容包含：節點輸入/輸出、LLM Prompt 與回應、SQL 重試流程、延遲時間、Token 用量。

---

## 環境變數

| 變數 | 預設值 | 說明 |
|---|---|---|
| `OLLAMA_MODEL` | `gemma4:e4b` | Ollama 模型標籤 |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama API 端點 |
| `DB_PATH` | `data/supermarket.db` | SQLite 資料庫路徑 |
| `LANGSMITH_API_KEY` | — | LangSmith API Key（選填） |
| `LANGSMITH_PROJECT` | `text2sql-agent` | LangSmith 專案名稱 |
| `DEBUG` | `false` | 在 CLI 中顯示 SQL 查詢 |
