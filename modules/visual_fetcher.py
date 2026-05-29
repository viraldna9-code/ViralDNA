# VERSION: 41.0
# MODULE: visual_fetcher.py
# PURPOSE: High-Res Visual Fetcher with strict image validation + quality scoring.
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
    Score image quality using OpenCV heuristics.
    Returns: {"score": float (0-100), "issues": list of str}
    Lower score = worse quality. Score < 30 = reject.
    Checks: blur, text/edges, color variance, border mismatch,
            TV logo in corners, face detection, white/black ratio.
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

        # 1. Blur detection (Laplacian variance)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        if laplacian_var < 30:
            return {"score": 0, "issues": [f"Too blurry (Laplacian: {laplacian_var:.1f})"]}
        elif laplacian_var < 80:
            score -= (80 - laplacian_var) * 0.5
            issues.append(f"moderate_blur({laplacian_var:.0f})")

        # 2. Text / overlay detection  Canny edge density
        edges = cv2.Canny(gray, 50, 150)
        edge_density = np.count_nonzero(edges) / (w * h)
        if edge_density > 0.25:
            return {"score": 0, "issues": [f"Too many edges/text (density: {edge_density:.2f})"]}
        elif edge_density > 0.15:
            score -= (edge_density - 0.15) * 200
            issues.append(f"high_edges({edge_density:.2f})")

        # 3. MSER text region detection
        try:
            mser = cv2.MSER_create()
            regions, _ = mser.detectRegions(gray)
            text_like = [r for r in regions if 20 < len(r) < 500]
            if len(text_like) > 80:
                return {"score": 0, "issues": [f"MSER text regions: {len(text_like)}"]}
            elif len(text_like) > 40:
                score -= (len(text_like) - 40) * 0.3
                issues.append(f"mser_text({len(text_like)})")
        except Exception:
            pass

        # 4. Color variance
        color_std = np.std(img, axis=(0, 1)).mean()
        if color_std < 15:
            return {"score": 0, "issues": [f"Flat image (color std: {color_std:.1f})"]}

        # 5. Border/frame detection
        border_size = 10
        top_border = img[:border_size, :, :].mean()
        bottom_border = img[-border_size:, :, :].mean()
        left_border = img[:, :border_size, :].mean()
        right_border = img[:, -border_size:, :].mean()
        border_avg = (top_border + bottom_border + left_border + right_border) / 4
        center_avg = img[h//4:3*h//4, w//4:3*w//4, :].mean()
        if abs(border_avg - center_avg) > 80:
            score -= 20
            issues.append("border_mismatch")

        # 6. TV logo / channel watermark in corners
        corner_size = min(w, h) // 6
        corners = [
            gray[:corner_size, :corner_size],
            gray[:corner_size, -corner_size:],
            gray[-corner_size:, :corner_size],
            gray[-corner_size:, -corner_size:],
        ]
        for corner in corners:
            if corner.size == 0:
                continue
            corner_blur = cv2.Laplacian(corner, cv2.CV_64F).var()
            corner_mean = corner.mean()
            if corner_blur > 500 and (corner_mean < 60 or corner_mean > 200):
                return {"score": 0, "issues": ["TV logo/watermark in corner"]}
            corner_std = corner.std()
            if corner_std < 20 and abs(corner_mean - corner_blur) > 100:
                return {"score": 0, "issues": ["TV logo/watermark in corner"]}

        # 7. Face detection  (reject large faces = news anchors)
        try:
            face_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            )
            if not face_cascade.empty():
                faces = face_cascade.detectMultiScale(
                    gray, scaleFactor=1.1, minNeighbors=4, minSize=(30, 30)
                )
                if len(faces) > 0:
                    max_face_area = max(fw * fh for (_, _, fw, fh) in faces)
                    face_ratio = max_face_area / (w * h)
                    if face_ratio > 0.05:
                        return {"score": 0, "issues": [f"Large face ({face_ratio:.1%} of image)"]}
                    else:
                        # REJECT all images with detected faces — no human faces allowed
                        # in news visuals (prevents devil faces, AI-generated people, anchors)
                        return {"score": 0, "issues": [f"Face detected ({len(faces)} face(s), {face_ratio:.1%}) — no human faces allowed"]}
        except Exception:
            pass

        # 7b. AI-generated face / unnatural skin-tone detection
        # Even when Haar cascade misses small/distorted AI faces, unnatural
        # skin-tone pixel concentration reveals AI-generated human imagery.
        try:
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            # Broad skin-tone range in HSV (covers light to dark skin)
            skin_lower1 = np.array([0, 20, 70], dtype=np.uint8)
            skin_upper1 = np.array([25, 180, 255], dtype=np.uint8)
            skin_lower2 = np.array([160, 20, 70], dtype=np.uint8)
            skin_upper2 = np.array([180, 180, 255], dtype=np.uint8)
            skin_mask1 = cv2.inRange(hsv, skin_lower1, skin_upper1)
            skin_mask2 = cv2.inRange(hsv, skin_lower2, skin_upper2)
            skin_mask = cv2.bitwise_or(skin_mask1, skin_mask2)
            skin_ratio = np.count_nonzero(skin_mask) / (w * h)
            if skin_ratio > 0.25:
                return {"score": 0, "issues": [f"AI-face/skin-tone ({skin_ratio:.1%} skin pixels) — likely AI-generated human"]}
            elif skin_ratio > 0.15:
                score -= 20
                issues.append(f"elevated_skin_tone({skin_ratio:.1%})")
        except Exception:
            pass

        # 8. Near-white / near-black ratio
        white_ratio = np.count_nonzero(gray > 240) / (w * h)
        black_ratio = np.count_nonzero(gray < 15) / (w * h)
        if white_ratio > 0.6:
            return {"score": 0, "issues": [f"Mostly white ({white_ratio:.0%})"]}
        if black_ratio > 0.5:
            return {"score": 0, "issues": [f"Mostly black ({black_ratio:.0%})"]}

        score = max(0, min(100, score))
        return {"score": round(score, 1), "issues": issues}

    except Exception as e:
        return {"score": 0, "issues": [f"Quality check error: {e}"]}


def score_semantic_relevance(topic_title: str, image_title: str = "",
                              image_source: str = "", image_domain: str = "") -> dict:
    """
    Score how relevant a fetched image is to the news topic.
    Returns: {"relevant": bool, "score": float (0-100), "issues": list of str}

    Uses multiple signals:
    1. Keyword overlap between topic and image title/source (Jaccard-like)
    2. Image title/source keyword matching against topic keywords
    3. URL domain heuristics (stock photo vs editorial)
    4. Penalty for generic stock-photo titles

    Threshold: score < 40 = reject as off-topic.
    """
    issues = []
    score = 70.0  # Default trust Serper's search relevance

    # Clean and tokenize
    import re
    stop_words = {"the", "a", "an", "is", "are", "was", "were", "in", "on", "at",
                  "to", "for", "of", "and", "or", "but", "with", "from", "by",
                  "about", "image", "photo", "stock", "picture", "photograph",
                  "jpg", "png", "https", "http", "www", "com"}

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
            score -= 30
            issues.append("no_keyword_overlap")
    else:
        score -= 10
        issues.append("empty_image_metadata")

    # 2. Generic stock photo title detection
    generic_phrases = ["free photo", "royalty free", "stock image", "shutterstock",
                       "getty images", "istock", "dreamstime", "depositphotos",
                       "123rf", "alamy", "bigstock", "clip art", "vector",
                       "illustration", "cartoon", "meme", "emoji", "icon"]
    combined_lower = (image_title + " " + image_source).lower()
    for phrase in generic_phrases:
        if phrase in combined_lower:
            score -= 15
            issues.append(f"generic_stock({phrase})")
            break

    # 3. URL domain heuristics
    editorial_domains = ["bbc", "cnn", "ndtv", "thehindu", "timesofindia",
                         "reuters", "apnews", "aljazeera", "wikipedia",
                         "wikimedia", "nytimes", "washingtonpost", "guardian",
                         "bbc.co.uk", "inquirer", "telugustop", "123telugu",
                         "idlebrain", "greatandhra", "filmibeat"]
    stock_domains = ["shutterstock", "getty", "istock", "istockphoto",
                     "dreamstime", "depositphotos", "123rf", "alamy",
                     "bigstock", "canstock", "pond5", "vectorsock"]

    domain_lower = image_domain.lower().replace("www.", "")
    for ed in editorial_domains:
        if ed in domain_lower:
            score += 10
            break
    for sd in stock_domains:
        if sd in domain_lower:
            score -= 10
            issues.append("stock_domain")

    score = max(0, min(100, score))
    return {
        "relevant": score >= 40,
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
        Semantic relevance < 40 = rejected (off-topic).
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

    def fetch_visuals(self, topic: dict) -> list:
        """Fetch, semantically score + validate images from Serper Google Image Search."""
        url = "https://google.serper.dev/images"
        topic_title = topic.get("title", "")
        # Build a documentary-style search query to avoid news screenshots
        search_q = f"{topic_title} documentary photography high resolution"
        payload = {"q": search_q, "num": 10}  # Request more to allow for rejections
        headers = {'X-API-KEY': self.api_key, 'Content-Type': 'application/json'}

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15).json()
            images = response.get('images', [])

            paths = []
            for img in images[:10]:  # Try up to 10 to get 3 valid ones
                if len(paths) >= 3:
                    break
                img_url = img.get('imageUrl', '')
                if not img_url:
                    continue
                save_path = os.path.join(config.DRIVE["RUNTIME"], f"viz_news_{len(paths)}.jpg")
                # Pass Serper metadata for semantic relevance scoring
                img_title = img.get('title', '')
                img_source = img.get('source', '')
                img_domain = img.get('domain', '')
                if self._download_single_image(img_url, save_path, topic_title,
                                                img_title, img_source, img_domain):
                    paths.append(save_path)

            if paths:
                return paths
            print("    No valid images fetched from Serper, using fallback.")
            return [os.path.join(config.DRIVE["THUMBNAILS"], "production_thumb.jpg")]
        except Exception as e:
            print(f"    Visual fetch failed: {e}")
            return [os.path.join(config.DRIVE["THUMBNAILS"], "production_thumb.jpg")]
