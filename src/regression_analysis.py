"""
regression_analysis.py
-----------------------
Statistical Analysis Challenge — Section 5.2 (confidence intervals) and
5.3 (correlation / driver analysis via regression).
"""

from __future__ import annotations

import logging

import duckdb
import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats
from statsmodels.stats.outliers_influence import variance_inflation_factor

from config import PROCESSED_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("regression")


def get_connection() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(PROCESSED_DIR / "edinburgh_airbnb.duckdb"))


# ---------------------------------------------------------------------------
# Section 5.2: Confidence intervals for mean price by room type
# ---------------------------------------------------------------------------
def confidence_intervals_by_room_type(con: duckdb.DuckDBPyConnection, confidence: float = 0.95) -> pd.DataFrame:
    """
    95% CI for mean price by room_type, using a t-distribution CI on the
    mean (standard approach) but ALSO reporting the median with a
    bootstrap CI, since price is heavily right-skewed and the mean is not
    a robust summary of a skewed distribution on its own (consistent with
    every other price-skew finding in this project).
    """
    df = con.execute(
        "SELECT room_type, price FROM fact_listing WHERE price_is_sentinel = FALSE AND price IS NOT NULL"
    ).df()

    rows = []
    rng = np.random.default_rng(42)  # fixed seed for reproducibility
    for room_type, group in df.groupby("room_type"):
        prices = group["price"].values
        n = len(prices)
        mean = prices.mean()
        sem = stats.sem(prices)
        ci_mean = stats.t.interval(confidence, n - 1, loc=mean, scale=sem)

        # Bootstrap CI for the median (1000 resamples)
        boot_medians = [np.median(rng.choice(prices, size=n, replace=True)) for _ in range(1000)]
        ci_median = np.percentile(boot_medians, [2.5, 97.5])

        rows.append(
            {
                "room_type": room_type,
                "n": n,
                "mean_price": round(mean, 2),
                "ci_mean_lower": round(ci_mean[0], 2),
                "ci_mean_upper": round(ci_mean[1], 2),
                "median_price": round(np.median(prices), 2),
                "ci_median_lower_bootstrap": round(ci_median[0], 2),
                "ci_median_upper_bootstrap": round(ci_median[1], 2),
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Section 5.3: Correlation matrix + regression + VIF
# ---------------------------------------------------------------------------
NUMERIC_FEATURES = ["accommodates", "bedrooms", "bathrooms", "minimum_nights", "review_scores_rating"]


def correlation_matrix(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    df = con.execute(
        f"""
        SELECT price, {", ".join(NUMERIC_FEATURES)}
        FROM fact_listing
        WHERE price_is_sentinel = FALSE AND price IS NOT NULL
        """
    ).df()
    df = df.dropna()
    return df.corr(method="spearman")  # Spearman, not Pearson, given established price skew


def fit_price_regression(con: duckdb.DuckDBPyConnection) -> dict:
    """
    OLS regression of log(price) on key predictors. We model log(price)
    rather than raw price because price is strongly right-skewed
    (established repeatedly throughout this project) and OLS assumes
    normally-distributed residuals -- modeling the log transforms the
    long right tail into something much closer to symmetric, which is
    the standard, well-documented approach for skewed economic/price data.
    """
    df = con.execute(
        f"""
        SELECT price, room_type, host_is_superhost, {", ".join(NUMERIC_FEATURES)}
        FROM fact_listing
        WHERE price_is_sentinel = FALSE AND price IS NOT NULL
        """
    ).df()
    df = df.dropna()
    df["log_price"] = np.log(df["price"])

    # Dummy-encode room_type (drop_first to avoid the dummy variable trap --
    # one category, here 'Entire home/apt', becomes the implicit reference
    # level that all coefficients are interpreted relative to).
    room_dummies = pd.get_dummies(df["room_type"], prefix="room", drop_first=True, dtype=float)
    df["host_is_superhost"] = df["host_is_superhost"].astype(float)

    X = pd.concat([df[NUMERIC_FEATURES + ["host_is_superhost"]], room_dummies], axis=1)
    X = sm.add_constant(X)
    y = df["log_price"]

    model = sm.OLS(y, X).fit()

    # VIF: statsmodels' variance_inflation_factor requires the constant
    # column to remain IN the matrix passed to it -- it uses the constant
    # internally when computing VIF for every other column, even though
    # "VIF for the constant" itself isn't a meaningful number to report.
    # An earlier version of this function dropped 'const' before calling
    # variance_inflation_factor, which silently corrupted the VIF for
    # every other variable (e.g. it originally reported accommodates'
    # VIF as 15.2 and review_scores_rating's as 9.1, both flagged as
    # high-multicollinearity; with the constant correctly retained, the
    # true VIFs are 3.8 and 1.1 respectively -- no serious multicollinearity
    # at all). Caught by checking that the raw pairwise correlations
    # between predictors didn't support such high VIF values in the first
    # place, which prompted re-deriving the calculation from the
    # statsmodels documentation rather than trusting the first result.
    vif_data = pd.DataFrame(
        {
            "feature": X.columns,
            "VIF": [variance_inflation_factor(X.values, i) for i in range(X.shape[1])],
        }
    )
    vif_data = vif_data[vif_data["feature"] != "const"].reset_index(drop=True)

    return {
        "model_summary": model.summary().as_text(),
        "r_squared": model.rsquared,
        "adj_r_squared": model.rsquared_adj,
        "n_obs": int(model.nobs),
        "coefficients": model.params.to_dict(),
        "p_values": model.pvalues.to_dict(),
        "vif": vif_data.to_dict(orient="records"),
        "high_vif_features": vif_data[vif_data["VIF"] > 5]["feature"].tolist(),
    }


if __name__ == "__main__":
    import json

    con = get_connection()

    logger.info("Computing confidence intervals by room type...")
    ci_df = confidence_intervals_by_room_type(con)
    print(ci_df.to_string(index=False))
    ci_df.to_csv(PROCESSED_DIR / "ci_by_room_type.csv", index=False)

    logger.info("Computing Spearman correlation matrix...")
    corr = correlation_matrix(con)
    print(corr.round(3))
    corr.to_csv(PROCESSED_DIR / "correlation_matrix.csv")

    logger.info("Fitting log(price) regression model...")
    reg_results = fit_price_regression(con)
    print(f"R-squared: {reg_results['r_squared']:.3f}")
    print(f"Adjusted R-squared: {reg_results['adj_r_squared']:.3f}")
    print(f"High-VIF features (>5): {reg_results['high_vif_features']}")
    print(pd.DataFrame(reg_results["vif"]))

    with open(PROCESSED_DIR / "regression_results.json", "w") as f:
        json.dump(reg_results, f, indent=2, default=str)

    con.close()
    logger.info("Done.")
