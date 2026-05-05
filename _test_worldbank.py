"""Ukraine yield data via World Bank + OWID"""
import urllib.request, json, csv, io

# World Bank API — yield indicators
# AG.YLD.CREL.KG = Cereal yield (kg per hectare)  
# AG.PRD.CREL.MT = Cereal production (metric tons)
WB_BASE = "https://api.worldbank.org/v2/country/UA/indicator"

indicators = {
    "wheat": "AG.PRD.WHEA.KG",     # Wheat yield (kg/ha)
    "maize": "AG.YLD.CREL.KG",     # Cereal yield (used as proxy)
    "sunflower": "AG.PRD.SUNF.KG",  # This might not exist  
}

for crop, ind in indicators.items():
    url = f"{WB_BASE}/{ind}?format=json&per_page=50&date=2000:2024"
    req = urllib.request.Request(url, headers={"User-Agent": "crop-mcp/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            d = json.loads(resp.read().decode())
        records = d[1] if len(d) > 1 else []
        if records:
            vals = {r["year"]: r["value"] for r in records if r.get("value")}
            t_ha = {y: v/10000 for y, v in vals.items()}
            years = sorted(t_ha.keys())
            if years:
                print(f"UA {crop} ({ind}): {len(years)} yr ({years[0]}-{years[-1]})")
                for y in years[-3:]:
                    print(f"  {y}: {t_ha[y]:.2f} t/ha")
        else:
            print(f"UA {crop}: no data via {ind}")
    except Exception as e:
        print(f"UA {crop}: {str(e)[:60]}")
