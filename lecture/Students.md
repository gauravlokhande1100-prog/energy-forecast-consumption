# Guide for students

Welcome to the course "Data-Driven Modeling and Optimization". This
document is aimed at **students**. It explains how to run the lecture
notebooks locally, in which order to work through the chapters, and a
few notebook-rendering quirks worth knowing.

## Sources and notebooks

The lecture is maintained in two parallel formats:

| File                         | Who maintains it? | Purpose                                |
|------------------------------|:------------------|:---------------------------------------|
| `01_...qmd` ... `13_...qmd`  | lecturer          | source of truth (Quarto Markdown)      |
| `01_...ipynb` ... `13_...ipynb` | automatic      | what you open in JupyterLab            |
| `_book/index.html`           | automatic         | nicely typeset HTML variant to read    |

For the **live ddmo-sose-26 challenge submission workflow** see
`13_live_submission.qmd` (chapter 13) — a self-contained walkthrough
from a fresh clone through writing the validated CSV into your forked
`challenge-leaderboard` repo and opening the auto-merging PR.

**You work exclusively in the `.ipynb` files.** You do not need to
open the `.qmd` sources --- the lecturer converts them to `.ipynb`
and distributes them via GitLab. When you update the repo
(`git pull`), updated notebooks arrive automatically.

## Preparing the environment

### 1. Python environment with `spotforecast2-safe`

You need a Python interpreter (Python >= 3.13) with the package
`spotforecast2-safe` installed. All dependencies are declared in the
repo root in `pyproject.toml` and pinned in `uv.lock` --- you do
**not** have to assemble a package list by hand.

Recommendation with [`uv`](https://docs.astral.sh/uv/):

```sh
# once in the course repo root (one level above lecture/):
cd /path/to/ddmo-sose-26
uv sync
```

That creates the venv under `.venv/` in the repo root and installs
exactly the versions from `uv.lock` --- byte-identical to what the
lecturer uses. When the lecturer later updates dependencies (a new
commit on `uv.lock`), another `uv sync` is enough.

Alternative with `pip` (slower, no lockfile guarantee):

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e .          # reads pyproject.toml in the repo root
```

### 2. Starting JupyterLab

The venv lives in the **repo root**, not in `lecture/`. Start
JupyterLab from the repo root and navigate to `lecture/`:

```sh
# either via the activated venv:
source .venv/bin/activate
jupyter lab lecture/

# or via uv without activation:
uv run jupyter lab lecture/
```

Pick the `python3` kernel of the venv as kernel (typical display name:
"Python 3 (ipykernel)"). **No** additional kernel registration with
`jupyter kernelspec install` is needed.

### 3. ENTSO-E API key

Chapter 02 loads real electric load data from the ENTSO-E
Transparency Platform. For that you need a free API key:

1. Register at <https://transparency.entsoe.eu/> with a professional
   email address.
2. In the profile under "My Account Settings" request a *Web API
   Security Token* (it may take a few days until it is activated).
3. Before starting the notebook, set it in the shell:

   ```sh
   export ENTSOE_API_KEY="your-token-here"
   ```

   Tip: add it to your `~/.zshrc` or `~/.bashrc` to keep it
   permanently.

Open-Meteo (chapter 06) needs **no** key.

## Chapter order: 01 -> 12

**Important:** chapters depend on each other. Every chapter writes
intermediate files (Parquet files, the trained forecaster) into the
directory `_cache/shared/`, which later chapters read again.

If you start with chapter 06, for example, you will get:

```
FileNotFoundError: [Errno 2] No such file or directory:
'_cache/shared/load_de_2024_clean.parquet'
```

...because chapter 04 has not yet produced the cleaned load series.

**Recommended workflow on the first run**: open in sequence

1. `index.ipynb` --- preface, overview of the AI Act and code rules
2. `01_audit_log.ipynb`
3. `02_entsoe_data.ipynb` (loads ~1 MB from ENTSO-E, once)
4. `03_data_annotation.ipynb` --- preferred strategy for gaps/outliers
5. `04_missing_data.ipynb` --- linear interpolation as an alternative
6. `05_train_test_split.ipynb`
7. `06_calendar_and_weather.ipynb` (loads weather from Open-Meteo, once)
8. `07_forecaster_training.ipynb` (may take 1-2 min depending on hardware)
9. `08_forecast.ipynb`
10. `09_accuracy.ipynb`
11. `10_backtest.ipynb`
12. `11_provenance.ipynb`
13. `12_challenge.ipynb` --- rules and setup of the live challenge

In every notebook: **Kernel -> Restart Kernel and Run All Cells**.
When a chapter runs through without errors, move on to the next.

Chapter 12 contains **deliberately non-executed** code blocks
(`#| eval: false`) because they would pull live ENTSO-E data. Read
the chapter carefully and run the submission script separately from
JupyterLab once your team is registered.

On the second and subsequent runs all data come from the cache; you
can then run individual chapters at any time.

## What happens in `_cache/`?

Running the notebooks creates two local data stores:

```
_cache/
├── spotforecast2_data/
│   ├── raw/              # raw ENTSO-E API responses
│   └── interim/          # filtered load series
├── shared/               # intermediate artefacts between chapters
│   ├── load_de_2024.parquet
│   ├── load_de_2024_clean.parquet
│   ├── y_train.parquet
│   ├── y_eval.parquet
│   ├── exog.parquet
│   ├── y_pred_24h.parquet
│   └── split_meta.json
├── forecaster.pkl        # serialised LightGBM model from chapter 07
├── weather_de_2024.parquet
├── provenance.json
└── logs/
```

These files are not in the repo (which is why you have to run the
chapters once in the correct order). You may delete `_cache/`
freely --- the next run will recreate it.

## Known notebook rendering quirks

The notebooks are converted automatically from the `.qmd` sources.
A few Quarto syntax peculiarities remain visible as raw text:

- **Learning-objective and exercise boxes.** In the HTML book
  (`_book/`) these appear as coloured highlight boxes. In the notebook
  you see lines like:

  ```
  ::: {.callout-note title="Learning objective"}
  You can ...
  :::
  ```

  The content is identical, just unformatted. The `:::` lines are
  the Quarto markup for the box and can be ignored.

- **Cross-references and citations.** Things like `@sec-missing` or
  `[@euro24a]` remain as raw text. In the HTML book they are
  clickable links to sections or bibliography entries.

- **Mermaid diagrams** (chapters 01 and 11). JupyterLab 4.1+ with the
  Mermaid extension enabled renders them. Otherwise you see the
  source of the diagram as a code block. In the HTML book the
  diagrams are always rendered correctly.

- **LaTeX formulas** (chapter 09). Rendered natively by JupyterLab
  --- no action needed.

**If you want the nicely typeset variant**, ask the lecturer for the
link to the rendered HTML book, or build it yourself with
`make render` (requires Quarto and the Python venv).

## The challenge

The second half of the module grade (50%) is a **live challenge**:
starting on 11 May 2026 you submit a 24-hour load forecast for
Germany every day, which is automatically scored against the
ENTSO-E ground truth. Rules, submission format and the public
leaderboard are described in `12_challenge.ipynb`.

Important:

- **Team registration (2-4 people)** until 11 May 2026 by email to
  the lecturer (team name, team ID, GitHub handles).
- Submissions go via the public repo `challenge-leaderboard` (link
  follows with the registration confirmation).
- The leaderboard on GitHub Pages is updated daily; the weekly
  snapshot is archived every Sunday at 23:55 UTC.

## Exercises with Claude

Every chapter ends with an "Exercises (with Claude)" box. The
exercises are phrased so that you can paste them directly as a
prompt into the AI assistant **Claude** (e.g. <https://claude.ai>
in the browser or *Claude Code* in the terminal). A typical
exercise is:

> *Ask Claude:* "Show me the source of
> `spotforecast2_safe.preprocessing.LinearlyInterpolateTS`. Explain
> line by line how the parameter `on_missing` changes the
> behaviour."

Really put these exercises to Claude --- the learning effect comes
from the dialogue: question Claude's explanation, ask for concrete
examples, or probe for the connection to the EU AI Act or to one of
the four code rules (CR-1 to CR-4).

## Help with common errors

| Error message                                                          | Cause                                                                | Fix                                                                            |
|------------------------------------------------------------------------|----------------------------------------------------------------------|--------------------------------------------------------------------------------|
| `ModuleNotFoundError: No module named 'spotforecast2_safe'`            | wrong kernel selected, or package not installed in the venv          | pick the `python3` kernel from your venv; if needed re-run `pip install`       |
| `RuntimeError: Set ENTSOE_API_KEY in the shell ...`                    | API key not set                                                      | `export ENTSOE_API_KEY=...` **before** starting JupyterLab                     |
| `FileNotFoundError: _cache/shared/...parquet`                          | previous chapter not yet executed                                    | run chapters 01 -> 12 in order                                                 |
| `requests.exceptions.HTTPError: 401 Unauthorized` (ENTSO-E)            | token not yet activated or copied incorrectly                        | inquire at ENTSO-E; the token may take 1-3 days to activate after registration |
| `pyarrow.lib.ArrowInvalid: ...`                                        | corrupted parquet file in the cache                                  | delete `_cache/` and re-run chapters 02 -> 07                                  |
| Kernel "dies" during training (chapter 07)                             | too little RAM (<4 GB free)                                          | close other programs; if needed reduce `n_estimators` in the notebook          |

For questions not in this table: ask Claude first, then in the
tutorials or by email to the lecturer.
