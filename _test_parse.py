"""Parse Eurostat data without strucpro filter, extract yield per country"""
import urllib.request, json

crops = {"wheat": "C1100", "barley": "C1300", "corn": "C1500",
         "rapeseed": "C2000", "sunflower": "C2200"}

for country in ["UK", "FR", "DE", "PL", "UA"]:
    print(f"\n=== {country} ===")
    for cname, ccode in crops.items():
        url = f"https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/apro_cpshr?format=JSON&lang=EN&crops={ccode}&geo={country}"
        req = urllib.request.Request(url, headers={"User-Agent": "crop-mcp/4.0"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                d = json.loads(resp.read().decode())
        except:
            print(f"  {cname}: HTTP error")
            continue
        
        vals = d.get("value", {})
        if not vals:
            print(f"  {cname}: no data at all")
            continue
            
        # Parse dimensions to find YI_HU_EU entries
        dims = d.get("dimension", {})
        time_idx = dims.get("time", {}).get("category", {}).get("index", {})
        time_pos = {v: k for k, v in time_idx.items()}
        strucpro_idx = dims.get("strucpro", {}).get("category", {}).get("index", {})
        
        # Find YI_HU_EU position
        yi_pos = [k for k, v in strucpro_idx.items() if v == "YI_HU_EU" or "YI" in v or "yield" in str(v).lower()]
        hu_pos = [k for k, v in strucpro_idx.items() if "YI" in str(v) or v == "YI_HU_EU"]
        
        if not hu_pos:
            # Print available codes
            codes = list(strucpro_idx.keys())
            print(f"  {cname}: {len(vals)} vals total, strucpro codes: {codes}")
            continue
            
        yi_idx = strucpro_idx.get("YI_HU_EU")
        data = {}
        for pos_str, val in vals.items():
            parts = d.get("id", [])
            # Map position to dimensions - complex
            # Simpler: just group by strucpro
            pass
        print(f"  {cname}: found YI_HU_EU at pos {hu_pos}, need proper parsing...")
        break  # one crop is enough to understand
    break  # one country is enough
