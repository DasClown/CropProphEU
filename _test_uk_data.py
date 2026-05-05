"""Check UK + UA data availability in Eurostat"""
import sys
sys.path.insert(0, '/home/j/crop-mcp')
from build_europe import fetch_eurostat

crops = {"wheat": "C1100", "barley": "C1300", "corn": "C1500",
         "rapeseed": "C2000", "sunflower": "C2200"}

for country in ["UK", "DE", "FR", "UA"]:
    print(f"\n=== {country} ===")
    for cname, ccode in crops.items():
        try:
            data = fetch_eurostat(country, ccode)
            years = sorted(data.keys())
            if years:
                avg = sum(data[y] for y in years) / len(years)
                print(f"  {cname}: {len(years)} yr ({years[0]}-{years[-1]}), avg {avg:.2f} t/ha")
            else:
                print(f"  {cname}: 0 years (empty)")
        except Exception as e:
            print(f"  {cname}: ERROR - {str(e)[:60]}")
