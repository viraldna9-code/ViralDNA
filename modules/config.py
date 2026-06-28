# VERSION: 50.5 (v88.0: typewriter renderer background images + Ken Burns)
# MODULE: config.py
# PURPOSE: Central configuration for ViralDNA pipeline
#          v50.4: Added growth-critical defaults (embeddable, publicStatsViewable,
#                  license, liveBroadcastContent, notifySubscribers)
#          v50.3: Added YouTube Analytics API config (F1.x), notification channels (K3.x),
#                  API quota monitoring (K3.3), topic playlist IDs (H2.3),
#                  adaptive growth config keys (J2.x)
#          v50.2: Initial config
#
# PIPELINE_VERSION: v85.1 (unified across all modules as of June 9, 2026)
#   Previously each module had its own random version (v1.0-v84.3).
#   From v85.1 onward, all changes increment this single version.
PIPELINE_VERSION = "v85.1"
import os
from dotenv import load_dotenv

# Load .env: try project root first, then user home, then CWD (works for both WSL and GitHub Actions)
_project_env = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
_home_env = os.path.join(os.path.expanduser("~"), ".env")
_loaded = dotenv_path = None
for _candidate in (_project_env, _home_env, ".env"):
    if os.path.isfile(_candidate):
        dotenv_path = _candidate
        _loaded = load_dotenv(dotenv_path, override=True)
        break
if not _loaded and not os.getenv("GEMINI_API_KEY"):
    # Auto-copy home .env to project root for future runs (self-healing)
    if os.path.isfile(_home_env):
        import shutil
        try:
            shutil.copy2(_home_env, _project_env)
            dotenv_path = _project_env
            load_dotenv(dotenv_path, override=True)
        except OSError:
            pass

from datetime import datetime
from zoneinfo import ZoneInfo

IST   = ZoneInfo("Asia/Kolkata")

# DRIVE_BASE: env var override for GitHub Actions (DRIVE_BASE=/home/runner/ViralDNA)
DRIVE_BASE = os.getenv("DRIVE_BASE", "/home/jay/ViralDNA")

DRIVE = {
    "BASE": DRIVE_BASE,
    "CACHE": os.path.join(DRIVE_BASE, "cache"),
    "AUDIO_OUTPUT": os.path.join(DRIVE_BASE, "audio"),
    "VIDEO_OUTPUT": os.path.join(DRIVE_BASE, "videos"),
    "THUMBNAILS": os.path.join(DRIVE_BASE, "thumbnails"),
    "CREDENTIALS": os.path.join(DRIVE_BASE, "credentials"),
    "RUNTIME": os.path.join(DRIVE_BASE, "output", "runtime"),
}

# API keys: always from env vars, NO hardcoded fallbacks
API_KEYS = {
    "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY", ""),
    "SERPER_API_KEY": os.getenv("SERPER_API_KEY", ""),
    "SERPER_API_KEY_BACKUP1": os.getenv("SERPER_API_KEY_BACKUP1", ""),
}

GEMINI_CONFIG = {"text_model": "gemini-flash-latest"}
SCRIPT_GENERATION_CONFIG = {"model": "gemini-flash-latest"}
LEGAL_CONFIG = {"max_fallback_attempts": 3}
POST_FILTER_CONFIG = {"min_description_length": 50}
BRANDING_CONFIG = {"palette": {"primary_text": (255,255,255), "secondary_text": (26,26,46), "accent_yellow": (255,215,0), "overlay_black": (0,0,0,153)}}

# YouTube Uploader Configuration
YOUTUBE_UPLOAD_CONFIG = {
    "privacy_status": "public",
    "category_id": "25",  # News & Politics
    "default_language": "en",
    "schedule_premiere": True,
    # PUBLISH SCHEDULE RULE (Jun 28 2026):
    # Main video goes live 1 hour after upload, shorts 30 min after upload.
    # These relative delays are used by _get_scheduled_publish_time() fallback.
    "main_publish_delay_minutes": 60,
    "shorts_publish_gap_minutes": 30,
    # Static publish times — leave None to use relative delays above.
    # If set (e.g. "19:00"), overrides relative delay.
    "main_publish_time_ist": None,
    "shorts_publish_time_ist": None,
    "title_max_length": 70,
    "description_max_length": 5000,
    "tags_max_length": 500,
    "self_declared_made_for_kids": False,
    "set_to_public_on_premiere": True,
    "shorts_tag": "Shorts",
    "video_mimetype": "video/mp4",
    "thumbnail_mimetype": "image/jpeg",
    "upload_chunk_size": 10 * 1024 * 1024,
    "upload_max_retries": 3,
    "upload_retry_delay": 5,
    "retryable_http_status_codes": [500, 502, 503, 504],
    "upload_delay_seconds": 10,
    "main_playlist_url": "https://www.youtube.com/playlist?list=PLurcy8riMgyDJj9xw2APKaNRLSz-0yrjT",
    "shorts_playlist_url": "https://www.youtube.com/playlist?list=PLurcy8riMgyAI0P-FysIhnhk9uYOe_6if",
    "main_playlist_id": "PLurcy8riMgyDJj9xw2APKaNRLSz-0yrjT",
    "shorts_playlist_id": "PLurcy8riMgyAI0P-FysIhnhk9uYOe_6if",
    # ── v50.4: Growth-critical defaults missing from earlier versions ──
    "embeddable": True,           # Allow embedding = free distribution on blogs/forums
    "public_stats_viewable": True,  # Public stats = transparency = subscriber trust
    "license": "youtube",           # Standard YouTube license (accepted by API v3; "standard" is INVALID)
    "live_broadcast_content": "none",  # Pre-recorded content (not live)
    "notify_subscribers": True,    # Send notification to subscribers on publish
}

YOUTUBE_API_CONFIG = {
    "token_file": "youtube_token.json",
    "secrets_file": "client_secrets.json"
}

# ─── v50.3: YouTube Analytics API Config (F1.x) ───
YOUTUBE_ANALYTICS_CONFIG = {
    "enabled": True,
    "metrics": [
        "views", "estimatedMinutesWatched", "estimatedRevenue",
        "subscribersGained", "averageViewDuration", "likes", "shares", "comments",
    ],
    "dimensions": ["day", "video", "insightTrafficSourceType"],
    "default_lookback_days": 28,
    "ctr_target_percent": 5.0,
    "avg_duration_target_pct": 40,
}

# ─── v50.3: Topic-based Playlist IDs (H2.3) ───
# Override with real playlist IDs when created
TOPIC_PLAYLIST_CONFIG = {
    "topic_playlist_telangana": "",  # Telangana politics playlist
    "topic_playlist_andhra": "",     # Andhra Pradesh politics playlist
    "topic_playlist_cricket": "",    # Cricket & sports playlist
    "topic_playlist_tollywood": "",  # Tollywood & entertainment playlist
    "topic_playlist_tech": "",       # Technology playlist
    "topic_playlist_business": "",   # Business & economy playlist
}

# ─── v50.3: Notification Channels (K3.x) ───
NOTIFICATION_CONFIG = {
    "enabled": True,
    "channels": {
        "telegram": {
            "enabled": True,  # v85.1: enabled — Telegram is primary notification channel
            "bot_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
            "chat_id": os.getenv("TELEGRAM_CHAT_ID", ""),
        },
        "discord": {
            "enabled": False,
            "webhook_url": os.getenv("DISCORD_WEBHOOK_URL", ""),
        },
        "email": {
            "enabled": False,
            "smtp_server": os.getenv("SMTP_SERVER", ""),
            "smtp_port": int(os.getenv("SMTP_PORT", "587")),
            "username": os.getenv("SMTP_USERNAME", ""),
            "password": os.getenv("SMTP_PASSWORD", ""),
            "to_email": os.getenv("NOTIFICATION_EMAIL", ""),
        },
    },
    "notify_on": {
        "upload_success": True,
        "upload_failure": True,
        "pipeline_error": True,
        "daily_summary": False,
        "rpm_drop_alert": True,
        "trending_topic_detected": False,
    },
}

# ─── v50.3: API Quota Monitoring (K3.3) ───
QUOTA_CONFIG = {
    "youtube_data_api": {
        "daily_limit": 10000,       # YouTube Data API daily quota units
        "upload_cost": 1600,        # Cost per upload
        "search_cost": 100,
        "list_cost": 1,
        "alert_threshold_pct": 80,  # Alert at 80% usage
    },
    "youtube_analytics_api": {
        "daily_limit": 10000,       # Analytics API separate quota
        "alert_threshold_pct": 80,
    },
    "gemini_api": {
        "model": "gemini-flash-latest",
        "rpm_limit": int(os.getenv("GEMINI_RPM_LIMIT", "15")),
        "rpd_limit": int(os.getenv("GEMINI_RPD_LIMIT", "1500")),
        "alert_threshold_pct": 80,
    },
    "serper_api": {
        "monthly_limit": int(os.getenv("SERPER_MONTHLY_LIMIT", "2500")),
        "alert_threshold_pct": 80,
    },
    "quota_log_path": os.path.join(DRIVE_BASE, "output", "quota_usage.json"),
}

# ─── v50.3: Adaptive Growth Defaults (J2.x) ───
ADAPTIVE_GROWTH_CONFIG = {
    "optimal_upload_hour_ist": "17:30",
    "optimal_upload_days": [0, 2, 4, 5, 6],  # Mon, Wed, Fri, Sat, Sun
    "shorts_main_ratio": 3,
    "retention_hook_seconds": 5,
    "cta_position_pct": 85,
    "title_max_length": 70,
    "description_target_length": 1200,
    "hashtag_count": 8,
}

# ─── Brand Identity (v52.1) ───
BRAND_CONFIG = {
    "channel_name": "ViralDNA",
    "tagline_en": "Real News. Real Voices. Built with AI.",
    "tagline_te": "నిజమైన వార్తలు. అసలైన వాయిసులు. AI తో నిర్మించబడింది.",
    "channel_description": (
        "Real News. Real Voices. Built with AI.\n\n"
        "ViralDNA brings you the latest Telugu news — politics, tech, entertainment, "
        "sports, business, and everything that matters. "
        "100% AI-powered. No humans. One machine. Every day.\n\n"
        "Telugu News. Telugu Politics. Telugu Entertainment. Telugu Tech. "
        "Telugu Sports. Telugu Business. Telugu Cinema. Telugu Culture.\n\n"
        "తెలుగు వార్తలు. రాజకీయాలు. టెక్నాలజీ. వినోదం. క్రీడలు.\n\n"
        "తెలుగు వార్తలు ఇప్పుడే.\n\n"
        "Subscribe for daily Telugu news — fresh, fast, and fully autonomous."
    ),
    "keywords": [
        "telugu news", "telugu breaking news", "viral news telugu",
        "telugu politics", "telugu news today",
        "andhra pradesh news", "telangana news",
        "ai news channel", "telugu viral news",
        "telugu entertainment", "telugu cinema news",
        "telugu tech news", "telugu business news",
        "telugu sports news", "telugu cricket news",
        "telugu analysis", "telugu daily news",
        "viral telugu", "telugu current affairs",
        "telugu latest news", "telugu headlines", "ai journalism",
    ],
    "trailer_video_id": "",  # Updated after v6 trailer upload
}
