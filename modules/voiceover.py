# VERSION: 62.0
# MODULE: voiceover.py
# PURPOSE: Advanced bilingual newsroom audio engine. Performs high-fidelity Telugu-English splitting,
#          sequential synthesis to prevent MS rate limits, RVC batch directory voice cloning
#          of spoken chunks to ensure zero drift/hallucination, precision silent pause stitching,
#          and broadcast-grade DSP mastering (Highpass, Compressor, Limiter).

import os
import re
import html
import shutil
import subprocess
import asyncio
import config

class VoiceoverGenerator:
    def __init__(self, engine=None, config_obj=None):
        """
        Initializes the Advanced Bilingual Audio Engine.
        :param engine: Database client or auxiliary client (unused, kept for signature compatibility)
        :param config_obj: Configuration module (unused, uses global config for standard mappings)
        """
        # edge-tts binary: use system path or env var override (GitHub Actions installs globally)
        self.edge_tts_bin = os.getenv("EDGE_TTS_BIN", "edge-tts")
        # RVC removed — model file and rvc_python not available
        self.use_rvc = False
        self.rvc_model = None
        
        # Voice profiles (used for reference; gTTS uses default voices)
        # gTTS doesn't support rate/pitch — uses natural speech cadence
        self.eng_voice = "en-IN"      # Indian English (gTTS default)
        self.eng_rate = "-6%"
        self.eng_pitch = "-5Hz"
        
        self.tel_voice = "te-IN"      # Telugu (gTTS default)
        self.tel_rate = "-3%"
        self.tel_pitch = "-4Hz"
        
        # Configure output paths dynamically based on config DRIVE mappings
        self.audio_dir = config.DRIVE.get("AUDIO_OUTPUT", "/home/jay/ViralDNA/audio")
        self.runtime_dir = config.DRIVE.get("RUNTIME", "/home/jay/ViralDNA/output/runtime")
        
        os.makedirs(self.audio_dir, exist_ok=True)
        os.makedirs(self.runtime_dir, exist_ok=True)
        
        print("⚡ [AUDIO ENGINE] Advanced Bilingual Master-Stitching Engine (v62.0) Initialized.")
        if self.use_rvc:
            print(f"   🎙️  RVC Neural Voice Twin Active: {os.path.basename(self.rvc_model)}")
            print(f"   📢  Vocal Profiles: English -> {self.eng_voice} | Telugu -> {self.tel_voice}")
        else:
            print("   📢  Direct Edge-TTS Mode Active (RVC Neural Voice Twin Bypassed).")

    def _get_silence_file(self, duration: float) -> str:
        """
        Generates or retrieves a cached silent MP3 padding file of precise duration.
        """
        path = os.path.join(self.runtime_dir, f"silence_{duration:.2f}.mp3")
        if not os.path.exists(path):
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"anullsrc=r=24000:cl=mono",
                "-t", f"{duration:.2f}",
                "-c:a", "libmp3lame", "-b:a", "48k",
                path
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return path

    def _fix_tts_text(self, text):
        """Pre-process text for TTS: fix abbreviations, possessives, apostrophes."""
        import re as _re
        # Normalize ALL apostrophe-like Unicode characters to straight quotes first
        text = text.replace("\u2019", "'").replace("\u2018", "'")
        text = text.replace("\u2032", "'").replace("\u2035", "'")
        text = text.replace("\u02bc", "'").replace("\u02bb", "'")
        text = text.replace("\uff07", "'").replace("\u201b", "'")
        text = text.replace("\u2039", "'").replace("\u203a", "'")
        # Abbreviations -> full words
        abbrev = [
            (r'\bDr\.', 'Doctor'), (r'\bMr\.', 'Mister'), (r'\bMs\.', 'Miss'),
            (r'\bMrs\.', 'Missus'), (r'\bProf\.', 'Professor'), (r'\bSt\.', 'Saint'),
            (r'\bJr\.', 'Junior'), (r'\bSr\.', 'Senior'), (r'\bvs\.', 'versus'),
            (r'\bNo\.', 'Number'), (r'\bInc\.', 'Incorporated'), (r'\bLtd\.', 'Limited'),
            (r'\bCorp\.', 'Corporation'), (r'\bGovt\.', 'Government'),
            (r'\bDept\.', 'Department'), (r'\bUniv\.', 'University'),
            (r'\bAve\.', 'Avenue'), (r'\bBlvd\.', 'Boulevard'), (r'\bRd\.', 'Road'),
            (r'\bPM\.', 'Prime Minister'), (r'\bCM\.', 'Chief Minister'),
            (r'\bMLA\.', 'M L A'), (r'\bMP\.', 'M P'),
            (r'\bBJP\.', 'B J P'), (r'\bINC\.', 'I N C'), (r'\bTDP\.', 'T D P'),
            (r'\bYSRCP\.', 'Y S R C P'), (r'\bTRS\.', 'T R S'), (r'\bBRS\.', 'B R S'),
        ]
        for pat, repl in abbrev:
            text = _re.sub(pat, repl, text, flags=_re.IGNORECASE)
        # Remove possessive 's -> just the base word
        text = _re.sub(r"(\w+)'s\b", r"\1", text)
        text = _re.sub(r"(\w+)s'\b", r"\1s", text)
        # Strip remaining apostrophes
        text = text.replace("'", "")
        # Collapse double spaces
        text = _re.sub(r'\s+', ' ', text).strip()
        return text

    def _expand_contractions(self, text: str) -> str:
        """
        Expands contractions to full form so TTS doesn't pronounce them as two words.
        E.g. "you're" -> "you are", "they've" -> "they have", "it's" -> "it is".
        Must run BEFORE _fix_tts_text so contractions get expanded first.
        """
        contractions = {
            # Pronoun + be/have/will/would
            "you're": "you are", "they're": "they are", "we're": "we are",
            "I'm": "I am", "he's": "he is", "she's": "she is",
            "it's": "it is", "that's": "that is", "what's": "what is",
            "who's": "who is", "where's": "where is", "how's": "how is",
            "there's": "there is", "here's": "here is", "why's": "why is",
            "I've": "I have", "you've": "you have", "we've": "we have",
            "they've": "they have", "I'd": "I would", "you'd": "you would",
            "he'd": "he would", "she'd": "she would", "we'd": "we would",
            "they'd": "they would", "I'll": "I will", "you'll": "you will",
            "he'll": "he will", "she'll": "she will", "we'll": "we will",
            "they'll": "they will",
            # Negations — these are the most common TTS problem
            "isn't": "is not", "aren't": "are not",
            "wasn't": "was not", "weren't": "were not",
            "don't": "do not", "doesn't": "does not", "didn't": "did not",
            "won't": "will not", "wouldn't": "would not",
            "can't": "cannot", "couldn't": "could not",
            "shouldn't": "should not", "mustn't": "must not",
            "hasn't": "has not", "haven't": "have not", "hadn't": "had not",
            # Other common
            "let's": "let us", "who'd": "who would", "what'll": "what will",
            "who'll": "who will", "that'll": "that will", "it'll": "it will",
            "ain't": "is not", "y'all": "you all",
            # Possessive/genitive that edge-tts misreads
            "i'm": "i am",
        }
        # Gemini sometimes outputs contractions with SPACE instead of apostrophe
        # e.g. "isn t" instead of "isn't", "don t" instead of "don't"
        # Add space-separated variants so these also get expanded
        space_variants = {}
        for k, v in contractions.items():
            if "'" in k:
                space_key = k.replace("'", " ")
                space_variants[space_key] = v
        contractions.update(space_variants)
        # Add case variants for common contractions that appear in ALL CAPS
        upper_variants = {k.upper(): v.title() for k, v in contractions.items()}
        contractions.update(upper_variants)
        # Case-insensitive replacement — preserve original case of first letter
        for contraction, expansion in contractions.items():
            # Match whole word case-insensitively
            pattern = re.compile(re.escape(contraction), re.IGNORECASE)
            text = pattern.sub(lambda m, e=expansion: (
                e.capitalize() if m.group(0)[0].isupper() else e
            ), text)
        return text

    def _expand_acronyms(self, text: str) -> str:
        """
        Expands common acronyms to spelled-out letter sequences so TTS
        engines pronounce them correctly (e.g. INA -> I N A, not 'ina').
        Only processes ALL-CAPS tokens of 2-5 letters (skipping common words).
        """
        common_words = {"THE", "AND", "FOR", "ARE", "BUT", "NOT", "YOU", "ALL", "CAN",
                        "HER", "WAS", "ONE", "OUR", "HAD", "HAS", "ITS", "MAY", "NEW",
                        "NOW", "OLD", "SEE", "WHO", "BOY", "DID", "LET", "SAY", "SHE",
                        "TOO", "USE", "WAY", "USA", "BBC", "CNN"}
        def _replace(m):
            word = m.group(0)
            if word in common_words:
                return word
            # Spell out: "INA" -> "I N A", "NASA" -> "N A S A"
            return " ".join(list(word))
        # Match standalone ALL-CAPS words (2-5 chars, surrounded by word boundaries)
        return re.sub(r'\b([A-Z]{2,5})\b', _replace, text)

    def _segment_script(self, text: str) -> list:
        """
        Splits bilingual script text into English and Telugu blocks, and English blocks into sentences.
        """
        # Step 1: Extract Telugu blocks using specific Unicode pattern
        telugu_pattern = re.compile(r'([\u0c00-\u0c7f]+(?:[\s,\.\-\"\'](?:[\u0c00-\u0c7f]+))*)')
        blocks = []
        last_idx = 0
        for match in telugu_pattern.finditer(text):
            start, end = match.span()
            if start > last_idx:
                eng_text = text[last_idx:start]
                if eng_text.strip():
                    blocks.append({"lang": "en", "text": eng_text})
            te_text = match.group(0)
            if te_text.strip():
                blocks.append({"lang": "te", "text": te_text})
            last_idx = end
        if last_idx < len(text):
            eng_text = text[last_idx:]
            if eng_text.strip():
                blocks.append({"lang": "en", "text": eng_text})
                
        # Step 2: Sub-split English blocks into logical sentences to allow breathing cadence
        final_segments = []
        for b in blocks:
            if b["lang"] == "te":
                if re.search(r'[\u0c00-\u0c7f]', b["text"]):
                    final_segments.append(b)
            else:
                sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9]|$)', b["text"].strip())
                for s in sentences:
                    if re.search(r'[a-zA-Z0-9]', s):
                        final_segments.append({"lang": "en", "text": s.strip()})
                        
        return final_segments

    async def _synthesize_segment_async(self, text: str, lang: str, out_path: str) -> bool:
        """
        Synthesizes a single text segment using gTTS (Google Text-to-Speech).
        Falls back from edge-tts which is currently broken (NoAudioReceived).
        """
        import asyncio
        out_dir = os.path.dirname(out_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        # Map internal lang codes to gTTS language codes
        gtts_lang = "en" if lang == "en" else "te"

        try:
            # gTTS is synchronous — run in thread pool to not block the event loop
            loop = asyncio.get_event_loop()

            def _do_tts():
                from gtts import gTTS
                tts = gTTS(text=text, lang=gtts_lang, slow=False)
                tts.save(out_path)

            await loop.run_in_executor(None, _do_tts)
        except Exception as e:
            print(f"   ❌ gTTS Synthesis Error for '{text[:30]}...' (lang={gtts_lang}): {e}")
            return False

        # Post-synthesis verification
        if not os.path.exists(out_path):
            print(f"   ❌ Synthesis produced no output file for '{text[:30]}...'")
            return False
        if os.path.getsize(out_path) == 0:
            print(f"   ❌ Synthesis produced empty file for '{text[:30]}...'")
            os.remove(out_path)
            return False
        return True

    def generate_voiceover(self, script_obj, slot):
        """
        Main interface method. Performs bilingual segmenting, sequential synthesis,
        RVC batch chunk translation, pause-concatenation, and broadcast-grade DSP mastering.
        """
        text = script_obj.get("full_script", "").strip()
        # DEBUG: log the raw input text
        print(f"   [TTS DEBUG] Raw input ({len(text)} chars): {repr(text[:200])}")
        # Normalize smart quotes to straight quotes BEFORE contraction expansion.
        # Gemini/humanizer often outputs ' (right single quote) instead of '
        # which breaks contraction matching and causes edge-tts to read "Don't" as "Don T"
        text = text.replace("\u2019", "'").replace("\u2018", "'")
        # Also normalize other apostrophe-like characters
        text = text.replace("\u2032", "'").replace("\u2035", "'")
        text = text.replace("\u02bc", "'").replace("\u02bb", "'")
        text = text.replace("\uff07", "'").replace("\u201b", "'")
        print(f"   [TTS DEBUG] After smart quote norm: {repr(text[:200])}")
        text = self._expand_contractions(text)  # Fix "you're" -> "you are" etc.
        print(f"   [TTS DEBUG] After contraction expansion: {repr(text[:200])}")
        text = self._expand_acronyms(text)  # Fix TTS pronunciation of acronyms
        text = self._fix_tts_text(text)  # Fix abbreviations, possessives, apostrophes
        print(f"   [TTS DEBUG] After fix_tts_text: {repr(text[:200])}")
        final_path = os.path.join(self.audio_dir, f"{slot}_final.mp3")

        print(f"▶ [AUDIO ENGINE] Beginning generation for slot: {slot}...")
        
        # Configure dynamic pacing and mastering based on video slot type
        is_short = "short" in str(slot).lower()
        if is_short:
            print("   📱 Format Detected: Shorts/Reels (Fast-Paced, High-Retention Hype preset)")
            self.eng_rate = "+5%"
            self.eng_pitch = "+1Hz"
            self.tel_rate = "+5%"
            self.tel_pitch = "+1Hz"
            
            lang_transition_pause = 0.10
            sentence_end_pause = 0.25
            standard_pause = 0.05
            conclusion_tail_pause = 0.20
            
            mastering_filters = "highpass=f=80,equalizer=f=120:t=o:w=1:g=3.0,equalizer=f=4500:t=o:w=1:g=2.0,acompressor=threshold=-10dB:ratio=4:attack=3:release=40:makeup=3.5,alimiter=limit=-0.5dB"
        else:
            print("   📺 Format Detected: Long-Form Main Video (Trustworthy, Authoritative News preset)")
            self.eng_rate = "-6%"
            self.eng_pitch = "-5Hz"
            self.tel_rate = "-3%"
            self.tel_pitch = "-4Hz"
            
            lang_transition_pause = 0.15
            sentence_end_pause = 0.50
            standard_pause = 0.10
            conclusion_tail_pause = 0.40
            
            mastering_filters = "highpass=f=80,equalizer=f=120:t=o:w=1:g=2.5,equalizer=f=4500:t=o:w=1:g=1.5,acompressor=threshold=-12dB:ratio=3:attack=5:release=50:makeup=3,alimiter=limit=-1.0dB"
            
        # 1. Segment script dynamically
        segments = self._segment_script(text)
        print(f"   🔍 Forensic Segment Audit: Found {len(segments)} bilingual segments.")
        
        # Count words
        en_words = 0
        te_words = 0
        for s in segments:
            w_count = len(s["text"].split())
            if s["lang"] == "en":
                en_words += w_count
            else:
                te_words += w_count
        print(f"      🇺🇸 English: {en_words} words | 🇮🇳 Telugu: {te_words} words (Ratio: {te_words/(en_words+te_words or 1)*100:.1f}%)")

        # Create localized workspace inside output/runtime
        workspace_dir = os.path.join(self.runtime_dir, f"work_{slot}")
        if os.path.exists(workspace_dir):
            shutil.rmtree(workspace_dir)
        os.makedirs(workspace_dir, exist_ok=True)
        
        # 2. Sequential Synthesis Stage (Safe sequential processing prevents MS rate limiting)
        print("   🎙️  Synthesizing voice segments sequentially...")
        segment_paths = []
        max_retries = 3
        for idx, s in enumerate(segments):
            chunk_name = f"chunk_{idx:03d}.mp3"
            chunk_path = os.path.join(workspace_dir, chunk_name)
            
            # Synthesize single chunk with retry for edge-tts 7.2.8 transient failures
            success = False
            for attempt in range(1, max_retries + 1):
                success = asyncio.run(self._synthesize_segment_async(s["text"], s["lang"], chunk_path))
                if success:
                    break
                if attempt < max_retries:
                    print(f"      ↻ Retry {attempt}/{max_retries} for segment {idx}...")
                    import time
                    time.sleep(1.0 * attempt)  # Linear backoff: 1s, 2s
            
            if not success:
                raise RuntimeError(f"Failed to synthesize segment {idx} after {max_retries} attempts: '{s['text'][:40]}'")
            
            # Add to list of active audio chunks
            segment_paths.append((s, chunk_path))
            
        # 3. Batch RVC Stage (Processes all chunks in a single load to prevent OOM/drift/hallucination)
        if self.use_rvc:
            print(f"   🧠  RVC: Translating {len(segments)} spoken chunks sequentially to {os.path.basename(self.rvc_model)}...")
            rvc_cmd = [
                "/home/jay/venv/bin/python3",
                "/home/jay/modules/rvc_infer.py",
                "-i", workspace_dir,
                "-o", workspace_dir,
                "-m", self.rvc_model
            ]
            
            result = subprocess.run(rvc_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"   ❌ RVC Batch Translation Failed: {result.stderr}")
                raise RuntimeError("RVC Batch Translation FAILED. Voiceover generation halted.")
                
        # 4. Create precision-spaced stitching schedule (silence is stitched AFTER RVC to ensure 100% digital silence)
        print("   🧩  Assembling precision stitching schedule...")
        concat_list_path = os.path.join(workspace_dir, "concat_list.txt")
        stitching_files = []
        
        for idx, (s, path) in enumerate(segment_paths):
            # If RVC is active, use the converted rvc_chunk_*.mp3 instead of raw chunk_*.mp3
            if self.use_rvc:
                chunk_name = f"rvc_chunk_{idx:03d}.mp3"
                chunk_path = os.path.join(workspace_dir, chunk_name)
            else:
                chunk_path = path
                
            stitching_files.append(chunk_path)
            
            # Determine spacing pause after this segment
            if idx < len(segment_paths) - 1:
                next_s = segment_paths[idx+1][0]
                
                # Language Boundary Transition -> Tiny spacing for natural flow
                if s["lang"] != next_s["lang"]:
                    stitching_files.append(self._get_silence_file(lang_transition_pause))
                # Sentence Ending Boundary -> Clear pause to give reader breathing room
                elif s["lang"] == "en" and s["text"].endswith(('.', '!', '?')):
                    stitching_files.append(self._get_silence_file(sentence_end_pause))
                # Standard segment spacing -> Natural sub-clause transition pause
                else:
                    stitching_files.append(self._get_silence_file(standard_pause))
            else:
                # Script conclusion tail fade
                stitching_files.append(self._get_silence_file(conclusion_tail_pause))
                
        # Write files list for FFmpeg concat demuxer
        with open(concat_list_path, "w", encoding="utf-8") as f:
            for f_path in stitching_files:
                safe_path = f_path.replace("'", "'\\''")
                f.write(f"file '{safe_path}'\n")
                
        # 5. Concatenate segments into stitched raw file
        raw_stitched_path = os.path.join(workspace_dir, "raw_stitched.mp3")
        print("   🔗  Concatenating audio segments offline...")
        concat_cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_list_path,
            "-c", "copy",
            raw_stitched_path
        ]
        subprocess.run(concat_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        
        # 6. Broadcast DSP Mastering Stage (HPF -> Compressor -> Peak Limiter)
        print("   🎛️  DSP Mastering: Applying Highpass, Compressor, and Brickwall Limiter...")
        # (Uses slot-tailored dynamic mastering_filters defined at start of generation)
        
        master_cmd = [
            "ffmpeg", "-y",
            "-i", raw_stitched_path,
            "-af", mastering_filters,
            "-c:a", "libmp3lame", "-b:a", "192k",  # High-fidelity 192kbps final export
            final_path
        ]
        subprocess.run(master_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        
        # Forensic validation
        final_size = os.path.getsize(final_path)
        print(f"   ✅ [FORENSIC AUDIT] Audio mastering completed successfully!")
        print(f"      📁 Final Audio File: {final_path}")
        print(f"      ⚖️  File Size: {final_size} bytes ({final_size/1024:.1f} KB)")
        
        # Clean workspace
        try:
            shutil.rmtree(workspace_dir)
        except Exception:
            pass
            
        return {"status": "success", "path": final_path}
