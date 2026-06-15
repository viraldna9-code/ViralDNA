"""
Shorts Optimizer v3.0
Shorts title generation, CTA to long-form, comment reply scheduling,
remix detection, branding consistency check.
v3.0: LLM-based shorts titles (replacing hardcoded templates), dynamic CTA with main video URL.
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

    def __init__(self, *args, **kwargs):
        pass

    # ── Shorts Title Generation ─────────────────────────────────────────

    def generate_shorts_title_batch(self, base_title: str, topic_context: str = "",
                                     source: str = "") -> list:
        """
        Generate 3 distinct Shorts title variants from a base title.
        v3.0: Uses LLM (Gemini) for creative, non-formulaic titles.
              Falls back to heuristic templates if LLM unavailable.
        Each variant has a unique angle and hook.
        """
        clean = base_title.strip()
        clean = re.sub(r'^(BREAKING|JUST IN|UPDATE|NEWS)\s*:\s*', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'\s*\|\s*Telugu News.*$', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'\s*\(\d{4}\)\s*$', '', clean).strip()

        # Try LLM first
        llm_variants = self._generate_llm_shorts_titles(clean, topic_context, source)
        if llm_variants and len(llm_variants) >= 3:
            return llm_variants[:3]

        # Fallback: heuristic templates (v2.0 style, with hooks/emoji injected)
        return self._generate_fallback_titles(clean)

    def _generate_llm_shorts_titles(self, clean_title: str, topic_context: str,
                                      source: str) -> list:
        """Use Gemini LLM to generate creative, non-formulaic shorts titles."""
        try:
            import google.generativeai as genai
            import json as _json

            api_key = ""
            try:
                import config
                api_key = getattr(config, "GEMINI_API_KEY", "") or getattr(config, "API_KEY", "")
            except Exception:
                pass
            if not api_key:
                return []

            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-2.0-flash")

            context_snippet = topic_context[:300] if topic_context else clean_title
            source_name = source or "Telugu news"

            prompt = f"""You are a YouTube Shorts title expert for "TheViralDNA" Telugu news channel.
Generate 3 DISTINCT, VIRAL Shorts titles for this news story.

Base headline: {clean_title}
Context: {context_snippet}
Source: {source_name}

RULES:
- Each title must be 40-80 characters (Shorts titles get truncated above 80 chars)
- Each title must use a DIFFERENT hook/angle — never repeat the same pattern
- At least 1 title MUST include an appropriate emoji (🔥😱⚠️🚨💥👀🤯😤)
- At least 1 title MUST use a power word: BREAKING, SHOCKING, REVEALED, EXPOSED, URGENT
- At least 1 title should ask a question or create curiosity ("Why...?", "What happens when...?")
- Think like a Telugu youth audience — punchy, scroll-stopping, shareable
- NEVER use these formulaic patterns: "X — What Happened", "What X Means for You", "X — Telugu States React"
- Output ONLY a JSON array of 3 strings, nothing else

Example output:
["🔥 Shocking Twist in AP Politics — Here's Why", "What Just Happened in Telangana Will Surprise You 😱", "BREAKING: Exposed — The Truth Behind Today's Decision"]"""

            response = model.generate_content(prompt)
            text = response.text.strip()
            # Extract JSON array from response
            start = text.find("[")
            end = text.rfind("]") + 1
            if start >= 0 and end > start:
                titles = _json.loads(text[start:end])
                if isinstance(titles, list) and len(titles) >= 3:
                    angles = ["hook_emoji", "power_word", "curiosity"]
                    return [{"title": t[:80], "angle": angles[i] if i < len(angles) else "llm"}
                            for i, t in enumerate(titles[:3])]
        except Exception as e:
            pass
        return []

    def _generate_fallback_titles(self, clean_title: str) -> list:
        """Enhanced heuristic titles with hooks and emoji — better than v2.0 templates."""
        words = clean_title.split()
        entity = ' '.join(words[:4]) if len(words) > 4 else clean_title
        import random

        # Diverse angle templates — not formulaic
        angle_templates = [
            lambda e, r: (f"🔥 {e[:50]} — What You Need to Know", "hook_emoji"),
            lambda e, r: (f"BREAKING: {e[:48]}", "power_word"),
            lambda e, r: (f"Why {e[:42]} Changes Everything 👀", "curiosity"),
            lambda e, r: (f"SHOCKING: {e[:44]} Revealed", "power_word"),
            lambda e, r: (f"{e[:45]} — The Truth 😱", "hook_emoji"),
            lambda e, r: (f"What Happens After {e[:38]}?", "curiosity"),
            lambda e, r: (f"⚠️ {e[:48]} — Latest Update", "breaking"),
            lambda e, r: (f"EXPOSED: {e[:46]} — Full Story", "power_word"),
            lambda e, r: (f"{e[:40]} — Why Everyone's Talking 💥", "hook_emoji"),
            lambda e, r: (f"Just In: {e[:44]} — Details Emerge", "breaking"),
        ]

        # Pick 3 distinct random angles
        selected = random.sample(angle_templates, min(3, len(angle_templates)))
        variants = []
        for tmpl in selected:
            title, angle = tmpl(entity, None)
            if len(title) > 80:
                title = title[:77] + "..."
            variants.append({"title": title, "angle": angle})

        return variants
    
    def _generate_fallback_titles_old(self, clean_title: str) -> list:
        """DEPRECATED v2.0 — kept for reference only."""
        words = clean_title.split()
        entity = ' '.join(words[:4]) if len(words) > 4 else clean_title
        variants = []
        v1 = f"{entity[:55]} — What Happened"
        if len(v1) > 80:
            v1 = f"{entity[:50]} — Key Facts"
        variants.append({"title": v1, "angle": "news_facts"})
        v2 = f"What {entity[:40]} Means for You"
        if len(v2) > 80:
            v2 = f"Why {entity[:45]} Matters"
        variants.append({"title": v2, "angle": "impact"})
        v3 = f"{entity[:45]} — Telugu States React"
        if len(v3) > 80:
            v3 = f"{entity[:40]} — AP Telangana Update"
        variants.append({"title": v3, "angle": "diaspora"})
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

    def build_shorts_cta(self, main_video_url: str = None, topic_title: str = "") -> dict:
        """
        Build a call-to-action directing Shorts viewers to the main long-form video.
        This is the PRIMARY subscriber conversion path from Shorts.
        v3.0: Always uses main_video_url when available — never falls back to generic "link in bio".
        """
        if main_video_url and main_video_url.strip():
            cta_text = f"Full video here: {main_video_url}"
            overlay_text = "Full video on my channel 👆"
            pinned_comment = f"🎥 Watch the full story: {main_video_url}"
        else:
            # Only fallback when no main video URL exists (shorts-only runs)
            cta_text = "Full video on my channel — subscribe for more 🔔"
            overlay_text = "Full video on my channel 👆"
            pinned_comment = "Subscribe for more Telugu news updates 🔔"

        return {
            "cta_text": cta_text,
            "overlay_text": overlay_text,
            "end_screen_text": "Full Video → Subscribe",
            "pinned_comment": pinned_comment,
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
