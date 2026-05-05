"""Try alternative Eurostat geo codes for UK"""
import urllib.request, json

codes = ["UK", "GB", "GBR", "UK0", "UKI", "EL", "DE", "FR"]  # DE/FR/EL as control

for gc in codes:
    url = f"https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/apro_cpshr?format=JSON&lang=EN&crops=C1100&strucpro=YI_HU_EU&geo={gc}"
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
        label = d.get("dimension",{}).get("geo",{}).get("category",{}).get("label",{}).get(gc, gc)
        print(f"{gc} ({label}): {len(years)} years" + (f" {years[0]}-{years[-1]}" if years else " no data"))
    except Exception as e:
        print(f"{gc}: ERROR - {str(e)[:60]}")
