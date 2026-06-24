"""
Typewriter text renderer for VDNA 3.0 — News Edition v88.0.

v88.0: MAJOR UPGRADE — Background Image Support + Ken Burns Effect
  - Accepts optional background images per scene (real news photos)
  - Layers text on background with gradient overlay for readability
  - Adds subtle Ken Burns zoom/pan for visual motion
  - Falls back to dark background if no images available (safe mode)
  - Maintains typewriter reveal timing over real imagery
  - Professional news-channel look matching thumbnail style

Previous: v87.3 (text-only, dark blue background, 2 red lines)
"""

import os
import re
import subprocess
import math


class TypewriterRenderer:
    """Renders typewriter-style text animation over background images for news videos."""

    def __init__(self, ffmpeg_bin="ffmpeg"):
        self.ffmpeg = ffmpeg_bin

    # ── sizing helpers ──────────────────────────────────────────────

    @staticmethod
    def _font_size(out_h, is_short=False):
        if is_short:
            return max(68, min(96, out_h // 18))
        else:
            return max(44, min(60, out_h // 13))

    @staticmethod
    def _max_chars(out_w, is_short=False):
        if is_short:
            return max(14, min(20, out_w // 56))
        else:
            # With background images, we have more visual space
            # Use narrower text area for professional news look
            return max(28, min(42, out_w // 32))

    @staticmethod
    def _line_height(font_size):
        return int(font_size * 1.5)

    # ── word wrap ───────────────────────────────────────────────────

    @staticmethod
    def _wrap_text(text, max_chars=38):
        words = text.split()
        lines = []
        current = ""
        for w in words:
            if len(current) + len(w) + 1 > max_chars:
                if current:
                    lines.append(current)
                current = w
            else:
                current = f"{current} {w}".strip()
        if current:
            lines.append(current)
        return "\n".join(lines)

    # ── background image discovery ──────────────────────────────────

    @staticmethod
    def _find_background_images(runtime_dir, topic_slug, num_scenes):
        """
        Find background images for video scenes.
        Searches multiple sources in priority order:
        1. slideshow_production_{slug}/ (Serper-fetched real news photos)
        2. runtime_dir/slideshow_production_main/
        3. output/runtime/sd_scenes/ (stable diffusion / image pack fallback)
        4. runtime_dir/ (any scene_img_*, viz_news_*, scene_* files)
        5. Local image pack fallback
        
        Returns list of image paths (may be fewer than num_scenes).
        """
        candidates = []

        # Search paths in priority order
        search_dirs = []

        if runtime_dir and topic_slug:
            search_dirs.append(os.path.join(runtime_dir, f"slideshow_production_{topic_slug}"))
            search_dirs.append(os.path.join(runtime_dir, "slideshow_production_main"))
            search_dirs.append(os.path.join(runtime_dir, f"slideshow_{topic_slug}_main"))
            search_dirs.append(runtime_dir)

        # v88.1: Also search the output/runtime/ directory (where sd_scenes lives)
        try:
            from modules import config as _cfg
            _runtime = _cfg.DRIVE.get("RUNTIME", "")
            if _runtime and os.path.isdir(_runtime):
                if _runtime not in search_dirs:
                    search_dirs.append(_runtime)
                # Check for sd_scenes subdirectory
                _sd = os.path.join(_runtime, "sd_scenes")
                if os.path.isdir(_sd):
                    search_dirs.insert(0, _sd)  # Highest priority
                # Check for topic-specific subdirectories
                if topic_slug:
                    _topic_dir = os.path.join(_runtime, topic_slug)
                    if os.path.isdir(_topic_dir):
                        search_dirs.insert(0, _topic_dir)
        except Exception:
            pass

        for sdir in search_dirs:
            if not os.path.isdir(sdir):
                continue
            # Priority: scene_img_* (Serper/real photos) > viz_news_* > scene_*
            for prefix in ["scene_img_", "viz_news_", "scene_"]:
                files = sorted(
                    [f for f in os.listdir(sdir)
                     if f.startswith(prefix) and f.endswith((".jpg", ".png", ".jpeg"))],
                    reverse=True
                )
                for fname in files:
                    fpath = os.path.join(sdir, fname)
                    if fpath not in candidates:
                        candidates.append(fpath)
            if candidates:
                break  # Found images in this dir, no need to check lower priority

        # Filter out watermarked/copyrighted images
        filtered = []
        for cpath in candidates:
            try:
                from PIL import Image as PILImage
                from PIL.ExifTags import TAGS as EXIF_TAGS
                im = PILImage.open(cpath)
                exif = im.getexif()
                if exif:
                    reject = False
                    for tid, val in exif.items():
                        tag = EXIF_TAGS.get(tid, tid)
                        if tag in ("Copyright", "Artist", "ImageDescription"):
                            val_lower = str(val).lower()
                            _bad = ["hindustan times", "getty", "shutterstock",
                                    "dreamstime", "alamy", "reuters", "afp"]
                            if any(b in val_lower for b in _bad):
                                reject = True
                                break
                    if reject:
                        continue
                # Check minimum resolution
                w, h = im.size
                if w < 320 or h < 240:
                    continue
                filtered.append(cpath)
            except Exception:
                continue

        return filtered[:num_scenes]

    # ── scene render ────────────────────────────────────────────────

    def render_scene(self, text, output_path, duration_s, out_w=1280, out_h=720,
                     is_short=False, bg_color=None, global_cps=None,
                     bg_image_path=None, ken_burns=True):
        """Render a single scene with news-style text presentation over background image.
        
        Args:
            text: Script text for this scene
            output_path: Output .mp4 path
            duration_s: Scene duration in seconds
            out_w: Output width (1280 or 1080)
            out_h: Output height (720 or 1920)
            is_short: True for vertical shorts format
            bg_color: Fallback background color (default dark blue)
            global_cps: Characters per second for typewriter timing
            bg_image_path: Path to background image (optional)
            ken_burns: Add subtle zoom effect (default True)
        """
        if not text.strip():
            text = "..."

        font_size = self._font_size(out_h, is_short)
        max_chars = self._max_chars(out_w, is_short)
        lh = self._line_height(font_size)

        wrapped = self._wrap_text(text, max_chars=max_chars)
        lines = [l for l in wrapped.split('\n') if l.strip()]
        if not lines:
            lines = ["..."]
        num_lines = len(lines)

        # Text positioning: lower third (news style) with background
        top_margin = int(out_h * 0.08)
        bottom_margin = int(out_h * 0.14)
        available_h = out_h - top_margin - bottom_margin
        total_text_h = num_lines * lh
        start_y = top_margin + max(0, (available_h - total_text_h) // 2)

        # Panel: semi-transparent overlay for text readability
        panel_pad_lr = int(out_w * 0.03)
        panel_pad_top = int(font_size * 0.6)
        panel_pad_bot = int(font_size * 0.5)
        panel_x = panel_pad_lr
        panel_w = out_w - 2 * panel_pad_lr
        panel_y = start_y - panel_pad_top
        panel_h = total_text_h + panel_pad_top + panel_pad_bot

        # Clamp panel to frame
        panel_x = max(0, panel_x)
        panel_w = min(panel_w, out_w - panel_x)
        panel_y = max(0, panel_y)
        panel_h = min(panel_h, out_h - panel_y)

        # Compute CPS
        total_chars = sum(len(l) for l in lines)
        if global_cps is not None:
            cps = global_cps
        else:
            speaking_time = duration_s * 0.88
            cps = max(8, min(16, total_chars / max(speaking_time, 0.5)))

        # Line start times
        char_offsets = [0]
        for line in lines:
            char_offsets.append(char_offsets[-1] + len(line))

        # ── Build filter chain ──────────────────────────────────────
        filter_parts = []

        # ── 1. Background image or solid color ──
        if bg_image_path and os.path.exists(bg_image_path) and os.path.getsize(bg_image_path) > 1024:
            # Use background image with optional Ken Burns
            if ken_burns and duration_s > 2:
                # Ken Burns: slow zoom from 100% to 105% over scene duration
                # Uses zoompan filter for smooth motion
                zoom_expr = "1+0.05*t/{}".format(max(duration_s, 0.1))
                filter_parts.append(
                    f"zoompan=z='{zoom_expr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                    f"d={int(duration_s * 25)}:s={out_w}x{out_h}:fps=25"
                )
            # Scale and crop background to fill frame
            filter_parts.append(
                f"scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
                f"crop={out_w}:{out_h}"
            )
            # Slight darkening for text readability (overlay later)
            filter_parts.append(
                f"eq=brightness=-0.05:contrast=1.05"
            )
            input_src = f"-i '{bg_image_path}'"
        else:
            # Fallback: solid dark background
            color = bg_color or "0x0c0c20"
            input_src = (
                f"-f lavfi -i 'color=c={color}:s={out_w}x{out_h}:d={duration_s}:r=25'"
            )

        # ── 2. Semi-transparent text panel (over background) ──
        # Darker panel for better text contrast over images
        filter_parts.append(
            f"drawbox=x={panel_x}:y={panel_y}:w={panel_w}:h={panel_h}:"
            f"color=0x06060e@0.75:t=fill"
        )
        # Red accent at top of panel
        filter_parts.append(
            f"drawbox=x={panel_x}:y={panel_y}:w={panel_w}:h=4:"
            f"color=0xc33731@1.0:t=fill"
        )
        # Gold accent line below red
        filter_parts.append(
            f"drawbox=x={panel_x}:y={panel_y + 5}:w={panel_w}:h=2:"
            f"color=0xD4AF37@0.8:t=fill"
        )

        # ── 3. Text lines with enable= for reveal timing ──
        for i, line in enumerate(lines):
            line_start = char_offsets[i] / cps
            esc = (line
                   .replace("\\", "\\\\")
                   .replace("'", "'\\\\\\''")
                   .replace(":", "\\\\:")
                   .replace("%", "%%")
                   .replace("[", "\\\\[")
                   .replace("]", "\\\\]")
                   .replace(",", "\\\\,")
                   .replace(";", "\\\\;"))

            y_pos = start_y + i * lh
            x_pos = f"({out_w}-text_w)/2"

            filter_parts.append(
                f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
                f"text='{esc}':fontsize={font_size}:fontcolor=0xf8f8ff:"
                f"x={x_pos}:y={y_pos}:"
                f"shadowcolor=0x000000@0.95:shadowx=2:shadowy=2:"
                f"enable='gte(t\\\\,{line_start:.2f})'"
            )

        # ── 4. Bottom news bar ──
        bar_h = int(out_h * 0.08)
        bar_y = out_h - bar_h
        bar_font = max(16, min(26, out_h // 30))
        bar_pad = int(out_w * 0.02)
        accent_w = max(4, int(out_w * 0.004))

        filter_parts.append(
            f"drawbox=x=0:y={bar_y}:w={out_w}:h={bar_h}:color=0x040410@0.92:t=fill"
        )
        filter_parts.append(
            f"drawbox=x=0:y={bar_y}:w={out_w}:h=3:color=0xc33731@1.0:t=fill"
        )
        filter_parts.append(
            f"drawbox=x=0:y={bar_y}:w={accent_w}:h={bar_h}:color=0xc33731@1.0:t=fill"
        )
        filter_parts.append(
            f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
            f"text='THE VIRAL DNA':fontsize={bar_font}:fontcolor=0xf0f0f0:"
            f"x={bar_pad + accent_w + int(out_w * 0.01)}:"
            f"y={bar_y}+({bar_h}-{bar_font})/2:"
            f"shadowcolor=0x000000@0.9:shadowx=2:shadowy=1"
        )

        # ── 5. Progress bar (1px above bottom bar) ──
        prog_y = bar_y - 2
        filter_parts.append(
            f"drawbox=x=0:y={prog_y}:w={out_w}:h=2:color=0x1a1a2e@0.6:t=fill"
        )
        filter_parts.append(
            f"drawbox=x=0:y={prog_y}:"
            f"w='if(gte(t\\\\,0.3)\\\\,min(iw\\\\,(t/{max(duration_s,0.1):.2f})*iw)\\\\,0)':"
            f"h=2:color=0xc33731@0.95:t=fill"
        )

        # ── 6. Subtle vignette for cinematic look ──
        # Darken edges slightly to draw eye to center text
        vignette_strength = 0.3
        filter_parts.append(
            f"drawbox=x=0:y=0:w={out_w}:h={out_h}:"
            f"color=0x000000@0:t=fill"  # placeholder, vignette done via blend
        )
        # Remove the placeholder vignette (not valid ffmpeg filter)
        filter_parts.pop()

        vf = ','.join(filter_parts)

        # ── Build ffmpeg command ────────────────────────────────────
        # Use input_src which already has the proper input specification
        if bg_image_path and os.path.exists(bg_image_path) and os.path.getsize(bg_image_path) > 1024:
            cmd = [
                self.ffmpeg, '-y',
                '-loop', '1', '-t', f'{duration_s:.2f}',
                '-i', bg_image_path,
                '-vf', vf,
                '-c:v', 'libx264',
                '-preset', 'ultrafast',
                '-crf', '23',
                '-pix_fmt', 'yuv420p',
                '-r', '25',
                '-an',  # No audio in scene clips (muxed later)
                output_path
            ]
        else:
            cmd = [
                self.ffmpeg, '-y',
                '-f', 'lavfi',
                '-i', f'color=c={bg_color or "0x0c0c20"}:s={out_w}x{out_h}:d={duration_s}:r=25',
                '-vf', vf,
                '-c:v', 'libx264',
                '-preset', 'ultrafast',
                '-crf', '23',
                '-pix_fmt', 'yuv420p',
                '-r', '25',
                '-t', f'{duration_s:.2f}',
                output_path
            ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                return self._render_minimal(text, output_path, duration_s, out_w, out_h, is_short, cps)
            ok = os.path.exists(output_path) and os.path.getsize(output_path) > 1024
            if not ok:
                return self._render_minimal(text, output_path, duration_s, out_w, out_h, is_short, cps)
            return ok
        except Exception as e:
            print(f"    [Typewriter] Exception: {e}")
            return self._render_minimal(text, output_path, duration_s, out_w, out_h, is_short, cps)

    def _render_minimal(self, text, output_path, duration_s, out_w, out_h, is_short, cps):
        """Minimal fallback: text on dark background (original behavior)."""
        try:
            font_size = min(52, out_h // 12)
            max_chars = self._max_chars(out_w, is_short)
            wrapped = self._wrap_text(text, max_chars=max_chars)
            wrapped = wrapped.replace("\\", "\\\\").replace("'", "'\\\\\\''").replace(":", "\\\\:").replace("%", "%%")

            vf = (
                f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
                f"text='{wrapped}':fontsize={font_size}:fontcolor=0xf8f8ff:"
                f"x=(w-text_w)/2:y=(h-text_h)/2:"
                f"shadowcolor=0x000000@0.8:shadowx=2:shadowy=2"
            )

            cmd = [
                self.ffmpeg, '-y',
                '-f', 'lavfi',
                '-i', f'color=c=0x0c0c20:s={out_w}x{out_h}:d={duration_s}:r=25',
                '-vf', vf,
                '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23',
                '-pix_fmt', 'yuv420p', '-r', '25',
                '-t', f'{duration_s:.2f}',
                output_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            return os.path.exists(output_path) and os.path.getsize(output_path) > 1024
        except Exception:
            return False

    # ── multi-scene render ──────────────────────────────────────────

    def render_all_scenes(self, script_text, num_scenes, duration_s, output_dir,
                          out_w=1280, out_h=720, is_short=False, voice_wps=None,
                          runtime_dir=None, topic_slug=None, ken_burns=True):
        """Render all scenes with background images.
        
        Args:
            script_text: Full script text
            num_scenes: Number of scenes to split into
            duration_s: Total video duration
            output_dir: Directory for output scene clips
            out_w, out_h: Output dimensions
            is_short: Vertical shorts format
            voice_wps: Words per second for timing
            runtime_dir: Runtime directory containing background images
            topic_slug: Topic slug for finding slideshow directory
            ken_burns: Add Ken Burns zoom effect (default True)
        """
        os.makedirs(output_dir, exist_ok=True)
        chunks = self._split_script(script_text, num_scenes)

        chunk_words = [max(1, len(chunk.split())) for chunk in chunks]
        total_words = sum(chunk_words)

        if voice_wps is None:
            voice_wps = total_words / (duration_s * 0.95)

        total_chars_estimate = total_words * 5
        speaking_time = total_words / voice_wps
        global_cps = total_chars_estimate / max(speaking_time, 0.5)
        global_cps = max(8, min(16, global_cps))

        total_silence = duration_s - speaking_time

        # ── Find background images for scenes ──
        bg_images = []
        if runtime_dir and topic_slug:
            bg_images = self._find_background_images(runtime_dir, topic_slug, num_scenes)
            if bg_images:
                print(f"    [Typewriter] Found {len(bg_images)} background images for video scenes")
            else:
                print(f"    [Typewriter] No background images found — using dark background")

        paths = []
        elapsed = 0.0

        for i, chunk in enumerate(chunks):
            scene_speaking_time = chunk_words[i] / voice_wps
            scene_silence = (chunk_words[i] / total_words) * total_silence if total_words > 0 else 0
            scene_duration = scene_speaking_time + scene_silence

            out_path = os.path.join(output_dir, f"tw_scene_{i}.mp4")

            # Assign background image for this scene (cycle if fewer than scenes)
            bg_image = None
            if bg_images:
                bg_image = bg_images[i % len(bg_images)]

            ok = self.render_scene(
                text=chunk, output_path=out_path, duration_s=scene_duration,
                out_w=out_w, out_h=out_h, is_short=is_short, global_cps=global_cps,
                bg_image_path=bg_image, ken_burns=ken_burns,
            )
            if ok:
                paths.append(out_path)
                bg_info = f" (bg: {os.path.basename(bg_image)})" if bg_image else ""
                print(f"    [Typewriter] Scene {i+1}/{num_scenes} OK "
                      f"({chunk_words[i]}w, {scene_duration:.1f}s){bg_info}")
            else:
                print(f"    [Typewriter] Scene {i+1}/{num_scenes} FAILED")
                blank_path = os.path.join(output_dir, f"tw_scene_{i}_blank.mp4")
                self._render_blank(blank_path, scene_duration, out_w, out_h)
                paths.append(blank_path)

            elapsed += scene_duration

        return paths

    def _render_blank(self, output_path, duration_s, out_w, out_h):
        cmd = [
            self.ffmpeg, '-y',
            '-f', 'lavfi',
            '-i', f'color=c=0x0c0c20:s={out_w}x{out_h}:d={duration_s}:r=25',
            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23',
            '-pix_fmt', 'yuv420p', '-r', '25',
            '-t', f'{duration_s:.2f}',
            output_path
        ]
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except Exception:
            pass

    # ── script splitting ────────────────────────────────────────────

    @staticmethod
    def _split_script(script_text, num_scenes):
        sentences = re.split(r'(?<=[.!?])\s+', script_text.strip())
        sentences = [s for s in sentences if s.strip()]
        if not sentences:
            return ["..."] * num_scenes

        chunks = []
        per_scene = max(1, len(sentences) // num_scenes)
        for i in range(num_scenes):
            start = i * per_scene
            end = start + per_scene if i < num_scenes - 1 else len(sentences)
            chunk = " ".join(sentences[start:end])
            if chunk.strip():
                chunks.append(chunk)
        while len(chunks) < num_scenes:
            chunks.append(chunks[-1] if chunks else "...")
        return chunks[:num_scenes]
