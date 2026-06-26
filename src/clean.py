"""
clean.py
--------
Data Engineering Challenge — Section 3.2: Data Cleaning & Standardization

Takes the raw listings DataFrame and applies a documented set of cleaning
and standardization steps. Each transformation is a separate, named
function so the pipeline is auditable step-by-step rather than one large
opaque block (this matters for the "document your decisions" requirement
in Section 3.2 and the Decision Log).

Every cleaning decision here was already reasoned through in Day 1's
profiling pass and recorded in reports/00_assumptions_and_decisions.md.
This module is the implementation of those decisions, not new judgment
calls made silently in code.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from config import BOOLEAN_TF_COLUMNS, PROCESSED_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("clean")

SENTINEL_PRICE_VALUE = 9999.00  # see Decision 5, Day 1 log


# ---------------------------------------------------------------------------
# Individual cleaning steps
# ---------------------------------------------------------------------------
def clean_price_column(df: pd.DataFrame, column: str = "price") -> pd.DataFrame:
    """
    '$155.00' (string) -> 155.00 (float).
    Also adds a boolean flag column for the $9,999 sentinel value
    (Decision 5: flag, don't silently drop).
    """
    df = df.copy()
    cleaned = (
        df[column]
        .astype(str)
        .str.replace(r"[\$,]", "", regex=True)
        .replace("nan", np.nan)
    )
    df[f"{column}_clean"] = pd.to_numeric(cleaned, errors="coerce")
    df[f"{column}_is_sentinel"] = np.isclose(df[f"{column}_clean"], SENTINEL_PRICE_VALUE)
    n_sentinel = df[f"{column}_is_sentinel"].sum()
    logger.info("Cleaned '%s': %d sentinel ($9,999) values flagged", column, n_sentinel)
    return df


def parse_date_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Parse ISO date strings to real datetime dtype. Leaves nulls as NaT (not imputed)."""
    df = df.copy()
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    logger.info("Parsed date columns: %s", columns)
    return df


def parse_percentage_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """'94%' (string) -> 0.94 (float, 0-1 scale)."""
    df = df.copy()
    for col in columns:
        if col in df.columns:
            df[col] = (
                df[col].astype(str).str.replace("%", "", regex=False).replace("nan", np.nan)
            )
            df[col] = pd.to_numeric(df[col], errors="coerce") / 100.0
    logger.info("Parsed percentage columns to 0-1 scale: %s", columns)
    return df


def standardize_boolean_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Inside Airbnb encodes booleans as 't'/'f' strings. Convert to real bool, NaN stays NaN."""
    df = df.copy()
    tf_map = {"t": True, "f": False}
    for col in columns:
        if col in df.columns:
            df[col] = df[col].map(tf_map).astype("boolean")  # pandas nullable boolean dtype
    logger.info("Standardized boolean columns: %s", columns)
    return df


def parse_bathrooms(df: pd.DataFrame) -> pd.DataFrame:
    """
    'bathrooms' (numeric) has 3 nulls but 'bathrooms_text' (e.g. '1.5 baths',
    '1 shared bath') is more complete. Extract a numeric value from the text
    field to fill the small number of gaps, and keep a separate flag for
    'shared' bathrooms since that's a real amenity distinction, not noise.
    """
    df = df.copy()
    extracted = df["bathrooms_text"].astype(str).str.extract(r"([\d.]+)")[0]
    df["bathrooms_filled"] = df["bathrooms"].fillna(pd.to_numeric(extracted, errors="coerce"))
    df["bathroom_is_shared"] = df["bathrooms_text"].astype(str).str.contains("shared", case=False, na=False)
    n_filled = df["bathrooms"].isna().sum() - df["bathrooms_filled"].isna().sum()
    logger.info("Filled %d bathroom values from bathrooms_text", n_filled)
    return df


def normalize_property_type(df: pd.DataFrame) -> pd.DataFrame:
    """
    property_type is high-cardinality free text (70+ values, e.g. 'Entire
    rental unit', 'Private room in condo'). room_type is already a clean
    4-category field and is used as the primary categorical elsewhere.
    Here we additionally derive a broad property_category bucket from
    property_type for descriptive EDA, grouping into a small number of
    recognizable groups rather than leaving 70+ raw categories.
    """
    df = df.copy()

    def bucket(pt: str) -> str:
        pt_lower = str(pt).lower()
        if "hotel" in pt_lower or "bnb" in pt_lower or "bed and breakfast" in pt_lower:
            return "Hotel/B&B"
        if "private room" in pt_lower:
            return "Private room"
        if "shared room" in pt_lower:
            return "Shared room"
        if "entire" in pt_lower:
            return "Entire place"
        return "Other"

    df["property_category"] = df["property_type"].apply(bucket)
    logger.info("Derived property_category buckets: %s", df["property_category"].value_counts().to_dict())
    return df


def add_derived_flags(df: pd.DataFrame) -> pd.DataFrame:
    """
    Section 3.3-adjacent derived fields that are really cleaning-stage
    flags: has_reviews (Decision: null first/last_review = zero reviews,
    not missing data), license_disclosed.
    """
    df = df.copy()
    df["has_reviews"] = df["first_review"].notna()
    df["license_disclosed"] = df["license"].notna()
    return df


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
DATE_COLUMNS = ["host_since", "first_review", "last_review", "last_scraped", "calendar_last_scraped"]
PERCENTAGE_COLUMNS = ["host_response_rate", "host_acceptance_rate"]


def clean_listings(df: pd.DataFrame) -> pd.DataFrame:
    """Run the full Section 3.2 cleaning sequence on the raw listings DataFrame."""
    logger.info("Starting listings cleaning: %d rows in", len(df))
    df = clean_price_column(df, "price")
    df = parse_date_columns(df, DATE_COLUMNS)
    df = parse_percentage_columns(df, PERCENTAGE_COLUMNS)
    df = standardize_boolean_columns(df, BOOLEAN_TF_COLUMNS)
    df = parse_bathrooms(df)
    df = normalize_property_type(df)
    df = add_derived_flags(df)

    # Drop columns confirmed 100% null on Day 1 (neighbourhood_group_cleansed,
    # calendar_updated) and the unusable raw 'neighbourhood' free-text field.
    cols_to_drop = ["neighbourhood_group_cleansed", "calendar_updated", "neighbourhood"]
    df = df.drop(columns=[c for c in cols_to_drop if c in df.columns])

    logger.info("Finished listings cleaning: %d rows out, %d columns", len(df), len(df.columns))
    return df


if __name__ == "__main__":
    from config import CITY_CONFIG

    raw = pd.read_csv(CITY_CONFIG["files"]["listings"], low_memory=False)
    cleaned = clean_listings(raw)

    out_path = PROCESSED_DIR / "listings_clean.parquet"
    cleaned.to_parquet(out_path, index=False)
    logger.info("Wrote cleaned listings to %s", out_path)
