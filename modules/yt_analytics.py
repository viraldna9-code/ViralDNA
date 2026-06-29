"""
YouTube Analytics — Real implementation using YouTube Analytics API v2.
Pulls views, watch time, avg view duration, likes, subscriber metrics,
and audience retention curves.

Requires scope: https://www.googleapis.com/auth/yt-analytics.readonly
Enable API: https://console.developers.google.com/apis/api/youtubeanalytics.googleapis.com/overview

Retention curve API:
  dimensions=elapsedVideoTimeRatio  (0.0–1.0 = 0%–100% through video)
  metrics=relativeRetentionPerformance,audienceWatchRatio
  filters=video==<id>
  → Returns list of (ratio, relative_perf, watch_ratio) rows
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

    def pull_retention_curve(self, video_id: str, days: int = 30) -> dict:
        """
        Pull the audience retention curve for a single video.

        Uses YouTube Analytics API v2 with:
          dimension = elapsedVideoTimeRatio  (0.0 to 1.0 = 0% to 100% through video)
          metrics   = relativeRetentionPerformance, audienceWatchRatio

        Returns:
          {
            "video_id": str,
            "days": int,
            "curve": [
              {"ratio": 0.05, "relative_retention": 1.10, "audience_watch_ratio": 0.95},
              {"ratio": 0.10, "relative_retention": 0.95, "audience_watch_ratio": 0.88},
              ...
            ],
            "peak_drop_ratio": float,     # ratio where steepest drop occurs
            "avg_relative_retention": float,
            "has_data": bool,
          }

        Notes:
          - relative_retention > 1.0 means this point retains BETTER than
            YouTube's baseline for videos of the same length.
          - audience_watch_ratio is the fraction of the *initial audience*
            still watching at that point (0.0–1.0). This is the closest
            public-API equivalent of "X% of viewers still watching."
          - Returns has_data=False if the video is too new or API errors.
        """
        if not video_id or len(video_id) < 8:
            return {"video_id": video_id, "has_data": False, "error": "invalid video_id"}

        try:
            service = self._get_service()
        except Exception as e:
            return {"video_id": video_id, "has_data": False, "error": str(e)[:120]}

        end_date = datetime.date.today().strftime("%Y-%m-%d")
        start_date = (datetime.date.today() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")

        try:
            request = service.reports().query(
                ids="channel==MINE",
                startDate=start_date,
                endDate=end_date,
                metrics="relativeRetentionPerformance,audienceWatchRatio",
                dimensions="elapsedVideoTimeRatio",
                filters=f"video=={video_id}",
                sort="elapsedVideoTimeRatio",
            )
            response = request.execute()
        except Exception as e:
            return {"video_id": video_id, "has_data": False, "error": str(e)[:120]}

        rows = response.get("rows", [])
        if not rows:
            return {"video_id": video_id, "has_data": False, "error": "no data (video too new or no views)"}

        curve = []
        for row in rows:
            # Row: [elapsedVideoTimeRatio, relativeRetentionPerformance, audienceWatchRatio]
            ratio = float(row[0]) if row[0] is not None else 0.0
            rel_ret = float(row[1]) if row[1] is not None else 0.0
            watch_ratio = float(row[2]) if row[2] is not None else 0.0
            curve.append({
                "ratio": round(ratio, 4),
                "relative_retention": round(rel_ret, 4),
                "audience_watch_ratio": round(watch_ratio, 4),
            })

        if not curve:
            return {"video_id": video_id, "has_data": False, "error": "empty curve"}

        # Find peak drop: largest negative delta in audience_watch_ratio between consecutive points
        peak_drop_ratio = 0.0
        max_drop = 0.0
        for i in range(1, len(curve)):
            drop = curve[i - 1]["audience_watch_ratio"] - curve[i]["audience_watch_ratio"]
            if drop > max_drop:
                max_drop = drop
                peak_drop_ratio = curve[i]["ratio"]

        avg_rel_ret = sum(p["relative_retention"] for p in curve) / len(curve)

        return {
            "video_id": video_id,
            "days": days,
            "curve": curve,
            "peak_drop_ratio": round(peak_drop_ratio, 4),
            "avg_relative_retention": round(avg_rel_ret, 4),
            "has_data": True,
        }

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


def pull_retention_curve(video_id: str, days: int = 30,
                         credentials_path: str | None = None) -> dict:
    """
    Pull the audience retention curve for a single video.
    Convenience wrapper around YouTubeAnalytics.pull_retention_curve().

    Returns dict with keys: video_id, days, curve, peak_drop_ratio,
    avg_relative_retention, has_data, error (if any).
    """
    yt = YouTubeAnalytics(credentials_path=credentials_path)
    return yt.pull_retention_curve(video_id, days)
