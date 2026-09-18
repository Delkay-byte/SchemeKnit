# Desktop Activation System

## Overview

The TeachFlow desktop application supports license activation through activation codes. This allows schools to activate premium features on their local installation.

## Activation Flow

### 1. User Launches TeachFlow
- Application checks for existing license cache
- If no license found, shows activation screen

### 2. Activation Screen
Two options:
- **Activate School License** — enter activation code
- **Continue with Free Offline** — use basic features

### 3. Enter Activation Code
User enters code in format: `TF-SCH-XXXX-XXXX-XXXX`

### 4. Validation
Desktop sends activation request to central TeachFlow service:
```
POST /api/platform-admin/activate
{
  "activation_code": "TF-SCH-XXXX-XXXX-XXXX"
}
```

### 5. Service Response
On success:
```json
{
  "school": {
    "id": "...",
    "name": "Awasive M/A Basic School",
    "school_code": "AWASIVE-001"
  },
  "license": {
    "code": "TF-LIC-XXXX-XXXX",
    "plan": "TeachFlow School Annual",
    "start_date": "2026-10-01",
    "expiry_date": "2027-09-30",
    "seat_limit": 20,
    "features": ["multi_teacher", "admin_dashboard", "premium_templates"]
  },
  "message": "Activation successful"
}
```

### 6. Local Cache
License info is cached locally in SQLite:
- School ID and name
- License code
- Plan name and features
- Seat limit
- Expiry date
- Cached timestamp

### 7. School Admin Creation
After activation:
- First user created becomes School Administrator
- School Admin can then create teacher accounts

## Security

### Validation Authority
- The central TeachFlow service is authoritative
- Desktop does NOT trust local-only validation
- Periodic online validation recommended

### Offline Grace Period
- After activation, desktop works offline for configurable period
- Cached license includes expiry date
- After expiry, premium features require re-validation

### Code Security
- Activation codes are cryptographically generated
- Not sequential or predictable
- Stored securely in database
- Used codes cannot be reused
- Revoked codes are rejected

## API Endpoint

### POST /api/platform-admin/activate

**No authentication required** — the activation code itself is the credential.

**Request:**
```json
{
  "activation_code": "TF-SCH-XXXX-XXXX-XXXX"
}
```

**Response (200):**
```json
{
  "school": { "id": "...", "name": "...", "school_code": "..." },
  "license": { "code": "...", "plan": "...", "expiry_date": "...", "seat_limit": 20, "features": [...] },
  "message": "Activation successful"
}
```

**Error responses:**
- 404: Invalid activation code
- 403: Code revoked or expired
- 403: License not active

## Desktop Implementation

The desktop application (`main.js`) should:
1. Check for cached license on startup
2. If no cache, show activation screen
3. On activation, call the API
4. Cache the response locally
5. Set school context for all subsequent operations
