# TeachFlow Backend Crash — Root Cause Report

## Incident
Backend process exits with null exit code after uploading a scheme of work document.

## Date Investigated
2026-09-15

## Symptoms
- User uploads .docx scheme file
- Backend process terminates unexpectedly
- Electron shows no error (silent hang)
- Exit code: null (process killed by OS or supervisor)

---

## Root Cause Analysis

### Primary Cause: Synchronous Blocking I/O in Async Event Loop

**File:** `backend/src/routers/documents.py`

The upload handler used synchronous file operations inside an `async` function:
```python
file_path.write_bytes(content)  # SYNCHRONOUS - blocks the event loop
scheme = await parser.parse(file_path)  # Document() inside is SYNCHRONOUS
```

On Windows, uvicorn uses IOCP (I/O Completion Ports) as its event loop. Synchronous file I/O inside an async context causes:
1. Event loop starvation (all other requests blocked)
2. Health check failures
3. Process manager kills worker with SIGKILL → exit code null

### Contributing Factors

**BUG #1: Missing Import (NameError)**
- `TemplateType` referenced in `service.py:create_term_config()` but never imported
- Would crash during generation (step after upload)

**BUG #2: Unprotected File I/O**
- `file_path.write_bytes()` was outside try/except block
- OSError (permissions, disk full, Windows file locking) would propagate unhandled

**BUG #9: Memory Exhaustion Risk**
- Entire file loaded into memory BEFORE size check
- 1GB upload would consume 1GB RAM before rejection

---

## Fixes Applied

### Fix 1: Async File I/O (`documents.py`)
```python
# Before (BLOCKING):
file_path.write_bytes(content)

# After (NON-BLOCKING):
loop = asyncio.get_event_loop()
await loop.run_in_executor(None, _write_file_sync, file_path, content)
```

### Fix 2: Stream-Read Size Check (`documents.py`)
```python
# Before (LOADS ENTIRE FILE):
content = await file.read()
if len(content) > MAX_SIZE: ...

# After (STREAMS IN CHUNKS):
chunks = []
total_size = 0
while True:
    chunk = await file.read(8192)
    if not chunk: break
    total_size += len(chunk)
    if total_size > MAX_SIZE:
        raise HTTPException(413, "File too large")
    chunks.append(chunk)
content = b"".join(chunks)
```

### Fix 3: Error Handling & Cleanup (`documents.py`)
```python
try:
    # ... parse and save ...
except HTTPException:
    raise
except Exception as e:
    # Clean up file on failure
    if file_path.exists():
        file_path.unlink()
    # Roll back database
    db.rollback()
    raise HTTPException(422, detail=str(e))
```

### Fix 4: Missing Import (`service.py`)
```python
# Added TemplateType to imports
from .models import (
    ..., TemplateType, ...
)
```

### Fix 5: Database Rollback (`database.py`)
```python
def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        raise
    finally:
        db.close()
```

### Fix 6: Validation Issues Storage (`service.py`)
```python
# Before (DATA LOSS):
validation_issues=[],

# After (PRESERVES ISSUES):
validation_issues=[vi.model_dump() for vi in scheme.validation_issues],
```

### Fix 7: Absolute Upload Directory (`documents.py`)
```python
# Before (FRAGILE):
UPLOAD_DIR = Path("uploads")

# After (STABLE):
def _get_upload_dir() -> Path:
    base = os.environ.get("TEACHFLOW_DATA_DIR", os.path.expanduser("~/teachflow_data"))
    upload_dir = Path(base) / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir
```

### Fix 8: PDF Rejection (`documents.py`)
```python
# Before (WILL CRASH):
if ext not in (".docx", ".pdf"):  # PDF passes check but crashes parser

# After (REJECTS PDF):
if ext != ".docx":  # Only .docx supported
```

---

## Verification

After fixes applied:
1. Backend builds successfully with PyInstaller
2. All 3 migrations apply
3. Upload endpoint accepts .docx files without crash
4. File written to absolute path
5. Database session rolled back on error
6. Uploaded files cleaned up on parse failure

---

## Prevention

1. **Never use synchronous I/O in async handlers** — use `run_in_executor`
2. **Always stream-check file sizes** — don't load entire file before validation
3. **Wrap all file operations in try/except** — clean up on failure
4. **Test on Windows specifically** — IOCP event loop behaves differently than Linux epoll
5. **Use absolute paths** — relative paths break when CWD changes
