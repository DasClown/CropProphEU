"""World Bank — find crop yield indicators"""
import urllib.request, json

# Search World Bank indicators for crop yields
indicators_to_check = [
    "AG.YLD.CREL.KG",     # Cereal yield (kg/ha)
    "AG.PRD.WHEA.MT",     # Wheat production  
    "AG.PRD.MAIZ.MT",     # Maize production
    "AG.PRD.SUNF.MT",     # Sunflower production
    "AG.PRD.RAPS.MT",     # Rapeseed production
    "AG.PRD.BARL.MT",     # Barley production
]

for ind in indicators_to_check:
    url = f"https://api.worldbank.org/v2/indicator/{ind}?format=json&per_page=5"
    req = urllib.request.Request(url, headers={"User-Agent": "crop-mcp/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            d = json.loads(resp.read().decode())
        if len(d) > 1 and d[1]:
            name = d[1][0].get("name", "unknown")
            print(f"  {ind}: {name[:80]}")
        else:
            print(f"  {ind}: no results")
    except Exception as e:
        print(f"  {ind}: {str(e)[:40]}")

print()

# Now try to get Ukraine data
for ind in ["AG.PRD.WHEA.MT", "AG.PRD.MAIZ.MT"]:
    url = f"https://api.worldbank.org/v2/country/UA/indicator/{ind}?format=json&per_page=30&date=2000:2024"
    req = urllib.request.Request(url, headers={"User-Agent": "crop-mcp/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            d = json.loads(resp.read().decode())
        if len(d) > 1 and d[1]:
            vals = {r["year"]: r["value"] for r in d[1] if r.get("value")}
            years = sorted(vals.keys())
            print(f"UA {ind}: {len(years)} yr ({years[0]}-{years[-1]})")
            for y in years[-3:]:
                print(f"  {y}: {vals[y]:.0f} MT")
    except Exception as e:
        print(f"UA {ind}: {str(e)[:40]}")
