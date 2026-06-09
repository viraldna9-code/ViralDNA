# ViralDNA Change Log

Every significant change is logged here AND sent to Telegram.
Format: `STATUS | DATE | WHAT | DETAIL`

---

## 2026-06-09

### 16:30 IST — v85.1 Audit Fixes (10 fixes)
- **FIXED** YouTube token refresh — token was expired (2026-06-09T10:15:56 UTC). Refreshed and verified (8 subs, 30 videos, 13345 views).
- **ADDED** `https://www.googleapis.com/auth/youtube.commentThreads` scope to YOUTUBE_SCOPES in `run_multi_agent_pipeline.py` and `upload_approved.py`. Requires re-authorization on next OAuth flow.
- **IMPLEMENTED** all 13 integration agents with real validation logic (were stubs that just returned state):
  - `DiscoveryWeightingIntegration` — validates raw_news has articles
  - `WeightingScriptingIntegration` — validates weighted_topics has entries
  - `ScriptingComplianceIntegration` — validates script exists
  - `FactCheckComplianceIntegration` — BLOCKS pipeline if fact-check failed
  - `ComplianceAdFriendlyIntegration` — validates compliance before ad-friendly
  - `ComplianceVoiceIntegration` — validates compliance before voice synthesis
  - `VoiceVisualIntegration` — validates voice duration vs visual scenes
  - `VisualThumbnailIntegration` — validates visuals before thumbnail creation
  - `ThumbnailAssemblyIntegration` — validates thumbnail exists before assembly
  - `CTROptimizationIntegration` — validates CTR-optimized thumbnail and title
  - `AssemblyUploadIntegration` — validates video file exists before upload
  - `ForensicAuditUploadIntegration` — validates forensic audit passed
  - `UploadFeedbackIntegration` — validates upload result
- **FIXED** `NOTIFICATION_CONFIG["telegram"]["enabled"]` → `True` in `config.py` (was `False`, misleading)
- **ADDED** publish schedule to approval Telegram message (Main 9AM/7PM, Shorts +30min)
- **ADDED** Serper backup key fallback in `video_assembler.py` — tries `SERPER_BACKUP_API_KEY` if primary fails
- **ADDED** `PIPELINE_VERSION = "v85.1"` to `config.py` — unified version constant (previously scattered v1.0-v84.3)
- **ADDED** `--mode weekly` support to `scripts/daily_report.py` (weekly cron was failing — script didn't support the flag)
- **MOVED** 21 test files from `modules/` to `tests/` (proper separation)
- **ADDED** `SKILL.md` — project documentation with architecture, config, cron jobs, troubleshooting
- **REMOVED** duplicate integration agent definitions (file had two sections with overlapping classes)

### 15:45 IST — Infrastructure Additions
- **ADDED** `vdna_health_check.py` — System health check script (disk, env, deps, imports, cron, queue, YouTube, credentials). Supports `--json` and `--quiet`.
- **ADDED** `dashboard/generate_dashboard.py` — Live dashboard generator. Produces `dashboard/index.html` with real-time cron, topics, YouTube, env data. Auto-refreshes 60s.
- **ADDED** `opencv-python-headless` to venv — was missing, needed by cv2 in visual_fetcher and video_assembler.
- **UPDATED** Cron Morning/Evening/Monitor prompts — changed `python3` → `/home/jay/venv/bin/python3` so gTTS and all deps are available.
- **FIXED** `send_telegram_notification()` in `run_multi_agent_pipeline.py` — added `load_dotenv("~/.env")` so it reads token/chat_id in cron context.
- **PURGED** VDNA200 stale approval queue entry (missing video/thumb files).
- **CLEANED** Old validation log files from `output/runtime/` (88KB).
- **COMMIT** `85167fe` — health check + dashboard
- **COMMIT** `4708dc2` — telegram dotenv fix
- **SCORE** Evening Publish reliability: 8.5/10 (was 6.5 before fixes)

### 2026-06-08
- **ADDED** Semi-auto approval gate (v85.0) — pipeline → Telegram → manual /approve → upload
- **RESUMED** Morning + Evening cron jobs
- **FIXED** ResilientUploader `'str' object has no attribute 'get'` bug (line 1184 isinstance check)
- **REPLACED** edge-tts → gTTS in voiceover.py (edge-tts broken by Microsoft)
- **COMMIT** `cc8dc54` — gTTS switch

## 2026-06-07
- **ADDED** YouTube Studio long video style overhaul (v84.2) — hook-first, conversational, analogy requirement
- **ADDED** Shorts overhaul (v84.3) — shocking 2s hook, jump-cut zooms, CTA overlay
- **ADDED** FactCheckAgent (v83.0) — verifies named entities+roles against source URL
- **COMMIT** `a10fdf3`, `ee0da7f`, FactCheckAgent commit

## Template for future entries:
```
### YYYY-MM-DD
- **ADDED** what — detail
- **UPDATED** what — detail
- **FIXED** what — detail
- **REMOVED** what — detail
- **COMMIT** hash — description
```
