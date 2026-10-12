import csv
import json

import pytest
from freshcheck import core
from freshcheck.cli import main


def targets(**over):
    t = {
        "benchmark": "toybench",
        "pinned_commit_or_version": "v1",
        "pinned_date": "2025-01-01",
        "rows": [
            {"id": "a", "problem": "A", "direction": "min", "target_value": 10},
            {
                "id": "b",
                "problem": "B",
                "direction": "max",
                "target_value": 5,
                "prev_best": 4,
            },
            {"id": "c", "problem": "C", "direction": "min", "target_value": 3},
            {"id": "d", "problem": "D", "direction": "max", "target_value": 8},
        ],
    }
    t.update(over)
    return t


@pytest.fixture
def ws(tmp_path):
    p = tmp_path / "targets.json"
    p.write_text(json.dumps(targets()))
    assert main(["init", str(p)]) == 0
    return tmp_path


def run(ws, *a):
    return main(["--dir", str(ws), *a])


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=sorted({k for r in rows for k in r}))
        w.writeheader()
        w.writerows(rows)


def good_stale(pid, date="2026-01-01", bv="9"):
    return {
        "problem_id": pid,
        "search_date": date,
        "verdict": "STALE",
        "better_value": bv,
        "source_kind": "primary",
        "source": "http://x",
        "source_date": "2025-06-01",
        "notes": '"value is 9"',
    }


# ----------------------------------------------------------------- init
def test_init_freezes_and_prints_sha(tmp_path, capsys):
    p = tmp_path / "t.json"
    t = targets()
    p.write_text(json.dumps(t))
    assert main(["init", str(p)]) == 0
    out = capsys.readouterr().out
    assert core.sha256_of(t) in out
    assert (tmp_path / "targets.frozen.json").exists()
    assert main(["init", str(p)]) == 0  # idempotent on same content


def test_init_refuses_changed_content(tmp_path):
    p = tmp_path / "t.json"
    p.write_text(json.dumps(targets()))
    assert main(["init", str(p)]) == 0
    t2 = targets()
    t2["rows"][0]["target_value"] = 11
    p.write_text(json.dumps(t2))
    assert main(["init", str(p)]) == 3


def test_init_refuses_prev_best_better_min(tmp_path, capsys):
    t = targets()
    t["rows"][0]["prev_best"] = 9  # min: 9 < 10 is better than target
    p = tmp_path / "t.json"
    p.write_text(json.dumps(t))
    assert main(["init", str(p)]) == 3
    assert not (tmp_path / "targets.frozen.json").exists()
    assert "prev_best" in capsys.readouterr().err
    assert main(["init", str(p), "--allow-flagged"]) == 0
    assert (tmp_path / "targets.frozen.json").exists()


def test_init_refuses_prev_best_better_max(tmp_path):
    t = targets()
    t["rows"][3]["prev_best"] = 9  # max: 9 > 8
    p = tmp_path / "t.json"
    p.write_text(json.dumps(t))
    assert main(["init", str(p)]) == 3


def test_init_equal_prev_best_ok(tmp_path):
    t = targets()
    t["rows"][0]["prev_best"] = 10
    p = tmp_path / "t.json"
    p.write_text(json.dumps(t))
    assert main(["init", str(p)]) == 0


@pytest.mark.parametrize(
    "mut",
    [
        lambda t: t.pop("pinned_date"),
        lambda t: t.update(pinned_date="yesterday"),
        lambda t: t["rows"][0].update(direction="up"),
        lambda t: t["rows"][0].update(target_value="x"),
        lambda t: t["rows"][1].update(id="a"),
        lambda t: t.update(rows=[]),
    ],
)
def test_init_schema_errors(tmp_path, mut):
    t = targets()
    mut(t)
    p = tmp_path / "t.json"
    p.write_text(json.dumps(t))
    assert main(["init", str(p)]) == 2


# ----------------------------------------------------------------- rows
def test_row_add_and_columns(ws):
    assert (
        run(
            ws,
            "row",
            "add",
            "--id",
            "a",
            "--search-date",
            "2026-01-01",
            "--verdict",
            "CURRENT",
            "--searcher",
            "s1",
        )
        == 0
    )
    f = ws / "rows_2026-01-01.csv"
    with open(f, newline="") as fh:
        rd = csv.DictReader(fh)
        assert rd.fieldnames == core.COLUMNS and len(core.COLUMNS) == 14
        rows = list(rd)
    assert rows[0]["benchmark"] == "toybench"
    assert rows[0]["pinned_value"] == "10"
    assert rows[0]["direction"] == "min"
    # append another problem, same date
    assert (
        run(
            ws,
            "row",
            "add",
            "--id",
            "b",
            "--search-date",
            "2026-01-01",
            "--verdict",
            "CURRENT",
        )
        == 0
    )
    assert len(core.read_rows(f)) == 2
    # re-recording the same problem is refused
    assert (
        run(
            ws,
            "row",
            "add",
            "--id",
            "a",
            "--search-date",
            "2026-01-01",
            "--verdict",
            "UNCLEAR",
        )
        == 2
    )
    assert len(core.read_rows(f)) == 2


def test_import_append_only_refusal(ws):
    src = ws / "in.csv"
    write_csv(
        src, [{"problem_id": "a", "search_date": "2026-02-01", "verdict": "CURRENT"}]
    )
    assert run(ws, "rows", "import", str(src)) == 0
    before = (ws / "rows_2026-02-01.csv").read_text()
    assert run(ws, "rows", "import", str(src)) == 2
    assert (ws / "rows_2026-02-01.csv").read_text() == before


def test_import_rejects_mixed_dates_and_unknown_id_and_bad_verdict(ws):
    src = ws / "in.csv"
    write_csv(
        src,
        [
            {"problem_id": "a", "search_date": "2026-02-01", "verdict": "CURRENT"},
            {"problem_id": "b", "search_date": "2026-02-02", "verdict": "CURRENT"},
        ],
    )
    assert run(ws, "rows", "import", str(src)) == 2
    write_csv(
        src, [{"problem_id": "zzz", "search_date": "2026-02-01", "verdict": "CURRENT"}]
    )
    assert run(ws, "rows", "import", str(src)) == 2
    write_csv(
        src, [{"problem_id": "a", "search_date": "2026-02-01", "verdict": "MAYBE"}]
    )
    assert run(ws, "rows", "import", str(src)) == 2
    assert not list(ws.glob("rows_*.csv"))


def test_stale_without_quote_downgraded(ws, capsys):
    r = good_stale("a")
    r["notes"] = ""
    src = ws / "in.csv"
    write_csv(src, [r])
    assert run(ws, "rows", "import", str(src)) == 0
    assert "downgraded to UNCLEAR" in capsys.readouterr().err
    assert core.read_rows(ws / "rows_2026-01-01.csv")[0]["verdict"] == "UNCLEAR"


def test_stale_with_leaderboard_source_downgraded(ws):
    r = good_stale("a")
    r["source_kind"] = "leaderboard"
    write_csv(ws / "in.csv", [r])
    assert run(ws, "rows", "import", str(ws / "in.csv")) == 0
    assert core.read_rows(ws / "rows_2026-01-01.csv")[0]["verdict"] == "UNCLEAR"


def test_stale_not_strictly_better_downgraded(ws):
    r = good_stale("a", bv="10")  # equal on a min problem
    write_csv(ws / "in.csv", [r])
    assert run(ws, "rows", "import", str(ws / "in.csv")) == 0
    assert core.read_rows(ws / "rows_2026-01-01.csv")[0]["verdict"] == "UNCLEAR"


def test_valid_stale_kept_and_validator_kind_ok(ws):
    r1, r2 = good_stale("a"), good_stale("b", bv="6")
    r2["source_kind"] = "validator"
    write_csv(ws / "in.csv", [r1, r2])
    assert run(ws, "rows", "import", str(ws / "in.csv")) == 0
    rows = core.read_rows(ws / "rows_2026-01-01.csv")
    assert [r["verdict"] for r in rows] == ["STALE", "STALE"]


# --------------------------------------------------------------- sample
def test_sample_deterministic_and_size(ws, capsys):
    assert run(ws, "sample", "--seed", "3", "--frac", "0.5") == 0
    a = json.loads(capsys.readouterr().out)
    assert run(ws, "sample", "--seed", "3", "--frac", "0.5") == 0
    b = json.loads(capsys.readouterr().out)
    assert a == b and len(a["ids"]) == 2
    assert set(a["ids"]) <= {"a", "b", "c", "d"}


def test_sample_cap():
    ids = [f"p{i}" for i in range(200)]
    assert len(core.draw_sample(ids, 1, 0.3, 30)) == 30
    assert len(core.draw_sample(ids[:10], 1, 0.3, 30)) == 3


# ---------------------------------------------------------------- agree
def mk(pid, v):
    return {"problem_id": pid, "verdict": v}


def test_kappa_known_table():
    # 2x2: both STALE 20, (STALE,CURRENT) 5, (CURRENT,STALE) 10, both CURRENT 15
    r1, r2, i = [], [], 0
    for v1, v2, n in (
        ("STALE", "STALE", 20),
        ("STALE", "CURRENT", 5),
        ("CURRENT", "STALE", 10),
        ("CURRENT", "CURRENT", 15),
    ):
        for _ in range(n):
            r1.append(mk(f"p{i}", v1))
            r2.append(mk(f"p{i}", v2))
            i += 1
    a = core.agreement(r1, r2)
    assert a["n"] == 50
    assert a["raw_agreement"] == pytest.approx(0.7)
    assert a["kappa"] == pytest.approx(0.4)
    assert len(a["reversals"]) == 5 and len(a["recall_gaps"]) == 10


def test_kappa_perfect_and_degenerate():
    r = [mk("a", "CURRENT"), mk("b", "CURRENT")]
    assert core.agreement(r, r)["kappa"] == 1.0
    with pytest.raises(core.FreshError):
        core.agreement(r, [mk("z", "CURRENT")])


def test_agree_cli(ws, capsys):
    p1, p2 = ws / "p1.csv", ws / "p2.csv"
    write_csv(p1, [mk("a", "STALE"), mk("b", "CURRENT")])
    write_csv(p2, [mk("a", "CURRENT"), mk("b", "STALE")])
    assert run(ws, "agree", str(p1), str(p2), "--json") == 0
    out = json.loads(capsys.readouterr().out)
    assert out["reversals"] == ["a"] and out["recall_gaps"] == ["b"]
    assert run(ws, "agree", str(p1), str(p2)) == 0
    assert "cohen kappa" in capsys.readouterr().out


# --------------------------------------------------------------- report
def test_wilson_known():
    lo, hi = core.wilson(5, 10)
    assert lo == pytest.approx(0.2366, abs=1e-3)
    assert hi == pytest.approx(0.7634, abs=1e-3)
    assert core.wilson(0, 0) == (0.0, 0.0)


def test_report_series(ws, capsys):
    d1 = [
        good_stale("a", "2026-01-01"),  # source 2025-06-01, after pin
        {**good_stale("b", "2026-01-01", "6"), "source_date": "2024-06-01"},
        {"problem_id": "c", "search_date": "2026-01-01", "verdict": "UNCLEAR"},
        {"problem_id": "d", "search_date": "2026-01-01", "verdict": "MALFORMED"},
    ]
    d2 = [
        {"problem_id": "a", "search_date": "2026-02-01", "verdict": "CURRENT"},
        good_stale("b", "2026-02-01", "6"),
        good_stale("c", "2026-02-01", "2"),
        {"problem_id": "d", "search_date": "2026-02-01", "verdict": "MALFORMED"},
    ]
    d2[1]["source_date"] = "2024-06-01"
    d2[2]["source_date"] = "2026-01-15"
    for rows, n in ((d1, "i1.csv"), (d2, "i2.csv")):
        write_csv(ws / n, rows)
        assert run(ws, "rows", "import", str(ws / n)) == 0
    capsys.readouterr()
    assert run(ws, "report", "--json") == 0
    rep = json.loads(capsys.readouterr().out)
    e1, e2 = rep
    assert e1["n"] == 4 and e1["stale_or_malformed"] == 3
    assert e1["unclear_not_counted"] == 1
    assert e1["already_stale_at_pin"] == 1
    assert e1["median_lag_days"] == 396.5
    assert "newly_stale" not in e1
    assert e2["newly_stale"] == ["c"] and e2["newly_fixed"] == ["a"]
    assert e2["wilson95"][0] < e2["stale_or_malformed_rate"] < e2["wilson95"][1]
    assert run(ws, "report") == 0
    assert "Wilson95" in capsys.readouterr().out


def test_report_no_files(tmp_path):
    assert main(["--dir", str(tmp_path), "report"]) == 2


# ------------------------------------------------------------- validate
def test_validate_example_scorer(tmp_path, capsys):
    f = tmp_path / "c.json"
    f.write_text(json.dumps({"n": 10, "set": [6, 7, 8, 9, 10]}))
    base = [
        "validate",
        "--scorer",
        "freshcheck.examples:sum_free_size",
        "--construction",
        str(f),
    ]
    assert main(base + ["--claimed", "5"]) == 0
    assert main(base + ["--claimed", "6"]) == 1
    assert main(base + ["--claimed", "5.4", "--tol", "0.5"]) == 0
    f.write_text(json.dumps({"n": 10, "set": [1, 2, 3]}))  # 1+2=3
    assert main(base + ["--claimed", "3"]) == 1
    assert "INVALID" in capsys.readouterr().err


def test_validate_bad_scorer(tmp_path):
    assert (
        main(["validate", "--scorer", "nope", "--construction", "x", "--claimed", "1"])
        == 2
    )
    assert (
        main(
            [
                "validate",
                "--scorer",
                "no_such_mod:f",
                "--construction",
                "x",
                "--claimed",
                "1",
            ]
        )
        == 2
    )


def test_help_exit_zero():
    with pytest.raises(SystemExit) as e:
        main(["--help"])
    assert e.value.code == 0
