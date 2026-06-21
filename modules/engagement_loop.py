"""
Engagement Loop Module — VDNA 3.0
Comment response generation, pinned comment optimization, and reply suggestions.
Uses YouTube Data API to read top comments and generate contextual responses.
"""
import random
from datetime import datetime


class EngagementLoop:
    """Manage post-upload engagement: comment responses, pinning, community interaction."""

    # Response templates by comment type
    RESPONSE_TEMPLATES = {
        "question": [
            "Great question! We cover this in detail in the video. Let us know if you need more info 👍",
            "Thanks for asking! Check the full video for the complete answer. We'll do a deep-dive soon.",
            "Good point! What aspect would you like us to cover next? Tell us in the comments 👇",
        ],
        "praise": [
            "Thank you! Your support keeps us going 🙏 Subscribe for more Telugu news breakdowns!",
            "Appreciate it! Share this with someone who needs to see it 🔗",
            "Thanks! Hit the bell icon so you never miss an update 🔔",
        ],
        "criticism": [
            "We hear you. We strive to be accurate and balanced. Sources are in the description.",
            "Fair point. We'll look into this further. Thanks for the feedback.",
            "We appreciate constructive criticism. What would you like to see improved?",
        ],
        "confusion": [
            "Let us clarify — the key point is in the first 2 minutes. Hope that helps!",
            "We understand it's complex. We'll simplify it in our next video. Stay tuned!",
            "Check the pinned comment for a quick summary 📌",
        ],
        "general": [
            "Thanks for watching! What topic should we cover next? 👇",
            "Your thoughts? Drop them below — we read every comment 🙏",
            "Share this with someone who needs to see this. Tag them below!",
        ],
    }

    PINNED_COMMENT_TEMPLATES = [
        "📌 SUMMARY: {summary}\n\nWhat do you think? Drop your thoughts below 👇\n🔔 Subscribe for daily Telugu news updates",
        "📌 KEY POINTS:\n{key_points}\n\nAgree or disagree? Let's discuss in the comments 👇",
        "📌 TIMESTAMPS:\n{timestamps}\n\nShare this with someone who needs to see it! 🔗",
        "📌 What should we cover next? Tell us in the comments — we read every one! 👇\n🔔 Don't forget to subscribe!",
    ]

    def __init__(self, *args, **kwargs):
        self.youtube_service = None

    def set_youtube_service(self, service):
        """Set the YouTube API service for live comment reading."""
        self.youtube_service = service

    def generate_pinned_comment(self, topic: dict, video_id: str = "") -> dict:
        """Generate an optimized pinned comment for a video."""
        title = topic.get("title", "this topic")
        summary = topic.get("description", topic.get("summary", title))[:200]

        template = random.choice(self.PINNED_COMMENT_TEMPLATES)
        if "{summary}" in template:
            comment = template.format(summary=summary)
        elif "{key_points}" in template:
            points = f"• {title}\n• Key developments explained\n• What happens next"
            comment = template.format(key_points=points)
        elif "{timestamps}" in template:
            ts = "0:00 - Intro\n1:30 - What happened\n3:00 - Why it matters\n4:30 - What's next"
            comment = template.format(timestamps=ts)
        else:
            comment = template

        return {
            "pinned_comment": comment,
            "video_id": video_id,
            "generated_at": datetime.now().isoformat(),
            "strategy": "summary_hook" if "{summary}" in template else "engagement_hook",
        }

    def respond_to_comment(self, comment_text: str, topic: dict = None) -> dict:
        """Generate a response to a viewer comment."""
        text_lower = comment_text.lower()

        # Classify comment type
        if any(w in text_lower for w in ["what", "why", "how", "when", "where", "?"]):
            comment_type = "question"
        elif any(w in text_lower for w in ["great", "awesome", "love", "thanks", "good", "nice", "best"]):
            comment_type = "praise"
        elif any(w in text_lower for w in ["wrong", "fake", "lie", "bias", "bad", "hate", "stupid"]):
            comment_type = "criticism"
        elif any(w in text_lower for w in ["confused", "don't understand", "unclear", "what do you mean"]):
            comment_type = "confusion"
        else:
            comment_type = "general"

        response = random.choice(self.RESPONSE_TEMPLATES[comment_type])

        return {
            "original_comment": comment_text[:100],
            "comment_type": comment_type,
            "response": response,
            "generated_at": datetime.now().isoformat(),
        }

    def generate_engagement_prompt(self, topic: dict) -> str:
        """Generate a call-to-action prompt for end of video."""
        prompts = [
            f"What do you think about {topic.get('title', 'this')}? Agree or disagree? Comment below 👇",
            f"Is this happening in your area? Let us know in the comments!",
            f"What should we cover next? Tell us — we read every comment 🙏",
            f"Share this with someone who needs to see this. Tag them below!",
            f"If you're watching from outside India — where are you from? Comment below!",
        ]
        return random.choice(prompts)

    def execute(self, state):
        return state
