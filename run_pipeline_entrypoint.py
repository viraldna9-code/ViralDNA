#!/usr/bin/env python3
"""
ViralDNA Pipeline Entrypoint for GitHub Actions / Docker
========================================================
Selects which pipeline mode to run based on --mode argument.
Downloads credentials from GitHub Secrets (injected as env vars as JSON files).

Usage:
  python3 run_pipeline_entrypoint.py --mode spike_check
  python3 run_pipeline_entrypoint.py --mode primetime
  python3 run_pipeline_entrypoint.py --mode normal

Note: This entrypoint uses run_multi_agent_pipeline (v80.0+).
"""

import os
import sys
import json
import argparse

def setup_credentials():
    """Write credential files from env vars to disk.
    In Docker/GitHub Actions: uses env vars injected from secrets.
    Locally: credentials already exist on disk, just verify paths."""
    # Detect local vs Docker
    if os.path.exists("/app/ViralDNA"):
        cred_dir = "/app/ViralDNA/credentials"
    elif os.path.exists(os.path.expanduser("~/ViralDNA")):
        cred_dir = os.path.expanduser("~/ViralDNA/credentials")
    else:
        cred_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "credentials")

    os.makedirs(cred_dir, exist_ok=True)

    # In Docker/GitHub Actions, write from env vars
    client_secrets = os.getenv("YOUTUBE_CLIENT_SECRETS")
    if client_secrets:
        with open(os.path.join(cred_dir, "client_secrets.json"), "w") as f:
            f.write(client_secrets)

    youtube_token = os.getenv("YOUTUBE_TOKEN")
    if youtube_token:
        with open(os.path.join(cred_dir, "youtube_token.json"), "w") as f:
            f.write(youtube_token)

    # Set DRIVE_BASE
    os.environ["DRIVE_BASE"] = os.path.dirname(cred_dir)

    print(f"[Setup] Credentials dir: {cred_dir}")
    print(f"[Setup] DRIVE_BASE = {os.environ['DRIVE_BASE']}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["spike_check", "primetime", "normal"], default="normal")
    parser.add_argument("--topic-file", type=str, default=None,
                        help="Path to a JSON file with pre-selected topic (from monitor_cloud.py topics_history.json). "
                             "Skips discovery/weighting, goes straight to production.")
    parser.add_argument("--shorts-only", action="store_true",
                        help="Only produce shorts, skip main video")
    args = parser.parse_args()

    print(f"="*60)
    print(f"  ViralDNA Pipeline Entrypoint — Mode: {args.mode}")
    print(f"="*60)

    # Load credentials from env vars (GitHub Secrets)
    setup_credentials()

    # Import after creds are set up
    drive_base = os.environ.get("DRIVE_BASE", "")
    if os.path.exists("/app/modules"):
        sys.path.insert(0, "/app/modules")
    elif drive_base:
        sys.path.insert(0, os.path.join(drive_base, "modules"))
    else:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "modules"))
    from run_multi_agent_pipeline import MultiAgentOrchestrator

    orchestrator = MultiAgentOrchestrator()

    # If topic file provided, inject pre-selected topic into state
    if args.topic_file:
        if os.path.exists(args.topic_file):
            with open(args.topic_file) as f:
                topic_data = json.load(f)
            if isinstance(topic_data, dict) and "title" in topic_data:
                topic = topic_data
            elif isinstance(topic_data, list) and len(topic_data) > 0:
                topic = topic_data[0]
            else:
                print(f"  ⚠️ Could not parse topic from {args.topic_file}")
                topic = None
            if topic:
                orchestrator.state["injected_topic"] = topic
                print(f"  Injected topic: {topic.get('title', 'Unknown')}")
        else:
            print(f"  ⚠️ Topic file not found: {args.topic_file}")

    if args.shorts_only:
        orchestrator.state["shorts_only"] = True
        print("  Shorts-only mode: main video will be skipped")

    if args.mode == "spike_check":
        orchestrator.execute_spike_check()
    elif args.mode == "primetime":
        orchestrator.state["lookback_hours"] = 12
        orchestrator.execute_pipeline()
        orchestrator.send_telegram_notification("✅ GH Actions: Primetime Pipeline Complete.")
    else:
        orchestrator.state["lookback_hours"] = 12
        orchestrator.execute_pipeline()

if __name__ == "__main__":
    main()
