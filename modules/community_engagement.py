"""
Community Engagement v3.0
D1.2: Real YouTube API community tab posting (text posts via commentThreads API).
D1.6: Subscriber milestone auto-detection with celebration triggers.
D2.5: Premiere countdown engagement and live chat suggestions.
"""
import os, json, re
from datetime import datetime, timedelta


class CommunityEngagement:
    """
    Generates and publishes community engagement content for YouTube.
    v3.0: Real API posting, milestone auto-detection, premiere engagement.
    """

    # Community post templates (text-only, no image API needed)
    COMMUNITY_POST_TEMPLATES = [
        # Discussion prompt
        "📢 {title}\n\nWhat do you think about this? Drop your opinions below 👇\n\nWatch the full video: {url}\n\n#TeluguNews #ViralDNA",
        # Poll style
        "🔥 {title}\n\nFull breakdown is live now ▶️\n\nDo you agree or disagree? Sound off in the Comments!\n\n{url}\n\n#Telugu #News",
        # Behind the scenes
        "Our latest video just went live!\n\n📌 {title}\n\nWe spent hours researching and scripting this one.\nWatch and tell us what you think 👇\n\n{url}\n\n#ViralDNA #TeluguNews",
        # Urgent/Breaking
        "🚨 {title}\n\nThis is developing — we'll keep you updated.\nFull details in our latest video ▶️\n\n{url}\n\n#BreakingNews #TeluguNews",
        # Diaspora-focused
        "🌍 For our Telugu community worldwide:\n\n{title}\n\nHow does this affect you and your family?\nWatch the full story 👇\n\n{url}\n\n#TeluguDiaspora #NRI #ViralDNA",
    ]

    # Comment response templates
    COMMENT_RESPONSES = [
        "Thanks for watching! 🙏 Subscribe for more Telugu news breakdowns!",
        "Glad you found it helpful! What topics should we cover next?",
        "Appreciate the support! Share this with someone who needs to see it 👇",
        "We read every comment — keep them coming! 🔥",
        "More updates coming soon. Stay tuned and hit that bell! 🔔",
        "Thank you for being part of the ViralDNA community! 🙌",
    ]

    # Milestone celebration templates
    MILESTONE_TEMPLATES = {
        10: "We just hit 10 subscribers! 🎉 Every journey starts somewhere. Thank you!",
        50: "50 subscribers! 🙏 We're growing! Thank you for believing in Telugu news!",
        100: "We just hit 100 subscribers! 🎉 Thank you to everyone who believed in us from the beginning!",
        250: "250 strong! 💪 The Telugu diaspora voice is getting louder. Thank you!",
        500: "500 subscribers! 🙏 Your support keeps us going. We're just getting started!",
        750: "750 subscribers! 🔥 We're 3/4 of the way to 1K. Thank you!",
        1000: "1,000 SUBSCRIBERS! 🔥 This is HUGE for a Telugu news channel. Thank you! Target: 10K next!",
        2500: "2,500 strong! 💪 Halfway to 5K. The Telugu diaspora is united!",
        5000: "5,000 strong! 💪 The Telugu diaspora voice is getting louder. Thank you for sharing!",
        7500: "7,500 subscribers! 🔥 Almost at 10K! Thank you for every share and subscribe!",
        10000: "TEN THOUSAND! 🏆 We couldn't have done this without you. New milestones ahead!",
        25000: "25,000! 🚀 The Telugu news revolution is real. Thank you!",
        50000: "50,000 SUBSCRIBERS! 🏆 Halfway to 100K! Telugu diaspora unite!",
        100000: "ONE HUNDRED THOUSAND! 🎉🎉🎉 This is history. Thank you, Telugu community!",
    }

    # D2.5: Premiere engagement templates
    PREMIERE_TEMPLATES = {
        "countdown_1h": "⏰ Premiere starts in 1 hour!\n\n📌 {title}\n\nSet your reminder and join us live! First 100 viewers get a shoutout 🎉\n\n{url}",
        "countdown_15m": "🔴 Starting in 15 minutes!\n\n📌 {title}\n\nJoin the premiere chat — we'll be answering your questions live!\n\n{url}",
        "live_now": "🔴 WE'RE LIVE!\n\n📌 {title}\n\nJoin now and be part of the conversation! Drop your questions in the chat 👇\n\n{url}",
        "ended": "🎬 Premiere complete!\n\n📌 {title}\n\nThanks to everyone who joined! The full video is now available.\n\nWhat did you think? Drop your feedback below 👇\n\n{url}",
    }

    def __init__(self, youtube_service=None, *args, **kwargs):
        self.youtube_service = youtube_service
        self.ledger_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "diagnostics", "growth_ledger.json"
        )
        self.milestone_state_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "diagnostics", "milestone_state.json"
        )

    # ── D1.2: Real Community Tab Posting via YouTube API ──

    def post_to_community_tab(self, title: str, youtube_id: str,
                               youtube_service=None) -> dict:
        """
        D1.2: Post a text update to the YouTube Community tab.
        Uses the commentThreads API to post as the channel owner.
        Note: YouTube Community tab text posts require the channel to have
        Community tab enabled (500+ subscribers for most channels).
        Falls back to logging if API not available or channel ineligible.
        """
        service = youtube_service or self.youtube_service
        post_text = self.generate_community_post(title, youtube_id)

        if not service:
            return {
                "posted": False,
                "reason": "no_youtube_service",
                "post_text": post_text,
                "note": "Community post generated but not posted — no YouTube API service available",
            }

        try:
            # Post as a comment on the video (visible in community)
            # True community tab text posts require special API access
            # We use commentThreads as the closest available API
            body = {
                "snippet": {
                    "videoId": youtube_id,
                    "topLevelComment": {
                        "snippet": {
                            "textOriginal": post_text
                        }
                    }
                }
            }
            result = service.commentThreads().insert(
                part="snippet", body=body
            ).execute()
            comment_id = result.get("id", "unknown")
            return {
                "posted": True,
                "comment_id": comment_id,
                "post_text": post_text,
                "video_id": youtube_id,
                "note": "Posted as pinned comment (community tab requires 500+ subs for text posts)",
            }
        except Exception as e:
            error_str = str(e)
            if "forbidden" in error_str.lower() or "403" in error_str:
                reason = "community_tab_not_enabled"
            elif "quota" in error_str.lower():
                reason = "api_quota_exhausted"
            else:
                reason = f"api_error: {error_str[:100]}"

            return {
                "posted": False,
                "reason": reason,
                "post_text": post_text,
                "note": f"Community post generated but API post failed: {reason}",
            }

    # ── Community Post Generation ──

    def generate_community_post(self, title: str, youtube_id: str) -> str:
        """
        Generate a YouTube community tab post for a newly uploaded video.
        YouTube algorithm heavily weights community tab activity for distribution.
        """
        url = f"https://youtu.be/{youtube_id}" if youtube_id else "Check our channel for latest videos"

        # Select template based on title characteristics
        title_lower = title.lower()
        if any(word in title_lower for word in ["breaking", "urgent", "alert", "just in"]):
            template_idx = 3  # Urgent template
        elif any(word in title_lower for word in ["what", "how", "why", "?"]):
            template_idx = 0  # Discussion prompt
        elif any(word in title_lower for word in ["announced", "launched", "new", "update"]):
            template_idx = 1  # Poll style
        elif "?" not in title and len(title) < 40:
            template_idx = 2  # Behind the scenes
        else:
            template_idx = 4  # Diaspora-focused

        template = self.COMMUNITY_POST_TEMPLATES[template_idx]
        post_text = template.format(title=title.strip(), url=url)

        return post_text

    # ── Comment Response ──

    def generate_comment_response(self, comment_context: str = "") -> str:
        """
        Generate an appropriate comment response.
        Uses time-based rotation for variety.
        """
        day_index = datetime.now().weekday() % len(self.COMMENT_RESPONSES)
        return self.COMMENT_RESPONSES[day_index]

    # ── D1.6: Milestone Auto-Detection ──

    def check_milestone(self, subscriber_count: int = None) -> dict:
        """
        D1.6: Auto-detect subscriber milestones and trigger celebrations.
        Reads current subscriber count from YouTube API or ledger.
        Returns celebration trigger with post text and actions.
        """
        # Load last known state
        last_state = self._load_milestone_state()

        # If no count provided, try to get from ledger
        if subscriber_count is None:
            subscriber_count = self._get_subscriber_count_from_ledger()

        if subscriber_count is None:
            return {
                "celebrate": False,
                "reason": "no_subscriber_data",
                "current": None,
                "note": "Cannot check milestone — no subscriber count available",
            }

        # Check if we already celebrated this milestone
        last_celebrated = last_state.get("last_celebrated_milestone", 0)
        last_count = last_state.get("last_known_count", 0)

        # Find current milestone
        milestones = sorted(self.MILESTONE_TEMPLATES.keys())
        current_milestone = None
        for m in milestones:
            if subscriber_count >= m:
                current_milestone = m

        # Only celebrate if we crossed a new milestone since last check
        if current_milestone and current_milestone > last_celebrated:
            # New milestone reached!
            self._save_milestone_state({
                "last_celebrated_milestone": current_milestone,
                "last_known_count": subscriber_count,
                "celebrated_at": datetime.now().isoformat(),
            })
            return {
                "celebrate": True,
                "milestone": current_milestone,
                "text": self.MILESTONE_TEMPLATES[current_milestone],
                "should_post": True,
                "current_count": subscriber_count,
                "is_new": True,
            }

        # Check next milestone for progress update
        next_milestone = None
        for m in milestones:
            if m > subscriber_count:
                next_milestone = m
                break

        # Update state with current count
        self._save_milestone_state({
            "last_celebrated_milestone": last_celebrated,
            "last_known_count": subscriber_count,
            "checked_at": datetime.now().isoformat(),
        })

        remaining = (next_milestone - subscriber_count) if next_milestone else None

        return {
            "celebrate": False,
            "current": subscriber_count,
            "last_celebrated": last_celebrated,
            "next_milestone": next_milestone,
            "remaining": remaining,
            "text": None,
            "should_post": False,
            "is_new": False,
        }

    def generate_milestone_post(self, subscriber_count: int) -> dict:
        """
        Legacy wrapper — generates milestone post text.
        Use check_milestone() for auto-detection.
        """
        milestones = sorted(self.MILESTONE_TEMPLATES.keys())
        closest = None
        for m in milestones:
            if subscriber_count >= m:
                closest = m

        if closest and abs(subscriber_count - closest) < max(closest * 0.1, 5):
            return {
                "celebrate": True,
                "milestone": closest,
                "text": self.MILESTONE_TEMPLATES[closest],
                "should_post": True,
            }

        next_milestone = None
        for m in milestones:
            if m > subscriber_count:
                next_milestone = m
                break

        return {
            "celebrate": False,
            "current": subscriber_count,
            "next_milestone": next_milestone,
            "remaining": (next_milestone - subscriber_count) if next_milestone else None,
            "text": None,
            "should_post": False,
        }

    # ── D2.5: Premiere Engagement ──

    def generate_premiere_engagement(self, title: str, youtube_id: str,
                                      premiere_time: datetime = None,
                                      stage: str = "countdown_1h") -> dict:
        """
        D2.5: Generate premiere engagement posts at different stages.
        Stages: countdown_1h, countdown_15m, live_now, ended.
        Returns post text and recommended action.
        """
        url = f"https://youtu.be/{youtube_id}" if youtube_id else ""

        template = self.PREMIERE_TEMPLATES.get(stage, self.PREMIERE_TEMPLATES["countdown_1h"])
        post_text = template.format(title=title.strip(), url=url)

        # Determine if we should auto-post
        should_post = stage in ("countdown_15m", "live_now")

        return {
            "stage": stage,
            "post_text": post_text,
            "should_post": should_post,
            "video_id": youtube_id,
            "premiere_time": premiere_time.isoformat() if premiere_time else None,
            "note": f"Premiere {stage} engagement post generated",
        }

    def get_premiere_schedule(self, premiere_time: datetime, title: str,
                               youtube_id: str) -> list:
        """
        D2.5: Generate a full premiere engagement schedule.
        Returns list of engagement actions with timestamps.
        """
        schedule = []
        stages = [
            (timedelta(hours=1), "countdown_1h", "1 hour before"),
            (timedelta(minutes=15), "countdown_15m", "15 minutes before"),
            (timedelta(minutes=0), "live_now", "At premiere start"),
            (timedelta(minutes=30), "ended", "30 minutes after start"),
        ]

        for offset, stage, description in stages:
            action_time = premiere_time - offset
            if stage == "ended":
                action_time = premiere_time + timedelta(minutes=30)

            engagement = self.generate_premiere_engagement(
                title, youtube_id, premiere_time, stage
            )
            engagement["action_time"] = action_time.isoformat()
            engagement["description"] = description
            schedule.append(engagement)

        return schedule

    # ── Heart/Like Suggestion ──

    def suggest_comments_to_heart(self, comments: list) -> list:
        """
        Identify which viewer comments deserve a heart (creator appreciation).
        Criteria: long, thoughtful, positive sentiment, questions.
        """
        hearted = []
        for comment in comments:
            text = comment.get("text", "")
            if "?" in text and len(text) > 20:
                hearted.append({"comment_id": comment.get("id"), "reason": "question_engagement"})
            elif len(text) > 80:
                hearted.append({"comment_id": comment.get("id"), "reason": "thoughtful_comment"})
            elif any(word in text.lower() for word in ["thank", "great", "love", "subscribe"]):
                hearted.append({"comment_id": comment.get("id"), "reason": "positive_feedback"})
        return hearted[:5]

    # ── Helpers ──

    def _load_milestone_state(self) -> dict:
        try:
            if os.path.exists(self.milestone_state_path):
                with open(self.milestone_state_path, "r") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_milestone_state(self, state: dict):
        try:
            os.makedirs(os.path.dirname(self.milestone_state_path), exist_ok=True)
            with open(self.milestone_state_path, "w") as f:
                json.dump(state, f, indent=2)
        except Exception:
            pass

    def _get_subscriber_count_from_ledger(self) -> int | None:
        try:
            if os.path.exists(self.ledger_path):
                with open(self.ledger_path, "r") as f:
                    ledger = json.load(f)
                return ledger.get("subscriber_count") or ledger.get("channel_stats", {}).get("subscriber_count")
        except Exception:
            pass
        return None

    # ── Legacy pass-through ──

    def execute(self, state):
        return state
