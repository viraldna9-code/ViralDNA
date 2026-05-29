"""
Newsletter Generator v2.0
Generates HTML email newsletter from recent video content.
Saves to disk — email sending can be manual or via SMTP/API later.
"""
import os, json
from datetime import datetime


class NewsletterGenerator:
    """
    Generates weekly newsletter digest from video topics.
    Produces HTML file ready for email service (Mailchimp, SendGrid, etc.)
    """

    NEWSLETTER_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "diagnostics", "newsletters"
    )

    def __init__(self, *args, **kwargs):
        os.makedirs(self.NEWSLETTER_DIR, exist_ok=True)

    def run(self, topics: list) -> dict:
        """
        Generate HTML newsletter from list of topics.
        Returns {newsletter_path, topic_count, generated_at}.
        Called by NewsletterAgent post-pipeline.
        """
        if not topics:
            topics = [{"title": "Latest Telugu News Update", "category": "general"}]

        now = datetime.now()
        date_str = now.strftime("%B %d, %Y")
        filename = f"newsletter_{now.strftime('%Y%m%d_%H%M')}.html"
        filepath = os.path.join(self.NEWSLETTER_DIR, filename)

        # Build HTML newsletter
        html = self._build_html(topics, date_str, now)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)

        return {
            "newsletter_path": filepath,
            "topic_count": len(topics),
            "generated_at": now.isoformat(),
            "filename": filename,
        }

    def _build_html(self, topics: list, date_str: str, now: datetime) -> str:
        """Build complete HTML email newsletter."""
        topic_rows = ""
        for i, topic in enumerate(topics[:10], 1):
            title = topic.get("title", "Untitled") if isinstance(topic, dict) else str(topic)
            category = topic.get("category", "news") if isinstance(topic, dict) else "news"
            topic_rows += f"""
            <tr>
                <td style="padding:12px 16px;border-bottom:1px solid #eee;font-size:15px;">
                    <strong>{i}. {title}</strong><br>
                    <span style="color:#888;font-size:13px;">{category.upper()}</span>
                </td>
            </tr>"""

        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width">
    <title>ViralDNA Newsletter — {date_str}</title>
</head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;margin:0 auto;background:#fff;">
    <!-- Header -->
    <tr>
        <td style="background:#C04020;padding:24px;text-align:center;">
            <h1 style="color:#fff;margin:0;font-size:24px;">ViralDNA</h1>
            <p style="color:#FFD6C0;margin:4px 0 0;font-size:14px;">Telugu Diaspora News Digest — {date_str}</p>
        </td>
    </tr>
    <!-- Intro -->
    <tr>
        <td style="padding:20px 16px 12px;">
            <p style="font-size:15px;color:#333;margin:0;">
                Namaste! Here are this week's top stories from the Telugu world.
                Watch the full breakdowns on our YouTube channel.
            </p>
        </td>
    </tr>
    <!-- Topics -->
    {topic_rows}
    <!-- CTA -->
    <tr>
        <td style="padding:20px 16px;text-align:center;">
            <a href="https://www.youtube.com/@ViralDNA"
               style="display:inline-block;background:#C04020;color:#fff;padding:12px 32px;
                      text-decoration:none;border-radius:6px;font-size:16px;font-weight:bold;">
                Watch on YouTube ▶
            </a>
        </td>
    </tr>
    <!-- Footer -->
    <tr>
        <td style="background:#0D0D0D;padding:16px;text-align:center;">
            <p style="color:#888;font-size:12px;margin:0;">
                ViralDNA — Telugu News for the Global Diaspora<br>
                <a href="#" style="color:#D6B300;">Unsubscribe</a> |
                <a href="#" style="color:#D6B300;">View in Browser</a>
            </p>
        </td>
    </tr>
</table>
</body>
</html>"""
        return html

    def execute(self, state):
        return state
