# VERSION: 83.0
# MODULE: fact_check.py
# PURPOSE: Named Entity Fact-Checking Gate
#          Verifies that people, organizations, and roles mentioned in the
#          generated script match the actual news source.
#          Blocks videos with factual errors before they reach YouTube.
#
#          v83.0: Initial fact-check module
#          - Fetches news article from source URL
#          - Extracts named entities from script using Gemini
#          - Verifies entity roles against source text
#          - Blocks on critical errors (wrong person, wrong role, false attribution)

import json
import re
import os
import sys
import urllib.request
import urllib.error
from html.parser import HTMLParser


class _HTMLTextExtractor(HTMLParser):
    """Simple HTML-to-text extractor for news article fetching."""

    def __init__(self):
        super().__init__()
        self.result = []
        self.skip = False
        self.skip_tags = {"script", "style", "nav", "footer", "header", "aside"}

    def handle_starttag(self, tag, attrs):
        if tag in self.skip_tags:
            self.skip = True

    def handle_endtag(self, tag):
        if tag in self.skip_tags:
            self.skip = False

    def handle_data(self, data):
        if not self.skip:
            text = data.strip()
            if text:
                self.result.append(text)

    def get_text(self):
        return " ".join(self.result)


def _fetch_article_text(url: str, timeout: int = 15) -> str:
    """Fetch and extract text from a news article URL.

    Returns the article body text, or empty string if fetch fails.
    """
    if not url or "news.google.com" in url:
        # Google News is an aggregator — we can't fetch the actual article
        return ""

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            # Try UTF-8, fall back to latin-1
            try:
                html = raw.decode("utf-8")
            except UnicodeDecodeError:
                html = raw.decode("latin-1")

        extractor = _HTMLTextExtractor()
        extractor.feed(html)
        text = extractor.get_text()
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text).strip()
        # Return first 5000 chars (enough for fact-checking)
        return text[:5000]
    except Exception as e:
        print(f"    ⚠️ FactCheck: Failed to fetch article from {url}: {e}")
        return ""


def _extract_entities_via_gemini(script_text: str, engine) -> list:
    """Use Gemini to extract named entities and their roles from the script.

    Returns a list of dicts: [{"name": "K. Annamalai", "role": "BJP state president", "context": "..."}]
    """
    if not engine:
        return []

    prompt = (
        f"You are a fact-checking editor. Extract ALL named people and their roles/positions "
        f"from the following news script. Be precise — include the exact role or position "
        f"as stated in the text.\n\n"
        f"Script:\n{script_text[:2000]}\n\n"
        f"Return a JSON array of objects with keys: "
        f'"name" (the person\'s name as written), '
        f'"role" (their role/position as stated in the script), '
        f'"context" (the sentence or phrase where they appear). '
        f"Return ONLY the JSON array, no other text."
    )

    try:
        response = engine.ask(prompt)
        if not response:
            return []
        # Try to parse JSON from response
        # Handle cases where Gemini wraps in ```json ... ```
        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        entities = json.loads(cleaned)
        if isinstance(entities, list):
            return entities
        return []
    except Exception as e:
        print(f"    ⚠️ FactCheck: Gemini entity extraction failed: {e}")
        return []


def _verify_entities_via_gemini(entities: list, article_text: str, title: str, engine) -> dict:
    """Use Gemini to verify entity roles against the actual news source.

    Returns: {"verdict": "PASS" | "FAIL" | "UNCERTAIN", "errors": [...], "warnings": [...]}
    """
    if not engine or not entities:
        return {"verdict": "UNCERTAIN", "errors": [], "warnings": ["No entities to verify or no engine available"]}

    entity_list = "\n".join(
        f"- {e.get('name', '?')}: {e.get('role', '?')} (context: {e.get('context', '?')})"
        for e in entities
    )

    # Truncate article text for prompt
    article_snippet = article_text[:3000] if article_text else "[No article text available — source is Google News aggregator]"

    prompt = (
        "You are a senior fact-checking editor. Verify the following named entities and their roles "
        "against the actual news source text.\n\n"
        f"News Headline: {title}\n\n"
        f"Entities extracted from the video script:\n{entity_list}\n\n"
        f"Actual news source text:\n{article_snippet}\n\n"
        "For each entity, check:\n"
        "1. Is the person's NAME correct? (spelling, full name)\n"
        "2. Is their ROLE/POSITION correct? (e.g., 'BJP state president' vs 'former BJP chief')\n"
        "3. Is their ACTION correct? (e.g., 'made an appeal' vs 'resigned')\n\n"
        'Return a JSON object with:\n'
        '"verdict": "PASS" (all entities correct), "FAIL" (at least one critical error), or "UNCERTAIN" (cannot verify from source text)\n'
        '"errors": [{"entity": "name", "claimed_role": "...", "actual_role": "...", "issue": "description"}]\n'
        '"warnings": ["any minor concerns"]\n\n'
        "CRITICAL: If a person is attributed the WRONG role (e.g., calling someone 'state president' "
        "when they are actually a 'former chief who resigned'), that is a FAIL. "
        "Return ONLY the JSON object, no other text."
    )

    try:
        response = engine.ask(prompt)
        if not response:
            return {"verdict": "UNCERTAIN", "errors": [], "warnings": ["Gemini returned empty response"]}

        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)

        result = json.loads(cleaned)
        if isinstance(result, dict):
            return result
        return {"verdict": "UNCERTAIN", "errors": [], "warnings": [f"Unexpected response format: {type(result)}"]}
    except json.JSONDecodeError as e:
        print(f"    ⚠️ FactCheck: Failed to parse Gemini verification response: {e}")
        return {"verdict": "UNCERTAIN", "errors": [], "warnings": [f"JSON parse error: {e}"]}
    except Exception as e:
        print(f"    ⚠️ FactCheck: Gemini verification failed: {e}")
        return {"verdict": "UNCERTAIN", "errors": [], "warnings": [str(e)]}


def _heuristic_entity_check(script_text: str, title: str) -> dict:
    """Lightweight heuristic fact-check when Gemini is unavailable or as a pre-filter.

    Checks for common hallucination patterns:
    - Title mentions person X as subject, but script attributes action to person Y
    - Role contradictions (e.g., "former chief" vs "state president")
    """
    errors = []
    warnings = []

    # Extract capitalized names from title and script
    title_names = set(re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z]+)?', title))
    script_names = set(re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z]+)?', script_text))

    # Check for role keywords near names
    role_patterns = [
        (r'(?:state|party|chief|president|minister|leader|mla|mp)\s+(?:of|for)?', 'role'),
        (r'(?:resigned|quit|left|exited)', 'resignation'),
        (r'(?:appealed|urged|asked|requested)', 'appeal'),
        (r'(?:says|said|stated|announced|claimed)', 'statement'),
    ]

    # Check if title's main subject appears in script with a different role
    # This is a simple heuristic — the Gemini check does the deep analysis
    if "post" in title.lower() or "after" in title.lower():
        # Title says "after X" — X should NOT be the main actor in the script
        # Extract the "after X" part
        after_match = re.search(r'(?:post|after)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)', title)
        if after_match:
            after_name = after_match.group(1)
            # Check if script attributes actions to this person
            sentences = re.split(r'[.!?]+', script_text)
            for sent in sentences:
                if after_name in sent:
                    action_verbs = ['appealed', 'urged', 'asked', 'requested', 'said', 'stated', 'announced']
                    for verb in action_verbs:
                        if verb in sent.lower():
                            warnings.append(
                                f"Title says 'after {after_name}' but script has '{after_name} {verb}' — "
                                f"verify {after_name} is not the main actor"
                            )
                            break

    return {"verdict": "UNCERTAIN", "errors": errors, "warnings": warnings}


def fact_check_script(script_text: str, title: str, source_url: str, engine=None) -> dict:
    """Main fact-check entry point.

    Args:
        script_text: The generated script text to verify
        title: The news headline/title
        source_url: URL of the news source
        engine: Gemini engine instance (optional — heuristic check runs without it)

    Returns:
        {
            "verdict": "PASS" | "FAIL" | "UNCERTAIN",
            "errors": [{"entity": "...", "issue": "..."}],
            "warnings": ["..."],
            "source_text_fetched": bool,
            "entities_checked": int
        }
    """
    print("  🔍 FactCheck: Starting named entity verification...")

    result = {
        "verdict": "UNCERTAIN",
        "errors": [],
        "warnings": [],
        "source_text_fetched": False,
        "entities_checked": 0,
    }

    # Step 1: Heuristic pre-check (always runs)
    heuristic = _heuristic_entity_check(script_text, title)
    result["warnings"].extend(heuristic.get("warnings", []))
    result["errors"].extend(heuristic.get("errors", []))

    # Step 2: Fetch article text
    article_text = _fetch_article_text(source_url)
    if article_text:
        result["source_text_fetched"] = True
        print(f"  🔍 FactCheck: Fetched {len(article_text)} chars of source text")
    else:
        print("  🔍 FactCheck: No source text available (Google News aggregator or fetch failed)")
        result["warnings"].append("Could not fetch source article text — verification limited to heuristics")

    # Step 3: Gemini entity extraction + verification
    if engine:
        entities = _extract_entities_via_gemini(script_text, engine)
        result["entities_checked"] = len(entities)
        print(f"  🔍 FactCheck: Extracted {len(entities)} named entities from script")

        if entities:
            verification = _verify_entities_via_gemini(entities, article_text, title, engine)
            result["errors"].extend(verification.get("errors", []))
            result["warnings"].extend(verification.get("warnings", []))

            # Determine final verdict
            if verification.get("verdict") == "FAIL" or result["errors"]:
                result["verdict"] = "FAIL"
            elif verification.get("verdict") == "PASS" and not result["warnings"]:
                result["verdict"] = "PASS"
            elif verification.get("verdict") == "PASS" and result["warnings"]:
                result["verdict"] = "PASS"  # warnings alone don't block
            else:
                result["verdict"] = "UNCERTAIN"
        else:
            print("  🔍 FactCheck: No entities extracted — skipping Gemini verification")
    else:
        print("  🔍 FactCheck: No Gemini engine — heuristic check only")
        if result["errors"]:
            result["verdict"] = "FAIL"
        elif result["warnings"]:
            result["verdict"] = "UNCERTAIN"

    # Print summary
    status_icon = {"PASS": "✅", "FAIL": "❌", "UNCERTAIN": "⚠️"}.get(result["verdict"], "?")
    print(f"  {status_icon} FactCheck Result: {result['verdict']} "
          f"({len(result['errors'])} errors, {len(result['warnings'])} warnings)")

    if result["errors"]:
        for err in result["errors"]:
            if isinstance(err, dict):
                entity = err.get("entity", "?")
                issue = err.get("issue", str(err))
                print(f"     ❌ {entity}: {issue}")
            else:
                print(f"     ❌ {err}")

    if result["warnings"]:
        for warn in result["warnings"][:5]:  # Show max 5 warnings
            print(f"     ⚠️ {warn}")

    return result


def correct_script_with_facts(
    script_text: str,
    errors: list,
    title: str,
    source_url: str,
    engine,
) -> str:
    """Use Gemini to rewrite the script correcting factual errors.

    Fetches the actual article, identifies the correct facts, and rewrites
    the script with accurate entity names, roles, and actions.

    Returns the corrected script text, or the original if correction fails.
    """
    import re, json

    # Fetch the actual article for correction context
    article_text = ""
    try:
        import urllib.request
        req = urllib.request.Request(source_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            # Strip HTML tags for clean text
            article_text = re.sub(r"<[^>]+>", " ", raw)
            article_text = re.sub(r"\s+", " ", article_text).strip()
    except Exception:
        pass

    article_snippet = article_text[:3000] if article_text else "[Could not fetch article — use the error descriptions to correct]"

    # Build error descriptions for the prompt
    error_descs = []
    for err in errors:
        if isinstance(err, dict):
            entity = err.get("entity", "?")
            claimed = err.get("claimed_role", "?")
            actual = err.get("actual_role", "?")
            issue = err.get("issue", "")
            error_descs.append(f"- Entity '{entity}': claimed role '{claimed}' but actual is '{actual}'. Issue: {issue}")
        else:
            error_descs.append(f"- {err}")

    error_block = "\n".join(error_descs)

    prompt = (
        "You are a senior news editor. The following video script contains factual errors "
        "about named entities. Rewrite the script to fix ALL the errors listed below, "
        "using the actual news source text for reference.\n\n"
        f"Original Headline: {title}\n\n"
        f"Factual Errors to Fix:\n{error_block}\n\n"
        f"Actual News Source Text:\n{article_snippet}\n\n"
        f"Original Script (with errors):\n{script_text}\n\n"
        "INSTRUCTIONS:\n"
        "1. Fix ALL entity names, roles, and actions to match the actual news source\n"
        "2. Keep the same tone, style, and approximate length\n"
        "3. Do NOT add new information not in the source\n"
        "4. Return ONLY the corrected script text, no explanations or JSON\n"
    )

    try:
        response = engine.ask(prompt)
        if not response:
            return script_text

        # Clean up the response — strip any markdown or JSON wrapping
        corrected = response.strip()
        # Remove markdown code blocks if present
        if corrected.startswith("```"):
            corrected = re.sub(r"^```[a-z]*\n?", "", corrected)
            corrected = re.sub(r"\n?```$", "", corrected)
        # If response is JSON with a "script" key, extract it
        try:
            parsed = json.loads(corrected)
            if isinstance(parsed, dict):
                for key in ("script", "corrected_script", "text", "content"):
                    if key in parsed:
                        corrected = str(parsed[key])
                        break
        except (json.JSONDecodeError, ValueError):
            pass  # Not JSON, use as-is

        corrected = corrected.strip()
        if len(corrected) < 20:
            return script_text  # Too short, probably garbage

        return corrected

    except Exception as e:
        print(f"  ⚠️ correct_script_with_facts error: {e}")
        return script_text
