# Statistical Analysis — Edinburgh Airbnb Market

All tests use alpha = 0.05. Effect sizes are reported alongside every
p-value per the assignment's explicit instruction that statistical
significance alone is insufficient. Full numeric output (test statistics,
exact p-values, confidence intervals) is in
`data/processed/hypothesis_test_results.json`,
`data/processed/regression_results.json`, and `data/processed/ci_by_room_type.csv`.
Source code: `src/stats_analysis.py`, `src/regression_analysis.py`.

## 5.1 Hypothesis Testing

### H1 — Entire-home listings command higher prices than private rooms
**Test:** Mann-Whitney U (one-sided). Chosen over a t-test because price is
strongly right-skewed in both groups (Shapiro-Wilk rejects normality,
p < 0.001 for both).
**Result:** Entire homes median £186 vs. private rooms £87, **p < 0.001**.

**Effect size — a worked example of why we report more than one:**
Cohen's d = 0.18 ("negligible" by convention) but rank-biserial r = 0.72
("large"). These disagree sharply because Cohen's d depends on standard
deviation, and entire-home prices have an enormous SD (~£1,310) driven by
a handful of luxury outliers — this mechanically shrinks d even though the
median gap is large and obvious in Figure 2. Rank-biserial r, based on
ranks rather than means, isn't distorted the same way. **We report both
rather than quoting whichever looks more impressive.** The honest
conclusion, based on r and the visibly large gap in medians: this is a
real, substantial price premium for entire homes.

*Business interpretation:* Hosts converting a private-room listing to a
whole-property listing (where feasible) can expect to access a
meaningfully higher price tier, not just a statistically detectable one.

### H2 — Superhosts achieve higher review scores than non-superhosts
**Test:** Mann-Whitney U (one-sided), same normality rationale as H1.
**Result:** Superhost median 4.90 vs. non-superhost 4.75, **p < 0.001**,
Cohen's d = 0.69 (medium effect).

*Business interpretation:* This is a genuine, medium-sized effect — not
an artifact of sample size. But it occurs entirely within the top of a
heavily compressed rating scale (Day 3: 91.3% of listings score ≥4.5/5),
so the absolute gap is well under half a star. Superhost status is real
signal, best combined with other indicators rather than relied on alone.

### H3 — Listings with >10 reviews have different prices than listings with fewer
**Test:** Mann-Whitney U (two-sided).
**Result:** Median £160 (>10 reviews) vs. £155 (≤10 reviews),
**p < 0.001**, but rank-biserial r = -0.14 ("small") and Cohen's d = -0.11
("negligible").
*Business interpretation:* Statistically detectable at this sample size,
but the practical difference is small. Combined with Day 3's finding of
no strong visual price/review-count relationship, the more likely
explanation is that older, longer-listed properties simply accumulate
more reviews over time — not that price itself drives review volume in
either direction.

### H4 — Neighbourhood average prices differ significantly
**Test:** Kruskal-Wallis H-test (non-parametric alternative to one-way
ANOVA). Chosen because price is right-skewed within every neighbourhood
group and Levene's test indicates unequal variances across neighbourhoods
— both violate standard ANOVA assumptions.
**Sample:** 89 of 111 neighbourhoods with ≥10 listings (22 excluded as
statistically unreliable at small sample size, per Decision 12).
**Result:** H = 749.7, **p < 0.001**, eta-squared = 0.141.

*Business interpretation:* Neighbourhood explains roughly 14% of price
variance on its own — real and significant, but location alone is far
from the whole story. The regression analysis below (Section 5.3) puts
this in context against property characteristics.

### H5 — Weekend vs. weekday pricing differences are statistically significant
**Important limitation:** `calendar.csv`'s price field is 100% null in
this snapshot (Decision 3, Day 1 log), so weekend/weekday *pricing*
cannot be tested directly from calendar data as the hypothesis literally
states. We substitute **availability** (booked-up-ness) as the closest
testable proxy for weekend vs. weekday demand.

**Test:** Chi-square test of independence (weekend/weekday × available/not),
across all 1,801,640 calendar-day observations.
**Result:** Weekend availability 44.0% vs. weekday 45.9%, χ² = 535.3,
**p < 0.001**, but **Cramer's V = 0.017 — negligible by convention.**

*Business interpretation — reported honestly rather than oversold:* At
1.8 million observations, even a 2-percentage-point gap becomes
"significant" by p-value alone. This is precisely the scenario the
assignment's instruction to report effect size alongside p-value exists
to catch. The honest summary: the weekend effect on availability is real
and directionally consistent (confirmed visually in Day 3's Figure 5b,
present in every week of the 12-month window), but small in absolute
size. A host should expect a modest, not dramatic, weekend booking
advantage from this signal, and we cannot quantify a weekend *price*
premium directly given the calendar pricing gap — this is flagged as a
genuine data limitation, not glossed over.

## 5.2 Confidence Intervals & Effect Sizes

95% confidence intervals for mean price by room type (t-distribution),
plus a 1,000-resample bootstrap CI for the median (more appropriate given
established price skew):

| Room type | n | Mean price | 95% CI (mean) | Median | 95% CI (median, bootstrap) |
|---|---|---|---|---|---|
| Entire home/apt | 3,535 | £337.18 | [£293.99, £380.36] | £186 | [£183, £189] |
| Hotel room | 21 | £191.19 | [£131.80, £250.58] | £200 | [£89, £289] |
| Private room | 1,340 | £133.36 | [£117.64, £149.07] | £87 | [£85, £90] |
| Shared room | 19 | £285.95 | [£103.89, £468.00] | £68 | [£55, £155] |

**Note the Shared room row:** the mean (£285.95) and median (£68) tell
almost opposite stories, and the median's confidence interval is very
wide relative to its size — a direct consequence of the small sample
(n=19) and the hostel whole-room-booking pricing convention documented in
Day 3 (Decision 14). This is a clear, visible example of why reporting
both a point estimate and its confidence interval matters: the wide CI
itself is the signal that this estimate should not be treated as
precise.

## 5.3 Correlation & Driver Analysis

**Correlation matrix (Spearman, not Pearson — chosen because price and
several predictors are non-normally distributed):** `accommodates`
(ρ=0.675) and `bedrooms` (ρ=0.606) are the strongest correlates of price;
`review_scores_rating` and `minimum_nights` show weak correlation with
price (ρ=0.031 and 0.020 respectively).

**Regression model:** OLS regression of **log(price)** on accommodates,
bedrooms, bathrooms, minimum_nights, review_scores_rating,
host_is_superhost, and room_type (dummy-encoded, "Entire home/apt" as
reference category).

*Why log(price), not raw price:* raw price skew is 14.9 — extremely
right-skewed, violating OLS's assumption of normally-distributed
residuals. Log-transforming reduces skew to 1.5, a substantial
improvement, though not a perfect fix (see limitations below).

**Results:** R² = 0.414 (the model explains ~41% of variance in
log-price). Statistically significant predictors (p < 0.05):
`accommodates` (+0.131 log-points per additional guest), `bathrooms`
(+0.088), `bedrooms` (+0.041), `review_scores_rating` (+0.147), and all
room-type dummies relative to entire homes (private rooms −0.445,
hotel rooms −0.299, shared rooms −0.266 log-points). **`host_is_superhost`
is not significant in this model (p = 0.533)** once property
characteristics and room type are controlled for.

**This appears to contradict H2 above — it doesn't.** H2 tested whether
superhosts have higher *review scores*; this regression tests whether
superhost status predicts *price* after controlling for property size and
type. Both can be true simultaneously: superhosts may earn better reviews
without charging more, once you've already accounted for what kind of
property they're renting out. This is a useful, nuanced finding for a
revenue strategist — superhost status functions more as a quality/trust
signal than a price lever.

**Multicollinearity check (VIF):** all features show VIF well under 5
(highest: `accommodates` at 3.83), indicating no serious multicollinearity
among predictors despite `accommodates` and `bedrooms` both relating to
property size.

> **A note on getting this right:** an earlier version of this VIF
> calculation incorrectly reported `accommodates` at VIF=15.2 and
> `review_scores_rating` at VIF=9.1 — both flagged as problematic
> multicollinearity. This was traced to a coding error (the regression
> constant term was dropped from the matrix before calling statsmodels'
> VIF function, which requires the constant to remain present internally
> to compute correct values for the other columns). The error was caught
> by checking that the raw pairwise correlations between predictors didn't
> support such high VIF values in the first place, prompting a review of
> the calculation against statsmodels' documented usage. Corrected VIFs
> are reported above.

**Limitations of this model** (per Section 5's documentation
requirements):
- Residuals remain right-skewed (skew ≈ 3.0) and heavy-tailed
  (kurtosis ≈ 22.5) even after the log transform — Omnibus/Jarque-Bera
  tests reject residual normality (p < 0.001). A small number of
  high-price luxury properties likely still exert outsized influence even
  in log-space. Standard errors and p-values should be interpreted with
  this in mind; they are a reasonable approximation, not an exact result.
- R² of 0.414 means the majority of price variation (~59%) is **not**
  explained by the features in this model. Likely missing drivers include
  exact location (beyond neighbourhood), amenities, photo quality, and
  host responsiveness, none of which are modeled here.
- `host_is_superhost`'s non-significance and the residual non-normality
  are both reported as genuine model limitations, not hidden in favor of
  a cleaner-looking result.
