# VERSION: 1.0
# MODULE: competitor_intelligence.py
# PURPOSE: Reverse-engineer successful videos in a niche to identify patterns,
#          saturation levels, and content gaps.
# Data source: YouTube Data API v3 (search.list + videos.list)

import json
import os
import re
import sys
import time
import urllib.request
import urllib.parse
from collections import Counter
from datetime import datetime


CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "vdna")
CACHE_FILE = os.path.join(CACHE_DIR, "competitor_cache.json")
CACHE_TTL = 4 * 3600
MAX_SEARCHES_PER_DAY = 5
QUOTA_FILE = os.path.join(CACHE_DIR, "yt_quota.json")

EMOTIONAL_TRIGGERS = {
    "curiosity": ["why", "how", "secret", "hidden", "truth", "revealed", "explained", "nobody tells", "mystery"],
    "fear": ["danger", "warning", "crisis", "threat", "risk", "emergency", "ban", "arrest", "scam", "fraud"],
    "controversy": ["vs", "battle", "war", "clash", "exposed", "scandal", "protest", "rebel", "corruption", "fake"],
    "urgency": ["breaking", "urgent", "just", "now", "happening", "alert", "immediately", "today", "update"],
    "inspiration": ["success", "triumph", "hero", "saved", "rescued", "miracle", "incredible", "amazing", "win"],
    "shock": ["shocking", "unbelievable", "insane", "crazy", "wild", "massive", "devastating", "horrific"],
}


def _load_quota():
    if os.path.exists(QUOTA_FILE):
        try:
            with open(QUOTA_FILE) as f:
                data = json.load(f)
            if data.get("date") != datetime.now().strftime("%Y-%m-%d"):
                return {"date": datetime.now().strftime("%Y-%m-%d"), "units": 0}
            return data
        except Exception:
            pass
    return {"date": datetime.now().strftime("%Y-%m-%d"), "units": 0}


def _save_quota(t):
    os.makedirs(CACHE_DIR, exist_ok=True)
    try:
        with open(QUOTA_FILE, "w") as f:
            json.dump(t, f)
    except Exception:
        pass


def _can_search():
    return _load_quota().get("units", 0) < MAX_SEARCHES_PER_DAY * 100


def _record_search():
    t = _load_quota()
    t["units"] = t.get("units", 0) + 100
    _save_quota(t)


def _get_api_key():
    key = os.environ.get("YOUTUBE_DATA_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if key:
        return key
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from config import QUOTA_CONFIG
        k = QUOTA_CONFIG.get("youtube_data_api", {}).get("api_key", "")
        if k and k != "YOUR_API_KEY_HERE":
            return k
    except Exception:
        pass
    return None


def _yt_search(query, max_results=20):
    api_key = _get_api_key()
    if not api_key or not _can_search():
        return []
    try:
        params = urllib.parse.urlencode({
            "part": "snippet", "q": query, "type": "video",
            "order": "viewCount", "maxResults": min(max_results, 50), "key": api_key,
        })
        url = "https://www.googleapis.com/youtube/v3/search?" + params
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        _record_search()
        results = []
        for item in data.get("items", []):
            s = item.get("snippet", {})
            results.append({
                "video_id": item.get("id", {}).get("videoId", ""),
                "title": s.get("title", ""),
                "channel": s.get("channelTitle", ""),
            })
        return results
    except Exception:
        return []


def _yt_stats(video_ids):
    api_key = _get_api_key()
    if not api_key or not video_ids:
        return {}
    try:
        all_s = {}
        for i in range(0, len(video_ids), 50):
            batch = video_ids[i:i+50]
            params = urllib.parse.urlencode({
                "part": "statistics", "id": ",".join(batch), "key": api_key,
            })
            url = "https://www.googleapis.com/youtube/v3/videos?" + params
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            for item in data.get("items", []):
                st = item.get("statistics", {})
                all_s[item.get("id", "")] = {
                    "views": int(st.get("viewCount", 0)),
                    "likes": int(st.get("likeCount", 0)),
                }
        return all_s
    except Exception:
        return {}


def _cache_load():
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _cache_save(cache):
    os.makedirs(CACHE_DIR, exist_ok=True)
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2)
    except Exception:
        pass


def _cache_get(query):
    entry = _cache_load().get(query.lower().strip())
    if entry and (time.time() - entry.get("_ts", 0)) < CACHE_TTL:
        return entry
    return None


def _cache_set(query, data):
    cache = _cache_load()
    data["_ts"] = time.time()
    cache[query.lower().strip()] = data
    _cache_save(cache)


def _detect_emotions(title):
    tl = title.lower()
    return [t for t, kws in EMOTIONAL_TRIGGERS.items() if any(k in tl for k in kws)]


def _detect_structure(title):
    pats = {
        "question": r"^(what|why|how|when|where|who|is|are|can|do|does|will|did)\b",
        "listicle": r"^\d+\s",
        "vs": r"\bvs\.?\b",
        "curiosity": r"\?|!.{0,3}$",
        "number": r"\b\d+\b",
    }
    found = [n for n, p in pats.items() if re.search(p, title, re.IGNORECASE)]
    if _detect_emotions(title):
        found.append("emotional")
    return found


def _view_tiers(views):
    if not views:
        return {"viral": 0, "high": 0, "mid": 0, "low": 0}
    sv = sorted(views, reverse=True)
    n = len(sv)
    p75 = sv[max(0, n // 4)]
    p50 = sv[max(0, n // 2)]
    return {
        "viral": sum(1 for v in views if v >= p75 * 2),
        "high": sum(1 for v in views if p75 <= v < p75 * 2),
        "mid": sum(1 for v in views if p50 <= v < p75),
        "low": sum(1 for v in views if v < p50),
        "median": p50, "max": sv[0] if sv else 0, "avg": sum(views) // len(views) if views else 0,
    }


def search_competitor_videos(keyword, max_results=20):
    cached = _cache_get(keyword)
    if cached:
        cached["source"] = "cache"
        return cached
    if not _can_search():
        return {"keyword": keyword, "n": 0, "videos": [], "saturation": 0.5, "source": "unavailable", "reason": "quota"}
    results = _yt_search(keyword, max_results)
    if not results:
        return {"keyword": keyword, "n": 0, "videos": [], "saturation": 0.5, "source": "unavailable", "reason": "no_results"}
    vids = [r["video_id"] for r in results if r["video_id"]]
    stats = _yt_stats(vids)
    ec = Counter()
    sc = Counter()
    cc = Counter()
    views_list = []
    videos = []
    for r in results:
        vid = r["video_id"]
        v = stats.get(vid, {}).get("views", 0)
        views_list.append(v)
        em = _detect_emotions(r["title"])
        st = _detect_structure(r["title"])
        for e in em:
            ec[e] += 1
        for s in st:
            sc[s] += 1
        cc[r["channel"]] += 1
        videos.append({"video_id": vid, "title": r["title"], "channel": r["channel"], "views": v, "emotions": em, "structures": st})
    vd = _view_tiers(views_list)
    n = len(videos)
    if n > 0 and vd.get("median", 0) > 0:
        sat = min(1.0, (vd["viral"] + vd["high"]) / n * 0.7 + (n / max(max_results, 1)) * 0.3)
    else:
        sat = 0.5
    output = {
        "keyword": keyword, "n": n, "videos": videos[:10],
        "view_distribution": vd, "top_emotions": ec.most_common(5),
        "top_structures": sc.most_common(5), "top_channels": cc.most_common(5),
        "saturation": round(sat, 2), "source": "live",
    }
    _cache_set(keyword, output)
    return output


def score_opportunity(keyword, our_avg_views=0):
    a = search_competitor_videos(keyword)
    if a["source"] == "unavailable":
        return {"keyword": keyword, "score": 50, "rec": "insufficient_data", "analysis": a}
    score = 0
    reasons = []
    sat = a.get("saturation", 0.5)
    if sat < 0.3:
        score += 40
        reasons.append("low_saturation")
    elif sat < 0.5:
        score += 25
        reasons.append("moderate_saturation")
    elif sat < 0.7:
        score += 10
        reasons.append("high_saturation")
    else:
        reasons.append("very_saturated")
    med = a.get("view_distribution", {}).get("median", 0)
    if our_avg_views > 0 and med > our_avg_views * 2:
        score += 30
        reasons.append("high_ceiling")
    elif med > 0:
        score += 15
        reasons.append("some_ceiling")
    if a.get("top_emotions"):
        score += 15
        reasons.append("emotional_hooks")
    if len(a.get("top_structures", [])) >= 2:
        score += 15
        reasons.append("structure_diversity")
    try:
        from keyword_research import get_search_volume
        sv = get_search_volume(keyword)
        if sv.get("traffic_score", 0) > 50000:
            score += 20
            reasons.append("high_search_volume")
        elif sv.get("traffic_score", 0) > 10000:
            score += 10
            reasons.append("moderate_search_volume")
    except Exception:
        pass
    if score >= 70:
        rec = "high_potential"
    elif score >= 50:
        rec = "moderate_potential"
    elif score >= 30:
        rec = "challenging"
    else:
        rec = "avoid"
    return {"keyword": keyword, "score": min(100, score), "rec": rec, "reasons": reasons, "analysis": a}


def get_content_gaps(keyword):
    a = search_competitor_videos(keyword)
    if a["source"] == "unavailable":
        return []
    gaps = []
    used_e = {t for t, _ in a.get("top_emotions", [])}
    used_s = {s for s, _ in a.get("top_structures", [])}
    for tr in set(EMOTIONAL_TRIGGERS.keys()) - used_e:
        gaps.append({"type": "emotion", "desc": "No top videos use " + tr + " angle", "potential": "medium"})
    for st in {"question", "listicle", "vs", "curiosity"} - used_s:
        gaps.append({"type": "structure", "desc": "Few top videos use " + st + " format", "potential": "medium"})
    return gaps


if __name__ == "__main__":
    kw = sys.argv[1] if len(sys.argv) > 1 else "west bengal news"
    r = search_competitor_videos(kw)
    print("Source:", r["source"], "Videos:", r["n"], "Saturation:", r.get("saturation", "N/A"))
    if r.get("videos"):
        for v in r["videos"][:3]:
            print("  [{:,}] {}".format(v["views"], v["title"][:60]))
