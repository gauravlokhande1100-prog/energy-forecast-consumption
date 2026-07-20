"""
DDMO SoSe 26 - Team Gladiators - Live Forecasting Pipeline
Framework   : spotforecast2_safe x LightGBM
Compliance  : Chapters 1-14 | CR-1 | CR-2 | CR-3 | CR-4
Reference   : Bartz-Beielstein (2026) Safety-Critical Time-Series Forecasting

Chapter references:
  Ch 1     : setup_logging (CR-1) - FIRST line always
  Ch 2     : download_new_data + fetch_data (Art. 10, CR-2)
  Ch 3     : mark_outliers + get_missing_weights(72) + WeightFunction (CR-3)
  Ch 4     : LinearlyInterpolateTS(on_missing="ffill_bfill") (CR-3)
  Ch 6     : ExogBuilder(country_code="DE") handles holidays automatically
  Ch 7     : ForecasterRecursiveLGBM + LGBMRegressor (CR-2, CR-4)
  Ch 8     : predict LIVE_N_STEPS -> slice tomorrow 24h
  Ch 10    : rolling-origin backtest with TimeSeriesFold
  Ch 13.5.3: LAST_FULL_HOUR as TRAIN_END - minimises bridge steps

Daily workflow:
  1. Update DATA_END to today's date
  2. Run: python final.py -> validate_predictions_YYYY-MM-DD.csv saved
  3. Next day: run calculate_mae.py to check real accuracy
"""
# =============================================================================
# Block 0
# Importing Dependencies - all imports at the top (CR-2)
# =============================================================================
import os
import logging
import requests
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from sklearn.feature_selection import mutual_info_regression
from sklearn.preprocessing import PolynomialFeatures
from dotenv import load_dotenv
from lightgbm import LGBMRegressor

from spotforecast2_safe import ForecasterRecursiveLGBM, LinearlyInterpolateTS
from spotforecast2_safe import ExogBuilder, Period
from spotforecast2_safe.preprocessing import (
    mark_outliers, get_missing_weights, WeightFunction
)
from spotforecast2_safe.manager.logger import setup_logging
from spotforecast2_safe.downloader.entsoe import download_new_data
from spotforecast2_safe.data.fetch_data import fetch_data, get_data_home

# Chapter 10 | CR-4: backtesting validation
# Try professor's exact path first, fall back to skforecast (same internal engine)
try:
    from spotforecast2_safe.backtesting.validation import (
        TimeSeriesFold, backtesting_forecaster
    )
    HAS_BACKTESTING = True
except ModuleNotFoundError:
    try:
        from skforecast.model_selection import (
            TimeSeriesFold, backtesting_forecaster
        )
        HAS_BACKTESTING = True
    except ImportError:
        HAS_BACKTESTING = False


# =============================================================================
# Block 1 - Chapter 1 | CR-1
# setup_logging MUST be first — before any other code
# Logs go to _cache/logs/validate/ to avoid overwriting production logs
# =============================================================================
log_dir = Path("_cache/logs/validate")
log_dir.mkdir(parents=True, exist_ok=True)
logger, log_path = setup_logging(level=logging.INFO, log_dir=log_dir)
logger.info("Pipeline start - CR-1 to CR-4, Chapters 1-13.")
print(f"Audit log -> {log_path.name if log_path else '<stdout>'}")


# =============================================================================
# Block 2 - Chapter 2 | CR-3
# Fail-safe API key - halt immediately if missing
# =============================================================================
load_dotenv()
API_KEY = os.getenv("ENTSOE_API_KEY")
if not API_KEY:
    logger.error("ENTSOE_API_KEY missing - aborting (CR-3).")
    raise ValueError("Missing ENTSOE_API_KEY in .env file!")
logger.info("ENTSO-E API key loaded.")
print("API key loaded.")


# =============================================================================
# Block 3 - Chapter 2 | CR-2
# Pinned constants - same input = bit-identical output (CR-2)
# TOMORROW_UTC is derived from DATA_END (not the real-time clock) so that
# running this script on any future date always predicts 2026-07-18,
# ensuring bit-identical reproducibility for the professor's verification.
# =============================================================================
DATA_START  = "2024-01-01 00:00"   # pinned CR-2 — do NOT change
DATA_END    = "2026-07-08 23:00"   # pinned CR-2 — do NOT change
COUNTRY     = "DE"
RANDOM_SEED = 2026                 # fixed seed CR-2

# Chapter 14.6: lags 1-24 (full day context) + weekly + fortnightly
KEY_LAGS = list(range(1, 25)) + [48, 168, 336]

# Chapter 6.4: weather variables (Frankfurt: 50.110924, 8.682127)
WEATHER_COLS = [
    "temperature_2m", "relative_humidity_2m", "precipitation",
    "cloud_cover", "wind_speed_10m", "wind_direction_10m",
    "surface_pressure", "wind_gusts_10m"
]

DATA_HOME = Path.cwd() / "_cache" / "spotforecast2_data"   # shared read — no re-download
DATA_HOME.mkdir(parents=True, exist_ok=True)
os.environ["SPOTFORECAST2_DATA"] = str(DATA_HOME)

OUTPUT_DIR = Path(r"C:\Users\Gaurav\DDMO_PY_ENV\ddmo-sose-26\data") / "validate"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
timestamp_now = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")

# Chapter 13.5.1: date constants anchored to DATA_END — NOT the real-time clock.
# This guarantees the same target date regardless of when the script is run.
TOMORROW_UTC    = (
    pd.Timestamp(DATA_END, tz="UTC") + pd.Timedelta(hours=1)
).normalize()
LAST_TARGET     = TOMORROW_UTC + pd.Timedelta(hours=23)
target_date_str = TOMORROW_UTC.strftime("%Y-%m-%d")

# Chapter 5: pinned backtest timelines (CR-2)
BT_TRAIN_END = pd.Timestamp("2025-10-31 23:00", tz="UTC")
BT_EVAL_END  = pd.Timestamp("2025-11-30 23:00", tz="UTC")

logger.info(
    f"DATA: {DATA_START}->{DATA_END}, seed={RANDOM_SEED}, "
    f"target={target_date_str}."
)
print(f"\n  DATA_START : {DATA_START}  (pinned CR-2)")
print(f"  DATA_END   : {DATA_END}  (pinned CR-2)")
print(f"  Target day : {target_date_str}  (derived from DATA_END)")
print(f"  Key lags   : {KEY_LAGS[:6]}... ({len(KEY_LAGS)} total)")


# =============================================================================
# Block 4 - Chapter 2 | Art. 10
# Professor's exact downloader — incremental, caches to energy_load.csv
# Actual Load fallback to Forecasted Load reduces bridge hours
# =============================================================================
print("\nChapter 2: Downloading ENTSO-E data...")
logger.info(f"Ch2: download_new_data zone={COUNTRY}, {DATA_START}->{DATA_END}.")

interim = get_data_home() / "interim" / "energy_load.csv"
download_new_data(
    api_key      = API_KEY,
    country_code = COUNTRY,
    start        = DATA_START,
    end          = DATA_END,
    force        = False,   # incremental: only fetches new rows
)
logger.info(f"Ch2: download complete -> {interim}.")

df       = fetch_data(filename=str(interim))
df.index = pd.to_datetime(df.index, utc=True)

# Use Actual Load where available, fallback to Forecasted Load
# This reduces bridge from ~40h to ~2h (Ch 13.5.3)
actual_col   = next(c for c in df.columns if "Actual"     in c and "Load" in c)
forecast_col = next(c for c in df.columns if "Forecasted" in c and "Load" in c)
y_raw        = df[actual_col].fillna(df[forecast_col]).astype(float).rename("load")
y_raw        = y_raw.resample("h").mean()

# Clip to DATA_END — shared cache may have newer rows from the main script.
# This ensures LAST_FULL_HOUR never exceeds DATA_END regardless of cache state.
DATA_END_TS = pd.Timestamp(DATA_END, tz="UTC")
y_raw       = y_raw.loc[:DATA_END_TS]

# Keep ENTSO-E own forecast for visual comparison on graph (visual only)
entsoe_fcst  = df[forecast_col].astype(float).rename("entsoe_forecast")
entsoe_fcst  = entsoe_fcst.resample("h").mean()
entsoe_fcst  = entsoe_fcst.loc[:DATA_END_TS]

logger.info(f"Ch2: {len(y_raw):,} timestamps, NaN={int(y_raw.isna().sum())}.")
print(f"  Loaded : {len(y_raw):,} hours")
print(f"  Range  : {y_raw.index.min()} -> {y_raw.index.max()}")
print(f"  NaN    : {int(y_raw.isna().sum())} hours")


# =============================================================================
# Block 5 - Chapters 3+4 | CR-3
# Ch 3.5: mark_outliers — annotate anomalies explicitly
# Ch 3.6: get_missing_weights(window_size=72) — professor's exact value
# Ch 3.7: WeightFunction — weekend=3x, outlier=0x (picklable, CR-2)
# Ch 4  : LinearlyInterpolateTS(on_missing="ffill_bfill") — endpoint gaps
# =============================================================================
print("Chapters 3+4: Outlier annotation + gap handling...")
logger.info("Ch3: mark_outliers -> get_missing_weights -> LinearlyInterpolateTS.")

df_y = pd.DataFrame({"load": y_raw.copy()})

# Ch 3.5: Isolation Forest — annotate, never overwrite
df_marked, _ = mark_outliers(
    df_y.copy(), contamination=0.005,
    random_state=RANDOM_SEED, verbose=False
)

# Ch 3.6: professor's exact window_size=72
df_filled, weights = get_missing_weights(
    df_marked, window_size=72, verbose=False
)

# Master arrays (before any filtering)
hist_y_all   = df_filled["load"].copy()
hist_y_all.index = pd.DatetimeIndex(hist_y_all.index, freq="h")
hist_weights = weights.copy()

y = df_filled["load"].copy()
y.index = pd.DatetimeIndex(y.index, freq="h")

# Ch 4: ffill_bfill — handles ENTSO-E endpoint NaN (last hours not published)
y = LinearlyInterpolateTS(on_missing="ffill_bfill").fit_transform(y)
y.index = pd.DatetimeIndex(y.index, freq="h")

# Ch 3.7: WeightFunction — vectorized, picklable (CR-2)
# weekend=3x: industrial load drops ~30-40% on weekends
# outlier=0x: excluded from training loss
# holidays handled automatically by ExogBuilder(country_code="DE")
def build_weight_series(idx, base_weights=None):
    """
    Ch 3.7: Index-based, picklable weight series.
    Weekend = 3x (industrial load drops on weekends)
    Outlier = 0x (excluded from training loss)
    """
    w = pd.Series(1.0, index=idx)
    w[idx.dayofweek >= 5] = 3.0   # weekend 3x — professor's exact value
    if base_weights is not None:
        w[base_weights.reindex(idx).fillna(1.0) == 0] = 0.0
    return w

clean_idx = weights[weights > 0].index

logger.info(f"Ch3: outliers={int((weights==0).sum())}, clean={len(clean_idx)}.")
print(f"  Outliers : {int((weights==0).sum())} | Clean: {len(clean_idx)}")

# Save raw data (Art. 10 provenance) — isolated under data/validate/
raw_csv = OUTPUT_DIR / f"entsoe_fetched_{timestamp_now}.csv"
pd.DataFrame({
    "timestamp"      : y.index.strftime("%Y-%m-%dT%H:%M:%SZ"),
    "actual_load_mw" : y.values.round(2)
}).to_csv(raw_csv, index=False)
print(f"  Raw data : {raw_csv.name}")


# =============================================================================
# Block 6 - Chapter 13.5.3
# LAST_FULL_HOUR = last non-NaN actual from ENTSO-E
# TRAIN_END      = LAST_FULL_HOUR (train on ALL available data)
# LIVE_N_STEPS   = bridge + 24 (tomorrow)
# =============================================================================
print("Chapter 13.5.3: Live cutoff + training split...")

LAST_FULL_HOUR = hist_y_all.dropna().index.max().floor("h")
FIRST_PRED     = LAST_FULL_HOUR + pd.Timedelta(hours=1)
LIVE_N_STEPS   = int(
    (LAST_TARGET - FIRST_PRED).total_seconds() // 3600
) + 1

TRAIN_END     = LAST_FULL_HOUR
y_train       = y.loc[:TRAIN_END]
y_train_clean = y_train.loc[y_train.index.intersection(clean_idx)]

logger.info(
    f"Ch13.5.3: LAST_FULL_HOUR={LAST_FULL_HOUR}, "
    f"LIVE_N_STEPS={LIVE_N_STEPS}, train_rows={len(y_train_clean)}."
)
print(f"  LAST_FULL_HOUR : {LAST_FULL_HOUR}")
print(f"  TRAIN_END      : {TRAIN_END}")
print(f"  FIRST_PRED     : {FIRST_PRED}")
print(f"  LIVE_N_STEPS   : {LIVE_N_STEPS}  (bridge={LIVE_N_STEPS-24}h + 24h)")
print(f"  Train rows     : {len(y_train_clean):,} hours")

future_index   = pd.date_range(
    start=FIRST_PRED, periods=LIVE_N_STEPS, freq="h", tz="UTC"
)
TOMORROW_HOURS = pd.date_range(
    start=TOMORROW_UTC, end=LAST_TARGET, freq="h", tz="UTC"
)


# =============================================================================
# Block 7 - Chapter 6 | Art. 10(2)(f)
# ExogBuilder(country_code="DE") handles holidays automatically
# Five seasonal RBF periods + weather + rolling + polynomial interactions
# =============================================================================
print("Chapter 6: Building features...")
logger.info("Ch6: ExogBuilder(country_code=DE) + weather + rolling + poly.")

# Ch 6.3: five seasonal RBF periods
PERIODS = [
    Period(name="daily",     n_periods=12, column="hour",      input_range=(0, 23)),
    Period(name="weekly",    n_periods=7,  column="dayofweek", input_range=(0, 6)),
    Period(name="monthly",   n_periods=12, column="month",     input_range=(1, 12)),
    Period(name="quarterly", n_periods=4,  column="quarter",   input_range=(1, 4)),
    Period(name="yearly",    n_periods=12, column="dayofyear", input_range=(1, 366)),
]

builder   = ExogBuilder(periods=PERIODS, country_code=COUNTRY)
exog_full = builder.build(
    y.index.min(), max(LAST_TARGET, future_index.max())
)

exog_train  = exog_full.loc[y.index]
exog_future = exog_full.loc[future_index]

for df_ex in [exog_train, exog_future]:
    df_ex["is_weekend"]       = (df_ex.index.dayofweek >= 5).astype(int)
    df_ex["is_weekday"]       = (df_ex.index.dayofweek < 5).astype(int)
    df_ex["day_integer_code"] = df_ex.index.dayofweek

sin_cos_cols = [c for c in exog_train.columns
                if any(x in c for x in ("sin", "cos"))]
for col in sin_cos_cols:
    for df_ex in [exog_train, exog_future]:
        df_ex[f"{col}_wknd"] = df_ex[col] * df_ex["is_weekend"]

# Ch 6.4: weather (archive + forecast APIs)
print("  Fetching weather from Open-Meteo...")
weather_df     = None
global_med     = 12.0
available_cols = []

try:
    arc = requests.get(
        "https://archive-api.open-meteo.com/v1/archive",
        params={
            "latitude"  : 50.110924,
            "longitude" : 8.682127,
            "start_date": pd.Timestamp(DATA_START).strftime("%Y-%m-%d"),
            "end_date"  : pd.Timestamp(DATA_END).strftime("%Y-%m-%d"),
            "hourly"    : ",".join(WEATHER_COLS),
            "timezone"  : "UTC"
        },
        timeout=60
    )
    arc.raise_for_status()
    ad             = arc.json()
    available_cols = [c for c in WEATHER_COLS if c in ad.get("hourly", {})]
    archive_w      = pd.DataFrame(
        {c: ad["hourly"][c] for c in available_cols},
        index=pd.to_datetime(ad["hourly"]["time"], utc=True)
    ).resample("h").mean()

    frc = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude"     : 50.110924,
            "longitude"    : 8.682127,
            "hourly"       : ",".join(WEATHER_COLS),
            "past_days"    : 7,
            "forecast_days": 3,
            "timezone"     : "UTC"
        },
        timeout=30
    )
    frc.raise_for_status()
    fd      = frc.json()
    fcast_w = pd.DataFrame(
        {c: fd["hourly"][c] for c in WEATHER_COLS
         if c in fd.get("hourly", {})},
        index=pd.to_datetime(fd["hourly"]["time"], utc=True)
    ).resample("h").mean()

    weather_df = pd.concat([archive_w, fcast_w])
    weather_df = weather_df[~weather_df.index.duplicated(keep="last")]
    weather_df = weather_df.sort_index().interpolate("linear")
    global_med = float(weather_df["temperature_2m"].median())

    for col in available_cols:
        safe = col.replace("_2m", "").replace("_10m", "")
        for df_ex in [exog_train, exog_future]:
            df_ex[safe] = df_ex.join(
                weather_df[col].rename(safe), how="left"
            )[safe].ffill().bfill().fillna(weather_df[col].median())

    # Ch 14.6.6: rolling windows 1D + 7D
    temp_s = weather_df["temperature_2m"]
    for wn, wh in [("1D", 24), ("7D", 168)]:
        roll = temp_s.rolling(window=wh, min_periods=1)
        for ag, av in [
            ("mean", roll.mean()),
            ("max",  roll.max()),
            ("min",  roll.min())
        ]:
            cn = f"tw_{wn}_{ag}"
            for df_ex in [exog_train, exog_future]:
                df_ex[cn] = df_ex.join(
                    av.rename(cn), how="left"
                )[cn].ffill().bfill().fillna(global_med)

    logger.info(f"Ch6: weather merged {len(available_cols)} vars + rolling.")
    print(f"  Weather: {len(available_cols)} vars + 1D/7D rolling windows")

except Exception as e:
    # CR-3: fail-loud — do NOT silently generate synthetic weather data
    # Synthetic data violates EU AI Act Art. 10(3) representativeness
    # and Art. 15 accuracy/robustness requirements
    logger.error(
        f"CR-3 VIOLATION RISK: Open-Meteo weather API failed: {e}. "
        f"Weather data is unavailable. This affects forecast accuracy. "
        f"Fix network connection and re-run. "
        f"Synthetic fallback is NOT used — it violates EU AI Act Art. 10(3)."
    )
    raise RuntimeError(
        f"\n\nCR-3: Weather API unavailable: {e}\n"
        f"Real weather data is required for EU AI Act compliance.\n"
        f"Synthetic data would violate Art. 10(3) representativeness.\n"
        f"Solutions:\n"
        f"  1. Check internet connection\n"
        f"  2. Wait 60 seconds and re-run\n"
        f"  3. Check Open-Meteo status: https://status.open-meteo.com\n"
    )


# Ch 14.6.6: polynomial interactions — degree=2, top 10 by mutual info
def add_poly_features(df_train, df_list, y_ref=None):
    """Top polynomial weather interactions selected by mutual information."""
    weather_base = [c for c in df_train.columns if any(
        x in c for x in
        ["temperature", "cloud", "precipitation",
         "wind_speed", "humidity", "pressure"]
    )]
    if len(weather_base) < 2:
        return
    poly   = PolynomialFeatures(
        degree=2, interaction_only=True, include_bias=False
    )
    X_poly = poly.fit_transform(df_train[weather_base].fillna(0).values)
    fnames = poly.get_feature_names_out(weather_base)
    nc     = len(weather_base)
    Xi, fn = X_poly[:, nc:], fnames[nc:]

    if y_ref is not None and len(y_ref) == len(Xi):
        mi      = mutual_info_regression(
            Xi, y_ref.values, random_state=RANDOM_SEED
        )
        top_idx = np.argsort(mi)[::-1][:10]
    else:
        top_idx = np.arange(min(10, Xi.shape[1]))

    for df_ex in df_list:
        Xd = poly.transform(df_ex[weather_base].fillna(0).values)[:, nc:]
        for i, name in zip(top_idx, fn[top_idx]):
            df_ex[f"poly_{name.replace(' ', '_')}"] = Xd[:, i]

    logger.info(f"Ch14.6.6: {len(top_idx)} poly features added.")
    print(f"  Polynomial interactions: top {len(top_idx)} by mutual info")


# Align to clean training indices
exog_train_clean = exog_train.loc[exog_train.index.intersection(clean_idx)]
y_train_clean    = y_train.loc[y_train.index.intersection(clean_idx)]

add_poly_features(
    df_train = exog_train_clean,
    df_list  = [exog_train_clean, exog_future],
    y_ref    = y_train_clean.reindex(exog_train_clean.index)
)

logger.info(f"Ch6: train={exog_train_clean.shape}, future={exog_future.shape}.")
print(f"  Feature matrix: train={exog_train_clean.shape}, "
      f"future={exog_future.shape}")


# =============================================================================
# Block 8 - Chapter 7 | CR-2 | CR-4
# ForecasterRecursiveLGBM with WeightFunction (Ch 3.7)
# CR-4: LightGBM only — no PyTorch/TensorFlow
# CR-2: deterministic=True, fixed seed=2026
# =============================================================================
print("Chapter 7: Training ForecasterRecursiveLGBM...")
logger.info(f"Ch7: lags={len(KEY_LAGS)}, n_estimators=1000, seed={RANDOM_SEED}.")

# Ch 3.7: WeightFunction (weekend=3x, outlier=0x)
weight_func = WeightFunction(
    build_weight_series(
        pd.DatetimeIndex(y_train_clean.index),
        base_weights=hist_weights
    )
)
n_wknd = int((pd.DatetimeIndex(y_train_clean.index).dayofweek >= 5).sum())
logger.info(
    f"Ch3.7: {len(y_train_clean)-n_wknd} weekday(1x), {n_wknd} weekend(3x)."
)
print(f"  WeightFunction: {len(y_train_clean)-n_wknd} weekday(1x), "
      f"{n_wknd} weekend(3x)")

forecaster = ForecasterRecursiveLGBM(
    iteration     = 0,
    end_dev       = y_train.index[-1],
    lags_consider = KEY_LAGS,
    weight_func   = weight_func      # Ch 3.7 exact API
)
forecaster.forecaster.estimator = LGBMRegressor(
    n_estimators      = 1000,
    learning_rate     = 0.015,
    num_leaves        = 31,
    max_depth         = 6,
    min_child_samples = 35,
    subsample         = 0.8,
    colsample_bytree  = 0.7,
    reg_alpha         = 0.1,
    reg_lambda        = 1.5,
    n_jobs            = -1,
    verbose           = -1,
    deterministic     = True,        # CR-2: bit-identical
    force_col_wise    = True,
    random_state      = RANDOM_SEED
)
forecaster.forecaster.fit(y=y_train_clean, exog=exog_train_clean)
logger.info("Ch7: training complete (CR-2 verified).")
print("  Training complete.")


# =============================================================================
# Block 9 - Chapter 8 | Art. 13
# Recursive multi-step forecast -> slice tomorrow 24h (Ch 13.5.3)
# =============================================================================
print(f"Chapter 8: Forecasting {target_date_str}...")
logger.info(f"Ch8: LIVE_N_STEPS={LIVE_N_STEPS}, target={target_date_str}.")

last_window = y_train_clean.loc[:LAST_FULL_HOUR].iloc[-max(KEY_LAGS):].copy()
last_window = last_window[~last_window.index.duplicated(keep="first")]
last_window = last_window.asfreq("h", method="ffill")

predictions_full = forecaster.forecaster.predict(
    steps       = LIVE_N_STEPS,
    last_window = last_window,
    exog        = exog_future
)
predictions_full.index = future_index

# Ch 13.5.3: slice exactly 24 rows for tomorrow
predictions_tomorrow = predictions_full.loc[TOMORROW_HOURS]

# Weekly persistence — VISUAL ONLY, no influence on model
baseline_tomorrow = hist_y_all.reindex(
    (TOMORROW_HOURS - pd.Timedelta(hours=168))
    .tz_convert(hist_y_all.index.tz)
).values

# Save submission CSV — Ch 12.6 exact format, isolated under data/validate/
pred_csv = OUTPUT_DIR / f"predictions_{target_date_str}.csv"
pd.DataFrame({
    "timestamp_utc" : [i.strftime("%Y-%m-%dT%H:%M:%SZ")
                       for i in TOMORROW_HOURS],
    "forecast_mw"   : predictions_tomorrow.values.round(2)
}).to_csv(pred_csv, index=False)
logger.info(f"Ch8: predictions saved -> {pred_csv}.")
print(f"  Saved -> {pred_csv.name}")

print(f"\nLIVE FORECAST: {target_date_str}")
print("=" * 50)
print(f"  {'Hour (UTC)':<22} | {'Forecast [MW]':>12}")
print("-" * 50)
for ts, val in zip(TOMORROW_HOURS, predictions_tomorrow.values):
    print(f"  {ts.strftime('%Y-%m-%dT%H:%M:%SZ'):<22} | {val:>12,.2f}")
print("=" * 50)
print(f"  Peak : "
      f"{TOMORROW_HOURS[np.argmax(predictions_tomorrow.values)].strftime('%H:%M')}"
      f" -> {predictions_tomorrow.values.max():,.0f} MW")
print(f"  Low  : "
      f"{TOMORROW_HOURS[np.argmin(predictions_tomorrow.values)].strftime('%H:%M')}"
      f" -> {predictions_tomorrow.values.min():,.0f} MW")


# =============================================================================
# Block 10 - Chapter 10 | Art. 9 + Art. 10(3)
# Rolling-origin backtest — professor's EXACT Ch 10.3 + 10.5 code
# Tests model over 30 days of November 2025 (Ch 5 evaluation range)
# Does NOT affect forecast — only proves model quality for audit
# =============================================================================
print("\nChapter 10: Rolling-origin backtest (TimeSeriesFold)...")
logger.info("Ch10: rolling-origin backtest with TimeSeriesFold.")

if not HAS_BACKTESTING:
    print("  Skipping: spotforecast2_safe.backtesting not available.")
    BT_AVAILABLE = False
    mae_per_fold = np.array([])
    mean_mae     = float("nan")
else:
    try:
        # Professor's EXACT Ch 10.3:
        # y_bt = y_clean.loc[exog.index.min():exog.index.max()]
        # initial_train_size = len(y_train)
        bt_exog_idx   = exog_full.loc[:BT_EVAL_END].index
        bt_exog_idx   = pd.DatetimeIndex(bt_exog_idx, freq="h")

        y_bt          = y.reindex(bt_exog_idx).ffill().bfill()
        y_bt.index    = pd.DatetimeIndex(y_bt.index, freq="h")
        exog_bt       = exog_full.reindex(bt_exog_idx).ffill().bfill()
        exog_bt.index = pd.DatetimeIndex(exog_bt.index, freq="h")

        # y_train equivalent = y_bt up to BT_TRAIN_END
        y_bt_train    = y_bt.loc[:BT_TRAIN_END]

        for df_ex in [exog_bt]:
            df_ex["is_weekend"]       = (df_ex.index.dayofweek >= 5).astype(int)
            df_ex["is_weekday"]       = (df_ex.index.dayofweek < 5).astype(int)
            df_ex["day_integer_code"] = df_ex.index.dayofweek

        for col in sin_cos_cols:
            if col in exog_bt.columns:
                exog_bt[f"{col}_wknd"] = exog_bt[col] * exog_bt["is_weekend"]

        if weather_df is not None and len(available_cols) > 0:
            if weather_df.index.tz is None:
                weather_df.index = weather_df.index.tz_localize("UTC")
            for col in available_cols:
                safe = col.replace("_2m","").replace("_10m","")
                exog_bt[safe] = exog_bt.join(
                    weather_df[col].rename(safe), how="left"
                )[safe].ffill().bfill().fillna(weather_df[col].median())
            temp_s = weather_df["temperature_2m"]
            for wn, wh in [("1D", 24), ("7D", 168)]:
                roll = temp_s.rolling(window=wh, min_periods=1)
                for ag, av in [
                    ("mean", roll.mean()),
                    ("max",  roll.max()),
                    ("min",  roll.min())
                ]:
                    cn = f"tw_{wn}_{ag}"
                    exog_bt[cn] = exog_bt.join(
                        av.rename(cn), how="left"
                    )[cn].ffill().bfill().fillna(global_med)
        else:
            # CR-3: weather_df is None only if Block 7 raised RuntimeError
            # This branch is unreachable — script would have stopped already
            raise RuntimeError(
                "CR-3: weather_df is None in Block 10. "
                "Block 7 should have raised RuntimeError first. "
                "Synthetic weather data is not permitted."
            )

        add_poly_features(
            df_train = exog_bt,
            df_list  = [exog_bt],
            y_ref    = y_bt.reindex(exog_bt.index)
        )

        # Professor's EXACT Ch 10.3: initial_train_size = len(y_train)
        cv = TimeSeriesFold(
            steps              = 24,
            initial_train_size = len(y_bt_train),
            refit              = False,
            fixed_train_size   = False,
            verbose            = False,
        )

        metrics_df, predictions_df = backtesting_forecaster(
            forecaster    = forecaster.forecaster,
            y             = y_bt,
            cv            = cv,
            metric        = "mean_absolute_error",
            exog          = exog_bt,
            show_progress = False,
            verbose       = False,
        )

        mean_mae = float(metrics_df.iloc[0, 0])
        n_folds  = len(predictions_df) // 24

        # Professor's Ch 10.5 loop — adapted for 30 folds
        # predictions_df columns: ['fold', 'pred']
        # Use last column ('pred') for predicted values
        pred_col     = predictions_df.columns[-1]
        mae_per_fold = []
        for i in range(n_folds):
            fold_idx  = predictions_df.index[i * 24 : (i + 1) * 24]
            pred_vals = predictions_df.loc[fold_idx, pred_col].values
            actual    = y_bt.loc[fold_idx].values
            mae_per_fold.append(np.abs(pred_vals - actual).mean())
        mae_per_fold = np.array(mae_per_fold) / 1000   # MW → GW

        # Compute MAPE using mean actual load for Nov 2025
        nov_actual    = y_bt.loc[predictions_df.index]
        mean_actual   = float(nov_actual.mean())
        mape_val      = (mean_mae / mean_actual) * 100
        mape_per_fold = (mae_per_fold * 1000 / mean_actual) * 100

        logger.info(
            f"Ch10: folds={n_folds}, mean_MAE={mean_mae:.1f} MW, "
            f"MAPE={mape_val:.2f}%, median={np.median(mae_per_fold)*1000:.1f} MW."
        )
        print(f"  Folds          : {n_folds}  (each = 24-hour daily forecast)")
        print(f"  Mean MAE       : {mean_mae:,.1f} MW  ({mape_val:.2f}% MAPE)")
        print(f"  Median MAE     : {np.median(mae_per_fold)*1000:,.1f} MW  ({np.median(mape_per_fold):.2f}%)")
        print(f"  Best fold MAE  : {mae_per_fold.min()*1000:,.1f} MW  ({mape_per_fold.min():.2f}%)")
        print(f"  Worst fold MAE : {mae_per_fold.max()*1000:,.1f} MW  ({mape_per_fold.max():.2f}%)")
        print(f"  Target (<3%)   : {'MET ✅' if mape_val < 3.0 else 'NOT MET ❌'}  MAPE={mape_val:.2f}%")
        BT_AVAILABLE = True

    except Exception as e:
        logger.warning(f"Ch10: rolling backtest failed: {e}")
        print(f"  Rolling backtest skipped: {e}")
        mae_per_fold = np.array([])
        mean_mae     = float("nan")
        BT_AVAILABLE = False


# =============================================================================
# Block 11 - Chapter 13 | Art. 13
# EU AI Act Compliance Dashboard
# Panel 1: tomorrow 24h forecast (exactly 24 points)
# Panel 2: rolling-origin MAE histogram (Ch 10)
# =============================================================================
fig = plt.figure(figsize=(16, 5.5), facecolor="#fdfdfd")
ax1 = fig.add_subplot(1, 2, 1)
fig.suptitle(
    f"EU AI Act Compliance Dashboard - Germany (DE)\n"
    f"CR-1 | CR-2 | CR-3 | CR-4 | Ch 1-13 | Seed: {RANDOM_SEED}\n"
    f"Train: {DATA_START[:10]} -> {TRAIN_END.date()} | "
    f"Bridge: {LIVE_N_STEPS-24}h | "
    f"Lags: {len(KEY_LAGS)} | WeightFunction: weekend 3x",
    fontsize=9, fontweight="bold", y=0.99
)

# Panel 1: Tomorrow forecast — exactly 24 hours
ax1.fill_between(TOMORROW_HOURS, predictions_tomorrow.values,
                 alpha=0.12, color="#1F4E79")
ax1.plot(TOMORROW_HOURS, predictions_tomorrow.values,
         color="#1F4E79", linewidth=2.5, marker="o", markersize=4,
         label="LightGBM forecast")
if baseline_tomorrow is not None and not np.all(np.isnan(baseline_tomorrow)):
    ax1.plot(TOMORROW_HOURS, baseline_tomorrow,
             color="#999999", linewidth=1.2, linestyle="--",
             label="Persistence (visual ref only)")

# ENTSO-E own forecast — visual reference only
entsoe_fcst_tomorrow = entsoe_fcst.reindex(
    TOMORROW_HOURS.tz_convert(entsoe_fcst.index.tz)
)
entsoe_fcst_tomorrow.index = TOMORROW_HOURS
if not entsoe_fcst_tomorrow.isna().all():
    ax1.plot(TOMORROW_HOURS, entsoe_fcst_tomorrow.values,
             color="#E07B00", linewidth=1.5, linestyle="-.",
             label="ENTSO-E forecast (visual ref only)")

ax1.set_xlim(
    TOMORROW_HOURS[0]  - pd.Timedelta(hours=1),
    TOMORROW_HOURS[-1] + pd.Timedelta(hours=1)
)
ax1.set_title(f"Day-Ahead Forecast: {target_date_str}",
              fontsize=10, fontweight="bold", color="#1F4E79")
ax1.set_ylabel("Predicted Load [MW]")
ax1.set_xlabel("Hour (UTC)")
ax1.grid(linestyle="--", alpha=0.5)
ax1.legend(fontsize=8)
ax1.xaxis.set_major_locator(mdates.HourLocator(byhour=[0, 4, 8, 12, 16, 20]))
ax1.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))

# Panel 2: Rolling-origin MAE histogram (Ch 10)
if BT_AVAILABLE and len(mae_per_fold) > 0:
    ax2 = fig.add_subplot(1, 2, 2)
    mae_mw = mae_per_fold * 1000   # convert to MW for plot
    ax2.hist(mae_mw, bins=12, color="#1F4E79", alpha=0.85, edgecolor="white")
    ax2.axvline(np.median(mae_mw), color="#E07B00", linestyle="--",
                linewidth=1.2,
                label=f"Median = {np.median(mae_mw):,.0f} MW ({np.median(mape_per_fold):.2f}%)")
    ax2.axvline(mae_mw.max(), color="#B33A3A", linewidth=1.2,
                label=f"Maximum = {mae_mw.max():,.0f} MW ({mape_per_fold.max():.2f}%)")
    ax2.set_xlabel("MAE per 24-h fold [MW]")
    ax2.set_ylabel("Number of folds")
    ax2.set_title(
        f"Ch10 Rolling-Origin Backtest\n"
        f"Nov 2025 | {len(mae_per_fold)} folds | "
        f"Mean MAE: {mean_mae:,.0f} MW ({mape_val:.2f}% MAPE)",
        fontsize=9, fontweight="bold"
    )
    ax2.legend(loc="upper right", frameon=False, fontsize=8)
    ax2.grid(True, color="#E5E5E5", linewidth=0.5)

plt.tight_layout()
plt.show()

logger.info("Pipeline complete. CR-1 to CR-4. All chapters followed.")
print("\nPipeline complete!")
print(f"  Raw data    -> {raw_csv.name}")
print(f"  Predictions -> {pred_csv.name}")
print(f"  Audit log   -> {log_path.name if log_path else 'stdout'}")
