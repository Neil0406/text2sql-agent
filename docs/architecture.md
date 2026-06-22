# 架構設計文件

## Text2SQL AI Agent — 設計概述

### 1. 為什麼這樣切分節點？

每個節點只負責一件事，讓整個工作流程容易除錯、替換或獨立進行單元測試。

```
intent_parser   →  理解使用者的問題意圖
schema_fetcher  →  提供模型正確的資料庫結構資訊
text2sql        →  生成 SQL（失敗時重試）
sql_validator   →  安全性與語法驗證關卡
sql_executor    →  安全執行查詢
response_router →  決定回覆格式：口語 / 列表 / 圖表
chart_generator →  渲染 PNG 圖表（僅在需要時執行）
response_composer → 撰寫自然語言回覆
```

---

### 2. LangGraph State 設計

```python
class AgentState(TypedDict):
    user_input:           str
    conversation_history: Annotated[list, operator.add]  # 只能 append
    intent:               Optional[dict]   # query_type, entities, viz_hint, …
    schema_info:          Optional[str]    # 注入每個 SQL prompt
    sql_query:            Optional[str]
    retry_count:          int              # 0 → MAX_RETRIES (3)
    sql_error:            Optional[str]    # 重試時回饋給 text2sql
    query_results:        Optional[list]   # list[dict] 查詢結果
    response_format:      Optional[str]    # "verbal" | "table" | "chart"
    chart_type:           Optional[str]    # "bar" | "line" | "pie" | "scatter"
    verbal_response:      Optional[str]
    chart_path:           Optional[str]
    final_response:       Optional[str]
    error:                Optional[str]    # 錯誤路由的旗標
```

`conversation_history` 使用 `Annotated[list, operator.add]`，每個節點只需回傳**新增的訊息**，LangGraph 會自動串接。這讓多輪對話的實作非常乾淨。

---

### 3. 回覆格式決策邏輯

```
單一數值結果           →  口語
有錯誤 / 結果為空      →  口語
關鍵字「趨勢/trend」   →  圖表（折線圖）
關鍵字「佔比/pie」     →  圖表（圓餅圖）
關鍵字「比較/compare」 →  圖表（長條圖）
關鍵字「列出/list」    →  列表
intent.viz_hint=chart + ≥2 筆數值資料 → 圖表
intent.viz_hint=table + ≤20 筆        → 列表
>20 筆，無關鍵字      →  圖表（長條圖）
2~6 筆，有數值欄位    →  圖表（長條圖）
預設                  →  列表
```

---

### 4. 安全防護機制

| 防護層 | 控制方式 |
|---|---|
| SQL 生成 | System prompt 明確禁止 DDL/DML |
| SQL 驗證 | Regex 關鍵字黑名單 + sqlparse 語句數量檢查 + SQLite EXPLAIN 語法驗證 |
| SQL 執行 | 結果筆數上限（1,000 筆），查詢逾時（30 秒） |
| 資料隔離 | 結果為唯讀；使用者資料不會被插入 SQL |

---

### 5. LangSmith 可觀測性

在 `.env` 設定 `LANGSMITH_API_KEY` 後，Agent 自動追蹤：

- 每個 LangGraph 節點的輸入 / 輸出
- 每次 LLM 呼叫（Prompt + 回應 + Token 用量）
- SQL 生成重試流程
- 每次執行的總延遲

前往 https://smith.langchain.com 查看追蹤記錄。

---

### 6. 重試機制

```
text2sql → sql_validator
              │
              ├─ 驗證通過              → sql_executor
              ├─ 驗證失敗 + 重試 < 3  → text2sql（帶入錯誤訊息重試）
              ├─ 重試 ≥ 3             → response_composer（禮貌性拒絕）
              └─ unsupported          → response_composer（說明無法處理）
```

Validator 的錯誤訊息會注入下一次 `text2sql` 的 prompt，讓模型能自我修正。

---

### 7. 多輪對話支援

`conversation_history` 攜帶最近 N 輪對話記錄。`intent_parser` 和 `text2sql` 都會接收這個上下文，讓使用者可以問後續問題，例如：「那 Giza 呢？」

---

### 8. 模型選型理由

| 模型 | 優點 | 缺點 |
|---|---|---|
| **Gemma 4 E4B** | 原生 Function Calling、128K context、Google 級推理品質、INT4 約 5 GB | 較新，Ollama 可能尚未有穩定版 |
| Gemma 3 4B | 成熟穩定，Ollama 普遍可用 | 推理品質略低 |
| Llama 3.2 3B | 速度快、體積小 | SQL 生成能力較弱 |
| Qwen 2.5 7B | 中文 + SQL 能力優秀 | 體積較大（7B），CPU 較慢 |

Gemma 4 E4B 是首選，兼顧模型大小、上下文視窗長度，以及 Agent 場景所需的 Function Calling 支援。Gemma 3 4B（`gemma3:4b`）作為 `setup.sh` 的自動備案。

---

### 9. 技術挑戰與解決方案

| 挑戰 | 解決方案 |
|---|---|
| LLM 回傳 JSON 格式不穩定 | 多模式 regex 串接 + 規則型 fallback |
| LLM 把 SQL 包在說明文字裡 | `_extract_sql()` 三層 regex 提取 |
| matplotlib 中文字型 | 自動偵測系統 CJK 字型；備案使用 DejaVu Sans |
| 重複查詢浪費延遲 | `QueryCache`（記憶體內 LRU，上限 128 筆） |
| LLM 輸出的 SQL Injection | 三層驗證（prompt + 關鍵字黑名單 + EXPLAIN） |
| 多輪對話上下文飄移 | `conversation_history` 截取最近 4 筆訊息 |
