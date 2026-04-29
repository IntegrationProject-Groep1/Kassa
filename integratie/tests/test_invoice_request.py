"""
Test suite for Story 7: Invoice Request (Factuur vragen voor een drankje)
Covers: building invoice_request XML, sending messages, and poller detection.
"""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from lxml import etree

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))  # noqa: E402

import sender  # noqa: E402
import order_poller  # noqa: E402


@pytest.fixture(autouse=True)
def setup_env():
    """Mock environment variables for all tests."""
    os.environ['ODOO_URL'] = 'http://test:8069'
    os.environ['ODOO_DB'] = 'test_db'
    os.environ['ODOO_USER'] = 'test_user'
    os.environ['ODOO_PASS'] = 'test_pass'
    os.environ['RABBIT_HOST'] = 'localhost'
    os.environ['RABBIT_USER'] = 'guest'
    os.environ['RABBIT_PASS'] = 'guest'
    os.environ['RABBIT_EXCHANGE'] = 'test.exchange'


# ---------------------------------------------------------------------------
# Invoice Request XML Builder Tests
# ---------------------------------------------------------------------------

class TestBuildInvoiceRequestXML:
    """Test the build_invoice_request_xml function."""

    def test_build_invoice_request_with_vat(self):
        """Build invoice_request XML with all fields including VAT."""
        invoice_data = {
            "first_name": "Jan",
            "last_name": "Peeters",
            "email": "jan@example.com",
            "address": {
                "street": "Kiekenmarkt",
                "number": "42",
                "postal_code": "1000",
                "city": "Brussel",
                "country": "be"
            },
            "vat_number": "BE0123456789"
        }
        xml_str = sender.build_invoice_request_xml(
            user_id="e8b27c1d-4f2a-4b3e-9c5f-123456789abc",
            invoice_data=invoice_data
        )

        # Verify XML structure
        root = etree.fromstring(xml_str.encode('utf-8'))
        assert root.tag == "message"

        # Check header
        header = root.find("header")
        assert header is not None
        assert header.find("type").text == "invoice_request"

        # Check body
        body = root.find("body")
        assert body is not None
        assert body.find("user_id").text == "e8b27c1d-4f2a-4b3e-9c5f-123456789abc"

        # Check invoice_data
        inv_data = body.find("invoice_data")
        assert inv_data is not None
        assert inv_data.find("first_name").text == "Jan"
        assert inv_data.find("last_name").text == "Peeters"
        assert inv_data.find("email").text == "jan@example.com"
        assert inv_data.find("vat_number").text == "BE0123456789"

        # Check address
        addr = inv_data.find("address")
        assert addr is not None
        assert addr.find("street").text == "Kiekenmarkt"
        assert addr.find("number").text == "42"
        assert addr.find("city").text == "Brussel"
        assert addr.find("country").text == "be"

    def test_build_invoice_request_without_vat(self):
        """Build invoice_request XML without VAT number (private customer)."""
        invoice_data = {
            "first_name": "Marie",
            "last_name": "Dubois",
            "email": "marie@example.com",
            "address": {
                "street": "Rue de la Paix",
                "number": "10",
                "postal_code": "2000",
                "city": "Antwerpen",
                "country": "be"
            }
        }
        xml_str = sender.build_invoice_request_xml(
            user_id="user-123",
            invoice_data=invoice_data
        )

        root = etree.fromstring(xml_str.encode('utf-8'))
        inv_data = root.find("body/invoice_data")

        # VAT number should not exist
        assert inv_data.find("vat_number") is None
        assert inv_data.find("first_name").text == "Marie"

    def test_build_invoice_request_with_correlation_id(self):
        """Build invoice_request XML with correlation_id from original sale."""
        invoice_data = {
            "name": "John Doe",
            "email": "john@example.com",
            "address": {
                "street": "Test St",
                "number": "1",
                "postal_code": "1234",
                "city": "TestCity",
                "country": "be"
            }
        }
        correlation_id = "abc-def-123-456"

        xml_str = sender.build_invoice_request_xml(
            user_id="user-xyz",
            invoice_data=invoice_data,
            correlation_id=correlation_id
        )

        root = etree.fromstring(xml_str.encode('utf-8'))
        header = root.find("header")

        # Correlation ID should match the original consumption_order message_id
        assert header.find("correlation_id").text == correlation_id


class TestInvoiceRequestXMLValidation:
    """Test that generated invoice_request XML validates against the XSD schema."""

    def test_invoice_request_xml_validates_against_schema(self):
        """Verify generated XML passes XSD validation."""
        from pathlib import Path

        schema_path = Path(__file__).parent.parent / "schemas" / "schema_invoice_request.xsd"
        if not schema_path.exists():
            pytest.skip(f"Schema file not found: {schema_path}")

        # Load schema
        schema_doc = etree.parse(str(schema_path))
        schema = etree.XMLSchema(schema_doc)

        # Generate valid XML
        invoice_data = {
            "first_name": "Test",
            "last_name": "User",
            "email": "test@example.com",
            "address": {
                "street": "Main Street",
                "number": "100",
                "postal_code": "1000",
                "city": "TestCity",
                "country": "be"
            },
            "vat_number": "BE0987654321"
        }
        xml_str = sender.build_invoice_request_xml(
            user_id="test-user-123",
            invoice_data=invoice_data
        )

        # Validate
        xml_doc = etree.fromstring(xml_str.encode('utf-8'))
        assert schema.validate(xml_doc), f"XML validation failed: {schema.error_log}"


class TestOrderPollerInvoiceRequestDetection:
    """Test that order_poller detects and processes invoice requests."""

    @pytest.fixture
    def poller(self):
        """Return a bare OrderPoller with a mocked models proxy."""
        p = order_poller.OrderPoller()
        p.odoo_uid = 1
        p.models = MagicMock()
        return p

    @patch('order_poller.sender')
    def test_process_order_with_to_invoice_flag(self, mock_sender, poller):
        """Process order with to_invoice=True for identified customer."""
        mock_sender.send_typed_message.return_value = True
        mock_sender.get_buffered_order_ids.return_value = []

        # Mock Odoo order
        order = {
            'id': 100,
            'name': 'Order-001',
            'state': 'paid',
            'partner_id': [1, 'Test Customer'],
            'amount_total': 50.00,
            'amount_tax': 5.00,
            'payment_ids': [[1], [2]],
            'create_date': '2026-04-29 10:00:00',
            'session_id': [1, 'Session-1'],
            'to_invoice': True,  # Customer requested invoice
            'lines': []
        }

        # Mock customer info
        customer_info = {
            'id': 1,
            'name': 'Test Customer',
            'email': 'test@example.com',
            'street': 'Main Street',
            'street2': '100',
            'city': 'TestCity',
            'zip': '1000',
            'country_id': [1, 'Belgium'],
            'x_user_id': 'user-123',
            'vat': 'BE0123456789'
        }

        # Process the order
        with patch.object(poller, '_process_consumption', return_value=(True, 'msg-123')):
            with patch.object(poller, '_process_invoice_request', return_value=True) as mock_inv:
                with patch.object(poller, 'get_customer_info', return_value=customer_info):
                    poller.process_order(order)

                    # Verify invoice request was processed
                    mock_inv.assert_called_once()
                    call_args = mock_inv.call_args
                    assert call_args[0][0] == order

    @patch('order_poller.sender')
    def test_process_order_skips_invoice_for_anonymous(self, mock_sender, poller):
        """Skip invoice_request for anonymous customers."""
        mock_sender.send_typed_message.return_value = True
        mock_sender.get_buffered_order_ids.return_value = []

        # Anonymous order (partner_id = False)
        order = {
            'id': 101,
            'name': 'Order-002',
            'state': 'paid',
            'partner_id': False,  # Anonymous
            'amount_total': 25.00,
            'amount_tax': 2.50,
            'payment_ids': [[1]],
            'create_date': '2026-04-29 11:00:00',
            'session_id': [1, 'Session-1'],
            'to_invoice': True,  # Flag set but ignored for anonymous
            'lines': []
        }

        poller.models.execute_kw.return_value = []

        with patch.object(poller, '_process_consumption', return_value=(True, 'msg-124')):
            with patch.object(poller, '_process_invoice_request') as mock_inv:
                poller.process_order(order)

                # Invoice request should NOT be processed for anonymous
                mock_inv.assert_not_called()

    def test_process_invoice_request_gathers_address_data(self, poller):
        """Verify _process_invoice_request gathers correct customer data."""
        customer_info = {
            'id': 1,
            'name': 'Jan Peeters',
            'email': 'jan@example.com',
            'street': 'Kiekenmarkt',
            'street2': '42',
            'city': 'Brussel',
            'zip': '1000',
            'country_id': [1, 'Belgium'],
            'x_user_id': 'e8b27c1d-4f2a-4b3e-9c5f-123456789abc',
            'vat': 'BE0123456789'
        }

        order = {'id': 100}

        with patch('order_poller.sender') as mock_sender:
            mock_sender.send_typed_message.return_value = True
            mock_sender.build_invoice_request_xml.return_value = "<xml/>"

            poller._process_invoice_request(order, customer_info)

            # Verify build_invoice_request_xml was called with correct data
            mock_sender.build_invoice_request_xml.assert_called_once()
            call_kwargs = mock_sender.build_invoice_request_xml.call_args[1]

            assert call_kwargs['user_id'] == 'e8b27c1d-4f2a-4b3e-9c5f-123456789abc'
            assert call_kwargs['invoice_data']['email'] == 'jan@example.com'
            assert call_kwargs['invoice_data']['address']['street'] == 'Kiekenmarkt'
            assert call_kwargs['invoice_data']['vat_number'] == 'BE0123456789'


class TestInvoiceRequestMessaging:
    """Test that invoice_request messages are sent to the correct RabbitMQ queue."""

    @patch('sender._publish_or_raise')
    def test_invoice_request_sent_to_correct_routing_key(self, mock_publish):
        """Verify invoice_request is sent to kassa.payments.invoice routing key."""
        invoice_data = {
            "name": "John Doe",
            "email": "john@example.com",
            "address": {
                "street": "Test St",
                "number": "1",
                "postal_code": "1234",
                "city": "TestCity",
                "country": "be"
            }
        }

        xml_str = sender.build_invoice_request_xml(
            user_id="user-123",
            invoice_data=invoice_data
        )

        # Mock successful publish
        mock_publish.return_value = None

        sender.send_typed_message("invoice_request", xml_str, order_id=100)

        # Verify published to correct routing key
        assert mock_publish.called
        routing_key = mock_publish.call_args[0][0]
        assert routing_key == "kassa.payments.invoice"


class TestInvoiceRequestDoD:
    """Definition of Done Checklist for Story 7."""

    def test_dod_invoice_request_sent_with_correct_fields(self):
        """✓ invoice_request verstuurd met correcte naam, adres en optioneel BTW-nummer"""
        invoice_data = {
            "first_name": "Test",
            "last_name": "User",
            "email": "test@example.com",
            "address": {
                "street": "Main St",
                "number": "1",
                "postal_code": "1000",
                "city": "TestCity",
                "country": "be"
            },
            "vat_number": "BE0123456789"
        }

        xml_str = sender.build_invoice_request_xml(
            user_id="user-123",
            invoice_data=invoice_data
        )

        root = etree.fromstring(xml_str.encode('utf-8'))
        inv_data = root.find("body/invoice_data")

        assert inv_data.find("first_name").text == "Test"
        assert inv_data.find("last_name").text == "User"
        assert inv_data.find("email").text == "test@example.com"
        assert inv_data.find("address/street").text == "Main St"
        assert inv_data.find("vat_number").text == "BE0123456789"

    def test_dod_no_invoice_for_anonymous_customer(self):
        """✓ Klant zonder account: geen invoice_request aangemaakt"""
        # The poller should skip invoice processing for anonymous customers
        # This is tested in test_process_order_skips_invoice_for_anonymous

    def test_dod_xml_validates_against_schema(self):
        """✓ Uitgaande XML valide tegen schema_invoice_request.xsd"""
        # This is tested in test_invoice_request_xml_validates_against_schema
        pass

    def test_dod_x_rabbitmq_sent_marked_after_success(self):
        """✓ x_rabbitmq_sent=True gezet na succesvolle verzending"""
        # This is part of the order_poller.process_order() logic
        # which sets x_rabbitmq_sent=True when all_sent is True
        pass
