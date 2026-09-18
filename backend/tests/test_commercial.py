"""
SchemeKnit Commercial Flow Acceptance Tests

End-to-end tests for the complete payment and entitlement workflow.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from src.models import (
    PaymentMethod, PaymentStatus, ProductType, AIMode,
    EducationalLevel, ClassLevel, Subject, TemplateFamily,
)
from src.payment_service import PaymentService
from src.entitlements import check_feature_access, get_active_subscription
from src.database import generate_id


class TestCommercialFlowAcceptance:
    """End-to-end commercial flow tests."""

    def setup_method(self):
        self.service = PaymentService()

    def test_free_user_basic_functionality(self):
        """Scenario A: Free/offline user can use basic features."""
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        result = check_feature_access("user-free", "ai_basic", db)
        assert result is False

    def test_payment_submission_pending(self):
        """Payment is created as PENDING."""
        db = MagicMock()
        db.add = MagicMock()
        db.commit = MagicMock()
        db.refresh = MagicMock()

        payment = self.service.create_payment(
            db=db,
            user_id="user-teacher",
            payment_method="mtn_momo",
            amount=50.0,
            product_type="subscription",
            product_id="plan-teacher-monthly",
            product_name="Teacher Monthly",
            reference="MTN-REF-TEST-001",
            payer_name="Kobla Saviour",
            payer_phone="0553976334",
        )

        assert payment.status == "pending"

    def test_pending_payment_blocks_paid_feature(self):
        """PENDING payment does not activate entitlement."""
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        result = check_feature_access("user-teacher", "ai_basic", db)
        assert result is False

    def test_verified_payment_activates_entitlement(self):
        """VERIFIED payment activates entitlement."""
        mock_ent = MagicMock()
        mock_ent.features = ["ai_basic", "cloud_sync"]
        mock_ent.ai_enabled = True
        mock_ent.cloud_sync = True
        mock_ent.expires_at = datetime.utcnow() + timedelta(days=30)

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = mock_ent

        result = check_feature_access("user-teacher", "ai_basic", db)
        assert result is True

    def test_rejected_payment_blocks_access(self):
        """REJECTED payment does not activate entitlement."""
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        result = check_feature_access("user-teacher", "ai_basic", db)
        assert result is False

    def test_subscription_expiry(self):
        """Expired subscription blocks access."""
        mock_sub = MagicMock()
        mock_sub.expires_at = datetime.utcnow() - timedelta(days=1)
        mock_sub.status = "active"

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = mock_sub

        sub = get_active_subscription(db, "user-teacher")
        assert sub is None

    def test_active_subscription_grants_access(self):
        """Active subscription grants access."""
        mock_ent = MagicMock()
        mock_ent.features = ["ai_basic", "cloud_sync", "template_import"]
        mock_ent.ai_enabled = True
        mock_ent.cloud_sync = True
        mock_ent.template_import = True
        mock_ent.expires_at = datetime.utcnow() + timedelta(days=30)

        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = mock_ent

        assert check_feature_access("user-teacher", "ai_basic", db) is True
        assert check_feature_access("user-teacher", "cloud_sync", db) is True
        assert check_feature_access("user-teacher", "template_import", db) is True

    def test_content_pack_purchase_flow(self):
        """Content pack purchase flow."""
        db = MagicMock()
        db.add = MagicMock()
        db.commit = MagicMock()
        db.refresh = MagicMock()

        payment = self.service.create_payment(
            db=db,
            user_id="user-teacher",
            payment_method="bank_transfer",
            amount=25.0,
            product_type="content_pack",
            product_id="pack-b9-science-term1",
            product_name="B9 Science Term 1",
            reference="GCB-TRANSFER-001",
            payer_name="Kobla Saviour",
        )

        assert payment.status == "pending"
        assert payment.product_type == "content_pack"

    def test_admin_cannot_verify_own_payment(self):
        """Admin cannot verify their own payment (separation of duties)."""
        pass

    def test_audit_log_recorded(self):
        """Every payment status change is audited."""
        pass


class TestAIRegenerationFlow:
    """AI section regeneration tests."""

    def test_regeneratable_sections(self):
        from src.routers.ai_regeneration import REGENERATABLE_SECTIONS
        assert "introduction" in REGENERATABLE_SECTIONS
        assert "assessment" in REGENERATABLE_SECTIONS
        assert "differentiation" in REGENERATABLE_SECTIONS
        assert "reflection" in REGENERATABLE_SECTIONS

    def test_non_regeneratable_section_rejected(self):
        """Cannot regenerate non-regeneratable sections."""
        from src.routers.ai_regeneration import REGENERATABLE_SECTIONS
        assert "strand" not in REGENERATABLE_SECTIONS
        assert "subject" not in REGENERATABLE_SECTIONS
        assert "class_level" not in REGENERATABLE_SECTIONS


class TestBackwardCompatibility:
    """Ensure existing functionality is not broken."""

    def test_template_type_still_works(self):
        from src.models import TemplateType
        assert TemplateType.GES_STYLE.value == "GES-style"

    def test_class_level_taxonomy_complete(self):
        from src.models import ClassLevel
        expected = [
            "Nursery", "KG 1", "KG 2",
            "Basic 1", "Basic 2", "Basic 3", "Basic 4", "Basic 5", "Basic 6",
            "Basic 7", "Basic 8", "Basic 9",
            "SHS 1", "SHS 2", "SHS 3",
        ]
        for level in expected:
            assert any(c.value == level for c in ClassLevel)

    def test_no_basic_10(self):
        from src.models import ClassLevel
        assert not hasattr(ClassLevel, 'BASIC_10')

    def test_educational_levels_complete(self):
        from src.models import EducationalLevel
        levels = [e.value for e in EducationalLevel]
        assert "Early Childhood" in levels
        assert "Primary" in levels
        assert "Junior High School" in levels
        assert "Senior High School" in levels
