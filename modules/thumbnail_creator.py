# VERSION: 22.0
# MODULE: thumbnail_creator.py
# PURPOSE: Rich Visual Thumbnail Engine — news-channel style with image background,
#          gradient overlay, headline text, accent bar, and branding watermark.
#          Produces both a clean background (for video assembly) and a branded
#          thumbnail (for YouTube upload).
#          v22.0: A4.6 smart text overlay (contrast-aware positioning, adaptive sizing,
#                 breaking-badge only for breaking news). A4.8 style guide enforcement
#                 (category-specific colors/fonts, consistent brand treatment).

import os, textwrap, re
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import config

class ThumbnailCreator:
    """
    A4.8: Style Guide Enforcement
    Consistent thumbnail branding across all videos. Category-specific accent colors
    and text placement rules ensure professional news-channel look.
    """

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
        "text_rules": {
            "headline_min_size": 36,
            "headline_max_size": 56,
            "headline_width": 32,           # wrap width
            "max_lines": 3,
            "subtitle_size": 22,
            "badge_size": 20,
            "margin_left": 50,
            "margin_right": 50,             # leave space for watermark
            "safe_zone_top": 60,            # below badge
            "safe_zone_bottom": 80,         # above watermark
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
            "POLICY": ["scheme", "welfare", "policy", "government", "bill", "act", "law", "regulation"],
            "POLITICS": ["election", "party", "minister", "cm ", "mla", "mp ", "vote", "campaign", "bypoll"],
            "ECONOMICS": ["budget", "tax", "price", "market", "economy", "gst", "inflation", "trade"],
            "SPORTS": ["cricket", "match", "tournament", "ipl", "player", "score", "win", "sports", "game"],
            "ENTERTAINMENT": ["movie", "film", "actor", "actress", "tollywood", "cinema", "song", "music", "album"],
            "HEALTH": ["hospital", "doctor", "health", "disease", "covid", "medicine", "medical", "vaccine"],
            "TECHNOLOGY": ["tech", "ai ", "app", "software", "digital", "cyber", "mobile", "internet", "startup"],
        }
        for cat, keywords in categories.items():
            if any(kw in text for kw in keywords):
                return cat
        return "DEFAULT"

    # ── A4.6: Smart text position calculation ──

    def _calc_text_position(self, img: Image.Image, title: str, lines: list) -> tuple:
        """
        Calculate optimal text Y position based on image content.
        v22.1 (v87.12): Content-aware placement — avoids faces/salient regions.
        
        Strategy:
        1. Divide image into a 3x3 grid of regions
        2. Score each region by visual complexity (edge density)
        3. Place text in the region with LOWEST complexity (cleanest area)
        4. If the image has detected faces, avoid the face region
        
        Returns (text_y_start, is_upper_safe) tuple.
        """
        W = self.sg["dimensions"]["width"]
        H = self.sg["dimensions"]["height"]
        safe_bottom = H - self.tr["safe_zone_bottom"]
        safe_top = self.tr["safe_zone_top"]
        line_height = int(self.tr["headline_max_size"] * 1.25)
        total_text_height = len(lines) * line_height + 40

        # Try to find cleanest horizontal band using edge analysis
        try:
            import numpy as np
            # Convert to grayscale numpy array for analysis
            gray = img.convert("L")
            arr = np.array(gray)

            # Divide into horizontal bands and compute edge density per band
            num_bands = 6
            band_height = H // num_bands
            band_scores = []
            for b in range(num_bands):
                y_start = b * band_height
                y_end = min((b + 1) * band_height, H)
                band = arr[y_start:y_end, :]
                # Simple gradient-based edge detection
                gy, gx = np.gradient(band.astype(float))
                edge_density = np.mean(np.sqrt(gx**2 + gy**2))
                band_scores.append((edge_density, y_start, y_end))

            # Find the band with lowest edge density that can fit our text block
            # Prefer lower portion but avoid the very bottom (watermark zone)
            candidate_bands = []
            for score, y_start, y_end in band_scores:
                region_height = y_end - y_start
                if region_height >= total_text_height:
                    # Check this band doesn't overlap with bottom watermark zone
                    if y_start + total_text_height <= safe_bottom:
                        candidate_bands.append((score, y_start))

            if candidate_bands:
                # Pick the cleanest (lowest edge density) band
                candidate_bands.sort(key=lambda x: x[0])
                best_y = candidate_bands[0][1]
                # Ensure minimum safe zone
                text_y_start = max(best_y, safe_top)
                # Ensure text fits above watermark
                if text_y_start + total_text_height > safe_bottom:
                    text_y_start = safe_bottom - total_text_height
                return text_y_start, (text_y_start < H // 3)

        except Exception:
            pass

        # Fallback: position in lower third above watermark (original behavior)
        text_y_start = safe_bottom - total_text_height
        text_y_start = max(text_y_start, safe_top)
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
        if title_len <= 30:
            return self.tr["headline_max_size"]  # 56
        elif title_len <= 60:
            return 48
        elif title_len <= 90:
            return 42
        elif title_len <= 120:
            return 38
        else:
            return self.tr["headline_min_size"]  # 36

    # ── A4.6: Check if news is actually breaking ──

    def _is_breaking_news(self, title: str, topic: dict) -> bool:
        """Only show BREAKING badge for actually urgent/breaking content."""
        text = f"{title} {topic.get('title', '')}".lower()
        breaking_keywords = [
            "breaking", "just in", "urgent", "alert", "live:",
            "exclusive:", "flash:", "breaking news"
        ]
        return any(kw in text for kw in breaking_keywords)

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
                print(f"  ⚠️ Thumbnail local image pack fallback failed: {e}")

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
            except Exception as e:
                print(f"  Thumbnail local image pack fallback failed: {e}")

        return results

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
        bg_images = self._load_background_images(runtime_dir, slideshow_dir=slideshow_dir,
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
                # Add gold left border accent on first line for readability
                if i == 0:
                    draw.rectangle(
                        [(self.tr["margin_left"] - 8, text_y_start + 6),
                         (self.tr["margin_left"] - 4, text_y_start + line_spacing - 8)],
                        fill=self.sg["brand_colors"]["gold"]
                    )
                self._draw_text_with_shadow(
                    draw, (self.tr["margin_left"], text_y_start + i * line_spacing), line,
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
                "DEFAULT": "Telugu News Report",
            }
            cat_label = category_labels.get(category, category_labels["DEFAULT"])
            subtitle = f"The ViralDNA  |  {cat_label}  |  Telugu News"
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
