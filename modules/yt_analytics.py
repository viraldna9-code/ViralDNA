"""
YouTube Analytics — Real implementation using YouTube Analytics API v2.
Pulls views, watch time, avg view duration, likes, and subscriber metrics.

Requires scope: https://www.googleapis.com/auth/yt-analytics.readonly
Enable API: https://console.developers.google.com/apis/api/youtubeanalytics.googleapis.com/overview
"""
import datetime
import json
import os
import sys
from typing import Optional

# Add project modules to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class YouTubeAnalytics:
    """
    Pulls real YouTube Analytics data for the authorized channel.
    Uses YouTube Analytics API v2 (separate from Data API v3).
    """

    def __init__(self, credentials_path: str | None = None, token_data: dict | None = None):
        self.credentials_path = credentials_path
        self.token_data = token_data
        self._service = None

    def _get_service(self):
        """Build the YouTube Analytics API service."""
        if self._service:
            return self._service

        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
        except ImportError:
            print("  ERROR: google-api-python-client / google-auth not installed")
            print("  Install: pip install google-api-python-client google-auth google-auth-oauthlib")
            raise

        if self.token_data:
            creds = Credentials.from_authorized_user_info(self.token_data)
        elif self.credentials_path and os.path.exists(self.credentials_path):
            with open(self.credentials_path) as f:
                token_json = json.load(f)
            creds = Credentials.from_authorized_user_info(token_json)
        else:
            raise FileNotFoundError(f"Token not found at {self.credentials_path}")

        # Verify analytics scope
        analytics_scope = "https://www.googleapis.com/auth/yt-analytics.readonly"
        if analytics_scope not in (creds.scopes or []):
            print(f"  WARNING: Token missing {analytics_scope}")
            print(f"  Current scopes: {creds.scopes}")

        self._service = build("youtubeAnalytics", "v2", credentials=creds)
        return self._service

    def pull_metrics(self, video_ids: list[str], days: int = 30) -> dict:
        """
        Pull per-video metrics for the given video IDs.
        Returns dict of {video_id: {views, watch_time_minutes, ...}}
        """
        if not video_ids:
            return {}

        try:
            service = self._get_service()
        except Exception as e:
            print(f"  YouTube Analytics service build failed: {e}")
            return {}

        end_date = datetime.date.today().strftime("%Y-%m-%d")
        start_date = (datetime.date.today() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")

        # YouTube Analytics API does not support multi-video OR filters reliably.
        # Query top videos by views and match against requested IDs.
        requested = set(video_ids)
        results = {}

        try:
            request = service.reports().query(
                ids="channel==MINE",
                startDate=start_date,
                endDate=end_date,
                metrics="views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,subscribersGained",
                dimensions="video",
                sort="-views",
                maxResults=max(len(video_ids) * 3, 50),  # over-fetch to find our videos
            )
            response = request.execute()

            rows = response.get("rows", [])
            for row in rows:
                # Row: [video_id, views, mins_watched, avg_dur_sec, avg_pct, likes, subs_gained]
                vid = row[0]
                if vid in requested:
                    results[vid] = {
                        "views": int(row[1]) if row[1] else 0,
                        "watch_time_minutes": float(row[2]) if row[2] else 0.0,
                        "avg_view_duration_seconds": float(row[3]) if row[3] else 0.0,
                        "avg_view_percentage": float(row[4]) if row[4] else 0.0,
                        "likes": int(row[5]) if row[5] else 0,
                        "subscribers_gained": int(row[6]) if row[6] else 0,
                    }

            # Fill zeros for requested IDs not returned
            for vid in video_ids:
                if vid not in results:
                    results[vid] = {
                        "views": 0,
                        "watch_time_minutes": 0.0,
                        "avg_view_duration_seconds": 0.0,
                        "avg_view_percentage": 0.0,
                        "likes": 0,
                        "subscribers_gained": 0,
                    }

            print(f"  Analytics: pulled metrics for {len(results)} video(s)")

        except Exception as e:
            print(f"  YouTube Analytics API error: {e}")

        return results

    def pull_channel_metrics(self, days: int = 30) -> dict:
        """
        Pull aggregate channel metrics for the last N days.
        """
        try:
            service = self._get_service()
        except Exception as e:
            print(f"  YouTube Analytics service build failed: {e}")
            return {}

        end_date = datetime.date.today().strftime("%Y-%m-%d")
        start_date = (datetime.date.today() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")

        try:
            request = service.reports().query(
                ids="channel==MINE",
                startDate=start_date,
                endDate=end_date,
                metrics="views,estimatedMinutesWatched,subscribersGained,averageViewDuration,averageViewPercentage",
            )
            response = request.execute()

            rows = response.get("rows", [])
            if rows:
                row = rows[0]
                # Row: [views, mins_watched, subs_gained, avg_dur_sec, avg_pct]
                return {
                    "views": int(row[0]) if row[0] else 0,
                    "watch_time_minutes": float(row[1]) if row[1] else 0.0,
                    "subscribers_gained": int(row[2]) if row[2] else 0,
                    "avg_view_duration_seconds": float(row[3]) if row[3] else 0.0,
                    "avg_view_percentage": float(row[4]) if row[4] else 0.0,
                    "period_days": days,
                }
        except Exception as e:
            print(f"  Channel metrics pull failed: {e}")

        return {}


# Convenience function for pipeline use
def pull_metrics(video_ids: list[str] | None = None, days: int = 30,
                 credentials_path: str | None = None) -> dict:
    """Legacy convenience wrapper."""
    yt = YouTubeAnalytics(credentials_path=credentials_path)
    if video_ids:
        return yt.pull_metrics(video_ids, days)
    return yt.pull_channel_metrics(days)
