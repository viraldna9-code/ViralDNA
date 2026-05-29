import os, json, re, time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from collections import deque
import importlib # Explicitly for reload

import config

class SpikeDetector:
    def __init__(self, config_instance=config):
        self.config = config_instance
        # Default spike detection values since it might be missing from config
        self.spike_config = getattr(self.config, "TOPIC_DISCOVERY_CONFIG", {}).get("spike_detection", {})
        if not self.spike_config:
            # fallback defaults
            self.spike_config = {
                "max_history_days": 7,
                "rolling_window_hours": 24,
                "rolling_window_maxlen_multiplier": 2,
                "spike_threshold_moderate": 3.0,
                "spike_threshold_urgent": 5.0,
                "min_mentions_for_spike": 5,
                "min_topics_for_storm": 3,
                "fresh_topic_spike_multiplier": 2,
                "avg_mentions_min_history_hours_ratio": 0.5
            }

        self.history_file = os.path.join(self.config.DRIVE["CACHE"], self.spike_config.get("history_filename", "spike_history.json"))
        self.max_history_days = self.spike_config.get("max_history_days", 7)
        self.rolling_window_hours = self.spike_config.get("rolling_window_hours", 24)
        self.rolling_window_maxlen_multiplier = self.spike_config.get("rolling_window_maxlen_multiplier", 2)
        self.spike_threshold_moderate = self.spike_config.get("spike_threshold_moderate", 3.0)
        self.spike_threshold_urgent = self.spike_config.get("spike_threshold_urgent", 5.0)
        self.min_mentions_for_spike = self.spike_config.get("min_mentions_for_spike", 5)
        self.min_topics_for_storm = self.spike_config.get("min_topics_for_storm", 3)
        self.urgent_slots_config = self.spike_config.get("urgent_slots_config", {
            "SLOT_1": {"priority": 1, "type": "main"},
            "SLOT_2": {"priority": 2, "type": "short"},
            "SLOT_3": {"priority": 3, "type": "short"},
        })
        self.fresh_topic_spike_multiplier = self.spike_config.get("fresh_topic_spike_multiplier", 2)
        self.avg_mentions_min_history_hours_ratio = self.spike_config.get("avg_mentions_min_history_hours_ratio", 0.5)
        self.ist_timezone = getattr(self.config, "IST", ZoneInfo("Asia/Kolkata"))

        self.history = self._load_history()

    def _load_history(self) -> dict:
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    loaded_history = {}
                    for topic_title, entries_list in data.items():
                        loaded_entries = []
                        for entry in entries_list:
                            if isinstance(entry, dict) and "timestamp" in entry:
                                try:
                                    entry["timestamp"] = datetime.fromisoformat(entry["timestamp"]).astimezone(self.ist_timezone)
                                    loaded_entries.append(entry)
                                except ValueError:
                                    continue
                        if loaded_entries:
                            loaded_history[topic_title] = deque(loaded_entries, maxlen=self.rolling_window_hours * self.rolling_window_maxlen_multiplier)
                    return loaded_history
            except Exception as e:
                print(f"  ⚠️  SpikeDetector: History load failed ({e}). Starting fresh.")
                return {}
        return {}

    def _save_history(self):
        cutoff = datetime.now(self.ist_timezone) - timedelta(days=self.max_history_days)
        cleaned_history_for_save = {}
        for topic, entries_deque in self.history.items():
            cleaned_entries = [
                {"timestamp": e["timestamp"].isoformat(), "mentions": e["mentions"]}
                for e in entries_deque if e["timestamp"] > cutoff
            ]
            if cleaned_entries:
                cleaned_history_for_save[topic] = cleaned_entries
        
        os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(cleaned_history_for_save, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"  ❌ SpikeDetector: History save failed: {e}.")

    def _update_history_with_current_topics(self, current_topics: list):
        now = datetime.now(self.ist_timezone)
        for topic in current_topics:
            title = topic.get("title", "")
            mentions = topic.get("num_sources", 1) # fallback to 1 source
            if not title:
                continue

            if title not in self.history:
                self.history[title] = deque(maxlen=self.rolling_window_hours * self.rolling_window_maxlen_multiplier)
            
            self.history[title].append({"timestamp": now, "mentions": mentions})
            cutoff = now - timedelta(hours=self.rolling_window_hours)
            self.history[title] = deque([e for e in self.history[title] if e["timestamp"] > cutoff], 
                                         maxlen=self.rolling_window_hours * self.rolling_window_maxlen_multiplier)

    def _calculate_average_mentions(self, topic_title: str) -> float:
        entries = self.history.get(topic_title, deque())
        if not entries:
            return 0.0
        
        total_mentions = sum(e["mentions"] for e in entries)
        if len(entries) > 1:
            total_history_duration_seconds = (entries[-1]["timestamp"] - entries[0]["timestamp"]).total_seconds()
            total_history_duration_hours = total_history_duration_seconds / 3600
        else:
            total_history_duration_hours = 0.0

        if total_history_duration_hours < (self.rolling_window_hours * self.avg_mentions_min_history_hours_ratio):
            return total_mentions / max(1, len(entries))
        
        return total_mentions / max(1.0, total_history_duration_hours) 

    def run(self, all_topics: list) -> dict:
        print("  ⚡️ Spike Detector: Running...")
        self._update_history_with_current_topics(all_topics)
        self._save_history()

        spike_level = "NONE"
        max_jump = 0.0
        spiked_topics_details = []
        urgent_topics_for_slots = []

        for topic in all_topics:
            title = topic.get("title", "")
            mentions_current = topic.get("num_sources", 1)
            
            if not title:
                continue

            avg_mentions = self._calculate_average_mentions(title)
            
            jump_ratio = 1.0
            if avg_mentions == 0:
                if mentions_current >= self.min_mentions_for_spike:
                    jump_ratio = self.spike_threshold_moderate + 0.1
            else:
                jump_ratio = mentions_current / avg_mentions

            current_topic_level = "NONE"
            if jump_ratio >= self.spike_threshold_urgent:
                current_topic_level = "URGENT"
                urgent_topics_for_slots.append(topic)
                max_jump = max(max_jump, jump_ratio)
            elif jump_ratio >= self.spike_threshold_moderate:
                current_topic_level = "MODERATE"
                max_jump = max(max_jump, jump_ratio)

            if current_topic_level != "NONE":
                 spiked_topics_details.append({
                     "title": topic.get("title", ""),
                     "jump_ratio": round(jump_ratio, 2),
                     "mentions_current": mentions_current,
                     "avg_mentions": round(avg_mentions, 2),
                     "level": current_topic_level,
                     "topic_full_data": topic
                 })

        if len(urgent_topics_for_slots) >= self.min_topics_for_storm:
            spike_level = "STORM"
            print(f"    🔴 STORM DETECTED: {len(urgent_topics_for_slots)} urgent topics!")
        elif len(urgent_topics_for_slots) > 0:
            spike_level = "URGENT"
            print(f"    🔴 URGENT SPIKE DETECTED: {len(urgent_topics_for_slots)} urgent topics!")
        elif any(t["level"] == "MODERATE" for t in spiked_topics_details):
            spike_level = "MODERATE"
            print(f"    🟡 MODERATE SPIKE DETECTED.")
        else:
            print(f"    🟢 No significant spike detected.")
            
        slot_assignments = {}
        if spike_level in ("URGENT", "STORM"):
            sort_keys = ["viral_score", "jump_ratio"]
            
            def _sort_func(t):
                return tuple(t.get(key, 0) for key in sort_keys)

            urgent_topics_for_slots.sort(key=_sort_func, reverse=True)
            
            for sk_name, sk_cfg in self.urgent_slots_config.items():
                if urgent_topics_for_slots:
                    slot_assignments[sk_name] = urgent_topics_for_slots.pop(0)
                    print(f"      📌 Assigned {sk_name}: {slot_assignments[sk_name].get('title', '')[:40]}...")
                else:
                    print(f"      ⚠️  No more urgent topics to fill {sk_name}.")
            
            if urgent_topics_for_slots:
                slot_assignments["extra_slots"] = urgent_topics_for_slots

        result = {
            "spike_detected": spike_level != "NONE",
            "spike_level": spike_level,
            "max_jump": round(max_jump, 2),
            "spiked_topics": spiked_topics_details,
            "all_topics_for_selection": all_topics,
            **slot_assignments
        }
        
        print(f"  ✅ Spike Detector completed. Level: {spike_level}, Max Jump: {max_jump:.1f}")
        return result
