"""
Typewriter text renderer for VDNA 3.0 — News Edition.

Renders text with per-line reveal effect over a premium dark background.
Layout: text centered in the full frame with a large semi-transparent panel,
bottom news bar with branding, and progress indicator.
All ffmpeg filters — no external images, no AI visuals.
"""

import os
import re
import subprocess


class TypewriterRenderer:
    """Renders typewriter-style text animation for news videos."""

    def __init__(self, ffmpeg_bin="ffmpeg"):
        self.ffmpeg = ffmpeg_bin

    # ── sizing helpers ──────────────────────────────────────────────

    @staticmethod
    def _font_size(out_h, is_short=False):
        if is_short:
            return max(72, min(100, out_h // 18))
        else:
            # Large, readable font — fills the frame
            return max(48, min(64, out_h // 12))

    @staticmethod
    def _max_chars(out_w, is_short=False):
        if is_short:
            return max(14, min(20, out_w // 56))
        else:
            # Wide text area — fewer, longer lines
            return max(32, min(48, out_w // 28))

    @staticmethod
    def _line_height(font_size):
        return int(font_size * 1.55)

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

    # ── scene render ────────────────────────────────────────────────

    def render_scene(self, text, output_path, duration_s, out_w=1280, out_h=720,
                     is_short=False, bg_color=None, global_cps=None):
        """Render a single scene with news-style text presentation."""
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

        # Center text block in the frame (leave 8% top, 18% bottom for bar)
        top_margin = int(out_h * 0.10)
        bottom_margin = int(out_h * 0.16)
        available_h = out_h - top_margin - bottom_margin
        total_text_h = num_lines * lh
        start_y = top_margin + max(0, (available_h - total_text_h) // 2)

        # Panel: full width minus generous side padding
        panel_pad_lr = int(out_w * 0.04)
        panel_pad_top = int(font_size * 0.8)
        panel_pad_bot = int(font_size * 0.6)
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

        # 1. Text background panel (large, prominent)
        filter_parts.append(
            f"drawbox=x={panel_x}:y={panel_y}:w={panel_w}:h={panel_h}:"
            f"color=0x08081a@0.80:t=fill"
        )
        # Red accent at top of panel
        filter_parts.append(
            f"drawbox=x={panel_x}:y={panel_y}:w={panel_w}:h=4:"
            f"color=0xc33731@1.0:t=fill"
        )

        # 2. Text lines with enable= for reveal timing
        for i, line in enumerate(lines):
            line_start = char_offsets[i] / cps
            esc = (line
                   .replace("\\", "\\\\")
                   .replace("'", "'\\\\''")
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
                f"shadowcolor=0x000000@0.9:shadowx=2:shadowy=2:"
                f"enable='gte(t\\,{line_start:.2f})'"
            )

        # 3. Bottom news bar
        bar_h = int(out_h * 0.10)
        bar_y = out_h - bar_h
        bar_font = max(18, min(28, out_h // 28))
        bar_pad = int(out_w * 0.03)
        accent_w = max(4, int(out_w * 0.005))

        filter_parts.append(
            f"drawbox=x=0:y={bar_y}:w={out_w}:h={bar_h}:color=0x060612@0.90:t=fill"
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
            f"x={bar_pad+accent_w+int(out_w*0.01)}:"
            f"y={bar_y}+({bar_h}-{bar_font})/2:"
            f"shadowcolor=0x000000@0.9:shadowx=2:shadowy=1"
        )

        # 4. Progress bar (1px above bottom bar)
        prog_y = bar_y - 2
        filter_parts.append(
            f"drawbox=x=0:y={prog_y}:w={out_w}:h=2:color=0x1a1a2e@0.6:t=fill"
        )
        filter_parts.append(
            f"drawbox=x=0:y={prog_y}:"
            f"w='if(gte(t\\,0.3)\\,min(iw\\,(t/{max(duration_s,0.1):.2f})*iw)\\,0)':"
            f"h=2:color=0xc33731@0.95:t=fill"
        )

        vf = ','.join(filter_parts)

        # ── Build ffmpeg command ────────────────────────────────────
        cmd = [
            self.ffmpeg, '-y',
            '-f', 'lavfi',
            '-i', f'color=c=0x0c0c20:s={out_w}x{out_h}:d={duration_s}:r=25',
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
        """Minimal fallback: text on dark background."""
        try:
            font_size = min(52, out_h // 12)
            max_chars = self._max_chars(out_w, is_short)
            wrapped = self._wrap_text(text, max_chars=max_chars)
            wrapped = wrapped.replace("\\", "\\\\").replace("'", "'\\\\''").replace(":", "\\\\:").replace("%", "%%")

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
                          out_w=1280, out_h=720, is_short=False, voice_wps=None):
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

        paths = []
        elapsed = 0.0

        for i, chunk in enumerate(chunks):
            scene_speaking_time = chunk_words[i] / voice_wps
            scene_silence = (chunk_words[i] / total_words) * total_silence if total_words > 0 else 0
            scene_duration = scene_speaking_time + scene_silence

            out_path = os.path.join(output_dir, f"tw_scene_{i}.mp4")
            ok = self.render_scene(
                text=chunk, output_path=out_path, duration_s=scene_duration,
                out_w=out_w, out_h=out_h, is_short=is_short, global_cps=global_cps,
            )
            if ok:
                paths.append(out_path)
                print(f"    [Typewriter] Scene {i+1}/{num_scenes} OK "
                      f"({chunk_words[i]}w, {scene_duration:.1f}s)")
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
