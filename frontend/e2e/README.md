# Browser acceptance harness

Real-browser checks for the export download path. These exist because the download
failures that reached production were invisible to unit tests: the server answered
`200 OK` with a correct body, and the *browser* refused to save it.

## What it covers

`download-acceptance.js` launches a real Chrome/Edge, logs in through the UI, opens the
generation export panel, selects the canonical approved organizational template, and then:

| Check | Why |
|---|---|
| Word download reaches disk, is a real DOCX (`PK`), named `*.docx` | the reported "Download Word: FAIL (Chrome / PASS Edge)" |
| `URL.revokeObjectURL` only ever runs inside a `setTimeout` | Chrome aborts a download whose object URL is revoked in the click's task |
| ZIP download reaches disk, is a real archive, named `*.zip` | `Content-Disposition: attachment` made Chrome/Edge refuse `application/zip` from `fetch()` |
| PDF either downloads a real PDF (`%PDF-`) **or** shows the controlled server message | distinguishes "PDF generation failed" from "browser download failed" |
| No uncaught exceptions, no unexpected 4xx/5xx | catches silent regressions in the export path |

Responses from `/export/pdf` answering 4xx/5xx are expected on a server with no document
converter (LibreOffice/docx2pdf); that is the documented layer-1 behaviour.

## Running it

Start the backend and the web app, then:

```bash
# from frontend/
TF_SCHEME_ID=<scheme id with a completed generation job> npm run e2e:downloads:chrome
TF_SCHEME_ID=<scheme id with a completed generation job> npm run e2e:downloads:edge
```

Environment:

| Variable | Default | Purpose |
|---|---|---|
| `TF_WEB_URL` | `http://localhost:3000` | web app base URL |
| `TF_SCHEME_ID` | *(required)* | scheme that already has generated lessons |
| `TF_DOWNLOAD_DIR` | `backend/temp/ba/downloads` | where downloads are saved for inspection |

Credentials are read from the acceptance fixture (`teacher@acceptance.test`); seed an
equivalent licensed school first. The backend must allow the web app's origin via
`CORS_ORIGINS`.

## Interpreting failures

* `[Word]`/`[ZIP]` "browser saved a file" fails → the response never reached JS. Check
  for `Content-Disposition: attachment` or a revoked-early object URL.
* `[PDF]` "no download -> controlled, user-visible message" fails → the server error is
  not being surfaced in the UI, which makes a failed export look like a dead button.
