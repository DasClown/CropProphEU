"""FAOSTAT API test — Ukraine yield data"""
import urllib.request, json

# FAOSTAT API v1
# Domain: QCL = Crops and Livestock Products
# Element: 5421 = Yield (hg/ha)
# Area: UA = Ukraine
# Items are crop-specific codes

# First, let's find crop codes
BASE = "https://fenixservices.fao.org/faostat/api/v1/en"

# Get available items for QCL domain
url = f"{BASE}/QAQ/QCL/lists/ITEM"
req = urllib.request.Request(url, headers={"User-Agent": "crop-mcp/5.0"})
with urllib.request.urlopen(req, timeout=20) as resp:
    items = json.loads(resp.read().decode())

# Search for wheat, barley, corn, sunflower, rapeseed
targets = ["wheat", "barley", "maize", "sunflower", "rapeseed", "rye", "oats"]
for item in items:
    label = item.get("Label", "").lower()
    if any(t in label for t in targets):
        print(f"  {item['Identifier']}: {item['Label']}")

print()

# Get available elements
url = f"{BASE}/QAQ/QCL/lists/ELEMENT"
req = urllib.request.Request(url, headers={"User-Agent": "crop-mcp/5.0"})
with urllib.request.urlopen(req, timeout=20) as resp:
    elements = json.loads(resp.read().decode())

for el in elements:
    label = el.get("Label", "").lower()
    if "yield" in label or "production" in label or "area" in label:
        print(f"  {el['Identifier']}: {el['Label']}")

print()

# Now try to fetch Ukraine wheat yield data
# area=UA (Ukraine), item=15 (Wheat), element=5421 (Yield)
url = f"{BASE}/data?area=UA&item=15&element=5421"
req = urllib.request.Request(url, headers={"User-Agent": "crop-mcp/5.0"})
try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        d = json.loads(resp.read().decode())
    data = d.get("data", [])
    print(f"Ukraine wheat yield: {len(data)} records")
    for year_record in data[:5]:
        print(f"  {year_record}")
    if data:
        years = sorted(set(r.get("year", "") for r in data))
        print(f"  Years: {years[0]}-{years[-1]} ({len(years)} total)")
except Exception as e:
    print(f"Error: {e}")
