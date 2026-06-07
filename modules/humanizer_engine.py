# VERSION: 1.0
# MODULE: humanizer_engine.py
# PURPOSE: Post-process generated scripts to strip AI-isms and inject natural voice.
#          Applied after Gemini/heuristic script generation, before voice synthesis.
#          Targets the 29 AI writing patterns documented in the humanizer skill.

import re


class HumanizerEngine:
    """Strips AI-omorphism from generated scripts to improve viewer retention."""

    # Pattern groups for detection and removal

    # 1. Significance inflation
    SIGNIFICANCE = [
        r'\bstands as\b', r'\bserve as\b', r'\ba testament\b', r'\ba reminder\b',
        r'\bvital role\b', r'\bsignificant role\b', r'\bcrucial role\b',
        r'\bpivotal role\b', r'\bkey role\b', r'\bkey moment\b',
        r'\bunderscores its importance\b', r'\bunderscore the importance\b',
        r'\breflects broader\b', r'\bsymbolizing its', r'\benduring',
        r'\blasting legacy\b', r'\bcontributing to the\b', r'\bsetting the stage for\b',
        r'\bmarking a\b', r'\bshapes the\b', r'\brepresents a shift\b',
        r'\bkey turning point\b', r'\bevolving landscape\b', r'\bfocal point\b',
        r'\bindelible mark\b', r'\bdeeply rooted\b',
    ]

    # 2. Notability claims
    NOTABILITY = [
        r'\bindependent coverage\b', r'\blocal media outlets\b',
        r'\bnational media outlets\b', r'\bregional media\b',
        r'\bwritten by a leading expert\b', r'\bactive social media presence\b',
    ]

    # 3. Superficial -ing analysis
    ING_PHRASES = [
        r',?\s*highlighting\s+the\b', r',?\s*underscoring\s+the\b',
        r',?\s*emphasizing\s+the\b', r',?\s*ensuring\s+that\b',
        r',?\s*reflecting\s+the\b', r',?\s*contributing\s+to\s+the\b',
        r',?\s*cultivating\b', r',?\s*fostering\b',
        r',?\s*encompassing\b', r',?\s*showcasing\b',
    ]

    # 4. Promotional language
    PROMOTIONAL = [
        r'\bbreathtaking\b', r'\bvibrant\b', r'\brich cultural heritage\b',
        r'\bprofound\b', r'\bexemplifies\b', r'\bcommitment to\b',
        r'\bnatural beauty\b', r'\bnestled\b', r'\bin the heart of\b',
        r'\bgroundbreaking\b', r'\brenowned\b', r'\bmust-visit\b',
        r'\bstunning\b', r'\boffers a\b',
    ]

    # 5. Vague attributions
    VAGUE_ATTR = [
        r'\bindustry reports\s+(show|suggest|indicate)',
        r'\bexperts\s+(say|believe|argue|suggest)',
        r'\bobservers\s+(have\s+)?(noted|cited|mentioned)',
        r'\bsome\s+critics\s+argue\b', r'\bmany\s+believe\b',
        r'\bit\s+is\s+widely\b',
    ]

    # 6. Formulaic challenges/future
    FORMULAIC = [
        r'\bDespite\s+its\b.*\bfaces?\s+(several\s+)?challenges\b',
        r'\bDespite\s+these\s+challenges,\s+',
        r'\bChallenges?\s+and\s+(Legacy|Future)\b',
        r'\bFuture\s+Outlook\b',
    ]

    # 7. AI vocabulary (lighter touch — only when overused)
    AI_WORDS = [
        r'\badditionally\b', r'\balign\s+with\b', r'\bcrucial\b',
        r'\bdelve\b', r'\bemphasizing\b', r'\bkey\b',
        r'\bintricate\b', r'\bpivotal\b', r'\bvaluable\b',
        r'\binterplay\b', r'\bshowcase\b', r'\benhance\b',
        r'\blandscape\b', r'\btapestry\b', r'\btestament\b',
        r'\bunderscore\b',
    ]

    # 8. Copula avoidance
    COPULA_AVOID = [
        r'\bstands\s+as\s+a\b', r'\bstands\s+as\b',
        r'\bserve\s+as\s+a\b', r'\bserve\s+as\b',
        r'\bboasts\s+a\b', r'\bboasts\b',
]

    # Filler phrase reductions
    FILLERS = [
        r'\bIn\s+order\s+to\b',  # -> "To"
        r'\bDue\s+to\s+the\s+fact\s+that\b',  # -> "Because"
        r'\bAt\s+this\s+point\s+in\s+time\b',  # -> "Now"
        r'\bIn\s+the\s+event\s+that\b',  # -> "If"
        r'\bIt\s+is\s+important\s+to\s+note\s+that\b',  # -> (delete)
        r'\bhas\s+the\s+ability\s+to\b',  # -> "can"
    ]

    FILLER_REPLACEMENTS = {
        'in order to': 'to',
        'due to the fact that': 'because',
        'at this point in time': 'now',
        'in the event that': 'if',
        'it is important to note that': '',
        'has the ability to': 'can',
    }

    def __init__(self):
        # Compile all regex patterns for efficiency
        self._compiled = {}
        for name, patterns in [
            ('significance', self.SIGNIFICANCE),
            ('notability', self.NOTABILITY),
            ('ing_phrases', self.ING_PHRASES),
            ('promotional', self.PROMOTIONAL),
            ('vague_attr', self.VAGUE_ATTR),
            ('formulaic', self.FORMULAIC),
            ('copula_avoid', self.COPULA_AVOID),
        ]:
            combined = '|'.join(f'(?:{p})' for p in patterns)
            self._compiled[name] = re.compile(combined, re.IGNORECASE)

        self._fillers = {}
        for phrase, replacement in self.FILLER_REPLACEMENTS.items():
            self._fillers[phrase] = (re.compile(r'\b' + re.escape(phrase) + r'\b', re.IGNORECASE), replacement)

    def _remove_pattern_group(self, text: str, group_name: str) -> tuple[str, int]:
        """Remove all matches of a pattern group. Returns (cleaned_text, count)."""
        compiled = self._compiled.get(group_name)
        if not compiled:
            return text, 0
        matches = compiled.findall(text)
        count = len(matches)
        if count > 0:
            text = compiled.sub('', text)
        return text, count

    def _fix_fillers(self, text: str) -> tuple[str, int]:
        """Replace filler phrases with simpler alternatives."""
        count = 0
        for phrase, (pattern, replacement) in self._fillers.items():
            matches = pattern.findall(text)
            if matches:
                count += len(matches)
                text = pattern.sub(replacement, text)
        return text, count

    def _clean_residual(self, text: str) -> str:
        """Clean up residual artifacts from removal: double spaces, empty lines."""
        # Remove double+ spaces
        text = re.sub(r' {2,}', ' ', text)
        # Remove empty lines
        text = re.sub(r'\n{3,}', '\n\n', text)
        # Fix punctuation artifacts: ". ." -> ".", ", ," -> ","
        text = re.sub(r'\.\s*\.', '.', text)
        text = re.sub(r',\s*,', ',', text)
        # Fix " - " artifacts
        text = re.sub(r'\s+-\s+', ' — ', text)
        # Strip leading/trailing whitespace per line
        text = '\n'.join(line.strip() for line in text.split('\n'))
        return text.strip()

    def humanize(self, script_text: str, segment_type: str = 'main') -> tuple[str, dict]:
        """
        Humanize a script text. Returns (cleaned_text, stats_dict).
        segment_type: 'main' | 'short_1' | 'short_2' | 'short_3'
        """
        if not script_text or not script_text.strip():
            return script_text, {'skipped': True}

        text = script_text
        # Normalize ALL apostrophe-like Unicode characters to straight quotes
        # Gemini outputs various smart quote characters that break TTS contraction matching
        text = text.replace("\u2019", "'").replace("\u2018", "'")  # right/left single quote
        text = text.replace("\u2032", "'").replace("\u2035", "'")  # prime/reversed prime
        text = text.replace("\u02bc", "'").replace("\u02bb", "'")  # modifier letter apostrophe/turned comma
        text = text.replace("\uff07", "'").replace("\u201b", "'")  # fullwidth apostrophe/high-reversed-9
        text = text.replace("\u2039", "'").replace("\u203a", "'")  # single angle quotes
        stats = {'segment_type': segment_type, 'original_word_count': len(text.split())}

        # 1. Remove significance inflation patterns
        text, count = self._remove_pattern_group(text, 'significance')
        stats['significance_removed'] = count

        # 2. Remove notability claims
        text, count = self._remove_pattern_group(text, 'notability')
        stats['notability_removed'] = count

        # 3. Remove superficial -ing phrases
        text, count = self._remove_pattern_group(text, 'ing_phrases')
        stats['ing_phrases_removed'] = count

        # 4. Remove promotional language
        text, count = self._remove_pattern_group(text, 'promotional')
        stats['promotional_removed'] = count

        # 5. Remove vague attributions
        text, count = self._remove_pattern_group(text, 'vague_attr')
        stats['vague_attr_removed'] = count

        # 6. Remove formulaic challenges/future sections
        text, count = self._remove_pattern_group(text, 'formulaic')
        stats['formulaic_removed'] = count

        # 7. Fix copula avoidance ("serves as" -> "is")
        text, count = self._remove_pattern_group(text, 'copula_avoid')
        stats['copula_fixed'] = count  # These are replaced by context, just removed here

        # 8. Fix filler phrases
        text, count = self._fix_fillers(text)
        stats['fillers_fixed'] = count

        # 9. Clean residual artifacts
        text = self._clean_residual(text)
        stats['cleaned_word_count'] = len(text.split())

        stats['total_changes'] = sum(v for k, v in stats.items()
                                      if k not in ('segment_type', 'original_word_count', 'cleaned_word_count'))

        return text, stats

    def humanize_package(self, sections: dict) -> tuple[dict, dict]:
        """
        Humanize a full script package (main + 3 shorts).
        sections: {"main": {...}, "short_1": {...}, "short_2": {...}, "short_3": {...}}
        Returns (humanized_section, all_stats).
        """
        result = {}
        all_stats = {}

        for key in ['main', 'short_1', 'short_2', 'short_3']:
            section = sections.get(key, {})
            script_text = section.get('script', '') if isinstance(section, dict) else str(section)

            if script_text:
                cleaned, stats = self.humanize(script_text, segment_type=key)
                section['script'] = cleaned
                section['_humanizer_stats'] = stats
                result[key] = section
                all_stats[key] = stats
            else:
                result[key] = section
                all_stats[key] = {'skipped': True, 'reason': 'empty_script'}

        return result, all_stats
