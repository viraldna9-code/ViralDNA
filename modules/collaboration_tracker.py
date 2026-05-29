"""
Collaboration Tracker v2.0
Tracks Telugu creator partners, generates outreach templates, maintains partner database.
"""
import os, json
from datetime import datetime


class CollaborationTracker:
    """
    Manages collaboration partner database and generates outreach.
    Tracks Telugu news/entertainment creators for cross-promotion opportunities.
    """

    # Pre-seeded potential collaboration targets (Telugu creator ecosystem)
    DEFAULT_PARTNERS = [
        {
            "name": "Telugu Tech Hub",
            "platform": "youtube",
            "subscribers": "50K-200K",
            "category": "technology",
            "collab_type": "cross-promo",
            "status": "identified",
            "notes": "Tech-focused Telugu channel. Good for tech news collabs.",
        },
        {
            "name": "NRI Life Stories",
            "platform": "youtube",
            "subscribers": "10K-50K",
            "category": "lifestyle",
            "collab_type": "interview",
            "status": "identified",
            "notes": "Diaspora lifestyle content. Perfect for NRI-focused stories.",
        },
        {
            "name": "Telugu Cinema Today",
            "platform": "youtube",
            "subscribers": "100K+",
            "category": "entertainment",
            "collab_type": "reaction",
            "status": "identified",
            "notes": "Entertainment news. Good for film industry news collabs.",
        },
        {
            "name": "Andhra Politics Watch",
            "platform": "youtube",
            "subscribers": "20K-80K",
            "category": "politics",
            "collab_type": "debate",
            "status": "identified",
            "notes": "Political analysis. Good for election coverage collabs.",
        },
        {
            "name": "Telugu Food Trails",
            "platform": "instagram",
            "subscribers": "15K-40K",
            "category": "lifestyle",
            "collab_type": "cross-promo",
            "status": "identified",
            "notes": "Food/travel content. Good for cultural stories.",
        },
    ]

    OUTREACH_TEMPLATES = {
        "cross-promo": """Subject: Collaboration Idea — ViralDNA x {partner_name}

Hi {partner_name} team,

I'm from ViralDNA, a Telugu diaspora news channel on YouTube. We cover breaking news, policy, and stories relevant to Telugu communities worldwide.

I love your content on {partner_category} and think our audiences overlap significantly. Would you be open to a cross-promotion? We could:
- Feature each other's videos in our community tabs
- Create a joint video on a trending Telugu topic
- Share each other's content on social media

Let me know if this interests you!

Best,
ViralDNA Team
youtube.com/@ViralDNA""",

        "interview": """Subject: Interview Collaboration — ViralDNA x {partner_name}

Hi {partner_name} team,

ViralDNA here — we're building a Telugu diaspora news platform on YouTube.

We'd love to feature you in our "Telugu Voices" interview series. Your perspective on {partner_category} would be valuable for our global Telugu audience.

Format: 15-20 minute video call, edited into a short feature on both channels.

Interested? Let's chat!

ViralDNA Team""",

        "reaction": """Subject: Reaction/Review Collab — ViralDNA x {partner_name}

Hi {partner_name},

ViralDNA covers Telugu news with a global perspective. We've been following your {partner_category} content and think a reaction/review collab would be great for both channels.

Idea: We react to your latest video (or vice versa) and share perspectives. Cross-pollination + entertainment value.

Let us know!

ViralDNA Team""",
    }

    def __init__(self, *args, **kwargs):
        self.db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "diagnostics", "collaboration_db.json"
        )
        self._load_db()

    def run(self, topic=None) -> dict:
        """
        Run collaboration tracking cycle.
        Returns {stats, recommendations, outreach_drafted}.
        Called by CollaborationAgent post-pipeline.
        """
        topic = topic or {}
        topic_title = topic.get("title", "") if isinstance(topic, dict) else ""
        topic_category = topic.get("category", "") if isinstance(topic, dict) else ""

        # Find relevant partners for this topic
        relevant = self._find_relevant_partners(topic_category, topic_title)

        # Generate outreach for top candidates
        outreach_drafted = []
        for partner in relevant[:3]:
            template = self.OUTREACH_TEMPLATES.get(
                partner.get("collab_type", "cross-promo"),
                self.OUTREACH_TEMPLATES["cross-promo"]
            )
            outreach_text = template.format(
                partner_name=partner["name"],
                partner_category=partner.get("category", "content"),
            )
            outreach_drafted.append({
                "partner": partner["name"],
                "platform": partner.get("platform", "youtube"),
                "collab_type": partner.get("collab_type", "cross-promo"),
                "outreach_text": outreach_text,
                "drafted_at": datetime.now().isoformat(),
            })

        # Generate recommendations
        recommendations = self._generate_recommendations(relevant, topic_category)

        return {
            "stats": self.get_stats(),
            "recommendations": recommendations,
            "outreach_drafted": outreach_drafted,
            "topic_matched": topic_title,
        }

    def get_stats(self) -> dict:
        """Return collaboration database statistics."""
        partners = self.db.get("partners", [])
        outreach = self.db.get("outreach_sent", [])
        return {
            "total_partners": len(partners),
            "active_partners": sum(1 for p in partners if p.get("status") == "active"),
            "identified_partners": sum(1 for p in partners if p.get("status") == "identified"),
            "total_outreach_sent": len(outreach),
            "successful_collabs": sum(1 for o in outreach if o.get("status") == "accepted"),
            "pending_outreach": sum(1 for o in outreach if o.get("status") == "sent"),
        }

    def _find_relevant_partners(self, category: str, title: str) -> list:
        """Find partners relevant to the current topic."""
        partners = self.db.get("partners", [])
        if not partners:
            partners = self.DEFAULT_PARTNERS
            self.db["partners"] = partners
            self._save_db()

        # Score partners by relevance
        scored = []
        title_lower = title.lower() if title else ""
        for partner in partners:
            score = 0
            p_cat = partner.get("category", "")
            if p_cat == category:
                score += 3  # Same category
            elif category and p_cat:
                score += 1  # Different but both exist

            # Boost if partner is not yet contacted
            if partner.get("status") == "identified":
                score += 2

            # Boost if title keywords match partner's focus
            p_name = partner.get("name", "").lower()
            if any(word in title_lower for word in p_name.split()):
                score += 2

            scored.append((score, partner))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in scored]

    def _generate_recommendations(self, relevant: list, category: str) -> list:
        """Generate collaboration recommendations."""
        recs = []
        stats = self.get_stats()

        if stats["total_partners"] == 0:
            recs.append("No partners in database yet. Starting with default Telugu creator list.")

        if stats["total_outreach_sent"] == 0:
            recs.append("No outreach sent yet. Start with cross-promo proposals to similar-sized channels.")

        if category:
            cat_partners = [p for p in relevant if p.get("category") == category]
            if cat_partners:
                recs.append(
                    f"Found {len(cat_partners)} potential partner(s) in '{category}' category. "
                    f"Top pick: {cat_partners[0]['name']} ({cat_partners[0].get('collab_type', 'cross-promo')})"
                )

        if stats["total_partners"] > 0 and stats["active_partners"] == 0:
            recs.append("No active partnerships yet. Follow up on identified partners or reach out to new ones.")

        recs.append(
            "Growth tip: Collaborate with channels of similar size (within 2-3x subscriber count) "
            "for maximum cross-pollination benefit."
        )

        return recs

    def _load_db(self):
        try:
            if os.path.exists(self.db_path):
                with open(self.db_path, "r") as f:
                    self.db = json.load(f)
            else:
                self.db = {"partners": [], "outreach_sent": []}
        except Exception:
            self.db = {"partners": [], "outreach_sent": []}

    def _save_db(self):
        try:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            with open(self.db_path, "w") as f:
                json.dump(self.db, f, indent=2, default=str)
        except Exception:
            pass

    def execute(self, state):
        return state
