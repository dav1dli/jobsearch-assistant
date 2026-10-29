# SPA fallback for li_job when cross-document navigation hangs (Page.navigate creates a loader that never commits,
# new tabs freeze on Runtime.evaluate). Loads a job into the search page's details pane via history.pushState +
# popstate. Run inside browser_exec on a tab already showing /jobs/search/?currentJobId=...
#   exec(open('/opt/data/skills/career/job-search-workflow/scripts/li_spa_reader.py').read())
#   d = li_job_spa('4479348461', expect_title='Senior Cloud Engineer ...')
import re as _re, time as _time


def li_job_spa(job_id_num, expect_title=None, wait=15):
    u = js('location.href')
    if 'currentJobId=' not in u:
        raise RuntimeError('open a /jobs/search/ page first')
    nu = _re.sub(r'currentJobId=\d+', f'currentJobId={job_id_num}', u)
    js(f"history.pushState({{}}, '', {nu!r}); dispatchEvent(new PopStateEvent('popstate', {{state: {{}}}}));")
    d = None
    for n in range(wait * 2):
        _time.sleep(0.5)
        if d and d['desc'] and (not expect_title or expect_title[:25] in d['head']) and not d['apply_button'] and n < 14:
            d = None
            continue  # pane matched but apply button not rendered yet; re-read
        d = js(r"""(() => { const m=document.querySelector('main')||document.body; const t=m.innerText;
          let s=t.lastIndexOf('LinkedIn Corporation ©'); let pane = s>0 ? t.slice(s).replace(/^.*\n/, '') : t;
          const i=pane.indexOf('About the job'); const head=(i>0?pane.slice(0,i):pane.slice(0,800));
          let desc=i>0?pane.slice(i+13):''; for (const stop of ['About the company','Similar jobs','More jobs','Looking for talent?']) { const k=desc.indexOf(stop); if(k>0) desc=desc.slice(0,k); }
          const det=document.querySelector('.jobs-search__job-details--wrapper, .jobs-details, .job-view-layout') || m;
          const btns=[...det.querySelectorAll('button, a')].map(b=>(b.innerText||'').trim().split('\n')[0]);
          const ap = btns.find(x=>/^(Easy Apply|Apply)$/.test(x)) || null;
          return {head: head.slice(-1500), desc: desc.trim().slice(0,9000), apply_button: ap,
            applied: /\bApplied\b.{0,40}ago|Application submitted/.test(head),
            closed: /No longer accepting applications/i.test(head)}; })()""")
        if d and d['desc'] and (not expect_title or expect_title[:25] in d['head']):
            break
    d['job_id'] = f'linkedin:{job_id_num}'
    d['title_match'] = bool(expect_title and expect_title[:25] in d['head'])
    lines = [l.strip() for l in d['head'].split('\n') if l.strip()]
    d['meta'] = next((l for l in lines if '·' in l), None)  # 'City · posted · applicants'
    d['apply_route'] = ('easy_apply' if d['apply_button'] == 'Easy Apply' or 'Easy Apply' in lines else
                        'external' if d['apply_button'] == 'Apply' or 'Apply' in lines else 'none')
    return d