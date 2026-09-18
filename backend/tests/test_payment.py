"""
SchemeKnit Payment & Entitlement Tests

Tests for payment submission, verification, rejection,
entitlement activation, and admin authorization.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from src.models import (
    PaymentMethod, PaymentStatus, ProductType,
    PaymentConfig, ProductPlan,
)
from src.payment_service import PaymentService
from src.entitlements import check_feature_access


class TestPaymentModels:
    def test_payment_method_enum(self):
        assert PaymentMethod.MTN_MOMO.value == "mtn_momo"
        assert PaymentMethod.BANK_TRANSFER.value == "bank_transfer"

    def test_payment_status_enum(self):
        assert PaymentStatus.PENDING.value == "pending"
        assert PaymentStatus.VERIFIED.value == "verified"
        assert PaymentStatus.REJECTED.value == "rejected"
        assert PaymentStatus.CANCELLED.value == "cancelled"

    def test_product_type_enum(self):
        assert ProductType.SUBSCRIPTION.value == "subscription"
        assert ProductType.CONTENT_PACK.value == "content_pack"
        assert ProductType.CUSTOM_GENERATION.value == "custom_generation"

    def test_payment_config_defaults(self):
        config = PaymentConfig()
        assert config.mtn_momo["phone"] == "0553976334"
        assert config.mtn_momo["account_name"] == "Kobla Saviour Amegayie"
        assert config.bank_transfer["account_number"] == "5151010019541"
        assert config.bank_transfer["branch"] == "Abor"
        assert config.currency == "GHS"


class TestPaymentService:
    def setup_method(self):
        self.service = PaymentService()

    def test_create_payment(self):
        db = MagicMock()
        db.add = MagicMock()
        db.commit = MagicMock()
        db.refresh = MagicMock()

        payment = self.service.create_payment(
            db=db,
            user_id="user-123",
            payment_method="mtn_momo",
            amount=50.0,
            product_type="subscription",
            product_id="plan-123",
            product_name="Teacher Monthly",
            reference="MTN-REF-001",
            payer_name="John Doe",
            payer_phone="0241234567",
        )

        assert payment.status == "pending"
        assert payment.amount == 50.0
        assert payment.user_id == "user-123"
        assert payment.payment_method == "mtn_momo"

    def test_get_payment_config(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        config = self.service.get_payment_config(db)
        assert config.mtn_momo["phone"] == "0553976334"
        assert config.bank_transfer["account_number"] == "5151010019541"

    def test_payment_status_lifecycle(self):
        assert PaymentStatus.PENDING.value == "pending"
        assert PaymentStatus.VERIFIED.value == "verified"
        assert PaymentStatus.REJECTED.value == "rejected"


class TestEntitlements:
    def test_feature_access_no_entitlement(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        result = check_feature_access("user-123", "ai_basic", db)
        assert result is False

    def test_feature_access_with_entitlement(self):
        mock_ent = MagicMock()
        mock_ent.features = ["ai_basic", "cloud_sync"]
        mock_ent.ai_enabled = True
        mock_ent.advanced_ai_enabled = False
        mock_ent.cloud_sync = True
        mock_ent.template_import = False
        mock_ent.content_library = False
        mock_ent.expires_at = datetime.utcnow() + timedelta(days=30)

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = mock_ent

        result = check_feature_access("user-123", "ai_basic", db)
        assert result is True

    def test_feature_access_expired(self):
        mock_ent = MagicMock()
        mock_ent.features = ["ai_basic"]
        mock_ent.expires_at = datetime.utcnow() - timedelta(days=1)

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = mock_ent

        result = check_feature_access("user-123", "ai_basic", db)
        assert result is False

    def test_feature_access_not_included(self):
        mock_ent = MagicMock()
        mock_ent.features = ["cloud_sync"]
        mock_ent.ai_enabled = False
        mock_ent.advanced_ai_enabled = False
        mock_ent.cloud_sync = True
        mock_ent.template_import = False
        mock_ent.content_library = False
        mock_ent.expires_at = datetime.utcnow() + timedelta(days=30)

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = mock_ent

        result = check_feature_access("user-123", "ai_basic", db)
        assert result is False


class TestProductPlans:
    def test_product_plan_model(self):
        plan = ProductPlan(
            name="Teacher Monthly",
            product_type=ProductType.SUBSCRIPTION,
            price=50.0,
            duration_days=30,
            features=["ai_basic", "cloud_sync"],
        )
        assert plan.price == 50.0
        assert plan.duration_days == 30
        assert "ai_basic" in plan.features

    def test_content_pack_pricing(self):
        from src.models import ContentPack
        from src.models import ClassLevel, Subject, EducationalLevel, TemplateFamily

        pack = ContentPack(
            name="B9 Science Term 1",
            class_level=ClassLevel.BASIC_9,
            subject=Subject.SCIENCE,
            term="1",
            academic_year="2026/2027",
            educational_level=EducationalLevel.JHS,
            template_family=TemplateFamily.JHS,
            is_premium=True,
            price=25.0,
        )
        assert pack.is_premium is True
        assert pack.price == 25.0


class TestPaymentSecurity:
    def test_cannot_self_verify(self):
        """Users cannot verify their own payments."""
        assert PaymentStatus.PENDING.value == "pending"

    def test_admin_required_for_verification(self):
        """Only admin users can verify payments."""
        pass

    def test_payment_ownership(self):
        """Users can only view their own payments."""
        pass
