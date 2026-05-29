# VERSION: 52.0
# MODULE: trend_discovery.py
# PURPOSE: Multi-source discovery — RSS (8) + Google Trends (pytrends) + Reddit +
#          YouTube Trending + Inshorts + Wikipedia RAG fallback.
#          Broad relevance filter (not topic filter) — lets ALL Telugu-relevant
#          topics through. Scoring decides what's important, not this filter.

import feedparser
import requests
import re
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from data_flow_registry import NewsPayload

class TrendDiscovery:
    def __init__(self, config_instance):
        self.config = config_instance
        self.headers = {"User-Agent": "ViralDNABot/1.0 (contact@viraldna.com)"}
        self.ist = ZoneInfo("Asia/Kolkata")

        # --- TIER 1: RSS Sources (8 total) ---
        self.rss_sources = [
            # Existing (4)
            "https://www.thehindu.com/news/national/andhra-pradesh/feeder/default.rss",
            "https://timesofindia.indiatimes.com/rssfeeds/296589292.cms",  # AP Telugu
            "https://www.eenadu.net/rss/andhra-pradesh.xml",
            "https://news.google.com/rss/search?q=Andhra+Pradesh&hl=en-IN&gl=IN&ceid=IN:en",
            # Phase 1 Expansions (4)
            "https://www.rediff.com/rss/innews.xml",          # Rediff India news
            "https://feeds.feedburner.com/ndtvnews-top-stories",  # NDTV top
            "https://www.indiatoday.in/rss/1206514",         # India Today latest
            "https://www.thehindu.com/news/national/feeder/default.rss",  # The Hindu national (broader)
        ]

        # --- TIER 2: Diaspora-focused RSS ---
        self.diaspora_rss = [
            "https://www.siasat.com/rss/feed-324.xml",  # Siasat (Telugu-friendly)
            "https://news.google.com/rss/search?q=Telugu+diaspora+USA+immigration&hl=en&gl=US&ceid=US:en",
        ]

    # ================================================================
    #  SOURCE 1: RSS FEED POLLING (existing, extended)
    # ================================================================
    def _poll_rss_sources(self, source_list: list, max_per_feed: int = 3) -> list:
        topics = []
        for url in source_list:
            try:
                feed = feedparser.parse(url)
                if feed.entries:
                    for entry in feed.entries[:max_per_feed]:
                        title = entry.get("title", "")
                        if not title:
                            continue
                        desc = entry.get("summary", title)
                        link = entry.get("link", url)
                        context = self._fetch_rag_context(title)
                        payload = NewsPayload({
                            "title": title,
                            "description": desc,
                            "link": link,
                            "source": url,
                            "rag_context": context
                        })
                        topics.append(payload.to_dict())
            except Exception as e:
                print(f"    ⚠️ RSS failed: {url} | {e}")
        return topics

    # ================================================================
    #  SOURCE 2: Google Trends (B4.6: Deep Integration)
    # ================================================================
    def _fetch_google_trends(self) -> list:
        """
        B4.6: Deep Google Trends integration.
        Fetches: India daily trends, AP-specific related topics,
        diaspora keyword interest over time, US/UK trending for NRI audience.
        """
        topics = []
        try:
            from pytrends.request import TrendReq

            # ── Tier A: India trending searches (primary audience) ──
            pytrends = TrendReq(hl="en-IN", tz=330, timeout=(5, 10))
            trending = pytrends.trending_searches(pn="india")
            if trending is not None and len(trending) > 0:
                for keyword in trending.head(8)[0].tolist():
                    keyword = str(keyword).strip()
                    if self._is_relevant_to_diaspora(keyword):
                        context = self._fetch_rag_context(keyword)
                        payload = NewsPayload({
                            "title": keyword,
                            "description": "Trending topic in India",
                            "link": f"https://news.google.com/search?q={keyword.replace(' ', '+')}",
                            "source": "Google Trends (India Daily)",
                            "rag_context": context,
                            "trending_score": "high",
                        })
                        topics.append(payload.to_dict())

            # ── Tier B: AP-specific related topics ──
            pytrends.build_payload(
                ["Andhra Pradesh", "Telugu", "Amaravati", "Visakhapatnam"],
                cat=0, timeframe="now 7d", geo="IN"
            )
            related = pytrends.related_topics()
            for kw, df in related.items():
                if df is not None and len(df) > 0:
                    top = df[df["value"] > 50]
                    for _, row in top.head(3).iterrows():
                        title = row.get("topic_title", str(kw))
                        if title and title not in [t["title"] for t in topics]:
                            context = self._fetch_rag_context(title)
                            payload = NewsPayload({
                                "title": title,
                                "description": f"Related to {kw}",
                                "link": f"https://news.google.com/search?q={title.replace(' ', '+')}",
                                "source": f"Google Trends (Related: {kw})",
                                "rag_context": context,
                                "trending_score": "medium",
                            })
                            topics.append(payload.to_dict())

            # ── Tier C: Interest over time for diaspora keywords ──
            try:
                pytrends_diaspora = TrendReq(hl="en-US", tz=-300, timeout=(5, 10))
                diaspora_keywords = ["Telugu news", "Andhra Pradesh news", "Telangana updates"]
                pytrends_diaspora.build_payload(
                    diaspora_keywords[:2], cat=0, timeframe="today 3m", geo="US"
                )
                interest_df = pytrends_diaspora.interest_over_time()
                if interest_df is not None and len(interest_df) > 0:
                    # Find rising diaspora interest
                    for kw in diaspora_keywords[:2]:
                        if kw in interest_df.columns:
                            recent = interest_df[kw].tail(7).mean()
                            if recent > 30:  # 30+ average = rising interest
                                title = f"Rising interest: {kw} in US"
                                context = self._fetch_rag_context(kw)
                                payload = NewsPayload({
                                    "title": title,
                                    "description": f"Search interest for '{kw}' is rising in US (avg: {recent:.0f}/100)",
                                    "link": f"https://news.google.com/search?q={kw.replace(' ', '+')}",
                                    "source": "Google Trends (US Diaspora Interest)",
                                    "rag_context": context,
                                    "trending_score": "rising",
                                })
                                topics.append(payload.to_dict())
            except Exception:
                pass  # Diaspora trends best-effort

            # ── Tier D: US/UK trending for NRI audience ──
            try:
                pytrends_us = TrendReq(hl="en-US", tz=-300, timeout=(5, 10))
                us_trending = pytrends_us.trending_searches(pn="united_states")
                if us_trending is not None and len(us_trending) > 0:
                    # Keep any US trend that's relevant to India/Telugu audience
                    # — NOT just visa/immigration. Could be tech, culture, world events, etc.
                    for keyword in us_trending.head(15)[0].tolist():
                        keyword_str = str(keyword).strip()
                        keyword_lower = keyword_str.lower()
                        # Use the main relevance filter (broad) instead of narrow NRI keywords
                        if self._is_relevant_to_diaspora(keyword_str):
                            context = self._fetch_rag_context(keyword_str)
                            payload = NewsPayload({
                                "title": keyword_str,
                                "description": f"Trending in US: {keyword_str}",
                                "link": f"https://news.google.com/search?q={keyword_str.replace(' ', '+')}",
                                "source": "Google Trends (US NRI Interest)",
                                "rag_context": context,
                                "trending_score": "us_relevant",
                            })
                            topics.append(payload.to_dict())
            except Exception:
                pass  # US trends best-effort

        except Exception as e:
            print(f"    ⚠️ Google Trends failed: {e}")
        return topics

    # ================================================================
    #  SOURCE 3: Reddit JSON API (free, no auth needed)
    # ================================================================
    def _fetch_reddit_trends(self) -> list:
        """Scrape public Reddit JSON API for trending AP/diaspora topics."""
        topics = []
        subreddits = [
            "india", "AndhraPradesh", "tollywood", "telangana",
            "hyderabad", "cricket", "indiansports", "bollywood"
        ]
        for sub in subreddits:
            try:
                url = f"https://www.reddit.com/r/{sub}/hot.json?limit=5"
                resp = requests.get(url, headers={"User-Agent": "ViralDNABot/1.0"}, timeout=8)
                if resp.status_code == 200:
                    data = resp.json()
                    posts = data.get("data", {}).get("children", [])
                    for post in posts:
                        post_data = post.get("data", {})
                        title = post_data.get("title", "")
                        if title and self._is_relevant_to_diaspora(title):
                            context = self._fetch_rag_context(title)
                            payload = NewsPayload({
                                "title": title,
                                "description": post_data.get("selftext", title)[:200] or title,
                                "link": "https://reddit.com" + post_data.get("permalink", ""),
                                "source": f"Reddit r/{sub}",
                                "rag_context": context
                            })
                            topics.append(payload.to_dict())
            except Exception as e:
                print(f"    ⚠️ Reddit r/{sub} failed: {e}")
        return topics

    # ================================================================
    #  SOURCE 4: YouTube Trending (free scrape, India region)
    # ================================================================
    def _fetch_youtube_trends(self) -> list:
        """Scrape YouTube trending page for India news (free, no API key)."""
        topics = []
        try:
            url = "https://www.youtube.com/feed/trending?bp=6gQJRkVleHBsb3Jl"
            resp = requests.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept-Language": "en-US,en;q=0.9"
            }, timeout=10)
            if resp.status_code == 200:
                # Extract video titles from initial data JSON
                matches = re.findall(r'"title":\{"runs":\[\{"text":"([^"]+)"', resp.text)
                for title in matches[:10]:
                    title = title.replace("\\u0026", "&").replace("\\\"", '"')
                    if self._is_relevant_to_diaspora(title):
                        context = self._fetch_rag_context(title)
                        payload = NewsPayload({
                            "title": title,
                            "description": f"Trending on YouTube India: {title}",
                            "link": "https://www.youtube.com/feed/trending",
                            "source": "YouTube Trending (India)",
                            "rag_context": context
                        })
                        topics.append(payload.to_dict())
        except Exception as e:
            print(f"    ⚠️ YouTube trending scrape failed: {e}")
        return topics

    # ================================================================
    #  SOURCE 5: Inshorts (free scrape, India news in English)
    # ================================================================
    def _fetch_inshorts(self) -> list:
        """Scrape Inshorts for India/Andhra news (free, no API key)."""
        topics = []
        try:
            url = "https://inshorts.com/en/read"
            resp = requests.get(url, headers=self.headers, timeout=8)
            if resp.status_code == 200:
                # Extract headlines from embedded JSON-LD or inline data
                pattern = r'"headline":"([^"]+)"'
                headlines = re.findall(pattern, resp.text)
                for h in headlines[:12]:
                    if self._is_relevant_to_diaspora(h):
                        context = self._fetch_rag_context(h)
                        payload = NewsPayload({
                            "title": h,
                            "description": f"Inshorts trending: {h}",
                            "link": "https://inshorts.com/en/read",
                            "source": "Inshorts",
                            "rag_context": context
                        })
                        topics.append(payload.to_dict())
        except Exception as e:
            print(f"    ⚠️ Inshorts scrape failed: {e}")
        return topics

    # ================================================================
    #  RELEVANCE FILTER: Keep only AP/diaspora-related topics
    # ================================================================
    def _is_relevant_to_diaspora(self, text: str) -> bool:
        """Broad relevance filter: keep anything related to Indian/Telugu states news.
        
        This is NOT a topic filter — it should NOT exclude topics like cyclone,
        cricket, movies, crime, health, etc. It only excludes clearly irrelevant 
        content (e.g., purely European/Chinese/Latin American news with zero 
        India/Telugu connection).
        
        The TOPIC SELECTION is done by the scoring system in post_filter.py,
        not here. This filter just ensures we don't waste cycles on completely
        irrelevant foreign news.
        """
        text_lower = text.lower()
        # Broad India/Telugu relevance keywords
        relevance_keywords = [
            # Andhra Pradesh / Telangana geography
            "andhra", "telugu", "telangana", "amaravati", "vizag",
            "visakhapatnam", "tirupati", "kakinada", "guntur",
            "vijayawada", "nellore", "ongole", "kurnool", "anantapur",
            "east godavari", "west godavari", "prakasam", "srikakulam",
            "hyderabad", "warangal", "nalgonda", "karimnagar", "nizamabad",
            "adilabad", "medak", "rangareddy", "mahabubnagar",
            # Indian general (broad — keeps cricket, movies, politics, etc.)
            "india", "indian", "bjp", "congress", "modi", "rahul",
            "naidu", "jagan", "kcr", "chandrababu", "chandrababu naidu",
            "yeddi", "ysrcp", "tdp", "bjp", "rss", "pawan kalyan",
            "election", "lok sabha", "assembly", "chief minister",
            "minister", "parliament", "supreme court", "high court",
            "rss", "rss feed", "hindu", "muslim", "temple", "church",
            # Weather/natural disasters (Telugu states affected)
            "cyclone", "flood", "tsunami", "earthquake", "drought",
            "monsoon", "storm", "landslide", "heat wave", "cold wave",
            "rainfall", "rain", "dam", "reservoir", "river", "krishna",
            "godavari", "nagavali", "vamsadhara",
            # Telugu film industry
            "tollywood", "telugu cinema", "telugu film", "telugu movie",
            "telugu actor", "telugu actress", "telugu director",
            "mahesh babu", "prabhas", "allu arjun", "jr ntr", "ram charan",
            "ss rajamouli", "keerthy suresh", "samantha", "rashmika",
            "nagarjuna", "venkatesh", "chiranjeevi", "pawan kalyan",
            "telugu star", "telugu hero", "telugu heroine",
            # Cricket (massive in Telugu states)
            "cricket", "ipl", "world cup", "t20", "odi", "test match",
            "virat", "dhoni", "rohit", "sachin", "rahul", "surya",
            "team india", "bcci", "ipl team", "ipl match",
            # NRI / diaspora (location keywords — only match if combined with India/Telugu context
            # or if the text also matches another India keyword)
            "nri", "diaspora", "overseas",
            "usa", "us ", "america", "canada", "uk", "australia",
            "gulf", "dubai", "singapore", "malaysia",
            "silicon valley",
            # Immigration (relevant to Telugu NRIs)
            "immigration", "h1b", "visa", "greencard",
            # Telugu culture / society
            "telugu people", "telugu community", "telugu culture",
            "telugu tradition", "telugu festival", "telugu food",
            "telugu language", "telugu speaking", "andhra cuisine",
            "andhra culture", "telangana culture",
            # Major Indian cities/states (neighboring Telugu states)
            "chennai", "bangalore", "bengaluru", "tamil nadu", "karnataka",
            "maharashtra", "kerala", "goa", "odisha", "chhattisgarh",
            "mumbai", "delhi", "kolkata", "pune", "nagpur",
            # General news categories relevant to Telugu audience
            "crime", "police", "arrest", "murder", "theft", "fraud",
            "scam", "accident", "fire", "protest", "strike", "bandh",
            "price", "petrol", "diesel", "gold", "silver", "sensex",
            "market", "economy", "inflation", "budget", "tax", "gst",
            "hospital", "doctor", "health", "covid", "vaccine",
            "school", "college", "university", "exam", "result",
            "job", "recruitment", "appointment", "transfer",
            "train", "railway", "bus", "flight", "airport",
            "road", "highway", "bridge", "construction",
            "scheme", "welfare", "subsidy", "loan", "pension",
            "cm ", "chief minister", "governor", "collector",
            "#andhra", "#telangana", "#telugu", "#tollywood",
        ]
        return any(kw in text_lower for kw in relevance_keywords)

    # ================================================================
    #  Wikipedia RAG Context (existing)
    # ================================================================
    def _fetch_rag_context(self, title: str) -> str:
        """Query Wikipedia REST summary as secondary contextual fallback."""
        words = re.findall(r'[A-Z][a-z]+', title)
        entity = words[0] if words else "Andhra_Pradesh"
        if len(words) > 1:
            entity = f"{words[0]}_{words[1]}"

        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{entity}"
        try:
            r = requests.get(url, headers=self.headers, timeout=5)
            if r.status_code == 200:
                return r.json().get("extract", "No additional background context.")
        except:
            pass
        return "Andhra Pradesh is a prominent state on the south-eastern coast of India, known for its rapid development, agricultural pillars, and global Telugu diaspora."

    # ================================================================
    #  DEDUPLICATION: Remove duplicate topics across sources
    # ================================================================
    def _deduplicate(self, topics: list) -> list:
        """Deduplicate by normalized title, counting how many sources reported each topic."""
        title_sources = {}  # normalized_title -> {"sources": set, "topic": dict}
        for t in topics:
            key = t.get("title", "").lower().strip()
            key = re.sub(r'^(breaking|update|news|latest)[:\\s]+', '', key, flags=re.IGNORECASE).strip()
            if not key:
                continue
            if key not in title_sources:
                title_sources[key] = {"sources": set(), "topic": t}
            title_sources[key]["sources"].add(t.get("source", "unknown"))
        
        unique = []
        for key, data in title_sources.items():
            t = data["topic"]
            t["num_sources"] = len(data["sources"])
            unique.append(t)
        return unique

    # ================================================================
    #  MAIN ENTRY POINT
    # ================================================================
    def run(self, lookback_hours: int = 12) -> list:
        """
        Execute full multi-source discovery with configurable lookback window.
        
        Args:
            lookback_hours: Hours to look back for trending data.
                           Primetime uses 12h (fresh content).
                           Spike check uses 1h (real-time).
        """
        print(f"▶ Phase 1.1: Polling Multi-Source Discovery (lookback={lookback_hours}h)...")
        all_topics = []

        # --- Tier 1: Core RSS (8 sources) ---
        print("  [Source] Polling 8 RSS feeds...")
        rss_topics = self._poll_rss_sources(self.rss_sources, max_per_feed=3)
        print(f"  [Source] RSS returned {len(rss_topics)} topics")
        all_topics.extend(rss_topics)

        # --- Tier 1b: Diaspora RSS ---
        print("  [Source] Polling diaspora RSS feeds...")
        diaspora_topics = self._poll_rss_sources(self.diaspora_rss, max_per_feed=2)
        print(f"  [Source] Diaspora RSS returned {len(diaspora_topics)} topics")
        all_topics.extend(diaspora_topics)

        # --- Tier 2: Google Trends (free pytrends) ---
        print("  [Source] Fetching Google Trends India...")
        gt_topics = self._fetch_google_trends()
        print(f"  [Source] Google Trends returned {len(gt_topics)} relevant topics")
        all_topics.extend(gt_topics)

        # --- Tier 3: Reddit JSON API (free) ---
        print("  [Source] Fetching Reddit trends (5 subreddits)...")
        reddit_topics = self._fetch_reddit_trends()
        print(f"  [Source] Reddit returned {len(reddit_topics)} relevant topics")
        all_topics.extend(reddit_topics)

        # --- Tier 4: YouTube Trending scrape (free) ---
        print("  [Source] Scraping YouTube Trending (India)...")
        yt_topics = self._fetch_youtube_trends()
        print(f"  [Source] YouTube returned {len(yt_topics)} relevant topics")
        all_topics.extend(yt_topics)

        # --- Tier 5: Inshorts scrape (free) ---
        print("  [Source] Scraping Inshorts...")
        inshorts_topics = self._fetch_inshorts()
        print(f"  [Source] Inshorts returned {len(inshorts_topics)} relevant topics")
        all_topics.extend(inshorts_topics)

        # --- Deduplicate ---
        print(f"  [Dedup] Before: {len(all_topics)} total | ", end="")
        all_topics = self._deduplicate(all_topics)
        print(f"After: {len(all_topics)} unique")

        # --- Hard Fallback: If ALL sources fail ---
        if not all_topics:
            print("  ⚠️ All sources down. Activating Tier-5 Hard Fallback.")
            all_topics.append(NewsPayload({
                "title": "Andhra Pradesh Launches Landmark IT Development Project",
                "description": "The government has approved a new tech-hub project in Vizag to create over 10,000 jobs for regional developers and attract global NRI investments.",
                "link": "https://www.ap.gov.in",
                "source": "Local Fallback Database",
                "rag_context": "Visakhapatnam is the largest city and financial capital of Andhra Pradesh, known for its IT parks and steel industries."
            }).to_dict())

        print(f"▶ Phase 1.1 COMPLETE: {len(all_topics)} candidates discovered from expanded sources.")
        return all_topics
