#!/usr/bin/env python3
"""
ViralDNA Mandatory Run (9AM / 7PM)
===================================
Pulls latest topics_history.json from GitHub Actions monitor,
picks the highest-scoring topic that was recently updated,
shows it for confirmation, then executes the pipeline.

Usage:
  python3 mandatory_run.py              # auto-pick highest scoring recent topic
  python3 mandatory_run.py --topic VDNA121  # override: pick specific topic
  python3 mandatory_run.py --dry-run    # show topic only, don't execute

Timing gate: only picks topics where the monitor's last_run is within
the last 30 minutes (i.e., the GitHub Actions monitor just ran and
updated topics_history.json). If stale, warns and exits.
"""
import sys
import os
import json
import subprocess
import argparse
from datetime import datetime, timezone, timedelta

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
TOPICS_FILE = os.path.join(PROJECT_ROOT, "logs", "topics_history.json")
TOPIC_FILE = os.path.join(PROJECT_ROOT, "logs", "injected_topic.json")

IST = timezone(timedelta(hours=5, minutes=30))

# How fresh must topics_history.json be (minutes)
MAX_STALENESS_MINUTES = 30


def git_pull() -> bool:
    """Pull latest topics_history.json from GitHub. Returns True if updated."""
    print("[Sync] Pulling latest topics_history.json from GitHub...")
    try:
        result = subprocess.run(
            ["git", "pull", "--quiet", "origin", "main"],
            cwd=PROJECT_ROOT, timeout=30, capture_output=True, text=True
        )
        if result.returncode == 0:
            print("  Git pull OK")
            return True
        else:
            print(f"  Git pull failed: {result.stderr.strip()}")
            return False
    except Exception as e:
        print(f"  Git pull error: {e}")
        return False


def load_topics() -> dict:
    if not os.path.exists(TOPICS_FILE):
        print("ERROR: topics_history.json not found")
        sys.exit(1)
    with open(TOPICS_FILE) as f:
        return json.load(f)


def check_freshness(data: dict) -> tuple[bool, str]:
    """Check if topics_history.json was recently updated by the monitor."""
    last_run_str = data.get("last_run")
    if not last_run_str:
        return False, "No last_run timestamp in topics_history.json"

    try:
        last_run = datetime.fromisoformat(last_run_str)
        now = datetime.now(IST)
        elapsed = (now - last_run).total_seconds() / 60.0

        if elapsed <= MAX_STALENESS_MINUTES:
            return True, f"topics_history.json is {elapsed:.0f} min old (fresh)"
        else:
            return False, (
                f"topics_history.json is {elapsed:.0f} min old "
                f"(stale — monitor last ran at {last_run_str}). "
                f"Max allowed: {MAX_STALENESS_MINUTES} min."
            )
    except Exception as e:
        return False, f"Could not parse last_run: {e}"


def find_highest_pending(data: dict) -> dict | None:
    """Find the highest-scoring topic that hasn't been published yet."""
    topics = data.get("topics", [])
    pending = data.get("pending_review", [])

    # Get IDs of pending (not yet produced) topics
    pending_ids = {p["id"] for p in pending}

    # Filter to unpublished topics with score >= 20
    candidates = [
        t for t in topics
        if t.get("id") in pending_ids
        and not t.get("published", False)
        and t.get("score", 0) >= 20
    ]

    if not candidates:
        return None

    # Sort by score descending, then by rescored_at descending (most recent first)
    candidates.sort(
        key=lambda x: (x.get("score", 0), x.get("rescored_at", "")),
        reverse=True
    )
    return candidates[0]


def confirm_topic(topic: dict) -> bool:
    """Display topic details and ask for confirmation."""
    score = topic.get("score", 0)
    title = topic.get("title", "")
    topic_id = topic.get("id", "")
    source = topic.get("source", "unknown")
    date = topic.get("date", "unknown")
    rescored_at = topic.get("rescored_at", "unknown")
    breakdown = topic.get("score_breakdown", topic.get("breakdown", []))
    breakdown_str = " | ".join(breakdown) if breakdown else "N/A"

    print()
    print("=" * 60)
    print("  MANDATORY RUN — TOPIC SELECTED")
    print("=" * 60)
    print(f"  ID:         {topic_id}")
    print(f"  Title:      {title}")
    print(f"  Score:      {score}/30")
    print(f"  Source:     {source}")
    print(f"  News Date:  {date}")
    print(f"  Rescored:   {rescored_at}")
    print(f"  Breakdown:  {breakdown_str}")
    print("=" * 60)
    print()

    # Non-interactive mode: auto-confirm
    if not sys.stdin.isatty():
        print("  [Non-interactive] Auto-confirming...")
        return True

    # Ask for confirmation
    while True:
        response = input("  Execute this topic? [y/n]: ").strip().lower()
        if response in ("y", "yes"):
            return True
        elif response in ("n", "no"):
            return False
        else:
            print("  Please enter 'y' or 'n'")


def execute_topic(topic: dict, dry_run: bool = False) -> int:
    """Write injected topic and run pipeline."""
    # Write injected_topic.json
    with open(TOPIC_FILE, "w") as f:
        json.dump(topic, f, indent=2)
    print(f"  Written to {TOPIC_FILE}")

    if dry_run:
        print("\n[DRY RUN] Topic selected but not executing pipeline.")
        return 0

    # Run pipeline
    entrypoint = os.path.join(PROJECT_ROOT, "run_pipeline_entrypoint.py")
    cmd = [sys.executable, entrypoint, "--mode", "normal", "--topic-file", TOPIC_FILE]
    print(f"\n[Pipeline] Launching: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    return result.returncode


def main():
    parser = argparse.ArgumentParser(description="ViralDNA Mandatory Run (9AM / 7PM)")
    parser.add_argument("--topic", type=str, default=None,
                        help="Override: pick specific topic ID instead of auto-select")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show selected topic only, don't execute pipeline")
    parser.add_argument("--force", action="store_true",
                        help="Skip freshness check (execute even if topics_history is stale)")
    args = parser.parse_args()

    now = datetime.now(IST)
    print("=" * 60)
    print(f"  ViralDNA Mandatory Run — {now.strftime('%Y-%m-%d %H:%M:%S IST')}")
    print("=" * 60)
    print()

    # Step 1: Git pull latest topics
    git_pull()
    print()

    # Step 2: Load topics
    data = load_topics()

    # Step 3: Freshness check (unless --force or --topic override)
    if not args.force and not args.topic:
        fresh, msg = check_freshness(data)
        print(f"[Freshness] {msg}")
        if not fresh:
            print("\n[ABORT] topics_history.json is too stale.")
            print("  The GitHub Actions monitor may not have run recently.")
            print("  Use --force to override, or --topic <ID> to pick manually.")
            sys.exit(1)
    print()

    # Step 4: Select topic
    if args.topic:
        # Manual override — find specific topic
        topic = None
        for t in data.get("topics", []):
            if t.get("id", "").upper() == args.topic.upper():
                topic = t
                break
        if not topic:
            print(f"ERROR: Topic {args.topic} not found in topics_history.json")
            print("\nAvailable topics (top 10 by score):")
            for t in sorted(data["topics"], key=lambda x: x.get("score", 0), reverse=True)[:10]:
                print(f"  {t['id']:8s} [{t.get('score', 0):2d}/30] {t['title'][:60]}")
            sys.exit(1)
        print(f"[Override] Using specified topic: {args.topic}")
    else:
        # Auto-pick highest scoring pending topic
        topic = find_highest_pending(data)
        if not topic:
            print("[Result] No pending topics with score >= 20 found.")
            print("  All topics have been produced or none are viral enough.")
            print("  Nothing to execute.")
            sys.exit(0)

    # Step 5: Confirm
    if not confirm_topic(topic):
        print("\n[CANCELLED] Topic not confirmed. Exiting.")
        sys.exit(0)

    # Step 6: Execute
    exit_code = execute_topic(topic, dry_run=args.dry_run)

    if exit_code == 0:
        print(f"\n[SUCCESS] Pipeline completed for {topic['id']}")
    else:
        print(f"\n[FAILED] Pipeline exited with code {exit_code} for {topic['id']}")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
