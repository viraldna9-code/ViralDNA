# VERSION: 22.0
# MODULE: thumbnail_creator.py
# PURPOSE: Rich Visual Thumbnail Engine — news-channel style with image background,
#          gradient overlay, headline text, accent bar, and branding watermark.
#          Produces both a clean background (for video assembly) and a branded
#          thumbnail (for YouTube upload).
#          v22.0: A4.6 smart text overlay (contrast-aware positioning, adaptive sizing,
#                 breaking-badge only for breaking news). A4.8 style guide enforcement
#                 (category-specific colors/fonts, consistent brand treatment).

import os, textwrap, re, base64, hashlib, io
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import config

class ThumbnailCreator:
    """
    A4.8: Style Guide Enforcement
    Consistent thumbnail branding across all videos. Category-specific accent colors
    and text placement rules ensure professional news-channel look.
    v90.0: 3-layer image relevance filter — face detection, Gemini vision,
           and featured-image-first selection.
    """

    # ── v90.0: Politician face detection ──
    # OpenCV Haar cascade for face detection — no ML model download needed
    _FACE_CASCADE = None

    # ── v90.0: Known politician names to flag (Telugu/Indian politics) ──
    POLITICIAN_NAMES = {
        "naidu", "chandrababu", "jagan", "ysr", "modi", "rahul", "gandhi",
        "shah", "amit", "nirmala", "sitharaman", "jaishankar", "piyush",
        "gadkari", "rajnath", "singh", "smriti", "irani", "nadda", "kcr",
        "revanth", "pawan", "kalyan", "babu", "maharaj", "ramdev", "yogi",
        "adityanath", "mamata", "banerjee", "kejriwal", "arvind", "akhilesh",
        "yadav", "mayawati", "nitish", "kumar", "lalu", "prasad", "mulayam",
        "siddaramaiah", "bommai", "kumaraswamy", "dk", "shivakumar", "ravi",
        "naidu", "pawan", "chiranjeevi", "balakrishna", "ntr", "jr", "ntr",
        "mahesh", "babu", "allu", "arjun", "prabhas", "ram", "charan",
        "teja", "nani", "vijay", "devarakonda", "naga", "chaitanya",
        "varun", "tej", "sai", "pallavi", "anil", "kapoor", "odisha",
        "naveen", "patnaik", "biju", "janata", "dal", "bjp", "congress",
        "tdp", "ysrcp", "jsp", "bsp", "sp", "aap", "trs", "bRS",
    }

    # A4.8: Brand style guide — consistent colors, fonts, layout rules
    STYLE_GUIDE = {
        "dimensions": {"width": 1280, "height": 720},
        "font_bold": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "font_regular": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "brand_colors": {
            "primary_red": (220, 50, 50),      # C04020 equivalent
            "gold": (255, 215, 0),              # D6B300 equivalent
            "dark": (13, 13, 13),               # 0D0D0D
            "white": (255, 255, 255),
            "light_gray": (200, 200, 220),
        },
        # A4.8: Category-specific accent colors for visual variety
        "category_accents": {
            "DISASTER": (220, 50, 50),     # Red
            "CRIME": (180, 30, 30),        # Dark red
            "POLICY": (40, 100, 200),      # Blue
            "POLITICS": (220, 50, 50),     # Red
            "ECONOMICS": (30, 150, 80),    # Green
            "SPORTS": (255, 165, 0),       # Orange
            "ENTERTAINMENT": (180, 60, 200), # Purple
            "HEALTH": (50, 180, 120),      # Teal
            "TECHNOLOGY": (60, 130, 220),  # Blue
            "DEFAULT": (220, 50, 50),      # Red fallback
        },
        # A4.6: Text overlay rules
        # Updated Jun 28 2026: Large centered text for full-frame readability
        "text_rules": {
            "headline_min_size": 52,
            "headline_max_size": 80,
            "headline_width": 28,           # wrap width (shorter lines = bigger font)
            "max_lines": 4,
            "subtitle_size": 28,
            "badge_size": 22,
            "margin_left": 80,
            "margin_right": 80,
            "safe_zone_top": 40,
            "safe_zone_bottom": 60,
        },
    }

    def __init__(self, pacer, config_instance):
        sg = self.STYLE_GUIDE
        self.font_path = sg["font_bold"]
        self.font_path_regular = sg["font_regular"]
        self.logo_path = os.getenv(
            "VIRALDNA_WATERMARK",
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "watermark.png")
        )
        self.sg = sg
        self.tr = sg["text_rules"]
        print("  ✅ ThumbnailCreator (v22.0): Style Guide + Smart Text Overlay Active.")

    # ── A4.8: Detect news category from topic ──

    def _detect_category(self, topic: dict, title: str = "") -> str:
        text = f"{title} {topic.get('title', '')} {topic.get('description', '')}".lower()
        categories = {
            "DISASTER": ["flood", "cyclone", "earthquake", "disaster", "tragedy", "collapse", "fire accident", "accident"],
            "CRIME": ["murder", "theft", "arrest", "police", "crime", "scam", "fraud", "drug", "gang"],
            "POLICY": ["scheme", "welfare", "policy", "government", "bill", "act", "law", "regulation", "court", "high court", "pil", "litigation"],
            "POLITICS": ["election", "party", "minister", "cm ", "mla", "mp ", "vote", "campaign", "bypoll", "congress", "bjp", "tdp", "ysrcp", "janasena", "chandrababu", "mamata"],
            "ECONOMICS": ["budget", "tax", "price", "market", "economy", "gst", "inflation", "trade"],
            "SPORTS": ["cricket", "match", "tournament", "ipl", "player", "score", "win", "sports", "game"],
            "ENTERTAINMENT": ["movie", "film", "actor", "actress", "tollywood", "cinema", "song", "music", "album"],
            "HEALTH": ["hospital", "doctor", "health", "disease", "covid", "medicine", "medical", "vaccine"],
            "TECHNOLOGY": ["tech ", " ai ", "app ", "software", "digital", "cyber", "mobile ", "internet", "startup", "artificial intelligence"],
        }
        for cat, keywords in categories.items():
            if any(kw in text for kw in keywords):
                return cat
        return "DEFAULT"

    # ── A4.6: Smart text position calculation ──

    def _calc_text_position(self, img: Image.Image, title: str, lines: list) -> tuple:
        """
        Calculate optimal text Y position — CENTERED vertically.
        Updated Jun 28 2026: Text is centered in frame for full-frame readability.
        Previous behavior (bottom-anchored, small font) made text unreadable.
        
        Strategy:
        1. Center the text block vertically in the safe zone
        2. If image has high visual content, try to avoid salient regions
        3. Fallback: pure vertical center
        
        Returns (text_y_start, is_upper_safe) tuple.
        """
        W = self.sg["dimensions"]["width"]
        H = self.sg["dimensions"]["height"]
        safe_bottom = H - self.tr["safe_zone_bottom"]
        safe_top = self.tr["safe_zone_top"]
        line_height = int(self.tr["headline_max_size"] * 1.25)
        total_text_height = len(lines) * line_height + 40
        safe_height = safe_bottom - safe_top

        # Primary: center the text block vertically in the safe zone
        text_y_start = safe_top + (safe_height - total_text_height) // 2

        # If there's a strong visual region, try to avoid it
        try:
            import numpy as np
            gray = img.convert("L")
            arr = np.array(gray)
            num_bands = 6
            band_height = H // num_bands
            band_scores = []
            for b in range(num_bands):
                y_start = b * band_height
                y_end = min((b + 1) * band_height, H)
                band = arr[y_start:y_end, :]
                gy, gx = np.gradient(band.astype(float))
                edge_density = np.mean(np.sqrt(gx**2 + gy**2))
                band_scores.append((edge_density, y_start))

            # Only adjust if there's a very busy region (edge density > 3x average)
            avg_edge = sum(s for s, _ in band_scores) / len(band_scores)
            if avg_edge > 5:  # there's actual visual content
                # Find the band our centered text would overlap
                center_band = min(range(num_bands),
                                  key=lambda b: abs(b * band_height - text_y_start))
                center_score = band_scores[center_band][0]
                if center_score > avg_edge * 3:
                    # Center band is very busy, find a cleaner band
                    clean_bands = [(s, y) for s, y in band_scores
                                   if s < avg_edge * 1.5 and y + total_text_height <= safe_bottom]
                    if clean_bands:
                        clean_bands.sort(key=lambda x: x[0])
                        text_y_start = max(clean_bands[0][1], safe_top)
        except Exception:
            pass

        # Clamp to safe zone
        text_y_start = max(text_y_start, safe_top)
        if text_y_start + total_text_height > safe_bottom:
            text_y_start = safe_bottom - total_text_height
        return text_y_start, False

    def _find_salient_region(self, img: Image.Image) -> tuple:
        """
        Find the most visually salient (interesting) region in the image.
        Used to avoid placing text over important content like faces, text, objects.
        
        Returns (x, y, w, h) bounding box of the salient region, or None.
        """
        try:
            import numpy as np
            from PIL import ImageFilter
            
            gray = img.convert("L")
            # Apply edge detection filter
            edges = gray.filter(ImageFilter.FIND_EDGES)
            arr = np.array(edges)
            
            # Divide into grid and find region with highest edge concentration
            grid_size = 4
            cell_w = img.size[0] // grid_size
            cell_h = img.size[1] // grid_size
            max_density = 0
            best_cell = (0, 0)
            
            for gy in range(grid_size):
                for gx in range(grid_size):
                    y1 = gy * cell_h
                    y2 = (gy + 1) * cell_h
                    x1 = gx * cell_w
                    x2 = (gx + 1) * cell_w
                    density = np.mean(arr[y1:y2, x1:x2])
                    if density > max_density:
                        max_density = density
                        best_cell = (gx, gy)
            
            # Return bounding box of salient region with some padding
            pad = 20
            sx = best_cell[0] * cell_w + pad
            sy = best_cell[1] * cell_h + pad
            sw = cell_w - pad * 2
            sh = cell_h - pad * 2
            return (sx, sy, sw, sh)
        except Exception:
            return None

    # ── A4.6: Adaptive font size based on title length ──

    def _get_adaptive_font_size(self, title: str) -> int:
        """
        Longer titles get smaller fonts to fit within max_lines.
        Shorter titles get larger fonts for visual impact.
        """
        title_len = len(title)
        # Updated Jun 28 2026: Larger sizes for full-frame centered text
        if title_len <= 25:
            return self.tr["headline_max_size"]  # 80
        elif title_len <= 40:
            return 72
        elif title_len <= 60:
            return 64
        elif title_len <= 80:
            return 58
        elif title_len <= 100:
            return 54
        else:
            return self.tr["headline_min_size"]  # 52

    # ── A4.6: Check if news is actually breaking ──

    def _is_breaking_news(self, title: str, topic: dict) -> bool:
        """Only show BREAKING badge for actually urgent/breaking content."""
        text = f"{title} {topic.get('title', '')}".lower()
        breaking_keywords = [
            "breaking", "just in", "urgent", "alert", "live:",
            "exclusive:", "flash:", "breaking news"
        ]
        return any(kw in text for kw in breaking_keywords)

    # ── v90.0: 3-Layer Image Relevance Filter ──
    # Layer 1: Featured-image-first selection
    # Layer 2: Face detection — reject images with politician faces for non-political topics
    # Layer 3: Gemini Vision — verify image content matches topic headline

    def _get_face_cascade(self):
        """Lazy-load OpenCV Haar cascade for face detection."""
        if self._FACE_CASCADE is None:
            import cv2
            # Try bundled cascade first, then system
            cascade_paths = [
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml",
                "/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml",
                "/usr/local/share/opencv4/haarcascades/haarcascade_frontalface_default.xml",
            ]
            for cp in cascade_paths:
                if os.path.exists(cp):
                    self._FACE_CASCADE = cv2.CascadeClassifier(cp)
                    break
            if self._FACE_CASCADE is None:
                # Download if not found
                import urllib.request
                url = "https://raw.githubusercontent.com/opencv/opencv/master/data/haarcascades/haarcascade_frontalface_default.xml"
                local = os.path.expanduser("~/.hermes/cache/haarcascade_frontalface_default.xml")
                os.makedirs(os.path.dirname(local), exist_ok=True)
                if not os.path.exists(local):
                    print("  📥 Downloading face detection model...")
                    urllib.request.urlretrieve(url, local)
                self._FACE_CASCADE = cv2.CascadeClassifier(local)
        return self._FACE_CASCADE

    def _detect_faces(self, img_path):
        """Detect faces in an image. Returns list of (x, y, w, h) rectangles."""
        try:
            import cv2
            cascade = self._get_face_cascade()
            if cascade is None:
                return []
            img = cv2.imread(img_path)
            if img is None:
                return []
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
            return faces.tolist() if faces is not None and len(faces) > 0 else []
        except Exception:
            return []

    def _is_political_topic(self, topic_text):
        """Check if the topic is about politics/government."""
        text = topic_text.lower()
        political_keywords = {
            "minister", "cm", "chief minister", "pm", "prime minister", "bjp", "congress",
            "tdp", "ysrcp", "jsp", "bsp", "sp", "aap", "trs", "brs", "election", "vote",
            "parliament", "assembly", "mla", "mp", "cabinet", "government", "party",
            "leader", "opposition", "ruling", "coalition", "mandate", "poll", "campaign",
            "naidu", "modi", "jagan", "kcr", "chandra babu", "chandrababu",
        }
        return any(kw in text for kw in political_keywords)

    def _layer2_face_filter(self, img_path, topic_text, max_faces_for_nonpolitical=0):
        """
        Layer 2: Face detection filter.
        For non-political topics: reject images with any faces (likely politician stock photos).
        For political topics: allow up to 2 faces (reasonable for political imagery).
        Returns True if image passes the filter.
        """
        faces = self._detect_faces(img_path)
        if not faces:
            return True  # No faces — safe for any topic

        is_political = self._is_political_topic(topic_text)
        if is_political:
            # Political topics: allow images with faces (up to 4)
            return len(faces) <= 4
        else:
            # Non-political topics: reject if any faces detected
            if max_faces_for_nonpolitical == 0:
                return False
            return len(faces) <= max_faces_for_nonpolitical

    def _layer3_vision_check(self, img_path, topic_text):
        """
        Layer 3: Gemini Vision relevance check.
        Sends the image to Gemini with the topic and asks if the image is relevant.
        Returns True if relevant, False if not, None if check unavailable.
        """
        try:
            _key = os.environ.get("GEMINI_API_KEY", "")
            if not _key:
                _env = os.path.expanduser("~/.env")
                if os.path.exists(_env):
                    for line in open(_env):
                        if line.startswith("GEMINI_API_KEY="):
                            _key = line.strip().split("=", 1)[1].strip("\"'")
                            break
            if not _key:
                return None  # No API key — skip check

            with open(img_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")

            prompt = (
                f"News topic: \"{topic_text}\"\n\n"
                f"Is this image RELEVANT to the topic? "
                f"Answer with exactly one word: YES or NO.\n"
                f"Consider: Does the image show people/events/places related to the topic? "
                f"If the image shows random politicians or unrelated people, answer NO."
            )

            payload = {
                "contents": [{
                    "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": "image/jpeg", "data": b64}}
                    ]
                }]
            }

            import requests as req
            for model in ["gemini-2.0-flash", "gemini-1.5-flash"]:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={_key}"
                try:
                    resp = req.post(url, json=payload, timeout=20).json()
                    if "candidates" in resp:
                        text = resp["candidates"][0]["content"]["parts"][0]["text"].strip().upper()
                        if "YES" in text:
                            return True
                        elif "NO" in text:
                            return False
                except Exception:
                    continue
            return None  # All models failed
        except Exception:
            return None

    def _is_image_relevant(self, img_path, topic_text):
        """
        Combined 3-layer relevance check for a single image.
        Returns (is_relevant: bool, reason: str).
        """
        if not os.path.exists(img_path):
            return False, "file_missing"

        # Layer 2: Face detection
        face_ok = self._layer2_face_filter(img_path, topic_text)
        if not face_ok:
            return False, "face_rejected"

        # Layer 3: Vision check (only if face check passed)
        vision_ok = self._layer3_vision_check(img_path, topic_text)
        if vision_ok is False:
            return False, "vision_rejected"
        # If vision_ok is None (unavailable), we trust the face check result

        return True, "passed"

    def _rank_images_by_relevance(self, image_paths, topic_text):
        """
        Rank a list of image paths by relevance to the topic.
        Returns filtered + ranked list (most relevant first).
        Non-relevant images are excluded.
        """
        if not image_paths:
            return []

        results = []
        for path in image_paths:
            if not os.path.exists(path):
                continue
            is_rel, reason = self._is_image_relevant(path, topic_text)
            if is_rel:
                results.append(path)
            else:
                print(f"  🖼️ Thumbnail: REJECTED {os.path.basename(path)} ({reason})")

        return results

    # ── Background loading (unchanged logic) ──

    def _load_background_image(self, runtime_dir: str, slideshow_dir: str = None,
                                  topic_text: str = None) -> Image.Image | None:
        # 1. Check slideshow dir — prefer scene_img_* (Serper/real photos) over scene_* (image_pack fallback)
        if runtime_dir and os.path.isdir(runtime_dir):
            if slideshow_dir and os.path.isdir(slideshow_dir):
                # Prefer Serper-fetched images (scene_img_*) over pre-generated pack (scene_*)
                all_files = os.listdir(slideshow_dir)
                serper_files = sorted(
                    [f for f in all_files if f.startswith("scene_img_") and f.endswith((".jpg", ".png"))],
                    reverse=True
                )
                pack_files = sorted(
                    [f for f in all_files if f.startswith("scene_") and not f.startswith("scene_img_") and f.endswith((".jpg", ".png"))],
                    reverse=True
                )
                # Try Serper images first, then pack images
                for fname in serper_files + pack_files:
                    fpath = os.path.join(slideshow_dir, fname)
                    img = self._try_load_image(fpath)
                    if img:
                        # v75.3: Reject watermarked stock photos in thumbnail
                        try:
                            from PIL import Image as PILImage
                            from PIL.ExifTags import TAGS as EXIF_TAGS
                            im = PILImage.open(fpath)
                            exif = im.getexif()
                            if exif:
                                for tid, val in exif.items():
                                    tag = EXIF_TAGS.get(tid, tid)
                                    if tag in ("Copyright", "Artist", "ImageDescription"):
                                        val_lower = str(val).lower()
                                        _bad = ["hindustan times", "getty", "shutterstock", "dreamstime", "alamy", "reuters", "afp"]
                                        if any(b in val_lower for b in _bad):
                                            print(f"  Thumbnail: REJECTED {fname} (copyright: {val[:60]})")
                                            img = None
                                            break
                        except Exception:
                            pass
                        if img:
                            return img
            # 2. Check runtime viz_news images (from VisualFetcher)
            if runtime_dir and os.path.isdir(runtime_dir):
                candidates = sorted(
                    [f for f in os.listdir(runtime_dir) if f.startswith("viz_news_") and f.endswith(".jpg")],
                    reverse=True
                )
                for fname in candidates:
                    fpath = os.path.join(runtime_dir, fname)
                    img = self._try_load_image(fpath)
                    if img:
                        # v80.0: Watermark check for viz_news images too
                        try:
                            from PIL import Image as PILImage
                            from PIL.ExifTags import TAGS as EXIF_TAGS
                            im = PILImage.open(fpath)
                            exif = im.getexif()
                            if exif:
                                for tid, val in exif.items():
                                    tag = EXIF_TAGS.get(tid, tid)
                                    if tag in ("Copyright", "Artist", "ImageDescription"):
                                        val_lower = str(val).lower()
                                        _bad = ["hindustan times", "getty", "shutterstock", "dreamstime", "alamy", "reuters", "afp"]
                                        if any(b in val_lower for b in _bad):
                                            print(f"  Thumbnail: REJECTED {fname} (copyright: {val[:60]})")
                                            img = None
                                            break
                        except Exception:
                            pass
                        if img:
                            return img

        # 3. FALLBACK: Local Image Pack (v52.1 — prevents solid-color thumbnails)
        if topic_text:
            try:
                import importlib.util
                lip_path = os.path.join(os.path.dirname(__file__), "local_image_pack.py")
                if os.path.exists(lip_path):
                    spec = importlib.util.spec_from_file_location("local_image_pack", lip_path)
                    if spec and spec.loader:
                        mod = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(mod)
                        pack = mod.LocalImagePack()
                        images = pack.get_images(topic_text, count=5)
                        if images:
                            # Pick the largest image (best quality)
                            images.sort(key=lambda p: os.path.getsize(p), reverse=True)
                            img = self._try_load_image(images[0])
                            if img:
                                return img
            except Exception as e:
                pass  # local_image_pack fallback — skip silently

        # 4. LAST RESORT: solid color (should almost never reach this)
        return None

    def _load_background_images(self, runtime_dir: str, slideshow_dir: str = None,
                                   topic_text: str = None, count: int = 4) -> list:
        """
        Load MULTIPLE background images for variant diversity.
        Returns a list of PIL Images (up to `count`).
        v81.0: Each thumbnail variant gets a different background.
        """
        results = []
        seen_hashes = set()

        def _add_image(img):
            if img and len(results) < count:
                # Simple dedup: compare resized thumb hashes
                try:
                    thumb = img.resize((64, 36), Image.LANCZOS).convert("L")
                    h = hashlib.md5(thumb.tobytes()).hexdigest()
                    if h not in seen_hashes:
                        seen_hashes.add(h)
                        results.append(img)
                except Exception:
                    results.append(img)

        # 1. Check slideshow dir — prefer scene_img_* (real photos) over scene_*
        if runtime_dir and os.path.isdir(runtime_dir):
            if slideshow_dir and os.path.isdir(slideshow_dir):
                all_files = os.listdir(slideshow_dir)
                serper_files = sorted(
                    [f for f in all_files if f.startswith("scene_img_") and f.endswith((".jpg", ".png"))],
                    reverse=True
                )
                pack_files = sorted(
                    [f for f in all_files if f.startswith("scene_") and not f.startswith("scene_img_") and f.endswith((".jpg", ".png"))],
                    reverse=True
                )
                for fname in serper_files + pack_files:
                    fpath = os.path.join(slideshow_dir, fname)
                    img = self._try_load_image(fpath)
                    if img:
                        try:
                            from PIL import Image as PILImage
                            from PIL.ExifTags import TAGS as EXIF_TAGS
                            im = PILImage.open(fpath)
                            exif = im.getexif()
                            if exif:
                                for tid, val in exif.items():
                                    tag = EXIF_TAGS.get(tid, tid)
                                    if tag in ("Copyright", "Artist", "ImageDescription"):
                                        val_lower = str(val).lower()
                                        _bad = ["hindustan times", "getty", "shutterstock", "dreamstime", "alamy", "reuters", "afp"]
                                        if any(b in val_lower for b in _bad):
                                            img = None
                                            break
                        except Exception:
                            pass
                    _add_image(img)
                    if len(results) >= count:
                        return results

            # 2. Check runtime viz_news images
            if runtime_dir and os.path.isdir(runtime_dir):
                candidates = sorted(
                    [f for f in os.listdir(runtime_dir) if f.startswith("viz_news_") and f.endswith(".jpg")],
                    reverse=True
                )
                for fname in candidates:
                    fpath = os.path.join(runtime_dir, fname)
                    img = self._try_load_image(fpath)
                    if img:
                        try:
                            from PIL import Image as PILImage
                            from PIL.ExifTags import TAGS as EXIF_TAGS
                            im = PILImage.open(fpath)
                            exif = im.getexif()
                            if exif:
                                for tid, val in exif.items():
                                    tag = EXIF_TAGS.get(tid, tid)
                                    if tag in ("Copyright", "Artist", "ImageDescription"):
                                        val_lower = str(val).lower()
                                        _bad = ["hindustan times", "getty", "shutterstock", "dreamstime", "alamy", "reuters", "afp"]
                                        if any(b in val_lower for b in _bad):
                                            img = None
                                            break
                        except Exception:
                            pass
                    _add_image(img)
                    if len(results) >= count:
                        return results

        # 3. FALLBACK: Local Image Pack
        if topic_text and len(results) < count:
            try:
                import importlib.util
                lip_path = os.path.join(os.path.dirname(__file__), "local_image_pack.py")
                if os.path.exists(lip_path):
                    spec = importlib.util.spec_from_file_location("local_image_pack", lip_path)
                    if spec and spec.loader:
                        mod = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(mod)
                        pack = mod.LocalImagePack()
                        images = pack.get_images(topic_text, count=count * 2)
                        if images:
                            images.sort(key=lambda p: os.path.getsize(p), reverse=True)
                            for ipath in images:
                                img = self._try_load_image(ipath)
                                _add_image(img)
                                if len(results) >= count:
                                    break
            except Exception:
                pass  # local_image_pack fallback — skip silently

        # ── v90.0: Layer 1 — Featured-image-first reordering ──
        # Reorder so that scene_img_* (Serper/real news photos) come first,
        # then viz_news_*, then pack images. This is already handled by the
        # collection order above. The relevance filter below handles Layers 2+3.

        return results

    def _load_background_images_filtered(self, runtime_dir, slideshow_dir=None, topic_text=None, count=4):
        """
        v90.0: Load background images with 3-layer relevance filter applied.
        Falls back to unfiltered results if filter removes all images.
        """
        # Load candidates (may return more than count so we have filtering room)
        raw = self._load_background_images(runtime_dir, slideshow_dir=slideshow_dir,
                                            topic_text=topic_text, count=count * 3)
        if not raw:
            return raw

        # We need file paths for the filter, but _load_background_images returns PIL Images.
        # Re-collect paths from the same sources for filtering.
        candidate_paths = self._collect_candidate_paths(runtime_dir, slideshow_dir, topic_text, count * 3)
        if not candidate_paths:
            return raw  # No paths to filter — return unfiltered

        # Apply 3-layer relevance filter
        filtered_paths = self._rank_images_by_relevance(candidate_paths, topic_text or "")

        if not filtered_paths:
            print("  ⚠️ Thumbnail: All images rejected by relevance filter — using unfiltered")
            return raw  # Fallback: return unfiltered if everything was rejected

        # Load filtered images
        from PIL import Image as PILImage
        results = []
        seen_hashes = set()
        for fpath in filtered_paths:
            if len(results) >= count:
                break
            try:
                img = PILImage.open(fpath)
                if img.size[0] < 320 or img.size[1] < 240:
                    continue
                if img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGB")
                elif img.mode == "RGBA":
                    img = img.convert("RGB")
                thumb = img.resize((64, 36), PILImage.LANCZOS).convert("L")
                h = hashlib.md5(thumb.tobytes()).hexdigest()
                if h not in seen_hashes:
                    seen_hashes.add(h)
                    results.append(img)
            except Exception:
                continue

        if not results:
            return raw  # Fallback

        print(f"  🖼️ Thumbnail: {len(results)}/{len(raw)} images passed relevance filter")
        return results

    def _collect_candidate_paths(self, runtime_dir, slideshow_dir=None, topic_text=None, max_paths=12):
        """Collect candidate image file paths from all sources (without loading them)."""
        paths = []
        seen = set()

        def _add(path):
            if path and os.path.exists(path) and path not in seen:
                seen.add(path)
                paths.append(path)

        # 1. Slideshow dir — scene_img_* first, then scene_*
        if runtime_dir and os.path.isdir(runtime_dir):
            if slideshow_dir and os.path.isdir(slideshow_dir):
                all_files = os.listdir(slideshow_dir)
                for prefix in ["scene_img_", "scene_"]:
                    for fname in sorted(all_files, reverse=True):
                        if fname.startswith(prefix) and fname.endswith((".jpg", ".png")):
                            _add(os.path.join(slideshow_dir, fname))
                            if len(paths) >= max_paths:
                                return paths

            # 2. viz_news images
            if os.path.isdir(runtime_dir):
                for fname in sorted(os.listdir(runtime_dir), reverse=True):
                    if fname.startswith("viz_news_") and fname.endswith(".jpg"):
                        _add(os.path.join(runtime_dir, fname))
                        if len(paths) >= max_paths:
                            return paths

        # 3. Local Image Pack
        if topic_text and len(paths) < max_paths:
            try:
                import importlib.util
                lip_path = os.path.join(os.path.dirname(__file__), "local_image_pack.py")
                if os.path.exists(lip_path):
                    spec = importlib.util.spec_from_file_location("local_image_pack", lip_path)
                    if spec and spec.loader:
                        mod = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(mod)
                        pack = mod.LocalImagePack()
                        images = pack.get_images(topic_text, count=max_paths)
                        for ipath in images:
                            _add(ipath)
                            if len(paths) >= max_paths:
                                break
            except Exception:
                pass  # local_image_pack fallback — skip silently

        return paths

    def _try_load_image(self, fpath: str) -> Image.Image | None:
        try:
            img = Image.open(fpath)
            if img.size[0] < 320 or img.size[1] < 240:
                return None
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGB")
            elif img.mode == "RGBA":
                img = img.convert("RGB")
            return img
        except Exception:
            return None

    def _center_crop(self, img: Image.Image, target_w: int, target_h: int) -> Image.Image:
        src_w, src_h = img.size
        target_ratio = target_w / target_h
        src_ratio = src_w / src_h
        if src_ratio > target_ratio:
            new_w = int(src_h * target_ratio)
            left = (src_w - new_w) // 2
            img = img.crop((left, 0, left + new_w, src_h))
        else:
            new_h = int(src_w / target_ratio)
            top = (src_h - new_h) // 2
            img = img.crop((0, top, src_w, top + new_h))
        return img.resize((target_w, target_h), Image.LANCZOS)

    def _create_gradient_overlay(self, width: int, height: int) -> Image.Image:
        """Creates a semi-transparent gradient overlay (dark bottom 2/3) for text readability."""
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        gradient_start = int(height * 0.35)
        for y in range(gradient_start, height):
            alpha = int(180 * (y - gradient_start) / (height - gradient_start))
            draw.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))
        return overlay

    def _draw_text_with_shadow(self, draw: ImageDraw.Draw, pos: tuple, text: str,
                                font: ImageFont.FreeTypeFont, fill: tuple,
                                shadow_color: tuple = (0, 0, 0), offset: int = 3):
        """Draw text with a subtle shadow for readability on any background."""
        x, y = pos
        draw.text((x + offset, y + offset), text, fill=shadow_color, font=font)
        draw.text((x, y), text, fill=fill, font=font)

    # ── Main thumbnail creation ──

    def create_thumbnail(self, topic: dict, thumb_output_dir: str, sk: str,
                         runtime_dir: str = None, title_variants: list = None) -> dict:
        """
        Creates rich visual thumbnails (1280x720) with:
        - Background image from fetched news visuals (or gradient fallback)
        - Semi-transparent gradient overlay for text readability
        - Adaptive headline text (A4.6: smart sizing, contrast-aware positioning)
        - Category-specific accent bar (A4.8)
        - BREAKING badge only for breaking news (A4.6)
        - ViralDNA watermark logo (bottom-right)
        - Consistent brand treatment (A4.8)

        Produces:
        - {sk}_clean.jpg — clean background for video assembly
        - {sk}_branded.jpg — default branded thumbnail (uses first variant title)
        - {sk}_branded_v1.jpg, _v2.jpg, _v3.jpg — per-variant branded thumbnails
        """
        os.makedirs(thumb_output_dir, exist_ok=True)
        branded_path = os.path.join(thumb_output_dir, f"{sk}_branded.jpg")
        clean_path = os.path.join(thumb_output_dir, f"{sk}_clean.jpg")

        W, H = self.sg["dimensions"]["width"], self.sg["dimensions"]["height"]

        # A4.8: Detect category for accent color
        category = self._detect_category(topic)
        accent_color = self.sg["category_accents"].get(category, self.sg["category_accents"]["DEFAULT"])

        # ── 1. Background ──
        slideshow_dir = None
        if runtime_dir:
            for suffix in ["_main", ""]:
                candidate = os.path.join(runtime_dir, f"slideshow_{sk}{suffix}")
                if os.path.isdir(candidate):
                    slideshow_dir = candidate
                    break
        topic_text = topic.get("title", "") if topic else ""
        # v81.0: Load MULTIPLE background images for variant diversity
        # v90.0: Apply 3-layer relevance filter (face detection + Gemini vision + featured-first)
        bg_images = self._load_background_images_filtered(runtime_dir, slideshow_dir=slideshow_dir,
                                                           topic_text=topic_text, count=4)
        if bg_images:
            img = self._center_crop(bg_images[0], W, H).convert("RGBA").resize((W, H), Image.LANCZOS)
        else:
            img = Image.new("RGBA", (W, H), (15, 15, 30, 255))

        # ── 2. Gradient overlay ──
        gradient = self._create_gradient_overlay(W, H)
        img = Image.alpha_composite(img, gradient)

        # ── Save clean version ──
        img.convert("RGB").save(clean_path, "JPEG", quality=92)

        # ── Determine titles for each variant ──
        if title_variants and len(title_variants) > 0:
            variant_titles = []
            for v in title_variants[:3]:
                t = v.get("title", topic.get("title", "BREAKING NEWS"))
                variant_titles.append(t)
        else:
            variant_titles = [topic.get("title", "BREAKING NEWS")]

        result = {"path": branded_path, "clean_path": clean_path, "variants": []}

        for v_idx, title_text in enumerate(variant_titles):
            # v81.0: Use a DIFFERENT background image for each variant
            if bg_images and v_idx < len(bg_images):
                variant_base = self._center_crop(bg_images[v_idx], W, H).convert("RGBA").resize((W, H), Image.LANCZOS)
            elif bg_images:
                variant_base = self._center_crop(bg_images[v_idx % len(bg_images)], W, H).convert("RGBA").resize((W, H), Image.LANCZOS)
            else:
                variant_base = img.copy()
            variant_gradient = self._create_gradient_overlay(W, H)
            variant_img = Image.alpha_composite(variant_base, variant_gradient)
            draw = ImageDraw.Draw(variant_img)

            # ── A4.8: Category-specific accent bar ──
            draw.rectangle([(0, 0), (W, 8)], fill=accent_color)
            draw.rectangle([(0, 8), (W, 10)], fill=self.sg["brand_colors"]["gold"])

            # ── A4.6: BREAKING badge only for breaking news ──
            if self._is_breaking_news(title_text, topic):
                try:
                    badge_font = ImageFont.truetype(self.font_path, self.tr["badge_size"])
                except Exception:
                    badge_font = ImageFont.load_default()
                badge_text = "● BREAKING"
                badge_x, badge_y = 40, 24
                bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
                bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
                draw.rounded_rectangle(
                    [(badge_x - 10, badge_y - 4), (badge_x + bw + 10, badge_y + bh + 4)],
                    radius=6, fill=accent_color
                )
                draw.text((badge_x, badge_y), badge_text, fill=self.sg["brand_colors"]["white"], font=badge_font)

            # ── A4.6: Smart headline text ──
            title = title_text.strip()
            # Remove trailing pipe segments for cleaner display
            title = re.sub(r'\s*[|]\s*[^|]*$', '', title).strip()
            # Remove trailing " - Source Name" suffix from Google News RSS titles
            # e.g. "Andhra High Court Adjourns PIL - Telangana Today" -> "Andhra High Court Adjourns PIL"
            # Common Indian news sources: Telangana Today, NDTV, BBC, The Guardian, Times of India, etc.
            title = re.sub(r'\s*-\s*(Telangana Today|Telugu News|NDTV|BBC|The Guardian|Times of India|Indian Express|Deccan Chronicle|Hindustan Times|ANI|PTI|IANS|UNI|Reuters|AP|AFP|Al Jazeera|News18|India Today| Zee News|Republic TV|NDTV India).*$', '', title, flags=re.IGNORECASE).strip()

            # A4.6: Adaptive font size based on title length
            font_size = self._get_adaptive_font_size(title)
            # A4.6: Adaptive wrap width based on font size
            wrap_width = max(24, int(self.tr["headline_width"] * (56 / font_size)))

            if len(title) > 150:
                title = title[:147] + "..."

            try:
                headline_font = ImageFont.truetype(self.font_path, font_size)
            except Exception:
                headline_font = ImageFont.load_default()

            # Title Case for professional news look (not ALL CAPS)
            display_title = title.strip().title()
            lines = textwrap.wrap(display_title, width=wrap_width)[: self.tr["max_lines"]]

            # A4.6: Smart text positioning
            text_y_start, _ = self._calc_text_position(variant_img, display_title, lines)

            line_spacing = int(font_size * 1.25)
            for i, line in enumerate(lines):
                # Center each line horizontally
                bbox = draw.textbbox((0, 0), line, font=headline_font)
                line_w = bbox[2] - bbox[0]
                text_x = (W - line_w) // 2  # horizontal center
                self._draw_text_with_shadow(
                    draw, (text_x, text_y_start + i * line_spacing), line,
                    headline_font, fill=self.sg["brand_colors"]["white"],
                    shadow_color=self.sg["brand_colors"]["dark"], offset=2
                )

            # ── A4.8: Category-aware subtitle ──
            try:
                sub_font = ImageFont.truetype(self.font_path_regular, self.tr["subtitle_size"])
            except Exception:
                sub_font = ImageFont.load_default()

            # A4.8: Dynamic subtitle based on category
            category_labels = {
                "DISASTER": "Emergency Report",
                "CRIME": "Crime Desk",
                "POLICY": "Policy Watch",
                "POLITICS": "Political Desk",
                "ECONOMICS": "Economy Watch",
                "SPORTS": "Sports Desk",
                "ENTERTAINMENT": "Entertainment Desk",
                "HEALTH": "Health Desk",
                "TECHNOLOGY": "Tech Report",
                "DEFAULT": "News Report",
            }
            cat_label = category_labels.get(category, category_labels["DEFAULT"])
            subtitle = f"The Viral DNA  |  {cat_label}"
            self._draw_text_with_shadow(
                draw,
                (self.tr["margin_left"], text_y_start + len(lines) * line_spacing + 10),
                subtitle,
                sub_font, fill=self.sg["brand_colors"]["light_gray"],
                shadow_color=self.sg["brand_colors"]["dark"], offset=1
            )

            # ── A4.8: Bottom accent line (brand red) ──
            draw.rectangle([(0, H - 6), (W, H)], fill=accent_color)

            # ── 8. Watermark ──
            img_branded = variant_img.convert("RGB")
            if os.path.exists(self.logo_path):
                try:
                    logo = Image.open(self.logo_path).convert("RGBA")
                    logo_w = 140
                    logo_h = int(logo.size[1] * (logo_w / logo.size[0]))
                    logo = logo.resize((logo_w, logo_h), Image.LANCZOS)
                    pos = (W - logo_w - 20, H - logo_h - 20)
                    img_branded.paste(logo, pos, logo)
                except Exception as e:
                    print(f"  ⚠️ Logo watermark error: {e}")

            # Save variant thumbnail
            # v81.0: branded.jpg IS the first variant (v_idx==0)
            # Additional variants: branded_v2.jpg, branded_v3.jpg (different backgrounds)
            if v_idx == 0:
                img_branded.save(branded_path, "JPEG", quality=92)
                result["path"] = branded_path
                variant_path = branded_path  # v1 IS branded.jpg
            else:
                variant_path = os.path.join(thumb_output_dir, f"{sk}_branded_v{v_idx + 1}.jpg")
                img_branded.save(variant_path, "JPEG", quality=92)
            result["variants"].append({"path": variant_path, "title": title_text, "index": v_idx + 1})

        return result
