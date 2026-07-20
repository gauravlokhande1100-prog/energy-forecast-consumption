"""
DDMO SoSe 26 - Team Gladiators - Cross-Validation vs ENTSO-E Actuals
Loads all predictions_*.csv from data/, fetches real ENTSO-E load, and reports
MAE + MAPE per day plus an overview plot.
"""
import argparse
import os
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from dotenv import load_dotenv

from spotforecast2_safe.manager.logger import setup_logging
from spotforecast2_safe.downloader.entsoe import download_new_data
from spotforecast2_safe.data.fetch_data import fetch_data, get_data_home


# =============================================================================
# CLI argument: --date YYYY-MM-DD  (optional; defaults to most recent scored day)
# =============================================================================
parser = argparse.ArgumentParser(
    description="Cross-validate LightGBM forecasts against ENTSO-E actuals."
)
parser.add_argument(
    "--date", "-d",
    type=str,
    default=None,
    metavar="YYYY-MM-DD",
    help="Specific day to highlight in the detail panel (default: most recent scored day).",
)
args = parser.parse_args()
HIGHLIGHT_DATE = args.date  # None means auto-select most recent

# Anchor all paths to the script's directory so it works from any cwd
REPO_ROOT = Path(__file__).resolve().parent


# =============================================================================
# Setup: logging + API key
# =============================================================================
log_dir = REPO_ROOT / "_cache" / "logs" / "cross_validation"
log_dir.mkdir(parents=True, exist_ok=True)
logger, log_path = setup_logging(level=logging.INFO, log_dir=log_dir)
logger.info("Cross-validation pipeline start.")

load_dotenv()
API_KEY = os.getenv("ENTSOE_API_KEY")
if not API_KEY:
    logger.error("ENTSOE_API_KEY missing.")
    raise ValueError("Missing ENTSOE_API_KEY in .env file!")


# =============================================================================
# Config
# =============================================================================
DATA_DIR   = REPO_ROOT / "data"                       # source: predictions_*.csv
OUT_DIR    = REPO_ROOT / "data" / "cross_validation"  # all CV outputs go here
OUT_DIR.mkdir(parents=True, exist_ok=True)
COUNTRY    = "DE"
DATA_START = "2026-05-01 00:00"
DATA_END   = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

DATA_HOME = REPO_ROOT / "_cache" / "spotforecast2_data"
DATA_HOME.mkdir(parents=True, exist_ok=True)
os.environ["SPOTFORECAST2_DATA"] = str(DATA_HOME)


# =============================================================================
# Step 1: Refresh ENTSO-E actuals (incremental, uses cache)
# =============================================================================
print("Refreshing ENTSO-E actuals from API (incremental)...")
download_new_data(
    api_key      = API_KEY,
    country_code = COUNTRY,
    start        = DATA_START,
    end          = DATA_END,
    force        = False,
)

interim = get_data_home() / "interim" / "energy_load.csv"
df_raw  = fetch_data(filename=str(interim))
df_raw.index = pd.to_datetime(df_raw.index, utc=True)

actual_col   = next(c for c in df_raw.columns if "Actual"     in c and "Load" in c)
forecast_col = next(c for c in df_raw.columns if "Forecasted" in c and "Load" in c)

# Use Actual Load; fall back to Forecasted Load where actual not yet published
actuals = df_raw[actual_col].fillna(df_raw[forecast_col]).astype(float)
actuals = actuals.resample("h").mean()
actuals.name = "actual_mw"

logger.info(f"Actuals loaded: {len(actuals):,} rows, "
            f"{actuals.index.min()} -> {actuals.index.max()}.")
print(f"  Actuals: {len(actuals):,} hourly rows, "
      f"{actuals.index.min().date()} -> {actuals.index.max().date()}")


# =============================================================================
# Step 2: Load all predictions_*.csv and compute MAE / MAPE per day
# =============================================================================
pred_files = sorted((DATA_DIR / "validate").glob("cross_predictions_????-??-??.csv"))
print(f"\nFound {len(pred_files)} cross-prediction files in data/validate/.")

today_utc = pd.Timestamp(datetime.now(timezone.utc)).normalize()
results   = []
skipped   = []

for pf in pred_files:
    date_str  = pf.stem.replace("cross_predictions_", "")
    pred_date = pd.Timestamp(date_str, tz="UTC")

    # Actuals for a day are only complete the day after
    if pred_date >= today_utc:
        skipped.append(date_str)
        continue

    df_pred = pd.read_csv(pf)
    df_pred["timestamp_utc"] = pd.to_datetime(df_pred["timestamp_utc"], utc=True)
    df_pred = df_pred.set_index("timestamp_utc")

    actual_slice = actuals.reindex(df_pred.index)
    if actual_slice.isna().all():
        print(f"  {date_str}: no actuals in cache yet, skipping.")
        skipped.append(date_str)
        continue

    mask    = ~actual_slice.isna()
    n_valid = int(mask.sum())
    errors  = df_pred.loc[mask, "forecast_mw"].values - actual_slice[mask].values

    mae  = float(np.abs(errors).mean())
    rmse = float(np.sqrt((errors ** 2).mean()))
    mape = float((np.abs(errors) / actual_slice[mask].values).mean() * 100)

    results.append({
        "date"         : date_str,
        "mae_mw"       : mae,
        "rmse_mw"      : rmse,
        "mape_pct"     : mape,
        "n_hours"      : n_valid,
        "forecast_mean": float(df_pred["forecast_mw"].mean()),
        "actual_mean"  : float(actual_slice[mask].mean()),
    })
    print(f"  {date_str}: MAE={mae:7,.0f} MW | MAPE={mape:5.2f}% | n={n_valid}h")

if not results:
    print("\nNo completed days found — nothing to cross-validate.")
    raise SystemExit(0)

df_cv = pd.DataFrame(results)
df_cv["date"] = pd.to_datetime(df_cv["date"])
df_cv = df_cv.set_index("date").sort_index()

overall_mae  = df_cv["mae_mw"].mean()
overall_rmse = df_cv["rmse_mw"].mean()
overall_mape = df_cv["mape_pct"].mean()
best_day     = df_cv["mae_mw"].idxmin()
worst_day    = df_cv["mae_mw"].idxmax()

print(f"\n{'='*55}")
print(f"  Days scored  : {len(df_cv)}")
print(f"  Overall MAE  : {overall_mae:,.1f} MW")
print(f"  Overall RMSE : {overall_rmse:,.1f} MW")
print(f"  Overall MAPE : {overall_mape:.2f}%")
print(f"  Target <3%   : {'MET ✅' if overall_mape < 3.0 else 'NOT MET ❌'}")
print(f"  Best  day    : {best_day.date()}  ({df_cv.loc[best_day,'mae_mw']:,.0f} MW)")
print(f"  Worst day    : {worst_day.date()}  ({df_cv.loc[worst_day,'mae_mw']:,.0f} MW)")
if skipped:
    print(f"  Skipped      : {len(skipped)} future/no-data days")
print(f"{'='*55}")

logger.info(
    f"Cross-val: {len(df_cv)} days, MAE={overall_mae:.0f} MW, "
    f"MAPE={overall_mape:.2f}%."
)


# =============================================================================
# Step 3: Save summary CSV
# =============================================================================
summary_csv = OUT_DIR / "cross_validation_summary.csv"
df_cv.to_csv(summary_csv)
print(f"\nSaved: {summary_csv}")


# =============================================================================
# Step 4: Resolve the day to highlight in the detail panel
# =============================================================================
if HIGHLIGHT_DATE is not None:
    requested = pd.Timestamp(HIGHLIGHT_DATE)  # index is tz-naive date strings
    if requested not in df_cv.index:
        available = ", ".join(d.strftime("%Y-%m-%d") for d in df_cv.index)
        raise ValueError(
            f"--date {HIGHLIGHT_DATE} not in scored days.\nAvailable: {available}"
        )
    most_recent = requested
else:
    most_recent = df_cv.index.max()

# =============================================================================
# Step 5: Plot — Forecast vs Actual for selected day
# =============================================================================
_date_str  = most_recent.strftime("%Y-%m-%d")
pf_day     = DATA_DIR / "validate" / f"cross_predictions_{_date_str}.csv"

df_day     = pd.read_csv(pf_day)
df_day["timestamp_utc"] = pd.to_datetime(df_day["timestamp_utc"], utc=True)
df_day     = df_day.set_index("timestamp_utc")
act_day    = actuals.reindex(df_day.index)

day_mae  = df_cv.loc[most_recent, "mae_mw"]
day_mape = df_cv.loc[most_recent, "mape_pct"]

fig, ax = plt.subplots(figsize=(14, 6), facecolor="#fdfdfd")
fig.suptitle(
    f"Cross-Validation — LightGBM vs ENTSO-E Actuals (DE)\n"
    f"Overall MAE: {overall_mae:,.0f} MW  |  MAPE: {overall_mape:.2f}%  "
    f"|  Days: {len(df_cv)}",
    fontsize=11, fontweight="bold",
)

ax.plot(df_day.index, df_day["forecast_mw"],
        color="#1F4E79", linewidth=2, marker="o", markersize=4,
        label="LightGBM forecast")
ax.plot(act_day.index, act_day.values,
        color="#2E7D32", linewidth=2, marker="s", markersize=4,
        label="ENTSO-E actual")
ax.fill_between(df_day.index, df_day["forecast_mw"], act_day.values,
                alpha=0.15, color="#B33A3A", label="Error")
ax.set_title(
    f"{_date_str}  —  MAE: {day_mae:,.0f} MW  |  MAPE: {day_mape:.2f}%",
    fontsize=10, fontweight="bold",
)
ax.set_xlabel("Hour (UTC)")
ax.set_ylabel("Load [MW]")
ax.legend(fontsize=9)
ax.grid(linestyle="--", alpha=0.5)
ax.xaxis.set_major_locator(mdates.HourLocator(byhour=[0, 4, 8, 12, 16, 20]))
ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))

plt.tight_layout()

plot_path = OUT_DIR / f"cross_validation_{_date_str}.png"
plt.savefig(plot_path, dpi=150, bbox_inches="tight")
print(f"Saved: {plot_path}")
plt.show()

logger.info("Cross-validation complete.")
print("\nDone.")
