# CHANGELOG.md — ViralDNA Platform

All notable changes to the ViralDNA platform are documented in this file.

## [52.0] — 2026-05-27 — SCORING REWRITE: Google Trends Primary

### Changed
- `modules/post_filter.py` — VERSION 48.0 → 52.0
  - Scoring formula completely rewritten
  - Google Trends India Daily: 50 pts (was 30) — PRIMARY driver
  - Google Trends Related: 35 pts
  - Source diversity: 30 pts max (was 40)
  - Recency: 15 pts max (NEW)
  - CPM nudge: 5 pt MAX (was 15) — visa/H1B CPM removed entirely
  - Category-based dedup replaces Jaccard keyword overlap
  - 14 TOPIC_CATEGORIES active
- `modules/trend_discovery.py` — VERSION 51.0 → 52.0
  - `_is_relevant_to_diaspora()` → broad relevance filter (180+ keywords)
  - Covers: geography, weather, cricket, movies, politics, crime, health, economy
  - Tier D Google Trends: removed NRI-only filter, uses broad relevance
  - Reddit subreddits expanded: telangana, hyderabad, cricket, indiansports, bollywood
- `modules/run_multi_agent_pipeline.py`
  - WeightingAgent docstring rewritten: Google Trends primary, not CPM
  - Removed CPM-weighted language from timer labels
  - Growth recommendations: "Cover trending topics" (not "Focus on H1B/Visa")

### Why
- Channel was producing 8+ near-identical visa videos (CPM 50 dominated scoring)
- Keyword-overlap dedup too strict (0.12 overlap for same-topic videos)
- User explicitly stated: channel must cover what Telugu people actually search for

### Verification
- All 3 files compile clean (py_compile)
- Scoring test: Prabhas movie (Trends) = 83 pts > Cyclone (3 RSS) = 55 pts > H1B visa (1 RSS) = 30 pts

---

## [51.0] — 2026-05-25 — VALIDATION VIDEO FIXES

### Fixed
1. **Double watermark** — Removed FFmpeg overlay from video, branding only on thumbnail
2. **Thumbnail render failure** — Pass runtime_dir=config.DRIVE["AUDIO_OUTPUT"] to create_thumbnail()
3. **Subtitle sync offset** — Added SYNC_OFFSET_S=0.5s in format_ass_time() for TTS startup latency
4. **Contraction expansion** — Added _expand_contractions() in voiceover.py (40+ contractions)

### Verification
- Main video: y_gYepexqa0 — forensic PASSED
- Short: JwO_VpGAb18 — forensic PASSED
- Quality gate: 100/100 scores

---

## [50.0] — 2026-05-24 — BILINGUAL AUDIO ENGINE

### Added
- en-IN-PrabhatNeural (Indian English, -6% pacing, -5Hz pitch)
- te-IN-MohanNeural (Telugu, -3% pacing, -4Hz pitch)
- Broadcast Warmth FFmpeg mastering chain:
  - Low-Shelf EQ + presence sparkle boost
  - Tight acompressor + brickwall limiter

---

## [48.0] — 2026-05-23 — WMP COMPATIBILITY + IMAGE REJECTION

### Fixed
- Pixel format: yuv444p → yuv420p (Windows Media Player requires yuv420p)
- Devil face fix: skin-tone concentration + red-pixel rejection in visual_fetcher.py
- Telugu font path: /usr/share/fonts/truetype/noto/NotoSansTeluguUI-Bold.ttf
- English font: /usr/share/fonts/truetype/noto/NotoSans-Bold.ttf

---

## Production Policy (May 2026, Permanent)
- **No-delete policy**: Once videos are published to YouTube, NEVER delete them
- Exception: User explicitly authorized dedupe removal of near-duplicates (May 26 cleanup)
