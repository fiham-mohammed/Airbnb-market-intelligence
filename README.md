# Edinburgh Airbnb Market Intelligence — Data Engineer Intern Assignment

**Candidate:** Fiham Mohammed
**Submitted to:** Expernetic (Pvt) Ltd — Talent Assessment Program
**City analyzed:** Edinburgh, Scotland, United Kingdom (single-city scope)
**Data snapshot:** Inside Airbnb, 21 September 2025

## What this is

A data engineering + analytics project built on the Inside Airbnb Edinburgh dataset,
covering ingestion, profiling, cleaning, dimensional modeling, exploratory analysis,
and statistical hypothesis testing. Scope and prioritization rationale are documented
in `reports/00_assumptions_and_decisions.md` and the final PDF report.

## Repository structure

```
edinburgh-airbnb/
├── data/
│   ├── raw/              # Original Inside Airbnb files (gitignored if large)
│   └── processed/        # DuckDB database + data_quality_report.json
├── src/                  # Pipeline source code
│   ├── config.py         # City config, paths, validation rules (edit this to retarget a new city)
│   ├── ingest.py         # Section 3.1: ingestion + profiling
│   ├── clean.py          # Section 3.2: cleaning + standardization
│   ├── model.py          # Section 3.4: dimensional model build
│   └── ...
├── sql/                  # Analytical queries against the dimensional model
├── notebooks/            # Annotated EDA / stats notebooks
├── reports/              # Markdown working docs that feed the final PDF
│   ├── 00_assumptions_and_decisions.md
│   ├── 01_dataset_familiarization.md
│   └── ...
├── tests/                # Data quality / pipeline tests
├── requirements.txt
└── README.md             # You are here
```

## How to run this

```bash
# 1. Create environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Place raw Inside Airbnb files in data/raw/
#    (listings.csv, calendar.csv, reviews.csv, neighbourhoods.csv, neighbourhoods.geojson)

# 3. Run ingestion + profiling
python src/ingest.py
# → writes data/processed/data_quality_report.json
# → writes data/processed/edinburgh_airbnb.duckdb (calendar + reviews tables)

# 4. Run cleaning
python src/clean.py

# 5. Build the dimensional model
python src/model.py
```

## Order to review artifacts

1. `reports/00_assumptions_and_decisions.md` — start here
2. `reports/01_dataset_familiarization.md` — schema, relationships, data quality findings
3. `data/processed/data_quality_report.json` — raw profiling output
4. `src/` — pipeline code
5. `notebooks/` — EDA and statistical analysis
6. Final PDF report (see `reports/`)

## AI Usage Disclosure

See Appendix A of the final PDF report, and `reports/ai_usage_disclosure.md` for
the full breakdown of AI tool usage, prompts, and validation steps.
