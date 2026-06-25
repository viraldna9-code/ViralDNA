"""
Community Poster v2.0
YouTube Community Tab post scheduler.
Generates weekly post schedule from video content — no external API needed.
"""
import os, json
from datetime import datetime, timedelta


class CommunityPoster:
    """
    Generates YouTube Community Tab posts and weekly schedule.
    Text-only generation — actual posting can be manual or via YouTube API later.
    """

    # Post types based on timing relative to video upload
    POST_SCHEDULE = [
        {"day": "today", "hour": 0, "type": "launch", "template": "launch"},
        {"day": "today", "hour": 4, "type": "discussion", "template": "discussion"},
        {"day": "+1", "hour": 7, "type": "morning_recap", "template": "recap"},
        {"day": "+2", "hour": 12, "type": "deep_dive", "template": "deep_dive"},
        {"day": "+3", "hour": 18, "type": "appreciation", "template": "appreciation"},
        {"day": "+5", "hour": 10, "type": "related", "template": "related"},
        {"day": "+7", "hour": 14, "type": "weekly_recap", "template": "weekly_recap"},
    ]

    TEMPLATES = {
        "launch": [
            "🎬 {title}\n\nOur latest video is LIVE! Watch the full story 👇\n\n{video_url}\n\n#TeluguNews #ViralDNA",
            "🔥 NEW VIDEO: {title}\n\nWe spent hours researching this one. See what we found ▶️\n\n{video_url}\n\n#Telugu #News",
        ],
        "discussion": [
            "💬 {title}\n\nWe shared our analysis — now we want to hear YOUR take. Comment below 👇\n\n{video_url}\n\n#TeluguNews #Discussion",
        ],
        "recap": [
            "☀️ Good morning, ViralDNA family!\n\nMissed yesterday's video? Here's your quick recap:\n\n📌 {title}\n\nWatch the full breakdown ▶️ {video_url}\n\n#TeluguNews #MorningUpdate",
        ],
        "deep_dive": [
            "🔍 DEEP DIVE: {title}\n\nWe explored the details others missed. Still relevant today.\n\n{video_url}\n\n#TeluguNews #DeepDive #ViralDNA",
        ],
        "appreciation": [
            "🙏 Thank you, ViralDNA family!\n\nYour comments and shares on our recent video mean everything.\n\nWhat should we cover next? Let us know! 👇\n\n#TeluguNews #ViralDNA",
        ],
        "related": [
            "📚 RELATED: {title}\n\nWant more context on this topic? Our deep dive is still getting views:\n\n{video_url}\n\n#TeluguNews #ViralDNA",
        ],
        "weekly_recap": [
            "📅 WEEKLY ROUNDUP: Here's what we covered this week on ViralDNA\n\n👉 {title}\n\nCatch up on anything you missed ▶️ {video_url}\n\nWhat topics should we cover next week? Comment below!\n\n#TeluguNews #WeeklyRecap #ViralDNA",
        ],
    }

    def __init__(self, *args, **kwargs):
        pass

    def run(self, topic: dict, videos: list) -> dict:
        """
        Generate a week of community posts based on uploaded video.
        Returns {post, weekly_schedule, total_weekly_posts}.
        Called by CommunityPosterAgent post-pipeline.
        """
        title = topic.get("title", "Latest Update") if isinstance(topic, dict) else "Latest Update"
        video_url = videos[0].get("url", "") if videos else ""
        now = datetime.now()

        # Generate the immediate (launch) post
        launch_templates = self.TEMPLATES["launch"]
        launch_post = launch_templates[now.day % len(launch_templates)].format(
            title=title, video_url=video_url
        )

        # Generate weekly schedule
        weekly_schedule = []
        for sched in self.POST_SCHEDULE:
            if sched["day"] == "today":
                post_time = now + timedelta(hours=sched["hour"])
            else:
                days = int(sched["day"].replace("+", ""))
                post_time = now + timedelta(days=days, hours=sched["hour"])

            templates = self.TEMPLATES.get(sched["template"], self.TEMPLATES["discussion"])
            template = templates[post_time.day % len(templates)]

            post_text = template.format(title=title, video_url=video_url)
            weekly_schedule.append({
                "day": sched["day"],
                "time_ist": post_time.strftime("%Y-%m-%d %H:%M"),
                "type": sched["type"],
                "text": post_text,
            })

        return {
            "post": launch_post,
            "weekly_schedule": weekly_schedule,
            "total_weekly_posts": len(weekly_schedule),
            "video_title": title,
            "video_url": video_url,
        }

    def execute(self, state):
        return state
