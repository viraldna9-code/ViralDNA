"""
Blog Companion v3.0 — VDNA 3.0 Port
Blog article generation from video scripts.
Uses existing BlogCompanionGenerator from blog_companion.py.
Ported from old pipeline's BlogCompanionAgent.
"""
import os, sys

_MODULES_DIR = os.path.dirname(os.path.abspath(__file__))
if _MODULES_DIR not in sys.path:
    sys.path.insert(0, _MODULES_DIR)

from blog_companion import BlogCompanionGenerator
from datetime import datetime


class BlogCompanionV3:
    """
    Post-pipeline blog companion: generates HTML and Markdown articles
    from video script content for content repurposing.
    """

    def __init__(self, *args, **kwargs):
        self.generator = BlogCompanionGenerator()

    def generate(self, topic: dict = None, script_text: str = "", video_url: str = "") -> dict:
        """Generate blog article from video content. Returns paths dict."""
        try:
            result = self.generator.run(
                topic=topic or {},
                script_text=script_text,
                video_url=video_url,
            )
            return {
                "paths": result if isinstance(result, dict) else {"output": str(result)},
                "generated_at": datetime.now().isoformat(),
                "success": True,
            }
        except Exception as e:
            return {
                "paths": {},
                "error": str(e)[:100],
                "generated_at": datetime.now().isoformat(),
                "success": False,
            }

    def execute(self, state):
        return state
