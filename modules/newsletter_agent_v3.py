"""
Newsletter Agent v3.0 — VDNA 3.0 Port
Weekly newsletter digest generation from recent video content.
Uses existing NewsletterGenerator from newsletter_generator.py.
Ported from old pipeline's NewsletterAgent.
"""
import os, sys

_MODULES_DIR = os.path.dirname(os.path.abspath(__file__))
if _MODULES_DIR not in sys.path:
    sys.path.insert(0, _MODULES_DIR)

from newsletter_generator import NewsletterGenerator
from datetime import datetime


class NewsletterAgentV3:
    """
    Post-pipeline newsletter: creates HTML email newsletter from recent video content.
    """

    def __init__(self, *args, **kwargs):
        self.generator = NewsletterGenerator()

    def generate(self, topics: list = None) -> dict:
        """Generate weekly newsletter digest. Returns result dict."""
        try:
            result = self.generator.run(topics=topics or [])
            return {
                "newsletter_path": result.get("newsletter_path", "") if isinstance(result, dict) else str(result),
                "topics_included": len(topics or []),
                "generated_at": datetime.now().isoformat(),
                "success": True,
            }
        except Exception as e:
            return {
                "newsletter_path": "",
                "topics_included": 0,
                "error": str(e)[:100],
                "generated_at": datetime.now().isoformat(),
                "success": False,
            }

    def execute(self, state):
        return state
