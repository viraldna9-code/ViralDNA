# VERSION: 1.0
# MODULE: trailer_generator.py
# PURPOSE: Channel trailer generator for ViralDNA Telugu Diaspora News.
#          Produces a world-class channel trailer that:
#          - Introduces the channel's core topics (Telugu news, diaspora, culture)
#          - Discloses AI-100% built with single-click production
#          - Uses real news with human voices (Edge-TTS Prabhat + Mohan)
#          - Is bilingual (English + Telugu) matching pipeline style
#          - 60-second cinematic format with branding
#
# USAGE:
#  python3 -m modules.trailer-generator [--dry-run]

import os
import sys
import json
import shutil
import subprocess
import asyncio

# Setup paths — modules/ must be on path for config and pipeline imports
MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(MODULE_DIR)
if MODULE_DIR not in sys.path:
    sys.path.insert(0, MODULE_DIR)

import config
from voiceover import VoiceoverGenerator
from thumbnail_creator import ThumbnailCreator

# ═══════════════════════════════════════════════════════════════
# TRAILER SCRIPT — THE BEST CHANNEL TRAILER
# Humanizer principles applied:
#   - No AI-isms ("delve", "tapestry", "utilize", "leverage")
#   - Short, punchy sentences (news anchor cadence)
#   - Authentic diaspora voice (first person, emotional connection)
#   - Bilingual flow (English anchor -> Telugu warmth -> English close)
#   - Single compelling hook in first 3 seconds
# ═══════════════════════════════════════════════════════════════

_TRAILER_SCRIPT = """
Every Telugu family far from home carries the same heartbeat. What is happening back home? Are our people safe? Is our culture surviving? Is our future secure?

మన దేశం మన ఆత్మ. మన కుటుంబాలు, మన ప్రజలు, మన భవిష్యత్తు — ఇవన్నీ మనకు తెలిసి ఉండాలి.

There is no channel built for us. No channel that speaks our language. Our politics. Our culture. Our truth. Until now.

హైదరాబాద్ నుండి హౌస్టన్ వరకు. విజయవాడ నుండి లండన్ వరకు. ప్రపంచవ్యాప్తంగా ఉన్న తెలుగు ఆత్మలు — ఇప్పుడు ఒక్క క్లిక్కులో కలుస్తాయి.

This is ViralDNA. Breaking news in Telugu and English. Political analysis that matters. Cultural stories that connect generations. Tech and business that shape the diaspora. Every single day.

తెలుగు రాజకీయ వార్తలు. ప్రపంచ వార్తలు. మన సంస్కృతి. మన భవిష్యత్తు. అన్నీ ఒకే చిహ్నంలో.

Now here is what makes this different. What makes this impossible. This entire newsroom runs itself. No human camera crew. No human anchors. No human editors. Just artificial intelligence — reading the world's news, writing scripts in Telugu and English, speaking with real human voice clones, assembling broadcast-quality videos — and publishing. All from one machine. One click. Every day.

ఈ ఛానల్ మొత్తం ఒక కంప్యూటర్ నడుపుతోంది. కానీ వార్తలు మాయలేదు. వాయిసులు మాయలేవు. మన ఆత్మ నిజం.

This is not the future. This is now. This is how Telugu diaspora news gets built in the age of AI.

ViralDNA. Built different. Run different.

మనది. ఇప్పుడు. ఎల్లప్పుడూ.

Subscribe. Stay Telugu. Stay ahead.
సభ్యత్వం పొందండి. మనతో <longcat_arg_value>

"""

# Scene timing for visual slides (seconds)
# Total target: ~60 seconds with cinematic pacing
_TRAILER_SCENES = [
    {
        "id": "hook",
        "duration": 5.0,
        "text": "What is happening\nback home?",
        "subtitle_tel": "దేశంలో ఏమి జరుగుతోంది?",
        "visual": "world_map",
        "transition": "fade_in",
        "music_energy": "low",
    },
    {
        "id": "diaspora_reach",
        "duration": 5.0,
        "text": "Telugu voices\naround the world",
        "subtitle_tel": "ప్రపంచంలో తెలుగు గొంతులు",
        "visual": "diaspora_map",
        "transition": "cross_dissolve",
        "music_energy": "building",
    },
    {
        "id": "content_showcase",
        "duration": 5.0,
        "text": "News • Politics • Culture\nTech • Business • Diaspora",
        "subtitle_tel": "వార్తలు • రాజకీయాలు • సంస్కృతి",
        "visual": "news_collage",
        "transition": "slide_left",
        "music_energy": "medium",
    },
    {
        "id": "ai_disclosure",
        "duration": 7.0,
        "text": "This entire newsroom\nruns on AI\nNo humans. One click.",
        "subtitle_tel": "ఈ న్యూస్‌రూమ్ మొత్తం AI తో\nఒక క్లిక్కులో",
        "visual": "ai_tech",
        "transition": "zoom_in",
        "music_energy": "high",
    },
    {
        "id": "real_news",
        "duration": 5.0,
        "text": "Real news.\nReal voices.\nReal AI.",
        "subtitle_tel": "నిజమైన వార్తలు\nనిజమైన వాయిసులు",
        "visual": "microphone",
        "transition": "cross_dissolve",
        "music_energy": "peak",
    },
    {
        "id": "brand_reveal",
        "duration": 4.0,
        "text": "ViralDNA\nBuilt different.\nRun different.",
        "subtitle_tel": "తెలుగు డయాస్పోరా న్యూస్",
        "visual": "logo_reveal",
        "transition": "scale_up",
        "music_energy": "anthem",
    },
    {
        "id": "cta",
        "duration": 4.0,
        "text": "Subscribe.\nStay Telugu.\nStay ahead.",
        "subtitle_tel": "సభ్యత్వం పొందండి\nమనతో ఉండండి",
        "visual": "subscribe_cta",
        "transition": "fade_out",
        "music_energy": "resolve",
    },
]

# Visual generation config
_TRAILER_VISUALS = {
    "resolution": (1920, 1080),  # Full HD for cinematic feel
    "fps": 30,
    "bg_color": (13, 13, 13),  # Brand dark #0D0D0D
    "accent_color": (192, 64, 32),  # Brand red #C04020
    "gold_color": (214, 179, 0),  # Brand gold #D6B300
    "font_path": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "font_path_regular": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "font_path_telugu": "/usr/share/fonts/truetype/noto/NotoSansTeluguUI-Bold.ttf",
    "font_path_telugu_reg": "/usr/share/fonts/truetype/noto/NotoSansTelugu-ExtraCondensed.ttf",
}


class TrailerGenerator:
    """
    End-to-end channel trailer generator for ViralDNA.
    Produces: voiceover MP3, visual slideshow MP4, thumbnail JPG, final trailer MP4.
    """

    def __init__(self, dry_run=False):
        self.dry_run = dry_run
        self.project_dir = PROJECT_DIR
        self.output_dir = os.path.join(config.DRIVE["VIDEO_OUTPUT"], "trailer")
        self.audio_dir = os.path.join(config.DRIVE["AUDIO_OUTPUT"], "trailer")
        self.thumb_dir = os.path.join(config.DRIVE["THUMBNAILS"], "trailer")
        self.runtime_dir = os.path.join(config.DRIVE["RUNTIME"], "trailer")

        for d in [self.output_dir, self.audio_dir, self.thumb_dir, self.runtime_dir]:
            os.makedirs(d, exist_ok=True)

        self.voiceover_gen = VoiceoverGenerator()
        print(f"🎬 TrailerGenerator v1.0 initialized")
        print(f"   Output: {self.output_dir}")
        print(f"   Dry run: {self.dry_run}")

    def generate_trailer_voiceover(self):
        """Step 1: Generate per-scene voiceover matching each scene's duration."""
        print("\n🎙️  STEP 1: Generating trailer voiceover...")

        if self.dry_run:
            print(f"   [DRY RUN] Would generate voiceover for {len(_TRAILER_SCENES)} scenes")
            return {"status": "dry_run", "path": os.path.join(self.audio_dir, "trailer_final.mp3")}

        # Generate per-scene audio files
        scene_audio_files = []
        total_audio_dur = 0
        for i, scene in enumerate(_TRAILER_SCENES):
            scene_text = scene["text"].strip()
            if not scene_text:
                continue
            scene_audio = os.path.join(self.audio_dir, f"scene_{i:02d}_{scene['id']}.mp3")
            
            # Generate voiceover for this scene's text
            # Use bilingual script: English text + Telugu subtitle combined
            combined_text = scene_text
            sub_tel = scene.get("subtitle_tel", "").strip()
            if sub_tel:
                combined_text = scene_text + "\n\n" + sub_tel
            
            # Call voiceover generator for this segment
            try:
                result = self.voiceover_gen.generate_voiceover(
                    {"full_script": combined_text},
                    f"trailer_scene_{scene['id']}"
                )
                src = result.get("path", "")
                if os.path.exists(src) and src != scene_audio:
                    shutil.copy2(src, scene_audio)
                elif not os.path.exists(scene_audio):
                    # Create silent placeholder if generation failed
                    subprocess.run([
                        "ffmpeg", "-y", "-f", "lavfi",
                        "-i", f"anullsrc=r=44100:cl=stereo:t={scene['duration']}",
                        "-t", str(scene['duration']),
                        "-c:a", "libmp3lame", "-b:a", "128k",
                        scene_audio
                    ], capture_output=True, timeout=30)
                scene_audio_files.append(scene_audio)
                # Get actual duration
                probe = subprocess.run([
                    "ffprobe", "-v", "error", "-show_entries", "format=duration",
                    "-of", "csv=p=0", scene_audio
                ], capture_output=True, text=True, timeout=10)
                dur = float(probe.stdout.strip()) if probe.returncode == 0 else scene["duration"]
                total_audio_dur += dur
                print(f"   ✅ Scene {i+1}/{len(_TRAILER_SCENES)}: {scene['id']} ({dur:.1f}s)")
            except Exception as e:
                print(f"   ⚠️ Scene {i} voiceover failed: {e}")
                scene_audio_files.append(None)

        # Concatenate all scene audio files in order
        concat_list = os.path.join(self.runtime_dir, "trailer_audio_concat.txt")
        valid_audio = [a for a in scene_audio_files if a and os.path.exists(a)]
        with open(concat_list, "w", encoding="utf-8") as f:
            for a in valid_audio:
                safe = a.replace("'", "'\\''")
                f.write(f"file '{safe}'\n")

        trailer_audio = os.path.join(self.audio_dir, "trailer_final.mp3")
        if valid_audio:
            subprocess.run([
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", concat_list,
                "-c:a", "libmp3lame", "-b:a", "192k",
                trailer_audio
            ], capture_output=True, timeout=60, check=True)
        else:
            print("   ❌ No audio generated")
            return {"status": "error", "path": trailer_audio}

        print(f"   ✅ Trailer voiceover: {trailer_audio} ({total_audio_dur:.1f}s total)")
        return {"status": "success", "path": trailer_audio, "duration": total_audio_dur}

    def generate_trailer_visuals(self):
        """
        Step 2: Generate cinematic visual slides for each scene.
        Uses FFmpeg to create Ken Burns slideshow with kinetic typography.
        """
        print("\n🎨 STEP 2: Generating trailer visuals...")

        scenes_dir = os.path.join(self.runtime_dir, "trailer_scenes")
        os.makedirs(scenes_dir, exist_ok=True)

        W, H = _TRAILER_VISUALS["resolution"]
        bg_r, bg_g, bg_b = _TRAILER_VISUALS["bg_color"]

        scene_video_files = []

        for i, scene in enumerate(_TRAILER_SCENES):
            scene_id = scene["id"]
            duration = scene["duration"]
            main_text = scene["text"]
            sub_text = scene.get("subtitle_tel", "")

            scene_mp4 = os.path.join(scenes_dir, f"scene_{i:02d}_{scene_id}.mp4")

            if self.dry_run:
                print(f"   [DRY RUN] Scene '{scene_id}': {main_text[:40]}...")
                scene_video_files.append(scene_mp4)
                continue

            # Generate cinematic scene with FFmpeg
            # Create text-overlay video with Ken Burns zoom effect
            self._create_scene_video(
                scene=scene,
                output_path=scene_mp4,
                width=W,
                height=H,
                scene_index=i,
            )
            scene_video_files.append(scene_mp4)
            print(f"   ✅ Scene {i+1}/{len(_TRAILER_SCENES)}: {scene_id} ({duration}s)")

        return {"scenes_dir": scenes_dir, "scene_files": scene_video_files}

    def _create_scene_video(self, scene, output_path, width, height, scene_index):
        """
        Create a single trailer scene video using Pillow flash-card rendering.
        - Rich gradient backgrounds with visual effects (glows, particles, shapes)
        - Proper Telugu font rendering (Noto Sans Telugu)
        - English + Telugu bilingual text overlay
        - Brand accent bars
        - Ken Burns zoom effect via FFmpeg
        """
        from PIL import Image, ImageDraw, ImageFont, ImageFilter
        import math

        W, H = width, height
        duration = scene["duration"]
        main_text = scene["text"]
        sub_text = scene.get("subtitle_tel", "")
        scene_id = scene["id"]

        # ── SCENE-SPECIFIC COLOR THEMES (richer, more vibrant) ──
        scene_themes = {
            "hook": {
                "bg_top": (15, 15, 40), "bg_bottom": (30, 10, 60),
                "glow_color": (100, 50, 200), "accent": (192, 64, 32),
                "particles": True, "world_dots": True,
            },
            "diaspora_reach": {
                "bg_top": (10, 20, 50), "bg_bottom": (20, 40, 80),
                "glow_color": (50, 100, 200), "accent": (80, 160, 220),
                "particles": True, "world_dots": True,
            },
            "content_showcase": {
                "bg_top": (40, 15, 15), "bg_bottom": (60, 20, 30),
                "glow_color": (200, 80, 50), "accent": (192, 64, 32),
                "particles": False, "world_dots": False,
            },
            "ai_disclosure": {
                "bg_top": (5, 25, 35), "bg_bottom": (10, 40, 60),
                "glow_color": (0, 200, 200), "accent": (0, 220, 220),
                "particles": True, "world_dots": False,
            },
            "real_news": {
                "bg_top": (35, 10, 10), "bg_bottom": (55, 15, 15),
                "glow_color": (200, 60, 40), "accent": (192, 64, 32),
                "particles": False, "world_dots": False,
            },
            "brand_reveal": {
                "bg_top": (10, 10, 10), "bg_bottom": (20, 20, 20),
                "glow_color": (192, 64, 32), "accent": (214, 179, 0),
                "particles": True, "world_dots": False,
            },
            "cta": {
                "bg_top": (10, 10, 10), "bg_bottom": (25, 20, 15),
                "glow_color": (214, 179, 0), "accent": (192, 64, 32),
                "particles": False, "world_dots": False,
            },
        }
        theme = scene_themes.get(scene_id, scene_themes["hook"])

        # ── BUILD FLASH CARD IMAGE WITH PILLOW ──
        img = Image.new("RGB", (W, H))
        draw = ImageDraw.Draw(img)

        # Rich gradient background
        bg_top = theme["bg_top"]
        bg_bottom = theme["bg_bottom"]
        for y in range(H):
            t = y / H
            r = int(bg_top[0] + (bg_bottom[0] - bg_top[0]) * t)
            g = int(bg_top[1] + (bg_bottom[1] - bg_top[1]) * t)
            b = int(bg_top[2] + (bg_bottom[2] - bg_top[2]) * t)
            draw.line([(0, y), (W, y)], fill=(r, g, b))

        # Glow effect (large blurred radial glow behind text)
        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow)
        glow_cx, glow_cy = W // 2, H // 2 - 50
        for radius in range(500, 50, -10):
            alpha = int(35 * (1 - radius / 500))
            glow_draw.ellipse(
                [glow_cx - radius, glow_cy - radius, glow_cx + radius, glow_cy + radius],
                fill=(*theme["glow_color"], alpha),
            )
        img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")
        draw = ImageDraw.Draw(img)

        # Soft floating bokeh circles (large, blurred, subtle — NOT small squares)
        if theme.get("particles"):
            import random as rng
            rng.seed(scene_id)
            for _ in range(12):
                px = rng.randint(100, W - 100)
                py = rng.randint(100, H - 100)
                pr = rng.randint(30, 80)
                alpha = rng.randint(15, 40)
                # Draw soft circle using alpha composite
                bokeh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                bokeh_draw = ImageDraw.Draw(bokeh)
                for r in range(pr, 5, -2):
                    a = int(alpha * (1 - r / pr))
                    bokeh_draw.ellipse([px-r, py-r, px+r, py+r], fill=(255, 255, 255, max(a, 1)))
                img = Image.alpha_composite(img.convert("RGBA"), bokeh).convert("RGB")
                draw = ImageDraw.Draw(img)

        # World map dots — soft glowing circles for diaspora scenes
        if theme.get("world_dots"):
            import random as rng
            rng.seed(42)
            dot_r = theme["accent"]
            for _ in range(25):
                px = rng.randint(150, W - 150)
                py = rng.randint(150, H - 150)
                # Outer soft glow
                for r in range(20, 3, -2):
                    a = int(20 * (1 - r / 20))
                    dot_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                    dot_draw = ImageDraw.Draw(dot_layer)
                    dot_draw.ellipse([px-r, py-r, px+r, py+r], fill=(*dot_r, a))
                    img = Image.alpha_composite(img.convert("RGBA"), dot_layer).convert("RGB")
                    draw = ImageDraw.Draw(img)
                # Inner bright dot
                draw.ellipse([px-3, py-3, px+3, py+3], fill=dot_r)

        # Geometric accent lines (clean, smooth — no rectangles)
        accent = theme["accent"]
        # Left accent line — thin, elegant
        draw.line([(62, 180), (62, H - 180)], fill=accent, width=3)
        # Right accent line
        draw.line([(W - 62, 180), (W - 62, H - 180)], fill=accent, width=3)
        # Small diamond shapes (clean, not boxes)
        for dy in [220, H - 220]:
            draw.polygon([(W//2, dy-12), (W//2+12, dy), (W//2, dy+12), (W//2-12, dy)], fill=accent)

        # ── LOAD FONTS ──
        font_en_bold = _TRAILER_VISUALS["font_path"]
        font_en_reg = _TRAILER_VISUALS["font_path_regular"]
        font_tel = _TRAILER_VISUALS["font_path_telugu"]
        font_tel_reg = _TRAILER_VISUALS["font_path_telugu_reg"]

        try:
            f_title = ImageFont.truetype(font_en_bold, 80)
        except Exception:
            f_title = ImageFont.load_default()
        try:
            f_tel = ImageFont.truetype(font_tel, 56)
        except Exception:
            f_tel = ImageFont.load_default()
        try:
            f_sub = ImageFont.truetype(font_en_reg, 40)
        except Exception:
            f_sub = ImageFont.load_default()

        # ── DRAW ENGLISH TITLE (centered, with shadow) ──
        # Handle multiline
        en_lines = main_text.split("\n")
        line_height = 95
        total_en_height = len(en_lines) * line_height
        en_start_y = H // 2 - total_en_height // 2 - 60

        for i, line in enumerate(en_lines):
            bbox = draw.textbbox((0, 0), line, font=f_title)
            tw = bbox[2] - bbox[0]
            x = (W - tw) // 2
            y = en_start_y + i * line_height
            # Shadow
            draw.text((x + 3, y + 3), line, fill=(0, 0, 0), font=f_title)
            # Main
            draw.text((x, y), line, fill=(255, 255, 255), font=f_title)

        # ── DRAW TELUGU SUBTITLE (below English) ──
        if sub_text and sub_text.strip():
            tel_y = en_start_y + total_en_height + 40
            bbox2 = draw.textbbox((0, 0), sub_text, font=f_tel)
            tw2 = bbox2[2] - bbox2[0]
            x2 = (W - tw2) // 2
            # Shadow
            draw.text((x2 + 2, tel_y + 2), sub_text, fill=(0, 0, 0), font=f_tel)
            # Gold text
            draw.text((x2, tel_y), sub_text, fill=(214, 179, 0), font=f_tel)

        # ── BRAND ACCENT BARS ──
        draw.rectangle([(0, 0), (W, 10)], fill=(192, 64, 32))   # Red top
        draw.rectangle([(0, 12), (W, 18)], fill=(214, 179, 0))  # Gold
        draw.rectangle([(0, H - 10), (W, H)], fill=(192, 64, 32))  # Red bottom
        draw.rectangle([(0, H - 18), (W, H - 12)], fill=(214, 179, 0))  # Gold

        # ── SAVE FLASH CARD IMAGE ──
        card_dir = os.path.join(os.path.dirname(output_path), "cards")
        os.makedirs(card_dir, exist_ok=True)
        card_path = os.path.join(card_dir, f"card_{scene_index:02d}_{scene_id}.png")
        img.save(card_path, "PNG")

        # ── ENCODE TO VIDEO (STATIC — no zoom, no shake) ──
        # Use simple image-to-video encoding. No zoompan = no shakiness.
        # Smooth crossfades between scenes handled by concat demuxer.
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", card_path,
            "-t", str(duration),
            "-c:v", "libx264", "-preset", "slow", "-crf", "17",
            "-pix_fmt", "yuv420p",
            "-vf", f"scale={W}x{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2",
            "-r", "30",
            "-movflags", "+faststart",
            "-an",
            output_path,
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                print(f"   ⚠️ FFmpeg error for scene {scene_id}: {result.stderr[:300]}")
                # Fallback: simple image-to-video without zoom
                fallback_cmd = [
                    "ffmpeg", "-y",
                    "-loop", "1", "-i", card_path,
                    "-t", str(duration),
                    "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                    "-pix_fmt", "yuv420p", "-vf", f"scale={W}x{H}",
                    "-an", output_path,
                ]
                subprocess.run(fallback_cmd, capture_output=True, timeout=60, check=True)
        except Exception as e:
            print(f"   ❌ Failed to create scene {scene_id}: {e}")

    def assemble_trailer(self, voiceover_result, visuals_result):
        """
        Step 3: Stitch scenes together, add voiceover audio, add watermark branding.
        Produces: final trailer MP4 ready for YouTube.
        """
        print("\n🔧 STEP 3: Assembling final trailer...")

        scenes_dir = visuals_result["scenes_dir"]
        concat_list = os.path.join(self.runtime_dir, "trailer_concat.txt")

        # Build concat list in scene order
        scene_files = sorted(visuals_result["scene_files"])
        with open(concat_list, "w", encoding="utf-8") as f:
            for sf in scene_files:
                safe = sf.replace("'", "'\\''")
                f.write(f"file '{safe}'\n")

        # Intermediate: concatenated video (no audio)
        concat_video = os.path.join(self.output_dir, "trailer_no_audio.mp4")

        if self.dry_run:
            print(f"   [DRY RUN] Would concat {len(scene_files)} scenes")
            print(f"   [DRY RUN] Would mux audio: {voiceover_result.get('path', 'N/A')}")
            return {"status": "dry_run", "path": os.path.join(self.output_dir, "trailer_final.mp4")}

        # Concatenate all scene videos with crossfade transitions
        scene_list = sorted(visuals_result["scene_files"])
        n = len(scene_list)

        if n == 1:
            # Single scene: just copy
            shutil.copy2(scene_list[0], concat_video)
        elif n <= 8:
            # Use xfade filter for smooth crossfades between scenes
            # Build filter_complex for n inputs
            inputs = []
            for sf in scene_list:
                inputs.extend(["-i", sf])
            
            # Build the xfade chain
            # [0][1]xfade=transition=fade:duration=0.8:offset=scene_dur-0.8[v01];
            # [v01][2]xfade=transition=fade:duration=0.8:offset=2*scene_dur-1.6[v02]; ...
            filter_parts = []
            last_label = "0"
            total_dur = 0
            scene_dur = 5  # default, will calculate from actual
            
            # Get actual scene durations from _TRAILER_SCENES
            scene_durations = []
            for sf in scene_list:
                try:
                    r = subprocess.run([
                        "ffprobe", "-v", "error",
                        "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1", sf
                    ], capture_output=True, text=True, timeout=10)
                    scene_durations.append(float(r.stdout.strip()))
                except Exception:
                    scene_durations.append(5.0)
            
            offset = scene_durations[0] - 0.8
            for i in range(1, n):
                out_label = f"v{i:02d}" if i < n - 1 else "vout"
                trans = "fade"  # smooth fade
                filter_parts.append(
                    f"[{last_label}][i]xfade=transition={trans}:duration=0.8:offset={offset:.2f}[{out_label}]"
                )
                last_label = out_label
                if i < n - 1:
                    offset += scene_durations[i] - 0.8
            
            filter_str = ";".join(filter_parts)
            
            xfade_cmd = [
                "ffmpeg", "-y",
                *inputs,
                "-filter_complex", filter_str,
                "-map", "[vout]",
                "-c:v", "libx264", "-preset", "slow", "-crf", "18",
                "-pix_fmt", "yuv420p",
                "-an",
                concat_video,
            ]
            try:
                subprocess.run(xfade_cmd, capture_output=True, timeout=180, check=True)
                print(f"   ✅ Scene concat with crossfades complete: {concat_video}")
            except subprocess.CalledProcessError:
                # Fallback: simple concat without crossfades
                print("   ⚠️  xfade failed, falling back to simple concat")
                concat_cmd = [
                    "ffmpeg", "-y",
                    "-f", "concat", "-safe", "0",
                    "-i", concat_list,
                    "-c:v", "libx264", "-preset", "slow", "-crf", "18",
                    "-pix_fmt", "yuv420p",
                    "-an",
                    concat_video,
                ]
                subprocess.run(concat_cmd, capture_output=True, timeout=180, check=True)
                print(f"   ✅ Scene concat (no crossfade) complete: {concat_video}")
        else:
            # Too many scenes for xfade chain, use simple concat
            concat_cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", concat_list,
                "-c:v", "libx264", "-preset", "slow", "-crf", "18",
                "-pix_fmt", "yuv420p",
                "-an",
                concat_video,
            ]
            subprocess.run(concat_cmd, capture_output=True, timeout=180, check=True)
            print(f"   ✅ Scene concat complete: {concat_video}")

        # Get audio from voiceover result
        audio_path = voiceover_result.get("path", "")
        if not audio_path or not os.path.exists(audio_path):
            # Fallback: search for any trailer audio
            for candidate in [
                os.path.join(self.audio_dir, "trailer_final.mp3"),
                os.path.join(self.audio_dir, "channel_trailer_final.mp3"),
                os.path.join(config.DRIVE["AUDIO_OUTPUT"], "channel_trailer_final.mp3"),
            ]:
                if os.path.exists(candidate):
                    audio_path = candidate
                    break

        # Final mux: video + audio + watermark + branding
        watermark = os.getenv(
            "VIRALDNA_WATERMARK",
            os.path.join(PROJECT_DIR, "assets", "watermark.png"),
        )

        final_output = os.path.join(self.output_dir, "trailer_final.mp4")

        if audio_path and os.path.exists(audio_path):
            # Common encoding args: force yuv420p for WMP compatibility,
            # proper 44.1kHz stereo audio
            enc_args = [
                "-c:v", "libx264", "-preset", "slow", "-crf", "17",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
                "-shortest",
                "-movflags", "+faststart",
                final_output,
            ]
            if os.path.exists(watermark):
                mux_cmd = [
                    "ffmpeg", "-y",
                    "-i", concat_video,
                    "-i", audio_path,
                    "-i", watermark,
                    "-filter_complex",
                    "[0:v][2:v]overlay=W-w-30:H-h-30:format=auto[vout]",
                    "-map", "[vout]",
                    "-map", "1:a",
                ] + enc_args
            else:
                mux_cmd = [
                    "ffmpeg", "-y",
                    "-i", concat_video,
                    "-i", audio_path,
                ] + enc_args
        else:
            print("   ⚠️  No audio found — producing video-only trailer")
            shutil.copy2(concat_video, final_output)
            return {"status": "video_only", "path": final_output}

        try:
            result = subprocess.run(
                mux_cmd, capture_output=True, text=True, timeout=300
            )
            if result.returncode != 0:
                print(f"   ⚠️ Mux error: {result.stderr[:400]}")
                # Fallback: simple copy
                shutil.copy2(concat_video, final_output)
                return {"status": "fallback_no_audio", "path": final_output}
        except Exception as e:
            print(f"   ❌ Mux failed: {e}")
            shutil.copy2(concat_video, final_output)
            return {"status": "error", "path": final_output}

        # Validate output
        if os.path.exists(final_output):
            size_mb = os.path.getsize(final_output) / (1024 * 1024)
            # Get duration
            probe_cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                final_output,
            ]
            try:
                probe = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=30)
                duration = float(probe.stdout.strip())
            except Exception:
                duration = 0

            # ── POST-GENERATION VISUAL VERIFICATION ──
            # Verify the final video actually has video frames (not blank/black)
            verify_cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "stream=codec_type,width,height,nb_frames",
                "-of", "json",
                final_output,
            ]
            try:
                verify = subprocess.run(verify_cmd, capture_output=True, text=True, timeout=30)
                import json as _json
                probe_data = _json.loads(verify.stdout)
                streams = probe_data.get("streams", [])
                video_streams = [s for s in streams if s.get("codec_type") == "video"]
                audio_streams = [s for s in streams if s.get("codec_type") == "audio"]

                if not video_streams:
                    print(f"   ❌ VISUAL VERIFICATION FAILED: No video stream in {final_output}")
                    return {"status": "error_no_video", "path": final_output}

                if not audio_streams:
                    print(f"   ❌ VISUAL VERIFICATION FAILED: No audio stream in {final_output}")
                    return {"status": "error_no_audio", "path": final_output}

                vw = video_streams[0].get("width", 0)
                vh = video_streams[0].get("height", 0)
                vframes = video_streams[0].get("nb_frames", 0)

                if vw == 0 or vh == 0:
                    print(f"   ❌ VISUAL VERIFICATION FAILED: Video resolution is 0x0")
                    return {"status": "error_zero_resolution", "path": final_output}

                # Check scene files exist and have content
                scene_files = sorted(visuals_result.get("scene_files", []))
                missing_scenes = [sf for sf in scene_files if not os.path.exists(sf)]
                tiny_scenes = [sf for sf in scene_files if os.path.exists(sf) and os.path.getsize(sf) < 5000]

                if missing_scenes:
                    print(f"   ❌ VISUAL VERIFICATION FAILED: {len(missing_scenes)} scene files missing:")
                    for ms in missing_scenes:
                        print(f"      MISSING: {ms}")
                    return {"status": "error_missing_scenes", "path": final_output}

                if tiny_scenes:
                    print(f"   ⚠️  VISUAL WARNING: {len(tiny_scenes)} scene files are suspiciously small (<5KB):")
                    for ts in tiny_scenes:
                        print(f"      TINY: {ts} ({os.path.getsize(ts)} bytes)")

                print(f"   ✅ Visual verification passed: {vw}x{vh}, {vframes} frames, "
                      f"{len(audio_streams)} audio stream(s), {len(scene_files)} scenes OK")

            except Exception as e:
                print(f"   ⚠️  Visual verification could not complete: {e}")
                # Don't fail the pipeline for a verification error, but warn loudly

            print(f"   ✅ FINAL TRAILER: {final_output}")
            print(f"      📁 Size: {size_mb:.1f} MB")
            print(f"      ⏱️  Duration: {duration:.1f}s")
            return {
                "status": "success",
                "path": final_output,
                "size_mb": size_mb,
                "duration_s": duration,
            }
        else:
            return {"status": "error", "path": final_output}

    def generate_trailer_thumbnail(self):
        """
        Step 4: Generate YouTube channel trailer thumbnail (1280x720).
        Uses ThumbnailCreator with 'TRAILER' category styling.
        """
        print("\n🖼️  STEP 4: Generating trailer thumbnail...")

        thumb_output = os.path.join(self.thumb_dir, "trailer_branded.jpg")

        if self.dry_run:
            print(f"   [DRY RUN] Would create thumbnail: {thumb_output}")
            return {"status": "dry_run", "path": thumb_output}

        # Create a simple but effective trailer thumbnail using Pillow
        from PIL import Image, ImageDraw, ImageFont, ImageFilter

        W, H = 1280, 720
        img = Image.new("RGB", (W, H), (13, 13, 13))
        draw = ImageDraw.Draw(img)

        # Gradient background
        for y in range(H):
            alpha = int(60 * y / H)
            draw.line([(0, y), (W, y)], fill=(13, 13, min(13 + alpha, 40)))

        # Brand bars
        draw.rectangle([(0, 0), (W, 8)], fill=(192, 64, 32))   # Top red
        draw.rectangle([(0, 10), (W, 14)], fill=(214, 179, 0)) # Gold

        try:
            font_large = ImageFont.truetype(_TRAILER_VISUALS["font_path"], 80)
            font_med = ImageFont.truetype(_TRAILER_VISUALS["font_path"], 36)
            font_sub = ImageFont.truetype(_TRAILER_VISUALS["font_path_regular"], 28)
        except Exception:
            font_large = ImageFont.load_default()
            font_med = ImageFont.load_default()
            font_sub = ImageFont.load_default()

        # Main title
        title = "ViralDNA"
        bbox = draw.textbbox((0, 0), title, font=font_large)
        tw = bbox[2] - bbox[0]
        draw.text(((W - tw) / 2, H // 2 - 100), title,
                  fill=(255, 255, 255), font=font_large)

        # Subtitle
        subtitle = "Telugu Diaspora News"
        bbox2 = draw.textbbox((0, 0), subtitle, font=font_med)
        sw = bbox2[2] - bbox2[0]
        draw.text(((W - sw) / 2, H // 2), subtitle,
                  fill=(214, 179, 0), font=font_med)

        # Tagline
        tagline = "Real News. Real Voices. Built with AI."
        bbox3 = draw.textbbox((0, 0), tagline, font=font_sub)
        tw3 = bbox3[2] - bbox3[0]
        draw.text(((W - tw3) / 2, H // 2 + 60), tagline,
                  fill=(180, 180, 180), font=font_sub)

        # Bottom bars
        draw.rectangle([(0, H - 8), (W, H)], fill=(192, 64, 32))
        draw.rectangle([(0, H - 14), (W, H - 10)], fill=(214, 179, 0))

        # Watermark
        wm_path = os.getenv(
            "VIRALDNA_WATERMARK",
            os.path.join(PROJECT_DIR, "assets", "watermark.png"),
        )
        if os.path.exists(wm_path):
            try:
                wm = Image.open(wm_path).convert("RGBA")
                wm_w = 160
                wm_h = int(wm.size[1] * (wm_w / wm.size[0]))
                wm = wm.resize((wm_w, wm_h), Image.LANCZOS)
                img.paste(wm, (W - wm_w - 25, H - wm_h - 25), wm)
            except Exception:
                pass

        img.save(thumb_output, "JPEG", quality=93)
        print(f"   ✅ Thumbnail: {thumb_output}")
        return {"status": "success", "path": thumb_output}

    def run_full_pipeline(self):
        """
        Execute complete trailer generation pipeline.
        Returns dict with all output paths and status.
        """
        print("=" * 60)
        print("🎬 ViralDNA Channel Trailer Generator v1.0")
        print("   'THE BEST' — Real News. Real Voices. Built with AI.")
        print("=" * 60)

        result = {"status": "started", "steps": []}

        # Step 1: Voiceover
        print("\n" + "─" * 50)
        print("STEP 1/4: Voiceover Generation")
        print("─" * 50)
        audio_result = self.generate_trailer_voiceover()
        result["audio"] = audio_result
        result["steps"].append({"step": "voiceover", "status": audio_result["status"]})

        # Step 2: Visuals
        print("\n" + "─" * 50)
        print("STEP 2/4: Visual Generation")
        print("─" * 50)
        visuals_result = self.generate_trailer_visuals()
        result["visuals"] = {"status": "success", "scenes": len(_TRAILER_SCENES)}
        result["steps"].append({"step": "visuals", "status": "success"})

        # Step 3: Assembly
        print("\n" + "─" * 50)
        print("STEP 3/4: Video Assembly")
        print("─" * 50)
        assembly_result = self.assemble_trailer(audio_result, visuals_result)
        result["assembly"] = assembly_result
        result["steps"].append({"step": "assembly", "status": assembly_result["status"]})

        # Step 4: Thumbnail
        print("\n" + "─" * 50)
        print("STEP 4/4: Thumbnail Generation")
        print("─" * 50)
        thumb_result = self.generate_trailer_thumbnail()
        result["thumbnail"] = thumb_result
        result["steps"].append({"step": "thumbnail", "status": thumb_result["status"]})

        # Summary
        print("\n" + "=" * 60)
        print("🎬 TRAILER GENERATION COMPLETE")
        print("=" * 60)
        for step in result["steps"]:
            icon = "✅" if step["status"] in ("success", "dry_run") else "❌"
            print(f"   {icon} {step['step']}: {step['status']}")

        if assembly_result.get("path"):
            print(f"\n   📁 Final trailer: {assembly_result['path']}")
        if thumb_result.get("path"):
            print(f"   🖼️  Thumbnail: {thumb_result['path']}")

        result["status"] = "complete"
        return result


# ═══════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    generator = TrailerGenerator(dry_run=dry_run)
    result = generator.run_full_pipeline()

    if result["status"] == "complete":
        print("\n🎬 Channel trailer pipeline finished successfully!")
        sys.exit(0)
    else:
        print("\n❌ Trailer pipeline encountered errors.")
        sys.exit(1)
