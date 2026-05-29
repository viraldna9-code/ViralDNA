#!/usr/bin/env python3
"""
ViralDNA Smart Scheduler
========================
Called by Hermes cron every hour.
Determines current time slot, picks best unpublished topic,
runs build_topic.py, sends Telegram notification.

Time Slots (IST):
  7AM-11AM  = MAIN_MORNING   (1 main + 2 shorts)
  11AM-3PM  = SHORT_1        (1 short only)
  3PM-6PM   = REST           (nothing)
  6PM-10PM  = MAIN_EVENING   (1 main + 2 shorts)
  10PM-11PM = SHORT_2        (1 short only)
  11PM-7AM  = SLEEP          (nothing)
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
TOPICS_FILE = os.path.join(PROJECT_ROOT, "logs", "topics_history.json")
DAILY_LOG_FILE = os.path.join(PROJECT_ROOT, "logs", "daily_log.json")
TOPIC_USAGE_FILE = os.path.join(PROJECT_ROOT, "logs", "topic_usage_today.json")

# Telegram creds from env
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = "8659664950"


def get_slot(now):
    h = now.hour
    if 7 <= h < 11:
        return "MAIN_MORNING"
    elif 11 <= h < 15:
        return "SHORT_1"
    elif 15 <= h < 18:
        return "REST"
    elif 18 <= h < 22:
        return "MAIN_EVENING"
    elif 22 <= h < 23:
        return "SHORT_2"
    else:
        return "SLEEP"


def load_topics():
    if not os.path.exists(TOPICS_FILE):
        return []
    with open(TOPICS_FILE) as f:
        return json.load(f).get("topics", [])


def load_daily_log():
    today = datetime.now(IST).strftime("%Y-%m-%d")
    if not os.path.exists(DAILY_LOG_FILE):
        return {"main_done": False, "shorts_done": 0, "topics_used": []}, today
    with open(DAILY_LOG_FILE) as f:
        log = json.load(f)
    return log.get(today, {"main_done": False, "shorts_done": 0, "topics_used": []}), today


def save_daily_log(log_entry, today):
    os.makedirs(os.path.dirname(DAILY_LOG_FILE), exist_ok=True)
    try:
        with open(DAILY_LOG_FILE) as f:
            full_log = json.load(f)
    except Exception:
        full_log = {}
    full_log[today] = log_entry
    with open(DAILY_LOG_FILE, "w") as f:
        json.dump(full_log, f, indent=2)


def load_topic_usage():
    if not os.path.exists(TOPIC_USAGE_FILE):
        return []
    with open(TOPIC_USAGE_FILE) as f:
        return json.load(f)


def save_topic_usage(used):
    os.makedirs(os.path.dirname(TOPIC_USAGE_FILE), exist_ok=True)
    with open(TOPIC_USAGE_FILE, "w") as f:
        json.dump(used, f, indent=2)


def pick_best_topic(topics, used_titles=None, min_score=5):
    """Pick highest-scored unpublished topic not yet used today."""
    if used_titles is None:
        used_titles = []
    unpublished = [
        t for t in topics
        if not t.get("published") and t.get("title", "") not in used_titles and t.get("score", 0) >= min_score
    ]
    if not unpublished:
        return None
    return unpublished[0]  # already sorted by score (descending from monitor)


def send_telegram(message):
    import urllib.request
    if not TELEGRAM_BOT_TOKEN:
        print("  [Telegram] No token, skipping.")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=15)
        result = json.loads(resp.read())
        if result.get("ok"):
            print("  Telegram sent.")
        else:
            print(f"  Telegram error: {result}")
    except Exception as e:
        print(f"  Telegram failed: {e}")


def run_build(topic_id, shorts_only=False):
    """Run build_topic.py for the given topic ID."""
    cmd = [sys.executable, os.path.join(PROJECT_ROOT, "build_topic.py"), topic_id]
    if shorts_only:
        cmd.append("--shorts-only")
    print(f"  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=600)
    output = result.stdout + result.stderr
    success = result.returncode == 0
    return success, output


def extract_video_id(output):
    import re
    for pat in [r'Video ID:\s+([a-zA-Z0-9_-]{11})', r'youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})']:
        m = re.search(pat, output)
        if m:
            return m.group(1)
    return None


def main():
    now = datetime.now(IST)
    now_str = now.strftime("%Y-%m-%d %H:%M IST")
    slot = get_slot(now)

    print(f"\n🎬 ViralDNA Smart Scheduler — {now_str}")
    print(f"   Slot: {slot}")

    # Sleep/Rest — do nothing
    if slot in ("SLEEP", "REST"):
        print(f"   Skipping — {slot} slot.")
        return

    # Load state
    topics = load_topics()
    if not topics:
        print("   No topics available. Waiting for monitor.")
        send_telegram(f"⚠️ ViralDNA: No topics in queue. Monitor may not have run.")
        return

    daily_log, today = load_daily_log()
    used_titles = load_topic_usage()

    # Determine what to produce
    if slot in ("MAIN_MORNING", "MAIN_EVENING"):
        if daily_log.get("main_done"):
            print("   Main already produced today. Skipping.")
            send_telegram(f"✅ ViralDNA: {slot.replace('_', ' ')} main already done today.")
            return
        shorts_only = False
        slot_label = slot.replace("_", " ").title()

    elif slot == "SHORT_1":
        if daily_log.get("shorts_done", 0) >= 2:
            print("   Already 2 shorts done today. Skipping.")
            return
        shorts_only = True
        slot_label = "Short #1 (12PM IST)"

    elif slot == "SHORT_2":
        if daily_log.get("shorts_done", 0) >= 2:
            print("   Already 2 shorts done today. Skipping.")
            return
        shorts_only = True
        slot_label = "Short #2 (9PM IST)"

    # Pick topic
    min_score = 4 if shorts_only else 6  # lower bar for shorts
    topic = pick_best_topic(topics, used_titles=used_titles, min_score=min_score)

    if not topic:
        print(f"   No unpublished topics with score >= {min_score}. Skipping.")
        send_telegram(f"⚠️ ViralDNA {slot_label}: No suitable topics. Min score: {min_score}")
        return

    topic_id = topic.get("id", "???")
    title = topic.get("title", "Unknown")
    score = topic.get("score", 0)
    source = topic.get("source", "?")

    print(f"   🎯 Selected: [{topic_id}] {title[:60]}")
    print(f"      Score: {score}/30 | Source: {source}")

    # Run build
    success, output = run_build(topic_id, shorts_only=shorts_only)

    if success:
        video_id = extract_video_id(output)
        yt_url = f"https://youtube.com/watch?v={video_id}" if video_id else "Check YouTube Studio"

        # Update daily log
        if shorts_only:
            daily_log["shorts_done"] = daily_log.get("shorts_done", 0) + 1
        else:
            daily_log["main_done"] = True
        daily_log["topics_used"] = daily_log.get("topics_used", []) + [topic_id]
        save_daily_log(daily_log, today)

        # Mark topic as used today
        used_titles.append(title)
        save_topic_usage(used_titles)

        # Telegram notification
        shorts_label = "📱 Short" if shorts_only else "🎥 Main Video"
        msg = (
            f"🎬 <b>ViralDNA — Published</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📅 {now_str}\n"
            f"📺 {shorts_label} | {slot_label}\n"
            f"🆔 {topic_id} | Score: {score}/30\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📰 <b>{title[:100]}</b>\n"
            f"🔗 {yt_url}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Today: {'✅' if daily_log.get('main_done') else '⏳'} Main | {daily_log.get('shorts_done', 0)}/2 Shorts"
        )
        send_telegram(msg)
        print(f"   ✅ Done! {yt_url}")

    else:
        print(f"   ❌ Build failed for {topic_id}")
        send_telegram(
            f"❌ <b>ViralDNA — Build Failed</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📅 {now_str}\n"
            f"🆔 {topic_id}: {title[:80]}\n"
            f"📊 Score: {score}/30\n"
            f"💡 Check logs or try: build_topic.py {topic_id}"
        )


if __name__ == "__main__":
    main()
