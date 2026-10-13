"""freshcheck GitHub Action: list rows due a literature check.

Stdlib only. Reads inputs from FC_* environment variables (see action.yml).
"""

import datetime as dt
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from freshcheck import core

MARKER = "<!-- freshcheck-action:due-rows -->"
API = "https://api.github.com"


def latest_by_row(rows):
    """Latest row (by search_date) per problem_id."""
    out = {}
    for r in rows:
        pid = (r.get("problem_id") or "").strip()
        date = (r.get("search_date") or "").strip()
        if not pid or not date:
            continue
        if pid not in out or date >= out[pid]["search_date"]:
            out[pid] = {
                "search_date": date,
                "verdict": (r.get("verdict") or "").strip().upper(),
            }
    return out


def due_rows(targets, rows, stale_days, today):
    pinned = core.parse_date(targets["pinned_date"], "pinned_date")
    latest = latest_by_row(rows or [])
    due = []
    for t in targets["rows"]:
        last = latest.get(t["id"])
        if last:
            checked = core.parse_date(last["search_date"], "search_date")
            verdict = last["verdict"]
        else:
            checked, verdict = pinned, ""
        age = (today - checked).days
        reasons = []
        if age > stale_days:
            reasons.append(f"last checked {age} days ago")
        if verdict in core.BAD:
            reasons.append(f"latest verdict {verdict}")
        if reasons:
            due.append(
                {
                    "id": t["id"],
                    "problem": t.get("problem", ""),
                    "last_checked": checked.isoformat(),
                    "days": age,
                    "verdict": verdict or "-",
                    "reasons": reasons,
                }
            )
    return due


def render(benchmark, due, stale_days, n_total):
    lines = [
        f"## freshcheck: {benchmark}",
        "",
        f"{len(due)} of {n_total} rows need attention (threshold {stale_days} days).",
        "",
    ]
    if due:
        lines += [
            "| row | problem | last checked | days | latest verdict | why |",
            "|---|---|---|---|---|---|",
        ]
        for d in due:
            prob = d["problem"].replace("|", "\\|")
            lines.append(
                f"| {d['id']} | {prob} | {d['last_checked']} | {d['days']} "
                f"| {d['verdict']} | {'; '.join(d['reasons'])} |"
            )
        lines += [
            "",
            "To record a pass: search each row, then "
            "`python -m freshcheck rows import <your.csv>` and commit the new "
            "`rows_<date>.csv`. This check does not search the literature.",
        ]
    return "\n".join(lines) + "\n"


def issue_title(n):
    return f"freshcheck: {n} rows need a literature check"


def issue_body(report):
    return f"{MARKER}\n{report}"


def _api(method, url, token, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "freshcheck-action",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read() or b"null")


def find_issue(issues):
    for i in issues or []:
        if "pull_request" not in i and MARKER in (i.get("body") or ""):
            return i
    return None


def upsert_issue(repo, token, title, body, api=_api):
    base = f"{API}/repos/{repo}/issues"
    existing = find_issue(api("GET", f"{base}?state=open&per_page=100", token))
    if existing:
        api(
            "PATCH",
            f"{base}/{existing['number']}",
            token,
            {"title": title, "body": body},
        )
        return "updated", existing["number"]
    made = api("POST", base, token, {"title": title, "body": body})
    return "opened", made["number"]


def main(env=os.environ, today=None):
    today = today or dt.date.today()
    targets = core.load_targets(env["FC_TARGETS"])
    errors, _flagged = core.validate_targets(targets)
    if errors:
        for e in errors:
            print(f"targets error: {e}", file=sys.stderr)
        return 2
    rows_path = env.get("FC_ROWS", "").strip()
    rows = core.read_rows(rows_path) if rows_path else []
    stale_days = int(env.get("FC_STALE_DAYS") or 90)
    due = due_rows(targets, rows, stale_days, today)
    report = render(
        targets.get("benchmark", "benchmark"), due, stale_days, len(targets["rows"])
    )
    print(report)
    summary = env.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(report)
    token, repo = env.get("GITHUB_TOKEN"), env.get("GITHUB_REPOSITORY")
    if due and env.get("FC_OPEN_ISSUE", "true").lower() == "true" and token and repo:
        action, num = upsert_issue(
            repo, token, issue_title(len(due)), issue_body(report)
        )
        print(f"{action} issue #{num}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except core.FreshError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)
