# REA Capability Discovery (recorded per task §2)

Discovered from the installed environment on 2026-10-14 (host: win32 x64, Node 22.23.2).

## Installed tooling

- `rea-agents@6.5.0` (npm global). CLI: `C:\nvm4w\nodejs\rea.cmd`. Binary verified: `rea --version` → `6.5.0`.
- opencode MCP registration for REA: **`state: aligned`**
  (`C:\Users\SAVIOUR\.config\opencode\opencode.jsonc`, command
  `cmd.exe /d /c npx -y rea-agents@6.5.0 mcp`). Skill `reverse-engineer-anything`
  v42, 207 MCP tools, 153 CLI commands.
- Catalog digests: tools `805433f1…38ded`, prompts `7152916a…f18aa7e`.

## How REA was actually used in this study

The REA **MCP tools are not exposed in this session's toolset**, so the study used the
**REA CLI**, which REA's own skill explicitly sanctions as the operator fallback
("Prefer an existing `rea` CLI … use `npx -y rea-agents@6.5.0` in its place").
This substitution is recorded here as required. Every capture below is a real REA
invocation whose JSON output is stored under `evidence/`.

## Capabilities verified AVAILABLE on this host

| Capability | REA command | Evidence effect |
|---|---|---|
| Bounded browser scenario (Playwright, launch or connect) | `capture-browser-scenario <json>` | runs declared actions; returns DOM/URL/screenshot/network events as Evidence |
| Passive page inspection via CDP | `inspect-web-page <endpoint> <targetId>` | page structure, scripts, network observation |
| List CDP page targets | `list-browser-targets <endpoint>` | target inventory |
| Capture one viewport | `capture-web-screenshot` | digested PNG |
| Observe user-driven session | `observe-web-session` | navigation window observation |
| Observe execution coverage | `observe-web-execution` | counters/optimization toggle |
| Capture+statically analyze a page bundle | `analyze-web-bundle <endpoint> <targetId>` | bundle static analysis |
| Inspect retained HAR/SAZ/qlog captures | `inspect-web-network-capture` | requests/responses/payloads, no URL fetch |
| Static JavaScript/Electron application | `analyze-javascript-application <path>` | modules, imports, routes, IPC |
| Artifact/package inventory | `inspect-artifact`, `extract-artifact` | member inventory, extraction |
| Managed .NET static inspection | `inspect-managed-*` | PE/CLI metadata |
| Compare captures | `compare-web-captures`, `compare-web-screenshots` | normalized equality |

Browser launch mode requires an absolute executable path; found:
`C:\Program Files\Google\Chrome\Application\chrome.exe` (155.0.8059.79) and
Edge (`C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`).

## Capabilities verified UNAVAILABLE on this host (recorded, not used)

| Capability | Reason |
|---|---|
| Native binary decompilation (Ghidra/IDA/Hopper) | no engine configured (`GHIDRA_INSTALL_DIR` unset; no IDA MCP; Hopper is macOS-only) |
| SQLite inspection | requires Node ≥24.15 (`native DatabaseSync.limits`); host is 22.23.2 → `unsupported_version` |
| Android APK analysis | no caller-supplied JADX JAR |
| macOS native utilities, firmware (Linux), packet capture (Linux tshark) | unsupported host |

## Scenario contract actually used

`browserScenarioInputSchema` (strict):
`{ browser: {mode:"launch", executable_path, headless:true} | {mode:"connect", cdp_endpoint, target_id},
   start_url: {url, query:[]},
   environment: {viewport, locale, timezone, color_scheme, reduced_motion, service_workers},
   actions: [ {step_id, action:"goto"|"click"|"fill"|"press"|"select_option"|"check"|"uncheck"|"wait_for"|"wait_for_timeout", …} ] (min 1),
   storage: {cookies, local_storage, session_storage},
   secrets: [ {secret_id, environment_variable} ],
   capture: { after_each_step:[…], at_end:[url|dom|accessibility|screenshot|history|storage],
              events:[console|page-errors|network|websockets|frames|workers|popups|downloads],
              network:{request_body,response_body,header_values} } }`

Locators: `{kind:"css",selector}` | `{kind:"role",role,name}` | `{kind:"test_id",value}`.
Action values/URL query values use `{source:"literal",value}` or `{source:"secret",secret_id}`
(the latter references env vars; secrets are never inline). Captures redact credential
headers and hash/redact storage values automatically.

## Ethical posture

Black-box only; public pages and normal application flows; agents act only via
declared REA scenario actions; no auth bypass, no payment bypass, no guessed
endpoints, no other users' data. Products requiring login/payment that cannot be
obtained legitimately are recorded as limitations and skipped.