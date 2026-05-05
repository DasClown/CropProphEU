"""Debug Eurostat API response structure for FR wheat"""
import urllib.request, json

# Try a simpler query for FR wheat
url = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/apro_cpshr?format=JSON&lang=EN&crops=C1100&geo=FR"
req = urllib.request.Request(url, headers={"User-Agent": "crop-mcp/4.0"})
with urllib.request.urlopen(req, timeout=20) as resp:
    d = json.loads(resp.read().decode())

# Check dimensions
dims = d.get("dimension", {})
print("Dimensions:", list(dims.keys()))
for name, dim in dims.items():
    cats = dim.get("category", {}).get("index", {})
    labs = dim.get("category", {}).get("label", {})
    if name == "geo":
        codes = list(cats.keys())[:10]
        print(f"  geo codes: {codes}")
    elif name == "strucpro":
        print(f"  strucpro codes: {list(cats.keys())}")
    elif name == "time":
        times = sorted([int(k) for k in cats.keys() if k.isdigit()])
        print(f"  years: {times[0] if times else '?'} - {times[-1] if times else '?'} ({len(times)} total)")
    else:
        print(f"  {name}: {list(cats.keys())[:5]}")

# Check value count
vals = d.get("value", {})
print(f"\nTotal values: {len(vals)}")
if len(vals) > 0:
    sample_keys = list(vals.keys())[:5]
    print(f"Sample keys: {sample_keys}")
    print(f"Sample vals: {[vals[k] for k in sample_keys]}")
