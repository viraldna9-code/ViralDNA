import os, sys
sys.path.append("/home/jay/modules")
import config
from trend_discovery import TrendDiscovery
from post_filter import PostFilter
from spike_detector import SpikeDetector

print("Running trend discovery...")
td = TrendDiscovery(config)
raw_news = td.run()

print(f"Discovered {len(raw_news)} raw news items.")
pf = PostFilter(config.POST_FILTER_CONFIG)
sorted_topics = pf.run(raw_news)
print(f"Filtered to {len(sorted_topics)} topics.")

sd = SpikeDetector(config)
result = sd.run(sorted_topics)
print(f"Spike Level: {result['spike_level']}")
print(f"Spike Detected: {result['spike_detected']}")
