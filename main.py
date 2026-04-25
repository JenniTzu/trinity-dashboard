# ============================================================
# TRINITY - main.py
# 主執行入口：每天凌晨5點由 Windows 工作排程器呼叫
# ============================================================

import sys
import os
import logging
from datetime import datetime
import pytz

if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import config

# ── 設定 log 檔 ─────────────────────────────────────────
os.makedirs(config.LOGS_DIR, exist_ok=True)
log_file = os.path.join(config.LOGS_DIR, f"trinity_{datetime.now().strftime('%Y%m')}.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)
log = logging.getLogger("TRINITY")

TW_TZ = pytz.timezone("Asia/Taipei")


def is_us_market_holiday() -> bool:
    """簡易美股假日判斷（主要節日）"""
    today = datetime.now(TW_TZ).date()
    year  = today.year

    holidays = [
        f"{year}-01-01",  # 元旦
        f"{year}-07-04",  # 國慶日
        f"{year}-12-25",  # 聖誕節
        f"{year}-11-28",  # 感恩節（近似）
        f"{year}-11-29",  # 黑色星期五
    ]

    return str(today) in holidays


def should_run_today() -> bool:
    """判斷今天是否應執行（跳過週末與假日）"""
    today = datetime.now(TW_TZ)
    weekday = today.weekday()  # 0=週一, 6=週日

    if weekday >= 5:  # 週六=5, 週日=6
        log.info(f"今日 {today.strftime('%Y-%m-%d')} 為週末，跳過執行")
        return False

    if is_us_market_holiday():
        log.info(f"今日為美股假日，跳過執行")
        return False

    return True


def run(test_mode: bool = False, use_cache: bool = False, skip_deploy: bool = False):
    """
    主執行函式
    test_mode:   True=測試模式（不推送 GitHub）
    use_cache:   True=使用快取數據（不重新抓取）
    skip_deploy: True=跳過 GitHub 推送
    """
    log.info("=" * 50)
    log.info("  TRINITY 系統啟動")
    log.info(f"  模式：{'測試' if test_mode else '正式'} | 快取：{use_cache} | 跳過部署：{skip_deploy}")
    log.info("=" * 50)

    if not test_mode and not should_run_today():
        log.info("今日不執行，結束")
        return

    try:
        # ── 步驟1：數據抓取 + 計算 + 寫入 data.json ─────
        log.info("[1/2] 執行數據更新流程...")
        from core import update_data
        result = update_data.update_data(use_cache=use_cache)

        # 取得今日共識
        consensus = result.get("latest", {}).get("consensus", {})
        log.info(f"三腦共識：{consensus.get('label')} ({consensus.get('score')}%)")

        # ── 步驟2：部署到 GitHub Pages ─────────────────
        if not test_mode and not skip_deploy:
            log.info("[2/2] 部署到 GitHub Pages...")
            from core import deploy
            deploy.deploy_to_github()
        elif test_mode:
            log.info("[2/2] 測試模式：跳過 GitHub 推送")
        else:
            log.info("[2/2] 已設定跳過部署")

        log.info("TRINITY 執行完成！")

    except Exception as e:
        log.error(f"TRINITY 執行失敗：{e}", exc_info=True)
        sys.exit(1)


# ── 執行入口 ────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="TRINITY 投資監控系統")
    parser.add_argument("--test",       action="store_true", help="測試模式（不推送 GitHub）")
    parser.add_argument("--cache",      action="store_true", help="使用快取數據（不重新抓取）")
    parser.add_argument("--no-deploy",  action="store_true", help="跳過 GitHub 推送")
    args = parser.parse_args()

    run(
        test_mode   = args.test,
        use_cache   = args.cache,
        skip_deploy = args.no_deploy,
    )
