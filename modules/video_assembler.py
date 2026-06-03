# VERSION: 70.0
# MODULE: video_assembler.py
# PURPOSE: Advanced Generative Slideshow + Kinetic Typography Captioning Engine.
#          v69.0: Image pipeline reworked for real news photos:
#                  - Source 1: Serper Image Search (try all 10 results)
#                  - Source 2: Wikimedia Commons API (real politician/event photos)
#                  - Source 3: Unsplash, Source 4: Pexels, Source 5: Pixabay
#                  - Source 6: ComfyUI (LAST RESORT — AI illustrations if all real sources fail)
#                  - Removed Serper-Web (too slow, news sites timeout at 3-5s)
#                  - ComfyUI: steps 20→30, CFG 7→8, added face-deformation negative prompts
#          v65.0: Fixed sync FFmpeg pipe deadlock (capture_output=True → log file)
#                  processing queue with progress tracking (K2.8), async upload prep.

import subprocess, os, re, urllib.parse, urllib.request, json, config, time, shutil

class VideoAssembler:
    def __init__(self, config_instance):
        self.config = config_instance
        self.ffmpeg = "ffmpeg"
        self.watermark = os.getenv(
            "VIRALDNA_WATERMARK",
            "/home/jay/ViralDNA/assets/watermark.png"
        )
        if not os.path.exists(self.watermark):
            print(f"  ⚠️ Watermark not found at {self.watermark}, creating 1x1 transparent placeholder")
            self.watermark = None
        # v64.0: detect available hardware acceleration at init
        self.hwaccel = self._detect_hwaccel()

    # ─── HARDWARE ACCELERATION DETECTION (K2.7 / v64.0) ──────────────

    HWACCEL_METHODS = [
        # (name, encoder, decoder_flag, test_filter)
        ("nvenc", "h264_nvenc", "-hwaccel cuda", null := None),
        ("vaapi", "h264_vaapi", "-hwaccal vaapi", None),
        ("qsv", "h264_qsv", "-hwaccel qsv", None),
        ("videotoolbox", "h264_videotoolbox", "-hwaccel videotoolbox", None),
    ]

    def _detect_hwaccel(self):
        """Detect available HW acceleration. Returns method name or None."""
        try:
            result = subprocess.run(
                ["ffmpeg", "-encoders"], capture_output=True, text=True, timeout=10
            )
            encoders_output = result.stdout

            # Check for GPU devices
            has_nvidia = os.path.exists("/dev/nvidia0") or os.path.exists("/proc/driver/nvidia")
            has_intel = os.path.exists("/dev/dri/renderD128")
            has_vaapi = os.path.exists("/dev/dri/card0")

            if has_nvidia and "h264_nvenc" in encoders_output:
                print("   🖥️  HW Acceleration: NVIDIA NVENC detected")
                return "nvenc"
            elif has_vaapi and "h264_vaapi" in encoders_output:
                print("   🖥️  HW Acceleration: VAAPI detected")
                return "vaapi"
            elif has_intel and "h264_qsv" in encoders_output:
                print("   🖥️  HW Acceleration: Intel QSV detected")
                return "qsv"
            else:
                print("   🖥️  HW Acceleration: None (using libx264 software encoding)")
                return None
        except Exception as e:
            print(f"   ⚠️ HW detection failed: {e}")
            return None

    def _get_video_encoder(self):
        """Return encoder string based on detected HW accel."""
        mapping = {
            "nvenc": "h264_nvenc",
            "vaapi": "h264_vaapi",
            "qsv": "h264_qsv",
        }
        return mapping.get(self.hwaccel, "libx264")

    # ─── OUTPUT QUALITY VALIDATION (K2.9 / v64.0) ─────────────────────

    def validate_output(self, output_path, expected_w=None, expected_h=None,
                         min_bitrate_kbps=2000, min_duration_s=1.0):
        """Post-assembly quality check. Returns (is_ok: bool, report: dict)."""
        report = {
            "file": output_path,
            "exists": False,
            "size_bytes": 0,
            "duration_s": 0,
            "width": 0,
            "height": 0,
            "bitrate_kbps": 0,
            "codec": "",
            "issues": [],
        }
        if not os.path.exists(output_path):
            report["issues"].append("FILE_NOT_FOUND")
            return False, report
        report["exists"] = True
        report["size_bytes"] = os.path.getsize(output_path)

        if report["size_bytes"] < 10240:
            report["issues"].append(f"TINY_FILE: {report['size_bytes']} bytes")
            return False, report

        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration,size,bit_rate:stream=width,height,codec_name,bit_rate",
                "-of", "json",
                output_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            probe = json.loads(result.stdout)

            fmt = probe.get("format", {})
            streams = probe.get("streams", [{}])
            video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})

            report["duration_s"] = float(fmt.get("duration", 0))
            report["bitrate_kbps"] = int(fmt.get("bit_rate", 0)) // 1000
            report["width"] = int(video_stream.get("width", 0))
            report["height"] = int(video_stream.get("height", 0))
            report["codec"] = video_stream.get("codec_name", "unknown")

            # Validate
            if report["duration_s"] < min_duration_s:
                report["issues"].append(f"SHORT_DURATION: {report['duration_s']:.1f}s < {min_duration_s}s")
            if report["bitrate_kbps"] < min_bitrate_kbps:
                report["issues"].append(f"LOW_BITRATE: {report['bitrate_kbps']}kbps < {min_bitrate_kbps}kbps")
            if expected_w and report["width"] != expected_w:
                report["issues"].append(f"WIDTH_MISMATCH: got {report['width']} expected {expected_w}")
            if expected_h and report["height"] != expected_h:
                report["issues"].append(f"HEIGHT_MISMATCH: got {report['height']} expected {expected_h}")
        except Exception as e:
            report["issues"].append(f"PROBE_ERROR: {e}")

        is_ok = len(report["issues"]) == 0
        return is_ok, report

    # ─── PROCESSING QUEUE (K2.8 / v64.0) ─────────────────────────────

    def __init_processing_queue(self):
        self._queue = []
        self._completed = []
        self._failed = []

    def queue_assembly(self, assembly_params):
        """Add an assembly job to the processing queue."""
        if not hasattr(self, '_queue'):
            self.__init_processing_queue()
        job = {
            "id": len(self._queue) + 1,
            "params": assembly_params,
            "status": "queued",
            "started_at": None,
            "completed_at": None,
            "output_report": None,
        }
        self._queue.append(job)
        return job["id"]

    def get_queue_progress(self):
        """Return summary of processing queue state."""
        if not hasattr(self, '_queue'):
            return {"queued": 0, "completed": 0, "failed": 0, "total": 0}
        return {
            "queued": sum(1 for j in self._queue if j["status"] == "queued"),
            "completed": sum(1 for j in self._queue if j["status"] == "completed"),
            "failed": sum(1 for j in self._queue if j["status"] == "failed"),
            "total": len(self._queue),
        }

    # ─── EXISTING METHODS (carried forward) ───────────────────────────

    def get_audio_duration(self, audio_path: str) -> float:
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                audio_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(result.stdout.strip())
        except Exception as e:
            print(f"  ⚠️ Warning: Could not extract physical audio duration via ffprobe: {e}")
            return None

    def _check_relevance(self, img_info: dict, prompt: str, topic_title: str) -> dict:
        """
        v70.0: Semantic relevance gate — relaxed for real news photos.
        Uses Serper image metadata (title, source domain) to reject off-topic images.
        Key changes v70.0:
          - Lowered threshold from 10% to 5% (real photos have generic titles)
          - Added stock photo domain whitelist (istock, shutterstock, getty, etc.)
          - Added YouTube thumbnail domain whitelist (ytimg.com)
          - Single keyword match is enough for trusted domains
          - Broader domain matching (handles timesofindia.indiatimes.com, etc.)
        Returns: {"relevant": bool, "reason": str}
        """
        # Extract keywords from prompt and topic (words > 4 chars, lowercase)
        topic_words = set(w.lower() for w in re.findall(r'\b[a-zA-Z]{5,}\b', topic_title))
        prompt_words = set(w.lower() for w in re.findall(r'\b[a-zA-Z]{5,}\b', prompt))
        # Weight topic words higher — they're the core subject
        key_terms = topic_words | prompt_words
        # Remove generic filler words that match everything
        filler = {"professional", "photorealistic", "cinematic", "report", "visualization",
                  "showing", "background", "lighting", "studio", "dramatic", "broadcast",
                  "quality", "image", "photo", "picture", "scene", "close", "detail",
                  "related", "search", "query", "just", "high", "resolution"}
        key_terms -= filler
        if not key_terms:
            return {"relevant": True, "reason": "no key terms to check"}

        # Build text to check: image title + source domain + alt text
        title = (img_info.get("title", "") or "").lower()
        domain = urllib.parse.urlparse(img_info.get("imageUrl", "")).netloc.lower()
        alt = (img_info.get("imageAltText", "") or img_info.get("alt", "") or "").lower()
        check_text = f"{title} {domain} {alt}"

        # Count how many key terms appear in the image metadata
        matches = sum(1 for term in key_terms if term in check_text)
        match_ratio = matches / len(key_terms) if key_terms else 0

        # Trusted news/image domains — accept even with very low keyword match
        # These domains have real photos even when the title doesn't contain our exact keywords
        trusted_domains = {
            # Indian news
            'thewire.in', 'thehindu.com', 'hindustantimes.com', 'ndtv.com',
            'indianexpress.com', 'scroll.in', 'news18.com', 'reuters.com',
            'apnews.com', 'bbc.com', 'cnn.com', 'aljazeera.com',
            'deccanherald.com', 'deccanchronicle.com', 'newindianexpress.com',
            'timesofindia.indiatimes.com', 'indiatimes.com', 'livemint.com',
            'economictimes.com', 'firstpost.com', 'thequint.com',
            'siasat.com', 'deshabhimani.com', 'telanganatoday.com',
            'thenewsminute.com', 'newslaundry.com', 'thewire.in',
            # YouTube thumbnails (ytimg.com)
            'ytimg.com', 'youtube.com',
            # Twitter/social
            'pbs.twimg.com', 'x.com', 'twitter.com',
            # Stock photo sites (real photos, generic titles)
            'istockphoto.com', 'shutterstock.com', 'gettyimages.com',
            'gettyimages.in', 'dreamstime.com', 'alamy.com',
            'stock.adobe.com', 'pexels.com', 'unsplash.com',
            'pixabay.com', 'freepik.com', 'pngtree.com',
            # Wikipedia / Wikimedia
            'wikimedia.org', 'wikipedia.org', 'upload.wikimedia.org',
            # Telugu news sites
            'eenadu.net', 'sakshi.com', 'andhrabhoomi.com',
            'andhrajyothy.com', 'vaartha.com', 'namasthetelangana.com',
            'telugu360.com', 'greatandhra.com', 'mirchilife.com',
            'apnews.gov.in', 'pib.gov.in',
        }
        domain_is_trusted = any(td in domain for td in trusted_domains)

        # For trusted domains: accept if ANY single keyword matches
        if domain_is_trusted and matches >= 1:
            return {"relevant": True, "reason": f"Trusted domain + match ({domain})"}
        # For trusted domains with zero keyword match: still accept (stock photos have generic titles)
        if domain_is_trusted and match_ratio < 0.05:
            return {"relevant": True, "reason": f"Trusted image domain ({domain})"}
        # For untrusted domains: require 5% match (relaxed from 10%)
        if match_ratio < 0.05:
            return {
                "relevant": False,
                "reason": f"Off-topic (title: '{title[:60]}', match: {match_ratio:.0%})"
            }
        return {"relevant": True, "reason": f"Relevant ({match_ratio:.0%} match)"}

    def generate_image_prompts(self, script_text, num_scenes):
        prompts = []
        try:
            from gemini_engine import GeminiEngine
            engine = GeminiEngine()
            prompt_text = f"""
Analyze this news script and divide it into exactly {num_scenes} sequential visual scenes.
For each scene, write a specific, detailed image search query showing the ACTUAL SUBJECT MATTER.
BAD: 'professional news report visualization showing visa policy'
GOOD: 'Indian wedding couple at airport with suitcases, dramatic lighting, documentary photo'
Use real-world concrete imagery: people, places, events related to the script.
NO text overlays, logos, or screenshot-style images.
Output ONLY a JSON array of {num_scenes} search query strings.
Script:
\\\"\\\"\\\"{script_text}\\\"\\\"\\\"
"""
            response_text = engine.ask(prompt_text)
            text = response_text.strip() if response_text else ""
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            prompts = json.loads(text)
            print(f"    Assembler: Successfully generated {len(prompts)} custom prompts via GeminiEngine.")
        except Exception as e:
            print(f"    ⚠️ Warning: Gemini prompt generation failed: {e}. Using keyword extraction fallback.")
            prompts = []

        if not prompts or len(prompts) != num_scenes:
            prompts = []
            # Fallback: extract NAMED ENTITIES and key noun phrases, not generic keywords
            sentences = [s.strip() for s in re.split(r'[.!?]+', script_text) if len(s.strip()) > 5]
            if len(sentences) == 0:
                sentences = [script_text]
            chunk_size = max(1, len(sentences) // num_scenes)
            for i in range(num_scenes):
                idx_start = i * chunk_size
                idx_end = (i + 1) * chunk_size if i < num_scenes - 1 else len(sentences)
                scene_sentences = sentences[idx_start:idx_end]
                scene_text = " ".join(scene_sentences)
                # Extract proper nouns and capitalized phrases (named entities likely)
                cap_phrases = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', scene_text)
                # Extract ALL-CAPS acronyms
                acronyms = re.findall(r'\b[A-Z]{2,5}\b', scene_text)
                # Extract important nouns (6+ chars)
                nouns = [w for w in re.sub(r'[^\w\s]', '', scene_text).split()
                         if len(w) >= 6 and w[0].islower()]
                # Build specific search query
                parts = list(dict.fromkeys(cap_phrases[:3] + acronyms[:2] + nouns[:3]))
                if parts:
                    query = " ".join(parts) + ", documentary photography, news"
                else:
                    query = " ".join(scene_text.split()[:8]) + ", documentary photography"
                prompts.append(query)

        return prompts[:num_scenes]

    def _validate_image_quality(self, img_path: str, topic_title: str = "") -> dict:
        """
        Comprehensive image quality gate using OpenCV.
        Rejects blurry images, news screenshots (text/logos/faces),
        low-detail images, and off-topic images.
        Returns: {"passed": bool, "reason": str, "score": float}
        """
        try:
            import cv2
            import numpy as np

            img = cv2.imread(img_path)
            if img is None:
                return {"passed": False, "reason": "OpenCV cannot read file", "score": 0}

            h, w = img.shape[:2]
            score = 100.0
            reasons = []

            # 1. Resolution check — minimum total pixels (accepts both landscape and portrait)
            # YouTube/news thumbnails come in various orientations
            total_pixels = w * h
            if total_pixels < 300000:  # ~640x480 or equivalent
                return {"passed": False, "reason": f"Too small: {w}x{h} ({total_pixels:,} px, min 300k)", "score": 0}

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            # 2. Blur detection — Laplacian variance
            # Sharp image: >100, blurry: <50
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            if laplacian_var < 30:
                return {"passed": False, "reason": f"Too blurry (Laplacian: {laplacian_var:.1f} < 30)", "score": 0}
            elif laplacian_var < 80:
                score -= (80 - laplacian_var) * 0.5
                reasons.append(f"moderate_blur({laplacian_var:.0f})")

            # 3. Text / overlay detection — multi-method
            # Method A: Canny edge density (news screenshots have dense text edges)
            # Threshold relaxed: 0.35 catches real screenshots, allows news photos with light text
            edges = cv2.Canny(gray, 50, 150)
            edge_density = np.count_nonzero(edges) / (w * h)
            if edge_density > 0.35:
                return {"passed": False, "reason": f"Too many edges/text overlay (density: {edge_density:.2f})", "score": 0}
            elif edge_density > 0.20:
                score -= (edge_density - 0.20) * 150
                reasons.append(f"high_edges({edge_density:.2f})")

            # Method C: Quadrant edge analysis — detect broadcast screenshot pattern
            # News broadcast screenshots have: (a) high edge density in one corner (channel logo),
            # (b) a horizontal band at the bottom (news ticker text)
            # Real photos have relatively even edge distribution across the image
            try:
                qh, qw = h // 2, w // 2
                quadrants = [
                    edges[0:qh, 0:qw],         # top-left
                    edges[0:qh, qw:w],         # top-right
                    edges[qh:h, 0:qw],         # bottom-left
                    edges[qh:h, qw:w],         # bottom-right
                ]
                q_densities = [np.count_nonzero(q) / (qh * qw) for q in quadrants]
                max_q = max(q_densities)
                min_q = min(q_densities)
                # If one quadrant has 3x+ the edge density of the least-dense quadrant,
                # that's likely a channel logo in a corner
                if min_q > 0.01 and max_q / min_q > 3.0 and max_q > 0.25:
                    # Check bottom half has high edges (ticker bar)
                    bottom_half = edges[qh:h, :]
                    bottom_density = np.count_nonzero(bottom_half) / (qh * w)
                    top_half = edges[0:qh, :]
                    top_density = np.count_nonzero(top_half) / (qh * w)
                    if bottom_density > top_density * 1.5 and bottom_density > 0.15:
                        return {"passed": False,
                                "reason": f"Broadcast screenshot (corner logo q_ratio={max_q/min_q:.1f}, "
                                           f"bottom_ticker={bottom_density:.2f})", "score": 0}
            except Exception:
                pass

            # Method B: MSER text region detection
            # DISABLED for news content — real news photos frequently have watermarks,
            # captions, and channel logos that trigger false positives.
            # The edge density check (Method A) + quadrant check (Method C) catch screenshots.
            # try:
            #     mser = cv2.MSER_create()
            #     regions, _ = mser.detectRegions(gray)
            #     text_like = [r for r in regions if 20 < len(r) < 500]
            #     if len(text_like) > 200:
            #         return {"passed": False, "reason": f"MSER text regions: {len(text_like)} (news screenshot?)", "score": 0}
            #     elif len(text_like) > 100:
            #         score -= (len(text_like) - 100) * 0.1
            #         reasons.append(f"mser_text({len(text_like)})")
            # except Exception:
            #     pass
            # Face detection — reject close-up face shots (often press photos, not scene images)
            # DISABLED — news photos of politicians are legitimate scene images

            # 4. Color variance check — reject flat/gradient-only images
            color_std = np.std(img, axis=(0, 1)).mean()
            if color_std < 15:
                return {"passed": False, "reason": f"Flat image, no detail (color std: {color_std:.1f})", "score": 0}

            # 5. Border/frame detection — news screenshots often have white/black borders
            border_size = 10
            top_border = img[:border_size, :, :].mean()
            bottom_border = img[-border_size:, :, :].mean()
            left_border = img[:, :border_size, :].mean()
            right_border = img[:, -border_size:, :].mean()
            border_avg = (top_border + bottom_border + left_border + right_border) / 4
            center_avg = img[h//4:3*h//4, w//4:3*w//4, :].mean()
            if abs(border_avg - center_avg) > 80:
                score -= 20
                reasons.append("border_mismatch")

            # 6. TV logo / channel watermark detection
            # DISABLED for news content — real news photos ALWAYS have channel watermarks
            # (TV9, ETV, NTV, etc. in corners). This is normal and expected for news.
            # A watermark doesn't make an image invalid — it proves it's a real news photo.

            # 6b. Meme / graphic / AI-generated detection via edge pattern analysis
            # News photos have natural edge distributions; memes/graphics have sharp
            # geometric edges and flat color regions that create a distinct signature.
            # Check: ratio of strong edges (high gradient) to total edges
            if edge_density > 0.05:
                sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
                sobely = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
                sobel_mag = np.sqrt(sobelx**2 + sobely**2)
                strong_edge_ratio = np.count_nonzero(sobel_mag > 100) / (w * h)
                # Graphics/memes: high strong-edge ratio relative to total edges
                # Natural photos: strong edges are a small fraction of total edges
                if edge_density > 0.15 and strong_edge_ratio / edge_density > 0.6:
                    score -= 25
                    reasons.append("graphic_like_edges")

            # 7. Face detection — DISABLED for news content
            # News photos of politicians, rallies, events WITH faces are legitimate.
            # We WANT to see Nara Lokesh's face in a TDP rally photo.
            # Face detection was rejecting real news photos with people in them.
            # try:
            #     face_cascade = cv2.CascadeClassifier(
            #         cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            #     )
            #     if not face_cascade.empty():
            #         faces = face_cascade.detectMultiScale(
            #             gray, scaleFactor=1.1, minNeighbors=4, minSize=(30, 30)
            #         )
            #         if len(faces) > 0:
            #             max_face_area = max(fw * fh for (_, _, fw, fh) in faces)
            #             face_ratio = max_face_area / (w * h)
            #             if face_ratio > 0.05:
            #                 return {"passed": False, "reason": f"Large face detected", "score": 0}
            #             else:
            #                 score -= len(faces) * 3
            #                 reasons.append(f"small_faces({len(faces)})")
            # except Exception:
            #     pass

            # 8. Near-white / near-black ratio — catches blank/webpage screenshots only
            # mostly white (web page) or have large text blocks
            white_ratio = np.count_nonzero(gray > 240) / (w * h)
            black_ratio = np.count_nonzero(gray < 15) / (w * h)
            if white_ratio > 0.6:
                return {"passed": False, "reason": f"Mostly white ({white_ratio:.0%}) — likely web page screenshot", "score": 0}
            if black_ratio > 0.5:
                return {"passed": False, "reason": f"Mostly black ({black_ratio:.0%}) — likely dark overlay", "score": 0}

            score = max(0, min(100, score))
            return {
                "passed": True,
                "reason": "OK" + (f" ({', '.join(reasons)})" if reasons else ""),
                "score": round(score, 1)
            }

        except ImportError:
            return {"passed": True, "reason": "OpenCV unavailable, skipped", "score": 50}
        except Exception as e:
            return {"passed": False, "reason": f"Quality check error: {e}", "score": 0}

    def download_scene_images(self, prompts, output_dir, topic_title=""):
        image_paths = []
        os.makedirs(output_dir, exist_ok=True)
        used_image_hashes = set()  # prevent duplicate images across scenes

        # Known stock photo / watermark domains and copyright strings to reject
        REJECT_DOMAINS = {
            "gettyimages", "shutterstock", "dreamstime", "alamy", "istockphoto",
            "stock.adobe", "bigstock", "depositphotos", "123rf", "pond5",
            "canstockphoto", "fotolia", "featurepics", "photodune",
        }
        REJECT_COPYRIGHT = {
            "hindustan times", "getty images", "shutterstock", "dreamstime",
            "alamy", "istock", "adobe stock", "bigstock", "depositphotos",
            "reuters", "afp", "ani",  # news agency watermarks cause strikes
        }

        def _is_watermarked_stock(img_path, img_url="", img_title="", img_source=""):
            """Reject stock photos with watermarks/copyright that cause channel strikes."""
            # Check URL domain
            from urllib.parse import urlparse
            domain = urlparse(img_url).netloc.lower()
            for rd in REJECT_DOMAINS:
                if rd in domain:
                    return True, f"stock domain: {rd}"
            # Check EXIF copyright
            try:
                from PIL import Image as PILImage
                from PIL.ExifTags import TAGS as EXIF_TAGS
                im = PILImage.open(img_path)
                exif = im.getexif()
                if exif:
                    for tid, val in exif.items():
                        tag = EXIF_TAGS.get(tid, tid)
                        if tag in ("Copyright", "Artist", "ImageDescription"):
                            val_lower = str(val).lower()
                            for rc in REJECT_COPYRIGHT:
                                if rc in val_lower:
                                    return True, f"copyright: {rc}"
            except Exception:
                pass
            # Check title/source text
            meta_text = (img_title + " " + img_source).lower()
            for rc in REJECT_COPYRIGHT:
                if rc in meta_text:
                    return True, f"meta: {rc}"
            return False, ""

        def _is_valid_image(path):
            try:
                with open(path, 'rb') as f:
                    header = f.read(12)
                if header[:3] == b'\xff\xd8\xff':
                    return True
                if header[:4] == b'\x89PNG':
                    return True
                if header[:4] == b'RIFF' and header[8:12] == b'WEBP':
                    return True
                return False
            except:
                return False

        for i, prompt in enumerate(prompts):
            img_path = os.path.join(output_dir, f"scene_img_{i}.jpg")
            if os.path.exists(img_path):
                try:
                    os.remove(img_path)
                except:
                    pass
            downloaded = False

            # Source 1: Serper Image Search (real news photos — PRIMARY)
            # Try up to 10 results before giving up
            if not downloaded:
                try:
                    print(f"    Assembler: [Serper-Img] Fetching scene {i}...")
                    serper_key = config.API_KEYS.get("SERPER_API_KEY", "")
                    if serper_key:
                        headers = {'X-API-KEY': serper_key, 'Content-Type': 'application/json'}

                        # Build state-specific Serper query to avoid wrong-state images
                        _serper_state = ""
                        _serper_ctx = (topic_title + " " + prompt).lower()
                        if "telangana" in _serper_ctx or "hyderabad" in _serper_ctx or "revanth" in _serper_ctx:
                            _serper_state = "Telangana"
                        elif "andhra pradesh" in _serper_ctx or "andhra" in _serper_ctx or "amaravati" in _serper_ctx or "vijayawada" in _serper_ctx or "visakhapatnam" in _serper_ctx or "vizag" in _serper_ctx:
                            _serper_state = "Andhra Pradesh"
                        elif "tamil nadu" in _serper_ctx or "chennai" in _serper_ctx:
                            _serper_state = "Tamil Nadu"
                        elif "karnataka" in _serper_ctx or "bengaluru" in _serper_ctx or "bangalore" in _serper_ctx:
                            _serper_state = "Karnataka"
                        elif "kerala" in _serper_ctx or "kochi" in _serper_ctx or "thiruvananthapuram" in _serper_ctx:
                            _serper_state = "Kerala"

                        # Use scene-specific prompt (from Gemini) as primary query, but
                        # replace generic "Andhra farmers" with state-correct term
                        _serper_query = prompt if prompt else topic_title
                        if _serper_state:
                            # Remove wrong-state terms that Gemini may have injected
                            _swap = [("Andhra Pradesh farmers", "Telangana farmers"),
                                     ("Andhra farmers", "Telangana farmers"),
                                     ("Andhra Pradesh agriculture", "Telangana agriculture")]
                            for _wrong, _right in _swap:
                                if _serper_state == "Telangana" and _wrong.lower() in _serper_query.lower():
                                    _serper_query = _serper_query.replace(_wrong, _right)
                                    _serper_query = _serper_query.replace(_wrong.lower(), _right)
                            # Prepend state only if not already present in query
                            if _serper_state.lower() not in _serper_query.lower():
                                _serper_query = f"{_serper_state} {_serper_query}"
                            # Dedup: remove redundant state mentions (e.g. "Andhra Pradesh Andhra")
                            _dedup_pairs = [("Andhra Pradesh Andhra ", "Andhra Pradesh "),
                                           ("Telangana Telangana ", "Telangana ")]
                            for _dup, _single in _dedup_pairs:
                                _serper_query = _serper_query.replace(_dup, _single)

                        payload = {"q": _serper_query, "num": 10}
                        req_data = json.dumps(payload).encode('utf-8')
                        req = urllib.request.Request("https://google.serper.dev/images", data=req_data, headers=headers)
                        with urllib.request.urlopen(req, timeout=10) as resp:
                            data = json.loads(resp.read().decode())
                            images = data.get("images", [])
                            for attempt_idx, img_info in enumerate(images[:10]):
                                try:
                                    url = img_info.get("imageUrl", "")
                                    if not url: continue

                                    # Fix #3: Image relevance check using Serper metadata
                                    # Check if the image title/source is actually about the topic
                                    img_title = (img_info.get("title", "") or "").lower()
                                    img_source = (img_info.get("source", "") or "").lower()
                                    img_domain = ""
                                    try:
                                        from urllib.parse import urlparse
                                        img_domain = urlparse(url).netloc.lower()
                                    except:
                                        pass

                                    # Build topic keyword set from prompt + topic_title
                                    _topic_words = set()
                                    for _src in [prompt, topic_title]:
                                        if _src:
                                            _topic_words.update(w.lower() for w in _src.split() if len(w) >= 4)
                                    # Add state name as a required keyword if detected
                                    if _serper_state:
                                        _topic_words.add(_serper_state.lower())
                                        # Also add related terms
                                        if _serper_state == "Telangana":
                                            _topic_words.update(["telangana", "hyderabad", "farmers", "procurement", "paddy", "ration", "cm", "revanth", "congress", "bjp", "tdp"])
                                        elif _serper_state == "Andhra Pradesh":
                                            _topic_words.update(["andhra", "amaravati", "vijayawada", "farmers", "procurement", "paddy", "cm", "jagan", "ysrcp", "tdp"])

                                    # Check relevance: image title or source should share keywords with topic
                                    _img_text = img_title + " " + img_source + " " + img_domain
                                    _img_words = set(w.strip(".,;:!?()[]'\"") for w in _img_text.split() if len(w) >= 4)
                                    if _topic_words and _img_words:
                                        _overlap = _topic_words & _img_words
                                        # Require at least 1 keyword overlap for relevance
                                        if len(_overlap) == 0:
                                            # Exception: if image is from a known news domain, be more lenient
                                            _news_domains = ["thehindu", "deccanherald", "deccanchronicle", "newindianexpress",
                                                           "timesofindia", "hindustantimes", "indianexpress", "ndtv",
                                                           "news18", "reuters", "apnews", "bbc", "aljazeera",
                                                           "wikimedia", "commons.wikimedia"]
                                            _is_news_domain = any(nd in img_domain for nd in _news_domains)
                                            if not _is_news_domain:
                                                print(f"      [Serper-Img] Scene {i} attempt {attempt_idx}: REJECTED off-topic (title: {img_title[:60]}...)")
                                                continue
                                            # For news domains, still check state match
                                            if _serper_state:
                                                _state_in_img = _serper_state.lower() in _img_text
                                                _wrong_state = False
                                                if _serper_state == "Telangana" and ("andhra pradesh" in _img_text or ("andhra" in _img_text and "pradesh" in _img_text)):
                                                    _wrong_state = True
                                                elif _serper_state == "Andhra Pradesh" and "telangana" in _img_text:
                                                    _wrong_state = True
                                                if _wrong_state:
                                                    print(f"      [Serper-Img] Scene {i} attempt {attempt_idx}: REJECTED wrong state (title: {img_title[:60]}...)")
                                                    continue

                                    # v80.0: Person-name verification (shared validator)
                                    from modules.image_validator import check_person_name_in_title
                                    _person_ok, _expected = check_person_name_in_title(topic_title or "", img_title)
                                    if not _person_ok:
                                        print(f"      [Serper-Img] Scene {i} attempt {attempt_idx}: REJECTED person missing (expected: {_expected}, title: {img_title[:60]}...)")
                                        continue

                                    req2 = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                                    with urllib.request.urlopen(req2, timeout=10) as dl:
                                        raw = dl.read()
                                    if len(raw) < 10000: continue
                                    with open(img_path, 'wb') as f:
                                        f.write(raw)
                                    from PIL import Image
                                    import numpy as np
                                    import cv2
                                    import tempfile
                                    im = Image.open(img_path).convert("RGB")
                                    arr = np.array(im)
                                    h_img, w_img = im.size[1], im.size[0]
                                    sz = os.path.getsize(img_path)
                                    color_std = arr.std()
                                    if sz < 10000: os.remove(img_path); continue
                                    if color_std < 15: os.remove(img_path); continue
                                    if w_img < 400 or h_img < 300: os.remove(img_path); continue
                                    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
                                    edges = cv2.Canny(gray, 50, 150)
                                    edge_density = np.count_nonzero(edges) / (w_img * h_img)
                                    if edge_density > 0.50: os.remove(img_path); continue

                                    # v75.3: Reject watermarked stock photos (channel strike risk)
                                    is_stock, stock_reason = _is_watermarked_stock(
                                        img_path, img_url=url,
                                        img_title=img_info.get("title", ""),
                                        img_source=img_info.get("source", "")
                                    )
                                    if is_stock:
                                        print(f"      [Serper-Img] Scene {i} REJECTED stock/watermark: {stock_reason}")
                                        try: os.remove(img_path)
                                        except: pass
                                        continue

                                    # v75.3: Reject duplicate images within same run
                                    import hashlib
                                    with open(img_path, 'rb') as _hf:
                                        _h = hashlib.md5(_hf.read()).hexdigest()
                                    if _h in used_image_hashes:
                                        print(f"      [Serper-Img] Scene {i} REJECTED duplicate (hash {_h[:12]})")
                                        try: os.remove(img_path)
                                        except: pass
                                        continue
                                    used_image_hashes.add(_h)

                                    print(f"      [Serper-Img] Scene {i} saved ({sz//1024}KB, {w_img}x{h_img}, std={color_std:.1f}, edges={edge_density:.2f})")
                                    image_paths.append(img_path)
                                    downloaded = True
                                    break
                                except Exception as e:
                                    if os.path.exists(img_path): 
                                        try: os.remove(img_path)
                                        except: pass
                except Exception as e:
                    print(f"      [Serper-Img] Scene {i} failed: {e}")

            # Source 2: Wikimedia Commons (real politician/event photos — fast & reliable)
            if not downloaded:
                try:
                    print(f"    Assembler: [WikiCommons] Fetching scene {i}...")
                    import tempfile
                    from PIL import Image
                    import numpy as np
                    search_q = topic_title if topic_title else prompt[:100]
                    # Search Wikimedia Commons API directly (fast, no HTML parsing)
                    wiki_url = f"https://commons.wikimedia.org/w/api.php?action=query&generator=search&gsrsearch={urllib.parse.quote(search_q + ' filetype:bitmap')}&gsrnamespace=6&gsrlimit=5&prop=imageinfo&iiprop=url|size&iiurlwidth=1280&format=json"
                    req = urllib.request.Request(wiki_url, headers={'User-Agent': 'ViralDNA/69.0'})
                    with urllib.request.urlopen(req, timeout=8) as resp:
                        data = json.loads(resp.read().decode())
                    pages = (data.get('query', {}) or {}).get('pages', {})
                    for pid, pdata in pages.items():
                        try:
                            ii = (pdata.get('imageinfo') or [{}])[0]
                            thumb = ii.get('thumburl', '') or ii.get('url', '')
                            if not thumb or not thumb.startswith('http'): continue
                            sz_info = ii.get('size', 0)
                            if sz_info and sz_info > 10*1024*1024: continue  # skip >10MB originals
                            req2 = urllib.request.Request(thumb, headers={'User-Agent': 'ViralDNA/69.0'})
                            with urllib.request.urlopen(req2, timeout=8) as dl:
                                raw = dl.read()
                            if len(raw) < 10000: continue
                            with open(img_path, 'wb') as f:
                                f.write(raw)
                            im = Image.open(img_path).convert('RGB')
                            arr = np.array(im)
                            h_img, w_img = im.size[1], im.size[0]
                            sz = os.path.getsize(img_path)
                            if arr.std() < 15 or w_img < 400 or h_img < 300:
                                os.remove(img_path); continue
                            # v75.3: Reject watermarked stock photos
                            is_stock, stock_reason = _is_watermarked_stock(
                                img_path, img_url=thumb)
                            if is_stock:
                                print(f"      [WikiCommons] Scene {i} REJECTED: {stock_reason}")
                                try: os.remove(img_path)
                                except: pass
                                continue
                            # v75.3: Reject duplicates
                            import hashlib
                            with open(img_path, 'rb') as _hf:
                                _h = hashlib.md5(_hf.read()).hexdigest()
                            if _h in used_image_hashes:
                                print(f"      [WikiCommons] Scene {i} REJECTED duplicate")
                                try: os.remove(img_path)
                                except: pass
                                continue
                            used_image_hashes.add(_h)
                            print(f"      [WikiCommons] Scene {i} saved ({sz//1024}KB, {w_img}x{h_img})")
                            downloaded = True
                            break
                        except Exception:
                            if os.path.exists(img_path):
                                try: os.remove(img_path)
                                except: pass
                except Exception as e:
                    print(f"      [WikiCommons] Scene {i} failed: {e}")

            # Source 3: Unsplash (random from curated photo site — usually high quality)
            if not downloaded:
                try:
                    print(f"    Assembler: [Unsplash] Fetching scene {i}...")
                    quality_term = urllib.parse.quote((prompt[:80] if prompt else topic_title) + " professional photography")
                    url = f"https://source.unsplash.com/1280x720/?{quality_term}"
                    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        content = resp.read()
                    if len(content) > 5120:
                        with open(img_path, 'wb') as f:
                            f.write(content)
                        if _is_valid_image(img_path):
                            quality = self._validate_image_quality(img_path)
                            if quality["passed"]:
                                # v75.3: Reject watermarked stock photos
                                is_stock, stock_reason = _is_watermarked_stock(
                                    img_path, img_url=url)
                                if is_stock:
                                    print(f"      [Unsplash] Scene {i} REJECTED: {stock_reason}")
                                    try: os.remove(img_path)
                                    except: pass
                                else:
                                    # v75.3: Reject duplicates
                                    import hashlib
                                    with open(img_path, 'rb') as _hf:
                                        _h = hashlib.md5(_hf.read()).hexdigest()
                                    if _h in used_image_hashes:
                                        print(f"      [Unsplash] Scene {i} REJECTED duplicate")
                                        try: os.remove(img_path)
                                        except: pass
                                    else:
                                        used_image_hashes.add(_h)
                                        image_paths.append(img_path)
                                        downloaded = True
                                        print(f"      ✅ [Unsplash] Scene {i} — quality: {quality['score']:.0f}/100")
                            else:
                                print(f"      ⚠️ [Unsplash] Rejected: {quality['reason']}")
                                os.remove(img_path)
                        else:
                            os.remove(img_path)
                except Exception as e:
                    print(f"      ⚠️ [Unsplash] Scene {i} failed: {e}")

            # Source 3: Pexels
            if not downloaded:
                try:
                    print(f"    Assembler: [Pexels] Fetching scene {i}...")
                    pexels_key = config.API_KEYS.get("PEXELS_API_KEY", "")
                    if pexels_key:
                        search_term = urllib.parse.quote(prompt[:80] if prompt else topic_title)
                        url = f"https://api.pexels.com/v1/search?query={search_term}&per_page=3&size=large"
                        req = urllib.request.Request(url, headers={'Authorization': pexels_key})
                        with urllib.request.urlopen(req, timeout=10) as resp:
                            data = json.loads(resp.read())
                        photos = data.get("photos", [])
                        if photos:
                            img_url = photos[0].get("src", {}).get("large", photos[0].get("src", {}).get("original", ""))
                            if img_url:
                                urllib.request.urlretrieve(img_url, img_path)
                                if os.path.exists(img_path) and os.path.getsize(img_path) > 5120 and _is_valid_image(img_path):
                                    quality = self._validate_image_quality(img_path)
                                    if quality["passed"]:
                                        # v75.3: Reject watermarked stock photos
                                        is_stock, stock_reason = _is_watermarked_stock(
                                            img_path, img_url=img_url)
                                        if is_stock:
                                            print(f"      [Pexels] Scene {i} REJECTED: {stock_reason}")
                                            try: os.remove(img_path)
                                            except: pass
                                        else:
                                            # v75.3: Reject duplicates
                                            import hashlib
                                            with open(img_path, 'rb') as _hf:
                                                _h = hashlib.md5(_hf.read()).hexdigest()
                                            if _h in used_image_hashes:
                                                print(f"      [Pexels] Scene {i} REJECTED duplicate")
                                                try: os.remove(img_path)
                                                except: pass
                                            else:
                                                used_image_hashes.add(_h)
                                                image_paths.append(img_path)
                                                downloaded = True
                                                print(f"      ✅ [Pexels] Scene {i} — quality: {quality['score']:.0f}/100")
                                    else:
                                        print(f"      ⚠️ [Pexels] Rejected: {quality['reason']}")
                                        os.remove(img_path)
                                else:
                                    if os.path.exists(img_path):
                                        os.remove(img_path)
                except Exception as e:
                    print(f"      ⚠️ [Pexels] Scene {i} failed: {e}")

            # Source 4: Pixabay
            if not downloaded:
                try:
                    print(f"    Assembler: [Pixabay] Fetching scene {i}...")
                    pixabay_key = config.API_KEYS.get("PIXABAY_API_KEY", "")
                    if pixabay_key:
                        search_term = urllib.parse.quote(prompt[:80] if prompt else topic_title)
                        url = f"https://pixabay.com/api/?key={pixabay_key}&q={search_term}&image_type=photo&per_page=3&orientation=horizontal"
                        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                        with urllib.request.urlopen(req, timeout=10) as resp:
                            data = json.loads(resp.read())
                        hits = data.get("hits", [])
                        if hits:
                            img_url = hits[0].get("largeImageURL", hits[0].get("webformatURL", ""))
                            if img_url:
                                urllib.request.urlretrieve(img_url, img_path)
                                if os.path.exists(img_path) and os.path.getsize(img_path) > 5120 and _is_valid_image(img_path):
                                    quality = self._validate_image_quality(img_path)
                                    if quality["passed"]:
                                        # v75.3: Reject watermarked stock photos
                                        is_stock, stock_reason = _is_watermarked_stock(
                                            img_path, img_url=img_url)
                                        if is_stock:
                                            print(f"      [Pixabay] Scene {i} REJECTED: {stock_reason}")
                                            try: os.remove(img_path)
                                            except: pass
                                        else:
                                            # v75.3: Reject duplicates
                                            import hashlib
                                            with open(img_path, 'rb') as _hf:
                                                _h = hashlib.md5(_hf.read()).hexdigest()
                                            if _h in used_image_hashes:
                                                print(f"      [Pixabay] Scene {i} REJECTED duplicate")
                                                try: os.remove(img_path)
                                                except: pass
                                            else:
                                                used_image_hashes.add(_h)
                                                image_paths.append(img_path)
                                                downloaded = True
                                                print(f"      ✅ [Pixabay] Scene {i} — quality: {quality['score']:.0f}/100")
                                    else:
                                        print(f"      ⚠️ [Pixabay] Rejected: {quality['reason']}")
                                        os.remove(img_path)
                                else:
                                    if os.path.exists(img_path):
                                        os.remove(img_path)
                except Exception as e:
                    print(f"      ⚠️ [Pixabay] Scene {i} failed: {e}")

            # Source 5: ComfyUI (LAST RESORT — generates AI illustrations, not real photos)
            # Only used if all real-photo sources fail. Images are obviously AI-generated.
            if not downloaded:
                try:
                    from comfyui_image_generator import generate_scene_image, ensure_ready
                    comfy_ready = ensure_ready()
                    if comfy_ready:
                        print(f"    Assembler: [ComfyUI-LAST-RESORT] Generating scene {i}...")
                        comfy_out = img_path.replace(".jpg", ".png")
                        result = generate_scene_image(
                            scene_description=prompt[:200] if prompt else topic_title,
                            output_path=comfy_out,
                            width=1280, height=720
                        )
                        if result and os.path.exists(comfy_out):
                            from PIL import Image as _IMG
                            _im = _IMG.open(comfy_out).convert("RGB")
                            _im.save(img_path, "JPEG", quality=92)
                            os.remove(comfy_out)
                            if os.path.exists(img_path) and os.path.getsize(img_path) > 5120:
                                image_paths.append(img_path)
                                downloaded = True
                                print(f"      ⚠️ [ComfyUI-LAST-RESORT] Scene {i} saved ({os.path.getsize(img_path):,} bytes) — AI-generated, not real")
                            else:
                                if os.path.exists(img_path):
                                    os.remove(img_path)
                        elif result and os.path.exists(img_path):
                            if os.path.getsize(img_path) > 5120:
                                image_paths.append(img_path)
                                downloaded = True
                                print(f"      ⚠️ [ComfyUI-LAST-RESORT] Scene {i} saved ({os.path.getsize(img_path):,} bytes) — AI-generated, not real")
                    else:
                        print(f"      ⚠️ [ComfyUI] Server not ready, skipping...")
                except ImportError:
                    pass
                except Exception as e:
                    print(f"      ⚠️ [ComfyUI] Scene {i} failed: {e}")

            # Source 6: Craiyon (disabled — consistently returns 403)
            # Source 7: Pollinations (disabled — returns news screenshots with text)

            if not downloaded:
                print(f"      ❌ All image sources failed for scene {i}. Will use fallback background.")

        return image_paths

    def generate_ass_file(self, script_text, total_duration, ass_path, out_w=1280, out_h=720):
        words = script_text.split()
        if not words:
            return False

        total_words = len(words)
        phrases = []
        words_per_phrase = 5
        for i in range(0, len(words), words_per_phrase):
            phrases.append(" ".join(words[i:i + words_per_phrase]))

        events = []
        # TTS engine has ~0.3-0.8s startup latency before first word is spoken.
        # Compensate by applying a sync offset so subtitles match actual speech onset.
        current_time = 0.0
        SYNC_OFFSET_S = 0.5   # positive = subtitles appear earlier (closer to actual speech)

        def format_ass_time(seconds):
            seconds = max(0.0, seconds - SYNC_OFFSET_S)
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            centiseconds = int((seconds % 1) * 100)
            return f"{hours:01d}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"

        for phrase in phrases:
            phrase_word_count = len(phrase.split())
            phrase_duration = total_duration * (phrase_word_count / total_words)
            end_time = current_time + phrase_duration
            start_str = format_ass_time(current_time)
            end_str = format_ass_time(end_time)
            dialogue_line = f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{{\\fad(200,200)}}{phrase}"
            events.append(dialogue_line)
            current_time = end_time

        if out_h > out_w:
            font_size = 55
            margin_v = 120
        else:
            font_size = 45
            margin_v = 60

        ass_content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {out_w}
PlayResY: {out_h}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Bebas Neue,{font_size},&H00FFFFFF,&H0000D7FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,2,2,30,30,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + "\n".join(events)

        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(ass_content)
        print(f"    Assembler: Successfully wrote timed ASS subtitles to {ass_path}")
        return True

    def assemble_video(self, slot, audio_path, visual_path, output_name,
                       target_duration_s: float = 30.0, async_mode: bool = False,
                       script_text: str = None, is_short: bool = False,
                       topic_title: str = ""):
        output_path = os.path.join(config.DRIVE["VIDEO_OUTPUT"], output_name)

        real_duration = self.get_audio_duration(audio_path)
        if real_duration is not None and real_duration > 0:
            print(f"    Assembler: Probed physical audio duration -> {real_duration:.2f}s "
                  f"(Overriding target {target_duration_s:.2f}s)")
            target_duration_s = real_duration

        duration_str = f"{target_duration_s:.2f}"
        runtime_dir = os.path.dirname(audio_path)
        ass_path = os.path.join(runtime_dir, f"{output_name}.ass")

        if is_short:
            out_w, out_h = 1080, 1920
        else:
            out_w, out_h = 1280, 720

        has_subtitles = False
        if script_text:
            has_subtitles = self.generate_ass_file(script_text, target_duration_s, ass_path, out_w, out_h)

        image_paths = []
        if is_short:
            num_scenes = 3
        elif target_duration_s > 120:
            num_scenes = 7
        elif target_duration_s > 60:
            num_scenes = 5
        else:
            num_scenes = 3

        if script_text:
            print(f"    Assembler: Preparing generative slideshow ({num_scenes} scenes) via multi-source image chain...")
            prompts = self.generate_image_prompts(script_text, num_scenes)
            slideshow_dir = os.path.join(runtime_dir, f"slideshow_{output_name.replace('.mp4', '')}")
            image_paths = self.download_scene_images(prompts, slideshow_dir, topic_title=topic_title or script_text[:100])

        if not image_paths:
            # v52.1: Try local image pack before falling back to static background
            print("    Assembler: API image sources failed, trying local image pack...")
            try:
                import importlib.util
                lip_path = os.path.join(os.path.dirname(__file__), "local_image_pack.py")
                spec = importlib.util.spec_from_file_location("local_image_pack", lip_path)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    pack = mod.LocalImagePack()
                local_images = pack.get_images(script_text or "", count=num_scenes, diversity=True)
                if local_images:
                    slideshow_dir = os.path.join(runtime_dir, f"slideshow_{output_name.replace('.mp4', '')}")
                    os.makedirs(slideshow_dir, exist_ok=True)
                    for i, src in enumerate(local_images):
                        import shutil
                        dest = os.path.join(slideshow_dir, f"scene_{i}.jpg")
                        shutil.copy2(src, dest)
                        image_paths.append(dest)
                    print(f"    Assembler: ✓ Local pack: {len(image_paths)} images for slideshow")
            except Exception:
                pass

        if not image_paths:
            print(f"    Assembler: Falling back to static background loop ({visual_path}).")
            image_paths = [visual_path]

        cmd_inputs = []
        filter_parts = []

        unique_images = list(image_paths)
        if len(unique_images) <= 1:
            target_image = unique_images[0] if unique_images else visual_path
            image_paths = [target_image]
            num_inputs = 1
            cmd_inputs.extend(["-loop", "1", "-t", f"{target_duration_s:.2f}", "-i", target_image])
            scale_filter = f"scale={out_w}:{out_h},setsar=1"
            fade_filter = f"fade=t=in:st=0:d=0.5,fade=t=out:st={target_duration_s - 0.5:.2f}:d=0.5"
            filter_parts.append(f"[0:v]{scale_filter},{fade_filter}[bgv];")
        else:
            if is_short:
                MAX_CLIP_DURATION = 6.0
            elif target_duration_s > 120:
                MAX_CLIP_DURATION = 25.0
            elif target_duration_s > 60:
                MAX_CLIP_DURATION = 20.0
            else:
                MAX_CLIP_DURATION = 15.0

            import math
            min_clips = math.ceil(target_duration_s / MAX_CLIP_DURATION)
            min_clips = min(min_clips, num_scenes)
            min_clips = max(min_clips, 1)

            if len(unique_images) < min_clips:
                repeated_images = []
                while len(repeated_images) < min_clips:
                    repeated_images.extend(unique_images)
                image_paths = repeated_images[:min_clips]
            else:
                image_paths = unique_images[:min_clips]

            num_inputs = len(image_paths)
            clip_duration = target_duration_s / num_inputs

            # Use gentler Kenburns zoom for main videos (less magnification = fewer artifacts)
            zoom_percent = 0.03 if not is_short else 0.05
            for i, img in enumerate(image_paths):
                cmd_inputs.extend(["-loop", "1", "-t", f"{clip_duration:.2f}", "-i", img])
                total_frames = int(clip_duration * 25)
                zoom_expr = f"1+{zoom_percent}*in/{total_frames}"
                pan_x = "(iw-iw/zoom)/2"
                pan_y = "(ih-ih/zoom)/2"
                # Scale slightly above target to allow Kenburns pan without edge artifacts
                scale_factor = 1.08 if not is_short else 1.2
                kenburns = (f"scale={int(out_w * scale_factor)}:{int(out_h * scale_factor)},"
                            f"zoompan=z='{zoom_expr}':x='{pan_x}':y='{pan_y}':d=1:"
                            f"s={out_w}x{out_h}:fps=25,setsar=1")
                fade_filter = f"fade=t=in:st=0:d=0.5,fade=t=out:st={clip_duration - 0.5:.2f}:d=0.5"
                filter_parts.append(f"[{i}:v]{kenburns},{fade_filter}[v{i}];")

            concat_input_tags = "".join(f"[v{i}]" for i in range(num_inputs))
            filter_parts.append(f"{concat_input_tags}concat=n={num_inputs}:v=1:a=0[bgv];")

        # No FFmpeg watermark overlay on video — branding is only on the YouTube thumbnail
        audio_input_idx = num_inputs
        cmd_inputs.extend(["-i", audio_path])

        if has_subtitles:
            escaped_ass = ass_path.replace(":", "\\:").replace("\\", "/")
            filter_parts.append(f"[bgv]subtitles={escaped_ass}[outv]")
        else:
            filter_parts.append(f"[bgv]copy[outv]")

        filter_complex = "".join(filter_parts)

        # v64.0: use HW encoder if available
        video_encoder = self._get_video_encoder()
        preset = "medium" if video_encoder == "libx264" else "default"

        cmd = [self.ffmpeg, "-y", "-threads", "2"]
        cmd.extend(cmd_inputs)
        cmd.extend([
            "-filter_complex", filter_complex,
            "-map", "[outv]",
            "-map", f"{audio_input_idx}:a",
            "-c:v", video_encoder,
        ])
        if video_encoder == "libx264":
            cmd.extend(["-preset", preset])
        cmd.extend([
            "-r", "25", "-g", "25",
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            output_path
        ])

        if async_mode:
            log_dir = os.path.join(config.DRIVE["VIDEO_OUTPUT"], "logs")
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(log_dir, f"{output_name}.log")
            log_file = open(log_path, "w")
            print(f"    Assembler: Launching asynchronous background assembly for {output_name}...")
            process = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT)
            return {
                "process": process, "path": output_path, "log_path": log_path,
                "log_file": log_file, "output_name": output_name, "duration_str": duration_str
            }
        else:
            log_dir = os.path.join(config.DRIVE["VIDEO_OUTPUT"], "logs")
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(log_dir, f"{output_name}.log")
            print(f"    Assembler: Syncing frames. Target: {duration_str}s | Encoder: {video_encoder}...")
            with open(log_path, "w") as log_file:
                result = subprocess.run(cmd, stdout=log_file, stderr=subprocess.STDOUT)
            if result.returncode != 0:
                # Read last 50 lines of log for error context
                try:
                    with open(log_path, "r") as lf:
                        tail = "".join(lf.readlines()[-50:])
                except Exception:
                    tail = "(log unreadable)"
                print(f"❌ FFmpeg Assembly Failed (rc={result.returncode}):\n{tail}")
                raise Exception("Assembly failed.")

            # v64.0: validate output quality
            is_valid, report = self.validate_output(
                output_path, expected_w=out_w, expected_h=out_h
            )
            if not is_valid:
                print(f"   ⚠️ VALIDATION WARNINGS: {'; '.join(report['issues'])}")
            else:
                print(f"   ✅ Quality validated: {report['bitrate_kbps']}kbps, "
                      f"{report['width']}x{report['height']}, {report['duration_s']:.1f}s")

            print(f"    ✅ Assembled: {output_name} ({duration_str}s)")
            return {"path": output_path, "validation_report": report}
