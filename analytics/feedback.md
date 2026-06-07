# ViralDNA Analytics & Feedback
**Last updated**: 2026-06-07 21:00 IST

## Channel Stats
- Channel: The ViralDNA (UCkW7fqkJiaej2PeNcP4PejQ)
- 17 videos | 8 subscribers | 11,965 views (sum) / 9,926 (channel total)
- Country: IN (set & verified)
- Category: News & Politics (25)

## Issues Fixed (2026-06-07)

### Tags (ALL 18 videos)
- **Before**: Identical 27 static tags on every video (same for nuclear, DMK, Karnataka, everything)
- **After**: Topic-specific tags per video. DMK video gets DMK/INDIA bloc/Tamil Nadu tags.
  Nuclear video gets Rosatom/AP Nuclear/Nara Lokesh tags. Zero overlap between topics.
- **Pipeline fix**: `_generate_topic_tags()` using Gemini LLM + NLP fallback (v82.6)

### Descriptions (ALL 18 videos)
- **Before**: Template artifacts leaking into public descriptions — "TITLE:", "DESCRIPTION:",
  "📰 SUMMARY:", "🔥", "💡 CONTEXT:", "📌 SOURCE:", "🎥 Watch the full story"
- **After**: Clean descriptions with proper formatting, no template markers
- **Pipeline fix**: `desc_raw` sanitization added to `_build_full_description()` (v82.6)
  - Strips TITLE:/DESCRIPTION:/SUMMARY:/emoji prefixes before they reach YouTube
  - Old `f"SUMMARY: {desc_raw[:300]}"` replaced with clean text append
  - Old `f"📰 {title_raw}"` replaced with plain title
  - Old `f"💡 CONTEXT:"` and `f"📌 SOURCE:"` replaced with clean labels

### Zero-View Videos
- Re-published 5 videos via private→public cycle: PhPKatQc61c, IiTvxsoXCGA, dLZZXotpUL4,
  JDEvBAqd44g, ffAZ7m8XxMY
- IiTvxsoXCGA already showing 2 views (picked up)
- PhPKatQc61c, dLZZXotpUL4 still at 0 (needs 24-48h for YouTube re-index)
- JDEvBAqd44g, ffAZ7m8XxMY showing 1 view each

### Short Titles
- Fixed 2 generic shorts: "-q57XLoI1ro" and "4t0xaL3Alfs" now have topic-specific titles

## Pipeline Code Changes (v82.6)
1. `_generate_topic_tags()` new method — LLM-generated topic-specific tags
2. `default_tags` static list replaced with 10 channel-level + 8-12 dynamic topic tags
3. Audit check G5b — CRITICAL if zero topic-specific tags
4. `desc_raw` sanitization in `_build_full_description()` — strips all template markers
5. Description layout cleaned — no more 📰/💡/📌 emoji prefixes in output
6. All 3 code paths updated: `generate_upload_metadata()`, `_create_metadata()`, `_build_full_description()`

## Known Issues (Remaining)
- DriveCopy hangs after 2 files (known workaround: manual rclone after killing process)
- Deccan Chronicle RSS feed times out repeatedly
- 2 zero-view videos still pending YouTube re-index (check in 24-48h)
- Channel trailer not set in YouTube Studio (manual action needed)
- Comments not pinned on high-performing videos (manual action needed)
