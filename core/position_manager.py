# ============================================================
# TRINITY - position_manager.py
# 負責部位風險管理：集中度警示、損失估計、可用子彈計算
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


def get_total_capital_usd() -> float:
    """取得總資金（美元）"""
    return config.TOTAL_CAPITAL_TWD / config.USD_TWD_RATE


def calc_position_risk(raw_data: dict) -> dict:
    """
    計算完整部位風險報告
    """
    stocks     = raw_data.get("stocks", {})
    total_usd  = get_total_capital_usd()
    total_twd  = config.TOTAL_CAPITAL_TWD

    # ── 估算各持倉市值（假設各自持有1單位，實際應由用戶輸入）──
    # 注意：這裡計算的是「若跌X%，總資金損失多少」的情境分析
    # 而非真實持倉比例（因系統沒有帳戶連接）

    # 使用設定的成本價計算虛擬持倉比例
    # NVDA注意：2024/6/10進行10:1分割，若成本為分割前850，
    # 需除以10得到分割後成本85
    cost_basis_adjusted = {}
    split_notes = {}

    for ticker, cost in config.COST_BASIS.items():
        current_price = stocks.get(ticker, {}).get("price")
        if current_price and cost and current_price > 0:
            # 自動偵測是否需要調整分割（若成本/現價 > 5，可能未調整）
            ratio = cost / current_price
            if ratio > 5:
                adjusted = cost / 10  # 10:1分割調整
                cost_basis_adjusted[ticker] = adjusted
                split_notes[ticker] = f"原始成本${cost} -> 分割後成本${adjusted}（10:1調整）"
            else:
                cost_basis_adjusted[ticker] = cost
        else:
            cost_basis_adjusted[ticker] = cost

    # ── 假設持倉比例（無帳戶連接，使用估算值）─────────────────
    assumed_allocation = {
        "NVDA":  0.15,
        "QQQ":   0.20,
        "SMH":   0.10,
        "GOOGL": 0.08,
        "MSFT":  0.08,
        "V":     0.05,
        "BRK-B": 0.05,
        "GLD":   0.07,
        "TSM":   0.05,
        "PLTR":  0.05,
        "AMD":   0.05,
        "ASML":  0.05,
        "VTI":   0.02,
    }

    # ── 集中度計算（用假設持倉比例，非股價比例）─────────────
    concentration_tickers   = config.CONCENTRATION_WARN["tickers"]
    concentration_threshold = config.CONCENTRATION_WARN["threshold"]

    conc_pct = {
        t: round(assumed_allocation.get(t, 0) * 100, 1)
        for t in concentration_tickers
    }
    concentration_ratio = sum(assumed_allocation.get(t, 0) for t in concentration_tickers)
    concentration_alert = concentration_ratio > concentration_threshold

    # ── 情境分析：若各標的跌20%損失估計 ──────────────────────
    scenario_loss = {}
    total_invested_usd = 0

    for ticker, alloc in assumed_allocation.items():
        invested = total_usd * alloc
        total_invested_usd += invested
        scenario_loss[ticker] = {
            "invested_usd":    round(invested, 0),
            "invested_twd":    round(invested * config.USD_TWD_RATE, 0),
            "loss_20pct_usd":  round(invested * 0.20, 0),
            "loss_20pct_twd":  round(invested * 0.20 * config.USD_TWD_RATE, 0),
        }

    # 總組合若跌20%損失
    total_loss_20pct_usd = round(total_invested_usd * 0.20, 0)
    total_loss_20pct_twd = round(total_loss_20pct_usd * config.USD_TWD_RATE, 0)

    # ── 可用子彈 ───────────────────────────────────────────
    # 假設已投入70%資金，剩餘30%為現金
    invested_ratio  = 0.70
    cash_ratio      = 1 - invested_ratio
    cash_usd        = round(total_usd * cash_ratio, 0)
    cash_twd        = round(total_twd * cash_ratio, 0)

    # 每次加碼上限
    single_add_usd  = round(total_usd * config.MAX_SINGLE_ADD_PCT, 0)
    single_add_twd  = round(total_twd * config.MAX_SINGLE_ADD_PCT, 0)

    # 剩餘可加碼次數
    add_times_left  = int(cash_usd / single_add_usd) if single_add_usd > 0 else 0

    # ── 持倉損益（有成本價的標的）────────────────────────────
    pnl = {}
    for ticker, cost in cost_basis_adjusted.items():
        stock = stocks.get(ticker, {})
        price = stock.get("price")
        if price and cost:
            pnl_pct  = round((price / cost - 1) * 100, 2)
            pnl[ticker] = {
                "cost":     cost,
                "price":    price,
                "pnl_pct":  pnl_pct,
                "pnl_icon": "+" if pnl_pct >= 0 else "-",
                "split_note": split_notes.get(ticker, ""),
            }

    # ── 財報距今天數 ───────────────────────────────────────
    from datetime import datetime
    import pytz
    TW_TZ = pytz.timezone("Asia/Taipei")
    today = datetime.now(TW_TZ).date()

    earnings_countdown = {}
    for ticker in config.PORTFOLIO["value_stocks"] + config.PORTFOLIO["swing"]:
        stock = stocks.get(ticker, {})
        ed = stock.get("next_earnings_date")
        if ed:
            try:
                earnings_date = datetime.strptime(ed[:10], "%Y-%m-%d").date()
                days_to = (earnings_date - today).days
                if 0 <= days_to <= 60:
                    earnings_countdown[ticker] = {
                        "date": ed[:10],
                        "days": days_to,
                        "urgency": "red" if days_to <= 7 else ("yellow" if days_to <= 21 else "normal"),
                    }
            except Exception:
                pass

    return {
        "date":               raw_data.get("date"),
        "total_capital_twd":  total_twd,
        "total_capital_usd":  round(total_usd, 0),
        "cash_available_usd": cash_usd,
        "cash_available_twd": cash_twd,
        "cash_ratio":         f"{cash_ratio*100:.0f}%",
        "single_add_usd":     single_add_usd,
        "single_add_twd":     single_add_twd,
        "add_times_left":     add_times_left,
        "concentration": {
            "tickers":    concentration_tickers,
            "ratio":      f"{concentration_ratio*100:.0f}%",
            "alert":      concentration_alert,
            "alert_msg":  f"集中度 {concentration_ratio*100:.0f}% > {concentration_threshold*100:.0f}% 警示" if concentration_alert else "集中度正常",
            "pct_each":   conc_pct,
        },
        "scenario_loss_20pct": {
            "total_usd":  total_loss_20pct_usd,
            "total_twd":  total_loss_20pct_twd,
            "by_stock":   scenario_loss,
        },
        "pnl":                pnl,
        "cost_adjusted":      cost_basis_adjusted,
        "split_notes":        split_notes,
        "earnings_countdown": earnings_countdown,
    }


def print_position_summary(pm: dict):
    """印出部位風險摘要"""
    print("\n" + "="*60)
    print("  TRINITY 部位風險報告")
    print("="*60)

    print(f"\n[總資金]")
    print(f"  台幣：NT${pm['total_capital_twd']:,}")
    print(f"  美元：${pm['total_capital_usd']:,}")

    print(f"\n[可用子彈]")
    print(f"  現金：${pm['cash_available_usd']:,} (NT${pm['cash_available_twd']:,})  {pm['cash_ratio']}")
    print(f"  每次加碼上限：${pm['single_add_usd']:,} (NT${pm['single_add_twd']:,})")
    print(f"  剩餘可加碼次數：{pm['add_times_left']}次")

    conc = pm["concentration"]
    alert_mark = " [!!! 警告]" if conc["alert"] else " [正常]"
    print(f"\n[集中度警示]{alert_mark}")
    print(f"  {'+'.join(conc['tickers'])} 估計佔比：{conc['ratio']}")
    print(f"  {conc['alert_msg']}")

    print(f"\n[若跌20%損失估計]")
    print(f"  組合整體損失：${pm['scenario_loss_20pct']['total_usd']:,} (NT${pm['scenario_loss_20pct']['total_twd']:,})")

    print(f"\n[持倉損益]")
    for ticker, p in pm["pnl"].items():
        note = f"  ({p['split_note']})" if p["split_note"] else ""
        print(f"  {ticker:<8} 成本${p['cost']}  現價${p['price']}  損益{p['pnl_pct']:+.1f}%{note}")

    if pm["split_notes"]:
        print(f"\n[注意] 自動偵測到股票分割調整：")
        for t, n in pm["split_notes"].items():
            print(f"  {t}: {n}")

    print(f"\n[即將財報（60日內）]")
    if pm["earnings_countdown"]:
        for ticker, ec in pm["earnings_countdown"].items():
            urgency = "[急!]" if ec["urgency"] == "red" else ("[注意]" if ec["urgency"] == "yellow" else "")
            print(f"  {ticker:<8} {ec['date']}  距今{ec['days']}天 {urgency}")
    else:
        print("  無60日內財報")

    print("\n" + "="*60)


# ── 執行入口 ────────────────────────────────────────────────
if __name__ == "__main__":
    cache_path = os.path.join(config.DATA_DIR, "raw_data_cache.json")
    if not os.path.exists(cache_path):
        print("請先執行 fetch_data.py")
        sys.exit(1)

    with open(cache_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    pm = calc_position_risk(raw_data)
    print_position_summary(pm)

    pm_path = os.path.join(config.DATA_DIR, "position_cache.json")
    with open(pm_path, "w", encoding="utf-8") as f:
        json.dump(pm, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n部位資料已儲存至：{pm_path}")
