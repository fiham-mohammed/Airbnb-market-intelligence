# Assumptions & Engineering Decision Log

This log is updated as decisions are made, not reconstructed afterward — entries
are dated and kept in chronological order.

---

### Decision 1 — City selection: Edinburgh, single-city scope
**Date:** Day 1
**Options considered:** 1 large city (London/NYC-scale), multiple small cities,
single mid-sized city.
**Choice:** Single mid-sized city — Edinburgh.
**Why:** The assignment explicitly states quality over breadth ("one city analyzed
with exceptional depth beats five cities skimmed superficially"). Edinburgh's ~4,900
listings / 1.8M calendar rows / 559K reviews is large enough to support meaningful
statistics and segmentation, but small enough to iterate on quickly within a 5-day
window without needing distributed processing. Megacities (London, NYC) would have
forced either heavy downsampling or much slower iteration for no analytical benefit
at this assignment's scope.
**Trade-off accepted:** No cross-city comparison narrative (Sections 3.3/4.2/5.4
multi-city items are out of scope). Compensated for by depth in the single-city
analysis instead.

---

### Decision 2 — pandas for listings/neighbourhoods, DuckDB for calendar/reviews
**Date:** Day 1
**Options considered:** pandas for everything; DuckDB/SQL for everything; a split.
**Choice:** Split — pandas for the two small, wide files (listings: 4,936×79,
neighbourhoods: 111×2); DuckDB for the two large files (calendar: 1.8M rows,
reviews: 559K rows with free text).
**Why:** pandas is well-suited to wide tables with mixed dtypes where row-level
Python logic (string cleaning, categorical mapping) is the dominant operation —
that's `listings.csv`. DuckDB's columnar engine is dramatically faster for
read-then-aggregate workloads on `calendar.csv`/`reviews.csv`, and lets the
dimensional model (Section 3.4) live in the same database used during ingestion,
avoiding an extra export/import step.
**Trade-off accepted:** Two different code paths (pandas profiling function vs.
SQL-based profiling function) instead of one. Mitigated by giving both the same
output schema (`TableProfile` dataclass) so downstream reporting code doesn't care
which engine produced it.

---

### Decision 3 — Calendar pricing gap: use listings.csv precomputed fields instead
**Date:** Day 1
**Finding:** `calendar.csv`'s `price` and `adjusted_price` columns are 100% null
across all 1,801,640 rows, for both available and unavailable dates. Verified this
against the raw CSV text directly (not a parsing artifact) and checked it holds
regardless of the `available` flag.
**Options considered:** (a) Treat as a blocking data quality failure and exclude
calendar entirely; (b) try to impute calendar-level prices from `listings.price`
treating it as constant across the year; (c) use Inside Airbnb's own precomputed
`estimated_occupancy_l365d` / `estimated_revenue_l365d` fields in listings.csv,
and limit calendar.csv's role to availability/seasonality analysis only (it has
zero nulls on `available` and `date`).
**Choice:** (c).
**Why:** Option (b) would fabricate a false precision (real listings change price
seasonally; assuming a flat rate misrepresents revenue). Option (c) uses numbers
Inside Airbnb itself derives from the same underlying scrape history, which is more
defensible than re-deriving a weaker estimate ourselves from incomplete data.
**Trade-off accepted:** We cannot build our own day-level revenue model from
calendar pricing (Section 3.3's literal instruction). We substitute the listings-level
precomputed fields and are explicit about this substitution in the report rather
than presenting it as equivalent.

---

### Decision 4 — `neighbourhood_cleansed`, not `neighbourhood`, is the geography join key
**Date:** Day 1
**Finding:** Raw `neighbourhood` field is 43.8% null and populated values are
host-written free text, not real neighbourhood names. `neighbourhood_cleansed` is
0% null with exactly 111 unique values matching `neighbourhoods.csv` 1:1.
**Choice:** Use `neighbourhood_cleansed` as the sole geography key throughout the
pipeline and dimensional model.
**Why:** It's the only one of the two fields that is actually usable as a join key.
**Trade-off accepted:** None meaningful — this is a correctness fix, not a trade-off.

---

### Decision 5 — Sentinel price values ($9,999) flagged, not silently dropped
**Date:** Day 1
**Finding:** 10 listings priced at exactly $9,999.00, spanning unrelated property
types (cottages, shared/private rooms) with no plausible relationship to property
characteristics — a strong signal of a placeholder/deterrent price rather than a
real market price.
**Options considered:** (a) Leave as-is and let it skew price statistics; (b) drop
silently; (c) flag with a boolean column and exclude from price-distribution and
modeling analysis while documenting the exclusion.
**Choice:** (c).
**Why:** Matches the assignment's explicit instruction to document validation
decisions rather than quietly removing data. Keeps the row available for any
analysis that doesn't depend on price (e.g. review-text NLP), while preventing it
from distorting price-based statistics.

---

### Decision 6 — host_id + lat/lon collisions retained as legitimate multi-unit hosts
**Date:** Day 1
**Finding:** 92 groups of listings share identical host_id + coordinates. Largest
group: one host, 16 listings named "Room 1" through "Room 15" at one address.
**Choice:** Retained as legitimate data (not deduplicated), and earmarked as a
feature for host segmentation (Section 4.4 — professional/commercial hosts vs.
casual single-listing hosts).
**Why:** Investigation showed this is a real serviced-apartment-style commercial
operation, not duplicate scrape records. Removing it would delete real market
structure that the assignment specifically asks us to analyze.

---

*(Further entries added as Days 2–5 progress: cleaning decisions, dimensional model
design, statistical test selection, etc.)*
