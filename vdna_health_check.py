#!/usr/bin/env python3
"""
ViralDNA Health Check Script
Checks all system components and outputs a status report.
Can be run standalone or by a cron job.

Usage:
    python3 vdna_health_check.py          # Print report
    python3 vdna_health_check.py --json   # Output JSON for dashboard
    python3 vdna_health_check.py --quiet  # Exit code only (0=healthy, 1=issues)
"""

import json
import os
import sys
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE_DIR = Path("/home/jay/ViralDNA")
LOGS_DIR = BASE_DIR / "logs"
ANALYTICS_DIR = BASE_DIR / "analytics"
OUTPUT_DIR = BASE_DIR / "output"
DOTENV_FILE = Path.home() / ".env"


def check_disk():
    """Check available disk space."""
    stat = os.statvfs("/")
    total = stat.f_blocks * stat.f_frsize
    free = stat.f_bavail * stat.f_frsize
    used = total - free
    pct = (used / total) * 100
    status = "ok" if pct < 80 else ("warn" if pct < 90 else "crit")
    return {
        "name": "Disk Space",
        "status": status,
        "total_gb": f"{total/1e9:.1f}",
        "used_gb": f"{used/1e9:.1f}",
        "free_gb": f"{free/1e9:.1f}",
        "used_pct": f"{pct:.1f}%",
        "detail": f"{free/1e9:.1f}GB free ({pct:.1f}% used)"
    }


def check_env_vars():
    """Check that required environment variables are set."""
    from dotenv import load_dotenv
    load_dotenv(DOTENV_FILE)
    required = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]
    optional = ["SERPER_API_KEY", "OPENROUTER_API_KEY"]
    results = []
    for var in required:
        val = os.getenv(var)
        ok = val is not None and len(val) > 5
        results.append({
            "name": var,
            "status": "ok" if ok else "crit",
            "required": True,
            "detail": "SET" if ok else "MISSING"
        })
    for var in optional:
        val = os.getenv(var)
        ok = val is not None and len(val) > 5
        results.append({
            "name": var,
            "status": "ok" if ok else "warn",
            "required": False,
            "detail": "SET" if ok else "MISSING"
        })
    return results


def check_venv_deps():
    """Check that all required Python packages are installed in venv."""
    venv_python = "/home/jay/venv/bin/python3"
    deps = [
        "gtts", "requests", "bs4", "PIL", "cv2", "numpy",
        "dotenv", "yaml", "feedparser", "pytz",
        "googleapiclient"
    ]
    result = subprocess.run(
        [venv_python, "-c",
         "import " + ",".join(deps) + "; print('all_ok')"],
        capture_output=True, text=True, timeout=10
    )
    ok = result.returncode == 0 and "all_ok" in result.stdout
    return {
        "name": "Venv Dependencies",
        "status": "ok" if ok else "crit",
        "detail": f"{'All' if ok else 'Some'} of {len(deps)} packages OK",
        "packages": deps
    }


def check_pipeline_imports():
    """Check that all pipeline modules import cleanly."""
    venv_python = "/home/jay/venv/bin/python3"
    mods = [
        "run_multi_agent_pipeline", "voiceover", "script_generator",
        "visual_fetcher", "thumbnail_creator", "video_assembler",
        "youtube_uploader", "telegram_alert", "approval_gate",
        "trend_discovery", "config", "forensic_audit"
    ]
    result = subprocess.run(
        [venv_python, "-c",
         f"import sys; sys.path.insert(0, 'modules'); " +
         "; ".join(f"import {m}" for m in mods) +
         "; print('all_ok')"],
        capture_output=True, text=True, timeout=15,
        cwd=str(BASE_DIR)
    )
    ok = result.returncode == 0 and "all_ok" in result.stdout
    err = result.stderr.strip()[:200] if not ok else ""
    return {
        "name": "Pipeline Imports",
        "status": "ok" if ok else "crit",
        "detail": f"{'All' if ok else 'Some'} of {len(mods)} modules import OK",
        "error": err
    }


def check_topics_db():
    """Check topics database health."""
    tf = LOGS_DIR / "topics_history.json"
    if not tf.exists():
        return {"name": "Topics DB", "status": "crit", "detail": "File missing"}
    try:
        d = json.load(tf.open())
        topics = d.get("topics", [])
        total = len(topics)
        has_id = sum(1 for t in topics if isinstance(t, dict) and "id" in t)
        published = sum(1 for t in topics if isinstance(t, dict) and t.get("published"))
        rejected = sum(1 for t in topics if isinstance(t, dict) and t.get("status") == "rejected")
        ids = [t["id"] for t in topics if isinstance(t, dict) and "id" in t]
        max_id = max(ids, default="none")
        last_run = d.get("last_run", "unknown")
        return {
            "name": "Topics Database",
            "status": "ok",
            "total": total,
            "has_id": has_id,
            "published": published,
            "rejected": rejected,
            "max_id": max_id,
            "last_run": last_run,
            "detail": f"{total} topics, {published} published, max {max_id}"
        }
    except Exception as e:
        return {"name": "Topics DB", "status": "crit", "detail": str(e)}


def check_approval_queue():
    """Check approval queue status."""
    qf = OUTPUT_DIR / "runtime" / "approval_queue.json"
    if not qf.exists():
        return {"name": "Approval Queue", "status": "ok", "detail": "No queue file (clean)"}
    try:
        q = json.load(qf.open())
        pending = q.get("pending", {})
        approved = q.get("approved", {})
        rejected = q.get("rejected", {})
        # Check for stale entries (no video files)
        stale = []
        for tid, entry in pending.items():
            vids = entry.get("video_files", [])
            thumbs = entry.get("thumbnail_files", [])
            if not vids and not thumbs:
                stale.append(tid)
        status = "ok" if not stale else "warn"
        return {
            "name": "Approval Queue",
            "status": status,
            "pending": len(pending),
            "approved": len(approved),
            "rejected": len(rejected),
            "stale": stale,
            "detail": f"{len(pending)} pending, {stale} stale" if stale else f"{len(pending)} pending"
        }
    except Exception as e:
        return {"name": "Approval Queue", "status": "crit", "detail": str(e)}


def check_cron_jobs():
    """Check cron job status from Hermes cronjob tool."""
    # Read the cron jobs directly from Hermes state
    cron_file = Path.home() / ".hermes" / "cron" / "jobs.json"
    if not cron_file.exists():
        return {"name": "Cron Jobs", "status": "warn", "detail": "jobs.json not found"}
    try:
        data = json.load(cron_file.open())
        if isinstance(data, list):
            jobs = data
        elif isinstance(data, dict):
            jobs = data.get("jobs", data.get("crons", []))
        else:
            return {"name": "Cron Jobs", "status": "warn", "detail": "Unexpected jobs.json format"}
        total = len(jobs)
        active = sum(1 for j in jobs if j.get("enabled"))
        ok_count = sum(1 for j in jobs if j.get("last_status") == "ok")
        error_count = sum(1 for j in jobs if j.get("last_status") == "error")
        job_summaries = []
        for j in jobs:
            next_run = j.get("next_run_at", "?")[:16]
            job_summaries.append({
                "name": j.get("name", "?"),
                "status": j.get("last_status", "never"),
                "next": next_run,
                "enabled": j.get("enabled", False)
            })
        status = "ok" if error_count == 0 else "warn"
        return {
            "name": "Cron Jobs",
            "status": status,
            "total": total,
            "active": active,
            "ok": ok_count,
            "errors": error_count,
            "jobs": job_summaries,
            "detail": f"{active}/{total} active, {error_count} errors"
        }
    except Exception as e:
        return {"name": "Cron Jobs", "status": "warn", "detail": str(e)}


def check_youtube_token():
    """Check YouTube token validity."""
    tf = BASE_DIR / "credentials" / "youtube_token.json"
    if not tf.exists():
        return {"name": "YouTube Token", "status": "crit", "detail": "Token file missing"}
    try:
        d = json.load(tf.open())
        has_token = "token" in d or "access_token" in d
        scopes = d.get("scopes", [])
        scope_count = len(scopes) if isinstance(scopes, list) else "?"
        return {
            "name": "YouTube Token",
            "status": "ok" if has_token else "crit",
            "scopes": scope_count,
            "detail": f"Token present, {scope_count} scopes"
        }
    except Exception as e:
        return {"name": "YouTube Token", "status": "crit", "detail": str(e)}


def check_output_files():
    """Check for stale output files that might cause cross-topic contamination."""
    runtime_dir = OUTPUT_DIR / "runtime"
    stale_patterns = ["production_*", "viz_*", "scene_*", "*.mp4", "*.mp3"]
    stale_count = 0
    if runtime_dir.exists():
        for p in runtime_dir.iterdir():
            if p.is_file():
                stale_count += 1
    status = "ok" if stale_count == 0 else "warn"
    return {
        "name": "Runtime Cleanup",
        "status": status,
        "stale_files": stale_count,
        "detail": f"{stale_count} stale files in output/runtime/" if stale_count else "Clean"
    }


def check_credentials():
    """Check all credential files exist."""
    creds_dir = BASE_DIR / "credentials"
    required_files = ["youtube_token.json"]
    missing = []
    for f in required_files:
        if not (creds_dir / f).exists():
            missing.append(f)
    optional = ["youtube_client_secrets.json", "serper_key.txt"]
    found_optional = []
    for f in optional:
        if (creds_dir / f).exists():
            found_optional.append(f)
    status = "ok" if not missing else "crit"
    return {
        "name": "Credentials",
        "status": status,
        "missing": missing,
        "found_optional": found_optional,
        "detail": f"Missing: {missing}" if missing else f"All required present"
    }


def check_recent_runs():
    """Check recent pipeline run logs."""
    lf = LOGS_DIR / "run_log.jsonl"
    if not lf.exists():
        return {"name": "Recent Runs", "status": "warn", "detail": "No run log"}
    lines = lf.read_text().strip().split("\n")
    if not lines:
        return {"name": "Recent Runs", "status": "warn", "detail": "Empty run log"}
    last = json.loads(lines[-1])
    last_time_str = last.get("run_end", last.get("run_start", ""))
    last_topics = last.get("produce_topics", 0)
    last_alerts = last.get("alerts_sent", 0)
    detail = f"Last run: {last.get('produce_topics',0)} topics, {last.get('alerts_sent',0)} alerts"
    if last_time_str:
        try:
            from datetime import datetime
            t = datetime.fromisoformat(last_time_str)
            now = datetime.now(tz=t.tzinfo)
            hours_ago = (now - t).total_seconds() / 3600
            detail += f", {hours_ago:.1f}h ago"
        except:
            pass
    return {
        "name": "Recent Runs",
        "status": "ok",
        "detail": detail,
        "last_run": last_time_str,
        "last_topics": last_topics,
        "last_alerts": last_alerts
    }


def run_all_checks():
    """Run all health checks and return results."""
    tz = timezone(timedelta(hours=5, minutes=30))
    now = datetime.now(tz).strftime("%Y-%m-%d %H:%M IST")

    all_checks = []

    # Individual checks
    all_checks.append(check_disk())
    all_checks.append(check_topics_db())
    all_checks.append(check_approval_queue())
    all_checks.append(check_pipeline_imports())
    all_checks.append(check_venv_deps())
    all_checks.append(check_cron_jobs())
    all_checks.append(check_youtube_token())
    all_checks.append(check_credentials())
    all_checks.append(check_output_files())
    all_checks.append(check_recent_runs())

    # Env vars (returns list)
    env_results = check_env_vars()
    all_checks.extend(env_results)

    # Calculate overall status
    statuses = [c["status"] for c in all_checks if isinstance(c, dict) and "status" in c]
    if "crit" in statuses:
        overall = "crit"
    elif "warn" in statuses:
        overall = "warn"
    else:
        overall = "ok"

    return {
        "timestamp": now,
        "overall": overall,
        "checks": all_checks
    }


def format_report(data):
    """Format health check data as a readable text report."""
    lines = []
    lines.append("=" * 60)
    lines.append(f"  ViralDNA Health Check — {data['timestamp']}")
    lines.append(f"  Overall: {data['overall'].upper()}")
    lines.append("=" * 60)

    for check in data["checks"]:
        if not isinstance(check, dict):
            continue
        name = check.get("name", "?")
        status = check.get("status", "?")
        detail = check.get("detail", "")

        icon = {"ok": "✅", "warn": "⚠️", "crit": "❌"}.get(status, "❓")
        lines.append(f"  {icon} {name}: {detail}")

        # Sub-items for cron jobs
        if "jobs" in check:
            for j in check["jobs"]:
                jicon = {"ok": "  ✅", "error": "  ❌", "never": "  ○"}.get(j["status"], "  ?")
                lines.append(f"    {jicon} {j['name']} → next {j['next']}")

    lines.append("=" * 60)
    return "\n".join(lines)


if __name__ == "__main__":
    args = sys.argv[1:]

    if "--json" in args:
        data = run_all_checks()
        print(json.dumps(data, indent=2, default=str))
    elif "--quiet" in args:
        data = run_all_checks()
        sys.exit(0 if data["overall"] == "ok" else 1)
    else:
        data = run_all_checks()
        print(format_report(data))
        # Exit with non-zero if there are issues
        sys.exit(0 if data["overall"] == "ok" else 1)
