# freshcheck

**Your benchmark's baselines are stale. Find out in an afternoon.**

![License: MIT](https://img.shields.io/badge/license-MIT-green)
![tests: 29 passing](https://img.shields.io/badge/tests-29%20passing-success)
![stdlib only](https://img.shields.io/badge/dependencies-stdlib%20only-informational)

freshcheck is a small command-line tool for maintainers of "best known" tables. It does not
search the literature for you. It makes a literature audit **structured, blind-checkable and
repeatable**: frozen targets, dated append-only verdict rows, a seeded blind second-searcher
sample, inter-searcher agreement, and a time-series report.

## Why

We audited five public "best known" tables used to evaluate AI-driven mathematics
(audit data: https://doi.org/10.5281/zenodo.23324073):

- **69 of 268 targets (25.7%)** were superseded or not scoreable as written.
- **48 of 231 AI-discovery improvement claims (20.8%)** had an equal-or-better value published
  before the claim; **17 (7.4%)** from a third party the claimant did not cite.
- Correcting **five** stale values on one public arena leaderboard reorders its top 10
  (**7 reversals**); **57%** of recorded "beats" sat on stale rows.
- **603 of 603** public records re-scored with their benchmarks' own validators were valid.
  The records are fine; the reference values are what rot.
- Classical OR libraries (TSPLIB, QAPLIB, CVRPLIB, MIPLIB, OR-Library): **0 stale rows of 158**.
  The decay is specific to young AI-era tables.

If your table is young and fast-moving, assume it has the same problem and measure it.
The corrected values live in the [Extremal Values Registry](https://doi.org/10.5281/zenodo.23326558).

## 2-minute quickstart

Python 3.10+, no dependencies. The files below ship in `examples/`.

```
mkdir demo && cd demo
cp ../examples/targets.json ../examples/pass1.csv ../examples/second.csv .
export PYTHONPATH=..            # or: pip install ..
```

`targets.json` freezes the table you are auditing (6 toy rows here):

```json
{"benchmark": "toy-benchmark", "pinned_commit_or_version": "v1.0", "pinned_date": "2026-01-15",
 "rows": [
  {"id": "p1", "problem": "Smallest known ratio for toy inequality A", "direction": "min",
   "target_value": 1.50, "prev_best": 1.60, "notes": ""},
  {"id": "p2", "problem": "Largest known size for toy packing B", "direction": "max",
   "target_value": 40, "prev_best": 38, "notes": ""}
 ]}
```

**1. init** - validate and freeze (a changed targets file is rejected afterwards):

```
$ python -m freshcheck init targets.json
frozen 6 rows -> .../targets.frozen.json
sha256 4fe2f17dc88c20412d94b828a4f649ad466859afac3f15bc958949c5e2414432
```

**2. rows import** - record the first searcher's verdicts (`pass1.csv`, one row per target):

```
$ python -m freshcheck rows import pass1.csv
wrote 6 row(s) -> ./rows_2026-10-11.csv
```

**3. sample** - draw the blind second-searcher sample (seeded, reproducible):

```
$ python -m freshcheck sample --seed 7 --frac 0.5
{ "seed": 7, "frac": 0.5, "cap": 30, "n_targets": 6, "ids": ["p2", "p3", "p4"] }
```

A second person searches only those targets, without seeing the first verdicts, and records
`second.csv`.

**4. agree** - agreement between the two passes:

```
$ python -m freshcheck agree rows_2026-10-11.csv second.csv
n compared      3
raw agreement   0.667
cohen kappa     0.500
reversals (first STALE, second CURRENT): ['p4']
recall gaps (first CURRENT, second STALE): []
unmatched: first=['p1', 'p5', 'p6'] second=[]
```

Investigate every reversal row by row before publishing.

**5. report** - counts, Wilson interval, time series:

```
$ python -m freshcheck report
== 2026-10-11  n=6
   STALE=2  MALFORMED=1  UNCLEAR=1  CURRENT=2  STALE-LEADERBOARD=0
   STALE+MALFORMED 3/6 = 0.500  Wilson95 [0.188, 0.812]
   UNCLEAR (reported, not counted): 1
   already stale at pin: 1
   median lag (days, source_date -> search_date): 274.0
```

Other commands: `row add` (one row), `validate --scorer module:function --construction FILE
--claimed VALUE` (re-score a public construction with your own scorer; example scorer
`freshcheck.examples:sum_free_size`). Global options `--dir` and `--targets` go before the
command. Re-runs on later dates are new files, never edits.

## Targets and rows

`init` refuses a row whose `prev_best` is numerically better than `target_value` in the
stated direction (a typical extraction defect) unless `--allow-flagged` is given.

Rows are an append-only CSV, one file per search date (`rows_<search_date>.csv`), with the
columns `benchmark, problem_id, pinned_value, pinned_commit, direction, search_date,
searcher, verdict, better_value, source, source_date, source_kind, queries_run, notes`
(`source_kind` is `primary|validator|leaderboard|secondary`). Pinned fields are filled from
the frozen targets when blank. An existing date file is never overwritten. The verbatim quote
goes in `notes`.

## Verdicts

- **STALE**: a strictly better value exists, with either (a) a verbatim quote from a PRIMARY
  source that was opened (paper PDF, canonical table, the authors' own paper), with URL and
  date; or (b) a public construction re-scored offline with the benchmark's own validator,
  with the command and output saved.
- **STALE-LEADERBOARD** / **UNCLEAR**: a snippet, abstract-only hit, blog, tweet or
  leaderboard cell alone is never STALE. A STALE row lacking a primary/validator source, a
  quote, or a strictly better value is downgraded to UNCLEAR with a warning.
- **MALFORMED**: the pinned value is not a scoreable best-known value (a proven bound stored
  as a target, a range string, a count).
- **UNCLEAR**: primary source unreachable, unrefereed claim to a major open problem, or
  conflicting sources. Reported, not counted.
- **CURRENT**: two independent passes found no superseding primary source. Record the last
  query. "Better" means strictly better in the benchmark's direction; equal is CURRENT.

Headline rate = (STALE + MALFORMED) / targets, with a Wilson 95% interval.

## Replicate an audit

Give a second auditor only `replicate/procedure.md`, `replicate/hints.txt` and the target
rows, never the original verdicts. The cut-off date is the search date. Then compare with
`python -m freshcheck agree original_rows.csv replicate_rows.csv`.

## How to cite

Cite the method through the audit dataset, and the registry for corrected values:

> Thalluri, A. (2026). Audit of stale "best known" targets in AI-mathematics benchmarks (data). Zenodo.
> https://doi.org/10.5281/zenodo.23324073
> Thalluri, A. (2026). Extremal Values Registry (v0.1.0). Zenodo.
> https://doi.org/10.5281/zenodo.23326559

```bibtex
@dataset{thalluri2026audit,
  author    = {Thalluri, Advatiya},
  title     = {Audit of stale "best known" targets in AI-mathematics benchmarks (data)},
  year      = {2026},
  publisher = {Zenodo},
  doi       = {10.5281/zenodo.23324073}
}

@dataset{thalluri2026extremal,
  author    = {Thalluri, Advatiya},
  title     = {Extremal Values Registry},
  year      = {2026},
  version   = {0.1.0},
  publisher = {Zenodo},
  doi       = {10.5281/zenodo.23326559}
}
```

`CITATION.cff` is included (GitHub's "Cite this repository" uses it).

## Used on

Five audited tables: two AI-system result sets, a mathematical-benchmark suite, an
optimization-constants table, and a public arena leaderboard.

## License

MIT.
