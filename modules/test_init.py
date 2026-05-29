import time
import sys
sys.path.append("/home/jay/modules")

import config
from trend_discovery import TrendDiscovery
from post_filter import PostFilter
from script_generator import ScriptGenerator
from voiceover import VoiceoverGenerator
from video_assembler import VideoAssembler
from thumbnail_creator import ThumbnailCreator
from gemini_engine import GeminiEngine
from legal_script_check import LegalScriptCheck
from visual_fetcher import VisualFetcher
from youtube_uploader import YouTubeUploader
from growth_observer import GrowthObserver
from spike_detector import SpikeDetector

print("Testing instantiations:")
t0 = time.time()
print("Instantiating GeminiEngine...")
engine = GeminiEngine()
print(f"GeminiEngine instantiated in {time.time() - t0:.2f}s")

t0 = time.time()
print("Instantiating TrendDiscovery...")
td = TrendDiscovery(config)
print(f"TrendDiscovery instantiated in {time.time() - t0:.2f}s")

t0 = time.time()
print("Instantiating PostFilter...")
pf = PostFilter(config.POST_FILTER_CONFIG)
print(f"PostFilter instantiated in {time.time() - t0:.2f}s")

t0 = time.time()
print("Instantiating ScriptGenerator...")
sg = ScriptGenerator(engine, config.SCRIPT_GENERATION_CONFIG)
print(f"ScriptGenerator instantiated in {time.time() - t0:.2f}s")

t0 = time.time()
print("Instantiating LegalScriptCheck...")
lsc = LegalScriptCheck(engine, config.LEGAL_CONFIG)
print(f"LegalScriptCheck instantiated in {time.time() - t0:.2f}s")

t0 = time.time()
print("Instantiating VoiceoverGenerator...")
vg = VoiceoverGenerator(None, config)
print(f"VoiceoverGenerator instantiated in {time.time() - t0:.2f}s")

t0 = time.time()
print("Instantiating VisualFetcher...")
vf = VisualFetcher(None, config)
print(f"VisualFetcher instantiated in {time.time() - t0:.2f}s")

t0 = time.time()
print("Instantiating ThumbnailCreator...")
tc = ThumbnailCreator(None, config)
print(f"ThumbnailCreator instantiated in {time.time() - t0:.2f}s")

t0 = time.time()
print("Instantiating VideoAssembler...")
va = VideoAssembler(config)
print(f"VideoAssembler instantiated in {time.time() - t0:.2f}s")

t0 = time.time()
print("Instantiating GrowthObserver...")
observer = GrowthObserver()
print(f"GrowthObserver instantiated in {time.time() - t0:.2f}s")
