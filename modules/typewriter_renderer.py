"""
Typewriter text renderer for VDNA 3.0.

Renders text with a per-character typewriter effect using ffmpeg drawtext.
No subtitles — text is burned directly onto the video frames.

For shorts (9:16 vertical): smaller font, narrower wrap, safe margins.
For main (16:9): standard font, wider wrap.
"""

import os
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
            # 1080x1920: 56px fits ~24 lines with 1.6x line height
            return max(44, min(64, out_h // 30))
        else:
            # 1280x720: 42px fits ~12 lines
            return max(36, min(52, out_h // 16))

    @staticmethod
    def _max_chars(out_w, is_short=False):
        if is_short:
            # 1080px wide, ~56px font, 120px side margins → ~22 chars
            return max(16, min(24, out_w // 48))
        else:
            return 38

    @staticmethod
    def _line_height(font_size):
        return int(font_size * 1.6)

    @staticmethod
    def _safe_zone(out_h, is_short=False):
        if is_short:
            # Keep text in middle 65% to avoid top/bottom UI overlays
            top = int(out_h * 0.175)
            bottom = int(out_h * 0.825)
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

    def _build_typewriter_filter(self, text, out_w, out_h, duration_s, is_short=False):
        """
        Build an ffmpeg drawtext filter with real per-character typewriter effect.

        Uses ffmpeg's eif expression to reveal characters one by one over time.
        Each line appears sequentially with its own typewriter animation.
        """
        font_size = self._font_size(out_h, is_short)
        max_chars = self._max_chars(out_w, is_short)
        lh = self._line_height(font_size)
        safe_top, safe_bottom = self._safe_zone(out_h, is_short)

        wrapped = self._wrap_text(text, max_chars=max_chars)
        lines = wrapped.split('\n')
        num_lines = len(lines)

        # Total text block height
        total_h = num_lines * lh
        safe_height = safe_bottom - safe_top
        start_y = safe_top + max(0, (safe_height - total_h) // 2)

        # Time allocation: each line gets equal time within duration
        time_per_line = duration_s / max(num_lines, 1)

        # Horizontal margin for shorts (keep text away from right-side UI)
        x_margin = int(out_w * 0.06) if is_short else 0  # ~64px on 1080

        filter_parts = []

        for i, line in enumerate(lines):
            if not line.strip():
                continue

            # Escape for ffmpeg drawtext
            escaped = line.replace("\\", "\\\\").replace("'", "\\\\'").replace(":", "\\\\:").replace("%", "%%")

            line_start = i * time_per_line
            line_end = line_start + time_per_line

            # Number of characters in this line
            n_chars = len(line)

            # Typewriter: reveal chars over the line's time slot
            # Use eif expression: show min(trunc((t - start) * cps), n_chars) characters
            # cps = chars per second for this line
            active_time = time_per_line * 0.85  # leave 15% pause at end
            cps = max(8, min(20, n_chars / max(active_time, 0.5)))

            # Build the typewriter text expression:
            # text='%{eif:min(trunc((t-T0)*cps),N):d}' shows N chars progressively
            # But drawtext doesn't support printf-style. Use textfile approach instead.

            # RELIABLE APPROACH: Use drawtext with text= and enable=
            # Split each line into N segments, each showing one more character
            # This gives a true typewriter effect without complex expressions.

            # Actually, the most reliable ffmpeg-native typewriter:
            # Use text='%{eif\:trunc((t-T0)*cps)\:d}' with text= prefix
            # But this only works for numbers. For text, we use a different trick.

            # PRACTICAL TYPEWRITER: Use the 'text' parameter with textfile
            # that we generate dynamically. But that's complex.

            # SIMPLEST RELIABLE TYPEWRITER:
            # Use drawtext with text=full_text and alpha that reveals per-character
            # using the 'enable' expression with text_w and x offset.
            # Actually, just use a clip/mask approach.

            # FINAL APPROACH: Use multiple drawtext layers, each showing one more
            # character, with enable expressions. For short text this is fine.

            # Even simpler: use the 'text' parameter with a fixed string and
            # animate a white rectangle mask that reveals characters left-to-right.
            # But that requires overlay filters.

            # MOST PRACTICAL: Use drawtext with text= and a fade-in per character
            # by splitting the line into individual character drawtext calls.
            # For a 20-char line, that's 20 drawtext calls — ffmpeg handles it.

            for ch_idx in range(1, n_chars + 1):
                partial = line[:ch_idx]
                ch_escaped = partial.replace("\\", "\\\\").replace("'", "\\\\'").replace(":", "\\\\:").replace("%", "%%")

                # This character appears at: line_start + (ch_idx-1)/cps
                ch_time = line_start + (ch_idx - 1) / cps
                ch_time_end = ch_time + 0.15  # brief fade for this char

                # Enable: show this partial text from ch_time until line_end
                enable_expr = f"between(t\\,{ch_time:.3f}\\,{line_end:.3f})"

                # Alpha: quick fade-in for each char
                alpha_expr = (
                    f"if(lte(t\\,{ch_time:.3f})\\,0\\,"
                    f"if(lte(t\\,{ch_time_end:.3f})\\,((t-{ch_time:.3f})/{ch_time_end-ch_time:.3f})\\,1))"
                )

                y_pos = start_y + i * lh
                x_pos = f"({out_w}-text_w)/2" if not is_short else f"{x_margin}+({out_w}-2*{x_margin}-text_w)/2"

                filter_parts.append(
                    f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
                    f"text='{ch_escaped}':"
                    f"fontsize={font_size}:"
                    f"fontcolor=white:"
                    f"x={x_pos}:"
                    f"y={y_pos}:"
                    f"shadowcolor=black@0.7:"
                    f"shadowx=2:"
                    f"shadowy=2:"
                    f"alpha='{alpha_expr}':"
                    f"enable='{enable_expr}'"
                )

        return ','.join(filter_parts) if filter_parts else "null"

    # ── scene render ────────────────────────────────────────────────

    def render_scene(self, text, output_path, duration_s, out_w=1280, out_h=720,
                     is_short=False, bg_color="0x1a1a2e"):
        """
        Render a single scene: dark background + typewriter text animation.
        Returns True on success.
        """
        if not text.strip():
            text = "..."

        dt_filter = self._build_typewriter_filter(text, out_w, out_h, duration_s, is_short)

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
        """Fallback: show full text with fade-in, no typewriter effect."""
        font_size = self._font_size(out_h, is_short)
        max_chars = self._max_chars(out_w, is_short)
        lh = self._line_height(font_size)
        safe_top, safe_bottom = self._safe_zone(out_h, is_short)

        wrapped = self._wrap_text(text, max_chars=max_chars)
        escaped = wrapped.replace("\\", "\\\\").replace("'", "\\\\'").replace(":", "\\\\:").replace("%", "%%")

        num_lines = wrapped.count('\n') + 1
        total_h = num_lines * lh
        safe_height = safe_bottom - safe_top
        start_y = safe_top + max(0, (safe_height - total_h) // 2)

        x_margin = int(out_w * 0.06) if is_short else 0
        x_pos = f"(w-text_w)/2" if not is_short else f"{x_margin}+(w-2*{x_margin}-text_w)/2"

        # Fade in over 0.4s
        alpha = "if(lte(t,0),0,if(lte(t,0.4),t/0.4,1))"

        dt = (
            f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
            f"text='{escaped}':"
            f"fontsize={font_size}:"
            f"fontcolor=white:"
            f"x={x_pos}:"
            f"y={start_y}:"
            f"shadowcolor=black@0.7:"
            f"shadowx=2:"
            f"shadowy=2:"
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
                          out_w=1280, out_h=720, is_short=False):
        """
        Render all scenes for a video. Returns list of scene clip paths.
        Each scene gets an equal slice of the total duration.
        """
        os.makedirs(output_dir, exist_ok=True)
        chunks = self._split_script(script_text, num_scenes)
        clip_duration = duration_s / max(num_scenes, 1)
        paths = []

        for i, chunk in enumerate(chunks):
            out_path = os.path.join(output_dir, f"tw_scene_{i}.mp4")
            ok = self.render_scene(
                text=chunk,
                output_path=out_path,
                duration_s=clip_duration,
                out_w=out_w,
                out_h=out_h,
                is_short=is_short,
            )
            if ok:
                paths.append(out_path)
                print(f"    [Typewriter] Scene {i+1}/{num_scenes} OK ({clip_duration:.1f}s)")
            else:
                print(f"    [Typewriter] Scene {i+1}/{num_scenes} FAILED — using blank")
                blank_path = os.path.join(output_dir, f"tw_scene_{i}_blank.mp4")
                self._render_blank(blank_path, clip_duration, out_w, out_h)
                paths.append(blank_path)

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
        import re
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

        # Pad if we got fewer chunks than requested
        while len(chunks) < num_scenes:
            chunks.append(chunks[-1] if chunks else "...")

        return chunks[:num_scenes]
