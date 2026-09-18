# Platform Administration Architecture

## Overview

TeachFlow has THREE administrative levels:

1. **Platform Administrator** (BloomCore/TeachFlow) — manages the entire platform
2. **School Administrator** — manages one school workspace
3. **Teacher** — uses TeachFlow for lesson planning

## Role Model

### Platform Administrator
- **Role value:** `platform_admin`
- **Access:** `/platform-admin`
- **Can manage:**
  - Schools (create, edit, suspend, archive)
  - Licenses (create, activate, suspend, renew, cancel)
  - Product Plans (create, edit, deactivate)
  - Payments (verify, reject)
  - Activation Codes (generate, revoke)
  - Content Packs
  - Global Templates
  - Platform Settings
  - Audit Logs
- **Cannot:**
  - Be impersonated by school admin or teacher
  - Access school-specific data directly (must use school context)

### School Administrator
- **Role value:** `school_admin`
- **Access:** `/admin`
- **Can manage:**
  - Teachers within their school
  - School settings
  - School schemes and lesson plans
  - Licensed features for their school
- **Cannot:**
  - Manage other schools
  - Change global product pricing
  - Create platform licenses
  - Modify global payment configuration
  - Extend their own subscription
  - Grant premium features beyond the school's entitlement

### Teacher
- **Role value:** `teacher`
- **Access:** Dashboard, Upload, Lessons, Templates
- **Can:**
  - Upload schemes
  - Generate lesson plans
  - Edit and export plans
  - Use permitted templates
- **Cannot:**
  - Manage users
  - Manage payments
  - Access admin functions

## Database Schema

### Users Table
- `role` column: `platform_admin`, `school_admin`, `teacher`
- `school_id` column: references `schools.id`
- `is_admin` column: retained for backward compatibility

### Schools Table
- `id`, `name`, `school_code`, `contact_*`, `status`
- Status: `active`, `suspended`, `archived`

### School Memberships Table
- Links users to schools with role and status
- Supports future multi-school membership

### School Licenses Table
- Links schools to product plans
- Contains license code, seat limit, dates
- Status: `pending`, `active`, `expired`, `suspended`, `cancelled`

### Activation Codes Table
- Secure codes for desktop activation
- Status: `active`, `used`, `revoked`

## Authorization

### Backend Dependencies
- `require_platform_admin()` — checks `user.role == "platform_admin"`
- `require_admin()` — checks `user.is_admin` or `user.role == "school_admin"`
- `require_school_membership(school_id)` — checks school membership

### Frontend Gating
- Platform Admin link only shown when `user.role === 'platform_admin'`
- Admin link only shown when `user.is_admin`
- Non-admin redirected from `/admin` to `/dashboard`
- Non-platform-admin redirected from `/platform-admin` to `/dashboard`

## Migration Strategy

Existing `is_admin` users are migrated to the role system:
- `is_admin = 1` → `role = 'school_admin'`
- No existing user becomes `platform_admin` automatically
- Platform Admin must be created through a controlled process

## Security

- Platform Admin access is server-side enforced
- No self-assignment of platform role through client requests
- JWT tokens include user ID; role is checked from database
- Audit log tracks all platform admin actions
