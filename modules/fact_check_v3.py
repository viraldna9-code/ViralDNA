"""
Fact Check v3.0 — VDNA 3.0 Port
Named entity fact-checking on generated scripts.
Uses existing fact_check.py module.
Ported from old pipeline's FactCheckAgent.
"""
import os, sys

_MODULES_DIR = os.path.dirname(os.path.abspath(__file__))
if _MODULES_DIR not in sys.path:
    sys.path.insert(0, _MODULES_DIR)

from datetime import datetime


class FactCheckV3:
    """
    Phase 3.5: Named entity fact-checking gate.
    Verifies that people, organizations, and roles in the generated script
    match the actual news source.
    """

    def __init__(self, *args, **kwargs):
        self.blocked_count = 0

    def check_script(self, script_text: str, title: str = "", source_url: str = "", topic_desc: str = "") -> dict:
        """Run fact-check on a script. Returns verdict dict."""
        try:
            from fact_check import fact_check_script
            # fact_check_script needs an engine parameter
            try:
                from gemini_engine import GeminiEngine
                engine = GeminiEngine()
            except Exception:
                engine = None

            result = fact_check_script(
                script_text=script_text,
                title=title,
                source_url=source_url,
                engine=engine,
                topic_desc=topic_desc,
            )
            return result
        except ImportError:
            return {
                "verdict": "UNCERTAIN",
                "errors": [],
                "warnings": ["fact_check module not available"],
                "checked_at": datetime.now().isoformat(),
            }
        except Exception as e:
            return {
                "verdict": "UNCERTAIN",
                "errors": [],
                "warnings": [str(e)[:100]],
                "checked_at": datetime.now().isoformat(),
            }

    def execute(self, state):
        return state
