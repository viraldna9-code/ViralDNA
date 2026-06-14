#!/usr/bin/env python3
"""Test v87.2 image relevance - full flow simulation."""
import sys, os
sys.path.insert(0, '/home/jay/ViralDNA/modules')
os.chdir('/home/jay/ViralDNA')

from news_image_fetcher import _keyword_overlap, _text_only_relevance_check, _visual_relevance_check

topic = "Another jolt to TMC, party MP Sushmita Dev resigns from Rajya Sabha"

test_cases = [
    # (article_title, expected_result, reason)
    ("TMC's Sushmita Dev Quits Party and Rajya Sabha, Me", True, "3-word overlap: tmc, sushmita, rajya"),
    ("Another Blow To TMC: Sushmita Dev Resigns As Rajya", True, "3-word overlap: another, tmc, sushmita"),
    ("Sushmita Dev's Fi", False, "only 1 meaningful word: sushmita"),
    ("Rajya Sabha polls: Congress delegation meets ECI", True, "2-word overlap: rajya, sabha -> borderline, Gemini decides"),
    ("Sanjiv Goenka Exclusive: He's The Best PM", False, "0 overlap"),
    ("Shreyas Iyer's father's viral celebration sparks buzz", False, "0 overlap"),
    ("India Today: Latest News Update", False, "all generic words"),
]

print("=== v87.2 Image Relevance Tests ===\n")
all_pass = True
for title, expected, reason in test_cases:
    overlap = _keyword_overlap(topic, title)
    text_ok = _text_only_relevance_check(title, topic)
    
    # Simulate the 3-tier check
    GENERIC = {"india", "us", "usa", "news", "live", "update", "breaking", "latest",
               "top", "watch", "video", "photo", "photos", "gallery", "pictures",
               "report", "reports", "said", "says", "new", "first", "last", "one",
               "two", "three", "day", "days", "week", "month", "year", "today",
               "yesterday", "tomorrow", "gets", "get", "got", "give", "given",
               "after", "before", "over", "under", "from", "with", "into", "out",
               "off", "up", "down", "the", "a", "an", "and", "or", "but", "for",
               "not", "all", "any", "can", "has", "had", "have", "was", "were",
               "been", "being", "are", "is", "it", "its", "this", "that", "these",
               "those", "what", "which", "who", "how", "when", "where", "why",
               "will", "would", "could", "should", "may", "might", "more", "most",
               "some", "such", "than", "then", "there", "their", "them", "they",
               "about", "also", "just", "only", "very", "much", "many", "well",
               "back", "even", "still", "already", "since", "while", "during",
               "between", "through", "across"}
    filtered = {w for w in overlap if w.lower() not in GENERIC}
    
    if len(filtered) < 2:
        result = False  # Tier 1 reject
        tier = "T1-reject"
    elif len(filtered) >= 3:
        result = True   # Tier 1.5 bypass
        tier = "T1.5-bypass"
    else:
        result = True   # Tier 2 — would call Gemini, but we accept
        tier = "T2-accept"
    
    status = "PASS" if result == expected else "FAIL"
    if status == "FAIL":
        all_pass = False
    print(f"  [{status}] {tier:12} | {str(result):5} (exp {str(expected):5}) | {title[:55]}")
    print(f"         overlap={overlap} filtered={filtered}")
    print(f"         {reason}")
    print()

print(f"{'ALL PASS' if all_pass else 'SOME FAILED'}")
