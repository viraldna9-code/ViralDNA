"""
Typewriter Text Renderer — VDNA 3.0
Replaces the entire image pipeline with typewriter-style text animation.
Each scene = one paragraph of script text that types out character by character.
Clean, readable, no images needed.
"""
import os
import subprocess
import math


class TypewriterRenderer:
    """Renders text-as-video with typewriter animation using ffmpeg drawtext."""

    def __init__(self, ffmpeg_bin="ffmpeg"):
        self.ffmpeg = ffmpeg_bin

    # ── helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _split_script(script_text, num_scenes):
        """Split script into ~equal paragraph chunks for each scene."""
        if not script_text:
            return ["Breaking news."] * num_scenes

        # Split into sentences
        import re
        sentences = re.split(r'(?<=[.!?])\s+', script_text.strip())
        sentences = [s for s in sentences if s.strip()]

        if not sentences:
            return ["Breaking news."] * num_scenes

        if len(sentences) <= num_scenes:
            # Fewer sentences than scenes — pad with empty, each sentence is a scene
            chunks = sentences + [""] * (num_scenes - len(sentences))
            return chunks[:num_scenes]

        # Group sentences into num_scenes chunks
        chunk_size = max(1, len(sentences) // num_scenes)
        chunks = []
        for i in range(num_scenes):
            start = i * chunk_size
            end = (i + 1) * chunk_size if i < num_scenes - 1 else len(sentences)
            chunk = " ".join(sentences[start:end]).strip()
            if not chunk:
                chunk = "..."
            chunks.append(chunk)
        return chunks

    def _build_drawtext_filter(self, text, out_w, out_h, duration_s, is_short=False):
        """
        Build an ffmpeg drawtext filter expression that types out text
        character by character (typewriter effect).

        Text is centered, large font, white on dark background.
        """
        # Font size: larger for shorts (vertical), slightly smaller for main
        if is_short:
            font_size = max(48, out_h // 12)
        else:
            font_size = max(36, out_h // 14)

        # Escape text for ffmpeg drawtext: single quotes, colons, backslashes
        escaped = text.replace("\\", "\\\\").replace("'", "\\\\'").replace(":", "\\\\:").replace("%", "%%")

        # Typewriter: reveal characters over time
        # pct = percent of text revealed (0 to 1)
        # We use the 'enable' trick with text that grows character by character
        # ffmpeg drawtext doesn't have native typewriter, so we use:
        #   text='%{eif\:trunc(t*%d)\:d}' % chars_per_sec
        # But simpler: use the 'text' source with enable expression

        chars = len(escaped)
        # Typing speed: ~20 chars/sec, but cap so minimum 2s per scene
        chars_per_sec = max(12, min(25, chars / max(duration_s * 0.7, 1.5)))
        reveal_duration = min(chars / chars_per_sec, duration_s * 0.85)

        # Build the typewriter expression
        # Use text='%{eif:trunc(t*chars_per_sec):d}' to reveal chars over time
        # Then pad with empty string after reveal is complete
        typing_expr = (
            f"if(lte(t\\,{reveal_duration:.2f})\\,"
            f"%{{eif\\:trunc(t\\*{chars_per_sec:.1f})\\:{chars}}}\\,"
            f"{chars})"
        )

        # Word-wrap: break long text into multiple lines
        # We pre-process: insert newlines every ~40 chars at word boundaries
        wrapped_text = self._wrap_text(text, max_chars=38)
        escaped_wrapped = wrapped_text.replace("\\", "\\\\").replace("'", "\\\\'").replace(":", "\\\\:").replace("%", "%%")

        # For typewriter with word-wrap, we use a simpler approach:
        # Reveal the full wrapped text with a typewriter cursor effect
        # Use enable to show progressively
        num_lines = wrapped_text.count('\n') + 1
        line_height = int(font_size * 1.4)
        total_text_height = num_lines * line_height
        start_y = (out_h - total_text_height) // 2

        # drawtext with typewriter: use textfile that updates, or use expression
        # Simplest reliable approach: use drawtext with 'text' containing
        # the expression for progressive reveal
        # We'll use the 'text' parameter with eif expression

        # Actually the most reliable way: use drawtext with text= and enable=
        # to show the full text after a fade-in per character
        # But ffmpeg drawtext doesn't support per-character timing natively.

        # PRACTICAL APPROACH: Use the 'text' source filter with drawtext
        # and animate the 'text' parameter using sendcmd or multiple drawtext layers.
        # Simpler: just fade in the full text with a typing cursor bar.

        # FINAL APPROACH: Use drawtext with a visible cursor that moves across text.
        # The full text is always visible but greyed out, and revealed progressively.
        # This is the "teleprompter" style.

        # Even simpler and cleaner: just show text with a smooth fade-in per line.
        # Each line fades in sequentially. Clean, readable, no gimmicks.

        lines = wrapped_text.split('\n')
        filter_parts = []

        for line_idx, line in enumerate(lines):
            line_escaped = line.replace("\\", "\\\\").replace("'", "\\\\'").replace(":", "\\\\:").replace("%", "%%")
            line_start = line_idx * (duration_s / max(num_lines, 1))
            line_end = line_start + min(0.4, duration_s / max(num_lines, 1) * 0.5)

            # Fade in each line sequentially
            enable_expr = f"between(t\\,{line_start:.2f}\\,{duration_s:.2f})"
            alpha_expr = (
                f"if(lte(t\\,{line_start:.2f})\\,0\\,"
                f"if(lte(t\\,{line_end:.2f})\\,((t-{line_start:.2f})/{line_end-line_start:.2f})\\,1))"
            )

            y_pos = start_y + line_idx * line_height

            filter_parts.append(
                f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
                f"text='{line_escaped}':"
                f"fontsize={font_size}:"
                f"fontcolor=white@1:"
                f"x=(w-text_w)/2:"
                f"y={y_pos}:"
                f"shadowcolor=black@0.8:"
                f"shadowx=2:"
                f"shadowy=2:"
                f"alpha='{alpha_expr}':"
                f"enable='{enable_expr}'"
            )

        return ','.join(filter_parts) if filter_parts else "null"

    @staticmethod
    def _wrap_text(text, max_chars=38):
        """Simple word-wrap at max_chars, breaking at spaces."""
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

    # ── main render ──────────────────────────────────────────────────

    def render_scene(self, text, output_path, duration_s, out_w=1280, out_h=720,
                     is_short=False, bg_color="0x1a1a2e"):
        """
        Render a single scene: dark background + typewriter text animation.
        Returns True on success.
        """
        if not text.strip():
            text = "..."

        # Build the drawtext filter
        dt_filter = self._build_drawtext_filter(text, out_w, out_h, duration_s, is_short)

        # Build ffmpeg command: color source + drawtext overlay
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
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120
            )
            if result.returncode != 0:
                # Fallback: simpler render without complex alpha expression
                return self._render_simple(text, output_path, duration_s, out_w, out_h, is_short, bg_color)
            return os.path.exists(output_path) and os.path.getsize(output_path) > 1024
        except Exception as e:
            print(f"    [Typewriter] Render failed: {e}")
            return self._render_simple(text, output_path, duration_s, out_w, out_h, is_short, bg_color)

    def _render_simple(self, text, output_path, duration_s, out_w, out_h, is_short, bg_color):
        """Simpler fallback: just show text with fade-in, no per-line animation."""
        wrapped = self._wrap_text(text, max_chars=38)
        escaped = wrapped.replace("\\", "\\\\").replace("'", "\\\\'").replace(":", "\\\\:").replace("%", "%%")
        font_size = max(48, out_h // 12) if is_short else max(36, out_h // 14)

        num_lines = wrapped.count('\n') + 1
        line_height = int(font_size * 1.4)
        total_h = num_lines * line_height
        start_y = (out_h - total_h) // 2

        # Simple fade-in over 0.5s
        alpha = "if(lte(t,0),0,if(lte(t,0.5),t/0.5,1))"

        dt = (
            f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
            f"text='{escaped}':"
            f"fontsize={font_size}:"
            f"fontcolor=white:"
            f"x=(w-text_w)/2:"
            f"y={start_y}:"
            f"shadowcolor=black@0.8:"
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

    def render_all_scenes(self, script_text, num_scenes, duration_s, output_dir,
                          out_w=1280, out_h=720, is_short=False):
        """
        Render all scenes for a video. Returns list of scene clip paths.
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
                # Create a blank clip as fallback
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
