"""FAOSTAT API test — minimal"""
import urllib.request, json, sys

BASE = "https://fenixservices.fao.org/faostat/api/v1/en"

# Just try the data endpoint directly for Ukraine wheat
# Known FAO codes: Wheat = 15, Maize = 56, Barley = 44, Sunflower = 267, Rapeseed = 270
# Element 5421 = Yield (hg/ha)
area_code = "UA"
items = {"wheat": 15, "barley": 44, "maize": 56, "sunflower": 267, "rapeseed": 270}

for cname, icode in items.items():
    url = f"{BASE}/data?area={area_code}&item={icode}&element=5421"
    req = urllib.request.Request(url, headers={"User-Agent": "crop-mcp/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            d = json.loads(resp.read().decode())
        data = d.get("data", [])
        if data:
            years = sorted(set(r.get("year", "") for r in data))
            vals = {int(r["year"]): r["value"] for r in data if r.get("value")}
            t_ha = {y: float(v)/10000 for y,v in vals.items() if float(v) > 0}
            print(f"UA {cname}: {len(t_ha)} yr ({min(t_ha.keys())}-{max(t_ha.keys())})")
            latest = sorted(t_ha.keys())[-3:]
            for y in latest:
                print(f"  {y}: {t_ha[y]:.2f} t/ha")
        else:
            print(f"UA {cname}: no data")
    except Exception as e:
        print(f"UA {cname}: {str(e)[:60]}")
