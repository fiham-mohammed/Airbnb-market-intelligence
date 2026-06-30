"""
Project configuration.

Centralizing paths and city metadata here means the ingestion pipeline
can be pointed at a different city later by changing only this file
(see Section 3.5 'configurable pipeline' requirement in the assignment).
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Project root and directory layout
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]

RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
REPORTS_DIR = PROJECT_ROOT / "reports"
SQL_DIR = PROJECT_ROOT / "sql"

DUCKDB_PATH = PROCESSED_DIR / "edinburgh_airbnb.duckdb"

# ---------------------------------------------------------------------------
# City configuration
# ---------------------------------------------------------------------------
CITY_CONFIG = {
    "city_name": "Edinburgh",
    "country": "United Kingdom",
    "region": "Scotland",
    "snapshot_date": "2025-09-21",
    "source_url": "https://insideairbnb.com/edinburgh/",
    "files": {
        "listings": RAW_DIR / "listings.csv",
        "calendar": RAW_DIR / "calendar.csv",
        "reviews": RAW_DIR / "reviews.csv",
        "neighbourhoods": RAW_DIR / "neighbourhoods.csv",
        "neighbourhoods_geojson": RAW_DIR / "neighbourhoods.geojson",
    },
}

# Columns we expect to be price-like and need currency-symbol stripping
PRICE_COLUMNS = {
    "listings": ["price"],
    "calendar": ["price", "adjusted_price"],
}

# Columns we expect to be boolean-like ("t"/"f" strings in Inside Airbnb exports)
BOOLEAN_TF_COLUMNS = [
    "host_is_superhost",
    "host_has_profile_pic",
    "host_identity_verified",
    "has_availability",
    "instant_bookable",
]

# Domain validation rules used in profiling / data quality checks
VALIDATION_RULES = {
    "price_min": 0,
    "price_max": 10000,  # generous ceiling; flagged not dropped beyond this
    "latitude_range": (-90, 90),
    "longitude_range": (-180, 180),
    "min_nights_floor": 1,
}
