#!/usr/bin/env python3
"""
ViralDNA Daily/Weekly Analytics Report — sends summary to Telegram.
Called by Hermes cron: daily at 6AM IST, weekly on Sunday 6AM IST.
Usage: python3 scripts/daily_report.py [--mode daily|weekly]
"""
import os, sys, json, urllib.request, subprocess, argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

IST = timezone(timedelta(hours=5, minutes=30))
PROJECT_ROOT = Path(__file__).parent.parent  # scripts/ -> ViralDNA/

# ── Args ──
parser = argparse.ArgumentParser()
parser.add_argument("--mode", choices=["daily", "weekly"], default="daily",
                    help="Report mode: daily (today) or weekly (last 7 days)")
args = parser.parse_args()

# Load env
from dotenv import load_dotenv
load_dotenv(Path.home() / ".env")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT = os.getenv("TELEGRAM_CHAT_ID")

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

def run(cmd, timeout=30):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, cwd=PROJECT_ROOT)
        return r.stdout.strip()
    except Exception as e:
        return f"ERR: {e}"

# ── Drive data ──
drive_out = run("rclone lsf gdrive:ViralDNA_Review/ 2>/dev/null | tail -5")
drive_lines = [l for l in drive_out.split("\n") if l.strip()]
drive_folders = run("rclone lsf gdrive:ViralDNA_Review/ 2>/dev/null | wc -l").strip()

# ── Topics data ──
topics_file = PROJECT_ROOT / "logs" / "topics_history.json"
if topics_file.exists():
    with open(topics_file) as f:
        d = json.load(f)
    topics = d.get("topics", [])
    now_ist = datetime.now(IST)

    if args.mode == "weekly":
        # Last 7 days
        week_ago = (now_ist - timedelta(days=7)).strftime("%Y-%m-%d")
        today_str = now_ist.strftime("%Y-%m-%d")
        period_topics = [t for t in topics if week_ago <= t.get("date", "") <= today_str]
        period_label = f"Last 7 days ({week_ago} → {today_str})"
    else:
        # Today only
        today_str = now_ist.strftime("%Y-%m-%d")
        period_topics = [t for t in topics if t.get("date", "") == today_str]
        period_label = today_str

    pub = [t for t in topics if t.get("published")]
    top5 = sorted(topics, key=lambda x: x.get("score", 0), reverse=True)[:5]
    top5_lines = [f'  [{t["score"]:2d}] {t["id"]} {t["title"][:60]}' for t in top5]
    last_run = d.get("last_run", "?")
else:
    topics, period_topics, pub, top5_lines, last_run = [], [], [], [], "no file"
    period_label = "no data"

# ── Channel health ──
health_file = PROJECT_ROOT / "logs" / "channel_health_last_run.txt"
health_data = health_file.read_text().strip() if health_file.exists() else "No record"

# ── Format ──
now_str = datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")
emoji = "📊" if args.mode == "daily" else "📅"
label = "Daily" if args.mode == "daily" else "Weekly"
lines = [
    f"{emoji} <b>ViralDNA {label} Report — {now_str}</b>",
    "",
    f"📈 <b>Topics — {period_label}</b>",
    f"Total: {len(topics)}  |  Period new: {len(period_topics)}  |  Published: {len(pub)}",
    f"Monitor last run: {last_run[:19] if last_run else '?'}",
    "",
    "<b>Top 5 by score:</b>",
] + (top5_lines if top5_lines else ["  (no topics)"]) + [
    "",
    f"📁 <b>Drive Review Folders: {drive_folders}</b>",
] + ([f"  {l}" for l in drive_lines] if drive_lines else ["  (empty)"]) + [
    "",
    "💚 <b>Channel Health</b>",
    f"  {health_data[:200]}",
]

text = "\n".join(lines)

# ── Send Telegram ──
if not TOKEN or not CHAT:
    print("ERROR: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")
    print("Would have sent:\n" + text)
    sys.exit(1)

payload = json.dumps({"chat_id": CHAT, "text": text, "parse_mode": "HTML"}).encode()
req = urllib.request.Request(
    f"https://api.telegram.org/bot{TOKEN}/sendMessage",
    data=payload,
    headers={"Content-Type": "application/json"}
)
try:
    resp = urllib.request.urlopen(req, timeout=15)
    print(f"Telegram sent OK — {resp.status}")
    print(text)
except Exception as e:
    print(f"Telegram FAILED: {e}")
    sys.exit(1)
