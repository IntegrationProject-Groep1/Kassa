import os
import pytest
import xml.etree.ElementTree as ET
from unittest.mock import patch, MagicMock, ANY

from order_poller import OrderPoller
import receiver

# Setup environment
os.environ['ODOO_URL'] = 'http://test:8069'
os.environ['ODOO_DB'] = 'test_db'
os.environ['ODOO_USER'] = 'test_user'
os.environ['ODOO_PASS'] = 'test_pass'
os.environ['RABBIT_HOST'] = 'localhost'
os.environ['RABBIT_EXCHANGE'] = 'test.exchange'


class OdooMock:
    def __init__(self):
        self.customer = {
            'id': 200, 'name': 'B2B', 'x_user_id': 'u-b2b',
            'is_company': True, 'parent_id': False, 'country_id': False,
            'email': 'b2b@test.com', 'x_badge_id': '', 'x_wallet_balance': 0.0,
            'x_lease_active': False, 'x_lease_id': '', 'x_lease_transaction_count': 0,
            'vat': 'BE0123456789', 'street': 'Test St 1', 'city': 'Brussels', 'zip': '1000',
        }
        self.config_name = "Bar Kassa"
        self.original_msg_id = "ORIG-123"
        self.call_log = []

    def execute_kw(self, db, uid, pw, model, method, *args, **kwargs):
        self.call_log.append((model, method))
        if model == 'res.partner' and method in ('search_read', 'read'):
            return [self.customer] if self.customer else []
        if method == 'read' and model == 'pos.session':
            return [{'config_id': [1, 'C1']}]
        if method == 'read' and model == 'pos.config':
            return [{'name': self.config_name}]
        if method == 'read' and model == 'pos.order.line':
            fields = args[0][1] if args and len(args[0]) > 1 else []
            if isinstance(fields, list) and 'refunded_orderline_id' in fields:
                return [{'refunded_orderline_id': [1101, 'L1']}]
            if isinstance(fields, list) and fields == ['order_id']:
                return [{'order_id': [99, 'ORIG']}]
            return [{'id': 1, 'product_id': [1, 'P1'], 'qty': 1, 'price_unit': 10, 'price_subtotal_incl': 10}]
        if method == 'read' and model == 'product.product':
            return [{'id': 1, 'x_is_topup': False, 'pos_categ_ids': []}]
        if method == 'read' and model == 'pos.payment':
            return [{'id': 2001, 'payment_method_id': [2, 'Cash'], 'amount': 10.0}]
        if method == 'read' and model == 'pos.order':
            return [{'x_payment_message_id': self.original_msg_id, 'order_id': [99, 'ORIG']}]
        if method == 'search_read' and model == 'pos.order.line':
            return [{'refunded_orderline_id': [1101, 'L1']}]
        if method == 'read' and model == 'res.country':
            return [{'id': 1, 'code': 'be'}]
        if method in ('action_add_wallet_amount', 'action_process_wallet_payment'):
            return 15.0
        return True


@pytest.fixture
def poller():
    p = OrderPoller()
    p.models = OdooMock()
    p._customer_cache = {}
    p._session_config_cache = {}
    return p


def _make_order(order_id, partner_id=200, total=10.0, is_refund=False):
    return {
        'id': order_id, 'name': f'POS/{order_id:04}',
        'partner_id': [partner_id, 'User'] if partner_id else False,
        'session_id': [1, 'S1'], 'lines': [1000 + order_id],
        'amount_total': -abs(total) if is_refund else abs(total),
        'payment_ids': [2000 + order_id],
        'x_wallet_updated': False, 'x_rabbitmq_sent': False,
        'create_date': '2026-05-10 14:00:00', 'to_invoice': False,
    }


class TestSystemicInteractions:

    @patch('order_poller.sender.send_typed_message', return_value=True)
    @patch('order_poller.sender.build_refund_processed_xml', return_value="<r/>")
    def test_refund_traceability_logic(self, mock_build, mock_send, poller):
        # Process a refund order
        poller.process_order(_make_order(order_id=102, is_refund=True))

        # Verify that traceability info was found and passed to builder
        mock_build.assert_called_with(
            original_payment_msg_id="ORIG-123",
            refund_type=ANY, refund_amount=ANY, refund_method=ANY,
            refund_reason=ANY, original_transaction_id=ANY,
            identity_uuid=ANY, is_anonymous=ANY, email=ANY, items=ANY
        )

    @patch('order_poller.sender.send_typed_message', return_value=True)
    @patch('order_poller.sender.build_consumption_order_xml', return_value="<c/>")
    def test_anonymous_flow_logic(self, mock_build, mock_send, poller):
        poller.models.customer = None  # Force anonymous
        poller.process_order(_make_order(order_id=201, partner_id=False))

        mock_build.assert_called_with(
            items=ANY, customer_id=None, identity_uuid=None,
            customer_type="anonymous", email=None, address=None, is_anonymous=True,
            company_name=None, vat_number=None
        )

    @patch('order_poller.sender.send_typed_message', return_value=True)
    @patch('order_poller.sender.build_invoice_request_xml', return_value="<inv/>")
    @patch('order_poller.sender.build_consumption_order_xml', return_value="<c/>")
    @patch('order_poller.sender.build_payment_registered_xml', return_value="<p/>")
    def test_invoice_sent_when_to_invoice_true(self, mock_p, mock_c, mock_build_inv, mock_send, poller):
        # Odoo sets to_invoice=True automatically for company orders on validate
        order = {**_make_order(order_id=401), 'to_invoice': True, 'account_move': None,
                 'x_invoice_message_id': None, 'x_rabbitmq_error': ''}
        poller.process_order(order)
        assert mock_build_inv.called

    def test_cancel_registration_rpc(self):
        models = MagicMock()
        models.execute_kw.return_value = [{'id': 200}]
        cancel_xml = ET.fromstring("<message><body><identity_uuid>u1</identity_uuid></body></message>")
        receiver.process_cancel_registration(cancel_xml, 1, models)
        # Verify registration cancellation fields written
        models.execute_kw.assert_any_call(
            ANY, ANY, ANY, 'res.partner', 'write',
            [[200], {
                "x_outstanding_amount": 0.0,
                "x_payment_status": "cancelled",
            }]
        )
        # Verify bus event published
        models.execute_kw.assert_any_call(
            ANY, ANY, ANY, 'pos.order', 'send_partner_bus_event',
            [200, 0.0, 'cancelled', ANY]
        )
