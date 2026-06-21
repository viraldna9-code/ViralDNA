"""
Community Engagement v3.0 — VDNA 3.0 Port
YouTube Community Tab posting + subscriber milestone auto-detection.
Ported from old pipeline's CommunityEngagementAgent.
"""
import os, json, re
from datetime import datetime, timedelta


class CommunityEngagement:
    """
    Generates and publishes community engagement content for YouTube.
    VDNA 3.0 port: milestone auto-detection + community tab posting.
    """

    # Community post templates (text-only, no image API needed)
    COMMUNITY_POST_TEMPLATES = [
        "📢 {title}\n\nWhat do you think about this? Drop your opinions below 👇\n\nWatch the full video: {url}\n\n#TeluguNews #ViralDNA",
        "🔥 {title}\n\nFull breakdown is live now ▶️\n\nDo you agree or disagree? Sound off in the Comments!\n\n{url}\n\n#Telugu #News",
        "Our latest video just went live!\n\n📌 {title}\n\nWe spent hours researching and scripting this one.\nWatch and tell us what you think 👇\n\n{url}\n\n#ViralDNA #TeluguNews",
        "🚨 {title}\n\nThis is developing — we'll keep you updated.\nFull details in our latest video ▶️\n\n{url}\n\n#BreakingNews #TeluguNews",
        "🌍 For our Telugu community worldwide:\n\n{title}\n\nHow does this affect you and your family?\nWatch the full story 👇\n\n{url}\n\n#TeluguDiaspora #NRI #ViralDNA",
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

    def generate_community_post(self, title: str, youtube_id: str) -> str:
        """Generate a YouTube community tab post for a newly uploaded video."""
        url = f"https://youtu.be/{youtube_id}" if youtube_id else "Check our channel for latest videos"
        title_lower = title.lower()
        if any(word in title_lower for word in ["breaking", "urgent", "alert", "just in"]):
            template_idx = 3
        elif any(word in title_lower for word in ["what", "how", "why", "?"]):
            template_idx = 0
        elif any(word in title_lower for word in ["announced", "launched", "new", "update"]):
            template_idx = 1
        elif "?" not in title and len(title) < 40:
            template_idx = 2
        else:
            template_idx = 4
        return self.COMMUNITY_POST_TEMPLATES[template_idx].format(title=title.strip(), url=url)

    def post_to_community_tab(self, title: str, youtube_id: str, youtube_service=None) -> dict:
        """
        Post a text update to the YouTube Community tab.
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
            body = {
                "snippet": {
                    "videoId": youtube_id,
                    "topLevelComment": {
                        "snippet": {"textOriginal": post_text}
                    }
                }
            }
            result = service.commentThreads().insert(part="snippet", body=body).execute()
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

    def check_milestone(self, subscriber_count: int = None) -> dict:
        """
        Auto-detect subscriber milestones and trigger celebrations.
        Returns celebration trigger with post text and actions.
        """
        last_state = self._load_milestone_state()

        if subscriber_count is None:
            subscriber_count = self._get_subscriber_count_from_ledger()

        if subscriber_count is None:
            return {
                "celebrate": False,
                "reason": "no_subscriber_data",
                "current": None,
                "note": "Cannot check milestone — no subscriber count available",
            }

        last_celebrated = last_state.get("last_celebrated_milestone", 0)
        milestones = sorted(self.MILESTONE_TEMPLATES.keys())
        current_milestone = None
        for m in milestones:
            if subscriber_count >= m:
                current_milestone = m

        if current_milestone and current_milestone > last_celebrated:
            self._save_milestone_state({
                "last_celebrated_milestone": current_milestone,
                "last_known_count": subscriber_count,
                "celebrated_at": datetime.now().isoformat(),
            })
            return {
                "celebrate": True,
                "milestone": current_milestone,
                "subscriber_count": subscriber_count,
                "message": self.MILESTONE_TEMPLATES.get(current_milestone, "🎉 Milestone reached!"),
                "note": f"New milestone: {current_milestone} subscribers!",
            }

        return {
            "celebrate": False,
            "milestone": current_milestone,
            "subscriber_count": subscriber_count,
            "last_celebrated": last_celebrated,
            "note": f"No new milestone (current: {subscriber_count}, last celebrated: {last_celebrated})",
        }

    def _load_milestone_state(self) -> dict:
        if os.path.exists(self.milestone_state_path):
            try:
                with open(self.milestone_state_path) as f:
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

    def _get_subscriber_count_from_ledger(self) -> int:
        """Try to get subscriber count from the growth ledger."""
        try:
            if os.path.exists(self.ledger_path):
                with open(self.ledger_path) as f:
                    ledger = json.load(f)
                # Check analytics snapshots for subscriber count
                snapshots = ledger.get("analytics_snapshots", [])
                if snapshots:
                    latest = snapshots[-1]
                    sub_count = latest.get("subscribers") or latest.get("subscriber_count")
                    if sub_count:
                        return int(sub_count)
        except Exception:
            pass
        return None

    def execute(self, state):
        return state
