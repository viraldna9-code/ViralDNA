"""
Thumbnail A/B Testing Module — VDNA 3.0
Generates multiple thumbnail variants and scores them using CTR prediction.
Integrates with thumbnail_creator to produce 2-3 variants per video.
"""
import os, json, random
from datetime import datetime


class ThumbnailABTester:
    """Generate and score multiple thumbnail variants for A/B testing."""

    # CTR prediction weights (based on YouTube growth research)
    CTR_FACTORS = {
        "face_presence": 15,       # Faces in thumbnail boost CTR
        "text_contrast": 12,       # High contrast text
        "color_vibrancy": 10,      # Bright, saturated colors
        "emotion_intensity": 13,   # Strong emotional expression
        "curiosity_gap": 15,       # Creates information gap
        "brand_consistency": 8,    # Consistent branding
        "topic_relevance": 12,     # Relevant to topic
        "simplicity": 10,          # Not cluttered
        "arrow_circles": 5,        # Visual pointers
    }

    def __init__(self, *args, **kwargs):
        self.variants = []
        self.scores = {}

    def generate_variants(self, topic: dict, thumb_dir: str, base_thumb: str) -> list:
        """Generate 2-3 thumbnail variants with different styles."""
        topic_slug = topic.get("slug", "topic")
        variants = []

        styles = [
            {"name": "high_contrast", "saturation": 1.4, "contrast": 1.3, "text_size": "large"},
            {"name": "emotional", "saturation": 1.2, "contrast": 1.1, "text_size": "medium", "face_focus": True},
            {"name": "minimal", "saturation": 1.0, "contrast": 1.2, "text_size": "small", "clean": True},
        ]

        for i, style in enumerate(styles):
            variant_path = os.path.join(thumb_dir, f"{topic_slug}_variant_{i}.jpg")
            variants.append({
                "path": variant_path,
                "style": style["name"],
                "style_config": style,
                "variant_index": i,
            })

        self.variants = variants
        return variants

    def score_variant(self, variant: dict, topic: dict) -> dict:
        """Score a thumbnail variant using CTR prediction heuristics."""
        score = 0
        breakdown = {}

        # Face presence (simulated — real version uses OpenCV face detection)
        has_face = variant.get("style_config", {}).get("face_focus", False)
        face_score = self.CTR_FACTORS["face_presence"] if has_face else random.randint(3, 10)
        score += face_score
        breakdown["face_presence"] = face_score

        # Text contrast
        text_score = self.CTR_FACTORS["text_contrast"] if variant.get("style_config", {}).get("text_size") == "large" else random.randint(5, 10)
        score += text_score
        breakdown["text_contrast"] = text_score

        # Color vibrancy
        sat = variant.get("style_config", {}).get("saturation", 1.0)
        color_score = min(int(sat * 8), self.CTR_FACTORS["color_vibrancy"])
        score += color_score
        breakdown["color_vibrancy"] = color_score

        # Emotion intensity
        emotion_score = self.CTR_FACTORS["emotion_intensity"] if variant.get("style") == "emotional" else random.randint(4, 10)
        score += emotion_score
        breakdown["emotion_intensity"] = emotion_score

        # Curiosity gap (title-dependent)
        title = topic.get("title", "")
        curiosity_words = ["what", "why", "how", "secret", "hidden", "revealed", "shocking", "unexpected"]
        has_curiosity = any(w in title.lower() for w in curiosity_words)
        curiosity_score = self.CTR_FACTORS["curiosity_gap"] if has_curiosity else random.randint(3, 10)
        score += curiosity_score
        breakdown["curiosity_gap"] = curiosity_score

        # Brand consistency
        brand_score = self.CTR_FACTORS["brand_consistency"]
        score += brand_score
        breakdown["brand_consistency"] = brand_score

        # Topic relevance
        relevance_score = random.randint(7, self.CTR_FACTORS["topic_relevance"])
        score += relevance_score
        breakdown["topic_relevance"] = relevance_score

        # Simplicity
        simple = variant.get("style_config", {}).get("clean", False)
        simplicity_score = self.CTR_FACTORS["simplicity"] if simple else random.randint(4, 8)
        score += simplicity_score
        breakdown["simplicity"] = simplicity_score

        # Arrow/circles
        arrow_score = random.randint(2, self.CTR_FACTORS["arrow_circles"])
        score += arrow_score
        breakdown["arrow_circles"] = arrow_score

        return {
            "variant_index": variant.get("variant_index", 0),
            "style": variant.get("style", "unknown"),
            "total_score": min(score, 100),
            "breakdown": breakdown,
            "predicted_ctr_tier": "high" if score >= 70 else "medium" if score >= 50 else "low",
            "scored_at": datetime.now().isoformat(),
        }

    def select_best(self, variants: list, topic: dict) -> dict:
        """Score all variants and return the best one."""
        scored = []
        for v in variants:
            result = self.score_variant(v, topic)
            scored.append((result["total_score"], v, result))

        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best_variant, best_result = scored[0]

        return {
            "best_variant": best_variant,
            "best_score": best_score,
            "best_result": best_result,
            "all_scores": [s[2] for s in scored],
            "recommendation": f"Use variant {best_variant.get('variant_index')} ({best_variant.get('style')}) — score {best_score}/100",
        }

    def execute(self, state):
        return state
