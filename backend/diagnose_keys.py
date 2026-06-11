"""
Run in backend/: python diagnose_keys.py
Shows exactly why each key is failing with full error details.
"""
import sys, requests
sys.path.insert(0, '.')
from config import GOOGLE_KEY_CX_PAIRS

print(f"Testing {len(GOOGLE_KEY_CX_PAIRS)} pairs\n")

for i, (key, cx) in enumerate(GOOGLE_KEY_CX_PAIRS):
    print(f"{'='*55}")
    print(f"Pair {i+1}: key=...{key[-8:]}  cx={cx}")
    
    r = requests.get(
        "https://www.googleapis.com/customsearch/v1",
        params={"key": key, "cx": cx, "q": "test", "num": 1},
        timeout=10
    )
    
    print(f"HTTP Status: {r.status_code}")
    
    if r.status_code == 200:
        data = r.json()
        total = data.get("searchInformation", {}).get("totalResults", "?")
        print(f"✅ WORKS — total results: {total}")
    else:
        data = r.json()
        err = data.get("error", {})
        print(f"❌ Status {r.status_code}")
        print(f"   Message: {err.get('message', 'unknown')}")
        print(f"   Reason:  {err.get('errors', [{}])[0].get('reason', 'unknown')}")
        print(f"   Domain:  {err.get('errors', [{}])[0].get('domain', 'unknown')}")
        print(f"   Full error: {err}")
    print()
