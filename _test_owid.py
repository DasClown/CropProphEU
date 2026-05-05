"""Our World in Data — Ukraine yield data"""
import urllib.request, csv, io

# OWID crop yield dataset
urls = [
    "https://raw.githubusercontent.com/owid/owid-datasets/master/datasets/Crop%20yields/15788858/owid-crop-yields.csv",
    "https://raw.githubusercontent.com/owid/owid-datasets/master/datasets/Crop%20yields%20vs.%20GDP%20per%20capita/Crop%20yields%20vs.%20GDP%20per%20capita.csv",
]

for url in urls:
    req = urllib.request.Request(url, headers={"User-Agent": "crop-mcp/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode()
        lines = content.split("\n")
        print(f"\n=== {url.split('/')[-1]} ===")
        print(f"Rows: {len(lines)-1}")
        # Print header
        print(f"Header: {lines[0][:200]}")
        # Find Ukraine rows
        ukraine_lines = [l for l in lines if "Ukraine" in l or "UA" in l.split(",")[0]]
        print(f"Ukraine rows: {len(ukraine_lines)}")
        if ukraine_lines:
            for l in ukraine_lines[:3]:
                print(f"  {l[:200]}")
    except Exception as e:
        print(f"{url.split('/')[-1]}: {e}")
