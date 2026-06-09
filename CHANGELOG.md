# ViralDNA Change Log

Every significant change is logged here AND sent to Telegram.
Format: `STATUS | DATE | WHAT | DETAIL`

---

## 2026-06-09

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
