#!/usr/bin/env python3
"""
content_registry.py - Unified Video + Blog Content Tracking
============================================================
Tracks each "content unit" (one topic -> video + blog post) as a single entity
so analytics can answer "how did this topic perform across ALL platforms."

Integrates:
- Video metrics (from YouTube Analytics API / growth ledger)
- Blog metrics (from WordPress REST API / analytics)
- Shared content_id links them both
"""

import os
import json
import hashlib
from datetime import datetime
from zoneinfo import ZoneInfo

_IST = ZoneInfo("Asia/Kolkata")
REGISTRY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "analytics", "content_registry.json")


def generate_content_id(title: str) -> str:
    """Generate a stable content ID from a topic title."""
    return hashlib.md5(title.encode()).hexdigest()[:12]


class ContentRegistry:
    """Tracks each topic's performance across video + blog."""

    def __init__(self, registry_path=None):
        self.registry_path = registry_path or REGISTRY_PATH
        self.data = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.registry_path):
            try:
                with open(self.registry_path) as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {"entries": [], "last_updated": None}

    def _save(self):
        self.data["last_updated"] = datetime.now(_IST).isoformat()
        os.makedirs(os.path.dirname(self.registry_path), exist_ok=True)
        with open(self.registry_path, "w") as f:
            json.dump(self.data, f, indent=2, default=str)

    def register_content_unit(self, content_id: str, title: str, youtube_url: str = None,
                               blog_url: str = None, blog_post_id: int = None,
                               keyword: str = None, category: str = None) -> dict:
        """Register a new content unit linking video + blog."""
        entry = {
            "content_id": content_id,
            "title": title,
            "created_at": datetime.now(_IST).isoformat(),
            "youtube_url": youtube_url,
            "youtube_video_id": self._extract_yt_id(youtube_url) if youtube_url else None,
            "blog_url": blog_url,
            "blog_post_id": blog_post_id,
            "keyword": keyword,
            "category": category,
            "metrics": {
                "video": {"views": None, "ctr": None, "avg_view_duration": None, "likes": None},
                "blog": {"views": None, "comments": None, "word_count": None},
            },
            "synergy": {
                "video_to_blog_clicks": None,  # TODO: UTM tracking
                "blog_to_video_clicks": None,
            }
        }
        self.data["entries"].append(entry)
        self._save()
        return entry

    def update_video_metrics(self, content_id: str, views=None, ctr=None,
                              avg_view_duration=None, likes=None):
        """Update video side metrics for a content unit."""
        entry = self._find_entry(content_id)
        if entry:
            m = entry["metrics"]["video"]
            if views is not None: m["views"] = views
            if ctr is not None: m["ctr"] = ctr
            if avg_view_duration is not None: m["avg_view_duration"] = avg_view_duration
            if likes is not None: m["likes"] = likes
            self._save()

    def update_blog_metrics(self, content_id: str, views=None, comments=None):
        """Update blog side metrics for a content unit."""
        entry = self._find_entry(content_id)
        if entry:
            m = entry["metrics"]["blog"]
            if views is not None: m["views"] = views
            if comments is not None: m["comments"] = comments
            self._save()

    def get_content_unit(self, content_id: str) -> dict:
        return self._find_entry(content_id)

    def get_all_units(self) -> list:
        return self.data.get("entries", [])

    def get_top_performing(self, platform="combined", limit=10) -> list:
        """
        Get top performing content units.
        platform: 'video', 'blog', or 'combined'
        """
        entries = self.data.get("entries", [])
        if platform == "video":
            scored = [(e, e["metrics"]["video"].get("views") or 0) for e in entries]
        elif platform == "blog":
            scored = [(e, e["metrics"]["blog"].get("views") or 0) for e in entries]
        else:  # combined
            scored = [(e, (e["metrics"]["video"].get("views") or 0) +
                       (e["metrics"]["blog"].get("views") or 0)) for e in entries]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [e for e, _ in scored[:limit]]

    def get_synergy_report(self) -> dict:
        """Report on video↔blog cross-pollination."""
        entries = self.data.get("entries", [])
        total = len(entries)
        has_both = sum(1 for e in entries if e.get("youtube_url") and e.get("blog_url"))
        has_video_only = sum(1 for e in entries if e.get("youtube_url") and not e.get("blog_url"))
        has_blog_only = sum(1 for e in entries if not e.get("youtube_url") and e.get("blog_url"))

        return {
            "total_content_units": total,
            "video_and_blog": has_both,
            "video_only": has_video_only,
            "blog_only": has_blog_only,
            "integration_rate": round(has_both / total * 100, 1) if total > 0 else 0,
        }

    def _find_entry(self, content_id: str) -> dict:
        for e in self.data.get("entries", []):
            if e["content_id"] == content_id:
                return e
        return None

    @staticmethod
    def _extract_yt_id(url: str) -> str:
        """Extract video ID from various YouTube URL formats."""
        if not url:
            return None
        if "v=" in url:
            return url.split("v=")[-1].split("&")[0]
        if "youtu.be/" in url:
            return url.split("youtu.be/")[-1].split("?")[0]
        return None


def register_from_pipeline(title: str, youtube_url: str = None, blog_url: str = None,
                             blog_post_id: int = None, keyword: str = None,
                             category: str = None) -> dict:
    """Convenience: register a content unit from pipeline after video+blog publish."""
    reg = ContentRegistry()
    cid = generate_content_id(title)
    entry = reg.register_content_unit(
        content_id=cid,
        title=title,
        youtube_url=youtube_url,
        blog_url=blog_url,
        blog_post_id=blog_post_id,
        keyword=keyword,
        category=category,
    )
    return entry


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--synergy":
        reg = ContentRegistry()
        report = reg.get_synergy_report()
        print(json.dumps(report, indent=2))
    elif len(sys.argv) > 1 and sys.argv[1] == "--list":
        reg = ContentRegistry()
        for e in reg.get_all_units():
            print(f"  [{e['content_id']}] {e['title'][:60]}")
            print(f"    Video: {e.get('youtube_url', 'N/A')}  Blog: {e.get('blog_url', 'N/A')}")
    else:
        reg = ContentRegistry()
        print(f"Content Registry: {len(reg.get_all_units())} entries")
        print("Usage: python3 content_registry.py [--synergy|--list]")
