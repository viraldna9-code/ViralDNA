#!/usr/bin/env python3
"""
ViralDNA System Monitor — Single Dashboard
==========================================
Checks EVERY component end-to-end and sends ONE Telegram message.

Called by: Manual run or Hermes cron (daily recommended)
Exit code: 0 = all OK, 1 = issues found
"""
import os, sys, json, subprocess, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from dotenv import load_dotenv

IST = timezone(timedelta(hours=5, minutes=30))
PROJECT_ROOT = Path(__file__).parent
LOGS = PROJECT_ROOT / "logs"

# ── Load credentials ──
load_dotenv(Path.home() / ".env")
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT = os.getenv("TELEGRAM_CHAT_ID", "")

# ── Helpers ──
now = datetime.now(IST)
issues = []  # list of (severity, message)
severity_weight = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}

def add(sev, msg):
    issues.append((sev, msg))

def run_cmd(cmd, timeout=15):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, cwd=str(PROJECT_ROOT))
        return r.stdout.strip(), r.returncode
    except subprocess.TimeoutExpired:
        return "", -1
    except Exception as e:
        return "", -1

# ════════════════════════════════════════════════
# CHECK 1: Topic Discovery (monitor_cloud.py)
# ════════════════════════════════════════════════
tf = LOGS / "topics_history.json"
if not tf.exists():
    add("CRITICAL", "topics_history.json MISSING — monitor_cloud.py never ran")
else:
    with open(tf) as f:
        d = json.load(f)
    topics = d.get("topics", [])
    last_run_str = d.get("last_run", "")
    pub = [t for t in topics if t.get("published")]
    unpub = [t for t in topics if not t.get("published")]
    high_score = [t for t in unpub if t.get("score", 0) >= 20]

    age_min = (now.timestamp() - tf.stat().st_mtime) / 60
    age_h = age_min / 60

    if age_h > 24:
        add("CRITICAL", f"Monitor STALE — last run {age_h:.0f}h ago ({last_run_str[:16]})")
    elif age_h > 2:
        add("WARNING", f"Monitor delayed — last run {age_h:.1f}h ago")
    # else OK

    if len(topics) == 0:
        add("WARNING", "0 topics discovered — all sources may be down")

    if len(high_score) == 0:
        add("INFO", "No high-score topics (20+) available for production")

# ════════════════════════════════════════════════
# CHECK 2: Production Activity (daily_log.json)
# ════════════════════════════════════════════════
dl = LOGS / "daily_log.json"
today = now.strftime("%Y-%m-%d")
if not dl.exists():
    add("WARNING", "daily_log.json MISSING — no production run today")
else:
    with open(dl) as f:
        d = json.load(f)
    dl_date = d.get("date", "")
    main_done = d.get("main_done", False)
    shorts_done = d.get("shorts_done", 0)
    used = d.get("used_titles", [])

    if dl_date != today:
        add("WARNING", f"Daily log is from {dl_date}, not today ({today})")
    else:
        if not main_done:
            add("INFO", f"Main video not done yet today ({today})")
        if shorts_done < 2:
            add("INFO", f"Shorts: {shorts_done}/2 done today")

# ════════════════════════════════════════════════
# CHECK 3: Google Drive Output (best effort — skip if rclone hangs)
# ════════════════════════════════════════════════
# NOTE: rclone may hang if Google token expired. Run `rclone config reconnect gdrive:`
#       if Drive checks consistently timeout.
drive_ok = False
try:
    r = subprocess.run(
        ["timeout", "15", "rclone", "lsf", "gdrive:ViralDNA_Review/", "--max-depth", "1"],
        capture_output=True, text=True, timeout=20
    )
    if r.returncode == 0:
        folders = [l.strip() for l in r.stdout.strip().split('\n') if l.strip()]
        today_folders = [f for f in folders if today.replace("-", "") in f]
        if len(today_folders) == 0:
            add("WARNING", f"No Drive folder for today ({today}) — pipeline may not have run")
        drive_ok = True
    else:
        add("WARNING", f"rclone failed: {r.stderr[:60]}")
except subprocess.TimeoutExpired:
    add("WARNING", "rclone timed out — Google token may need reconnect (rclone config reconnect gdrive:)")
except Exception as e:
    add("WARNING", f"rclone error: {e}")

# ════════════════════════════════════════════════
# CHECK 4: Hermes Cron Jobs (are they running?)
# ════════════════════════════════════════════════
try:
    r = subprocess.run(["hermes", "cron", "list"], capture_output=True, text=True, timeout=10)
    cron_output = r.stdout
    # Count active jobs
    active_count = cron_output.count("[active]")
    if active_count < 5:
        add("WARNING", f"Only {active_count}/5 Hermes cron jobs active")
    # Check for actual error status lines
    for line in cron_output.split('\n'):
        if "error:" in line.lower() and "last run:" in line.lower():
            add("WARNING", f"Cron job had error: {line.strip()}")
except Exception as e:
    add("INFO", f"Could not check Hermes crons: {e}")

# ════════════════════════════════════════════════
# CHECK 5: GitHub Actions Monitor
# ════════════════════════════════════════════════
wf_file = PROJECT_ROOT / ".github" / "workflows" / "spike-monitor.yml"
if not wf_file.exists():
    add("CRITICAL", "spike-monitor.yml MISSING — GitHub Actions monitor disabled")
else:
    age_d = (now.timestamp() - wf_file.stat().st_mtime) / 86400
    if age_d > 30:
        add("INFO", f"spike-monitor.yml not updated in {age_d:.0f} days")

# ════════════════════════════════════════════════
# CHECK 6: Credential Health
# ════════════════════════════════════════════════
required_creds = ["GEMINI_API_KEY", "SERPER_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]
missing_creds = []
for k in required_creds:
    if not os.getenv(k):
        missing_creds.append(k)

yt_token = PROJECT_ROOT / "credentials" / "youtube_token.json"
if not yt_token.exists():
    missing_creds.append("youtube_token.json")

if missing_creds:
    add("CRITICAL", f"Missing credentials: {', '.join(missing_creds)}")

# ════════════════════════════════════════════════
# CHECK 7: Pipeline Entry Points Integrity
# ════════════════════════════════════════════════
entry_points = {
    "monitor_cloud.py": "Topic discovery & scoring",
    "execute_topic.py": "Manual topic execution",
    "run_pipeline_entrypoint.py": "Pipeline runner",
    "channel_health.py": "YouTube health checks",
}
missing_ep = []
for ep, desc in entry_points.items():
    if not (PROJECT_ROOT / ep).exists():
        missing_ep.append(f"{ep} ({desc})")
if missing_ep:
    add("CRITICAL", f"Missing entry points: {', '.join(missing_ep)}")

# ════════════════════════════════════════════════
# CHECK 8: Stale Cron Delivery (output/runtime age)
# ════════════════════════════════════════════════
rd = PROJECT_ROOT / "output" / "runtime"
if rd.exists():
    stale_files = []
    for f in rd.glob("*.json"):
        age_h = (now.timestamp() - f.stat().st_mtime) / 3600
        if age_h > 48:
            stale_files.append(f.name)
    if stale_files:
        add("INFO", f"Stale runtime files (>48h): {', '.join(stale_files)}")

# ════════════════════════════════════════════════
# CHECK 9: topic_usage_today.json (dedup tracking)
# ════════════════════════════════================================
usage_file = LOGS / "topic_usage_today.json"
if usage_file.exists():
    with open(usage_file) as f:
        d = json.load(f)
    usage_date = d.get("date", "")
    if usage_date != today:
        add("INFO", f"topic_usage_today.json is from {usage_date}, not today")

# ════════════════════════════════════════════════
# COMPILE REPORT
# ════════════════════════════════================================
# Sort by severity
issues.sort(key=lambda x: severity_weight.get(x[0], 99))

critical = [i for s, i in issues if s == "CRITICAL"]
warnings = [i for s, i in issues if s == "WARNING"]
infos = [i for s, i in issues if s == "INFO"]

# Determine overall status
if critical:
    overall = "🔴 CRITICAL"
    exit_code = 1
elif warnings:
    overall = "🟡 WARNINGS"
    exit_code = 1
elif infos:
    overall = "🟢 OK (with notes)"
    exit_code = 0
else:
    overall = "🟢 ALL OK"
    exit_code = 0

# ── Load additional stats for the report ──
topics = pub = unpub = []
try:
    with open(tf) as f:
        d = json.load(f)
    topics_local = d.get("topics", [])
    pub = [t for t in topics_local if t.get("published")]
    unpub = [t for t in topics_local if not t.get("published")]
    topics = topics_local
    top_unpub = sorted(unpub, key=lambda x: x.get("score",0), reverse=True)[:3]
    top_lines = [f"  [{t.get('score'):2d}/30] {t.get('id','?')} — {t.get('title','')[:50]}" for t in top_unpub]
except:
    top_lines = ["  (no topics)"]
    pub, unpub = [], []

# ── Format Telegram message ──
now_str = now.strftime("%Y-%m-%d %H:%M IST")
lines = [
    f"<b>🖥 ViralDNA System Monitor</b>",
    f"<code>{now_str}</code>",
    f"",
    f"<b>Status: {overall}</b>",
    f"",
    f"<b>📊 Topics</b>",
    f"Total: {len(topics)}  |  Published: {len(pub)}  |  Ready: {len(unpub)}",
]
if top_lines:
    lines.append("<b>Top 3 unpublished:</b>")
    lines.extend(top_lines)

lines.append("")
lines.append("<b>🔍 Issues</b>")
if not issues:
    lines.append("  None — all systems nominal")
else:
    for sev, msg in issues:
        icon = {"CRITICAL": "🔴", "WARNING": "🟡", "INFO": "🔵"}.get(sev, "⚪")
        lines.append(f"  {icon} [{sev}] {msg}")

lines.append("")
lines.append("─" * 30)

# Hermes cron summary
lines.append("<b>⏰ Hermes Crons</b>")
lines.append("  viraldna-analytics-daily: midnight")
lines.append("  viraldna-report-daily: midnight")
lines.append("  Daily Analytics Report: 00:30")
lines.append("  Weekly Analytics Report: Sun 00:30")
lines.append("  Channel Health Monitor: every 2h")

text = "\n".join(lines)

# ── Print to stdout ──
print(text)
print(f"\nExit code: {exit_code}")
print(f"Issues: {len(critical)} critical, {len(warnings)} warnings, {len(infos)} info")

# ── Send to Telegram ──
if TOKEN and CHAT:
    try:
        payload = json.dumps({
            "chat_id": CHAT,
            "text": text,
            "parse_mode": "HTML"
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        resp = urllib.request.urlopen(req, timeout=15)
        print(f"Telegram sent: {resp.status}")
    except Exception as e:
        print(f"Telegram failed: {e}")
else:
    print("Telegram skipped: token or chat_id not set")

sys.exit(exit_code)
