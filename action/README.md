# freshcheck action

Checks a "best known" table on a schedule and opens one issue when rows need attention.

## Use it (two lines)

In any workflow job, after `actions/checkout`:

```yaml
      - uses: OWNER/freshcheck/action@v0.1
        with: { targets: targets.json, rows: rows_latest.csv }
```

A complete scheduled workflow is in [examples/workflow.yml](../examples/workflow.yml).
Give the job `permissions: issues: write` so it can open the issue.

Inputs: `targets` (path to `targets.json`, required), `rows` (path to the latest rows CSV,
optional), `stale_days` (default `90`), `open_issue` (default `true`).

## What it does

- Loads `targets.json` and validates it with freshcheck's core (fails on fatal errors).
- For each row, computes days since its last check: the latest `search_date` in the rows CSV,
  or the targets' `pinned_date` if the row was never checked.
- Lists rows older than `stale_days` and rows whose latest verdict is STALE or MALFORMED.
- Writes a markdown table to the job summary.
- If `open_issue` is true and rows are due, opens or updates ONE issue titled
  "freshcheck: N rows need a literature check". It finds its own issue by a hidden marker in
  the body, so re-runs never create duplicates.

## What it does not do

It does **not** search the literature. It tells you which rows are due. To record a pass,
search each due row, write your verdicts to a CSV, run
`python -m freshcheck rows import <your.csv>`, and commit the new `rows_<date>.csv`
(see the main [README](../README.md)).

If you would rather not do the search yourself, a full-table literature check is available.
