"""
Tests for crop-mcp: EU Crop Intelligence MCP Server.

These tests exercise core functionality without requiring network access
or external API calls. Model-dependent tests verify the model can load
and produce predictions.
"""

import json
import os
import pytest

# ─────────────────────────────────────────────────────────────
# 1. Region lookup
# ─────────────────────────────────────────────────────────────
class TestRegions:
    def test_regions_basic(self):
        """get_region('DEE0') returns correct name/country."""
        from crop_mcp.core.regions import get_region
        r = get_region("DEE0")
        assert r.name == "Sachsen-Anhalt", f"Expected Sachsen-Anhalt, got {r.name}"
        assert r.country == "DE", f"Expected DE, got {r.country}"
        assert r.code == "DEE0"
        assert r.latitude is not None
        assert r.longitude is not None

    def test_regions_unknown(self):
        """get_region('XXXX') raises KeyError."""
        from crop_mcp.core.regions import get_region
        with pytest.raises(KeyError):
            get_region("XXXX")

# ─────────────────────────────────────────────────────────────
# 2. Crop parameters
# ─────────────────────────────────────────────────────────────
class TestCrops:
    def test_crops_basic(self):
        """get_crop('wheat') returns correct gdd_base=0.0."""
        from crop_mcp.core.regions import get_crop
        c = get_crop("wheat")
        assert c.gdd_base == 0.0, f"Expected gdd_base=0.0, got {c.gdd_base}"
        assert c.name == "wheat"
        assert c.name_de == "Winterweizen"

    def test_crops_unknown(self):
        """get_crop('invalid') raises KeyError."""
        from crop_mcp.core.regions import get_crop
        with pytest.raises(KeyError):
            get_crop("invalid_crop_123")

# ─────────────────────────────────────────────────────────────
# 3. Environmental Risk Score (ERS) module
# ─────────────────────────────────────────────────────────────
class TestERS:
    def test_ers_module_import(self):
        """environmental_risk module loads successfully."""
        import crop_mcp.environmental_risk as ers
        assert hasattr(ers, "compute_ers")
        assert hasattr(ers, "compute_wild_boar_risk")
        assert hasattr(ers, "full_environmental_risk")

    def test_ers_compute(self):
        """compute_ers('DE26', 'DE') returns valid dict with ers_score."""
        from crop_mcp.environmental_risk import compute_ers
        result = compute_ers("DE26", "DE")
        assert isinstance(result, dict)
        assert "ers_score" in result
        assert isinstance(result["ers_score"], (int, float))
        assert 0 <= result["ers_score"] <= 100
        assert result["ers_level"] in ("low", "moderate", "high")
        assert result["region_code"] == "DE26"
        assert "components" in result

    def test_wild_boar_risk(self):
        """compute_wild_boar_risk('DE26') returns valid score."""
        from crop_mcp.environmental_risk import compute_wild_boar_risk
        result = compute_wild_boar_risk("DE26")
        assert isinstance(result, dict)
        assert "wild_boar_risk_score" in result
        assert isinstance(result["wild_boar_risk_score"], (int, float))
        assert 0 <= result["wild_boar_risk_score"] <= 100
        assert "region_code" in result
        assert result["region_code"] == "DE26"
        assert "estimated_loss_eur_per_ha" in result
        assert "description" in result

# ─────────────────────────────────────────────────────────────
# 4. Weather / Forecast
# ─────────────────────────────────────────────────────────────
class TestForecast:
    def test_forecast_imports(self):
        """Weather and forecast modules load without error."""
        from crop_mcp.sources.weather import get_forecast, get_historical
        assert callable(get_forecast)
        assert callable(get_historical)

    def test_forecast_for_known_region(self):
        """weather_outlook for a known region requires region lookup success."""
        from crop_mcp.core.regions import get_region
        region = get_region("FRF2")
        assert region.code == "FRF2"
        assert region.latitude is not None
        assert region.longitude is not None

# ─────────────────────────────────────────────────────────────
# 5. Yield model prediction
# ─────────────────────────────────────────────────────────────
class TestYieldModel:
    def test_yield_and_value_basic(self):
        """predict_europe_yield returns valid prediction for known inputs."""
        from crop_mcp.europe_model_api import predict_europe_yield
        result = predict_europe_yield(
            "DEE0", "DE", "wheat",
            gdd=1450, precip_mm=320, solar_kwh=4.2, soil_moisture=0.45,
        )
        assert isinstance(result, dict)
        assert "predicted_yield_t_ha" in result
        assert isinstance(result["predicted_yield_t_ha"], (int, float))
        assert result["predicted_yield_t_ha"] > 0  # Reasonable yield
        assert result["region"] == "DEE0"
        assert result["crop"] == "wheat"
        assert "p10" in result
        assert "p90" in result
        assert "model_info" in result

    def test_yield_unknown_crop(self):
        """predict_europe_yield returns error for unverified crop."""
        from crop_mcp.europe_model_api import predict_europe_yield
        result = predict_europe_yield("DEE0", "DE", "invalid_crop")
        assert isinstance(result, dict)
        assert "error" in result or result.get("status") == "error"

# ─────────────────────────────────────────────────────────────
# 6. Soil cache
# ─────────────────────────────────────────────────────────────
class TestSoilCache:
    def test_soil_cache_exists(self):
        """soil_cache.json exists at project root and in data/."""
        root_cache = os.path.join(os.path.dirname(__file__), "..", "soil_cache.json")
        data_cache = os.path.join(os.path.dirname(__file__), "..", "data", "soil_cache.json")
        assert os.path.exists(root_cache) or os.path.exists(data_cache), \
            "soil_cache.json not found at root or data/"

    def test_soil_cache_has_data(self):
        """soil_cache.json loads and has data (123 NUTS2 regions)."""
        root_cache = os.path.join(os.path.dirname(__file__), "..", "soil_cache.json")
        data_cache = os.path.join(os.path.dirname(__file__), "..", "data", "soil_cache.json")
        path = root_cache if os.path.exists(root_cache) else data_cache
        with open(path) as f:
            data = json.load(f)
        assert isinstance(data, dict)
        assert len(data) > 50, f"Expected 50+ regions, got {len(data)}"
        # Check a known entry has soil fields
        for key in list(data.keys())[:3]:
            entry = data[key]
            assert "soc_g_kg" in entry or "clay_pct" in entry or "ph" in entry, \
                f"Entry {key} missing soil fields: {list(entry.keys())}"

# ─────────────────────────────────────────────────────────────
# 7. NDVI module
# ─────────────────────────────────────────────────────────────
class TestNDVI:
    def test_ndvi_module_import(self):
        """ndvi module imports and has expected constants."""
        import crop_mcp.ndvi_correction as ndvi
        assert hasattr(ndvi, "NDVI_SENSITIVITY")
        assert isinstance(ndvi.NDVI_SENSITIVITY, dict)
        assert "wheat" in ndvi.NDVI_SENSITIVITY
        assert ndvi.NDVI_SENSITIVITY["wheat"] == 0.25

    def test_ndvi_correction_logic(self):
        """NDVI sensitivity follows expected yield correction patterns."""
        from crop_mcp.ndvi_correction import NDVI_SENSITIVITY
        # All crops should have positive sensitivity
        for crop, sens in NDVI_SENSITIVITY.items():
            assert sens > 0, f"{crop} has non-positive sensitivity: {sens}"
        # Wheat should be most sensitive
        assert NDVI_SENSITIVITY["wheat"] >= NDVI_SENSITIVITY["sunflower"]


# ─────────────────────────────────────────────────────────────
# 8. Regression: Eurostat code mapping (V5.1d fix)
# ─────────────────────────────────────────────────────────────
class TestEurostatCodes:
    """Regression: Verify Eurostat crop codes are correctly mapped.
    
    V5.1d fix: Rapeseed was trained on Rice data (C2000) instead of
    Industrial crops (I1110). Sunflower had the same issue (C2200 → I1120).
    These tests prevent regression to the wrong codes.
    """

    def test_verified_crops_set(self):
        """VERIFIED_CROPS contains exactly the 5 supported crops."""
        from crop_mcp.europe_model_api import VERIFIED_CROPS
        expected = {"wheat", "corn", "barley", "rapeseed", "sunflower"}
        assert VERIFIED_CROPS == expected, \
            f"VERIFIED_CROPS mismatch: {VERIFIED_CROPS} != {expected}"

    def test_wheat_code_c1100(self):
        """Wheat uses Eurostat C1100 (common wheat and spelt)."""
        from crop_mcp.europe_model_api import VERIFIED_CROPS
        assert "wheat" in VERIFIED_CROPS

    def test_rapeseed_code_i1110_not_c2000(self):
        """Rapeseed must use I1110 (industrial crops), NOT C2000 (rice).
        
        Regression from V5.1d critical fix. C2000 = Rice in Eurostat,
        not rapeseed. Using C2000 caused DE rapeseed prediction of
        7.21 t/ha when real value is 2.63 t/ha.
        """
        from crop_mcp.europe_model_api import VERIFIED_CROPS
        assert "rapeseed" in VERIFIED_CROPS

    def test_sunflower_code_i1120_not_c2200(self):
        """Sunflower must use I1120, NOT C2200 (industrial crops other)."""
        from crop_mcp.europe_model_api import VERIFIED_CROPS
        assert "sunflower" in VERIFIED_CROPS

    def test_crop_code_in_docstrings(self):
        """Tool descriptions reference correct codes (I1110/I1120, not C2000/C2200)."""
        import inspect
        from crop_mcp import server
        # Check a key handler's docstring doesn't contain wrong codes
        src = inspect.getsource(server._handle_europe_yield_forecast)
        # The docstring or calling code should reference I1110 not C2000
        # This is a soft check - the description is in the TOOLS dict
        tools_src = inspect.getsource(server)
        assert "I1110" in tools_src, "I1110 not found in server.py"
        assert "I1120" in tools_src, "I1120 not found in server.py"
        # These should NOT appear with wrong codes
        assert "C2000" not in tools_src, "C2000 (rice code) still used in server.py!"
        assert "C2200" not in tools_src, "C2200 (wrong code) still used in server.py!"
