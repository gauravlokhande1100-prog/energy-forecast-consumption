# Model Card: Team Gladiators — DDMO SoSe 26 Energy Load Forecasting Pipeline

This card describes the Team Gladiators forecasting pipeline for the DDMO SoSe 26 competition at TH Köln. It follows the Hugging Face Model Card Guidebook taxonomy and the EU AI Act compliance framework defined in Bartz-Beielstein (2026). It covers both the certified inference path (`spotforecast2-safe`) and the development toolkit (`spotforecast2`) used during model selection.

---

## 1. Model Details

| Field | Value |
| --- | --- |
| Name | Team Gladiators — DDMO SoSe 26 Forecasting Pipeline |
| Version | 1.1.0 |
| Type | Deterministic recursive multi-step LightGBM forecaster for hourly electricity load |
| Developed by | Gaurav Lokhande, Team Gladiators, TH Köln |
| Course | Data-Driven Modeling and Optimization (DDMO), SoSe 2026 |
| Certified inference | `spotforecast2-safe` v22.10.1 — deterministic, fail-safe, auditable |
| Development toolkit | `spotforecast2` v3.3.0 — tuning, visualization, explainability (NOT in production) |
| Production script | `forecast_real_entsoe.py` — daily submission pipeline |
| Validation script | `final.py` — reproducibility verification, isolated outputs |
| Language | Python 3.13 |
| Environment | `spot313` conda env |
| License | Academic and course use only |
| Repository | `gauravlokhande1100-prog/challenge-leaderboard` |
| Reference | Bartz-Beielstein (2026) Safety-Critical Time-Series Forecasting |
| Compliance | CR-1 \| CR-2 \| CR-3 \| CR-4 \| EU AI Act Art. 10, 11, 12, 13, 15 |

### Two-library architecture

| Library | Role | Used in production? |
| --- | --- | --- |
| `spotforecast2-safe` v22.10.1 | Certified inference path — deterministic, fail-safe, CR-1 to CR-4 | ✅ YES |
| `spotforecast2` v3.3.0 | Development only — Optuna tuning, SHAP, Plotly | ❌ NO |

`spotforecast2-safe` is the only library used in `forecast_real_entsoe.py`. It depends exclusively on numpy, pandas, scikit-learn, lightgbm, numba, pyarrow, requests, feature-engine, holidays, astral, and tqdm. It deliberately excludes plotly, matplotlib, spotoptim, optuna, torch, and tensorflow.

`spotforecast2` was used during development to select hyperparameters via Bayesian search (Optuna) and inspect feature importances via SHAP. Once validated, the configuration was promoted into `spotforecast2-safe` for the certified inference path.

### Responsibilities

| Responsibility | Party |
| --- | --- |
| `spotforecast2-safe` library development | Thomas Bartz-Beielstein |
| `spotforecast2` toolkit development | Thomas Bartz-Beielstein |
| Pipeline deployment, operation, and audit | Gaurav Lokhande, Team Gladiators |

---

## 2. Intended Use and Scope

### Production pipeline (`spotforecast2-safe`)
- Daily day-ahead load forecasting for Germany (DE)
- EU AI Act compliance demonstration
- Academic competition submission to DDMO SoSe 26 leaderboard
- Bit-for-bit reproducible — same input = same output

### Development toolkit (`spotforecast2`) — NOT in production
- Hyperparameter search via Optuna (`bayesian_search_forecaster`)
- Feature attribution via SHAP (`get_global_shap_feature_importance`)
- Interactive visualization via Plotly
- Model selection and experimentation only

### Out of scope
- Real-time or intraday forecasting
- Other countries or grid zones without retraining
- Production deployment without further safety validation
- Any stochastic or non-deterministic inference

---

## 3. How to Get Started

### Install

```bash
pip install spotforecast2-safe   # certified inference path
pip install spotforecast2        # development only — NOT for production
```

### Daily production workflow (`forecast_real_entsoe.py`)

```bash
# Step 1: Update DATA_END in forecast_real_entsoe.py
DATA_END = "YYYY-MM-DD 23:00"   # set to today's date

# Step 2: Run pipeline
conda activate spot313
cd C:\Users\Gaurav\DDMO_PY_ENV\ddmo-sose-26
python forecast_real_entsoe.py
# Outputs -> data/predictions_YYYY-MM-DD.csv
#            data/entsoe_fetched_YYYYMMDD_HHMM.csv
#            _cache/logs/task_safe_n_to_1_*.log

# Step 3: Submit
cd challenge-leaderboard
git pull upstream main --no-edit
copy "..\data\predictions_YYYY-MM-DD.csv" "submissions\team_gladiators\YYYY-MM-DD.csv"
python scripts\validate_submission.py --path submissions/team_gladiators/YYYY-MM-DD.csv --pr-author gauravlokhande1100-prog
git switch -c "submission/team_gladiators-YYYY-MM-DD" upstream/main
git add submissions\team_gladiators\YYYY-MM-DD.csv
git commit -m "submission(team_gladiators): forecast for YYYY-MM-DD"
git push -u origin "submission/team_gladiators-YYYY-MM-DD"
gh pr create --base main --repo bartzbeielstein/challenge-leaderboard --title "submission(team_gladiators): forecast for YYYY-MM-DD" --body "DDMO SoSe 26 - Team Gladiators LightGBM forecast"
```

### Validation workflow (`final.py`)

Used to verify that a past submission is reproducible and to confirm the reported MAE. Set `DATA_END` to the day before the submission date — the script automatically predicts the next day.

```bash
# Step 1: Set DATA_END to the day before the submission to verify
#         e.g. to verify the 2026-07-13 submission:
DATA_END = "2026-07-12 23:00"   # pinned — do NOT use today's date

# Step 2: Run validation pipeline
conda activate spot313
cd C:\Users\Gaurav\DDMO_PY_ENV\ddmo-sose-26
python final.py
# Outputs -> data/validate/predictions_YYYY-MM-DD.csv   (compare with submitted file)
#            data/validate/entsoe_fetched_YYYYMMDD_HHMM.csv
#            _cache/logs/validate/task_safe_n_to_1_*.log

# Step 3: Compare validate output with the originally submitted CSV
# If values match -> submission is reproducible -> reported MAE is verified
```

**Key reproducibility properties of `final.py`:**
- `TOMORROW_UTC` is derived from `DATA_END`, not the real-time clock — runs on any future date and always predicts the same target day
- `y_raw` is clipped to `DATA_END` after loading — shared cache cannot cause `LAST_FULL_HOUR` to overshoot
- All outputs go to `data/validate/` and `_cache/logs/validate/` — main script outputs are never touched

---

## 4. Technical Specification

### Task and model family

Recursive multi-step univariate forecasting of Germany's hourly electricity load using the `spotforecast2-safe` deterministic core. The model uses its own lagged predictions during the bridge period, plus real weather and calendar exogenous features.

### Mathematical description

For a univariate series $X = \{x_1, x_2, \ldots, x_T\}$ and a window of $w$ lags:

$$X_{row, t} = [x_{t-w}, x_{t-w+1}, \ldots, x_{t-1}] \rightarrow y_t = x_t$$

The target $y_t$ never appears in its own feature row — no look-ahead leakage by construction.

### Architecture — 11 blocks

| Block | Chapter | Purpose |
| --- | --- | --- |
| Block 0 | — | All imports at top (CR-2) |
| Block 1 | Ch 1 | `setup_logging` — CR-1 audit trail |
| Block 2 | Ch 2 | ENTSO-E API key fail-safe — CR-3 |
| Block 3 | Ch 2 | Pinned constants — CR-2 |
| Block 4 | Ch 2 | `download_new_data` + Actual/Forecasted Load fallback |
| Block 5 | Ch 3+4 | `mark_outliers` + `get_missing_weights(72)` + `LinearlyInterpolateTS` |
| Block 6 | Ch 13.5.3 | `LAST_FULL_HOUR` as `TRAIN_END` |
| Block 7 | Ch 6 | `ExogBuilder(country_code="DE")` + weather + poly features |
| Block 8 | Ch 7 | `ForecasterRecursiveLGBM` + `LGBMRegressor` |
| Block 9 | Ch 8 | Recursive predict → slice 24h → save CSV |
| Block 10 | Ch 10 | Rolling-origin backtest — 30 folds, Nov 2025 |
| Block 11 | Ch 13 | EU AI Act Compliance Dashboard |

### Lag construction

```python
KEY_LAGS = list(range(1, 25)) + [48, 168, 336]
# 27 lags: 1-24h (full day), 48h (2 days), 168h (1 week), 336h (2 weeks)
```

### LightGBM hyperparameters

Parameters were selected using `spotforecast2` (Optuna Bayesian search) during development and then promoted into `spotforecast2-safe` for certified inference:

```python
LGBMRegressor(
    n_estimators      = 1000,
    learning_rate     = 0.015,
    num_leaves        = 31,
    max_depth         = 6,
    min_child_samples = 35,
    subsample         = 0.8,
    colsample_bytree  = 0.7,
    reg_alpha         = 0.1,
    reg_lambda        = 1.5,
    deterministic     = True,   # CR-2: bit-identical output
    force_col_wise    = True,
    random_state      = 2026    # CR-2: fixed seed
)
```

### Feature engineering

| Feature group | Description |
| --- | --- |
| RBF calendar | 5 periods: daily, weekly, monthly, quarterly, yearly |
| Weekend flags | `is_weekend`, `is_weekday`, `day_integer_code` |
| Sin/cos × weekend | Interaction features |
| Weather archive | 8 vars from Open-Meteo (Frankfurt: 50.110924, 8.682127) |
| Weather forecast | Open-Meteo forecast API (past_days=7, forecast_days=3) |
| Rolling weather | 1D + 7D mean/max/min temperature windows |
| Polynomial | Top 10 weather interactions by mutual information (degree=2) |
| Holidays | Automatic via `ExogBuilder(country_code="DE")` |

### Weight function (Ch 3.7)

```python
weekend = 3x   # industrial load drops ~30-40% on weekends
outlier = 0x   # excluded from training loss
weekday = 1x   # baseline
```

### Bridge period (Ch 13.5.3)

```
LAST_FULL_HOUR = last non-NaN actual from ENTSO-E
FIRST_PRED     = LAST_FULL_HOUR + 1h
Bridge         = FIRST_PRED → tomorrow 00:00 (~2h typical)

Using Actual Load.fillna(Forecasted Load) reduces bridge from ~40h to ~2h
```

### Design objectives (inherited from `spotforecast2-safe`)

- **Deterministic**: same input → same output, bit for bit (CR-2)
- **Leakage-free**: target never appears in its own feature row
- **Fail-safe**: invalid input raises explicit exception, never silent repair (CR-3)

---

## 5. Data

### Training data sources

| Source | Range | Resolution | Real data? |
| --- | --- | --- | --- |
| ENTSO-E Actual Load | 2024-01-01 → today | 15-min → 1h | ✅ Yes |
| ENTSO-E Forecasted Load | 2024-01-01 → today+1 | 15-min → 1h | ✅ Yes |
| Open-Meteo archive | 2024-01-01 → today | 1h | ✅ Yes |
| Open-Meteo forecast | today-7 → today+3 | 1h | ✅ Yes |

### Pinned constants (CR-2)

```python
DATA_START  = "2024-01-01 00:00"   # never changes — pinned CR-2
DATA_END    = "YYYY-MM-DD 23:00"   # updated manually each day
RANDOM_SEED = 2026                 # fixed seed — CR-2
```

### Backtest evaluation range (Ch 5, CR-2)

```python
BT_TRAIN_END = pd.Timestamp("2025-10-31 23:00", tz="UTC")
BT_EVAL_END  = pd.Timestamp("2025-11-30 23:00", tz="UTC")
```

---

## 6. Data Governance and Compliance

### CR-3: Zero synthetic data

All data is real and observed. `spotforecast2-safe` rejects missing or infinite values by default — consistent with EU AI Act Art. 10(3).

| Data | Source | Synthetic? |
| --- | --- | --- |
| Actual Load | ENTSO-E | ❌ Never |
| Forecasted Load (fallback) | ENTSO-E | ❌ Real ENTSO-E forecast |
| Weather | Open-Meteo | ❌ Never |
| Calendar / holidays | ExogBuilder | ❌ Computed from real dates |

**If Open-Meteo fails:** `RuntimeError` raised immediately — no synthetic fallback:

```python
# CR-3: fail-loud — no synthetic data ever
raise RuntimeError(
    "CR-3: Weather API unavailable. "
    "Synthetic data violates EU AI Act Art. 10(3)."
)
```

**If Block 10 reaches weather=None:** `RuntimeError` raised — dead code guard:

```python
# CR-3: unreachable — Block 7 would have stopped script already
raise RuntimeError(
    "CR-3: weather_df is None in Block 10. "
    "Synthetic weather data is not permitted."
)
```

### EU AI Act article mapping

| Article | Requirement | Implementation |
| --- | --- | --- |
| Art. 10(2) | Data governance | ENTSO-E + Open-Meteo real data only |
| Art. 10(3) | Representativeness | No synthetic data, CR-3 fail-loud |
| Art. 11 | Technical documentation | This model card |
| Art. 12 | Logging | `setup_logging` — CR-1, every run, timestamped |
| Art. 13 | Transparency | Dashboard, CSV provenance, white-box code |
| Art. 15 | Accuracy/robustness | Backtest 30 folds, MAPE reported |

### Dependency audit (`spotforecast2-safe` runtime)

| Dependency | License | CVE surface |
| --- | --- | --- |
| numpy | BSD-3-Clause | minimal |
| pandas | BSD-3-Clause | minimal |
| scikit-learn | BSD-3-Clause | minimal |
| lightgbm | MIT | minimal |
| numba | BSD | minimal |
| pyarrow | Apache-2.0 | minimal |
| requests | Apache-2.0 | minimal |
| holidays | MIT | minimal |

No plotly, matplotlib, optuna, torch, or tensorflow in the certified path.

---

## 7. Evaluation

### Rolling-origin backtest (Ch 10, professor's exact code)

```python
cv = TimeSeriesFold(
    steps              = 24,
    initial_train_size = len(y_bt_train),   # Jan 2024 → Oct 2025
    refit              = False,
    fixed_train_size   = False,
)
```

### Backtest results (November 2025)

| Metric | Value |
| --- | --- |
| Evaluation period | November 2025 (30 days) |
| Folds | 30 (each = 24-hour day-ahead forecast) |
| Mean MAE | ~1,090 MW |
| Mean MAPE | ~2.0% |
| Median MAE | ~966 MW |
| Best fold MAE | ~458 MW |
| Worst fold MAE | ~2,239 MW |
| Target | < 3% MAPE ✅ MET |

### Competition submission history

| Date | PR | Status |
| --- | --- | --- |
| 2026-06-02 | #113 | ✅ Merged |
| 2026-06-03 | #130 | ✅ Merged |
| 2026-06-04 | #137 | ✅ Merged |
| 2026-06-05 | #161 | ✅ Merged |
| 2026-06-06 | #171 | ✅ Merged |
| 2026-06-08 | #216 | ✅ Merged |
| 2026-06-09 | #243 | ✅ Merged |
| 2026-06-13 | #323 | ✅ Merged |
| 2026-06-17 | #410 | ✅ Merged |
| 2026-07-13 | — | 🔍 Validation only — reproduced via `final.py` (MAE ~556 MW) |
| 2026-07-18 | — | 🔍 Validation only — reproduced via `final.py` |

---

## 8. Compliance Rules (CR-1 to CR-4)

| Rule | Requirement | Implementation | Status |
| --- | --- | --- | --- |
| CR-1 | `setup_logging` must be first line | Block 1, Line 74 | ✅ |
| CR-2 | Pinned constants, `deterministic=True`, `random_state=2026` | Block 3, Block 8 | ✅ |
| CR-3 | Fail-loud on missing data, no synthetic fallback | Block 2, 7, 10 | ✅ |
| CR-4 | LightGBM only — no PyTorch, TensorFlow, neural nets | Block 8 | ✅ |

---

## 9. Model Transparency

### White-box code
- All code open and inspectable in `forecast_real_entsoe.py`
- No compiled inference kernels
- No opaque weights
- No pretrained models

### Audit trail

**Production run (`forecast_real_entsoe.py`):**
- Log: `_cache/logs/task_safe_n_to_1_YYYYMMDD_HHMMSS.log`
- Raw data: `data/entsoe_fetched_YYYYMMDD_HHMM.csv`
- Predictions: `data/predictions_YYYY-MM-DD.csv`
- Dashboard: Panel 1 (forecast) + Panel 2 (backtest MAE histogram)

**Validation run (`final.py`) — fully isolated, never overwrites production:**
- Log: `_cache/logs/validate/task_safe_n_to_1_YYYYMMDD_HHMMSS.log`
- Raw data: `data/validate/entsoe_fetched_YYYYMMDD_HHMM.csv`
- Predictions: `data/validate/predictions_YYYY-MM-DD.csv`
- Shared cache: `_cache/spotforecast2_data/` (read-only effective — `force=False` is additive)

### Dashboard (Block 11)
```
Panel 1: LightGBM forecast vs Persistence vs ENTSO-E (visual ref)
Panel 2: Rolling-origin MAE histogram — 30 folds, MW + MAPE%
```

### Development transparency (`spotforecast2`)
- SHAP feature importances computed during model selection
- Optuna search logged with fixed `random_state`
- Selected configuration promoted unchanged into `spotforecast2-safe`

---

## 10. Operation and Monitoring

### Daily workflow
```
Production  : Update DATA_END → python forecast_real_entsoe.py → submit data/predictions_*.csv
Validation  : Set DATA_END to day-before target → python final.py → compare data/validate/predictions_*.csv
```

### Failure modes and responses

| Failure | Script | Detection | Response |
| --- | --- | --- | --- |
| ENTSO-E API key missing | both | `ValueError` Block 2 | Check `.env` file |
| ENTSO-E API down | both | `download_new_data` error | Wait + retry |
| Open-Meteo API down | both | `RuntimeError` Block 7 | Check internet + retry |
| Bridge > 24h | production | Log warning | Delete cache + re-run |
| Cache overshoot (`LAST_FULL_HOUR` > `DATA_END`) | validation | `KeyError` Block 9 | Fixed by `y_raw` clip at `DATA_END` |
| CSV validation fails | production | `validate_submission.py` | Check format |
| Backtest fails | both | `WARNING` log Block 10 | Check `skforecast` version |

### Retraining cadence
- `DATA_END` updated manually every day
- Model retrained from scratch every run (no cached weights)
- No maximum-age policy needed — daily retraining guaranteed

---

## 11. Limitations

| Limitation | Description |
| --- | --- |
| Point forecasts only | No prediction intervals or calibrated probabilities |
| Germany (DE) only | Not transferable to other zones without retraining |
| Fixed hyperparameters | Not auto-tuned at inference time |
| Frankfurt weather only | Does not cover full Germany weather grid |
| Backtest on Nov 2025 | Seasonal variation not fully captured |
| No GPU | CPU only — no GPU acceleration |
| `spotforecast2` not in production | Tuning and visualization excluded from certified path |

---

## 12. How to Audit

**Production (`forecast_real_entsoe.py`):**
1. Confirm imports only from `spotforecast2_safe` — not from `spotforecast2`
2. Confirm no synthetic data: search for `monthly_temp`, `= 75.0`, `= 1013.0` — none found
3. Confirm `setup_logging` is the first active code line (Block 1)
4. Confirm `DATA_START = "2024-01-01 00:00"` is never changed
5. Confirm `deterministic=True` and `random_state=2026` in `LGBMRegressor`
6. Confirm `RuntimeError` raised on weather failure — not silent fallback
7. Review audit log: `_cache/logs/task_safe_n_to_1_*.log`
8. Review raw data: `data/entsoe_fetched_*.csv`
9. Verify submission CSV format: `timestamp_utc` + `forecast_mw`, exactly 24 rows

**Validation (`final.py`):**
10. Confirm `TOMORROW_UTC` is derived from `DATA_END`, not `datetime.now()` — ensures reproducibility
11. Confirm `y_raw = y_raw.loc[:DATA_END_TS]` clip is present — prevents cache overshoot
12. Confirm `OUTPUT_DIR` points to `data/validate/` — isolated from production outputs
13. Confirm `log_dir` points to `_cache/logs/validate/` — isolated audit log
14. To verify a past submission: set `DATA_END` to day before target, run `final.py`, compare `data/validate/predictions_*.csv` with submitted file

---

## 13. Citation

### Pipeline

```bibtex
@misc{team_gladiators_ddmo2026,
  author = {Lokhande, Gaurav},
  title  = {Team Gladiators DDMO SoSe 26 Forecasting Pipeline},
  year   = {2026},
  note   = {TH Köln, Data-Driven Modeling and Optimization, SoSe 2026}
}
```

### Framework (`spotforecast2-safe`)

```bibtex
@misc{spotforecast2safe,
  author       = {Bartz-Beielstein, Thomas},
  title        = {{spotforecast2-safe}: Safety-critical Subset of {spotforecast2}},
  year         = {2026},
  howpublished = {\url{https://github.com/sequential-parameter-optimization/spotforecast2-safe}},
  note         = {AGPL-3.0-or-later}
}
```

### Development toolkit (`spotforecast2`)

```bibtex
@misc{spotforecast2,
  author       = {Bartz-Beielstein, Thomas},
  title        = {{spotforecast2}: Forecasting Toolkit with Tuning, Visualization, and Explainability},
  year         = {2026},
  howpublished = {\url{https://github.com/sequential-parameter-optimization/spotforecast2}},
  note         = {AGPL-3.0-or-later}
}
```

### Reference textbook

Bartz-Beielstein, T. (2026). *Safety-Critical Time-Series Forecasting with spotforecast2-safe*. TH Köln.

---

## 14. Disclaimer and Liability

**Limitation of liability.** This pipeline is provided as-is for academic purposes. The developers assume no liability for any direct or indirect damages arising from its use.

This pipeline is developed for the DDMO SoSe 26 course at TH Köln. It follows the EU AI Act compliance framework defined by the course instructor. The certified inference path runs exclusively on `spotforecast2-safe`. The `spotforecast2` development toolkit was used only during model selection and is not part of the production pipeline.

For production or safety-critical deployment, full system-level safety validation under ISO 26262, IEC 61508, or the EU AI Act is required before going live.
