# CLAUDE.md — TRINITY 投資監控系統

## 專案簡介

TRINITY 是一個全自動美股投資監控系統，每天台灣時間凌晨 5 點（美股收盤後）執行，
透過三個 AI Agent 分析持倉，並將結果發佈到 GitHub Pages 網站。

## 系統架構

```
main.py              ← 主入口（--test / --cache / --no-deploy）
├── fetch_data.py    ← 抓取原始數據（yfinance, fear-greed, FRED）
├── calculate.py     ← 策略計算（三軌策略 + 市場三層分析共用函式）
├── position_manager.py ← 部位管理（金字塔加碼、損益）
├── analyst_agent.py ← Agent 1：策略分析師（三軌整合）
├── buffett_agent.py ← Agent 2：巴菲特大腦（護城河分析）
├── howard_marks_agent.py ← Agent 3：霍華馬克斯大腦（鐘擺理論）
├── update_data.py   ← 整合所有步驟、更新歷史數據
├── deploy.py        ← 部署 docs/ 到 GitHub Pages
├── gemini_client.py ← Gemini API 單例（全系統共用一個實例）
└── config.py        ← 全域設定（API Key、持倉成本、閾值）
```

## 關鍵設計原則

### 1. 市場三層分析只算一次
`calculate.py` 中的 4 個公開函式是**唯一計算來源**：
- `calc_emotion_layer(fear_greed, macro)` — FGI + VIX
- `calc_credit_layer(credit_spread)` — HY OAS 信用利差
- `calc_valuation_layer(stocks)` — QQQ PE vs 歷史均值
- `calc_pendulum_position(emotion, credit, valuation)` — 綜合鐘擺

`howard_marks_agent.py` 直接 import 這 4 個函式，不重複實作。
`calc_market_environment()` 是薄包裝，供 analyst_agent 使用。

### 2. Gemini API 只初始化一次
`gemini_client.py` 用單例模式管理 `GenerativeModel` 實例。
所有 Agent 都 `from gemini_client import get_model, is_available`，
不直接呼叫 `genai.configure()` 或 `genai.GenerativeModel()`。

### 3. NVDA 股票分割自動調整
成本 $850（10:1 分割前）→ 系統自動偵測（若 cost/price 比 > 5）→ 調整為 $85。
`position_manager.py` 的 `cost_adjusted` 欄位會標注分割調整。

## 投資組合

| 標的 | 類型 | 成本價 |
|------|------|--------|
| NVDA | 核心持倉 | $850（分割前），調整後 $85 |
| SMH  | 產業ETF | $210 |
| QQQ  | 核心定投 | — |
| GOOGL, MSFT, V, BRK-B, VTI, ASML, AMD | 價值股 | — |
| TSM, PLTR | 波段 | — |
| GLD  | 避險 | — |

總資金：750,000 TWD（約 $23,000 USD，匯率 32.5）

## 三軌策略

| 軌道 | 觸發條件 | 動作 |
|------|----------|------|
| A（QQQ定投） | FGI < 25 **且** VIX > 30 | 額外加碼 QQQ（上限 5%） |
| B（逢低加碼） | 100分評分 ≥ 70 | 買入對應個股 |
| C（波段） | RSI < 35 + 成交量 > 1.5x | 波段買入 |

## 執行方式

```bash
# 完整執行（含部署）
python main.py

# 測試模式（不部署）
python main.py --test

# 使用快取（不重新抓數據）
python main.py --cache

# 不部署到 GitHub Pages
python main.py --no-deploy
```

## 設定（config.py 需手動填入）

| 設定項 | 位置 | 說明 |
|--------|------|------|
| `FRED_API_KEY` | config.py | 信用利差數據，申請：fred.stlouisfed.org |
| `GITHUB_REPO` | config.py | 格式：`username/repo-name` |
| `GITHUB_TOKEN` | config.py | GitHub Personal Access Token |

`GEMINI_API_KEY` 已填入（模型：gemini-2.5-flash）。

## 自動排程

Windows Task Scheduler 設定：台灣時間 05:00 執行 `main.py`。
設定腳本：`setup_scheduler.ps1`（需以系統管理員身分執行）。

## 資料流

```
fetch_data.py → data/raw_data_cache.json
calculate.py  → data/calc_cache.json
position_manager.py → data/position_cache.json
analyst_agent.py → data/analyst_cache.json
buffett_agent.py → data/buffett_cache.json
howard_marks_agent.py → data/howard_marks_cache.json
update_data.py → docs/data.json（90天歷史）
deploy.py → GitHub Pages
```

## 已知限制

- `fear-greed` 套件版本 0.1.0，回傳 `dict`（`score`/`rating` 鍵），不是物件。
- yfinance 1.2.0+ 新聞格式：內容在 `item['content']` 下的巢狀結構。
- Gemini free tier 有每日用量限制；模型 `gemini-2.5-flash` 目前可用。
- GitHub Pages 需先在 repo Settings 啟用，來源設為 `/docs` 資料夾。
