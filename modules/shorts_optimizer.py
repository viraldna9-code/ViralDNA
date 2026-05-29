"""
Shorts Optimizer v2.0
Shorts title generation, CTA to long-form, comment reply scheduling,
remix detection, branding consistency check.
"""
import re
from datetime import datetime, timedelta


class ShortsOptimizer:
    """
    Optimizes Shorts-specific signals for maximum growth.
    Shorts are the #1 subscriber acquisition channel for new YouTube channels.
    """

    # Title formula components for viral Shorts
    HOOK_WORDS = [
        "BREAKING", "JUST IN", "SHOCKING", "URGENT", "EXCLUSIVE",
        "REVEALED", "EXPOSED", "WARNING", "ALERT", "MUST WATCH",
    ]
    EMOTION_TRIGGERS = [
        "😱", "🔥", "⚠️", "💥", "🚨", "👀", "😤", "🤯",
    ]
    CTA_PHRASES = [
        "Full video on my channel",
        "Watch the full breakdown — link in bio",
        "Part 1 is on my channel — go watch",
        "Full story on my channel — subscribe",
        "More details on my channel — link in bio",
    ]

    def __init__(self, *args, **kwargs):
        pass

    # ── Shorts Title Generation ─────────────────────────────────────────

    def generate_shorts_title_batch(self, base_title: str) -> list:
        """
        Generate 3 Shorts title variants from a base title.
        Uses hook words, emotion triggers, and Telugu-English mix.
        """
        clean = base_title.strip()
        # Remove common news prefixes for Shorts
        clean = re.sub(r'^(BREAKING|JUST IN|UPDATE|NEWS)\s*:\s*', '', clean, flags=re.IGNORECASE)

        variants = []

        # Variant 1: Hook word + short title
        hook = self.HOOK_WORDS[hash(clean) % len(self.HOOK_WORDS)]
        v1 = f"{hook}: {clean[:60]}"
        variants.append(v1)

        # Variant 2: Emotion trigger + question format
        emoji = self.EMOTION_TRIGGERS[hash(clean + "emoji") % len(self.EMOTION_TRIGGERS)]
        short_text = clean[:50] if len(clean) > 50 else clean
        v2 = f"{emoji} {short_text}?"
        variants.append(v2)

        # Variant 3: Telugu-English mix (for diaspora audience)
        v3 = f"{clean[:55]} 🔥 #TeluguNews"
        variants.append(v3)

        return variants

    def optimize_titles(self, titles: list) -> list:
        """Score and rank a list of Shorts titles."""
        scored = []
        for title in titles:
            score = 50  # Base
            # Length bonus (Shorts titles should be short)
            if len(title) <= 60:
                score += 15
            elif len(title) <= 80:
                score += 8
            # Hook word bonus
            if any(hw in title.upper() for hw in self.HOOK_WORDS):
                score += 10
            # Emoji bonus
            if any(e in title for e in self.EMOTION_TRIGGERS):
                score += 8
            # Hashtag bonus
            if "#" in title:
                score += 5
            # Question bonus (engagement)
            if "?" in title:
                score += 7
            scored.append({"title": title, "score": min(score, 100)})
        return sorted(scored, key=lambda x: x["score"], reverse=True)

    # ── Shorts-to-Long CTA ──────────────────────────────────────────────

    def build_shorts_cta(self, main_video_url: str = None) -> dict:
        """
        Build a call-to-action directing Shorts viewers to the main long-form video.
        This is the PRIMARY subscriber conversion path from Shorts.
        """
        if main_video_url and main_video_url.strip():
            cta_text = f"Full video here: {main_video_url}"
            overlay_text = "Full video on my channel 👆"
        else:
            cta_text = self.CTA_PHRASES[hash(datetime.now().isoformat()) % len(self.CTA_PHRASES)]
            overlay_text = "Watch full video — link in bio 👆"

        return {
            "cta_text": cta_text,
            "overlay_text": overlay_text,
            "end_screen_text": "Full Video → Subscribe",
            "pinned_comment": cta_text,
            "placement": "last_3_seconds",
            "priority": "high",
        }

    # ── Comment Reply Schedule ──────────────────────────────────────────

    def plan_comment_reply_schedule(self, upload_epoch: int, comments_count: int = 5) -> list:
        """
        Plan when to reply to comments on a Short for maximum engagement.
        Early replies signal to YouTube that the video is engaging.
        """
        upload_dt = datetime.fromtimestamp(upload_epoch)
        schedule = []

        # Reply strategy: first hour is critical
        reply_windows = [
            {"delay_minutes": 5, "count": min(2, comments_count),
             "strategy": "Immediate — first 2 comments within 5 min of upload"},
            {"delay_minutes": 30, "count": min(2, comments_count - 2),
             "strategy": "Early engagement — next 2 within 30 min"},
            {"delay_minutes": 120, "count": min(1, comments_count - 4),
             "strategy": "Sustained — 1 more within 2 hours"},
        ]

        remaining = comments_count
        for window in reply_windows:
            if remaining <= 0:
                break
            actual_count = min(window["count"], remaining)
            reply_time = upload_dt + timedelta(minutes=window["delay_minutes"])
            schedule.append({
                "reply_at": reply_time.isoformat(),
                "delay_minutes": window["delay_minutes"],
                "comments_to_reply": actual_count,
                "strategy": window["strategy"],
            })
            remaining -= actual_count

        return schedule

    # ── Branding Consistency Check ──────────────────────────────────────

    def check_branding_consistency(self, video_meta: dict) -> dict:
        """
        Verify that a Short follows ViralDNA brand guidelines.
        Returns pass/fail with specific issues.
        """
        issues = []
        score = 100

        # Check watermark
        if not video_meta.get("has_watermark", False):
            issues.append("Missing ViralDNA watermark (bottom-right)")
            score -= 25

        # Check brand colors
        if not video_meta.get("brand_colors", False):
            issues.append("Brand colors not applied (expected: #C04020 red, #D6B300 gold)")
            score -= 20

        # Check font
        expected_font = "Bebas Neue"
        if video_meta.get("font", "") != expected_font:
            issues.append(f"Font mismatch: expected '{expected_font}', got '{video_meta.get('font', 'none')}'")
            score -= 15

        # Check CTA presence
        cta = video_meta.get("cta", "")
        if not cta or len(cta) < 10:
            issues.append("CTA text missing or too short")
            score -= 20

        # Check Telugu presence
        if not video_meta.get("has_telugu", False):
            issues.append("No Telugu text/branding — diaspora audience expects Telugu identity")
            score -= 10

        return {
            "pass": score >= 70,
            "score": max(score, 0),
            "issues": issues,
            "recommendation": "PASS" if score >= 70 else "FIX: " + "; ".join(issues[:3]),
        }

    # ── Legacy pass-through ─────────────────────────────────────────────

    def run(self, shorts_data: dict | None = None) -> dict:
        return {"optimized": True, "data": shorts_data or {}}

    def execute(self, state):
        return state
