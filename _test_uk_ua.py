"""Quick test: do Eurostat have UK / UA data?"""
import urllib.request, json

crops = {"wheat": "C1100", "barley": "C1300", "corn": "C1500",
         "rapeseed": "C2000", "sunflower": "C2200"}

for country, label in [("UK", "UK"), ("UA", "Ukraine")]:
    print(f"\n=== {label} ===")
    for cname, ccode in crops.items():
        url = f"https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/apro_cpshr?format=JSON&lang=EN&crops={ccode}&strucpro=YI_HU_EU&geo={country}"
        req = urllib.request.Request(url, headers={"User-Agent": "crop-mcp/4.0"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                d = json.loads(resp.read().decode())
            vals = d.get("value", {})
            time_idx = d.get("dimension",{}).get("time",{}).get("category",{}).get("index",{})
            time_pos = {v: k for k, v in time_idx.items()}
            data = {}
            for pos_str, val in vals.items():
                year = time_pos.get(int(pos_str), "?")
                data[year] = val
            years = sorted([y for y in data.keys() if isinstance(y, int)])
            if years:
                avg = sum(data[y] for y in years) / len(years)
                print(f"  {cname}: {len(years)} years, avg {avg:.2f} t/ha ({years[0]}-{years[-1]})")
            else:
                print(f"  {cname}: no data")
        except Exception as e:
            print(f"  {cname}: ERROR - {str(e)[:60]}")
