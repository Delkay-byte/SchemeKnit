# SchemeKnit Storage Quotas and Recovery

Status: **IMPLEMENTED AND LOCALLY VERIFIED** for the storage adapter, quota
ledger, concurrency guards, deletion release and reconciliation. The live
Cloudflare R2 plan and current bucket usage could not be inspected from this
workstation because no R2 credentials are present in the local environment.
The owner must confirm the account allowance before relying on the 8 GiB cap.

## 1. Existing durable upload integration

The code already wired original uploads through the storage adapter when
`STORAGE_BACKEND=s3`:

- bucket: `schemeknit` (private);
- production prefix: `production/`;
- key shape: `production/uploads/{owner_id}/{random-hex}{ext}` — opaque, never
  derived from the teacher filename;
- the original is written to R2 before the upload is reported successful;
- `schemes.storage_filename` stores the object key (or a local path in local
  development), never a public URL;
- originals are retrieved only through authenticated backend operations;
- local temporary files are removed after a successful durable upload;
- the bucket is never made public.

This workstream added the missing authoritative quota accounting, the
user-facing usage surface, deletion release and reconciliation. It did not
change the bucket or move existing production objects.

## 2. Quotas

Defaults (all environment-configurable):

| Setting | Default | Meaning |
|---|---:|---|
| `STORAGE_USER_QUOTA_BYTES` | `524288000` (500 MiB) | Retained original storage per teacher |
| `STORAGE_GLOBAL_QUOTA_BYTES` | `8589934592` (8 GiB) | Global cap for the `production/` prefix |
| `STORAGE_MAX_FILE_BYTES` | `52428800` (50 MiB) | Single uploaded original |
| `MAX_UPLOAD_SIZE_MB` | `50` | Legacy cap; the effective per-file limit is the stricter of the two |

The global cap stays below the previously assessed 10 GB free R2 allocation to
preserve headroom. The owner must verify the current Cloudflare plan and usage;
if the actual free capacity is lower, lower `STORAGE_GLOBAL_QUOTA_BYTES` before
enabling uploads at scale.

## 3. Authoritative accounting

`backend/src/storage_quota.py` and tables `storage_ledger` /
`storage_counters` provide:

- actual byte count from the upload body (never `Content-Length` or a
  browser-supplied size);
- a row per object with owner, opaque key, size, file type, document id,
  reservation state, timestamps and an optional idempotency key;
- integer byte counters for the teacher and the global prefix;
- atomic guarded SQL:
  `committed_bytes + reserved_bytes + requested <= limit`;
- a reservation before the object is written, committed only after the object
  exists, and released on every failure path;
- exactly-once release on document deletion (`state: deleted`);
- idempotent commit/release so a retry cannot double-count;
- shared database counters, so multiple workers cannot each spend the full
  quota.

A failed validation never creates a reservation. A failed R2 write releases the
reservation. A timeout never produces a false success: the upload endpoint
returns a safe error and no scheme row.

## 4. User-facing behaviour

`GET /api/documents/storage` returns only the caller's own usage:

- used, reserved and total bytes;
- quota and remaining bytes, plus readable MiB/GiB values;
- per-file maximum;
- global usage/remaining (aggregate only, no other teacher's data).

The upload page shows `Storage: X of Y used`, remaining space and the per-file
limit, checks the selected file before upload, and refreshes after success.
Quota exhaustion returns HTTP 507 with a machine code and readable message; a
single oversized file returns HTTP 413. An over-quota upload creates no scheme,
no R2 object and consumes no lesson/AI credit.

## 5. Deletion and ownership

`data_service.delete_scheme` deletes the scheme row, removes the object only
when no other scheme references it, then releases the ledger exactly once.
Upload, read and delete routes all resolve the scheme through the authenticated
owner. Another teacher receives 403/404 and cannot inspect or delete the file.

## 6. Reconciliation and orphan handling

Command (read-only by default):

```bash
cd backend
python -m scripts.reconcile_storage
```

It reports:

- committed ledger objects missing from the bucket;
- objects under `production/` with no ledger and no live scheme reference
  (orphan candidates);
- legacy scheme objects that predate the ledger and should be counted
  (backfilled, never deleted).

Deletion is deliberately hard to trigger:

```bash
python -m scripts.reconcile_storage --delete-orphans --no-dry-run --min-age-hours 24
```

Even then an object is deleted only when no live scheme row references it and
it is older than the minimum age. A dry run never writes or deletes. This
protects valid teacher documents from a stale or partial ledger.

## 7. Tests

`backend/tests/test_storage_quotas.py` (16 tests) proves:

- a reservation commits and is counted once;
- a failed reservation releases quota;
- the same idempotency key reserves once;
- deletion releases exactly once;
- teacher quota is atomic across independent sessions;
- the global cap blocks a second teacher;
- reconciliation reports orphans without deleting valid referenced objects;
- an HTTP upload counts actual bytes and exposes usage;
- an oversized file is rejected before storage;
- teacher and global quota exhaustion reject with 507 and no partial scheme;
- invalid files create no object or reservation;
- an R2 timeout releases the reservation and creates no scheme;
- the original is still readable after a simulated restart;
- another teacher cannot read or delete the file;
- document deletion returns the quota to zero.

Existing durable-upload, upload-security and export suites also pass
(`66 passed` in the targeted run).

## 8. Residual limitations

- The live R2 account plan and byte usage were not verified locally; no live
  R2 write was performed.
- Legacy objects are counted after the reconciliation backfill. Until that
  command runs in production, a pre-ledger object does not consume its
  teacher's counter. It is reported, not silently ignored.
- Reconciliation listing requires the S3-compatible bucket credentials; the
  command intentionally prints no secret.
- Storing generated exports in R2 remains unnecessary: exports are regenerated
  from persisted lesson data.
