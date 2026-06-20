# VERSION: 87.8
# MODULE: local_visual_generator.py
# PURPOSE: Generate topic-relevant scene images using Stable Diffusion.
#          Primary: SD 1.5 via diffusers (RTX 3050 6GB, ~10s/image)
#          Fallback: PIL gradient + text placeholder (if SD fails)
#
# Pipeline: topic_title -> scene description prompt -> SD generate -> JPEG
#           Falls back to PIL gradient if SD model unavailable or OOM.

import os
import re
import time
import textwrap
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ─── Font paths ───────────────────────────────────────────────────────────────
FONT_DIR = "/usr/share/fonts/truetype"
FONT_PATHS = {
    "bold": [
        f"{FONT_DIR}/dejavu/DejaVuSans-Bold.ttf",
        f"{FONT_DIR}/liberation/LiberationSans-Bold.ttf",
        f"{FONT_DIR}/freefont/FreeSansBold.ttf",
        f"{FONT_DIR}/noto/NotoSans-Bold.ttf",
    ],
    "regular": [
        f"{FONT_DIR}/dejavu/DejaVuSans.ttf",
        f"{FONT_DIR}/liberation/LiberationSans-Regular.ttf",
        f"{FONT_DIR}/freefont/FreeSans.ttf",
        f"{FONT_DIR}/noto/NotoSans-Regular.ttf",
    ],
}

# ─── Category color schemes (for text overlay) ───────────────────────────────
CATEGORY_COLORS = {
    "politics":    ((15, 30, 80),   (25, 50, 120),  (200, 50, 50),  (255, 255, 255), (200, 50, 50)),
    "war":         ((60, 15, 15),   (100, 25, 25),  (220, 60, 30),  (255, 255, 240), (220, 60, 30)),
    "disaster":    ((50, 30, 10),   (90, 50, 20),   (230, 160, 40), (255, 255, 255), (230, 160, 40)),
    "economics":   ((10, 50, 30),   (20, 80, 50),   (50, 200, 100), (255, 255, 255), (50, 200, 100)),
    "tech":        ((10, 20, 60),   (20, 40, 100),  (60, 150, 255), (255, 255, 255), (60, 150, 255)),
    "health":      ((20, 40, 60),   (30, 60, 90),   (80, 200, 220), (255, 255, 255), (80, 200, 220)),
    "crime":       ((40, 10, 40),   (70, 20, 70),   (200, 50, 200), (255, 255, 255), (200, 50, 200)),
    "sports":      ((10, 50, 20),   (20, 80, 40),   (100, 220, 100), (255, 255, 255), (100, 220, 100)),
    "general":     ((20, 25, 40),   (35, 45, 70),   (100, 150, 220), (255, 255, 255), (100, 150, 220)),
}

# Keywords to detect category from topic title
CATEGORY_KEYWORDS = {
    "war":       {"war", "attack", "bomb", "missile", "military", "army", "navy", "air force",
                  "explosion", "conflict", "iran", "israel", "gaza", "ukraine", "russia",
                  "pentagon", "defense", "weapon", "drone", "strike", "battle", "troops"},
    "disaster":  {"earthquake", "flood", "cyclone", "tsunami", "landslide", "fire", "accident",
                  "crash", "collapse", "disaster", "evacuation", "rescue", "relief"},
    "economics": {"economy", "gdp", "inflation", "stock", "market", "trade", "budget", "tax",
                  "rupee", "dollar", "bank", "rbi", "interest", "growth", "recession"},
    "tech":      {"tech", "ai", "artificial intelligence", "google", "apple", "microsoft",
                  "startup", "app", "software", "digital", "cyber", "robot", "chatgpt"},
    "health":    {"health", "covid", "vaccine", "hospital", "doctor", "disease", "medical",
                  "medicine", "patient", "virus", "outbreak", "who"},
    "crime":     {"crime", "murder", "rape", "theft", "robbery", "arrest", "police", "court",
                  "jail", "prison", "scam", "fraud", "bribe", "corruption"},
    "sports":    {"cricket", "football", "hockey", "olympic", "match", "tournament", "player",
                  "coach", "team", "score", "win", "loss", "ipl", "world cup", "bcci"},
    "politics":  {"modi", "bjp", "congress", "election", "vote", "minister", "pm", "parliament",
                  "lok sabha", "rajya sabha", "party", "politician", "government", "policy",
                  "trump", "biden", "white house", "senate", "democrat", "republican"},
}

# ─── Stable Diffusion globals ────────────────────────────────────────────────
_sd_pipe = None  # Pipeline singleton: loaded once, reused across scenes

# ─── SD model config ──────────────────────────────────────────────────────────
SD_MODEL_ID = "runwayml/stable-diffusion-v1-5"
SD_MODEL_DIR = "/home/jay/ViralDNA/models/sd-v1-5-flat"
SD_WIDTH = 1024
SD_HEIGHT = 768
SD_INFERENCE_STEPS = 25
SD_GUIDANCE_SCALE = 7.5


def _detect_category(topic_title: str) -> str:
    """Detect news category from topic title keywords."""
    title_lower = topic_title.lower()
    scores = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in title_lower)
        if score > 0:
            scores[category] = score
    if scores:
        return max(scores, key=scores.get)
    return "general"


def _find_font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    """Find first available font path and load at given size."""
    for path in FONT_PATHS.get(weight, FONT_PATHS["regular"]):
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _build_sd_prompt(topic_title: str, scene_index: int, category: str) -> str:
    """
    Build a Stable Diffusion prompt from the topic title.
    Creates scene-specific prompts that generate relevant imagery.
    """
    # Clean the topic title
    clean = re.sub(r'\[.*?\]', '', topic_title).strip()
    clean = re.sub(r'#\w+', '', clean).strip()
    clean = re.sub(r'\s+', ' ', clean).strip()

    # Scene-specific prompt variations for visual diversity
    scene_variants = [
        # Scene 0: Wide establishing shot
        f"photojournalism, news photography of {clean}, wide establishing shot, professional news reporting, realistic, high detail, 4k",
        # Scene 1: Close-up / detail
        f"photojournalism, close-up detail of {clean}, news media coverage, dramatic lighting, professional photography, realistic",
        # Scene 2: Context / environment
        f"photojournalism, environmental context of {clean}, Indian landscape and culture, news documentary style, realistic, high detail",
        # Scene 3: Action / people
        f"photojournalism, people reacting to {clean}, Indian citizens, emotional moment, news coverage, realistic photography",
        # Scene 4: Abstract / conceptual
        f"editorial illustration about {clean}, conceptual news art, professional media, dramatic composition",
    ]

    prompt = scene_variants[scene_index % len(scene_variants)]
    return prompt


def _build_sd_negative_prompt() -> str:
    """Negative prompt to suppress common SD artifacts in news contexts."""
    return (
        "cartoon, anime, painting, drawing, illustration, sketch, "
        "deformed, ugly, blurry, bad anatomy, bad proportions, "
        "watermark, text overlay, logo, stock photo border, "
        "oversaturated, low quality, jpeg artifacts"
    )


def _gpu_available() -> bool:
    """Check if CUDA GPU is available (not just torch.cuda.is_available, but also
    that the GPU has enough VRAM for SD 1.5 ~3.5GB). Returns False on CPU-only/WSL."""
    try:
        import torch
        if not torch.cuda.is_available():
            return False
        # Check VRAM >= 3GB
        gpu_mem = torch.cuda.get_device_properties(0)
        vram_bytes = getattr(gpu_mem, "total_mem", 0)
        if vram_bytes < 3 * 1024**3:  # < 3GB
            print(f"  [LocalVisual] GPU VRAM {vram_bytes // (1024**2)}MB < 3GB — skip SD")
            return False
        return True
    except Exception:
        return False


def _ensure_sd_model() -> object:
    """
    Download SD v1.5 model if not present, then return the pipeline.
    Returns None if download fails OR no GPU is available.
    """
    global _sd_pipe
    if _sd_pipe is not None:
        return _sd_pipe

    # ─── Early GPU detection — skip entire SD path on CPU-only ─────────────
    if not _gpu_available():
        print("  [LocalVisual] No CUDA GPU with >=3GB VRAM — skipping SD, using PIL fallback")
        return None

    try:
        from diffusers import StableDiffusionPipeline
        import torch
    except ImportError:
        print("  [LocalVisual] diffusers not installed — using PIL fallback")
        return None

    # Check if model already downloaded locally
    if os.path.exists(os.path.join(SD_MODEL_DIR, "model_index.json")):
        try:
            print(f"  [LocalVisual] Loading SD v1.5 from local cache: {SD_MODEL_DIR}")
            _sd_pipe = StableDiffusionPipeline.from_pretrained(
                SD_MODEL_DIR,
                torch_dtype=torch.float16,
            )
            _sd_pipe.to("cuda")
            _sd_pipe.enable_attention_slicing()
            print("  [LocalVisual] SD pipeline loaded on CUDA (attention slicing ON)")
            return _sd_pipe
        except Exception as e:
            print(f"  [LocalVisual] Failed to load local model: {e}")

    # Download from HuggingFace
    try:
        print(f"  [LocalVisual] Downloading SD v1.5 from HuggingFace...")
        os.makedirs(SD_MODEL_DIR, exist_ok=True)
        _sd_pipe = StableDiffusionPipeline.from_pretrained(
            SD_MODEL_ID,
            torch_dtype=torch.float16,
            cache_dir=SD_MODEL_DIR,
        )
        # Save full model to local dir for offline use
        _sd_pipe.save_pretrained(SD_MODEL_DIR)
        _sd_pipe.to("cuda")
        _sd_pipe.enable_attention_slicing()
        print(f"  [LocalVisual] SD v1.5 downloaded and loaded on CUDA")
        return _sd_pipe
    except Exception as e:
        print(f"  [LocalVisual] Failed to download SD model: {e}")
        return None


def _generate_with_sd(topic_title: str, output_path: str, scene_index: int = 0) -> str:
    """
    Generate a scene image using Stable Diffusion.
    Returns the output path on success, None on failure.
    """
    import torch

    pipe = _ensure_sd_model()
    if pipe is None:
        return None

    category = _detect_category(topic_title)
    prompt = _build_sd_prompt(topic_title, scene_index, category)
    negative = _build_sd_negative_prompt()

    try:
        # Deterministic seed per scene for consistency
        generator = torch.Generator("cuda").manual_seed(42 + scene_index)

        result = pipe(
            prompt=prompt,
            negative_prompt=negative,
            width=SD_WIDTH,
            height=SD_HEIGHT,
            num_inference_steps=SD_INFERENCE_STEPS,
            guidance_scale=SD_GUIDANCE_SCALE,
            generator=generator,
        )
        image = result.images[0]

        # Upscale to 1920x1080 for video use
        image = image.resize((1920, 1080), Image.LANCZOS)

        # Overlay category text and branding
        image = _overlay_news_branding(image, topic_title, scene_index, category)

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        image.save(output_path, "JPEG", quality=92)
        print(f"  [SD] Generated scene {scene_index}: {output_path} ({os.path.getsize(output_path)//1024}KB)")
        return output_path
    except Exception as e:
        print(f"  [SD] Generation failed for scene {scene_index}: {e}")
        return None


def _overlay_news_branding(img: Image.Image, topic_title: str,
                            scene_index: int, category: str) -> Image.Image:
    """Overlay news ticker, category badge, and scene number on the SD image."""
    draw = ImageDraw.Draw(img)
    w, h = img.size

    # ─── Top category badge ──────────────────────────────────────────────
    cat_colors = CATEGORY_COLORS.get(category, CATEGORY_COLORS["general"])
    accent = cat_colors[2]
    cat_font = _find_font("bold", max(16, h // 40))
    cat_label = f"  {category.upper()}  "
    bbox = draw.textbbox((0, 0), cat_label, font=cat_font)
    badge_w = bbox[2] - bbox[0] + 20
    badge_h = bbox[3] - bbox[1] + 12
    # Dark background for badge
    draw.rectangle([10, 10, 10 + badge_w, 10 + badge_h], fill=(0, 0, 0, 180))
    draw.rectangle([10, 10, 10 + badge_w, 10 + badge_h], outline=accent, width=2)
    draw.text((20, 16), cat_label, font=cat_font, fill=(255, 255, 255))

    # ─── Bottom news ticker bar ──────────────────────────────────────────
    bar_h = max(50, h // 12)
    bar_y = h - bar_h
    # Semi-transparent dark bar
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.rectangle([0, bar_y, w, h], fill=(0, 0, 0, 160))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Accent line on top of bar
    draw.line([(0, bar_y), (w, bar_y)], fill=accent, width=3)

    # Headline text (truncated)
    headline_font = _find_font("bold", max(20, h // 25))
    clean_title = re.sub(r'\[.*?\]', '', topic_title).strip()
    clean_title = re.sub(r'#\w+', '', clean_title).strip()
    clean_title = re.sub(r'\s+', ' ', clean_title).strip()
    if len(clean_title) > 80:
        clean_title = clean_title[:77] + "..."
    draw.text((20, bar_y + 12), clean_title, font=headline_font, fill=(255, 255, 255))

    # Scene indicator on right
    info_font = _find_font("regular", max(14, h // 35))
    draw.text((w - 20, bar_y + bar_h // 2), f"Scene {scene_index + 1}",
              font=info_font, fill=accent, anchor="rm")

    return img


# ─── PIL fallback (gradient + text) ──────────────────────────────────────────

def _create_gradient(width: int, height: int, color_start: tuple, color_end: tuple,
                     direction: str = "diagonal") -> Image.Image:
    """Create a smooth gradient image."""
    arr = np.zeros((height, width, 3), dtype=np.uint8)
    if direction == "diagonal":
        y_coords, x_coords = np.mgrid[0:height, 0:width]
        t = (x_coords / max(width - 1, 1) + y_coords / max(height - 1, 1)) / 2
    elif direction == "vertical":
        t = np.linspace(0, 1, height).reshape(-1, 1)
        t = np.tile(t, (1, width))
    else:
        t = np.linspace(0, 1, width).reshape(1, -1)
        t = np.tile(t, (height, 1))
    t = np.clip(t, 0, 1)
    for c in range(3):
        arr[:, :, c] = (color_start[c] * (1 - t) + color_end[c] * t).astype(np.uint8)
    return Image.fromarray(arr)


def _draw_text_with_shadow(draw: ImageDraw.Draw, pos: tuple, text: str,
                            font: ImageFont.FreeTypeFont, fill: tuple,
                            shadow_color: tuple = (0, 0, 0), offset: int = 3,
                            anchor: str = "lt"):
    """Draw text with a subtle shadow for readability."""
    x, y = pos
    draw.text((x + offset, y + offset), text, font=font, fill=shadow_color, anchor=anchor)
    draw.text((x, y), text, font=font, fill=fill, anchor=anchor)


def _wrap_text_to_width(text: str, font: ImageFont.FreeTypeFont, max_width: int,
                        draw: ImageDraw.Draw) -> list:
    """Wrap text to fit within max_width pixels."""
    words = text.split()
    lines = []
    current_line = []
    for word in words:
        test_line = " ".join(current_line + [word])
        bbox = draw.textbbox((0, 0), test_line, font=font)
        w = bbox[2] - bbox[0]
        if w <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]
    if current_line:
        lines.append(" ".join(current_line))
    return lines


def _generate_pil_fallback(topic_title: str, output_path: str,
                            width: int = 1920, height: int = 1080,
                            scene_index: int = 0) -> str:
    """Generate a PIL gradient + text placeholder image (fallback)."""
    category = _detect_category(topic_title)
    colors = CATEGORY_COLORS.get(category, CATEGORY_COLORS["general"])
    bg_start, bg_end, accent, text_color, overlay_color = colors

    # Vary gradient direction per scene
    directions = ["diagonal", "vertical", "horizontal", "diagonal", "vertical"]
    direction = directions[scene_index % len(directions)]

    img = _create_gradient(width, height, bg_start, bg_end, direction)
    draw = ImageDraw.Draw(img)

    margin_x = width // 10
    margin_top = height // 8
    max_text_width = width - 2 * margin_x

    # Category badge
    cat_font = _find_font("bold", max(16, height // 30))
    cat_label = category.upper()
    bbox = draw.textbbox((0, 0), cat_label, font=cat_font)
    badge_w = bbox[2] - bbox[0] + 20
    badge_h = bbox[3] - bbox[1] + 12
    draw.rounded_rectangle(
        [margin_x, margin_top - badge_h - 10, margin_x + badge_w, margin_top - 10],
        radius=6, fill=accent
    )
    draw.text((margin_x + 10, margin_top - badge_h - 4), cat_label,
              font=cat_font, fill=(255, 255, 255), anchor="lt")

    # Main headline
    clean_title = re.sub(r'\[.*?\]', '', topic_title).strip()
    clean_title = re.sub(r'#\w+', '', clean_title).strip()
    clean_title = re.sub(r'\s+', ' ', clean_title).strip()

    title_len = len(clean_title)
    if title_len <= 30:
        title_font_size = max(48, height // 10)
    elif title_len <= 60:
        title_font_size = max(36, height // 14)
    elif title_len <= 100:
        title_font_size = max(28, height // 18)
    else:
        title_font_size = max(22, height // 22)

    title_font = _find_font("bold", title_font_size)
    wrapped_lines = _wrap_text_to_width(clean_title, title_font, max_text_width, draw)

    line_height = title_font_size * 1.3
    headline_y = margin_top + 20
    for i, line in enumerate(wrapped_lines[:4]):
        bbox = draw.textbbox((0, 0), line, font=title_font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        pad = 8
        overlay_img = Image.new("RGBA", img.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay_img)
        overlay_draw.rounded_rectangle(
            [margin_x - pad, int(headline_y) - pad,
             margin_x + text_w + pad, int(headline_y) + text_h + pad],
            radius=4, fill=(0, 0, 0, 100)
        )
        img = Image.alpha_composite(img.convert("RGBA"), overlay_img).convert("RGB")
        draw = ImageDraw.Draw(img)
        _draw_text_with_shadow(draw, (margin_x, headline_y), line,
                               title_font, text_color, shadow_color=(0, 0, 0), offset=2)
        headline_y += line_height

    # Decorative divider
    divider_y = headline_y + 20
    divider_width = width // 4
    draw.line([(margin_x, divider_y), (margin_x + divider_width, divider_y)],
              fill=accent, width=3)

    # Subtitle
    subtitle_font = _find_font("regular", max(16, height // 30))
    subtitles = ["Breaking News", "Live Updates", "Developing Story",
                 "Latest Report", "Exclusive", "Top Story"]
    subtitle = subtitles[scene_index % len(subtitles)]
    draw.text((margin_x, divider_y + 15), f"  {subtitle}",
              font=subtitle_font, fill=accent, anchor="lt")

    # Bottom bar
    bar_height = max(40, height // 18)
    bar_y = height - bar_height - 10
    draw.rounded_rectangle(
        [10, bar_y, width - 10, bar_y + bar_height],
        radius=4, fill=(20, 20, 30)
    )
    info_font = _find_font("regular", max(14, height // 40))
    draw.text((25, bar_y + bar_height // 2), f"Scene {scene_index + 1}",
              font=info_font, fill=(180, 180, 200), anchor="lm")
    cat_indicator = f"  {category.upper()}"
    draw.text((width - 25, bar_y + bar_height // 2), cat_indicator,
              font=info_font, fill=accent, anchor="rm")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    img.save(output_path, "JPEG", quality=92)
    print(f"  [PIL] Fallback scene {scene_index}: {output_path} ({width}x{height})")
    return output_path


# ─── Public API ───────────────────────────────────────────────────────────────

def generate_scene_image(topic_title: str, output_path: str,
                          width: int = 1920, height: int = 1080,
                          scene_index: int = 0) -> str:
    """
    Generate a single scene image for a news topic.
    Tries Stable Diffusion first, falls back to PIL gradient.
    Returns the output path.
    """
    # Try SD first
    result = _generate_with_sd(topic_title, output_path, scene_index)
    if result is not None:
        return result

    # Fallback to PIL
    return _generate_pil_fallback(topic_title, output_path, width, height, scene_index)


def generate_scene_images(topic_title: str, output_dir: str, count: int = 5,
                           width: int = 1920, height: int = 1080) -> list:
    """
    Generate multiple scene images for a topic.
    Each image has a different prompt variation for visual diversity.
    Returns list of saved file paths.
    """
    os.makedirs(output_dir, exist_ok=True)
    paths = []
    for i in range(count):
        path = os.path.join(output_dir, f"scene_img_{i}.jpg")
        generate_scene_image(topic_title, path, width, height, scene_index=i)
        paths.append(path)
    print(f"  [LocalVisual] Generated {count} scene images in {output_dir}")
    return paths


# ─── Self-test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import tempfile
    test_dir = tempfile.mkdtemp()
    test_topic = "ASI survey uncovers 25 inscriptions, ancient rock art in Nallamala Tiger Reserve"
    print(f"Testing with topic: {test_topic}")
    paths = generate_scene_images(test_topic, test_dir, count=2)
    for p in paths:
        sz = os.path.getsize(p)
        print(f"  {p}: {sz // 1024}KB")
    print("Self-test PASSED")
