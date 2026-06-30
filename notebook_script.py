import sys
sys.path.insert(0, '../src')

import duckdb
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd
import seaborn as sns
import shap
from scipy import stats

from config import PROCESSED_DIR, CITY_CONFIG

sns.set_style("whitegrid")


con = duckdb.connect(str(PROCESSED_DIR / "edinburgh_airbnb.duckdb"))
print("Connected. Tables:", con.execute("SHOW TABLES").fetchall())

df_price = con.execute('''
    SELECT room_type, price, property_category
    FROM fact_listing
    WHERE price_is_sentinel = FALSE AND price IS NOT NULL AND price < 1000
''').df()

fig, axes = plt.subplots(1, 2, figsize=(13, 5))

axes[0].hist(df_price['price'], bins=60, color='#2c5f7c', edgecolor='white')
axes[0].set_title('Figure 1. Distribution of Nightly Price (excl. sentinel & >£1000)', fontsize=10)
axes[0].set_xlabel('Price (£/night)')
axes[0].set_ylabel('Number of listings')
axes[0].axvline(df_price['price'].median(), color='red', linestyle='--',
                label=f"Median: £{df_price['price'].median():.0f}")
axes[0].legend()

order = df_price.groupby('room_type')['price'].median().sort_values(ascending=False).index
sns.boxplot(data=df_price, x='room_type', y='price', hue='room_type', order=order, legend=False, ax=axes[1])
axes[1].set_title('Figure 2. Price by Room Type', fontsize=10)
axes[1].set_xlabel('')
axes[1].set_ylabel('Price (£/night)')
axes[1].tick_params(axis='x', rotation=20)

plt.tight_layout()
plt.show()

print(df_price.groupby('room_type')['price'].agg(['count', 'median', 'mean']).sort_values('median', ascending=False))

# Host portfolio concentration — power law check
portfolio = con.execute('''
    SELECT h.host_key, COUNT(*) as n_listings
    FROM fact_listing f JOIN dim_host h ON f.host_key = h.host_key
    GROUP BY h.host_key
''').df()

portfolio_sorted = portfolio.sort_values('n_listings', ascending=False).reset_index(drop=True)
portfolio_sorted['cum_pct'] = 100 * portfolio_sorted['n_listings'].cumsum() / portfolio_sorted['n_listings'].sum()
top_10pct_n = int(len(portfolio_sorted) * 0.10)
pct_controlled = portfolio_sorted.iloc[top_10pct_n - 1]['cum_pct']

fig, axes = plt.subplots(1, 2, figsize=(13, 5))
axes[0].hist(portfolio['n_listings'], bins=50, color='#2c5f7c')
axes[0].set_yscale('log')
axes[0].set_title('Figure 6. Host Portfolio Size Distribution (log scale)', fontsize=10)
axes[0].set_xlabel('Number of listings per host')
axes[0].set_ylabel('Number of hosts (log scale)')

axes[1].plot(range(1, len(portfolio_sorted) + 1), portfolio_sorted['cum_pct'], color='#2c5f7c')
axes[1].axvline(top_10pct_n, color='red', linestyle='--', alpha=0.7)
axes[1].axhline(pct_controlled, color='red', linestyle='--', alpha=0.7)
axes[1].set_title(f'Figure 7. Top 10% of Hosts Control {pct_controlled:.0f}% of Listings', fontsize=10)
axes[1].set_xlabel('Hosts, ranked by portfolio size')
axes[1].set_ylabel('Cumulative % of all listings')
plt.tight_layout()
plt.show()

print(f"Total hosts: {len(portfolio)}")
print(f"Single-listing hosts: {(portfolio['n_listings']==1).sum()} ({100*(portfolio['n_listings']==1).mean():.1f}%)")
print(f"Top 10% of hosts control {pct_controlled:.1f}% of all listings")

nbhd_stats = con.execute('''
    SELECT n.neighbourhood_name, COUNT(*) as n_listings, MEDIAN(f.price) as median_price
    FROM fact_listing f
    JOIN dim_neighbourhood n ON f.neighbourhood_key = n.neighbourhood_key
    WHERE f.price_is_sentinel = FALSE AND f.price IS NOT NULL
    GROUP BY n.neighbourhood_name
''').df()
nbhd_stats['reliable'] = nbhd_stats['n_listings'] >= 10
nbhd_stats['median_price_reliable'] = np.where(nbhd_stats['reliable'], nbhd_stats['median_price'], np.nan)

geo = gpd.read_file(str(CITY_CONFIG['files']['neighbourhoods_geojson']))
merged = geo.merge(nbhd_stats, left_on='neighbourhood', right_on='neighbourhood_name', how='left')

fig, axes = plt.subplots(1, 2, figsize=(15, 7))
merged.plot(column='median_price_reliable', cmap='YlOrRd', legend=True, ax=axes[0],
            edgecolor='grey', linewidth=0.3,
            legend_kwds={'label': 'Median price (£/night)', 'shrink': 0.7},
            missing_kwds={'color': 'lightgrey'})
axes[0].set_title('Figure 3. Median Price by Neighbourhood\n(grey = <10 listings, excluded)', fontsize=10)
axes[0].set_axis_off()
grey_patch = mpatches.Patch(color='lightgrey', label='<10 listings (excluded)')
axes[0].legend(handles=[grey_patch], loc='lower left', fontsize=8)

merged.plot(column='n_listings', cmap='Blues', legend=True, ax=axes[1],
            edgecolor='grey', linewidth=0.3,
            legend_kwds={'label': 'Number of listings', 'shrink': 0.7},
            missing_kwds={'color': 'lightgrey'})
axes[1].set_title('Figure 4. Listing Density by Neighbourhood', fontsize=11)
axes[1].set_axis_off()
plt.tight_layout()
plt.show()

print(f"Neighbourhoods excluded as unreliable (<10 listings): {(~nbhd_stats['reliable']).sum()} of {len(nbhd_stats)}")
print()
print("Top 5 reliable neighbourhoods by median price:")
print(nbhd_stats[nbhd_stats['reliable']].sort_values('median_price', ascending=False).head(5)[['neighbourhood_name','n_listings','median_price']])

avail = con.execute('''
    SELECT d.date_key, d.month, d.is_weekend, d.is_festival_month,
           SUM(CASE WHEN c.available THEN 1 ELSE 0 END) as n_available,
           COUNT(*) as n_total
    FROM calendar_raw c
    JOIN dim_date d ON c.date = d.date_key
    GROUP BY d.date_key, d.month, d.is_weekend, d.is_festival_month
    ORDER BY d.date_key
''').df()
avail['pct_available'] = 100 * avail['n_available'] / avail['n_total']
avail['date_key'] = pd.to_datetime(avail['date_key'])
avail['rolling_7d'] = avail['pct_available'].rolling(7, center=True).mean()

dow_stats = con.execute('''
    SELECT d.day_of_week,
           AVG(CASE WHEN c.available THEN 1.0 ELSE 0.0 END) * 100 as pct_available
    FROM calendar_raw c JOIN dim_date d ON c.date = d.date_key
    GROUP BY d.day_of_week ORDER BY d.day_of_week
''').df()

fig = plt.figure(figsize=(13, 9))
ax0 = fig.add_subplot(2, 1, 1)
ax1 = fig.add_subplot(2, 1, 2)

ax0.plot(avail['date_key'], avail['pct_available'], color='lightsteelblue', linewidth=0.8, label='Daily % available')
ax0.plot(avail['date_key'], avail['rolling_7d'], color='#2c5f7c', linewidth=2, label='7-day rolling average')
ax0.fill_between(avail['date_key'], 0, 100, where=avail['is_festival_month'], color='orange', alpha=0.15, label='August (Fringe Festival)')
ax0.set_ylim(0, 100)
ax0.set_title('Figure 5a. Availability: Daily Noise vs. Underlying Trend', fontsize=11)
ax0.set_ylabel('% of listings available')
ax0.legend(fontsize=8, loc='upper right')

weekday_names = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat']
ax1.bar([weekday_names[int(i)] for i in dow_stats['day_of_week']], dow_stats['pct_available'], color='#5b8aa6')
ax1.set_title('Figure 5b. Average Availability by Day of Week', fontsize=11)
ax1.set_ylabel('% of listings available')
plt.tight_layout()
plt.show()

scores = con.execute("SELECT review_scores_rating FROM fact_listing WHERE review_scores_rating IS NOT NULL").df()
rel = con.execute('''
    SELECT number_of_reviews, price, review_scores_rating
    FROM fact_listing WHERE price_is_sentinel = FALSE AND price < 1000 AND review_scores_rating IS NOT NULL
''').df()

fig, axes = plt.subplots(1, 2, figsize=(13, 5))
axes[0].hist(scores['review_scores_rating'], bins=40, color='#2c5f7c')
axes[0].set_title('Figure 8. Review Score Distribution', fontsize=10)
axes[0].set_xlabel('Review score (out of 5)')
axes[0].axvline(4.8, color='red', linestyle='--', label='4.8 (superhost threshold area)')
axes[0].legend(fontsize=8)

axes[1].scatter(rel['number_of_reviews'], rel['price'], alpha=0.15, s=10, color='#2c5f7c')
axes[1].set_xscale('log')
axes[1].set_title('Figure 9. Review Count vs. Price (log x-axis)', fontsize=10)
axes[1].set_xlabel('Number of reviews (log scale)')
axes[1].set_ylabel('Price (£/night)')
plt.tight_layout()
plt.show()

print(f"% of listings rated >= 4.8: {100*(scores['review_scores_rating']>=4.8).mean():.1f}%")
print(f"% of listings rated >= 4.5: {100*(scores['review_scores_rating']>=4.5).mean():.1f}%")
print(f"% of listings rated <  4.0: {100*(scores['review_scores_rating']<4.0).mean():.1f}%")

from stats_analysis import test_h1, test_h2, test_h3, test_h4, test_h5

h1 = test_h1(con)
print(f"H1: {h1['statement']}")
print(f"  Test: {h1['test_used']}")
print(f"  p-value: {h1['p_value_display']}")
print(f"  Cohen's d: {h1['cohens_d']:.3f} ({h1['effect_size_interpretation_cohens_d']})")
print(f"  Rank-biserial r: {h1['rank_biserial_r']:.3f} ({h1['effect_size_interpretation_rank_biserial']})")

h2 = test_h2(con)
print(f"H2: {h2['statement']}")
print(f"  p-value: {h2['p_value']:.3e} | Cohen's d: {h2['cohens_d']:.3f} ({h2['effect_size_interpretation']})")
print()
print(h2['business_interpretation'])

h3 = test_h3(con)
print(f"H3: {h3['statement']}")
print(f"  p-value: {h3['p_value_display']} | Cohen's d: {h3['cohens_d']:.3f} | rank-biserial r: {h3['rank_biserial_r']:.3f}")
print()
print(h3['business_interpretation'])

h4 = test_h4(con)
print(f"H4: {h4['statement']}")
print(f"  Test: {h4['test_used']}")
print(f"  Neighbourhoods tested: {h4['n_neighbourhoods_tested']} (excluded for small sample: {h4['n_neighbourhoods_excluded_small_sample']})")
print(f"  p-value: {h4['p_value']:.3e} | eta-squared: {h4['eta_squared']:.3f}")

h5 = test_h5(con)
print(f"H5: {h5['statement']}")
print(f"  CAVEAT: {h5['caveat']}")
print()
print(f"  Weekend availability: {h5['pct_available_weekend']:.1f}% | Weekday: {h5['pct_available_weekday']:.1f}%")
print(f"  p-value: {h5['p_value']:.3e} | Cramer's V: {h5['cramers_v']:.4f}")

from regression_analysis import fit_price_regression, confidence_intervals_by_room_type, correlation_matrix

reg = fit_price_regression(con)
print(f"R-squared: {reg['r_squared']:.3f}")
print(f"Adjusted R-squared: {reg['adj_r_squared']:.3f}")
print(f"N observations: {reg['n_obs']}")
print()
print("High-VIF features (>5):", reg['high_vif_features'] if reg['high_vif_features'] else "None -- no serious multicollinearity")
print()
import pandas as pd
print(pd.DataFrame(reg['vif']))

print(reg['model_summary'])

from ml_price_prediction import build_feature_matrix, compare_models, compute_shap_values

con = duckdb.connect(str(PROCESSED_DIR / "edinburgh_airbnb.duckdb"))
X, y = build_feature_matrix(con)
print(f"Feature matrix: {X.shape[0]} rows x {X.shape[1]} features")
print("Features:", list(X.columns))

results = compare_models(X, y)
import pandas as pd
comparison_df = pd.DataFrame([{k: v for k, v in r.items() if k != 'y_pred_log'} for r in results])
print(comparison_df.to_string(index=False))

explainer, shap_values = compute_shap_values(X, y)

plt.figure(figsize=(10, 8))
shap.summary_plot(shap_values, X, show=False, max_display=15)
plt.title('Figure 10. SHAP Feature Importance for log(price) Prediction (XGBoost)', fontsize=11)
plt.tight_layout()
plt.show()

raw_listings = pd.read_csv(str(CITY_CONFIG['files']['listings']), low_memory=False)
raw_listings['has_parking'] = raw_listings['amenities'].apply(lambda a: 'parking' in str(a).lower())

parking_by_neighbourhood = raw_listings.groupby('neighbourhood_cleansed')['has_parking'].mean().sort_values()
print("Lowest parking prevalence (likely central/dense neighbourhoods):")
print(parking_by_neighbourhood.head(5))
print()
print("Highest parking prevalence (likely outer/suburban neighbourhoods):")
print(parking_by_neighbourhood.tail(5))

con.close()
print("Notebook complete. See reports/02_eda_findings.md, reports/03_statistical_findings.md,")
print("and reports/04_ml_findings.md for full written findings.")
