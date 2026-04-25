# ============================================================
# TRINITY - calculate.py
# 負責計算所有策略指標與評分
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


# ════════════════════════════════════════════════════════════
# 軌道 B 評分：逢低加碼評分（滿分100分）
# PE30 + FCF20 + 52W跌幅20 + 均線偏離15 + 目標價15
# ════════════════════════════════════════════════════════════

def calc_track_b_score(stock: dict) -> dict:
    """
    計算軌道B逢低加碼綜合評分（滿分100）
    回傳：score, breakdown, signal
    """
    breakdown = {}
    total = 0

    ticker = stock.get("ticker", "")

    # ── 1. 本益比評分（30分）─────────────────────────────
    pe        = stock.get("pe_ratio")
    pe_10y    = stock.get("pe_10y_avg")
    pe_score  = 0

    if pe and pe > 0:
        if pe_10y and pe_10y > 0:
            pe_discount = (pe_10y - pe) / pe_10y  # 相對10年均值折價比例
            if pe_discount >= 0.30:    # 打7折以下
                pe_score = 30
            elif pe_discount >= 0.15:  # 打85折
                pe_score = 22
            elif pe_discount >= 0.05:  # 打95折
                pe_score = 15
            elif pe_discount >= -0.10: # 基本合理
                pe_score = 8
            else:                      # 明顯高估
                pe_score = 0
        else:
            # 無歷史均值：用絕對PE評分
            if pe < 15:
                pe_score = 28
            elif pe < 20:
                pe_score = 22
            elif pe < 25:
                pe_score = 15
            elif pe < 35:
                pe_score = 8
            else:
                pe_score = 2
    else:
        pe_score = 5  # ETF或無PE標的給基本分

    breakdown["pe"]    = pe_score
    breakdown["pe_detail"] = f"PE={pe:.1f}, 10Y均={pe_10y}" if pe else "PE=N/A"
    total += pe_score

    # ── 2. FCF Yield 評分（20分）─────────────────────────
    fcf_yield = stock.get("fcf_yield")
    fcf_score = 0

    if fcf_yield is not None:
        if fcf_yield >= 5.0:
            fcf_score = 20
        elif fcf_yield >= 3.0:
            fcf_score = 15
        elif fcf_yield >= 1.5:
            fcf_score = 10
        elif fcf_yield >= 0.5:
            fcf_score = 5
        else:
            fcf_score = 0
    else:
        fcf_score = 5  # ETF 給基本分

    breakdown["fcf"]    = fcf_score
    breakdown["fcf_detail"] = f"FCF Yield={fcf_yield:.1f}%" if fcf_yield else "N/A（ETF）"
    total += fcf_score

    # ── 3. 52週跌幅評分（20分）─────────────────────────────
    w52_drop = stock.get("pct_from_52w_high")
    w52_score = 0

    if w52_drop is not None:
        drop = abs(w52_drop)
        if drop >= 35:
            w52_score = 20
        elif drop >= 25:
            w52_score = 15
        elif drop >= 15:
            w52_score = 10
        elif drop >= 8:
            w52_score = 5
        else:
            w52_score = 0

    breakdown["w52"]    = w52_score
    breakdown["w52_detail"] = f"距52W高={w52_drop:+.1f}%" if w52_drop is not None else "N/A"
    total += w52_score

    # ── 4. 200MA 偏離評分（15分）─────────────────────────
    ma_dev = stock.get("ma200_deviation_pct")
    ma_score = 0

    if ma_dev is not None:
        if ma_dev <= -20:
            ma_score = 15
        elif ma_dev <= -10:
            ma_score = 12
        elif ma_dev <= -5:
            ma_score = 8
        elif ma_dev <= 0:
            ma_score = 4
        elif ma_dev <= 10:
            ma_score = 2
        else:
            ma_score = 0

    breakdown["ma200"]   = ma_score
    breakdown["ma200_detail"] = f"200MA偏離={ma_dev:+.1f}%" if ma_dev is not None else "N/A"
    total += ma_score

    # ── 5. 分析師目標價空間（15分）───────────────────────
    upside = stock.get("upside_pct")
    analyst_score = 0

    if upside is not None:
        if upside >= 50:
            analyst_score = 15
        elif upside >= 30:
            analyst_score = 12
        elif upside >= 15:
            analyst_score = 8
        elif upside >= 5:
            analyst_score = 4
        else:
            analyst_score = 0

    breakdown["analyst"]  = analyst_score
    breakdown["analyst_detail"] = f"上漲空間={upside:+.1f}%" if upside is not None else "N/A"
    total += analyst_score

    # ── 最終評分與訊號 ────────────────────────────────────
    threshold = config.STRATEGY["track_b_score_threshold"]

    if total >= threshold:
        signal = "green"     # 亮綠燈
        signal_text = f"買入訊號（{total}分 >= {threshold}分）"
    elif total >= threshold - 15:
        signal = "yellow"    # 接近
        signal_text = f"接近買入（{total}分）"
    else:
        signal = "neutral"
        signal_text = f"尚未達標（{total}分 < {threshold}分）"

    return {
        "ticker":      ticker,
        "score":       total,
        "breakdown":   breakdown,
        "signal":      signal,
        "signal_text": signal_text,
        "threshold":   threshold,
    }


# ════════════════════════════════════════════════════════════
# 軌道 A：QQQ 額外加碼條件
# ════════════════════════════════════════════════════════════

def calc_track_a(fear_greed: dict, macro: dict) -> dict:
    """
    軌道A：FGI < 25 且 VIX > 30 → 觸發 QQQ 額外加碼
    """
    fgi = fear_greed.get("value", 50)
    vix = macro.get("vix", 0)

    fgi_thresh = config.STRATEGY["track_a_fgi_threshold"]
    vix_thresh = config.STRATEGY["track_a_vix_threshold"]

    fgi_trigger = fgi < fgi_thresh
    vix_trigger = vix > vix_thresh
    both        = fgi_trigger and vix_trigger

    if both:
        signal      = "green"
        signal_text = f"觸發加碼（FGI={fgi:.1f} < {fgi_thresh} 且 VIX={vix:.1f} > {vix_thresh}）"
    elif fgi_trigger or vix_trigger:
        signal      = "yellow"
        signal_text = f"部分條件達標（FGI={fgi:.1f}, VIX={vix:.1f}）"
    else:
        signal      = "neutral"
        signal_text = f"條件未達標（FGI={fgi:.1f}, VIX={vix:.1f}）"

    return {
        "fgi":           fgi,
        "vix":           vix,
        "fgi_trigger":   fgi_trigger,
        "vix_trigger":   vix_trigger,
        "fgi_threshold": fgi_thresh,
        "vix_threshold": vix_thresh,
        "signal":        signal,
        "signal_text":   signal_text,
        "add_amount_pct": config.MAX_SINGLE_ADD_PCT if both else 0,
    }


# ════════════════════════════════════════════════════════════
# 軌道 C：波段訊號
# ════════════════════════════════════════════════════════════

def calc_track_c(stock: dict) -> dict:
    """
    軌道C：RSI < 35（必要條件）+ 成交量 > 1.5倍均量（確認條件）
    """
    ticker     = stock.get("ticker", "")
    rsi        = stock.get("rsi14")
    vol_ratio  = stock.get("volume_ratio")

    rsi_thresh = config.STRATEGY["track_c_rsi_buy"]
    vol_thresh = config.STRATEGY["track_c_volume_mult"]

    rsi_trigger = (rsi is not None) and (rsi < rsi_thresh)
    vol_confirm = (vol_ratio is not None) and (vol_ratio >= vol_thresh)

    if rsi_trigger and vol_confirm:
        signal      = "green"
        signal_text = f"強烈波段買入（RSI={rsi:.1f} < {rsi_thresh} + 量比={vol_ratio:.2f} > {vol_thresh}）"
    elif rsi_trigger:
        signal      = "yellow"
        signal_text = f"RSI觸底（{rsi:.1f}）但成交量未確認（量比={vol_ratio:.2f}）"
    elif vol_confirm and rsi is not None and rsi < 45:
        signal      = "yellow"
        signal_text = f"量能放大（{vol_ratio:.2f}x）但RSI={rsi:.1f}未到超賣"
    else:
        signal      = "neutral"
        rsi_str = f"{rsi:.1f}" if rsi is not None else "N/A"
        vol_str = f"{vol_ratio:.2f}" if vol_ratio is not None else "N/A"
        signal_text = f"無波段訊號（RSI={rsi_str}, 量比={vol_str}）"

    return {
        "ticker":      ticker,
        "rsi":         rsi,
        "vol_ratio":   vol_ratio,
        "rsi_trigger": rsi_trigger,
        "vol_confirm": vol_confirm,
        "signal":      signal,
        "signal_text": signal_text,
    }


# ════════════════════════════════════════════════════════════
# 金字塔加碼計算
# ════════════════════════════════════════════════════════════

def calc_pyramid(ticker: str, current_price: float, cost_basis: float, total_capital_usd: float) -> dict:
    """
    計算金字塔加碼建議
    """
    if not cost_basis or not current_price:
        return {"ticker": ticker, "drop_pct": None, "levels": [], "current_level": None}

    drop_pct = (current_price - cost_basis) / cost_basis * 100

    levels = []
    for lvl in config.PYRAMID:
        threshold  = lvl["drop_pct"] * 100  # 轉為百分比
        add_pct    = lvl["add_pct"]
        triggered  = drop_pct <= threshold
        add_amount = total_capital_usd * config.MAX_SINGLE_ADD_PCT * add_pct
        levels.append({
            "threshold_pct":  threshold,
            "add_proportion": f"{add_pct*100:.0f}%",
            "add_amount_usd": round(add_amount, 0),
            "triggered":      triggered,
            "price_level":    round(cost_basis * (1 + lvl["drop_pct"]), 2),
        })

    # 目前觸發哪一層
    current_level = None
    for lvl in reversed(levels):
        if lvl["triggered"]:
            current_level = lvl
            break

    return {
        "ticker":        ticker,
        "cost_basis":    cost_basis,
        "current_price": current_price,
        "drop_pct":      round(drop_pct, 2),
        "levels":        levels,
        "current_level": current_level,
    }


# ════════════════════════════════════════════════════════════
# 市場三層分析（共用函式，howard_marks_agent 也 import 這裡）
# ════════════════════════════════════════════════════════════

def calc_emotion_layer(fear_greed: dict, macro: dict) -> dict:
    """情緒層：FGI + VIX（單一計算來源）"""
    fgi = fear_greed.get("value", 50)
    vix = macro.get("vix", 20)
    tnx = macro.get("treasury_10y", 4.0)

    if fgi <= 20:
        fgi_state, fgi_score = "極度恐懼", 3
    elif fgi <= 35:
        fgi_state, fgi_score = "恐懼", 2
    elif fgi <= 55:
        fgi_state, fgi_score = "中性", 0
    elif fgi <= 75:
        fgi_state, fgi_score = "貪婪", -1
    else:
        fgi_state, fgi_score = "極度貪婪", -2

    if vix > 35:
        vix_state, vix_score = "市場恐慌", 3
    elif vix > 25:
        vix_state, vix_score = "高波動", 2
    elif vix > 20:
        vix_state, vix_score = "警戒", 1
    elif vix > 15:
        vix_state, vix_score = "正常", 0
    else:
        vix_state, vix_score = "過度樂觀", -1

    if tnx > 5.0:
        tnx_note = "殖利率偏高，股票估值壓力大"
    elif tnx > 4.5:
        tnx_note = "殖利率尚高，成長股承壓"
    elif tnx > 4.0:
        tnx_note = "殖利率中性"
    else:
        tnx_note = "殖利率有利股市"

    total_score = fgi_score + vix_score
    return {
        "fgi":          fgi,
        "fgi_label":    fear_greed.get("label", fgi_state),
        "fgi_state":    fgi_state,
        "fgi_score":    fgi_score,
        "vix":          vix,
        "vix_state":    vix_state,
        "vix_score":    vix_score,
        "treasury_10y": tnx,
        "tnx_note":     tnx_note,
        "total_score":  total_score,
        "summary":      f"情緒面：{fgi_state}（FGI={fgi:.0f}）+ {vix_state}（VIX={vix:.1f}）",
    }


def calc_credit_layer(credit_spread: dict) -> dict:
    """信用層：HY OAS Credit Spread（單一計算來源）"""
    cs = credit_spread.get("value")

    if cs is None:
        return {
            "value":   None,
            "state":   "未知",
            "score":   0,
            "summary": "Credit Spread 數據未取得（需設定 FRED API Key）",
            "advice":  "請填入 FRED API Key 以啟用信用週期分析",
        }

    if cs < config.CREDIT_SPREAD["overheat"]:
        state, score = "過熱", -3
        advice = f"信用利差 {cs}bps 極度壓縮，市場過熱，需謹慎"
    elif cs < config.CREDIT_SPREAD["opportunity"]:
        state, score = "正常", 0
        advice = f"信用利差 {cs}bps 正常範圍"
    elif cs < config.CREDIT_SPREAD["crisis"]:
        state, score = "機會", 2
        advice = f"信用利差 {cs}bps 擴大，出現投資機會"
    else:
        state, score = "危機", 3
        advice = f"信用利差 {cs}bps 危機水位，極端機會但需控制風險"

    history = credit_spread.get("history", [])
    trend   = "上升" if len(history) >= 2 and history[-1]["value"] > history[0]["value"] else "下降"

    return {
        "value":   cs,
        "state":   state,
        "score":   score,
        "trend":   trend,
        "advice":  advice,
        "summary": f"信用層：{state}（{cs}bps，趨勢{trend}）",
        "thresholds": {
            "overheat":    config.CREDIT_SPREAD["overheat"],
            "opportunity": config.CREDIT_SPREAD["opportunity"],
            "crisis":      config.CREDIT_SPREAD["crisis"],
        },
    }


def calc_valuation_layer(stocks: dict) -> dict:
    """估值層：QQQ PE vs 歷史均值（單一計算來源）"""
    qqq    = stocks.get("QQQ", {})
    qqq_pe = qqq.get("pe_ratio")
    historical_avg_pe = 25  # QQQ 歷史均值約 25x

    if qqq_pe:
        premium = (qqq_pe / historical_avg_pe - 1) * 100
        if premium > 30:
            state, score = "嚴重高估", -2
        elif premium > 15:
            state, score = "高估", -1
        elif premium > -10:
            state, score = "合理", 0
        elif premium > -25:
            state, score = "低估", 1
        else:
            state, score = "極度低估", 2
    else:
        qqq_pe, premium, state, score = None, None, "未知", 0

    pe_overview = {}
    for ticker in ["NVDA", "GOOGL", "MSFT", "V", "ASML", "TSM"]:
        s = stocks.get(ticker, {})
        pe = s.get("pe_ratio")
        pe_10y = s.get("pe_10y_avg")
        if pe:
            if pe_10y and pe_10y > 0:
                disc = round((pe_10y - pe) / pe_10y * 100, 1)
                pe_overview[ticker] = {"pe": pe, "vs_10y_avg": f"{disc:+.1f}%折/溢價"}
            else:
                pe_overview[ticker] = {"pe": pe, "vs_10y_avg": "歷史均值未知"}

    return {
        "qqq_pe":         qqq_pe,
        "historical_avg": historical_avg_pe,
        "premium_pct":    round(premium, 1) if premium is not None else None,
        "state":          state,
        "score":          score,
        "pe_overview":    pe_overview,
        "summary":        f"估值層：QQQ PE={qqq_pe:.1f}（{state}，vs歷史均值{premium:+.1f}%）"
                          if qqq_pe and premium is not None else "估值層：數據不足",
    }


def calc_pendulum_position(emotion: dict, credit: dict, valuation: dict) -> dict:
    """綜合鐘擺位置（單一計算來源）"""
    total_score = (
        emotion.get("total_score", 0) * 1.0 +
        credit.get("score", 0) * 1.5 +
        valuation.get("score", 0) * 0.5
    )

    if total_score >= 5:
        position, stance, color, position_pct = "深度恐懼", "積極加倉（歷史最佳機會區）", "green", 90
        cycle_note = f"市場深度恐懼（評分{total_score:.1f}），歷史上此刻往往是最佳買點"
    elif total_score >= 3:
        position, stance, color, position_pct = "恐懼", "逢低建倉（機會大於風險）", "yellow-green", 70
        cycle_note = f"鐘擺偏向恐懼端（評分{total_score:.1f}），建議積極布局但保留子彈"
    elif total_score >= 1:
        position, stance, color, position_pct = "輕微恐懼", "正常加倉", "yellow", 55
        cycle_note = f"市場情緒偏謹慎（評分{total_score:.1f}），可正常操作"
    elif total_score >= -1:
        position, stance, color, position_pct = "中性", "維持現有部位", "neutral", 50
        cycle_note = f"市場鐘擺中性（評分{total_score:.1f}），不宜追高也不急於加碼"
    elif total_score >= -3:
        position, stance, color, position_pct = "貪婪", "控制新倉，保留現金", "orange", 35
        cycle_note = f"市場偏樂觀（評分{total_score:.1f}），小心追高，等待回調機會"
    else:
        position, stance, color, position_pct = "極度貪婪", "大幅減少新倉，等待回調", "red", 20
        cycle_note = f"市場極度貪婪（評分{total_score:.1f}），霍華馬克斯警告：鐘擺終將回擺"

    return {
        "position":     position,
        "stance":       stance,
        "color":        color,
        "total_score":  round(total_score, 1),
        "position_pct": position_pct,
        "cycle_note_fallback": cycle_note,
        "components": {
            "emotion":   emotion.get("total_score", 0),
            "credit":    credit.get("score", 0),
            "valuation": valuation.get("score", 0),
        },
    }


def calc_market_environment(fear_greed: dict, macro: dict, credit_spread: dict, stocks: dict = None) -> dict:
    """
    綜合判斷市場環境，供 analyst_agent 與網站使用。
    直接呼叫共用層函式，不再重複實作邏輯。
    """
    emotion   = calc_emotion_layer(fear_greed, macro)
    credit    = calc_credit_layer(credit_spread)
    valuation = calc_valuation_layer(stocks) if stocks else {"score": 0, "state": "未知", "qqq_pe": None, "premium_pct": None, "pe_overview": {}, "summary": "估值層：未傳入股票數據"}
    pendulum  = calc_pendulum_position(emotion, credit, valuation)

    return {
        "fgi":           emotion["fgi"],
        "vix":           emotion["vix"],
        "credit_spread": credit.get("value"),
        "emotion":       emotion["fgi_state"],
        "credit_label":  credit.get("state", "未知"),
        "pendulum":      pendulum["position"],
        "stance":        pendulum["stance"],
        "color":         pendulum["color"],
        "total_score":   pendulum["total_score"],
        "vix_state":     emotion["vix_state"],
        "tnx_note":      emotion["tnx_note"],
    }


# ════════════════════════════════════════════════════════════
# 主函式：計算所有指標
# ════════════════════════════════════════════════════════════

def calculate_all(raw_data: dict) -> dict:
    """
    輸入：fetch_data 的原始數據
    輸出：所有策略指標計算結果
    """
    stocks        = raw_data.get("stocks", {})
    fear_greed    = raw_data.get("fear_greed", {})
    macro         = raw_data.get("macro", {})
    credit_spread = raw_data.get("credit_spread", {})

    # 換算總資金為美元
    total_usd = config.TOTAL_CAPITAL_TWD / config.USD_TWD_RATE

    results = {
        "date":      raw_data.get("date"),
        "track_a":   {},
        "track_b":   {},
        "track_c":   {},
        "pyramid":   {},
        "market":    {},
    }

    # ── 軌道 A ─────────────────────────────────────────────
    results["track_a"] = calc_track_a(fear_greed, macro)

    # ── 市場環境 ───────────────────────────────────────────
    results["market"] = calc_market_environment(fear_greed, macro, credit_spread, stocks)

    # ── 軌道 B、C、金字塔（逐股）──────────────────────────
    for ticker in config.PORTFOLIO["value_stocks"]:
        stock = stocks.get(ticker, {})
        if stock:
            results["track_b"][ticker] = calc_track_b_score(stock)

    for ticker in config.PORTFOLIO["swing"]:
        stock = stocks.get(ticker, {})
        if stock:
            results["track_c"][ticker] = calc_track_c(stock)

    # 金字塔加碼（只針對有成本價的持倉）
    for ticker, cost in config.COST_BASIS.items():
        stock = stocks.get(ticker, {})
        price = stock.get("price")
        if price:
            results["pyramid"][ticker] = calc_pyramid(ticker, price, cost, total_usd)

    return results


def print_calculation_summary(results: dict, raw_data: dict):
    """印出計算結果摘要"""
    print("\n" + "="*60)
    print("  TRINITY 指標計算結果")
    print("="*60)

    # 軌道 A
    ta = results["track_a"]
    print(f"\n[軌道A] QQQ 額外加碼條件")
    print(f"  {ta['signal_text']}")

    # 軌道 B
    print(f"\n[軌道B] 逢低加碼評分（綠燈 >= {config.STRATEGY['track_b_score_threshold']}分）")
    tb_sorted = sorted(results["track_b"].items(), key=lambda x: x[1]["score"], reverse=True)
    for ticker, tb in tb_sorted:
        signal_icon = "✓ " if tb["signal"] == "green" else ("~ " if tb["signal"] == "yellow" else "  ")
        print(f"  {signal_icon}{ticker:<8} {tb['score']:>3}分  {tb['signal_text']}")
        bd = tb["breakdown"]
        print(f"           PE={bd['pe']}分 FCF={bd['fcf']}分 52W={bd['w52']}分 MA={bd['ma200']}分 目標={bd['analyst']}分")

    # 軌道 C
    print(f"\n[軌道C] 波段訊號（RSI<35 + 量比>1.5）")
    for ticker, tc in results["track_c"].items():
        signal_icon = "✓ " if tc["signal"] == "green" else ("~ " if tc["signal"] == "yellow" else "  ")
        print(f"  {signal_icon}{ticker:<8} {tc['signal_text']}")

    # 金字塔
    print(f"\n[金字塔加碼] 持倉跌幅分析")
    for ticker, pyr in results["pyramid"].items():
        print(f"  {ticker}: 成本${pyr['cost_basis']} 現價${pyr['current_price']} 跌幅{pyr['drop_pct']:+.1f}%")
        for lvl in pyr["levels"]:
            triggered_mark = " <== 已觸發" if lvl["triggered"] else ""
            print(f"    跌{abs(lvl['threshold_pct']):.0f}%（${lvl['price_level']}）加{lvl['add_proportion']} = ${lvl['add_amount_usd']:.0f}{triggered_mark}")

    # 市場環境
    mkt = results["market"]
    print(f"\n[市場鐘擺] {mkt['pendulum']}  建議：{mkt['stance']}")
    print(f"  FGI={mkt['fgi']:.1f} ({raw_data['fear_greed'].get('label','')})  VIX={mkt['vix']}  Credit Spread={mkt['credit_spread']} bps")

    print("\n" + "="*60)


# ── 執行入口 ────────────────────────────────────────────────
if __name__ == "__main__":
    cache_path = os.path.join(config.DATA_DIR, "raw_data_cache.json")
    if not os.path.exists(cache_path):
        print("請先執行 fetch_data.py")
        sys.exit(1)

    with open(cache_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    results = calculate_all(raw_data)
    print_calculation_summary(results, raw_data)

    # 儲存計算結果
    calc_path = os.path.join(config.DATA_DIR, "calc_cache.json")
    with open(calc_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n計算結果已儲存至：{calc_path}")
