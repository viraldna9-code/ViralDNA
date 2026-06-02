#!/usr/bin/env python3
"""
ViralDNA Topic Executor — Execute pipeline for a specific topic from alert.
Usage: python3 execute_topic.py VDNA042 [--mode normal|primetime]
"""
import sys, os, json, subprocess, argparse
from pathlib import Path

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
TOPICS_FILE = os.path.join(PROJECT_ROOT, "logs", "topics_history.json")
TOPIC_FILE = os.path.join(PROJECT_ROOT, "logs", "injected_topic.json")

def load_topics():
    if not os.path.exists(TOPICS_FILE):
        print("ERROR: topics_history.json not found")
        sys.exit(1)
    with open(TOPICS_FILE) as f:
        return json.load(f)

def find_topic(data, topic_id):
    for t in data.get("topics", []):
        if t.get("id", "").upper() == topic_id.upper():
            return t
    return None

def main():
    parser = argparse.ArgumentParser(description="Execute pipeline for a specific topic")
    parser.add_argument("topic_id", help="Topic ID (e.g. VDNA042)")
    parser.add_argument("--mode", default="normal", choices=["normal", "primetime", "spike"])
    parser.add_argument("--dry-run", action="store_true", help="Look up topic and show info, don't execute")
    args = parser.parse_args()

    # Git pull first to get latest topics_history.json
    print("[Sync] Pulling latest topics from Git...")
    try:
        subprocess.run(["git", "pull", "--quiet"], cwd=PROJECT_ROOT, timeout=30, check=True)
        print("  Git pull OK")
    except Exception as e:
        print(f"  Git pull failed (using local): {e}")

    # Find topic
    data = load_topics()
    topic = find_topic(data, args.topic_id)
    if not topic:
        print(f"\nERROR: Topic {args.topic_id} not found in topics_history.json")
        print("\nAvailable topics (top 10 by score):")
        for t in sorted(data["topics"], key=lambda x: x.get("score",0), reverse=True)[:10]:
            print(f"  {t['id']:8s} [{t.get('score',0):2d}/30] {t['title'][:60]}")
        sys.exit(1)

    # Confirm
    score = topic.get("score", 0)
    title = topic.get("title", "")
    sb = topic.get("score_breakdown")
    breakdown = " | ".join(sb if sb is not None else topic.get("breakdown", []))
    source = topic.get("source", "unknown")

    print(f"\n{'='*50}")
    print(f"  Topic:    {title}")
    print(f"  ID:       {topic['id']}")
    print(f"  Score:    {score}/30")
    print(f"  Source:   {source}")
    print(f"  Break:    {breakdown}")
    print(f"  Mode:     {args.mode}")
    print(f"{'='*50}")

    # Write injected_topic.json
    with open(TOPIC_FILE, "w") as f:
        json.dump(topic, f, indent=2)
    print(f"\n[OK] Written to {TOPIC_FILE}")

    if args.dry_run:
        print("\n[DRY RUN] Topic found and written. Not executing pipeline.")
        sys.exit(0)

    # Run pipeline via entrypoint that supports --topic-file injection
    entrypoint = os.path.join(PROJECT_ROOT, "run_pipeline_entrypoint.py")
    cmd = [sys.executable, entrypoint, "--mode", args.mode, "--topic-file", TOPIC_FILE]
    print(f"\n[Pipeline] Launching: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    sys.exit(result.returncode)

if __name__ == "__main__":
    main()
