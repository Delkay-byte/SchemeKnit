# Individual Teacher Plan — Acceptance Criteria

## Functional Requirements

### Registration
- [x] Individual teacher can register at `/api/auth/register/individual` with email, password, full_name
- [x] Registration creates a Free Teacher entitlement automatically
- [x] Duplicate email is rejected with 409
- [x] `user.school_id` is NULL for individual teachers
- [x] `user.subscription_type` is 'free' on registration

### Entitlement Resolution
- [x] Free Teacher plan: 3 generations, no batch, no ZIP, 1 template, 10 history, 5 AI credits
- [x] Teacher Pro plan: unlimited generations, batch, ZIP, 10 templates, 100 history, 50 AI credits
- [x] School + Individual: most permissive wins for each capability
- [x] Expired entitlement falls back to free plan
- [x] `getMyPlan()` returns correct plan name, source, and limits

### Feature Gates
- [x] Generation quota enforced — returns 403 when limit exceeded
- [x] Batch generation blocked for free teachers
- [x] ZIP export blocked for free teachers
- [x] AI credits tracked and decremented
- [x] Custom template limit enforced

### Payment Flow
- [x] Individual teacher can upgrade from Free to Pro via payment service
- [x] Pro activation reads plan-specific limits from `product_plans`
- [x] `user.subscription_type` updated to 'teacher_pro'

### Platform Admin
- [x] Can list all individual teachers
- [x] Can view individual teacher details with entitlements
- [x] Can activate Pro for individual teacher

## Non-Functional Requirements

### Data Integrity
- [x] Migration `v013` is idempotent (safe to re-run)
- [x] Existing school subscriptions unaffected
- [x] Entitlement precedence is deterministic

### Security
- [x] Individual teacher endpoints require authentication
- [x] Platform admin endpoints require platform_admin role
- [x] No data leakage between users

### Testing
- [x] 40 new tests for individual teacher plan
- [x] 622 total tests passing
- [x] TypeScript compilation clean

## Test Results

```
622 passed, 2073 warnings in 148.44s
```
