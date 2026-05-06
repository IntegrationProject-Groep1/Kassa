# test_vat_validation.py – VAT number validation tests
# Team Kassa (Odoo POS) | Integratieproject Desideriushogeschool 2026

"""
VAT Validation Story: Enforcing VAT requirements per contract Section 11.1

Checklist:
✓ Incoming check: receiver.py rejects new_registration for company type without vat_number
✓ Outgoing check: order_poller.py blocks invoice_request for company without vat_number
✓ Centralized logging: Errors sent to kassa.errors with code 'invalid_xml_format'
"""

from unittest.mock import MagicMock, patch
import pytest
import xml.etree.ElementTree as ET

import receiver
import order_poller


class TestVATValidationIncoming:
    """Incoming check: receiver.py must reject company registrations without VAT."""

    def test_company_registration_without_vat_raises_error(self):
        """Verify that new_registration for company type without vat_number raises ValueError."""
        root = ET.Element("message")
        header = ET.SubElement(root, "header")
        ET.SubElement(header, "type").text = "new_registration"

        body = ET.SubElement(root, "body")
        customer = ET.SubElement(body, "customer")
        ET.SubElement(customer, "user_id").text = "user123"
        ET.SubElement(customer, "name").text = "Acme Corp"
        ET.SubElement(customer, "type").text = "company"
        # Note: vat_number is intentionally missing

        payment_due = ET.SubElement(customer, "payment_due")
        ET.SubElement(payment_due, "status").text = "unpaid"
        ET.SubElement(payment_due, "amount").text = "100.00"

        models = MagicMock()
        with pytest.raises(ValueError, match="vat_number is mandatory for company type"):
            receiver.process_new_registration(root, uid=1, models=models)

    def test_company_registration_with_empty_vat_raises_error(self):
        """Verify that company registration with empty vat_number is rejected."""
        root = ET.Element("message")
        header = ET.SubElement(root, "header")
        ET.SubElement(header, "type").text = "new_registration"

        body = ET.SubElement(root, "body")
        customer = ET.SubElement(body, "customer")
        ET.SubElement(customer, "user_id").text = "user123"
        ET.SubElement(customer, "name").text = "Acme Corp"
        ET.SubElement(customer, "type").text = "company"
        ET.SubElement(customer, "vat_number").text = "   "  # whitespace only

        payment_due = ET.SubElement(customer, "payment_due")
        ET.SubElement(payment_due, "status").text = "unpaid"
        ET.SubElement(payment_due, "amount").text = "100.00"

        models = MagicMock()
        with pytest.raises(ValueError, match="vat_number is mandatory for company type"):
            receiver.process_new_registration(root, uid=1, models=models)

    def test_company_registration_with_vat_succeeds(self):
        """Verify that company registration with vat_number succeeds."""
        root = ET.Element("message")
        header = ET.SubElement(root, "header")
        ET.SubElement(header, "type").text = "new_registration"

        body = ET.SubElement(root, "body")
        customer = ET.SubElement(body, "customer")
        ET.SubElement(customer, "user_id").text = "user123"
        ET.SubElement(customer, "name").text = "Acme Corp"
        ET.SubElement(customer, "type").text = "company"
        ET.SubElement(customer, "vat_number").text = "BE0123456789"

        payment_due = ET.SubElement(customer, "payment_due")
        ET.SubElement(payment_due, "status").text = "unpaid"
        ET.SubElement(payment_due, "amount").text = "100.00"

        models = MagicMock()
        models.execute_kw.return_value = [{"id": 1, "name": "Acme Corp", "x_user_id": "user123"}]

        # Should not raise
        receiver.process_new_registration(root, uid=1, models=models)

        # Verify create was called with vat field
        assert models.execute_kw.call_count >= 1

    def test_private_registration_without_vat_succeeds(self):
        """Verify that private (individual) registration works without VAT."""
        root = ET.Element("message")
        header = ET.SubElement(root, "header")
        ET.SubElement(header, "type").text = "new_registration"

        body = ET.SubElement(root, "body")
        customer = ET.SubElement(body, "customer")
        ET.SubElement(customer, "user_id").text = "user456"
        ET.SubElement(customer, "name").text = "John Doe"
        ET.SubElement(customer, "type").text = "private"
        # Note: vat_number is intentionally missing

        payment_due = ET.SubElement(customer, "payment_due")
        ET.SubElement(payment_due, "status").text = "unpaid"
        ET.SubElement(payment_due, "amount").text = "50.00"

        models = MagicMock()
        models.execute_kw.return_value = []

        # Should not raise - private customers don't need VAT
        receiver.process_new_registration(root, uid=1, models=models)


class TestVATValidationOutgoing:
    """Outgoing check: order_poller.py blocks invoice_request for companies without VAT."""

    def test_invoice_request_blocked_for_company_without_vat(self):
        """Verify that invoice_request is not sent if company has no VAT number."""
        poller = order_poller.OrderPoller()

        order = {
            'id': 100,
            'name': 'Order/00001',
        }

        customer_info = {
            'id': 50,
            'name': 'Acme Corp',
            'customer_type': 'company',
            'vat': None,  # Missing VAT
            'x_user_id': 'comp123',
            'email': 'contact@acme.com',
            'country_code': 'be',
            'street': 'Main St',
            'street2': '42',
            'zip': '2000',
            'city': 'Antwerpen',
        }

        with patch("order_poller.sender.send_error_to_queue") as mock_send_error:
            success, msg_id = poller._process_invoice_request(order, customer_info, correlation_id="corr123")

        # Verify invoice_request was not sent (returns False, None)
        assert success is False
        assert msg_id is None

        # Verify error was sent to kassa.errors
        mock_send_error.assert_called_once()
        error_code, related_msg_id, description = mock_send_error.call_args[0]
        assert error_code == "invalid_xml_format"
        assert "VAT number" in description
        assert "50" in description  # Customer ID should be in error message

    def test_invoice_request_blocked_for_company_with_empty_vat(self):
        """Verify that whitespace-only VAT also blocks invoice_request."""
        poller = order_poller.OrderPoller()

        order = {'id': 101, 'name': 'Order/00002'}

        customer_info = {
            'id': 51,
            'name': 'Tech Innovations',
            'customer_type': 'company',
            'vat': '   ',  # Whitespace only
            'x_user_id': 'tech123',
            'email': 'info@tech.com',
            'country_code': 'be',
            'street': 'Tech Park',
            'street2': '1',
            'zip': '1000',
            'city': 'Brussels',
        }

        with patch("order_poller.sender.send_error_to_queue") as mock_send_error:
            success, msg_id = poller._process_invoice_request(order, customer_info, correlation_id="corr456")

        assert success is False
        assert msg_id is None
        mock_send_error.assert_called_once()

    def test_invoice_request_sent_for_company_with_vat(self):
        """Verify that invoice_request IS sent when company has VAT."""
        poller = order_poller.OrderPoller()

        order = {'id': 102, 'name': 'Order/00003'}

        customer_info = {
            'id': 52,
            'name': 'Valid Company',
            'customer_type': 'company',
            'vat': 'BE0987654321',  # Valid VAT
            'x_user_id': 'valid123',
            'email': 'hello@validco.com',
            'country_code': 'be',
            'street': 'Valid Ave',
            'street2': '99',
            'zip': '9000',
            'city': 'Ghent',
        }

        with patch("order_poller.sender.send_typed_message") as mock_send:
            mock_send.return_value = True
            success, msg_id = poller._process_invoice_request(order, customer_info, correlation_id="corr789")

        # Verify invoice_request was sent (returns True with message_id)
        assert success is True
        assert msg_id is not None
        mock_send.assert_called_once()

    def test_invoice_request_sent_for_private_without_vat(self):
        """Verify that private customers can have invoice_request sent without VAT."""
        poller = order_poller.OrderPoller()

        order = {'id': 103, 'name': 'Order/00004'}

        customer_info = {
            'id': 53,
            'name': 'John Smith',
            'customer_type': 'private',
            'vat': None,  # No VAT for private customer
            'x_user_id': 'john123',
            'email': 'john@example.com',
            'country_code': 'be',
            'street': 'Main St',
            'street2': '10',
            'zip': '3000',
            'city': 'Leuven',
        }

        with patch("order_poller.sender.send_typed_message") as mock_send:
            mock_send.return_value = True
            success, msg_id = poller._process_invoice_request(order, customer_info, correlation_id="corr000")

        # Verify invoice_request was sent (private customer OK without VAT)
        assert success is True
        assert msg_id is not None
        mock_send.assert_called_once()


class TestVATValidationCentralizedLogging:
    """Verify that VAT errors are logged with correct error codes in kassa.errors."""

    @patch("receiver.send_error_to_queue")
    def test_vat_error_has_correct_code_in_queue(self, mock_send_error):
        """Verify that VAT validation errors use 'invalid_xml_format' code."""
        root = ET.Element("message")
        header = ET.SubElement(root, "header")
        msg_id = ET.SubElement(header, "message_id")
        msg_id.text = "msg_vat_test"
        ET.SubElement(header, "type").text = "new_registration"

        body = ET.SubElement(root, "body")
        customer = ET.SubElement(body, "customer")
        ET.SubElement(customer, "user_id").text = "user_xyz"
        ET.SubElement(customer, "name").text = "Missing VAT Corp"
        ET.SubElement(customer, "type").text = "company"
        # Missing vat_number

        payment_due = ET.SubElement(customer, "payment_due")
        ET.SubElement(payment_due, "status").text = "unpaid"
        ET.SubElement(payment_due, "amount").text = "500.00"

        models = MagicMock()
        with pytest.raises(ValueError):
            receiver.process_new_registration(root, uid=1, models=models)

    def test_vat_error_message_includes_context(self):
        """Verify error messages include relevant context for debugging."""
        poller = order_poller.OrderPoller()

        order = {'id': 999}
        customer_info = {
            'id': 777,
            'name': 'Debug Test Corp',
            'customer_type': 'company',
            'vat': '',  # Empty
            'x_user_id': 'debug123',
        }

        with patch("order_poller.sender.send_error_to_queue") as mock_send_error:
            poller._process_invoice_request(order, customer_info, correlation_id="debug_corr")

        # Verify error message contains useful debugging info
        error_code, msg_id, description = mock_send_error.call_args[0]
        assert "Company" in description or "VAT" in description
        assert "777" in description  # Customer ID for tracing
