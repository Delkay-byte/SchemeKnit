# Individual Teacher Plan — User Guide

## Overview

TeachFlow now supports two commercial models:

1. **School Subscription** — A school administrator purchases a plan for their institution. Teachers inherit features from the school's subscription.
2. **Individual Teacher Plan** — A teacher can register independently and subscribe to a plan directly.

When a teacher has both a school subscription and an individual plan, TeachFlow applies the **most permissive** capabilities from each source.

## Plans

### Free Teacher

| Feature | Limit |
|---|---|
| Account | Yes |
| Upload scheme | Yes |
| Review curriculum | Yes |
| Configure lessons | Yes |
| Individual lesson generation | 3 total |
| Full batch generation | No |
| Individual DOCX download | Yes |
| Full batch / ZIP download | No |
| PDF export | Yes |
| Custom templates | 1 saved |
| Approved GES templates | Yes |
| AI assistance | 5 trial credits |
| Lesson history | 10 lessons |

### Teacher Pro

| Feature | Limit |
|---|---|
| All Free features | Unlimited |
| Full batch generation | Yes |
| Full batch / ZIP download | Yes |
| Custom templates | 10 saved |
| AI assistance | 50 credits |
| Lesson history | 100 lessons |
| Advanced analytics | Yes |

## Registration

### Individual Teacher Registration

1. Go to `/login` and click **Register as individual teacher** (or navigate directly)
2. Enter your email, full name, and password
3. You'll receive a Free Teacher account with the limits above

### School Teacher Registration

School teachers are created by the school administrator. They inherit the school's subscription automatically.

## Upgrading

To upgrade from Free to Teacher Pro:

1. Click **Upgrade to Pro** on your dashboard
2. Follow the instructions to contact your school administrator or subscribe individually

## Entitlement Precedence

If you belong to a school AND have an individual plan, TeachFlow applies the most permissive capability from each source for every feature. For example:

- School allows 10 generations, Individual allows 5 → You get 10
- Individual allows ZIP export, School does not → You can export ZIP

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/auth/register/individual` | POST | Register as an individual teacher |
| `/api/auth/my-plan` | GET | Get your resolved plan and entitlements |

## Platform Admin Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/platform-admin/individual-teachers` | GET | List all individual teachers |
| `/api/platform-admin/individual-teachers/{id}` | GET | Get individual teacher details |
| `/api/platform-admin/individual-teachers/activate` | POST | Activate Pro for an individual teacher |
