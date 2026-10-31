"""Public website identity, contact, legal pages and purchase-entry checks."""
from __future__ import annotations

from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
SRC = FRONTEND / "src"
APP = SRC / "app"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def test_contact_configuration_is_single_source_and_verified():
    contact = _text(SRC / "lib" / "contact.ts")
    assert "bloomcoretechnologies@gmail.com" in contact
    assert "0240064668" in contact and "0553976334" in contact
    assert "+233240064668" in contact and "+233553976334" in contact
    assert "233240064668" in contact
    assert "BloomCore Technologies" in contact
    assert "L7 Olive St., Akast Road, Akatsi, Volta Region, Ghana." in contact
    assert "BUSINESS_ADDRESS" in contact
    assert "contactTelUrl" in contact and "contactTelUrl2" in contact
    # WhatsApp is built only from the primary number.
    assert "https://wa.me/${WHATSAPP_NUMBER}" in contact


def test_no_old_or_invented_mailboxes_remain():
    for path in SRC.rglob("*.tsx"):
        text = _text(path)
        for old in (
            "support@schemeknit.com", "billing@schemeknit.com",
            "privacy@schemeknit.com", "security@schemeknit.com",
        ):
            assert old not in text, f"{old} still in {path}"


def test_contact_page_uses_call_links_and_whatsapp_only_for_primary():
    page = _text(APP / "contact" / "page.tsx")
    assert "contactTelUrl" in page and "contactTelUrl2" in page
    assert "whatsappUrl" in page
    assert page.count("data-whatsapp-link") == 1
    assert "not registered for WhatsApp" in page
    for subject in (
        "Billing and Payment Support", "Privacy and Data Request", "Security Report",
    ):
        assert subject in page


def test_pricing_modal_preserves_selected_package_and_invite_notice():
    page = _text(APP / "pricing" / "page.tsx")
    assert "Almost there! Your package is waiting." in page
    assert "Create a free teacher account" in page
    assert "I already have an account — Sign in" in page
    assert "authHref('/signup', selectedNext)" in page
    assert "authHref('/login', selectedNext)" in page
    assert "pilot invitation code" in page
    assert "DialogContent" in page and "DialogTitle" in page
    assert "selectedPlan.name" in page
    assert "selectedPlan.credits" in page
    assert "selectedPlan.validity_label" in page


def test_purchase_return_helper_rejects_external_and_unknown_destinations():
    helper = _text(SRC / "lib" / "purchase-return.ts")
    assert "APPROVED_PAID_PACKAGE_SLUGS" in helper
    assert "'flexible-credit-pack'" in helper
    assert "startsWith('//')" in helper
    assert "includes('\\\\')" in helper
    assert "pathname !== '/upgrade'" in helper
    assert "slugs.length !== 1" in helper
    assert "authHref" in helper and "currentNextPath" in helper


def test_login_and_signup_honour_validated_next_destination():
    login = _text(SRC / "components" / "role-login.tsx")
    signup = _text(APP / "signup" / "page.tsx")
    layout = _text(APP / "(app)" / "layout.tsx")
    upgrade = _text(APP / "(app)" / "upgrade" / "page.tsx")
    assert "currentNextPath()" in login
    assert "entry === 'teacher' && user.role === 'teacher'" in login
    assert "authHref('/signup', nextPath)" in login
    assert "currentNextPath() || '/dashboard'" in signup
    assert "authHref('/login', nextPath)" in signup
    assert "startsWith('/upgrade')" in layout
    assert "router.push(`/login?next=" in layout
    assert "`/login?next=${encodeURIComponent(target)}`" in upgrade
    assert "The selected package is no longer available" in upgrade


def test_footer_has_verified_registered_business_panel_and_no_tin():
    footer = _text(SRC / "components" / "public-footer.tsx")
    for value in (
        "BloomCore Technologies", "BUSINESS_REGISTRATION_NUMBER",
        "BUSINESS_REGISTRATION_DATE",
        "Registration of Business Names Act, 1962 (No. 151)",
        "Office of the Registrar of Companies, Republic of Ghana",
        "Operated by {BUSINESS_NAME}, Ghana.",
    ):
        assert value in footer
    assert "P0066415551" not in footer
    assert "Ltd" not in footer and "Limited" not in footer
    assert "privacy-policy" in footer and "cookie-policy" in footer
    assert "contactTelUrl" in footer and "contactTelUrl2" in footer
    assert "BUSINESS_ADDRESS" in footer


def test_tin_and_old_corporate_form_do_not_appear_in_public_source():
    for path in (SRC.rglob("*.tsx")):
        text = _text(path)
        assert "P0066415551" not in text, path
        assert "BloomCore Technologies Ltd" not in text, path
        assert "BloomCore Technologies Limited" not in text, path


def test_cookie_policy_exists_and_describes_actual_storage():
    page = _text(APP / "cookie-policy" / "page.tsx")
    assert "path: '/cookie-policy'" in page
    assert "sessionStorage" in page
    assert "localStorage" in page
    assert "service-worker" in page.lower()
    assert "does not set first-party browser" in page
    assert "does not currently run advertising pixels" in page
    assert "Paystack" in page and "WhatsApp" in page
    sitemap = _text(APP / "sitemap.ts")
    assert "'/cookie-policy'" in sitemap


def test_legal_pages_reference_verified_identity_and_contact():
    for relative in (
        "privacy-policy/page.tsx", "terms/page.tsx",
        "refunds-cancellation/page.tsx", "data-retention/page.tsx",
        "license-subscription/page.tsx", "cookie-policy/page.tsx",
    ):
        page = _text(APP / relative)
        assert "BloomCore" in page or "BUSINESS_NAME" in page, relative
        assert "P0066415551" not in page, relative


def test_privacy_policy_reflects_actual_processing_and_rights():
    page = _text(APP / "privacy-policy" / "page.tsx")
    assert "Act 843" in page
    assert "Data Protection Commission" in page
    assert "does not claim that DPC registration has been completed" in page
    assert "not a student records" in page
    assert "DeepSeek and Groq" in page
    assert "Cloudflare R2" in page
    assert "Paystack" in page
    assert "Resend" in page
    assert "backup copies may take time" in page


def test_refund_policy_uses_act_772_without_blanket_waiver():
    page = _text(APP / "refunds-cancellation" / "page.tsx")
    assert "Electronic Transactions Act, 2008 (Act 772)" in page
    assert "seven-day grace period" in page
    assert "statutory right" in page
    assert "does not currently present a separate immediate-start" in page
    assert "not automatically refundable" in page or "not treat every purchase as" in page
    assert "all payments are non-refundable" not in page.lower()


def test_retention_policy_does_not_repeat_unverified_periods():
    page = _text(APP / "data-retention" / "page.tsx")
    assert "No scheduled automatic 30-day purge is implemented" in page
    assert "10 minutes" in page
    assert "30 minutes" in page
    assert "No scheduled expiry" in page
    assert "7 years" not in page
    assert "2 years" not in page


def test_license_packages_match_approved_catalogue():
    page = _text(APP / "license-subscription" / "page.tsx")
    for row in (
        ("Free", "GH₵0", "2 per calendar month"),
        ("Flexible Credit Pack", "GH₵12", "20"),
        ("Teacher Monthly", "GH₵22", "40"),
        ("Teacher Term Pass", "GH₵50", "160"),
        ("Academic Year Pass", "GH₵120", "480"),
    ):
        for value in row:
            assert value in page, value
    assert "automatic renewal" in page


def test_confirmed_business_address_is_public_and_old_missing_address_wording_is_gone():
    contact = _text(SRC / "lib" / "contact.ts")
    footer = _text(SRC / "components" / "public-footer.tsx")
    page = _text(APP / "contact" / "page.tsx")
    privacy = _text(APP / "privacy-policy" / "page.tsx")
    assert "L7 Olive St., Akast Road, Akatsi, Volta Region, Ghana." in contact
    assert "BUSINESS_ADDRESS" in footer
    assert "BUSINESS_ADDRESS" in page
    assert "BUSINESS_ADDRESS" in privacy
    assert "does not show a physical or registered business address" not in privacy
    assert "outstanding with the owner" not in privacy
    assert "P.O. Box" not in footer + page + privacy
    assert "PO Box" not in footer + page + privacy


def test_no_false_dpc_registration_or_certificate_page_is_published():
    privacy = _text(APP / "privacy-policy" / "page.tsx")
    assert "does not claim that DPC registration has been completed" in privacy
    assert "pursuing the separate DPC registration process" in privacy
    assert "application is pending" not in privacy
    assert "registration number is" not in privacy
    for path in APP.rglob("page.tsx"):
        text = _text(path)
        assert "DPC Registration Certificate" not in text, path
        assert "Data Protection Commission Registration" not in text, path
    sitemap = _text(APP / "sitemap.ts")
    assert "dpc" not in sitemap.lower()
    assert "certificate" not in sitemap.lower()
    assert (APP / "privacy-policy" / "page.tsx").exists()
    assert (APP / "data-retention" / "page.tsx").exists()


def test_refund_policy_preserves_statutory_rights_for_consumed_credits():
    page = _text(APP / "refunds-cancellation" / "page.tsx")
    assert "not normally refunded" in page
    assert "remains subject to any statutory cancellation" in page
    assert "does not currently present a separate immediate-start" in page
    assert "not a waiver" in page or "not treated here as a waiver" in page
    assert "not presented as legally approved" not in page
    # The page may say it is not legal advice, but must not claim legal approval.
    assert "legally approved" not in page.lower()


def test_data_retention_uses_statutory_frameworks_without_overgeneralising():
    page = _text(APP / "data-retention" / "page.tsx")
    assert "section 24" in page and "Act 843" in page
    assert "section 27" in page and "Act 915" in page
    assert "Section 8" in page and "Electronic Transactions Act, 2008" in page
    assert "six years" in page
    assert "not a general justification" in page
    assert "Categories with no scheduled expiry" in page
    assert "No scheduled automatic 30-day purge is implemented" in page
    assert "7 years" not in page
    assert "2 years" not in page


def test_terms_include_section_47_supplier_disclosures():
    page = _text(APP / "terms" / "page.tsx")
    assert "section 47 of the Electronic Transactions Act" in page
    assert "BUSINESS_ADDRESS" in page
    assert "Self-regulatory or related-body membership" in page
    assert "membership is claimed" in page
    assert "No code of conduct is" in page
    assert "Minimum duration" in page
    assert "Consumer rights" in page
    assert "SITE_URL" in page
    assert "P.O. Box" not in page


def test_sitemap_contains_only_public_routes():
    sitemap = _text(APP / "sitemap.ts")
    for private in ("/dashboard", "/upgrade", "/login", "/signup", "/platform-admin", "/school-admin", "/payments"):
        assert f"'{private}'" not in sitemap, private
    for public in ("/privacy-policy", "/terms", "/refunds-cancellation", "/data-retention", "/license-subscription", "/cookie-policy"):
        assert f"'{public}'" in sitemap, public


def test_orc_business_registration_is_not_confused_with_dpc_registration():
    page = " ".join(_text(APP / "privacy-policy" / "page.tsx").split())
    assert "Office of the Registrar of Companies, Ghana" in page
    assert "Registration of Business Names Act, 1962 (No. 151)" in page
    assert "BUSINESS_REGISTRATION_NUMBER" in page
    assert "BUSINESS_REGISTRATION_DATE" in page
    contact = _text(SRC / "lib" / "contact.ts")
    assert "BN428031125" in contact
    assert "7 November 2025" in contact
    assert "separate from registration with the" in page
    assert "Ghana Data Protection Commission (DPC)" in page
    assert "does not claim that DPC registration has been completed" in page
    assert "DPC registration number is BN" not in page
    assert "business-name registration number is a DPC" not in page
    assert "P0066415551" not in page


def test_tin_is_absent_from_production_frontend_output_when_built():
    static = FRONTEND / ".next" / "static"
    if not static.exists():
        return
    for path in static.rglob("*"):
        if path.is_file():
            data = path.read_bytes()
            assert b"P0066415551" not in data, path
