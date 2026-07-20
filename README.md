# Energy Forecast Consumption — Team Gladiators

**DDMO SoSe 2026 · TH Köln**
Forecasting German electricity load (DE) using LightGBM + spotforecast2_safe.

---

## Grading

| Component | Weight |
|---|---|
| Project work (Challenge) | 50% |
| Written exam | 50% |

---

## What this repo does

Submits a 24-hour day-ahead load forecast for Germany every day to the
[challenge leaderboard](https://bartzbeielstein.github.io/challenge-leaderboard/).
Forecasts are scored daily by MAE against ENTSO-E final actuals.

---

## Project structure

```
Energy_Forecast_Consumption/
├── forecast_real_entsoe.py     # daily competition script (submit new forecast)
├── final.py                    # reproduce any past forecast date (--date flag)
├── Cross_Validation.py         # compare reproduced forecasts vs ENTSO-E actuals
├── data/
│   ├── predictions_*.csv       # original daily competition submissions
│   ├── validate/
│   │   ├── cross_predictions_YYYY-MM-DD.csv   # reproduced forecasts (final.py)
│   │   └── entsoe_fetched_*.csv               # raw ENTSO-E data snapshots
│   └── cross_validation/
│       ├── cross_validation_summary.csv        # MAE/MAPE per day
│       └── cross_validation_YYYY-MM-DD.png     # comparison plots
├── _cache/
│   ├── spotforecast2_data/     # shared ENTSO-E download cache
│   └── logs/                   # audit logs (CR-1)
└── pyproject.toml              # dependencies
```

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
# or with uv:
uv sync
```

### 2. Set your ENTSO-E API key

Create a `.env` file in the project root:

```
ENTSOE_API_KEY=your_key_here
```

Get a key at: https://transparencyplatform.zendesk.com/hc/en-us/articles/12845911031188

---

## Scripts

### `forecast_real_entsoe.py` — Daily competition submission

Run every day to generate and submit tomorrow's forecast.

```bash
python forecast_real_entsoe.py
```

- Downloads latest ENTSO-E actual load data for Germany
- Fetches weather forecast from Open-Meteo (Frankfurt)
- Trains LightGBM on all available data
- Predicts next 24 hours
- Saves `data/predictions_YYYY-MM-DD.csv`

> Update `DATA_END` in the script to today's date before running.

---

### `final.py` — Reproduce any past forecast

Reproduces a prediction for any past competition date. Used for professor's
validation exercise — proves the model is deterministic and reproducible.

```bash
python final.py --date 2026-07-05
```

- Trains on ENTSO-E data up to the day **before** the target date (no leakage)
- Fetches real archived weather for the target date from Open-Meteo archive API
- Uses identical LightGBM pipeline (same seed, same lags, same hyperparameters)
- Saves `data/validate/cross_predictions_YYYY-MM-DD.csv`

**Why the MAE may be slightly lower than competition:** The original submission used
a weather *forecast* for the target day. Reproduction uses real *archived* weather
(actual measured values). Perfect weather knowledge improves accuracy slightly —
this is expected and acceptable for validation purposes.

---

### `Cross_Validation.py` — Compare predictions vs ENTSO-E actuals

Reads all `cross_predictions_*.csv` files and scores each one against real ENTSO-E
load actuals.

```bash
# Score all days and highlight the most recent:
python Cross_Validation.py

# Highlight a specific day in the detail plot:
python Cross_Validation.py --date 2026-07-05
```

Outputs:
- Console: MAE, RMSE, MAPE per day + overall summary
- `data/cross_validation/cross_validation_summary.csv`
- `data/cross_validation/cross_validation_YYYY-MM-DD.png`

---

## Full validation workflow (professor's reproduction exercise)

```bash
# Step 1: reproduce a past forecast
python final.py --date 2026-07-05

# Step 2: compare against ENTSO-E actuals
python Cross_Validation.py --date 2026-07-05
```

Repeat Step 1 for each date you want to validate, then run Step 2 once to score all of them.

---

## Model pipeline (both scripts follow this exactly)

```
ENTSO-E data (2024-01-01 → DATA_END)
        │
        ▼
Ch 3: mark_outliers (Isolation Forest, contamination=0.005)
Ch 3: get_missing_weights (window=72h)
Ch 4: LinearlyInterpolateTS (ffill_bfill)
        │
        ▼
Ch 6: ExogBuilder (DE holidays + 5 RBF seasonal periods)
      + Open-Meteo weather (Frankfurt: temperature, wind, cloud cover, pressure…)
      + rolling windows (1D, 7D mean/max/min)
      + polynomial interactions (top 10 by mutual info)
        │
        ▼
Ch 7: ForecasterRecursiveLGBM
      LGBMRegressor(n_estimators=1000, lr=0.015, seed=2026, deterministic=True)
      WeightFunction: weekday=1x, weekend=3x, outlier=0x
      Lags: 1–24 + 48 + 168 + 336
        │
        ▼
Ch 8: predict LIVE_N_STEPS → slice 24h for target date
        │
        ▼
cross_predictions_YYYY-MM-DD.csv
```

---

## Data leakage protection

- **Load data**: `y_raw = y_raw.loc[:DATA_END_TS]` — hard clip at DATA_END. The model
  never sees any load value from the target date or later.
- **Weather**: reproduction uses archive actuals for the target day (not a leak for
  validation; original submission used forecasts as would happen in practice).

---

## Compliance

| Code Rule | What it means | Where applied |
|---|---|---|
| CR-1 | `setup_logging` is the first line | Block 1 |
| CR-2 | Deterministic: fixed seed=2026, pinned `DATA_START` | Block 3, 7 |
| CR-3 | No synthetic data; fail-loud on missing inputs | Block 2, 6 |
| CR-4 | LightGBM only — no PyTorch / TensorFlow | Block 7 |

---

## Course schedule

| Date | Topic |
|---|---|
| 2026-04-21 | Kick-off |
| 2026-04-28 | Background, Challenge |
| 2026-05-26 | Lecture |
| 2026-06-02 | Background: Data Preprocessing |
| 2026-06-09 | Background: Critical Infrastructure |
| 2026-06-23 | 2nd Interim Presentation |
| 2026-07-14 | Mock Exam |
| 2026-07-21 | 3rd Final Presentation: Challenge Winners |

---

## References

- [spotforecast2-safe docs](https://sequential-parameter-optimization.github.io/spotforecast2-safe/)
- [spotforecast2 docs](https://sequential-parameter-optimization.github.io/spotforecast2/)
- [Challenge leaderboard](https://bartzbeielstein.github.io/challenge-leaderboard/)
- [ENTSO-E Transparency Platform](https://transparency.entsoe.eu/)
- [Forecasting: Principles and Practice](https://otexts.com/fpp3/)
