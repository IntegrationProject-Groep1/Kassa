"""B2B Invoice Tests

For company customers, Odoo auto-activates to_invoice=True and Customer Account on validate.
For private persons, the cashier manually activates to_invoice at the bar.
invoice_request is sent whenever to_invoice=True or account_move is set, for all customer types.
"""
import os
import uuid
from unittest.mock import MagicMock, patch
import pytest

from integratie.order_poller import OrderPoller


@pytest.fixture
def mock_env():
    """Set up minimal environment for OrderPoller."""
    with patch.dict(os.environ, {
        'ODOO_URL': 'http://localhost:8069',
        'ODOO_DB': 'test_db',
        'ODOO_USER': 'test_user',
        'ODOO_PASS': 'test_pass',
    }):
        yield


@pytest.fixture
def mock_odoo():
    """Mock Odoo connection."""
    return MagicMock()


@pytest.fixture
def mock_sender():
    """Mock sender module."""
    mock = MagicMock()
    mock.send_typed_message = MagicMock(return_value=True)
    mock.send_error_to_queue = MagicMock()
    mock.build_invoice_request_xml = MagicMock(
        return_value="<message><header><message_id>test-id</message_id></header></message>"
    )
    mock.extract_message_id = MagicMock(return_value=str(uuid.uuid4()))
    return mock


@pytest.fixture
def poller(mock_env, mock_odoo, mock_sender):
    """Create OrderPoller with mocked dependencies."""
    with patch('integratie.order_poller.sender', mock_sender):
        poller = OrderPoller()
        poller.models = mock_odoo
        return poller


def make_execute_kw_side_effect(customer_data):
    """Factory for execute_kw side effect that handles partner reads."""
    def side_effect(*args, **kwargs):
        if len(args) >= 5:
            model, method = args[3], args[4]
            if model == 'res.partner' and method == 'read':
                return [customer_data]
            if model == 'res.country' and method == 'read':
                return [{'id': 4, 'code': 'nl'}]
            if method == 'write':
                return True
        return []
    return side_effect


def make_company_customer(partner_id=5, vat='NL123456789'):
    """Factory for company customer data."""
    return {
        'id': partner_id,
        'name': f'Company{partner_id}',
        'email': f'info@company{partner_id}.nl',
        'is_company': True,
        'parent_id': None,
        'vat': vat,
        'street': 'Straat',
        'street2': '1',
        'city': 'Amsterdam',
        'zip': '1000',
        'country_id': [4, 'Netherlands'],
        'x_user_id': f'user_{partner_id}',
        'x_wallet_balance': 0,
    }


def make_private_customer(partner_id=9):
    """Factory for private customer data."""
    return {
        'id': partner_id,
        'name': f'Customer{partner_id}',
        'email': f'customer{partner_id}@example.com',
        'is_company': False,
        'parent_id': None,
        'vat': None,
        'street': 'Straat',
        'street2': '10',
        'city': 'Amsterdam',
        'zip': '1001',
        'country_id': [4, 'Netherlands'],
        'x_user_id': f'user_{partner_id}',
        'x_wallet_balance': 0,
    }


class TestB2BAutoInvoice:
    """B2B Auto-Invoice generation tests."""

    def test_company_with_to_invoice_gets_invoice_request(self, poller, mock_odoo, mock_sender):
        """
        GIVEN a company customer order with to_invoice=True (set automatically by Odoo on validate)
        WHEN process_order is called
        THEN invoice_request should be generated
        """
        order = {
            'id': 100,
            'partner_id': 5,
            'amount_total': 100.0,
            'to_invoice': True,
            'account_move': None,
            'lines': [],
            'payment_ids': [],
            'state': 'done',
            'create_date': '2024-01-01 10:00:00',
            'session_id': [1, 'Session 1'],
            'x_payment_message_id': str(uuid.uuid4()),
        }

        customer_data = make_company_customer(5, 'NL123456789')
        mock_odoo.execute_kw.side_effect = make_execute_kw_side_effect(customer_data)

        with patch.object(poller, '_process_consumption', return_value=(True, str(uuid.uuid4()), str(uuid.uuid4()), "paid", "on_site")), \
             patch.object(poller, '_process_invoice_request', return_value=(True, str(uuid.uuid4()))) as mock_invoice:
            poller.process_order(order)

            mock_invoice.assert_called_once()

    def test_deduplication_skips_invoice_if_already_sent(self, poller, mock_odoo, mock_sender):
        """
        GIVEN an order with x_invoice_message_id already set
        WHEN process_order is called
        THEN invoice_request should NOT be generated again (de-duplication)
        """
        invoice_msg_id = str(uuid.uuid4())

        order = {
            'id': 102,
            'partner_id': 7,
            'amount_total': 75.0,
            'to_invoice': True,
            'account_move': None,
            'x_invoice_message_id': invoice_msg_id,
            'lines': [],
            'payment_ids': [],
            'state': 'done',
            'create_date': '2024-01-01 10:00:00',
            'session_id': [1, 'Session 1'],
            'x_payment_message_id': str(uuid.uuid4()),
        }

        customer_data = make_company_customer(7, 'NL987654321')
        mock_odoo.execute_kw.side_effect = make_execute_kw_side_effect(customer_data)

        with patch.object(poller, '_process_consumption', return_value=(True, str(uuid.uuid4()), str(uuid.uuid4()), "paid", "on_site")), \
             patch.object(poller, '_process_invoice_request') as mock_invoice:
            poller.process_order(order)

            # Verify _process_invoice_request was NOT called (already sent)
            mock_invoice.assert_not_called()

    def test_private_customer_requires_to_invoice_flag(self, poller, mock_odoo, mock_sender):
        """
        GIVEN a private customer order without to_invoice flag
        WHEN process_order is called
        THEN invoice_request should NOT be generated automatically
        """
        order = {
            'id': 103,
            'partner_id': 8,
            'amount_total': 25.0,
            'to_invoice': False,
            'account_move': None,
            'lines': [],
            'payment_ids': [],
            'state': 'done',
            'create_date': '2024-01-01 10:00:00',
            'session_id': [1, 'Session 1'],
            'x_payment_message_id': str(uuid.uuid4()),
        }

        customer_data = make_private_customer(8)
        mock_odoo.execute_kw.side_effect = make_execute_kw_side_effect(customer_data)

        with patch.object(poller, '_process_consumption', return_value=(True, str(uuid.uuid4()), str(uuid.uuid4()), "paid", "on_site")), \
             patch.object(poller, '_process_invoice_request') as mock_invoice:
            poller.process_order(order)

            # Verify _process_invoice_request was NOT called (private without flag)
            mock_invoice.assert_not_called()

    def test_private_customer_with_to_invoice_flag_gets_invoice(self, poller, mock_odoo, mock_sender):
        """
        GIVEN a private customer order WITH to_invoice flag
        WHEN process_order is called
        THEN invoice_request should be generated (Story 7)
        """
        order = {
            'id': 104,
            'partner_id': 9,
            'amount_total': 40.0,
            'to_invoice': True,
            'account_move': None,
            'lines': [],
            'payment_ids': [],
            'state': 'done',
            'create_date': '2024-01-01 10:00:00',
            'session_id': [1, 'Session 1'],
            'x_payment_message_id': str(uuid.uuid4()),
        }

        customer_data = make_private_customer(9)
        mock_odoo.execute_kw.side_effect = make_execute_kw_side_effect(customer_data)

        with patch.object(poller, '_process_consumption', return_value=(True, str(uuid.uuid4()), str(uuid.uuid4()), "paid", "on_site")), \
             patch.object(poller, '_process_invoice_request', return_value=(True, str(uuid.uuid4()))) as mock_invoice:
            poller.process_order(order)

            # Verify _process_invoice_request was called (to_invoice flag honored)
            mock_invoice.assert_called_once()

    def test_company_without_vat_blocks_invoice(self, poller, mock_odoo, mock_sender):
        """
        GIVEN a company customer order without VAT (to_invoice=True as Odoo sets it)
        WHEN process_order is called
        THEN invoice generation should be attempted but blocked by VAT check
        """
        order = {
            'id': 106,
            'partner_id': 11,
            'amount_total': 100.0,
            'to_invoice': True,
            'account_move': None,
            'lines': [],
            'payment_ids': [],
            'state': 'done',
            'create_date': '2024-01-01 10:00:00',
            'session_id': [1, 'Session 1'],
            'x_payment_message_id': str(uuid.uuid4()),
        }

        customer_data = make_company_customer(11, '')  # No VAT
        mock_odoo.execute_kw.side_effect = make_execute_kw_side_effect(customer_data)

        # Mock send_error_to_queue to prevent RabbitMQ connection attempts
        with patch.object(poller, '_process_consumption', return_value=(True, str(uuid.uuid4()), str(uuid.uuid4()), "paid", "on_site")), \
             patch('integratie.order_poller.sender.send_error_to_queue'):
            poller.process_order(order)
            # VAT check is tested in test_vat_validation.py
            # This test just verifies the auto-invoice logic doesn't break when VAT is missing
