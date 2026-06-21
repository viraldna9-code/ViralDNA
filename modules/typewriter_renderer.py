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
        For shorts (9:16 vertical): smaller font, narrower wrap, safe margins.
        """
        # Font size: tuned per aspect ratio
        if is_short:
            # 1080x1920 vertical: ~72px gives ~20 lines with 1.5x line height
            # Safe for mobile viewing with UI overlay margins
            font_size = max(56, min(80, out_h // 24))
        else:
            font_size = max(36, out_h // 14)

        # Word-wrap: narrower for shorts (vertical = less horizontal space)
        if is_short:
            # ~24 chars at ~72px font fits within 1080px with 150px side margins
            max_chars = max(18, min(28, out_w // 40))
        else:
            max_chars = 38

        wrapped_text = self._wrap_text(text, max_chars=max_chars)
        escaped_wrapped = wrapped_text.replace("\\", "\\\\").replace("'", "\\\\'").replace(":", "\\\\:").replace("%", "%%")

        num_lines = wrapped_text.count('\n') + 1
        line_height = int(font_size * 1.55)  # slightly more breathing room
        total_text_height = num_lines * line_height

        # Safe vertical margin: keep text in middle 70% of screen
        safe_top = int(out_h * 0.15)
        safe_bottom = int(out_h * 0.85)
        safe_height = safe_bottom - safe_top
        start_y = safe_top + max(0, (safe_height - total_text_height) // 2)

        # Typewriter: reveal characters over time
        chars = len(escaped_wrapped)
        chars_per_sec = max(12, min(25, chars / max(duration_s * 0.7, 1.5)))
        reveal_duration = min(chars / chars_per_sec, duration_s * 0.85)

        # Horizontal safe margin for shorts (UI overlays on right side)
        margin_x = int(out_w * 0.08) if is_short else 0  # ~88px on 1080 width

        lines = wrapped_text.split('\n')
        filter_parts = []

        for line_idx, line in enumerate(lines):
            line_escaped = line.replace("\\", "\\\\").replace("'", "\\\\'").replace(":", "\\\\:").replace("%", "%%")
            line_start = line_idx * (duration_s / max(num_lines, 1))
            line_end = line_start + min(0.4, duration_s / max(num_lines, 1) * 0.5)

            enable_expr = f"between(t\\,{line_start:.2f}\\,{duration_s:.2f})"
            alpha_expr = (
                f"if(lte(t\\,{line_start:.2f})\\,0\\,"
                f"if(lte(t\\,{line_end:.2f})\\,((t-{line_start:.2f})/{line_end-line_start:.2f})\\,1))"
            )

            y_pos = start_y + line_idx * line_height

            # For shorts: add horizontal margin to keep text away from right-side UI
            if is_short and margin_x > 0:
                x_expr = f"(w-text_w)/2"
            else:
                x_expr = "(w-text_w)/2"

            filter_parts.append(
                f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
                f"text='{line_escaped}':"
                f"fontsize={font_size}:"
                f"fontcolor=white@1:"
                f"x={x_expr}:"
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
        # Match the main renderer's sizing for consistency
        if is_short:
            font_size = max(56, min(80, out_h // 24))
            max_chars = max(18, min(28, out_w // 40))
        else:
            font_size = max(36, out_h // 14)
            max_chars = 38

        wrapped = self._wrap_text(text, max_chars=max_chars)
        escaped = wrapped.replace("\\", "\\\\").replace("'", "\\\\'").replace(":", "\\\\:").replace("%", "%%")

        num_lines = wrapped.count('\n') + 1
        line_height = int(font_size * 1.55)
        total_h = num_lines * line_height

        # Safe vertical margin for shorts
        if is_short:
            safe_top = int(out_h * 0.15)
            safe_bottom = int(out_h * 0.85)
            safe_height = safe_bottom - safe_top
            start_y = safe_top + max(0, (safe_height - total_h) // 2)
        else:
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
