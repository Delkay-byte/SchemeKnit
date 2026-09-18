# Role & Entitlement Decision Matrix

Legend: CURRENT = observed web behavior (tested). RULE = recommended product rule.
PA = Platform Admin, SA = School Admin, T = Teacher.

## Licensing & membership

| Scenario | PA | SA | T | Notes |
|---|---|---|---|---|
| No license (school w/o license) | manage | views banner, T-creation 403 | free-tier workflow allowed | CURRENT: SA exists only if school was activated earlier (code needs a license); RULE: keep — activation requires a license; free tier only for unassigned teachers |
| Pending license | manage/activate | T-creation 403 (no usable license) | workflow allowed only if unassigned | CURRENT: pending not usable; redeeming a code flips it active. RULE: keep |
| Active license | manage | full access | full access | CURRENT = RULE |
| Suspended license | manage/reactivate | views data, T-creation 403 | workflow 403, data intact | CURRENT = RULE (verified live both ways) |
| Expired license | manage/renew | same as suspended | same as suspended | CURRENT (code path; past-expiry unit-tested). RULE: keep |
| Teacher not added to school | N/A | N/A | free-tier: login, list, upload, review, generate, edit, export all allowed; anonymous register 401 | CURRENT: permissive free tier for the deterministic workflow, **AI excluded** (Decision: option (a)). RULE: keep — free tier stays the acquisition funnel for everything except AI |
| Teacher added to school | N/A | directory + lifecycle | school-scoped everything | CURRENT = RULE |

## AI (assisted section regeneration + AI at generation time)

Decision (owner-approved): **option (a)** — AI is gated on a usable licence, free tier
excluded. Enforced server-side at every AI entry point, before any provider is built.

| Scenario | Button visible? | Request allowed? | Server response |
|---|---|---|---|
| Active licensed school | yes | yes | 200, content inserted |
| Suspended / cancelled school | yes | **no** | 403 `AI assistance requires an active school license or a paid AI entitlement.` |
| Expired school (active row past expiry) | yes | **no** | 403, same message |
| School membership, no licence row | yes | **no** | 403, same message |
| No school membership (free tier) | yes | **no** | 403, same message |
| Unexpired paid entitlement row | yes | yes | 200, content inserted |
| Expired paid entitlement row | yes | **no** | 403, same message |
| AI OFF | n/a | deterministic only | full lesson plan, gate not consulted |
| AI unavailable (provider unreachable) | yes | attempt → controlled failure | 503/message, data intact (proven) |

**Resolved (was: WEB COMMERCIAL ENFORCEMENT GAP).** Availability (can we reach Ollama)
and entitlement (may this school use AI?) are now separate: entitlement is decided from
licence/entitlement rows first, so a reachable local provider can no longer grant access.
Reason codes are returned internally: `paid_entitlement`, `school_license`,
`no_entitlement`, `no_active_license`, `license_expired`.
See `WEB_BEHAVIOR_BASELINE_FOR_DESKTOP.md` §2 for the parity specification.

## Scheme deletion

| Scenario | CURRENT | RULE candidates |
|---|---|---|
| Own scheme, no generated content | 200 + storage file cleaned | keep (== OPTION A) |
| Own scheme with jobs/lessons | 409 + message, nothing deleted | keep (== OPTION A); B (cascade with explicit confirm) only if owner explicitly wants destructive cleanup; C (archive) is a new feature — defer |
| Another teacher's scheme | 403 | keep |
| Missing scheme | 404 | keep |
| UI affordance | icon-only trash per scheme card | keep; consider explicit label/tooltip |

## Other rows

| Scenario | PA | SA | T |
|---|---|---|---|
| Scheme upload | N/A (refuses teacher workflow, 403) | N/A | own uploads; unassigned allowed (free tier) |
| Lesson generation | N/A | N/A | own schemes; license-gated iff school assigned |
| Export | N/A | N/A | own jobs/lessons; same gating as generation |
| AI enabled/disabled | N/A | N/A | buttons always rendered; enforcement = entitlement first (403), then availability (503) |
| Templates | global publish | school scope only (no auto-ownership of teacher privates) | own + applicable built-ins |
| Payments/plans | full control | none (read-only license summary) | none |
