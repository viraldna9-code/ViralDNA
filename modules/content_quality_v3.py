"""
Content Quality Engine v3.0 — VDNA 3.0 Port
Fact-checking, bias detection, content pillar analysis.
Ported from old pipeline's ContentQualityAgent.
"""
import os, json, re
from datetime import datetime


class ContentQualityEngine:
    def __init__(self, *args, **kwargs):
        self.ledger_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "diagnostics", "growth_ledger.json"
        )

    def load_ledger(self) -> dict:
        if os.path.exists(self.ledger_path):
            try:
                with open(self.ledger_path, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"execution_history": [], "videos": [], "user_reviews": {"scripts": [], "thumbnails": [], "videos": []}}

    def fact_check_script(self, script_text: str) -> dict:
        """
        Heuristic fact-check: flags unverified claims, statistics without
        sources, and absolute statements that need verification.
        """
        flags = []

        # Numbers/percentages without source citation
        unverified_stats = re.findall(
            r'\b(\d+[\d,.]*\s*(%|percent|crore|lakh|million|billion|thousand))(?!\s*(according to|per|as per|reported by|source))',
            script_text, re.IGNORECASE
        )
        if unverified_stats:
            flags.append(f"{len(unverified_stats)} statistic(s) without cited source")

        # Absolute claims
        absolute_patterns = [
            r'\b(all|every|none|never|always|no one|everyone)\s+(?:politician|minister|party|government|opposition)\b',
            r'\b(proven|guaranteed|100%|definitely|certainly)\b',
        ]
        for pat in absolute_patterns:
            matches = re.findall(pat, script_text, re.IGNORECASE)
            if matches:
                flags.append(f"Absolute claim detected: '{matches[0]}'")

        # Vague sources
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

    def detect_bias(self, script_text: str) -> dict:
        """
        Heuristic bias detection: checks for loaded language, one-sided
        framing, and partisan signaling.
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

        # One-sided framing
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
        mix_data = self.analyze_content_mix(video_history)
        if not mix_data["mix"]:
            return "POLITICS"  # Default starting pillar
        # Recommend the least-used pillar
        used = set(mix_data["mix"].keys())
        unused = [p for p in self.CONTENT_PILLARS if p not in used]
        if unused:
            return unused[0]
        # All used — pick the one with lowest ratio
        return min(mix_data["mix"], key=lambda k: mix_data["mix"][k])

    def run_quality_check(self, script_text: str, video_history: list = None) -> dict:
        """Run full quality check: fact-check + bias + pillar analysis."""
        fact_result = self.fact_check_script(script_text)
        bias_result = self.detect_bias(script_text)
        pillar_data = self.analyze_content_mix(video_history or [])
        next_pillar = self.recommend_next_pillar(video_history or [])

        overall_pass = fact_result["pass"] and bias_result["pass"]

        return {
            "overall_pass": overall_pass,
            "fact_check": fact_result,
            "bias_detection": bias_result,
            "content_mix": pillar_data,
            "recommended_next_pillar": next_pillar,
            "checked_at": datetime.now().isoformat(),
        }

    def execute(self, state):
        return state
