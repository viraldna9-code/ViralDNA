#!/usr/bin/env python3
"""
ViralDNA Topic Builder
======================
Called by Hermes when user types "VDNA007 Post" or "build VDNA007".

Usage:
    python3 build_topic.py VDNA007          # build specific topic by ID
    python3 build_topic.py --latest          # build highest-scored unpublished topic
    python3 build_topic.py --list            # list available topics with IDs

Reads logs/topics_history.json, finds the topic, writes to topic file,
runs the pipeline, and reports back.
"""

import json
import os
import sys
import subprocess
import glob
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
TOPICS_FILE = os.path.join(PROJECT_ROOT, "logs", "topics_history.json")
TOPIC_FILE_TMP = os.path.join(PROJECT_ROOT, "tmp_topic.json")
DAILY_USAGE_FILE = os.path.join(PROJECT_ROOT, "logs", "topic_usage_today.py")


def load_topics():
    if not os.path.exists(TOPICS_FILE):
        print("ERROR: topics_history.json not found. Run monitor first.")
        return []
    with open(TOPICS_FILE) as f:
        data = json.load(f)
    return data.get("topics", [])


def find_topic_by_id(topics, topic_id):
    """Find topic by VDNA ID (case-insensitive)."""
    topic_id_upper = topic_id.upper().strip()
    for t in topics:
        if t.get("id", "").upper() == topic_id_upper:
            return t
    # Also try partial match (user types "123" instead of "VDNA123")
    for t in topics:
        if topic_id_upper in t.get("id", "").upper():
            return t
    return None


def write_topic_file(topic):
    """Write topic to tmp_topic.json for pipeline consumption."""
    os.makedirs(os.path.dirname(TOPIC_FILE_TMP), exist_ok=True)
    with open(TOPIC_FILE_TMP, "w") as f:
        json.dump(topic, f, indent=2)
    print(f"  Topic written to {TOPIC_FILE_TMP}")


def extract_video_id_from_output(output):
    """Try to extract YouTube video ID from pipeline output."""
    import re
    patterns = [
        r'video_id["\s:]+([a-zA-Z0-9_-]{11})',
        r'youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})',
        r'youtu\.be/([a-zA-Z0-9_-]{11})',
        r'Upload successful.*?([a-zA-Z0-9_-]{11})',
    ]
    for pat in patterns:
        m = re.search(pat, output)
        if m:
            return m.group(1)
    return None


def count_shorts_in_dir(videos_dir):
    """Count how many short videos exist in the directory."""
    if not os.path.isdir(videos_dir):
        return 0
    return len(glob.glob(os.path.join(videos_dir, "production_short_*.mp4")))


def run_pipeline_for_topic(topic, shorts_only=False):
    """Run the multi-agent pipeline with the injected topic."""
    topic_id = topic.get("id", "???")
    title = topic.get("title", "Unknown")

    print(f"\n🎬 Building: [{topic_id}] {title[:60]}")
    print(f"   Source: {topic.get('source', '?')} | Score: {topic.get('score', 0)}/30")
    print(f"   Mode: {'shorts-only' if shorts_only else 'full (main + shorts)'}")
    print("-" * 50)

    write_topic_file(topic)

    cmd = [
        sys.executable,
        os.path.join(PROJECT_ROOT, "run_pipeline_entrypoint.py"),
        "--topic-file", TOPIC_FILE_TMP,
        "--mode", "normal",
    ]
    if shorts_only:
        cmd.append("--shorts-only")

    print(f"  Running pipeline...")
    result = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=600,  # 10 min timeout
    )

    stdout = result.stdout
    stderr = result.stderr

    if stdout:
        print(stdout[-3000:] if len(stdout) > 3000 else stdout)  # last 3000 chars

    if result.returncode != 0:
        print(f"\n  ❌ Pipeline FAILED (exit code {result.returncode})")
        if stderr:
            print(f"  Last stderr: {stderr[-500:]}")
        return False

    video_id = extract_video_id_from_output(stdout)
    if video_id:
        print(f"\n  ✅ Uploaded! Video ID: {video_id}")
        print(f"  🔗 https://youtube.com/watch?v={video_id}")
    else:
        print(f"\n  ⚠️ Pipeline completed but couldn't confirm upload.")
        print(f"  Check YouTube Studio manually.")

    return True


def mark_topic_published(topic_id):
    """Mark topic as published in topics_history.json."""
    with open(TOPICS_FILE) as f:
        data = json.load(f)
    for t in data.get("topics", []):
        if t.get("id", "").upper() == topic_id.upper():
            t["published"] = True
            t["published_at"] = datetime.now(IST).isoformat()
            break
    with open(TOPICS_FILE, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  📝 Topic {topic_id} marked as published")


def list_topics(topics):
    """Display available topics."""
    now = datetime.now(IST)
    print(f"\n📋 ViralDNA Topics — {now.strftime('%Y-%m-%d %H:%M IST')}")
    print("=" * 70)
    print(f"{'ID':<12} {'Score':>5}  {'Title'}")
    print("-" * 70)
    for t in topics[:20]:
        marker = "✅" if t.get("published") else "🆕"
        print(f"{marker} {t.get('id', 'N/A'):<10} {t.get('score', 0):>5}/30  {t.get('title', '')[:55]}")
    print(f"\nTotal: {len(topics)} topics | 🆕 = unpublished | ✅ = published")
    print(f"\nUsage: python3 build_topic.py VDNA007")
    print(f"       python3 build_topic.py VDNA007 --shorts-only")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nUsage: python3 build_topic.py <VDNA_ID> [--shorts-only]")
        print("       python3 build_topic.py --latest")
        print("       python3 build_topic.py --list")
        sys.exit(1)

    topics = load_topics()
    if not topics:
        print("No topics available. Wait for GitHub monitor to run.")
        sys.exit(1)

    arg = sys.argv[1].strip()

    if arg == "--list":
        list_topics(topics)
        sys.exit(0)

    if arg == "--latest":
        # Pick highest-scored unpublished topic
        unpublished = [t for t in topics if not t.get("published")]
        if not unpublished:
            print("All topics already published. Waiting for new ones.")
            sys.exit(0)
        topic = unpublished[0]  # already sorted by score
        print(f"  Auto-selected best unpublished topic:")
    else:
        # Find by ID
        topic = find_topic_by_id(topics, arg)
        if not topic:
            print(f"❌ Topic '{arg}' not found in topics_history.json")
            print(f"   Run 'python3 build_topic.py --list' to see available IDs")
            sys.exit(1)
        if topic.get("published"):
            print(f"⚠️ Topic {arg} was already published on {topic.get('published_at', 'unknown')}")
            print(f"   Still building it? That may create a duplicate.")
            # Continue anyway — user might want a remake

    shorts_only = "--shorts-only" in sys.argv

    success = run_pipeline_for_topic(topic, shorts_only=shorts_only)

    if success:
        mark_topic_published(topic.get("id", arg))
        print(f"\n✅ Done! [{topic.get('id', arg)}] published successfully.")
    else:
        print(f"\n❌ Failed to build [{topic.get('id', arg)}].")
        print(f"   Try again or pick a different topic.")
        sys.exit(1)


if __name__ == "__main__":
    main()
