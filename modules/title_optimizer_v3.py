"""
Title Optimization Module — VDNA 3.0
A/B tests multiple title variants using CTR prediction.
Generates 3-5 title options and scores each for click-through potential.
"""
import random
from datetime import datetime


class TitleOptimizer:
    """Generate and score multiple title variants for maximum CTR."""

    # Power words that boost CTR (Telugu news context)
    POWER_WORDS_EN = [
        "Breaking", "Exclusive", "Shocking", "Revealed", "Hidden",
        "Truth", "Exposed", "Urgent", "Alert", "Just In",
        "What Happened", "Why", "How", "Secret", "Unexpected",
    ]

    POWER_WORDS_TE = [
        "విడుదల", "తాజా", "అసలు", "రహస్యం", "ఆశ్చర్యం",
        "నిజం", "బయటపడింది", "హెచ్చరిక", "కొత్త", "ముఖ్యమైన",
    ]

    # CTR-killing words (reduce clickbait penalty)
    CTR_KILLERS = ["click here", "you won't believe", "this is crazy", "omg"]

    def __init__(self, *args, **kwargs):
        self.variants = []

    def generate_variants(self, base_title: str, topic_context: str = "", num_variants: int = 5) -> list:
        """Generate multiple title variants from a base title."""
        variants = []
        clean = base_title.strip()

        # Variant 1: Original (baseline)
        variants.append({"text": clean, "style": "original", "index": 0})

        # Variant 2: Power word prefix
        pw = random.choice(self.POWER_WORDS_EN)
        variants.append({"text": f"{pw}: {clean}", "style": "power_prefix", "index": 1})

        # Variant 3: Question format
        if not clean.endswith("?"):
            q = f"What Happened With {clean}?"
            variants.append({"text": q, "style": "question", "index": 2})

        # Variant 4: Curiosity gap
        variants.append({"text": f"{clean} — The Truth Is Out", "style": "curiosity", "index": 3})

        # Variant 5: Urgency
        variants.append({"text": f"BREAKING: {clean}", "style": "urgency", "index": 4})

        # Trim to num_variants
        variants = variants[:num_variants]

        # Enforce 100-char YouTube limit
        for v in variants:
            if len(v["text"]) > 100:
                v["text"] = v["text"][:97] + "..."

        self.variants = variants
        return variants

    def score_title(self, title: str) -> dict:
        """Score a single title for CTR potential."""
        score = 50  # baseline
        breakdown = {}

        # Length score (40-70 chars is optimal)
        length = len(title)
        if 40 <= length <= 70:
            length_score = 15
        elif 30 <= length <= 80:
            length_score = 10
        else:
            length_score = 5
        score += length_score
        breakdown["length"] = length_score

        # Power word bonus
        pw_count = sum(1 for pw in self.POWER_WORDS_EN if pw.lower() in title.lower())
        pw_score = min(pw_count * 5, 15)
        score += pw_score
        breakdown["power_words"] = pw_score

        # Question bonus (questions get more clicks)
        question_score = 8 if title.endswith("?") else 0
        score += question_score
        breakdown["question_format"] = question_score

        # Number bonus (numbered titles perform well)
        number_score = 5 if any(c.isdigit() for c in title) else 0
        score += number_score
        breakdown["contains_number"] = number_score

        # CTR killer penalty
        killer_count = sum(1 for k in self.CTR_KILLERS if k.lower() in title.lower())
        killer_penalty = killer_count * -10
        score += killer_penalty
        breakdown["ctr_killer_penalty"] = killer_penalty

        # Emotional intensity (caps words = urgency)
        caps_words = sum(1 for w in title.split() if w.isupper() and len(w) > 1)
        emotion_score = min(caps_words * 3, 10)
        score += emotion_score
        breakdown["emotional_intensity"] = emotion_score

        # Telugu word bonus (local audience connection)
        te_count = sum(1 for w in self.POWER_WORDS_TE if w in title)
        te_score = min(te_count * 3, 8)
        score += te_score
        breakdown["telugu_connection"] = te_score

        final_score = max(0, min(score, 100))
        return {
            "title": title,
            "score": final_score,
            "breakdown": breakdown,
            "tier": "high" if final_score >= 70 else "medium" if final_score >= 50 else "low",
            "scored_at": datetime.now().isoformat(),
        }

    def select_best(self, variants: list) -> dict:
        """Score all variants and return the best."""
        scored = [self.score_title(v["text"]) for v in variants]
        scored.sort(key=lambda x: x["score"], reverse=True)
        best = scored[0]

        return {
            "best_title": best["title"],
            "best_score": best["score"],
            "best_tier": best["tier"],
            "all_scores": scored,
            "recommendation": f"Use: \"{best['title']}\" (score: {best['score']}/100, {best['tier']} CTR)",
        }

    def execute(self, state):
        return state
