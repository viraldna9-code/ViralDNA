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
    """Write credential files from GitHub Secrets (env vars) to disk."""
    cred_dir = "/app/ViralDNA/credentials"
    os.makedirs(cred_dir, exist_ok=True)

    # YouTube client secrets
    client_secrets = os.getenv("YOUTUBE_CLIENT_SECRETS")
    if client_secrets:
        with open(os.path.join(cred_dir, "client_secrets.json"), "w") as f:
            f.write(client_secrets)

    # YouTube token
    youtube_token = os.getenv("YOUTUBE_TOKEN")
    if youtube_token:
        with open(os.path.join(cred_dir, "youtube_token.json"), "w") as f:
            f.write(youtube_token)

    # Set DRIVE_BASE to container path
    os.environ["DRIVE_BASE"] = "/app/ViralDNA"

    print(f"[Setup] Credentials written to {cred_dir}")
    print(f"[Setup] DRIVE_BASE = {os.environ['DRIVE_BASE']}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["spike_check", "primetime", "normal"], default="normal")
    args = parser.parse_args()

    print(f"="*60)
    print(f"  ViralDNA Pipeline Entrypoint — Mode: {args.mode}")
    print(f"="*60)

    # Load credentials from env vars (GitHub Secrets)
    setup_credentials()

    # Import after creds are set up
    sys.path.insert(0, "/app/modules")
    from run_multi_agent_pipeline import MultiAgentOrchestrator

    orchestrator = MultiAgentOrchestrator()

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
