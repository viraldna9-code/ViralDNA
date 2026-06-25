"""
Blog Companion Generator v2.0
Generates blog companion articles from video scripts.
Produces both Markdown and HTML files with YouTube video embeds.
"""
import os, json, re
from datetime import datetime


class BlogCompanionGenerator:
    """
    Generates SEO-optimized blog articles that complement YouTube videos.
    Each article includes: title, meta description, article body, YouTube embed, tags.
    Saved to disk — publishing to blog can be manual or via CMS API later.
    """

    BLOG_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "diagnostics", "blog_articles"
    )

    def __init__(self, *args, **kwargs):
        os.makedirs(self.BLOG_DIR, exist_ok=True)

    def run(self, topic=None, script_text: str = "", video_url: str = "") -> dict:
        """
        Generate blog companion article from video topic + script.
        Returns {html_path, markdown_path, slug, word_count}.
        Called by BlogCompanionAgent post-pipeline.

        Can be called with:
        - (topic, script_text, video_url) — for a specific video
        - (topics=list) — for a digest of multiple topics
        """
        # Handle both signatures
        if isinstance(topic, list):
            return self._run_digest(topic)

        topic = topic or {}
        title = topic.get("title", "Telugu News Update") if isinstance(topic, dict) else "Telugu News Update"
        category = topic.get("category", "news") if isinstance(topic, dict) else "news"
        now = datetime.now()
        slug = self._slugify(title)
        date_str = now.strftime("%Y-%m-%d")

        # Build article content
        markdown_content = self._build_markdown(title, category, script_text, video_url, date_str)
        html_content = self._build_html(title, category, script_text, video_url, date_str, slug)

        # Save files
        md_path = os.path.join(self.BLOG_DIR, f"{slug}.md")
        html_path = os.path.join(self.BLOG_DIR, f"{slug}.html")

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        word_count = len(markdown_content.split())

        return {
            "html_path": html_path,
            "markdown_path": md_path,
            "slug": slug,
            "word_count": word_count,
            "title": title,
            "category": category,
            "generated_at": now.isoformat(),
        }

    def _run_digest(self, topics: list) -> dict:
        """Generate a digest article covering multiple topics."""
        now = datetime.now()
        slug = f"weekly-digest-{now.strftime('%Y%m%d')}"
        date_str = now.strftime("%B %d, %Y")

        titles = []
        for t in topics[:10]:
            if isinstance(t, dict):
                titles.append(t.get("title", ""))
            elif isinstance(t, str):
                titles.append(t)

        markdown_content = f"""---
title: "ViralDNA Weekly Digest — {date_str}"
date: "{now.strftime('%Y-%m-%d')}"
category: "digest"
tags: ["telugu-news", "weekly-digest", "diaspora"]
---

# ViralDNA Weekly Digest — {date_str}

*Your weekly roundup of Telugu news stories from around the world.*

---

"""
        for i, t in enumerate(titles, 1):
            markdown_content += f"## {i}. {t}\n\n"
            markdown_content += f"Watch the full breakdown on our YouTube channel.\n\n---\n\n"

        md_path = os.path.join(self.BLOG_DIR, f"{slug}.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)

        return {
            "markdown_path": md_path,
            "slug": slug,
            "word_count": len(markdown_content.split()),
            "title": f"Weekly Digest — {date_str}",
            "type": "digest",
        }

    def _build_markdown(self, title, category, script_text, video_url, date_str):
        """Build Markdown article."""
        # Extract key points from script (first few sentences as summary)
        summary = self._extract_summary(script_text)
        yt_id = self._extract_youtube_id(video_url)

        md = f"""---
title: "{title} — Full Analysis"
date: "{date_str}"
category: "{category}"
tags: ["telugu-news", "{category}", "viral-dna"]
---

# {title}

**Published:** {date_str} | **Category:** {category.upper()}

---

## Summary

{summary}

---

## Full Analysis

{self._script_to_article(script_text)}

---

## Watch the Video

"""
        if yt_id:
            md += f"[Watch on YouTube]({video_url})\n\n"
            md += f"[![Watch on YouTube](https://img.youtube.com/vi/{yt_id}/0.jpg)]({video_url})\n"
        else:
            md += f"[Watch on YouTube]({video_url})\n"

        md += f"""

---

*This article complements our YouTube video. Subscribe to [ViralDNA](https://www.youtube.com/@ViralDNA) for daily Telugu news updates.*

"""
        return md

    def _build_html(self, title, category, script_text, video_url, date_str, slug):
        """Build HTML article."""
        summary = self._extract_summary(script_text)
        yt_id = self._extract_youtube_id(video_url)
        article_body = self._script_to_article(script_text)

        # Convert markdown-style line breaks to HTML
        article_html = article_body.replace("\n\n", "</p><p>")

        embed_html = ""
        if yt_id:
            embed_html = f'''
    <div style="position:relative;padding-bottom:56.25%;height:0;overflow:hidden;margin:24px 0;">
        <iframe src="https://www.youtube.com/embed/{yt_id}" 
                style="position:absolute;top:0;left:0;width:100%;height:100%;"
                frameborder="0" allowfullscreen></iframe>
    </div>'''

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="description" content="{summary[:150]}">
    <title>{title} — ViralDNA</title>
    <style>
        body {{ font-family: Georgia, serif; max-width: 800px; margin: 0 auto; padding: 20px; color: #333; }}
        h1 {{ color: #C04020; }}
        .meta {{ color: #888; font-size: 14px; margin-bottom: 20px; }}
        .summary {{ background: #f5f5f5; padding: 16px; border-left: 4px solid #C04020; margin: 20px 0; }}
        a {{ color: #C04020; }}
        .footer {{ border-top: 1px solid #eee; margin-top: 40px; padding-top: 16px; font-size: 14px; color: #888; }}
    </style>
</head>
<body>
    <article>
        <h1>{title}</h1>
        <p class="meta">{date_str} | {category.upper()}</p>
        <div class="summary"><strong>Summary:</strong> {summary}</div>
        <div class="content"><p>{article_html}</p></div>
        {embed_html}
    </article>
    <div class="footer">
        ViralDNA — Telugu News for the Global Diaspora | 
        <a href="https://www.youtube.com/@ViralDNA">Subscribe on YouTube</a>
    </div>
</body>
</html>"""
        return html

    def _extract_summary(self, script_text: str) -> str:
        """Extract a 2-3 sentence summary from script text."""
        if not script_text:
            return "Stay updated with the latest Telugu news and analysis."
        # Take first 3 sentences
        sentences = re.split(r'[.!?]+', script_text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
        summary = ". ".join(sentences[:3])
        if summary and not summary.endswith("."):
            summary += "."
        return summary or "Stay updated with the latest Telugu news and analysis."

    def _script_to_article(self, script_text: str) -> str:
        """Convert script text to article paragraphs."""
        if not script_text:
            return "Full story and analysis available in our latest video. Watch the complete breakdown on our YouTube channel."

        # Split into sentences and group into paragraphs
        sentences = re.split(r'(?<=[.!?])\s+', script_text)
        paragraphs = []
        current = []
        for sent in sentences:
            current.append(sent)
            if len(current) >= 3:
                paragraphs.append(" ".join(current))
                current = []
        if current:
            paragraphs.append(" ".join(current))

        return "\n\n".join(paragraphs) if paragraphs else script_text

    def _extract_youtube_id(self, url: str) -> str:
        """Extract YouTube video ID from URL."""
        if not url:
            return ""
        patterns = [
            r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
            r'(?:embed\/)([0-9A-Za-z_-]{11})',
            r'(?:youtu\.be\/)([0-9A-Za-z_-]{11})',
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return ""

    def _slugify(self, text: str) -> str:
        """Convert title to URL-safe slug."""
        slug = re.sub(r'[^\w\s-]', '', text.lower())
        slug = re.sub(r'[\s_]+', '-', slug)
        return slug.strip('-')[:60]

    def execute(self, state):
        return state
