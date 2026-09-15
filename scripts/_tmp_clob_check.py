import requests, time

# CLOB endpoints — the ones quant actually needs
tid = "86530853819696929920199555682888623138387770161330010338937420714007836804346"

for name, url, params in [
    ("prices-history", "https://clob.polymarket.com/prices-history",
     {"market": tid, "interval": "1w", "fidelity": 60}),
    ("book", "https://clob.polymarket.com/book", {"token_id": tid}),
]:
    for attempt in range(3):
        try:
            t0 = time.time()
            r = requests.get(url, params=params, timeout=30, verify=False)
            print(f"{name} attempt {attempt+1}: {r.status_code} len={len(r.text)} in {time.time()-t0:.1f}s")
            break
        except Exception as e:
            print(f"{name} attempt {attempt+1}: {type(e).__name__}: {str(e)[:100]}")
            time.sleep(10)
