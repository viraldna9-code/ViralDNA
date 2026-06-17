#!/home/jay/venv/bin/python3
"""
VDNA 3.0 — Clean Pipeline Entrypoint
=====================================
This is the ONLY entry point for the ViralDNA pipeline.

It wraps the proven VDNA 2.0 Director (vdna2_director.py) which provides:
  - 9-phase pipeline with FactoryWorker crash isolation
  - Checkpoint/resume (any phase can crash and resume)
  - Per-phase timeout enforcement
  - Graceful degradation with fallback functions
  - Disk space monitoring
  - Signal handling (SIGTERM/SIGINT graceful shutdown)

Architecture:
    run_vdna3.py → VDNA2Director.run()
        ├── Phase 1:  Discovery        (trend_discovery.py v70.0)
        ├── Phase 2:  Weighting        (post_filter.py v71.0)
        ├── Phase 3:  Scripting        (script_generator.py v84.3)
        ├── Phase 4:  Voice            (voiceover.py v63.0)
        │             └─ Fallback: gTTS-only
        ├── Phase 5:  Visuals          (local_visual_generator.py v87.8 → visual_fetcher.py v70.0)
        │             └─ Fallback: local background gen
        ├── Phase 6:  Thumbnail       (thumbnail_creator.py v22.0)
        ├── Phase 7:  Assembly        (video_assembler.py v84.3)
        ├── Phase 8:  Forensic Audit  (forensic_audit.py)
        ├── Phase 9:  Upload          (youtube_uploader.py v1.8)
        │             └─ Skipped if VIRALDNA_UPLOAD_ENABLED=false
        └── Phase 10: Post-Pipeline   (analytics + Telegram notification)

Modules NOT used in VDNA 3.0 (legacy/v80 monolith — do not call):
    - run_multi_agent_pipeline.py  (old 3687-line orchestrator)
    - daily_publish.py             (old cron script)

Usage:
    python3 run_vdna3.py                          # Full pipeline
    python3 run_vdna3.py --topic "Some News"      # Inject topic, skip discovery
    python3 run_vdna3.py --run-id 20260615_0900   # Custom run ID

Environment variables (loaded from ~/.env):
    GEMINI_API_KEY       — Google AI Studio API key
    SERPER_API_KEY       — Serper search API key
    TELEGRAM_BOT_TOKEN   — Telegram bot token
    TELEGRAM_CHAT_ID     — Telegram chat ID
    VIRALDNA_UPLOAD_ENABLED — Set "true" to enable YouTube uploads (default: false)
"""

import os
import sys
import argparse

# ── Ensure project root is on sys.path ────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "modules"))

# ── Load .env (config.py also loads it, but we do it early for VIRALDNA_UPLOAD_ENABLED) ──
try:
    from dotenv import load_dotenv
    _env_path = os.path.expanduser("~/.env")
    if os.path.isfile(_env_path):
        load_dotenv(_env_path, override=True)
        print(f"[VDNA 3.0] Loaded env from {_env_path}")
except ImportError:
    print("[VDNA 3.0] python-dotenv not installed, reading env from system")


def main():
    parser = argparse.ArgumentParser(
        description="VDNA 3.0 — ViralDNA Clean Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 run_vdna3.py
  python3 run_vdna3.py --topic "Breaking News Headline"
  python3 run_vdna3.py --run-id 20260615_0900
        """,
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Run ID for checkpoint/resover. Auto-generated if not set.",
    )
    parser.add_argument(
        "--topic",
        type=str,
        default=None,
        help="Inject a topic title string. Skips discovery + weighting phases.",
    )
    parser.add_argument(
        "--topic-file",
        type=str,
        default=None,
        help="Path to JSON file with pre-selected topic (from monitor_cloud.py or build_topic.py).",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  VIRALDNA 3.0 — Clean Pipeline Entrypoint")
    print("=" * 60)

    # ── Check upload mode ──
    upload_enabled = os.environ.get("VIRALDNA_UPLOAD_ENABLED", "false").lower() == "true"
    print(f"[Config] Upload enabled: {upload_enabled}")
    if not upload_enabled:
        print("[Config] REVIEW MODE — videos will NOT be uploaded to YouTube")
        print("[Config] Set VIRALDNA_UPLOAD_ENABLED=true to enable uploads")

    # ── Load the Director ──
    try:
        from modules.vdna2_director import VDNA2Director
    except ImportError:
        # Fallback import path
        from vdna2_director import VDNA2Director

    # ── Initialize Director ──
    director = VDNA2Director(run_id=args.run_id)

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
    result = director.run(injected_topic=injected_topic)

    # ── Summary ──
    compiled = result.get("compiled_videos", [])
    errors = result.get("errors", [])

    print("\n" + "=" * 60)
    print("  VIRALDNA 3.0 — EXECUTION SUMMARY")
    print("=" * 60)
    print(f"  Videos produced: {len(compiled)}")
    for v in compiled:
        size = os.path.getsize(v) / (1024 * 1024) if os.path.exists(v) else 0
        print(f"    {os.path.basename(v)} ({size:.1f}MB)")
    print(f"  Errors: {len(errors)}")
    for e in errors:
        print(f"    {e}")
    print("=" * 60)

    # Exit with error if no videos produced
    if not compiled:
        print("\n[FAIL] No videos produced. Check errors above.")
        sys.exit(1)

    print("\n[DONE] Pipeline complete.")
    sys.exit(0)


if __name__ == "__main__":
    main()
