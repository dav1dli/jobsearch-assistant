#!/usr/bin/env python3
"""Synthetic tests for job_ledger.py (no real data touched)."""
import json
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import job_ledger as L  # noqa: E402

tmp = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
db = os.path.join(tmp, "t.sqlite")


def run(*args):
    return L.main(["--db", db, *map(str, args)])


def expect_fail(*args):
    assert run(*args) == 2, f"expected failure: {args}"


def write(name, obj):
    p = os.path.join(tmp, name)
    with open(p, "w") as f:
        json.dump(obj, f) if not isinstance(obj, str) else f.write(obj)
    return p


assert run("init") == 0
jobs = [{"job_id": "linkedin:1", "url": "https://x/1", "title": "Senior DevOps Engineer (m/w/d)", "company": "Acme"},
        {"job_id": "linkedin:2", "url": "https://x/2", "title": "Cloud Architect", "company": "Beta"}]
assert run("discover", write("d.json", jobs)) == 0
con = L.connect(db)
# rediscovery is not new; repost with same normalized title is flagged
r = L.discover(con, jobs + [{"job_id": "linkedin:3", "url": "https://x/3", "title": "Senior DevOps Engineer (f/m/d)", "company": "ACME"}])
con.commit()
assert [x["new"] for x in r] == [False, False, True] and r[2]["possible_repost_of"] == [1], r
print("PASS: dedupe by job id and repost detection")

# decisions require user actor and valid order
expect_fail("decide", "approve", 1, "--actor", "user", "--text", "approve 1")   # still 'discovered'
assert run("screen", 1, "--result", "shortlist", "--fit", "Azure, Terraform") == 0
assert run("screen", 2, "--result", "screen_out", "--reason", "onsite Munich") == 0
expect_fail("decide", "approve", 1, "--actor", "agent", "--text", "x")
assert run("decide", "approve", 1, "--actor", "user", "--text", "approve 1") == 0
expect_fail("decide", "approve", 2, "--actor", "user", "--text", "approve 2")  # terminal
L.discover(L.connect(db), [])  # no-op
assert run("discover", write("d4.json", [{"job_id": "linkedin:4", "url": "https://x/4", "title": "SRE", "company": "Q"}])) == 0
assert run("decide", "applied_manually", 4, "--actor", "user", "--text", "applied 4 on company site") == 0
assert L.get(L.connect(db), 4)["state"] == "already_applied"
print("PASS: state machine and user-only decisions")

# preflight needs sourced answers
expect_fail("preflight", 1, "--result", "ok")
expect_fail("preflight", 1, "--result", "ok", "--answers", write("bad.json", [{"question": "GCP?", "answer": ""}]))
assert run("preflight", 1, "--result", "ok", "--answers",
           write("a.json", [{"question": "Years of Terraform?", "answer": "5", "source": "profile.json r1_2"}])) == 0
cv = write("cv.pdf", "%PDF fake")
assert run("docs", 1, "--cv", cv, "--kind", "default") == 0
expect_fail("authorize-submit", 1, "--actor", "user", "--text", "submit 1")   # docs not confirmed
expect_fail("confirm-docs", 1, "--actor", "agent", "--text", "ok")
assert run("confirm-docs", 1, "--actor", "user", "--text", "cv ok 1") == 0
expect_fail("authorize-submit", 1, "--actor", "user", "--text", "submit 2")   # wrong number
expect_fail("authorize-submit", 1, "--actor", "user", "--text", "go ahead")   # not literal
expect_fail("authorize-submit", 1, "--actor", "agent", "--text", "submit 1")
with open(cv, "a") as f:
    f.write("tampered")
expect_fail("authorize-submit", 1, "--actor", "user", "--text", "submit 1")   # hash changed
with open(cv, "w") as f:
    f.write("%PDF fake")
assert run("authorize-submit", 1, "--actor", "user", "--text", "Submit #1") == 0
print("PASS: submission gate (approval, answers, doc hash, confirmation, literal submit N)")

expect_fail("verify", 1, "--evidence", "x")   # must be submitted first
assert run("submitted", 1) == 0
assert run("verify", 1, "--evidence", "LinkedIn 'Application submitted' + tracker Applied") == 0
assert L.get(con, 1)["state"] == "applied"
print("PASS: submitted -> verified applied")

for sql in ("UPDATE events SET actor='x'", "DELETE FROM events", "DELETE FROM jobs"):
    try:
        con.execute(sql); raise AssertionError(sql)
    except sqlite3.DatabaseError:
        pass
con.rollback(); con.close()
print("PASS: events append-only, jobs undeletable")

obs = write("obs.json", {"applications": [{"job_id": "99", "url": "https://x/99", "title": "DevOps", "company": "Z",
                                          "applied_date_approx": "2026-10-27", "evidence": "tracker"}]})
assert run("import-observed", obs) == 0 and run("import-observed", obs) == 0
st = L.connect(db).execute("SELECT state, count(*) c FROM jobs WHERE job_id='linkedin:99'").fetchone()
assert st["state"] == "already_applied" and st["c"] == 1
print("PASS: observed import is idempotent and marks already_applied")