"""
CTR Optimizer v2.0
Content-aware title/thumbnail CTR optimization.
Uses proven CTR factors: hook words, emotional triggers, length, specificity, curiosity gap.
"""
import re


class CTROptimizer:
    """
    Real CTR scoring based on YouTube best practices and research.
    Scores titles on multiple factors that research shows impact click-through rate.
    """

    # Hook words that increase CTR (based on YouTube analytics research)
    HIGH_CTR_HOOKS = {
        "breaking": 12, "exclusive": 10, "revealed": 10, "shocking": 9,
        "urgent": 9, "alert": 8, "warning": 8, "just": 7, "new": 6,
        "update": 5, "explained": 8, "analysis": 7, "full": 5, "complete": 5,
        "why": 9, "how": 8, "what": 7, "secret": 11, "hidden": 10,
        "truth": 9, "real": 7, "finally": 8, "official": 6, "confirmed": 7,
    }

    # Words that decrease CTR (clickbait fatigue, vague)
    LOW_CTR_WORDS = {
        "stuff": -5, "things": -4, "something": -3, "whatever": -6,
        "interesting": -3, "nice": -4, "good": -3, "bad": -2,
        "very": -2, "really": -2, "just": -1, "basically": -3,
    }

    # Emotional triggers (curiosity, urgency, fear of missing out)
    EMOTIONAL_TRIGGERS = {
        "curiosity": ["why", "how", "what happened", "secret", "hidden", "revealed", "truth"],
        "urgency": ["breaking", "urgent", "just", "alert", "warning", "now", "today"],
        "fomo": ["before it's too late", "don't miss", "last chance", "ending", "final"],
        "authority": ["official", "confirmed", "government", "rbi", "supreme court", "pm"],
    }

    # Optimal title length range (YouTube truncates at ~60 chars in search)
    OPTIMAL_MIN_LEN = 30
    OPTIMAL_MAX_LEN = 60
    ABSOLUTE_MAX = 100

    def __init__(self):
        pass

    def optimize(self, title: str, thumbnail_path: str = "") -> dict:
        """
        Full CTR optimization analysis.
        Returns {title, thumbnail_path, ctr_score, factors, recommendations}.
        """
        score = self._score_title(title)
        factors = self._analyze_factors(title)
        recommendations = self._generate_recommendations(title, score, factors)

        return {
            "title": title,
            "thumbnail_path": thumbnail_path,
            "ctr_score": score,
            "factors": factors,
            "recommendations": recommendations,
        }

    def score_titles(self, title_variants: list) -> list:
        """
        Score and rank title variants. Returns list of {title, score, factors}.
        Sorted by score descending.
        """
        scored = []
        for variant in title_variants:
            if isinstance(variant, dict):
                t = variant.get("title", str(variant))
            elif isinstance(variant, (list, tuple)) and len(variant) >= 1:
                t = str(variant[0])
            else:
                t = str(variant)

            score = self._score_title(t)
            factors = self._analyze_factors(t)
            scored.append({"title": t, "score": score, "factors": factors})

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored

    def generate_title_variants(self, title: str) -> list:
        """
        Generate meaningful A/B test variants from a base title.
        Uses proven CTR patterns: hook prefix, question format, specificity.
        """
        variants = [
            {"title": title, "type": "original"},
        ]

        # Variant 1: Add high-CTR hook prefix
        has_hook = any(hook in title.lower() for hook in self.HIGH_CTR_HOOKS)
        if not has_hook:
            # Add "Breaking:" if it's news, "Explained:" if analytical
            if any(word in title.lower() for word in ["announced", "said", "reported", "update"]):
                variants.append({"title": f"Breaking: {title}", "type": "hook_breaking"})
            else:
                variants.append({"title": f"{title} — Explained", "type": "hook_explained"})
        else:
            variants.append({"title": f"{title} — What It Means", "type": "context"})

        # Variant 2: Question format (curiosity gap)
        if "?" not in title:
            # Convert statement to question
            words = title.split()
            if len(words) > 3:
                question = f"What Happened with {' '.join(words[:4])}?"
                variants.append({"title": question, "type": "question"})
            else:
                variants.append({"title": f"Why {title}?", "type": "question"})
        else:
            variants.append({"title": f"Analysis: {title}", "type": "analysis"})

        # Variant 3: Specificity (add numbers or specifics if generic)
        if not re.search(r'\d', title):
            variants.append({"title": f"{title} — Full Analysis", "type": "specificity"})
        else:
            variants.append({"title": f"{title} — Complete Breakdown", "type": "specificity"})

        return variants

    # ── Scoring Engine ──────────────────────────────────────────────────

    def _score_title(self, title: str) -> int:
        """Score a title 0-100 based on multiple CTR factors."""
        score = 50  # Start at baseline
        title_lower = title.lower()
        words = title_lower.split()

        # Factor 1: Hook words (+up to 20)
        hook_score = 0
        for word, points in self.HIGH_CTR_HOOKS.items():
            if word in title_lower:
                hook_score += points
        score += min(20, hook_score)

        # Factor 2: Negative words (-up to -15)
        neg_score = 0
        for word, points in self.LOW_CTR_WORDS.items():
            if word in title_lower:
                neg_score += points
        score += max(-15, neg_score)

        # Factor 3: Length optimization (+/- 10)
        title_len = len(title)
        if self.OPTIMAL_MIN_LEN <= title_len <= self.OPTIMAL_MAX_LEN:
            score += 10  # Sweet spot
        elif title_len < self.OPTIMAL_MIN_LEN:
            score += max(-5, (title_len - self.OPTIMAL_MIN_LEN) // 3)  # Too short
        elif title_len > self.ABSOLUTE_MAX:
            score -= 10  # Way too long, will be truncated
        else:
            score += max(0, 10 - (title_len - self.OPTIMAL_MAX_LEN) // 5)  # Slightly long

        # Factor 4: Emotional triggers (+up to 15)
        emotion_score = 0
        for emotion, triggers in self.EMOTIONAL_TRIGGERS.items():
            for trigger in triggers:
                if trigger in title_lower:
                    emotion_score += 5
                    break  # One point per emotion category
        score += min(15, emotion_score)

        # Factor 5: Specificity (+up to 10)
        if re.search(r'\d', title):  # Contains numbers
            score += 5
        if re.search(r'\b(percent|%|rs\.?|₹|million|billion|crore|lakh)\b', title_lower):
            score += 5  # Financial specificity

        # Factor 6: Curiosity gap (+up to 10)
        if "?" in title:
            score += 5  # Questions create curiosity
        if any(word in title_lower for word in ["why", "how", "what"]):
            score += 5  # Question words

        # Factor 7: Penalties
        # ALL CAPS words (aggressive)
        caps_count = sum(1 for w in words if w.isupper() and len(w) > 2)
        if caps_count > 2:
            score -= 10
        elif caps_count > 0:
            score -= 3

        # Excessive punctuation
        if re.search(r'[!?]{2,}', title):
            score -= 5

        # Clickbait patterns (YouTube may suppress)
        clickbait = ["you won't believe", "this will shock", "what happened next",
                     "number \\d+ will surprise", "doctors hate"]
        for pattern in clickbait:
            if re.search(pattern, title_lower):
                score -= 8
                break

        return max(0, min(100, score))

    def _analyze_factors(self, title: str) -> dict:
        """Analyze which CTR factors are present in the title."""
        title_lower = title.lower()
        words = title_lower.split()

        hooks_found = [w for w in self.HIGH_CTR_HOOKS if w in title_lower]
        negatives_found = [w for w in self.LOW_CTR_WORDS if w in title_lower]
        emotions_found = []
        for emotion, triggers in self.EMOTIONAL_TRIGGERS.items():
            if any(t in title_lower for t in triggers):
                emotions_found.append(emotion)

        return {
            "length": len(title),
            "word_count": len(words),
            "hooks_found": hooks_found,
            "negatives_found": negatives_found,
            "emotions_triggered": emotions_found,
            "has_numbers": bool(re.search(r'\d', title)),
            "has_question": "?" in title,
            "has_caps": any(w.isupper() and len(w) > 2 for w in words),
            "optimal_length": self.OPTIMAL_MIN_LEN <= len(title) <= self.OPTIMAL_MAX_LEN,
        }

    def _generate_recommendations(self, title: str, score: int, factors: dict) -> list:
        """Generate actionable CTR improvement recommendations."""
        recs = []

        if score >= 80:
            recs.append("Title is well-optimized for CTR. No major changes needed.")
            return recs

        if not factors["hooks_found"]:
            recs.append("Add a high-CTR hook word: Breaking, Revealed, Explained, or Why")

        if not factors["emotions_triggered"]:
            recs.append("Add emotional trigger: curiosity (why/how), urgency (breaking/now), or authority (official/confirmed)")

        if not factors["optimal_length"]:
            if len(title) < self.OPTIMAL_MIN_LEN:
                recs.append(f"Title is too short ({len(title)} chars). Aim for {self.OPTIMAL_MIN_LEN}-{self.OPTIMAL_MAX_LEN} characters.")
            elif len(title) > self.OPTIMAL_MAX_LEN:
                recs.append(f"Title is long ({len(title)} chars). YouTube truncates at ~60 chars in search. Consider shortening.")

        if not factors["has_numbers"]:
            recs.append("Add specific numbers or data points for higher CTR (e.g., '50%', 'Rs 500 crore')")

        if not factors["has_question"] and "why" not in title.lower() and "how" not in title.lower():
            recs.append("Consider a question format or 'Why/How' prefix for curiosity gap")

        if factors["has_caps"]:
            recs.append("Reduce ALL CAPS words — looks aggressive and may reduce CTR")

        if factors["negatives_found"]:
            recs.append(f"Remove weak words: {', '.join(factors['negatives_found'][:3])}")

        if not recs:
            recs.append("Minor improvements possible but title is generally well-optimized.")

        return recs

    def execute(self, state):
        return state
