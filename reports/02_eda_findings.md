# Exploratory Data Analysis — Edinburgh Airbnb Market

All figures exclude the 10 listings flagged as sentinel-priced ($9,999; see
Decision 5) unless otherwise noted. Figures referencing neighbourhood-level
statistics exclude neighbourhoods with fewer than 10 listings to avoid
small-sample distortion (see note under Section 4.2 below).

## 4.1 Summary Statistics & Distributions

**Figure 1–2: Price distribution overall and by room type.**

Median price across all Edinburgh listings is **£158/night**, with a long
right tail (a small number of listings priced well above £500). "Entire
home/apt" and "Hotel room" command the highest prices; "Private room" is
roughly half the cost of an entire home.

*Business interpretation:* For a market entrant or investor benchmarking
new supply, £158/night is the realistic "typical" price point to plan
around — not the mean (£280–300), which is pulled upward by a relatively
small number of premium/large properties. Pricing strategy tools that use
the mean rather than the median will systematically overestimate what a
"normal" Edinburgh listing earns.

**Note on "Shared room" listings:** the boxplot shows unusually high prices
for some shared-room listings (up to £900/night). Investigation traced this
to hostel-style listings where the *entire dorm room* (4–16 beds) is booked
as a single unit, not a single bed. This is a labeling convention specific
to a handful of hostel operators, not representative shared-room pricing —
flagged here so the figure isn't misread as "shared rooms are expensive."

**Figure 6–7: Host portfolio concentration.**

**79.4%** of the 3,037 unique hosts in this dataset operate exactly one
listing. However, the **top 10% of hosts (303 hosts) control 38% of all
listings** — a clear power-law concentration pattern.

*Business interpretation:* Edinburgh's Airbnb supply is not purely a
"casual host" market. A meaningful share of inventory is run by
professional, multi-unit operators (e.g., one host alone runs 110
listings under what is almost certainly a property-management brand).
For a platform operator, this matters for policy design — host-support
needs and risk profiles differ substantially between someone renting a
spare room twice a year and an operator running a portfolio of 50+ units.
For an investor, it signals the market has room for both individual hosts
and an established professional-management segment to coexist.

**Figure 8: Review score distribution — rating inflation.**

**91.3%** of rated listings score **4.5 or higher** out of 5, and only
**1.2%** score below 4.0. The distribution is heavily compressed at the
top end of the scale.

*Business interpretation:* A 5-point review scale that's functionally
compressed into a narrow 4.5–5.0 band for the vast majority of listings
has limited power to distinguish "good" from "exceptional" — this is a
well-documented phenomenon on review-based platforms generally, not
specific to Edinburgh. For a revenue strategist building a quality-scoring
model, raw review score should not be treated as the primary differentiator
between listings; review *count*, recency, and sub-category scores
(cleanliness, communication, etc.) carry more discriminating signal than
overall rating alone.

## 4.2 Geographic & Spatial Analysis

**Figure 3–4: Price and listing density by neighbourhood.**

Listing density is heavily concentrated in central Edinburgh (Old Town /
New Town area), consistent with proximity to the historic city centre and
main tourist attractions. Median price is generally higher in and around
this central cluster (£200+/night) and lower toward the city's outer
residential edges (£50–100/night).

**Important caveat — small-sample neighbourhoods excluded:** 22 of the
111 neighbourhoods have fewer than 10 listings. An early version of this
map ranked "Fairmilehead" as the most expensive neighbourhood in
Edinburgh based on a median of just **2** listings — a textbook small-
sample artifact, not a real market signal. These 22 neighbourhoods are
shown in grey on Figure 3 and excluded from any price ranking discussed
in this report. This is the kind of finding that looks dramatic but
shouldn't be reported as fact without a minimum sample-size threshold.

One genuine geographic finding that *does* survive this filter: **Dalmeny,
Kirkliston and Newbridge** (20 listings, near Edinburgh Airport) has the
highest reliable median price (£234.5) outside the city centre, and its
listings accommodate 4.4 guests on average versus 3.66 city-wide —
suggesting larger, group/family-oriented properties near the airport
rather than a pricing premium per se.

*Business interpretation:* For a host deciding where to invest in a new
property, central neighbourhoods offer higher achievable nightly rates but
also the most competition (highest listing density). The airport-adjacent
cluster represents a distinct, less crowded niche serving larger travel
parties rather than competing directly on the city-centre tourist market.

## 4.3 Temporal & Seasonal Trends

**Figure 5a–5b: Availability over time and by day of week.**

Two distinct patterns emerge, and it's important to separate them:

1. **Weekly cycle (Figure 5b):** Friday and Saturday nights are reliably
   *less* available than weekday nights, every week in the 12-month
   calendar window. This indicates genuinely stronger weekend booking
   demand — a pattern we test formally in Section 5 (Hypothesis H5).
2. **Slower seasonal trend (Figure 5a, thick line):** availability rises
   from the snapshot date toward a plateau around Nov–Feb (~55-60%
   available), then declines steadily from spring through to its lowest
   point in August.

**Caveat on causal framing:** August (Fringe Festival month) does show the
lowest availability of the year, but it is the tail end of a months-long
declining trend that begins in spring — not an isolated festival spike.
It would be an overstatement to say "the Fringe Festival causes the
August dip" based on this data alone; a more accurate statement is that
August demand is high and compounds a trend that was already declining.

*Business interpretation:* For a revenue strategist, the weekly Fri/Sat
pattern is the more operationally useful and unambiguous signal — pricing
tools should reliably weight weekend nights higher year-round, not just
during August. The slower seasonal decline toward late summer suggests
hosts should expect tightening supply (and have room to raise prices)
progressively from spring onward, not just in the festival month itself.

**Note on calendar pricing:** as documented in Decision 3 (Day 1 log),
`calendar.csv`'s price fields are 100% null in this snapshot, so this
section is necessarily limited to availability patterns rather than
day-by-day price seasonality. Price-driver analysis instead uses the
listings-level fields in Section 5 (statistical analysis).

## 4.4 Host & Supply-Side Analysis

See Figure 6–7 above (Section 4.1) for portfolio concentration. Combined
with the superhost/rating relationship below (Section 4.5), the picture
that emerges is a market with a large base of casual single-listing hosts
alongside a smaller but commercially significant set of professional
multi-unit operators — both segments coexisting rather than one displacing
the other.

## 4.5 Review & Demand-Side Analysis

**Figure 9: Review count vs. price.**

No strong visual relationship between number of reviews and price — highly
reviewed listings span the full price range, and expensive listings are
not concentrated at either the high or low end of review-count. Popularity
(measured by review volume, a demand proxy per Inside Airbnb's own
methodology notes) does not appear to be simply a function of price in
either direction.

*Business interpretation:* This is a mildly counter-intuitive but useful
finding — a host cannot assume that cutting price alone will reliably
drive up booking volume (proxied by review count), nor that raising price
will suppress it. Other factors (location, photos, amenities, response
rate) likely matter more for demand than price positioning alone. This
motivates the regression/driver analysis in Section 5.3, which looks at
multiple predictors jointly rather than price and reviews in isolation.

---

*All figures are saved in `notebooks/figures/`. Source code for every
chart in this section is in `notebooks/` (to be finalized as an annotated
notebook) and was built directly against the `fact_listing` /
`dim_neighbourhood` / `dim_date` star schema from Day 2, demonstrating the
dimensional model in practical use.*
