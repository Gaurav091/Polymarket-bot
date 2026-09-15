"""Test free internet data sources for Polymarket bot integration."""
import requests
import json

print("=" * 60)
print("FREE DATA SOURCE TESTS")
print("=" * 60)

# Test 1: CoinGecko (crypto prices — no API key needed)
print("\n--- CoinGecko API (crypto prices) ---")
try:
    r = requests.get(
        "https://api.coingecko.com/api/v3/simple/price",
        params={"ids": "bitcoin,ethereum,solana", "vs_currencies": "usd", "include_24hr_change": "true"},
        timeout=10, verify=False,
    )
    print(f"Status: {r.status_code}")
    if r.ok:
        print(json.dumps(r.json(), indent=2))
except Exception as e:
    print(f"FAILED: {e}")

# Test 2: Yahoo Finance (VIX, S&P 500, DXY, Gold)
print("\n--- Yahoo Finance API (macro data) ---")
for sym in ["^VIX", "^GSPC", "^DXY", "GC=F"]:
    try:
        r = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}",
            params={"interval": "1d", "range": "2d"},
            timeout=10, verify=False,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if r.ok:
            data = r.json()["chart"]["result"][0]
            meta = data["meta"]
            price = meta.get("regularMarketPrice", "N/A")
            prev = meta.get("chartPreviousClose", "N/A")
            print(f"  {sym}: price={price}  prev_close={prev}")
        else:
            print(f"  {sym}: FAILED HTTP {r.status_code}")
    except Exception as e:
        print(f"  {sym}: FAILED {e}")

# Test 3: Polymarket event metadata
print("\n--- Polymarket Events API ---")
try:
    r = requests.get(
        "https://gamma-api.polymarket.com/events",
        params={"limit": 5, "active": "true", "closed": "false"},
        timeout=10, verify=False,
    )
    if r.ok:
        events = r.json()
        for e in events[:3]:
            title = e.get("title", "?")[:60]
            cat = e.get("category", "?")
            liq = e.get("liquidity", 0)
            print(f"  {title} | cat={cat} | liq=${liq:.0f}")
    else:
        print(f"  FAILED HTTP {r.status_code}")
except Exception as e:
    print(f"  FAILED: {e}")

# Test 4: DeFi Llama (on-chain TVL / crypto metrics)
print("\n--- DeFi Llama API (on-chain metrics) ---")
try:
    r = requests.get("https://api.llama.fi/v2/historicalChainTvl", timeout=10, verify=False)
    if r.ok:
        tvl_data = r.json()
        latest = tvl_data[-1] if tvl_data else {}
        prev = tvl_data[-2] if len(tvl_data) > 1 else {}
        print(f"  Total DeFi TVL: ${latest.get('tvl', 0)/1e9:.2f}B")
        print(f"  Previous day:   ${prev.get('tvl', 0)/1e9:.2f}B")
except Exception as e:
    print(f"  FAILED: {e}")

# Test 5: FRED API (economic indicators — needs free API key)
print("\n--- FRED API (economic indicators) ---")
import os
fred_key = os.getenv("FRED_API_KEY", "")
if fred_key:
    try:
        # CPI
        r = requests.get(
            "https://api.stlouisfed.org/fred/series/observations",
            params={"series_id": "CPIAUCSL", "api_key": fred_key, "file_type": "json", "sort_order": "desc", "limit": 3},
            timeout=10, verify=False,
        )
        if r.ok:
            obs = r.json().get("observations", [])
            for o in obs[:2]:
                print(f"  CPI {o['date']}: {o['value']}")
    except Exception as e:
        print(f"  FAILED: {e}")
else:
    print("  No FRED_API_KEY set — skipping (free key at https://fred.stlouisfed.org/docs/api/api_key.html)")

# Test 6: Google Trends (via pytrends)
print("\n--- Google Trends ---")
try:
    from pytrends.request import TrendReq
    pytrends = TrendReq(hl="en-US", tz=360)
    pytrends.build_payload(["Polymarket", "prediction market"], cat=0, timeframe="now 7-d")
    interest = pytrends.interest_over_time()
    if not interest.empty:
        latest = interest.iloc[-1]
        print(f"  Polymarket interest (latest): {latest.get('Polymarket', 'N/A')}")
        print(f"  Prediction market interest:   {latest.get('prediction market', 'N/A')}")
    else:
        print("  No data returned")
except ImportError:
    print("  pytrends NOT installed (pip install pytrends)")
except Exception as e:
    print(f"  FAILED: {e}")

# Test 7: NewsAPI.org (free tier — 100 req/day)
print("\n--- NewsAPI.org (free tier) ---")
newsapi_key = os.getenv("NEWSAPI_KEY", "")
if newsapi_key:
    try:
        r = requests.get(
            "https://newsapi.org/v2/everything",
            params={"q": "prediction market OR polymarket OR crypto", "sortBy": "publishedAt", "pageSize": 3, "apiKey": newsapi_key},
            timeout=10, verify=False,
        )
        if r.ok:
            articles = r.json().get("articles", [])
            for a in articles[:3]:
                print(f"  {a['title'][:70]}")
        else:
            print(f"  FAILED: {r.status_code} {r.text[:100]}")
    except Exception as e:
        print(f"  FAILED: {e}")
else:
    print("  No NEWSAPI_KEY set (free at https://newsapi.org/register)")

# Test 8: Polymarket CLOB — advanced endpoints
print("\n--- Polymarket CLOB advanced ---")
try:
    # Get recently resolved markets for calibration
    r = requests.get(
        "https://gamma-api.polymarket.com/markets",
        params={"closed": "true", "limit": 3, "order": "endDate", "ascending": "false"},
        timeout=10, verify=False,
    )
    if r.ok:
        markets = r.json()
        for m in markets[:3]:
            title = m.get("question", "?")[:60]
            outcome = m.get("outcome", "?")
            print(f"  RESOLVED: {title} → {outcome}")
except Exception as e:
    print(f"  FAILED: {e}")

print("\n" + "=" * 60)
print("TESTS COMPLETE")
print("=" * 60)
