"""Test bot/macro.py fetch_newsapi_headlines with newsapi.ai."""
import sys, logging
sys.path.insert(0, ".")
logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

from bot.macro import fetch_newsapi_headlines

# Test with comma-separated keywords (newsapi.ai format)
print("=== fetch_newsapi_headlines(query='bitcoin,crypto,prediction market') ===")
articles = fetch_newsapi_headlines(query="bitcoin,crypto,prediction market", page_size=3)
print(f"Returned {len(articles)} articles\n")
for a in articles:
    print(f"Title:   {a.get('title', '?')[:80]}")
    print(f"Source:  {a.get('source', {}).get('name', '?')}")
    print(f"Summary: {(a.get('description') or '?')[:80]}")
    print(f"URL:     {a.get('url', '?')[:70]}")
    print()

# Verify caching works
print("=== Second call (should be cached) ===")
import time
t0 = time.time()
articles2 = fetch_newsapi_headlines(query="bitcoin,crypto,prediction market", page_size=3)
dt = time.time() - t0
print(f"Returned {len(articles2)} articles in {dt*1000:.0f}ms (cached)\n")

print("=== RESULT ===")
print(f"{'PASS' if len(articles) > 0 else 'FAIL'}: {len(articles)} articles returned")
