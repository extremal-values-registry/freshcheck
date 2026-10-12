"""Pure logic for freshcheck (stdlib only)."""

import csv
import datetime as dt
import hashlib
import json
import math
import os
import random
import statistics

COLUMNS = [
    "benchmark",
    "problem_id",
    "pinned_value",
    "pinned_commit",
    "direction",
    "search_date",
    "searcher",
    "verdict",
    "better_value",
    "source",
    "source_date",
    "source_kind",
    "queries_run",
    "notes",
]
VERDICTS = ["STALE", "MALFORMED", "UNCLEAR", "CURRENT", "STALE-LEADERBOARD"]
SOURCE_KINDS = ["primary", "validator", "leaderboard", "secondary"]
BAD = ("STALE", "MALFORMED")


class FreshError(Exception):
    pass


def parse_date(s, what="date"):
    try:
        return dt.date.fromisoformat(str(s).strip())
    except ValueError:
        raise FreshError(f"{what} must be ISO YYYY-MM-DD, got {s!r}")


def num(x, what):
    try:
        v = float(x)
    except (TypeError, ValueError):
        raise FreshError(f"{what} must be numeric, got {x!r}")
    if math.isnan(v):
        raise FreshError(f"{what} is NaN")
    return v


def strictly_better(a, b, direction):
    """True if a is strictly better than b in the given direction."""
    return a < b if direction == "min" else a > b


# ---------------------------------------------------------------- targets
def load_targets(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError) as e:
        raise FreshError(f"cannot read targets {path}: {e}")


def validate_targets(t):
    """Return (errors, flagged). errors are fatal; flagged are refused
    unless the caller allows them."""
    errors, flagged = [], []
    if not isinstance(t, dict):
        return ["targets file must be a JSON object"], []
    for k in ("benchmark", "pinned_commit_or_version", "pinned_date", "rows"):
        if k not in t:
            errors.append(f"missing key: {k}")
    if errors:
        return errors, []
    for k in ("benchmark", "pinned_commit_or_version"):
        if not isinstance(t[k], str) or not t[k].strip():
            errors.append(f"{k} must be a non-empty string")
    try:
        parse_date(t["pinned_date"], "pinned_date")
    except FreshError as e:
        errors.append(str(e))
    if not isinstance(t["rows"], list) or not t["rows"]:
        errors.append("rows must be a non-empty list")
        return errors, []
    seen = set()
    for i, r in enumerate(t["rows"]):
        tag = f"rows[{i}]"
        if not isinstance(r, dict):
            errors.append(f"{tag}: not an object")
            continue
        rid = r.get("id")
        if not isinstance(rid, str) or not rid.strip():
            errors.append(f"{tag}: id must be a non-empty string")
            continue
        tag = f"row {rid}"
        if rid in seen:
            errors.append(f"{tag}: duplicate id")
        seen.add(rid)
        if not isinstance(r.get("problem"), str) or not r["problem"].strip():
            errors.append(f"{tag}: problem must be a non-empty string")
        d = r.get("direction")
        if d not in ("min", "max"):
            errors.append(f"{tag}: direction must be 'min' or 'max'")
        try:
            tv = num(r.get("target_value"), "target_value")
        except FreshError as e:
            errors.append(f"{tag}: {e}")
            continue
        if r.get("prev_best") is not None:
            try:
                pb = num(r["prev_best"], "prev_best")
            except FreshError as e:
                errors.append(f"{tag}: {e}")
                continue
            if d in ("min", "max") and strictly_better(pb, tv, d):
                flagged.append(
                    f"{tag}: prev_best {pb} is better than target_value {tv} "
                    f"(direction={d}); likely extraction defect"
                )
    return errors, flagged


def canonical_json(t):
    return json.dumps(t, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_of(t):
    return hashlib.sha256(canonical_json(t).encode("utf-8")).hexdigest()


def target_index(t):
    return {r["id"]: r for r in t["rows"]}


# ------------------------------------------------------------------- rows
def normalize_row(row, targets=None):
    """Fill pinned fields from targets, validate, apply the STALE downgrade.
    Returns (row_dict_with_all_columns, warnings)."""
    warns = []
    r = {c: ("" if row.get(c) is None else str(row.get(c)).strip()) for c in COLUMNS}
    if targets is not None:
        idx = target_index(targets)
        if r["problem_id"] not in idx:
            raise FreshError(f"problem_id {r['problem_id']!r} not in targets")
        tr = idx[r["problem_id"]]
        r["benchmark"] = r["benchmark"] or targets["benchmark"]
        r["pinned_commit"] = r["pinned_commit"] or targets["pinned_commit_or_version"]
        r["direction"] = r["direction"] or tr["direction"]
        r["pinned_value"] = r["pinned_value"] or str(tr["target_value"])
    for c in (
        "benchmark",
        "problem_id",
        "pinned_value",
        "direction",
        "search_date",
        "verdict",
    ):
        if not r[c]:
            raise FreshError(f"missing required field: {c}")
    parse_date(r["search_date"], "search_date")
    if r["source_date"]:
        parse_date(r["source_date"], "source_date")
    num(r["pinned_value"], "pinned_value")
    if r["direction"] not in ("min", "max"):
        raise FreshError("direction must be min or max")
    r["verdict"] = r["verdict"].upper()
    if r["verdict"] not in VERDICTS:
        raise FreshError(f"verdict must be one of {VERDICTS}, got {r['verdict']!r}")
    if r["source_kind"] and r["source_kind"] not in SOURCE_KINDS:
        raise FreshError(f"source_kind must be one of {SOURCE_KINDS}")
    if r["better_value"]:
        num(r["better_value"], "better_value")
    if r["verdict"] == "STALE":
        why = []
        if r["source_kind"] not in ("primary", "validator"):
            why.append("source_kind is not primary/validator")
        if not r["notes"]:
            why.append("no quote in notes")
        if not r["better_value"]:
            why.append("no better_value")
        elif not strictly_better(
            float(r["better_value"]), float(r["pinned_value"]), r["direction"]
        ):
            why.append("better_value is not strictly better than pinned_value")
        if why:
            warns.append(
                f"{r['problem_id']}: STALE downgraded to UNCLEAR ("
                + "; ".join(why)
                + ")"
            )
            r["verdict"] = "UNCLEAR"
    return r, warns


def rows_filename(date):
    return f"rows_{date}.csv"


def write_rows(path, rows, append=False):
    exists = os.path.exists(path)
    if exists and not append:
        raise FreshError(f"{path} already exists; rows files are append-only")
    with open(path, "a" if append else "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\n")
        if not exists:
            w.writeheader()
        for r in rows:
            w.writerow(r)


def read_rows(path):
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            return list(csv.DictReader(fh))
    except OSError as e:
        raise FreshError(f"cannot read {path}: {e}")


# ----------------------------------------------------------------- sample
def draw_sample(ids, seed, frac=0.3, cap=30):
    ids = sorted(ids)
    k = min(math.ceil(frac * len(ids)), cap, len(ids))
    return sorted(random.Random(seed).sample(ids, k))


# ------------------------------------------------------------------ stats
def wilson(k, n, z=1.959964):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def agreement(r1, r2):
    m1 = {r["problem_id"]: r["verdict"] for r in r1}
    m2 = {r["problem_id"]: r["verdict"] for r in r2}
    ids = sorted(set(m1) & set(m2))
    n = len(ids)
    if n == 0:
        raise FreshError("no overlapping problem_ids")
    po = sum(m1[i] == m2[i] for i in ids) / n
    cats = sorted(set(m1[i] for i in ids) | set(m2[i] for i in ids))
    pe = sum(
        (sum(m1[i] == c for i in ids) / n) * (sum(m2[i] == c for i in ids) / n)
        for c in cats
    )
    kappa = (1.0 if po == 1 else 0.0) if pe == 1 else (po - pe) / (1 - pe)
    return {
        "n": n,
        "raw_agreement": po,
        "kappa": kappa,
        "reversals": [i for i in ids if m1[i] == "STALE" and m2[i] == "CURRENT"],
        "recall_gaps": [i for i in ids if m1[i] == "CURRENT" and m2[i] == "STALE"],
        "only_in_first": sorted(set(m1) - set(m2)),
        "only_in_second": sorted(set(m2) - set(m1)),
    }


def report(files_rows, pinned_date=None):
    """files_rows: list of row lists. Rows are grouped by search_date."""
    by_date = {}
    for rows in files_rows:
        for r in rows:
            by_date.setdefault(r["search_date"], []).append(r)
    out, prev_bad = [], None
    for d in sorted(by_date):
        rows = by_date[d]
        n = len(rows)
        counts = {v: sum(r["verdict"] == v for r in rows) for v in VERDICTS}
        bad = {r["problem_id"] for r in rows if r["verdict"] in BAD}
        lo, hi = wilson(len(bad), n)
        already, lags = 0, []
        for r in rows:
            if r["verdict"] == "STALE" and r["source_date"]:
                sd = parse_date(r["source_date"])
                if pinned_date is not None and sd < pinned_date:
                    already += 1
                lags.append((parse_date(d) - sd).days)
        entry = {
            "search_date": d,
            "n": n,
            "counts": counts,
            "stale_or_malformed": len(bad),
            "stale_or_malformed_rate": len(bad) / n if n else 0.0,
            "wilson95": [lo, hi],
            "unclear_not_counted": counts["UNCLEAR"],
            "already_stale_at_pin": already if pinned_date is not None else None,
            "median_lag_days": statistics.median(lags) if lags else None,
        }
        if prev_bad is not None:
            entry["newly_stale"] = sorted(bad - prev_bad)
            entry["newly_fixed"] = sorted(prev_bad - bad)
        out.append(entry)
        prev_bad = bad
    return out
