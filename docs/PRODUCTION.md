# PRODUCTION.md — ViralDNA Platform

## What This Is

ViralDNA is an autonomous Telugu diaspora newsroom. It discovers trending topics
from Google Trends and RSS feeds, generates bilingual scripts via Gemini,
produces voiceover via Edge-TTS, assembles branded videos via FFmpeg,
and uploads to YouTube — all without human intervention.

**THIS DOCUMENT**: How to run, monitor, and debug the system.

## Quick Start

```bash
cd /home/jay/ViralDNA

# Run full pipeline manually
python3 run_pipeline_entrypoint.py

# Run via Hermes (preferred)
# Just say: "Run the pipeline"
# Hermes will: read plan → spawn agents → execute → report

# Check pipeline status
cat output/runtime/pipeline_run_*.log | tail -50

# Verify uploaded videos
cat output/runtime/topic_history.json
```

## Daily Operations (After Cron Setup)

You should NOT need to manually run anything. Cron handles it:

| Time (IST) | Job | What It Does |
|-----------|-----|-------------|
| 06:00 | Pipeline Run | Full discovery → script → voice → video → upload |
| 06:30 | Verify | Checks all 3 videos are live on YouTube |
| 12:00 | Analyze | Pulls YouTube Analytics, updates growth data |
| 18:00 | Pipeline Run | Second daily run (different topics) |
| 00:00 | Daily Report | Sends you a summary of everything |

## File Locations

```
/home/jay/ViralDNA/
├── modules/                  ← 73 Python worker modules
│   ├── run_multi_agent_pipeline.py  ← Main orchestrator (v52.0)
│   ├── trend_discovery.py    ← Topic discovery (Google Trends + RSS)
│   ├── script_generator.py   ← Gemini-powered script writing
│   ├── voiceover.py          ← Edge-TTS bilingual voiceover
│   ├── video_assembler.py    ← FFmpeg video assembly
│   ├── youtube_uploader.py   ← YouTube Data API uploader
│   └── config.py             ← All API keys, paths, settings
├── videos/                   ← Output MP4 files
│   ├── production_main.mp4
│   ├── production_short_1.mp4
│   └── production_short_2.mp4
├── thumbnails/               ← Generated JPG thumbnails
├── audio/                    ← TTS voiceover files
├── credentials/              ← OAuth tokens, API keys
│   ├── youtube_token.json
│   └── ...
├── output/runtime/           ← Runtime state
│   ├── topic_history.json    ← Used topics (dedup)
│   └── pipeline_run_*.log    ← Run logs
├── docs/                     ← Documentation (NEW)
│   ├── architecture.html     ← Visual system architecture
│   ├── CHANGELOG.md          ← Version history
│   └── PRODUCTION.md         ← This file
└── diagnostics/              ← Checklists, growth framework
    ├── youtube_growth_framework_checklist.md
    └── hermes_skill_checklist.md
```

## Configuration

All settings are in `modules/config.py`:

- API keys: Gemini, YouTube OAuth, Serper (news)
- Video specs: 1920x1080, yuv420p, 30fps
- Audio specs: 44100Hz, stereo, 192kbps
- Branding: bottom-right watermark, font paths
- Drive paths: audio output, thumbnail output

## Credentials Setup

```bash
# Location
/home/jay/ViralDNA/credentials/

# YouTube OAuth
# Token: youtube_token.json
# Scopes: youtube.upload, youtube.force-ssl, youtube.readonly
# Quota: 10,000 units/day
# Upload cost: ~1650 units/video

# Gemini API
# Set in config.py or environment variable
# Model: gemini-flash-latest (pay-as-you-go)
```

## Known Issues & Solutions

| Issue | Cause | Fix |
|-------|-------|-----|
| Quota 429 on upload | YouTube API daily limit | Wait for midnight PST reset |
| Devil faces in visuals | AI image generators | Skin-tone + red-pixel rejection in visual_fetcher.py |
| Same topic repeatedly | CPM-weighted scoring (old) | Fixed in v52.0: category dedup + Trends primary |
| WMP won't play video | yuv444p not supported | Fixed: forces yuv420p in FFmpeg |
| Subtitle out of sync | TTS startup latency | Fixed: +0.5s SYNC_OFFSET_S |
| "Unsupported video" | Pixel format / codec | Fixed: yuv420p + AAC audio |

## Monitoring

```bash
# Check latest pipeline log
ls -lt output/runtime/pipeline_run_*.log | head -1

# Check topic history (what's been covered)
cat output/runtime/topic_history.json | python3 -m json.tool

# Check YouTube upload status
python3 -c "
import json
with open('output/runtime/topic_history.json') as f:
    h = json.load(f)
for t in h.get('topics', [])[-10:]:
    print(f\"{t.get('topic','?')[:60]} | {t.get('youtube_id','NOT UPLOADED')}\")
"

# Check disk space
df -h /home/jay/ViralDNA/videos/

# Verify video integrity
ffprobe -v error -show_entries format=duration,size:stream=codec_name,width,height -of json videos/production_main.mp4
```

## Emergency Procedures

```bash
# If pipeline fails mid-run
# 1. Check the log
tail -100 output/runtime/pipeline_run_*.log

# 2. Topic history is saved at end of Phase 2 — safe to re-run

# 3. If partial videos exist, they'll be overwritten on next run

# 4. If YouTube quota exhausted, wait for reset (midnight PST = 12:30pm IST next day)

# Re-run specific module
python3 -c "
import sys; sys.path.insert(0, '.')
from modules.youtube_uploader import upload_all
upload_all()
"
```

## YouTube Channel Info

- Channel: "The ViralDNA"
- Channel ID: UCkW7fqkJiaej2PeNcP4PejQ
- Trailer ID: mhxkWUBjXRE (v5, needs to be SET as trailer via API)
- Upload policy: NEVER delete published videos (permanent no-delete)

## Growth Checklist Status

See `diagnostics/youtube_growth_framework_checklist.md` for full 171-item breakdown.

**Key remaining:**
- H1.4: Set channel trailer via API (video exists, just not set)
- H1.8: Set featured video via API
- Hometab: Configure channel sections via API

**Blocked (need milestones):**
- A3.5: Community tab (500+ subs)
- A4.4: Memberships (1000+ subs)
- E2.1: Shorts shelf optimization
- E2.2: End screens
- H3.1: Playlist auto-org
- H3.3: Channel translation
