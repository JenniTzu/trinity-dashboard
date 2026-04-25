# ============================================================
# TRINITY - buffett_agent.py
# Agent 2：巴菲特大腦（基本面護城河分析）
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


def run_buffett_agent(raw_data: dict) -> dict:
    """
    巴菲特大腦：這家公司值得持有10年嗎？
    """
    stocks = raw_data.get("stocks", {})

    all_verdicts = {}

    # 分析所有持倉標的（不含純ETF）
    tickers_to_analyze = [
        t for t in (config.PORTFOLIO["value_stocks"] + config.PORTFOLIO["swing"])
        if t not in ["QQQ", "SMH", "XLF", "XLE", "VTI", "GLD"]
    ]

    for ticker in tickers_to_analyze:
        stock = stocks.get(ticker, {})
        if stock:
            verdict = _analyze_moat(ticker, stock)
            all_verdicts[ticker] = verdict

    # AI 深度分析（若有 API Key）
    ai_insights = _call_gemini_buffett(raw_data, all_verdicts)

    # 整合 AI 見解
    if ai_insights.get("verdicts"):
        for ticker, insight in ai_insights["verdicts"].items():
            if ticker in all_verdicts:
                all_verdicts[ticker]["ai_comment"] = insight

    return {
        "date":       raw_data.get("date"),
        "agent":      "巴菲特大腦",
        "verdicts":   all_verdicts,
        "ai_summary": ai_insights.get("summary", ""),
        "ai_note":    ai_insights.get("note", ""),
    }


def _analyze_moat(ticker: str, stock: dict) -> dict:
    """基本面護城河規則分析"""
    issues   = []
    strengths = []
    score    = 0
    max_score = 5

    # ── 1. ROE 連5年 > 15% ─────────────────────────────
    roe = stock.get("roe")
    roe_trend = stock.get("roe_trend", [])

    if roe is not None:
        if roe >= config.BUFFETT["roe_min"]:
            score += 1
            strengths.append(f"ROE={roe:.1f}% 優良（>{config.BUFFETT['roe_min']}%）")
        else:
            issues.append(f"ROE={roe:.1f}% 偏低（<{config.BUFFETT['roe_min']}%）")

    # 5年ROE趨勢
    if len(roe_trend) >= 3:
        roe_values = [r["roe"] for r in roe_trend if r.get("roe") is not None]
        all_above_15 = all(r > config.BUFFETT["roe_min"] for r in roe_values)
        if all_above_15:
            score += 1
            strengths.append(f"ROE連{len(roe_values)}年均>15%")
        else:
            low_years = [r for r in roe_values if r <= config.BUFFETT["roe_min"]]
            if low_years:
                issues.append(f"歷史ROE曾低於15%（{len(low_years)}年）")

    # ── 2. 毛利率趨勢上升 ──────────────────────────────
    gm_trend = stock.get("gross_margin_trend", [])
    if len(gm_trend) >= 2:
        gm_values = [g["gross_margin"] for g in gm_trend if g.get("gross_margin") is not None]
        if len(gm_values) >= 2:
            # 最新 vs 最舊
            latest  = gm_values[0]
            oldest  = gm_values[-1]
            if latest > oldest:
                score += 1
                strengths.append(f"毛利率上升趨勢（{oldest:.1f}% → {latest:.1f}%）")
            elif latest > oldest - 2:
                score += 0.5
                strengths.append(f"毛利率穩定（{oldest:.1f}% → {latest:.1f}%）")
            else:
                issues.append(f"毛利率下降（{oldest:.1f}% → {latest:.1f}%）")

    # ── 3. FCF 穩定成長 ─────────────────────────────────
    fcf_yield = stock.get("fcf_yield")
    if fcf_yield is not None:
        if fcf_yield >= 3.0:
            score += 1
            strengths.append(f"FCF Yield 健康（{fcf_yield:.1f}%）")
        elif fcf_yield >= 1.0:
            score += 0.5
            strengths.append(f"FCF Yield 尚可（{fcf_yield:.1f}%）")
        else:
            issues.append(f"FCF Yield 偏低（{fcf_yield:.1f}%）")
    else:
        issues.append("FCF 數據無法取得")

    # ── 4. 負債健康 ────────────────────────────────────
    dte = stock.get("debt_to_equity")
    if dte is not None:
        if dte < 50:
            score += 1
            strengths.append(f"負債比率健康（D/E={dte:.1f}%）")
        elif dte < 150:
            score += 0.5
            strengths.append(f"負債比率適中（D/E={dte:.1f}%）")
        else:
            issues.append(f"負債偏高（D/E={dte:.1f}%）")
    else:
        issues.append("負債數據無法取得")

    # ── 5. 分析師目標價 ────────────────────────────────
    upside = stock.get("upside_pct")
    if upside is not None and upside > 10:
        score += 0.5
        strengths.append(f"分析師看漲（上漲空間{upside:.1f}%）")

    # ── 最終判斷 ────────────────────────────────────────
    score_ratio = score / max_score

    if score_ratio >= 0.7:
        verdict = "moat_strong"
        verdict_icon = "✅"
        verdict_text = "護城河穩固"
        reason = f"{ticker} 基本面優良：{', '.join(strengths[:2])}"
    elif score_ratio >= 0.4:
        verdict = "watch"
        verdict_icon = "⚠️"
        verdict_text = "需觀察"
        reason_parts = []
        if strengths:
            reason_parts.append(f"優勢：{strengths[0]}")
        if issues:
            reason_parts.append(f"隱憂：{issues[0]}")
        reason = f"{ticker} 基本面中性：{'；'.join(reason_parts)}"
    else:
        verdict = "deteriorating"
        verdict_icon = "❌"
        verdict_text = "基本面惡化"
        reason = f"{ticker} 需謹慎：{', '.join(issues[:2])}" if issues else f"{ticker} 數據不足，無法評估"

    return {
        "ticker":       ticker,
        "score":        round(score, 1),
        "max_score":    max_score,
        "verdict":      verdict,
        "verdict_icon": verdict_icon,
        "verdict_text": verdict_text,
        "reason":       reason,
        "strengths":    strengths,
        "issues":       issues,
        "roe":          roe,
        "fcf_yield":    fcf_yield,
        "dte":          dte,
        "gm_trend":     gm_trend,
        "roe_trend":    roe_trend,
        "ai_comment":   "",   # 由 AI 填入
    }


def _call_gemini_buffett(raw_data: dict, verdicts: dict) -> dict:
    """呼叫 Gemini API 進行巴菲特式分析"""
    from gemini_client import get_model, is_available
    if not is_available():
        return {
            "verdicts": {},
            "summary":  "",
            "note":     "Gemini API Key 尚未設定",
        }

    try:
        model = get_model()

        stocks = raw_data.get("stocks", {})

        # 準備各股摘要
        stock_summaries = []
        for ticker, v in verdicts.items():
            s = stocks.get(ticker, {})
            stock_summaries.append(
                f"{ticker}: ROE={s.get('roe','N/A')}% FCF={s.get('fcf_yield','N/A')}% "
                f"PE={s.get('pe_ratio','N/A')} D/E={s.get('debt_to_equity','N/A')} "
                f"分析師目標={s.get('analyst_target','N/A')} 規則評分={v['score']}/{v['max_score']}"
            )

        prompt = f"""你是巴菲特的投資分析助理。請針對以下持股，以「這家公司值得持有10年嗎？」的角度，用繁體中文給出簡短評估。

每檔股票請輸出格式：
TICKER: [✅護城河穩固 / ⚠️需觀察 / ❌基本面惡化] — 一句話說明原因

股票數據：
{chr(10).join(stock_summaries)}

最後請用2句話總結整個投資組合的基本面品質。"""

        response  = model.generate_content(prompt)
        ai_text   = response.text.strip()

        # 解析 AI 輸出
        ai_verdicts = {}
        for line in ai_text.split("\n"):
            for ticker in verdicts.keys():
                if line.strip().startswith(ticker + ":"):
                    ai_verdicts[ticker] = line.strip()[len(ticker)+1:].strip()
                    break

        # 提取總結（最後2行）
        lines   = [l.strip() for l in ai_text.split("\n") if l.strip()]
        summary = " ".join(lines[-2:]) if len(lines) >= 2 else ai_text

        return {
            "verdicts": ai_verdicts,
            "summary":  summary,
            "note":     "AI生成",
            "full_text": ai_text,
        }

    except Exception as e:
        return {
            "verdicts": {},
            "summary":  "",
            "note":     f"Gemini API 失敗：{e}",
        }


# ── 執行入口 ────────────────────────────────────────────────
if __name__ == "__main__":
    cache_path = os.path.join(config.DATA_DIR, "raw_data_cache.json")
    if not os.path.exists(cache_path):
        print("請先執行 fetch_data.py")
        sys.exit(1)

    with open(cache_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    result = run_buffett_agent(raw_data)

    print("\n" + "="*60)
    print("  Agent 2：巴菲特大腦 輸出")
    print("="*60)

    print(f"\n[護城河評估]")
    for ticker, v in result["verdicts"].items():
        ai_part = f"\n          AI: {v['ai_comment']}" if v.get("ai_comment") else ""
        print(f"  {v['verdict_icon']} {ticker:<8} {v['verdict_text']:<10} （{v['score']}/{v['max_score']}分）")
        print(f"     {v['reason']}{ai_part}")

    if result.get("ai_summary"):
        print(f"\n[AI總結] {result['ai_summary']}")

    if result.get("ai_note"):
        print(f"[AI狀態] {result['ai_note']}")

    out_path = os.path.join(config.DATA_DIR, "buffett_cache.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n結果已儲存至：{out_path}")
