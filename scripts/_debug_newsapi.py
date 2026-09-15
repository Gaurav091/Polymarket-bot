"""Debug bot/macro.py fetch_newsapi_headlines."""
import sys, logging
sys.path.insert(0, ".")
logging.basicConfig(level=logging.DEBUG)

from bot import config
print(f"NEWS_API_KEY: {config.NEWS_API_KEY[:8]}..." if config.NEWS_API_KEY else "NEWS_API_KEY: EMPTY")

import requests
r = requests.get(
    "https://eventregistry.org/api/v1/article/getArticles",
    params={
        "keyword": "bitcoin OR crypto OR prediction market OR federal reserve",
        "resultType": "articles",
        "articlesSortBy": "date",
        "articlesCount": 5,
        "lang": "eng",
        "apiKey": config.NEWS_API_KEY,
    },
    timeout=12, verify=False,
)
print(f"Status: {r.status_code}")
data = r.json()
raw = data.get("articles", {}).get("results", [])
print(f"Raw articles: {len(raw)}")
if raw:
    for a in raw[:3]:
        print(f"  - {a.get('title', '?')[:80]}")
else:
    print(f"Full response keys: {list(data.keys())}")
    print(f"Response snippet: {str(data)[:500]}")
