#!/usr/bin/env python3
"""
ViralDNA Local Pipeline Launcher
==================================
Usage:
  python3 run_local.py                  # default normal mode, 12h lookback
  python3 run_local.py --mode normal    # normal mode
  python3 run_local.py --mode primetime # primetime mode (12h lookback + telegram notify)
  python3 run_local.py --mode spike     # spike check only, no uploads
  python3 run_local.py --dry-run        # load orchestrator only, don't execute
  python3 run_local.py --preflight-only # run cleanup + validate, exit before pipeline
"""

import os
import sys
import argparse
import time

# ── Bootstrap ──
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
MODULES_DIR = os.path.join(PROJECT_ROOT, "modules")
sys.path.insert(0, MODULES_DIR)

# Load .env from project root or home
try:
    from dotenv import load_dotenv
    env_locations = [
        os.path.join(PROJECT_ROOT, ".env"),
        os.path.expanduser("~/.env"),
    ]
    for env_path in env_locations:
        if os.path.isfile(env_path):
            load_dotenv(env_path)
            print(f"[Bootstrap] Loaded .env: {env_path}")
            break
    else:
        print("[Bootstrap] WARNING: No .env file found — API keys must be in environment")
except ImportError:
    print("[Bootstrap] WARNING: python-dotenv not installed — relying on system env vars")


def preflight_cleanup(project_root: str) -> dict:
    """Delete temp files and stale outputs before pipeline run."""
    import glob
    import shutil

    cleaned = {"dirs": [], "files": [], "errors": []}

    # Clean temp directories
    temp_patterns = [
        os.path.join(project_root, "temp"),
        os.path.join(project_root, "tmp"),
        os.path.join(project_root, "output", "temp_*"),
        os.path.join(project_root, "output", "staging_*"),
        os.path.join(project_root, "_ffmpeg_temp_*"),
    ]

    for pattern in temp_patterns:
        for path in glob.glob(pattern):
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                    cleaned["dirs"].append(path)
                else:
                    os.remove(path)
                    cleaned["files"].append(path)
            except Exception as e:
                cleaned["errors"].append(f"{path}: {e}")

    # Clean temp file patterns in output
    file_patterns = [
        os.path.join(project_root, "output", "*.tmp"),
        os.path.join(project_root, "output", "*.part"),
        os.path.join(project_root, "output", "*_temp.*"),
    ]
    for pattern in file_patterns:
        for fpath in glob.glob(pattern):
            try:
                os.remove(fpath)
                cleaned["files"].append(fpath)
            except Exception as e:
                cleaned["errors"].append(f"{fpath}: {e}")

    return cleaned


def validate_environment() -> list:
    """Check that API keys and credentials exist."""
    issues = []

    # Check env vars
    required_keys = ["GEMINI_API_KEY", "SERPER_API_KEY"]
    for key in required_keys:
        val = os.getenv(key, "")
        if not val or len(val) < 10:
            issues.append(f"  MISSING or EMPTY: {key}")

    # Check credentials directory
    cred_dir = os.path.join(PROJECT_ROOT, "credentials")
    if not os.path.isdir(cred_dir):
        issues.append(f"  MISSING DIR: {cred_dir}")
    else:
        for fname in ["client_secrets.json", "youtube_token.json"]:
            fpath = os.path.join(cred_dir, fname)
            if not os.path.isfile(fpath):
                issues.append(f"  MISSING FILE: {fpath}")
            elif os.path.getsize(fpath) < 10:
                issues.append(f"  EMPTY FILE: {fpath}")

    return issues


def main():
    parser = argparse.ArgumentParser(description="ViralDNA Local Pipeline Launcher")
    parser.add_argument("--mode", choices=["normal", "primetime", "spike"],
                        default="normal", help="Pipeline run mode")
    parser.add_argument("--lookback", type=int, default=12,
                        help="Discovery lookback hours (default: 12)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Load and validate only, don't execute pipeline")
    parser.add_argument("--preflight-only", action="store_true",
                        help="Run cleanup + validation, exit before pipeline")
    parser.add_argument("--skip-cleanup", action="store_true",
                        help="Skip preflight cleanup")
    args = parser.parse_args()

    print("=" * 60)
    print("  ViralDNA Pipeline — Local Launcher")
    print("=" * 60)
    print(f"  Mode:     {args.mode}")
    print(f"  Project:  {PROJECT_ROOT}")
    print(f"  Time:     {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # ── Step 1: Preflight cleanup ──
    if not args.skip_cleanup:
        print("[Preflight] Cleaning temp files and stale outputs...")
        result = preflight_cleanup(PROJECT_ROOT)
        if result["dirs"]:
            print(f"  Removed {len(result['dirs'])} temp dirs")
            for d in result["dirs"][:5]:
                print(f"    - {d}")
        if result["files"]:
            print(f"  Removed {len(result['files'])} temp files")
        if result["errors"]:
            print(f"  Cleanup errors ({len(result['errors'])}):")
            for e in result["errors"][:5]:
                print(f"    ! {e}")
        if not result["dirs"] and not result["files"]:
            print("  Nothing to clean — already clean")
        print()
    else:
        print("[Preflight] Cleanup skipped (--skip-cleanup)")
        print()

    # ── Step 2: Validate environment ──
    print("[Preflight] Validating environment...")
    issues = validate_environment()
    if issues:
        print("  WARNINGS:")
        for issue in issues:
            print(f"    {issue}")
        print()
    else:
        print("  All checks passed.")
        print()

    if args.preflight_only:
        print("[Preflight] --preflight-only set — exiting before pipeline.")
        sys.exit(0)

    # ── Step 3: Import orchestrator ──
    print("[Pipeline] Loading orchestrator...")
    try:
        from run_multi_agent_pipeline import MultiAgentOrchestrator
        orchestrator = MultiAgentOrchestrator()
        orchestrator.state["lookback_hours"] = args.lookback
        print(f"  Orchestrator loaded OK.")
        print(f"  Agents: {len(orchestrator.pre_agents)} pre + "
              f"{len(orchestrator.task_agents)} task + "
              f"{len(orchestrator.integration_agents)} integration + "
              f"{len(orchestrator.post_agents)} post = "
              f"{len(orchestrator.pre_agents) + len(orchestrator.task_agents) + len(orchestrator.integration_agents) + len(orchestrator.post_agents)} total")
        print()
    except Exception as e:
        print(f"  FAILED to load orchestrator: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    if args.dry_run:
        print("[Dry Run] Orchestrator loaded successfully. Exiting.")
        sys.exit(0)

    # ── Step 4: Execute pipeline ──
    print("=" * 60)
    print(f"  EXECUTING PIPELINE — Mode: {args.mode}")
    print("=" * 60)
    print()

    try:
        if args.mode == "spike":
            orchestrator.execute_spike_check()
        elif args.mode == "primetime":
            orchestrator.execute_pipeline()
            orchestrator.send_telegram_notification(
                "✅ Local Run: Primetime Pipeline Complete.")
        else:
            orchestrator.execute_pipeline()
    except KeyboardInterrupt:
        print("\n\n[ABORT] Pipeline interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print(f"\n[FATAL] Pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print()
    print("=" * 60)
    print("  PIPELINE COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
