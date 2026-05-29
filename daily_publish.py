#!/usr/bin/env python3
"""
ViralDNA Daily Auto-Publish
============================
Called by Hermes cron every hour. Checks if daily quota is met.
If not, pulls latest topics from GitHub and runs the production pipeline.

This runs on the laptop (not GitHub) because it needs:
- RVC voice model / edge-tts
- ffmpeg with all filters
- YouTube upload credentials
- All asset files

Usage:
  python3 daily_publish.py          # normal hourly check
  python3 daily_publish.py --force  # force publish regardless of quota
"""

import json
import os
import sys
import subprocess
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")
TOPICS_FILE = os.path.join(LOGS_DIR, "topics_history.json")
PUBLISH_LOG = os.path.join(LOGS_DIR, "daily_publish_log.json")
DAILY_TARGET_MAIN = 1
DAILY_TARGET_SHORTS = 2


def load_env():
    env = {}
    env_path = os.path.join(os.path.expanduser("~"), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    return env


def send_telegram(text):
    env = load_env()
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print("  Telegram: no credentials")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read())
        if result.get("ok"):
            print("  Telegram sent!")
            return True
    except Exception as e:
        print(f"  Telegram error: {e}")
    return False


def get_today_publishes():
    if not os.path.exists(PUBLISH_LOG):
        return {"mains": 0, "shorts": 0, "videos": []}
    with open(PUBLISH_LOG) as f:
        log = json.load(f)
    today = datetime.now(IST).strftime("%Y-%m-%d")
    today_entries = [e for e in log if e.get("date") == today]
    mains = [e for e in today_entries if e.get("type") == "main"]
    shorts = [e for e in today_entries if e.get("type") == "short"]
    return {"mains": len(mains), "shorts": len(shorts), "videos": today_entries}


def add_publish_entry(entry):
    log = []
    if os.path.exists(PUBLISH_LOG):
        with open(PUBLISH_LOG) as f:
            log = json.load(f)
    log.append(entry)
    os.makedirs(os.path.dirname(PUBLISH_LOG), exist_ok=True)
    with open(PUBLISH_LOG, "w") as f:
        json.dump(log, f, indent=2)


def git_pull():
    os.chdir(PROJECT_ROOT)
    try:
        result = subprocess.run(
            ["git", "pull", "--quiet", "--rebase"],
            timeout=30, capture_output=True, text=True
        )
        if result.returncode == 0:
            print("  Git pull: OK")
            return True
        else:
            print(f"  Git pull failed: {result.stderr[:100]}")
            return False
    except Exception as e:
        print(f"  Git pull error: {e}")
        return False


def run_pipeline(mode="normal", topic=None):
    """Run the multi-agent pipeline. If topic is provided, inject it via --topic-file."""
    os.chdir(PROJECT_ROOT)
    cmd = [sys.executable, "run_pipeline_entrypoint.py", "--mode", mode]
    if topic:
        # Write topic to temp file for injection
        topic_file = os.path.join(PROJECT_ROOT, "logs", "injected_topic.json")
        with open(topic_file, "w") as f:
            json.dump(topic, f)
        cmd += ["--topic-file", topic_file]
        print(f"  Running pipeline: --mode {mode} --topic-file {topic_file}")
    else:
        print(f"  Running pipeline: --mode {mode}")
    try:
        result = subprocess.run(
            cmd,
            timeout=3600,  # 1 hour max
            capture_output=True,
            text=True
        )
        print(f"  Pipeline exit code: {result.returncode}")
        if result.stdout:
            lines = result.stdout.strip().split("\n")
            for line in lines[-20:]:
                print(f"    {line}")
        if result.returncode != 0 and result.stderr:
            print(f"  Pipeline stderr: {result.stderr[:300]}")
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print("  Pipeline timed out (1h)")
        return False
    except Exception as e:
        print(f"  Pipeline error: {e}")
        return False


def pick_best_topic():
    """Pick the highest-scoring topic from topics_history.json that hasn't been published today."""
    topics_file = os.path.join(PROJECT_ROOT, "logs", "topics_history.json")
    if not os.path.exists(topics_file):
        print("  No topics file found")
        return None
    with open(topics_file) as f:
        data = json.load(f)
    topics = data.get("topics", [])
    if not topics:
        print("  No topics in file")
        return None
    # Filter out already-published topics
    today = datetime.now(IST).strftime("%Y-%m-%d")
    pub = get_today_publishes()
    published_titles = [v.get("title", "") for v in pub.get("videos", [])]
    print(f"  Published today: {published_titles}")

    def jaccard(a, b):
        sa = set(a.lower().split())
        sb = set(b.lower().split())
        if not sa or not sb: return 0
        return len(sa & sb) / len(sa | sb)

    available = [t for t in topics if not any(jaccard(t.get("title", ""), p) >= 0.5 for p in published_titles)]
    if not available:
        print("  All topics already published today")
        return None
    # Sort by score descending
    best = max(available, key=lambda t: t.get("score", 0))
    print(f"  Best topic: [{best.get('score', 0)}] {best.get('title', '')[:70]}")
    return best


def main():
    force = "--force" in sys.argv
    now_ist = datetime.now(IST)
    hour_ist = now_ist.hour
    today_str = now_ist.strftime("%Y-%m-%d")

    print(f"\n{'='*60}")
    print(f"ViralDNA Daily Auto-Publish — {now_ist.strftime('%Y-%m-%d %H:%M IST')}")
    print(f"{'='*60}")

    # Pull latest topics from GitHub
    git_pull()

    # Check today's publish status
    pub = get_today_publishes()
    mains_done = pub["mains"]
    shorts_done = pub["shorts"]
    print(f"\n  Today: {mains_done}/{DAILY_TARGET_MAIN} mains, {shorts_done}/{DAILY_TARGET_SHORTS} shorts")

    if not force and mains_done >= DAILY_TARGET_MAIN and shorts_done >= DAILY_TARGET_SHORTS:
        print("  Daily quota met. Nothing to do.")
        print(f"{'='*60}\n")
        return

    # Determine what slot we're in
    # 7-11 AM: Morning main window
    # 11 AM-3 PM: First short window
    # 4-8 PM: Evening main window
    # 8-11 PM: Second short window
    # 11 PM-7 AM: Late catch-up (anything not done)

    published = False

    # Pick best available topic for this run
    best_topic = pick_best_topic()
    if best_topic:
        print(f"  Selected topic: [{best_topic.get('score',0)}] {best_topic.get('title','')[:60]}")
    else:
        print("  No suitable topic found — pipeline will do its own discovery")
        best_topic = None

    if force or (hour_ist >= 7 and hour_ist < 11 and mains_done < DAILY_TARGET_MAIN):
        print("\n[SLOT] Morning main video")
        success = run_pipeline(mode="normal", topic=best_topic)
        if success:
            add_publish_entry({
                "date": today_str, "type": "main", "slot": "morning",
                "title": "pipeline_output", "status": "completed",
                "timestamp": now_ist.isoformat()
            })
            send_telegram(
                f"ViralDNA Morning Main Published\n\n"
                f"Time: {now_ist.strftime('%H:%M IST')}\n"
                f"Check YouTube Studio for details."
            )
            published = True
        else:
            send_telegram("Morning main pipeline FAILED. Will retry next hour.")

    elif force or (hour_ist >= 11 and hour_ist < 15 and shorts_done < 1):
        print("\n[SLOT] First short")
        success = run_pipeline(mode="primetime", topic=best_topic)
        if success:
            add_publish_entry({
                "date": today_str, "type": "short", "slot": "midday",
                "title": "pipeline_output", "status": "completed",
                "timestamp": now_ist.isoformat()
            })
            send_telegram(f"ViralDNA Midday Short Published — {now_ist.strftime('%H:%M IST')}")
            published = True
        else:
            send_telegram("Midday short FAILED. Will retry.")

    elif force or (hour_ist >= 16 and hour_ist < 20 and mains_done < DAILY_TARGET_MAIN):
        print("\n[SLOT] Evening main video")
        success = run_pipeline(mode="normal", topic=best_topic)
        if success:
            add_publish_entry({
                "date": today_str, "type": "main", "slot": "evening",
                "title": "pipeline_output", "status": "completed",
                "timestamp": now_ist.isoformat()
            })
            send_telegram(
                f"ViralDNA Evening Main Published\n\n"
                f"Time: {now_ist.strftime('%H:%M IST')}\n"
                f"Check YouTube Studio."
            )
            published = True
        else:
            send_telegram("Evening main FAILED. Will retry.")

    elif force or (hour_ist >= 20 and hour_ist < 23 and shorts_done < DAILY_TARGET_SHORTS):
        print("\n[SLOT] Evening short")
        success = run_pipeline(mode="primetime")
        if success:
            add_publish_entry({
                "date": today_str, "type": "short", "slot": "evening",
                "title": "pipeline_output", "status": "completed",
                "timestamp": now_ist.isoformat()
            })
            send_telegram(f"ViralDNA Evening Short Published — {now_ist.strftime('%H:%M IST')}")
            published = True
        else:
            send_telegram("Evening short FAILED. Will retry.")

    elif hour_ist >= 23 or hour_ist < 7:
        # Late night catch-up: anything still not done
        if mains_done < DAILY_TARGET_MAIN:
            print("\n[SLOT] Late catch-up: main")
            success = run_pipeline(mode="normal")
            if success:
                add_publish_entry({
                    "date": today_str, "type": "main", "slot": "late_catchup",
                    "title": "pipeline_output", "status": "completed",
                    "timestamp": now_ist.isoformat()
                })
                send_telegram(f"Late catch-up main uploaded — {now_ist.strftime('%H:%M IST')}")
                published = True
        if shorts_done < DAILY_TARGET_SHORTS:
            print("\n[SLOT] Late catch-up: short")
            success = run_pipeline(mode="primetime")
            if success:
                add_publish_entry({
                    "date": today_str, "type": "short", "slot": "late_catchup",
                    "title": "pipeline_output", "status": "completed",
                    "timestamp": now_ist.isoformat()
                })
                published = True

    if not published and not force:
        print(f"\n  Not in an active publish window at {hour_ist}:00 IST")
        print(f"  Windows: 7-11AM (main), 11AM-3PM (short), 4-8PM (main), 8-11PM (short)")

    pub = get_today_publishes()
    print(f"\n  End of run: {pub['mains']}/{DAILY_TARGET_MAIN} mains, {pub['shorts']}/{DAILY_TARGET_SHORTS} shorts")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
