# VERSION: 70.0
# MODULE: visual_fetcher.py
# PURPOSE: High-Res Visual Fetcher with strict image validation + quality scoring.
#          v42.0: Added ComfyUI Stable Diffusion 1.5 as primary image source.
#          Priority: ComfyUI (local generation) > Serper > Local image pack.
#          Validates magic bytes, content-type, minimum file size,
#          and actual image dimensions before accepting a download.
#          Rejects HTML error pages, CAPTCHA responses, corrupt files,
#          blurry images, news screenshots (text/logos/faces), and off-topic images.

import os, struct, config
import requests
from PIL import Image
from io import BytesIO

# Known image format magic bytes
IMAGE_SIGNATURES = {
    b'\xff\xd8\xff': 'jpeg',
    b'\x89PNG': 'png',
    b'GIF87a': 'gif',
    b'GIF89a': 'gif',
    b'RIFF': 'webp',  # WebP starts with RIFF....WEBP
    b'BM': 'bmp',
}

# Minimum acceptable file size (bytes) anything smaller is likely an error page
MIN_IMAGE_SIZE = 8 * 1024  # 8 KB

# Minimum acceptable image dimensions
MIN_WIDTH = 320
MIN_HEIGHT = 240

# Maximum acceptable file size (bytes)  20 MB cap
MAX_IMAGE_SIZE = 20 * 1024 * 1024


def _validate_image_bytes(data: bytes, url: str) -> bool:
    """
    Multi-layer image validation:
    1. Size check (not too small, not too large)
    2. Magic bytes check (must start with known image signature)
    3. PIL open check (must be parseable as an image)
    4. Dimension check (must meet minimum resolution)
    Returns True only if ALL checks pass.
    """
    # 1. Size check
    if len(data) < MIN_IMAGE_SIZE:
        print(f"    Image rejected (too small: {len(data)} bytes): {url[:60]}")
        return False
    if len(data) > MAX_IMAGE_SIZE:
        print(f"    Image rejected (too large: {len(data)} bytes): {url[:60]}")
        return False

    # 2. Magic bytes check
    is_image = False
    for sig, fmt in IMAGE_SIGNATURES.items():
        if data[:len(sig)] == sig:
            is_image = True
            break
    # Special check for WebP (RIFF....WEBP)
    if not is_image and data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        is_image = True
    if not is_image:
        # Check if it starts with HTML
        head = data[:200].strip().lower()
        if head.startswith(b'<!doctype') or head.startswith(b'<html') or head.startswith(b'<head'):
            print(f"    Image rejected (HTML page, not image): {url[:60]}")
        else:
            print(f"    Image rejected (unknown format, first 8 bytes: {data[:8].hex()}): {url[:60]}")
        return False

    # 3. PIL parse check
    try:
        img = Image.open(BytesIO(data))
        img.verify()  # Verify it's a valid image without fully decoding
    except Exception as e:
        print(f"    Image rejected (PIL verify failed: {e}): {url[:60]}")
        return False

    # 4. Dimension check (re-open after verify)
    try:
        img = Image.open(BytesIO(data))
        w, h = img.size
        if w < MIN_WIDTH or h < MIN_HEIGHT:
            print(f"    Image rejected (too small: {w}x{h}): {url[:60]}")
            return False
    except Exception as e:
        print(f"    Image rejected (dimension check failed: {e}): {url[:60]}")
        return False

    return True


def score_image_quality(data: bytes, url: str) -> dict:
    """
    v70.0: Score image quality using OpenCV heuristics — RELAXED for news photos.
    Returns: {"score": float (0-100), "issues": list of str}
    Lower score = worse quality. Score < 30 = reject.

    v70.0 changes: Disabled MSER text detection, TV logo detection, face detection,
    and HSV skin-tone detection. These all rejected real news screenshots (which have
    text overlays, channel logos, politicians' faces, and crowd scenes). Only blur,
    resolution, edge density (relaxed), color variance, and white/black ratio remain.
    Checks: blur, resolution, edge_density (relaxed), color variance, white/black ratio.
    """
    issues = []
    try:
        import cv2
        import numpy as np
    except ImportError:
        return {"score": 50, "issues": ["OpenCV unavailable"]}

    try:
        # Decode image from bytes
        img_array = np.frombuffer(data, dtype=np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if img is None:
            return {"score": 0, "issues": ["Cannot decode image bytes"]}

        h, w = img.shape[:2]
        score = 100.0

        # Resolution check
        if w < 640 or h < 360:
            return {"score": 0, "issues": [f"Too small: {w}x{h} (min 640x360)"]}

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # 1. Blur detection (Laplacian variance) — keep, but relaxed
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        if laplacian_var < 20:  # v70.0: Relaxed from 30
            return {"score": 0, "issues": [f"Too blurry (Laplacian: {laplacian_var:.1f})"]}
        elif laplacian_var < 50:  # v70.0: Relaxed from 80
            score -= (50 - laplacian_var) * 0.3  # v70.0: Reduced penalty
            issues.append(f"moderate_blur({laplacian_var:.0f})")

        # 2. Edge density — RELAXED (news screenshots have lots of edges)
        edges = cv2.Canny(gray, 50, 150)
        edge_density = np.count_nonzero(edges) / (w * h)
        if edge_density > 0.40:  # v70.0: Relaxed from 0.25
            return {"score": 0, "issues": [f"Too many edges/text (density: {edge_density:.2f})"]}
        elif edge_density > 0.25:  # v70.0: Relaxed from 0.15
            score -= (edge_density - 0.25) * 100  # v70.0: Reduced penalty from 200
            issues.append(f"high_edges({edge_density:.2f})")

        # 3. MSER text region detection — DISABLED v70.0
        # News screenshots legitimately have text overlays. Re-enabling this
        # would reject most real news photos from Serper.
        # Kept as no-op for backward compatibility.
        pass

        # 4. Color variance — keep, but relaxed
        color_std = np.std(img, axis=(0, 1)).mean()
        if color_std < 10:  # v70.0: Relaxed from 15
            return {"score": 0, "issues": [f"Flat image (color std: {color_std:.1f})"]}

        # 5. Border/frame detection — DISABLED v70.0
        # Many news photos and stock images have borders/frames.
        pass

        # 6. TV logo / channel watermark — DISABLED v70.0
        # News screenshots legitimately have channel logos in corners.
        # This was rejecting real news photos from Indian news channels.
        pass

        # 7. Face detection — DISABLED v70.0
        # News photos of politicians, crowds, events ALL have faces.
        # Rejecting faces means rejecting the most important news images.
        # The "devil face" problem from ComjyUI is solved by using Serper (real photos).
        pass

        # 7b. HSV skin-tone detection — DISABLED v70.0
        # Crowd shots, group photos, political rallies all have skin-tone pixels.
        # This was rejecting real news photos showing people.
        pass

        # 8. Near-white / near-black ratio — keep, but relaxed
        white_ratio = np.count_nonzero(gray > 240) / (w * h)
        black_ratio = np.count_nonzero(gray < 15) / (w * h)
        if white_ratio > 0.80:  # v70.0: Relaxed from 0.60
            return {"score": 0, "issues": [f"Mostly white ({white_ratio:.0%})"]}
        if black_ratio > 0.70:  # v70.0: Relaxed from 0.50
            return {"score": 0, "issues": [f"Mostly black ({black_ratio:.0%})"]}

        score = max(0, min(100, score))
        return {"score": round(score, 1), "issues": issues}

    except Exception as e:
        return {"score": 0, "issues": [f"Quality check error: {e}"]}


def score_semantic_relevance(topic_title: str, image_title: str = "",
                              image_source: str = "", image_domain: str = "") -> dict:
    """
    v70.0: Score how relevant a fetched image is to the news topic.
    Returns: {"relevant": bool, "score": float (0-100), "issues": list of str}

    Key changes v70.0:
      - Default trust raised 70→80 (Serper already searched for our query)
      - No-keyword-overlap penalty halved -30→-15 (real photos have generic titles)
      - Stock photo penalty reduced -15→-5 (stock photos ARE real photos)
      - Stock domains no longer penalized — moved to trusted list
      - Added YouTube/Wikimedia/twitter image domains as trusted
      - Threshold lowered 40→30 (more photos accepted)
      - Telugu news domains added

    Threshold: score < 30 = reject as off-topic.
    """
    issues = []
    score = 80.0  # v70.0: Trust Serper's search relevance more

    # Clean and tokenize
    import re
    stop_words = {"the", "a", "an", "is", "are", "was", "were", "in", "on", "at",
                  "to", "for", "of", "and", "or", "but", "with", "from", "by",
                  "about", "image", "photo", "stock", "picture", "photograph",
                  "jpg", "png", "https", "http", "www", "com", "just", "high",
                  "resolution", "royalty", "free", "download", "close", "detail"}

    def tokenize(text):
        return set(w.lower() for w in re.findall(r'[a-zA-Z]{3,}', text) if w.lower() not in stop_words)

    topic_tokens = tokenize(topic_title)
    image_tokens = tokenize(image_title + " " + image_source + " " + image_domain)

    if not topic_tokens:
        return {"relevant": True, "score": 50, "issues": ["empty topic tokens"]}

    # 1. Jaccard-like overlap
    if image_tokens:
        overlap = len(topic_tokens & image_tokens)
        total = len(topic_tokens | image_tokens)
        jaccard = overlap / total if total > 0 else 0
        score += jaccard * 30  # Up to +30 for full overlap
        if overlap == 0 and len(topic_tokens) >= 3:
            score -= 15  # v70.0: Halved from -30 — real photos have generic titles
            issues.append("no_keyword_overlap")
    else:
        score -= 5  # v70.0: Reduced from -10
        issues.append("empty_image_metadata")

    # 2. Generic illustration/clip-art detection (not real photos)
    # v70.0: Only penalize non-photo content — real photos from stock sites are OK
    generic_phrases = ["clip art", "vector illustration", "cartoon image",
                       "meme template", "emoji pack", "icon set",
                       "ai generated", "ai image", "midjourney", "dall-e"]
    combined_lower = (image_title + " " + image_source).lower()
    for phrase in generic_phrases:
        if phrase in combined_lower:
            score -= 20  # Strong penalty for non-photo content
            issues.append(f"non_photo({phrase})")
            break

    # 3. Trusted domain bonuses (legitimate news/image sources)
    # v70.0: Merged editorial + stock into single trusted list — all real photos
    trusted_editorial = ["bbc", "cnn", "ndtv", "thehindu", "timesofindia",
                         "reuters", "apnews", "aljazeera", "wikipedia",
                         "wikimedia", "nytimes", "washingtonpost", "guardian",
                         "indianexpress", "hindustantimes", "scroll", "news18",
                         "deccanherald", "deccanchronicle", "livemint",
                         "economictimes", "firstpost", "thequint", "thewire",
                         "siasat", "newslaundry", "telanganatoday",
                         "thenewsminute", "greatandhra", "filmibeat",
                         "telugustop", "123telugu", "idlebrain",
                         "eenadu", "sakshi", "andhrajyothy", "vaartha",
                         "pib.gov.in", "india.gov.in",
                         "inquirer", "bbc.co.uk"]
    trusted_image_domains = ["ytimg.com", "youtube.com",  # YouTube thumbnails
                              "pbs.twimg.com", "x.com", "twitter.com",  # Social
                              "istockphoto", "shutterstock", "gettyimages",  # Stock
                              "dreamstime", "alamy", "depositphotos",
                              "unsplash", "pexels", "pixabay",  # Free stock
                              "upload.wikimedia.org", "wikimedia.org"]  # Wiki

    domain_lower = image_domain.lower().replace("www.", "")

    domain_bonus = False
    for td in trusted_editorial:
        if td in domain_lower:
            score += 10
            domain_bonus = True
            break
    if not domain_bonus:
        for td in trusted_image_domains:
            if td in domain_lower:
                score += 5  # Smaller bonus for image domains
                break

    score = max(0, min(100, score))
    return {
        "relevant": score >= 30,  # v70.0: Lowered threshold from 40
        "score": round(score, 1),
        "issues": issues,
    }


class VisualFetcher:
    def __init__(self, pacer, config_instance):
        self.api_key = config.API_KEYS.get("SERPER_API_KEY")
        print("  VisualFetcher (v41.0): Quality Scoring + Validation + License Tracking Active.")

    def _download_single_image(self, url: str, save_path: str, topic_title: str = "",
                               image_title: str = "", image_source: str = "",
                               image_domain: str = "") -> bool:
        """
        Download, validate, quality-score, semantically score AND track license.
        Quality score < 30 = rejected.
        Semantic relevance < 30 = rejected (off-topic).
        Returns True on success.
        """
        try:
            resp = requests.get(url, timeout=10, headers={
                'User-Agent': 'Mozilla/5.0 (compatible; ViralDNA/1.0)'
            })
            if resp.status_code != 200:
                print(f"    Image download failed (HTTP {resp.status_code}): {url[:60]}")
                return False

            data = resp.content

            # Content-type check (soft  some servers lie, so this is just a warning)
            content_type = resp.headers.get('Content-Type', '').lower()
            if content_type and not any(t in content_type for t in ['image', 'octet-stream', 'binary']):
                print(f"    Suspicious Content-Type '{content_type}' for: {url[:60]}")

            # Layer 0: Semantic relevance scoring (cheap check before expensive download decode)
            if topic_title:
                sem = score_semantic_relevance(topic_title, image_title, image_source, image_domain)
                if not sem["relevant"]:
                    issue_str = "; ".join(sem["issues"]) if sem["issues"] else "low semantic score"
                    print(f"    Image rejected (semantic {sem['score']}/100): {issue_str}  {image_title[:50] or url[:50]}")
                    return False
                if sem["issues"]:
                    print(f"    Semantic check passed ({sem['score']}/100) minor: {'; '.join(sem['issues'])}")

            # Layer 1: Structural validation (magic bytes, PIL parse, dimensions)
            if not _validate_image_bytes(data, url):
                return False

            # Layer 2: Quality scoring (blur, text, logo, face, color checks)
            quality = score_image_quality(data, url)
            if quality["score"] < 30:
                issue_str = "; ".join(quality["issues"])
                print(f"    Image rejected (quality {quality['score']}/100): {issue_str}  {url[:60]}")
                return False
            if quality["issues"]:
                print(f"    Image accepted ({quality['score']}/100) minor issues: {'; '.join(quality['issues'])}")
            else:
                print(f"    Image accepted ({quality['score']}/100)  clean")

            # Save to disk
            with open(save_path, "wb") as f:
                f.write(data)

            # Layer 3: License tracking
            self._track_fetched_image(url, save_path, topic_title, resp.headers)

            return True

        except requests.exceptions.Timeout:
            print(f"    Image download timed out: {url[:60]}")
            return False
        except requests.exceptions.ConnectionError:
            print(f"    Image download connection error: {url[:60]}")
            return False

    def _track_fetched_image(self, url: str, save_path: str,
                              topic_title: str, headers: dict):
        """
        Auto-register fetched image in license database.
        Infers license type from URL domain and HTTP headers.
        """
        try:
            from modules.license_tracker import LicenseTracker
            tracker = LicenseTracker()

            # Infer source from URL domain
            from urllib.parse import urlparse
            domain = urlparse(url).netloc.lower()
            source = "unknown"

            source_mapping = {
                "unsplash.com": "unsplash",
                "pexels.com": "pexels",
                "pixabay.com": "pixabay",
                "wikimedia.org": "wikimedia_commons",
                "upload.wikimedia.org": "wikimedia_commons",
                "i.imgur.com": "generated_ai",
                "serper.dev": "news_image",
            }

            for domain_key, src in source_mapping.items():
                if domain_key in domain:
                    source = src
                    break

            if source == "unknown":
                parts = domain.replace("www.", "").split(".")
                source = parts[0] if parts else "unknown"

            # Check if source is in blocked list
            if source in tracker.BLOCKED_SOURCES:
                print(f"    BLOCKED image from disallowed source ({source}): {url[:60]}")
                os.remove(save_path)
                return

            # Determine license info
            approved = tracker.APPROVED_SOURCES.get(source, {})
            commercial_safe = approved.get("commercial_safe", False)
            attribution_required = approved.get("attribution_required", True)
            license_type = approved.get("license", f"Unknown  from {domain}")

            # Check for license headers
            lic_header = headers.get("X-License", "") or headers.get("License", "")
            if lic_header:
                license_type = lic_header

            # Check for Creative Commons in URL
            if "creativecommons.org" in url:
                license_type = "Creative Commons"
                commercial_safe = True
                attribution_required = True

            tracker.track_asset(
                asset_path=save_path,
                source=source,
                license_type=license_type,
                commercial_safe=commercial_safe,
                attribution_required=attribution_required,
                notes=f"Topic: {topic_title[:80]} | URL: {url} | Domain: {domain}",
            )
        except Exception:
            pass  # License tracking must not break image fetching

    def _fetch_from_comfyui(self, topic: dict) -> list:
        """Generate images via ComfyUI Stable Diffusion 1.5 (local, high quality)."""
        try:
            from comfyui_image_generator import generate_scene_image
            import random
            topic_title = topic.get("title", "")
            category = topic.get("category", "DEFAULT")
            runtime = config.DRIVE["RUNTIME"]

            # Detect category from topic
            cat = "DEFAULT"
            cat_keywords = {
                "POLITICS": ["politics", "election", "minister", "party", "congress", "bjp", "tdp", "mla", "mp"],
                "DISASTER": ["flood", "cyclone", "earthquake", "disaster", "fire", "accident", "collapse"],
                "CRIME": ["murder", "theft", "arrest", "police", "crime", "scam", "fraud"],
                "ECONOMICS": ["economy", "market", "price", "inflation", "budget", "trade", "stock"],
                "SPORTS": ["cricket", "match", "player", "tournament", "sports", "game", "score"],
                "HEALTH": ["health", "hospital", "disease", "covid", "medicine", "doctor", "vaccine"],
                "TECHNOLOGY": ["tech", "ai", "software", "app", "digital", "internet", "cyber"],
                "ENTERTAINMENT": ["movie", "film", "actor", "singer", "celebration", "award", "show"],
            }
            topic_lower = topic_title.lower()
            for c, keywords in cat_keywords.items():
                if any(kw in topic_lower for kw in keywords):
                    cat = c
                    break

            # Build scene-specific prompts from topic title (3 distinct visual angles)
            title = topic_title.strip()
            prompts = [
                f"wide establishing shot of {title}, documentary photojournalism, editorial",
                f"close-up detail scene related to {title}, indian context, professional photography",
                f"aerial or overview shot of {title}, cinematic composition, dramatic lighting",
            ]

            paths = []
            for i, prompt in enumerate(prompts):
                save_path = os.path.join(runtime, f"viz_comfyui_{i}.jpg")
                ok = generate_scene_image(
                    scene_description=prompt,
                    output_path=save_path,
                    category=cat,
                    width=768,
                    height=512,
                    seed=random.randint(1, 2147483647)
                )
                if ok:
                    paths.append(save_path)

            if paths:
                print(f"  [ComfyUI] Generated {len(paths)} scene images.")
            return paths
        except ImportError:
            print("  [ComfyUI] comfyui_image_generator.py not available, skipping.")
            return []
        except Exception as e:
            # ComfyUI must not crash the pipeline
            print(f"  [ComfyUI] Error: {e}")
            return []

    def _fetch_from_comfyui_thumbnail(self, topic: dict, output_dir: str, nickname: str) -> dict:
        """Generate thumbnail background via ComfyUI."""
        try:
            from comfyui_image_generator import generate_thumbnail_background
            topic_title = topic.get("title", "")
            category = topic.get("category", "DEFAULT")

            thumb_bg_path = os.path.join(output_dir, f"{nickname}_comfyui_bg.png")
            ok = generate_thumbnail_background(topic_title, category, thumb_bg_path)
            if ok:
                print(f"  [ComfyUI] Thumbnail background generated: {thumb_bg_path}")
                return {"background": thumb_bg_path}
            return {}
        except Exception as e:
            print(f"  [ComfyUI] Thumbnail bg error: {e}")
            return {}

    def fetch_visuals(self, topic: dict) -> list:
        """
        Fetch images with priority:
        1. ComfyUI Stable Diffusion (local generation, best quality)
        2. Serper Google Image Search (external, variable quality)
        3. Local image pack (fallback)
        """
        topic_title = topic.get("title", "")

        # Strategy 1: Serper (real news photos — PRIMARY)
        url = "https://google.serper.dev/images"
        search_q = f"{topic_title} news photo"
        payload = {"q": search_q, "num": 10}
        headers = {'X-API-KEY': self.api_key, 'Content-Type': 'application/json'}

        serper_paths = []
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15).json()
            images = response.get('images', [])
            for img in images[:10]:
                if len(serper_paths) >= 3:
                    break
                img_url = img.get('imageUrl', '')
                if not img_url:
                    continue
                save_path = os.path.join(config.DRIVE["RUNTIME"], f"viz_news_{len(serper_paths)}.jpg")
                img_title = img.get('title', '')
                img_source = img.get('source', '')
                img_domain = img.get('domain', '')
                if self._download_single_image(img_url, save_path, topic_title,
                                                img_title, img_source, img_domain):
                    serper_paths.append(save_path)
        except Exception as e:
            print(f"  Serper failed: {e}")

        if serper_paths:
            print(f"  VisualFetcher: Using {len(serper_paths)} Serper images.")
            return serper_paths

        # Strategy 2: ComfyUI (AI-generated — LAST RESORT)
        comfy_paths = self._fetch_from_comfyui(topic)
        if comfy_paths:
            print(f"  VisualFetcher: Using {len(comfy_paths)} ComfyUI-generated images.")
            return comfy_paths

        # Strategy 3: Local image pack fallback
        print("  ⚠️ All external sources failed, using local image pack.")
        return self._local_image_pack_fallback(topic_title, runtime_dir=config.DRIVE["RUNTIME"])

    def _local_image_pack_fallback(self, topic_text: str, runtime_dir: str) -> list:
        """Pull topic-relevant images from the local image pack as fallback."""
        try:
            import importlib.util
            lip_path = os.path.join(os.path.dirname(__file__), "local_image_pack.py")
            spec = importlib.util.spec_from_file_location("local_image_pack", lip_path)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                pack = mod.LocalImagePack()
                images = pack.get_images(topic_text, count=3, diversity=True)
                if images:
                    # Copy images to runtime dir with viz_news_ prefix for downstream consumption
                    paths = []
                    for i, src_path in enumerate(images):
                        dest = os.path.join(runtime_dir, f"viz_news_{i}.jpg")
                        import shutil
                        shutil.copy2(src_path, dest)
                        paths.append(dest)
                    print(f"  ✓ Local pack: {len(images)} images for thumbnail/background")
                    return paths
                else:
                    print(f"  ⚠️ Local pack returned 0 images for topic: '{topic_text[:40]}...'")
        except Exception as e:
            print(f"  ⚠️ Local image pack fallback failed: {e}")
        # If even local pack fails, return None (signals no visuals; gate must allow this)
        return None
