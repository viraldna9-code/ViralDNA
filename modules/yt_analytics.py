"""
YouTube Analytics — Real implementation using YouTube Analytics API v2.
Pulls views, CTR, average view duration, likes, and subscriber metrics.

Requires scope: https://www.googleapis.com/auth/yt-analytics.readonly
Token must be re-authorized if this scope is missing.

API reference:
  https://developers.google.com/youtube/analytics/available_reports
"""
import datetime
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


class YouTubeAnalytics:
    """Pull real YouTube Analytics data for uploaded videos."""

    def __init__(self, credentials_path: str | None = None, token_data: dict | None = None):
        """
        Initialize with either a token file path or token dict.
        """
        self.credentials_path = credentials_path
        self.token_data = token_data
        self._service = None

    def _get_service(self):
        """Build the YouTube Analytics API service."""
        if self._service:
            return self._service

        SCOPES = ["https://www.googleapis.com/auth/yt-analytics.readonly"]

        if self.token_data:
            creds = Credentials(
                token=self.token_data.get("token"),
                refresh_token=self.token_data.get("refresh_token"),
                token_uri=self.token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
                client_id=self.token_data.get("client_id"),
                client_secret=self.token_data.get("client_secret"),
                scopes=SCOPES,
            )
        elif self.credentials_path:
            creds = Credentials.from_authorized_user_file(self.credentials_path, SCOPES)
        else:
            raise ValueError("Need credentials_path or token_data")

        # Refresh if expired
        if creds.expired and creds.refresh_token:
            from google.auth.transport.requests import Request
            creds.refresh(Request())

        self._service = build("youtubeAnalytics", "v2", credentials=creds)
        return self._service

    def pull_metrics(self, video_ids: list, days: int = 30) -> dict:
        """
        Pull analytics metrics for a list of video IDs.

        Returns dict of {video_id: {views, ctr, avg_view_pct, likes, ...}}
        """
        if not video_ids:
            return {}

        try:
            service = self._get_service()
        except Exception as e:
            print(f"  ⚠️ YouTube Analytics service build failed: {e}")
            return {}

        # Format video IDs for API filter
        video_filter = ",".join(f"video=={vid}" for vid in video_ids)

        # Date range: last N days
        end_date = datetime.date.today().strftime("%Y-%m-%d")
        start_date = (datetime.date.today() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")

        results = {}

        try:
            # Core metrics: views, estimatedMinutesWatched, averageViewDuration,
            #              averageViewPercentage, likes, subscribersGained, impressions, impressionClickRate
            request = service.reports().query(
                ids="channel==MINE",
                startDate=start_date,
                endDate=end_date,
                metrics="views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,subscribersGained,impressions,impressionClickRate",
                dimensions="video",
                filters=video_filter,
                sort="-views",
            )
            response = request.execute()

            rows = response.get("rows", [])
            for row in rows:
                # Row format: [video_id, views, mins_watched, avg_dur, avg_pct, likes, subs_gained, impressions, ctr]
                vid = row[0]
                impressions = row[7] if row[7] else 0
                ctr = row[8] if row[8] else 0.0
                results[vid] = {
                    "views": int(row[1]) if row[1] else 0,
                    "estimated_minutes_watched": float(row[2]) if row[2] else 0.0,
                    "average_view_duration": float(row[3]) if row[3] else 0.0,
                    "average_view_percentage": float(row[4]) if row[4] else 0.0,
                    "likes": int(row[5]) if row[5] else 0,
                    "subscribers_gained": int(row[6]) if row[6] else 0,
                    "impressions": int(impressions),
                    "impression_click_rate": float(ctr),
                }

            # Fill in zeros for any requested IDs that weren't returned
            for vid in video_ids:
                if vid not in results:
                    results[vid] = {
                        "views": 0,
                        "estimated_minutes_watched": 0.0,
                        "average_view_duration": 0.0,
                        "average_view_percentage": 0.0,
                        "likes": 0,
                        "subscribers_gained": 0,
                        "impressions": 0,
                        "impression_click_rate": 0.0,
                    }

        except HttpError as e:
            if e.resp.status == 403:
                print("  ⚠️ YouTube Analytics API access denied. Token needs 'yt-analytics.readonly' scope.")
                print("  → Re-authorize at: https://accounts.google.com/o/oauth2/auth with scope added")
            else:
                print(f"  ⚠️ YouTube Analytics API error: {e}")
            return {}
        except Exception as e:
            print(f"  ⚠️ YouTube Analytics pull failed: {e}")
            return {}

        return results

    def pull_channel_metrics(self, days: int = 30) -> dict:
        """
        Pull aggregate channel metrics for the last N days.
        Returns dict with views, subscribers_gained, watch_time_minutes, etc.
        """
        try:
            service = self._get_service()
        except Exception as e:
            print(f"  ⚠️ YouTube Analytics service build failed: {e}")
            return {}

        end_date = datetime.date.today().strftime("%Y-%m-%d")
        start_date = (datetime.date.today() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")

        try:
            request = service.reports().query(
                ids="channel==MINE",
                startDate=start_date,
                endDate=end_date,
                metrics="views,estimatedMinutesWatched,subscribersGained,averageViewDuration,averageViewPercentage,impressions,impressionClickRate",
            )
            response = request.execute()

            rows = response.get("rows", [])
            if rows:
                row = rows[0]
                return {
                    "views": int(row[0]) if row[0] else 0,
                    "estimated_minutes_watched": float(row[1]) if row[1] else 0.0,
                    "subscribers_gained": int(row[2]) if row[2] else 0,
                    "average_view_duration": float(row[3]) if row[3] else 0.0,
                    "average_view_percentage": float(row[4]) if row[4] else 0.0,
                    "impressions": int(row[5]) if row[5] else 0,
                    "impression_click_rate": float(row[6]) if row[6] else 0.0,
                    "period_days": days,
                }
        except Exception as e:
            print(f"  ⚠️ Channel metrics pull failed: {e}")

        return {}
