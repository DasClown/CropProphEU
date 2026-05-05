"""FAOSTAT — retry with proper parameters, timeout per crop"""
import urllib.request, json, time

BASE = "https://fenixservices.fao.org/faostat/api/v1/en/data"

# Known FAO item codes
ITEMS = {"wheat": 15, "maize": 56, "barley": 44, "sunflower": 267, "rapeseed": 270}

# Area: UA (Ukraine), Element: 5421 (Yield hg/ha)
for cname, icode in ITEMS.items():
    url = f"{BASE}?area=UA&item={icode}&element=5421"
    req = urllib.request.Request(url, headers={"User-Agent": "crop-mcp/5.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                d = json.loads(resp.read().decode())
            data = d.get("data", [])
            if data:
                vals = {}
                for r in data:
                    if r.get("value"):
                        y = int(r["year"])
                        v = float(r["value"])
                        if v > 0:
                            vals[y] = v / 10000  # hg/ha → t/ha
                years = sorted(vals.keys())
                print(f"UA {cname}: {len(years)} yr ({years[0]}-{years[-1]})")
                for y in years[-5:]:
                    print(f"  {y}: {vals[y]:.2f} t/ha")
            else:
                print(f"UA {cname}: 0 records")
            break  # success
        except Exception as e:
            e_str = str(e)
            if "521" in e_str:
                print(f"UA {cname}: server 521 (attempt {attempt+1}/3)")
                time.sleep(3)
            else:
                print(f"UA {cname}: {e_str[:60]}")
                break
