# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A **Quarto book** in English --- `lecture/` is the lecture script
"Safety-Critical Time-Series Forecasting with spotforecast2-safe" for the
SoSe-26 *Data-Driven Modeling and Optimization* (ddmo) course. Each of the
twelve numbered chapters (`01_...qmd`-`12_...qmd`) plus `index.qmd` and
`references.qmd` is a Quarto document that executes Python code via Jupyter
and renders to HTML+PDF.

The book teaches the EU AI Act by walking through a complete load-forecasting
pipeline that uses live data from **ENTSO-E** (electricity load) and
**Open-Meteo** (weather), built on top of the external package
[`spotforecast2-safe`](https://github.com/sequential-parameter-optimization/spotforecast2-safe).
This repo contains *no* Python source --- it imports `spotforecast2_safe`
from the venv.

This English book is a sibling of the German lecture in
`numerische-mathematik-sose-26/lecture/`; both are kept structurally aligned.
If you change pedagogical content here, consider whether the German sibling
needs the same change.

## Build / preview / convert --- all via `make`

The book renders against the venv at `../.venv` (one level up from
`lecture/`, at the course-repo root). Dependencies are managed in
`../pyproject.toml` and locked in `../uv.lock`. To rebuild the venv from
scratch (e.g. on a fresh clone or after a dependency bump):

```sh
cd /Users/bartz/workspace/Lehre.d/ddmo-sose-26
uv sync          # creates .venv from pyproject.toml + uv.lock
```

`spotforecast2-safe` is pinned at `>=15.1.0,<16` and `spotforecast2` at
`>=3.0.0,<4` (the `15.1.0` floor carries the Open-Meteo recent-window
weather fix used by chapter 14). Chapters 01--12 use only the `spotforecast2-safe` surface
(`ForecasterRecursiveLGBM` still works via the top-level
backwards-compat re-export; `LinearlyInterpolateTS(on_missing=...)`
still accepts the same parameter as in 3.x). Chapter 13 additionally
uses the full `spotforecast2` package for `ConfigEntsoe`, `MultiTask`,
the `entsoe_*` task hooks, and SpotOptim tuning. One module path moved
between 3.x and 13.x: `spotforecast2_safe.manager.metrics` is now
`spotforecast2_safe.manager.demo_metrics` (chapter 09 already updated).
The 14.0.0 major bump is behavioural, not structural: the `manager`
functions (`package_prediction`, `get_model_prediction`, `load_iteration`,
`get_last_model`, `load_forecasters`, `setup_logging`) now raise typed
exceptions instead of returning silently on failure. The book only uses
`setup_logging` (chapter 01), and only on the success path with a `Path`
`log_dir` --- `setup_logging` now calls `log_dir.mkdir(...)`, so a `str`
is no longer accepted. `spotforecast2 2.2.4` is the first release that
imports `initialize_lags` from `preprocessing.forecaster_config` (it moved
out of `forecaster.utils`); earlier `spotforecast2` fails to import against
`spotforecast2-safe >= 13.4`.
The `spotforecast2-safe 15.0.0` / `spotforecast2 3.0.0` major bump replaced
the boolean `include_poly_features` config flag with an integer
`poly_features_degree` (1 = off, 2 = pairwise bilinear interactions) plus a
`max_poly_features` cap (top-K interaction columns by mutual information,
default 10); chapter 14 uses `poly_features_degree=2, max_poly_features=10`.
The polynomial degree is now actually threaded into
`create_interaction_features` --- previously the flag was inert (degree
defaulted to 1, so no interaction columns were ever produced).
Quarto's render launcher additionally needs `pyyaml`, `nbclient`,
`nbformat`, `jupyter-client` (already pinned in pyproject.toml --- none
are transitive via `ipykernel`).

Chapter 13 follows the canonical date-range / naming convention from
the bart26b publication: `y_{-1}` = yesterday's 24 hourly DE Actual
Load values; `ŷ_{-1}` = model prediction for the same window (the
scorable exemplar used by chapters 08--10); `y_0` = today's 24 h, the
*real* live target. All date constants in chapter 13 derive from
`pd.Timestamp.now(tz="UTC").normalize()` --- never hard-code calendar
dates. After `download_new_data`, the chapter asserts the merged
interim CSV extends through `D-1 23:00 UTC` and aborts loudly otherwise.
Chapters 02--11 keep the frozen 2024 window (`DATA_START="2024-01-01 00:00"`,
`DATA_END="2024-12-31 23:00"`) for pedagogical determinism.

The `Makefile` in `lecture/` is the single entry point and reads
`QUARTO_PYTHON` from the environment:

```sh
cd lecture
export QUARTO_PYTHON="$PWD/../.venv/bin/python3"   # required for render/preview

make help               # list targets
make render             # HTML + PDF
make preview            # live preview
make notebooks          # qmd -> ipynb (one-way, for students; no Python needed)
make clean-notebooks    # delete generated *.ipynb
make clean-freeze       # purge _freeze/ + .quarto/

# Or override per-call:
make render QUARTO_PYTHON=/path/to/python3
```

The Jupyter kernel name in every `.qmd` front matter is the **standard
`python3` kernel** --- automatically present in any venv that has
`ipykernel` installed. There is no per-user `jupyter kernelspec install`
step; Quarto discovers the kernel directly from `QUARTO_PYTHON`. Do not
reintroduce a custom kernel name in the front matter: it forces every
collaborator to register a user-level kernel by hand, which cannot be
committed to Git.

`ENTSOE_API_KEY` must be exported in the shell before rendering chapters
that hit ENTSO-E (02, and indirectly any later chapter whose `_cache/`
artefacts are missing). Open-Meteo (chapter 06) needs no key.

## Notebook generation: one-way, lecturer-driven

Students consume `lecture/*.ipynb` via Git pull. The lecturer writes
only `*.qmd` and runs `make notebooks` before pushing; `quarto convert`
emits `.ipynb` files **alongside** each `.qmd` (not in a subdir --- the
chapters use relative paths into `_cache/shared/`, so notebooks must
live in `lecture/` for paths to resolve).

Rules for any future Claude session touching this repo:

- **Never hand-edit `lecture/*.ipynb`.** They are build artefacts. The
  next `make notebooks` overwrites edits silently. The source of truth
  is always the `.qmd`.
- The conversion is **one-way**. There is no `ipynb -> qmd` step. If a
  student supplies an edited notebook, the change must be reapplied to
  the `.qmd` source by hand.
- `references.qmd` is excluded from conversion (no Python; would
  produce an empty notebook). The `Makefile` filters it out via
  `filter-out references.qmd`.
- Notebooks are committed without outputs (`quarto convert` default).
  Do not introduce a "pre-execute before commit" step --- it would
  trash diff cleanliness.
- The student-facing English guide is `lecture/Students.md`. Keep
  it in sync when changing chapter order or required env vars.

## Three intertwined caches --- know which to clear

| Path        | Owner      | Holds                                                                  | When to clear                                       |
|-------------|------------|------------------------------------------------------------------------|-----------------------------------------------------|
| `_freeze/`  | Quarto     | per-chapter executed-cell output                                       | when chapter logic changed but `freeze: auto` did not notice |
| `_cache/`   | the lessons | live API pulls + cross-chapter handoff parquets (`_cache/shared/`)    | when changing `DATA_START`/`DATA_END`/`COUNTRY`, or to re-fetch ENTSO-E/Open-Meteo |
| `_book/`    | Quarto     | rendered HTML+PDF                                                      | only if a stale build is interfering                |

All three are in `.gitignore` and must never be committed.

## Chapters share state through `_cache/shared/`

Chapters are **sequentially dependent**, not independent. Earlier chapters
write parquet files (`y_train.parquet`, `y_eval.parquet`, `exog.parquet`,
`load_de_2024_clean.parquet`, `split_meta.json`, `forecaster.pkl`,
`y_pred_24h.parquet`, ...) into `_cache/shared/`; later chapters read them.
Rendering chapter N in isolation only works if chapters before it have
already produced their artefacts. After invalidating `_freeze/` you must
re-render in order, not selectively.

The chapter `_quarto.yml` order is the canonical render order --- do not
reorder there without auditing the read/write contract between chapters.

## Determinism is a load-bearing invariant (CR-2)

The book's pedagogical spine is four "code rules" CR-1 to CR-4 (see
`index.qmd` Section "The four code rules"). CR-2 (determinism) is what
allows live-API chapters to remain reproducible: the time window is pinned
via constants

```
DATA_START = "2024-01-01 00:00+00:00"
DATA_END   = "2024-12-31 23:00+00:00"
COUNTRY    = "DE"
```

so every student gets byte-identical data. When editing chapter 02 or 06,
do not introduce floating "now"-relative dates, random seeds, or
unordered-dict iteration --- they break the pedagogical promise the rest of
the book relies on.

## Editing conventions specific to this book

- Every chapter follows **Learning objective -> Motivation -> AI Act
  link -> Code -> Visualisation -> Exercises (with Claude)**. The trailing
  "Exercises" box is not optional decoration: it contains 2-4 prompts that
  students paste into Claude to explore `spotforecast2-safe`'s source.
  Preserve this structure when editing.
- Cross-references use Quarto's `{#sec-...}` IDs (e.g. `@sec-missing`,
  `@sec-split`). Keep IDs stable when restructuring.
- The bibliography lives **outside this directory** at
  `../bart26hDE.bib` (shared with the German sibling and the companion
  paper). Citations like `[@euro24a]` must resolve against that file.
- Text is English throughout (`lang: en`). New prose must match.
- The book builds a `pdf` target with `documentclass: scrbook` and
  `mainfont: "TeX Gyre Termes"` --- that font and a working LaTeX install
  must be present for the PDF target.

## Repo-level context (one level up)

The parent directory `/Users/bartz/workspace/Lehre.d/ddmo-sose-26/`
is the *course* repo (not just this book). Its `README.md` carries the
syllabus, term schedule, and grading scheme (50% challenge / 50% written
exam) and the `.gitlab-ci.yml` adds GitLab SAST + secret-detection
pipelines. The `lecture/` directory is the only build target in the repo.
