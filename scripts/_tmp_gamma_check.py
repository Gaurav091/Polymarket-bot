import requests, time

url = "https://gamma-api.polymarket.com/markets"
params = {"limit": 100, "active": "true", "closed": "false",
          "order": "volume", "ascending": "false", "offset": 0}

for attempt in range(4):
    try:
        t0 = time.time()
        r = requests.get(url, params=params, timeout=30, verify=False)
        print(f"attempt {attempt+1}: {r.status_code} len={len(r.text)} in {time.time()-t0:.1f}s")
        break
    except Exception as e:
        print(f"attempt {attempt+1}: {type(e).__name__}: {str(e)[:120]}")
        time.sleep(20)
