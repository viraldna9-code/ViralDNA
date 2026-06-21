"""
Shorts-Specific Optimization Module — VDNA 3.0
Hook optimization, format tuning, and Shorts-specific metadata for maximum reach.
Shorts have different CTR dynamics than main videos — hooks must be in first 2 seconds.
"""
import random
from datetime import datetime


class ShortsOptimizer:
    """Optimize Shorts for maximum reach in the Shorts feed."""

    # Hook patterns that work for Shorts (first 2 seconds)
    HOOK_PATTERNS = {
        "shock_value": [
            "This just happened in {location}...",
            "You won't believe what {subject} just did...",
            "Breaking: {headline}",
            "Wait for it... {teaser}",
        ],
        "curiosity_gap": [
            "Why is everyone talking about {topic}?",
            "The real reason {topic} is trending...",
            "What they're not telling you about {topic}...",
            "This changes everything about {topic}...",
        ],
        "urgency": [
            "Just in: {headline}",
            "Developing: {headline}",
            "Alert: {headline}",
            "Urgent update on {topic}...",
        ],
        "relatability": [
            "If you live in {location}, you need to see this...",
            "Every Telugu person needs to know this...",
            "This affects millions of people in {location}...",
            "Are you affected by {topic}? Watch this...",
        ],
    }

    # Shorts title patterns (shorter than main, more punchy)
    SHORTS_TITLE_PATTERNS = [
        "{emoji} {headline_short}",
        "{headline_short} {emoji}",
        "😱 {headline_short}",
        "🔥 {headline_short}",
        "⚡ {headline_short}",
        "{headline_short} — Explained",
        "{headline_short} | Telugu News",
    ]

    SHORTS_EMOJIS = ["😱", "🔥", "⚡", "🚨", "💥", "😤", "🤔", "👀", "📢", "⚠️"]

    def __init__(self, *args, **kwargs):
        pass

    def generate_hook(self, topic: dict, style: str = "shock_value") -> dict:
        """Generate a hook for the first 2 seconds of a Short."""
        title = topic.get("title", "this topic")
        location = topic.get("location", topic.get("state", "India"))
        subject = topic.get("subject", topic.get("who", "they"))

        patterns = self.HOOK_PATTERNS.get(style, self.HOOK_PATTERNS["shock_value"])
        template = random.choice(patterns)

        hook_text = template.format(
            location=location,
            subject=subject,
            topic=title,
            headline=title[:60],
            teaser=title[:40],
        )

        return {
            "hook_text": hook_text,
            "style": style,
            "target_duration_sec": 2,
            "generated_at": datetime.now().isoformat(),
        }

    def generate_shorts_title(self, base_title: str, variant_idx: int = 0) -> dict:
        """Generate a Shorts-optimized title (short, punchy, emoji)."""
        # Truncate to 50 chars for Shorts (shorter than main)
        short_title = base_title[:47] if len(base_title) > 50 else base_title

        pattern = self.SHORTS_TITLE_PATTERNS[variant_idx % len(self.SHORTS_TITLE_PATTERNS)]
        emoji = random.choice(self.SHORTS_EMOJIS)

        title = pattern.format(emoji=emoji, headline_short=short_title)

        # Enforce 100-char limit
        if len(title) > 100:
            title = title[:97] + "..."

        return {
            "title": title,
            "variant_index": variant_idx,
            "emoji": emoji,
            "char_count": len(title),
        }

    def generate_shorts_description(self, topic: dict, video_url: str = "") -> str:
        """Generate Shorts-optimized description (short, hashtag-heavy)."""
        title = topic.get("title", "")
        hashtags = topic.get("hashtags", ["#TeluguNews", "#ViralDNA", "#India", "#News", "#Shorts"])

        desc = f"{title}\n\n"
        if video_url:
            desc += f"Full video: {video_url}\n\n"
        desc += " ".join(hashtags[:8])
        desc += "\n\n#Shorts"

        return desc[:500]

    def generate_end_screen_cta(self, topic: dict, main_video_url: str = "") -> dict:
        """Generate end-screen CTA for Shorts (subscribe + watch main)."""
        ctas = [
            {"text": "🔔 Subscribe for more!", "type": "subscribe", "duration_sec": 3},
            {"text": "👉 Watch the full video!", "type": "main_video", "duration_sec": 3, "url": main_video_url},
            {"text": "💬 What do you think? Comment below!", "type": "engagement", "duration_sec": 3},
            {"text": "📢 Share this with someone!", "type": "share", "duration_sec": 3},
        ]

        return {
            "cta_sequence": ctas,
            "total_duration_sec": sum(c["duration_sec"] for c in ctas),
            "generated_at": datetime.now().isoformat(),
        }

    def execute(self, state):
        return state
