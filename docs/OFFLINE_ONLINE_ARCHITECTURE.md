# TeachFlow Offline/Online Architecture

## Overview

TeachFlow supports both **offline** and **online** operation, designed for rural Ghana where internet connectivity is intermittent.

## Architecture

```
┌─────────────────────────────────────────┐
│              Frontend (Next.js)         │
│  ┌─────────────┐  ┌──────────────────┐  │
│  │   Offline   │  │    Online Mode   │  │
│  │  Mode       │  │                  │  │
│  │ (localStorage│  │ (Server API +    │  │
│  │  + IndexedDB)│  │  Database)       │  │
│  └─────────────┘  └──────────────────┘  │
│         │                   │            │
│         └─────────┬─────────┘            │
│                   │                      │
│         ┌─────────▼─────────┐            │
│         │   Sync Engine     │            │
│         │ (connect/retry)   │            │
│         └───────────────────┘            │
└─────────────────────────────────────────┘
```

## Offline Mode

When server is unreachable:
- All operations use localStorage/IndexedDB
- Upload and parse work offline (client-side PDF.js, mammoth.js)
- Lesson plan generation runs locally
- DOCX export uses client-side libraries
- Data is queued for sync when online

## Online Mode

When server is available:
- All data persists in SQLite database
- Full API access
- User authentication
- AI enrichment (requires internet)
- Cloud backup
- Content pack downloads

## Sync Strategy

### Conflict Resolution
- Server is source of truth for authenticated users
- Last-write-wins for concurrent edits
- Teacher edits always take priority over AI suggestions
- Deleted records are soft-deleted

### Sync Queue
1. Pending operations stored in IndexedDB
2. On reconnect, operations sent in order
3. Failed operations retried with exponential backoff
4. Conflicts reported to teacher for resolution

## Data Storage

### Offline (Client)
- Schemes: IndexedDB (full document data)
- Weeks: IndexedDB
- Lesson Plans: IndexedDB
- Preferences: localStorage
- Auth Token: localStorage

### Online (Server)
- SQLite database (all tables)
- File uploads on disk
- Exports in memory/TempDir

## Features by Mode

| Feature | Offline | Online |
|---------|---------|--------|
| Upload & Parse | ✅ Client-side | ✅ Server-side |
| Edit Weeks | ✅ IndexedDB | ✅ Database |
| Generate Lessons | ✅ Client-side | ✅ Server-side |
| AI Enrichment | ❌ Requires internet | ✅ Yes |
| Export DOCX | ✅ Client-side | ✅ Server-side |
| Export PDF | ⚠️ Limited | ✅ Full |
| User Auth | ⚠️ Local only | ✅ Full |
| Content Packs | ❌ Requires internet | ✅ Download |
| Cloud Backup | ❌ Requires internet | ✅ Yes |

## Detection

```javascript
// Check server availability
async function checkServerStatus() {
  try {
    const response = await fetch('/api/health', { timeout: 5000 });
    return response.ok;
  } catch {
    return false;
  }
}
```

## Progressive Enhancement

1. **Offline First**: App loads and works without server
2. **Graceful Degradation**: Features degrade gracefully when offline
3. **Background Sync**: Data syncs automatically when online
4. **User Control**: Teacher can manually sync or stay offline

## Ghana-Specific Considerations

- **Intermittent connectivity**: Operations queue and retry
- **Low bandwidth**: Minimize data transfer, compress exports
- **Shared devices**: Support multi-user with local auth
- **Power outages**: Local storage survives power loss
- **Rural areas**: Full functionality offline
