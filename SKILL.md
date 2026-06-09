# ViralDNA — Project Skill

## What is ViralDNA?

ViralDNA is an automated AI video production pipeline that creates YouTube videos from trending news topics. It runs on Hermes Agent (WSL/Linux) and produces:

- **Long-form videos** (8-15 min) — main channel content
- **YouTube Shorts** (30-60 sec) — 2 per topic, staggered 30min from main
- **Thumbnails** — CTR-optimized with bold text overlays
- **Voiceover** — gTTS (default) or RVC custom voice (jay_voice_prod.pth)

## Architecture

```
run_pipeline_entrypoint.py     ← Cron entry point
modules/run_multi_agent_pipeline.py  ← Main orchestrator (~3500 lines)
modules/config.py              ← Central config (PIPELINE_VERSION = "v85.1")
modules/approval_gate.py       ← Semi-auto approval via Telegram
upload_approved.py             ← Handles approved uploads with scheduling
scripts/daily_report.py        ← Daily/weekly analytics reports
```

### Agent Pipeline (in order)

**Pre-agents:** TopicDiscovery, TopicWeighting, ScriptGenerator, FactCheck, Compliance, AdFriendly

**Integration gates (13):** DiscoveryWeightingIntegration, WeightingScriptingIntegration, ScriptingComplianceIntegration, FactCheckComplianceIntegration, ComplianceAdFriendlyIntegration, ComplianceVoiceIntegration, VoiceVisualIntegration, VisualThumbnailIntegration, ThumbnailAssemblyIntegration, CTROptimizationIntegration, AssemblyUploadIntegration, ForensicAuditUploadIntegration, UploadFeedbackIntegration

**Task agents:** VoiceAgent, VisualAgent, ThumbnailAgent, CTRAgent, AssemblyAgent, ForensicAuditAgent, UploaderAgent

**Post-agents:** FeedbackAgent, YouTubeAnalyticsAgent, CommunityEngagementAgent, etc.

## Key Configuration

| Setting | Value |
|---------|-------|
| `PIPELINE_VERSION` | `v85.1` (in `modules/config.py`) |
| `VIRALDNA_UPLOAD_ENABLED` | `false` (permanent ban) |
| YouTube channel | "The ViralDNA" |
| Category | 25 (News & Politics) |
| Privacy | Private with scheduled premiere |
| TTS | gTTS (soft-fail per segment) |
| Python venv | `/home/jay/venv/bin/python3` |

## Cron Jobs (5 total)

| Job | Schedule | Purpose |
|-----|----------|---------|
| Morning Publish | 9AM IST (3:30AM UTC) | Run pipeline → approval gate |
| Evening Publish | 7PM IST (1:30PM UTC) | Run pipeline → approval gate |
| Channel Health Monitor | Every 2h | Check channel stats → Telegram |
| Daily Analytics | 6AM IST daily | Daily report → Telegram |
| Weekly Analytics | Sunday 6AM IST | Weekly report → Telegram |

All deliver to `telegram:8659664950`.

## Approval Gate Workflow

1. Pipeline finishes → `send_approval_request()` in `approval_gate.py`
2. Telegram sends photo + metadata + publish schedule to Jay
3. Jay replies `/approve <topic_id>` or `/reject <topic_id>`
4. `upload_approved.py --upload <token>` handles upload with `publishAt`

**Publish schedule (shown in approval message):**
- Morning: Main 9AM IST, Short1 9:30AM, Short2 10AM IST
- Evening: Main 7PM IST, Short1 7:30PM, Short2 8PM IST

## Important Rules

1. **NEVER auto-upload.** `VIRALDNA_UPLOAD_ENABLED=false` always. Jay must approve.
2. **NEVER delete YouTube videos.** Permanent no-delete policy (May 2026).
3. **Always update CHANGELOG.md** after any change + send Telegram summary to Jay.
4. **Use venv python:** `/home/jay/venv/bin/python3` for all pipeline operations.
5. **topics_history.json** uses `{"topics": [...]}` structure (not flat list).

## File Locations

| Path | Purpose |
|------|---------|
| `/home/jay/ViralDNA/` | Project root |
| `/home/jay/ViralDNA/modules/` | Pipeline modules (no test files) |
| `/home/jay/ViralDNA/tests/` | Test files (moved from modules/) |
| `/home/jay/ViralDNA/scripts/` | Utility scripts (daily_report.py, etc.) |
| `/home/jay/ViralDNA/logs/` | Runtime logs, topics_history.json |
| `/home/jay/ViralDNA/output/` | Generated videos, thumbnails |
| `/home/jay/ViralDNA/credentials/` | YouTube token, API keys |
| `/home/jay/ViralDNA/CHANGELOG.md` | Change log (mandatory updates) |
| `/home/jay/.hermes/cron/jobs.json` | Cron job definitions |
| `/home/jay/.env` | Environment variables (Telegram, API keys) |

## Common Operations

### Run pipeline manually
```bash
cd /home/jay/ViralDNA
/home/jay/venv/bin/python3 run_pipeline_entrypoint.py
```

### Upload approved video
```bash
cd /home/jay/ViralDNA
/home/jay/venv/bin/python3 upload_approved.py --upload <approval_token>
```

### Generate daily report
```bash
cd /home/jay/ViralDNA
/home/jay/venv/bin/python3 scripts/daily_report.py --mode daily
/home/jay/venv/bin/python3 scripts/daily_report.py --mode weekly
```

### Check channel health
```bash
cd /home/jay/ViralDNA
/home/jay/venv/bin/python3 vdna_health_check.py
```

### Refresh YouTube token
```bash
cd /home/jay/ViralDNA
/home/jay/venv/bin/python3 -c "
from upload_approved import refresh_token_if_needed
refresh_token_if_needed()
"
```

## Troubleshooting

- **YouTube token expired:** Run refresh via `upload_approved.py` or re-auth with OAuth
- **Serper image fetch fails:** Backup key fallback uses `SERPER_BACKUP_API_KEY` env var
- **gTTS fails:** Soft-fail per segment — pipeline continues with next segment
- **Cron job fails:** Check `~/.hermes/cron/jobs.json` for correct venv python path
- **topics_history.json parse error:** Ensure `{"topics": [...]}` structure, not flat list

## Version History

- **v85.1** (Jun 9, 2026): Implemented all 13 integration agents with real validation logic, added Serper backup key fallback, unified PIPELINE_VERSION in config.py, fixed NOTIFICATION_CONFIG telegram enabled=True, added publish schedule to approval Telegram message, added comment_threads scope to YouTube OAuth, refreshed YouTube token, added --mode weekly to daily_report.py, moved 21 test files from modules/ to tests/
- **v85.0** (Jun 8, 2026): Semi-auto approval gate, cron jobs resumed
- **v84.3** (Jun 2026): YouTube style overhaul
- **v84.2** (Jun 2026): YouTube style overhaul
- **v83.0** (Jun 2026): FactCheckAgent improvements
