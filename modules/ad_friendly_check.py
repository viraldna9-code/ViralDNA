"""
Ad-Friendly Content Checker v2.0
Real advertiser-friendly content analysis.
Checks title, description, script, and tags against YouTube's advertiser-friendly guidelines.
Returns score, risk level, and specific recommendations.
"""
import re


class AdFriendlyChecker:
    """
    Checks content against YouTube's advertiser-friendly guidelines.
    Based on YouTube's official advertiser-friendly content guidelines:
    https://support.google.com/youtube/answer/6162278
    """

    # Content categories that reduce CPM or cause demonetization
    # Each category: (keywords/patterns, severity_weight, description)
    RISK_CATEGORIES = {
        "profanity": {
            "weight": 25,
            "patterns": [
                r"\b(damn|hell|ass|shit|fuck|bitch|bastard|crap)\b",
                r"\b( asshole|bullshit|cocksucker|motherfucker)\b",
            ],
            "description": "Profanity or explicit language",
        },
        "violence": {
            "weight": 20,
            "patterns": [
                r"\b(killed|murder|massacre|slaughter|execution|torture)\b",
                r"\b(bombing|terrorist|terrorism|assassination)\b",
                r"\b(gunshot|shootout|bloodshed|carnage)\b",
            ],
            "description": "Violence-related content",
        },
        "sexual_content": {
            "weight": 25,
            "patterns": [
                r"\b(sex|porn|nude|naked|erotic|seductive)\b",
                r"\b(affair|prostitute|escort|stripper)\b",
            ],
            "description": "Sexual or suggestive content",
        },
        "substance_abuse": {
            "weight": 20,
            "patterns": [
                r"\b(cocaine|heroin|meth|drug dealer|drug cartel)\b",
                r"\b(drunk|intoxicated|alcoholism)\b",
            ],
            "description": "Drug or alcohol abuse references",
        },
        "controversy": {
            "weight": 15,
            "patterns": [
                r"\b(scandal|corrupt|controversy|controversial)\b",
                r"\b(impeachment|resign|ousted|no confidence)\b",
            ],
            "description": "Controversial or divisive topics",
        },
        "tragedy": {
            "weight": 15,
            "patterns": [
                r"\b(death toll|bodies|devastating tragedy|horrific)\b",
                r"\b(mass grave|genocide|ethnic cleansing)\b",
            ],
            "description": "Graphic tragedy or disaster descriptions",
        },
        "sensitive_events": {
            "weight": 20,
            "patterns": [
                r"\b(suicide|self-harm|lynching|hate crime)\b",
                r"\b(child abuse|sexual assault|rape)\b",
            ],
            "description": "Highly sensitive events",
        },
        "misinformation": {
            "weight": 15,
            "patterns": [
                r"\b(conspiracy|cover.?up|they don't want you to know)\b",
                r"\b(miracle cure|100% effective|doctors hate)\b",
            ],
            "description": "Potential misinformation patterns",
        },
        "hate_speech": {
            "weight": 30,
            "patterns": [
                r"\b(racist|supremacist|xenophobic)\b",
            ],
            "description": "Hate speech or discriminatory content",
        },
        "armed_conflict": {
            "weight": 20,
            "patterns": [
                r"\b(war zone|ceasefire violation|military strike|airstrike)\b",
                r"\b(invasion|annexation|occupation force)\b",
            ],
            "description": "Armed conflict or military action",
        },
    }

    # Category-specific CPM adjustments (multipliers)
    CATEGORY_CPM_MULTIPLIERS = {
        "technology": 1.3,
        "economics": 1.4,
        "health": 1.2,
        "politics": 0.8,
        "crime": 0.6,
        "disaster": 0.5,
        "sports": 1.0,
        "entertainment": 0.9,
        "policy": 1.1,
    }

    def __init__(self, *args, **kwargs):
        pass

    # ── Main Check ──────────────────────────────────────────────────────

    def check_content(self, title: str, description: str, script: str, tags: list) -> dict:
        """
        Full ad-friendly content analysis.
        Returns {score, risk_level, flags, monetization_expectation, recommendations}.
        """
        flags = []
        total_penalty = 0

        # Combine all text for analysis (tags joined as text)
        all_text = f"{title} {description} {script} {' '.join(tags)}"
        all_text_lower = all_text.lower()

        # Check each risk category
        for category, config in self.RISK_CATEGORIES.items():
            category_hits = []
            for pattern in config["patterns"]:
                matches = re.findall(pattern, all_text_lower)
                if matches:
                    category_hits.extend(matches)

            if category_hits:
                # Deduplicate hits
                unique_hits = list(set(category_hits))
                # Scale penalty by number of unique hits, capped at weight
                penalty = min(config["weight"], config["weight"] * len(unique_hits) / 2)
                total_penalty += penalty
                flags.append(
                    f"{config['description']}: found {unique_hits[:3]}"
                    + (f" (+{len(unique_hits) - 3} more)" if len(unique_hits) > 3 else "")
                )

        # Check title specifically (title has higher ad-friendly weight)
        title_lower = title.lower()
        title_flags = []
        for category, config in self.RISK_CATEGORIES.items():
            for pattern in config["patterns"]:
                if re.search(pattern, title_lower):
                    title_flags.append(config["description"])
                    total_penalty += 5  # Additional penalty for title violations
                    break  # One penalty per category in title

        if title_flags:
            flags.append(f"Title contains sensitive content: {', '.join(title_flags[:3])}")

        # Check for ALL CAPS words (aggressive = less ad-friendly)
        caps_words = re.findall(r'\b[A-Z]{3,}\b', title)
        if len(caps_words) > 2:
            total_penalty += 5
            flags.append(f"Excessive caps in title: {caps_words[:3]}")

        # Check for excessive punctuation (!!!, ???)
        if re.search(r'[!?]{2,}', title):
            total_penalty += 3
            flags.append("Excessive punctuation in title (!!! or ???)")

        # Check for clickbait patterns
        clickbait_patterns = [
            r"You won't believe",
            r"This will shock you",
            r"What happened next",
            r"Number \d+ will surprise",
            r"(?:Don't|Never|Stop) .+ (?:until|before|unless)",
        ]
        for pattern in clickbait_patterns:
            if re.search(pattern, title, re.IGNORECASE):
                total_penalty += 8
                flags.append("Clickbait pattern in title")
                break

        # Calculate score
        score = max(0, min(100, 100 - total_penalty))

        # Determine risk level
        if score >= 85:
            risk_level = "low"
            monetization_expectation = "Full monetization expected — advertiser-friendly"
        elif score >= 70:
            risk_level = "medium"
            monetization_expectation = "Limited ads — some advertisers may exclude"
        elif score >= 50:
            risk_level = "high"
            monetization_expectation = "Limited or no ads — significant restrictions expected"
        else:
            risk_level = "very_high"
            monetization_expectation = "Demonetized — content flagged as unsuitable for advertisers"

        # Generate recommendations
        recommendations = self._generate_recommendations(flags, score, title)

        return {
            "score": round(score),
            "risk_level": risk_level,
            "monetization_expectation": monetization_expectation,
            "flags": flags,
            "recommendations": recommendations,
            "checked_at": __import__("datetime").datetime.now().isoformat(),
        }

    # ── CPM Estimation ──────────────────────────────────────────────────

    def estimate_cpm_impact(self, category: str, ad_score: int) -> dict:
        """
        Estimate CPM based on content category and ad-friendliness score.
        News/politics naturally has lower CPM; technology/economics higher.
        """
        category_multiplier = self.CATEGORY_CPM_MULTIPLIERS.get(category, 1.0)

        # Base CPM for Telugu news in diaspora market (conservative)
        base_cpm_usd = 2.50

        # Ad-friendliness adjustment
        if ad_score >= 85:
            ad_multiplier = 1.0
        elif ad_score >= 70:
            ad_multiplier = 0.7
        elif ad_score >= 50:
            ad_multiplier = 0.4
        else:
            ad_multiplier = 0.1

        estimated_cpm = base_cpm_usd * category_multiplier * ad_multiplier

        return {
            "base_cpm": base_cpm_usd,
            "category": category,
            "category_multiplier": category_multiplier,
            "ad_score_multiplier": ad_multiplier,
            "estimated_cpm_usd": round(estimated_cpm, 2),
            "note": "Diaspora Telugu news audience (US/UK) commands higher CPM than India-only",
        }

    # ── Internal ────────────────────────────────────────────────────────

    def _generate_recommendations(self, flags: list, score: int, title: str) -> list:
        """Generate actionable recommendations based on flags."""
        recs = []

        if score >= 85:
            recs.append("Content is advertiser-friendly. No changes needed.")
            return recs

        # Check specific flag types
        flag_text = " ".join(flags).lower()

        if "profanity" in flag_text:
            recs.append("Remove or soften profanity for broader advertiser appeal")

        if "violence" in flag_text or "tragedy" in flag_text:
            recs.append("Use measured language for tragedy/violence — avoid graphic descriptors")

        if "sexual" in flag_text:
            recs.append("Remove sexual references or use clinical language")

        if "controversy" in flag_text:
            recs.append("Present multiple viewpoints to reduce controversy perception")

        if "clickbait" in flag_text:
            recs.append("Replace clickbait title with descriptive, factual headline")

        if "caps" in flag_text:
            recs.append("Use sentence case or title case instead of ALL CAPS")

        if "punctuation" in flag_text:
            recs.append("Limit to single exclamation/question mark")

        if not recs:
            if score < 70:
                recs.append("Content score is borderline. Consider softening language for broader advertiser appeal.")
            else:
                recs.append("Minor improvements possible but content is generally advertiser-friendly.")

        return recs

    # ── Legacy pass-through ─────────────────────────────────────────────

    def check(self, text: str) -> dict:
        """Legacy convenience method."""
        return self.check_content(title=text, description="", script=text, tags=[])

    def execute(self, state):
        return state
