# LinkedIn browser helpers for job scouting. Load inside browser_exec with:
#   exec(open('/opt/data/skills/career/job-search-workflow/scripts/li_browser.py').read())
# Uses the pre-imported browser_exec helpers (goto_url, wait_for_load, js). Read-only:
# never clicks Apply/Submit. Keep request volume modest (no bulk crawling).
import json as _json
import re as _re
import time as _time
import urllib.parse as _up

ROLE_QUERY = ('"Cloud Engineer" OR "DevOps Engineer" OR "Cloud Architect" OR "Solution Architect" '
              'OR "Solutions Architect" OR "Platform Engineer" OR "Site Reliability Engineer"')
# Obvious non-matches dropped before opening postings (title-level only; everything else is screened by reading).
TITLE_EXCLUDE = _re.compile(r"\b(SAP|Salesforce|HVDC|Storefront|ServiceNow|Dynamics|C\+\+|Werkstudent|Working Student|"
                            r"Intern(ship)?|Praktik|Junior|Trainee|Ausbildung|Sales Engineer|Pre-?Sales)\b", _re.I)



def li_search(keywords=ROLE_QUERY, location="Germany", tpr_seconds=86400, max_pages=4):
    """Collect search cards (all pages up to max_pages). Returns list of dicts."""
    base = ("https://www.linkedin.com/jobs/search/?keywords=" + _up.quote(keywords) +
            "&location=" + _up.quote(location) + f"&f_TPR=r{int(tpr_seconds)}&sortBy=DD")
    goto_url(base); wait_for_load(); _time.sleep(5)
    if "/login" in js("location.href") or "/checkpoint" in js("location.href"):
        raise RuntimeError("LINKEDIN_SIGNED_OUT: " + js("location.href"))
    total = js("(document.querySelector('main')||document.body).innerText.split('\\n').find(s=>/results?$/.test(s.trim()))||''")
    seen, out = set(), []
    for page in range(1, max_pages + 1):
        if page > 1:
            if not js(f"""!!document.querySelector('button[aria-label="Page {page}"]')"""):
                break
            goto_url(base + f"&start={25 * (page - 1)}"); wait_for_load(); _time.sleep(4)
            if not js(f"""!!document.querySelector('button[aria-label="Page {page}"][aria-current="page"]')"""):
                break  # LinkedIn did not land on the requested page; stop rather than re-read page 1
        rows = []
        n = js("document.querySelectorAll('li[data-occludable-job-id]').length")
        for i in range(n):  # cards are occluded until scrolled into view, one at a time
            r = None
            for _ in range(4):
                r = js(f"""(() => {{ const li=document.querySelectorAll('li[data-occludable-job-id]')[{i}]; if(!li) return null;
                    li.scrollIntoView({{block:'center'}});
                    return {{id: li.getAttribute('data-occludable-job-id'), lines: li.innerText.split('\\n').map(s=>s.trim()).filter(Boolean)}}; }})()""")
                if r is None or len(r["lines"]) >= 4:
                    break
                _time.sleep(0.4)
            if r:
                rows.append(r)
        for r in rows:
            if r["id"] in seen or len(r["lines"]) < 4:
                continue
            seen.add(r["id"])
            L = r["lines"]
            # lines: title, title (dup/with verification), company, location (model), then badges/age
            loc = L[3]
            m = _re.search(r"\((Remote|Hybrid|On-site)\)", loc)
            out.append({"job_id": "linkedin:" + r["id"], "url": f"https://www.linkedin.com/jobs/view/{r['id']}/",
                        "title": L[0], "company": L[2], "location": _re.sub(r"\s*\((Remote|Hybrid|On-site)\)", "", loc),
                        "work_model": m.group(1) if m else None,
                        "badges": " | ".join(L[4:]), "easy_apply_badge": "Easy Apply" in L[4:],
                        "card_applied": any(x.startswith("Applied") for x in L[4:]),
                        "query": f"{keywords} @ {location} r{tpr_seconds}"})
    return {"total_text": total, "cards": out}


def li_prefilter(cards):
    keep, drop = [], []
    for c in cards:
        (drop if TITLE_EXCLUDE.search(c["title"]) else keep).append(c)
    return keep, drop


def li_job(job_id_num):
    """Read one posting: header, workplace/type chips, apply route, applied state, description."""
    goto_url(f"https://www.linkedin.com/jobs/view/{job_id_num}/"); wait_for_load(); _time.sleep(4)
    if "/login" in js("location.href"):
        raise RuntimeError("LINKEDIN_SIGNED_OUT")
    d = js(r"""(() => { const m=document.querySelector('main')||document.body; const t=m.innerText;
      const i=t.indexOf('About the job'); const head=(i>0?t.slice(0,i):t.slice(0,800));
      let desc=i>0?t.slice(i+13):''; for (const stop of ['About the company','Show more','… more','Similar jobs','More jobs']) { const k=desc.indexOf(stop); if(k>0) desc=desc.slice(0,k); }
      const btn=[...m.querySelectorAll('button, a')].find(b=>/^(Easy Apply|Apply)$/.test((b.innerText||'').trim()));
      return {page_title:document.title, head, desc:desc.trim().slice(0,9000),
        apply_button: btn ? btn.innerText.trim() : null,
        applied: /\bApplied\b.{0,40}ago|Application submitted/.test(head),
        closed: /No longer accepting applications/i.test(head)}; })()""")
    d["job_id"] = f"linkedin:{job_id_num}"
    d["apply_route"] = ("easy_apply" if d["apply_button"] == "Easy Apply" else
                        "external" if d["apply_button"] == "Apply" else "none")
    return d


def save_json(obj, name):
    import os
    p = os.path.join(os.environ.get("BH_AGENT_WORKSPACE", "."), name)
    with open(p, "w") as f:
        _json.dump(obj, f, ensure_ascii=False, indent=1)
    return p