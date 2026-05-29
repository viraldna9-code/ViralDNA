"""
Content Quality Engine v2.0
Fact-checking, bias detection, content pillar analysis.
Returns structured dicts matching ContentQualityAgent expectations.
"""
import os, json, re
from datetime import datetime


class ContentQualityEngine:
    def __init__(self, *args, **kwargs):
        self.ledger_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "diagnostics", "growth_ledger.json"
        )

    # ── Ledger ──────────────────────────────────────────────────────────

    def load_ledger(self) -> dict:
        if os.path.exists(self.ledger_path):
            try:
                with open(self.ledger_path, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"execution_history": [], "videos": [], "user_reviews": {"scripts": [], "thumbnails": [], "videos": []}}

    # ── Fact Check ──────────────────────────────────────────────────────

    def fact_check_script(self, script_text: str) -> dict:
        """
        Heuristic fact-check: flags unverified claims, statistics without
        sources, and absolute statements that need verification.
        Returns {"pass": bool, "needs_review": int, "flags": list}
        """
        flags = []

        # Pattern: numbers/percentages without "according to" or source
        unverified_stats = re.findall(
            r'\b(\d+[\d,.]*\s*(%|percent|crore|lakh|million|billion|thousand))(?!\s*(according to|per|as per|reported by|source))',
            script_text, re.IGNORECASE
        )
        if unverified_stats:
            flags.append(f"{len(unverified_stats)} statistic(s) without cited source")

        # Pattern: absolute claims
        absolute_patterns = [
            r'\b(all|every|none|never|always|no one|everyone)\s+(?:politician|minister|party|government|opposition)\b',
            r'\b(proven|guaranteed|100%|definitely|certainly)\b',
        ]
        for pat in absolute_patterns:
            matches = re.findall(pat, script_text, re.IGNORECASE)
            if matches:
                flags.append(f"Absolute claim detected: '{matches[0]}'")

        # Pattern: "sources say" without naming
        vague_sources = re.findall(
            r'\b(sources say|sources claim|it is said|reports suggest|some say)\b',
            script_text, re.IGNORECASE
        )
        if vague_sources:
            flags.append(f"{len(vague_sources)} vague source reference(s) without naming")

        needs_review = len(flags)
        return {
            "pass": needs_review == 0,
            "needs_review": needs_review,
            "flags": flags,
            "checked_at": datetime.now().isoformat(),
        }

    # ── Bias Detection ──────────────────────────────────────────────────

    def detect_bias(self, script_text: str) -> dict:
        """
        Heuristic bias detection: checks for loaded language, one-sided
        framing, and partisan signaling.
        Returns {"pass": bool, "risk_level": str, "flags": list}
        """
        flags = []
        text_lower = script_text.lower()

        # Loaded emotional language
        loaded_words = [
            "shocking", "disastrous", "catastrophic", "horrific",
            "brilliant", "genius", "heroic", "legendary",
            "corrupt", "incompetent", "pathetic", "ridiculous",
            "destroyed", "crushed", "slammed", "blasted",
        ]
        found_loaded = [w for w in loaded_words if w in text_lower]
        if found_loaded:
            flags.append(f"Loaded language: {', '.join(found_loaded[:5])}")

        # One-sided framing (only negative or only positive about a subject)
        negative_framing = re.findall(
            r'\b(failed|failure|scandal|controversy|backlash|outrage|anger|fury)\b',
            text_lower
        )
        positive_framing = re.findall(
            r'\b(success|achievement|breakthrough|praise|celebrated|applauded|hailed)\b',
            text_lower
        )
        if len(negative_framing) >= 3 and len(positive_framing) == 0:
            flags.append("One-sided negative framing detected")
        elif len(positive_framing) >= 3 and len(negative_framing) == 0:
            flags.append("One-sided positive framing detected")

        # Partisan signaling
        partisan = re.findall(
            r'\b(our side|their side|true patriot|anti-national|propaganda|agenda|biased media)\b',
            text_lower
        )
        if partisan:
            flags.append(f"Partisan signaling: {', '.join(partisan[:3])}")

        # Determine risk level
        if len(flags) == 0:
            risk_level = "low"
        elif len(flags) <= 2:
            risk_level = "medium"
        else:
            risk_level = "high"

        return {
            "pass": risk_level == "low",
            "risk_level": risk_level,
            "flags": flags,
            "checked_at": datetime.now().isoformat(),
        }

    # ── Content Pillar Analysis ──────────────────────────────────────────

    CONTENT_PILLARS = [
        "POLITICS", "ECONOMICS", "DISASTER", "CRIME",
        "POLICY", "SPORTS", "ENTERTAINMENT", "HEALTH", "TECHNOLOGY"
    ]

    def analyze_content_mix(self, video_history: list) -> dict:
        """Analyze the mix of content pillars in recent video history."""
        if not video_history:
            return {"mix": {}, "total": 0, "dominant": None}

        pillar_counts = {}
        for video in video_history:
            pillar = (
                video.get("pillar")
                or video.get("category")
                or video.get("topic_category")
                or "UNKNOWN"
            )
            pillar_counts[pillar] = pillar_counts.get(pillar, 0) + 1

        total = sum(pillar_counts.values())
        mix = {k: round(v / total, 2) for k, v in pillar_counts.items()}
        dominant = max(pillar_counts, key=lambda k: pillar_counts[k]) if pillar_counts else None

        return {"mix": mix, "total": total, "dominant": dominant}

    def recommend_next_pillar(self, video_history: list) -> str:
        """Recommend the next content pillar to maintain variety."""
        mix = self.analyze_content_mix(video_history)
        if mix["total"] == 0:
            return "POLITICS"

        # Find the least-represented pillar
        represented = set(mix["mix"].keys())
        missing = [p for p in self.CONTENT_PILLARS if p not in represented]
        if missing:
            return missing[0]

        # All represented — pick the one with lowest share
        return min(mix["mix"], key=mix["mix"].get)

    # ── B2.8: Content Depth Analysis ──────────────────────────────────────

    # Depth indicators: words/phrases that signal substantive reporting
    DEPTH_SIGNALS = {
        "data_points": [
            r'\$\d+', r'\d+%', r'\d+\s*(million|billion|crore|lakh)',
            r'\d+\s*people', r'\d+\s*days', r'\d+\s*years',
        ],
        "attribution": [
            "according to", "reported by", "sources say", "officials confirmed",
            "data shows", "analysis reveals", "study found", "experts say",
            "government data", "census", "survey", "report",
        ],
        "context": [
            "background", "history", "previously", "in contrast", "compared to",
            "this follows", "comes after", "builds on", "related to",
            "impact on", "effect of", "consequence", "result of",
        ],
        "nuance": [
            "however", "but", "although", "on the other hand", "critics say",
            "supporters argue", "debate", "controversy", "complex",
            "multifaceted", "nuanced", "perspective",
        ],
        "actionability": [
            "what this means", "how it affects", "what you need to know",
            "steps to", "what to do", "how to", "guide", "explained",
            "breakdown", "analysis", "deep dive",
        ],
    }

    def analyze_content_depth(self, script_text: str, topic: dict = None) -> dict:
        """
        B2.8: Score content depth 0-100 based on topic complexity signals.
        Evaluates: data richness, attribution quality, contextual depth,
        nuance/perspective balance, and actionability.
        Returns {"score": float, "level": str, "breakdown": dict, "recommendations": list}
        """
        if not script_text:
            return {"score": 0, "level": "shallow", "breakdown": {}, "recommendations": ["No script text provided"]}

        text_lower = script_text.lower()
        words = text_lower.split()
        word_count = len(words)
        breakdown = {}
        recommendations = []

        # 1. Data richness (0-20 points)
        data_score = 0
        for pattern in self.DEPTH_SIGNALS["data_points"]:
            if re.search(pattern, text_lower):
                data_score += 5
        data_score = min(data_score, 20)
        breakdown["data_richness"] = data_score
        if data_score < 10:
            recommendations.append("Add specific numbers, percentages, or statistics for credibility")

        # 2. Attribution quality (0-20 points)
        attr_count = sum(1 for phrase in self.DEPTH_SIGNALS["attribution"] if phrase in text_lower)
        attr_score = min(attr_count * 5, 20)
        breakdown["attribution"] = attr_score
        if attr_score < 10:
            recommendations.append("Add source attribution (e.g., 'according to officials', 'data shows')")

        # 3. Contextual depth (0-20 points)
        ctx_count = sum(1 for phrase in self.DEPTH_SIGNALS["context"] if phrase in text_lower)
        ctx_score = min(ctx_count * 4, 20)
        breakdown["context"] = ctx_score
        if ctx_score < 10:
            recommendations.append("Add background context — explain why this matters and what led to it")

        # 4. Nuance / perspective balance (0-20 points)
        nuance_count = sum(1 for phrase in self.DEPTH_SIGNALS["nuance"] if phrase in text_lower)
        nuance_score = min(nuance_count * 5, 20)
        breakdown["nuance"] = nuance_score
        if nuance_score < 10:
            recommendations.append("Include multiple perspectives — what supporters and critics say")

        # 5. Actionability (0-20 points)
        action_count = sum(1 for phrase in self.DEPTH_SIGNALS["actionability"] if phrase in text_lower)
        action_score = min(action_count * 5, 20)
        breakdown["actionability"] = action_score
        if action_score < 10:
            recommendations.append("Add 'what this means for you' section — make it actionable")

        # 6. Length bonus/penalty (word count adequacy)
        if word_count >= 150:
            length_bonus = 0  # adequate
        elif word_count >= 100:
            length_bonus = -5
            recommendations.append(f"Script is {word_count} words — aim for 150+ for adequate depth")
        else:
            length_bonus = -10
            recommendations.append(f"Script is only {word_count} words — too short for meaningful depth analysis")

        total_score = sum(breakdown.values()) + length_bonus
        total_score = max(0, min(total_score, 100))

        if total_score >= 70:
            level = "deep"
        elif total_score >= 45:
            level = "moderate"
        elif total_score >= 25:
            level = "shallow"
        else:
            level = "very_shallow"

        return {
            "score": total_score,
            "level": level,
            "word_count": word_count,
            "breakdown": breakdown,
            "recommendations": recommendations[:5],  # top 5
            "checked_at": datetime.now().isoformat(),
        }

    # ── Legacy pass-through (kept for backward compat) ──────────────────

    def execute(self, state):
        return state
