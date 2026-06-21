"""
Cross-Platform Distribution Module — VDNA 3.0
Clips and distributes content to Instagram Reels, Facebook, X/Twitter.
Generates platform-optimized metadata for each target platform.
"""
import os
from datetime import datetime


class CrossPlatformDistributor:
    """Generate platform-optimized clips and metadata for cross-platform distribution."""

    PLATFORM_SPECS = {
        "instagram_reels": {
            "aspect_ratio": "9:16",
            "max_duration_sec": 90,
            "caption_limit": 2200,
            "hashtag_limit": 30,
            "optimal_hashtags": ["#reels", "#viral", "#news", "#india", "#telugu", "#trending"],
        },
        "facebook_reels": {
            "aspect_ratio": "9:16",
            "max_duration_sec": 60,
            "caption_limit": 63206,
            "hashtag_limit": 10,
            "optimal_hashtags": ["#news", "#india", "#telugu", "#viral", "#breakingnews"],
        },
        "x_twitter": {
            "aspect_ratio": "9:16",
            "max_duration_sec": 140,
            "caption_limit": 280,
            "hashtag_limit": 3,
            "optimal_hashtags": ["#TeluguNews", "#India", "#News"],
        },
    }

    def __init__(self, *args, **kwargs):
        self.clips_dir = None

    def generate_clip_plan(self, video_path: str, topic: dict) -> dict:
        """Plan clips for cross-platform distribution."""
        title = topic.get("title", "ViralDNA News")
        clips = []

        for platform, specs in self.PLATFORM_SPECS.items():
            clip = {
                "platform": platform,
                "source_video": video_path,
                "max_duration_sec": specs["max_duration_sec"],
                "aspect_ratio": specs["aspect_ratio"],
                "caption": self._generate_caption(platform, topic),
                "hashtags": specs["optimal_hashtags"],
                "status": "planned",
                "generated_at": datetime.now().isoformat(),
            }
            clips.append(clip)

        return {
            "clips": clips,
            "total_platforms": len(clips),
            "source_topic": title,
            "planned_at": datetime.now().isoformat(),
        }

    def _generate_caption(self, platform: str, topic: dict) -> str:
        """Generate platform-optimized caption."""
        title = topic.get("title", "")
        desc = topic.get("description", topic.get("summary", ""))[:100]

        if platform == "instagram_reels":
            return f"{title}\n\n{desc}\n\nFollow @viralDNA for daily Telugu news updates 🔔"
        elif platform == "facebook_reels":
            return f"📢 {title}\n\n{desc}\n\nLike and follow for more updates!"
        elif platform == "x_twitter":
            return f"🚨 {title}\n\n{desc}"
        return title

    def generate_posting_schedule(self, clips: list) -> list:
        """Generate optimal posting schedule for cross-platform clips."""
        from datetime import timedelta
        now = datetime.now()

        schedule = []
        for i, clip in enumerate(clips):
            # Stagger posts by 30 minutes
            post_time = now + timedelta(minutes=30 * (i + 1))
            schedule.append({
                "platform": clip["platform"],
                "scheduled_time": post_time.isoformat(),
                "status": "scheduled",
            })

        return schedule

    def execute(self, state):
        return state
