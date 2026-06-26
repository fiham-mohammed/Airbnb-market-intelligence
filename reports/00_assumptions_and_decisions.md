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

---

### Decision 7 — Cleaning implementation: separate, named functions per transformation
**Date:** Day 2
**Choice:** `src/clean.py` implements each cleaning step (price parsing, date
parsing, percentage parsing, boolean standardization, bathroom-field merge,
property-type bucketing) as its own small function, composed together in
`clean_listings()`.
**Why:** Keeps each transformation auditable in isolation and testable on its
own, rather than one large block where a mistake in one step is hard to
isolate. Matches the assignment's emphasis on documenting *each* cleaning
decision separately (Section 3.2).

### Decision 8 — Boolean fields use pandas' nullable boolean dtype, not plain bool
**Date:** Day 2
**Finding (self-caught during validation):** an early version of the boolean
standardization step produced an `object`-typed column instead of a proper
boolean type when missing values (`None`) were present (144 hosts have not
disclosed superhost status). This still worked but was imprecise — generic
`object` columns don't get the same type-safety or fast vectorized handling
that a real boolean dtype gets in pandas.
**Fix:** Cast explicitly to pandas' nullable `boolean` dtype (`.astype("boolean")`),
which correctly represents True/False/missing as `True`/`False`/`<NA>` instead
of mixing Python `None` into a generic object column.
**Why this is worth logging:** Validating your own cleaning output and fixing
issues you find in it — rather than assuming a script ran error-free just
because it didn't crash — is itself part of the data engineering discipline
this assignment is testing for.

### Decision 9 — Property type bucketing: 5 broad categories derived from `property_type`
**Date:** Day 2
**Choice:** Mapped the 70+ raw `property_type` free-text values into 5 buckets:
Entire place, Private room, Shared room, Hotel/B&B, Other — using keyword
matching on the text rather than a hardcoded lookup table of all 70+ values.
**Why:** Keyword matching on "entire", "private room", "shared room",
"hotel"/"bnb" generalizes to property types we haven't seen yet (useful if
this pipeline is later pointed at a different city with different property
type strings), whereas a hardcoded lookup table would silently miss any new
value and dump it into a catch-all without warning.
**Validated:** Checked the resulting "Other" bucket (42 listings, 0.9% of
data) manually — confirmed it correctly captures genuinely unusual property
types (boats, tents, a castle, a converted shipping container) rather than
hiding a bucketing bug.

### Decision 11 — Star schema design: one fact table, three dimensions
**Date:** Day 2
**Options considered:** (a) Fully normalized relational schema with many
small tables; (b) one wide denormalized table (no separate dimensions);
(c) a single fact table (`fact_listing`, grain = one row per listing) with
three supporting dimension tables (`dim_host`, `dim_neighbourhood`,
`dim_date`), leaving `calendar_raw`/`reviews_raw` as-is since they're
already at their natural grain.
**Choice:** (c).
**Why:** The dataset's natural unit of analysis is "one listing" — host and
neighbourhood attributes describe a listing but aren't independent
measurable events themselves, so they belong as dimensions, not separate
facts. A fully normalized schema (a) would add join complexity with no
analytical benefit at this dataset's scale. A single flat table (b) would
duplicate host/neighbourhood attributes across every listing row and make
"host_since hasn't changed" type integrity bugs possible. `dim_date` is
precomputed with weekend/season/festival-month flags so seasonal queries
(Section 4.3) don't need to recompute date logic every time.
**Trade-off accepted:** `dim_host` is derived (not present in the source
data) by deduplicating host attributes from listings.csv using "first
non-null value per host_id." This assumes a host's descriptive attributes
(name, since-date, superhost status) are consistent across all of that
host's listings. Spot-checked this assumption; did not find contradictory
values across a host's multiple listings in the rows checked.
**Validation:** Built and ran 3 test queries (top neighbourhoods by price,
superhost vs. non-superhost average rating, top hosts by listing count).
Zero unmatched foreign keys on both host_key and neighbourhood_key across
all 4,936 fact rows — confirms the join keys identified on Day 1
(`host_id`, `neighbourhood_cleansed`) are fully reliable for this dataset.
Results are also directionally sensible: Old Town/Princes Street area
(Edinburgh's historic tourist core) has the highest median price among
well-represented neighbourhoods; superhosts average a higher rating
(4.88 vs 4.69) than non-superhosts, consistent with the platform's own
superhost-criteria logic.

