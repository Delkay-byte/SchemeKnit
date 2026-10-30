# TeachFlow Commercial Model

## Business Structure

### BloomCore Technologies (Platform Owner)
- Owns and operates TeachFlow platform
- Manages all commercial relationships
- Controls pricing, licensing, and payments
- Maintains the central licensing service

### Schools (Licensees)
- Receive license/subscription to use TeachFlow
- Do NOT own the software
- School Administrator manages local workspace
- Teachers use the platform for lesson planning

## Revenue Streams

### 1. Individual Teacher Packages
Primary customer-facing revenue source. All packages are one-time prepaid
purchases; there is no automatic renewal.

| Package | Price (GH₵) | Lesson-plan credits | Validity |
|---------|------------|---------------------|----------|
| Free | 0 | 2 per calendar month | Monthly reset |
| Flexible Credit Pack | 12 | 20 | Credits do not expire |
| Teacher Monthly | 22 | 40 | 30 days |
| Teacher Term Pass | 50 | 160 | 120 days |
| Academic Year Pass | 120 | 480 | 365 days |

One credit = one successfully generated, independently teachable,
indicator-level lesson plan. School package pricing remains unapproved and the
legacy school catalogue row is inactive for new purchases.

### 2. Content Packs
Additional curriculum content available for purchase.

### 3. Custom Generation Service
Bespoke lesson plan generation for schools with specific requirements.

### 4. Premium Templates
Advanced template designs and formatting options.

## Payment Methods

Payments are processed online by Paystack. Only two customer-facing methods are
offered:

1. **Bank Transfer** — Paystack Ghana Pay with Transfer, returning a temporary
   account and expiry.
2. **Mobile Money** — MTN, Telecel or AirtelTigo, authorised on the customer's
   phone.

Card checkout is not offered. Both methods are one-time prepaid payments; no
automatic renewal or recurring charge is initiated. A package activates only
after Paystack confirms the payment and TeachFlow verifies it.

All transactions are in GH₵ (Ghana Cedis).

## Licensing Model

### Free Offline Core
- Basic lesson plan generation
- No subscription required
- No internet required
- Limited to 1 teacher, 5 schemes, 50 lessons per scheme

### Licensed Premium Features
- Multi-teacher support
- Admin dashboard
- Premium templates
- Advanced AI generation
- Content library access
- Cloud sync
- Template import

## Entitlement System

Each license defines entitlements:
- `seat_limit` — maximum teacher accounts
- `features` — list of enabled features
- `expiry_date` — license validity period
- `plan_name` — product tier name

## Data Model

### Product Plans
Configurable plans with:
- Name, description, price
- Duration, seat limit
- Feature entitlements
- Active/inactive status

### School Licenses
Links schools to plans:
- License code (unique, secure)
- Status (pending/active/expired/suspended/cancelled)
- Start and expiry dates
- Seat limit

### Activation Codes
Secure codes for desktop activation:
- Format: `TF-SCH-XXXX-XXXX-XXXX`
- One-time use
- Can be revoked before use

### Payments
Manual payment records:
- Payment method (MTN MoMo / Bank Transfer)
- Amount and currency (GHS)
- Product type and name
- Reference and payer info
- Status (pending/verified/rejected)
- Audit trail

## School Data Isolation

Each school's data is isolated:
- Schemes belong to school users
- Lesson plans belong to school users
- Teachers are linked to schools
- No cross-school data access

Enforced at the backend level, not just frontend filtering.

## Platform Administration

Platform Admin manages:
- Schools (CRUD)
- Licenses (CRUD)
- Product Plans (CRUD)
- Payments (verify/reject)
- Activation Codes (generate/revoke)
- Content Packs
- Audit Logs

School Admin manages:
- Teachers within their school
- School settings
- School schemes and lesson plans

Teacher uses:
- Upload, review, generate, edit, export

## Migration from Existing System

Existing `is_admin` users:
- Migrated to `role = 'school_admin'`
- No automatic platform admin assignment
- Platform Admin created through controlled process
- Backward compatible with existing workflows
