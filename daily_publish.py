#!/usr/bin/env python3
"""
ViralDNA Daily Auto-Publish
============================
Runs once (called by cron). Picks best UNPUBLISHED topics:
  1. Morning main (score >= 10 ideally, or best available)
  2. Evening main  (different topic)
  3. Shorts (2 shorts, different topics if possible)

Per-day quota: 1 main + 2 shorts. Each video uses a DIFFERENT topic.
Only publishes if current time is in a valid window or --force.

Upload windows (IST):
  Morning main:   7AM - 11AM
  Midday short:   11AM - 3PM  (short #1)
  Evening main:   4PM - 8PM
  Evening short:  8PM - 11PM (short #2)

UPLOAD KILL SWITCH: Set VIRALDNA_UPLOAD_ENABLED=false (default) to disable all YouTube uploads.
When disabled, pipeline still runs (build, render, thumbnail) but output goes to Google Drive for manual review.
"""
import os

UPLOAD_ENABLED = os.environ.get("VIRALDNA_UPLOAD_ENABLED", "false").lower() == "true"

import json
import subprocess
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
TOPICS_FILE = os.path.join(PROJECT_ROOT, "logs", "topics_history.json")
PUBLISH_LOG = os.path.join(PROJECT_ROOT, "logs", "daily_publish_log.json")
TOPIC_USAGE_FILE = os.path.join(PROJECT_ROOT, "logs", "topic_usage_today.json")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "8659664950")

# Load Telegram creds from ~/.env if not set in environment
if not TELEGRAM_BOT_TOKEN:
    env_path = os.path.expanduser("~/.env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("TELEGRAM_BOT_TOKEN="):
                    TELEGRAM_BOT_TOKEN = line.split("=", 1)[1].strip().strip("'\"")
                elif line.startswith("TELEGRAM_CHAT_ID="):
                    TELEGRAM_CHAT_ID = line.split("=", 1)[1].strip().strip("'\"")

DAILY_LOG_FILE = os.path.join(PROJECT_ROOT, "logs", "daily_log.json")


def load_daily_log():
    """Load today's upload log. Returns (log_entry_dict, today_str)."""
    today = datetime.now(IST).strftime("%Y-%m-%d")
    if not os.path.exists(DAILY_LOG_FILE):
        return {"main_done": False, "shorts_done": 0, "topics_used": []}, today
    with open(DAILY_LOG_FILE) as f:
        log = json.load(f)
    return log.get(today, {"main_done": False, "shorts_done": 0, "topics_used": []}), today


def save_daily_log(log_entry, today):
    """Save today's upload log entry."""
    os.makedirs(os.path.dirname(DAILY_LOG_FILE), exist_ok=True)
    try:
        with open(DAILY_LOG_FILE) as f:
            full_log = json.load(f)
    except Exception:
        full_log = {}
    full_log[today] = log_entry
    with open(DAILY_LOG_FILE, "w") as f:
        json.dump(full_log, f, indent=2)


def send_telegram(msg):
    if not TELEGRAM_BOT_TOKEN:
        print("  No Telegram token, skipping")
        return False
    try:
        import urllib.request, json
        payload = json.dumps({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg,
            "parse_mode": "HTML"
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read())
        if result.get("ok"):
            print("  Telegram sent!")
            return True
    except Exception as e:
        print(f"  Telegram error: {e}")
    return False


def jaccard(a, b):
    sa = set(a.lower().split())
    sb = set(b.lower().split())
    if not sa or not sb:
        return 0
    return len(sa & sb) / len(sa | sb)


def load_today_usage():
    """Load which topic titles have been used today.

    On a new day, preloads used_titles from topics_history.json
    so that topics published by other uploaders (smart_scheduler)
    are not re-picked.
    """
    today = datetime.now(IST).strftime("%Y-%m-%d")
    if not os.path.exists(TOPIC_USAGE_FILE):
        return _preload_from_history({"date": today, "used_titles": []}, today)
    with open(TOPIC_USAGE_FILE) as f:
        data = json.load(f)
    if data.get("date") != today:
        return _preload_from_history({"date": today, "used_titles": []}, today)
    return data


def _preload_from_history(usage, today):
    """Preload used_titles from topics_history.json for today's already-published topics.

    This ensures that if smart_scheduler.py or another publish path already
    uploaded a topic today, daily_publish.py won't re-pick it.
    """
    try:
        if not os.path.exists(TOPICS_FILE):
            return usage
        with open(TOPICS_FILE) as f:
            data = json.load(f)
        preloaded = []
        for t in data.get("topics", []):
            if not t.get("published"):
                continue
            pub_at = t.get("published_at", "")
            # Include if published today (compare date prefix)
            if isinstance(pub_at, str) and pub_at[:10] == today:
                preloaded.append(t.get("title", ""))
        if preloaded:
            usage["used_titles"] = preloaded
            print(f"  Preloaded {len(preloaded)} already-published topic(s) from today")
    except Exception as e:
        print(f"  Warning: Could not preload from history: {e}")
    return usage


def save_today_usage(usage):
    os.makedirs(os.path.dirname(TOPIC_USAGE_FILE), exist_ok=True)
    with open(TOPIC_USAGE_FILE, "w") as f:
        json.dump(usage, f, indent=2)


def mark_topic_used(title):
    usage = load_today_usage()
    usage["used_titles"].append(title)
    save_today_usage(usage)


def mark_topic_published_in_history(topic):
    """Mark a topic as published in topics_history.json by topic id or title."""
    if not topic:
        return
    topics_file = os.path.join(PROJECT_ROOT, "logs", "topics_history.json")
    if not os.path.exists(topics_file):
        return
    with open(topics_file) as f:
        data = json.load(f)
    topic_id = topic.get("id", "")
    topic_title = topic.get("title", "")
    now_str = datetime.now(IST).isoformat()
    for t in data.get("topics", []):
        if t.get("id") == topic_id or t.get("title") == topic_title:
            t["published"] = True
            t["published_at"] = now_str
            break
    with open(topics_file, "w") as f:
        json.dump(data, f, indent=2)


def pick_topic(exclude_titles=None, exclude_ids=None, min_score=7):
    """
    Pick the best topic from topics_history.json that:
    - Has not been used today (not in exclude_titles, not in exclude_ids)
    - Has score >= min_score
    - Is NOT already marked as published in topics_history.json
    Returns (topic_dict, remaining_topics_count) or (None, 0)
    """
    if not os.path.exists(TOPICS_FILE):
        print("  No topics file found")
        return None, 0
    with open(TOPICS_FILE) as f:
        data = json.load(f)
    topics = data.get("topics", [])
    if not topics:
        print("  No topics in file")
        return None, 0

    exclude = exclude_titles or []
    exclude_i = set(exclude_ids or [])
    available = []
    skipped_published = 0
    skipped_used = 0
    skipped_score = 0
    for t in topics:
        title = t.get("title", "")
        topic_id = t.get("id", "")
        score = t.get("score", 0)
        # HARD CHECK: skip if already published (regardless of usage file)
        if t.get("published"):
            skipped_published += 1
            continue
        if score < min_score:
            skipped_score += 1
            continue
        if topic_id in exclude_i:
            skipped_used += 1
            continue
        if any(jaccard(title, used) >= 0.4 for used in exclude):
            skipped_used += 1
            continue
        available.append(t)

    print(f"  Filter: {skipped_published} published, {skipped_used} already used, {skipped_score} low score, {len(available)} available")

    if not available:
        print(f"  No available topics (min_score={min_score})")
        return None, 0

    # Sort by score descending
    available.sort(key=lambda t: t.get("score", 0), reverse=True)
    best = available[0]
    print(f"  Picked topic: [{best.get('score', 0)}] {best.get('id', '')} — {best.get('title', '')[:60]}")
    return best, len(available)


def git_pull():
    os.chdir(PROJECT_ROOT)
    try:
        subprocess.run(["git", "stash", "--quiet"], timeout=10, capture_output=True)
        result = subprocess.run(
            ["git", "pull", "--quiet", "--rebase"],
            timeout=30, capture_output=True, text=True
        )
        subprocess.run(["git", "stash", "pop", "--quiet"], timeout=10, capture_output=True)
        if result.returncode == 0:
            print("  Git pull: OK")
            return True
        else:
            print(f"  Git pull failed: {result.stderr[:100]}")
            return False
    except Exception as e:
        print(f"  Git pull error: {e}")
        return False


def run_pipeline(mode="normal", topic=None, shorts_only=False):
    """Run the multi-agent pipeline. If topic is provided, inject it."""
    os.chdir(PROJECT_ROOT)
    cmd = [sys.executable, "run_pipeline_entrypoint.py", "--mode", mode]
    if shorts_only:
        cmd.append("--shorts-only")
    topic_file = None
    if topic:
        topic_file = os.path.join(PROJECT_ROOT, "logs", "injected_topic.json")
        with open(topic_file, "w") as f:
            json.dump(topic, f)
        cmd += ["--topic-file", topic_file]
        print(f"  Pipeline: --mode {mode} + injected topic")
    else:
        print(f"  Pipeline: --mode {mode} (auto-discovery)")
    try:
        result = subprocess.run(cmd, timeout=3600, capture_output=True, text=True)
        print(f"  Pipeline exit code: {result.returncode}")
        if result.stdout:
            lines = result.stdout.strip().split("\n")
            for line in lines[-15:]:
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

    # Load today's usage + daily log (shared with smart_scheduler)
    usage = load_today_usage()
    used_titles = usage["used_titles"]
    daily_log, _ = load_daily_log()

    # Build exclude_ids from topics_history.json — NEVER re-pick published topics
    exclude_ids = set()
    try:
        if os.path.exists(TOPICS_FILE):
            with open(TOPICS_FILE) as f:
                th_data = json.load(f)
            for t in th_data.get("topics", []):
                if t.get("published"):
                    exclude_ids.add(t.get("id", ""))
                    exclude_ids.add(t.get("title", ""))  # also exclude by title
    except Exception as e:
        print(f"  Warning: Could not load exclude_ids from history: {e}")
    # Also exclude by today's usage file titles
    used_ids = set()
    for t in used_titles:
        used_ids.add(t)

    print(f"\n  Topics used today: {len(used_titles)}")
    for t in used_titles:
        print(f"    - {t[:60]}")
    print(f"  Published topics excluded: {len(exclude_ids)}")
    print(f"  Daily log: main_done={daily_log.get('main_done')}, shorts_done={daily_log.get('shorts_done', 0)}")

    # Determine what slot we're in
    # 7-11 AM: Morning main
    # 11 AM-3 PM: First short
    # 4-8 PM: Evening main
    # 8-11 PM: Second short
    # 11 PM-7 AM: Nothing (sleep)

    published = False

    if force or (hour_ist >= 7 and hour_ist < 11):
        # MORNING MAIN
        if not force and daily_log.get("main_done"):
            print(f"\n[SKIP] Main already done today (daily_log). Skipping morning slot.")
        else:
            print(f"\n[SLOT] Morning main (hour={hour_ist})")
            topic, remaining = pick_topic(exclude_titles=used_titles, exclude_ids=exclude_ids, min_score=7)
            if topic:
                success = run_pipeline(mode="normal", topic=topic)
                if success:
                    mark_topic_used(topic.get("title", ""))
                    mark_topic_published_in_history(topic)
                    # Update daily_log
                    daily_log["main_done"] = True
                    daily_log.setdefault("topics_used", []).append(topic.get("title", ""))
                    save_daily_log(daily_log, today_str)
                    send_telegram(
                        f"📺 ViralDNA Morning Main Published\n\n"
                        f"Topic: {topic.get('title', '')[:80]}\n"
                        f"Score: {topic.get('score', 0)}/30\n"
                        f"Time: {now_ist.strftime('%H:%M IST')}\n\n"
                        f"YouTube Studio."
                    )
                    published = True
                else:
                    send_telegram("❌ Morning main pipeline FAILED. Will retry next run.")
            else:
                print("  No topic available for morning main")

    elif force or (hour_ist >= 11 and hour_ist < 15):
        # MIDDAY SHORT #1
        if not force and daily_log.get("shorts_done", 0) >= 2:
            print(f"\n[SKIP] Already {daily_log.get('shorts_done', 0)} shorts done today. Skipping midday short.")
        else:
            print(f"\n[SLOT] Midday short (hour={hour_ist})")
            topic, remaining = pick_topic(exclude_titles=used_titles, exclude_ids=exclude_ids, min_score=5)
            if topic:
                success = run_pipeline(mode="primetime", topic=topic, shorts_only=True)
                if success:
                    mark_topic_used(topic.get("title", ""))
                    mark_topic_published_in_history(topic)
                    # Update daily_log
                    daily_log["shorts_done"] = daily_log.get("shorts_done", 0) + 1
                    daily_log.setdefault("topics_used", []).append(topic.get("title", ""))
                    save_daily_log(daily_log, today_str)
                    send_telegram(
                        f"📱 ViralDNA Short Published\n\n"
                        f"Topic: {topic.get('title', '')[:80]}\n"
                        f"Score: {topic.get('score', 0)}/30\n"
                        f"Time: {now_ist.strftime('%H:%M IST')}"
                    )
                    published = True
                else:
                    send_telegram("❌ Midday short pipeline FAILED.")
            else:
                print("  No topic available for midday short")

    elif force or (hour_ist >= 16 and hour_ist < 20):
        # EVENING MAIN
        if not force and daily_log.get("main_done"):
            print(f"\n[SKIP] Main already done today (daily_log). Skipping evening slot.")
        else:
            print(f"\n[SLOT] Evening main (hour={hour_ist})")
            topic, remaining = pick_topic(exclude_titles=used_titles, exclude_ids=exclude_ids, min_score=7)
            if topic:
                success = run_pipeline(mode="normal", topic=topic)
                if success:
                    mark_topic_used(topic.get("title", ""))
                    mark_topic_published_in_history(topic)
                    # Update daily_log
                    daily_log["main_done"] = True
                    daily_log.setdefault("topics_used", []).append(topic.get("title", ""))
                    save_daily_log(daily_log, today_str)
                    send_telegram(
                        f"📺 ViralDNA Evening Main Published\n\n"
                        f"Topic: {topic.get('title', '')[:80]}\n"
                        f"Score: {topic.get('score', 0)}/30\n"
                        f"Time: {now_ist.strftime('%H:%M IST')}\n\n"
                        f"YouTube Studio."
                    )
                    published = True
                else:
                    send_telegram("❌ Evening main pipeline FAILED. Will retry next run.")
            else:
                print("  No topic available for evening main")

    elif force or (hour_ist >= 20 and hour_ist < 23):
        # EVENING SHORT #2
        if not force and daily_log.get("shorts_done", 0) >= 2:
            print(f"\n[SKIP] Already {daily_log.get('shorts_done', 0)} shorts done today. Skipping evening short.")
        else:
            print(f"\n[SLOT] Evening short (hour={hour_ist})")
            topic, remaining = pick_topic(exclude_titles=used_titles, exclude_ids=exclude_ids, min_score=5)
            if topic:
                success = run_pipeline(mode="primetime", topic=topic, shorts_only=True)
                if success:
                    mark_topic_used(topic.get("title", ""))
                    mark_topic_published_in_history(topic)
                    # Update daily_log
                    daily_log["shorts_done"] = daily_log.get("shorts_done", 0) + 1
                    daily_log.setdefault("topics_used", []).append(topic.get("title", ""))
                    save_daily_log(daily_log, today_str)
                    send_telegram(
                        f"📱 ViralDNA Short Published\n\n"
                        f"Topic: {topic.get('title', '')[:80]}\n"
                        f"Score: {topic.get('score', 0)}/30\n"
                        f"Time: {now_ist.strftime('%H:%M IST')}"
                    )
                    published = True
                else:
                    send_telegram("❌ Evening short pipeline FAILED.")
            else:
                print("  No topic available for evening short")

    elif hour_ist >= 23 or hour_ist < 7:
        print(f"\n[SLEEP] {hour_ist}:00 IST — outside publish window (7AM-11PM)")

    if not published and not force:
        print(f"\n  No action taken at {hour_ist}:00 IST")

    usage = load_today_usage()
    print(f"\n  Topics used today: {len(usage['used_titles'])}/{4} (target: 1 main + 2 shorts)")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
