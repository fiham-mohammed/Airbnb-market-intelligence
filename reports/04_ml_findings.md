# Data Science Experiment — Price Prediction (Section 6.1)

Source code: `src/ml_price_prediction.py`. Full results: see notebook
Section 6 and this write-up.

## Problem Framing

**Target variable:** nightly price (£), log-transformed for training.
Raw price skew is 14.9 (extremely right-skewed); log-price skew is 1.5 —
the same transformation rationale established in the Day 4 OLS regression.

**Success criteria:** Mean Absolute Error (MAE) and RMSE on log-price for
model comparison, plus MAE and MAPE back-transformed to £ for business
interpretability. All metrics are computed from **5-fold cross-validated
out-of-fold predictions**, not in-sample fit, to get an honest estimate of
how the model would perform on listings it hasn't seen.

## Feature Engineering

Built on top of the same property-characteristic features used in the
Day 4 regression (accommodates, bedrooms, bathrooms, minimum_nights,
review_scores_rating, host_is_superhost, room_type), plus:

- **Amenity flags** (10 features): parsed from the raw `amenities` text
  field (a Python-list-literal string per listing). Chose 10 amenities
  with real prevalence variance (20-60% range) rather than near-universal
  amenities like Wifi (89.8%) or Smoke alarm (97.8%), which carry little
  discriminating signal since almost every listing has them.
- **amenity_count**: total number of amenities listed, as a simple
  proxy for overall listing comprehensiveness/effort.
- **Two interaction terms**: `accommodates × bathrooms` (capacity and
  bathroom count plausibly compound rather than add independently — a
  6-person, 1-bathroom listing is a meaningfully different product from a
  6-person, 3-bathroom listing) and `private_room × has_private_entrance`
  (a private entrance plausibly matters more for a private-room listing,
  where it substitutes for not having the whole property, than for an
  entire-home listing where it's closer to a given).

Final feature matrix: **4,909 rows × 22 features** (27 listings dropped
for missing bedrooms/bathrooms/price, consistent with established Day 1
nulls).

## Model Comparison

Three model families, all evaluated identically via 5-fold CV:

| Model | MAE (log) | RMSE (log) | MAE (£) | MAPE |
|---|---|---|---|---|
| Ridge Regression | 0.348 | 0.543 | £147.29 | 35.1% |
| **Random Forest** | **0.326** | 0.511 | £143.57 | **33.0%** |
| XGBoost | 0.329 | **0.505** | £144.72 | 33.5% |

Random Forest and XGBoost both outperform Ridge by a modest margin
(consistent with the modest improvement over Day 4's linear OLS model:
Random Forest's CV R² = 0.49 vs. OLS's 0.41), reflecting that some
genuine non-linear/interaction structure exists in the data beyond what a
linear model captures, but the improvement is incremental, not dramatic.

**Random Forest selected as the primary model** for residual and SHAP
analysis (best MAE on log-price; XGBoost and Random Forest are close
enough that either choice is defensible).

## Residual Analysis — Are Errors Systematic?

**By room type:**

| Room type | Mean absolute % error |
|---|---|
| Hotel room | 42.5% |
| Private room | 52.7% |
| Entire home/apt | 69.9% |
| Shared room | 102.2% |

**Important caveat on "Shared room" (102% error):** this category has
only **19 listings** in the entire dataset, split roughly 3-4 per
cross-validation fold — nowhere near enough for the model to learn a
reliable pattern. This is compounded by the hostel whole-room-booking
pricing quirk documented in Day 3 (Decision 14), where 5 of these 19
listings are priced at £900/night for booking an entire dorm room, not a
single bed. Excluding "Shared room" entirely changes overall MAPE from
33.0% to 33.0% (no material difference), confirming this small, noisy
category isn't driving the broader error pattern — it's a separate,
small, explainable limitation rather than a systemic problem.

**By price range:**

| Price bucket | n | Mean absolute % error |
|---|---|---|
| <£100 | 1,028 | 48.7% |
| £100-200 | 2,220 | 27.0% |
| £200-300 | 905 | 23.8% |
| £300-500 | 497 | 33.3% |
| £500+ | 259 | 53.2% |

**A clear, honest U-shaped pattern:** the model is most accurate in the
£100-300 "mainstream" range and notably worse at both extremes. This
makes sense — cheap and very expensive listings are both rarer (less
training data per listing in those ranges) and likely priced by factors
outside this feature set (e.g. budget-hostel pricing conventions at the
low end; one-off luxury features — a private hot tub, a castle, a
specific exclusive location — at the high end that this feature set
doesn't capture in enough detail).

## SHAP Explainability

**Figure 10** (SHAP summary plot) shows feature impact on log-price
predictions, ranked by mean absolute SHAP value:

1. `accommodates` — by far the strongest driver, consistent with Day 4's
   regression and Day 3's correlation analysis (Spearman ρ=0.675).
2. `room_Private room` — being a private room (vs. the entire-home/apt
   reference category) strongly pushes price down.
3. `accommodates × bathrooms` interaction — confirms the interaction term
   adds real signal beyond the two main effects alone.
4. `review_scores_rating`, `bedrooms` — both positively associated with
   price, consistent with Day 4.

**A genuinely interesting, slightly counter-intuitive finding —
`has_parking`:** SHAP shows having a parking amenity flag is associated
with **lower**, not higher, predicted price. Investigated rather than
reported blindly: this is because on-site parking is a proxy for
location, not an independent value-add. Outer/suburban Edinburgh
neighbourhoods (e.g. Parkhead and Sighthill, South Gyle, West Pilton)
show 100% parking prevalence, while the priciest central tourist core
(Old Town, Princes Street and Leith Street — the same neighbourhood
identified as most expensive in Day 3's geographic analysis) sits at the
*bottom* of parking prevalence (47.5%) — dense city-centre listings
simply don't have space for parking and don't need it, since guests there
are typically not arriving by car.

*Business interpretation:* A host should not interpret "add parking" as
a literal price-raising action. The model has correctly detected that
parking *correlates* with lower price because of where parking-equipped
properties tend to be located, not because parking itself is undesirable
to guests. This is a clear, real-world illustration of why SHAP values
describe association, not causation — exactly the distinction the
assignment's documentation standard asks candidates to be able to
articulate.

## Limitations & What We'd Improve With More Time

- **MAPE of ~33%** means typical predictions are off by roughly a third
  of the true price — a usable but not highly precise model. This is
  consistent with Day 4's regression R² of 0.41 (now improved modestly to
  0.49 with Random Forest): the available features explain roughly half
  of price variation, with the rest likely driven by unmeasured factors
  (exact micro-location, photo quality, host responsiveness, listing
  description quality).
- **No external/listing-text features used**: amenity flags are derived
  from structured data, but the free-text `description` and
  `neighborhood_overview` fields (rich in tourist-destination language,
  per Day 1's profiling) were not used here. NLP-derived features from
  listing text are a natural extension (see Section 7 opportunities).
- **Small-sample categories** (Shared room, Hotel room) have unreliable
  per-category error estimates given how few listings exist in each —
  any production deployment of this model should flag predictions for
  these categories as lower-confidence rather than presenting them with
  the same apparent precision as the much larger Entire home/Private room
  categories.
