"""
Typewriter text renderer for VDNA 3.0.

Renders text with a per-character typewriter effect using ffmpeg drawtext.
No subtitles — text is burned directly onto the video frames.
Semi-transparent background box behind text for readability.

For shorts (9:16 vertical): larger font, narrower wrap, safe margins.
For main (16:9): standard font, wider wrap.
"""

import os
import re
import subprocess
import tempfile


class TypewriterRenderer:
    """Renders typewriter-style text animation over a dark background."""

    def __init__(self, ffmpeg_bin="ffmpeg"):
        self.ffmpeg = ffmpeg_bin

    # ── sizing helpers ──────────────────────────────────────────────

    @staticmethod
    def _font_size(out_h, is_short=False):
        if is_short:
            # 1080x1920: 80px for comfortable mobile reading
            return max(68, min(90, out_h // 24))
        else:
            # 1280x720: 48px
            return max(40, min(56, out_h // 14))

    @staticmethod
    def _max_chars(out_w, is_short=False):
        if is_short:
            # 1080px wide, ~80px font, ~120px side margins → ~13 chars
            return max(12, min(18, out_w // 64))
        else:
            return 38

    @staticmethod
    def _line_height(font_size):
        return int(font_size * 1.5)

    @staticmethod
    def _safe_zone(out_h, is_short=False):
        if is_short:
            # Keep text in middle 60% to avoid top/bottom UI overlays
            top = int(out_h * 0.20)
            bottom = int(out_h * 0.80)
        else:
            top = int(out_h * 0.12)
            bottom = int(out_h * 0.88)
        return top, bottom

    # ── word wrap ───────────────────────────────────────────────────

    @staticmethod
    def _wrap_text(text, max_chars=38):
        """Word-wrap at max_chars, breaking at spaces."""
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

    # ── drawtext filter builder ─────────────────────────────────────

    def _build_typewriter_filter(self, text, out_w, out_h, duration_s, is_short=False, global_cps=None):
        """
        Build an ffmpeg drawtext filter with real per-character typewriter effect.
        Uses a single drawtext per line with text expression that reveals characters.
        No overlapping — each line is one drawtext element.

        TIMING STRATEGY:
        - cps (chars/sec) = global_cps if provided, else calculated locally
        - Each line starts when its first character's time is reached:
          line_start = chars_before_this_line / cps
        - Each line's typewriter reveals chars at the same global cps.
        - This ensures text appears in sync with the voice.
        """
        font_size = self._font_size(out_h, is_short)
        max_chars = self._max_chars(out_w, is_short)
        lh = self._line_height(font_size)
        safe_top, safe_bottom = self._safe_zone(out_h, is_short)

        wrapped = self._wrap_text(text, max_chars=max_chars)
        lines = [l for l in wrapped.split('\n') if l.strip()]
        num_lines = len(lines)

        if num_lines == 0:
            return "null"

        # Total text block height
        total_h = num_lines * lh
        safe_height = safe_bottom - safe_top
        start_y = safe_top + max(0, (safe_height - total_h) // 2)

        # Horizontal margin for shorts
        x_margin = int(out_w * 0.08) if is_short else 0

        # ── Global typewriter rate ──────────────────────────────────
        # Use global_cps if provided (calculated from full video text + audio duration).
        # Otherwise, estimate from this scene's text and duration.
        total_chars = sum(len(l) for l in lines)
        if global_cps is not None:
            cps = global_cps
        else:
            # Fallback: estimate from scene duration, accounting for silence
            speaking_time = duration_s * 0.90
            cps = max(8, min(14, total_chars / max(speaking_time, 0.5)))

        # Per-line start times: proportional to cumulative char count
        # line N starts when char index = sum(len(lines[0..N-1])) / cps
        char_offsets = [0]
        for line in lines:
            char_offsets.append(char_offsets[-1] + len(line))
        # char_offsets[i] = total chars before line i

        # ── Background box ──────────────────────────────────────────
        box_pad_top = int(font_size * 0.5)
        box_pad_bot = int(font_size * 0.3)
        box_x = x_margin
        box_w = out_w - 2 * x_margin
        box_y = start_y - box_pad_top
        box_h = total_h + box_pad_top + box_pad_bot

        filter_parts = [
            f"drawbox=x={box_x}:y={box_y}:w={box_w}:h={box_h}:color=black@0.55:t=fill"
        ]

        # ── Typewriter text: one drawtext per line ──────────────────
        # Each line uses substr() to reveal characters at global cps.
        # Line N starts at char_offsets[N] / cps.
        for i, line in enumerate(lines):
            line_start = char_offsets[i] / cps
            n_chars = len(line)

            # Escape the line for ffmpeg
            escaped = (line
                       .replace("\\", "\\\\")
                       .replace("'", "'\\\\''")
                       .replace(":", "\\\\:")
                       .replace("%", "%%")
                       .replace("[", "\\\\[")
                       .replace("]", "\\\\]")
                       .replace(",", "\\\\,")
                       .replace(";", "\\\\;"))

            # Build text expression: reveal characters based on global time
            text_expr = (
                f"if(gt(t\\,{line_start:.3f})\\,"
                f"substr('{escaped}'\\,0\\,"
                f"min({n_chars}\\,floor((t-{line_start:.3f})*{cps:.1f})))\\,"
                f"'')"
            )

            # Alpha: fade in at line start, fade out at line end
            # Line ends when all its chars are revealed + a small hold
            line_type_dur = n_chars / cps
            line_end = line_start + line_type_dur + 0.3  # 300ms hold after last char
            fade_dur = min(0.2, line_type_dur * 0.3)  # quick fade
            fade_in_end = line_start + fade_dur
            fade_out_start = line_end - fade_dur
            alpha_expr = (
                f"if(lte(t\\,{line_start:.3f})\\,0\\,"
                f"if(lte(t\\,{fade_in_end:.3f})\\,((t-{line_start:.3f})/{max(fade_dur,0.01):.3f})\\,"
                f"if(gte(t\\,{fade_out_start:.3f})\\,(1-((t-{fade_out_start:.3f})/{max(fade_dur,0.01):.3f}))\\,"
                f"1))"
            )

            y_pos = start_y + i * lh
            x_pos = (f"({out_w}-text_w)/2" if not is_short
                     else f"{x_margin}+({out_w}-2*{x_margin}-text_w)/2")

            filter_parts.append(
                f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
                f"text='{text_expr}':"
                f"fontsize={font_size}:"
                f"fontcolor=white:"
                f"x={x_pos}:"
                f"y={y_pos}:"
                f"shadowcolor=black@0.8:"
                f"shadowx=3:"
                f"shadowy=3:"
                f"alpha='{alpha_expr}'"
            )

        return ','.join(filter_parts)

    # ── scene render ────────────────────────────────────────────────

    def render_scene(self, text, output_path, duration_s, out_w=1280, out_h=720,
                     is_short=False, bg_color="0x1a1a2e", global_cps=None):
        """
        Render a single scene: dark background + typewriter text + bg box.
        global_cps: if provided, use this global chars/sec rate instead of
                    calculating per-scene. This ensures all scenes type at the
                    same rate, matching the voice.
        Returns True on success.
        """
        if not text.strip():
            text = "..."

        dt_filter = self._build_typewriter_filter(text, out_w, out_h, duration_s, is_short, global_cps)

        cmd = [
            self.ffmpeg, "-y",
            "-f", "lavfi",
            "-i", f"color=c={bg_color}:s={out_w}x{out_h}:d={duration_s}:r=25",
            "-filter_complex", dt_filter,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-r", "25",
            "-t", f"{duration_s:.2f}",
            output_path
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                return self._render_simple(text, output_path, duration_s, out_w, out_h, is_short, bg_color)
            return os.path.exists(output_path) and os.path.getsize(output_path) > 1024
        except Exception as e:
            print(f"    [Typewriter] Render failed: {e}")
            return self._render_simple(text, output_path, duration_s, out_w, out_h, is_short, bg_color)

    def _render_simple(self, text, output_path, duration_s, out_w, out_h, is_short, bg_color):
        """Fallback: full text with background box + fade-in, no typewriter."""
        font_size = self._font_size(out_h, is_short)
        max_chars = self._max_chars(out_w, is_short)
        lh = self._line_height(font_size)
        safe_top, safe_bottom = self._safe_zone(out_h, is_short)

        wrapped = self._wrap_text(text, max_chars=max_chars)
        lines = [l for l in wrapped.split('\n') if l.strip()]
        num_lines = len(lines)
        if num_lines == 0:
            lines = ["..."]
            num_lines = 1

        escaped = wrapped.replace("\\", "\\\\").replace("'", "'\\\\''").replace(":", "\\\\:").replace("%", "%%")

        total_h = num_lines * lh
        safe_height = safe_bottom - safe_top
        start_y = safe_top + max(0, (safe_height - total_h) // 2)

        x_margin = int(out_w * 0.08) if is_short else 0
        x_pos = f"(w-text_w)/2" if not is_short else f"{x_margin}+(w-2*{x_margin}-text_w)/2"

        # Background box
        box_pad_x = int(font_size * 0.8)
        box_pad_top = int(font_size * 0.5)
        box_pad_bot = int(font_size * 0.3)
        box_x = x_margin
        box_w = out_w - 2 * x_margin
        box_y = start_y - box_pad_top
        box_h = total_h + box_pad_top + box_pad_bot

        # Fade in over 0.5s
        alpha = "if(lte(t,0),0,if(lte(t,0.5),t/0.5,1))"

        dt = (
            f"drawbox=x={box_x}:y={box_y}:w={box_w}:h={box_h}:color=black@0.55:t=fill,"
            f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
            f"text='{escaped}':"
            f"fontsize={font_size}:"
            f"fontcolor=white:"
            f"x={x_pos}:"
            f"y={start_y}:"
            f"shadowcolor=black@0.8:"
            f"shadowx=3:"
            f"shadowy=3:"
            f"alpha='{alpha}'"
        )

        cmd = [
            self.ffmpeg, "-y",
            "-f", "lavfi",
            "-i", f"color=c={bg_color}:s={out_w}x{out_h}:d={duration_s}:r=25",
            "-vf", dt,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-r", "25",
            "-t", f"{duration_s:.2f}",
            output_path
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            return os.path.exists(output_path) and os.path.getsize(output_path) > 1024
        except Exception as e:
            print(f"    [Typewriter] Simple render also failed: {e}")
            return False

    # ── multi-scene render ──────────────────────────────────────────

    def render_all_scenes(self, script_text, num_scenes, duration_s, output_dir,
                          out_w=1280, out_h=720, is_short=False, voice_wps=None):
        """
        Render all scenes for a video. Returns list of scene clip paths.
        All scenes share a global cps (chars/sec) matching the voice rate.
        """
        os.makedirs(output_dir, exist_ok=True)
        chunks = self._split_script(script_text, num_scenes)

        chunk_words = [max(1, len(chunk.split())) for chunk in chunks]
        total_words = sum(chunk_words)

        # Compute global voice rate from audio duration and word count
        if voice_wps is None:
            # Account for silence pauses (~5% of total duration)
            voice_wps = total_words / (duration_s * 0.95)

        # Global cps: chars per second the typewriter should reveal text
        # Total chars ≈ total_words * 5 (avg 4 chars/word + 1 space between words)
        # Speaking time = total_words / voice_wps
        # cps = total_chars / speaking_time
        total_chars_estimate = total_words * 5  # includes spaces between words
        speaking_time = total_words / voice_wps
        global_cps = total_chars_estimate / max(speaking_time, 0.5)
        global_cps = max(8, min(14, global_cps))  # clamp to reasonable range

        # Total silence time (distributed across scenes)
        total_silence = duration_s - speaking_time

        paths = []
        elapsed = 0.0

        for i, chunk in enumerate(chunks):
            # Active typing time for this scene (using global cps)
            scene_speaking_time = chunk_words[i] / voice_wps
            # Distribute silence proportionally by word count
            scene_silence = (chunk_words[i] / total_words) * total_silence if total_words > 0 else 0
            # Total scene duration = speaking time + silence share
            scene_duration = scene_speaking_time + scene_silence

            out_path = os.path.join(output_dir, f"tw_scene_{i}.mp4")
            ok = self.render_scene(
                text=chunk,
                output_path=out_path,
                duration_s=scene_duration,
                out_w=out_w,
                out_h=out_h,
                is_short=is_short,
                global_cps=global_cps,
            )
            if ok:
                paths.append(out_path)
                print(f"    [Typewriter] Scene {i+1}/{num_scenes} OK "
                      f"({chunk_words[i]}w, {scene_duration:.1f}s, "
                      f"t={elapsed:.1f}s-{elapsed+scene_duration:.1f}s)")
            else:
                print(f"    [Typewriter] Scene {i+1}/{num_scenes} FAILED — using blank")
                blank_path = os.path.join(output_dir, f"tw_scene_{i}_blank.mp4")
                self._render_blank(blank_path, scene_duration, out_w, out_h)
                paths.append(blank_path)

            elapsed += scene_duration

        return paths

    def _render_blank(self, output_path, duration_s, out_w, out_h):
        """Render a blank dark clip as ultimate fallback."""
        cmd = [
            self.ffmpeg, "-y",
            "-f", "lavfi",
            "-i", f"color=c=0x1a1a2e:s={out_w}x{out_h}:d={duration_s}:r=25",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-t", f"{duration_s:.2f}",
            output_path
        ]
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except Exception:
            pass

    # ── script splitting ────────────────────────────────────────────

    @staticmethod
    def _split_script(script_text, num_scenes):
        """Split script into num_scenes roughly equal chunks by sentences."""
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
