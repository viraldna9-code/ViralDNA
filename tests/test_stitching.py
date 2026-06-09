import asyncio
import edge_tts
import os
import subprocess
import re

def segment_bilingual_text(text: str):
    pattern = re.compile(r'([\u0c00-\u0c7f]+(?:[\s,\.\-\"\'](?:[\u0c00-\u0c7f]+))*)')
    segments = []
    last_idx = 0
    for match in pattern.finditer(text):
        start, end = match.span()
        if start > last_idx:
            eng_text = text[last_idx:start]
            if eng_text.strip():
                segments.append({"lang": "en", "text": eng_text})
        te_text = match.group(0)
        if te_text.strip():
            segments.append({"lang": "te", "text": te_text})
        last_idx = end
    if last_idx < len(text):
        eng_text = text[last_idx:]
        if eng_text.strip():
            segments.append({"lang": "en", "text": eng_text})
    return segments

async def synthesize_segment(text: str, voice: str, rate: str, pitch: str, output_path: str):
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(output_path)

async def amain():
    text = "Today, the Chief Minister of ఆంధ్ర ప్రదేశ్ announced a new welfare scheme. This will help millions of farmers in తెలంగాణ region."
    segments = segment_bilingual_text(text)
    
    print("Segments:")
    for s in segments:
        print(f"  [{s['lang'].upper()}]: {s['text']}")
        
    temp_files = []
    tasks = []
    
    for idx, s in enumerate(segments):
        temp_path = f"/home/jay/modules/temp_seg_{idx}.mp3"
        temp_files.append(temp_path)
        
        # Choose voice and parameters based on language
        if s["lang"] == "en":
            voice = "en-IN-PrabhatNeural"
            rate = "-6%"
            pitch = "-5Hz"
        else:
            voice = "te-IN-MohanNeural"
            rate = "-3%"
            pitch = "-4Hz"
            
        print(f"Synthesizing segment {idx} ({s['lang']}) using {voice}...")
        tasks.append(synthesize_segment(s["text"], voice, rate, pitch, temp_path))
        
    await asyncio.gather(*tasks)
    print("All segments synthesized successfully.")
    
    # Write concat list file
    list_path = "/home/jay/modules/concat_list.txt"
    with open(list_path, "w") as f:
        for tf in temp_files:
            # Escape path for FFmpeg concat demuxer
            safe_tf = tf.replace("'", "'\\''")
            f.write(f"file '{safe_tf}'\n")
            
    # Concatenate using FFmpeg
    output_path = "/home/jay/modules/test_stitched_out.mp3"
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", list_path,
        "-c", "copy",
        output_path
    ]
    
    print("Running FFmpeg concat...")
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode == 0:
        print(f"Concatenation successful! Output saved to: {output_path}")
        print("Output file size:", os.path.getsize(output_path))
    else:
        print("FFmpeg error:", res.stderr)
        
    # Master using the custom DSP chain
    mastered_path = "/home/jay/modules/test_stitched_mastered.mp3"
    mastering_filters = "highpass=f=80,equalizer=f=120:t=o:w=1:g=2.5,equalizer=f=4500:t=o:w=1:g=1.5,acompressor=threshold=-12dB:ratio=3:attack=5:release=50:makeup=3,alimiter=limit=-1.0dB"
    master_cmd = [
        "ffmpeg", "-y",
        "-i", output_path,
        "-af", mastering_filters,
        "-c:a", "libmp3lame", "-b:a", "192k",
        mastered_path
    ]
    print("Running FFmpeg master...")
    res_master = subprocess.run(master_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res_master.returncode == 0:
        print(f"Mastering successful! Output saved to: {mastered_path}")
        print("Mastered file size:", os.path.getsize(mastered_path))
    else:
        print("FFmpeg mastering error:", res_master.stderr)
        
    # Clean up temp files
    for tf in temp_files:
        if os.path.exists(tf):
            os.remove(tf)
    if os.path.exists(list_path):
        os.remove(list_path)

if __name__ == "__main__":
    asyncio.run(amain())
