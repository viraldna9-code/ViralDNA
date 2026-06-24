# VERSION: 50.0
# MODULE: data_flow_registry.py
# PURPOSE: Strict Pipeline State Machine & Schema Validator (Zero-Tolerance)

import re


class NewsPayload:
    """Schema Validator for Discovery (Phase 1) Output."""
    _KNOWN_SOURCES = [
        "Telangana Today", "Telugu News", "The Hindu", "Times of India", "NDTV",
        "BBC", "BBC News", "CNN", "Reuters", "Al Jazeera",
        "Indian Express", "Deccan Chronicle", "Hindustan Times", "ANI", "PTI",
        "IANS", "News18", "India Today", "Zee News", "Republic TV",
        "Eenadu", "Andhra Jyothi", "Sakshi", "Vaartha",
        "The Guardian", "Washington Post", "New York Times", "Bloomberg",
        "Livemint", "Economic Times", "Business Standard", "Mint",
        "Google News", "Yahoo News", "MSN News",
    ]
    _source_re = None

    @classmethod
    def _get_source_re(cls):
        if cls._source_re is None:
            sources = sorted(cls._KNOWN_SOURCES, key=len, reverse=True)
            cls._source_re = re.compile(
                r'\s*-\s+(' + '|'.join(re.escape(s) for s in sources) + r')$'
            )
        return cls._source_re

    def __init__(self, data: dict):
        raw_title = str(data.get("title", "")).strip()
        # Strip trailing " - Source Name" that Google News RSS and other feeds append
        # e.g. "Andhra High Court Adjourns PIL - Telangana Today" -> "Andhra High Court Adjourns PIL"
        self.title = self._get_source_re().sub('', raw_title).strip()
        self.description = str(data.get("description", "")).strip()
        self.link = str(data.get("link", "")).strip()
        self.source = str(data.get("source", "")).strip()
        self.rag_context = str(data.get("rag_context", "No additional background context.")).strip()
        self.trending_score = str(data.get("trending_score", "normal")).strip()
        self.published = str(data.get("published", "")).strip()
        self.validate()

    def validate(self):
        if not self.title or len(self.title) < 10:
            raise ValueError("❌ NewsPayload Validation Failed: Title is empty or too short.")
        if not self.description:
            raise ValueError("❌ NewsPayload Validation Failed: Description is empty.")

    def to_dict(self):
        return {
            "title": self.title,
            "description": self.description,
            "link": self.link,
            "source": self.source,
            "rag_context": self.rag_context,
            "trending_score": self.trending_score,
            "published": str(self.published) if hasattr(self, "published") else "",
        }


class ScriptPayload:
    """Schema Validator for Scripting (Phase 2) Output (Enforces Word Counts)."""
    WPM = 140 # Broadcast Standard: 140 Words Per Minute

    def __init__(self, raw_data: dict):
        self.main = raw_data.get("main", {"script": "", "title_variants": []})
        self.short_1 = raw_data.get("short_1", {"script": "", "title_variants": []})
        self.short_2 = raw_data.get("short_2", {"script": "", "title_variants": []})
        self.short_3 = raw_data.get("short_3", {"script": "", "title_variants": []})
        
        self.main_raw = self.main["script"]
        self.short_1_raw = self.short_1["script"]
        self.short_2_raw = self.short_2["script"]
        self.short_3_raw = self.short_3["script"]
        
        self.main_title_variants = self.main["title_variants"]
        self.short_1_title_variants = self.short_1["title_variants"]
        self.short_2_title_variants = self.short_2["title_variants"]
        self.short_3_title_variants = self.short_3["title_variants"]
        
        self.main_clean = self._clean(self.main_raw)
        self.short_1_clean = self._clean(self.short_1_raw)
        self.short_2_clean = self._clean(self.short_2_raw)
        self.short_3_clean = self._clean(self.short_3_raw)
        
        self.main_word_count = len(self.main_clean.split())
        self.short_1_word_count = len(self.short_1_clean.split())
        self.short_2_word_count = len(self.short_2_clean.split())
        self.short_3_word_count = len(self.short_3_clean.split())
        
        self.main_duration = self.main_word_count / self.WPM * 60 # Duration in seconds
        self.short_1_duration = self.short_1_word_count / self.WPM * 60
        self.short_2_duration = self.short_2_word_count / self.WPM * 60
        self.short_3_duration = self.short_3_word_count / self.WPM * 60
        
        self.validate()

    def _clean(self, text: str) -> str:
        """Sanitizer: Deletes all non-pronounceable characters, URLs, and markdown."""
        import re
        if not text: return ""
        # Remove markdown tags, bracketed text, HTML
        text = re.sub(r'```json|```|\[.*?\]|<.*?>', ' ', text)
        # Remove URLs and file paths
        text = re.sub(r'https?://\S+|www\.\S+|\S+\.\S+|/[a-zA-Z0-9_/.]+', ' ', text)
        # Remove non-alphanumeric chars except basic punctuation
        text = re.sub(r'[^a-zA-Z0-9\s.,?!]', ' ', text)
        # Collapse multiple spaces
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def validate(self):
        # v86.0: Main script must be 400-700 words for 3-5 minute video
        if self.main_word_count < 100:
            raise ValueError(f"❌ ScriptPayload Validation Failed: Main script too short ({self.main_word_count} words, minimum 100).")
        if self.main_word_count < 400:
            print(f"   ⚠️ Main script is only {self.main_word_count} words (target: 400-700 for 3-5 min video)")
        # Shorts must have minimum 20 words to produce meaningful 8-10s video
        for short_name, short_wc in [("short_1", self.short_1_word_count),
                                      ("short_2", self.short_2_word_count),
                                      ("short_3", self.short_3_word_count)]:
            if short_wc > 0 and short_wc < 20:
                raise ValueError(f"❌ ScriptPayload Validation Failed: {short_name} too short ({short_wc} words, minimum 20). Short was generated but is too brief for a meaningful video.")
        print(f"    📊 Script Audit: Main duration is {self.main_duration:.1f}s | Word Count: {self.main_word_count}")
        print(f"    📊 Script Audit: Short 1 duration is {self.short_1_duration:.1f}s | Word Count: {self.short_1_word_count}")

    def get_segment(self, key: str) -> dict:
        mapping = {
            "main": (self.main_clean, self.main_duration, self.main_word_count),
            "short_1": (self.short_1_clean, self.short_1_duration, self.short_1_word_count),
            "short_2": (self.short_2_clean, self.short_2_duration, self.short_2_word_count),
            "short_3": (self.short_3_clean, self.short_3_duration, self.short_3_word_count)
        }
        text, duration, words = mapping.get(key, ("", 0, 0))
        return {"text": text, "target_duration_s": duration, "word_count": words}

    def update_segment(self, key: str, new_text: str):
        """Update a segment's script text and recalculate derived fields."""
        if key == "main":
            self.main["script"] = new_text
            self.main_raw = new_text
            self.main_clean = self._clean(new_text)
            self.main_word_count = len(self.main_clean.split())
            self.main_duration = self.main_word_count / self.WPM * 60
        elif key == "short_1":
            self.short_1["script"] = new_text
            self.short_1_raw = new_text
            self.short_1_clean = self._clean(new_text)
            self.short_1_word_count = len(self.short_1_clean.split())
            self.short_1_duration = self.short_1_word_count / self.WPM * 60
        elif key == "short_2":
            self.short_2["script"] = new_text
            self.short_2_raw = new_text
            self.short_2_clean = self._clean(new_text)
            self.short_2_word_count = len(self.short_2_clean.split())
            self.short_2_duration = self.short_2_word_count / self.WPM * 60
        elif key == "short_3":
            self.short_3["script"] = new_text
            self.short_3_raw = new_text
            self.short_3_clean = self._clean(new_text)
            self.short_3_word_count = len(self.short_3_clean.split())
            self.short_3_duration = self.short_3_word_count / self.WPM * 60
