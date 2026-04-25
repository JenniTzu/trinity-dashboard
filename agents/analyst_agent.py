# ============================================================
# TRINITY - analyst_agent.py
# Agent 1：策略分析師（三軌策略）
# ============================================================

import json
import os
import sys

if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import config


def run_analyst_agent(raw_data: dict, calc_results: dict, position_data: dict) -> dict:
    """
    策略分析師：整合三軌策略，生成今日操作建議
    """
    stocks     = raw_data.get("stocks", {})
    fear_greed = raw_data.get("fear_greed", {})
    macro      = raw_data.get("macro", {})

    track_a = calc_results.get("track_a", {})
    track_b = calc_results.get("track_b", {})
    track_c = calc_results.get("track_c", {})
    pyramid = calc_results.get("pyramid", {})
    market  = calc_results.get("market", {})

    # ── 使用 Gemini AI 分析（若有 API Key）────────────────
    ai_analysis = _call_gemini_analyst(
        raw_data, calc_results, position_data
    )

    # ── 整合三軌訊號 ─────────────────────────────────────
    signals = []

    # 軌道A
    if track_a.get("signal") == "green":
        signals.append({
            "track": "A",
            "ticker": "QQQ",
            "action": "額外加碼",
            "reason": track_a["signal_text"],
            "priority": 1,
        })

    # 軌道B（綠燈標的）
    for ticker, tb in track_b.items():
        if tb.get("signal") == "green":
            signals.append({
                "track": "B",
                "ticker": ticker,
                "action": "逢低買入",
                "score":  tb["score"],
                "reason": tb["signal_text"],
                "breakdown": tb["breakdown"],
                "priority": 2,
            })
        elif tb.get("signal") == "yellow":
            signals.append({
                "track": "B",
                "ticker": ticker,
                "action": "接近買入區",
                "score":  tb["score"],
                "reason": tb["signal_text"],
                "priority": 3,
            })

    # 軌道C（波段）
    for ticker, tc in track_c.items():
        if tc.get("signal") == "green":
            signals.append({
                "track": "C",
                "ticker": ticker,
                "action": "波段買入",
                "reason": tc["signal_text"],
                "priority": 1,
            })
        elif tc.get("signal") == "yellow":
            signals.append({
                "track": "C",
                "ticker": ticker,
                "action": "觀察中",
                "reason": tc["signal_text"],
                "priority": 4,
            })

    # 依優先級排序
    signals.sort(key=lambda x: x["priority"])

    # ── NVDA 雙邏輯判斷 ───────────────────────────────────
    nvda_dual = _nvda_dual_logic(stocks, calc_results, position_data)

    # ── 今日操作總結 ──────────────────────────────────────
    summary = ai_analysis.get("summary") or _build_rule_based_summary(
        signals, market, fear_greed, macro, nvda_dual
    )

    return {
        "date":        raw_data.get("date"),
        "agent":       "策略分析師",
        "track_a":     track_a,
        "track_b":     track_b,
        "track_c":     track_c,
        "pyramid":     pyramid,
        "signals":     signals,
        "nvda_dual":   nvda_dual,
        "summary":     summary,
        "ai_analysis": ai_analysis,
    }


def _nvda_dual_logic(stocks: dict, calc_results: dict, position_data: dict) -> dict:
    """NVDA 同時跑軌道B（價值）+ 軌道C（波段）雙邏輯"""
    nvda     = stocks.get("NVDA", {})
    track_b  = calc_results.get("track_b", {}).get("NVDA", {})
    track_c  = calc_results.get("track_c", {}).get("NVDA", {})
    pnl_info = position_data.get("pnl", {}).get("NVDA", {})

    # 價值角度
    value_score  = track_b.get("score", 0)
    value_signal = track_b.get("signal", "neutral")
    value_detail = []
    if track_b.get("breakdown"):
        bd = track_b["breakdown"]
        value_detail = [
            f"PE評分：{bd.get('pe',0)}分 ({bd.get('pe_detail','')})",
            f"FCF評分：{bd.get('fcf',0)}分 ({bd.get('fcf_detail','')})",
            f"52W評分：{bd.get('w52',0)}分 ({bd.get('w52_detail','')})",
            f"均線評分：{bd.get('ma200',0)}分 ({bd.get('ma200_detail','')})",
            f"目標價：{bd.get('analyst',0)}分 ({bd.get('analyst_detail','')})",
        ]

    # 波段角度
    swing_rsi    = nvda.get("rsi14")
    swing_vol    = nvda.get("volume_ratio")
    swing_signal = track_c.get("signal", "neutral")
    swing_text   = track_c.get("signal_text", "")

    # 現價 vs 成本
    cost_adjusted = position_data.get("cost_adjusted", {}).get("NVDA")
    price = nvda.get("price")
    pnl_pct = pnl_info.get("pnl_pct") if pnl_info else None

    # 建議
    if value_signal == "green" and swing_signal == "green":
        recommendation = "強烈買入（價值+波段雙確認）"
        color = "green"
    elif value_signal == "green":
        recommendation = "價值買入（波段待確認）"
        color = "yellow-green"
    elif swing_signal == "green":
        recommendation = "波段買入（價值未達標）"
        color = "yellow"
    elif swing_signal == "yellow" or value_signal == "yellow":
        recommendation = "持續觀察"
        color = "yellow"
    else:
        recommendation = "持倉不動"
        color = "neutral"

    return {
        "ticker": "NVDA",
        "price":  price,
        "cost_adjusted": cost_adjusted,
        "pnl_pct": pnl_pct,
        "value": {
            "score":  value_score,
            "signal": value_signal,
            "detail": value_detail,
        },
        "swing": {
            "rsi":    swing_rsi,
            "vol_ratio": swing_vol,
            "signal": swing_signal,
            "text":   swing_text,
        },
        "recommendation": recommendation,
        "color": color,
    }


def _build_rule_based_summary(signals, market, fear_greed, macro, nvda_dual) -> str:
    """不依賴 AI 的規則式摘要（備用）"""
    fgi = fear_greed.get("value", 50)
    vix = macro.get("vix", 20)
    pendulum = market.get("pendulum", "中性")
    stance   = market.get("stance", "正常操作")

    green_signals = [s for s in signals if s.get("priority", 9) <= 2]
    action_items  = []

    for s in green_signals[:3]:
        action_items.append(f"{s['ticker']}（{s['action']}）")

    if action_items:
        action_str = "、".join(action_items)
        action_part = f"今日建議關注：{action_str}。"
    else:
        action_part = "今日無明確買入訊號，建議持倉觀察。"

    nvda_part = f"NVDA 目前損益{nvda_dual['pnl_pct']:+.1f}%，建議{nvda_dual['recommendation']}。" if nvda_dual.get("pnl_pct") is not None else ""

    market_part = f"市場處於{pendulum}狀態（FGI={fgi:.0f}, VIX={vix:.1f}），策略態度：{stance}。"

    return f"{market_part} {action_part} {nvda_part}".strip()


def _call_gemini_analyst(raw_data: dict, calc_results: dict, position_data: dict) -> dict:
    """呼叫 Gemini API 進行策略分析"""
    from gemini_client import get_model, is_available
    if not is_available():
        return {
            "summary": None,
            "note": "Gemini API Key 尚未設定，使用規則式分析",
        }

    try:
        model = get_model()

        # 準備 prompt 數據
        stocks    = raw_data.get("stocks", {})
        fear_greed = raw_data.get("fear_greed", {})
        macro     = raw_data.get("macro", {})
        track_b   = calc_results.get("track_b", {})
        track_c   = calc_results.get("track_c", {})
        track_a   = calc_results.get("track_a", {})
        market    = calc_results.get("market", {})

        # 精簡數據供 prompt 使用
        key_stocks = {}
        for t in ["NVDA", "GOOGL", "MSFT", "QQQ", "TSM", "PLTR"]:
            s = stocks.get(t, {})
            key_stocks[t] = {
                "price": s.get("price"),
                "rsi":   s.get("rsi14"),
                "pe":    s.get("pe_ratio"),
                "ma200_dev": s.get("ma200_deviation_pct"),
                "vol_ratio": s.get("volume_ratio"),
                "fcf_yield": s.get("fcf_yield"),
                "from_52w_high": s.get("pct_from_52w_high"),
            }

        prompt = f"""你是一位專業的美股策略分析師。請根據以下數據，用繁體中文生成今日投資操作建議摘要（150字以內）。

市場數據：
- Fear & Greed Index: {fear_greed.get('value', 'N/A')} ({fear_greed.get('label', '')})
- VIX: {macro.get('vix', 'N/A')}
- 美債10年: {macro.get('treasury_10y', 'N/A')}%
- 市場鐘擺: {market.get('pendulum', 'N/A')} → 建議態度: {market.get('stance', 'N/A')}

軌道A（QQQ）: {track_a.get('signal_text', 'N/A')}

軌道B評分前3名:
{chr(10).join([f"- {t}: {v['score']}分 {v['signal_text']}" for t, v in sorted(track_b.items(), key=lambda x: x[1]['score'], reverse=True)[:3]])}

軌道C波段:
{chr(10).join([f"- {t}: {v['signal_text']}" for t, v in calc_results.get('track_c', {}).items()])}

NVDA現價: ${key_stocks.get('NVDA', {}).get('price', 'N/A')}  RSI: {key_stocks.get('NVDA', {}).get('rsi', 'N/A')}  分割後成本: ${position_data.get('cost_adjusted', {}).get('NVDA', 'N/A')}

請提供：1) 今日市場氣氛一句話 2) 最值得關注的1-2個操作機會 3) 風險提示。保持客觀、簡潔。"""

        response = model.generate_content(prompt)
        summary = response.text.strip()

        return {
            "summary": summary,
            "model":   config.GEMINI_MODEL,
            "note":    "AI生成",
        }

    except Exception as e:
        return {
            "summary": None,
            "note":    f"Gemini API 呼叫失敗：{e}，使用規則式分析",
        }


# ── 執行入口 ────────────────────────────────────────────────
if __name__ == "__main__":
    for path, name in [
        (os.path.join(config.DATA_DIR, "raw_data_cache.json"), "原始數據"),
        (os.path.join(config.DATA_DIR, "calc_cache.json"), "計算結果"),
        (os.path.join(config.DATA_DIR, "position_cache.json"), "部位數據"),
    ]:
        if not os.path.exists(path):
            print(f"請先執行對應步驟以產生 {name}")
            sys.exit(1)

    with open(os.path.join(config.DATA_DIR, "raw_data_cache.json"), "r", encoding="utf-8") as f:
        raw_data = json.load(f)
    with open(os.path.join(config.DATA_DIR, "calc_cache.json"), "r", encoding="utf-8") as f:
        calc_results = json.load(f)
    with open(os.path.join(config.DATA_DIR, "position_cache.json"), "r", encoding="utf-8") as f:
        position_data = json.load(f)

    result = run_analyst_agent(raw_data, calc_results, position_data)

    print("\n" + "="*60)
    print("  Agent 1：策略分析師 輸出")
    print("="*60)

    print(f"\n[今日操作總結]")
    print(f"  {result['summary']}")

    print(f"\n[觸發訊號]")
    if result["signals"]:
        for s in result["signals"]:
            icon = "✓" if s.get("priority", 9) <= 2 else "~"
            print(f"  {icon} 軌道{s['track']} {s['ticker']:<8} {s['action']}：{s['reason']}")
    else:
        print("  無觸發訊號")

    print(f"\n[NVDA 雙邏輯]")
    nd = result["nvda_dual"]
    print(f"  建議：{nd['recommendation']}")
    print(f"  價值角度（{nd['value']['score']}分）：{nd['value']['signal']}")
    print(f"  波段角度：{nd['swing']['text']}")

    if result["ai_analysis"].get("note"):
        print(f"\n[AI狀態] {result['ai_analysis']['note']}")

    # 儲存
    out_path = os.path.join(config.DATA_DIR, "analyst_cache.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n結果已儲存至：{out_path}")
