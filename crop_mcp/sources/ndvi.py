"""
NDVI: Satellite vegetation index via Sentinel-2 (Planetary Computer STAC API).

Computes NDVI = (NIR - Red) / (NIR + Red) from Sentinel-2 L2A imagery.
Returns the most recent cloud-free NDVI value for a location.

API: https://planetarycomputer.microsoft.com/api/stac/v1/
Sentinel-2 bands: B04 (Red, 665nm), B08 (NIR, 842nm)
"""

import json
import time
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple
from urllib.request import Request, urlopen

import rasterio

# Cache
_cache: Dict[str, Tuple[float, Any]] = {}
CACHE_TTL = 3600  # 1 hour (NDVI changes slowly)

STAC_SEARCH = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
COLLECTION = "sentinel-2-l2a"


def _search_scenes(lat: float, lon: float, start_date: str, end_date: str,
                   max_cloud: float = 30.0, limit: int = 5) -> List[Dict]:
    """Search for Sentinel-2 scenes at a location with low cloud cover."""
    bbox = f"{lon-0.05},{lat-0.05},{lon+0.05},{lat+0.05}"
    
    url = (f"{STAC_SEARCH}?collections={COLLECTION}"
           f"&bbox={bbox}"
           f"&datetime={start_date}/{end_date}"
           f"&limit={limit}"
           f"&sortby=properties.datetime&sortdirection=desc")
    
    req = Request(url, headers={"User-Agent": "crop-mcp/2.0 (research)"})
    
    try:
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        return []
    
    features = data.get("features", [])
    
    # Filter by cloud cover and sort
    good_scenes = []
    for f in features:
        cloud = f.get("properties", {}).get("eo:cloud_cover", 100)
        date_str = f.get("properties", {}).get("datetime", "")
        if cloud <= max_cloud:
            good_scenes.append({
                "date": date_str[:10],
                "cloud_cover_pct": cloud,
                "scene_id": f["id"],
                "assets": f.get("assets", {}),
            })
    
    return sorted(good_scenes, key=lambda x: x["date"], reverse=True)


def _get_band_url(scene: Dict, band: str) -> Optional[str]:
    """Get the GeoTIFF URL for a Sentinel-2 band."""
    assets = scene.get("assets", {})
    band_asset = assets.get(band)
    if not band_asset:
        return None
    return band_asset.get("href")


def _get_sas_token() -> str:
    """Get temporary SAS token for Planetary Computer Azure Blob Storage."""
    url = "https://planetarycomputer.microsoft.com/api/sas/v1/token/sentinel-2-l2a"
    try:
        req = Request(url, headers={"User-Agent": "crop-mcp/2.0"})
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return data.get("token", "")
    except Exception:
        return ""


def _sample_ndvi(b04_url: str, b08_url: str, lat: float, lon: float) -> Optional[float]:
    """Sample NDVI from COG GeoTIFFs at a given coordinate."""
    try:
        import rasterio
        from rasterio.warp import transform as warp_transform
        import rasterio.env
        
        # Get SAS token for Planetary Computer access
        sas = _get_sas_token()
        b04_signed = f"{b04_url}?{sas}" if sas else b04_url
        b08_signed = f"{b08_url}?{sas}" if sas else b08_url
        
        # COG reading optimization
        env = rasterio.Env(
            GDAL_DISABLE_READDIR_ON_OPEN='TRUE',
            CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.tif',
            GDAL_HTTP_TIMEOUT='30',
            GDAL_HTTP_MAX_RETRY='3',
        )
        
        def read_band(url):
            with env:
                with rasterio.open(url) as src:
                    # Transform lat/lon (EPSG:4326) to raster CRS
                    xs, ys = warp_transform('EPSG:4326', src.crs, [lon], [lat])
                    easting, northing = xs[0], ys[0]
                    py, px = src.index(easting, northing)
                    height, width = src.height, src.width
                    row_start = max(0, py-1)
                    row_end = min(height, py+2)
                    col_start = max(0, px-1)
                    col_end = min(width, px+2)
                    if row_end <= row_start or col_end <= col_start:
                        return None
                    data = src.read(1, window=((row_start, row_end), (col_start, col_end)))
                    return float(data.mean())
        
        red_val = read_band(b04_signed)
        nir_val = read_band(b08_signed)
        
        # Sentinel-2 L2A values are scaled by 10000
        red = red_val / 10000.0
        nir = nir_val / 10000.0
        
        if red is None or nir is None or red < 0 or nir < 0:
            return None
        
        if nir + red == 0:
            return 0.0
        
        ndvi = (nir - red) / (nir + red)
        return round(ndvi, 3)
    
    except Exception as e:
        return None


def get_ndvi(lat: float, lon: float, reference_date: Optional[str] = None,
             max_lookback_days: int = 30) -> Dict[str, Any]:
    """
    Get the most recent cloud-free NDVI for a location.
    
    Returns the latest NDVI reading within max_lookback_days from reference_date.
    """
    ref = date.fromisoformat(reference_date) if reference_date else date.today()
    start = (ref - timedelta(days=max_lookback_days)).isoformat()
    end = ref.isoformat()
    
    scenes = _search_scenes(lat, lon, start, end, max_cloud=30, limit=10)
    
    if not scenes:
        # Try with higher cloud tolerance
        scenes = _search_scenes(lat, lon, start, end, max_cloud=60, limit=10)
    
    if not scenes:
        # Try further back
        start_wide = (ref - timedelta(days=max_lookback_days * 3)).isoformat()
        scenes = _search_scenes(lat, lon, start_wide, end, max_cloud=60, limit=10)
    
    results = []
    for scene in scenes:
        b04_url = _get_band_url(scene, "B04")
        b08_url = _get_band_url(scene, "B08")
        
        if not b04_url or not b08_url:
            continue
        
        ndvi = _sample_ndvi(b04_url, b08_url, lat, lon)
        if ndvi is not None:
            results.append({
                "date": scene["date"],
                "cloud_cover_pct": scene["cloud_cover_pct"],
                "ndvi": ndvi,
            })
        
        # Only need one good reading per scene
        if ndvi is not None:
            break
    
    latest = results[0] if results else None
    
    # NDVI interpretation
    interpretation = None
    if latest:
        nd = latest["ndvi"]
        if nd < 0:
            interpretation = "water/snow/bare"
        elif nd < 0.2:
            interpretation = "sparse_vegetation/fallow"
        elif nd < 0.4:
            interpretation = "moderate_vegetation"
        elif nd < 0.6:
            interpretation = "dense_vegetation"
        else:
            interpretation = "very_dense_vegetation/forest"
    
    return {
        "status": "ok" if latest else "no_data",
        "location": {"lat": lat, "lon": lon},
        "search_window": {"start": start, "end": end},
        "scenes_found": len(scenes),
        "latest": latest,
        "interpretation": interpretation,
    }


def get_ndvi_for_region(lat: float, lon: float, season_start: str,
                         season_end: str) -> Dict[str, Any]:
    """
    Get NDVI trend over a growing season.
    Samples monthly to build a seasonal NDVI profile.
    """
    start_d = date.fromisoformat(season_start)
    end_d = date.fromisoformat(season_end)
    
    readings = []
    current = start_d
    while current <= end_d:
        # Sample around the 15th of each month
        sample_date = current.replace(day=15)
        if sample_date > end_d:
            break
        
        ndvi = get_ndvi(lat, lon, sample_date.isoformat(), max_lookback_days=15)
        if ndvi.get("latest"):
            readings.append({
                "target_date": sample_date.isoformat(),
                "ndvi": ndvi["latest"]["ndvi"],
                "cloud_cover_pct": ndvi["latest"]["cloud_cover_pct"],
                "source_date": ndvi["latest"]["date"],
            })
        
        # Move to next month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)
        
        time.sleep(0.3)  # Rate limit
    
    # Calculate stats
    ndvi_values = [r["ndvi"] for r in readings if r["ndvi"] is not None]
    
    return {
        "status": "ok" if readings else "no_data",
        "location": {"lat": lat, "lon": lon},
        "season": {"start": season_start, "end": season_end},
        "readings": readings,
        "max_ndvi": max(ndvi_values) if ndvi_values else None,
        "min_ndvi": min(ndvi_values) if ndvi_values else None,
        "mean_ndvi": round(sum(ndvi_values) / len(ndvi_values), 3) if ndvi_values else None,
    }


if __name__ == "__main__":
    # Quick test: Winter wheat in Sachsen-Anhalt
    print("=== NDVI Test: Sachsen-Anhalt ===")
    ndvi = get_ndvi(51.5, 11.5, max_lookback_days=60)
    print(json.dumps(ndvi, indent=2, ensure_ascii=False))
