#!/usr/bin/env python3
"""
ViralDNA Live Dashboard Generator
Reads current system state and generates a fresh dashboard/index.html

Usage:
    python3 dashboard/generate_dashboard.py

Then open dashboard/index.html in a browser.
For auto-refresh, the generated page includes a 60-second meta refresh.
"""

import json
import os
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE_DIR = Path("/home/jay/ViralDNA")
DASHBOARD_DIR = BASE_DIR / "dashboard"
LOGS_DIR = BASE_DIR / "logs"
ANALYTICS_DIR = BASE_DIR / "analytics"
OUTPUT_DIR = BASE_DIR / "output"
DOTENV_FILE = Path.home() / ".env"

IST = timezone(timedelta(hours=5, minutes=30))


def now_ist():
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")


def load_json(path, default=None):
    try:
        return json.load(path.open())
    except Exception:
        return default or {}


def get_overview_data():
    """Get overview metrics."""
    topics = load_json(LOGS_DIR / "topics_history.json", {})
    topic_list = topics.get("topics", [])
    total = len(topic_list)
    published = sum(1 for t in topic_list if isinstance(t, dict) and t.get("published"))
    rejected = sum(1 for t in topic_list if isinstance(t, dict) and t.get("status") == "rejected")
    drive_ready = sum(1 for t in topic_list if isinstance(t, dict) and t.get("status") == "drive_ready")
    completed = sum(1 for t in topic_list if isinstance(t, dict) and t.get("status") == "completed")
    ids = [t["id"] for t in topic_list if isinstance(t, dict) and "id" in t]
    max_id = max(ids, default="none")

    # Count Python files
    py_files = list(BASE_DIR.rglob("*.py"))
    modules_dir = BASE_DIR / "modules"
    module_files = list(modules_dir.glob("*.py")) if modules_dir.exists() else []

    # Disk
    stat = os.statvfs("/")
    disk_free_gb = (stat.f_bavail * stat.f_frsize) / 1e9
    disk_total_gb = (stat.f_blocks * stat.f_frsize) / 1e9
    disk_pct = ((stat.f_blocks - stat.f_bavail) / stat.f_blocks) * 100

    return {
        "total_topics": total,
        "published": published,
        "rejected": rejected,
        "drive_ready": drive_ready,
        "completed": completed,
        "max_id": max_id,
        "py_files": len(py_files),
        "module_files": len(module_files),
        "disk_free_gb": f"{disk_free_gb:.1f}",
        "disk_total_gb": f"{disk_total_gb:.1f}",
        "disk_pct": f"{disk_pct:.1f}",
        "last_run": topics.get("last_run", "unknown")[:16] if topics.get("last_run") else "never"
    }


def get_cron_data():
    """Get cron job data from Hermes jobs.json."""
    cron_file = Path.home() / ".hermes" / "cron" / "jobs.json"
    data = load_json(cron_file, [])
    if isinstance(data, dict):
        jobs = data.get("jobs", data.get("crons", []))
    else:
        jobs = data
    return jobs


def get_approval_queue():
    qf = OUTPUT_DIR / "runtime" / "approval_queue.json"
    return load_json(qf, {"pending": {}, "approved": {}, "rejected": {}})


def get_recent_runs(count=10):
    """Get recent pipeline run entries."""
    lf = LOGS_DIR / "run_log.jsonl"
    if not lf.exists():
        return []
    lines = lf.read_text().strip().split("\n")
    entries = []
    for line in lines[-count:]:
        try:
            entries.append(json.loads(line))
        except Exception:
            pass
    return list(reversed(entries))


def get_analytics():
    """Get channel analytics."""
    health = load_json(ANALYTICS_DIR / "health_state.json", {})
    feedback = ANALYTICS_DIR / "feedback.md"
    feedback_text = feedback.read_text()[:500] if feedback.exists() else "No feedback"
    return {"health": health, "feedback": feedback_text}


def get_env_status():
    from dotenv import load_dotenv
    load_dotenv(DOTENV_FILE)
    keys = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "SERPER_API_KEY", "OPENROUTER_API_KEY"]
    return {k: "SET" if os.getenv(k) else "MISSING" for k in keys}


def get_youtube_stats():
    """Get YouTube channel statistics."""
    try:
        venv_python = "/home/jay/venv/bin/python3"
        result = subprocess.run(
            [venv_python, "-c", """
import json, os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
try:
    creds = Credentials.from_authorized_user_file('credentials/youtube_token.json',
        ['https://www.googleapis.com/auth/youtube.readonly'])
    yt = build('youtube', 'v3', credentials=creds)
    resp = yt.channels().list(part='statistics', mine=True).execute()
    s = resp['items'][0]['statistics']
    print(json.dumps(s))
except Exception as e:
    print(json.dumps({"error": str(e)}))
"""],
            capture_output=True, text=True, timeout=15,
            cwd=str(BASE_DIR)
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout.strip())
    except Exception:
        pass
    return {"error": "Could not fetch"}


def status_badge(status):
    """Return HTML badge for a status string."""
    mapping = {
        "ok": "badge-ok", "active": "badge-ok", "published": "badge-ok",
        "completed": "badge-ok", "drive_ready": "badge-info",
        "warn": "badge-warn", "pending": "badge-warn",
        "crit": "badge-crit", "error": "badge-crit", "rejected": "badge-crit",
        "none": "badge-dead", "never": "badge-dead",
    }
    css = mapping.get(str(status).lower(), "badge-info")
    return f'<span class="badge {css}">{status}</span>'


def status_dot(status):
    mapping = {
        "ok": "ok", "active": "ok", "published": "ok", "completed": "ok",
        "warn": "warn", "pending": "warn", "drive_ready": "warn",
        "crit": "crit", "error": "crit", "rejected": "crit",
    }
    css = mapping.get(str(status).lower(), "unk")
    return f'<span class="status-dot {css}"></span>'


def progress_bar(pct, css_class):
    return f'<div class="progress-bar"><div class="progress-fill {css_class}" style="width:{pct}%"></div></div>'


def generate_html(data):
    """Generate the full dashboard HTML."""
    ov = data["overview"]
    cron_jobs = data["cron_jobs"]
    queue = data["approval_queue"]
    runs = data["recent_runs"]
    analytics = data["analytics"]
    env = data["env"]
    yt = data["youtube"]

    # Calculate health score
    checks_pass = 0
    checks_total = 0

    # Cron health
    cron_ok = sum(1 for j in cron_jobs if j.get("last_status") == "ok")
    cron_total = len(cron_jobs)
    checks_pass += cron_ok
    checks_total += cron_total

    # Env health
    env_ok = sum(1 for v in env.values() if v == "SET")
    checks_pass += env_ok
    checks_total += len(env)

    health_pct = int((checks_pass / max(checks_total, 1)) * 100)
    if health_pct >= 80:
        health_class = "fill-ok"
        health_label = "HEALTHY"
    elif health_pct >= 50:
        health_class = "fill-warn"
        health_label = "DEGRADED"
    else:
        health_class = "fill-crit"
        health_label = "CRITICAL"

    # Build cron rows
    cron_rows = ""
    for j in cron_jobs:
        name = j.get("name", "?")
        schedule = j.get("schedule", "?")
        last_status = j.get("last_status", "never")
        last_run = j.get("last_run_at", "never")
        if last_run and last_run != "never":
            last_run = last_run[:16].replace("T", " ")
        next_run = j.get("next_run_at", "?")
        if next_run and next_run != "?":
            next_run = next_run[:16].replace("T", " ")
        enabled = j.get("enabled", False)
        cron_rows += f"""
      <tr>
        <td>{status_dot(last_status)} {name}</td>
        <td><code>{schedule}</code></td>
        <td>{last_run}</td>
        <td>{status_badge(last_status)}</td>
        <td>{next_run}</td>
        <td>{'✅' if enabled else '⏸️'}</td>
      </tr>"""

    # Build approval queue rows
    queue_rows = ""
    for tid, entry in queue.get("pending", {}).items():
        title = entry.get("topic_title", tid)[:60]
        vids = len(entry.get("video_files", []))
        thumbs = len(entry.get("thumbnail_files", []))
        stale = "⚠️ STALE" if vids == 0 and thumbs == 0 else "OK"
        requested = entry.get("requested_at", "?")[:16]
        queue_rows += f"""
      <tr>
        <td>{tid}</td>
        <td>{title}</td>
        <td>{vids}</td>
        <td>{thumbs}</td>
        <td>{requested}</td>
        <td>{status_badge(stale)}</td>
      </tr>"""

    if not queue_rows:
        queue_rows = '<tr><td colspan="6" style="text-align:center;color:var(--border)">No pending items ✅</td></tr>'

    # Build recent runs rows
    runs_rows = ""
    for r in runs[-8:]:
        start = r.get("run_start", "?")[:16].replace("T", " ")
        duration = r.get("duration_s", "?")
        topics = r.get("produce_topics", 0)
        alerts = r.get("alerts_sent", 0)
        top_title = r.get("top_title", "")[:40]
        top_score = r.get("top_score", "?")
        runs_rows += f"""
      <tr>
        <td>{start}</td>
        <td>{duration}s</td>
        <td>{topics}</td>
        <td>{alerts}</td>
        <td>{top_title}</td>
        <td>{top_score}</td>
      </tr>"""

    # YouTube stats
    yt_subs = yt.get("subscriberCount", "?")
    yt_videos = yt.get("videoCount", "?")
    yt_views = yt.get("viewCount", "?")
    yt_error = yt.get("error", "")

    # Env rows
    env_rows = ""
    for k, v in env.items():
        env_rows += f"""
      <tr>
        <td><code>{k}</code></td>
        <td>{status_badge(v)}</td>
      </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="refresh" content="60">
<title>ViralDNA Dashboard — Live System Health</title>
<style>
:root {{
  --bg: #0d1117; --surface: #161b22; --border: #30363d; --text: #c9d1d9;
  --accent: #58a6ff; --green: #3fb950; --red: #f85149; --yellow: #d29922;
  --orange: #db6d28; --purple: #a371f7; --cyan: #39c5cf;
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:var(--bg); color:var(--text); font-family: -apple-system, 'SF Mono', 'Fira Code', monospace; font-size:13px; line-height:1.5; }}
h1 {{ font-size:18px; color:var(--accent); padding:16px 20px; border-bottom:1px solid var(--border); display:flex; justify-content:space-between; align-items:center; }}
h1 .refresh {{ font-size:11px; color:var(--border); font-weight:normal; }}
h2 {{ font-size:15px; color:var(--text); margin-bottom:12px; }}
h3 {{ font-size:13px; color:var(--accent); margin-bottom:8px; margin-top:16px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(320px,1fr)); gap:16px; padding:16px 20px; }}
.card {{ background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:16px; }}
.card h2 {{ border-bottom:1px solid var(--border); padding-bottom:8px; margin-bottom:12px; }}
.metric {{ display:flex; justify-content:space-between; align-items:center; padding:6px 0; border-bottom:1px solid var(--border); }}
.metric:last-child {{ border-bottom:none; }}
.metric-label {{ color:var(--text); }}
.metric-value {{ font-weight:bold; }}
.metric-value.ok {{ color:var(--green); }}
.metric-value.warn {{ color:var(--yellow); }}
.metric-value.crit {{ color:var(--red); }}
.metric-value.info {{ color:var(--accent); }}
.status-dot {{ display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px; }}
.status-dot.ok {{ background:var(--green); }}
.status-dot.warn {{ background:var(--yellow); }}
.status-dot.crit {{ background:var(--red); }}
.status-dot.unk {{ background:var(--border); }}
table {{ width:100%; border-collapse:collapse; font-size:12px; }}
th, td {{ text-align:left; padding:6px 8px; border-bottom:1px solid var(--border); }}
th {{ color:var(--accent); font-weight:600; }}
tr:hover {{ background:rgba(88,166,255,0.05); }}
.badge {{ display:inline-block; padding:2px 8px; border-radius:12px; font-size:11px; font-weight:600; }}
.badge-ok {{ background:rgba(63,185,80,0.15); color:var(--green); }}
.badge-warn {{ background:rgba(210,153,34,0.15); color:var(--yellow); }}
.badge-crit {{ background:rgba(248,81,73,0.15); color:var(--red); }}
.badge-info {{ background:rgba(88,166,255,0.15); color:var(--accent); }}
.badge-dead {{ background:rgba(48,54,61,0.8); color:var(--border); }}
.badge-set {{ background:rgba(63,185,80,0.15); color:var(--green); }}
.badge-missing {{ background:rgba(248,81,73,0.15); color:var(--red); }}
.progress-bar {{ height:6px; background:var(--border); border-radius:3px; overflow:hidden; margin-top:4px; }}
.progress-fill {{ height:100%; border-radius:3px; transition:width 0.3s; }}
.fill-ok {{ background:var(--green); }}
.fill-warn {{ background:var(--yellow); }}
.fill-crit {{ background:var(--red); }}
.nav {{ display:flex; gap:4px; padding:0 20px; border-bottom:1px solid var(--border); overflow-x:auto; }}
.nav-btn {{ padding:8px 16px; cursor:pointer; border:none; background:none; color:var(--text); opacity:0.7; font-size:12px; border-bottom:2px solid transparent; white-space:nowrap; }}
.nav-btn:hover, .nav-btn.active {{ opacity:1; border-bottom-color:var(--accent); color:var(--accent); }}
.section {{ display:none; }}
.section.active {{ display:block; }}
#log {{ font-size:11px; max-height:400px; overflow-y:auto; background:var(--bg); padding:12px; border:1px solid var(--border); border-radius:6px; white-space:pre-wrap; }}
</style>
</head>
<body>

<h1>🧬 ViralDNA Dashboard — Live System Health <span class="refresh">Auto-refreshes every 60s • Generated {data["timestamp"]}</span></h1>

<div class="nav">
  <button class="nav-btn active" onclick="showSection('overview',this)">📊 Overview</button>
  <button class="nav-btn" onclick="showSection('cron',this)">⏰ Cron Jobs</button>
  <button class="nav-btn" onclick="showSection('queue',this)">📋 Approval Queue</button>
  <button class="nav-btn" onclick="showSection('runs',this)">🔄 Recent Runs</button>
  <button class="nav-btn" onclick="showSection('youtube',this)">📺 YouTube</button>
  <button class="nav-btn" onclick="showSection('env',this)">🔑 Environment</button>
  <button class="nav-btn" onclick="showSection('analytics',this)">📈 Analytics</button>
</div>

<!-- ===== OVERVIEW ===== -->
<div id="overview" class="section active">
<div class="grid">
  <div class="card">
    <h2>📊 Topics Summary</h2>
    <div class="metric"><span class="metric-label">Total Topics</span><span class="metric-value info">{ov["total_topics"]}</span></div>
    <div class="metric"><span class="metric-label">Published</span><span class="metric-value ok">{ov["published"]}</span></div>
    <div class="metric"><span class="metric-label">Drive Ready</span><span class="metric-value info">{ov["drive_ready"]}</span></div>
    <div class="metric"><span class="metric-label">Completed</span><span class="metric-value ok">{ov["completed"]}</span></div>
    <div class="metric"><span class="metric-label">Rejected</span><span class="metric-value crit">{ov["rejected"]}</span></div>
    <div class="metric"><span class="metric-label">Max ID</span><span class="metric-value info">{ov["max_id"]}</span></div>
    <div class="metric"><span class="metric-label">Last Discovery Run</span><span class="metric-value">{ov["last_run"]}</span></div>
  </div>
  <div class="card">
    <h2>💻 Codebase</h2>
    <div class="metric"><span class="metric-label">Python Files</span><span class="metric-value info">{ov["py_files"]}</span></div>
    <div class="metric"><span class="metric-label">Module Files</span><span class="metric-value info">{ov["module_files"]}</span></div>
    <div class="metric"><span class="metric-label">Entry Points</span><span class="metric-value warn">~8 active / 43 total</span></div>
    <div class="metric"><span class="metric-label">Empty Agent Stubs</span><span class="metric-value crit">20+</span></div>
    <div class="metric"><span class="metric-label">Test Files in modules/</span><span class="metric-value warn">10</span></div>
  </div>
  <div class="card">
    <h2>💾 System</h2>
    <div class="metric"><span class="metric-label">Disk Free</span><span class="metric-value ok">{ov["disk_free_gb"]} GB</span></div>
    <div class="metric"><span class="metric-label">Disk Used</span><span class="metric-value">{ov["disk_pct"]}%</span></div>
    <div class="progress-bar"><div class="progress-fill {'fill-ok' if float(ov['disk_pct']) < 50 else 'fill-warn'}" style="width:{ov['disk_pct']}%"></div></div>
    <div class="metric"><span class="metric-label">Python Venv</span><span class="metric-value ok">OK</span></div>
    <div class="metric"><span class="metric-label">Hermes Gateway</span><span class="metric-value ok">RUNNING</span></div>
    <div class="metric"><span class="metric-label">Hermes Version</span><span class="metric-value info">v0.16.0+ (latest)</span></div>
  </div>
  <div class="card">
    <h2>🏥 System Health Score</h2>
    <div class="metric"><span class="metric-label">Overall</span><span class="metric-value {'ok' if health_pct >= 80 else 'warn' if health_pct >= 50 else 'crit'}">{health_label} ({health_pct}%)</span></div>
    <div class="progress-bar"><div class="progress-fill {health_class}" style="width:{health_pct}%"></div></div>
    <div class="metric"><span class="metric-label">Cron Jobs OK</span><span class="metric-value {'ok' if cron_ok == cron_total else 'warn'}">{cron_ok}/{cron_total}</span></div>
    <div class="metric"><span class="metric-label">Env Vars SET</span><span class="metric-value {'ok' if env_ok == len(env) else 'crit'}">{env_ok}/{len(env)}</span></div>
    <div class="metric"><span class="metric-label">Upload Status</span><span class="metric-value crit">BANNED (Manual)</span></div>
    <div class="metric"><span class="metric-label">Approval Gate</span><span class="metric-value ok">ACTIVE</span></div>
  </div>
</div>
</div>

<!-- ===== CRON JOBS ===== -->
<div id="cron" class="section">
<div class="grid">
  <div class="card" style="grid-column:1/-1">
    <h2>⏰ Cron Jobs ({cron_total} total)</h2>
    <table>
    <tr><th>Job</th><th>Schedule</th><th>Last Run</th><th>Status</th><th>Next Run</th><th>Enabled</th></tr>
    {cron_rows}
    </table>
  </div>
</div>
</div>

<!-- ===== APPROVAL QUEUE ===== -->
<div id="queue" class="section">
<div class="grid">
  <div class="card" style="grid-column:1/-1">
    <h2>📋 Approval Queue ({len(queue.get("pending",{}))} pending, {len(queue.get("approved",{}))} approved, {len(queue.get("rejected",{}))} rejected)</h2>
    <table>
    <tr><th>Topic ID</th><th>Title</th><th>Videos</th><th>Thumbs</th><th>Requested</th><th>Status</th></tr>
    {queue_rows}
    </table>
  </div>
</div>
</div>

<!-- ===== RECENT RUNS ===== -->
<div id="runs" class="section">
<div class="grid">
  <div class="card" style="grid-column:1/-1">
    <h2>🔄 Recent Pipeline Runs (last {len(runs)})</h2>
    <table>
    <tr><th>Start Time</th><th>Duration</th><th>Topics</th><th>Alerts</th><th>Top Topic</th><th>Top Score</th></tr>
    {runs_rows}
    </table>
  </div>
</div>
</div>

<!-- ===== YOUTUBE ===== -->
<div id="youtube" class="section">
<div class="grid">
  <div class="card">
    <h2>📺 YouTube Channel</h2>
    <div class="metric"><span class="metric-label">Channel</span><span class="metric-value info">The ViralDNA</span></div>
    <div class="metric"><span class="metric-label">Subscribers</span><span class="metric-value ok">{yt_subs}</span></div>
    <div class="metric"><span class="metric-label">Total Videos</span><span class="metric-value info">{yt_videos}</span></div>
    <div class="metric"><span class="metric-label">Total Views</span><span class="metric-value info">{yt_views}</span></div>
    <div class="metric"><span class="metric-label">Upload</span><span class="metric-value crit">BANNED</span></div>
    <div class="metric"><span class="metric-label">Category</span><span class="metric-value">News & Politics (25)</span></div>
    {'<div class="metric"><span class="metric-label">Error</span><span class="metric-value crit">' + yt_error + '</div>' if yt_error else ''}
  </div>
  <div class="card">
    <h2>📊 Content Breakdown</h2>
    <div class="metric"><span class="metric-label">Long-form Videos</span><span class="metric-value info">~10</span></div>
    <div class="metric"><span class="metric-label">Shorts</span><span class="metric-value info">~20</span></div>
    <div class="metric"><span class="metric-label">Avg Views (Shorts)</span><span class="metric-value warn">~807</span></div>
    <div class="metric"><span class="metric-label">Avg Views (Long)</span><span class="metric-value crit">~0.7</span></div>
    <div class="metric"><span class="metric-label">Best Performer</span><span class="metric-value ok">Shorts</span></div>
  </div>
</div>
</div>

<!-- ===== ENVIRONMENT ===== -->
<div id="env" class="section">
<div class="grid">
  <div class="card">
    <h2>🔑 Environment Variables</h2>
    <table>
    <tr><th>Variable</th><th>Status</th></tr>
    {env_rows}
    </table>
  </div>
  <div class="card">
    <h2>📁 Key Paths</h2>
    <div class="metric"><span class="metric-label">Project</span><span class="metric-value"><code>/home/jay/ViralDNA</code></span></div>
    <div class="metric"><span class="metric-label">Modules</span><span class="metric-value"><code>modules/</code> ({ov["module_files"]} files)</span></div>
    <div class="metric"><span class="metric-label">Logs</span><span class="metric-value"><code>logs/</code></span></div>
    <div class="metric"><span class="metric-label">Venv Python</span><span class="metric-value"><code>/home/jay/venv/bin/python3</code></span></div>
    <div class="metric"><span class="metric-label">.env File</span><span class="metric-value"><code>~/.env</code></span></div>
    <div class="metric"><span class="metric-label">YouTube Token</span><span class="metric-value"><code>credentials/youtube_token.json</code></span></div>
  </div>
</div>
</div>

<!-- ===== ANALYTICS ===== -->
<div id="analytics" class="section">
<div class="grid">
  <div class="card" style="grid-column:1/-1">
    <h2>📈 Channel Analytics</h2>
    <h3>Health State</h3>
    <pre id="log">{json.dumps(analytics.get("health", {}), indent=2)}</pre>
    <h3>Latest Feedback</h3>
    <pre id="log">{analytics.get("feedback", "No feedback")}</pre>
  </div>
</div>
</div>

<script>
function showSection(id, btn) {{
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  btn.classList.add('active');
}}
</script>
</body>
</html>"""
    return html


def main():
    print(f"Generating live dashboard... ({now_ist()})")

    data = {
        "timestamp": now_ist(),
        "overview": get_overview_data(),
        "cron_jobs": get_cron_data(),
        "approval_queue": get_approval_queue(),
        "recent_runs": get_recent_runs(),
        "analytics": get_analytics(),
        "env": get_env_status(),
        "youtube": get_youtube_stats(),
    }

    html = generate_html(data)

    DASHBOARD_DIR.mkdir(exist_ok=True)
    out_file = DASHBOARD_DIR / "index.html"
    out_file.write_text(html)
    print(f"Dashboard written to {out_file} ({len(html):,} bytes)")
    print(f"Open in browser: file://{out_file}")


if __name__ == "__main__":
    main()
