"""Test newsapi.ai with correct query syntax."""
import os
import requests, json

API_KEY = os.getenv("NEWS_API_KEY", "")
BASE = "https://eventregistry.org/api/v1"

# Test 1: single keyword
print("=== Single keyword 'bitcoin' ===")
r = requests.get(f"{BASE}/article/getArticles", params={
    "keyword": "bitcoin",
    "apiKey": API_KEY,
    "resultType": "articles",
    "articlesSortBy": "date",
    "articlesCount": 3,
    "lang": "eng",
}, timeout=15, verify=False)
d = r.json()
total = d.get("articles", {}).get("totalResults", 0)
results = d.get("articles", {}).get("results", [])
print(f"  Total: {total}, returned: {len(results)}")
for a in results:
    print(f"  - {a.get('title', '?')[:80]}")

# Test 2: multiple keywords as separate param values
print("\n=== Multiple keywords as list ===")
r = requests.get(f"{BASE}/article/getArticles", params={
    "keywordList": "bitcoin,prediction market",
    "apiKey": API_KEY,
    "resultType": "articles",
    "articlesSortBy": "date",
    "articlesCount": 3,
    "lang": "eng",
}, timeout=15, verify=False)
d = r.json()
total = d.get("articles", {}).get("totalResults", 0)
results = d.get("articles", {}).get("results", [])
print(f"  Total: {total}, returned: {len(results)}")
for a in results:
    print(f"  - {a.get('title', '?')[:80]}")

# Test 3: OR query using correct Event Registry syntax
print("\n=== OR query with '|' separator ===")
r = requests.get(f"{BASE}/article/getArticles", params={
    "keyword": "bitcoin|crypto|prediction market|federal reserve",
    "apiKey": API_KEY,
    "resultType": "articles",
    "articlesSortBy": "date",
    "articlesCount": 3,
    "lang": "eng",
}, timeout=15, verify=False)
d = r.json()
total = d.get("articles", {}).get("totalResults", 0)
results = d.get("articles", {}).get("results", [])
print(f"  Total: {total}, returned: {len(results)}")
for a in results:
    print(f"  - {a.get('title', '?')[:80]}")

# Test 4: sourceUri for Polymarket-specific news
print("\n=== sourceUri 'polymarket.com' ===")
r = requests.get(f"{BASE}/article/getArticles", params={
    "sourceUri": "polymarket.com",
    "apiKey": API_KEY,
    "resultType": "articles",
    "articlesSortBy": "date",
    "articlesCount": 3,
    "lang": "eng",
}, timeout=15, verify=False)
d = r.json()
total = d.get("articles", {}).get("totalResults", 0)
results = d.get("articles", {}).get("results", [])
print(f"  Total: {total}, returned: {len(results)}")
for a in results:
    print(f"  - {a.get('title', '?')[:80]}")

# Test 5: conceptUri for bitcoin via Wikipedia
print("\n=== conceptUri bitcoin ===")
r = requests.get(f"{BASE}/article/getArticles", params={
    "conceptUri": "https://en.wikipedia.org/wiki/Bitcoin",
    "apiKey": API_KEY,
    "resultType": "articles",
    "articlesSortBy": "date",
    "articlesCount": 3,
    "lang": "eng",
}, timeout=15, verify=False)
d = r.json()
total = d.get("articles", {}).get("totalResults", 0)
results = d.get("articles", {}).get("results", [])
print(f"  Total: {total}, returned: {len(results)}")
for a in results:
    print(f"  - {a.get('title', '?')[:80]}")

# Test 6: concepts list
print("\n=== conceptUri list (bitcoin+crypto) ===")
r = requests.get(f"{BASE}/article/getArticles", params={
    "conceptUri": "https://en.wikipedia.org/wiki/Bitcoin,https://en.wikipedia.org/wiki/Cryptocurrency",
    "apiKey": API_KEY,
    "resultType": "articles",
    "articlesSortBy": "date",
    "articlesCount": 3,
    "lang": "eng",
}, timeout=15, verify=False)
d = r.json()
total = d.get("articles", {}).get("totalResults", 0)
results = d.get("articles", {}).get("results", [])
print(f"  Total: {total}, returned: {len(results)}")
for a in results:
    print(f"  - {a.get('title', '?')[:80]}")
