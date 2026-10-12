"""Command-line interface: python -m freshcheck <command>."""

import argparse
import csv
import glob
import importlib
import json
import os
import sys

from . import core
from .core import FreshError

FROZEN = "targets.frozen.json"


def _frozen_path(args):
    return args.targets or os.path.join(args.dir, FROZEN)


def cmd_init(args):
    t = core.load_targets(args.targets_file)
    errors, flagged = core.validate_targets(t)
    if errors:
        for e in errors:
            print(f"error: {e}", file=sys.stderr)
        return 2
    for f in flagged:
        print(f"{'warning' if args.allow_flagged else 'refused'}: {f}", file=sys.stderr)
    if flagged and not args.allow_flagged:
        print(
            "refusing to freeze; fix the rows or pass --allow-flagged", file=sys.stderr
        )
        return 3
    digest = core.sha256_of(t)
    out = args.out or os.path.join(
        os.path.dirname(os.path.abspath(args.targets_file)), FROZEN
    )
    if os.path.exists(out):
        old = core.load_targets(out)
        if core.sha256_of(old) != digest:
            print(
                f"error: {out} exists with different content; targets are frozen",
                file=sys.stderr,
            )
            return 3
    else:
        with open(out, "w", encoding="utf-8", newline="") as fh:
            fh.write(core.canonical_json(t) + "\n")
    print(f"frozen {len(t['rows'])} rows -> {out}")
    print(f"sha256 {digest}")
    return 0


def _load_frozen(args):
    t = core.load_targets(_frozen_path(args))
    errors, _ = core.validate_targets(t)
    if errors:
        raise FreshError("frozen targets invalid: " + "; ".join(errors))
    return t


def _store(args, rows_in, append_ok):
    targets = _load_frozen(args)
    norm, warns, dates = [], [], set()
    seen = set()
    for raw in rows_in:
        r, w = core.normalize_row(raw, targets)
        if (r["search_date"], r["problem_id"]) in seen:
            raise FreshError(
                f"duplicate row for {r['problem_id']} on {r['search_date']}"
            )
        seen.add((r["search_date"], r["problem_id"]))
        norm.append(r)
        warns += w
        dates.add(r["search_date"])
    if len(dates) != 1:
        raise FreshError(f"all rows must share one search_date, got {sorted(dates)}")
    date = dates.pop()
    path = os.path.join(args.dir, core.rows_filename(date))
    existing = set()
    if append_ok and os.path.exists(path):
        existing = {r["problem_id"] for r in core.read_rows(path)}
        dup = existing & {r["problem_id"] for r in norm}
        if dup:
            raise FreshError(
                f"{sorted(dup)} already recorded in {path}; never overwrite"
            )
    core.write_rows(path, norm, append=append_ok)
    for w in warns:
        print(f"warning: {w}", file=sys.stderr)
    print(f"wrote {len(norm)} row(s) -> {path}")
    return 0


def cmd_row_add(args):
    row = {c: getattr(args, c, None) for c in core.COLUMNS}
    row["problem_id"] = args.id
    return _store(args, [row], append_ok=True)


def cmd_rows_import(args):
    try:
        with open(args.csv_file, encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
    except OSError as e:
        raise FreshError(f"cannot read {args.csv_file}: {e}")
    if not rows:
        raise FreshError("no rows in CSV")
    return _store(args, rows, append_ok=False)


def cmd_sample(args):
    t = _load_frozen(args)
    ids = core.draw_sample(list(core.target_index(t)), args.seed, args.frac, args.cap)
    res = {
        "seed": args.seed,
        "frac": args.frac,
        "cap": args.cap,
        "n_targets": len(t["rows"]),
        "ids": ids,
    }
    text = json.dumps(res, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    print(text)
    return 0


def cmd_agree(args):
    a = core.agreement(core.read_rows(args.pass1), core.read_rows(args.pass2))
    if args.json:
        print(json.dumps(a, indent=2))
        return 0
    print(f"n compared      {a['n']}")
    print(f"raw agreement   {a['raw_agreement']:.3f}")
    print(f"cohen kappa     {a['kappa']:.3f}")
    print(f"reversals (first STALE, second CURRENT): {a['reversals']}")
    print(f"recall gaps (first CURRENT, second STALE): {a['recall_gaps']}")
    if a["only_in_first"] or a["only_in_second"]:
        print(f"unmatched: first={a['only_in_first']} second={a['only_in_second']}")
    return 0


def cmd_report(args):
    pinned = None
    tp = _frozen_path(args)
    if os.path.exists(tp):
        pinned = core.parse_date(core.load_targets(tp)["pinned_date"])
    files = sorted(glob.glob(os.path.join(args.dir, "rows_*.csv")))
    if not files:
        raise FreshError(f"no rows_*.csv in {args.dir}")
    rep = core.report([core.read_rows(f) for f in files], pinned)
    if args.json:
        print(json.dumps(rep, indent=2))
        return 0
    for e in rep:
        lo, hi = e["wilson95"]
        print(f"== {e['search_date']}  n={e['n']}")
        print("   " + "  ".join(f"{k}={v}" for k, v in e["counts"].items()))
        print(
            f"   STALE+MALFORMED {e['stale_or_malformed']}/{e['n']} = "
            f"{e['stale_or_malformed_rate']:.3f}  Wilson95 [{lo:.3f}, {hi:.3f}]"
        )
        print(f"   UNCLEAR (reported, not counted): {e['unclear_not_counted']}")
        print(f"   already stale at pin: {e['already_stale_at_pin']}")
        print(
            f"   median lag (days, source_date -> search_date): {e['median_lag_days']}"
        )
        if "newly_stale" in e:
            print(f"   newly stale: {e['newly_stale']}")
            print(f"   newly fixed: {e['newly_fixed']}")
    return 0


def cmd_validate(args):
    if ":" not in args.scorer:
        raise FreshError("--scorer must be module:function")
    mod, fn = args.scorer.split(":", 1)
    sys.path.insert(0, os.getcwd())
    try:
        func = getattr(importlib.import_module(mod), fn)
    except (ImportError, AttributeError) as e:
        raise FreshError(f"cannot load scorer {args.scorer}: {e}")
    try:
        got = float(func(args.construction))
    except Exception as e:  # scorer defined by the user
        print(f"INVALID construction: {e}", file=sys.stderr)
        return 1
    claimed = core.num(args.claimed, "claimed")
    ok = abs(got - claimed) <= args.tol
    print(
        f"scored={got} claimed={claimed} tol={args.tol} -> "
        f"{'MATCH' if ok else 'MISMATCH'}"
    )
    return 0 if ok else 1


def build_parser():
    p = argparse.ArgumentParser(
        prog="freshcheck",
        description="Structure and validate a best-known-table literature audit.",
    )
    p.add_argument("--dir", default=".", help="working directory for rows files")
    p.add_argument(
        "--targets", default=None, help=f"frozen targets file (default <dir>/{FROZEN})"
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="validate and freeze a targets file")
    s.add_argument("targets_file")
    s.add_argument("--out", default=None)
    s.add_argument(
        "--allow-flagged",
        action="store_true",
        help="accept rows whose prev_best beats target_value",
    )
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("row", help="single-row operations")
    rs = s.add_subparsers(dest="rcmd", required=True)
    a = rs.add_parser("add", help="append one row to rows_<search_date>.csv")
    a.add_argument("--id", required=True, help="problem_id from the targets file")
    a.add_argument("--search-date", dest="search_date", required=True)
    a.add_argument("--verdict", required=True)
    for c in (
        "searcher",
        "better_value",
        "source",
        "source_date",
        "source_kind",
        "queries_run",
        "notes",
        "pinned_value",
        "benchmark",
        "pinned_commit",
        "direction",
    ):
        a.add_argument("--" + c.replace("_", "-"), dest=c, default=None)
    a.set_defaults(fn=cmd_row_add)

    s = sub.add_parser("rows", help="bulk row operations")
    rs = s.add_subparsers(dest="rcmd", required=True)
    i = rs.add_parser("import", help="import a CSV as a new rows_<date>.csv")
    i.add_argument("csv_file")
    i.set_defaults(fn=cmd_rows_import)

    s = sub.add_parser("sample", help="draw the blind second-searcher sample")
    s.add_argument("--seed", type=int, required=True)
    s.add_argument("--frac", type=float, default=0.3)
    s.add_argument("--cap", type=int, default=30)
    s.add_argument("--out", default=None)
    s.set_defaults(fn=cmd_sample)

    s = sub.add_parser("agree", help="agreement between two passes")
    s.add_argument("pass1")
    s.add_argument("pass2")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_agree)

    s = sub.add_parser("report", help="per-date counts and time series")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_report)

    s = sub.add_parser("validate", help="re-score a construction with a scorer")
    s.add_argument("--scorer", required=True, help="module:function(path)->number")
    s.add_argument("--construction", required=True)
    s.add_argument("--claimed", required=True)
    s.add_argument("--tol", type=float, default=1e-9)
    s.set_defaults(fn=cmd_validate)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except FreshError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
