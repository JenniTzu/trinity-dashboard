# ============================================================
# TRINITY - update_data.py
# 整合所有數據，寫入 docs/data.json（網站讀取來源）
# ============================================================

import json
import os
import sys
from datetime import datetime
import pytz

if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import config
from core import fetch_data
from core import calculate
from core import position_manager
from agents import analyst_agent
from agents import buffett_agent
from agents import howard_marks_agent


TW_TZ = pytz.timezone("Asia/Taipei")


def load_history(data_json_path: str) -> dict:
    """載入現有 data.json（用於累積歷史數據）"""
    if os.path.exists(data_json_path):
        try:
            with open(data_json_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"history": [], "dates": []}


def update_data(use_cache: bool = False) -> dict:
    """
    主流程：抓取 → 計算 → 分析 → 寫入 data.json
    use_cache=True：使用上次快取數據（測試用，不重新抓取）
    """
    print("\n" + "="*60)
    print("  TRINITY 全流程啟動")
    print(f"  時間：{datetime.now(TW_TZ).strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)

    # ── Step 1: 抓取數據 ──────────────────────────────────
    cache_path = os.path.join(config.DATA_DIR, "raw_data_cache.json")
    if use_cache and os.path.exists(cache_path):
        print("\n[模式] 使用快取數據（不重新抓取）")
        with open(cache_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
    else:
        print("\n[Step 1/5] 抓取市場數據...")
        raw_data = fetch_data.fetch_all_data()
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(raw_data, f, ensure_ascii=False, indent=2, default=str)

    # ── Step 2: 計算指標 ──────────────────────────────────
    print("\n[Step 2/5] 計算策略指標...")
    calc_results = calculate.calculate_all(raw_data)

    # ── Step 3: 部位風險 ──────────────────────────────────
    print("\n[Step 3/5] 計算部位風險...")
    position_data = position_manager.calc_position_risk(raw_data)

    # ── Step 4: 三個 Agent ────────────────────────────────
    print("\n[Step 4/5] 執行三個 AI Agent...")
    analyst_result = analyst_agent.run_analyst_agent(raw_data, calc_results, position_data)
    buffett_result = buffett_agent.run_buffett_agent(raw_data)
    hm_result      = howard_marks_agent.run_howard_marks_agent(raw_data, calc_results)

    # Agent 共識程度
    consensus = _calc_consensus(analyst_result, buffett_result, hm_result)

    # ── Step 5: 整合並寫入 data.json ──────────────────────
    print("\n[Step 5/5] 整合數據寫入 data.json...")

    today_data = _build_today_snapshot(
        raw_data, calc_results, position_data,
        analyst_result, buffett_result, hm_result, consensus
    )

    # 載入歷史數據
    data_json_path = config.DATA_JSON
    os.makedirs(config.DOCS_DIR, exist_ok=True)
    full_data = load_history(data_json_path)

    # 更新今日數據
    today_str = raw_data["date"]
    full_data["latest"] = today_data
    full_data["updated_at"] = datetime.now(TW_TZ).strftime("%Y-%m-%d %H:%M:%S %Z")

    # 累積歷史（避免重複同一天）
    existing_dates = {d.get("date") for d in full_data.get("history", [])}
    if today_str not in existing_dates:
        full_data.setdefault("history", []).append(today_data)
        # 只保留最近 90 天
        full_data["history"] = full_data["history"][-90:]

    # 寫入
    with open(data_json_path, "w", encoding="utf-8") as f:
        json.dump(full_data, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n  data.json 寫入完成：{data_json_path}")
    print(f"  歷史記錄：{len(full_data.get('history', []))} 天")
    print("\n" + "="*60)
    print("  TRINITY 全流程完成！")
    print("="*60 + "\n")

    return full_data


def _build_today_snapshot(raw_data, calc_results, position_data,
                           analyst_result, buffett_result, hm_result, consensus) -> dict:
    """建立今日完整快照"""
    stocks     = raw_data.get("stocks", {})
    fear_greed = raw_data.get("fear_greed", {})
    macro      = raw_data.get("macro", {})
    credit     = raw_data.get("credit_spread", {})

    # 個股精簡格式（供圖表、評分歷史用）
    stocks_summary = {}
    for ticker, s in stocks.items():
        if s.get("error") and not s.get("price"):
            continue
        stocks_summary[ticker] = {
            "name":          s.get("name", ticker),
            "price":         s.get("price"),
            "pe_ratio":      s.get("pe_ratio"),
            "rsi14":         s.get("rsi14"),
            "ma200_dev":     s.get("ma200_deviation_pct"),
            "volume_ratio":  s.get("volume_ratio"),
            "fcf_yield":     s.get("fcf_yield"),
            "roe":           s.get("roe"),
            "from_52w_high": s.get("pct_from_52w_high"),
            "analyst_target":s.get("analyst_target"),
            "upside_pct":    s.get("upside_pct"),
            "week52_high":   s.get("week52_high"),
            "week52_low":    s.get("week52_low"),
            "gross_margin_trend": s.get("gross_margin_trend", []),
            "roe_trend":     s.get("roe_trend", []),
            "news":          s.get("news", [])[:3],
            "next_earnings": s.get("next_earnings_date"),
            "track_b_score": calc_results.get("track_b", {}).get(ticker, {}).get("score"),
            "track_b_signal": calc_results.get("track_b", {}).get(ticker, {}).get("signal"),
            "track_c_signal": calc_results.get("track_c", {}).get(ticker, {}).get("signal"),
            "buffett_verdict": buffett_result.get("verdicts", {}).get(ticker, {}).get("verdict"),
            "buffett_icon":  buffett_result.get("verdicts", {}).get(ticker, {}).get("verdict_icon", ""),
            "buffett_reason": buffett_result.get("verdicts", {}).get(ticker, {}).get("reason", ""),
        }

    # 30日 VIX 歷史（用於圖表）
    vix_history = macro.get("vix_history", [])[-30:]
    tnx_history = macro.get("treasury_10y_history", [])[-30:]
    cs_history  = credit.get("history", [])[-30:]

    return {
        "date":        raw_data.get("date"),
        "timestamp":   raw_data.get("timestamp"),

        # 市場溫度
        "market": {
            "fgi":          fear_greed.get("value"),
            "fgi_label":    fear_greed.get("label"),
            "fgi_history":  fear_greed.get("history", {}),
            "fgi_indicators": fear_greed.get("indicators", {}),
            "vix":          macro.get("vix"),
            "treasury_10y": macro.get("treasury_10y"),
            "credit_spread": credit.get("value"),
            "credit_label": credit.get("label"),
            "environment":  calc_results.get("market", {}),
            "vix_history":  vix_history,
            "tnx_history":  tnx_history,
            "cs_history":   cs_history,
        },

        # 三軌策略
        "track_a":   calc_results.get("track_a"),
        "track_b":   calc_results.get("track_b"),
        "track_c":   calc_results.get("track_c"),
        "pyramid":   calc_results.get("pyramid"),

        # 個股數據
        "stocks":    stocks_summary,

        # 部位風險
        "position":  position_data,

        # 三個 Agent
        "analyst":      analyst_result,
        "buffett":      buffett_result,
        "howard_marks": hm_result,
        "consensus":    consensus,

        # 即將事件
        "fomc_dates":   raw_data.get("fomc_dates", []),
    }


def _calc_consensus(analyst_result, buffett_result, hm_result) -> dict:
    """計算三腦共識程度（0-100%）"""
    # 策略分析師：綠訊號數量
    green_signals = sum(1 for s in analyst_result.get("signals", []) if s.get("priority", 9) <= 2)
    analyst_bullish = min(green_signals / 3, 1.0)  # 標準化

    # 巴菲特：護城河穩固比例
    verdicts = buffett_result.get("verdicts", {})
    if verdicts:
        strong = sum(1 for v in verdicts.values() if v.get("verdict") == "moat_strong")
        buffett_bullish = strong / len(verdicts)
    else:
        buffett_bullish = 0.5

    # 霍華馬克斯：鐘擺偏買入
    pendulum_score = hm_result.get("pendulum", {}).get("total_score", 0)
    hm_bullish = min(max(pendulum_score / 6, 0), 1.0)

    # 共識分數（三方平均）
    consensus_pct = round((analyst_bullish + buffett_bullish + hm_bullish) / 3 * 100, 1)

    if consensus_pct >= 70:
        label = "高度共識買入"
        color = "green"
    elif consensus_pct >= 50:
        label = "溫和偏多"
        color = "yellow"
    elif consensus_pct >= 35:
        label = "觀望中性"
        color = "neutral"
    else:
        label = "謹慎偏空"
        color = "red"

    return {
        "score":          consensus_pct,
        "label":          label,
        "color":          color,
        "analyst_score":  round(analyst_bullish * 100, 1),
        "buffett_score":  round(buffett_bullish * 100, 1),
        "hm_score":       round(hm_bullish * 100, 1),
    }


# ── 執行入口 ────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", action="store_true", help="使用快取數據（不重新抓取）")
    args = parser.parse_args()

    result = update_data(use_cache=args.cache)

    latest = result.get("latest", {})
    cons   = latest.get("consensus", {})
    print(f"三腦共識：{cons.get('label')}（{cons.get('score')}%）")
    print(f"  策略分析師：{cons.get('analyst_score')}%")
    print(f"  巴菲特：{cons.get('buffett_score')}%")
    print(f"  霍華馬克斯：{cons.get('hm_score')}%")
