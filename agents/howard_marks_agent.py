# ============================================================
# TRINITY - howard_marks_agent.py
# Agent 3：霍華馬克斯大腦（市場鐘擺與週期分析）
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
from core.calculate import (
    calc_emotion_layer,
    calc_credit_layer,
    calc_valuation_layer,
    calc_pendulum_position,
)


def run_howard_marks_agent(raw_data: dict, calc_results: dict) -> dict:
    """
    霍華馬克斯大腦：市場鐘擺現在在哪裡？
    """
    fear_greed    = raw_data.get("fear_greed", {})
    macro         = raw_data.get("macro", {})
    credit_spread = raw_data.get("credit_spread", {})
    stocks        = raw_data.get("stocks", {})

    # ── 三層分析（來自 calculate.py 共用函式）────────────
    emotion_layer   = calc_emotion_layer(fear_greed, macro)
    credit_layer    = calc_credit_layer(credit_spread)
    valuation_layer = calc_valuation_layer(stocks)
    pendulum        = calc_pendulum_position(emotion_layer, credit_layer, valuation_layer)

    # ── AI 深度分析 ────────────────────────────────────────
    ai_insight = _call_gemini_howard_marks(
        raw_data, emotion_layer, credit_layer, valuation_layer, pendulum
    )

    # 週期觀察一句話
    cycle_note = ai_insight.get("cycle_note") or pendulum.get("cycle_note_fallback", "")

    return {
        "date":             raw_data.get("date"),
        "agent":            "霍華馬克斯大腦",
        "emotion_layer":    emotion_layer,
        "credit_layer":     credit_layer,
        "valuation_layer":  valuation_layer,
        "pendulum":         pendulum,
        "cycle_note":       cycle_note,
        "ai_insight":       ai_insight,
    }


def _call_gemini_howard_marks(raw_data, emotion, credit, valuation, pendulum) -> dict:
    """呼叫 Gemini API 進行霍華馬克斯式週期分析"""
    from gemini_client import get_model, is_available
    if not is_available():
        return {
            "cycle_note": None,
            "full_text":  "",
            "note":       "Gemini API Key 尚未設定",
        }

    try:
        model = get_model()

        fgi = raw_data.get("fear_greed", {}).get("value", 50)
        vix = raw_data.get("macro", {}).get("vix", 20)
        cs  = raw_data.get("credit_spread", {}).get("value", "N/A")

        prompt = f"""你是霍華馬克斯（Howard Marks）的投資分析助理，專注於市場週期與鐘擺理論。

當前市場數據：
- Fear & Greed Index: {fgi:.0f}（{emotion['fgi_label']}）
- VIX: {vix:.1f}（{emotion['vix_state']}）
- 美債10年殖利率: {raw_data.get('macro', {}).get('treasury_10y', 'N/A')}%
- 信用利差（HY OAS）: {cs} bps → {credit.get('state', 'N/A')}
- QQQ PE: {valuation.get('qqq_pe', 'N/A')}（{valuation.get('state', 'N/A')}）
- 綜合鐘擺位置: {pendulum['position']}（評分{pendulum['total_score']}）

情緒層：{emotion['summary']}
信用層：{credit['summary']}
估值層：{valuation['summary']}

請以霍華馬克斯的週期理論視角，用繁體中文輸出：
1. 鐘擺位置判斷（一句話）
2. 建議倉位態度（一句話）
3. 本週最重要的週期觀察（一句話，點出最關鍵的市場訊號）

格式：
鐘擺: [位置描述]
態度: [建議行動]
週期: [最重要觀察]"""

        response = model.generate_content(prompt)
        ai_text  = response.text.strip()

        # 提取週期觀察
        cycle_note = ""
        for line in ai_text.split("\n"):
            if line.strip().startswith("週期:") or line.strip().startswith("週期："):
                cycle_note = line.strip().replace("週期:", "").replace("週期：", "").strip()
                break

        if not cycle_note:
            lines = [l.strip() for l in ai_text.split("\n") if l.strip()]
            cycle_note = lines[-1] if lines else ""

        return {
            "cycle_note": cycle_note,
            "full_text":  ai_text,
            "note":       "AI生成",
        }

    except Exception as e:
        return {
            "cycle_note": None,
            "full_text":  "",
            "note":       f"Gemini API 失敗：{e}",
        }


# ── 執行入口 ────────────────────────────────────────────────
if __name__ == "__main__":
    for path, name in [
        (os.path.join(config.DATA_DIR, "raw_data_cache.json"), "原始數據"),
        (os.path.join(config.DATA_DIR, "calc_cache.json"), "計算結果"),
    ]:
        if not os.path.exists(path):
            print(f"請先執行對應步驟以產生 {name}")
            sys.exit(1)

    with open(os.path.join(config.DATA_DIR, "raw_data_cache.json"), "r", encoding="utf-8") as f:
        raw_data = json.load(f)
    with open(os.path.join(config.DATA_DIR, "calc_cache.json"), "r", encoding="utf-8") as f:
        calc_results = json.load(f)

    result = run_howard_marks_agent(raw_data, calc_results)

    print("\n" + "="*60)
    print("  Agent 3：霍華馬克斯大腦 輸出")
    print("="*60)

    p = result["pendulum"]
    print(f"\n[市場鐘擺位置]  {p['position']}  （評分：{p['total_score']}）")
    print(f"[建議倉位態度]  {p['stance']}")
    print(f"[週期觀察]      {result['cycle_note']}")

    print(f"\n--- 三層分析 ---")
    print(f"情緒層：{result['emotion_layer']['summary']}")
    print(f"信用層：{result['credit_layer']['summary']}")
    print(f"估值層：{result['valuation_layer']['summary']}")

    if result["ai_insight"].get("full_text"):
        print(f"\n--- AI 完整輸出 ---")
        print(result["ai_insight"]["full_text"])

    if result["ai_insight"].get("note"):
        print(f"\n[AI狀態] {result['ai_insight']['note']}")

    out_path = os.path.join(config.DATA_DIR, "howard_marks_cache.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n結果已儲存至：{out_path}")
