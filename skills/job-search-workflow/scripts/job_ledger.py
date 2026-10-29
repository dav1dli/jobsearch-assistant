#!/usr/bin/env python3
"""Job application ledger: stable refs, gated state machine, append-only events.

Stdlib only. DB: $JOB_LEDGER_DB or $JOB_APPLICATION_HOME/ledger.sqlite.
Every state change writes an immutable event (UPDATE/DELETE on events is blocked
by triggers). Submission requires: user approval, passing preflight with recorded
answers, recorded documents whose SHA-256 still matches, user document
confirmation, and an explicit user "submit N" command recorded verbatim.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
import sys

TERMINAL = {"applied", "rejected", "screened_out", "skipped", "closed", "already_applied"}

# from-state -> allowed to-states for each action
TRANSITIONS = {
    "shortlist": ({"discovered"}, "shortlisted"),
    "screen_out": ({"discovered", "shortlisted"}, "screened_out"),
    "already_applied": ({"discovered", "shortlisted", "later", "approved"}, "already_applied"),
    "approve": ({"shortlisted", "later"}, "approved"),
    "reject": ({"shortlisted", "later", "approved", "preflight_blocked", "preflight_ok",
                "docs_proposed", "docs_confirmed"}, "rejected"),
    "later": ({"shortlisted"}, "later"),
    "preflight_ok": ({"approved", "preflight_blocked"}, "preflight_ok"),
    "preflight_blocked": ({"approved", "preflight_ok"}, "preflight_blocked"),
    "docs": ({"preflight_ok", "docs_proposed", "docs_confirmed"}, "docs_proposed"),
    "confirm_docs": ({"docs_proposed"}, "docs_confirmed"),
    "authorize_submit": ({"docs_confirmed"}, "submit_authorized"),
    "submitted": ({"submit_authorized"}, "submitted_unverified"),
    "submit_failed": ({"submit_authorized", "submitted_unverified"}, "docs_confirmed"),
    "verify": ({"submitted_unverified"}, "applied"),
    "skip": ({"approved", "preflight_blocked", "preflight_ok", "docs_proposed", "docs_confirmed"}, "skipped"),
    # user reports applying themselves (e.g. external employer site)
    "applied_manually": ({"discovered", "shortlisted", "later", "approved", "preflight_blocked", "preflight_ok",
                          "docs_proposed", "docs_confirmed", "skipped"}, "already_applied"),
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  ref INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT UNIQUE NOT NULL,          -- e.g. linkedin:4460731789
  url TEXT NOT NULL, title TEXT NOT NULL, company TEXT NOT NULL,
  location TEXT, work_model TEXT, apply_route TEXT, posted TEXT,
  state TEXT NOT NULL, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
  fit TEXT, gaps TEXT, note TEXT, digest_at TEXT,
  answers_json TEXT, cv_path TEXT, cv_sha256 TEXT, letter_path TEXT, letter_sha256 TEXT,
  docs_kind TEXT, applied_at TEXT, evidence TEXT
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ref INTEGER NOT NULL, ts TEXT NOT NULL, action TEXT NOT NULL,
  from_state TEXT, to_state TEXT, actor TEXT NOT NULL, data TEXT
);
CREATE TABLE IF NOT EXISTS answers (
  key TEXT PRIMARY KEY, value TEXT NOT NULL, source TEXT NOT NULL, updated TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
  BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
  BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS jobs_no_delete BEFORE DELETE ON jobs
  BEGIN SELECT RAISE(ABORT, 'jobs are never deleted; use a terminal state'); END;
"""


class LedgerError(Exception):
    pass


def now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def db_path():
    if os.environ.get("JOB_LEDGER_DB"):
        return os.environ["JOB_LEDGER_DB"]
    home = os.environ.get("JOB_APPLICATION_HOME", "/opt/data/job-applications")
    return os.path.join(home, "ledger.sqlite")


def connect(path=None):
    path = path or db_path()
    new = not os.path.exists(path)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    if new:
        os.chmod(path, 0o600)
    return con


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def norm_title(t):
    t = re.sub(r"\((?:[mwfdx]\s*/\s*)+[mwfdx]\)|\((?:all genders|verified job)\)", " ", t.lower())
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def get(con, ref):
    row = con.execute("SELECT * FROM jobs WHERE ref=?", (int(ref),)).fetchone()
    if not row:
        raise LedgerError(f"unknown ref {ref}")
    return row


def event(con, ref, action, frm, to, actor, data=None):
    con.execute("INSERT INTO events(ref,ts,action,from_state,to_state,actor,data) VALUES(?,?,?,?,?,?,?)",
                (ref, now(), action, frm, to, actor, json.dumps(data or {}, ensure_ascii=False)))


def transition(con, ref, action, actor, data=None, **fields):
    row = get(con, ref)
    allowed, to = TRANSITIONS[action]
    if row["state"] not in allowed:
        raise LedgerError(f"#{ref} is '{row['state']}'; '{action}' needs one of {sorted(allowed)}")
    sets = ", ".join(["state=?"] + [f"{k}=?" for k in fields])
    con.execute(f"UPDATE jobs SET {sets} WHERE ref=?", [to, *fields.values(), int(ref)])
    event(con, int(ref), action, row["state"], to, actor, data)
    return to


def discover(con, items, actor="scout"):
    """Insert new jobs; refresh last_seen on known ones. Returns list of result dicts."""
    out = []
    ts = now()
    for it in items:
        jid = it["job_id"]
        for k in ("url", "title", "company"):
            if not it.get(k):
                raise LedgerError(f"{jid}: missing {k}")
        row = con.execute("SELECT ref,state FROM jobs WHERE job_id=?", (jid,)).fetchone()
        if row:
            con.execute("UPDATE jobs SET last_seen=? WHERE ref=?", (ts, row["ref"]))
            out.append({"ref": row["ref"], "job_id": jid, "new": False, "state": row["state"]})
            continue
        similar = [dict(r) for r in con.execute(
            "SELECT ref,job_id,title,state FROM jobs WHERE lower(company)=lower(?)", (it["company"],))
            if norm_title(r["title"]) == norm_title(it["title"])]
        cur = con.execute(
            "INSERT INTO jobs(job_id,url,title,company,location,work_model,apply_route,posted,state,first_seen,last_seen)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (jid, it["url"], it["title"], it["company"], it.get("location"), it.get("work_model"),
             it.get("apply_route"), it.get("posted"), "discovered", ts, ts))
        ref = cur.lastrowid
        event(con, ref, "discover", None, "discovered", actor, {"query": it.get("query"), "similar": similar})
        out.append({"ref": ref, "job_id": jid, "new": True, "state": "discovered",
                    "possible_repost_of": [s["ref"] for s in similar]})
    return out


def import_observed(con, path):
    doc = json.load(open(path))
    res = []
    for a in doc["applications"]:
        item = {"job_id": "linkedin:" + a["job_id"], "url": a["url"], "title": a["title"],
                "company": a["company"], "location": a.get("location"), "work_model": a.get("work_model"),
                "apply_route": "unknown", "posted": a.get("posting_note")}
        r = discover(con, [item], actor="import")[0]
        if r["new"]:
            transition(con, r["ref"], "already_applied", "import",
                       {"source": path, "evidence": a.get("evidence"), "status_text": a.get("linkedin_status_text")},
                       applied_at=a.get("applied_date_approx"), evidence=a.get("evidence"))
        res.append(r)
    return res


def authorize_submit(con, ref, actor, command):
    row = get(con, ref)
    if actor != "user":
        raise LedgerError("only the user can authorize submission")
    if not re.fullmatch(rf"\s*submit\s+#?{int(ref)}\s*", command, re.I):
        raise LedgerError(f"command must be the user's literal 'submit {ref}', got {command!r}")
    evs = [e["action"] for e in con.execute("SELECT action,actor FROM events WHERE ref=? AND actor='user'", (ref,))]
    for need in ("approve", "confirm_docs"):
        if need not in evs:
            raise LedgerError(f"#{ref}: no user '{need}' event")
    if not row["answers_json"]:
        raise LedgerError(f"#{ref}: no recorded form answers (run preflight)")
    for p, h in ((row["cv_path"], row["cv_sha256"]), (row["letter_path"], row["letter_sha256"])):
        if p and (not os.path.exists(p) or sha256(p) != h):
            raise LedgerError(f"#{ref}: document changed or missing since confirmation: {p}")
    if not row["cv_path"]:
        raise LedgerError(f"#{ref}: no CV recorded")
    return transition(con, ref, "authorize_submit", actor, {"command": command, "cv_sha256": row["cv_sha256"]})


def fmt(row, long=False):
    s = f"#{row['ref']} [{row['state']}] {row['title']} — {row['company']} · {row['location'] or '?'}"
    if row["work_model"]:
        s += f" ({row['work_model']})"
    if long:
        for k in ("apply_route", "posted", "fit", "gaps", "note", "docs_kind", "cv_path", "applied_at", "evidence"):
            if row[k]:
                s += f"\n   {k}: {row[k]}"
        s += f"\n   {row['url']}"
    return s


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--db")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    s = sub.add_parser("import-observed"); s.add_argument("file")
    s = sub.add_parser("discover", help="JSON list of {job_id,url,title,company,location,work_model,apply_route,posted,query}")
    s.add_argument("file")
    s = sub.add_parser("screen"); s.add_argument("ref", type=int)
    s.add_argument("--result", choices=["shortlist", "screen_out", "already_applied"], required=True)
    s.add_argument("--fit", default=""); s.add_argument("--gaps", default=""); s.add_argument("--reason", default="")
    s.add_argument("--apply-route"); s.add_argument("--work-model"); s.add_argument("--location")
    s = sub.add_parser("mark-digested"); s.add_argument("refs", type=int, nargs="+")
    s = sub.add_parser("decide"); s.add_argument("action", choices=["approve", "reject", "later", "skip", "applied_manually"])
    s.add_argument("refs", type=int, nargs="+"); s.add_argument("--actor", required=True)
    s.add_argument("--text", required=True, help="user's verbatim message"); s.add_argument("--reason", default="")
    s = sub.add_parser("preflight"); s.add_argument("ref", type=int)
    s.add_argument("--result", choices=["ok", "blocked"], required=True)
    s.add_argument("--answers", help="JSON file: [{question, answer, source}]"); s.add_argument("--note", default="")
    s = sub.add_parser("docs"); s.add_argument("ref", type=int); s.add_argument("--cv", required=True)
    s.add_argument("--letter"); s.add_argument("--kind", choices=["default", "tailored"], required=True)
    s = sub.add_parser("confirm-docs"); s.add_argument("ref", type=int)
    s.add_argument("--actor", required=True); s.add_argument("--text", required=True)
    s = sub.add_parser("authorize-submit"); s.add_argument("ref", type=int)
    s.add_argument("--actor", required=True); s.add_argument("--text", required=True)
    s = sub.add_parser("submitted"); s.add_argument("ref", type=int); s.add_argument("--note", default="")
    s = sub.add_parser("submit-failed"); s.add_argument("ref", type=int); s.add_argument("--note", required=True)
    s = sub.add_parser("verify"); s.add_argument("ref", type=int); s.add_argument("--evidence", required=True)
    s = sub.add_parser("close"); s.add_argument("ref", type=int); s.add_argument("--reason", required=True)
    s = sub.add_parser("check"); s.add_argument("--company", required=True); s.add_argument("--title", required=True)
    s = sub.add_parser("show"); s.add_argument("ref", type=int)
    s = sub.add_parser("list"); s.add_argument("--state", action="append")
    s = sub.add_parser("answer-set"); s.add_argument("key"); s.add_argument("value"); s.add_argument("--source", required=True)
    sub.add_parser("answers")
    sub.add_parser("summary")
    a = p.parse_args(argv)
    con = connect(a.db)
    try:
        with con:
            r = run(con, a)
        if r is not None:
            print(r if isinstance(r, str) else json.dumps(r, indent=1, ensure_ascii=False))
        return 0
    except LedgerError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    finally:
        con.close()


def run(con, a):
    c = a.cmd
    if c == "init":
        return f"ledger ready: {a.db or db_path()}"
    if c == "import-observed":
        return import_observed(con, a.file)
    if c == "discover":
        return discover(con, json.load(open(a.file)))
    if c == "screen":
        extra = {k: v for k, v in (("apply_route", a.apply_route), ("work_model", a.work_model),
                                   ("location", a.location)) if v}
        fields = dict(fit=a.fit or None, gaps=a.gaps or None, note=a.reason or None, **extra)
        return transition(con, a.ref, a.result, "scout", {"reason": a.reason, **extra}, **fields)
    if c == "mark-digested":
        ts = now()
        for ref in a.refs:
            get(con, ref)
            con.execute("UPDATE jobs SET digest_at=? WHERE ref=?", (ts, ref))
            event(con, ref, "digest", None, None, "scout", {})
        return "ok"
    if c == "decide":
        if a.actor != "user":
            raise LedgerError("decisions must come from the user")
        return {ref: transition(con, ref, a.action, "user", {"text": a.text, "reason": a.reason},
                                **({"note": a.reason} if a.reason else {})) for ref in a.refs}
    if c == "preflight":
        answers = json.load(open(a.answers)) if a.answers else None
        if a.result == "ok":
            if not answers:
                raise LedgerError("preflight ok requires --answers (use [] if the form has no questions)")
            bad = [q for q in answers if not q.get("answer") or not q.get("source")]
            if bad:
                raise LedgerError(f"answers missing value/source: {bad}")
        return transition(con, a.ref, "preflight_" + a.result, "agent", {"note": a.note, "answers": answers},
                          note=a.note or None, **({"answers_json": json.dumps(answers, ensure_ascii=False)} if answers is not None else {}))
    if c == "docs":
        f = {"cv_path": os.path.abspath(a.cv), "cv_sha256": sha256(a.cv), "docs_kind": a.kind,
             "letter_path": os.path.abspath(a.letter) if a.letter else None,
             "letter_sha256": sha256(a.letter) if a.letter else None}
        return transition(con, a.ref, "docs", "agent", f, **f)
    if c == "confirm-docs":
        if a.actor != "user":
            raise LedgerError("only the user can confirm documents")
        row = get(con, a.ref)
        if sha256(row["cv_path"]) != row["cv_sha256"]:
            raise LedgerError("CV changed since it was recorded")
        return transition(con, a.ref, "confirm_docs", "user", {"text": a.text, "cv_sha256": row["cv_sha256"]})
    if c == "authorize-submit":
        return authorize_submit(con, a.ref, a.actor, a.text)
    if c == "submitted":
        return transition(con, a.ref, "submitted", "agent", {"note": a.note})
    if c == "submit-failed":
        return transition(con, a.ref, "submit_failed", "agent", {"note": a.note}, note=a.note)
    if c == "verify":
        return transition(con, a.ref, "verify", "agent", {"evidence": a.evidence},
                          evidence=a.evidence, applied_at=now())
    if c == "close":
        row = get(con, a.ref)
        if row["state"] in TERMINAL:
            raise LedgerError(f"#{a.ref} already terminal: {row['state']}")
        con.execute("UPDATE jobs SET state='closed', note=? WHERE ref=?", (a.reason, a.ref))
        event(con, a.ref, "close", row["state"], "closed", "agent", {"reason": a.reason})
        return "closed"
    if c == "check":
        n = norm_title(a.title)
        return [dict(ref=r["ref"], state=r["state"], title=r["title"], job_id=r["job_id"]) for r in
                con.execute("SELECT * FROM jobs WHERE lower(company)=lower(?)", (a.company,))
                if norm_title(r["title"]) == n]
    if c == "show":
        row = get(con, a.ref)
        evs = [f"  {e['ts']} {e['actor']}: {e['action']} {e['from_state'] or ''}->{e['to_state'] or ''} {e['data']}"
               for e in con.execute("SELECT * FROM events WHERE ref=? ORDER BY id", (a.ref,))]
        return fmt(row, True) + ("\n   answers: " + row["answers_json"] if row["answers_json"] else "") + "\n" + "\n".join(evs)
    if c == "list":
        q, args = "SELECT * FROM jobs", []
        if a.state:
            q += " WHERE state IN (%s)" % ",".join("?" * len(a.state)); args = a.state
        return "\n".join(fmt(r) for r in con.execute(q + " ORDER BY ref", args)) or "(none)"
    if c == "answer-set":
        con.execute("INSERT INTO answers(key,value,source,updated) VALUES(?,?,?,?) ON CONFLICT(key) DO UPDATE SET "
                    "value=excluded.value, source=excluded.source, updated=excluded.updated",
                    (a.key, a.value, a.source, now()))
        event(con, 0, "answer_set", None, None, "user", {"key": a.key, "value": a.value, "source": a.source})
        return "ok"
    if c == "answers":
        return {r["key"]: {"value": r["value"], "source": r["source"]} for r in con.execute("SELECT * FROM answers")}
    if c == "summary":
        return {r[0]: r[1] for r in con.execute("SELECT state, count(*) FROM jobs GROUP BY state")}


if __name__ == "__main__":
    sys.exit(main())