import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "action"))
import run

EX = os.path.join(ROOT, "examples")
TODAY = dt.date(2026, 10, 12)


def targets():
    with open(os.path.join(EX, "targets.json"), encoding="utf-8") as fh:
        return json.load(fh)


def test_no_rows_all_due_since_pin():
    t = targets()
    due = run.due_rows(t, [], 90, TODAY)
    assert [d["id"] for d in due] == [r["id"] for r in t["rows"]]
    assert all(d["last_checked"] == t["pinned_date"] for d in due)


def test_recent_rows_only_bad_verdicts_due():
    t = targets()
    rows = [
        {"problem_id": r["id"], "search_date": "2026-10-01", "verdict": "CURRENT"}
        for r in t["rows"]
    ]
    rows[0]["verdict"] = "STALE"
    rows[1]["verdict"] = "malformed"
    rows.append(
        {
            "problem_id": rows[0]["problem_id"],
            "search_date": "2026-01-01",
            "verdict": "CURRENT",
        }
    )  # older row must not win
    due = run.due_rows(t, rows, 90, TODAY)
    assert [d["id"] for d in due] == [rows[0]["problem_id"], rows[1]["problem_id"]]
    assert due[0]["reasons"] == ["latest verdict STALE"]
    assert due[1]["reasons"] == ["latest verdict MALFORMED"]


def test_threshold_boundary():
    t = targets()
    rows = [
        {"problem_id": r["id"], "search_date": "2026-07-14", "verdict": "CURRENT"}
        for r in t["rows"]
    ]  # exactly 90 days
    assert run.due_rows(t, rows, 90, TODAY) == []
    assert len(run.due_rows(t, rows, 89, TODAY)) == len(t["rows"])


def test_summary_rendering(tmp_path):
    summary = tmp_path / "summary.md"
    env = {
        "FC_TARGETS": os.path.join(EX, "targets.json"),
        "FC_ROWS": os.path.join(EX, "pass1.csv"),
        "FC_STALE_DAYS": "90",
        "FC_OPEN_ISSUE": "true",
        "GITHUB_STEP_SUMMARY": str(summary),
    }
    assert run.main(env, today=TODAY) == 0
    text = summary.read_text(encoding="utf-8")
    assert text.startswith("## freshcheck: toy-benchmark")
    assert "| row | problem |" in text and "latest verdict STALE" in text
    assert "does not search the literature" in text


def test_render_empty_and_pipe_escape():
    assert "0 of 3 rows" in run.render("b", [], 90, 3)
    d = [
        {
            "id": "x",
            "problem": "a|b",
            "last_checked": "2026-01-01",
            "days": 1,
            "verdict": "-",
            "reasons": ["r"],
        }
    ]
    assert "a\\|b" in run.render("b", d, 90, 1)


class FakeAPI:
    def __init__(self, issues):
        self.issues = issues

    def __call__(self, method, url, token, payload=None):
        if method == "GET":
            return self.issues
        if method == "POST":
            issue = {"number": len(self.issues) + 1, **payload}
            self.issues.append(issue)
            return issue
        num = int(url.rsplit("/", 1)[1])
        next(i for i in self.issues if i["number"] == num).update(payload)
        return {}


def test_issue_idempotent():
    api = FakeAPI(
        [
            {"number": 1, "title": "unrelated", "body": "hi"},
            {"number": 2, "title": "pr", "body": run.MARKER, "pull_request": {}},
        ]
    )
    body = run.issue_body("report")
    assert body.startswith(run.MARKER)
    assert run.upsert_issue("o/r", "t", run.issue_title(3), body, api=api) == (
        "opened",
        3,
    )
    assert run.upsert_issue("o/r", "t", run.issue_title(2), body, api=api) == (
        "updated",
        3,
    )
    mine = [
        i for i in api.issues if run.MARKER in i["body"] and "pull_request" not in i
    ]
    assert len(mine) == 1
    assert mine[0]["title"] == "freshcheck: 2 rows need a literature check"


def test_no_issue_without_token(monkeypatch):
    called = []
    monkeypatch.setattr(run, "upsert_issue", lambda *a, **k: called.append(a))
    env = {
        "FC_TARGETS": os.path.join(EX, "targets.json"),
        "FC_OPEN_ISSUE": "true",
        "GITHUB_REPOSITORY": "o/r",
    }
    assert run.main(env, today=TODAY) == 0
    assert called == []
