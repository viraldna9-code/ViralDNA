#!/usr/bin/env python3
"""
ViralDNA WordPress Auto-Publisher
Creates blog posts on theviraldna.mbitebyte.com from pipeline output.
Uses WP-CLI (preferred) or falls back to WP REST API.

Usage:
    from wordpress_publisher import WordPressPublisher
    publisher = WordPressPublisher()
    result = publisher.create_post(
        title="Breaking: Topic Name",
        content="Full article content...",
        excerpt="Short summary",
        categories=["Breaking News"],
        tags=["news", "viral", "topic"],
        thumbnail_path="/path/to/thumbnail.jpg",
        youtube_url="https://youtube.com/watch?v=..."
    )
"""

import subprocess
import json
import os
import requests
from pathlib import Path
from datetime import datetime


class WordPressPublisher:
    """Publishes content to WordPress via WP-CLI or REST API.

    Authentication: Uses cookie-based auth (wp-login.php session) because
    the admin user has full UI capabilities but REST Basic Auth is blocked
    by the security plugin. Falls back to WP-CLI if available on the server.
    """

    def __init__(self, site_url="https://theviraldna.mbitebyte.com",
                 wp_path="/home/church/public_html/sites/theviraldna",
                 admin_user="theviraldna_admin",
                 admin_pass="b7qNRCsG93b!"):
        self.site_url = site_url.rstrip("/")
        self.wp_path = wp_path
        self.admin_user = admin_user
        self.admin_pass = admin_pass
        self._wp_cli_available = None
        self._session = None
        self._nonce = None

    def _check_wp_cli(self):
        """Check if WP-CLI is available on the server."""
        if self._wp_cli_available is not None:
            return self._wp_cli_available
        try:
            result = subprocess.run(
                "which wp 2>/dev/null",
                shell=True, capture_output=True, text=True, timeout=5
            )
            self._wp_cli_available = bool(result.stdout.strip())
        except Exception:
            self._wp_cli_available = False
        return self._wp_cli_available

    def _login(self):
        """Log in to WordPress via wp-login.php and return a session with cookies.

        The admin user has full dashboard capabilities but REST Basic Auth is
        blocked by the security plugin. Cookie-based auth + X-WP-Nonce header
        mirrors what the browser does and works correctly.
        """
        if self._session is not None and self._nonce is not None:
            return self._session

        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

        login_url = f"{self.site_url}/wp-login.php"
        payload = {
            "log": self.admin_user,
            "pwd": self.admin_pass,
            "rememberme": "forever",
            "wp-submit": "Log In",
            "redirect_to": f"{self.site_url}/wp-admin/",
        }

        resp = session.post(login_url, data=payload, timeout=30, allow_redirects=False)

        # Check if login succeeded (302 redirect to wp-admin = success)
        logged_in = False
        if resp.status_code == 302 and "wp-admin" in resp.headers.get("Location", ""):
            logged_in = True

        # Fallback: check cookies for wordpress_logged_in_* cookie
        if not logged_in:
            for cookie in session.cookies:
                if cookie.name.startswith("wordpress_logged_in_"):
                    logged_in = True
                    break

        if not logged_in:
            raise RuntimeError(
                f"WordPress login failed: HTTP {resp.status_code}, "
                f"cookies={[c.name for c in session.cookies]}"
            )

        # Fetch REST nonce for cookie-based auth
        nonce_resp = session.post(
            f"{self.site_url}/wp-admin/admin-ajax.php?action=rest-nonce",
            timeout=15
        )
        nonce = nonce_resp.text.strip()

        if nonce and len(nonce) == 10:
            self._session = session
            self._nonce = nonce
        else:
            raise RuntimeError(
                f"Failed to obtain REST nonce: got '{nonce}' "
                f"(status {nonce_resp.status_code})"
            )

        return self._session

    def _get_session(self):
        """Get or create an authenticated session."""
        return self._login()

    def _get_headers(self, content_type=None):
        """Get request headers with nonce for cookie-based REST API auth."""
        self._get_session()
        headers = {"X-WP-Nonce": self._nonce}
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def _rest_api_post(self, endpoint, data):
        """Make a POST request to WP REST API using cookie + nonce auth."""
        session = self._get_session()
        url = f"{self.site_url}/wp-json/wp/v2/{endpoint}"
        try:
            resp = session.post(url, json=data, headers=self._get_headers("application/json"), timeout=30)
            if resp.status_code in (200, 201):
                return resp.json(), None
            return None, f"HTTP {resp.status_code}: {resp.text[:500]}"
        except Exception as e:
            return None, str(e)

    def _rest_api_get(self, endpoint, params=None):
        """Make a GET request to WP REST API using cookie + nonce auth."""
        session = self._get_session()
        url = f"{self.site_url}/wp-json/wp/v2/{endpoint}"
        try:
            resp = session.get(url, params=params, headers=self._get_headers(), timeout=30)
            if resp.status_code == 200:
                return resp.json(), None
            return None, f"HTTP {resp.status_code}: {resp.text[:500]}"
        except Exception as e:
            return None, str(e)

    def _rest_api_upload(self, file_path, filename=None):
        """Upload a file to WP REST API media library using cookie + nonce auth."""
        session = self._get_session()
        url = f"{self.site_url}/wp-json/wp/v2/media"
        filename = filename or Path(file_path).name
        try:
            with open(file_path, "rb") as f:
                files = {"file": (filename, f, "image/jpeg")}
                resp = session.post(url, files=files, headers=self._get_headers(), timeout=60)
            if resp.status_code in (200, 201):
                return resp.json(), None
            return None, f"HTTP {resp.status_code}: {resp.text[:500]}"
        except Exception as e:
            return None, str(e)

    def _wp_cli_cmd(self, command):
        """Run a WP-CLI command."""
        if not self._check_wp_cli():
            return None, "WP-CLI not available"
        try:
            full_cmd = f"cd {self.wp_path} && wp {command} --allow-root"
            result = subprocess.run(
                full_cmd, shell=True, capture_output=True, text=True, timeout=60
            )
            if result.returncode == 0:
                return result.stdout.strip(), None
            return None, result.stderr.strip()
        except subprocess.TimeoutExpired:
            return None, "Command timed out"
        except Exception as e:
            return None, str(e)

    def upload_image(self, image_path):
        """Upload a featured image to WordPress media library.
        Returns the attachment ID.
        """
        image_path = Path(image_path)
        if not image_path.exists():
            return None, f"File not found: {image_path}"

        # Try WP-CLI first
        if self._check_wp_cli():
            output, err = self._wp_cli_cmd(
                f'media import "{image_path}" --porcelain'
            )
            if err is None and output:
                try:
                    return int(output.strip()), None
                except ValueError:
                    pass

        # Fallback: Cookie-based REST API upload
        result, err = self._rest_api_upload(str(image_path), image_path.name)
        if err:
            return None, err
        return result.get("id"), None

    def _get_category_id(self, category_name):
        """Get or create a category by name, return its ID."""
        import html
        # Normalize: decode HTML entities for comparison (WP returns &amp; for &)
        normalized = html.unescape(category_name).lower()

        # Try WP-CLI
        if self._check_wp_cli():
            output, err = self._wp_cli_cmd(
                f'term list category --search="{category_name}" --format=json --fields=term_id,name'
            )
            if err is None and output:
                try:
                    terms = json.loads(output)
                    for term in terms:
                        if html.unescape(term["name"]).lower() == normalized:
                            return term["term_id"], None
                except json.JSONDecodeError:
                    pass

        # Fallback: Cookie-based REST API
        # Search with broad term (first word) to catch variants like "News & Politics"
        search_term = category_name.split("&")[0].strip().split()[0]
        data, err = self._rest_api_get("categories", params={
            "search": search_term, "per_page": 100
        })
        if err:
            return None, err
        for cat in data:
            if html.unescape(cat["name"]).lower() == normalized:
                return cat["id"], None

        # Category not found — create it
        new_data, err = self._rest_api_post("categories", {"name": category_name})
        if err:
            return None, err
        return new_data["id"], None

    def _get_tag_id(self, tag_name):
        """Get or create a tag by name, return its ID."""
        # Try WP-CLI
        if self._check_wp_cli():
            output, err = self._wp_cli_cmd(
                f'term list post_tag --search="{tag_name}" --format=json --fields=term_id,name'
            )
            if err is None and output:
                try:
                    terms = json.loads(output)
                    for term in terms:
                        if term["name"].lower() == tag_name.lower():
                            return term["term_id"], None
                except json.JSONDecodeError:
                    pass

        # Fallback: Cookie-based REST API
        data, err = self._rest_api_get("tags", params={
            "search": tag_name, "per_page": 1
        })
        if err:
            return None, err
        if data:
            return data[0]["id"], None

        # Tag not found — create it
        new_data, err = self._rest_api_post("tags", {"name": tag_name})
        if err:
            return None, err
        return new_data["id"], None

    def create_post(self, title, content, excerpt="",
                    categories=None, tags=None,
                    thumbnail_path=None, youtube_url=None,
                    status="publish"):
        """Create a WordPress post.

        Args:
            title: Post title
            content: Full post content (HTML)
            excerpt: Short excerpt
            categories: List of category names
            tags: List of tag names
            thumbnail_path: Path to featured image
            youtube_url: YouTube URL to embed at top
            status: 'publish', 'draft', 'pending'

        Returns:
            dict with 'success', 'post_id', 'url', 'errors'
        """
        errors = []
        result = {"success": False, "post_id": None, "url": None, "errors": []}

        # Build post content with YouTube embed if provided
        full_content = ""
        if youtube_url:
            # WordPress auto-embeds YouTube URLs on their own line
            full_content += f"\n\n{youtube_url}\n\n"
        full_content += content

        # Prepare post data
        post_data = {
            "title": title,
            "content": full_content,
            "excerpt": excerpt or content[:150],
            "status": status,
        }

        if categories:
            cat_ids = []
            for cat_name in categories:
                cat_id, err = self._get_category_id(cat_name)
                if err:
                    errors.append(f"Category error: {err}")
                else:
                    cat_ids.append(cat_id)
            if cat_ids:
                post_data["categories"] = cat_ids

        if tags:
            tag_ids = []
            for tag_name in tags:
                tag_id, err = self._get_tag_id(tag_name)
                if err:
                    errors.append(f"Tag error: {err}")
                else:
                    tag_ids.append(tag_id)
            if tag_ids:
                post_data["tags"] = tag_ids

        # Upload featured image
        if thumbnail_path and Path(thumbnail_path).exists():
            img_id, err = self.upload_image(thumbnail_path)
            if err:
                errors.append(f"Image upload error: {err}")
            else:
                post_data["featured_media"] = img_id

        # Try WP-CLI first
        if self._check_wp_cli():
            # Write post data to temp file for WP-CLI
            tmp_file = f"/tmp/vdna-wp-post-{os.getpid()}.json"
            with open(tmp_file, "w") as f:
                json.dump(post_data, f)

            cmd = f"post create {tmp_file} --porcelain"
            output, err = self._wp_cli_cmd(cmd)
            os.unlink(tmp_file)

            if err is None and output:
                try:
                    post_id = int(output.strip())
                    result["success"] = True
                    result["post_id"] = post_id
                    result["url"] = f"{self.site_url}/?p={post_id}"
                    result["errors"] = errors if errors else None
                    return result
                except ValueError:
                    pass
            errors.append(f"WP-CLI error: {err}")

        # Fallback: REST API
        api_result, err = self._rest_api_post("posts", post_data)
        if err:
            errors.append(f"REST API error: {err}")
            result["errors"] = errors
            return result

        result["success"] = True
        result["post_id"] = api_result.get("id")
        result["url"] = api_result.get("link")
        result["errors"] = errors if errors else None
        return result

    def create_news_post(self, video_data):
        """Create a news blog post from pipeline video data.

        Args:
            video_data: dict with keys:
                - title: Video title
                - description: Video description/transcript
                - topic: Topic category
                - thumbnail: Path to thumbnail image
                - youtube_url: YouTube video URL
                - tags: List of tags

        Returns:
            dict with success, post_id, url, errors
        """
        title = video_data.get("title", "Breaking News Update")
        description = video_data.get("description", "")
        topic = video_data.get("topic", "News & Politics")
        thumbnail = video_data.get("thumbnail")
        youtube_url = video_data.get("youtube_url")
        tags = video_data.get("tags", [])

        # Build article content
        content_parts = []

        # Lead paragraph
        lead = description[:300] if description else "Stay informed with the latest breaking news."
        content_parts.append(f"<p><strong>{lead}</strong></p>")

        # Full description
        if len(description) > 300:
            content_parts.append(f"<p>{description[300:]}</p>")

        # Key takeaways section
        content_parts.append("<h2>Key Takeaways</h2>")
        content_parts.append("<ul>")
        # Generate takeaways from description sentences
        sentences = description.replace("\n", " ").split(". ")
        for i, sentence in enumerate(sentences[:5]):
            if len(sentence.strip()) > 20:
                content_parts.append(f"<li>{sentence.strip()}.</li>")
        content_parts.append("</ul>")

        # CTA
        content_parts.append(
            '<p><em>Subscribe to <a href="https://www.youtube.com/@TheViralDNA">'
            "The ViralDNA on YouTube</a> for daily video coverage.</em></p>"
        )

        content = "\n".join(content_parts)

        # Map topic to category
        category_map = {
            "politics": "News & Politics",
            "news": "News & Politics",
            "breaking": "Breaking News",
            "world": "World News",
            "tech": "Technology",
            "technology": "Technology",
            "economy": "Economy",
            "business": "Economy",
            "viral": "Viral Stories",
            "trending": "Viral Stories",
        }
        category = category_map.get(topic.lower(), "News & Politics")

        return self.create_post(
            title=title,
            content=content,
            excerpt=description[:150] if description else title,
            categories=[category],
            tags=tags or [topic.lower()],
            thumbnail_path=thumbnail,
            youtube_url=youtube_url,
            status="publish"
        )


# Convenience function for pipeline integration
def publish_video_to_blog(video_data):
    """One-liner to publish a video to the blog.
    Called from the pipeline after YouTube upload.
    """
    publisher = WordPressPublisher()
    return publisher.create_news_post(video_data)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        # Test with sample data
        test_data = {
            "title": "Test: Breaking News Coverage",
            "description": "This is a test article from the ViralDNA pipeline. "
                          "It verifies the WordPress auto-publishing integration is working correctly.",
            "topic": "news",
            "thumbnail": None,
            "youtube_url": None,
            "tags": ["test", "news"]
        }
        pub = WordPressPublisher()
        result = pub.create_news_post(test_data)
        print(json.dumps(result, indent=2))
    else:
        print("Usage: python wordpress_publisher.py --test")
        print("\nThis module is designed to be imported into the ViralDNA pipeline.")
        print("Use: from wordpress_publisher import publish_video_to_blog")
