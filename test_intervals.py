"""Quick test to verify intervals.icu API connectivity."""
import requests
from config import Config

BASE = "https://intervals.icu/api/v1"
auth = ("API_KEY", Config.INTERVALS_API_KEY)

# Fetch athlete profile (i0 = self)
r = requests.get(f"{BASE}/athlete/i0", auth=auth)
print(f"Status: {r.status_code}")
if r.ok:
    a = r.json()
    print(f"Athlete ID : {a.get('id')}")
    print(f"Name       : {a.get('name')}")
    print(f"Country    : {a.get('country_code')}")
else:
    print(r.text)
