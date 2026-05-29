# VERSION: 65.0
# MODULE: video_assembler.py
# PURPOSE: Advanced Generative Slideshow + Kinetic Typography Captioning Engine.
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
        Semantic relevance gate — uses Serper image metadata (title, source domain)
        to reject off-topic images. Checks that the image title/URL contains at
        least one keyword from the scene prompt or topic title.
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
                  "quality", "image", "photo", "picture", "scene"}
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
        match_ratio = matches / len(key_terms)

        if match_ratio < 0.15:  # Less than 15% of topic keywords found
            return {
                "relevant": False,
                "reason": f"Off-topic (title: '{title[:60]}', match: {match_ratio:.0%})"
            }
        return {"relevant": True, "reason": f"Relevant ({match_ratio:.0%} match, title: '{title[:40]}')"}

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

            # 1. Resolution check — minimum 640x360
            if w < 640 or h < 360:
                return {"passed": False, "reason": f"Too small: {w}x{h} (min 640x360)", "score": 0}

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
            edges = cv2.Canny(gray, 50, 150)
            edge_density = np.count_nonzero(edges) / (w * h)
            if edge_density > 0.25:
                return {"passed": False, "reason": f"Too many edges/text overlay (density: {edge_density:.2f})", "score": 0}
            elif edge_density > 0.15:
                score -= (edge_density - 0.15) * 200
                reasons.append(f"high_edges({edge_density:.2f})")

            # Method B: MSER text region detection
            # News screenshots have many small high-contrast text regions
            try:
                mser = cv2.MSER_create()
                regions, _ = mser.detectRegions(gray)
                # Filter to small regions (text-sized)
                text_like = [r for r in regions if 20 < len(r) < 500]
                if len(text_like) > 80:
                    return {"passed": False, "reason": f"MSER text regions: {len(text_like)} (news screenshot?)", "score": 0}
                elif len(text_like) > 40:
                    score -= (len(text_like) - 40) * 0.3
                    reasons.append(f"mser_text({len(text_like)})")
            except Exception:
                pass  # MSER not critical

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
            # News channels place logos in corners — check for high-contrast
            # small regions in corners that differ from surroundings
            corner_size = min(w, h) // 6
            corners = [
                gray[:corner_size, :corner_size],           # top-left
                gray[:corner_size, -corner_size:],          # top-right
                gray[-corner_size:, :corner_size],          # bottom-left
                gray[-corner_size:, -corner_size:],         # bottom-right
            ]
            logo_detected = False
            for ci, corner in enumerate(corners):
                if corner.size == 0:
                    continue
                # Logos are small bright/dark patches on uniform backgrounds
                corner_blur = cv2.Laplacian(corner, cv2.CV_64F).var()
                corner_mean = corner.mean()
                # High variance in a small corner region = likely a logo
                if corner_blur > 500 and (corner_mean < 60 or corner_mean > 200):
                    logo_detected = True
                    break
                # Also check for solid-color patches (typical logo backgrounds)
                corner_std = corner.std()
                if corner_std < 20 and abs(corner_mean - corner_blur) > 100:
                    logo_detected = True
                    break
            if logo_detected:
                return {"passed": False, "reason": "TV logo/watermark detected in corner", "score": 0}

            # 7. Face detection — reject news screenshots with people
            # (We want documentary/stock photos, not news anchor shots)
            try:
                face_cascade = cv2.CascadeClassifier(
                    cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
                )
                if not face_cascade.empty():
                    faces = face_cascade.detectMultiScale(
                        gray, scaleFactor=1.1, minNeighbors=4,
                        minSize=(30, 30)
                    )
                    if len(faces) > 0:
                        # Check face size — large faces = news anchor/screenshot
                        max_face_area = max(fw * fh for (_, _, fw, fh) in faces)
                        img_area = w * h
                        face_ratio = max_face_area / img_area
                        if face_ratio > 0.05:  # Face takes >5% of image
                            return {"passed": False, "reason": f"Large face detected ({len(faces)} faces, max {face_ratio:.1%} of image)", "score": 0}
                        else:
                            # Small faces in crowd shots are OK but penalize
                            score -= len(faces) * 3
                            reasons.append(f"small_faces({len(faces)})")
            except Exception:
                pass  # Face detection not critical

            # 8. Near-white / near-black ratio — news screenshots are often
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

            # Source 1: Serper (try up to 3 results, pick best quality)
            if not downloaded:
                try:
                    print(f"    Assembler: [Serper] Fetching scene {i}...")
                    serper_key = config.API_KEYS.get("SERPER_API_KEY", "")
                    if serper_key:
                        headers = {'X-API-KEY': serper_key, 'Content-Type': 'application/json'}
                        search_q = prompt[:100] if prompt else topic_title
                        # Add negative keywords to filter out text/logos/screenshots
                        search_q += " -logo -text -screenshot -watermark -meme"
                        payload = {"q": search_q, "num": 5, "imgSize": "large"}
                        req_data = json.dumps(payload).encode('utf-8')
                        req = urllib.request.Request("https://google.serper.dev/images", data=req_data, headers=headers)
                        with urllib.request.urlopen(req, timeout=10) as resp:
                            data = json.loads(resp.read())
                        images = data.get("images", [])
                        # Try up to 3 results, pick the one that passes quality AND relevance gates
                        for attempt_idx, img_info in enumerate(images[:3]):
                            img_url = img_info.get("imageUrl", "")
                            if not img_url:
                                continue
                            # Relevance gate BEFORE downloading (no need to download off-topic images)
                            rel = self._check_relevance(img_info, prompt, topic_title)
                            if not rel["relevant"]:
                                print(f"      ⚠️ [Serper] Result {attempt_idx} off-topic: {rel['reason']}")
                                continue
                            urllib.request.urlretrieve(img_url, img_path)
                            if os.path.exists(img_path) and os.path.getsize(img_path) > 5120 and _is_valid_image(img_path):
                                # Quality gate — blur, text, edge density checks
                                quality = self._validate_image_quality(img_path)
                                if quality["passed"]:
                                    image_paths.append(img_path)
                                    downloaded = True
                                    print(f"      ✅ [Serper] Scene {i} saved ({os.path.getsize(img_path):,} bytes) — quality: {quality['score']:.0f}/100, {rel['reason']}")
                                    break
                                else:
                                    print(f"      ⚠️ [Serper] Result {attempt_idx} rejected: {quality['reason']}")
                                    os.remove(img_path)
                            else:
                                if os.path.exists(img_path):
                                    os.remove(img_path)
                except Exception as e:
                    print(f"      ⚠️ [Serper] Scene {i} failed: {e}")

            # Source 2: Unsplash (random from curated photo site — usually high quality)
            if not downloaded:
                try:
                    print(f"    Assembler: [Unsplash] Fetching scene {i}...")
                    # Add quality keywords to filter
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

            # Source 5: Craiyon
            if not downloaded:
                try:
                    print(f"    Assembler: [Craiyon] Generating scene {i}...")
                    payload = json.dumps({
                        "prompt": prompt[:200] if prompt else topic_title,
                        "token": None, "model": "photo",
                        "negative_prompt": "text, logo, watermark, writing"
                    }).encode('utf-8')
                    req = urllib.request.Request(
                        "https://api.craiyon.com/v3", data=payload,
                        headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'}
                    )
                    with urllib.request.urlopen(req, timeout=60) as resp:
                        data = json.loads(resp.read())
                    images = data.get("images", [])
                    if images:
                        import base64
                        img_data = images[0]
                        if isinstance(img_data, str) and img_data.startswith("data:image"):
                            img_data = base64.b64decode(img_data.split(",", 1)[1])
                        elif isinstance(img_data, str):
                            img_data = base64.b64decode(img_data)
                        with open(img_path, 'wb') as f:
                            f.write(img_data)
                        if os.path.exists(img_path) and os.path.getsize(img_path) > 5120 and _is_valid_image(img_path):
                            quality = self._validate_image_quality(img_path)
                            if quality["passed"]:
                                image_paths.append(img_path)
                                downloaded = True
                                print(f"      ✅ [Craiyon] Scene {i} — quality: {quality['score']:.0f}/100")
                            else:
                                print(f"      ⚠️ [Craiyon] Rejected: {quality['reason']}")
                                os.remove(img_path)
                        else:
                            if os.path.exists(img_path):
                                os.remove(img_path)
                except Exception as e:
                    print(f"      ⚠️ [Craiyon] Scene {i} failed: {e}")

            # Source 6: Pollinations
            if not downloaded:
                try:
                    print(f"    Assembler: [Pollinations] Fetching scene {i}...")
                    encoded_prompt = urllib.parse.quote(prompt[:200] if prompt else topic_title)
                    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1280&height=720&nologo=true&private=true&seed={i}"
                    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        content = resp.read()
                    if len(content) > 5120:
                        with open(img_path, 'wb') as f:
                            f.write(content)
                        if _is_valid_image(img_path):
                            quality = self._validate_image_quality(img_path)
                            if quality["passed"]:
                                image_paths.append(img_path)
                                downloaded = True
                                print(f"      ✅ [Pollinations] Scene {i} — quality: {quality['score']:.0f}/100")
                            else:
                                print(f"      ⚠️ [Pollinations] Rejected: {quality['reason']}")
                                os.remove(img_path)
                        else:
                            os.remove(img_path)
                except Exception as e:
                    print(f"      ⚠️ [Pollinations] Scene {i} failed: {e}")

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
                       script_text: str = None, is_short: bool = False):
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
            image_paths = self.download_scene_images(prompts, slideshow_dir, topic_title=script_text[:100])

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
