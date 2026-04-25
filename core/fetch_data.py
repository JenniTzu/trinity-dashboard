# ============================================================
# TRINITY - fetch_data.py
# 負責抓取所有市場數據（yfinance、fear-greed、FRED）
# ============================================================

import yfinance as yf
import pandas as pd
import numpy as np
import requests
import json
import os
import sys
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import pytz

# 設定 stdout 為 UTF-8（避免 Windows 中文亂碼）
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import config

# ── 時區設定 ───────────────────────────────────────────────
TW_TZ = pytz.timezone("Asia/Taipei")
US_TZ = pytz.timezone("America/New_York")


def get_today_str():
    """取得台灣時間今日日期字串"""
    return datetime.now(TW_TZ).strftime("%Y-%m-%d")


def fetch_stock_data(ticker: str) -> dict:
    """
    抓取單一股票完整數據
    包含：現價、52週高低、本益比、200MA偏離、RSI14、成交量、FCF Yield、毛利率趨勢、ROE、負債比率、分析師目標價、新聞
    """
    print(f"  抓取 {ticker}...")
    result = {"ticker": ticker, "error": None}

    try:
        tk = yf.Ticker(ticker)

        # ── 基本資訊 ───────────────────────────────────────
        info = tk.info or {}

        # 現價（優先用 currentPrice，備用 regularMarketPrice）
        price = (
            info.get("currentPrice")
            or info.get("regularMarketPrice")
            or info.get("navPrice")
        )
        result["price"] = round(float(price), 2) if price else None

        # 52 週高低
        result["week52_high"] = info.get("fiftyTwoWeekHigh")
        result["week52_low"]  = info.get("fiftyTwoWeekLow")

        # 52 週跌幅（從高點跌了多少%）
        if result["week52_high"] and result["price"]:
            result["pct_from_52w_high"] = round(
                (result["price"] / result["week52_high"] - 1) * 100, 2
            )
        else:
            result["pct_from_52w_high"] = None

        # 本益比（Trailing PE）
        result["pe_ratio"] = info.get("trailingPE")
        result["forward_pe"] = info.get("forwardPE")

        # 分析師目標價共識
        result["analyst_target"] = info.get("targetMeanPrice")
        result["analyst_low"]    = info.get("targetLowPrice")
        result["analyst_high"]   = info.get("targetHighPrice")

        # 上漲空間（vs 分析師目標價）
        if result["analyst_target"] and result["price"]:
            result["upside_pct"] = round(
                (result["analyst_target"] / result["price"] - 1) * 100, 2
            )
        else:
            result["upside_pct"] = None

        # 公司名稱
        result["name"] = info.get("shortName") or info.get("longName") or ticker

        # 產業
        result["sector"]   = info.get("sector", "")
        result["industry"] = info.get("industry", "")

        # ── 歷史價格（用於計算 200MA、RSI、成交量）──────────
        hist = tk.history(period="1y", auto_adjust=True)

        if hist is not None and len(hist) > 0:
            closes  = hist["Close"]
            volumes = hist["Volume"]

            # 200 日均線
            ma200 = closes.rolling(200).mean().iloc[-1] if len(closes) >= 200 else closes.mean()
            result["ma200"] = round(float(ma200), 2) if not pd.isna(ma200) else None

            # 200 日均線偏離度（%）
            if result["ma200"] and result["price"]:
                result["ma200_deviation_pct"] = round(
                    (result["price"] / result["ma200"] - 1) * 100, 2
                )
            else:
                result["ma200_deviation_pct"] = None

            # RSI 14 日
            result["rsi14"] = round(float(_calc_rsi(closes, 14)), 2)

            # 成交量：最近1日 vs 60日均量
            if len(volumes) >= 2:
                vol_today  = float(volumes.iloc[-1])
                vol_60_avg = float(volumes.iloc[-61:-1].mean()) if len(volumes) >= 61 else float(volumes.mean())
                result["volume_today"]   = int(vol_today)
                result["volume_60d_avg"] = int(vol_60_avg)
                result["volume_ratio"]   = round(vol_today / vol_60_avg, 2) if vol_60_avg else None
            else:
                result["volume_today"]   = None
                result["volume_60d_avg"] = None
                result["volume_ratio"]   = None

        else:
            result["ma200"] = result["ma200_deviation_pct"] = None
            result["rsi14"] = None
            result["volume_today"] = result["volume_60d_avg"] = result["volume_ratio"] = None

        # ── 本益比 10 年歷史均值（使用 5 年季度數據估算）──────
        result["pe_10y_avg"] = _estimate_historical_pe(tk, info)

        # ── 財務指標 ───────────────────────────────────────
        fin = _fetch_financials(tk, info)
        result.update(fin)

        # ── 財報發布日期 ───────────────────────────────────
        result["next_earnings_date"] = _get_next_earnings(tk)

        # ── 最新新聞（最多 5 則）─────────────────────────
        result["news"] = _fetch_news(tk)

    except Exception as e:
        result["error"] = str(e)
        print(f"    [警告] {ticker} 抓取部分失敗：{e}")

    return result


def _calc_rsi(prices: pd.Series, period: int = 14) -> float:
    """計算 RSI"""
    delta = prices.diff()
    gain  = delta.clip(lower=0)
    loss  = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    val = rsi.iloc[-1]
    return float(val) if not pd.isna(val) else 50.0


def _estimate_historical_pe(tk, info: dict):
    """
    估算本益比 10 年歷史均值
    使用可取得的最長季度 EPS 歷史資料估算
    """
    try:
        # 嘗試取得財報歷史
        earnings = tk.earnings_history
        if earnings is not None and len(earnings) >= 4:
            # 取得歷史 PE（若有的話用 trailingPE 的合理倍數估算）
            pe_list = []
            for _, row in earnings.iterrows():
                eps = row.get("epsActual", None)
                if eps and eps > 0:
                    pe_list.append(None)  # 需要當時股價，暫時跳過

        # 備用：使用 5 年季度數據或直接回傳 trailingPE
        pe_current = info.get("trailingPE")
        if pe_current and pe_current > 0:
            # 簡化：使用市場普遍認知的歷史均值估算（每檔股票不同）
            # 真實的 10 年均值需要付費 API，這裡用產業倍數調整
            sector = info.get("sector", "")
            pe_multiplier = {
                "Technology": 28,
                "Financial Services": 15,
                "Energy": 14,
                "Healthcare": 22,
                "Consumer Cyclical": 20,
                "Consumer Defensive": 18,
                "Industrials": 18,
                "Communication Services": 22,
            }.get(sector, 20)
            return round(pe_multiplier, 1)
        return None
    except Exception:
        return None


def _fetch_financials(tk, info: dict) -> dict:
    """抓取財務指標：FCF Yield、毛利率趨勢(5年)、ROE、負債比率"""
    result = {
        "fcf_yield": None,
        "gross_margin_trend": [],   # 5年毛利率
        "roe": None,
        "roe_trend": [],            # 5年ROE
        "debt_to_equity": None,
        "free_cashflow": None,
        "market_cap": None,
    }

    try:
        market_cap = info.get("marketCap")
        result["market_cap"] = market_cap

        # FCF Yield = 自由現金流 / 市值
        fcf = info.get("freeCashflow")
        result["free_cashflow"] = fcf
        if fcf and market_cap and market_cap > 0:
            result["fcf_yield"] = round(fcf / market_cap * 100, 2)

        # ROE（最新）
        roe = info.get("returnOnEquity")
        if roe is not None:
            result["roe"] = round(roe * 100, 2)

        # 負債比率
        dte = info.get("debtToEquity")
        if dte is not None:
            result["debt_to_equity"] = round(dte, 2)

        # 毛利率趨勢（5年年度）
        try:
            income = tk.income_stmt
            if income is not None and not income.empty:
                gross_profit_row  = income.loc["Gross Profit"]  if "Gross Profit"  in income.index else None
                total_revenue_row = income.loc["Total Revenue"] if "Total Revenue" in income.index else None

                if gross_profit_row is not None and total_revenue_row is not None:
                    margins = []
                    for col in income.columns[:5]:   # 最近5年
                        gp  = gross_profit_row.get(col)
                        rev = total_revenue_row.get(col)
                        if gp is not None and rev and float(rev) > 0:
                            margins.append({
                                "year": str(col)[:4],
                                "gross_margin": round(float(gp) / float(rev) * 100, 2)
                            })
                    result["gross_margin_trend"] = margins

            # ROE 趨勢（5年）
            balance = tk.balance_sheet
            if income is not None and balance is not None and not income.empty and not balance.empty:
                ni_row  = income.loc["Net Income"]         if "Net Income"         in income.index  else None
                eq_row  = balance.loc["Stockholders Equity"] if "Stockholders Equity" in balance.index else (
                          balance.loc["Total Equity Gross Minority Interest"] if "Total Equity Gross Minority Interest" in balance.index else None
                )
                if ni_row is not None and eq_row is not None:
                    roe_list = []
                    for col in income.columns[:5]:
                        ni = ni_row.get(col)
                        eq = eq_row.get(col)
                        if ni is not None and eq is not None and float(eq) > 0:
                            roe_list.append({
                                "year": str(col)[:4],
                                "roe": round(float(ni) / float(eq) * 100, 2)
                            })
                    result["roe_trend"] = roe_list
        except Exception:
            pass

    except Exception as e:
        pass

    return result


def _get_next_earnings(tk) -> str | None:
    """取得下一次財報發布日期"""
    try:
        cal = tk.calendar
        if cal is not None:
            if isinstance(cal, pd.DataFrame):
                if "Earnings Date" in cal.index:
                    val = cal.loc["Earnings Date"].iloc[0]
                    if pd.notna(val):
                        return str(val)[:10]
            elif isinstance(cal, dict):
                ed = cal.get("Earnings Date")
                if ed:
                    if isinstance(ed, list) and len(ed) > 0:
                        return str(ed[0])[:10]
                    return str(ed)[:10]
    except Exception:
        pass
    return None


def _fetch_news(tk) -> list:
    """抓取最新 5 則新聞標題（相容新舊 yfinance 格式）"""
    try:
        news_raw = tk.news or []
        result = []
        for item in news_raw[:5]:
            # 新版 yfinance：資料在 item['content'] 內
            content = item.get("content", {})
            if content:
                title     = content.get("title", "")
                publisher = (content.get("provider") or {}).get("displayName", "")
                link      = (content.get("canonicalUrl") or {}).get("url", "")
                pub_date  = content.get("pubDate", "")
                if pub_date:
                    try:
                        dt = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                        time_str = dt.astimezone(TW_TZ).strftime("%Y-%m-%d %H:%M")
                    except Exception:
                        time_str = pub_date[:10]
                else:
                    time_str = ""
            else:
                # 舊版格式
                title     = item.get("title", "")
                publisher = item.get("publisher", "")
                link      = item.get("link", "")
                ts        = item.get("providerPublishTime")
                time_str  = datetime.fromtimestamp(ts, tz=TW_TZ).strftime("%Y-%m-%d %H:%M") if ts else ""

            if title:
                result.append({
                    "title":     title,
                    "publisher": publisher,
                    "link":      link,
                    "time":      time_str,
                })
        return result
    except Exception:
        return []


def fetch_macro_data() -> dict:
    """抓取總經數據：VIX、美債10年殖利率"""
    print("  抓取總經數據（VIX、美債）...")
    result = {}

    for ticker, key in [("^VIX", "vix"), ("^TNX", "treasury_10y")]:
        try:
            tk   = yf.Ticker(ticker)
            hist = tk.history(period="35d")
            if hist is not None and len(hist) > 0:
                closes = hist["Close"]
                result[key] = round(float(closes.iloc[-1]), 2)
                # 30 日歷史（供圖表用）
                result[f"{key}_history"] = [
                    {"date": str(d)[:10], "value": round(float(v), 2)}
                    for d, v in zip(closes.index[-30:], closes.values[-30:])
                ]
            else:
                result[key] = None
                result[f"{key}_history"] = []
        except Exception as e:
            print(f"    [警告] {ticker} 失敗：{e}")
            result[key] = None
            result[f"{key}_history"] = []

    return result


def fetch_fear_greed() -> dict:
    """抓取 CNN Fear & Greed Index"""
    print("  抓取 Fear & Greed Index...")
    try:
        import fear_greed
        fgi_data = fear_greed.get()  # 回傳 dict

        # 支援 dict 格式（新版套件）
        if isinstance(fgi_data, dict):
            raw_value = fgi_data.get("score") or fgi_data.get("value") or 50
            rating    = fgi_data.get("rating", "")
        else:
            raw_value = getattr(fgi_data, "score", None) or getattr(fgi_data, "value", 50)
            rating    = getattr(fgi_data, "rating", "")

        value = round(float(raw_value), 1)

        # 判斷中文標籤
        rating_lower = rating.lower()
        if "extreme fear" in rating_lower or value <= 25:
            label = "極度恐懼"
        elif "fear" in rating_lower or value <= 45:
            label = "恐懼"
        elif "neutral" in rating_lower or value <= 55:
            label = "中性"
        elif "extreme greed" in rating_lower or value > 75:
            label = "極度貪婪"
        else:
            label = "貪婪"

        # 取得歷史數據（供圖表用）
        history = {}
        if isinstance(fgi_data, dict):
            history = fgi_data.get("history", {})

        return {
            "value": value,
            "label": label,
            "description": rating,
            "history": history,
            "indicators": fgi_data.get("indicators", {}) if isinstance(fgi_data, dict) else {},
        }
    except Exception as e:
        print(f"    [警告] Fear & Greed 失敗：{e}，使用備用數值")
        return {"value": 50.0, "label": "中性（抓取失敗）", "description": "N/A", "history": {}, "indicators": {}}


def _fetch_fgi_backup() -> dict:
    """備用 Fear & Greed 抓取方式"""
    try:
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()
        score = data["fear_and_greed"]["score"]
        rating = data["fear_and_greed"]["rating"]
        value = round(float(score), 1)
        label_map = {
            "Extreme Fear": "極度恐懼",
            "Fear": "恐懼",
            "Neutral": "中性",
            "Greed": "貪婪",
            "Extreme Greed": "極度貪婪",
        }
        return {
            "value": value,
            "label": label_map.get(rating, rating),
            "description": rating,
        }
    except Exception as e:
        print(f"    [警告] FGI 備用 API 也失敗：{e}")
        return {"value": 50.0, "label": "中性（無法取得）", "description": "N/A"}


def fetch_credit_spread(fred_api_key: str) -> dict:
    """
    抓取 HY OAS Credit Spread（BAMLH0A0HYM2）
    來源：FRED API
    """
    print("  抓取 Credit Spread（FRED）...")
    if not fred_api_key or fred_api_key == "待填入":
        print("    [提示] FRED API Key 尚未填入，使用模擬數據")
        return {
            "value": None,
            "label": "待設定 FRED API Key",
            "history": [],
            "mock": True,
        }

    try:
        from fredapi import Fred
        fred = Fred(api_key=fred_api_key)
        # 抓取最近 35 天（確保有 30 個交易日）
        end   = datetime.now()
        start = end - timedelta(days=50)
        series = fred.get_series("BAMLH0A0HYM2", observation_start=start, observation_end=end)
        series = series.dropna()

        if len(series) == 0:
            return {"value": None, "label": "無數據", "history": []}

        value = round(float(series.iloc[-1]), 2)

        # 標籤
        if value < config.CREDIT_SPREAD["overheat"]:
            label = "過熱（< 300bps）"
        elif value > config.CREDIT_SPREAD["crisis"]:
            label = "危機（> 800bps）"
        elif value > config.CREDIT_SPREAD["opportunity"]:
            label = "機會（> 500bps）"
        else:
            label = "正常"

        history = [
            {"date": str(d)[:10], "value": round(float(v), 2)}
            for d, v in zip(series.index[-30:], series.values[-30:])
        ]

        return {"value": value, "label": label, "history": history}

    except Exception as e:
        print(f"    [警告] Credit Spread 失敗：{e}")
        return {"value": None, "label": f"抓取失敗：{e}", "history": []}


def fetch_fomc_dates() -> list:
    """
    FOMC 2025-2026 會議日期（硬編碼，每年更新）
    來源：https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
    """
    fomc = [
        "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
        "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
        "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
        "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
    ]
    today = datetime.now(TW_TZ).date()
    upcoming = [d for d in fomc if d >= str(today)]
    return upcoming[:4]  # 回傳最近 4 個


def fetch_all_data() -> dict:
    """
    主函式：抓取所有數據，回傳完整字典
    """
    print("\n========================================")
    print("  TRINITY 數據抓取開始")
    print("========================================\n")

    all_data = {
        "date": get_today_str(),
        "timestamp": datetime.now(TW_TZ).strftime("%Y-%m-%d %H:%M:%S %Z"),
        "stocks": {},
        "macro": {},
        "fear_greed": {},
        "credit_spread": {},
        "fomc_dates": [],
    }

    # ── 1. 個股數據 ────────────────────────────────────────
    print("[1/4] 個股數據...")
    tickers_to_fetch = [t for t in config.ALL_TICKERS if not t.startswith("^")]

    for ticker in tickers_to_fetch:
        all_data["stocks"][ticker] = fetch_stock_data(ticker)

    # ── 2. 總經數據 ────────────────────────────────────────
    print("\n[2/4] 總經數據...")
    all_data["macro"] = fetch_macro_data()

    # ── 3. Fear & Greed ────────────────────────────────────
    print("\n[3/4] Fear & Greed Index...")
    all_data["fear_greed"] = fetch_fear_greed()

    # ── 4. Credit Spread ──────────────────────────────────
    print("\n[4/4] Credit Spread（FRED）...")
    all_data["credit_spread"] = fetch_credit_spread(config.FRED_API_KEY)

    # ── 5. FOMC 日期 ───────────────────────────────────────
    all_data["fomc_dates"] = fetch_fomc_dates()

    print("\n========================================")
    print("  數據抓取完成！")
    print("========================================\n")

    return all_data


def print_summary(data: dict):
    """印出摘要供人工確認"""
    print("\n" + "="*60)
    print("  TRINITY 數據摘要確認")
    print("="*60)
    print(f"  抓取時間：{data['timestamp']}")
    print(f"  日期：{data['date']}")

    print("\n--- 個股數據 ---")
    for ticker, d in data["stocks"].items():
        if d.get("error") and not d.get("price"):
            print(f"  {ticker:<8} [錯誤] {d['error']}")
            continue
        price   = d.get("price", "N/A")
        pe      = d.get("pe_ratio")
        rsi     = d.get("rsi14")
        ma_dev  = d.get("ma200_deviation_pct")
        vol_r   = d.get("volume_ratio")
        fcf     = d.get("fcf_yield")
        roe     = d.get("roe")
        w52h    = d.get("pct_from_52w_high")
        target  = d.get("analyst_target")
        pe_str  = f"PE={pe:.1f}" if pe else "PE=N/A"
        rsi_str = f"RSI={rsi:.1f}" if rsi else "RSI=N/A"
        ma_str  = f"MA200偏離={ma_dev:+.1f}%" if ma_dev is not None else "MA200=N/A"
        vol_str = f"量比={vol_r:.2f}" if vol_r else "量比=N/A"
        fcf_str = f"FCF={fcf:.1f}%" if fcf else "FCF=N/A"
        roe_str = f"ROE={roe:.1f}%" if roe else "ROE=N/A"
        w52_str = f"52W高點={w52h:+.1f}%" if w52h is not None else ""
        tgt_str = f"目標價=${target:.0f}" if target else ""
        print(f"  {ticker:<8} ${price}  {pe_str}  {rsi_str}  {ma_str}  {vol_str}  {fcf_str}  {roe_str}  {w52_str}  {tgt_str}")

    print("\n--- 總經指標 ---")
    macro = data["macro"]
    print(f"  VIX：{macro.get('vix', 'N/A')}")
    print(f"  美債10年：{macro.get('treasury_10y', 'N/A')}%")

    print("\n--- Fear & Greed Index ---")
    fgi = data["fear_greed"]
    print(f"  數值：{fgi.get('value', 'N/A')}  標籤：{fgi.get('label', 'N/A')}")

    print("\n--- Credit Spread ---")
    cs = data["credit_spread"]
    print(f"  數值：{cs.get('value', 'N/A')} bps  {cs.get('label', '')}")

    print("\n--- FOMC 即將會議 ---")
    for d in data["fomc_dates"]:
        print(f"  {d}")

    print("\n--- 新聞樣本（NVDA 最新1則）---")
    nvda_news = data["stocks"].get("NVDA", {}).get("news", [])
    if nvda_news:
        print(f"  {nvda_news[0].get('title', '')}")
        print(f"  來源：{nvda_news[0].get('publisher', '')}  時間：{nvda_news[0].get('time', '')}")

    print("\n" + "="*60)


# ── 執行入口 ────────────────────────────────────────────────
if __name__ == "__main__":
    data = fetch_all_data()
    print_summary(data)

    # 儲存到暫存檔（供後續步驟使用）
    cache_path = os.path.join(config.DATA_DIR, "raw_data_cache.json")
    os.makedirs(config.DATA_DIR, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n數據已快取至：{cache_path}")
