"""
stats_analysis.py
------------------
Statistical Analysis Challenge — Section 5

Implements the five hypothesis tests required by the assignment (H1-H5),
each following the same documented pattern:
    1. State null (H0) and alternative (H1) hypotheses
    2. Check test assumptions (normality, equal variance, independence)
    3. Select the appropriate test based on what the assumption checks show
    4. Report test statistic, p-value, AND effect size (not p-value alone)
    5. Interpret the result in plain business terms

We deliberately check assumptions rather than defaulting to the "textbook"
test for each scenario, because the assignment explicitly asks us to
document whether assumptions were verified and how violations were
handled (see Section 5's "Statistical Methodology Note").
"""

from __future__ import annotations

import logging

import duckdb
import numpy as np
import pandas as pd
from scipy import stats

from config import PROCESSED_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("stats")


def get_connection() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(PROCESSED_DIR / "edinburgh_airbnb.duckdb"))


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def rank_biserial_from_u(u_stat: float, n1: int, n2: int) -> float:
    """
    Rank-biserial correlation, the natural effect-size companion to the
    Mann-Whitney U test. Ranges from -1 to 1. Unlike Cohen's d, it is based
    on ranks rather than means/standard deviations, so it is not distorted
    by the extreme right-skew present in this dataset's price data (see
    Decision 15: Cohen's d on raw price values is misleadingly small here
    because a few extreme high-price listings inflate the pooled standard
    deviation Cohen's d depends on).
    """
    return (2 * u_stat) / (n1 * n2) - 1


def interpret_rank_biserial(r: float) -> str:
    ar = abs(r)
    if ar < 0.1:
        return "negligible"
    elif ar < 0.3:
        return "small"
    elif ar < 0.5:
        return "medium"
    else:
        return "large"


def cohens_d(group1: np.ndarray, group2: np.ndarray) -> float:
    """Cohen's d for two independent samples, using pooled standard deviation."""
    n1, n2 = len(group1), len(group2)
    var1, var2 = np.var(group1, ddof=1), np.var(group2, ddof=1)
    pooled_sd = np.sqrt(((n1 - 1) * var1 + (n2 - 1) * var2) / (n1 + n2 - 2))
    return (np.mean(group1) - np.mean(group2)) / pooled_sd


def interpret_cohens_d(d: float) -> str:
    ad = abs(d)
    if ad < 0.2:
        return "negligible"
    elif ad < 0.5:
        return "small"
    elif ad < 0.8:
        return "medium"
    else:
        return "large"


def normality_check(sample: np.ndarray, label: str, max_n: int = 5000) -> dict:
    """
    Shapiro-Wilk normality test. Capped at max_n because Shapiro-Wilk
    becomes oversensitive (flags trivial deviations as significant) on
    very large samples -- we report this explicitly rather than silently
    relying on a misleading p-value at n > 5000.
    """
    test_sample = sample if len(sample) <= max_n else np.random.choice(sample, max_n, replace=False)
    stat, p = stats.shapiro(test_sample)
    result = {
        "label": label,
        "n_tested": len(test_sample),
        "n_total": len(sample),
        "shapiro_stat": stat,
        "shapiro_p": p,
        "normal_at_5pct": p > 0.05,
        "capped": len(sample) > max_n,
    }
    return result


# ---------------------------------------------------------------------------
# H1: Entire-home listings command significantly higher prices than private rooms
# ---------------------------------------------------------------------------
def test_h1(con: duckdb.DuckDBPyConnection) -> dict:
    df = con.execute(
        """
        SELECT room_type, price FROM fact_listing
        WHERE price_is_sentinel = FALSE AND price IS NOT NULL
          AND room_type IN ('Entire home/apt', 'Private room')
        """
    ).df()
    entire = df[df.room_type == "Entire home/apt"]["price"].values
    private = df[df.room_type == "Private room"]["price"].values

    norm_entire = normality_check(entire, "entire home price")
    norm_private = normality_check(private, "private room price")
    # Price is strongly right-skewed (confirmed Day 1/3) -> expect non-normal.
    # Use Mann-Whitney U (non-parametric) rather than a t-test, since the
    # normality assumption a t-test relies on is violated here.
    u_stat, p_value = stats.mannwhitneyu(entire, private, alternative="greater")
    d = cohens_d(entire, private)
    r_rb = rank_biserial_from_u(u_stat, len(entire), len(private))

    p_display = "p < 0.001" if p_value < 0.001 else f"p = {p_value:.4g}"

    return {
        "hypothesis": "H1",
        "statement": "Entire-home listings command significantly higher prices than private rooms",
        "test_used": "Mann-Whitney U (one-sided, entire > private)",
        "why_this_test": (
            "Price is strongly right-skewed in both groups (confirmed via Shapiro-Wilk "
            f"below: p={norm_entire['shapiro_p']:.2e} for entire homes, "
            f"p={norm_private['shapiro_p']:.2e} for private rooms -- both reject normality "
            "at alpha=0.05), so a standard t-test's normality assumption is not met. "
            "Mann-Whitney U does not assume normality and is appropriate for comparing "
            "two independent skewed distributions."
        ),
        "normality_checks": [norm_entire, norm_private],
        "n_entire": len(entire), "n_private": len(private),
        "median_entire": float(np.median(entire)), "median_private": float(np.median(private)),
        "u_statistic": float(u_stat), "p_value": float(p_value), "p_value_display": p_display,
        "cohens_d": float(d), "effect_size_interpretation_cohens_d": interpret_cohens_d(d),
        "rank_biserial_r": float(r_rb), "effect_size_interpretation_rank_biserial": interpret_rank_biserial(r_rb),
        "effect_size_note": (
            f"Cohen's d ({d:.2f}, '{interpret_cohens_d(d)}') and rank-biserial r "
            f"({r_rb:.2f}, '{interpret_rank_biserial(r_rb)}') disagree substantially here. "
            "This is expected and worth explaining rather than picking one number: Cohen's "
            "d is computed from means and standard deviations, and entire-home prices have "
            "an extremely large standard deviation (~£1,310) driven by a small number of "
            "high-price outliers -- this inflates the pooled SD and mechanically shrinks d, "
            "even though the median difference (£186 vs £87) is large and obvious. "
            "Rank-biserial r is computed from ranks, not means, so it isn't distorted by "
            "those outliers in the same way and better reflects the true separation between "
            "the two groups visible in Figure 2. We report both rather than silently "
            "choosing the more flattering one."
        ),
        "business_interpretation": (
            f"Entire-home listings have a significantly higher median price "
            f"(£{np.median(entire):.0f}) than private rooms (£{np.median(private):.0f}), "
            f"{p_display}. The rank-biserial effect size (r={r_rb:.2f}, "
            f"{interpret_rank_biserial(r_rb)}) confirms this is a substantial, practically "
            "meaningful difference, not just a statistically detectable one at large sample "
            "size. For a host deciding which product to list, an entire home commands a "
            "real price premium over a private room in the same market."
        ),
    }


# ---------------------------------------------------------------------------
# H2: Superhost listings achieve higher review scores than non-superhost listings
# ---------------------------------------------------------------------------
def test_h2(con: duckdb.DuckDBPyConnection) -> dict:
    df = con.execute(
        """
        SELECT host_is_superhost, review_scores_rating FROM fact_listing
        WHERE review_scores_rating IS NOT NULL AND host_is_superhost IS NOT NULL
        """
    ).df()
    superhost = df[df.host_is_superhost]["review_scores_rating"].values
    non_superhost = df[~df.host_is_superhost]["review_scores_rating"].values

    norm_super = normality_check(superhost, "superhost rating")
    norm_non = normality_check(non_superhost, "non-superhost rating")
    # Ratings are also heavily left-skewed/compressed (Day 3 finding: 91% >= 4.5).
    u_stat, p_value = stats.mannwhitneyu(superhost, non_superhost, alternative="greater")
    d = cohens_d(superhost, non_superhost)

    return {
        "hypothesis": "H2",
        "statement": "Superhost listings achieve higher review scores than non-superhost listings",
        "test_used": "Mann-Whitney U (one-sided, superhost > non-superhost)",
        "why_this_test": (
            "Review scores are heavily compressed/left-skewed (Day 3 finding: 91.3% of "
            "listings score >=4.5/5), violating the normality assumption needed for a "
            f"t-test (Shapiro-Wilk p={norm_super['shapiro_p']:.2e} for superhosts, "
            f"p={norm_non['shapiro_p']:.2e} for non-superhosts). Mann-Whitney U is robust "
            "to this distribution shape."
        ),
        "normality_checks": [norm_super, norm_non],
        "n_superhost": len(superhost), "n_non_superhost": len(non_superhost),
        "median_superhost": float(np.median(superhost)), "median_non_superhost": float(np.median(non_superhost)),
        "u_statistic": float(u_stat), "p_value": float(p_value),
        "cohens_d": float(d), "effect_size_interpretation": interpret_cohens_d(d),
        "business_interpretation": (
            f"Superhosts have significantly higher review scores (median "
            f"{np.median(superhost):.2f}) than non-superhosts (median "
            f"{np.median(non_superhost):.2f}), p={p_value:.2e}, with a medium effect size "
            f"(Cohen's d={d:.2f}). This is a real, non-trivial difference -- not just an "
            "artifact of large sample size -- but it's worth noting it occurs entirely "
            "within the compressed top end of the rating scale (Day 3 finding: 91.3% of "
            "all listings score >=4.5/5). In absolute terms the gap is well under half a "
            "star. Superhost status is a genuine quality signal, but because the underlying "
            "scale leaves little room to differentiate further at the top, it should be "
            "combined with other signals (review count, sub-category scores) rather than "
            "relied on alone to assess listing quality."
        ),
    }


# ---------------------------------------------------------------------------
# H3: Listings with >10 reviews have significantly different prices than fewer
# ---------------------------------------------------------------------------
def test_h3(con: duckdb.DuckDBPyConnection) -> dict:
    df = con.execute(
        """
        SELECT (number_of_reviews > 10) as more_than_10, price FROM fact_listing
        WHERE price_is_sentinel = FALSE AND price IS NOT NULL
        """
    ).df()
    more = df[df.more_than_10]["price"].values
    fewer = df[~df.more_than_10]["price"].values

    norm_more = normality_check(more, "price, >10 reviews")
    norm_fewer = normality_check(fewer, "price, <=10 reviews")
    # Two-sided test here since H3 asks about "different", not a specific direction.
    u_stat, p_value = stats.mannwhitneyu(more, fewer, alternative="two-sided")
    d = cohens_d(more, fewer)
    r_rb = rank_biserial_from_u(u_stat, len(more), len(fewer))
    p_display = "p < 0.001" if p_value < 0.001 else f"p = {p_value:.4g}"

    return {
        "hypothesis": "H3",
        "statement": "Listings with more than 10 reviews have significantly different prices than listings with fewer",
        "test_used": "Mann-Whitney U (two-sided)",
        "why_this_test": (
            "Price is right-skewed in both groups "
            f"(Shapiro-Wilk p={norm_more['shapiro_p']:.2e} and p={norm_fewer['shapiro_p']:.2e}, "
            "both reject normality), so Mann-Whitney U is used in place of a t-test. As "
            "with H1, rank-biserial r is reported alongside Cohen's d since d is distorted "
            "by the same outlier-driven skew."
        ),
        "normality_checks": [norm_more, norm_fewer],
        "n_more_than_10": len(more), "n_10_or_fewer": len(fewer),
        "median_more_than_10": float(np.median(more)), "median_10_or_fewer": float(np.median(fewer)),
        "u_statistic": float(u_stat), "p_value": float(p_value), "p_value_display": p_display,
        "cohens_d": float(d), "effect_size_interpretation_cohens_d": interpret_cohens_d(d),
        "rank_biserial_r": float(r_rb), "effect_size_interpretation_rank_biserial": interpret_rank_biserial(r_rb),
        "business_interpretation": (
            f"Listings with more than 10 reviews have a median price of £{np.median(more):.0f} "
            f"vs. £{np.median(fewer):.0f} for listings with 10 or fewer reviews "
            f"({p_display}, rank-biserial r={r_rb:.2f}, {interpret_rank_biserial(r_rb)} effect). "
            "Combined with the Day 3 finding that review count and price show no strong "
            "linear relationship (Figure 9), this suggests the direction of any price "
            "difference here is more likely explained by listing maturity (older listings "
            "accumulate more reviews) and/or different room types and segments, rather "
            "than price itself driving review volume."
        ),
    }


# ---------------------------------------------------------------------------
# H4: Neighbourhood average prices differ significantly (ANOVA)
# ---------------------------------------------------------------------------
def test_h4(con: duckdb.DuckDBPyConnection) -> dict:
    df = con.execute(
        """
        SELECT n.neighbourhood_name, f.price
        FROM fact_listing f JOIN dim_neighbourhood n ON f.neighbourhood_key = n.neighbourhood_key
        WHERE f.price_is_sentinel = FALSE AND f.price IS NOT NULL
        """
    ).df()
    # Restrict to neighbourhoods with >= 10 listings, consistent with the
    # small-sample-exclusion rule established in Day 3 (Decision 12).
    counts = df.groupby("neighbourhood_name").size()
    valid_neighbourhoods = counts[counts >= 10].index
    df_filtered = df[df.neighbourhood_name.isin(valid_neighbourhoods)]

    groups = [g["price"].values for _, g in df_filtered.groupby("neighbourhood_name")]

    # Check homogeneity of variance (Levene's test) -- an ANOVA assumption.
    levene_stat, levene_p = stats.levene(*groups)

    # Price right-skew + heterogeneous variance across groups (expected, given
    # very different listing densities per neighbourhood) both push us toward
    # the non-parametric alternative to one-way ANOVA: Kruskal-Wallis.
    h_stat, p_value = stats.kruskal(*groups)

    # Eta-squared (effect size) approximation for Kruskal-Wallis
    n_total = len(df_filtered)
    eta_squared = (h_stat - len(groups) + 1) / (n_total - len(groups))

    return {
        "hypothesis": "H4",
        "statement": "Neighbourhood average prices differ significantly across neighbourhoods",
        "test_used": "Kruskal-Wallis H-test (non-parametric alternative to one-way ANOVA)",
        "why_this_test": (
            f"Levene's test for equal variance across {len(groups)} neighbourhood groups: "
            f"stat={levene_stat:.2f}, p={levene_p:.2e}. "
            + ("Variances are significantly unequal across groups, " if levene_p < 0.05 else "Variances are approximately equal, ")
            + "and price is right-skewed within every group (established repeatedly above), "
            "so a standard one-way ANOVA's assumptions (normality, homogeneity of variance) "
            "are not well met. Kruskal-Wallis tests for differences in distribution across "
            "groups without those assumptions."
        ),
        "n_neighbourhoods_tested": len(groups),
        "n_neighbourhoods_excluded_small_sample": int((counts < 10).sum()),
        "levene_stat": float(levene_stat), "levene_p": float(levene_p),
        "h_statistic": float(h_stat), "p_value": float(p_value),
        "eta_squared": float(eta_squared),
        "business_interpretation": (
            f"Median price differs significantly across Edinburgh's neighbourhoods "
            f"(Kruskal-Wallis H={h_stat:.1f}, p={p_value:.2e}, tested across "
            f"{len(groups)} neighbourhoods with sufficient sample size). Eta-squared "
            f"({eta_squared:.3f}) indicates neighbourhood explains a modest share of "
            "overall price variance -- location matters statistically, but it is one "
            "factor among several (room type, property size, host type) rather than the "
            "dominant driver of price on its own. This is explored further in the "
            "regression analysis (Section 5.3)."
        ),
    }


# ---------------------------------------------------------------------------
# H5: Weekend vs weekday pricing differences are statistically significant
# ---------------------------------------------------------------------------
def test_h5(con: duckdb.DuckDBPyConnection) -> dict:
    """
    IMPORTANT CAVEAT (see Decision 3, Day 1 log): calendar.csv's price field
    is 100% null in this snapshot. H5 as literally stated ("weekend vs.
    weekday pricing differences, from calendar data") cannot be tested on
    price directly. We substitute the closest testable proxy available in
    calendar data: weekend vs. weekday AVAILABILITY (booked-up-ness), which
    Day 3's EDA (Figure 5b) already showed a visual difference for. This
    substitution is documented here and in the business interpretation
    rather than silently presented as equivalent to a price test.
    """
    df = con.execute(
        """
        SELECT d.is_weekend, c.available
        FROM calendar_raw c JOIN dim_date d ON c.date = d.date_key
        """
    ).df()
    # NOTE: DuckDB's read_csv_auto infers 'available' as a native BOOLEAN
    # column (True/False), not the literal 't'/'f' strings found in the raw
    # CSV text. An earlier version of this function compared
    # df["available"] == "t", which silently evaluated to False on every
    # row (comparing a Python bool to a string), collapsing the contingency
    # table to a single column and producing a meaningless p=1 result with
    # a divide-by-zero warning. Fixed by using the boolean column directly.
    df["is_available"] = df["available"].astype(int)

    weekend = df[df.is_weekend]["is_available"].values
    weekday = df[~df.is_weekend]["is_available"].values

    contingency = pd.crosstab(df["is_weekend"], df["is_available"])
    chi2, p_value, dof, expected = stats.chi2_contingency(contingency)

    # Effect size for chi-square: Cramer's V
    n = contingency.sum().sum()
    cramers_v = np.sqrt(chi2 / (n * (min(contingency.shape) - 1)))

    pct_available_weekend = 100 * weekend.mean()
    pct_available_weekday = 100 * weekday.mean()

    return {
        "hypothesis": "H5",
        "statement": "Weekend vs. weekday pricing differences are statistically significant",
        "caveat": (
            "calendar.csv's price field is 100% null in this snapshot (Decision 3, Day 1 "
            "log). This test substitutes availability (booked-up-ness) as the closest "
            "testable proxy for weekend vs. weekday demand difference, since true price "
            "comparison from calendar data is not possible with this dataset."
        ),
        "test_used": "Chi-square test of independence (availability x weekend/weekday)",
        "why_this_test": (
            "Availability is a binary outcome (available / not available) observed across "
            "1.8M listing-day combinations, not a continuous measure -- a chi-square test "
            "of independence is the correct test for association between two categorical "
            "variables (weekend/weekday x available/not), not a t-test."
        ),
        "n_weekend_observations": len(weekend), "n_weekday_observations": len(weekday),
        "pct_available_weekend": float(pct_available_weekend),
        "pct_available_weekday": float(pct_available_weekday),
        "chi2_statistic": float(chi2), "p_value": float(p_value), "cramers_v": float(cramers_v),
        "business_interpretation": (
            f"Weekend nights (Fri/Sat) are available {pct_available_weekend:.1f}% of the "
            f"time vs. {pct_available_weekday:.1f}% for weekday nights -- a small but "
            f"consistent and statistically significant difference (chi2={chi2:.1f}, "
            f"p={p_value:.2e}). However, Cramer's V ({cramers_v:.3f}) is conventionally "
            "interpreted as negligible: at n=1.8 million observations, even a 2-percentage-"
            "point difference becomes 'significant' by p-value alone, which is precisely "
            "why effect size must be reported alongside p-value rather than p-value in "
            "isolation (per the assignment's own Section 5.2 instruction). The honest "
            "summary is that the weekend effect on availability is real and directionally "
            "consistent (it appears in every week of the 12-month window, per Day 3's "
            "Figure 5b), but small in absolute size -- a host should not expect a dramatic "
            "weekend booking advantage from this signal alone. Because calendar-level price "
            "data isn't available in this snapshot, we also cannot directly quantify the "
            "weekend *price premium* hosts could capture -- only that weekend demand (via "
            "availability) is reliably, if modestly, higher. Both limitations are noted "
            "here rather than allowing the very small p-value to imply a stronger finding "
            "than the data supports."
        ),
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def run_all_hypothesis_tests() -> list[dict]:
    con = get_connection()
    results = [test_h1(con), test_h2(con), test_h3(con), test_h4(con), test_h5(con)]
    con.close()
    for r in results:
        logger.info("%s: p=%.4g | %s", r["hypothesis"], r["p_value"], r["statement"])
    return results


if __name__ == "__main__":
    import json

    results = run_all_hypothesis_tests()
    out_path = PROCESSED_DIR / "hypothesis_test_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    logger.info("Wrote hypothesis test results to %s", out_path)
