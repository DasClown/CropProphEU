"""
Crop and region parameter definitions.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# ─────────────────────────────────────────────────────────────
# Crop parameters
# ─────────────────────────────────────────────────────────────

@dataclass
class CropParams:
    """Crop-specific agronomic parameters."""
    name: str
    name_de: str
    gdd_base: float             # Base temperature for GDD calculation (°C)
    gdd_optimum: float          # Optimal GDD range
    gdd_maximum: float          # Maximum useful GDD
    planting_month: int         # Typical planting month (1-12)
    harvest_month: int          # Typical harvest month (1-12)
    frost_sensitive: bool       # Damaged by frost?
    water_sensitivity: str      # "low", "medium", "high"
    description: str

CROPS: Dict[str, CropParams] = {
    "wheat": CropParams(
        name="wheat",
        name_de="Winterweizen",
        gdd_base=0.0,
        gdd_optimum=2000.0,
        gdd_maximum=2800.0,
        planting_month=10,
        harvest_month=7,
        frost_sensitive=False,
        water_sensitivity="medium",
        description="Winter wheat (Triticum aestivum). EU's most widely grown crop. "
                    "GDD base 0°C. Optimal 2000-2500 GDD. Key regions: France, Germany, Poland."
    ),
    "corn": CropParams(
        name="corn",
        name_de="Mais",
        gdd_base=10.0,
        gdd_optimum=2600.0,
        gdd_maximum=3200.0,
        planting_month=4,
        harvest_month=10,
        frost_sensitive=True,
        water_sensitivity="high",
        description="Grain maize (Zea mays). GDD base 10°C. Needs warm summers. "
                    "Key regions: Romania, France, Hungary, Italy."
    ),
    "rapeseed": CropParams(
        name="rapeseed",
        name_de="Raps",
        gdd_base=5.0,
        gdd_optimum=1800.0,
        gdd_maximum=2400.0,
        planting_month=8,
        harvest_month=7,
        frost_sensitive=False,
        water_sensitivity="medium",
        description="Winter oilseed rape (Brassica napus). EU's main oilseed. "
                    "GDD base 5°C. Key regions: Germany, France, Poland."
    ),
    "sunflower": CropParams(
        name="sunflower",
        name_de="Sonnenblume",
        gdd_base=7.0,
        gdd_optimum=2200.0,
        gdd_maximum=2800.0,
        planting_month=4,
        harvest_month=9,
        frost_sensitive=True,
        water_sensitivity="low",
        description="Sunflower (Helianthus annuus). Drought-tolerant oilseed. "
                    "GDD base 7°C. Key regions: Ukraine, Romania, Bulgaria, Hungary."
    ),
    "barley": CropParams(
        name="barley",
        name_de="Wintergerste",
        gdd_base=0.0,
        gdd_optimum=1800.0,
        gdd_maximum=2500.0,
        planting_month=10,
        harvest_month=7,
        frost_sensitive=False,
        water_sensitivity="medium",
        description="Winter barley (Hordeum vulgare). GDD base 0°C. "
                    "Earlier harvest than wheat. Key regions: Spain, France, Germany, UK."
    ),
}


# ─────────────────────────────────────────────────────────────
# EU NUTS2 region definitions (key agricultural zones)
# ─────────────────────────────────────────────────────────────

@dataclass
class Region:
    code: str
    name: str
    country: str
    latitude: float          # Centroid lat
    longitude: float         # Centroid lon
    altitude: float          # Average elevation (m)
    major_crops: List[str]   # What's grown here
    area_km2: Optional[float] = None

REGIONS: Dict[str, Region] = {
    # ── France ──
    "FRF2": Region(code="FRF2", name="Picardie", country="FR", latitude=49.5, longitude=2.6, altitude=80, major_crops=["wheat", "barley", "corn"], area_km2=19399),
    "FRF1": Region(code="FRF1", name="Champagne-Ardenne", country="FR", latitude=48.8, longitude=4.5, altitude=150, major_crops=["wheat", "barley", "rapeseed"], area_km2=25606),
    "FRF3": Region(code="FRF3", name="Haute-Normandie", country="FR", latitude=49.4, longitude=1.2, altitude=100, major_crops=["wheat", "barley", "rapeseed"], area_km2=12318),
    "FRB0": Region(code="FRB0", name="Centre-Val de Loire", country="FR", latitude=47.5, longitude=1.5, altitude=120, major_crops=["wheat", "corn", "rapeseed"], area_km2=39151),
    "FRH0": Region(code="FRH0", name="Bretagne", country="FR", latitude=48.1, longitude=-2.7, altitude=80, major_crops=["corn", "wheat"], area_km2=27508),
    "FRI0": Region(code="FRI0", name="Aquitaine", country="FR", latitude=44.6, longitude=-0.5, altitude=100, major_crops=["corn", "wheat"], area_km2=41308),
    "FRJ1": Region(code="FRJ1", name="Midi-Pyrénées", country="FR", latitude=43.8, longitude=1.5, altitude=300, major_crops=["wheat", "corn", "sunflower"], area_km2=45348),
    "FRG0": Region(code="FRG0", name="Pays de la Loire", country="FR", latitude=47.5, longitude=-1.0, altitude=60, major_crops=["corn", "wheat", "rapeseed"], area_km2=32082),

    # ── Germany ──
    "DE91": Region(code="DE91", name="Niedersachsen", country="DE", latitude=52.8, longitude=9.5, altitude=50, major_crops=["wheat", "corn", "rapeseed", "barley"], area_km2=47614),
    "DEE0": Region(code="DEE0", name="Sachsen-Anhalt", country="DE", latitude=51.9, longitude=11.7, altitude=80, major_crops=["wheat", "rapeseed", "barley"], area_km2=20451),
    "DED2": Region(code="DED2", name="Dresden", country="DE", latitude=51.2, longitude=13.5, altitude=150, major_crops=["wheat", "rapeseed", "corn"], area_km2=7930),
    "DE41": Region(code="DE41", name="Brandenburg", country="DE", latitude=52.5, longitude=13.0, altitude=60, major_crops=["wheat", "rapeseed", "corn"], area_km2=29654),
    "DE21": Region(code="DE21", name="Oberbayern", country="DE", latitude=48.3, longitude=11.8, altitude=500, major_crops=["wheat", "corn", "barley"], area_km2=17530),
    "DE22": Region(code="DE22", name="Niederbayern", country="DE", latitude=48.7, longitude=12.5, altitude=400, major_crops=["wheat", "corn"], area_km2=10330),
    "DE11": Region(code="DE11", name="Stuttgart", country="DE", latitude=48.9, longitude=9.4, altitude=350, major_crops=["wheat", "barley", "corn", "rapeseed"], area_km2=10558),
    "DE12": Region(code="DE12", name="Karlsruhe", country="DE", latitude=49.2, longitude=8.7, altitude=150, major_crops=["wheat", "corn", "barley", "rapeseed", "sunflower"], area_km2=6919),
    "DE13": Region(code="DE13", name="Freiburg", country="DE", latitude=48.2, longitude=8.5, altitude=600, major_crops=["wheat", "corn", "barley"], area_km2=9356),
    "DE14": Region(code="DE14", name="Tübingen", country="DE", latitude=48.3, longitude=9.6, altitude=500, major_crops=["wheat", "barley", "corn"], area_km2=8918),
    "DEF0": Region(code="DEF0", name="Schleswig-Holstein", country="DE", latitude=54.2, longitude=10.0, altitude=20, major_crops=["wheat", "rapeseed", "barley"], area_km2=15799),
    "DEG0": Region(code="DEG0", name="Thüringen", country="DE", latitude=50.9, longitude=11.0, altitude=300, major_crops=["wheat", "rapeseed", "barley"], area_km2=16171),
    "DE80": Region(code="DE80", name="Mecklenburg-Vorpommern", country="DE", latitude=53.8, longitude=12.5, altitude=30, major_crops=["wheat", "rapeseed"], area_km2=23295),
    # ── Hessen ──
    "DE71": Region(code="DE71", name="Darmstadt", country="DE", latitude=49.9, longitude=8.7, altitude=200, major_crops=["wheat", "corn", "rapeseed", "barley"], area_km2=7446),
    "DE72": Region(code="DE72", name="Gießen", country="DE", latitude=50.6, longitude=8.7, altitude=200, major_crops=["wheat", "barley", "corn", "rapeseed"], area_km2=5381),
    "DE73": Region(code="DE73", name="Kassel", country="DE", latitude=51.3, longitude=9.5, altitude=300, major_crops=["wheat", "barley", "rapeseed"], area_km2=5784),

    # ── Poland ──
    "PL41": Region(code="PL41", name="Wielkopolskie", country="PL", latitude=52.3, longitude=17.0, altitude=90, major_crops=["wheat", "corn", "rapeseed"], area_km2=29826),
    "PL12": Region(code="PL12", name="Mazowieckie", country="PL", latitude=52.2, longitude=21.2, altitude=110, major_crops=["wheat", "corn"], area_km2=35558),
    "PL51": Region(code="PL51", name="Dolnośląskie", country="PL", latitude=51.1, longitude=16.8, altitude=200, major_crops=["wheat", "rapeseed", "corn"], area_km2=19947),
    "PL61": Region(code="PL61", name="Kujawsko-Pomorskie", country="PL", latitude=53.1, longitude=18.5, altitude=60, major_crops=["wheat", "corn", "rapeseed"], area_km2=17972),
    "PL31": Region(code="PL31", name="Lubelskie", country="PL", latitude=51.2, longitude=23.0, altitude=180, major_crops=["wheat", "corn"], area_km2=25122),
    "PL42": Region(code="PL42", name="Zachodniopomorskie", country="PL", latitude=53.5, longitude=15.5, altitude=40, major_crops=["wheat", "rapeseed"], area_km2=22892),
    "PL63": Region(code="PL63", name="Pomorskie", country="PL", latitude=54.2, longitude=18.0, altitude=70, major_crops=["wheat", "rapeseed"], area_km2=18310),
    "PL52": Region(code="PL52", name="Opolskie", country="PL", latitude=50.6, longitude=17.9, altitude=200, major_crops=["wheat", "corn", "rapeseed"], area_km2=9412),

    # ── Romania ──
    "RO31": Region(code="RO31", name="Sud-Muntenia", country="RO", latitude=44.5, longitude=26.0, altitude=100, major_crops=["corn", "wheat", "sunflower"], area_km2=34489),
    "RO11": Region(code="RO11", name="Nord-Vest", country="RO", latitude=47.0, longitude=23.5, altitude=300, major_crops=["corn", "wheat"], area_km2=34153),
    "RO21": Region(code="RO21", name="Nord-Est", country="RO", latitude=47.0, longitude=26.5, altitude=250, major_crops=["wheat", "corn", "sunflower"], area_km2=36850),
    "RO12": Region(code="RO12", name="Centru", country="RO", latitude=46.3, longitude=24.5, altitude=400, major_crops=["corn", "wheat"], area_km2=34093),
    "RO41": Region(code="RO41", name="Sud-Vest Oltenia", country="RO", latitude=44.3, longitude=23.8, altitude=150, major_crops=["corn", "wheat", "sunflower"], area_km2=29212),
    "RO22": Region(code="RO22", name="Sud-Est", country="RO", latitude=44.8, longitude=28.0, altitude=50, major_crops=["wheat", "sunflower", "corn"], area_km2=35762),

    # ── Hungary ──
    "HU21": Region(code="HU21", name="Közép-Dunántúl", country="HU", latitude=47.0, longitude=18.0, altitude=150, major_crops=["corn", "wheat", "sunflower", "rapeseed"], area_km2=11016),
    "HU31": Region(code="HU31", name="Észak-Magyarország", country="HU", latitude=48.0, longitude=20.5, altitude=200, major_crops=["corn", "wheat"], area_km2=13245),
    "HU33": Region(code="HU33", name="Dél-Alföld", country="HU", latitude=46.5, longitude=19.8, altitude=90, major_crops=["corn", "wheat", "sunflower", "rapeseed"], area_km2=18169),
    "HU12": Region(code="HU12", name="Pest", country="HU", latitude=47.3, longitude=19.2, altitude=110, major_crops=["wheat", "corn"], area_km2=6394),

    # ── Italy ──
    "ITC4": Region(code="ITC4", name="Lombardia", country="IT", latitude=45.5, longitude=9.8, altitude=250, major_crops=["corn", "wheat"], area_km2=23863),
    "ITF5": Region(code="ITF5", name="Emilia-Romagna", country="IT", latitude=44.7, longitude=11.0, altitude=100, major_crops=["wheat", "corn", "sunflower"], area_km2=22453),
    "ITF3": Region(code="ITF3", name="Veneto", country="IT", latitude=45.6, longitude=12.0, altitude=50, major_crops=["corn", "wheat"], area_km2=18391),
    "ITC2": Region(code="ITC2", name="Piemonte", country="IT", latitude=45.2, longitude=7.8, altitude=300, major_crops=["corn", "wheat"], area_km2=25387),

    # ── Spain ──
    "ES61": Region(code="ES61", name="Andalucía", country="ES", latitude=37.5, longitude=-4.5, altitude=300, major_crops=["wheat", "barley", "sunflower"], area_km2=87599),
    "ES42": Region(code="ES42", name="Castilla y León", country="ES", latitude=41.8, longitude=-4.5, altitude=800, major_crops=["wheat", "barley", "corn"], area_km2=94224),
    "ES43": Region(code="ES43", name="Extremadura", country="ES", latitude=39.0, longitude=-6.0, altitude=300, major_crops=["corn", "wheat"], area_km2=41634),
    "ES24": Region(code="ES24", name="Aragón", country="ES", latitude=41.5, longitude=-0.5, altitude=400, major_crops=["barley", "wheat", "corn"], area_km2=47720),

    # ── Ukraine (critical for EU grain market) ──
    "UA11": Region(code="UA11", name="Odeska", country="UA", latitude=46.8, longitude=30.0, altitude=50, major_crops=["wheat", "sunflower", "barley", "corn"], area_km2=33310),
    "UA12": Region(code="UA12", name="Poltavska", country="UA", latitude=49.5, longitude=34.0, altitude=100, major_crops=["wheat", "corn", "sunflower"], area_km2=28750),
    "UA19": Region(code="UA19", name="Cherkaska", country="UA", latitude=49.3, longitude=32.0, altitude=120, major_crops=["wheat", "corn", "sunflower"], area_km2=20900),
    "UA16": Region(code="UA16", name="Kharkivska", country="UA", latitude=49.5, longitude=36.5, altitude=150, major_crops=["wheat", "sunflower", "corn"], area_km2=31400),
    "UA06": Region(code="UA06", name="Kyyivska", country="UA", latitude=50.0, longitude=30.5, altitude=150, major_crops=["wheat", "corn"], area_km2=28100),
    "UA04": Region(code="UA04", name="Zaporizka", country="UA", latitude=47.5, longitude=35.5, altitude=80, major_crops=["wheat", "sunflower"], area_km2=27180),
    "UA15": Region(code="UA15", name="Ternopilska", country="UA", latitude=49.5, longitude=25.5, altitude=300, major_crops=["wheat", "rapeseed", "corn"], area_km2=13823),
    "UA10": Region(code="UA10", name="Mykolaivska", country="UA", latitude=47.0, longitude=32.0, altitude=50, major_crops=["wheat", "sunflower", "barley"], area_km2=24598),

    # ── UK (key for wheat/barley) ──
    "UKH1": Region(code="UKH1", name="East of England", country="UK", latitude=52.2, longitude=0.5, altitude=20, major_crops=["wheat", "barley", "rapeseed"], area_km2=19381),
    "UKJ2": Region(code="UKJ2", name="South East", country="UK", latitude=51.2, longitude=-0.5, altitude=60, major_crops=["wheat", "barley"], area_km2=19095),
    "UKF1": Region(code="UKF1", name="Derbyshire & Nottinghamshire", country="UK", latitude=53.0, longitude=-1.2, altitude=100, major_crops=["wheat", "barley", "rapeseed"], area_km2=8050),
    "UKE0": Region(code="UKE0", name="Yorkshire & Humber", country="UK", latitude=53.8, longitude=-1.0, altitude=50, major_crops=["wheat", "barley", "rapeseed"], area_km2=15406),

    # ── Denmark ──
    "DK01": Region(code="DK01", name="Hovedstaden", country="DK", latitude=55.7, longitude=12.0, altitude=20, major_crops=["wheat", "barley", "rapeseed"], area_km2=2424),
    "DK02": Region(code="DK02", name="Sjælland", country="DK", latitude=55.5, longitude=11.5, altitude=20, major_crops=["wheat", "barley", "rapeseed"], area_km2=7273),
    "DK03": Region(code="DK03", name="Syddanmark", country="DK", latitude=55.3, longitude=9.5, altitude=20, major_crops=["wheat", "barley", "rapeseed", "corn"], area_km2=12191),
    "DK04": Region(code="DK04", name="Midtjylland", country="DK", latitude=56.2, longitude=9.5, altitude=40, major_crops=["wheat", "barley", "rapeseed"], area_km2=13005),
    "DK05": Region(code="DK05", name="Nordjylland", country="DK", latitude=57.0, longitude=10.0, altitude=20, major_crops=["wheat", "barley", "rapeseed"], area_km2=7874),

    # ── Bulgaria ──
    "BG31": Region(code="BG31", name="Severozapaden", country="BG", latitude=43.5, longitude=23.5, altitude=200, major_crops=["wheat", "corn", "sunflower"], area_km2=19173),
    "BG32": Region(code="BG32", name="Severen tsentralen", country="BG", latitude=43.2, longitude=25.5, altitude=150, major_crops=["wheat", "corn", "sunflower"], area_km2=14558),
    "BG33": Region(code="BG33", name="Severoiztochen", country="BG", latitude=43.5, longitude=27.0, altitude=100, major_crops=["wheat", "sunflower", "corn"], area_km2=14672),
    "BG34": Region(code="BG34", name="Yugoiztochen", country="BG", latitude=42.5, longitude=26.5, altitude=150, major_crops=["wheat", "sunflower", "corn"], area_km2=20819),
    "BG41": Region(code="BG41", name="Yugozapaden", country="BG", latitude=42.0, longitude=23.5, altitude=400, major_crops=["wheat", "corn"], area_km2=20477),

    # ── Czechia ──
    "CZ02": Region(code="CZ02", name="Střední Čechy", country="CZ", latitude=50.0, longitude=14.5, altitude=250, major_crops=["wheat", "rapeseed", "barley"], area_km2=11014),
    "CZ03": Region(code="CZ03", name="Jihozápad", country="CZ", latitude=49.3, longitude=13.5, altitude=400, major_crops=["wheat", "rapeseed", "barley"], area_km2=10794),
    "CZ04": Region(code="CZ04", name="Severozápad", country="CZ", latitude=50.3, longitude=13.5, altitude=300, major_crops=["wheat", "rapeseed", "barley"], area_km2=8836),
    "CZ05": Region(code="CZ05", name="Severovýchod", country="CZ", latitude=50.5, longitude=15.5, altitude=350, major_crops=["wheat", "rapeseed", "barley"], area_km2=9690),
    "CZ06": Region(code="CZ06", name="Jihovýchod", country="CZ", latitude=49.2, longitude=16.5, altitude=300, major_crops=["wheat", "rapeseed", "corn"], area_km2=9414),
    "CZ07": Region(code="CZ07", name="Střední Morava", country="CZ", latitude=49.5, longitude=17.3, altitude=250, major_crops=["wheat", "rapeseed", "corn"], area_km2=6394),

    # ── Austria ──
    "AT11": Region(code="AT11", name="Burgenland", country="AT", latitude=47.5, longitude=16.5, altitude=200, major_crops=["wheat", "corn", "rapeseed"], area_km2=3965),
    "AT12": Region(code="AT12", name="Niederösterreich", country="AT", latitude=48.3, longitude=15.5, altitude=300, major_crops=["wheat", "corn", "rapeseed"], area_km2=19186),
    "AT22": Region(code="AT22", name="Steiermark", country="AT", latitude=47.2, longitude=15.0, altitude=500, major_crops=["wheat", "corn"], area_km2=16401),
    "AT31": Region(code="AT31", name="Oberösterreich", country="AT", latitude=48.2, longitude=14.0, altitude=400, major_crops=["wheat", "corn"], area_km2=11982),

    # ── Netherlands ──
    "NL11": Region(code="NL11", name="Groningen", country="NL", latitude=53.2, longitude=6.6, altitude=2, major_crops=["wheat", "barley", "corn"], area_km2=2968),
    "NL21": Region(code="NL21", name="Overijssel", country="NL", latitude=52.4, longitude=6.5, altitude=5, major_crops=["wheat", "corn", "barley"], area_km2=3421),
    "NL22": Region(code="NL22", name="Gelderland", country="NL", latitude=52.0, longitude=5.9, altitude=10, major_crops=["wheat", "corn", "barley"], area_km2=5137),
    "NL33": Region(code="NL33", name="Zuid-Holland", country="NL", latitude=52.0, longitude=4.5, altitude=1, major_crops=["wheat", "barley"], area_km2=3419),
    "NL34": Region(code="NL34", name="Zeeland", country="NL", latitude=51.5, longitude=3.8, altitude=1, major_crops=["wheat", "barley", "corn"], area_km2=2934),
    "NL41": Region(code="NL41", name="Noord-Brabant", country="NL", latitude=51.6, longitude=5.2, altitude=10, major_crops=["corn", "wheat", "barley"], area_km2=5082),
    "NL42": Region(code="NL42", name="Limburg", country="NL", latitude=51.2, longitude=5.9, altitude=30, major_crops=["wheat", "corn", "barley"], area_km2=2209),

    # ── Belgium ──
    "BE21": Region(code="BE21", name="Antwerpen", country="BE", latitude=51.2, longitude=4.5, altitude=10, major_crops=["wheat", "barley", "corn"], area_km2=2867),
    "BE22": Region(code="BE22", name="Limburg", country="BE", latitude=51.0, longitude=5.3, altitude=30, major_crops=["wheat", "corn", "barley"], area_km2=2422),
    "BE23": Region(code="BE23", name="Oost-Vlaanderen", country="BE", latitude=51.1, longitude=3.8, altitude=5, major_crops=["wheat", "barley", "corn"], area_km2=2982),
    "BE24": Region(code="BE24", name="Vlaams-Brabant", country="BE", latitude=50.9, longitude=4.8, altitude=20, major_crops=["wheat", "barley", "corn"], area_km2=2106),
    "BE25": Region(code="BE25", name="West-Vlaanderen", country="BE", latitude=51.0, longitude=3.0, altitude=5, major_crops=["wheat", "barley", "corn", "rapeseed"], area_km2=3250),
    "BE32": Region(code="BE32", name="Hainaut", country="BE", latitude=50.5, longitude=3.8, altitude=50, major_crops=["wheat", "barley", "corn"], area_km2=3800),
    "BE33": Region(code="BE33", name="Liège", country="BE", latitude=50.6, longitude=5.5, altitude=150, major_crops=["wheat", "barley"], area_km2=3862),
    "BE35": Region(code="BE35", name="Namur", country="BE", latitude=50.3, longitude=5.0, altitude=100, major_crops=["wheat", "barley"], area_km2=3665),

    # ── Slovakia ──
    "SK02": Region(code="SK02", name="Západné Slovensko", country="SK", latitude=48.3, longitude=17.8, altitude=150, major_crops=["wheat", "corn", "barley", "rapeseed"], area_km2=14845),
    "SK04": Region(code="SK04", name="Východné Slovensko", country="SK", latitude=48.8, longitude=21.5, altitude=200, major_crops=["wheat", "corn", "barley"], area_km2=15933),

    # ── Sweden ──
    "SE22": Region(code="SE22", name="Sydsverige", country="SE", latitude=56.0, longitude=14.0, altitude=100, major_crops=["wheat", "barley", "rapeseed"], area_km2=13894),
    "SE23": Region(code="SE23", name="Västsverige", country="SE", latitude=57.5, longitude=13.0, altitude=150, major_crops=["wheat", "barley", "rapeseed"], area_km2=29113),
    "SE12": Region(code="SE12", name="Östra Mellansverige", country="SE", latitude=59.0, longitude=17.0, altitude=50, major_crops=["wheat", "barley", "rapeseed"], area_km2=39096),

    # ── Portugal ──
    "PT18": Region(code="PT18", name="Alentejo", country="PT", latitude=38.5, longitude=-7.5, altitude=200, major_crops=["wheat", "barley", "corn", "sunflower"], area_km2=31605),
    "PT11": Region(code="PT11", name="Norte", country="PT", latitude=41.5, longitude=-7.5, altitude=400, major_crops=["corn", "wheat", "barley"], area_km2=21278),
    "PT16": Region(code="PT16", name="Centro", country="PT", latitude=40.0, longitude=-7.5, altitude=300, major_crops=["wheat", "corn", "barley"], area_km2=28200),
    "PT17": Region(code="PT17", name="Área Metropolitana de Lisboa", country="PT", latitude=38.8, longitude=-9.0, altitude=100, major_crops=["wheat", "corn"], area_km2=3002),

    # ── Greece ──
    "EL52": Region(code="EL52", name="Kentriki Makedonia", country="EL", latitude=40.8, longitude=22.5, altitude=100, major_crops=["wheat", "corn", "sunflower", "barley"], area_km2=18810),
    "EL61": Region(code="EL61", name="Thessalia", country="EL", latitude=39.5, longitude=22.0, altitude=100, major_crops=["wheat", "corn", "barley", "sunflower"], area_km2=14037),
    "EL51": Region(code="EL51", name="Anatoliki Makedonia, Thraki", country="EL", latitude=41.0, longitude=25.0, altitude=200, major_crops=["wheat", "sunflower", "corn", "barley"], area_km2=14157),
    "EL65": Region(code="EL65", name="Peloponnisos", country="EL", latitude=37.5, longitude=22.0, altitude=300, major_crops=["wheat", "barley", "sunflower"], area_km2=15490),

    # ── Ireland ──
    "IE05": Region(code="IE05", name="Southern", country="IE", latitude=52.0, longitude=-8.5, altitude=100, major_crops=["barley", "wheat", "rapeseed"], area_km2=24897),
    "IE06": Region(code="IE06", name="Eastern & Midland", country="IE", latitude=53.3, longitude=-7.0, altitude=80, major_crops=["barley", "wheat", "rapeseed"], area_km2=20062),

    # ── Croatia ──
    "HR02": Region(code="HR02", name="Panonska Hrvatska", country="HR", latitude=45.5, longitude=17.0, altitude=150, major_crops=["wheat", "corn", "sunflower", "barley"], area_km2=12555),
    "HR03": Region(code="HR03", name="Jadranska Hrvatska", country="HR", latitude=43.5, longitude=16.5, altitude=200, major_crops=["corn", "wheat", "barley"], area_km2=24548),

    # ── Slovenia ──
    "SI03": Region(code="SI03", name="Vzhodna Slovenija", country="SI", latitude=46.3, longitude=15.5, altitude=250, major_crops=["wheat", "corn", "barley"], area_km2=10575),
    "SI04": Region(code="SI04", name="Zahodna Slovenija", country="SI", latitude=46.0, longitude=14.0, altitude=400, major_crops=["wheat", "corn"], area_km2=9420),

    # ── Lithuania ──
    "LT02": Region(code="LT02", name="Vidurio ir vakaru Lietuvos regionas", country="LT", latitude=55.5, longitude=23.0, altitude=80, major_crops=["wheat", "barley", "rapeseed"], area_km2=57561),

    # ── Latvia ──
    "LV00": Region(code="LV00", name="Latvija", country="LV", latitude=56.8, longitude=24.5, altitude=100, major_crops=["wheat", "barley", "rapeseed"], area_km2=64573),

    # ── Estonia ──
    "EE00": Region(code="EE00", name="Eesti", country="EE", latitude=58.6, longitude=25.0, altitude=60, major_crops=["wheat", "barley", "rapeseed"], area_km2=45228),

    # ── Finland ──
    "FI19": Region(code="FI19", name="Länsi-Suomi", country="FI", latitude=62.0, longitude=23.0, altitude=100, major_crops=["barley", "wheat", "rapeseed"], area_km2=46607),
    "FI1C": Region(code="FI1C", name="Etelä-Suomi", country="FI", latitude=60.5, longitude=25.0, altitude=50, major_crops=["barley", "wheat", "rapeseed"], area_km2=34180),

    # ── Cyprus ──
    "CY00": Region(code="CY00", name="Kypros", country="CY", latitude=35.0, longitude=33.0, altitude=200, major_crops=["wheat", "barley"], area_km2=9251),

    # ── Malta ──
    "MT00": Region(code="MT00", name="Malta", country="MT", latitude=35.9, longitude=14.4, altitude=100, major_crops=["wheat", "barley"], area_km2=316),
}


def get_region(code: str) -> Region:
    """Look up a region by NUTS2 code."""
    if code not in REGIONS:
        raise KeyError(f"Unknown region: {code}. Available: {list(REGIONS.keys())[:10]}...")
    return REGIONS[code]


def get_crop(name: str) -> CropParams:
    """Look up a crop by name."""
    if name not in CROPS:
        raise KeyError(f"Unknown crop: {name}. Available: {list(CROPS.keys())}")
    return CROPS[name]


def list_regions(country: Optional[str] = None) -> Dict[str, Region]:
    """List regions, optionally filtered by country code."""
    if country:
        return {k: v for k, v in REGIONS.items() if v.country == country}
    return REGIONS


def list_crops() -> Dict[str, CropParams]:
    return dict(CROPS)
