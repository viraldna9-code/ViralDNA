================================================================
  VIRALDNA — PRODUCTION HANDOFF DOCUMENT
  Version: v82.3  |  Date: 2026-06-04
================================================================

This document summarizes the current production state, all fixes
applied since v75.3, and the next steps.

────────────────────────────────────────────────────────────────
  CURRENT VERSION: v82.3
────────────────────────────────────────────────────────────────

  Module                    Version    Status
  ─────────────────────────────────────────────
  youtube_uploader.py       v82.3      Production ready (+ audit)
  script_generator.py       v82.3      Production ready (+ keyword titles)
  run_multi_agent_pipeline  v82.3      Production ready (+ audit in doc)
  video_assembler           v80.0      Production ready
  thumbnail_creator         v81.0      Production ready
  visual_fetcher            v81.0      Production ready (RSS Source 0)
  news_image_fetcher        v82.2      Production ready (3-layer defense)
  image_validator           v1.0       Production ready (NEW)
  pre_ship_check            v1.0       Production ready
  forensic_audit            v75.0      Production ready
  gemini_engine             v72.1      Production ready
  monitor_cloud             v74.0      Production ready
  post_filter               v71.0      Production ready

────────────────────────────────────────────────────────────────
  UPLOAD STATUS: DISABLED (Manual Review Mode)
────────────────────────────────────────────────────────────────

  VIRALDNA_UPLOAD_ENABLED = false  (permanent until Jay says otherwise)

  Pipeline produces:
    - 3 videos per topic (main + 2 shorts)
    - 3 thumbnail variants for main video (A/B testing)
    - Per-video metadata documents in docs/topics/<topic_id>/
    - Combined metadata in docs/topics/<topic_id>/00_INDEX.txt
    - Metadata quality audit (20+ checks, score 0-100)

  Upload workflow:
    1. Pipeline finishes -> videos in videos/
    2. Metadata docs in docs/topics/<topic_id>/
    3. Jay reviews videos on disk or in GDrive review folder
    4. Copy-paste from metadata doc into YouTube Studio
    5. Select best thumbnail variant after collecting CTR data

────────────────────────────────────────────────────────────────
  RECENT FIXES (v80.0 through v81.0r4)
────────────────────────────────────────────────────────────────

  v80.0 — Shared Image Validator
    - New modules/image_validator.py (watermark + person + dedup checks)
    - Applied to BOTH visual pipelines (video_assembler + visual_fetcher)
    - Person-name extraction: capitalized words, skip articles, hyphenated OK

  v81.0 — Real News Images + Thumbnail Variant Diversity
    - SSIM threshold relaxed: 0.85 -> 0.70
    - Minimum 2 thumbnail variants enforced
    - 3 title variants on branded thumbnails

  v81.0r2 — Thumbnail Dedup Fix
    - Fixed branded.jpg == branded_v3.jpg duplication

  v81.0r3 — Copy-Paste Metadata Doc for Drive Review
    - New YouTubeUploader.generate_upload_metadata() (no API calls)
    - New _build_full_description() (shared, DRY)
    - _copy_to_gdrive() produces _copy_paste_<topic_id>.txt

  v81.0r4 — Per-Video Metadata Documents
    - Separate docs/topics/<topic_id>/01_MAIN_VIDEO.txt
    - Separate docs/topics/<topic_id>/02_SHORT_1.txt
    - Separate docs/topics/<topic_id>/03_SHORT_2.txt
    - Topic index docs/topics/<topic_id>/00_INDEX.txt

────────────────────────────────────────────────────────────────
  PIPELINE OUTPUT PER TOPIC
────────────────────────────────────────────────────────────────

  videos/
    production_main.mp4         (horizontal, ~70s, ~10MB)
    production_short_1.mp4      (vertical 1080x1920, ~15s, ~4MB)
    production_short_2.mp4      (vertical 1080x1920, ~15s, ~4MB)

  thumbnails/
    production_branded.jpg      (196KB) — Variant A
    production_branded_v2.jpg   (208KB) — Variant B
    production_branded_v3.jpg   (156KB) — Variant C

  docs/topics/<topic_id>/
    00_INDEX.txt                — Topic overview + all file locations
    01_MAIN_VIDEO.txt           — Main video metadata (copy-paste ready)
    02_SHORT_1.txt              — Short 1 metadata (copy-paste ready)
    03_SHORT_2.txt              — Short 2 metadata (copy-paste ready)

  VDNA120 example: docs/topics/VDNA120/

────────────────────────────────────────────────────────────────
  WHAT WORKS NOW (Confirmed)
────────────────────────────────────────────────────────────────

  [OK] Topic scoring: Telugu-relevant topics rank highest (v71.0-74.0)
  [OK] Script generation: State disambiguation prevents wrong state (v75.0)
  [OK] Image pipeline: Real news photos from Serper + Wikimedia (v80.0)
  [OK] Watermark rejection: EXIF + domain + title checks (v75.3 + v80.0)
  [OK] Person-name verification: Shared validator, both pipelines (v80.0)
  [OK] Thumbnail diversity: 3 genuinely different variants (v81.0 + v81.0r2)
  [OK] Forensic audit: Hard halt on state mismatch + wrong images (v75.0)
  [OK] Pre-ship check: 5 content accuracy checks (v75.1)
  [OK] Metadata export: Copy-paste ready docs per video (v81.0r3-4)
  [OK] Drive review: Manifest + metadata alongside videos
  [OK] Monitor: Multi-alert, pending review list (v75.2)
  [OK] GitHub Actions: Proper push of topics_history.json (v75.2)

────────────────────────────────────────────────────────────────
  KNOWN LIMITATIONS / NEXT STEPS
────────────────────────────────────────────────────────────────

  1. SHORTS THUMBNAILS
     Shorts don't support custom thumbnails (YouTube limitation).
     The pipeline still tries to produce them but YouTube ignores.
     First frame is auto-used. No fix needed.

  2. GDRIVE UPLOAD DISABLED
     GDrive API scopes not configured. Pipeline produces files locally.
     Jay uploads manually after review. If GDrive upload is wanted,
     needs: Google Drive API credentials + folder ID in config.py.

  3. MANUAL UPLOAD REQUIRED
     Per Jay's May 31 directive: no auto uploads. Pipeline stops
     at video production + metadata generation. Upload is manual.

  4. TITLE A/B TESTING
     YouTube doesn't support A/B testing titles natively.
     The 3 thumbnails are A/B testable via YouTube Studio.
     For titles: pick Option A (CTR 65), monitor for 48h,
     then try Option B if performance is low.

  5. SCHEDULED PREMIERE
     All videos are set to "private" with scheduled premiere recommended.
     This allows review before going live.

────────────────────────────────────────────────────────────────
  FILES TO OPEN FOR MANUAL UPLOAD (VDNA120 example)
────────────────────────────────────────────────────────────────

  For MAIN VIDEO:
    docs/topics/VDNA120/01_MAIN_VIDEO.txt
    -> Copy title, paste into YouTube Studio title field
    -> Copy description, paste into YouTube Studio description
    -> Copy tags (comma-separated), paste into YouTube Studio tags
    -> Upload all 3 thumbnail variants in YouTube Studio settings

  For SHORT 1:
    docs/topics/VDNA120/02_SHORT_1.txt

  For SHORT 2:
    docs/topics/VDNA120/03_SHORT_2.txt

────────────────────────────────────────────────────────────────
  ENVIRONMENT SETTINGS (DO NOT CHANGE WITHOUT JAY'S APPROVAL)
────────────────────────────────────────────────────────────────

  VIRALDNA_UPLOAD_ENABLED = false
  Privacy: private (scheduled premiere recommended)
  Category: News & Politics (25)
  Language: en-IN
  Voice: Edge-TTS en-IN-PrabhatNeural only
  Model: gemini-2.5-flash-lite (Pay-as-you-go)

  Policy: Once published to YouTube, NEVER delete. Permanent no-delete.
  Policy: No auto-upload. Manual review required before every upload.

────────────────────────────────────────────────────────────────
  METADATA QUALITY AUDIT (v82.3)
────────────────────────────────────────────────────────────────

  Every metadata packet is audited BEFORE output with 20+ checks:

  CRITICAL CHECKS (9) — block output if any fail:
    C1  Title length 40-70 chars (sweet spot for CTR)
    C2  Year in title (freshness signal for news)
    C3  Subscribe CTA in first 3 lines (above mobile fold)
    C4  No "edge-tts" engine name exposed
    C5  Brand = "TheViralDNA" (one word, not "The Viral DNA")
    C6  Hashtags have # prefix
    C7  First 3 hashtags = highest search volume (#TeluguNews first)
    C8  Description >= 200 chars minimum
    C9  Timestamps/chapters present (Key Moments in search)
    S5  AI content disclosure present (YouTube policy)

  GROWTH CHECKS (8) — warnings, growth opportunities:
    G1  Competitor tags (TV9, Sakshi, Eenadu, NTV, ABN)
    G2  Telugu transliteration tags (telugu varthalu)
    G3  Year in description first line
    G4  Tag count 15-30 (optimal range)
    G5  Dynamic year in tags
    G6  SUMMARY not duplicate of CONTEXT
    G7  Like/Comment CTAs present
    G8  Upload schedule mentioned

  STYLE CHECKS (5) — cleanliness:
    S1  No double separator lines
    S2  Smart quotes converted to ASCII
    S3  Shorts tags for Shorts videos
    S4  No bare URLs
    S5  AI disclosure present

  Scoring: 0-100. Each warning -3 pts. Target >= 85 for production.
  Location: modules/youtube_uploader.py -> _audit_metadata()
  Output: Console print + metadata dict["audit"] + copy-paste doc section

================================================================
  END — PRODUCTION HANDOFF DOCUMENT
================================================================
