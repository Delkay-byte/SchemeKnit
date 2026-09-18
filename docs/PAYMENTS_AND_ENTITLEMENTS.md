# TeachFlow Payments & Entitlements

## Overview

TeachFlow uses a **manual payment verification** system. No automatic payment gateways are used. All payments are verified by an administrator before entitlements are activated.

## Payment Methods

### MTN MoMo
- Phone: 0553976334
- Account Name: Kobla Saviour Amegayie
- Instructions: Send money to this number. Use your name as reference.

### Bank Transfer
- Bank: GCB Bank
- Account Number: 5151010019541
- Branch: Abor
- Account Name: Kobla Saviour Amegayie
- Instructions: Use your name as payment reference.

**Note:** Payment details are stored in the database and can be updated by an administrator without code changes.

## Payment Workflow

1. User selects a product/plan
2. System displays:
   - Price (GH₵)
   - Payment instructions
   - Payment methods
3. User pays externally via MTN MoMo or bank transfer
4. User clicks "I've made the payment"
5. User submits:
   - Payment method
   - Amount
   - Payer name
   - Payer phone (if applicable)
   - Transaction/reference number
   - Optional notes
6. Payment is created as **PENDING**
7. User sees: "Payment submitted — awaiting verification"
8. Admin reviews payment
9. Admin chooses: **VERIFY** or **REJECT**
10. On VERIFY: entitlement is activated
11. On REJECT: access remains locked, rejection reason shown

## Payment Statuses

| Status | Description |
|--------|-------------|
| `pending` | Submitted, awaiting admin review |
| `verified` | Confirmed by admin, entitlement activated |
| `rejected` | Declined by admin, reason provided |
| `cancelled` | Cancelled by user before review |

## Product Types

| Type | Description |
|------|-------------|
| `subscription` | Monthly/annual access to premium features |
| `content_pack` | Pre-made lesson plan bundles |
| `custom_generation` | Paid lesson plan generation service |
| `software_license` | Software license purchase |
| `template` | Custom template purchase |
| `other` | Other products |

## Entitlements

Entitlements are created **server-side only** after payment verification. The frontend cannot create entitlements directly.

### Free Tier
- 1 scheme
- 10 lesson plans per scheme
- 1 template
- No AI
- No cloud sync

### Teacher Tier (after verified payment)
- 10 schemes
- 50 lesson plans per scheme
- 5+ templates
- BASIC AI mode
- Cloud sync
- Template import
- Content library access

### School Tier (after verified payment)
- Unlimited schemes
- Unlimited lesson plans
- All templates
- ENHANCED AI mode
- Multi-teacher support
- Priority support

## Subscription Lifecycle

1. Payment verified → Subscription created (ACTIVE)
2. Subscription has start date and end date
3. Access granted while subscription is ACTIVE
4. Subscription expires → Access revoked
5. Renewal: New payment → New subscription period

## Content Pack Purchases

1. User browses content packs
2. Selects a pack → sees price
3. Makes payment → submits proof
4. Admin verifies → purchase record created
5. User can download/access the pack

## Audit Logging

Every payment status change is recorded:
- Who submitted
- Who verified/rejected
- When
- Amount
- Product
- Method
- Old status → New status
- Notes

## Security

- Users can only view their own payment records
- Only admins can verify/reject payments
- Payment details are protected
- Transaction references are not exposed unnecessarily
- No fake "payment successful" messages before verification

## Configuration

Payment instructions are stored in the database and can be updated by administrators:

```
/api/payments/admin/config (PUT)
```

This allows changing payment details without code changes.
