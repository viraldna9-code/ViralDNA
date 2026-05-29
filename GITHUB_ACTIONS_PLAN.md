# ViralDNA — GitHub Actions Migration Plan
# ==========================================
# This directory contains the CI/CD configuration for running the
# ViralDNA pipeline on GitHub Actions (2000 min/month free Linux runners).
#
# ARCHITECTURE DECISIONS:
#   - RVC voice synthesis needs GPU → stays on local WSL
#   - GitHub Actions handles: Discovery → Upload (phases 1-3, 7-8)
#   - Voice + Assembly (phases 5-6) run locally on WSL via webhook trigger
#   - This file documents the full split; implement incrementally.
#
# SETUP STEPS:
#   1. Create GitHub repo (private recommended for credentials)
#   2. Add secrets (Settings → Secrets → Actions):
#        GEMINI_API_KEY       — Google AI Studio key
#        TELEGRAM_BOT_TOKEN   — Telegram bot token
#        TELEGRAM_CHAT_ID     — Telegram channel/group ID
#        YOUTUBE_CLIENT_SECRETS  — contents of client_secrets.json
#        YOUTUBE_TOKEN        — contents of youtube_token.json (refreshed)
#        DRIVE_BASE           — /home/jay/ViralDNA (or cloud path)
#   3. Push modules/ directory to repo
#   4. Copy Dockerfile and .github/ to repo root
#   5. Enable Actions in repo settings
#
# CRON SCHEDULE:
#   Spike check  : every 30 minutes (*/30 * * * *)
#   Primetime    : daily at 16:30 IST = 11:00 UTC (30 11 * * *)
#
# COST ANALYSIS:
#   Spike check  : ~2 min/run × 48 runs/day × 30 days = 2880 min/month
#                    → OVER LIMIT (2000 free). Solution: reduce to hourly = 1440 min/mo
#   Primetime    : ~10 min/run × 1 run/day × 30 days = 300 min/month
#   Total hourly : ~1740 min/month → within 2000 free limit ✓
#
# ALTERNATIVE FREE CLOUD (if GitHub Actions limit exceeded):
#   - Google Cloud Run: 2M requests/mo free, 360K GB-seconds
#   - Oracle Cloud Free Tier: 4 OCPU, 24GB ARM always free
#   - Fly.io: 3 shared-cpu VMs free

---

## FILES TO CREATE:

### 1. Dockerfile (for GitHub Actions self-hosted runner or cloud VM)
### 2. .github/workflows/spike-check.yml
### 3. .github/workflows/primetime-production.yml
### 4. .github/workflows/manual-trigger.yml

See template files below.
