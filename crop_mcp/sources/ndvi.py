"""
NDVI: Satellite vegetation index via Planetary Computer Sentinel-2.

V4.7: Simplified reliability improvements — retry logic, longer cache,
and Copernicus Data Space STAC as a future-ready option (Sentinel-2 not
currently in their v1 STAC catalog; CLMS NDVI COGs need S3 auth).

Sentinel-2 L2A bands: B04 (Red, 665nm), B08 (NIR, 842nm)
NDVI = (NIR - Red) / (NIR + Red)
"""

import json
import time
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple
from urllib.request import Request, urlopen

import rasterio

# Cache
_cache: Dict[str, Tuple[float, Any]] = {}
CACHE_TTL = 7200  # 2 hours

_PC_SEARCH = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
_PC_COLL = "sentinel-2-l2a"
_PC_SAS = "https://planetarycomputer.microsoft.com/api/sas/v1/token/sentinel-2-l2a"


def _search_scenes(lat: float, lon: float, start: str, end: str,
                   cloud_max: float = 30.0, limit: int = 10) -> List[Dict]:
    """Search Planetary Computer for cloud-free Sentinel-2 scenes."""
    bbox = f"{lon-0.05},{lat-0.05},{lon+0.05},{lat+0.05}"
    url = (f"{_PC_SEARCH}?collections={_PC_COLL}&bbox={bbox}"
           f"&datetime={start}/{end}&limit={limit}"
           "&sortby=properties.datetime&sortdirection=desc")
    try:
        req = Request(url, headers={"User-Agent": "crop-mcp/4.7"})
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        return []
    good = []
    for f in data.get("features", []):
        cloud = f.get("properties", {}).get("eo:cloud_cover", 100)
        if cloud <= cloud_max:
            good.append({
                "date": f.get("properties", {}).get("datetime", "")[:10],
                "cloud_pct": cloud,
                "assets": f.get("assets", {}),
            })
    return sorted(good, key=lambda x: x["date"], reverse=True)


def _get_sas() -> str:
    """Get SAS token with retry."""
    for i in range(3):
        try:
            req = Request(_PC_SAS, headers={"User-Agent": "crop-mcp/4.7"})
            with urlopen(req, timeout=15) as resp:
                tok = json.loads(resp.read().decode()).get("token", "")
                if tok:
                    return tok
        except Exception:
            if i < 2:
                time.sleep(2)
    return ""


def _sample_ndvi(b04_url: str, b08_url: str, lat: float,
                 lon: float, sas: str) -> Optional[float]:
    """Sample NDVI from Red/NIR GeoTIFF COGs."""
    for attempt in range(3):
        try:
            b04 = f"{b04_url}?{sas}" if sas else b04_url
            b08 = f"{b08_url}?{sas}" if sas else b08_url
            env = rasterio.Env(
                GDAL_DISABLE_READDIR_ON_OPEN='TRUE',
                CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.tif',
                GDAL_HTTP_TIMEOUT='30', GDAL_HTTP_MAX_RETRY='3')
            with env:
                with rasterio.open(b04) as src:
                    from rasterio.warp import transform as wt
                    xs, ys = wt('EPSG:4326', src.crs, [lon], [lat])
                    py, px = src.index(xs[0], ys[0])
                    h, w = src.height, src.width
                    win = ((max(0, py-1), min(h, py+2)),
                           (max(0, px-1), min(w, px+2)))
                    if win[0][0] >= win[0][1] or win[1][0] >= win[1][1]:
                        continue
                    red = float(src.read(1, window=win).mean()) / 10000.0
                with rasterio.open(b08) as src:
                    nir = float(src.read(1, window=win).mean()) / 10000.0
            if red < 0 or nir < 0:
                continue
            if nir + red == 0:
                return 0.0
            return round((nir - red) / (nir + red), 3)
        except Exception:
            if attempt < 2:
                time.sleep(2)
    return None


def _interpret(ndvi: float) -> str:
    if ndvi < 0:
        return "water/snow/bare"
    if ndvi < 0.2:
        return "sparse_vegetation/fallow"
    if ndvi < 0.4:
        return "moderate_vegetation"
    if ndvi < 0.6:
        return "dense_vegetation"
    return "very_dense_vegetation/forest"


# ── Public API ─────────────────────────────────

def get_ndvi(lat: float, lon: float,
             reference_date: Optional[str] = None,
             max_lookback_days: int = 30) -> Dict[str, Any]:
    """Get most recent cloud-free NDVI via Planetary Computer Sentinel-2."""
    ref = date.fromisoformat(reference_date) if reference_date else date.today()
    start = (ref - timedelta(days=max_lookback_days)).isoformat()
    end = ref.isoformat()

    sas = _get_sas()
    latest = None

    for cloud_max in [30, 60]:
        if latest:
            break
        scenes = _search_scenes(lat, lon, start, end, cloud_max, limit=10)
        for sc in scenes:
            a = sc.get("assets", {})
            b04 = a.get("B04", {}).get("href")
            b08 = a.get("B08", {}).get("href")
            if not b04 or not b08:
                continue
            ndvi = _sample_ndvi(b04, b08, lat, lon, sas)
            if ndvi is not None:
                latest = {"date": sc["date"], "ndvi": ndvi,
                          "cloud_pct": sc["cloud_pct"]}
                break

    # Wider search if nothing found
    if not latest:
        start_wide = (ref - timedelta(days=max_lookback_days * 3)).isoformat()
        for cloud_max in [30, 60]:
            if latest:
                break
            scenes = _search_scenes(lat, lon, start_wide, end, cloud_max, limit=10)
            for sc in scenes:
                a = sc.get("assets", {})
                b04 = a.get("B04", {}).get("href")
                b08 = a.get("B08", {}).get("href")
                if not b04 or not b08:
                    continue
                ndvi = _sample_ndvi(b04, b08, lat, lon, sas)
                if ndvi is not None:
                    latest = {"date": sc["date"], "ndvi": ndvi,
                              "cloud_pct": sc["cloud_pct"]}
                    break

    if latest:
        return {
            "status": "ok", "source": "planetary_computer_sentinel2",
            "location": {"lat": lat, "lon": lon},
            "search_window": {"start": start, "end": end},
            "latest": {
                "date": latest["date"], "ndvi": latest["ndvi"],
                "cloud_cover_pct": latest["cloud_pct"],
                "interpretation": _interpret(latest["ndvi"]),
            },
        }
    return {"status": "no_data", "location": {"lat": lat, "lon": lon},
            "search_window": {"start": start, "end": end},
            "source": "none", "latest": None}


def get_ndvi_for_region(lat: float, lon: float,
                        season_start: str, season_end: str) -> Dict[str, Any]:
    """Monthly NDVI profile over a growing season."""
    sd = date.fromisoformat(season_start)
    ed = date.fromisoformat(season_end)
    readings = []
    cur = sd
    while cur <= ed:
        samp = cur.replace(day=15)
        if samp > ed:
            break
        n = get_ndvi(lat, lon, samp.isoformat(), max_lookback_days=15)
        if n.get("latest"):
            readings.append({
                "target_date": samp.isoformat(),
                "ndvi": n["latest"]["ndvi"],
                "source": n.get("source", ""),
                "source_date": n["latest"]["date"],
            })
        cur = cur.replace(year=cur.year + 1, month=1) \
            if cur.month == 12 else cur.replace(month=cur.month + 1)
        time.sleep(0.3)
    vals = [r["ndvi"] for r in readings]
    return {
        "status": "ok" if readings else "no_data",
        "location": {"lat": lat, "lon": lon},
        "season": {"start": season_start, "end": season_end},
        "readings": readings,
        "max_ndvi": max(vals) if vals else None,
        "min_ndvi": min(vals) if vals else None,
        "mean_ndvi": round(sum(vals)/len(vals), 3) if vals else None,
    }


if __name__ == "__main__":
    print("=== NDVI Test: Sachsen-Anhalt ===")
    ndvi = get_ndvi(51.5, 11.5, max_lookback_days=60)
    print(json.dumps(ndvi, indent=2, ensure_ascii=False))
