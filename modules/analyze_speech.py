import os
import sys
import numpy as np
import librosa

path = "/home/jay/ViralDNA/audio/main_final.mp3"
if not os.path.exists(path):
    print("File does not exist.")
    sys.exit(0)

print(f"Analyzing: {path}")
y, sr = librosa.load(path, sr=None)
duration = librosa.get_duration(y=y, sr=sr)
print(f"Duration: {duration:.2f}s")
print(f"Sampling Rate: {sr} Hz")

# Compute RMS over time frames
rms_frames = librosa.feature.rms(y=y)
mean_rms = np.mean(rms_frames)
max_rms = np.max(rms_frames)
print(f"Mean RMS: {mean_rms:.6f}")
print(f"Max RMS: {max_rms:.6f}")

# Spectral centroid (high for static/hiss, low-to-mid for voice)
centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
mean_centroid = np.mean(centroid)
print(f"Mean Spectral Centroid: {mean_centroid:.2f} Hz")

# Zero crossing rate (high for noise, low for voiced speech)
zcr = librosa.feature.zero_crossing_rate(y)
mean_zcr = np.mean(zcr)
print(f"Mean Zero Crossing Rate: {mean_zcr:.4f}")

# Fundamental frequency F0 tracking (YIN or PYIN) to see if there is pitch (melodic voice)
# Voice has a clear fundamental frequency, unvoiced noise/silence doesn't.
f0, voiced_flag, voiced_probs = librosa.pyin(y, fmin=librosa.note_to_hz('C2'), fmax=librosa.note_to_hz('C7'))
voiced_frames = f0[voiced_flag]
if len(voiced_frames) > 0:
    print(f"Pitch (F0) Detected! Voiced frames count: {len(voiced_frames)}")
    print(f"Mean F0 (Pitch): {np.mean(voiced_frames):.2f} Hz")
    print(f"Min F0: {np.min(voiced_frames):.2f} Hz | Max F0: {np.max(voiced_frames):.2f} Hz")
else:
    print("No pitch detected (might be silent or purely unvoiced static noise).")
