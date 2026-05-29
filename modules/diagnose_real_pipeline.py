# Diagnostic script to run the real voiceover generation but keep the workspace
import os
import sys
import shutil

# Monkeypatch shutil.rmtree to be a no-op so we can inspect the workspace
orig_rmtree = shutil.rmtree
shutil.rmtree = lambda path, ignore_errors=False: print(f"[DIAGNOSTIC] Kept workspace at: {path}")

sys.path.append("/home/jay/modules")
import config
from gemini_engine import GeminiEngine
from script_generator import ScriptGenerator
from voiceover import VoiceoverGenerator

engine = GeminiEngine()
sg = ScriptGenerator(engine, config.SCRIPT_GENERATION_CONFIG)
vg = VoiceoverGenerator(None, config)

# Select a mock topic resembling the Telugu NRI panel topic
topic = {
    "title": "Telangana NRI panel studies Andhra Pradesh’s welfare model for migrant workers - The Hindu",
    "description": "A Telangana NRI panel is visiting Andhra Pradesh to study the welfare measures being implemented for migrant workers. The team seeks to understand the institutional mechanism and support systems.",
    "url": "https://www.thehindu.com/news/national/telangana-nri-panel-studies-ap-welfare-model/article12345.ece"
}

print("1. Generating script payload...")
script_payload = sg.run(topic)
main_data = script_payload.get_segment("main")
text = main_data["text"]
print("Generated text word count:", len(text.split()))
print("Generated text preview:", text[:200])

print("\n2. Generating voiceover (with RVC)...")
audio_result = vg.generate_voiceover({"full_script": text}, "test_main_diagnostic")
path = audio_result["path"]
print("Final audio path:", path)
print("Final audio exists:", os.path.exists(path))

# Find the workspace dir
workspace_dir = os.path.join(config.DRIVE["RUNTIME"], "voice_work_test_main_diagnostic")
print("Workspace dir exists:", os.path.exists(workspace_dir))

if os.path.exists(workspace_dir):
    import librosa
    import numpy as np
    print("\n--- Workspace Files Analysis ---")
    files = sorted(os.listdir(workspace_dir))
    for f in files:
        fpath = os.path.join(workspace_dir, f)
        if os.path.isfile(fpath) and fpath.endswith((".mp3", ".wav")):
            size = os.path.getsize(fpath)
            y, sr = librosa.load(fpath, sr=None)
            dur = librosa.get_duration(y=y, sr=sr)
            rms = np.mean(librosa.feature.rms(y=y))
            f0, voiced_flag, voiced_probs = librosa.pyin(y, fmin=70, fmax=300)
            voiced_frames = f0[voiced_flag] if len(f0) > 0 else []
            mean_f0 = np.mean(voiced_frames) if len(voiced_frames) > 0 else 0
            std_f0 = np.std(voiced_frames) if len(voiced_frames) > 0 else 0
            print(f"{f} | Size: {size/1024:.2f} KB | Dur: {dur:.2f}s | RMS: {rms:.6f} | Pitch: {mean_f0:.2f} Hz (std: {std_f0:.2f})")
