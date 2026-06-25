"""
ingest.py
---------
Data Engineering Challenge — Section 3.1: Data Ingestion & Profiling

This module implements a repeatable ingestion step and a profiling step
that together produce a Data Quality Report for the raw Inside Airbnb
files (listings, calendar, reviews, neighbourhoods).

Design notes (see report Section 5 "Engineering Approach" / Decision Log):
  - We use pandas for listings/neighbourhoods (small, wide tables where
    dtype inference and string handling matter) and DuckDB for calendar
    (1.8M rows) because DuckDB's CSV reader is column-oriented and far
    faster for purely numeric/date aggregation at this scale.
  - Profiling is implemented as a generic function that works on any
    DataFrame, so the same code profiles all four files without
    file-specific branching. This is what "repeatable" means here --
    a new file format only needs a new loader, not new profiling logic.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from config import CITY_CONFIG, PROCESSED_DIR, RAW_DIR, VALIDATION_RULES

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ingest")


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def load_listings() -> pd.DataFrame:
    """Load the listings file. Small enough (10k rows x 79 cols) for pandas."""
    path = CITY_CONFIG["files"]["listings"]
    logger.info("Loading listings from %s", path)
    df = pd.read_csv(path, low_memory=False)
    logger.info("Loaded listings: %d rows, %d columns", *df.shape)
    return df


def load_neighbourhoods() -> pd.DataFrame:
    path = CITY_CONFIG["files"]["neighbourhoods"]
    logger.info("Loading neighbourhoods from %s", path)
    df = pd.read_csv(path)
    logger.info("Loaded neighbourhoods: %d rows", len(df))
    return df


def load_calendar_via_duckdb(con: duckdb.DuckDBPyConnection) -> None:
    """
    Register the calendar CSV as a DuckDB table directly from disk.

    Rationale: calendar.csv is ~1.8M rows. Reading it into a pandas
    DataFrame first and then writing to DuckDB doubles memory pressure
    for no benefit -- DuckDB's CSV reader can ingest it directly and is
    faster for the aggregate queries we run on it later (Section 3.3).
    """
    path = CITY_CONFIG["files"]["calendar"]
    logger.info("Loading calendar into DuckDB from %s", path)
    con.execute(
        f"""
        CREATE OR REPLACE TABLE calendar_raw AS
        SELECT * FROM read_csv_auto('{path}', header=True)
        """
    )
    n_rows = con.execute("SELECT COUNT(*) FROM calendar_raw").fetchone()[0]
    logger.info("Loaded calendar_raw into DuckDB: %d rows", n_rows)


def load_reviews_via_duckdb(con: duckdb.DuckDBPyConnection) -> None:
    """Reviews (~559k rows, includes free text) -- also via DuckDB for speed."""
    path = CITY_CONFIG["files"]["reviews"]
    logger.info("Loading reviews into DuckDB from %s", path)
    con.execute(
        f"""
        CREATE OR REPLACE TABLE reviews_raw AS
        SELECT * FROM read_csv_auto('{path}', header=True, quote='"', escape='"')
        """
    )
    n_rows = con.execute("SELECT COUNT(*) FROM reviews_raw").fetchone()[0]
    logger.info("Loaded reviews_raw into DuckDB: %d rows", n_rows)


# ---------------------------------------------------------------------------
# Profiling
# ---------------------------------------------------------------------------
@dataclass
class ColumnProfile:
    column: str
    dtype: str
    n_missing: int
    pct_missing: float
    n_unique: int
    sample_values: list[Any] = field(default_factory=list)


@dataclass
class TableProfile:
    table_name: str
    n_rows: int
    n_columns: int
    columns: list[ColumnProfile]
    n_duplicate_rows: int


def profile_dataframe(df: pd.DataFrame, table_name: str, sample_n: int = 3) -> TableProfile:
    """
    Generic profiler: works on any DataFrame regardless of source file.

    Produces per-column null rates, cardinality, and a few sample values,
    plus an exact-duplicate row count at the table level.
    """
    n_rows, n_cols = df.shape
    col_profiles = []
    for col in df.columns:
        series = df[col]
        n_missing = int(series.isna().sum())
        non_null = series.dropna()
        samples = non_null.head(sample_n).tolist() if len(non_null) else []
        col_profiles.append(
            ColumnProfile(
                column=col,
                dtype=str(series.dtype),
                n_missing=n_missing,
                pct_missing=round(100 * n_missing / n_rows, 2) if n_rows else 0.0,
                n_unique=int(series.nunique(dropna=True)),
                sample_values=[str(s) for s in samples],
            )
        )
    n_dupes = int(df.duplicated().sum())
    return TableProfile(
        table_name=table_name,
        n_rows=n_rows,
        n_columns=n_cols,
        columns=col_profiles,
        n_duplicate_rows=n_dupes,
    )


def profile_duckdb_table(con: duckdb.DuckDBPyConnection, table_name: str) -> TableProfile:
    """
    Profile a DuckDB table without pulling the whole thing into pandas.

    Uses SQL aggregation (COUNT, COUNT DISTINCT) per column, which is the
    correct approach at calendar/reviews scale (1.8M / 559k rows) -- doing
    this in pandas would require loading everything into memory first.
    """
    n_rows = con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
    cols_info = con.execute(f"DESCRIBE {table_name}").fetchall()  # (name, type, ...)
    col_profiles = []
    for col_name, col_type, *_ in cols_info:
        q = f"""
            SELECT
                COUNT(*) - COUNT("{col_name}") AS n_missing,
                COUNT(DISTINCT "{col_name}") AS n_unique
            FROM {table_name}
        """
        n_missing, n_unique = con.execute(q).fetchone()
        sample_q = f'SELECT DISTINCT "{col_name}" FROM {table_name} WHERE "{col_name}" IS NOT NULL LIMIT 3'
        samples = [r[0] for r in con.execute(sample_q).fetchall()]
        col_profiles.append(
            ColumnProfile(
                column=col_name,
                dtype=str(col_type),
                n_missing=n_missing,
                pct_missing=round(100 * n_missing / n_rows, 2) if n_rows else 0.0,
                n_unique=n_unique,
                sample_values=[str(s) for s in samples],
            )
        )
    # Exact duplicate detection at this scale: hash all columns, count repeats
    dupe_q = f"""
        SELECT COUNT(*) FROM (
            SELECT *, COUNT(*) OVER (PARTITION BY {",".join(f'"{c[0]}"' for c in cols_info)}) AS cnt
            FROM {table_name}
        ) WHERE cnt > 1
    """
    try:
        n_dupes = con.execute(dupe_q).fetchone()[0]
    except duckdb.Error:
        n_dupes = -1  # signal "not computed" if the window query is too heavy
    return TableProfile(
        table_name=table_name,
        n_rows=n_rows,
        n_columns=len(cols_info),
        columns=col_profiles,
        n_duplicate_rows=n_dupes,
    )


# ---------------------------------------------------------------------------
# Validation checks (domain rules from Section 3.1, last bullet)
# ---------------------------------------------------------------------------
def validate_listings(df: pd.DataFrame) -> dict[str, Any]:
    """
    Domain validation: price cannot be negative, lat/lon must be valid, etc.
    Returns a dict of rule -> count of violating rows (does not mutate df;
    decisions about dropping/flagging happen in clean.py).
    """
    issues = {}

    if "price" in df.columns:
        price_numeric = (
            df["price"].astype(str).str.replace(r"[$,]", "", regex=True).astype(float, errors="ignore")
        )
        issues["negative_price"] = int((pd.to_numeric(price_numeric, errors="coerce") < 0).sum())

    if "latitude" in df.columns:
        lo, hi = VALIDATION_RULES["latitude_range"]
        issues["invalid_latitude"] = int((~df["latitude"].between(lo, hi)).sum())

    if "longitude" in df.columns:
        lo, hi = VALIDATION_RULES["longitude_range"]
        issues["invalid_longitude"] = int((~df["longitude"].between(lo, hi)).sum())

    if "minimum_nights" in df.columns:
        issues["min_nights_below_floor"] = int(
            (df["minimum_nights"] < VALIDATION_RULES["min_nights_floor"]).sum()
        )

    return issues


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------
def table_profile_to_dict(tp: TableProfile) -> dict:
    return {
        "table_name": tp.table_name,
        "n_rows": tp.n_rows,
        "n_columns": tp.n_columns,
        "n_duplicate_rows": tp.n_duplicate_rows,
        "columns": [
            {
                "column": c.column,
                "dtype": c.dtype,
                "n_missing": c.n_missing,
                "pct_missing": c.pct_missing,
                "n_unique": c.n_unique,
                "sample_values": c.sample_values,
            }
            for c in tp.columns
        ],
    }


def run_full_profiling() -> dict[str, Any]:
    """
    Orchestrates ingestion + profiling across all four files and writes
    a single JSON data-quality report to data/processed/.
    """
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {"city": CITY_CONFIG["city_name"], "snapshot_date": CITY_CONFIG["snapshot_date"]}

    # --- listings (pandas) ---
    listings_df = load_listings()
    listings_profile = profile_dataframe(listings_df, "listings")
    listings_validation = validate_listings(listings_df)
    report["listings"] = table_profile_to_dict(listings_profile)
    report["listings"]["validation_issues"] = listings_validation

    # --- neighbourhoods (pandas) ---
    nbhd_df = load_neighbourhoods()
    nbhd_profile = profile_dataframe(nbhd_df, "neighbourhoods")
    report["neighbourhoods"] = table_profile_to_dict(nbhd_profile)

    # --- calendar + reviews (DuckDB) ---
    con = duckdb.connect(str(PROCESSED_DIR / "edinburgh_airbnb.duckdb"))
    load_calendar_via_duckdb(con)
    load_reviews_via_duckdb(con)

    calendar_profile = profile_duckdb_table(con, "calendar_raw")
    reviews_profile = profile_duckdb_table(con, "reviews_raw")
    report["calendar"] = table_profile_to_dict(calendar_profile)
    report["reviews"] = table_profile_to_dict(reviews_profile)

    con.close()

    out_path = PROCESSED_DIR / "data_quality_report.json"
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    logger.info("Wrote data quality report to %s", out_path)

    return report


if __name__ == "__main__":
    run_full_profiling()
