# Dataset Familiarization — Edinburgh, Scotland

**Source:** Inside Airbnb · Edinburgh, Scotland, United Kingdom
**Snapshot date:** 21 September 2025
**Files used:** `listings.csv`, `calendar.csv`, `reviews.csv`, `neighbourhoods.csv`, `neighbourhoods.geojson`

## 1. File Inventory & Row Counts

| File | Rows | Columns | Notes |
|---|---|---|---|
| `listings.csv` | 4,936 | 79 | One row per active listing |
| `calendar.csv` | 1,801,640 | 7 | 365 days × 4,936 listings (Sept 2025 – Sept 2026) |
| `reviews.csv` | 559,087 | 6 | One row per guest review |
| `neighbourhoods.csv` | 111 | 2 | Reference list of neighbourhood names |
| `neighbourhoods.geojson` | 111 polygons | — | Boundary geometry, same neighbourhood keys |

**Caveat on row counting:** A naive `wc -l listings.csv` reports 10,165 lines, not 4,936.
This is because `description`, `neighborhood_overview`, and `amenities` contain
embedded newlines inside quoted CSV fields. Line-counting tools that don't respect
CSV quoting will overcount rows in this file. We verified the true row count (4,936)
via `pandas.read_csv`, which correctly handles RFC 4180 quoting, and cross-checked
that `id` has zero nulls and 4,936 unique values.

## 2. Entity-Relationship Model

```
neighbourhoods.csv (111 rows)
        │ neighbourhood (PK)
        │
        ▼
listings.csv (4,936 rows)
        │ id (PK)
        │ host_id (FK → grouping key, no separate hosts.csv exists)
        │ neighbourhood_cleansed (FK → neighbourhoods.csv.neighbourhood)
        │
        ├──────────────┬──────────────────┐
        ▼              ▼                  ▼
calendar.csv      reviews.csv      [no separate hosts table;
  listing_id (FK)   listing_id (FK)  host attributes live inline
  date                                in listings.csv, prefixed
  (grain: 1 row                       host_*]
  per listing per day)
```

**Keys:**
- `listings.id` is the primary key of the listing entity (verified unique, zero nulls).
- `listings.host_id` is not a foreign key to a separate file — Inside Airbnb does not
  ship a standalone hosts table. Host attributes (`host_name`, `host_since`,
  `host_is_superhost`, etc.) are denormalized directly into `listings.csv`. A "hosts"
  dimension table is therefore something *we* derive in the data model (Section 3.4),
  not something present in the source.
- `calendar.listing_id` and `reviews.listing_id` both join 1:many back to `listings.id`.
- `listings.neighbourhood_cleansed` joins 1:many to `neighbourhoods.csv.neighbourhood`
  (see field-interpretation note below — this is *not* the same as the raw
  `neighbourhood` column).

## 3. Business Domain Context

- **Listing** = a single bookable unit on Airbnb (a flat, a room, a whole house).
  One host can operate many listings.
- **Host** = the Airbnb account managing one or more listings. Hosts range from
  individuals letting a spare room to commercial operators running serviced
  apartment portfolios (see Section 5 below).
- **Calendar row** = the availability/price state of one listing on one specific
  future date, as observed at scrape time. It is a snapshot, not a booking record —
  Inside Airbnb does not have access to actual booking/transaction data.
- **Review** = guest feedback left after a stay. Review *counts* are commonly used
  in Airbnb research as a rough proxy for booking volume, since real booking data
  isn't public (see `behind-the-data` methodology notes).

## 4. Special-Interpretation Fields (Assumptions Log)

| Field | Issue | Our interpretation / decision |
|---|---|---|
| `neighbourhood` (raw) | 43.8% missing; populated values are junk free text (e.g. "Neighborhood highlights"), not a usable geography field | **Do not use.** Use `neighbourhood_cleansed` instead (0% missing, 111 clean values matching `neighbourhoods.csv` exactly). |
| `neighbourhood_group_cleansed` | 100% missing / always null | Edinburgh has no sub-city grouping tier in this dataset. Column dropped from analysis. |
| `calendar_updated` | 100% missing | Deprecated/unused field in this export. Dropped. |
| `license` | 75.4% missing; populated values follow pattern `EH-#####-[F/R]` | Real Scotland short-term-let licence numbers. Missing license ≠ necessarily unlicensed — could mean the host hasn't entered it, or the listing predates Scotland's licensing requirement window. We treat null as "not disclosed," not "unlicensed," and flag this distinction explicitly in any compliance-related commentary. |
| `calendar.price` / `calendar.adjusted_price` | **100% missing across all 1,801,640 rows**, regardless of `available` flag | Verified this is a genuine source limitation, not a parsing error (checked raw text, checked both available=t and available=f rows). We use `listings.csv`'s own `price`, `estimated_occupancy_l365d`, and `estimated_revenue_l365d` fields instead, which Inside Airbnb precomputes server-side and are 99.8% populated. Calendar data is still used for **availability-over-time and seasonality analysis** (the `available` boolean and `date` are fully populated), just not for calendar-level pricing. |
| `price` == exactly `$9,999.00` (10 listings) | Appears across unrelated property types (cottages, shared rooms) with no plausible market relationship to property characteristics | Treated as a **sentinel/placeholder value**, not a genuine price — likely hosts deliberately deterring bookings while keeping a listing technically live. Flagged and excluded from price-distribution and modeling analysis, documented rather than silently dropped. |
| Listings sharing identical `host_id` + `latitude`/`longitude` (92 groups) | Could look like duplicate listings | Investigated: largest group is one host with 16 individually named rooms ("Room 1"–"Room 15") at one building address — a legitimate serviced-apartment/commercial operation, not duplicate records. No rows removed; this pattern is *retained* and used as a feature for host-segmentation analysis (Section 4.4: professional vs. casual hosts). |
| `property_type` vs `room_type` | `property_type` is unstructured/high-cardinality (70+ free-text values e.g. "Entire rental unit", "Entire cottage"); `room_type` is a clean 4-category field | `room_type` used as the primary categorical variable for modeling/stats. `property_type` retained for descriptive EDA only, with planned grouping into broader buckets (entire place / private room / hotel / shared) if used further. |
| `first_review` / `last_review` nulls (286 listings) | Could be mistaken for a data quality defect | These are listings with **zero reviews** — null is the *correct* value here, not missing data to impute. Left as explicit null; a `has_reviews` boolean flag is derived instead of imputing a fake date. |

## 5. Dataset Limitations (Methodology, per Inside Airbnb's own documentation)

- Data is scraped from Airbnb's public site, not sourced from Airbnb's internal
  systems — so it is an **approximation**, not ground truth. Total listing counts
  are typically accurate to within ~10–20% per Inside Airbnb's own methodology notes.
- This is a **single point-in-time snapshot** (21 Sept 2025). It does not capture
  listings that were removed before this date or added after it.
- **Reviews as a demand proxy**: since Airbnb does not release real booking data,
  review counts are commonly used in this kind of research as a rough proxy for
  stay volume. This is an approximation with known biases (not every guest leaves
  a review).
- Calendar pricing gap (above) limits calendar.csv to availability/seasonality
  analysis only for this snapshot; no day-by-day price trend can be derived from it.

## 6. Single-City Scope Rationale

This assignment uses Edinburgh only (1-city scope). Rationale documented in the
final report's "Objectives & Scope" section: Edinburgh's listing count (~4,900) is
large enough to support meaningful statistical tests and segmentation while small
enough to permit full local iteration within the assignment's 1-week window, and its
strong festival-driven seasonality (Fringe Festival, Hogmanay) and active short-term-let
licensing regime provide genuine business narrative hooks for EDA and storytelling.
