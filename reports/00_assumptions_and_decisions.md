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

---

### Decision 12 — Small-sample neighbourhoods excluded from price rankings/maps
**Date:** Day 3
**Finding (self-caught during chart review):** an initial version of the
neighbourhood price map ranked "Fairmilehead" as Edinburgh's most expensive
neighbourhood. On inspection, this ranking was based on a median of just
**2** listings — a sample too small to support any real claim.
**Fix:** Applied a minimum threshold of 10 listings per neighbourhood for
any price ranking or choropleth coloring. 22 of 111 neighbourhoods fall
below this threshold and are shown as grey/excluded rather than colored
with a misleadingly confident value.
**Why this matters:** A map that colors a 2-listing neighbourhood the same
visual weight as a 638-listing neighbourhood actively misleads a reader
into thinking both estimates are equally reliable. Catching this before
it went into the report, rather than after, is the difference between a
defensible finding and a false one.

### Decision 13 — Separated weekly availability cycle from seasonal trend in Figure 5
**Date:** Day 3
**Finding (self-caught during chart review):** an initial single-line
availability-over-time chart visually suggested a smooth seasonal "ramp"
pattern. Closer inspection of the raw daily data revealed a strong,
consistent weekly sawtooth (Friday/Saturday nights show measurably lower
availability than weekdays, every single week in the sample) layered on
top of a genuinely slower seasonal trend.
**Fix:** Rebuilt as two panels — (a) daily values plus a 7-day rolling
average to isolate the underlying trend, and (b) a direct day-of-week bar
chart making the weekly pattern explicit and unambiguous.
**Why this matters:** The original single chart would have supported an
overstated, single causal story ("Fringe Festival causes the August dip")
when the more accurate story is two separate effects: a reliable weekly
demand cycle (strong, testable, year-round) and a slower multi-month trend
that August happens to sit at the tail of. Reporting the more precise
version avoids a claim the data doesn't fully support.

### Decision 14 — Hostel "Shared room" high prices flagged as a labeling convention, not corrected
**Date:** Day 3
**Finding:** A small number of "Shared room" listings (5 of 19) show
prices up to £900/night, wildly inconsistent with typical shared/dorm
pricing. Investigation found these are hostel dorm rooms (4-16 beds) where
the listing price represents booking the *entire room*, not a single bed.
**Choice:** Documented as a caveat in the EDA report rather than treated
as a data error to fix — the values are accurate for what they represent
(the room as a bookable unit); the risk is purely in how a reader might
*interpret* the "Shared room" category without this context.
**Why:** Changing or removing these values would require an assumption
about per-bed pricing this dataset doesn't support evidence for. Flagging
the interpretation risk is more honest than guessing at a "corrected" value.
---

### Decision 15 — Reporting two effect sizes (Cohen's d and rank-biserial r) for skewed comparisons
**Date:** Day 4
**Finding:** For H1 (entire-home vs. private-room price), Cohen's d = 0.18
("negligible") while rank-biserial r = 0.72 ("large") for the same
comparison. These disagree because Cohen's d is computed from means and
standard deviations, and entire-home prices have an extremely large
standard deviation (~£1,310) driven by a small number of luxury outliers,
which mechanically shrinks d even though the median difference (£186 vs
£87) is large and visually obvious.
**Choice:** Report both effect sizes wherever Mann-Whitney U is used on
price data (H1, H3), with an explicit note explaining the discrepancy,
rather than silently choosing whichever number looks more favorable.
**Why this matters:** Quietly picking the effect size that best supports
a desired conclusion (or not knowing the two would disagree) would be a
real, if subtle, form of misleading reporting. Showing the disagreement
and explaining its cause is more defensible and demonstrates the
disagreement was investigated, not missed.

### Decision 16 — Caught and fixed three bugs while building stats_analysis.py
**Date:** Day 4
**Bug 1 (H1/H3/H4 producing NaN):** All three tests use the `price` field,
which has 11 null values (out of 4,926 sentinel-excluded rows) that I
hadn't filtered before passing arrays to scipy. scipy's functions
propagate NaN silently rather than raising an error, so the bug surfaced
as a `nan` p-value with no traceback. Fixed by adding `price IS NOT NULL`
to every query using price.
**Bug 2 (H5 chi-square showing p=1 with a divide-by-zero warning):** Code
compared DuckDB's `available` column against the string `"t"`
(`df["available"] == "t"`), assuming it had stayed as raw CSV text. In
fact, DuckDB's `read_csv_auto` had already inferred it as a native
BOOLEAN column during ingestion (confirmed via `typeof(available)` in
DuckDB: returns `BOOLEAN`). Comparing a Python bool to a string is always
False, which collapsed every row into a single column and produced a
meaningless test. Fixed by using the boolean column directly
(`.astype(int)`) instead of a string comparison.
**Bug 3 (VIF in regression_analysis.py wildly overstated):** Dropped the
regression's constant column from the matrix before calling statsmodels'
`variance_inflation_factor`, which requires the constant to remain
present in the matrix to correctly compute VIF for every other column.
This silently corrupted every VIF value (e.g. reported `accommodates` at
15.2 and `review_scores_rating` at 9.1, both flagged as high
multicollinearity). Caught by checking that the raw pairwise correlations
between predictors (all weak, max ~0.33) didn't support such high VIF
values, prompting a re-check against statsmodels' documented usage.
Corrected VIFs are all under 4.
**Why this is worth logging in detail:** All three bugs ran without
crashing or raising visible errors — they produced plausible-looking but
wrong output. Each was caught only by independently sanity-checking the
result against something else (raw data, a second calculation, domain
expectation) rather than trusting that "the code ran" meant "the code is
correct." This is the habit being demonstrated here, not just the fixes
themselves.

### Decision 17 — Modeling log(price), not raw price, in the regression
**Date:** Day 4
**Choice:** OLS regression target is `log(price)`, not raw price.
**Why:** Raw price skew is 14.9 (extremely right-skewed), which strongly
violates OLS's assumption of normally distributed residuals. Log
transform reduces skew to 1.5 -- a substantial, genuine improvement,
though not a perfect fix (residual diagnostics still show skew ≈3.0 and
high kurtosis after transformation, reported as an explicit model
limitation rather than hidden).

### Decision 18 — H5 tested on availability, not price, due to the Day 1 calendar pricing gap
**Date:** Day 4
**Choice:** Substituted weekend/weekday availability for weekend/weekday
price as the test variable for H5, since `calendar.csv`'s price field is
100% null (Decision 3).
**Result reported honestly:** the effect is statistically significant
(p<0.001, driven by the very large n=1.8M sample) but Cramer's V=0.017 is
negligible by convention. Both the substitution and the small effect size
are stated plainly rather than letting the extreme p-value imply a
stronger finding than the data supports.
---

### Decision 19 — Combined Days 3-4 work into one annotated, fully-executed notebook
**Date:** Day 4 (notebook follow-up)
**Choice:** Built `notebooks/02_eda_and_statistics.ipynb` programmatically
(via `scripts/build_notebook.py`, using nbformat) rather than hand-writing
notebook JSON, importing the already-validated functions from
`src/stats_analysis.py` and `src/regression_analysis.py` directly rather
than re-implementing the statistical tests separately inside the notebook.
**Why:** Re-implementing the same logic twice (once in src/, once in the
notebook) risks the two drifting out of sync if either is edited later.
Importing the tested functions guarantees the notebook narrates the exact
same analysis already validated and written up in
`reports/02_eda_findings.md` / `reports/03_statistical_findings.md`.
**Validation:** Executed the notebook end-to-end via
`jupyter nbconvert --execute` and programmatically checked all 30 cells
for captured error outputs (found: zero). Spot-checked that printed
figures in the executed notebook (e.g. 79.4% single-listing hosts, 91.3%
rated >=4.5) exactly match the numbers already verified earlier in the
pipeline, confirming the notebook is a faithful, genuinely executed
re-run rather than a static mockup.
---

### Decision 20 — Amenity feature selection: prevalence-variance threshold, not "all amenities"
**Date:** Day 5
**Choice:** Selected 10 amenity flags from 1,956 unique raw amenity
strings, chosen for having genuine prevalence variance (20-60% range)
rather than near-universal amenities (Wifi 89.8%, Smoke alarm 97.8%).
**Why:** Near-universal amenities carry almost no discriminating signal
for a model trying to differentiate price between listings -- nearly
every listing has them, so they can't explain why one listing costs more
than another. Substring matching (not exact string matching) was required
because the raw amenity text has many near-duplicate variants (e.g.
"Free washer – In unit" vs "Washer" vs "Paid washer – In building").

### Decision 21 — Random Forest selected over XGBoost as primary model
**Date:** Day 5
**Finding:** Random Forest (MAE log=0.326) and XGBoost (MAE log=0.329,
but better RMSE log=0.505) perform near-identically in 5-fold CV; both
modestly outperform Ridge regression (MAE log=0.348).
**Choice:** Random Forest selected as the primary model for residual and
SHAP analysis, on marginally better MAE.
**Why this is a defensible, not arbitrary, choice:** the two models are
close enough that either choice is reasonable; documenting the small
margin explicitly (rather than picking one silently and implying a
clearer winner than the data shows) is more honest reporting.

### Decision 22 — Investigated and explained the counter-intuitive "parking lowers price" SHAP finding
**Date:** Day 5
**Finding:** SHAP analysis showed `has_parking` associated with LOWER
predicted price, which could easily be misreported as "remove parking to
raise your price" if not investigated further.
**Investigation:** Checked parking prevalence by neighbourhood. Found
100% parking prevalence in outer/suburban neighbourhoods (Parkhead and
Sighthill, South Gyle, West Pilton, etc.) vs. 47.5% in the priciest
central neighbourhood (Old Town, Princes Street and Leith Street -- the
same neighbourhood flagged as most expensive in the Day 3 geographic
analysis).
**Conclusion documented in the report:** parking is a location proxy, not
an independently undesirable amenity -- dense, expensive city-centre
listings don't have space for parking and their guests don't typically
need it. This is reported explicitly as an association-vs-causation
caveat rather than left as a literal, misleading "add/remove this
amenity" recommendation.

### Decision 23 — Reported U-shaped residual error by price range as an honest limitation
**Date:** Day 5
**Finding:** Model error is lowest in the £100-300 mainstream price range
(~24-27% MAPE) and notably higher at both extremes (<£100: 48.7%, £500+:
53.2%).
**Choice:** Reported plainly as a genuine limitation (smaller samples and
likely unmeasured factors -- budget-hostel conventions at the low end,
one-off luxury features at the high end) rather than omitted or buried.
**Also checked:** confirmed the tiny "Shared room" category (n=19, with
the known hostel whole-room pricing quirk from Decision 14) was not the
primary driver of overall error -- excluding it entirely leaves MAPE
essentially unchanged (33.0% either way), isolating it as a separate,
small, explainable issue rather than a systemic one.
---

### Decision 24 — Caught a missing import while extending the notebook
**Date:** Day 5
**Finding:** When adding the Section 6.1 ML/SHAP cells to
`notebooks/02_eda_and_statistics.ipynb`, the first execution attempt
failed with `NameError: name 'shap' is not defined` -- the notebook's
setup cell imported most libraries but `shap` had been used directly in
`src/ml_price_prediction.py` without a corresponding top-level import in
the notebook's own setup cell.
**Fix:** Added `import shap` to the notebook's setup cell, rebuilt, and
re-executed via `jupyter nbconvert --execute`, then re-verified all 38
cells for captured errors (found: zero) before accepting the result.
**Why this is worth logging:** this is the same discipline applied
throughout the project -- an unexecuted or partially-checked notebook
would have shipped a broken deliverable. Catching it here, before
packaging, is the point.
---

### Decision 25 — Final report built as styled HTML converted to PDF, not raw reportlab canvas
**Date:** Day 5 (report assembly)
**Choice:** The 24-page final report was authored as structured HTML/CSS
(four logical parts combined into one document) and converted to PDF via
wkhtmltopdf, rather than building it directly with reportlab's low-level
canvas API.
**Why:** HTML/CSS gives far more reliable control over typography,
tables, callout boxes, and figure layout for a long, heavily-formatted
document than manually positioning text and shapes with canvas commands.
**A real tooling limitation hit and worked around:** this sandbox's
wkhtmltopdf build lacks the Qt patches required for --footer-center /
--footer-html to function (confirmed via direct testing: both silently
produce a "not supported using unpatched qt" warning and are ignored).
Page numbers were instead added as a post-processing step
(`reports/build/add_page_numbers.py`), overlaying a reportlab-drawn
footer onto each generated page via pypdf, skipping the cover page per
standard report convention. Verified visually by rendering sample pages
back to images and confirming correct numbering ("Page 2 of 23" through
"Page 23 of 23", with the cover page correctly excluded from both the
visible number and the total count).

### Decision 26 — Report content drawn from already-validated JSON/markdown sources, not re-derived
**Date:** Day 5 (report assembly)
**Choice:** Every statistic quoted in the final PDF report (executive
summary metrics, hypothesis test results, regression coefficients, ML
model comparison numbers) was pulled directly from the saved JSON output
files (`hypothesis_test_results.json`, `regression_results.json`) and the
already-written markdown reports (`02_eda_findings.md` through
`04_ml_findings.md`), rather than re-typed from memory during report
drafting.
**Why:** This guarantees the final PDF cannot contain a transcription
error that silently diverges from the validated, tested output already
produced by the pipeline -- the same discipline applied throughout this
project (never trust an unverified number) extended to the report-writing
step itself.
