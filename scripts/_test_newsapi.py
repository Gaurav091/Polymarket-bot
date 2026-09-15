"""Quick NewsAPI key validation."""
import os
import requests
from dotenv import load_dotenv

load_dotenv(".env", override=True)
key = os.getenv("NEWS_API_KEY", "")
print(f"Key: {key[:12]}...{key[-4:]}" if len(key) > 16 else f"Key: {key}")

r = requests.get(
    "https://newsapi.org/v2/everything",
    params={"q": "bitcoin", "sortBy": "publishedAt", "pageSize": 3, "apiKey": key},
    timeout=10, verify=False,
)
print(f"Status: {r.status_code}")
if r.status_code == 200:
    data = r.json()
    print(f"Total results: {data.get('totalResults', 0)}")
    for a in data.get("articles", []):
        print(f"  - {a['title'][:80]}")
    print("\nVALID - NewsAPI key works!")
else:
    print(f"Error: {r.json().get('message', r.text[:200])}")
    print("\nINVALID - Register at https://newsapi.org/register")
