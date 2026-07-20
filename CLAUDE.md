# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

`ddmo-sose-26` is the course repository for *Data-Driven Modeling and
Optimization*, summer semester 2026 at TH Köln. It is not a software
project --- it is teaching material plus the venv and CI that ship it.
Two things live here:

1. `lecture/` --- a Quarto book "Safety-Critical Time-Series Forecasting
   with spotforecast2-safe" (chapters `01_...qmd` ... `13_...qmd`,
   `index.qmd`, `references.qmd`). This directory has its own
   `CLAUDE.md` with build, cache, and chapter-authoring rules; read it
   before touching anything in `lecture/`. Do not duplicate those rules
   here.
2. The dependency surface that the book renders against ---
   `pyproject.toml` + `uv.lock` at the repo root, resolved into `.venv/`
   one level above `lecture/`.

The course is graded 50 % project work (the live forecasting
*challenge*, see below) and 50 % written exam. The syllabus and term
schedule are in `README.md`.

## Top-level layout and where Python lives

```
ddmo-sose-26/
├── pyproject.toml         # single source of dependency truth
├── uv.lock                # exact resolved versions (commit-tracked)
├── .venv/                 # uv-managed venv; Quarto renders against this
├── bart26hDE.bib          # shared bibliography (sibling-repo and paper)
├── lecture/               # the Quarto book — see lecture/CLAUDE.md
└── .gitlab-ci.yml         # SAST + secret-detection + GitLab Pages deploy
```

There is no `src/` --- this repo contains zero Python source. Every
import in the lecture chapters resolves to `spotforecast2_safe` or
`spotforecast2` from `.venv/`. If a symbol behaves unexpectedly, the
fix usually lives in one of those sibling repos
(`/Users/bartz/workspace/spotforecast2-safe/`,
`/Users/bartz/workspace/spotforecast2/`), not here.

## Environment

Python 3.13 with [uv](https://docs.astral.sh/uv/):

```sh
cd /Users/bartz/workspace/Lehre.d/ddmo-sose-26
uv sync                                  # create / refresh .venv from uv.lock
export ENTSOE_API_KEY="..."              # required by chapters 02 and 13
export QUARTO_PYTHON="$PWD/.venv/bin/python3"   # required for render / preview
```

`spotforecast2-safe` is pinned `>=15.1.0,<16` and `spotforecast2` is
pinned `>=3.0.0,<4`. The `15.1.0` floor requires the Open-Meteo
recent-window weather fix (forecast `past_days` + refused long-gap LOCF).
The version-compatibility surface (which symbols
moved, which backwards-compat re-exports still work) is documented in
`lecture/CLAUDE.md`. Pre-releases require explicit opt-in
(`[tool.uv] prerelease = "allow"` is set in `pyproject.toml`).

## Building the book

All commands run from `lecture/`, not the repo root:

```sh
cd lecture
make render             # HTML + PDF into lecture/_book/
make preview            # live preview
make notebooks          # qmd -> ipynb (one-way, for students)
make clean-notebooks
make clean-freeze       # purge _freeze/ + .quarto/
```

Three caches at `lecture/_freeze/`, `lecture/_cache/`, `lecture/_book/`
each have distinct semantics --- see `lecture/CLAUDE.md` for when to
clear which.

## How rendered HTML reaches students

`lecture/_book/` is intentionally *not* gitignored: the GitLab Pages job
in `.gitlab-ci.yml` is a pure copy step. It does not install Quarto or
LaTeX in CI; it expects `lecture/_book/index.html` to already exist in
the commit. The render workflow is therefore:

1. Lecturer runs `make render` locally.
2. Lecturer commits the updated `lecture/_book/`.
3. Pushing to the default branch on `git-ce.rwth-aachen.de` triggers the
   `pages` job, which copies `lecture/_book/` into `public/` and
   publishes via GitLab Pages.

If a CI build fails with "lecture/_book/index.html fehlt", the fix is
always "render locally and recommit" --- never "add a render step to
CI". Treat the committed `_book/` artefacts as build output you are
responsible for keeping current.

GitLab CI also runs `Security/SAST.gitlab-ci.yml` and
`Security/Secret-Detection.gitlab-ci.yml`. Both are template-included;
do not modify them in place.

## The Challenge and the sibling leaderboard repo

The 50 % project grade is a live forecasting competition: each team
submits a 24-hour DE load forecast per day, scored by mean absolute
error against ENTSO-E final actuals. The end-to-end workflow ---
generating the forecast, writing the CSV, opening the auto-merging PR
--- is documented in `lecture/13_live_submission.qmd`.

Two repositories cooperate, and they are deliberately kept separate:

- This repo (`ddmo-sose-26`, on GitLab CE RWTH Aachen) --- pipeline,
  lecture, venv.
- `challenge-leaderboard` (on GitHub at
  `bartzbeielstein/challenge-leaderboard`) --- team registry,
  submission validator, daily scoring cron, public leaderboard at
  <https://bartzbeielstein.github.io/challenge-leaderboard/>.

Students clone the leaderboard alongside this repo at
`~/workspace/challenge-leaderboard/`. Chapter 13's `live-submission-write`
cell writes the CSV directly into that sibling clone. The
`challenge-leaderboard/` directory is gitignored here on purpose ---
it must not be vendored into the course repo.

When investigating a submission failure, the load-bearing scripts on
the leaderboard side are:

- `scripts/validate_submission.py` (schema, deadline, authorship)
- `scripts/score_day.py` (per-day MAE)
- `scripts/build_leaderboard.py` (rolling 7-day aggregation)
- `.github/workflows/score-daily.yml` (07:00 UTC cron)

## German sibling course

A structurally parallel German lecture lives at
`/Users/bartz/workspace/Lehre.d/numerische-mathematik-sose-26/lecture/`.
Pedagogical changes that affect chapter order, learning objectives, or
the four "code rules" (CR-1 ... CR-4 in `lecture/index.qmd`) should be
audited against the German sibling. Code changes inside `_cache/` or
`_freeze/` do not propagate.

## Writing style (all prose in this repo)

These rules apply to every Markdown / `.qmd` / commit message / PR body
authored here. They are imported from the `spotforecast2` repo's
authorship conventions because the lecture, the technical report
(`bart26hDE.bib` is shared), and the package documentation are read as
a unit.

- Boldface is an exception, not a default. Reserve Markdown bold
  (`**...**`) and `\textbf{...}` for two cases: (a) a genuinely critical
  warning the reader must not skip (a safety constraint, a data-loss
  hazard, a deadline), and (b) the first on-page introduction of a key
  term in a definition list. Do not bold list-item labels, step names,
  parameter defaults, or "important" phrases --- numbered lists and
  headings already carry the structure.
- Write concise, practical prose --- the way a working scientist
  explains a decision to a colleague. Order sentences in the order a
  reader needs the ideas.
- Avoid redundancy. If a point has been made, do not restate it one
  paragraph later with different words.
- Citations: choose textual vs. parenthetical form by whether the
  author name already appears in the sentence. Write `@pins13a` to
  render "Pinson (2013)"; write `[@pins13a]` to render "(Pinson, 2013)".
  Never write "Pinson [@pins13a]" --- that renders "Pinson (Pinson
  2013)". Citing a document title (e.g. "EU AI Act [@euAI24]") is not a
  repetition; the parenthetical form is correct.
- Acronyms (SIL, ASIL, CRA, NIS2, ENTSO-E, ...) are introduced full-form
  on first occurrence with the acronym in parentheses, then used in
  acronym form thereafter. Scan the whole document on substantive
  revisions, not just the diff.

## Bibliography

`bart26hDE.bib` at the repo root is the shared bibliography for the
English lecture, the German sibling, and the companion technical
report. Citations in `lecture/*.qmd` (e.g. `[@euro24a]`) resolve
against this file. Do not duplicate it into `lecture/`.

## Repo-level conventions

- Branch from and merge into the default branch on
  `git-ce.rwth-aachen.de`. There is no `develop` here --- this repo is
  not on the semantic-release workflow that `spotforecast2` uses.
- Do not hand-edit anything under `lecture/_cache/`, `lecture/_freeze/`,
  or any `lecture/*.ipynb`. The notebooks are build artefacts of
  `quarto convert`; the caches are owned by Quarto and by the chapter
  Python cells. Re-render to regenerate.
- The `.vscode/` directory is committed intentionally (course-wide
  editor defaults). Do not add personal settings to it.
