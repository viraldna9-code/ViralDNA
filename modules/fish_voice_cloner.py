"""
Fish Speech Voice Cloning Module for ViralDNA 2.0
Direct local inference — no API server required.

Checkpoint dir: /home/jay/fish-speech-v1.5/checkpoints/fish-speech-1.4/
  - model.pth (944MB) — text2semantic model
  - firefly-gan-vq-fsq-8x1024-21hz-generator.pth (180MB) — VQGAN decoder
  - config.json, tokenizer.json, etc.

Usage:
    cloner = FishVoiceCloner()
    cloner.load_all()
    cloner.clone_voice(text, ref_audio, ref_text, output_path)
"""

import os
import sys
import time
import warnings
import numpy as np
import torch
import torchaudio
import soundfile as sf
import librosa

FISH_DIR = "/home/jay/fish-speech-v1.5"
if FISH_DIR not in sys.path:
    sys.path.insert(0, FISH_DIR)

warnings.filterwarnings("ignore")

from fish_speech.models.text2semantic.llama import BaseTransformer
from fish_speech.models.vqgan.modules.firefly import FireflyArchitecture
from tools.llama.generate import load_model, generate_long
from tools.vqgan.inference import load_model as load_decoder_model


class FishVoiceCloner:
    def __init__(self, checkpoint_dir=None, device=None):
        """
        checkpoint_dir: directory containing model.pth, config.json, tokenizer.json, etc.
        """
        self.checkpoint_dir = checkpoint_dir or "/home/jay/fish-speech-v1.5/checkpoints/fish-speech-1.4"
        self.model_path = os.path.join(self.checkpoint_dir, "model.pth")
        self.decoder_path = os.path.join(self.checkpoint_dir, "firefly-gan-vq-fsq-8x1024-21hz-generator.pth")
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = None
        self.decode_one_token = None
        self.decoder_model = None
        self._loaded = False

    def load_model(self):
        """Load text2semantic model. Pass DIRECTORY path, not .pth file."""
        print(f"🐟 [Fish Speech] Loading text2semantic model on {self.device}...")
        t0 = time.time()

        # CRITICAL: load_model expects the DIRECTORY, not the .pth file
        # It reads config.json + tokenizer.json from the directory, then loads model.pth
        dtype = torch.bfloat16 if self.device == "cuda" else torch.float32
        self.model, self.decode_one_token = load_model(
            self.checkpoint_dir,  # DIRECTORY, not .pth
            device=self.device,
            precision=dtype,
            compile=False,
        )

        with torch.device(self.device):
            self.model.setup_caches(
                max_batch_size=1,
                max_seq_len=self.model.config.max_seq_len,
                dtype=next(self.model.parameters()).dtype,
            )

        n_params = sum(p.numel() for p in self.model.parameters()) / 1e6
        print(f"🐟 [Fish Speech] Model loaded: {n_params:.0f}M params in {time.time()-t0:.1f}s")
        return self

    def load_decoder(self):
        """Load VQGAN decoder."""
        print(f"🐟 [Fish Speech] Loading VQGAN decoder on {self.device}...")
        t0 = time.time()
        self.decoder_model = load_decoder_model(
            config_name="firefly_gan_vq",
            checkpoint_path=self.decoder_path,
            device=self.device,
        )
        print(f"🐟 [Fish Speech] Decoder loaded in {time.time()-t0:.1f}s")
        return self

    def load_all(self):
        self.load_model()
        self.load_decoder()
        self._loaded = True
        return self

    def _encode_reference(self, audio_path, max_ref_seconds=15):
        """
        Encode reference audio to VQ tokens for voice cloning.
        Trims reference to max_ref_seconds to stay within model's max_seq_len.
        """
        if self.decoder_model is None:
            self.load_decoder()

        sr = self.decoder_model.spec_transform.sample_rate
        waveform, orig_sr = torchaudio.load(audio_path)

        if waveform.shape[0] > 1:
            waveform = torch.mean(waveform, dim=0, keepdim=True)
        if orig_sr != sr:
            resampler = torchaudio.transforms.Resample(orig_freq=orig_sr, new_freq=sr)
            waveform = resampler(waveform)

        audio = waveform.squeeze().numpy()
        original_duration = len(audio) / sr

        # Trim reference audio to avoid exceeding max_seq_len
        max_samples = int(max_ref_seconds * sr)
        if len(audio) > max_samples:
            audio = audio[:max_samples]

        duration = len(audio) / sr
        print(f"🐟 [Fish Speech] Reference: {duration:.1f}s (trimmed from {original_duration:.1f}s) at {sr}Hz")

        audios = torch.from_numpy(audio).to(self.decoder_model.device)[None, None, :]
        audio_lengths = torch.tensor([audios.shape[2]], device=self.decoder_model.device, dtype=torch.long)

        with torch.no_grad():
            prompt_tokens = self.decoder_model.encode(audios, audio_lengths)[0][0]

        print(f"🐟 [Fish Speech] Encoded reference tokens: {prompt_tokens.shape}")
        return prompt_tokens

    def clone_voice(self, text, reference_audio, reference_text, output_path,
                    temperature=0.7, top_p=0.7, repetition_penalty=1.2, chunk_length=200):
        """Generate speech cloned from reference voice."""
        if not self._loaded:
            self.load_all()

        print(f"🐟 [Fish Speech] Cloning voice for: '{text[:100]}'")

        prompt_tokens = self._encode_reference(reference_audio)

        t0 = time.time()
        all_codes = []

        generator = generate_long(
            model=self.model,
            device=self.device,
            decode_one_token=self.decode_one_token,
            text=text,
            num_samples=1,
            max_new_tokens=0,
            top_p=top_p,
            repetition_penalty=repetition_penalty,
            temperature=temperature,
            compile=False,
            iterative_prompt=True,
            max_length=2048,
            chunk_length=chunk_length,
            prompt_text=[reference_text],
            prompt_tokens=[prompt_tokens],
        )

        for response in generator:
            if response.action == "sample" and response.codes is not None:
                all_codes.append(response.codes)

        if not all_codes:
            raise RuntimeError("Fish Speech generated no audio codes!")

        codes = torch.cat(all_codes, dim=-1)
        gen_time = time.time() - t0
        print(f"🐟 [Fish Speech] Generated {codes.shape[1]} tokens in {gen_time:.1f}s")

        # Decode to audio
        feature_lengths = torch.tensor([codes.shape[1]], device=self.device)
        with torch.no_grad():
            audio = self.decoder_model.decode(
                indices=codes[None],
                feature_lengths=feature_lengths,
            )[0].squeeze()

        audio_np = audio.cpu().float().numpy()
        peak = np.max(np.abs(audio_np))
        if peak > 0:
            audio_np = audio_np * (0.95 / peak)

        sr = self.decoder_model.spec_transform.sample_rate
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        sf.write(output_path, audio_np, sr)
        duration = len(audio_np) / sr
        print(f"🐟 [Fish Speech] Saved: {output_path} ({duration:.1f}s, {sr}Hz)")
        return output_path

    def tts(self, text, output_path, temperature=0.7, top_p=0.7, repetition_penalty=1.2):
        """Standard TTS without voice cloning."""
        if not self._loaded:
            self.load_all()

        print(f"🐟 [Fish Speech] TTS: '{text[:100]}'")

        t0 = time.time()
        all_codes = []

        generator = generate_long(
            model=self.model,
            device=self.device,
            decode_one_token=self.decode_one_token,
            text=text,
            num_samples=1,
            max_new_tokens=0,
            top_p=top_p,
            repetition_penalty=repetition_penalty,
            temperature=temperature,
            compile=False,
            iterative_prompt=True,
            max_length=2048,
            chunk_length=200,
        )

        for response in generator:
            if response.action == "sample" and response.codes is not None:
                all_codes.append(response.codes)

        if not all_codes:
            raise RuntimeError("Fish Speech generated no audio codes!")

        codes = torch.cat(all_codes, dim=-1)
        print(f"🐟 [Fish Speech] Generated {codes.shape[1]} tokens in {time.time()-t0:.1f}s")

        feature_lengths = torch.tensor([codes.shape[1]], device=self.device)
        with torch.no_grad():
            audio = self.decoder_model.decode(
                indices=codes[None],
                feature_lengths=feature_lengths,
            )[0].squeeze()

        audio_np = audio.cpu().float().numpy()
        peak = np.max(np.abs(audio_np))
        if peak > 0:
            audio_np = audio_np * (0.95 / peak)

        sr = self.decoder_model.spec_transform.sample_rate
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        sf.write(output_path, audio_np, sr)
        duration = len(audio_np) / sr
        print(f"🐟 [Fish Speech] Saved: {output_path} ({duration:.1f}s, {sr}Hz)")
        return output_path


if __name__ == "__main__":
    cloner = FishVoiceCloner()
    cloner.load_all()

    test_text = "Breaking news from India today. The government has announced new policies that will affect millions of citizens across the country."
    ref_audio = "/home/jay/voice_sample.wav"
    ref_text = "This is a reference voice sample for cloning."
    output = "/home/jay/ViralDNA/output/runtime/fish_clone_test.wav"

    cloner.clone_voice(
        text=test_text,
        reference_audio=ref_audio,
        reference_text=ref_text,
        output_path=output,
    )
    print(f"\n✅ Voice clone test complete: {output}")
