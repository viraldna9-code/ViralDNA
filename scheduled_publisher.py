#!/usr/bin/env python3
"""
ViralDNA Scheduled Publisher
=============================
Runs at fixed times to pick the next unpublished topic and execute the pipeline.

Schedule (IST):
  Morning:  7:00 AM  →  Publish at 9:00 AM
  Evening:  5:00 PM  →  Publish at 7:00 PM

Logic:
  1. Load topics_history.json
  2. Find next unpublished topic (sorted by final_score)
  3. Run execute_topic.py <topic_id>
  4. Mark topic as scheduled with publish time

Usage:
  python3 scheduled_publisher.py morning   # 7 AM cron
  python3 scheduled_publisher.py evening   # 5 PM cron
  python3 scheduled_publisher.py --next    # Dry run: show what would be picked
"""

import json
import os
import sys
import subprocess
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
TOPICS_FILE = os.path.join(PROJECT_ROOT, "logs", "topics_history.json")
SCHEDULE_LOG = os.path.join(PROJECT_ROOT, "logs", "schedule_log.json")

# Publish times (IST)
PUBLISH_TIMES = {
    "morning": {
        "start": 7,       # Pipeline starts at 7 AM
        "publish_hour": 9, # Video published/scheduled at 9 AM
        "label": "Morning (9AM)",
    },
    "evening": {
        "start": 17,      # Pipeline starts at 5 PM
        "publish_hour": 19,  # Video published/scheduled at 7 PM
        "label": "Evening (7PM)",
    },
}


def load_topics():
    """Load topics_history.json."""
    try:
        with open(TOPICS_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        print("ERROR: topics_history.json not found")
        sys.exit(1)


def save_topics(data):
    """Save topics_history.json."""
    with open(TOPICS_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_next_unpublished_topic(topics):
    """Find the next unpublished topic, sorted by final_score (highest first)."""
    unpublished = []
    for t in topics:
        if not t.get("published", False):
            unpublished.append(t)

    if not unpublished:
        return None

    # Sort by final_score (base + edge), then by score as fallback
    unpublished.sort(
        key=lambda x: x.get("final_score", x.get("score", 0)),
        reverse=True,
    )
    return unpublished[0]


def log_schedule(topic_id, slot, publish_time):
    """Log schedule to schedule_log.json."""
    try:
        with open(SCHEDULE_LOG) as f:
            log = json.load(f)
    except FileNotFoundError:
        log = {"entries": []}

    log["entries"].append({
        "timestamp": datetime.now(IST).isoformat(),
        "topic_id": topic_id,
        "slot": slot,
        "publish_time": publish_time.isoformat(),
        "status": "started",
    })

    # Keep last 100 entries
    log["entries"] = log["entries"][-100:]
    with open(SCHEDULE_LOG, "w") as f:
        json.dump(log, f, indent=2)


def main():
    now = datetime.now(IST)
    dry_run = "--next" in sys.argv

    if dry_run:
        # Show what would be picked
        data = load_topics()
        topics = data.get("topics", [])
        topic = get_next_unpublished_topic(topics)

        if not topic:
            print("No unpublished topics available.")
            return

        tid = topic.get("id", "???")
        score = topic.get("score", 0)
        edge = topic.get("edge_score", 0)
        final = topic.get("final_score", score)
        title = topic.get("title", "")

        print(f"Next topic to publish:")
        print(f"  ID:     {tid}")
        print(f"  Score:  {score} + {edge:.1f} = {final:.1f}")
        print(f"  Title:  {title}")

        # Also show upcoming queue
        unpublished = [t for t in topics if not t.get("published", False)]
        unpublished.sort(key=lambda x: x.get("final_score", x.get("score", 0)), reverse=True)
        print(f"\nQueue ({len(unpublished)} unpublished):")
        print(f"  {'ID':<10} {'Final':>6}  Title")
        print(f"  {'---':<10} {'---':>6}  ---")
        for t in unpublished[:10]:
            t_id = t.get("id", "???")
            t_final = t.get("final_score", t.get("score", 0))
            t_title = t.get("title", "")[:60]
            marker = " ← NEXT" if t_id == tid else ""
            print(f"  {t_id:<10} {t_final:>6.1f}  {t_title}{marker}")
        return

    # Determine slot
    slot = None
    for arg in sys.argv[1:]:
        if arg in PUBLISH_TIMES:
            slot = arg
            break

    if not slot:
        # Auto-detect based on current hour
        hour = now.hour
        if 6 <= hour < 12:
            slot = "morning"
        elif 16 <= hour < 20:
            slot = "evening"
        else:
            print(f"ERROR: Current hour {hour} doesn't match any scheduled slot")
            print("Usage: python3 scheduled_publisher.py morning|evening")
            sys.exit(1)

    slot_config = PUBLISH_TIMES[slot]
    publish_time = now.replace(
        hour=slot_config["publish_hour"],
        minute=0, second=0, microsecond=0,
    )

    print(f"═══════════════════════════════════════════════")
    print(f"  ViralDNA Scheduled Publisher — {slot_config['label']}")
    print(f"  {now.strftime('%Y-%m-%d %H:%M IST')}")
    print(f"  Publish target: {publish_time.strftime('%H:%M IST')}")
    print(f"═══════════════════════════════════════════════")

    # Pick next topic
    data = load_topics()
    topics = data.get("topics", [])
    topic = get_next_unpublished_topic(topics)

    if not topic:
        print("\nNo unpublished topics available. Nothing to do.")
        return

    tid = topic.get("id", "???")
    score = topic.get("score", 0)
    edge = topic.get("edge_score", 0)
    final = topic.get("final_score", score)
    title = topic.get("title", "")

    print(f"\n  Selected: {tid}")
    print(f"  Score:    {score} + {edge:.1f} = {final:.1f}")
    print(f"  Title:    {title}")
    print(f"  Publish:  {publish_time.strftime('%H:%M IST')}")

    # Mark topic as scheduled
    for t in topics:
        if t.get("id") == tid:
            t["scheduled"] = True
            t["scheduled_slot"] = slot
            t["scheduled_at"] = now.isoformat()
            t["publish_target"] = publish_time.isoformat()
            break
    save_topics(data)

    # Log it
    log_schedule(tid, slot, publish_time)

    print(f"\n  Starting pipeline for {tid}...")
    print(f"  ───────────────────────────────────────────────")

    # Run the pipeline
    result = subprocess.run(
        [sys.executable, os.path.join(PROJECT_ROOT, "execute_topic.py"), tid],
        cwd=PROJECT_ROOT,
        capture_output=False,  # Stream output live
    )

    if result.returncode == 0:
        print(f"\n  ✅ Pipeline completed for {tid}")
    else:
        print(f"\n  ❌ Pipeline FAILED for {tid} (exit code {result.returncode})")


if __name__ == "__main__":
    main()
