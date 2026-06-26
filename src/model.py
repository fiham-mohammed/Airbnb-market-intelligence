"""
model.py
--------
Data Engineering Challenge — Section 3.4: Data Modeling

Builds a star-schema dimensional model in DuckDB on top of the cleaned
listings data and the raw calendar/reviews tables already loaded by
ingest.py.

Design (see Decision 11 in the Decision Log for full rationale):

    dim_neighbourhood ──┐
                         │
    dim_host ────────────┼──► fact_listing ◄── dim_date
                         │         │
                         │         └──► (joins to calendar_raw, reviews_raw
                         │              by listing_id for time-series queries)
                         │
    fact_listing is the central fact table: one row per listing, with
    measures (price, review scores, occupancy estimate) and foreign keys
    out to the dimension tables.

Why a single fact table rather than separate listing/host/calendar facts:
this dataset's natural grain is "one listing," and host/neighbourhood
attributes are slowly-changing-dimension-style descriptive attributes of
that listing, not independent measurable events. calendar_raw and
reviews_raw remain as separate large tables (not modeled as new fact
tables) because they're already at their natural grain
(listing x day, and one row per review) and don't need restructuring --
they just need a clean foreign key back to fact_listing.id, which they
already have via listing_id.
"""

from __future__ import annotations

import logging

import duckdb
import pandas as pd

from clean import clean_listings
from config import CITY_CONFIG, PROCESSED_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("model")


def build_dim_neighbourhood(con: duckdb.DuckDBPyConnection) -> None:
    """Neighbourhood dimension: one row per neighbourhood, sourced from neighbourhoods.csv."""
    path = CITY_CONFIG["files"]["neighbourhoods"]
    con.execute(
        f"""
        CREATE OR REPLACE TABLE dim_neighbourhood AS
        SELECT
            ROW_NUMBER() OVER () AS neighbourhood_key,
            neighbourhood AS neighbourhood_name,
            neighbourhood_group
        FROM read_csv_auto('{path}', header=True)
        """
    )
    n = con.execute("SELECT COUNT(*) FROM dim_neighbourhood").fetchone()[0]
    logger.info("Built dim_neighbourhood: %d rows", n)


def build_dim_host(con: duckdb.DuckDBPyConnection, listings_clean: pd.DataFrame) -> None:
    """
    Host dimension: one row per unique host, derived from listings (no
    separate hosts file exists in the source -- see Day 1 schema notes).
    We deduplicate on host_id and take the most descriptive non-null value
    per attribute, since a host's name/since-date/superhost-status should
    be the same across all of a host's listings but isn't always populated
    identically on every row.
    """
    host_cols = [
        "host_id", "host_name", "host_since", "host_location",
        "host_response_time", "host_response_rate", "host_acceptance_rate",
        "host_is_superhost", "host_listings_count", "host_identity_verified",
    ]
    host_df = listings_clean[host_cols].copy()
    # groupby + first non-null per host_id
    dim_host = host_df.groupby("host_id", as_index=False).first()
    dim_host.insert(0, "host_key", range(1, len(dim_host) + 1))

    con.register("dim_host_tmp", dim_host)
    con.execute("CREATE OR REPLACE TABLE dim_host AS SELECT * FROM dim_host_tmp")
    n = con.execute("SELECT COUNT(*) FROM dim_host").fetchone()[0]
    logger.info("Built dim_host: %d unique hosts", n)


def build_dim_date(con: duckdb.DuckDBPyConnection) -> None:
    """
    Date dimension spanning the calendar.csv date range (Sept 2025 - Sept
    2026), with day-of-week and month/season attributes pre-computed so
    seasonal EDA (Section 4.3) doesn't need to recompute these from a raw
    date column in every query.
    """
    con.execute(
        """
        CREATE OR REPLACE TABLE dim_date AS
        SELECT
            d AS date_key,
            EXTRACT(YEAR FROM d) AS year,
            EXTRACT(MONTH FROM d) AS month,
            EXTRACT(DOW FROM d) AS day_of_week,         -- 0=Sunday
            CASE WHEN EXTRACT(DOW FROM d) IN (0, 6) THEN TRUE ELSE FALSE END AS is_weekend,
            CASE
                WHEN EXTRACT(MONTH FROM d) IN (12, 1, 2) THEN 'Winter'
                WHEN EXTRACT(MONTH FROM d) IN (3, 4, 5) THEN 'Spring'
                WHEN EXTRACT(MONTH FROM d) IN (6, 7, 8) THEN 'Summer'
                ELSE 'Autumn'
            END AS season,
            -- Edinburgh Festival Fringe runs roughly early-Aug to early-Sept
            CASE WHEN EXTRACT(MONTH FROM d) = 8 THEN TRUE ELSE FALSE END AS is_festival_month
        FROM (SELECT DISTINCT date AS d FROM calendar_raw) sub
        ORDER BY d
        """
    )
    n = con.execute("SELECT COUNT(*) FROM dim_date").fetchone()[0]
    logger.info("Built dim_date: %d distinct dates", n)


def build_fact_listing(con: duckdb.DuckDBPyConnection, listings_clean: pd.DataFrame) -> None:
    """
    Central fact table: one row per listing, with foreign keys to
    dim_host and dim_neighbourhood, plus the listing-level measures used
    throughout EDA/stats/ML (price, review scores, occupancy estimate).
    """
    con.register("listings_clean_tmp", listings_clean)
    con.execute(
        """
        CREATE OR REPLACE TABLE fact_listing AS
        SELECT
            l.id AS listing_id,
            h.host_key,
            n.neighbourhood_key,
            l.room_type,
            l.property_category,
            l.accommodates,
            l.bedrooms,
            l.bathrooms_filled AS bathrooms,
            l.bathroom_is_shared,
            l.price_clean AS price,
            l.price_is_sentinel,
            l.minimum_nights,
            l.maximum_nights,
            l.availability_365,
            l.number_of_reviews,
            l.number_of_reviews_ltm,
            l.review_scores_rating,
            l.review_scores_cleanliness,
            l.review_scores_location,
            l.review_scores_value,
            l.estimated_occupancy_l365d,
            l.estimated_revenue_l365d,
            l.host_is_superhost,
            l.instant_bookable,
            l.has_reviews,
            l.license_disclosed,
            l.first_review,
            l.last_review,
            l.host_since
        FROM listings_clean_tmp l
        LEFT JOIN dim_host h ON l.host_id = h.host_id
        LEFT JOIN dim_neighbourhood n ON l.neighbourhood_cleansed = n.neighbourhood_name
        """
    )
    n = con.execute("SELECT COUNT(*) FROM fact_listing").fetchone()[0]
    unmatched_host = con.execute(
        "SELECT COUNT(*) FROM fact_listing WHERE host_key IS NULL"
    ).fetchone()[0]
    unmatched_nbhd = con.execute(
        "SELECT COUNT(*) FROM fact_listing WHERE neighbourhood_key IS NULL"
    ).fetchone()[0]
    logger.info(
        "Built fact_listing: %d rows (unmatched host_key: %d, unmatched neighbourhood_key: %d)",
        n, unmatched_host, unmatched_nbhd,
    )


def build_star_schema() -> None:
    con = duckdb.connect(str(PROCESSED_DIR / "edinburgh_airbnb.duckdb"))

    raw = pd.read_csv(CITY_CONFIG["files"]["listings"], low_memory=False)
    listings_clean = clean_listings(raw)

    build_dim_neighbourhood(con)
    build_dim_host(con, listings_clean)
    build_dim_date(con)
    build_fact_listing(con, listings_clean)

    logger.info("Star schema build complete. Tables: %s", con.execute("SHOW TABLES").fetchall())
    con.close()


if __name__ == "__main__":
    build_star_schema()
