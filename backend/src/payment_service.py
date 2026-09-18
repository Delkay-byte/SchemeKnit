"""
SchemeKnit Payment Service

Handles payment submission, verification, rejection,
entitlement activation, and audit logging.
"""

from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import and_

from .database import (
    PaymentDB, PaymentAuditLogDB, ProductPlanDB, PaymentConfigDB,
    User, generate_id
)
from .models import (
    Payment, PaymentStatus, PaymentMethod, ProductType,
    PaymentAuditLog, ProductPlan, PaymentConfig,
    Entitlement, Subscription, ContentPackPurchase,
)


class PaymentService:
    """Payment processing with manual verification workflow."""

    def create_payment(
        self, db: Session, user_id: str,
        payment_method: str, amount: float,
        product_type: str, product_id: str,
        product_name: str = "", reference: str = "",
        payer_name: str = "", payer_phone: str = "",
        notes: str = "", proof_path: Optional[str] = None,
    ) -> PaymentDB:
        payment = PaymentDB(
            id=generate_id(),
            user_id=user_id,
            payment_method=payment_method,
            amount=amount,
            currency="GHS",
            product_type=product_type,
            product_id=product_id,
            product_name=product_name,
            reference=reference,
            payer_name=payer_name,
            payer_phone=payer_phone,
            proof_path=proof_path,
            notes=notes,
            status=PaymentStatus.PENDING.value,
            submitted_at=datetime.utcnow(),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(payment)
        db.commit()
        db.refresh(payment)

        self._log_audit(db, payment, "submitted", None, PaymentStatus.PENDING, user_id)
        return payment

    def get_payment(self, db: Session, payment_id: str, user_id: Optional[str] = None) -> Optional[PaymentDB]:
        q = db.query(PaymentDB).filter(PaymentDB.id == payment_id)
        if user_id:
            q = q.filter(PaymentDB.user_id == user_id)
        return q.first()

    def get_user_payments(self, db: Session, user_id: str) -> List[PaymentDB]:
        return db.query(PaymentDB).filter(
            PaymentDB.user_id == user_id
        ).order_by(PaymentDB.created_at.desc()).all()

    def get_pending_payments(self, db: Session) -> List[PaymentDB]:
        return db.query(PaymentDB).filter(
            PaymentDB.status == PaymentStatus.PENDING.value
        ).order_by(PaymentDB.submitted_at.asc()).all()

    def get_all_payments(self, db: Session, status: Optional[str] = None) -> List[PaymentDB]:
        q = db.query(PaymentDB)
        if status:
            q = q.filter(PaymentDB.status == status)
        return q.order_by(PaymentDB.created_at.desc()).all()

    def verify_payment(
        self, db: Session, payment_id: str,
        admin_user_id: str, notes: str = "",
    ) -> PaymentDB:
        payment = db.query(PaymentDB).filter(PaymentDB.id == payment_id).first()
        if not payment:
            raise ValueError("Payment not found")
        if payment.status != PaymentStatus.PENDING.value:
            raise ValueError(f"Payment is {payment.status}, not pending")

        old_status = payment.status
        payment.status = PaymentStatus.VERIFIED.value
        payment.reviewed_at = datetime.utcnow()
        payment.reviewed_by = admin_user_id
        payment.notes = notes or payment.notes
        payment.updated_at = datetime.utcnow()
        db.commit()

        self._log_audit(db, payment, "verified", old_status, PaymentStatus.VERIFIED, admin_user_id, notes)
        self._activate_entitlement(db, payment)
        return payment

    def reject_payment(
        self, db: Session, payment_id: str,
        admin_user_id: str, reason: str,
    ) -> PaymentDB:
        payment = db.query(PaymentDB).filter(PaymentDB.id == payment_id).first()
        if not payment:
            raise ValueError("Payment not found")
        if payment.status != PaymentStatus.PENDING.value:
            raise ValueError(f"Payment is {payment.status}, not pending")

        old_status = payment.status
        payment.status = PaymentStatus.REJECTED.value
        payment.reviewed_at = datetime.utcnow()
        payment.reviewed_by = admin_user_id
        payment.rejection_reason = reason
        payment.updated_at = datetime.utcnow()
        db.commit()

        self._log_audit(db, payment, "rejected", old_status, PaymentStatus.REJECTED, admin_user_id, reason)
        return payment

    def cancel_payment(
        self, db: Session, payment_id: str,
        user_id: str,
    ) -> PaymentDB:
        payment = db.query(PaymentDB).filter(
            PaymentDB.id == payment_id,
            PaymentDB.user_id == user_id,
        ).first()
        if not payment:
            raise ValueError("Payment not found")
        if payment.status != PaymentStatus.PENDING.value:
            raise ValueError("Only pending payments can be cancelled")

        old_status = payment.status
        payment.status = PaymentStatus.CANCELLED.value
        payment.updated_at = datetime.utcnow()
        db.commit()

        self._log_audit(db, payment, "cancelled", old_status, PaymentStatus.CANCELLED, user_id)
        return payment

    def get_payment_config(self, db: Session) -> PaymentConfig:
        cfg = db.query(PaymentConfigDB).filter(
            PaymentConfigDB.config_key == "payment_instructions"
        ).first()
        if cfg:
            return PaymentConfig(**cfg.config_value)
        return PaymentConfig()

    def update_payment_config(self, db: Session, config: PaymentConfig) -> PaymentConfig:
        cfg = db.query(PaymentConfigDB).filter(
            PaymentConfigDB.config_key == "payment_instructions"
        ).first()
        if cfg:
            cfg.config_value = config.model_dump()
            cfg.updated_at = datetime.utcnow()
        else:
            cfg = PaymentConfigDB(
                id=generate_id(),
                config_key="payment_instructions",
                config_value=config.model_dump(),
                updated_at=datetime.utcnow(),
            )
            db.add(cfg)
        db.commit()
        return config

    def get_product_plans(self, db: Session, active_only: bool = True) -> List[ProductPlanDB]:
        q = db.query(ProductPlanDB)
        if active_only:
            q = q.filter(ProductPlanDB.active == True)
        return q.order_by(ProductPlanDB.product_type, ProductPlanDB.price).all()

    def get_product_plan(self, db: Session, plan_id: str) -> Optional[ProductPlanDB]:
        return db.query(ProductPlanDB).filter(ProductPlanDB.id == plan_id).first()

    def create_product_plan(self, db: Session, plan: ProductPlan) -> ProductPlanDB:
        db_plan = ProductPlanDB(
            id=plan.id,
            name=plan.name,
            description=plan.description,
            product_type=plan.product_type.value,
            price=plan.price,
            currency=plan.currency,
            duration_days=plan.duration_days,
            features=plan.features,
            educational_levels=plan.educational_levels,
            template_access=plan.template_access,
            ai_access=plan.ai_access,
            content_access=plan.content_access,
            active=plan.active,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(db_plan)
        db.commit()
        db.refresh(db_plan)
        return db_plan

    def _activate_entitlement(self, db: Session, payment: PaymentDB):
        from .database import EntitlementDB, SubscriptionDB, ContentPackPurchaseDB, ProductPlanDB

        if payment.product_type == ProductType.SUBSCRIPTION.value:
            sub = db.query(SubscriptionDB).filter(
                SubscriptionDB.user_id == payment.user_id,
                SubscriptionDB.status == "active",
            ).first()

            now = datetime.utcnow()
            duration_days = 30
            plan = self.get_product_plan(db, payment.product_id)
            if plan and plan.duration_days:
                duration_days = plan.duration_days

            # Determine if this is an individual teacher plan
            is_individual = False
            if plan and hasattr(plan, 'customer_type'):
                is_individual = plan.customer_type == "individual_teacher"

            if sub:
                if sub.expires_at and sub.expires_at > now:
                    sub.expires_at = sub.expires_at + timedelta(days=duration_days)
                else:
                    sub.expires_at = now + timedelta(days=duration_days)
                sub.status = "active"
            else:
                sub = SubscriptionDB(
                    id=generate_id(),
                    user_id=payment.user_id,
                    edition="teacher",
                    plan_name=payment.product_name or "Teacher Plan",
                    status="active",
                    started_at=now,
                    expires_at=now + timedelta(days=duration_days),
                    payment_provider="manual",
                    external_id=payment.id,
                )
                db.add(sub)

            ent = db.query(EntitlementDB).filter(
                EntitlementDB.user_id == payment.user_id,
            ).first()

            # Read plan-specific limits from the product plan
            gen_limit = getattr(plan, 'generation_limit', 0) if plan else 0
            batch_gen = getattr(plan, 'batch_generation', False) if plan else False
            zip_exp = getattr(plan, 'zip_export', False) if plan else False
            pdf_exp = getattr(plan, 'pdf_export', True) if plan else True
            tpl_limit = getattr(plan, 'custom_template_limit', 10) if plan else 10
            hist_limit = getattr(plan, 'history_limit', 100) if plan else 100
            ai_enabled = getattr(plan, 'ai_enabled', True) if plan else True
            ai_credits = getattr(plan, 'ai_credits', 50) if plan else 50

            if ent:
                ent.edition = "teacher"
                ent.subscription_type = "individual" if is_individual else "school"
                ent.ai_enabled = ai_enabled
                ent.cloud_sync = True
                ent.template_import = True
                ent.content_library = True
                ent.generation_limit = gen_limit
                ent.batch_generation = batch_gen
                ent.zip_export = zip_exp
                ent.pdf_export = pdf_exp
                ent.custom_template_limit = tpl_limit
                ent.history_limit = hist_limit
                ent.ai_credits = ai_credits
                ent.expires_at = now + timedelta(days=duration_days)
                ent.updated_at = now
            else:
                ent = EntitlementDB(
                    id=generate_id(),
                    user_id=payment.user_id,
                    edition="teacher",
                    subscription_type="individual" if is_individual else "school",
                    features=["ai_basic", "cloud_sync", "template_import", "content_library"],
                    max_schemes=10,
                    max_lessons_per_scheme=50,
                    max_templates=tpl_limit,
                    ai_enabled=ai_enabled,
                    advanced_ai_enabled=False,
                    cloud_sync=True,
                    template_import=True,
                    content_library=True,
                    generation_limit=gen_limit,
                    generations_used=0,
                    batch_generation=batch_gen,
                    zip_export=zip_exp,
                    pdf_export=pdf_exp,
                    custom_template_limit=tpl_limit,
                    history_limit=hist_limit,
                    ai_credits=ai_credits,
                    ai_credits_used=0,
                    expires_at=now + timedelta(days=duration_days),
                    created_at=now,
                    updated_at=now,
                )
                db.add(ent)

            # Update user subscription_type if individual
            if is_individual:
                from .database import User
                user = db.query(User).filter(User.id == payment.user_id).first()
                if user:
                    user.subscription_type = "individual"

        elif payment.product_type == ProductType.CONTENT_PACK.value:
            purchase = ContentPackPurchaseDB(
                id=generate_id(),
                user_id=payment.user_id,
                pack_id=payment.product_id,
                version="1.0",
                purchased_at=datetime.utcnow(),
                download_count=0,
            )
            db.add(purchase)

        db.commit()

    def _log_audit(
        self, db: Session, payment: PaymentDB,
        action: str, old_status: Optional[str],
        new_status: PaymentStatus, performed_by: str,
        notes: str = "",
    ):
        log = PaymentAuditLogDB(
            id=generate_id(),
            payment_id=payment.id,
            user_id=payment.user_id,
            action=action,
            old_status=old_status,
            new_status=new_status.value,
            amount=payment.amount,
            currency=payment.currency,
            product_type=payment.product_type,
            product_id=payment.product_id,
            payment_method=payment.payment_method,
            performed_by=performed_by,
            notes=notes,
            timestamp=datetime.utcnow(),
        )
        db.add(log)
        db.commit()

    def get_audit_logs(self, db: Session, payment_id: Optional[str] = None) -> List[PaymentAuditLogDB]:
        q = db.query(PaymentAuditLogDB)
        if payment_id:
            q = q.filter(PaymentAuditLogDB.payment_id == payment_id)
        return q.order_by(PaymentAuditLogDB.timestamp.desc()).all()

    def get_revenue_stats(self, db: Session) -> dict:
        verified = db.query(PaymentDB).filter(
            PaymentDB.status == PaymentStatus.VERIFIED.value
        ).all()
        total = sum(p.amount for p in verified)
        by_type = {}
        for p in verified:
            by_type[p.product_type] = by_type.get(p.product_type, 0) + p.amount
        return {
            "total_verified_revenue": total,
            "revenue_by_product_type": by_type,
            "total_verified_payments": len(verified),
        }


payment_service = PaymentService()
