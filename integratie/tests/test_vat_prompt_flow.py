"""
Tests for the VAT prompt flow (Story: BTW-nummer vereist bij factuurvraag).

When a private (non-company) customer requests an invoice at the POS and has no
VAT number stored in Odoo, the cashier is prompted by VatPromptDialog (JS) to
enter one before the order can be validated.

  • Confirmed with VAT  → vat saved to res.partner.vat; order_poller includes
                           <vat_number> in the outgoing invoice_request XML.
  • Cancelled           → to_invoice is reset to False before validation;
                           order_poller skips invoice_request entirely.

These tests cover the Python (order_poller / sender) side of that flow.
JS/OWL dialog behaviour is covered in
addons/kassa_pos_custom/static/tests/vat_prompt_dialog.test.js.
"""

import os
import re
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
from lxml import etree

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import order_poller  # noqa: E402
import sender        # noqa: E402


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _env(monkeypatch):
    """Minimal env vars so imports and OrderPoller() succeed without a live stack."""
    monkeypatch.setenv("ODOO_URL",      "http://test:8069")
    monkeypatch.setenv("ODOO_DB",       "test_db")
    monkeypatch.setenv("ODOO_USER",     "test_user")
    monkeypatch.setenv("ODOO_PASS",     "test_pass")
    monkeypatch.setenv("RABBIT_HOST",   "localhost")
    monkeypatch.setenv("RABBIT_USER",   "guest")
    monkeypatch.setenv("RABBIT_PASS",   "guest")
    monkeypatch.setenv("RABBIT_EXCHANGE", "test.exchange")


def _poller():
    p = order_poller.OrderPoller()
    p.odoo_uid = 1
    p.models = MagicMock()
    return p


def _private(*, vat=None, partner_id=10):
    """Minimal customer_info dict for a private (non-company) person."""
    return {
        "id":            partner_id,
        "name":          "Jan Peeters",
        "email":         "jan@example.com",
        "customer_type": "private",
        "vat":           vat,
        "x_user_id":     "user-private-001",
        "street":        "Kiekenmarkt 42",
        "street2":       "",
        "city":          "Brussel",
        "zip":           "1000",
        "country_code":  "be",
        "country_id":    [187, "Belgium"],
    }


def _company(*, vat="BE0123456789", partner_id=20):
    """Minimal customer_info dict for a company."""
    return {
        "id":            partner_id,
        "name":          "Acme NV",
        "email":         "info@acme.be",
        "customer_type": "company",
        "vat":           vat,
        "x_user_id":     "user-company-001",
        "street":        "Industrielaan 1",
        "street2":       "",
        "city":          "Gent",
        "zip":           "9000",
        "country_code":  "be",
        "country_id":    [187, "Belgium"],
    }


def _order(partner_id=10, *, to_invoice=True, order_id=500):
    return {
        "id":                    order_id,
        "name":                  f"Order/{order_id:05d}",
        "partner_id":            [partner_id, "Jan Peeters"],
        "amount_total":          45.00,
        "amount_tax":            7.87,
        "state":                 "paid",
        "to_invoice":            to_invoice,
        "account_move":          None,
        "x_invoice_message_id":  None,
        "x_payment_message_id":  str(uuid.uuid4()),
        "payment_ids":           [[1]],
        "create_date":           "2026-05-18 12:00:00",
        "session_id":            [1, "Bar Kassa Session"],
        "lines":                 [],
    }


CORR = "550e8400-e29b-41d4-a716-446655440000"
SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "schema_invoice_request.xsd"


# ---------------------------------------------------------------------------
# 1. VAT format validation — mirrors the JS _isValidVat regex
# ---------------------------------------------------------------------------

EU_VAT_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{6,12}$", re.IGNORECASE)


class TestVatFormatValidation:
    """
    Documents and validates the regex used by VatPromptDialog._isValidVat().
    The JS regex is: /^[A-Z]{2}[A-Z0-9]{6,12}$/i
    """

    # ── valid inputs ──────────────────────────────────────────────────────────

    @pytest.mark.parametrize("vat", [
        "BE0123456789",   # Belgium (12 chars)
        "BE1234567890",   # Belgium alternative first digit
        "NL123456789B01", # Netherlands (14 chars, mixed alpha-numeric)
        "DE123456789",    # Germany (11 chars)
        "FR12345678901",  # France (13 chars)
        "FRXX999999999",  # France with letter prefix (valid EU)
        "LU12345678",     # Luxembourg (10 chars)
        "IT12345678901",  # Italy (13 chars)
        "GB123456789",    # GB format (11 chars, still EU-style)
        "be0123456789",   # Lowercase — regex is case-insensitive
        "Be0123456789",   # Mixed case
    ])
    def test_valid_vat_formats(self, vat):
        assert EU_VAT_RE.match(vat), f"Expected valid: {vat!r}"

    # ── invalid inputs ────────────────────────────────────────────────────────

    @pytest.mark.parametrize("vat,reason", [
        ("",              "empty string"),
        ("   ",           "whitespace only"),
        ("0123456789",    "no country prefix"),
        ("B0123456789",   "single-letter prefix"),
        ("BE01234",       "too short (only 5 chars after prefix)"),
        ("BE012345678901234", "too long (13+ chars after prefix)"),
        ("1234567890",    "starts with digit"),
        ("BE 0123456789", "space inside"),
        ("BE-0123456789", "dash inside"),
    ])
    def test_invalid_vat_formats(self, vat, reason):
        assert not EU_VAT_RE.match(vat), f"Expected invalid ({reason}): {vat!r}"

    def test_normalised_vat_is_uppercase(self):
        raw = "be0123456789"
        normalised = raw.strip().upper()
        assert EU_VAT_RE.match(normalised)


# ---------------------------------------------------------------------------
# 2. _process_invoice_request — private customer WITH VAT entered via dialog
# ---------------------------------------------------------------------------

class TestProcessInvoiceRequestPrivateWithVat:
    """
    After the cashier confirms the VAT number in VatPromptDialog, the partner's
    vat field is saved to Odoo before order validation.  By the time
    order_poller.process_order() picks up the order, customer_info already
    contains the vat value.  _process_invoice_request must include it in XML.
    """

    @pytest.mark.parametrize("vat", [
        "BE0123456789",
        "NL123456789B01",
        "DE123456789",
        "FR12345678901",
    ])
    def test_vat_included_in_invoice_request_xml(self, vat):
        """VAT entered by cashier appears in <vat_number> of outgoing XML."""
        poller = _poller()
        customer = _private(vat=vat)

        with patch("order_poller.sender") as mock_sender:
            mock_sender.send_typed_message.return_value = True
            mock_sender.build_invoice_request_xml.return_value = "<xml/>"

            poller._process_invoice_request({"id": 1}, customer, correlation_id=CORR)

            call_kwargs = mock_sender.build_invoice_request_xml.call_args[1]
            assert call_kwargs["invoice_data"]["vat_number"] == vat

    def test_vat_appears_in_generated_xml_element(self):
        """Full XML builder puts the VAT in the correct element."""
        invoice_data = {
            "first_name": "Jan",
            "last_name":  "Peeters",
            "email":      "jan@example.com",
            "vat_number": "BE0123456789",
            "address":    {
                "street":      "Kiekenmarkt",
                "number":      "42",
                "postal_code": "1000",
                "city":        "Brussel",
                "country":     "be",
            },
        }
        xml_str = sender.build_invoice_request_xml(
            identity_uuid=str(uuid.uuid4()),
            invoice_data=invoice_data,
            correlation_id=CORR,
        )
        root = etree.fromstring(xml_str.encode())
        elem = root.find("body/invoice_data/vat_number")
        assert elem is not None
        assert elem.text == "BE0123456789"

    def test_generated_xml_validates_against_xsd_with_vat(self):
        """invoice_request XML with private-customer VAT passes schema validation."""
        if not SCHEMA_PATH.exists():
            pytest.skip(f"Schema not found: {SCHEMA_PATH}")

        schema = etree.XMLSchema(etree.parse(str(SCHEMA_PATH)))
        invoice_data = {
            "first_name": "Jan",
            "last_name":  "Peeters",
            "email":      "jan@example.com",
            "vat_number": "BE0123456789",
            "address":    {
                "street":      "Kiekenmarkt",
                "number":      "42",
                "postal_code": "1000",
                "city":        "Brussel",
                "country":     "be",
            },
        }
        xml_str = sender.build_invoice_request_xml(
            identity_uuid=str(uuid.uuid4()),
            invoice_data=invoice_data,
            correlation_id=CORR,
        )
        doc = etree.fromstring(xml_str.encode())
        assert schema.validate(doc), schema.error_log

    def test_identity_uuid_comes_from_x_user_id(self):
        """The identity_uuid in XML must be the partner's x_user_id, not the Odoo id."""
        poller = _poller()
        customer = _private(vat="BE0123456789")
        customer["x_user_id"] = "crm-uuid-99"

        with patch("order_poller.sender") as mock_sender:
            mock_sender.send_typed_message.return_value = True
            mock_sender.build_invoice_request_xml.return_value = "<xml/>"

            poller._process_invoice_request({"id": 1}, customer, correlation_id=CORR)

            call_kwargs = mock_sender.build_invoice_request_xml.call_args[1]
            assert call_kwargs["identity_uuid"] == "crm-uuid-99"

    def test_address_split_applied_when_vat_present(self):
        """split_street_and_number is applied even for customers with VAT."""
        poller = _poller()
        customer = _private(vat="BE0123456789")
        customer["street"] = "Kiekenmarkt 42"

        with patch("order_poller.sender") as mock_sender:
            mock_sender.send_typed_message.return_value = True
            mock_sender.build_invoice_request_xml.return_value = "<xml/>"

            poller._process_invoice_request({"id": 1}, customer, correlation_id=CORR)

            call_kwargs = mock_sender.build_invoice_request_xml.call_args[1]
            assert call_kwargs["invoice_data"]["address"]["street"] == "Kiekenmarkt"
            assert call_kwargs["invoice_data"]["address"]["number"] == "42"

    def test_correlation_id_forwarded_correctly(self):
        """correlation_id from the original consumption_order is preserved."""
        poller = _poller()
        customer = _private(vat="BE0123456789")
        custom_corr = "custom-corr-id-abc"

        with patch("order_poller.sender") as mock_sender:
            mock_sender.send_typed_message.return_value = True
            mock_sender.build_invoice_request_xml.return_value = "<xml/>"

            poller._process_invoice_request({"id": 1}, customer, correlation_id=custom_corr)

            call_kwargs = mock_sender.build_invoice_request_xml.call_args[1]
            assert call_kwargs["correlation_id"] == custom_corr

    def test_returns_true_and_message_id_on_success(self):
        """_process_invoice_request returns (True, msg_id) when send succeeds."""
        poller = _poller()
        customer = _private(vat="BE0123456789")
        fake_msg_id = str(uuid.uuid4())
        fake_xml = f"<message><header><message_id>{fake_msg_id}</message_id></header></message>"

        with patch("order_poller.sender") as mock_sender:
            mock_sender.send_typed_message.return_value = True
            mock_sender.build_invoice_request_xml.return_value = fake_xml
            mock_sender.extract_message_id.return_value = fake_msg_id

            success, msg_id = poller._process_invoice_request(
                {"id": 1}, customer, correlation_id=CORR
            )

        assert success is True
        assert msg_id == fake_msg_id


# ---------------------------------------------------------------------------
# 3. _process_invoice_request — private customer WITHOUT VAT (B2C / cancelled)
# ---------------------------------------------------------------------------

class TestProcessInvoiceRequestPrivateWithoutVat:
    """
    When the cashier cancelled the VAT dialog, to_invoice is cleared before
    validation and order_poller never calls _process_invoice_request for that
    order.  If somehow a private customer without VAT reaches this function
    (e.g. a legacy order from before the dialog was introduced), no VAT element
    must appear in the XML — but the invoice_request IS still sent (B2C is legal).
    """

    @pytest.mark.parametrize("vat_value", [None, ""])
    def test_vat_omitted_from_xml_when_absent(self, vat_value):
        """<vat_number> element is absent in XML when vat_number is None or empty string.

        Note: build_invoice_request_xml uses a truthiness check (`if invoice_data.get("vat_number"):`).
        None and "" are falsy → element omitted.  Whitespace-only strings are truthy → element
        included as-is.  The JS VatPromptDialog always trims before saving to Odoo, so whitespace
        can only arrive from legacy manual edits (handled separately below).
        """
        invoice_data = {
            "first_name": "Marie",
            "last_name":  "Dubois",
            "email":      "marie@example.com",
            "address":    {
                "street":      "Rue de la Paix",
                "number":      "10",
                "postal_code": "2000",
                "city":        "Antwerpen",
                "country":     "be",
            },
        }
        if vat_value is not None:
            invoice_data["vat_number"] = vat_value

        xml_str = sender.build_invoice_request_xml(
            identity_uuid=str(uuid.uuid4()),
            invoice_data=invoice_data,
            correlation_id=CORR,
        )
        root = etree.fromstring(xml_str.encode())
        elem = root.find("body/invoice_data/vat_number")
        assert elem is None, "vat_number element must not appear when VAT is absent"

    def test_whitespace_vat_included_verbatim_in_xml(self):
        """Whitespace-only vat_number IS truthy, so it appears in the XML as-is.

        The JS dialog always trims before saving, so this only occurs for legacy data.
        This test documents the actual behaviour rather than an ideal one.
        """
        invoice_data = {
            "first_name": "Marie",
            "last_name":  "Dubois",
            "email":      "marie@example.com",
            "vat_number": "   ",
            "address":    {
                "street":      "Rue de la Paix",
                "number":      "10",
                "postal_code": "2000",
                "city":        "Antwerpen",
                "country":     "be",
            },
        }
        xml_str = sender.build_invoice_request_xml(
            identity_uuid=str(uuid.uuid4()),
            invoice_data=invoice_data,
            correlation_id=CORR,
        )
        root = etree.fromstring(xml_str.encode())
        elem = root.find("body/invoice_data/vat_number")
        # Whitespace is truthy → element IS present (legacy / manual-edit case)
        assert elem is not None
        assert elem.text == "   "

    def test_invoice_request_without_vat_passes_xsd(self):
        """B2C invoice_request without <vat_number> still validates against schema."""
        if not SCHEMA_PATH.exists():
            pytest.skip(f"Schema not found: {SCHEMA_PATH}")

        schema = etree.XMLSchema(etree.parse(str(SCHEMA_PATH)))
        invoice_data = {
            "first_name": "Marie",
            "last_name":  "Dubois",
            "email":      "marie@example.com",
            "address":    {
                "street":      "Rue de la Paix",
                "number":      "10",
                "postal_code": "2000",
                "city":        "Antwerpen",
                "country":     "be",
            },
        }
        xml_str = sender.build_invoice_request_xml(
            identity_uuid=str(uuid.uuid4()),
            invoice_data=invoice_data,
            correlation_id=CORR,
        )
        doc = etree.fromstring(xml_str.encode())
        assert schema.validate(doc), schema.error_log

    def test_private_without_vat_invoice_request_is_still_sent(self):
        """_process_invoice_request does NOT block private customers without VAT."""
        poller = _poller()
        customer = _private(vat=None)

        with patch("order_poller.sender") as mock_sender:
            mock_sender.send_typed_message.return_value = True
            mock_sender.build_invoice_request_xml.return_value = "<xml/>"

            success, _ = poller._process_invoice_request(
                {"id": 1}, customer, correlation_id=CORR
            )

        assert success is True

    def test_no_xsd_error_raised_for_private_without_vat(self):
        """Unlike companies, private customers without VAT must never raise XSDValidationError."""
        poller = _poller()
        customer = _private(vat=None)

        with patch("order_poller.sender") as mock_sender:
            mock_sender.send_typed_message.return_value = True
            mock_sender.build_invoice_request_xml.return_value = "<xml/>"

            # Must not raise
            poller._process_invoice_request({"id": 1}, customer, correlation_id=CORR)


# ---------------------------------------------------------------------------
# 4. VAT edge-cases in _process_invoice_request
# ---------------------------------------------------------------------------

class TestProcessInvoiceRequestVatEdgeCases:
    """Boundary values and whitespace handling for VAT on private customers."""

    @pytest.mark.parametrize("vat,expected", [
        ("BE0123456789",   "BE0123456789"),   # normal
        ("  BE0123456789", "  BE0123456789"), # leading spaces preserved (JS trims before save)
        ("BE0123456789  ", "BE0123456789  "), # trailing spaces preserved
    ])
    def test_vat_passed_through_as_stored(self, vat, expected):
        """order_poller passes vat exactly as stored — normalisation is the JS dialog's job."""
        poller = _poller()
        customer = _private(vat=vat)

        with patch("order_poller.sender") as mock_sender:
            mock_sender.send_typed_message.return_value = True
            mock_sender.build_invoice_request_xml.return_value = "<xml/>"

            poller._process_invoice_request({"id": 1}, customer, correlation_id=CORR)

            call_kwargs = mock_sender.build_invoice_request_xml.call_args[1]
            assert call_kwargs["invoice_data"]["vat_number"] == expected

    def test_empty_string_vat_treated_as_absent_in_xml(self):
        """Empty-string vat produces no <vat_number> element (build_invoice_request_xml guard)."""
        invoice_data = {
            "first_name": "Jan",
            "last_name":  "Peeters",
            "email":      "jan@example.com",
            "vat_number": "",
            "address":    {
                "street":      "Kiekenmarkt",
                "number":      "42",
                "postal_code": "1000",
                "city":        "Brussel",
                "country":     "be",
            },
        }
        xml_str = sender.build_invoice_request_xml(
            identity_uuid=str(uuid.uuid4()),
            invoice_data=invoice_data,
            correlation_id=CORR,
        )
        root = etree.fromstring(xml_str.encode())
        assert root.find("body/invoice_data/vat_number") is None


# ---------------------------------------------------------------------------
# 5. process_order — cashier confirmed VAT in dialog (to_invoice=True, vat set)
# ---------------------------------------------------------------------------

class TestProcessOrderCashierConfirmedVat:
    """
    End-to-end process_order behaviour after the cashier entered a VAT number
    and clicked Bevestigen in the dialog.
    """

    def test_invoice_request_sent_for_private_with_vat(self):
        """Full process_order calls _process_invoice_request for private with VAT."""
        poller = _poller()
        order = _order(to_invoice=True)
        customer = _private(vat="BE0123456789")

        cons_rv = (True, str(uuid.uuid4()), str(uuid.uuid4()), "paid", "on_site")
        with patch.object(poller, "_process_consumption", return_value=cons_rv), \
             patch.object(poller, "get_customer_info", return_value=customer), \
             patch.object(poller, "_process_invoice_request",
                          return_value=(True, str(uuid.uuid4()))) as mock_inv:
            poller.process_order(order)
            mock_inv.assert_called_once()

    def test_invoice_request_not_sent_for_private_with_vat_but_no_flag(self):
        """If to_invoice is False, invoice_request is skipped regardless of VAT presence."""
        poller = _poller()
        order = _order(to_invoice=False)
        customer = _private(vat="BE0123456789")

        cons_rv = (True, str(uuid.uuid4()), str(uuid.uuid4()), "paid", "on_site")
        with patch.object(poller, "_process_consumption", return_value=cons_rv), \
             patch.object(poller, "get_customer_info", return_value=customer), \
             patch.object(poller, "_process_invoice_request") as mock_inv:
            poller.process_order(order)
            mock_inv.assert_not_called()

    def test_vat_from_customer_info_used_not_refetched(self):
        """
        order_poller must use the customer_info vat field as fetched from Odoo
        — it does NOT need to re-query res.partner.vat separately.
        """
        poller = _poller()
        order = _order(to_invoice=True)
        customer = _private(vat="BE0123456789")

        cons_rv = (True, str(uuid.uuid4()), str(uuid.uuid4()), "paid", "on_site")
        with patch.object(poller, "_process_consumption", return_value=cons_rv), \
             patch.object(poller, "get_customer_info", return_value=customer), \
             patch.object(poller, "_process_invoice_request",
                          return_value=(True, str(uuid.uuid4()))) as mock_inv:
            poller.process_order(order)

            call_args = mock_inv.call_args
            passed_customer = call_args[0][1]
            assert passed_customer["vat"] == "BE0123456789"


# ---------------------------------------------------------------------------
# 6. process_order — cashier cancelled in dialog (to_invoice=False)
# ---------------------------------------------------------------------------

class TestProcessOrderCashierCancelledDialog:
    """
    When the cashier clicks "Factuur annuleren" in VatPromptDialog, the JS sets
    to_invoice=False before calling validate(), so the order arrives at
    order_poller with to_invoice=False.  No invoice_request must be generated.
    """

    def test_no_invoice_request_when_cashier_cancelled(self):
        poller = _poller()
        order = _order(to_invoice=False)
        customer = _private(vat=None)  # No VAT — that's why dialog was shown

        cons_rv = (True, str(uuid.uuid4()), str(uuid.uuid4()), "paid", "on_site")
        with patch.object(poller, "_process_consumption", return_value=cons_rv), \
             patch.object(poller, "get_customer_info", return_value=customer), \
             patch.object(poller, "_process_invoice_request") as mock_inv:
            poller.process_order(order)
            mock_inv.assert_not_called()

    def test_consumption_still_sent_after_cancel(self):
        """Cancelling the invoice does not affect the consumption_order message."""
        poller = _poller()
        order = _order(to_invoice=False)
        customer = _private(vat=None)

        cons_rv = (True, str(uuid.uuid4()), str(uuid.uuid4()), "paid", "on_site")
        with patch.object(poller, "_process_consumption", return_value=cons_rv) as mock_cons, \
             patch.object(poller, "get_customer_info", return_value=customer), \
             patch.object(poller, "_process_invoice_request"):
            poller.process_order(order)
            mock_cons.assert_called_once()

    def test_anonymous_order_with_to_invoice_still_skipped(self):
        """Anonymous orders never get an invoice_request even if somehow to_invoice=True."""
        poller = _poller()
        order = _order(to_invoice=True)
        order["partner_id"] = False  # Anonymous

        poller.models.execute_kw.return_value = []

        cons_rv = (True, str(uuid.uuid4()), str(uuid.uuid4()), "paid", "on_site")
        with patch.object(poller, "_process_consumption", return_value=cons_rv), \
             patch.object(poller, "_process_invoice_request") as mock_inv:
            poller.process_order(order)
            mock_inv.assert_not_called()


# ---------------------------------------------------------------------------
# 7. Deduplication — already-sent invoices are not resent
# ---------------------------------------------------------------------------

class TestInvoiceDeduplication:
    """
    If x_invoice_message_id is already set on the order, order_poller must not
    send a second invoice_request (the dialog flow must not break dedup).
    """

    def test_invoice_not_resent_when_message_id_present(self):
        poller = _poller()
        order = _order(to_invoice=True)
        order["x_invoice_message_id"] = str(uuid.uuid4())  # Already sent
        customer = _private(vat="BE0123456789")

        cons_rv = (True, str(uuid.uuid4()), str(uuid.uuid4()), "paid", "on_site")
        with patch.object(poller, "_process_consumption", return_value=cons_rv), \
             patch.object(poller, "get_customer_info", return_value=customer), \
             patch.object(poller, "_process_invoice_request") as mock_inv:
            poller.process_order(order)
            mock_inv.assert_not_called()

    def test_invoice_not_resent_for_private_with_vat(self):
        """Dedup applies equally to private customers who have a VAT number."""
        poller = _poller()
        order = _order(to_invoice=True)
        order["x_invoice_message_id"] = str(uuid.uuid4())
        customer = _private(vat="NL123456789B01")

        cons_rv = (True, str(uuid.uuid4()), str(uuid.uuid4()), "paid", "on_site")
        with patch.object(poller, "_process_consumption", return_value=cons_rv), \
             patch.object(poller, "get_customer_info", return_value=customer), \
             patch.object(poller, "_process_invoice_request") as mock_inv:
            poller.process_order(order)
            mock_inv.assert_not_called()


# ---------------------------------------------------------------------------
# 8. Company flow unchanged
# ---------------------------------------------------------------------------

class TestCompanyFlowUnchanged:
    """
    The dialog is never shown for company customers.  Company VAT is enforced at
    new_registration time (receiver.py).  _process_invoice_request must still
    block companies without VAT and pass companies with VAT.
    """

    def test_company_with_vat_invoice_request_sent(self):
        poller = _poller()
        customer = _company(vat="BE0123456789")

        with patch("order_poller.sender") as mock_sender:
            mock_sender.send_typed_message.return_value = True
            mock_sender.build_invoice_request_xml.return_value = "<xml/>"

            success, _ = poller._process_invoice_request(
                {"id": 2}, customer, correlation_id=CORR
            )

        assert success is True

    def test_company_without_vat_raises(self):
        poller = _poller()
        customer = _company(vat=None)

        with patch("order_poller.sender.send_error_to_queue"):
            with pytest.raises(sender.XSDValidationError):
                poller._process_invoice_request(
                    {"id": 2}, customer, correlation_id=CORR
                )

    def test_company_with_empty_vat_raises(self):
        poller = _poller()
        customer = _company(vat="")

        with patch("order_poller.sender.send_error_to_queue"):
            with pytest.raises(sender.XSDValidationError):
                poller._process_invoice_request(
                    {"id": 2}, customer, correlation_id=CORR
                )

    def test_company_vat_included_in_xml(self):
        """Company VAT flows into invoice_data.vat_number same as private."""
        poller = _poller()
        customer = _company(vat="BE9876543210")

        with patch("order_poller.sender") as mock_sender:
            mock_sender.send_typed_message.return_value = True
            mock_sender.build_invoice_request_xml.return_value = "<xml/>"

            poller._process_invoice_request({"id": 2}, customer, correlation_id=CORR)

            call_kwargs = mock_sender.build_invoice_request_xml.call_args[1]
            assert call_kwargs["invoice_data"]["vat_number"] == "BE9876543210"


# ---------------------------------------------------------------------------
# 9. XSD compliance — both with and without vat_number
# ---------------------------------------------------------------------------

class TestXSDCompliance:
    """Generated XML must pass schema_invoice_request.xsd in all VAT scenarios."""

    @pytest.fixture(autouse=True)
    def _check_schema(self):
        if not SCHEMA_PATH.exists():
            pytest.skip(f"Schema not found: {SCHEMA_PATH}")

    def _schema(self):
        return etree.XMLSchema(etree.parse(str(SCHEMA_PATH)))

    def _base_invoice_data(self, *, vat=None):
        d = {
            "first_name": "Test",
            "last_name":  "User",
            "email":      "test@example.com",
            "address": {
                "street":      "Teststraat",
                "number":      "1",
                "postal_code": "1000",
                "city":        "Brussel",
                "country":     "be",
            },
        }
        if vat:
            d["vat_number"] = vat
        return d

    @pytest.mark.parametrize("vat", [
        "BE0123456789",
        "NL123456789B01",
        "DE123456789",
    ])
    def test_with_various_vat_numbers(self, vat):
        xml_str = sender.build_invoice_request_xml(
            identity_uuid=str(uuid.uuid4()),
            invoice_data=self._base_invoice_data(vat=vat),
            correlation_id=CORR,
        )
        doc = etree.fromstring(xml_str.encode())
        assert self._schema().validate(doc), self._schema().error_log

    def test_without_vat_number(self):
        """B2C invoice (no vat_number) must also be schema-valid."""
        xml_str = sender.build_invoice_request_xml(
            identity_uuid=str(uuid.uuid4()),
            invoice_data=self._base_invoice_data(),
            correlation_id=CORR,
        )
        doc = etree.fromstring(xml_str.encode())
        assert self._schema().validate(doc), self._schema().error_log

    def test_with_payment_status_paid(self):
        xml_str = sender.build_invoice_request_xml(
            identity_uuid=str(uuid.uuid4()),
            invoice_data=self._base_invoice_data(vat="BE0123456789"),
            correlation_id=CORR,
            payment_status="paid",
        )
        doc = etree.fromstring(xml_str.encode())
        assert self._schema().validate(doc), self._schema().error_log

    def test_with_payment_status_pending(self):
        xml_str = sender.build_invoice_request_xml(
            identity_uuid=str(uuid.uuid4()),
            invoice_data=self._base_invoice_data(vat="BE0123456789"),
            correlation_id=CORR,
            payment_status="pending",
        )
        doc = etree.fromstring(xml_str.encode())
        assert self._schema().validate(doc), self._schema().error_log


# ---------------------------------------------------------------------------
# 10. Routing key
# ---------------------------------------------------------------------------

class TestRoutingKey:
    """invoice_request (with or without VAT) is always sent to kassa.payments.invoice."""

    @patch("sender._publish_or_raise")
    def test_routing_key_with_vat(self, mock_publish):
        invoice_data = {
            "first_name": "Jan",
            "last_name":  "Peeters",
            "email":      "jan@example.com",
            "vat_number": "BE0123456789",
            "address": {
                "street": "Kiekenmarkt", "number": "42",
                "postal_code": "1000", "city": "Brussel", "country": "be",
            },
        }
        xml_str = sender.build_invoice_request_xml(
            identity_uuid=str(uuid.uuid4()),
            invoice_data=invoice_data,
            correlation_id=CORR,
        )
        sender.send_typed_message("invoice_request", xml_str, record_id=100)
        routing_key = mock_publish.call_args[0][0]
        assert routing_key == "kassa.payments.invoice"

    @patch("sender._publish_or_raise")
    def test_routing_key_without_vat(self, mock_publish):
        invoice_data = {
            "first_name": "Marie",
            "last_name":  "Dubois",
            "email":      "marie@example.com",
            "address": {
                "street": "Rue de la Paix", "number": "10",
                "postal_code": "2000", "city": "Antwerpen", "country": "be",
            },
        }
        xml_str = sender.build_invoice_request_xml(
            identity_uuid=str(uuid.uuid4()),
            invoice_data=invoice_data,
            correlation_id=CORR,
        )
        sender.send_typed_message("invoice_request", xml_str, record_id=101)
        routing_key = mock_publish.call_args[0][0]
        assert routing_key == "kassa.payments.invoice"
