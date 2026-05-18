# crop-mcp: EU Crop Intelligence for AI Agents
from .europe_model_api import predict_europe_yield, get_available_countries
from .market_prices import get_market_price, calculate_revenue, get_production_cost, REFERENCE_PRICES
from .server import TOOLS

__version__ = "5.4.3"

# Forecast Anchoring (OpenTimestamps)
from .anchor import anchor_forecast
