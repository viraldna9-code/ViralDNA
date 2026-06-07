# VERSION: 64.0
# MODULE: script_generator.py
# PURPOSE: Hybrid Synthesis Script Engine (Dynamic Gemini API with Heuristic Fallback)
#          v64.0: Integrated HumanizerEngine post-processing pass to strip AI-isms
#                  from generated scripts (significance inflation, promotional language,
#                  vague attributions, filler phrases, copula avoidance, etc.)
#          v63.0: CTR-optimized title formulas, sentiment scoring, keyword integration,
#                  Shorts-specific title formulas, retention-optimized script structure,
#                  end-of-video CTA hooks, search volume keyword injection
#          v62.0: Initial Hybrid Synthesis Engine

import json, os, re, math
from data_flow_registry import ScriptPayload
from humanizer_engine import HumanizerEngine

class ScriptGenerator:
    def __init__(self, engine, config_dict: dict):
        self.engine = engine
        self.config = config_dict
        print("  ✅ ScriptGenerator (v63.0): Hybrid Synthesis Engine Initialized.")

    # ─── Bilingual Title Optimization (A1.7) ───
    # Telugu context words injected into title variants for bilingual SEO
    # These are standard English transliterations that TTS can pronounce
    TELUGU_CONTEXT_WORDS = {
        "andhra": ["ఆంధ్ర", "Andhra", "AP"],
        "telangana": ["తెలంగాణ", "Telangana", "TG"],
        "telugu": ["తెలుగు", "Telugu", "Tollywood"],
        "vijayawada": ["విజయవాడ", "Vijayawada", "VJA"],
        "vizag": ["విశాఖ", "Vizag", "Visakhapatnam", "Vizag"],
        "hyderabad": ["హైదరాబాద్", "Hyderabad", "Hyd"],
        "amaravati": ["అమరావతి", "Amaravati"],
        "guntur": ["గుంటూరు", "Guntur"],
        "cricket": ["క్రికెట్", "Cricket", "IPL"],
        "movie": ["సినిమా", "Movie", "Cinema", "Tollywood"],
        "cinema": ["సినిమా", "Cinema", "Tollywood"],
        "politics": ["రాజకీయాలు", "Politics", "Elections"],
        "economy": ["ఆర్థిక", "Economy", "Budget"],
        "health": ["ఆరోగ్య", "Health", "Medical"],
        "education": ["విద్య", "Education", "Schools"],
        "visa": ["వీజా", "Visa", "H1B", "Green Card"],
        "immigration": ["వలస", "Immigration", "NRI"],
        "usa": ["అమెరికా", "USA", "America", "US"],
        "uk": ["ఇంగ్లండు", "UK", "Britain", "London"],
        "canada": ["కెనడా", "Canada"],
        "breaking": ["బ్రేకింగ్", "Breaking", "Just In"],
        "urgent": ["అత్యవసర", "Urgent", "Alert"],
    }

    def _add_bilingual_title_variants(self, title: str, topic_context: str) -> list:
        """
        A1.7: Generate bilingual title variants with Telugu context words.
        Adds 2 extra title variants that include Telugu/English hybrid keywords
        for improved search discoverability in both languages.
        Returns list of {title, description} dicts.
        """
        clean_title = title.strip()
        text = f"{title} {topic_context}".lower()

        # Find matching Telugu context words
        matched_telugu = []
        for keyword, telugu_words in self.TELUGU_CONTEXT_WORDS.items():
            if keyword in text:
                # Use the English transliteration (index 1) for TTS compatibility
                if len(telugu_words) > 1:
                    matched_telugu.append(telugu_words[1])
                else:
                    matched_telugu.append(telugu_words[0])

        if not matched_telugu:
            return []

        # Pick top 2 Telugu context words
        telugu_tag = " | ".join(matched_telugu[:2])

        import datetime
        year = datetime.datetime.now().year

        variants = [
            {
                "title": f"{clean_title} | {telugu_tag} News {year}",
                "description": f"{clean_title} — {telugu_tag} updates from TheViralDNA. News for Telugu families worldwide."
            },
            {
                "title": f"{telugu_tag}: {clean_title} | {year}",
                "description": f"Latest {telugu_tag} news: {clean_title}. TheViralDNA keeps you connected to home."
            },
        ]
        return variants

    # ─── CTR Title Formula Engine (A1.4) ───
    # Power words, numbers, brackets, emotional triggers proven to boost CTR
    CTR_POWER_WORDS = [
        "BREAKING", "URGENT", "EXCLUSIVE", "SHOCKING", "JUST IN",
        "REVEALED", "IMPORTANT", "CRITICAL", "ALERT", "UPDATE",
    ]
    CTR_BRACKET_PATTERNS = ["{}", "[]", "📌", "🔥", "⚠️", "🚨"]
    CTR_NUMBER_PATTERNS = ["Top {}", "{} Facts", "{} Things", "{} Ways"]

    def _score_title_ctr(self, title: str) -> float:
        """Score a title 0-100 for predicted CTR using proven formulas."""
        score = 30.0  # base

        # Power words boost (+5 each, max +15)
        pw_count = sum(1 for w in self.CTR_POWER_WORDS if w.lower() in title.lower())
        score += min(pw_count * 5, 15)

        # Numbers in title (+10)
        if re.search(r'\d+', title):
            score += 10

        # Brackets/prefix markers (+8)
        if any(b in title for b in ["|", ":", " - ", " — "]):
            score += 8

        # Length sweet spot: 40-60 chars (+10)
        if 40 <= len(title) <= 60:
            score += 10
        elif len(title) > 80:
            score -= 5  # too long, gets truncated

        # Emotional trigger words (+7)
        emotion_words = ["shocking", "surprising", "secret", "truth", "real",
                         "biggest", "worst", "best", "first", "only"]
        if any(w in title.lower() for w in emotion_words):
            score += 7

        # Question format (+5)
        if title.endswith("?"):
            score += 5

        # Curiosity gap (numbers + colon/pipe pattern) (+8)
        if re.search(r'\d+\s*[|:-]', title):
            score += 8

        return min(score, 100.0)

    def _rank_title_variants(self, variants: list) -> list:
        """Rank title variants by predicted CTR score, return sorted desc."""
        scored = [(v, self._score_title_ctr(v.get("title", ""))) for v in variants]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    # ─── Sentiment / Emotional Score Analysis (A1.5) ───
    SENTIMENT_POSITIVE = [
        "good", "great", "best", "win", "success", "growth", "improve",
        "help", "support", "benefit", "progress", "achieve", "celebrate",
        "happy", "positive", "excellent", "amazing", "wonderful", "hope",
    ]
    SENTIMENT_NEGATIVE = [
        "bad", "worst", "fail", "loss", "crisis", "problem", "issue",
        "danger", "risk", "threat", "attack", "death", "crash", "scam",
        "fraud", "corruption", "disaster", "tragedy", "urgent", "alert",
    ]

    def _analyze_sentiment(self, title: str, description: str = "") -> dict:
        """Analyze emotional sentiment of content. Returns score and label."""
        text = f"{title} {description}".lower()
        pos = sum(1 for w in self.SENTIMENT_POSITIVE if w in text)
        neg = sum(1 for w in self.SENTIMENT_NEGATIVE if w in text)
        total = pos + neg
        if total == 0:
            return {"score": 0.0, "label": "neutral", "click_emotion": "curiosity"}
        ratio = (pos - neg) / total
        if ratio > 0.3:
            label = "positive"
            click_emotion = "aspiration"
        elif ratio < -0.3:
            label = "negative"
            click_emotion = "urgency_fear"
        else:
            label = "mixed"
            click_emotion = "curiosity"
        return {"score": ratio, "label": label, "click_emotion": click_emotion}

    # ─── Search Volume Keyword Integration (A1.6) ───
    HIGH_SEARCH_KEYWORDS = {
        "telugu news": 9500, "andhra pradesh news": 7200,
        "telangana news": 6800, "h1b visa 2026": 5400,
        "greencard news": 4200, "visa update": 3800,
        "nri news": 3200, "indian immigration": 2900,
        "telugu breaking news": 2500, "visakhapatnam news": 2100,
        "vijayawada news": 1800, "hyderabad latest news": 3500,
        "amaravati news": 1500, "tirupati news": 1400,
    }

    def _inject_search_keywords(self, title: str, topic_context: str) -> str:
        """Inject high-search-volume keywords into title for discoverability."""
        title_lower = title.lower()
        # Find the best keyword not already in title
        candidates = []
        for kw, volume in self.HIGH_SEARCH_KEYWORDS.items():
            if kw not in title_lower:
                candidates.append((kw, volume))
        if not candidates:
            return title
        candidates.sort(key=lambda x: x[1], reverse=True)
        best_kw = candidates[0][0]
        # Append via pipe separator if space allows
        candidate = f"{title} | {best_kw.title()}"
        if len(candidate) <= 100:
            return candidate
        return title

    # ─── Enhanced Title Variant Builder (A1.4, C1.6) ───
    # ─── YouTube Studio Title SEO Rules (v84.1) ───
    # Rule 1: LOCALIZE — always tie national news to Telangana/Andhra Pradesh/districts
    # Rule 2: QUESTION FORMAT — for alliances/coalitions/political restructuring,
    #         prefer "Will [EVENT] Change [LOCAL] Politics?" to drive curiosity clicks
    # Rule 3: EMOTIONAL HOOK PREFIX — for high-impact topics, prepend hooks like
    #         "BIG MOVE:", "EXPLAINED:", "BREAKING:" based on topic type
    # Rule 4: SPECIFICITY — replace vague terms ("region", "state") with specific ones
    #         ("Telangana districts", "Andhra villages", "Hyderabad")
    _TITLE_LOCALIZATION_TERMS = [
        "Telangana", "Andhra Pradesh", "Telangana districts",
        "Andhra villages", "Hyderabad", "Amaravati",
    ]
    _TITLE_HOOK_PREFIXES = {
        "coalition": "BIG MOVE:",
        "alliance": "BIG MOVE:",
        "restructuring": "BIG MOVE:",
        "breaking": "BREAKING:",
        "urgent": "BREAKING:",
        "death": "BREAKING:",
        "attack": "BREAKING:",
        "explainer": "EXPLAINED:",
        "analysis": "EXPLAINED:",
        "why": "EXPLAINED:",
        "how": "EXPLAINED:",
    }
    _TITLE_VAGUE_TERMS = {
        "region": "Telangana",
        "state": "Telangana",
        "area": "Telangana districts",
        "local area": "Telangana districts",
        "our state": "Telangana",
        "our region": "Telangana",
        "the state": "Telangana",
        "the region": "Telangana",
    }

    def _apply_title_seo_rules(self, title: str, topic_context: str = "") -> str:
        """Apply YouTube Studio title SEO rules to refine a title."""
        refined = title.strip()

        # Rule 4: Replace vague terms with specific ones
        for vague, specific in self._TITLE_VAGUE_TERMS.items():
            if vague.lower() in refined.lower() and specific.lower() not in refined.lower():
                refined = re.sub(re.escape(vague), specific, refined, flags=re.IGNORECASE)
                break  # Only replace first match to avoid over-correction

        return refined

    def _build_title_variants(self, title: str, segment_type: str,
                               topic_context: str = "") -> list:
        """Generates distinct YouTube title variants with CTR-optimized formulas.

        v82.5: Titles must be SPECIFIC — include names, places, numbers.
        Generic templates like "BREAKING: {title}" are removed.
        Each variant must have a distinct angle/focus.
        v84.1: YouTube Studio SEO rules — localize, question format, hook prefixes, specificity.
        """
        import datetime
        year = datetime.datetime.now().year
        clean_title = title.strip()

        # Extract key entities from title for more specific variants
        words = clean_title.split()
        # Find proper nouns (capitalized words that aren't common skip words)
        skip = {"the","and","for","are","but","not","you","all","can","had","her","was","one",
                "our","out","new","now","how","its","may","get","has","him","his","who","did",
                "own","say","she","too","use","with","this","will","your","from","they","been",
                "have","what","when","them","then","come","could","each","make","than","call",
                "breaking","urgent","news","update","latest","today","just","in","on","at","to",
                "of","by","as","is","it","be","or","an","if","so","no","up","go","do","he","we",
                "telugu","india","andhra","telangana","ap","explained","analysis","simple",
                "full","complete","key","facts","main","important","what","why","about"}
        entities = [w for w in words if len(w) > 2 and w[0].isupper() and w.lower() not in skip]
        entity_str = ' '.join(entities[:3]) if entities else clean_title[:50]

        # ── v84.1: Detect topic type for hook prefix and question format ──
        context_lower = f"{clean_title} {topic_context}".lower()
        # Detect if this is a coalition/alliance/political restructuring topic
        is_coalition_topic = any(w in context_lower for w in [
            "alliance", "coalition", "bloc", "janbandhan", "unite", "united",
            "join", "front", "combine", "merge", "parties"
        ])
        # Detect applicable hook prefix
        hook_prefix = ""
        for trigger, prefix in self._TITLE_HOOK_PREFIXES.items():
            if trigger in context_lower:
                hook_prefix = prefix
                break
        # Determine local reference for this topic
        local_ref = ""
        if "telangana" in context_lower or "hyderabad" in context_lower:
            local_ref = "Telangana"
        elif "andhra" in context_lower or "amaravati" in context_lower or "vijayawada" in context_lower or "vizag" in context_lower or "visakhapatnam" in context_lower:
            local_ref = "Andhra Pradesh"
        else:
            local_ref = "Telangana"  # Default for ViralDNA's core audience

        if segment_type == "main":
            raw = [
                {
                    # Variant 1: Localized with hook prefix (YouTube Studio Option 2 style)
                    "title": f"{hook_prefix + ' ' if hook_prefix else ''}{entity_str[:45]} — What It Means for {local_ref}".strip(),
                    "description": f"Full report on {clean_title}. TheViralDNA brings you the complete story from our homeland."
                },
            ]

            # Variant 2: Question format for coalition/alliance topics (YouTube Studio Option 1)
            if is_coalition_topic and local_ref:
                raw.append({
                    "title": f"Will {entity_str[:40]} Change {local_ref} Politics?",
                    "description": f"Understanding how {clean_title} could reshape the political landscape in {local_ref}."
                })
            else:
                raw.append({
                    "title": f"{entity_str[:50]} — What Happened & What's Next | {year}",
                    "description": f"Understanding {clean_title} and what comes next for Telugu states."
                })

            # Variant 3: Specific local impact (YouTube Studio Option 4 style)
            raw.append({
                "title": f"{clean_title[:55]} | {local_ref} News {year}",
                "description": f"Latest on {clean_title}. Stay informed with TheViralDNA."
            })

        elif segment_type == "short_1":
            raw = [
                {
                    "title": f"{entity_str[:45]} — Key Facts You Need to Know",
                    "description": f"Quick facts on {clean_title}. Watch the full report on TheViralDNA."
                },
                {
                    "title": f"What {entity_str[:40]} Means for Telugu Families",
                    "description": f"How {clean_title} impacts families in Andhra Pradesh and Telangana."
                },
                {
                    "title": f"{entity_str[:50]} — The Full Story in 60 Seconds",
                    "description": f"Everything you need to know about {clean_title} — fast."
                },
            ]
        elif segment_type == "short_2":
            raw = [
                {
                    "title": f"Why {entity_str[:45]} Is Making Headlines",
                    "description": f"Breaking down {clean_title} and why it matters to Telugu people."
                },
                {
                    "title": f"{entity_str[:45]} — What You Need to Know",
                    "description": f"Simple explanation of {clean_title} and its real-world impact."
                },
                {
                    "title": f"{entity_str[:40]} — Impact on AP & Telangana",
                    "description": f"Understanding the real impact of {clean_title} on our communities."
                },
            ]
        else:  # short_3 — NRI-targeted
            raw = [
                {
                    "title": f"Telugu People Abroad: {entity_str[:40]} Update",
                    "description": f"If you are watching from abroad, here is what you need to know about {clean_title}."
                },
                {
                    "title": f"{entity_str[:45]} — Share With Family Back Home",
                    "description": f"Important update about {clean_title}. Share this with your family in Telugu states."
                },
                {
                    "title": f"From USA/UK: {entity_str[:40]} — What's Happening",
                    "description": f"Stay connected to your homeland. Here is the latest on {clean_title}."
                },
            ]

        # ── v84.1: Apply SEO rule 4 (specificity) to all variants ──
        for variant in raw:
            variant["title"] = self._apply_title_seo_rules(variant["title"], topic_context)

        # Inject search keywords into top-ranked title variant
        if raw and len(raw) > 0:
            raw[0] = {
                "title": self._inject_search_keywords(raw[0]["title"], topic_context),
                "description": raw[0]["description"]
            }

        # A1.7: Append bilingual title variants (Telugu context words)
        bilingual = self._add_bilingual_title_variants(clean_title, topic_context)
        if bilingual:
            raw.extend(bilingual)

        return raw

    def _wrap_segment(self, script_text: str, title: str, segment_type: str,
                      topic_context: str = "") -> dict:
        """Wraps a plain script text into the {script, title_variants} schema."""
        return {
            "script": script_text,
            "title_variants": self._build_title_variants(title, segment_type, topic_context),
            # CTR analysis metadata — consumed by ctr_optimizer agent
            "ctr_analysis": {
                "title_scores": [
                    {"title": v["title"], "score": self._score_title_ctr(v["title"])}
                    for v in self._build_title_variants(title, segment_type, topic_context)
                ],
                "sentiment": self._analyze_sentiment(title),
                "best_variant_idx": 0,  # default, ctr_optimizer may override
            }
        }

    # ─── Retention-Optimized Script Structure (B2.6) ───
    def _build_retention_script(self, title: str, desc: str,
                                 segments_config: dict) -> dict:
        """
        Build retention-optimized 1+3 script package with:
        - Hook-first structure (first 15 seconds)
        - Open loops and callbacks
        - End-of-video CTA (subscribe before end)
        """
        main_script = segments_config.get("main", self._build_main_script(title, desc))
        short_1 = segments_config.get("short_1", self._build_short_1(title))
        short_2 = segments_config.get("short_2", self._build_short_2(title))
        short_3 = segments_config.get("short_3", self._build_short_3(title))

        return {
            "main": main_script,
            "short_1": short_1,
            "short_2": short_2,
            "short_3": short_3,
        }

    def _build_welcome_back_hook(self, title: str) -> str:
        """
        D4.6: Welcome-back hook for returning viewers.
        A warm, personalized opening line that acknowledges repeat viewers
        and makes them feel recognized. Used as a variant opening in the
        main script template.
        Targets: viewers watching 2+ videos in a session.
        CT avg increase for welcome hooks: ~8-12 seconds additional retention.
        """
        hook_variants = [
            # Variant A: Direct acknowledgment (warm, personal)
            (
                f"Welcome back to ViralDNA. Great to see you again. "
                f"Today we have something important about {title} that you need to know."
            ),
            # Variant B: Community reinforcement
            (
                f"One of our regular viewers just asked about {title}. "
                f"We knew we had to cover it right away. Thanks for being part of the ViralDNA family."
            ),
            # Variant C: NRI connection (identity-based)
            (
                f"Watching from the US, UK, or Canada? Welcome back. "
                f"Staying connected to our homeland is what ViralDNA is all about. "
                f"Today's update about {title} is one you will want to share with family."
            ),
        ]
        # Select based on title hash for consistency per topic
        idx = hash(title) % len(hook_variants)
        return hook_variants[idx if idx >= 0 else 0]

    def _build_main_script(self, title: str, desc: str) -> str:
        """Build main video script with viral YouTube hook-first structure.

        v84.2: YouTube Studio feedback — conversational tone, hook-first,
        'you/your' language, analogy, engagement question CTA.
        """
        # Impact-first hook: start with what changes for the viewer, not with "X announced"
        return (
            f"{title} — and it could change everything for your district. "
            f"Here is what you need to know. "
            f"According to reports, {desc}. "
            f"If you live in Telangana or Andhra Pradesh, this isn't just national news — "
            f"it's a local event that could affect your daily life. "
            f"Local leaders and community members are already discussing what this means "
            f"for common families, workers, and businesses in our region. "
            f"The big question: will this actually help people on the ground, "
            f"or is it just political promises? "
            f"We will keep watching closely and bring you honest, simple updates. "
            f"What do you think — will this make a real difference in your area? "
            f"Tell me in the comments below. And if you want to stay connected to your homeland, "
            f"hit subscribe — ViralDNA is here to keep you informed."
        )

    def _build_short_1(self, title: str) -> str:
        """Short #1: Viral hook format — impact-first, curiosity gap, 'you' language.

        v84.2: YouTube Studio feedback — no formal intros, start with conflict/benefit.
        """
        return (
            f"Here is something that could directly affect your family in Telangana. "
            f"{title} — and the big question is: will this actually reach people like you? "
            f"Watch the full breakdown on ViralDNA now. Hit subscribe so you never miss an update."
        )

    def _build_short_2(self, title: str) -> str:
        """Short #2: Conversational explanation + community angle.

        v84.2: YouTube Studio feedback — simple, relatable, question-driven.
        """
        return (
            f"What does {title} really mean for common families in Andhra and Telangana? "
            f"It's not just politics — it could change things in your daily life. "
            f"Do you think this will help? Tell me in the comments. Follow ViralDNA for more."
        )

    def _build_short_3(self, title: str) -> str:
        """Short #3: NRI direct CTA — personal, emotional, action-driven.

        v84.2: YouTube Studio feedback — direct 'you' language, emotional hook.
        """
        return (
            f"If you are watching from the US, UK, or Canada, this is about your home. "
            f"{title} is happening right now in our districts. "
            f"Share this with your family — they need to know. "
            f"Subscribe to ViralDNA and stay connected to your roots."
        )

    def run(self, topic: dict, producer_brief: str = "") -> ScriptPayload:
        title = topic.get("title", "Homeland News").strip()
        desc = topic.get("description", "A major development has occurred in our regional districts.").strip()
        context = topic.get("rag_context", "").strip()

        # Sentiment analysis for upload metadata / publishing decisions
        sentiment = self._analyze_sentiment(title, desc)
        topic_context = f"{title} {desc} {context}"

        sections = None

        # Analyze sentiment for publishing insights
        print(f"    Sentiment Analysis: {sentiment['label']} (score: {sentiment['score']:.2f}, "
              f"click emotion: {sentiment['click_emotion']})")

        # Try dynamic Gemini API structured generation first (Dynamic Scripting)
        if self.engine:
            try:
                print(f"    Script Generator: Attempting dynamic synthesis via Gemini API...")

                # Build RAG feedback section if available
                rag_section = ""
                if producer_brief and "No performance data" not in producer_brief:
                    rag_section = (
                        f"\n📊 CHANNEL PERFORMANCE FEEDBACK (from previous videos):\n"
                        f"{producer_brief}\n"
                        f"Use the insights above to guide your writing. If certain topics or angles "
                        f"are noted as high-performing, apply similar framing to this script. "
                        f"If low-performing patterns are noted, avoid them.\n"
                    )

                # Extract state/region from context for explicit disambiguation
                state_hints = []
                context_lower = f"{title} {desc} {context}".lower()
                if "telangana" in context_lower or "hyderabad" in context_lower or "revanth" in context_lower or "ktr" in context_lower or "chandrababu" not in context_lower and "tdp" in context_lower:
                    state_hints.append("Telangana")
                if "andhra pradesh" in context_lower or "andhra" in context_lower or "amaravati" in context_lower or "vijayawada" in context_lower or "vizag" in context_lower or "visakhapatnam" in context_lower:
                    state_hints.append("Andhra Pradesh")
                if "tamil nadu" in context_lower or "chennai" in context_lower:
                    state_hints.append("Tamil Nadu")
                if "karnataka" in context_lower or "bangalore" in context_lower or "bengaluru" in context_lower:
                    state_hints.append("Karnataka")
                if "kerala" in context_lower or "kochi" in context_lower or "thiruvananthapuram" in context_lower:
                    state_hints.append("Kerala")
                state_hint_str = ", ".join(state_hints) if state_hints else "the relevant Telugu state"

                prompt = (
                    f"You are the Lead Writer for ViralDNA, a YouTube news channel for the Telugu community worldwide.\n"
                    f"Write an engaging, story-driven news package (1 Main Video Script + 3 Short Videos) for the following news item:\n\n"
                    f"Headline/Title: {title}\n"
                    f"Description: {desc}\n"
                    f"Context: {context}\n"
                    f"{rag_section}\n"
                    f"CRITICAL COMPLIANCE RULES:\n"
                    f"0. ZERO HALLUCINATION: You may ONLY use facts explicitly stated in the Headline, Description, and Context above. Do NOT invent biographical details, timelines, quotes, motivations, or background information not present in the source text. If the source doesn't say how long someone lived somewhere, don't say it. If the source doesn't quote someone, don't invent a quote. If the source doesn't state a reason or motivation, don't speculate. When in doubt, use a generic phrase like 'according to reports' rather than inventing specifics.\n"
                    f"1. Tone and Vocabulary: Use simple, clear, conversational English — like you are explaining news to a friend. Avoid ALL academic/formal words: never use 'crystallization', 'discourse', 'dynamics', 'significant development', 'reshaping', 'immense potential', 'collaboration', 'implications', 'operational framework'. Instead use: 'teaming up', 'big change', 'what people are talking about', 'could flip the vote', 'real impact on your street'.\n"
                    f"2. Language: Write in 100% pure English. Do NOT mix any Telugu phrases, words, or regional jargon into the script because the text-to-speech voice is unable to pronounce mixed-language words properly.\n"
                    f"3. STATE ACCURACY: The news item concerns {state_hint_str}. You MUST mention the state name ({state_hint_str}) at least once in the main script. Do NOT write 'Andhra Pradesh' for a Telangana story or vice versa. DO NOT mention the other Telugu state unless the source text explicitly mentions both. The state name MUST appear explicitly — do NOT replace it with vague terms like 'our state' or 'our homeland'.\n"
                    f"4. Punctuation: Ensure excellent, standard punctuation with clear periods (.), commas (,), and question marks (?). These are critical cues for our speech generator to take natural pauses and not rush.\n"
                    f"5. Length requirements:\n"
                    f"   - 'main': A story-driven news report. It MUST be at least 150 words and at most 250 words to maintain our pacing.\n"
                    f"   - 'short_1': High-impact 15-20s highlights (approx 35-45 words). Start with a HOOK that creates curiosity.\n"
                    f"   - 'short_2': Simple summary of what this means for common people (approx 35-45 words).\n"
                    f"   - 'short_3': Direct, simple Call-to-Action for families watching from abroad (approx 35-45 words).\n"
                    f"6. STORYTELLING REQUIREMENTS (CRITICAL - follow exactly):\n"
                    f"   - The main script MUST read like a YouTube creator explaining news, NOT a TV news broadcast or Wikipedia summary.\n"
                    f"   - HOOK FIRST: Start with the IMPACT or CONFLICT — NOT with 'Minister X announced' or 'The Congress party said today'. Start with what changes for the VIEWER. Example: '23 parties just joined forces and it could change the political map of Telangana' instead of 'Congress announced today that 23 parties have confirmed participation.'\n"
                    f"   - Use 'YOU' and 'YOUR' language to make it personal. 'If you live in Hyderabad or Warangal, this isn't just national news — it's a local earthquake.'\n"
                    f"   - Include a RELATABLE ANALOGY for complex political events. Example: 'Think of it like 23 local sports teams forming one giant Super Team to take on the champion.' Or: 'Imagine a family gathering where suddenly half the members walk out.' Make abstract politics feel like everyday life.\n"
                    f"   - Include the WHO, WHAT, WHEN, WHERE, WHY — but ONLY as stated in the source text. Do NOT fill in gaps with assumptions.\n"
                    f"   - Use ACTIVE voice and VIVID language. Instead of 'X was accused by Y', write 'Y accused X of...'\n"
                    f"   - End with a SPECIFIC QUESTION to the audience that drives comments. NOT 'Stay tuned to ViralDNA.' Instead: 'Do you think this 23-party deal will actually work in Telangana, or is it too many voices? Tell me in the comments.' This is critical for YouTube algorithm engagement.\n"
                    f"   - AVOID generic filler phrases: 'This development has sent ripples', 'sparking intense debate', 'widely reported', 'political analysts alike', 'significant development', 'reshaping electoral dynamics', 'crystallization of alliances', 'immense potential for collaboration'. These are DEAD WORDS that make content sound like a press release.\n"
                    f"   - AVOID passive constructions: 'was announced', 'has been reported', 'is being discussed'. Use active voice instead.\n"
                    f"7. RETENTION HOOKS: For main video, the first sentence MUST be the hook — the most shocking or relevant piece of info. Never start with a formal introduction. Mention 'subscribe' or 'follow ViralDNA' near the END of the main script (not the beginning) to keep viewers watching.\n"
                    f"8. Format: Avoid markdown, bold text, brackets, URLs, or non-pronounceable tags. Keep the text clean, natural, and speakable.\n"
                    f"\nIMPORTANT: The system message defines the exact JSON schema. Follow it strictly. Each key (main, short_1, short_2, short_3) must return an object with 'script' (string) and 'title_variants' (array of 3 objects with 'title' and 'description' keys).\n"
                )

                response_dict = self.engine.ask_structured(prompt)

                # Validate that we received the correct nested dictionary structure
                if response_dict and all(k in response_dict for k in ["main", "short_1", "short_2", "short_3"]):
                    # Validate nested structure: each must have 'script' and 'title_variants'
                    valid_structure = True
                    key_order = ["main", "short_1", "short_2", "short_3"]
                    for key in key_order:
                        if not isinstance(response_dict[key], dict):
                            valid_structure = False
                            print(f"    ⚠️ Gemini response for '{key}' is not a dict. Got: {type(response_dict[key]).__name__}")
                            break
                        if "script" not in response_dict[key] or "title_variants" not in response_dict[key]:
                            valid_structure = False
                            print(f"    ⚠️ Gemini response for '{key}' missing 'script' or 'title_variants' keys.")
                            break
                        if not isinstance(response_dict[key]["title_variants"], list) or len(response_dict[key]["title_variants"]) < 1:
                            valid_structure = False
                            print(f"    ⚠️ Gemini response for '{key}' has invalid title_variants.")
                            break

                    if valid_structure:
                        main_text = response_dict["main"]["script"]
                        main_len = len(main_text.split())
                        if main_len >= 100:
                            # Score and rank CTR for each segment's titles
                            for key in key_order:
                                variants = response_dict[key]["title_variants"]
                                scored = self._rank_title_variants(variants)
                                response_dict[key]["_ctr_best_idx"] = 0  # highest scored first
                                response_dict[key]["_ctr_scores"] = [
                                    {"title": s[0]["title"], "score": s[1]} for s in scored
                                ]
                                # Reorder variants: best CTR first
                                reordered = [s[0] for s in scored]
                                response_dict[key]["title_variants"] = reordered

                            sections = {
                                "main": response_dict["main"],
                                "short_1": response_dict["short_1"],
                                "short_2": response_dict["short_2"],
                                "short_3": response_dict["short_3"],
                            }

                            # Print CTR summary
                            for key in key_order:
                                scores = response_dict[key].get("_ctr_scores", [])
                                if scores:
                                    print(f"    [{key}] Best title (CTR {scores[0]['score']:.0f}/100): "
                                          f"{scores[0]['title'][:60]}...")

                            print(f"    ✅ Dynamic Script Synthesis Successful! (Main: {main_len} words)")
                        else:
                            print(f"    ⚠️ Gemini script too short ({main_len} words). Triggering fallback...")
                    else:
                        print("    ⚠️ Invalid nested structure in Gemini response. Triggering fallback...")
                else:
                    print("    ⚠️ Invalid keys in Gemini response. Triggering fallback...")
            except Exception as e:
                print(f"    ⚠️ Dynamic synthesis failed: {e}. Triggering fallback...")

        # Heuristic Local Template Fallback (If API fails, bypassed, or returns invalid schemas)
        if not sections:
            print(f"    Script Generator: Locally synthesizing heuristic 1+3 package for '{title[:30]}'...")

            fallback_scripts = self._build_retention_script(title, desc, {})
            sections = {
                "main": self._wrap_segment(fallback_scripts["main"], title, "main", topic_context),
                "short_1": self._wrap_segment(fallback_scripts["short_1"], title, "short_1", topic_context),
                "short_2": self._wrap_segment(fallback_scripts["short_2"], title, "short_2", topic_context),
                "short_3": self._wrap_segment(fallback_scripts["short_3"], title, "short_3", topic_context),
            }

        # Attach sentiment metadata to the payload
        if sections:
            sections["_sentiment_meta"] = sentiment

        # ─── Enforce Minimum Short Word Counts ───
        # Gemini may return shorts shorter than the 35-45 word target.
        # If any short is below 15 words, pad it with a topic-relevant
        # extension so the voice synthesis stage doesn't silently skip it.
        if sections:
            _MIN_SHORT_WORDS = 15
            for _sk in ["short_1", "short_2", "short_3"]:
                _s = sections.get(_sk, {})
                if isinstance(_s, dict):
                    _script = _s.get("script", "")
                    _wc = len(_script.split())
                    if _wc < _MIN_SHORT_WORDS:
                        _pad = (
                            f" Stay connected with ViralDNA for the latest updates. "
                            f"Like, subscribe, and share this with your family and friends "
                            f"who care about what is happening back home."
                        )
                        _s["script"] = _script + _pad
                        _new_wc = len(_s["script"].split())
                        print(f"    🔧 Short pad: {_sk} padded from {_wc} to {_new_wc} words")

        # ─── Humanizer Pass: Strip AI-isms for natural voice ───
        if sections:
            try:
                _humanizer = HumanizerEngine()
                sections, humanizer_stats = _humanizer.humanize_package(sections)
                _total_fixed = sum(
                    s.get('total_changes', 0)
                    for s in humanizer_stats.values()
                    if isinstance(s, dict) and 'total_changes' in s
                )
                if _total_fixed > 0:
                    print(f"    🧬 Humanizer: Stripped {_total_fixed} AI-ism(s) across script package.")
                    for _seg, _st in humanizer_stats.items():
                        if isinstance(_st, dict) and _st.get('total_changes', 0) > 0:
                            print(f"       [{_seg}] {_st['total_changes']} fixes "
                                  f"({_st.get('original_word_count',0)} -> {_st.get('cleaned_word_count',0)} words)")
            except Exception as _e:
                print(f"    ⚠️ Humanizer pass failed (non-fatal): {_e}. Proceeding with original scripts.")

        return ScriptPayload(sections)
