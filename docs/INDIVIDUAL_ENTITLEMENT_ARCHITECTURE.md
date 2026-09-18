# Individual Teacher Entitlement Architecture

## Data Model

### Tables

#### `users`
- `subscription_type` — NULL (school teacher), 'free', 'teacher_pro', 'school'

#### `product_plans`
- `customer_type` — 'school' or 'individual_teacher'
- `plan_identifier` — 'SCHOOL_PRO', 'FREE_TEACHER', 'TEACHER_PRO'
- `generation_limit`, `batch_generation`, `zip_export`, `pdf_export`
- `custom_template_limit`, `history_limit`, `ai_enabled`, `ai_credits`
- `max_generations_per_period`, `max_custom_templates`, `max_history_entries`

#### `entitlements`
- `user_id` — Owner (school or individual)
- `school_id` — NULL for individual, set for school-owned
- `subscription_type` — 'school', 'free', 'teacher_pro'
- `product_plan_id` — References `product_plans`
- `generation_limit`, `generations_used`, `batch_generation`, `zip_export`, `pdf_export`
- `custom_template_limit`, `history_limit`, `ai_credits`, `ai_credits_used`
- `expires_at`, `is_active`

## Entitlement Resolution

`resolve_entitlement(user_id)` returns a `PlanResolution`:

1. Fetch the user's `subscription_type`
2. If school-owned: find active school entitlement
3. If individual: find active individual entitlement
4. If both: merge using `max()` per capability
5. If none: return FREE defaults

## Feature Gates

| Gate | Function | Behavior |
|---|---|---|
| Generation limit | `can_generate()` | Checks `generations_used < generation_limit` |
| Batch generation | `can_generate_batch()` | Returns `batch_generation` flag |
| ZIP export | `can_export_zip()` | Returns `zip_export` flag |
| AI usage | `can_use_ai()` | Checks `ai_credits_used < ai_credits` |
| Custom template | `can_create_custom_template()` | Checks `custom_templates_used < custom_template_limit` |
| Generation count | `increment_generation_count()` | Atomically increments `generations_used` |
| AI credits | `increment_ai_credits()` | Atomically increments `ai_credits_used` |

## Migration

`v013_individual_teacher_plan.py` adds:
- `users.subscription_type` column
- `product_plans` columns for limits and customer type
- `entitlements` columns for usage tracking
- Seeds FREE_TEACHER and TEACHER_PRO product plans

## Frontend Components

| Component | File | Purpose |
|---|---|---|
| `PlanComparisonCard` | `components/plan-comparison-card.tsx` | Free vs Pro comparison on login |
| Account Card | `app/dashboard/page.tsx` | Shows plan status on dashboard |
| Upgrade Page | `app/upgrade/page.tsx` | Upgrade flow for individual teachers |

## Tests

- `test_individual_teacher_plan.py` — 40 tests covering registration, free plan, pro plan, expiry, precedence, payment, AI, platform admin
- `test_export_download.py` — Updated with `_grant_pro_entitlement()` helper
- 622 total tests passing
