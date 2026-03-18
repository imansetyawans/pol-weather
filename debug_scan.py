"""Quick test: can we discover weather events via CLOB or search?"""
import requests
import json

# Try CLOB markets endpoint
print("=== CLOB markets search ===")
try:
    r = requests.get("https://clob.polymarket.com/markets",
        params={"next_cursor": "MA=="},
        timeout=15)
    data = r.json()
    # Check structure
    print(f"  Keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
    if isinstance(data, dict):
        markets = data.get("data", data.get("markets", []))
        if markets:
            print(f"  First market keys: {list(markets[0].keys())[:10]}")
            weather_m = [m for m in markets if "temperature" in str(m.get("question","")).lower()]
            print(f"  Weather markets in batch: {len(weather_m)}")
except Exception as ex:
    print(f"  Error: {ex}")

# Polymarket strapi/search
print("\n=== Polymarket search API ===")
try:
    r2 = requests.get("https://gamma-api.polymarket.com/events",
        params={"title": "Highest temperature", "active": "true", "closed": "false", "limit": "10"},
        timeout=15)
    data2 = r2.json()
    print(f"  title param: {len(data2)} events")
    for e in data2[:3]:
        print(f"    {e.get('title','?')}")
except Exception as ex:
    print(f"  Error: {ex}")

# Try tag_slug
print("\n=== Tag slug search ===")
for tag_slug in ["weather", "temperature", "highest-temperature", "science"]:
    try:
        r3 = requests.get("https://gamma-api.polymarket.com/events",
            params={"tag_slug": tag_slug, "active": "true", "closed": "false", "limit": "5"},
            timeout=15)
        data3 = r3.json()
        print(f"  tag_slug={tag_slug}: {len(data3)} events")
        for e in data3[:2]:
            print(f"    {e.get('title','?')[:60]}")
    except Exception as ex:
        print(f"  tag_slug={tag_slug}: Error: {ex}")

# 4. Try the Polymarket weather category page via strapi 
print("\n=== Strapi weather category ===")
try:
    r4 = requests.get("https://gamma-api.polymarket.com/events",
        params={"tag_id": "100420", "active": "true", "closed": "false", "limit": "10"},
        timeout=15)
    data4 = r4.json()
    print(f"  tag_id=100420: {len(data4)} events")
    for e in data4[:3]:
        print(f"    {e.get('title','?')[:60]}")
except Exception as ex:
    print(f"  Error: {ex}")

# 5. Try related_tags
print("\n=== Related tags check ===")
try:
    r5 = requests.get("https://gamma-api.polymarket.com/events",
        params={"related_tags": "weather", "active": "true", "closed": "false", "limit": "10"},
        timeout=15)
    data5 = r5.json()
    print(f"  related_tags=weather: {len(data5)} events")
except Exception as ex:
    print(f"  Error: {ex}")

# 6. Check what the Shanghai event's tags are
print("\n=== Shanghai event tags/metadata ===")
r6 = requests.get("https://gamma-api.polymarket.com/events",
    params={"slug": "highest-temperature-in-shanghai-on-march-19-2026"},
    timeout=15)
data6 = r6.json()
if data6:
    e = data6[0]
    # Print all top-level keys and some values
    for k, v in e.items():
        if k != "markets" and k != "description":
            print(f"  {k}: {str(v)[:80]}")
