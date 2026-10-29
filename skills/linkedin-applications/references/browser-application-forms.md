# Browser application forms across machines

Use this when the signed-in browser runs on a different machine from the generated CV/letter. Do not transfer account cookies. Keep the browser endpoint loopback-only and use the user's authenticated session.

1. Inspect the application before submitting: exact job, employer, location, contact fields, selected resume, letter, consent checkboxes, and any legal or salary questions. Distinguish a native LinkedIn flow from a link to an employer ATS. Do not infer sensitive answers.
2. A CDP file chooser resolves `DOM.setFileInputFiles` paths on the **browser host**, not the agent host. If a local file helper cannot reach the agent's PDF, encode the PDF with `base64 -w0 CV.pdf > RESTRICTED_SCRATCH.b64` (mode 0600). Do not print the encoded bytes or file contents.
3. Click the visible upload control to mount the hidden `input[type=file]`. Read the base64 privately in `browser_exec`, then construct a browser-side `File` and dispatch a normal change event:

```python
import json
b = open('/restricted/scratch/cv.b64').read()
js('window.__cvB64=""')
for i in range(0, len(b), 5000):
    js('window.__cvB64+=' + json.dumps(b[i:i+5000]))
print(js('''(() => {const bytes=Uint8Array.from(atob(window.__cvB64), c=>c.charCodeAt(0));
 const file=new File([bytes], 'tailored_CV.pdf', {type:'application/pdf'});
 const input=document.querySelector('input[type=file]');
 const transfer=new DataTransfer(); transfer.items.add(file);
 input.files=transfer.files;
 input.dispatchEvent(new Event('change', {bubbles:true}));
 delete window.__cvB64;
 return {name:input.files[0]?.name, size:input.files[0]?.size};})()'''))
```

Transfer base64 in small browser-evaluation chunks because a single long expression can exceed the browser transport limit; confirm the browser-side file size, the site's upload-success state, and the selected filename/radio before submitting. On LinkedIn Easy Apply, check the optional employer-follow checkbox and turn it off unless the user authorized following; it may start checked. Choose the exact input when there are separate resume and letter controls. On framework-controlled forms, click and type fields one at a time, then verify their values after a short debounce; programmatic fills or rapid sequential typing can be reset by rerenders. For searchable country/city/source controls, type the value, wait for suggestions, click the exact option, and verify the selected chip or display text: an uncommitted input value is not a selection.
4. Wait for the site's upload-success state, inspect the exact selected filename and final review page, and only then submit with the user's authorization. For employer-hosted iframe forms, open the iframe's actual `src` in a tab when same-origin interaction is unavailable; retain the LinkedIn referral link when provided. If a posting-linked page no longer offers the form, inspect the employer's live careers listing and verify role/title before using its current application route.
5. Read back a LinkedIn `Application submitted` state or the employer form's explicit confirmation. An ATS may reveal an emailed human-verification code only after an initial submit; hand this to the user rather than entering a code through browser input or claiming completion. Record the job ID, route, document paths, answers, and confirmation; do not equate a button click or a `SUBMITTING` spinner with success. Remove private base64 scratch files after use.