# Literature-check procedure (sections 2-3)

## 2. Search, two independent passes
Each pass is one searcher (person or model) working without seeing the other's notes.
Run each of these in order and log the query strings:
1. Problem name + "best known" / "improved" / "new bound" / "record".
2. Canonical identifiers: OEIS id, Erdős problem number, MathOverflow id, Wikipedia page, constant name.
3. arXiv listing search (math.CO, math.NT, math.MG, cs.DM as fit) restricted to the window
   [pinned source date, search_date].
4. The benchmark authors' own later papers and repos (v2 papers, public construction dumps).
5. Live leaderboards and public construction repos for the benchmark.
6. Google Scholar "cited by" on the pinned source.
Stop a pass when two consecutive queries return nothing new.

## 3. Evidence standard for a non-CURRENT verdict
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

## 4. (end of excerpt)
