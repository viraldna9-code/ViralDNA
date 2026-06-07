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
| v82.6 | 2026-06-07 | Dynamic topic-specific tags (LLM+Gemini), two-tier tag system, audit G5b, desc_raw sanitization (strips TITLE:/📰/🔥/💡/📌 markers), all 18 YouTube videos fixed |
| v82.5 | 2026-06-06 | Title quality overhaul — generic detection, distinct shorts, dedup, no BREAKING templates |
| v82.4 | 2026-06-05 | Image relevance defense — text check + keyword overlap + Gemini Vision |
| v82.3 | 2026-06-04 | Metadata audit, competitor tags, transliteration, Shorts discovery tags |
| v82.2 | 2026-06-04 | 3-layer image defense (bridge words, 2+ keyword overlap, Gemini Vision gate) |
| v82.1 | 2026-06-01 | Scheduled publisher (morning + evening cron) |
| v82.0 | 2026-05-31 | PostFilter redesign, word boundary re-score |

## Known Issues & Solutions

| Issue | Cause | Fix |
|-------|-------|-----|
| Wrong person in images | RSS picks article lead image, not person | v82.4: text check + keyword overlap + Gemini Vision |
| Devil faces in visuals | ComfyUI fallback when all real sources fail | v82.4: 3-layer defense, fail-closed on rate limit |
| DriveCopy hang in pipeline | rclone hangs after 2 files | Known issue — workaround: kill process, manually rclone copy |
| Zero-view videos | YouTube doesn't index private→scheduledpremiere videos | Fix: private→public re-publish cycle (24-48h to re-index) |
| Template artifacts in descriptions | `desc_raw` from script generator contains TITLE:/📰/🔥 markers | v82.6: desc_raw sanitization in `_build_full_description()` |

## YouTube Channel Info

- Channel: "The ViralDNA"
- Channel ID: UCkW7fqkJiaej2PeNcP4PejQ
- Upload policy: NO auto uploads (UPLOAD_ENABLED=false). Videos → Google Drive review folder.
- NEVER delete published videos (permanent no-delete)
- Country: IN (set via brandingSettings.channel.country)
- Analytics: See analytics/feedback.md for current stats
