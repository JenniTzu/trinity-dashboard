# ============================================================
# TRINITY 投資監控系統 - 全域設定檔
# 使用前請填入您的 API Key 與 GitHub 資訊
# ============================================================
import os

# ── API 金鑰 ──────────────────────────────────────────────
# GitHub Actions 執行時由 Secrets 注入；本機執行使用預設值
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
FRED_API_KEY   = os.environ.get("FRED_API_KEY",   "待填入")

# ── GitHub 設定 ────────────────────────────────────────────
GITHUB_REPO    = "JenniTzu/trinity-dashboard"
GITHUB_TOKEN   = "待填入"          # GitHub Personal Access Token

# ── 資金設定 ───────────────────────────────────────────────
TOTAL_CAPITAL_TWD = 750_000        # 總資金（台幣）
USD_TWD_RATE      = 32.5           # 美元/台幣匯率（系統會自動更新）
MAX_SINGLE_ADD_PCT = 0.05          # 每次加碼上限（5%）

# ── 持倉成本價 ─────────────────────────────────────────────
COST_BASIS = {
    "NVDA": 850,
    "SMH":  210,
}

# ── 投資組合清單 ───────────────────────────────────────────
PORTFOLIO = {
    "core_dca":    ["QQQ"],
    "value_stocks": ["NVDA", "GOOGL", "MSFT", "V", "BRK-B", "VTI", "ASML", "AMD"],
    "swing":       ["TSM", "PLTR", "NVDA"],
    "hedge":       ["GLD"],
    "etf_sectors": ["QQQ", "SMH", "XLF", "XLE", "GLD"],
    "macro":       ["^VIX", "^TNX"],
}

# 所有需要抓取的標的（去重）
ALL_TICKERS = list(dict.fromkeys(
    PORTFOLIO["value_stocks"] +
    PORTFOLIO["swing"] +
    PORTFOLIO["hedge"] +
    PORTFOLIO["etf_sectors"] +
    PORTFOLIO["macro"]
))

# ── 集中度警示 ─────────────────────────────────────────────
CONCENTRATION_WARN = {
    "tickers": ["NVDA", "SMH", "QQQ"],
    "threshold": 0.70,
}

# ── 金字塔加碼設定 ─────────────────────────────────────────
PYRAMID = [
    {"drop_pct": -0.10, "add_pct": 0.30},
    {"drop_pct": -0.20, "add_pct": 0.30},
    {"drop_pct": -0.30, "add_pct": 0.40},
]

# ── 策略閾值 ───────────────────────────────────────────────
STRATEGY = {
    "track_a_fgi_threshold":  25,
    "track_a_vix_threshold":  30,
    "track_c_rsi_buy":        35,
    "track_c_volume_mult":    1.5,
    "track_b_score_threshold": 70,
}

# ── Howard Marks 信用利差閾值 ──────────────────────────────
CREDIT_SPREAD = {
    "overheat": 300,
    "opportunity": 500,
    "crisis": 800,
}

# ── 巴菲特標準 ─────────────────────────────────────────────
BUFFETT = {
    "roe_min": 15,
    "roe_years": 5,
}

# ── 排程設定 ───────────────────────────────────────────────
SCHEDULE_HOUR   = 6    # 台灣時間早上6點（GitHub Actions: UTC 22:00 前一天）
SCHEDULE_MINUTE = 0

# ── AI 模型設定 ────────────────────────────────────────────
GEMINI_MODEL = "gemini-2.5-flash"

# ── 路徑設定 ───────────────────────────────────────────────
BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DATA_DIR  = os.path.join(BASE_DIR, "data")
DOCS_DIR  = os.path.join(BASE_DIR, "docs")
LOGS_DIR  = os.path.join(BASE_DIR, "logs")

DATA_JSON = os.path.join(DOCS_DIR, "data.json")
