# PRODUCTION.md — ViralDNA Platform

## What This Is

ViralDNA is an autonomous Telugu newsroom. It discovers trending topics
from RSS feeds, generates scripts via Gemini, produces voiceover via Edge-TTS,
assembles branded videos via FFmpeg, and saves to Google Drive for review
(uploads DISABLED until further notice).

**THIS DOCUMENT**: How to run, monitor, and debug the system.

## Quick Start

```bash
cd /home/jay/ViralDNA

# Run a specific topic
python3 execute_topic.py VDNA042

# Run full pipeline manually
python3 run_pipeline_entrypoint.py

# Check topic history
python3 -c "import json; d=json.load(open('logs/topics_history.json')); [print(f\"{t['id']} score={t.get('score',0)} pub={t.get('published',False)} {t['title'][:60]}\") for t in d['topics'][-10:]]"
```

## Daily Operations (Cron)

| Time (IST) | Job | What It Does |
|-----------|-----|-------------|
| 07:00 | VDNA Morning Publish | Picks best unpublished topic, runs pipeline, saves to Drive |
| 17:00 | VDNA Evening Publish | Picks best unpublished topic, runs pipeline, saves to Drive |

**NOTE**: Cron jobs run autonomously. Videos are saved to Google Drive review folder.
NO auto YouTube uploads (UPLOAD_ENABLED=false).

## File Locations

```
/home/jay/ViralDNA/
├── modules/                  ← 73+ Python worker modules
│   ├── run_multi_agent_pipeline.py  ← Main orchestrator (v82.5)
│   ├── video_assembler.py    ← FFmpeg video assembly + image fetching
│   ├── youtube_uploader.py   ← YouTube Data API (SAVE_TO_DRIVE mode)
│   ├── news_image_fetcher.py ← RSS image fetcher (primary source)
│   └── config.py             ← All API keys, paths, settings
├── audio/                    ← TTS voiceover + slideshow images
├── logs/                     ← Topic history, schedule log
│   ├── topics_history.json   ← All topics (score, published status)
│   └── schedule_log.json     ← Cron run log
├── docs/                     ← Documentation
│   ├── CHANGELOG.md          ← Version history
│   └── PRODUCTION.md         ← This file
└── diagnostics/              ← Growth framework, newsletters
```

## Credentials

```
# Location: ~/.env (NOT in repo)
SERPER_API_KEY=...          ← 40-char key (new format)
SERPER_API_KEY_BACKUP1=...  ← 40-char backup key
GEMINI_API_KEY=...          ← Gemini API key

# YouTube OAuth
/home/jay/ViralDNA/credentials/youtube_token.json
Scopes: youtube.upload, youtube.force-ssl, youtube.readonly
```

## Version History

| Version | Date | Key Changes |
|---------|------|-------------|
| v82.5 | Jun 6 2026 | Title quality overhaul: pre_ship_check (generic+proper noun), shorts_optimizer (distinct angles), pipeline (title dedup+no "Short N:"), youtube_uploader (C1b audit), script_generator (entity-first, no BREAKING templates) |
| v82.4 | Jun 5 2026 | Person-image fix: text-first check all 3 sources, keyword overlap, Gemini fallback fail-closed |
| v82.3 | Jun 3 2026 | Growth metadata + 20+ audit checks |
| v82.2 | Jun 2 2026 | 3-layer image defense |
| v82.1 | Jun 1 2026 | Scheduled publisher (morning + evening cron) |
| v82.0 | May 31 2026 | PostFilter redesign, word boundary re-score |

## Version History

| Version | Date | Key Changes |
|---------|------|-------------|
| v82.6 | 2026-06-06 | Dynamic topic-specific tags (LLM), two-tier tag system, audit check G5b |
| v82.5 | 2026-06-06 | Title quality overhaul — generic detection, distinct shorts, dedup, no BREAKING templates |
| v82.4 | 2026-06-05 | Image relevance defense — text check + keyword overlap + Gemini Vision |
| v82.3 | 2026-06-04 | Metadata audit, competitor tags, transliteration, Shorts discovery tags |

## Known Issues & Solutions

| Issue | Cause | Fix |
|-------|-------|-----|
| Wrong person in images | RSS picks article lead image, not person | v82.4: text check + keyword overlap + Gemini Vision |
| Devil faces in visuals | ComfyUI fallback when all real sources fail | v82.4: 3-layer defense, fail-closed on rate limit |
| D3.6 Upload Timing FAILED | Missing `run()` method | Non-critical, known — doesn't affect output |
| No GitHub Actions alerts | See investigation below | TBD |
| Cron not running | See investigation below | TBD |

## YouTube Channel Info

- Channel: "The ViralDNA"
- Channel ID: UCkW7fqkJiaej2PeNcP4PejQ
- Upload policy: NO auto uploads (UPLOAD_ENABLED=false). Videos → Google Drive review folder.
- NEVER delete published videos (permanent no-delete)
- H3.3: Channel translation
