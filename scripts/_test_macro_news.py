"""Test bot/macro.py fetch_newsapi_headlines directly."""
import sys
sys.path.insert(0, ".")

from bot.macro import fetch_newsapi_headlines

print("=== bot.macro.fetch_newsapi_headlines ===")
articles = fetch_newsapi_headlines(page_size=5)
print(f"Returned {len(articles)} articles")
for a in articles:
    print(f"  Title: {a.get('title', '?')[:80]}")
    print(f"  Source: {a.get('source', {}).get('name', '?')}")
    print(f"  URL: {a.get('url', '?')[:60]}")
    print()
