# VERSION: 1.8
# MODULE: youtube_uploader.py
# PURPOSE: Config-Driven & Modular YouTube Video Uploader
#          v1.8: YouTube upload dedup — _get_existing_video_titles() +
#                  _is_duplicate_title() using Jaccard similarity.
#                  upload_production_slot() checks dedup before each upload.
#                  Skips upload if title similarity >= 0.75 to any existing video.
#                  related video links (A2.8), Shorts-to-long CTA (C2.2/C2.3),
#                  topic-based playlist routing (H2.3), subscribe CTA in pinned comments (D4.4),
#                  comment reply timing optimization (D1.3)
#          v1.6: Respect publish_decision.produce_main flag (don't upload stale main),
#                pass publish_decision from pipeline, log upload plan
#          v1.5: A/B testing approach (best title only, no duplicate uploads),
#                per-variant thumbnails for Studio A/B testing
#
# VERSION HISTORY:
#   v1.0 — Initial uploader
#   v1.1 — Config-driven
#   v1.2 — Scheduled publish, altered content disclosure
#   v1.3 — Rich pinned comments, relative buffer scheduling
#   v1.4 — Multi-variant uploads, shorts thumbnail frame injection,
#          subtitles/captions upload, end screens, cards, playlist fixes
#   v1.5 — A/B testing: upload best title only (no spam), per-variant thumbnails

import os, json, time, re, subprocess, tempfile
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
import importlib

import config


class YouTubeUploader:
    def __init__(self, youtube_service, config_instance: dict):
        self.service = youtube_service
        self.global_config = config_instance
        self.upload_config = config_instance
        self.api_config = config.YOUTUBE_API_CONFIG

        self.credentials_dir = config.DRIVE["CREDENTIALS"]

        # Load configs with defaults
        self.privacy_status = self.upload_config.get("privacy_status", "private")
        self.category_id = self.upload_config.get("category_id", "25")
        self.default_language = self.upload_config.get("default_language", "en")
        self.schedule_premiere = self.upload_config.get("schedule_premiere", True)
        self.main_publish_delay_minutes = self.upload_config.get("main_publish_delay_minutes", 60)
        self.shorts_publish_gap_minutes = self.upload_config.get("shorts_publish_gap_minutes", 30)
        # Absolute publish times (IST) — e.g. "09:00" for 9AM, "19:00" for 7PM
        # When set, overrides relative delay. Format: "HH:MM" in IST.
        self.main_publish_time_ist = self.upload_config.get("main_publish_time_ist", None)
        self.shorts_publish_time_ist = self.upload_config.get("shorts_publish_time_ist", None)
        self.title_max_length = self.upload_config.get("title_max_length", 100)
        self.description_max_length = self.upload_config.get("description_max_length", 5000)
        self.tags_max_length = self.upload_config.get("tags_max_length", 500)
        self.self_declared_made_for_kids = self.upload_config.get("self_declared_made_for_kids", False)
        self.set_to_public_on_premiere = self.upload_config.get("set_to_public_on_premiere", True)
        self.shorts_tag = self.upload_config.get("shorts_tag", "Shorts")
        self.video_mimetype = self.upload_config.get("video_mimetype", "video/mp4")
        self.thumbnail_mimetype = self.upload_config.get("thumbnail_mimetype", "image/jpeg")
        self.upload_chunk_size = self.upload_config.get("upload_chunk_size", 10 * 1024 * 1024)
        self.upload_max_retries = self.upload_config.get("upload_max_retries", 3)
        self.upload_retry_delay = self.upload_config.get("upload_retry_delay", 5)
        self.retryable_http_status_codes = self.upload_config.get("retryable_http_status_codes", [500, 502, 503, 504])
        self.upload_delay_seconds = self.upload_config.get("upload_delay_seconds", 10)

        # Playlist IDs
        self.main_playlist_id = self.upload_config.get("main_playlist_id", "")
        self.shorts_playlist_id = self.upload_config.get("shorts_playlist_id", "")
        self.main_playlist_url = self.upload_config.get("main_playlist_url", "")
        self.shorts_playlist_url = self.upload_config.get("shorts_playlist_url", "")

        # Subtitles
        self.subtitles_enabled = self.upload_config.get("subtitles_enabled", True)
        self.subtitles_language = self.upload_config.get("subtitles_language", "en")

        # ── v50.4: Growth-critical defaults ──
        self.embeddable = self.upload_config.get("embeddable", True)
        self.public_stats_viewable = self.upload_config.get("public_stats_viewable", True)
        self.license_type = self.upload_config.get("license", "youtube")
        self.live_broadcast_content = self.upload_config.get("live_broadcast_content", "none")
        self.notify_subscribers = self.upload_config.get("notify_subscribers", True)

        # End screen & cards
        self.end_screen_enabled = self.upload_config.get("end_screen_enabled", True)
        self.end_screen_video_id = self.upload_config.get("end_screen_video_id", "")  # "best for viewer" if empty
        self.end_screen_playlist_id = self.upload_config.get("end_screen_playlist_id", "")
        self.card_video_id = self.upload_config.get("card_video_id", "")
        self.card_playlist_id = self.upload_config.get("card_playlist_id", "")

        self.ist = ZoneInfo("Asia/Kolkata")
        self.utc = ZoneInfo("UTC")

    # ─── Channel Info ───
    def _get_channel_info(self) -> dict:
        try:
            response = self.service.channels().list(part="id,snippet", mine=True).execute()
            items = response.get("items", [])
            return items[0] if items else {}
        except HttpError as e:
            print(f"  ❌ Failed to fetch channel info: {e}")
            return {}

    # ─── Upload Dedup: Fetch Existing Video Titles ───
    def _get_existing_video_titles(self, max_results: int = 50) -> list:
        """
        Fetch titles of recently uploaded videos on the channel.
        Used for dedup: skip upload if title is too similar to existing.
        Returns list of dicts: [{"title": "...", "video_id": "..."}]
        """
        try:
            # Get channel ID first
            channel_resp = self.service.channels().list(part="id", mine=True).execute()
            channel_id = channel_resp.get("items", [{}])[0].get("id", "")
            if not channel_id:
                return []

            # Search for videos on this channel, ordered by date (most recent first)
            search_resp = self.service.search().list(
                part="snippet",
                channelId=channel_id,
                type="video",
                order="date",
                maxResults=max_results
            ).execute()

            existing = []
            for item in search_resp.get("items", []):
                vid = item.get("id", {}).get("videoId", "")
                title = item.get("snippet", {}).get("title", "")
                if vid and title:
                    existing.append({"title": title, "video_id": vid})
            return existing
        except HttpError as e:
            print(f"  ⚠️ Could not fetch existing videos for dedup: {e}")
            return []

    # ─── Upload Dedup: Title Similarity Check ───
    def _is_duplicate_title(self, new_title: str, existing_videos: list,
                            threshold: float = 0.50) -> tuple:
        """
        Check if new_title is too similar to any existing video title.
        Uses word-overlap Jaccard similarity + prefix match detection.
        v1.8.1: Lowered threshold from 0.75 to 0.50 to catch near-duplicates
        (e.g., "Why It Matters" vs "What Happened" sharing 54% words).
        Also detects prefix-identical titles where only the last word differs.
        Returns (is_duplicate: bool, matched_title: str or None)
        """
        if not existing_videos or not new_title:
            return False, None

        new_words = new_title.lower().split()
        new_word_set = set(new_words)
        if not new_word_set:
            return False, None

        for video in existing_videos:
            existing_title = video.get("title", "")
            existing_words = existing_title.lower().split()
            existing_word_set = set(existing_words)
            if not existing_word_set:
                continue

            # Check 1: Jaccard similarity (word set overlap)
            intersection = new_word_set & existing_word_set
            union = new_word_set | existing_word_set
            jaccard_sim = len(intersection) / len(union) if union else 0

            if jaccard_sim >= threshold:
                return True, existing_title

            # Check 2: Prefix-identical detection (same words except last 1-2)
            # Catches "DMK to boycott June 8 — Why It Matters" vs "DMK to boycott June 8 — What Happened"
            if len(new_words) >= 5 and len(existing_words) >= 5:
                # Compare first 80% of words (by count of shorter title)
                min_len = min(len(new_words), len(existing_words))
                prefix_len = max(3, int(min_len * 0.7))
                new_prefix = new_words[:prefix_len]
                existing_prefix = existing_words[:prefix_len]
                if new_prefix == existing_prefix and jaccard_sim >= 0.45:
                    return True, existing_title

        return False, None

    # ─── Scheduled Publish Time ───
    def _get_scheduled_publish_time(self, is_short: bool = False, short_index: int = 0,
                                     upload_schedule: dict = None) -> str:
        """Return ISO-8601 UTC publish time for YouTube API.

        Priority:
        1. upload_schedule dict from UploadTimeOptimizer (state["upload_schedule"])
        2. Static main_publish_time_ist / shorts_publish_time_ist from config
        3. Relative delay from now (fallback)

        upload_schedule format: {"recommended_time_ist": "18:00", ...}
        """
        from datetime import datetime, timedelta, timezone
        IST = timezone(timedelta(hours=5, minutes=30))
        now_ist = datetime.now(IST)

        def _next_occurrence(time_str: str, extra_minutes: int = 0) -> str:
            """Compute next occurrence of HH:MM IST, optionally offset by extra_minutes."""
            h, m = map(int, time_str.split(":"))
            target = now_ist.replace(hour=h, minute=m, second=0, microsecond=0)
            if extra_minutes:
                target += timedelta(minutes=extra_minutes)
            # If this time already passed today, schedule for tomorrow
            if target <= now_ist:
                target += timedelta(days=1)
            # Convert to UTC ISO format for YouTube API
            utc = target.astimezone(timezone.utc)
            return utc.isoformat().replace("+00:00", "Z")

        # Determine which time string to use
        if is_short:
            # Shorts: use schedule's shorts times if available
            if upload_schedule and upload_schedule.get("shorts_schedule"):
                shorts_sched = upload_schedule["shorts_schedule"]
                if short_index < len(shorts_sched):
                    time_str = shorts_sched[short_index].get("ist_time", "18:00")
                    return _next_occurrence(time_str)
            if self.shorts_publish_time_ist:
                gap = self.shorts_publish_gap_minutes
                return _next_occurrence(self.shorts_publish_time_ist, extra_minutes=gap * short_index)
            # Fallback: relative
            now_utc = datetime.now(self.utc)
            main_delay = timedelta(minutes=self.main_publish_delay_minutes)
            gap = timedelta(minutes=self.shorts_publish_gap_minutes)
            target = now_utc + main_delay + (gap * short_index)
        else:
            # Main video: use schedule's recommended time if available
            if upload_schedule and upload_schedule.get("recommended_time_ist"):
                return _next_occurrence(upload_schedule["recommended_time_ist"])
            if self.main_publish_time_ist:
                return _next_occurrence(self.main_publish_time_ist)
            # Fallback: relative
            now_utc = datetime.now(self.utc)
            main_delay = timedelta(minutes=self.main_publish_delay_minutes)
            target = now_utc + main_delay

        return target.isoformat().replace("+00:00", "Z")

    # ─── Public: Generate upload metadata (no API call) ───
    def generate_upload_metadata(self, title_raw: str, desc_raw: str, rag_context: str,
                                  topic: dict = None, is_short: bool = False,
                                  short_index: int = 0) -> dict:
        """Generate full YouTube upload metadata as a clean dict.

        Does NOT call any YouTube API. Used by _copy_to_gdrive to produce
        a copy-paste document when uploads are disabled.
        Returns: {title, description, tags, category_id, privacy, is_short}
        """
        topic = topic or {}

        # Title — clean and optimize for CTR
        import datetime as _dt
        _year = str(_dt.datetime.now().year)

        # Strip source names from title (e.g., " - The Hindu", " | NDTV")
        import re as _re
        clean_title = _re.sub(r'\s*[-|]\s*(The Hindu|NDTV|Times of India|India Today|Firstpost|Scroll\.in|The Wire|News18|CNBC|BBC|CNN|Al Jazeera|Reuters|AP|AFP|PTI|ANI).*$', '', title_raw, flags=_re.IGNORECASE).strip()
        # Also strip " - Google News RSS" etc.
        clean_title = _re.sub(r'\s*[-|]\s*(Google News|RSS|India Top).*$', '', clean_title, flags=_re.IGNORECASE).strip()

        if is_short:
            # Short title: concise, under 60 chars, single #Shorts at end
            # Remove any existing #Shorts or year suffixes first
            base = _re.sub(r'\s*#Shorts.*$', '', clean_title, flags=_re.IGNORECASE).strip()
            base = _re.sub(r'\s*\(\d{4}\)\s*$', '', base).strip()
            # Truncate base so that "base ({year}) #Shorts" fits in 60 chars
            # " ({year}) #Shorts" = 13 chars
            max_base_len = 60 - len(f" ({_year}) #Shorts")
            if len(base) > max_base_len:
                base = base[:max_base_len - 3].rstrip() + "..."
            title = f"{base} ({_year}) #Shorts"
        else:
            # Main title: under 70 chars, include year
            base = _re.sub(r'\s*\(\d{4}\)\s*$', '', clean_title).strip()
            if _year not in base:
                candidate = f"{base} ({_year})"
            else:
                candidate = base
            if len(candidate) > 70:
                # Truncate base to fit
                overflow = len(candidate) - 70
                base = base[:len(base) - overflow - 3].rstrip()
                # Don't cut mid-word
                last_space = base.rfind(' ')
                if last_space > 20:
                    base = base[:last_space]
                candidate = f"{base} ({_year})" if _year not in base else base
            title = candidate

        if len(title) > self.title_max_length:
            title = title[:self.title_max_length - 3] + "..."

        # Build full description (same logic as _create_metadata)
        description = self._build_full_description(title_raw, desc_raw, rag_context,
                                                    topic, is_short)

        # Tags — v82.6: Two-tier system — topic-specific (LLM) + channel-level (static)
        import datetime
        year = datetime.datetime.now().year

        # Tier 1: Topic-specific tags (generated by Gemini LLM or fallback NLP)
        topic_tags = self._generate_topic_tags(topic, title_raw, rag_context)

        # Tier 2: Channel-level tags (always included for brand/SEO consistency)
        # NOTE: Competitor channel names (TV9, Sakshi, Eenadu, NTV, ABN) are
        # intentionally excluded — they help competitors' SEO, not ours.
        channel_tags = [
            "TheViralDNA",
            "telugu varthalu", "andhra varthalu", "telangana varthalu",
            f"trending India {year}",
        ]

        # Merge: topic tags first (highest priority), then channel tags
        tags = list(topic_tags)
        for ct in channel_tags:
            if ct.lower() not in [t.lower() for t in tags]:
                tags.append(ct)
        # v82.3: Shorts-specific discovery tags
        if is_short:
            shorts_tags = ["YouTube Shorts", "Shorts News", "Telugu Shorts", self.shorts_tag]
            for st in shorts_tags:
                if st not in tags:
                    tags.append(st)
        tags_str = ",".join(tags)
        if len(tags_str) > self.tags_max_length:
            trimmed = []
            current_len = 0
            for tag in tags:
                if current_len + len(tag) + 1 <= self.tags_max_length:
                    trimmed.append(tag)
                    current_len += len(tag) + 1
                else:
                    break
            tags = trimmed

        # v82.3: Run metadata quality audit before returning
        audit = self._audit_metadata(title, description, tags, is_short)

        result = {
            "title": title,
            "description": description,
            "tags": tags,
            "category_id": self.category_id,
            "category_name": "News & Politics",
            "privacy": self.privacy_status,
            "language": "en-IN",
            "is_short": is_short,
            "audit": audit,
        }
        return result

    def _build_full_description(self, title_raw: str, desc_raw: str, rag_context: str,
                                 topic: dict, is_short: bool) -> str:
        """Build the full YouTube description string (shared by upload + metadata export).
        
        v82.3: Growth-first metadata layout for new channel discovery:
        - Subscribe+bell CTA in FIRST 3 lines (above fold on mobile)
        - Timestamps/chapters for watch-time signal + "Key Moments" in search
        - Freshness signals (2026, today) in snippet
        - Competitor-adjacent tags for suggested video surface
        """
        import datetime
        year = datetime.datetime.now().year
        today_str = datetime.datetime.now().strftime("%B %d, %Y")

        # v83.3: Normalize ALL apostrophe-like Unicode characters in title and description
        _apostrophe_map = {
            "\u2019": "'", "\u2018": "'", "\u2032": "'", "\u2035": "'",
            "\u02bc": "'", "\u02bb": "'", "\uff07": "'", "\u201b": "'",
            "\u2039": "'", "\u203a": "'",
        }
        for _u, _a in _apostrophe_map.items():
            title_raw = title_raw.replace(_u, _a)
            desc_raw = desc_raw.replace(_u, _a)
            rag_context = rag_context.replace(_u, _a)

        # v82.6: Sanitize desc_raw — strip template markers that leak into public description
        if desc_raw:
            for _marker in [r'^TITLE:\s*\n\s*[^\n]+\n*', r'^DESCRIPTION:\s*\n',
                            r'^\s*📰\s*SUMMARY:\s*', r'^🔥\s*[^\n]+\n+',
                            r'💡 BACKGROUND[^:]*:', r'^🎥.*$']:
                desc_raw = re.sub(_marker, '', desc_raw, flags=re.MULTILINE)
            desc_raw = desc_raw.strip()
            if not is_short:
                desc_raw = re.sub(r'🎥 Watch the full story.*$', '', desc_raw, flags=re.MULTILINE)
            desc_raw = desc_raw.strip()

        seo_keywords = self._extract_seo_keywords(topic, title_raw, desc_raw)
        seo_keyword_line = ""
        if seo_keywords:
            seo_keyword_line = f"🔑 TOPICS: {', '.join(seo_keywords[:8])}"

        sources_str = topic.get("source", "ViralDNA Internal Desk")
        if re.match(r"^https?://", sources_str):
            sources_str = "Verified Regional News Feeds"

        related_links = self._build_related_links(topic)
        snippet_prefix = self._build_snippet_prefix(title_raw, desc_raw, seo_keyword_line)

        # ── GROWTH LAYOUT: Subscribe CTA FIRST (above fold on mobile) ──
        description_lines = [
            snippet_prefix,
            "",
            "🔔 SUBSCRIBE & hit the bell → https://www.youtube.com/@TheViralDNA",
            f"{title_raw} ({today_str})",
            "",
        ]
        # Add sanitized content summary (not prefixed with "SUMMARY:")
        if desc_raw:
            summary_text = desc_raw[:300].strip()
            if summary_text:
                description_lines.append(summary_text)

        # ── TIMESTAMP CHAPTERS (watch-time signal + Key Moments in search) ──
        chapters = self._generate_chapters(topic, desc_raw, is_short)
        if chapters:
            description_lines.append("")
            description_lines.append("⏱️ CHAPTERS:")
            for ts, label in chapters:
                description_lines.append(f"  {ts} {label}")

        description_lines.extend([
            "",
            rag_context[:300].strip(),
            "",
            f"SOURCE: {sources_str}",
        ])

        if seo_keyword_line:
            description_lines.append("")
            description_lines.append(seo_keyword_line)

        description_lines.extend([
            "",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "📺 TheViralDNA — Real News. Real Voices. Built with AI.",
            "🕘 New videos daily at 9:00 AM & 7:00 PM IST",
            "👍 Like • 💬 Comment • 📤 Share",
            "📧 viraldna9@gmail.com",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        ])

        # Affiliate/crowdfunding/merch sections removed — they add description bloat
        # without meaningful CTR benefit for a news channel at this stage.

        description_lines.extend([
            "",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        ])

        hashtag_block = self._build_hashtag_block(topic, title_raw)
        description_lines.append(hashtag_block)

        description_lines.extend([
            "",
            "🤖 ALTERED CONTENT DISCLOSURE:",
            "This video was produced using AI-assisted tools: AI script generation,",
            "AI voice synthesis, algorithmic video assembly. Visuals may",
            "include AI-generated imagery. Labeled per YouTube synthetic media policies.",
            "©️ Produced by TheViralDNA.",
        ])

        description = "\n".join(description_lines)

        if len(description) > self.description_max_length:
            description = description[:self.description_max_length - 50] + "\n\n...[truncated]"

        # Sanitize HTML but preserve apostrophes and smart quotes
        description = re.sub(r'<[^>]+>', '', description)
        description = description.replace("\u2018", "'").replace("\u2019", "'")  # smart single quotes
        description = description.replace("\u201c", '"').replace("\u201d", '"')  # smart double quotes
        description = description.strip()
        return description

    # ─── Metadata Builder (YouTube API format) ───
    def _create_metadata(self, title_raw: str, desc_raw: str, rag_context: str,
                         topic: dict = None, is_short: bool = False,
                         short_index: int = 0, variant_idx: int = 0,
                         upload_schedule: dict = None) -> dict:
        topic = topic or {}
        import datetime
        year = datetime.datetime.now().year

        # Title
        if is_short:
            title = f"{title_raw} #{self.shorts_tag}"
        else:
            title = title_raw
        # v82.3: Ensure year is in title (C2 audit — freshness signal for news)
        _year_s = str(year)
        if _year_s not in title:
            if f"#{self.shorts_tag}" in title:
                title = title.replace(f" #{self.shorts_tag}", f" ({_year_s}) #{self.shorts_tag}")
            else:
                title = f"{title} ({_year_s})"
        if len(title) > self.title_max_length:
            title = title[:self.title_max_length - 3] + "..."

        # Description (reuse shared builder)
        description = self._build_full_description(title_raw, desc_raw, rag_context,
                                                    topic, is_short)

        # Sanitize — strip HTML but preserve apostrophes/smart quotes
        title = re.sub(r'<[^>]+>', '', title).strip()
        description = re.sub(r'<[^>]+>', '', description)
        description = description.replace("\u2018", "'").replace("\u2019", "'")
        description = description.replace("\u201c", '"').replace("\u201d", '"')
        description = description.strip()

        # Tags — v82.6: Two-tier system — topic-specific (LLM) + channel-level (static)
        # Tier 1: Topic-specific tags (generated by Gemini LLM or fallback NLP)
        topic_tags = self._generate_topic_tags(topic, title_raw, rag_context)

        # Tier 2: Channel-level tags (always included for brand/SEO consistency)
        # NOTE: Competitor channel names (TV9, Sakshi, Eenadu, NTV, ABN) are
        # intentionally excluded — they help competitors' SEO, not ours.
        channel_tags = [
            "TheViralDNA",
            "telugu varthalu", "andhra varthalu", "telangana varthalu",
            f"trending India {year}",
        ]

        # Merge: topic tags first (highest priority), then channel tags
        tags = list(topic_tags)
        for ct in channel_tags:
            if ct.lower() not in [t.lower() for t in tags]:
                tags.append(ct)
        # v82.3: Shorts-specific discovery tags
        if is_short:
            shorts_tags = ["YouTube Shorts", "Shorts News", "Telugu Shorts", self.shorts_tag]
            for st in shorts_tags:
                if st not in tags:
                    tags.append(st)
        tags_str = ",".join(tags)
        if len(tags_str) > self.tags_max_length:
            trimmed = []
            current_len = 0
            for tag in tags:
                if current_len + len(tag) + 1 <= self.tags_max_length:
                    trimmed.append(tag)
                    current_len += len(tag) + 1
                else:
                    break
            tags = trimmed

        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
                "categoryId": self.category_id,
                "defaultLanguage": self.default_language,
                "defaultAudioLanguage": "en-IN",
                "liveBroadcastContent": self.live_broadcast_content,
            },
            "status": {
                "privacyStatus": self.privacy_status,
                "selfDeclaredMadeForKids": self.self_declared_made_for_kids,
                "embeddable": self.embeddable,
                "publicStatsViewable": self.public_stats_viewable,
                "license": self.license_type,
            }
        }

        if self.schedule_premiere:
            scheduled_time = self._get_scheduled_publish_time(is_short, short_index=short_index,
                                                              upload_schedule=upload_schedule)
            body["status"]["publishAt"] = scheduled_time
            body["status"]["privacyStatus"] = "private"

        return body

    # ─── SRT Subtitle Generator ───
    def _generate_srt(self, script_text: str, output_path: str, duration_s: float = None) -> bool:
        """Generate a basic SRT subtitle file from script text."""
        if not script_text:
            return False
        try:
            words = script_text.split()
            if not words:
                return False
            # Estimate duration: ~140 WPM broadcast standard
            if not duration_s:
                duration_s = len(words) / 140 * 60
            # Split into subtitle chunks (~2 lines, ~40 chars each)
            chunks = []
            current_chunk = []
            current_len = 0
            for word in words:
                if current_len + len(word) + 1 > 60 and current_chunk:
                    chunks.append(" ".join(current_chunk))
                    current_chunk = [word]
                    current_len = len(word)
                else:
                    current_chunk.append(word)
                    current_len += len(word) + 1
            if current_chunk:
                chunks.append(" ".join(current_chunk))

            if not chunks:
                return False

            # Time per chunk
            total_duration = max(duration_s, len(chunks) * 2.0)
            time_per_chunk = total_duration / len(chunks)

            srt_lines = []
            for i, chunk in enumerate(chunks):
                start_s = i * time_per_chunk
                end_s = min((i + 1) * time_per_chunk, total_duration)
                start_ts = f"{int(start_s // 3600):02d}:{int((start_s % 3600) // 60):02d}:{int(start_s % 60):02d},{int((start_s % 1) * 1000):03d}"
                end_ts = f"{int(end_s // 3600):02d}:{int((end_s % 3600) // 60):02d}:{int(end_s % 60):02d},{int((end_s % 1) * 1000):03d}"
                srt_lines.append(f"{i + 1}")
                srt_lines.append(f"{start_ts} --> {end_ts}")
                srt_lines.append(chunk)
                srt_lines.append("")

            with open(output_path, "w", encoding="utf-8") as f:
                f.write("\n".join(srt_lines))
            return True
        except Exception as e:
            print(f"    ⚠️ SRT generation failed: {e}")
            return False

    def _upload_captions(self, video_id: str, srt_path: str) -> bool:
        """Upload SRT captions to a video."""
        if not os.path.exists(srt_path):
            return False
        try:
            self.service.captions().insert(
                part="snippet",
                body={
                    "snippet": {
                        "videoId": video_id,
                        "language": self.subtitles_language,
                        "name": "English (auto-generated)",
                        "isDraft": False
                    }
                },
                media_body=MediaFileUpload(srt_path, mimetype="application/x-subrip")
            ).execute()
            print(f"    🟢 Captions uploaded for {video_id}")
            return True
        except HttpError as e:
            print(f"    ⚠️ Caption upload failed: {e}")
            return False

    # ─── End Screen & Cards (B3.2: Real API Usage) ───
    def _update_end_screen_and_cards(self, video_id: str, topic: dict = None,
                                      playlist_id: str = None,
                                      similar_video_ids: list = None) -> bool:
        """
        B3.2: Set end screen elements and playlist routing.
        YouTube Data API v3 doesn't support direct end screen editing,
        but we can: (1) add video to playlist, (2) set video's recording date
        for SEO, (3) log end screen config for Studio upload, (4) use
        the 'endScreen' property in videos.update if available.
        """
        success = False
        try:
            # 1. Add video to playlist for end-screen discoverability
            if playlist_id and playlist_id != "PLACEHOLDER_PLAYLIST":
                try:
                    self.service.playlistItems().insert(
                        part="snippet",
                        body={
                            "snippet": {
                                "playlistId": playlist_id,
                                "resourceId": {
                                    "kind": "youtube#video",
                                    "videoId": video_id
                                }
                            }
                        }
                    ).execute()
                    print(f"    🟢 Added to playlist: {playlist_id}")
                    success = True
                except HttpError as e:
                    print(f"    ⚠️ Playlist add failed: {e}")

            # 2. Fetch video metadata to find similar videos for end screen
            end_screen_targets = []
            if similar_video_ids:
                for sv_id in similar_video_ids[:4]:
                    try:
                        resp = self.service.videos().list(
                            part="snippet", id=sv_id
                        ).execute()
                        if resp.get("items"):
                            title = resp["items"][0]["snippet"]["title"]
                            end_screen_targets.append({
                                "type": "video",
                                "videoId": sv_id,
                                "title": title,
                                "end_ms": 20000,
                            })
                    except Exception:
                        pass

            # 3. Log end screen config for YouTube Studio manual setup
            # (API v3 limitation — end screens require Studio or Content Owner API)
            if end_screen_targets:
                end_screen_log = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "diagnostics", "end_screen_config.json"
                )
                config_entry = {
                    "video_id": video_id,
                    "topic": topic.get("title", "") if topic else "",
                    "recommended_end_screen": end_screen_targets,
                    "recommended_type": "video",
                    "note": "Set via YouTube Studio: Edit video → End Screen → Add element → Video",
                    "generated_at": datetime.now().isoformat(),
                }
                # Append to existing log
                existing = []
                if os.path.exists(end_screen_log):
                    try:
                        with open(end_screen_log, "r") as f:
                            existing = json.load(f)
                    except Exception:
                        existing = []
                existing.append(config_entry)
                with open(end_screen_log, "w") as f:
                    json.dump(existing[-50:], f, indent=2)  # keep last 50
                print(f"    🟢 End screen config logged: {len(end_screen_targets)} targets")

            # 4. Find related videos from channel for end screen recommendations
            if not similar_video_ids:
                try:
                    search_resp = self.service.search().list(
                        part="snippet",
                        channelId=self.upload_config.get("channel_id", ""),
                        type="video",
                        order="viewCount",
                        maxResults=5
                    ).execute()
                    for item in search_resp.get("items", []):
                        vid = item.get("id", {}).get("videoId", "")
                        if vid and vid != video_id:
                            title = item.get("snippet", {}).get("title", "")
                            end_screen_targets.append({
                                "type": "video",
                                "videoId": vid,
                                "title": title,
                                "end_ms": 20000,
                            })
                except Exception:
                    pass

            return success or len(end_screen_targets) > 0
        except Exception as e:
            print(f"    ⚠️ End screen setup error: {e}")
            return False

    # ─── Resumable Upload ───
    def _execute_resumable_upload(self, media_body: MediaFileUpload, body: dict,
                                   notify_subscribers: bool = True) -> str:
        insert_request = self.service.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media_body,
            notifySubscribers=notify_subscribers,
        )
        response = None
        error = None
        retry_count = 0
        print(f"    Resumable Upload started. Chunk Size: {self.upload_chunk_size / 1024 / 1024:.1f}MB...")
        while response is None:
            try:
                status, response = insert_request.next_chunk()
                if response is not None:
                    if "id" in response:
                        print(f"    🟢 Video uploaded! YouTube ID: {response['id']}")
                        return response["id"]
                    else:
                        raise HttpError(None, b"Upload succeeded but no video ID returned.")
                if status:
                    print(f"      Upload progress: {int(status.progress() * 100)}%...")
            except HttpError as e:
                if e.resp.status in self.retryable_http_status_codes:
                    error = e
                else:
                    raise e
            except Exception as e:
                error = e
            if error:
                retry_count += 1
                print(f"    ⚠️ Upload interrupted: {error}. Retry {retry_count}/{self.upload_max_retries} in {self.upload_retry_delay}s...")
                if retry_count > self.upload_max_retries:
                    raise Exception(f"Upload failed after {self.upload_max_retries} attempts. Last error: {error}")
                time.sleep(self.upload_retry_delay)
                error = None

    # ─── Thumbnail Upload ───
    def _upload_thumbnail(self, video_id: str, thumbnail_path: str) -> bool:
        if not os.path.exists(thumbnail_path):
            print(f"    ⚠️ Thumbnail not found: {thumbnail_path}. Skipping.")
            return False
        try:
            self.service.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail_path, mimetype=self.thumbnail_mimetype)
            ).execute()
            print(f"    🟢 Thumbnail linked to {video_id}")
            return True
        except HttpError as e:
            print(f"    ❌ Thumbnail upload failed: {e}")
            return False

    # ─── Shorts Thumbnail Frame Injection ───
    def _inject_thumbnail_frame(self, video_path: str, thumbnail_path: str, output_dir: str) -> str:
        """
        For YouTube Shorts: inject the desired thumbnail as the first frame of the video.
        YouTube Shorts doesn't support custom thumbnails via API — it auto-picks a frame.
        By making the first frame the thumbnail, we control what YouTube shows.
        Returns path to the new video file with injected frame.
        """
        if not os.path.exists(thumbnail_path) or not os.path.exists(video_path):
            return video_path

        output_path = os.path.join(output_dir, f"short_with_thumb_{os.path.basename(video_path)}")
        if os.path.exists(output_path):
            return output_path

        try:
            # Use FFmpeg: overlay thumbnail as first 1 second, then switch to video
            # Actually simpler: prepend the image as a 1-second clip, then concat with original
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-i", thumbnail_path,  # thumbnail as 1-sec loop
                "-i", video_path,                     # original video
                "-filter_complex",
                "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,trim=duration=1,setpts=PTS-STARTPTS[thumb];"
                "[1:v]setpts=PTS-STARTPTS[vid];"
                "[thumb][vid]concat=n=2:v=1:a=0[outv];"
                "[1:a]asetpts=PTS-STARTPTS[outa]",
                "-map", "[outv]", "-map", "[outa]",
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart",
                "-shortest",
                output_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode == 0 and os.path.exists(output_path):
                print(f"    🟢 Thumbnail frame injected for short: {os.path.basename(output_path)}")
                return output_path
            else:
                print(f"    ⚠️ Thumbnail frame injection failed, using original video")
                return video_path
        except Exception as e:
            print(f"    ⚠️ Thumbnail frame injection error: {e}")
            return video_path

    # ─── Pinned Comment ───
    def _add_pinned_comment(self, video_id: str, comment_text: str) -> bool:
        """Add a top-level comment to the video with retry logic."""
        max_attempts = 2
        for attempt in range(1, max_attempts + 1):
            try:
                resp = self.service.commentThreads().insert(
                    part="snippet",
                    body={
                        "snippet": {
                            "videoId": video_id,
                            "topLevelComment": {
                                "snippet": {"textOriginal": comment_text}
                            }
                        }
                    }
                ).execute()
                comment_id = resp.get("id", "")
                print(f"    🟢 Comment added to {video_id} (id: {comment_id})")
                return True
            except HttpError as e:
                if e.resp.status == 403:
                    print(f"    ⚠️ Comments disabled on {video_id} or quota exceeded")
                    return False
                elif e.resp.status == 429 and attempt < max_attempts:
                    import time
                    wait = 5 * attempt
                    print(f"    ⏳ Rate limited, retrying in {wait}s...")
                    time.sleep(wait)
                    continue
                else:
                    print(f"    ⚠️ Comment failed ({e.resp.status}): {e}")
                    return False
            except Exception as e:
                print(f"    ⚠️ Comment error: {e}")
                return False
        return False

    # ─── Playlist ───
    def _add_to_playlist(self, video_id: str, playlist_id: str) -> bool:
        if not playlist_id:
            return False
        try:
            self.service.playlistItems().insert(
                part="snippet",
                body={
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {"kind": "youtube#video", "videoId": video_id}
                    }
                }
            ).execute()
            print(f"    🟢 Added {video_id} to playlist {playlist_id}")
            return True
        except HttpError as e:
            print(f"    ⚠️ Playlist add failed: {e}")
            return False

    # ─── Helper Methods for SEO & CTA ──

    # A2.6: SEO keyword extraction
    HIGH_VALUE_KEYWORDS = [
        "telugu news", "andhra pradesh", "telangana", "hyderabad", "vizag",
        "visakhapatnam", "vijayawada", "amaravati", "guntur", "nri",
        "h1b visa", "green card", "visa update", "immigration", "india news",
        "breaking news", "cricket", "tollywood", "cinema", "economy",
        "budget", "policy", "election", "technology", "health",
        "us news", "uk news", "canada", "australia", "germany",
    ]

    def _extract_seo_keywords(self, topic: dict, title_raw: str,
                               desc_raw: str) -> list:
        """Extract SEO keywords from topic metadata for description injection.
        Uses word-boundary matching to avoid false positives (e.g., 'ai' in 'details')."""
        import re as _re
        text = f"{title_raw} {desc_raw}".lower()
        found = []
        for kw in self.HIGH_VALUE_KEYWORDS:
            kw_lower = kw.lower()
            # Use word-boundary regex for short keywords (<=3 chars), substring for longer
            if len(kw_lower) <= 3:
                pattern = r'\b' + _re.escape(kw_lower) + r'\b'
                if _re.search(pattern, text) and kw not in found:
                    found.append(kw)
            else:
                if kw_lower in text and kw not in found:
                    found.append(kw)
        # Also add topic tags if available
        topic_tags = topic.get("tags", "")
        if topic_tags:
            if isinstance(topic_tags, list):
                for tag in topic_tags:
                    tag = tag.strip() if isinstance(tag, str) else str(tag)
                    if tag and tag not in found:
                        found.append(tag)
            else:
                for tag in topic_tags.split(","):
                    tag = tag.strip()
                    if tag and tag not in found:
                        found.append(tag)
        return found[:12]

    # A2.7: Hashtag block builder
    def _fetch_trending_hashtags(self, topic_title: str) -> list:
        """
        A5.4: Fetch real trending hashtags from YouTube search suggestions.
        Uses YouTube's free autosuggest API (no API key required).
        Falls back to empty list on failure.
        """
        import urllib.request, urllib.parse, json as _json
        trending = []
        try:
            # Extract top 3 keywords from title for search queries
            words = [w for w in topic_title.lower().split() if len(w) > 3][:3]
            queries = words[:2] if words else ["telugu news"]

            seen = set()
            for query in queries:
                url = (
                    "https://suggestqueries.google.com/complete/search"
                    f"?client=youtube&ds=yt&q={urllib.parse.quote(query)}"
                )
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = _json.loads(resp.read().decode("utf-8"))
                    suggestions = data[1] if len(data) > 1 else []
                    for s in suggestions:
                        s_lower = s.lower().strip()
                        # Convert suggestions to hashtag format
                        if s_lower not in seen and len(s_lower) > 2:
                            hashtag = "#" + re.sub(r'[^a-zA-Z0-9]', '', s.title())
                            if len(hashtag) > 2:
                                trending.append(hashtag)
                                seen.add(s_lower)
                        if len(trending) >= 5:
                            break
                if len(trending) >= 3:
                    break
        except Exception:
            pass  # Network failure — fallback to keyword-based below
        return trending


    def _generate_topic_tags(self, topic: dict, title_raw: str, rag_context: str = "") -> list:
        """Generate topic-specific tags using Gemini LLM.

        v82.6: Replaces static default_tags with dynamic topic-aware tags.
        Extracts named entities, places, people, and themes from the topic
        content to produce tags that are unique to each video.

        Returns: list of tag strings (5-12 tags), or empty list on failure.
        """
        import datetime
        year = datetime.datetime.now().year

        topic_title = topic.get("title", title_raw)
        source = topic.get("source", "")
        url = topic.get("url", "")

        prompt = f"""You are a YouTube SEO expert for a Telugu news channel called TheViralDNA.
Generate 8-12 topic-specific YouTube tags for this news video, optimized for search discovery.

Topic: {topic_title}
Source: {source}
URL: {url}
Content preview: {rag_context[:500]}

SEARCH VOLUME STRATEGY:
- Include 2-3 HIGH-VOLUME tags: broad terms people actually search (e.g., "India news", "Telugu news", "breaking news today")
- Include 3-5 MEDIUM-VOLUME tags: specific to this story, moderate competition (e.g., "AP politics 2026", "Telangana budget")
- Include 2-3 LONG-TAIL tags: very specific phrases with low competition but intent-driven (e.g., "why did DMK boycott 2026 meeting")
- Think about what a viewer would TYPE IN THE SEARCH BAR to find this video
- Prioritize tags with search volume over obscure entity names nobody searches
- Include query-style tags (question format): "what is happening in AP", "why Telangana news today"
- For breaking/trending news, include "today", "latest", "update" suffixes — these match real-time search intent
- Include the year for temporal relevance (e.g., "India news {year}", "politics {year}")

Rules:
- Tags must be SPECIFIC to this topic (names, places, organizations, events)
- Include 2-3 broad category tags (e.g., "Tamil Nadu politics", "DMK news")
- Include 2-3 entity tags (e.g., "MK Stalin", "INDIA bloc", "Congress party")
- Include 1-2 long-tail search tags (e.g., "DMK boycott 2026", "opposition unity crisis")
- Include the year where relevant (e.g., "Tamil Nadu news {year}")
- Do NOT include generic channel-level tags like "Telugu news today", "Andhra Pradesh news", "Telangana news", "AP news today", "Hyderabad news", "Vijayawada news", "Vizag news", "Amaravati news", "Guntur news", "TheViralDNA", "TV9 Telugu", "Sakshi news", "Eenadu news", "NTV Telugu", "ABN Andhra", "telugu varthalu", "andhra varthalu", "telangana varthalu", "Telugu breaking news", "Tenglish news", "India news today", "NRI Telugu news", "Telugu current affairs", "AP Telangana updates", "viral news India", "trending India {year}", "Telugu states news" — these are added separately
- Output ONLY a JSON array of strings, nothing else
- Example: ["DMK boycott 2026", "INDIA bloc crisis", "MK Stalin", "Tamil Nadu politics", "Congress betrayal", "opposition unity", "DMK news", "June 8 meeting", "political news India {year}"]

Output JSON array:"""

        try:
            from gemini_engine import GeminiEngine
            engine = GeminiEngine()
            response = engine.ask(prompt)
            if response:
                response = response.strip()
                if response.startswith("```"):
                    lines = response.split("\n")
                    response = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
                    response = response.strip()
                tags = json.loads(response)
                if isinstance(tags, list):
                    cleaned = []
                    seen = set()
                    for t in tags:
                        t = str(t).strip().strip('"').strip("'")
                        if t and t.lower() not in seen and len(t) > 1:
                            cleaned.append(t)
                            seen.add(t.lower())
                    print(f"    [TopicTags] Generated {len(cleaned)} topic-specific tags: {cleaned[:5]}...")
                    return cleaned[:12]
        except Exception as e:
            print(f"    [TopicTags] LLM generation failed: {e}")

        # Fallback: extract tags from title using simple NLP
        print("    [TopicTags] Using fallback title-based tag extraction")
        fallback_tags = []
        words = topic_title.split()
        skip = {"the","and","for","are","but","not","you","all","can","had","her","was",
                "one","our","out","a","an","to","of","in","on","at","by","is","it","as",
                "be","or","if","up","so","no","has","have","do","does","did","will",
                "would","could","should","may","might","shall","this","that","these",
                "those","from","with","about","into","over","after","before","between",
                "under","above","through","during","without","within","along","across",
                "behind","beyond","toward","towards","upon","among","against",
                "throughout","until","unless","since","while","where","when","how",
                "what","which","who","whom","whose","why","news","update","breaking",
                "latest","today","just","new","says","said","told","announced",
                "reported","claims","vs","meets","meeting","talks","talk","visit",
                "visits","arrives","leaves","quits","resigns","joins","launches",
                "opens","closes","holds","takes","gives","makes","gets","goes",
                "comes","over","amid","following","ahead"}

        proper_nouns = []
        for w in words:
            clean = w.strip(".,;:!?()[]{}\"'").strip()
            if len(clean) > 2 and clean[0].isupper() and clean.lower() not in skip:
                proper_nouns.append(clean)

        if proper_nouns:
            fallback_tags.append(f"{proper_nouns[0]} news")
            if len(proper_nouns) > 1:
                fallback_tags.append(f"{' '.join(proper_nouns[:2])}")
            if len(proper_nouns) > 2:
                fallback_tags.append(f"{proper_nouns[0]} {proper_nouns[-1]}")

        if source:
            src_clean = source.strip()
            if src_clean:
                fallback_tags.append(f"{src_clean} news")

        fallback_tags.append(f"news {year}")

        seen = set()
        result = []
        for t in fallback_tags:
            if t.lower() not in seen:
                result.append(t)
                seen.add(t.lower())

        print(f"    [TopicTags] Fallback generated {len(result)} tags: {result}")
        return result[:8]

    def _build_hashtag_block(self, topic: dict, title_raw: str) -> str:
        """
        A5.4: Build a hashtag block with real trending hashtag discovery.
        1. Fetches trending hashtags from YouTube autosuggest
        2. Adds keyword-matched topic hashtags
        3. Adds base channel hashtags
        Deduplicates and limits to 15 total.
        """
        base_hashtags = [
            "#TeluguNews", "#AndhraPradesh", "#Telangana",
            "#IndiaNews", "#ViralDNA", "#NRI", "#TeluguDiaspora",
        ]

        # A1.7: Bilingual hashtag injection
        telugu_hashtags = {
            "andhra": "#AndhraNews", "telangana": "#TelanganaNews",
            "telugu": "#Telugu", "vijayawada": "#Vijayawada",
            "vizag": "#Vizag", "hyderabad": "#Hyderabad",
            "amaravati": "#Amaravati", "guntur": "#Guntur",
            "tirupati": "#Tirupati", "nellore": "#Nellore",
            "kakinada": "#Kakinada", "rajamundry": "#Rajamundry",
        }

        text = f"{title_raw} {topic.get('description', '')}".lower()
        topic_tags = []

        # Keyword-matched topic hashtags
        tag_map = {
            "telugu": "#Telugu", "andhra": "#AndhraNews", "telangana": "#TelanganaNews",
            "vizag": "#Vizag", "visakhapatnam": "#Visakhapatnam", "hyderabad": "#Hyderabad",
            "vijayawada": "#Vijayawada", "amaravati": "#Amaravati",
            "h1b": "#H1B", "visa": "#Visa", "immigration": "#Immigration",
            "cricket": "#Cricket", "movie": "#Tollywood", "cinema": "#Tollywood",
            "budget": "#Budget", "economy": "#Economy", "election": "#Election",
            "usa": "#USA", "uk": "#UK", "canada": "#Canada", "australia": "#Australia",
            "breaking": "#BreakingNews", "urgent": "#Urgent", "health": "#Health",
            "tech": "#Tech", "job": "#Jobs", "career": "#Career",
        }
        for keyword, hashtag in tag_map.items():
            if keyword in text and hashtag not in base_hashtags:
                topic_tags.append(hashtag)

        # Location-based Telugu hashtags
        for keyword, hashtag in telugu_hashtags.items():
            if keyword in text and hashtag not in base_hashtags and hashtag not in topic_tags:
                topic_tags.append(hashtag)

        # A5.4: Real trending hashtags from YouTube autosuggest
        trending_tags = self._fetch_trending_hashtags(title_raw)
        for tag in trending_tags:
            if tag not in topic_tags and tag not in base_hashtags:
                topic_tags.append(tag)

        all_tags = base_hashtags + topic_tags
        return " ".join(all_tags[:15])

    # A2.8: Related links builder
    def _build_related_links(self, topic: dict) -> list:
        """Build related video/channel links section for description."""
        links = []
        title_lower = (topic.get("title", "") + " " + topic.get("description", "")).lower()

        # Topic-based related playlist links
        if any(kw in title_lower for kw in ["visa", "h1b", "immigration", "green card"]):
            links.append(("Visa & Immigration Playlist", self.main_playlist_url or "https://youtube.com/@ViralDNA"))
        if any(kw in title_lower for kw in ["telangana", "hyderabad"]):
            links.append(("Telangana News Playlist", self.main_playlist_url or "https://youtube.com/@ViralDNA"))
        if any(kw in title_lower for kw in ["andhra", "vizag", "vijayawada", "amaravati"]):
            links.append(("Andhra Pradesh News Playlist", self.main_playlist_url or "https://youtube.com/@ViralDNA"))
        if any(kw in title_lower for kw in ["cricket", "ipl", "match", "score"]):
            links.append(("Cricket & Sports Playlist", self.main_playlist_url or "https://youtube.com/@ViralDNA"))

        # Always add channel subscribe link
        links.append(("Subscribe to ViralDNA", "https://youtube.com/@ViralDNA?sub_confirmation=1"))

        return links

    # H2.3: Topic-based playlist routing
    # Topic-specific playlist IDs (configurable via config.py)
    TOPIC_PLAYLIST_MAP = {
        "visa_immigration": "",    # Set via config: topic_playlist_visa
        "telangana_politics": "",  # Set via config: topic_playlist_telangana
        "andhra_politics": "",     # Set via config: topic_playlist_andhra
        "cricket": "",             # Set via config: topic_playlist_cricket
        "tollywood": "",           # Set via config: topic_playlist_tollywood
        "jobs_career": "",         # Set via config: topic_playlist_jobs
        "health": "",              # Set via config: topic_playlist_health
        "technology": "",          # Set via config: topic_playlist_tech
    }

    def _resolve_topic_playlist(self, topic: dict, publish_decision=None) -> str:
        """Resolve the best playlist ID based on topic content pillars and series."""
        # Use publish_decision content_pillars if available
        if publish_decision and hasattr(publish_decision, 'content_pillars'):
            pillars = publish_decision.content_pillars
        else:
            pillars = topic.get("content_pillars", {})
            if isinstance(pillars, dict):
                pillars = list(pillars.keys())

        if not pillars:
            return self.main_playlist_id

        # Map pillars to topic playlists
        pillar_to_playlist = {
            "immigration": "visa_immigration",
            "jobs_career": "jobs_career",
            "finance_investment": "andhra_politics",  # fallback to main politics playlist
            "health_wellness": "health",
            "tech_digital": "technology",
            "real_estate": "andhra_politics",
            "culture_cinema": "tollywood",
        }

        for pillar in pillars:
            if pillar in pillar_to_playlist:
                topic_key = pillar_to_playlist[pillar]
                playlist_id = self.TOPIC_PLAYLIST_MAP.get(topic_key, "")
                if playlist_id:
                    return playlist_id

        # Use content_series playlist if topic belongs to a series
        if publish_decision and hasattr(publish_decision, 'content_series'):
            series = publish_decision.content_series
            if series:
                series_key = series.replace("-", "_")
                if series_key in self.TOPIC_PLAYLIST_MAP:
                    sid = self.TOPIC_PLAYLIST_MAP.get(series_key, "")
                    if sid:
                        return sid

        return self.main_playlist_id

    # ─── A2.9: Snippet Prefix Builder ───
    def _build_snippet_prefix(self, title_raw: str, desc_raw: str,
                               seo_keyword_line: str = "") -> str:
        """
        Build the first ~150 chars of description for YouTube search snippet.
        This is the text that appears in YouTube/Google search results.
        
        v82.3: Lead with YEAR + freshness signal for news content.
        " telugu news today 2026" gets 9.5K/mo vs "telugu news" alone.
        Max 142 chars visible in search snippet.
        """
        import datetime
        year = datetime.datetime.now().year

        # Extract top SEO keywords for the opening line
        seo_kws = self._extract_seo_keywords({"title": title_raw, "description": desc_raw}, title_raw, desc_raw)
        kw_str = ""
        if seo_kws:
            # Use ONLY the strongest 2 keywords (not 4 — that's keyword stuffing)
            kw_str = " ".join(seo_kws[:2]).strip()

        # Build freshness-prefixed snippet
        clean_desc = desc_raw.strip()
        # Strip common leading phrases that waste snippet space
        for prefix in ["According to reports, ", "Reports say ", "It is reported that "]:
            if clean_desc.lower().startswith(prefix.lower()):
                clean_desc = clean_desc[len(prefix):]
                break

        # v82.3: Inject year for news freshness signal
        freshness = f"{year} update"
        snippet = clean_desc[:100].strip()
        if kw_str and kw_str.lower() not in snippet.lower():
            snippet = f"{kw_str} {freshness} | {snippet}"[:140]
        else:
            if str(year) not in snippet:
                snippet = f"{freshness}: {snippet}"[:140]
        snippet = snippet[:140]

        return snippet

    def _generate_chapters(self, topic: dict, desc_raw: str, is_short: bool) -> list:
        """v82.3: Generate timestamp chapters for YouTube 'Key Moments' in search.
        
        Chapters = watch-time signal + search result enhancement.
        For Shorts: returns empty (Shorts don't support chapters).
        """
        if is_short:
            return []

        # Build keyword-rich chapters from topic title
        title = topic.get("title", "")
        # Extract key entities (proper nouns) from title
        words = title.split()
        entities = [w for w in words if len(w) > 2 and w[0].isupper()]
        
        # Generate topic-specific chapters
        chapters = [("0:00", "Breaking")]
        
        if len(entities) >= 2:
            chapters.append(("0:15", f"{entities[0]} {entities[1]}"))
        elif len(entities) == 1:
            chapters.append(("0:15", entities[0]))
        else:
            chapters.append(("0:15", "The Story"))
        
        chapters.append(("1:30", "Key Details"))
        chapters.append(("3:00", "What Happens Next"))
        chapters.append(("4:30", "Impact on India"))
        
        # Final chapter from topic
        if entities:
            key = " ".join(entities[:2])
            chapters.append(("5:30", f"{key} — Key Takeaway"))
        else:
            chapters.append(("5:30", "Key Takeaway"))

        return chapters

    # ─── v82.3: Metadata Quality Audit ───
    def _audit_metadata(self, title: str, description: str, tags: list,
                         is_short: bool) -> dict:
        """Run 20+ quality/growth checks on metadata BEFORE output.
        
        Returns: {
            "passed": bool,          # True if no CRITICAL failures
            "score": int,            # 0-100 growth readiness score
            "critical": [str],       # Blockers that MUST be fixed
            "warnings": [str],       # Growth opportunities missed
            "checks": {str: bool}    # Individual check pass/fail
        }
        """
        import datetime
        year = str(datetime.datetime.now().year)
        checks = {}
        critical = []
        warnings = []

        desc_lines = [l for l in description.split("\n") if l.strip()]
        desc_lower = description.lower()
        title_lower = title.lower()

        # ═══ CRITICAL CHECKS (block output if failed) ═══

        # C1: Title length in sweet spot (40-70 chars)
        tlen = len(title)
        checks["title_length_sweet"] = 40 <= tlen <= 70
        if not checks["title_length_sweet"]:
            if tlen < 30:
                critical.append(f"Title too short ({tlen} chars) — YouTube treats as low-info")
            elif tlen > 100:
                critical.append(f"Title too long ({tlen} chars) — truncated in search results")
            else:
                warnings.append(f"Title {tlen} chars — sweet spot is 40-70 for CTR")

        # C1b: v82.5 — Title must NOT be generic/vague
        generic_title_patterns = [
            r"^political developments",
            r"^congress leaders",
            r"^leaders show",
            r"^what it means$",
            r"^latest developments",
            r"^breaking news",
            r"^news update",
            r"^today'?s news",
            r"^top news",
            r"^latest news",
            r"^news today",
            r"^just in",
            r"^update:",
            r"^news:",
        ]
        is_generic_title = any(re.search(p, title_lower) for p in generic_title_patterns)
        # Also check: title must have at least 2 proper nouns (names/places)
        title_words = title.split()
        skip_words = {
            "the","and","for","are","but","not","you","all","can","had","her","was","one","our",
            "out","breaking","urgent","news","telugu","india","andhra","telangana","update",
            "latest","today","just","what","how","why","when","where","who","this","that","with",
            "from","have","been","will","would","could","should","may","might","must","shall",
            "explained","analysis","full","complete","simple","key","facts","main","important",
        }
        proper_nouns_in_title = [
            w for w in title_words
            if len(w) > 2 and w[0].isupper() and w.lower() not in skip_words
        ]
        checks["title_not_generic"] = not is_generic_title and len(proper_nouns_in_title) >= 2
        if not checks["title_not_generic"]:
            if is_generic_title:
                critical.append(f"Title is too generic/vague: '{title}'. Must include specific names, places, or data — not generic news phrases.")
            elif len(proper_nouns_in_title) < 2:
                critical.append(f"Title lacks specific proper nouns: '{title}'. Found: {proper_nouns_in_title}. Need 2+ names/places for SEO.")

        # C2: Year in title (freshness signal for news content)
        checks["year_in_title"] = year in title
        if not checks["year_in_title"]:
            critical.append(f"Year {year} missing from title — news without year = evergreen (lower priority)")

        # C2b: v82.5 — Short titles must be distinct from main title
        # (Checked at pipeline level, not here — this is per-video)

        # C3: Subscribe CTA in first 3 non-empty lines
        first3 = " ".join(desc_lines[:3]).lower()
        checks["subscribe_above_fold"] = "subscribe" in first3
        if not checks["subscribe_above_fold"]:
            critical.append("Subscribe CTA not in first 3 lines — mobile users never see it")

        # C4: No "edge-tts" or engine names in description
        checks["no_engine_exposure"] = "edge-tts" not in desc_lower and "edgetts" not in desc_lower
        if not checks["no_engine_exposure"]:
            critical.append("TTS engine name 'edge-tts' exposed in description — privacy + unprofessional")

        # C5: Brand name consistency — "TheViralDNA" not "The Viral DNA"
        checks["brand_consistent"] = "the viral dna" not in desc_lower
        if not checks["brand_consistent"]:
            critical.append("Brand name 'The Viral DNA' found — must be 'TheViralDNA' (one word)")

        # C6: Hashtags have # prefix
        hashtag_section = ""
        for line in desc_lines:
            if line.strip().startswith("#"):
                hashtag_section = line
                break
        bare_hashtags = [w for w in hashtag_section.split() if len(w) > 3 and not w.startswith("#")
                         and w[0].isupper() and not w.startswith("http")]
        checks["hashtags_has_prefix"] = len(bare_hashtags) == 0
        if not checks["hashtags_has_prefix"] and bare_hashtags:
            warnings.append(f"Hashtags without # prefix: {bare_hashtags[:3]}")

        # C7: First 3 hashtags are search-volume hashtags (not brand)
        # Find the hashtag line (first line starting with #TeluguNews, #AndhraPradesh, etc.)
        hashtag_line = ""
        for line in desc_lines:
            stripped = line.strip()
            if stripped.startswith("#") and len(stripped.split()) >= 3:
                hashtag_line = stripped
                break
        first3_hash = [w for w in hashtag_line.split() if w.startswith("#")][:3]
        first3_lower = [h.lower() for h in first3_hash]
        checks["hashtags_search_first"] = "#telugunews" in first3_lower or "#andhrapradesh" in first3_lower
        if not checks["hashtags_search_first"]:
            warnings.append("First 3 hashtags not #TeluguNews/#AndhraPradesh/#Telangana — these show above title")

        # C8: Description not empty / too short
        checks["description_min_length"] = len(description) >= 200
        if not checks["description_min_length"]:
            critical.append(f"Description too short ({len(description)} chars) — YouTube demotes thin descriptions")

        # C9: Timestamps/chapters present (not Shorts)
        has_chapters = any(":" in line and any(c.isdigit() for c in line) 
                          and ("intro" in line.lower() or "story" in line.lower() or "chapter" in line.lower())
                          for line in desc_lines)
        checks["chapters_present"] = is_short or has_chapters
        if not checks["chapters_present"]:
            warnings.append("No timestamp chapters — missing 'Key Moments' in search results")

        # ═══ HIGH-IMPACT GROWTH CHECKS ═══

        # G1: Competitor tags check — competitor channel names should NOT be in tags
        # Tagging "TV9 Telugu" or "Sakshi" helps YouTube suggest THEIR videos, not ours.
        competitor_tags = ["tv9", "sakshi", "eenadu", "ntv", "abn"]
        tags_lower = [t.lower() for t in tags]
        has_competitor = any(c in " ".join(tags_lower) for c in competitor_tags)
        checks["no_competitor_tags"] = not has_competitor
        if has_competitor:
            warnings.append("Competitor channel tags found (TV9/Sakshi/Eenadu/NTV/ABN) — these help competitors' suggested videos, not ours")

        # G2: Telugu transliteration tags
        has_telugu_translit = any("varthalu" in t.lower() for t in tags)
        checks["telugu_transliteration_tags"] = has_telugu_translit
        if not checks["telugu_transliteration_tags"]:
            warnings.append("No Telugu transliteration tags (telugu varthalu etc.) — bilingual searchers")

        # G3: Year in snippet/description first line
        checks["year_in_snippet"] = year in desc_lines[0] if desc_lines else False
        if not checks["year_in_snippet"]:
            warnings.append(f"Year {year} missing from description first line — freshness signal lost")

        # G4: Tags count in optimal range (15-30)
        checks["tag_count_optimal"] = 15 <= len(tags) <= 30
        if not checks["tag_count_optimal"]:
            if len(tags) < 10:
                warnings.append(f"Only {len(tags)} tags — YouTube allows 500 chars, use 15-30")
            elif len(tags) > 30:
                warnings.append(f"{len(tags)} tags — diminishing returns past 30")

        # G5: Dynamic year in tags (not hardcoded)
        checks["tags_dynamic_year"] = any(year in t for t in tags)
        if not checks["tags_dynamic_year"]:
            warnings.append(f"No tag contains current year {year} — add 'trending India {year}'")

        # G5b: v82.6 — Topic-specific tags must be present (not just generic channel tags)
        # These are the known generic channel-level tags that should NOT be the only tags
        _generic_channel_tags = {
            "theviraldna", "tv9 telugu", "sakshi news", "eenadu news", "ntv telugu",
            "abn andhra", "telugu varthalu", "andhra varthalu", "telangana varthalu",
            "trending india", "telugu news today", "andhra pradesh news", "telangana news",
            "ap news today", "hyderabad news", "vijayawada news", "vizag news",
            "amaravati news", "guntur news", "telugu breaking news", "tenglish news",
            "india news today", "nri telugu news", "telugu current affairs",
            "ap telangana updates", "viral news india", "telugu states news",
        }
        _tag_lower = [t.lower().strip() for t in tags]
        _topic_specific_count = sum(1 for t in _tag_lower if t not in _generic_channel_tags)
        checks["topic_tags_present"] = _topic_specific_count >= 5
        if not checks["topic_tags_present"]:
            if _topic_specific_count == 0:
                critical.append(f"ZERO topic-specific tags — all {len(tags)} tags are generic channel tags. Tags must include names, places, and entities from the topic content.")
            else:
                warnings.append(f"Only {_topic_specific_count} topic-specific tags — need at least 5. Current tags: {tags[:8]}")

        # G6: No duplicate text in SUMMARY vs BACKGROUND
        summary_text = ""
        bg_text = ""
        for i, line in enumerate(desc_lines):
            if "SUMMARY" in line.upper() and i + 1 < len(desc_lines):
                summary_text = desc_lines[i + 1][:50].lower()
            if "CONTEXT" in line.upper() and i + 1 < len(desc_lines):
                bg_text = desc_lines[i + 1][:50].lower()
        if summary_text and bg_text:
            checks["summary_not_duplicate"] = summary_text != bg_text
            if not checks["summary_not_duplicate"]:
                warnings.append("SUMMARY and CONTEXT start with same text — YouTube sees as low-effort")
        else:
            checks["summary_not_duplicate"] = True

        # G7: Like/Comment CTAs present
        checks["engagement_ctas"] = "like" in desc_lower and "comment" in desc_lower
        if not checks["engagement_ctas"]:
            warnings.append("Missing Like/Comment CTAs — engagement signals drive recommendations")

        # G8: Channel schedule mentioned
        checks["schedule_mentioned"] = "9:00" in description or "9:00 AM" in description
        if not checks["schedule_mentioned"]:
            warnings.append("No upload schedule in description — returning viewers need predictability")

        # ═══ STYLE/CLEANLINESS CHECKS ═══

        # S1: No double separator lines
        double_sep = any(desc_lines[i] == desc_lines[i+1] and 
                        set(desc_lines[i]) <= {"━", "─", "═", "—"}
                        for i in range(len(desc_lines)-1))
        checks["no_double_separators"] = not double_sep
        if not checks["no_double_separators"]:
            warnings.append("Double separator lines — wastes description space")

        # S2: Smart quotes preserved properly — check ALL apostrophe-like Unicode chars
        _smart_quote_chars = ["\u2018", "\u2019", "\u2032", "\u2035", "\u02bc", "\u02bb", "\uff07", "\u201b", "\u2039", "\u203a"]
        checks["smart_quotes_converted"] = not any(c in description for c in _smart_quote_chars)
        if not checks["smart_quotes_converted"]:
            warnings.append("Smart quotes not converted to ASCII — rendering issues on some devices")

        # S3: Shorts tags if is_short
        if is_short:
            checks["shorts_tags"] = any("shorts" in t.lower() for t in tags)
            if not checks["shorts_tags"]:
                warnings.append("Shorts video missing Shorts-specific tags")
        else:
            checks["shorts_tags"] = True  # N/A for main video

        # S4: No bare URL-only description lines
        bare_urls = [i for i, l in enumerate(desc_lines) 
                     if l.strip().startswith("http") and not any(c in l for c in [" ", "—", "|"])]
        checks["no_bare_urls"] = len(bare_urls) == 0
        if not checks["no_bare_urls"]:
            warnings.append("Bare URLs without context text — YouTube may flag as spam")

        # S5: Disclosure present (YouTube AI content policy)
        checks["disclosure_present"] = "ai" in desc_lower and ("synthetic" in desc_lower or "ai-assisted" in desc_lower or "ai voice" in desc_lower)
        if not checks["disclosure_present"]:
            critical.append("No AI content disclosure — YouTube policy violation risk for AI-generated content")

        # ═══ SCORE CALCULATION ═══
        passed_checks = sum(1 for v in checks.values() if v)
        total_checks = len(checks)
        score = int((passed_checks / total_checks) * 100) if total_checks > 0 else 0

        # Reduce score for warnings
        score = max(0, score - len(warnings) * 3)

        result = {
            "passed": len(critical) == 0,
            "score": score,
            "critical": critical,
            "warnings": warnings,
            "checks": checks,
            "summary": f"{passed_checks}/{total_checks} checks passed, score {score}/100"
        }

        # Print audit report
        print(f"\n{'═'*50}")
        print(f"📋 METADATA QUALITY AUDIT (v82.3)")
        print(f"{'═'*50}")
        print(f"  Score: {score}/100")
        print(f"  Status: {'✅ PASSED' if result['passed'] else '❌ FAILED'}")
        print(f"  Checks: {passed_checks}/{total_checks} passed")
        if critical:
            print(f"\n  🚫 CRITICAL ({len(critical)}):")
            for c in critical:
                print(f"     • {c}")
        if warnings:
            print(f"\n  ⚠️  WARNINGS ({len(warnings)}):")
            for w in warnings:
                print(f"     • {w}")
        print(f"{'═'*50}\n")

        return result

    # ─── E2.5: Affiliate Links ───
    # Only populated when real affiliate URLs are configured.
    # No placeholder/fake links — empty by default.
    AFFILIATE_LINK_TEMPLATES = {}

    def _build_affiliate_links(self, topic: dict, title_raw: str) -> list:
        """E2.5: Build affiliate link section if topic matches high-value categories."""
        text = f"{title_raw} {topic.get('description', '')} {topic.get('title', '')}".lower()
        links = []
        for keyword, (label, url) in self.AFFILIATE_LINK_TEMPLATES.items():
            if keyword in text:
                links.append((label, url))
        return links[:3]  # Max 3 affiliate links to avoid spam perception

    # ─── E2.6: Crowdfunding / Support Links ───
    # Only shown when real support URLs are configured. No placeholders.
    CROWDFUNDING_LINE = ""

    def _build_crowdfunding_line(self, topic: dict) -> str:
        """E2.6: Return crowdfunding CTA line for description."""
        return self.CROWDFUNDING_LINE

    # ─── E2.3: Merchandise Shelf Placeholder ───
    # Only shown when real merch URL is configured. No placeholders.
    MERCH_LINE = ""

    def _build_merch_line(self, topic: dict) -> str:
        """E2.3: Return merchandise link line for description."""
        return self.MERCH_LINE

    # ─── Pinned Comment Builders ───
    def _build_main_pinned_comment(self, topic: dict, playlist_url: str) -> str:
        title = topic.get("title", "this story").strip()
        if len(title) > 60:
            title = title[:57] + "..."
        return (
            f"📌 What do you think about {title}?\n\n"
            f"💬 Drop your thoughts — we read every comment!\n"
            f"👍 Like this video for more Telugu diaspora news.\n"
            f"🔔 Subscribe & hit the bell!\n\n"
            f"📺 Full playlist: {playlist_url}\n"
            f"🌐 ViralDNA — Stay connected to your roots"
        )

    def _build_short_pinned_comment(self, topic: dict, short_idx: int,
                                     playlist_url: str,
                                     main_video_url: str = None) -> str:
        title = topic.get("title", "this story").strip()
        if len(title) > 50:
            title = title[:47] + "..."
        ctas = [
            f"🔥 What's your take on {title}? Comment below!",
            f"💬 Does this affect you or your family? Share your story!",
            f"🤔 Did you know about this? Like & follow for more!",
        ]
        cta = ctas[(short_idx - 1) % len(ctas)]

        # C2.2/C2.3: Shorts-to-long CTA
        long_cta = ""
        if main_video_url:
            long_cta = f"\n\n🎥 Watch the FULL report: {main_video_url}"

        return (
            f"{cta}\n\n"
            f"👍 Like • 🔔 Subscribe\n"
            f"\n#ViralDNA #TeluguNews #Shorts"
            f"{long_cta}"
        )

    # ─── Single Video Upload (one variant) ───
    def upload_single_video(self, title_raw: str, desc_raw: str, rag_context: str,
                            video_path: str, thumbnail_path: str = None,
                            is_short: bool = False, pinned_comment: str = None,
                            short_index: int = 0, variant_idx: int = 0,
                            topic: dict = None, script_text: str = "",
                            duration_s: float = 0,
                            upload_schedule: dict = None) -> dict:
        """Upload a single video variant. Returns status dict."""
        if not os.path.exists(video_path):
            return {"status": "failed", "error": f"Video not found: {video_path}"}

        try:
            print(f"▶ Uploading: {os.path.basename(video_path)} (variant {variant_idx + 1}, short: {is_short})...")

            body = self._create_metadata(title_raw, desc_raw, rag_context,
                                         topic=topic, is_short=is_short,
                                         short_index=short_index, variant_idx=variant_idx,
                                         upload_schedule=upload_schedule)

            media = MediaFileUpload(video_path, mimetype=self.video_mimetype,
                                    chunksize=self.upload_chunk_size, resumable=True)
            video_id = self._execute_resumable_upload(media, body,
                                                       notify_subscribers=self.notify_subscribers)
            video_url = f"https://youtube.com/watch?v={video_id}"

            # Thumbnail (main videos only — shorts use frame injection)
            if thumbnail_path and not is_short:
                self._upload_thumbnail(video_id, thumbnail_path)

            # Pinned comment
            if pinned_comment:
                self._add_pinned_comment(video_id, pinned_comment)

            # Subtitles/captions
            if self.subtitles_enabled and script_text:
                srt_path = os.path.join(tempfile.gettempdir(), f"captions_{video_id}.srt")
                if self._generate_srt(script_text, srt_path, duration_s):
                    self._upload_captions(video_id, srt_path)
                    try:
                        os.remove(srt_path)
                    except OSError:
                        pass

            # End screen / cards
            self._update_end_screen_and_cards(video_id, topic)

            return {
                "status": "success",
                "youtube_id": video_id,
                "youtube_url": video_url,
                "title_used": body["snippet"]["title"],
                "variant": variant_idx + 1,
                "uploaded_at": datetime.now(self.ist).isoformat()
            }
        except Exception as e:
            print(f"  ❌ Upload error: {e}")
            return {"status": "failed", "error": str(e), "variant": variant_idx + 1}

    # ─── Full Production Slot Upload (A/B testing approach) ───
    def upload_production_slot(self, topic: dict, videos_dir: str, thumbnails_dir: str,
                                script_payload=None, publish_decision=None,
                                upload_schedule: dict = None,
                                topic_slug: str = "") -> dict:
        """
        Uploads ONE video per slot (best title variant only).
        Per-variant thumbnails are generated for YouTube Studio A/B testing.
        Uploading duplicate videos with different titles = spam risk.
        Total: 1 main + N shorts (based on publish_decision)
        v86.0: Added topic_slug parameter for correct file naming.
        """
        upload_results = {
            "main": None,
            "shorts": {},
            "overall_status": "pending"
        }

        # Determine file names — support both old (production_*) and new (<slug>_) naming
        slug = topic_slug or topic.get("slug", "topic")
        main_video_path = os.path.join(videos_dir, "production_main.mp4")
        if not os.path.exists(main_video_path):
            main_video_path = os.path.join(videos_dir, f"{slug}_Main.mp4")
        main_thumb_base = os.path.join(thumbnails_dir, "production_branded.jpg")
        if not os.path.exists(main_thumb_base):
            main_thumb_base = os.path.join(thumbnails_dir, f"{slug}_branded.jpg")
        if not os.path.exists(main_thumb_base):
            main_thumb_base = os.path.join(thumbnails_dir, f"{slug}_thumb.jpg")

        # Determine how many shorts to produce
        # Handle publish_decision as object, dict, or string (checkpoint round-trip)
        num_shorts = 2
        produce_main = True
        if publish_decision:
            if isinstance(publish_decision, str):
                # Dataclass was serialized to string via json.dumps(default=str)
                print(f"  📋 publish_decision is a string (serialized): {publish_decision[:80]}")
                # Parse num_shorts from string representation
                import re
                m = re.search(r'num_shorts=(\d+)', publish_decision)
                if m:
                    num_shorts = int(m.group(1))
                m_main = re.search(r'produce_main=(True|False)', publish_decision)
                if m_main:
                    produce_main = m_main.group(1) == 'True'
            elif isinstance(publish_decision, dict):
                num_shorts = publish_decision.get("num_shorts", 2)
                produce_main = publish_decision.get("produce_main", True)
                print(f"  📋 Upload plan: produce_main={produce_main}, num_shorts={num_shorts}")
            else:
                # Original dataclass object
                num_shorts = publish_decision.num_shorts
                produce_main = publish_decision.produce_main
                print(f"  📋 Upload plan: produce_main={produce_main}, num_shorts={num_shorts}")
            if not produce_main:
                num_shorts = max(num_shorts, 1)
        else:
            print(f"  📋 No publish_decision provided, using defaults: num_shorts={num_shorts}")

        # ── 0. Upload Dedup: Fetch existing video titles once ──
        print("  🔍 Checking existing uploads for dedup...")
        existing_videos = self._get_existing_video_titles(max_results=50)
        print(f"  📊 Found {len(existing_videos)} existing videos on channel for dedup check")

        # ── 1. Main Video — Best Title Only (variant 0) ──
        main_script_text = script_payload.main_clean if script_payload else ""
        main_duration = script_payload.main_duration if script_payload else 0
        main_title_variants = script_payload.main_title_variants if script_payload else []

        if produce_main and os.path.exists(main_video_path) and main_title_variants:
            # Pick best title (variant 0 = highest-scoring from Gemini)
            best_variant = main_title_variants[0]
            title_raw = best_variant.get("title", "BREAKING NEWS")

            # ── Dedup check for main video — against ALL existing videos ──
            # v1.8.1: Compare against all videos (including shorts) since
            # _get_existing_video_titles doesn't provide is_short flag.
            is_dup, matched = self._is_duplicate_title(title_raw, existing_videos)
            if is_dup:
                print(f"  ⏭️ SKIPPING main video — duplicate title detected!")
                print(f"     New:      \"{title_raw[:80]}\"")
                print(f"     Existing: \"{matched[:80]}\"")
                upload_results["main"] = {"status": "skipped_duplicate", "title": title_raw, "matched_existing": matched}
            else:
                desc_raw = best_variant.get("description", "A detailed news report from ViralDNA.")
                rag = script_payload.main_clean[:500] if script_payload else ""
                pinned = self._build_main_pinned_comment(topic, self.main_playlist_url)

                # Use v1 thumbnail (best variant) as primary
                thumb = os.path.join(thumbnails_dir, "production_branded_v1.jpg")
                if not os.path.exists(thumb):
                    thumb = main_thumb_base

                print(f"  📤 Main video: uploading best title: \"{title_raw[:60]}...\"")
                res = self.upload_single_video(
                    title_raw=title_raw, desc_raw=desc_raw, rag_context=rag,
                    video_path=main_video_path, thumbnail_path=thumb,
                    is_short=False, pinned_comment=pinned,
                    variant_idx=0, topic=topic,
                    script_text=main_script_text, duration_s=main_duration,
                    upload_schedule=upload_schedule
                )
                upload_results["main"] = res

                # Rate-limit delay between uploads (avoid 429 per-minute quota)
                if num_shorts > 0:
                    import time
                    print(f"  ⏳ Rate-limit pause: 10s before uploading shorts...")
                    time.sleep(10)

                # Add to topic-specific playlist (H2.3)
                vid = res.get("youtube_id")
                if vid:
                    topic_playlist = self._resolve_topic_playlist(topic, publish_decision)
                    playlist_to_use = topic_playlist if topic_playlist else self.main_playlist_id
                    if playlist_to_use:
                        self._add_to_playlist(vid, playlist_to_use)

                # Add newly uploaded video to existing_videos list so shorts dedup works
                if res.get("status") == "success":
                    existing_videos.append({"title": title_raw, "video_id": vid, "is_short": False})

            # Log other variants for reference (manual A/B testing in Studio)
            if len(main_title_variants) > 1:
                print(f"  📋 Alternative titles for Studio A/B testing:")
                for v_idx, variant in enumerate(main_title_variants[1:], 1):
                    alt_thumb = os.path.join(thumbnails_dir, f"production_branded_v{v_idx + 1}.jpg")
                    print(f"     Variant {v_idx + 1}: \"{variant.get('title', '')[:60]}...\"")
                    if os.path.exists(alt_thumb):
                        print(f"     Thumbnail: {alt_thumb}")
        else:
            if not produce_main:
                print("  ⏭️ Skipping main video upload (publish decision: shorts only)")
            else:
                print("  ⚠️ Main video or title variants missing, skipping main upload")

        # Store main video URL for Shorts-to-long CTA (C2.2/C2.3)
        main_video_url = None
        if upload_results.get("main") and upload_results["main"].get("status") == "success":
            main_video_url = upload_results["main"].get("youtube_url")

        # ── 2. Shorts — Best Title Only ──
        for s_idx in range(1, num_shorts + 1):
            short_key = f"short_{s_idx}"
            short_video_path = os.path.join(videos_dir, f"production_short_{s_idx}.mp4")
            if not os.path.exists(short_video_path):
                short_video_path = os.path.join(videos_dir, f"{slug}_Short{s_idx}.mp4")
            short_title_variants = getattr(script_payload, f"{short_key}_title_variants", []) if script_payload else []
            short_script_text = getattr(script_payload, f"{short_key}_raw", "") if script_payload else ""
            short_duration = getattr(script_payload, f"{short_key}_duration", 0) if script_payload else 0
            short_thumb = os.path.join(thumbnails_dir, f"short_{s_idx}_thumb.jpg")
            # Also check the newer naming convention from ThumbnailCreator
            short_thumb_v2 = os.path.join(thumbnails_dir, f"short_{s_idx}_branded.jpg")
            if not os.path.exists(short_thumb) and os.path.exists(short_thumb_v2):
                short_thumb = short_thumb_v2
            # Also check <slug>_short_N naming
            if not os.path.exists(short_thumb):
                short_thumb_v3 = os.path.join(thumbnails_dir, f"{slug}_short_{s_idx}.jpg")
                if os.path.exists(short_thumb_v3):
                    short_thumb = short_thumb_v3

            if os.path.exists(short_video_path) and short_title_variants:
                # Pick best title (variant 0)
                best_variant = short_title_variants[0]
                title_raw = best_variant.get("title", f"Short {s_idx}")

                # ── Dedup check for short — against ALL existing videos ──
                # v1.8.1: Compare against all videos (including mains) since
                # _get_existing_video_titles doesn't provide is_short flag.
                is_dup, matched = self._is_duplicate_title(title_raw, existing_videos)
                if is_dup:
                    print(f"  ⏭️ SKIPPING {short_key} — duplicate title detected!")
                    print(f"     New:      \"{title_raw[:80]}\"")
                    print(f"     Existing: \"{matched[:80]}\"")
                    upload_results["shorts"][short_key] = {"status": "skipped_duplicate", "title": title_raw, "matched_existing": matched}
                else:
                    desc_raw = best_variant.get("description", "Quick news update from ViralDNA.")
                    # C2.2/C2.3: Inject Shorts-to-long CTA into description
                    cta_url = main_video_url if main_video_url else "https://youtube.com/@ViralDNA"
                    cta_line = f"🎥 Watch the full story: {cta_url}"
                    if cta_url not in desc_raw:
                        desc_raw = f"{desc_raw}\n\n{cta_line}"
                    rag = short_script_text[:300] if short_script_text else ""
                    pinned = self._build_short_pinned_comment(
                        topic, s_idx, self.shorts_playlist_url,
                        main_video_url=main_video_url if main_video_url else None
                    )

                    # Inject thumbnail frame for shorts (YouTube Shorts can't use custom thumbnails via API)
                    short_video_with_thumb = self._inject_thumbnail_frame(short_video_path, short_thumb, videos_dir)

                    print(f"  📤 {short_key}: uploading best title: \"{title_raw[:60]}...\"")
                    res = self.upload_single_video(
                        title_raw=title_raw, desc_raw=desc_raw, rag_context=rag,
                        video_path=short_video_with_thumb, thumbnail_path=None,
                        is_short=True, pinned_comment=pinned,
                        short_index=s_idx, variant_idx=0, topic=topic,
                        script_text=short_script_text, duration_s=short_duration,
                        upload_schedule=upload_schedule
                    )
                    upload_results["shorts"][short_key] = res

                    # Add to shorts playlist
                    vid = res.get("youtube_id")
                    if vid and self.shorts_playlist_id:
                        self._add_to_playlist(vid, self.shorts_playlist_id)

                    # Add newly uploaded short to existing_videos so next short dedup works
                    if res.get("status") == "success":
                        existing_videos.append({"title": title_raw, "video_id": vid, "is_short": True})

                    time.sleep(self.upload_delay_seconds)
            else:
                print(f"  ⚠️ {short_key} video or variants missing, skipping")

        # Overall status
        all_uploads = []
        if upload_results["main"]:
            all_uploads.append(upload_results["main"])
        all_uploads.extend(upload_results["shorts"].values())
        upload_results["overall_status"] = "success" if any(
            u.get("status") == "success" for u in all_uploads
        ) else "failed"
        print(f"  ✅ Production slot complete. Status: {upload_results['overall_status']}")
        return upload_results
