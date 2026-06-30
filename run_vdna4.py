#!/home/jay/venv/bin/python3
"""
VDNA 4.0 — Clean Pipeline Entrypoint
=====================================
This is the primary entry point for the ViralDNA 4.0 pipeline.

It wraps VDNA4Director (modules/vdna4_director.py) which provides:
  - 11 main phases (0-10) + 6 validation sub-phases
  - STRICT MODE by default (no skipping phases)
  - FactoryWorker crash isolation
  - Checkpoint/resume (any phase can crash and resume)
  - Per-phase timeout enforcement
  - Growth feedback bus (load/inject/persist across 6 insertion points)
  - Data guard (anti-fabrication, pre-emptive inventory)
  - All 17 skill modules wired (deduplicated — fixed VDNA 3.0 duplicate-key bug)

Architecture:
    run_vdna4.py → VDNA4Director.run()
        ├── Phase 0:  Genesis            (cleanup + bus load + guard inventory)
        ├── Phase 1:  Discovery          (trend_discovery.py)
        ├── Phase 1.1: Discovery Validation
        ├── Phase 2:  Weighting          (post_filter.py / edge_scorer.py)
        ├── Phase 2.5: Quality Gate      (fact_checker + compliance)
        ├── Phase 3:  Scripting          (script_generator.py + NER + RAG)
        ├── Phase 3.5: Script Review     (length + entity verification)
        ├── Phase 4:  Voice              (RVC → gTTS fallback chain)
        ├── Phase 4.5: Voice Verify      (audio file + duration check)
        ├── Phase 5:  Thumbnail         (thumbnail_creator.py + CTR optimizer)
        ├── Phase 5.5: Thumb Validate    (dimensions + size check)
        ├── Phase 6:  Assembly           (video_assembler.py + renderer)
        ├── Phase 6.5: Assembly Verify   (ffprobe duration check)
        ├── Phase 7:  Forensic Audit    (forensic_audit.py)
        ├── Phase 8:  Upload            (youtube_uploader.py)
        ├── Phase 8.5: Upload Verify     (YouTube ID confirmed)
        └── Phase 9:  Post-Pipeline     (analytics + growth agents + blog + Telegram)

Modules NOT used in VDNA 4.0 (legacy/v80 monolith — do not call):
    - run_multi_agent_pipeline.py  (old 3687-line orchestrator)
    - daily_publish.py             (old cron script)
    - vdna2_director.py            (VDNA 3.0 director — kept for reference)

Usage:
    python3 run_vdna4.py                          # Full pipeline (strict mode)
    python3 run_vdna4.py --topic "Some News"      # Inject topic, skip discovery
    python3 run_vdna4.py --run-id 20260630_0900   # Custom run ID
    python3 run_vdna4.py --no-strict              # Disable strict (NOT recommended)

What changed from VDNA 3.0:
    1. Renamed VDNA2Director → VDNA4Director (correct class identity)
    2. Fixed 29 duplicate keys in skills dict (was silent last-write-wins bug)
    3. Fixed 8 duplicate import statements
    4. Strict mode ON by default — no phase can be silently skipped
    5. Added Phase 0 (Genesis) — formal bus load + guard inventory
    6. Added 6 validation sub-phases (1.1, 3.5, 4.5, 5.5, 6.5, 8.5)
    7. All prints say "VDNA 4.0" consistently
    8. FactoryWorker gained fallback propagation control
"""

import os
import sys
import argparse
from datetime import datetime, timezone, timedelta

# ── IST timezone ──────────────────────────────────────────────────────────
IST = timezone(timedelta(hours=5, minutes=30))

def now_ist():
    """Return current time in IST as a formatted string."""
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")

def now_ist_ts():
    """Return current IST datetime object."""
    return datetime.now(IST)

# ── Ensure project root is on sys.path ────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "modules"))

# ── Load .env ─────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    _env_path = os.path.expanduser("~/.env")
    if os.path.isfile(_env_path):
        load_dotenv(_env_path, override=True)
        print(f"[VDNA 4.0] Loaded env from {_env_path}")
except ImportError:
    print("[VDNA 4.0] python-dotenv not installed, reading env from system")


def main():
    parser = argparse.ArgumentParser(
        description="VDNA 4.0 — ViralDNA Strict Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 run_vdna4.py
  python3 run_vdna4.py --topic "Breaking News Headline"
  python3 run_vdna4.py --run-id 20260630_0900
  python3 run_vdna4.py --no-strict     (NOT recommended)
        """,
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Run ID for checkpoint/resume. Auto-generated if not set.",
    )
    parser.add_argument(
        "--topic",
        type=str,
        default=None,
        help="Inject a topic title string. Skips discovery phase.",
    )
    parser.add_argument(
        "--topic-file",
        type=str,
        default=None,
        help="Path to JSON file with pre-selected topic.",
    )
    parser.add_argument(
        "--no-strict",
        action="store_true",
        default=False,
        help="Disable strict mode. NOT recommended — phases may silently fail.",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  🧬 VIRALDNA 4.0 — Clean Pipeline Entrypoint")
    print("=" * 60)
    print(f"[Pipeline started: {now_ist()}]")

    # ── Check upload mode ──
    upload_enabled = os.environ.get("VIRALDNA_UPLOAD_ENABLED", "false").lower() == "true"
    print(f"[Config] Upload enabled: {upload_enabled}")
    if not upload_enabled:
        print("[Config] REVIEW MODE — videos will NOT be uploaded to YouTube")
        print("[Config] Set VIRALDNA_UPLOAD_ENABLED=true to enable uploads")

    # ── Load the Director ──
    try:
        from modules.vdna4_director import VDNA4Director
    except ImportError:
        # Fallback import path
        from vdna4_director import VDNA4Director

    # ── Initialize Director ──
    director = VDNA4Director(run_id=args.run_id, strict=not args.no_strict)

    # ── Prepare injected topic if provided ──
    injected_topic = None

    if args.topic_file:
        import json
        if os.path.exists(args.topic_file):
            with open(args.topic_file) as f:
                topic_data = json.load(f)
            if isinstance(topic_data, dict) and "title" in topic_data:
                injected_topic = topic_data
            elif isinstance(topic_data, list) and len(topic_data) > 0:
                injected_topic = topic_data[0]
            if injected_topic:
                print(f"[Inject] Topic from file: {injected_topic.get('title', 'Unknown')}")
            else:
                print(f"[Inject] WARNING: Could not parse topic from {args.topic_file}")
        else:
            print(f"[Inject] WARNING: Topic file not found: {args.topic_file}")

    elif args.topic:
        injected_topic = {"title": args.topic, "id": args.topic.replace(" ", "_")}
        print(f"[Inject] Topic from CLI: {args.topic}")

    # ── Run the pipeline ──
    try:
        result = director.run(injected_topic=injected_topic)
    except RuntimeError as e:
        print(f"\n[PIPELINE HALTED — STRICT MODE] {e}")
        sys.exit(2)

    # ── Summary ──
    compiled = result.get("compiled_videos", [])
    errors = result.get("errors", [])
    audit = result.get("audit_report", {})

    print("\n" + "=" * 60)
    print("  🧬 VIRALDNA 4.0 — EXECUTION SUMMARY")
    print("=" * 60)
    print(f"  Pipeline completed: {now_ist()}")
    print(f"  Strict mode: {'ON' if result.get('strict_mode') else 'OFF'}")
    print(f"  Videos produced: {len(compiled)}")
    for v in compiled:
        size = os.path.getsize(v) / (1024 * 1024) if os.path.exists(v) else 0
        print(f"    {os.path.basename(v)} ({size:.1f}MB)")
    print(f"  Errors: {len(errors)}")
    for e in errors:
        print(f"    {e}")
    if audit:
        print(f"  Health: {audit.get('health_score', '?')}/100")
    print("=" * 60)

    # Exit with error if no videos produced
    if not compiled:
        print("\n[FAIL] No videos produced. Check errors above.")
        sys.exit(1)

    print("\n[DONE] VDNA 4.0 pipeline complete.")
    sys.exit(0)


if __name__ == "__main__":
    main()
