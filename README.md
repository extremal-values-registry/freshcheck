# freshcheck

A small, dependency-free command-line tool for benchmark maintainers who want to keep a
"best known" table fresh. It structures and validates a literature audit: it freezes the
targets, stores dated append-only verdict rows, draws a blind second-searcher sample,
measures inter-searcher agreement, reports a time series, and re-scores public
constructions with your own scorer. The literature search itself is done by a human or an
external agent and recorded as rows.

## Quickstart

```
python -m freshcheck init targets.json                      # validate + freeze, prints sha256
python -m freshcheck rows import pass1.csv                  # writes rows_<search_date>.csv
python -m freshcheck sample --seed 7 --frac 0.3             # blind second-pass sample
python -m freshcheck agree rows_2026-10-11.csv second.csv   # raw agreement, kappa, reversals
python -m freshcheck report                                 # counts, Wilson CI, time series
```

Other commands: `row add` (one row), `validate --scorer module:function` (re-score a
construction). Global options `--dir` and `--targets` go before the command.

## Targets file

```
{"benchmark": "...", "pinned_commit_or_version": "...", "pinned_date": "YYYY-MM-DD",
 "rows": [{"id": "p1", "problem": "...", "direction": "min|max",
           "target_value": 1.0, "prev_best": 1.1, "notes": "..."}]}
```

`init` refuses a row whose `prev_best` is numerically better than `target_value` in the
stated direction (a typical extraction defect) unless `--allow-flagged` is given. Once
frozen, a changed targets file is rejected.

## Row format

Append-only CSV, one file per search date (`rows_<search_date>.csv`), exactly these
columns:

`benchmark, problem_id, pinned_value, pinned_commit, direction, search_date, searcher,
verdict, better_value, source, source_date, source_kind(primary|validator|leaderboard|secondary),
queries_run, notes`

Pinned fields are filled from the frozen targets when blank. An existing date file is never
overwritten (`rows import` refuses; `row add` refuses to re-record a problem). The
verbatim quote goes in `notes`. A STALE row without `source_kind` of primary or validator,
without a non-empty quote, or whose `better_value` is not strictly better than the pinned
value is downgraded to UNCLEAR with a warning.

## Verdicts and evidence standard

- **STALE** requires one of: (a) a verbatim quote of the better value from a PRIMARY source that was opened
  (paper PDF, canonical table, authors' own paper), with URL and date; or (b) a public construction re-scored
  offline with the benchmark's own validator, with the command and output saved.
- A snippet, abstract-only hit, blog, tweet, or leaderboard cell alone is **STALE-LEADERBOARD** or **UNCLEAR**,
  never STALE.
- **MALFORMED**: the pinned value is not a scoreable best-known (proven bound stored as target, range string,
  count). Quote the pinned text.
- **UNCLEAR**: primary source unreachable, unrefereed claim to a major open problem, or conflicting sources.
- **CURRENT**: both passes found no superseding primary source. Record the last query run.
- Direction check: "better" means strictly better in the benchmark's direction. Equal is CURRENT.

Superseded or unscoreable = STALE + MALFORMED; UNCLEAR is reported, not counted.

## Method summary

Two independent passes per target, with a cut-off date equal to the search date. Re-runs on
later dates are new rows, never edits. A seeded random sample (30% of targets or 30 rows,
whichever is smaller) is searched blind by a second searcher; reversals (first STALE,
second CURRENT) and recall gaps (first CURRENT, second STALE) are investigated row by row
before publication.

`report` gives, per search date: verdict counts, the STALE+MALFORMED rate with a Wilson 95%
interval, UNCLEAR separately, the number of STALE rows whose `source_date` precedes the pin
(already stale at pin), the median lag in days from `source_date` to `search_date` for STALE
rows, and, across dates, newly stale and newly fixed problem ids.

## Validate hook

`validate --scorer module:function --construction FILE --claimed VALUE [--tol T]` imports
`function`, calls it with the construction path, and compares the returned number with the
claim (absolute tolerance). Exit 0 on match, 1 on mismatch or invalid construction. An
example (`freshcheck.examples:sum_free_size`, largest sum-free subset of {1..n}) ships with
the package.

## Replicate an audit

To re-audit a freshcheck targets table blind, give the auditor only `replicate/procedure.md`
(procedure sections 2-3), `replicate/hints.txt` (the shared source-hint list) and each target
row - never the original verdicts. The cut-off date is the search date: nothing published
after it counts. Record one row per target in the row format above, one attempt per row; a
row that ends without a verdict is recorded UNCLEAR and never retried. STALE without an
opened primary source and verbatim quote is downgraded to UNCLEAR.

When all rows are written, compare with the original rows (same `problem_id`s):

```
python -m freshcheck agree original_rows.csv replicate_rows.csv
```

Investigate every reversal row by row before calling it one.

## License

MIT.
