import time
import sys
sys.path.append("/home/jay/modules")

modules_to_test = [
    "config",
    "trend_discovery",
    "post_filter",
    "script_generator",
    "voiceover",
    "video_assembler",
    "thumbnail_creator",
    "gemini_engine",
    "legal_script_check",
    "visual_fetcher",
    "youtube_uploader",
    "growth_observer",
    "spike_detector"
]

for m in modules_to_test:
    t0 = time.time()
    print(f"Importing {m}...")
    try:
        __import__(m)
        print(f"Imported {m} in {time.time() - t0:.2f}s")
    except Exception as e:
        print(f"Failed to import {m}: {e}")
