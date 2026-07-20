# lecture/ --- "Safety-Critical Time-Series Forecasting" lecture notes

A Quarto **book** in English, with twelve chapters plus preface and
references. Companion to the scientific paper at the repo root, guiding
students with no prior knowledge of AI regulation through a complete,
AI-Act-compliant load-forecasting pipeline using live ENTSO-E and
Open-Meteo data.

> **Are you a student and only want to run the notebooks?**
> Read [`Students.md`](Students.md). This README is aimed at the
> lecturer (maintain sources, render the book, generate notebooks).

## Contents

| File                              | Topic                                          | Live data       |
|-----------------------------------|------------------------------------------------|:----------------|
| `index.qmd`                       | Preface: EU AI Act + CR-1 to CR-4              | ---             |
| `01_audit_log.qmd`                | Structured audit logging                       | ---             |
| `02_entsoe_data.qmd`              | Live load from ENTSO-E (market zone DE, 2024)  | **ENTSO-E**     |
| `03_data_annotation.qmd`          | Annotating outliers / gaps + training weights  | ---             |
| `04_missing_data.qmd`             | Fail-safe handling of NaN values               | ---             |
| `05_train_test_split.qmd`         | Chronological train/test split                 | ---             |
| `06_calendar_and_weather.qmd`     | Cyclic features + weather (Open-Meteo)         | **Open-Meteo**  |
| `07_forecaster_training.qmd`      | LightGBM training with determinism             | ---             |
| `08_forecast.qmd`                 | Recursive 24-h forecast                        | ---             |
| `09_accuracy.qmd`                 | MAE / MSE / RMSE / MAPE                        | ---             |
| `10_backtest.qmd`                 | Rolling-origin backtest                        | ---             |
| `11_provenance.qmd`               | Reproducibility audit                          | ---             |
| `12_challenge.qmd`                | Live load-forecasting challenge                | ---             |
| `references.qmd`                  | Bibliography (shared with paper)               | ---             |

Every chapter follows the structure Learning objective -> Motivation ->
Code -> Visualisation -> Exercises (with Claude). The exercise boxes
at the end of each chapter contain 2-4 prompts that students paste
directly into Claude to explore the source code of `spotforecast2-safe`
themselves.

## Prerequisites

1. **Python environment** with `spotforecast2-safe` and all other
   chapter dependencies. We recommend a local `uv`-managed venv at the
   repo root:

   ```sh
   uv sync
   ```

   The kernel referenced in `_quarto.yml` and in every `.qmd` is
   `python3` --- the standard kernel shipped by any `ipykernel`-capable
   venv. **No** additional `jupyter kernelspec install` registration
   is needed; Quarto finds the kernel automatically via the
   `QUARTO_PYTHON` variable set below.

2. **ENTSO-E API key** for chapter 02 (free registration at
   <https://transparency.entsoe.eu/>):

   ```sh
   export ENTSOE_API_KEY="your-token-here"
   ```

3. Open-Meteo (chapter 06) needs no key.

## Build

All build tasks run via `make` from this directory. The `Makefile`
reads `QUARTO_PYTHON` from the environment; you can override the path
per call:

```sh
cd lecture
export QUARTO_PYTHON="$PWD/../.venv/bin/python3"
make help                  # list available targets
make render                # HTML + PDF
make preview               # live preview
make notebooks             # qmd -> ipynb (for students)
make clean-notebooks       # delete generated *.ipynb
make clean-freeze          # purge Quarto cache (_freeze/, .quarto/)
```

The first render contacts ENTSO-E and Open-Meteo (~30-60 s). The
downloaded CSV/Parquet files are stored under `_cache/`; subsequent
renders are served from there. Quarto's `freeze: auto` additionally
caches the executed code chunks under `_freeze/`.

If the data are to change (e.g. new market zone or different year in
`02_entsoe_data.qmd`), delete `_freeze/` and `_cache/` before the
next render (`make clean-freeze`; also remove `_cache/` by hand).

## Generating notebooks for students

Students consume `*.ipynb` files, not the `*.qmd` sources. The
conversion is **one-way** before the push to GitLab:

```sh
make notebooks             # produces 13 *.ipynb next to the *.qmd
git add *.qmd *.ipynb
git commit -m "chapter X updated"
git push
```

Notes:

- `quarto convert` produces cells without outputs; students run them
  themselves (`Restart Kernel and Run All Cells`). That keeps Git
  diffs small and reproducible.
- `references.qmd` is **not** converted (purely bibliographic, no
  Python).
- The Makefile's pattern rule uses mtimes: `make notebooks` after
  editing a single chapter only reconverts that chapter.
- **Never** edit `*.ipynb` by hand --- the next `make notebooks`
  will overwrite your changes. The source of truth is always the
  `.qmd`.

## Output

After building, the finished book lives under `_book/`:

```
_book/
├── index.html                    # preface
├── 01_audit_log.html             # chapter 1
├── ...
├── 12_challenge.html             # chapter 12
├── references.html               # bibliography
└── search.json                   # full-text search
```

Open `_book/index.html` in a browser for the navigable HTML version
with sidebar and search.

`_book/`, `_freeze/` and `_cache/` are excluded via `.gitignore`.
