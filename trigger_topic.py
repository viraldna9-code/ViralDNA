#!/usr/bin/env python3
"""
ViralDNA Topic Trigger — Single Unified Entry Point
====================================================
ONE script for ALL topic execution. Used by:
  - Manual trigger: python3 trigger_topic.py VDNA097
  - Telegram/OWL trigger: python3 trigger_topic.py VDNA097
  - Auto-publish: python3 trigger_topic.py --latest
  - List topics: python3 trigger_topic.py --list

Every path reads the SAME topics_history.json, writes the SAME injected topic file,
and calls the SAME pipeline entrypoint with the SAME flags.

Output: video package in Google Drive review folder.
"""
import sys, os, json, subprocess, argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

IST = timezone(timedelta(hours=5, minutes=30))
PROJECT_ROOT = Path(__file__).parent
LOGS = PROJECT_ROOT / "logs"

TOPICS_FILE   = LOGS / "topics_history.json"
TOPIC_FILE    = LOGS / "injected_topic.json"   # single injection file for pipeline
USAGE_FILE    = LOGS / "topic_usage_today.json"
DAILY_LOG     = LOGS / "daily_log.json"
ENTRYPOINT    = PROJECT_ROOT / "run_pipeline_entrypoint.py"

# ── Credentials ──
from dotenv import load_dotenv
load_dotenv(Path.home() / ".env")
TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT    = os.getenv("TELEGRAM_CHAT_ID", "")


# ═══════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════

def load_topics():
    if not TOPICS_FILE.exists():
        print("ERROR: topics_history.json not found. Run monitor first.")
        sys.exit(1)
    with open(TOPICS_FILE) as f:
        d = json.load(f)
    return d.get("topics", [])


def find_topic(topics, topic_id):
    tid = topic_id.upper().strip()
    for t in topics:
        if t.get("id", "").upper() == tid:
            return t
    # partial match
    for t in topics:
        if tid in t.get("id", "").upper():
            return t
    return None


def get_unpublished(topics):
    return [t for t in topics if not t.get("published")]


def load_json(path, default=None):
    if default is None:
        default = {}
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return default


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


def send_telegram(text):
    if not TOKEN or not CHAT:
        return
    import urllib.request
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
        urllib.request.urlopen(req, timeout=15)
    except Exception as e:
        print(f"  Telegram send failed: {e}")


def git_pull():
    """Pull latest topics_history.json from GitHub."""
    try:
        subprocess.run(
            ["git", "pull", "--quiet"],
            cwd=str(PROJECT_ROOT), timeout=30, check=True
        )
        print("  Git pull OK")
        return True
    except Exception as e:
        print(f"  Git pull failed (using local): {e}")
        return False


def git_commit_push(msg):
    """Commit and push changes back to GitHub."""
    try:
        subprocess.run(["git", "add", str(USAGE_FILE.relative_to(PROJECT_ROOT)),
                        str(DAILY_LOG.relative_to(PROJECT_ROOT)),
                        str(TOPIC_FILE.relative_to(PROJECT_ROOT))],
                       cwd=str(PROJECT_ROOT), timeout=10, check=True)
        subprocess.run(["git", "commit", "-m", msg, "--quiet"],
                       cwd=str(PROJECT_ROOT), timeout=15, check=True)
        subprocess.run(["git", "push", "--quiet"],
                       cwd=str(PROJECT_ROOT), timeout=30, check=True)
        print("  Git push OK")
        return True
    except Exception as e:
        print(f"  Git push failed: {e}")
        return False


# ═══════════════════════════════════════════
# DAILY QUOTA TRACKING
# ═══════════════════════════════════════════

def load_daily_log():
    log = load_json(DAILY_LOG)
    today = datetime.now(IST).strftime("%Y-%m-%d")
    if log.get("date") != today:
        log = {"date": today, "main_done": False, "shorts_done": 0, "used_ids": [], "used_titles": []}
    return log


def save_daily_log(log):
    save_json(DAILY_LOG, log)


def is_topic_used(log, topic_id):
    return topic_id.upper() in [u.upper() for u in log.get("used_ids", [])]


# ═══════════════════════════════════════════
# TOPIC INJECTION
# ═══════════════════════════════════════════

def write_injected_topic(topic):
    """Write topic to the single injection file that the pipeline reads."""
    save_json(TOPIC_FILE, topic)
    print(f"  Injected: {TOPIC_FILE}")


# ═══════════════════════════════════════════
# PIPELINE EXECUTION
# ═══════════════════════════════════════════

def run_pipeline(topic, mode="normal", shorts_only=False):
    """Run the multi-agent pipeline via the unified entrypoint."""
    topic_id = topic.get("id", "???")
    title = topic.get("title", "Unknown")

    write_injected_topic(topic)

    cmd = [sys.executable, str(ENTRYPOINT),
           "--mode", mode,
           "--topic-file", str(TOPIC_FILE)]
    if shorts_only:
        cmd.append("--shorts-only")

    print(f"\n  Running pipeline: {' '.join(cmd)}")
    print(f"  This takes 10-30 minutes...\n")

    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    return result.returncode == 0


def mark_published(topic_id):
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
    print(f"  Marked {topic_id} as published")


# ═══════════════════════════════════════════
# LIST TOPICS
# ═══════════════════════════════════════════

def list_topics(topics):
    unpub = get_unpublished(topics)
    now_str = datetime.now(IST).strftime('%Y-%m-%d %H:%M IST')
    print(f"\n  ViralDNA Topics — {now_str}")
    print(f"  {'='*60}")

    top = sorted(unpub, key=lambda x: x.get("score", 0), reverse=True)[:15]
    for t in top:
        score = t.get("score", 0)
        marker = "★" if score >= 20 else " "
        print(f"  {marker} [{score:2d}/30] {t.get('id','?'):10s} — {t.get('title','')[:48]}")

    print(f"\n  Total: {len(topics)} | Published: {len(topics)-len(unpub)} | Ready: {len(unpub)}")
    print(f"  ★ = score >= 20 (alert threshold)")
    print(f"\n  Run: python3 trigger_topic.py <ID>     (e.g. VDNA097)")
    print(f"       python3 trigger_topic.py --latest  (best unpublished)")
    return top


# ═══════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="ViralDNA Topic Trigger — Unified entry point for ALL topic execution",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 trigger_topic.py VDNA097           Build specific topic
  python3 trigger_topic.py VDNA097 --shorts  Build only shorts for topic
  python3 trigger_topic.py --latest          Build best unpublished topic
  python3 trigger_topic.py --latest --auto   Auto mode (for cron: no prompts)
  python3 trigger_topic.py --list            List available topics
        """
    )
    parser.add_argument("topic_id", nargs="?", help="Topic ID (e.g. VDNA097)")
    parser.add_argument("--mode", default="normal", choices=["normal", "primetime"],
                       help="Pipeline mode (default: normal)")
    parser.add_argument("--shorts", action="store_true", help="Shorts only (no main video)")
    parser.add_argument("--latest", action="store_true", help="Pick highest-scored unpublished topic")
    parser.add_argument("--list", action="store_true", help="List available topics")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen, don't execute")
    parser.add_argument("--auto", action="store_true", help="Auto mode: no interactive prompts (for cron)")
    parser.add_argument("--no-push", action="store_true", help="Don't git push after execution")

    args = parser.parse_args()

    # Pull latest topics first
    print("[Sync] Pulling latest topics from Git...")
    git_pull()

    # Reload topics after git pull
    all_topics = load_topics()
    if not all_topics:
        print("No topics available. Wait for monitor to discover topics.")
        sys.exit(1)

    # List mode
    if args.list:
        list_topics(all_topics)
        sys.exit(0)

    # Determine which topic to execute
    topic = None

    if args.latest:
        unpub = get_unpublished(all_topics)
        if not unpub:
            print("All topics published. Waiting for new ones.")
            sys.exit(0)
        unpub_sorted = sorted(unpub, key=lambda x: x.get("score", 0), reverse=True)
        topic = unpub_sorted[0]
        print(f"\n[Auto] Selected best unpublished topic:")
    elif args.topic_id:
        topic = find_topic(all_topics, args.topic_id)
        if not topic:
            print(f"ERROR: Topic '{args.topic_id}' not found.")
            print("Run 'python3 trigger_topic.py --list' to see available IDs.")
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)

    # Display topic info
    topic_id = topic.get("id", "???")
    title = topic.get("title", "Unknown")
    score = topic.get("score", 0)
    sb = topic.get("score_breakdown")
    breakdown_str = " | ".join(sb if sb is not None else topic.get("breakdown", []))
    source = topic.get("source", "unknown")

    print(f"  ID:       {topic_id}")
    print(f"  Title:    {title}")
    print(f"  Score:    {score}/30")
    print(f"  Breakdown: {breakdown_str}")
    print(f"  Source:   {source}")

    # Check if already published
    if topic.get("published"):
        print(f"\n  WARNING: Already published on {topic.get('published_at', 'unknown')}")
        if not args.auto:
            resp = input("  Re-publish? [y/N]: ").strip().lower()
            if resp != 'y':
                print("  Aborted.")
                sys.exit(0)

    # Daily quota check (only for non-shorts)
    if not args.shorts:
        log = load_daily_log()
        if log.get("main_done") and not args.auto:
            print("\n  WARNING: Main video already done for today.")
            resp = input("  Publish another main? [y/N]: ").strip().lower()
            if resp != 'y':
                print("  Aborted. Use --shorts for shorts-only build.")
                sys.exit(0)

    # Dry run
    if args.dry_run:
        print(f"\n[DRY RUN] Would execute: {topic_id} (mode={args.mode}, shorts={args.shorts})")
        sys.exit(0)

    # Confirm (unless auto mode)
    mode_str = args.mode + (" + shorts" if args.shorts else "")
    print(f"\n  ▶ Executing: [{topic_id}] {title[:50]}")
    print(f"    Mode: {mode_str}")

    if not args.auto:
        resp = input("\n  Proceed? [Y/n]: ").strip().lower()
        if resp == 'n':
            print("  Aborted.")
            sys.exit(0)

    # EXECUTE PIPELINE
    now_str = datetime.now(IST).strftime('%H:%M IST')
    send_telegram(f"<b>▶ ViralDNA Pipeline Started</b>\n<code>{now_str}</code>\n[{topic_id}] {title[:60]}\nMode: {mode_str}")

    success = run_pipeline(topic, mode=args.mode, shorts_only=args.shorts)

    if success:
        # Mark published
        mark_published(topic_id)

        # Update daily log
        log = load_daily_log()
        if args.shorts:
            log["shorts_done"] = log.get("shorts_done", 0) + 1
        else:
            log["main_done"] = True
        used_ids = log.get("used_ids", [])
        if topic_id.upper() not in [u.upper() for u in used_ids]:
            used_ids.append(topic_id)
        log["used_ids"] = used_ids
        save_daily_log(log)

        # Git push
        if not args.no_push:
            git_commit_push(f"trigger: {topic_id} published — {title[:40]}")

        # Telegram
        send_telegram(f"<b>✓ ViralDNA Pipeline Complete</b>\n[{topic_id}] {title[:60]}\nMode: {mode_str}\n📁 Check Google Drive Review folder")

        print(f"\n  ✓ [{topic_id}] Complete!")
    else:
        send_telegram(f"<b>✗ ViralDNA Pipeline FAILED</b>\n[{topic_id}] {title[:60]}\nCheck logs for errors.")
        print(f"\n  ✗ [{topic_id}] Pipeline failed. Check output logs.")
        sys.exit(1)


if __name__ == "__main__":
    main()
