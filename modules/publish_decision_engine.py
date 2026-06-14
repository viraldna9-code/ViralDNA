# VERSION: 10.0
# MODULE: publish_decision_engine.py
# PURPOSE: Analyzes topic content and decides WHAT to publish.
#
# Decision matrix:
#   - Main video only: Deep/political/policy topics that need full context
#   - Shorts only: Quick-hit trending/entertainment/sports topics
#   - Main + 1 Short: Breaking news with one strong angle
#   - Main + 2 Shorts: Moderate depth news
#   - Main + 2 Shorts (default): Standard comprehensive coverage
#
# The decision is based on:
#   1. Content category (politics, economics, entertainment, sports, health, etc.)
#   2. Source diversity (how many independent sources cover it)
#   3. Content depth signals (word count in source articles)
#   4. Spike level (breaking vs. developing vs. background)
#   5. Keyword signals (budget, policy, etc. = deep; movie, match, etc. = quick)
#
# VERSION HISTORY:
#   v10.0 — Initial module.

import re
from enum import Enum
from dataclasses import dataclass, field
from typing import List


class ContentCategory(Enum):
    POLITICS = "politics"
    ECONOMICS = "economics"
    POLICY = "policy"
    ENTERTAINMENT = "entertainment"
    SPORTS = "sports"
    HEALTH = "health"
    TECHNOLOGY = "technology"
    CRIME = "crime"
    DISASTER = "disaster"
    GENERAL = "general"


class spikeLevel(Enum):
    BREAKING = "breaking"
    DEVELOPING = "developing"
    BACKGROUND = "background"


@dataclass
class PublishDecision:
    """What to produce and upload for this topic."""
    produce_main: bool = True
    num_shorts: int = 2
    reason: str = ""

    def summary(self) -> str:
        parts = []
        if self.produce_main:
            parts.append("1 Main Video")
        if self.num_shorts > 0:
            parts.append(f"{self.num_shorts} Short(s)")
        return " + ".join(parts) if parts else "Nothing"


# Keywords that signal deep/long-form content (favor main video)
DEEP_CONTENT_KEYWORDS = [
    "budget", "policy", "reform", "legislation", "act", "amendment",
    "election", "results", "manifesto", "parliament", "assembly",
    "supreme court", "high court", "verdict", "judgment",
    "economic survey", "gdp", "inflation", "fiscal", "monetary",
    "infrastructure", "development project", "water sharing", "dispute",
    "medical", "research", "study finds", "clinical", "treatment",
    "interview", "exclusive", "analysis", "opinion", "editorial",
]

# Keywords that signal quick-hit content (favor shorts only)
QUICK_CONTENT_KEYWORDS = [
    "movie", "film", "trailer", "box office", "album", "song",
    "match", "score", "wicket", "goal", "win", "defeat",
    "celebrity", "actor", "actress", "wedding", "birthday",
    "viral", "trending", "reel", "meme", "challenge",
    "weather alert", "rain alert", "flood warning", "cyclone",
    "accident", "fire", "blast", "crash",
    "update", "just in", "breaking",
]

# Category → default decision mapping
CATEGORY_DEFAULTS = {
    ContentCategory.POLITICS: {"produce_main": True, "num_shorts": 2},
    ContentCategory.ECONOMICS: {"produce_main": True, "num_shorts": 2},
    ContentCategory.POLICY: {"produce_main": True, "num_shorts": 2},
    ContentCategory.ENTERTAINMENT: {"produce_main": False, "num_shorts": 2},
    ContentCategory.SPORTS: {"produce_main": False, "num_shorts": 2},
    ContentCategory.HEALTH: {"produce_main": True, "num_shorts": 2},
    ContentCategory.TECHNOLOGY: {"produce_main": True, "num_shorts": 2},
    ContentCategory.CRIME: {"produce_main": True, "num_shorts": 1},
    ContentCategory.DISASTER: {"produce_main": True, "num_shorts": 2},
    ContentCategory.GENERAL: {"produce_main": True, "num_shorts": 2},
}


def _classify_category(title: str, tags: str = "") -> ContentCategory:
    """Classify the topic into a content category based on title and tags."""
    text = f"{title} {tags}".lower()

    # Order matters: first match wins. Put specific/high-value categories
    # BEFORE generic ones to avoid misclassification.
    # e.g. "visa" topics must match POLICY before SPORTS or ENTERTAINMENT.
    patterns = {
        ContentCategory.DISASTER: [r'cyclone|flood|earthquake|tsunami|landslide|drought|cloudburst'],
        ContentCategory.CRIME:     [r'murder|robbery|arrested|fraud|scam|theft|rape|assault|kidnapp|\baccident\b|killed|died'],
        ContentCategory.POLICY:    [r'\bpolicy\b|\breform\b|\bscheme\b|\bwelfare\b|\bsubsidy\b|\bpension\b|\bhousing\b|\bvisa\b|\bimmigration\b|visa restriction'],
        ContentCategory.POLITICS:  [r'\belection\b|\bminister\b|\bcm\b|\bmla\b|\bmp\b|\bparty\b|\bbjp\b|\btdp\b|\bysrcp\b|\bcongress\b|\bvote\b|\bcampaign\b|\brally\b|\btrump\b|\bpresident\b|\bgovernment\b'],
        ContentCategory.ECONOMICS: [r'\bbudget\b|\beconomy\b|\bgdp\b|\binflation\b|\bstock\b|\bmarket\b|\brupee\b|\btrade\b|\bexport\b|\bimport\b|\btax\b|\bgst\b|\bfiscal\b'],
        ContentCategory.HEALTH:    [r'\bhealth\b|\bhospital\b|\bdoctor\b|\bdisease\b|\bvaccine\b|\bcovid\b|\bdengue\b|\bmalaria\b|\bmedical\b|\bpatient\b|\btreatment\b|\bebola\b|\bsurveillance\b|\boutbreak\b|\bepidemic\b|\bpandemic\b|\bvirus\b|\binfection\b'],
        ContentCategory.TECHNOLOGY:[r'\btech\b|\bai\b|\bapp\b|\bstartup\b|\bdigital\b|\binternet\b|\bphone\b|\bgadgets\b|\bsoftware\b|\bcyber\b'],
        ContentCategory.SPORTS:    [r'\bcricket\b|\bscore\b|\bipl\b|\bgoal\b|\bwicket\b|\bbasketball\b|\bfootball\b|\btennis\b|\bolympics\b|\bsports\b'],
        ContentCategory.ENTERTAINMENT: [r'\bmovie\b|\bfilm\b|\bactor\b|\bactress\b|\bcinema\b|box.?office|\btrailer\b|\bsong\b|\balbum\b|\bmusic\b|\bcelebrity\b|\bwedding\b'],
    }

    for category, regex_list in patterns.items():
        for pattern in regex_list:
            if re.search(pattern, text):
                return category

    return ContentCategory.GENERAL


def _detect_spike_level(topic: dict) -> spikeLevel:
    """Detect if this is breaking, developing, or background news."""
    title = topic.get("title", "").lower()

    breaking_signals = ["breaking", "just in", "alert", "urgent", "live", "happening now"]
    if any(s in title for s in breaking_signals):
        return spikeLevel.BREAKING

    # Check spike score if available
    spike_score = topic.get("spike_score", 0)
    if spike_score >= 70:
        return spikeLevel.BREAKING
    elif spike_score >= 40:
        return spikeLevel.DEVELOPING

    return spikeLevel.BACKGROUND


def _keyword_analysis(title: str, description: str = "") -> tuple:
    """Returns (deep_score, quick_score) based on keyword matches."""
    text = f"{title} {description}".lower()
    deep_score = sum(1 for kw in DEEP_CONTENT_KEYWORDS if kw in text)
    quick_score = sum(1 for kw in QUICK_CONTENT_KEYWORDS if kw in text)
    return deep_score, quick_score


def _source_diversity_score(topic: dict) -> int:
    """Score 0-3 based on how many independent sources cover this topic."""
    sources = topic.get("sources", [])
    if isinstance(sources, list):
        return min(len(sources), 3)
    return 1


def decide_publish_plan(topic: dict) -> PublishDecision:
    """
    Main decision function. Analyzes the topic and returns a PublishDecision.
    
    Logic flow:
    1. Classify content category → get default decision
    2. Adjust based on spike level (breaking → more content)
    3. Adjust based on keyword analysis (deep → main, quick → shorts)
    4. Adjust based on source diversity (more sources → more content)
    5. Bounds-check (0-3 shorts, main is bool)
    """
    title = topic.get("title", "")
    description = topic.get("description", "")
    tags = topic.get("tags", "")

    # Step 1: Category classification
    category = _classify_category(title, tags)
    defaults = CATEGORY_DEFAULTS.get(category, {"produce_main": True, "num_shorts": 3})
    decision = PublishDecision(
        produce_main=defaults["produce_main"],
        num_shorts=defaults["num_shorts"],
        reason=f"Category: {category.value}"
    )

    # Step 2: Spike level adjustment
    spike = _detect_spike_level(topic)
    if spike == spikeLevel.BREAKING:
        decision.produce_main = True
        decision.num_shorts = max(decision.num_shorts, 2)
        decision.reason += " | Breaking news → ensure main + shorts"
    elif spike == spikeLevel.BACKGROUND:
        # Floor: never go below 2 shorts regardless of spike level
        # (channel growth requires consistent short-form output)
        decision.num_shorts = max(2, min(decision.num_shorts, 2))
        decision.reason += " | Background → floor 2 shorts"

    # Step 3: Keyword analysis
    deep_score, quick_score = _keyword_analysis(title, description)
    if deep_score >= 2 and quick_score == 0:
        decision.produce_main = True
        decision.num_shorts = min(decision.num_shorts, 2)
        decision.reason += " | Deep content keywords → main focused"
    elif quick_score >= 2 and deep_score == 0:
        decision.produce_main = False
        decision.num_shorts = 3
        decision.reason += " | Quick-hit keywords → shorts only"

    # Step 4: Source diversity
    diversity = _source_diversity_score(topic)
    if diversity >= 3:
        decision.produce_main = True
        decision.num_shorts = max(decision.num_shorts, 2)
        decision.reason += " | High source diversity"
    elif diversity <= 1:
        # Floor: never go below 2 shorts for any news category
        # (channel growth requires consistent short-form output)
        if decision.num_shorts < 2:
            decision.num_shorts = 2
        decision.reason += " | Low source diversity (floor applied)"

    # Step 5: Bounds check
    decision.num_shorts = max(0, min(3, decision.num_shorts))

    return decision
