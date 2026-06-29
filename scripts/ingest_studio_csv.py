#!/usr/bin/env python3
"""
YouTube Studio CSV CTR Ingestion
=================================
Parses a YouTube Studio Analytics CSV export (downloaded as ZIP from
studio.youtube.com → Analytics → Reach → Export) and updates
analytics/ctr_performance_log.json so the edge scorer learns real CTR patterns.

Usage:
  python3 ingest_studio_csv.py path/to/extracted/folder/
  python3 ingest_studio_csv.py path/to/download.zip

The script:
  1. Finds Table data.csv in the provided path
  2. Extracts impressions and CTR per video
  3. Matches titles to existing entries or creates new ones
  4. Updates weights in ctr_performance_log.json
  5. Prints a summary of what was learned
"""

import csv
import json
import os
import re
import sys
import zipfile
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANALYTICS_DIR = os.path.join(PROJECT_ROOT, "analytics")
CTR_LOG_FILE = os.path.join(ANALYTICS_DIR, "ctr_performance_log.json")


def find_csv_path(input_path: str) -> str:
    """Find Table data.csv from a directory or zip file."""
    if input_path.endswith(".zip"):
        with zipfile.ZipFile(input_path) as zf:
            for name in zf.namelist():
                if name.endswith("Table data.csv"):
                    extract_to = os.path.join(PROJECT_ROOT, "_studio_import")
                    os.makedirs(extract_to, exist_ok=True)
                    zf.extract(name, extract_to)
                    # Handle possible UTF-8 BOM / weird encoding
                    csv_path = os.path.join(extract_to, name)
                    # Read and rewrite as clean UTF-8
                    with open(csv_path, "r", encoding="utf-8-sig") as f:
                        content = f.read()
                    clean_path = os.path.join(extract_to, "table_clean.csv")
                    with open(clean_path, "w", encoding="utf-8") as f:
                        f.write(content)
                    return clean_path
        raise FileNotFoundError(f"No 'Table data.csv' found in {input_path}")

    # It's a directory
    for root, dirs, files in os.walk(input_path):
        for f in files:
            if f.endswith("Table data.csv"):
                return os.path.join(root, f)
    raise FileNotFoundError(f"No 'Table data.csv' found in {input_path}")


def parse_studio_csv(csv_path: str) -> list:
    """Parse the Studio CSV and return list of video records."""
    videos = []

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        # Try to detect dialect
        sample = f.read(4096)
        f.seek(0)

        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = "excel"

        reader = csv.DictReader(f, dialect=dialect)

        if not reader.fieldnames:
            print(f"ERROR: CSV has no headers. First 200 chars: {sample[:200]}")
            sys.exit(1)

        # Normalize headers (strip BOM, whitespace)
        reader.fieldnames = [h.strip().lstrip("\ufeff") for h in reader.fieldnames]

        # Find the relevant columns
        title_col = None
        imp_col = None
        ctr_col = None
        views_col = None
        subs_col = None

        for h in reader.fieldnames:
            hl = h.lower()
            if "video" in hl and "title" in hl:
                title_col = h
            elif "impression" in hl and "click" not in hl:
                imp_col = h
            elif "ctr" in hl or ("click-through" in hl and "impression" in hl):
                ctr_col = h
            elif "views" in hl or "view" in hl:
                views_col = h
            elif "subscriber" in hl and "gained" in hl:
                subs_col = h

        if not title_col:
            print(f"ERROR: No 'Video title' column found. Available: {reader.fieldnames}")
            sys.exit(1)
        if not imp_col:
            print(f"ERROR: No 'Impressions' column found. Available: {reader.fieldnames}")
            sys.exit(1)
        if not ctr_col:
            print(f"ERROR: No 'Impressions click-through rate' column found. Available: {reader.fieldnames}")
            sys.exit(1)

        for row in reader:
            title = (row.get(title_col) or "").strip()
            if not title:
                continue

            # Clean numeric fields
            imp_raw = str(row.get(imp_col, "0")).replace(",", "").strip()
            ctr_raw = str(row.get(ctr_col, "0")).replace("%", "").strip()
            views_raw = str(row.get(views_col, "0")).replace(",", "").strip() if views_col else "0"
            subs_raw = str(row.get(subs_col, "0")).replace(",", "").strip() if subs_col else "0"

            try:
                impressions = int(imp_raw)
            except ValueError:
                continue  # skip unparseable rows (like "Total" footer)

            try:
                ctr = float(ctr_raw)
            except ValueError:
                ctr = 0.0

            try:
                views = int(views_raw)
            except ValueError:
                views = 0

            try:
                subs = int(subs_raw)
            except ValueError:
                subs = 0

            # Skip the aggregate "Total" row
            if title.lower() == "total":
                continue

            videos.append({
                "title": title,
                "impressions": impressions,
                "ctr": ctr,
                "views": views,
                "subs_gained": subs,
            })

    return videos


def load_ctr_log() -> dict:
    """Load existing CTR performance log, or return empty structure."""
    if os.path.exists(CTR_LOG_FILE):
        with open(CTR_LOG_FILE) as f:
            return json.load(f)
    return {
        "version": "1.0",
        "last_updated": None,
        "videos": [],
        "learned_weights": {},
        "stats": {},
    }


def save_ctr_log(log: dict):
    """Save CTR performance log."""
    log["last_updated"] = datetime.now().isoformat()
    os.makedirs(os.path.dirname(CTR_LOG_FILE), exist_ok=True)
    with open(CTR_LOG_FILE, "w") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


def fuzzy_match_title(title: str, existing_titles: list) -> int:
    """
    Find index of matching video in existing log.
    Returns -1 if no match.
    Uses normalized comparison (lowercase, strip common suffixes).
    """
    def normalize(s):
        s = s.lower().strip()
        s = re.sub(r"\s*\(20\d{2}\)\s*$", "", s)
        s = re.sub(r"\s*#shorts?\s*$", "", s)
        s = re.sub(r"\s*#telugunews\s*$", "", s)
        s = re.sub(r"\s*\|\s*\S+\s*$", "", s)  # strip trailing | ChannelName
        return s.strip()

    norm_title = normalize(title)
    for i, existing in enumerate(existing_titles):
        if normalize(existing) == norm_title:
            return i
    return -1


def update_weights(log: dict):
    """
    Re-learn feature weights from accumulated data.
    Uses simple correlation: for each feature, compute avg CTR of videos with
    that feature vs without, and weight = (with_ctr - without_ctr).
    """
    videos = log.get("videos", [])
    if len(videos) < 5:
        log["stats"] = {"total_videos": len(videos), "message": "Need 5+ videos to learn weights"}
        return

    # Import feature detection from edge_scorer
    sys.path.insert(0, os.path.join(PROJECT_ROOT, "modules"))
    try:
        from edge_scorer import _detect_ctr_features
    except ImportError:
        log["stats"] = {"total_videos": len(videos), "message": "Could not import edge_scorer"}
        return

    # Only use videos with ≥50 impressions (statistically meaningful CTR)
    meaningful = [v for v in videos if v.get("impressions", 0) >= 50]
    if len(meaningful) < 3:
        meaningful = videos  # fall back to all videos

    feature_stats = {}
    feature_names = [
        "has_rebel_battle", "has_specific_number", "has_specific_person",
        "has_party_name", "has_dramatic_verb", "has_high_stakes",
        "title_over_70_chars", "has_colon_structure",
        "has_generic_latest_news", "has_vague_question",
        "has_cta_suffix", "starts_with_is_are",
    ]

    for feat in feature_names:
        with_feat = [v for v in meaningful if _detect_ctr_features(v["title"]).get(feat)]
        without_feat = [v for v in meaningful if not _detect_ctr_features(v["title"]).get(feat)]

        with_ctr = sum(v["ctr"] for v in with_feat) / len(with_feat) if with_feat else 0
        without_ctr = sum(v["ctr"] for v in without_feat) / len(without_feat) if without_feat else 0

        feature_stats[feat] = {
            "with_avg_ctr": round(with_ctr, 2),
            "without_avg_ctr": round(without_ctr, 2),
            "differential": round(with_ctr - without_ctr, 2),
            "with_count": len(with_feat),
            "without_count": len(without_feat),
        }

    # Convert differentials to weights (normalize to [-0.2, 0.2] range)
    # But only update weights when we have enough data (≥20 meaningful videos)
    # Otherwise keep the manually-derived priors which are more robust
    meaningful_count = len(meaningful)
    min_count = 20

    max_diff = max(abs(s["differential"]) for s in feature_stats.values()) or 1
    learned_weights = {}
    for feat, stats in feature_stats.items():
        # Weight = differential scaled to max 0.2, min -0.2
        weight = round((stats["differential"] / max_diff) * 0.2, 3)
        learned_weights[feat] = weight

    # Blend: if < min_count videos, keep priors (don't overwrite with noisy data)
    if meaningful_count < min_count:
        learned_weights = {}  # signal to keep priors

    log["learned_weights"] = learned_weights
    log["stats"] = {
        "total_videos": len(videos),
        "meaningful_videos": len(meaningful),
        "avg_ctr": round(sum(v["ctr"] for v in meaningful) / len(meaningful), 2) if meaningful else 0,
        "max_ctr": round(max(v["ctr"] for v in meaningful), 2) if meaningful else 0,
        "weight_source": (
            "learned_from_data" if meaningful_count >= min_count else "priors_only"
        ),
        "feature_stats": feature_stats,
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 ingest_studio_csv.py <path_to_csv_or_zip_or_dir>")
        print("")
        print("Examples:")
        print("  python3 ingest_studio_csv.py /tmp/c_extracted/")
        print("  python3 ingest_studio_csv.py ~/Downloads/c.zip")
        print("  python3 ingest_studio_csv.py /mnt/c/Users/sudha/Downloads/studio_export.zip")
        sys.exit(1)

    input_path = sys.argv[1]
    if not os.path.exists(input_path):
        print(f"ERROR: Path not found: {input_path}")
        sys.exit(1)

    # Find the CSV
    print(f"Looking for Studio CSV in: {input_path}")
    csv_path = find_csv_path(input_path)
    print(f"Found: {csv_path}")

    # Parse
    videos = parse_studio_csv(csv_path)
    if not videos:
        print("ERROR: No video data found in CSV")
        sys.exit(1)
    print(f"Parsed {len(videos)} videos from CSV")

    # Load existing log
    log = load_ctr_log()
    existing_titles = [v["title"] for v in log.get("videos", [])]

    # Merge: update existing or add new
    added = 0
    updated = 0
    for v in videos:
        idx = fuzzy_match_title(v["title"], existing_titles)
        if idx >= 0:
            # Update existing entry (keep the higher impression count — more recent data)
            existing = log["videos"][idx]
            if v["impressions"] > existing.get("impressions", 0):
                existing["impressions"] = v["impressions"]
                existing["ctr"] = v["ctr"]
                existing["views"] = v["views"]
                existing["subs_gained"] = v["subs_gained"]
                existing["last_seen"] = datetime.now().isoformat()
                updated += 1
            else:
                # Still update CTR if same period (YouTube revises data)
                existing["ctr"] = v["ctr"]
                existing["views"] = v["views"]
                updated += 1
        else:
            v["last_seen"] = datetime.now().isoformat()
            log.setdefault("videos", []).append(v)
            existing_titles.append(v["title"])
            added += 1

    # Re-learn weights from accumulated data
    update_weights(log)

    # Save
    save_ctr_log(log)

    # Print summary
    stats = log.get("stats", {})
    print(f"\n{'=' * 60}")
    print(f"CTR PERFORMANCE LOG UPDATED")
    print(f"{'=' * 60}")
    print(f"  Videos added:   {added}")
    print(f"  Videos updated: {updated}")
    print(f"  Total tracked:  {stats.get('total_videos', 0)}")
    print(f"  Avg CTR (≥50 imp): {stats.get('avg_ctr', 0)}%")
    print(f"  Max CTR:        {stats.get('max_ctr', 0)}%")

    if log.get("learned_weights"):
        print(f"\n  LEARNED WEIGHTS (from real data):")
        for feat, weight in sorted(log["learned_weights"].items(), key=lambda x: abs(x[1]), reverse=True):
            direction = "+" if weight > 0 else ""
            print(f"    {feat:<30} {direction}{weight:.3f}")

    print(f"\n  Saved to: {CTR_LOG_FILE}")


if __name__ == "__main__":
    main()
