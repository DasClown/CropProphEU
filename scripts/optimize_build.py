#!/usr/bin/env python3
"""
Feature-Cache-Skript für build_europe.py.
Cached NASA POWER API-Ergebnisse für 24h mit joblib.Memory.
Loggt Caching-Statistiken (hit/miss ratio).

Usage:
  python scripts/optimize_build.py         # Normal run
  python scripts/optimize_build.py --crop corn  # Crop-spezifisch
  python scripts/optimize_build.py --clear # Cache leeren
"""
import json, os, sys, time, math, hashlib
from datetime import date, datetime
from collections import defaultdict
from pathlib import Path

# ── joblib Memory Caching ──
try:
    from joblib import Memory
    HAS_JOELIB = True
except ImportError:
    HAS_JOELIB = False

CACHE_DIR = "/home/j/crop-mcp/.feature_cache"
CACHE_TTL = 86400  # 24h in Sekunden
STATS_PATH = "/home/j/crop-mcp/scripts/cache_stats.json"

# Cache-Statistiken (persistent)
_stats = {"hits": 0, "misses": 0, "total": 0, "by_function": {}}


def _load_stats():
    global _stats
    if os.path.exists(STATS_PATH):
        try:
            with open(STATS_PATH) as f:
                _stats = json.load(f)
        except Exception:
            _stats = {"hits": 0, "misses": 0, "total": 0, "by_function": {}}


def _save_stats():
    os.makedirs(os.path.dirname(STATS_PATH), exist_ok=True)
    with open(STATS_PATH, 'w') as f:
        json.dump(_stats, f, indent=2)


def _record_hit(func_name):
    _stats["hits"] += 1
    _stats["total"] += 1
    _stats["by_function"].setdefault(func_name, {"hits": 0, "misses": 0})
    _stats["by_function"][func_name]["hits"] += 1
    _save_stats()


def _record_miss(func_name):
    _stats["misses"] += 1
    _stats["total"] += 1
    _stats["by_function"].setdefault(func_name, {"hits": 0, "misses": 0})
    _stats["by_function"][func_name]["misses"] += 1
    _save_stats()


# ── Cache-Implementierung ──

class PowerCache:
    """
    Cached NASA POWER API-Ergebnisse.
    Nutzt joblib.Memory wenn verfügbar, sonst einfaches JSON-Dict-Caching.
    """

    def __init__(self, cache_dir=CACHE_DIR, ttl=CACHE_TTL):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl
        self._in_memory = {}
        _load_stats()

        # joblib.Memory als Preferred Backend
        if HAS_JOELIB:
            self._memory = Memory(location=str(self.cache_dir / "joblib"), verbose=0)
        else:
            self._memory = None

    def _cache_key(self, lat, lon, start_year, end_year, params_tuple):
        """Erzeuge einen eindeutigen Cache-Key für POWER-Parameter."""
        raw = f"power_{lat:.4f}_{lon:.4f}_{start_year}_{end_year}_{'_'.join(sorted(params_tuple))}"
        return hashlib.md5(raw.encode()).hexdigest()

    def _json_cache_path(self, key):
        return self.cache_dir / f"{key}.json"

    def get_power_data(self, lat, lon, start, end, params):
        """Cached Version von get_power_data."""
        key = self._cache_key(lat, lon, start, end, tuple(sorted(params)))
        func_name = "get_power_data"

        # 1. Try joblib cache (persistent, managed)
        if self._memory:
            try:
                cached = self._memory.cache(self._fetch_power_raw, ignore=['self'])
                return cached(lat, lon, start, end, params)
            except Exception:
                pass

        # 2. Try JSON file cache
        cache_path = self._json_cache_path(key)
        if cache_path.exists():
            mtime = os.path.getmtime(cache_path)
            age = time.time() - mtime
            if age < self.ttl:
                try:
                    with open(cache_path) as f:
                        result = json.load(f)
                    _record_hit(func_name)
                    return result
                except Exception:
                    pass

        _record_miss(func_name)
        # 3. Fresh fetch
        result = self._fetch_power_raw(lat, lon, start, end, params)
        # Save to JSON cache
        try:
            with open(cache_path, 'w') as f:
                json.dump(result, f)
        except Exception:
            pass
        self._in_memory[key] = (time.time(), result)
        return result

    def _fetch_power_raw(self, lat, lon, start, end, params):
        """Direkter API-Aufruf an NASA POWER."""
        from crop_mcp.sources.power import get_power_data as _raw
        return _raw(lat, lon, start, end, params)

    def get_eurostat_yields(self, country_code, crop_code):
        """Cached Eurostat Yield Fetch."""
        key = f"eurostat_{country_code}_{crop_code}"
        func_name = "get_eurostat_yields"
        cache_path = self.cache_dir / f"euro_{key}.json"

        if cache_path.exists():
            mtime = os.path.getmtime(cache_path)
            age = time.time() - mtime
            if age < self.ttl * 7:  # Eurostat data rarely changes → 7-day TTL
                try:
                    with open(cache_path) as f:
                        result = json.load(f)
                    _record_hit(func_name)
                    return {int(k): v for k, v in result.items()}
                except Exception:
                    pass

        _record_miss(func_name)
        result = self._fetch_eurostat_raw(country_code, crop_code)
        try:
            with open(cache_path, 'w') as f:
                json.dump({str(k): v for k, v in result.items()}, f)
        except Exception:
            pass
        return result

    def _fetch_eurostat_raw(self, country_code, crop_code):
        """Direkter Eurostat API-Aufruf."""
        import urllib.request
        url = (f"https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
               f"apro_cpshr?format=JSON&lang=EN&crops={crop_code}&"
               f"strucpro=YLD_HUMD_EU_T_HA&geo={country_code}")
        req = urllib.request.Request(url, headers={"User-Agent": "crop-mcp/4.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            d = json.loads(resp.read().decode())
        vals = d.get("value", {})
        time_idx = d.get("dimension", {}).get("time", {}).get("category", {}).get("index", {})
        time_pos = {v: k for k, v in time_idx.items()}
        return {int(time_pos.get(int(pos_str), "?")): float(val) for pos_str, val in vals.items()}

    def clear(self):
        """Leere den gesamten Cache."""
        import shutil
        if self.cache_dir.exists():
            shutil.rmtree(str(self.cache_dir))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._in_memory.clear()
        print(f"✅ Cache geleert: {self.cache_dir}")

    def print_stats(self):
        """Gib aktuelle Caching-Statistiken aus."""
        total = _stats["hits"] + _stats["misses"]
        ratio = _stats["hits"] / max(total, 1) * 100
        print(f"\n{'='*50}")
        print(f"📊 CACHE STATISTIKEN")
        print(f"{'='*50}")
        print(f"  Hits:  {_stats['hits']}")
        print(f"  Misses: {_stats['misses']}")
        print(f"  Total:  {total}")
        print(f"  Hit-Rate: {ratio:.1f}%")
        print(f"  Miss-Rate: {100 - ratio:.1f}%")
        print()
        if _stats["by_function"]:
            print(f"  {'Function':<25} {'Hits':<8} {'Misses':<8} {'Rate':<8}")
            print(f"  {'-'*25} {'-'*8} {'-'*8} {'-'*8}")
            for fn, s in sorted(_stats["by_function"].items()):
                ft = s["hits"] + s["misses"]
                fr = s["hits"] / max(ft, 1) * 100
                print(f"  {fn:<25} {s['hits']:<8} {s['misses']:<8} {fr:.0f}%")
        print(f"{'='*50}\n")


# ── Wrapper für build_europe.py ──

def patch_build_europe():
    """
    Erstelle eine gepatchte Version von build_one_sample,
    die den PowerCache nutzt statt direkter API-Aufrufe.
    Ruft build_europe mit caching-optimierter Ausführung auf.
    """
    cache = PowerCache()

    # Modifiziere die relevanten Funktionen via Import-Hook
    import crop_mcp.sources.power as power_mod

    original_get_power = power_mod.get_power_data

    def cached_get_power(lat, lon, start, end, params=None):
        if params is None:
            params = [power_mod.SOLAR_PARAM, power_mod.SOIL_M1]
        return cache.get_power_data(lat, lon, start, end, params)

    # Monkey-Patch: Ersetze get_power_data mit gecachter Version
    power_mod.get_power_data = cached_get_power
    print("🔧 PowerCache aktiv: get_power_data → cached version")
    return cache


# ── Ausführungs-Optimierung ──

def run_with_parallel_build(crop_name="wheat"):
    """
    Führe build_europe.py aus mit:
    - Parallelisierte Eurostat-Fetches
    - Gecachten POWER-Daten
    - Parallelisierte Sample-Generierung
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import build_europe as be

    # Patch PowerCache ein
    cache = patch_build_europe()

    # Crop-Parameter setzen
    eurostat_code = be.EUROSTAT_CROP_CODES.get(crop_name)
    if not eurostat_code:
        print(f"❌ Unbekannte Crop: {crop_name}")
        sys.exit(1)

    crop_countries = be.CROP_COUNTRIES.get(crop_name, be.COUNTRIES)
    crop = be.get_crop(crop_name)

    print(f"\n{'='*60}")
    print(f"🚀 OPTIMIZED BUILD: {crop_name.upper()} — {len(crop_countries)} countries")
    print(f"{'='*60}")

    # ── Schritt 1: Parallelisierte Eurostat-Fetches ──
    print(f"\n▶ Step 1: Eurostat yields ({len(crop_countries)} countries, parallel)")
    country_yields = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        fut_map = {
            ex.submit(cache.get_eurostat_yields, c, eurostat_code): c
            for c in crop_countries
        }
        for fut in as_completed(fut_map):
            c = fut_map[fut]
            try:
                country_yields[c] = fut.result()
                print(f"  {c}: {len(country_yields[c])} years ✓")
            except Exception as e:
                print(f"  {c}: ERROR — {str(e)[:50]}")

    # ── Schritt 2: Parallelisierte Feature-Generierung ──
    print(f"\n▶ Step 2: Features (parallel per region×year)")
    all_features = []
    lock = __import__('threading').Lock()

    def build_sample_task(cntry, reg_code, year):
        """Wrapper für build_one_sample."""
        try:
            region = be.get_region(reg_code)
            season_start = date(year - 1, crop.planting_month, 1)
            ref_date = date(year, 5, 1)
            if ref_date < season_start:
                return None
            sample = be.build_one_sample(cntry, reg_code, year, crop)
            return sample
        except Exception:
            return None

    total_tasks = 0
    task_list = []
    for cntry in crop_countries:
        yields = country_yields.get(cntry, {})
        regions = be.countries_with_regions.get(cntry, [])
        for reg_code in regions:
            for year in sorted(yields.keys()):
                task_list.append((cntry, reg_code, year))
                total_tasks += 1

    print(f"  {total_tasks} total tasks (regions × years)")
    batch_size = 50
    successes = 0
    failures = 0

    for batch_start in range(0, len(task_list), batch_size):
        batch = task_list[batch_start:batch_start + batch_size]
        with ThreadPoolExecutor(max_workers=10) as ex:
            fut_map = {
                ex.submit(build_sample_task, c, r, y): (c, r, y)
                for c, r, y in batch
            }
            for fut in as_completed(fut_map):
                sample = fut.result()
                if sample:
                    with lock:
                        all_features.append(sample)
                        successes += 1
                else:
                    failures += 1

        # Checkpoint alle batch_size Samples
        if len(all_features) % 50 == 0:
            print(f"    ... {len(all_features)} total (✓{successes} ✗{failures})")

    # ── Final: Save ──
    output_path = f'/home/j/crop-mcp/europe_training_data_{crop_name}.json'
    with open(output_path, 'w') as f:
        json.dump(all_features, f, indent=2)

    countries_ok = sorted(set(s['country'] for s in all_features))
    print(f"\n{'='*50}")
    print(f"✅ COMPLETE! {len(all_features)} samples → {output_path}")
    print(f"   Countries with data: {countries_ok}")

    # Cache-Statistiken ausgeben
    cache.print_stats()


# ── CLI ──

if __name__ == '__main__':
    import sys

    if "--clear" in sys.argv:
        cache = PowerCache()
        cache.clear()
        sys.exit(0)

    if "--stats" in sys.argv:
        cache = PowerCache()
        cache.print_stats()
        sys.exit(0)

    # Normal run: optimize build
    crop = "wheat"
    for i, arg in enumerate(sys.argv):
        if arg == "--crop" and i + 1 < len(sys.argv):
            crop = sys.argv[i + 1]

    run_with_parallel_build(crop)
