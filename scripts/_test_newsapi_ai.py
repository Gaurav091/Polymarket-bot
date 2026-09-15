"""Test newsapi.ai key against their API."""
import os
import requests, json

API_KEY = os.getenv("NEWS_API_KEY", "")
BASE = "https://eventregistry.org/api/v1"

# Test 1: article search
print("=== newsapi.ai article search ===")
r = requests.get(f"{BASE}/article/getArticles", params={
    "keyword": "bitcoin",
    "apiKey": API_KEY,
    "resultType": "articles",
    "articlesSortBy": "date",
    "articlesCount": 3,
    "lang": "eng",
}, timeout=15, verify=False)
print(f"Status: {r.status_code}")
if r.ok:
    d = r.json()
    total = d.get("articles", {}).get("totalResults", 0)
    results = d.get("articles", {}).get("results", [])
    print(f"Total results: {total}")
    for a in results:
        print(f"  - {a.get('title', '?')[:80]}")
else:
    print(r.text[:300])

# Test 2: event search
print("\n=== newsapi.ai event search ===")
r2 = requests.get(f"{BASE}/event/getEvents", params={
    "keyword": "crypto",
    "apiKey": API_KEY,
    "resultType": "events",
    "eventsSortBy": "date",
    "eventsCount": 3,
    "lang": "eng",
}, timeout=15, verify=False)
print(f"Status: {r2.status_code}")
if r2.ok:
    d2 = r2.json()
    total2 = d2.get("events", {}).get("totalResults", 0)
    results2 = d2.get("events", {}).get("results", [])
    print(f"Total events: {total2}")
    for e in results2:
        print(f"  - {e.get('title', '?')[:80]}")
else:
    print(r2.text[:300])

# Test 3: broader concept search
print("\n=== newsapi.ai concept search ===")
r3 = requests.get(f"{BASE}/article/getArticles", params={
    "conceptUri": "https://en.wikipedia.org/wiki/Bitcoin",
    "apiKey": API_KEY,
    "resultType": "articles",
    "articlesSortBy": "date",
    "articlesCount": 3,
    "lang": "eng",
}, timeout=15, verify=False)
print(f"Status: {r3.status_code}")
if r3.ok:
    d3 = r3.json()
    total3 = d3.get("articles", {}).get("totalResults", 0)
    results3 = d3.get("articles", {}).get("results", [])
    print(f"Total results: {total3}")
    for a in results3:
        print(f"  - {a.get('title', '?')[:80]}")
else:
    print(r3.text[:300])

print("\n=== RESULT ===")
print("Key is VALID for newsapi.ai" if r.status_code == 200 else "Key INVALID")
