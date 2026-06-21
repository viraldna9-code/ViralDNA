"""
Competitor Intelligence v3.0 — VDNA 3.0
Tracks competitor activity using YouTube Data API v3.
Identifies content gaps by scanning competitor recent uploads.
"""
import os, json
from datetime import datetime, timedelta


class CompetitorIntel:
    def __init__(self, *args, **kwargs):
        self.ledger_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "diagnostics", "growth_ledger.json"
        )
        # Real Telugu news channel IDs (verified)
        self.tracked_channels = [
            {"name": "TV9 Telugu", "channel_id": "UCAR3h_9fLU9FW6p8oFKj5jw", "threat_level": "high"},
            {"name": "NTV Telugu", "channel_id": "UCumtYpCY26F6Jr3o8QK1qKQ", "threat_level": "high"},
            {"name": "ETV Andhra Pradesh", "channel_id": "UCn7PBY0hJHVu8WMrW2J3nHA", "threat_level": "medium"},
            {"name": "Sakshi TV", "channel_id": "UC_2irx2SE867twwJpOZp3mg", "threat_level": "high"},
            {"name": "V6 News", "channel_id": "UCFo7sCk7X9A8Jc1Lq4B3q1g", "threat_level": "medium"},
            {"name": "ABN Andhra Jyothy", "channel_id": "UCPk5O2jDg0QnVgMyiFWpEhw", "threat_level": "medium"},
        ]
        self._youtube_service = None

    def set_youtube_service(self, service):
        """Set YouTube Data API service for live competitor scanning."""
        self._youtube_service = service

    def _fetch_recent_uploads(self, channel_id: str, max_results: int = 10) -> list:
        """Fetch recent uploads from a competitor channel using YouTube Data API."""
        if not self._youtube_service:
            return self._fallback_uploads(channel_id)

        try:
            # Get the uploads playlist ID
            channels_response = self._youtube_service.channels().list(
                part="contentDetails,statistics",
                id=channel_id
            ).execute()

            if not channels_response.get("items"):
                return []

            channel_info = channels_response["items"][0]
            uploads_playlist = channel_info["contentDetails"]["relatedPlaylists"]["uploads"]
            subscriber_count = channel_info["statistics"].get("subscriberCount", "unknown")

            # Fetch recent videos from uploads playlist
            playlist_response = self._youtube_service.playlistItems().list(
                part="snippet",
                playlistId=uploads_playlist,
                maxResults=max_results
            ).execute()

            videos = []
            for item in playlist_response.get("items", []):
                snippet = item["snippet"]
                videos.append({
                    "title": snippet.get("title", ""),
                    "video_id": snippet["resourceId"]["videoId"],
                    "published_at": snippet.get("publishedAt", ""),
                    "description": snippet.get("description", "")[:200],
                })

            return {
                "videos": videos,
                "subscriber_count": subscriber_count,
                "fetched_at": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"videos": [], "error": str(e)[:100]}

    def _fallback_uploads(self, channel_id: str) -> dict:
        """Fallback when YouTube API is unavailable — returns empty, not fake data."""
        return {
            "videos": [],
            "subscriber_count": "unknown",
            "note": "YouTube API not connected — set_youtube_service() to enable live scanning",
            "fetched_at": datetime.now().isoformat(),
        }

    def scan_competitors(self, max_videos_per_channel: int = 5) -> dict:
        """Scan all tracked competitors for recent uploads."""
        results = {}
        for channel in self.tracked_channels:
            data = self._fetch_recent_uploads(channel["channel_id"], max_videos_per_channel)
            results[channel["name"]] = {
                "channel_id": channel["channel_id"],
                "threat_level": channel["threat_level"],
                **data,
            }
        return results

    def identify_content_gaps(self, our_recent_topics: list = None) -> list:
        """
        Identify content gaps by comparing competitor uploads against our recent topics.
        Requires set_youtube_service() to be called first for real data.
        """
        if not self._youtube_service:
            return [{
                "topic": "YouTube API not connected",
                "urgency": "high",
                "note": "Call set_youtube_service() with authenticated YouTube service to enable live gap analysis",
                "action": "Pass youtube_service from upload phase to competitor_intel",
            }]

        competitor_data = self.scan_competitors()
        gaps = []

        # Extract keywords from competitor video titles
        competitor_keywords = {}
        for name, data in competitor_data.items():
            for video in data.get("videos", []):
                title = video.get("title", "").lower()
                # Extract key topics (simple keyword extraction)
                words = [w for w in title.split() if len(w) > 3]
                for w in words:
                    competitor_keywords[w] = competitor_keywords.get(w, 0) + 1

        # Find topics competitors cover frequently that we haven't
        our_topics_lower = [t.lower() for t in (our_recent_topics or [])]
        for keyword, count in sorted(competitor_keywords.items(), key=lambda x: x[1], reverse=True):
            if count >= 2 and keyword not in " ".join(our_topics_lower):
                gaps.append({
                    "topic": keyword,
                    "competitor_coverage": count,
                    "urgency": "high" if count >= 4 else "medium",
                    "our_coverage": "none",
                })

        return gaps[:10]

    def push_to_ledger(self, ledger: dict):
        """Push competitor intelligence data to the growth ledger."""
        if ledger is None:
            return

        summary = self.get_competitor_summary()
        competitor_data = {
            "last_scan": datetime.now().isoformat(),
            "channels_tracked": summary["total_tracked"],
            "high_threats": summary["high_threats"],
            "content_gaps": summary["content_gaps"],
            "top_priorities": summary["top_priorities"],
            "api_connected": self._youtube_service is not None,
        }
        if "competitor_intel" not in ledger:
            ledger["competitor_intel"] = []
        ledger["competitor_intel"].append(competitor_data)
        ledger["competitor_intel"] = ledger["competitor_intel"][-30:]
        try:
            os.makedirs(os.path.dirname(self.ledger_path), exist_ok=True)
            with open(self.ledger_path, "w") as f:
                json.dump(ledger, f, indent=2, default=str)
        except Exception:
            pass

    def get_competitor_summary(self) -> dict:
        """Return current competitor tracking summary."""
        high_threats = sum(1 for c in self.tracked_channels if c.get("threat_level") == "high")
        gaps = self.identify_content_gaps()
        return {
            "total_tracked": len(self.tracked_channels),
            "high_threats": high_threats,
            "content_gaps": len(gaps),
            "gaps": gaps,
            "top_priorities": self._get_top_priorities(gaps),
            "api_connected": self._youtube_service is not None,
            "scanned_at": datetime.now().isoformat(),
        }

    def get_content_gap_result(self) -> dict:
        """Identify content gaps — topics competitors cover that we don't."""
        gaps = self.identify_content_gaps()
        return {
            "content_gaps": len(gaps),
            "gaps": gaps,
            "top_priorities": self._get_top_priorities(gaps),
            "api_connected": self._youtube_service is not None,
            "analyzed_at": datetime.now().isoformat(),
        }

    def _get_top_priorities(self, gaps: list = None) -> list:
        """Return top 3 content gap priorities."""
        if gaps is None:
            gaps = self.identify_content_gaps()
        high_urgency = [g for g in gaps if g.get("urgency") == "high"]
        return high_urgency[:3]

    def execute(self, state):
        return state
