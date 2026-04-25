# ============================================================
# TRINITY - deploy.py
# 將 docs/ 資料夾推送到 GitHub Pages
# ============================================================

import subprocess
import os
import sys
import logging

if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import config

log = logging.getLogger("TRINITY.deploy")


def _run(cmd: list, cwd: str = None) -> tuple[int, str, str]:
    """執行命令，回傳 (returncode, stdout, stderr)"""
    result = subprocess.run(
        cmd, cwd=cwd or config.BASE_DIR,
        capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def setup_git_repo():
    """初始化 Git repo 並設定 remote（首次執行）"""
    if config.GITHUB_REPO == "待設定":
        log.error("請先在 config.py 填入 GITHUB_REPO")
        return False

    # 確認是否已初始化
    code, out, err = _run(["git", "rev-parse", "--is-inside-work-tree"])
    if code != 0:
        log.info("初始化 Git repository...")
        _run(["git", "init"])
        _run(["git", "branch", "-M", "main"])

    # 設定 remote
    code, out, err = _run(["git", "remote", "get-url", "origin"])
    if code != 0:
        remote_url = f"https://github.com/{config.GITHUB_REPO}.git"
        if config.GITHUB_TOKEN and config.GITHUB_TOKEN != "待填入":
            # 帶 token 的 URL（自動化用）
            owner, repo = config.GITHUB_REPO.split("/")
            remote_url = f"https://{config.GITHUB_TOKEN}@github.com/{owner}/{repo}.git"
        log.info(f"設定 remote: {config.GITHUB_REPO}")
        _run(["git", "remote", "add", "origin", remote_url])
    else:
        log.info(f"Git remote 已存在")

    # .gitignore
    gitignore_path = os.path.join(config.BASE_DIR, ".gitignore")
    if not os.path.exists(gitignore_path):
        with open(gitignore_path, "w", encoding="utf-8") as f:
            f.write("data/\nlogs/\n__pycache__/\n*.pyc\n.env\n")

    return True


def deploy_to_github():
    """推送最新 docs/data.json 到 GitHub"""
    if config.GITHUB_REPO == "待設定":
        log.warning("GITHUB_REPO 尚未設定，跳過部署")
        return False

    log.info(f"開始部署到 GitHub: {config.GITHUB_REPO}")

    # 設定 git user（CI 用）
    _run(["git", "config", "user.email", "trinity-bot@auto.com"])
    _run(["git", "config", "user.name",  "TRINITY Bot"])

    # 加入變更
    code, out, err = _run(["git", "add", "docs/"])
    if code != 0:
        log.error(f"git add 失敗：{err}")
        return False

    # 檢查是否有變更
    code, out, err = _run(["git", "diff", "--cached", "--quiet"])
    if code == 0:
        log.info("無新變更需要推送")
        return True

    # commit
    from datetime import datetime
    import pytz
    TW_TZ = pytz.timezone("Asia/Taipei")
    now   = datetime.now(TW_TZ).strftime("%Y-%m-%d %H:%M")
    msg   = f"TRINITY auto update {now}"

    code, out, err = _run(["git", "commit", "-m", msg])
    if code != 0:
        log.error(f"git commit 失敗：{err}")
        return False

    # push
    code, out, err = _run(["git", "push", "-u", "origin", "main"])
    if code != 0:
        log.error(f"git push 失敗：{err}")
        log.error(f"  stderr: {err}")
        return False

    log.info(f"部署成功！{config.GITHUB_REPO}")
    return True


def setup_github_pages():
    """
    說明如何在 GitHub 啟用 Pages
    （需手動在 GitHub 網頁上操作）
    """
    print("""
╔══════════════════════════════════════════════════════╗
║           GitHub Pages 設定說明                       ║
╠══════════════════════════════════════════════════════╣
║                                                      ║
║  1. 前往 GitHub.com 登入你的帳號                      ║
║  2. 建立新 Repository（建議命名：trinity-dashboard）  ║
║  3. 將 GITHUB_REPO 填入 config.py                    ║
║     範例：your-username/trinity-dashboard            ║
║                                                      ║
║  4. 在 Repository 設定中：                           ║
║     Settings → Pages → Source                       ║
║     選擇 "Deploy from a branch"                      ║
║     Branch: main / Folder: /docs                    ║
║                                                      ║
║  5. 網站網址：                                        ║
║     https://your-username.github.io/trinity         ║
║                                                      ║
╚══════════════════════════════════════════════════════╝
    """)


def create_windows_scheduler():
    """建立 Windows 工作排程器任務"""
    python_path = sys.executable
    script_path = os.path.join(config.BASE_DIR, "main.py")

    # PowerShell 指令建立排程任務
    task_name = "TRINITY_DailyRun"
    time_str  = f"{config.SCHEDULE_HOUR:02d}:{config.SCHEDULE_MINUTE:02d}"

    ps_script = f'''
$action  = New-ScheduledTaskAction -Execute "{python_path}" -Argument "{script_path}" -WorkingDirectory "{config.BASE_DIR}"
$trigger = New-ScheduledTaskTrigger -Daily -At "{time_str}"
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 1) -RunOnlyIfNetworkAvailable $true
Register-ScheduledTask -TaskName "{task_name}" -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest -Force
Write-Host "TRINITY 排程任務建立成功！每天 {time_str} 自動執行"
'''

    ps_path = os.path.join(config.BASE_DIR, "setup_scheduler.ps1")
    with open(ps_path, "w", encoding="utf-8") as f:
        f.write(ps_script)

    print(f"""
╔══════════════════════════════════════════════════════╗
║         Windows 工作排程器設定說明                    ║
╠══════════════════════════════════════════════════════╣
║                                                      ║
║  已產生設定腳本：setup_scheduler.ps1                  ║
║                                                      ║
║  執行步驟：                                           ║
║  1. 按 Windows 鍵，搜尋「PowerShell」                 ║
║  2. 右鍵 → 以系統管理員身份執行                       ║
║  3. 輸入以下指令：                                    ║
║                                                      ║
║     cd "{config.BASE_DIR}"
║     Set-ExecutionPolicy -Scope Process Bypass        ║
║     .\\setup_scheduler.ps1                           ║
║                                                      ║
║  設定後：每天 {time_str} 自動執行                     ║
║  （週末與假日自動跳過）                                ║
║                                                      ║
╚══════════════════════════════════════════════════════╝
    """)
    return ps_path


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--setup",     action="store_true", help="初始化 Git 並說明 GitHub Pages 設定")
    parser.add_argument("--scheduler", action="store_true", help="建立 Windows 排程器腳本")
    parser.add_argument("--deploy",    action="store_true", help="執行部署")
    args = parser.parse_args()

    if args.setup:
        setup_git_repo()
        setup_github_pages()
    elif args.scheduler:
        create_windows_scheduler()
    elif args.deploy:
        deploy_to_github()
    else:
        print("用法：")
        print("  python deploy.py --setup      # 初始化設定")
        print("  python deploy.py --scheduler  # 建立排程器腳本")
        print("  python deploy.py --deploy     # 立即部署")
