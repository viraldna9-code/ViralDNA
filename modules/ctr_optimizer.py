"""
CTR Optimizer v3.0
Content-aware title/thumbnail CTR optimization.
Uses proven CTR factors: hook words, emotional triggers, length, specificity, curiosity gap.
v3.0: Thumbnail visual analysis — brightness, contrast, face detection, text coverage.
"""
import re, os


class CTROptimizer:
    """
    Real CTR scoring based on YouTube best practices and research.
    Scores titles AND thumbnails on multiple factors that research shows impact click-through rate.
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
        Full CTR optimization analysis — title + thumbnail.
        Returns {title, thumbnail_path, ctr_score, title_score, thumbnail_score, factors, thumbnail_factors, recommendations}.
        """
        title_score = self._score_title(title)
        factors = self._analyze_factors(title)
        thumb_score, thumb_factors = self._score_thumbnail(thumbnail_path)
        combined = int(title_score * 0.6 + thumb_score * 0.4)
        recommendations = self._generate_recommendations(title, title_score, factors)
        thumb_recs = self._generate_thumbnail_recommendations(thumb_score, thumb_factors)
        recommendations.extend(thumb_recs)

        return {
            "title": title,
            "thumbnail_path": thumbnail_path,
            "ctr_score": combined,
            "title_score": title_score,
            "thumbnail_score": thumb_score,
            "factors": factors,
            "thumbnail_factors": thumb_factors,
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

    # ── Thumbnail Visual Analysis ─────────────────────────────────────────

    def _score_thumbnail(self, thumbnail_path: str) -> tuple:
        """
        Analyze thumbnail image for CTR-relevant visual factors.
        Returns (score, factors_dict).

        Analyzes: brightness, contrast, face presence, text coverage,
        color vibrancy — all proven to impact thumbnail CTR.
        """
        if not thumbnail_path or not os.path.exists(thumbnail_path):
            return 0, {"error": "thumbnail_not_found", "path": thumbnail_path}

        try:
            from PIL import Image, ImageStat
            img = Image.open(thumbnail_path).convert("RGB")
            stat = ImageStat.Stat(img)
        except Exception as e:
            return 0, {"error": str(e), "path": thumbnail_path}

        factors = {}
        score = 50  # baseline

        # 1. Brightness — well-lit thumbnails get 25%+ more clicks
        # stat.mean gives per-channel mean; overall brightness = average of R,G,B
        brightness = sum(stat.mean) / 3.0
        factors["brightness"] = round(brightness, 1)
        if 100 <= brightness <= 200:
            score += 10  # well-lit sweet spot
        elif brightness < 60:
            score -= 15  # too dark = invisible in feed
            factors["brightness_issue"] = "too_dark"
        elif brightness > 240:
            score -= 8  # overexposed/washed out
            factors["brightness_issue"] = "too_bright"

        # 2. Contrast — high contrast stands out in feed
        # stddev of luminance
        stddev = sum(stat.stddev) / 3.0
        factors["contrast"] = round(stddev, 1)
        if stddev >= 50:
            score += 10  # high contrast,
        elif stddev >= 30:
            score += 5   # moderate
        else:
            score -= 10  # low contrast = flat/unnoticeable
            factors["contrast_issue"] = "too_low"

        # 3. Color vibrancy — vibrant thumbnails outperform muted ones
        r, g, b = stat.mean
        color_spread = max(r, g, b) - min(r, g, b)
        factors["color_vibrancy"] = round(color_spread, 1)
        if color_spread >= 40:
            score += 8
        elif color_spread < 15:
            score -= 5  # monochrome/muted
            factors["vibrancy_issue"] = "too_muted"

        # 4. Face detection — faces increase CTR by 30-50%
        has_face = self._detect_faces(img)
        factors["has_face"] = has_face
        if has_face:
            score += 15

        # 5. Aspect ratio / resolution check
        w, h = img.size
        factors["resolution"] = f"{w}x{h}"
        if w >= 1280 and h >= 720:
            score += 5
        elif w < 640:
            score -= 10
            factors["resolution_issue"] = "too_small"

        # 6. Text coverage estimation (high text area = lower CTR for news,
        #    but some text helps — sweet spot 15-35% of image)
        text_ratio = self._estimate_text_area(img)
        factors["text_coverage_pct"] = round(text_ratio * 100, 1)
        if 0.15 <= text_ratio <= 0.35:
            score += 5
        elif text_ratio > 0.55:
            score -= 8  # too much text = cluttered
            factors["text_issue"] = "too_much_text"

        factors["score"] = max(0, min(100, score))
        return max(0, min(100, score)), factors

    def _detect_faces(self, img) -> bool:
        """
        Fast face detection using a simple brightness-blob heuristic.
        For production accuracy, falls back to OpenCV if available.
        Returns True if likely face region detected.
        """
        try:
            # Try OpenCV first (most reliable)
            import cv2
            import numpy as np
            gray = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
            cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            if os.path.exists(cascade_path):
                cascade = cv2.CascadeClassifier(cascade_path)
                faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(30, 30))
                return len(faces) > 0
        except ImportError:
            pass

        # Heuristic: look for skin-tone region in center-upper area
        # Skin tone in RGB: R>95, G>40, B>20, R>G, R>B, |R-G|>15
        import numpy as np
        arr = np.array(img)
        h, w = arr.shape[:2]
        # Focus on center-upper two-thirds (where faces typically appear)
        region = arr[h//6:h*2//3, w//4:w*3//4]
        if region.size == 0:
            return False
        r, g, b = region[:,:,0], region[:,:,1], region[:,:,2]
        skin_mask = (
            (r > 95) & (g > 40) & (b > 20) &
            (r > g) & (r > b) &
            (np.abs(r.astype(int) - g.astype(int)) > 15)
        )
        skin_ratio = skin_mask.sum() / skin_mask.size
        return skin_ratio > 0.03  # >3% skin pixels = likely a face

    def _estimate_text_area(self, img) -> float:
        """
        Estimate what fraction of the thumbnail is covered by text.
        Uses edge density heuristic: text regions have high edge concentration.
        Returns 0.0-1.0 ratio.
        """
        try:
            from PIL import ImageFilter, ImageStat
            gray = img.convert("L")
            # Apply edge detection filter
            edges = gray.filter(ImageFilter.FIND_EDGES)
            edge_stat = ImageStat.Stat(edges)
            # High edge density = more text/graphics
            edge_mean = edge_stat.mean[0]
            # Normalize: typical edge_mean range 10-80 for text-heavy images
            ratio = min(1.0, edge_mean / 80.0)
            return ratio
        except Exception:
            return 0.0

    def _generate_thumbnail_recommendations(self, score: int, factors: dict) -> list:
        """Generate actionable thumbnail improvement recommendations."""
        recs = []

        if factors.get("error") == "thumbnail_not_found":
            recs.append("THUMBNAIL MISSING — Provide a thumbnail_path for CTR analysis")
            return recs

        if score >= 80:
            recs.append("Thumbnail is visually well-optimized for CTR.")
            return recs

        if factors.get("brightness_issue") == "too_dark":
            recs.append("Thumbnail is TOO DARK — increase exposure/brightness by 30-50%")
        elif factors.get("brightness_issue") == "too_bright":
            recs.append("Thumbnail is OVEREXPOSED — reduce brightness, recover detail")

        if factors.get("contrast_issue") == "too_low":
            recs.append("Thumbnail has LOW CONTRAST — boost contrast or add dark overlay + bright text")

        if factors.get("vibrancy_issue") == "too_muted":
            recs.append("Thumbnail colors are MUTED — increase saturation by 20-30% for feed visibility")

        if not factors.get("has_face", False):
            recs.append("NO FACE detected — thumbnails with faces get 30-50% more clicks. Add a relevant face/image.")

        if factors.get("resolution_issue") == "too_small":
            recs.append("Thumbnail resolution too low — use at least 1280x720")

        if factors.get("text_issue") == "too_much_text":
            recs.append("Too much text on thumbnail — reduce to a short 3-5 word headline max")

        text_pct = factors.get("text_coverage_pct", 0)
        if text_pct < 15:
            recs.append("Add a short headline text to the thumbnail for context")

        return recs

    def execute(self, state):
        return state
