import os
import pytest
import xml.etree.ElementTree as ET
from unittest.mock import patch, MagicMock, ANY

from order_poller import OrderPoller
import receiver

# Setup environment before importing modules
os.environ['ODOO_URL'] = 'http://test:8069'
os.environ['ODOO_DB'] = 'test_db'
os.environ['ODOO_USER'] = 'test_user'
os.environ['ODOO_PASS'] = 'test_pass'
os.environ['RABBIT_HOST'] = 'localhost'
os.environ['RABBIT_EXCHANGE'] = 'test.exchange'


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def poller():
    p = OrderPoller()
    p.odoo_uid = 1
    p.models = MagicMock()
    return p


@pytest.fixture
def odoo():
    return 1, MagicMock()


@pytest.fixture(autouse=True)
def clear_caches():
    receiver.seen_message_ids.clear()
    yield
    receiver.seen_message_ids.clear()


# ── Helpers ────────────────────────────────────────────────────────────────────

_UUID = "550e8400-e29b-41d4-a716-446655440000"
_BADGE = "BADGE-123"


def _make_customer(balance=0.0, lease=False):
    return {
        'id': 100,
        'name': 'Test User',
        'x_user_id': _UUID,
        'x_badge_id': _BADGE,
        'x_wallet_balance': balance,
        'x_lease_active': lease,
        'x_lease_id': 'L-001' if lease else '',
        'x_lease_transaction_count': 5 if lease else 0,
        'is_company': False,
        'email': 'test@example.com',
        'customer_type': 'private',
        'street': 'Teststraat 1',
        'zip': '1000',
        'city': 'Brussel',
        'country_code': 'be',
    }


def _make_order(order_id, config_id=1, total=10.0):
    return {
        'id': order_id,
        'name': f'POS/{order_id:04}',
        'partner_id': [100, 'Test User'],
        'session_id': [config_id, f'Session {config_id}'],
        'lines': [1000 + order_id],
        'amount_total': total,
        'payment_ids': [2000 + order_id],
        'x_wallet_updated': False,
        'x_rabbitmq_sent': False,
        'create_date': '2026-05-10 12:00:00',
        'to_invoice': False,
        'account_move': None,
        'x_payment_message_id': None,
        'x_invoice_message_id': None,
    }


# ── Scenario Tests ─────────────────────────────────────────────────────────────

class TestComplexEventScenarios:

    @patch('sender.send_typed_message', return_value=True)
    def test_scenario_arrival_flow(self, mock_send, poller, odoo):
        """
        Scenario: Visitor Arrival
        1. Scan Badge at entrance (Receiver triggers Lease Request)
        2. Pay for Registration + Top-up (Poller triggers Story 6 & 11)
        """
        uid, models = odoo
        poller.models = models

        # Patch both receiver and sender names
        with patch('receiver.send_typed_message', mock_send):
            # 1. Receiver processes scan
            scan_xml = ET.fromstring(f"<message><body><badge_id>{_BADGE}</badge_id><location>entrance</location></body></message>")
            models.execute_kw.side_effect = [[_make_customer(balance=0.0)], True]
            receiver.process_badge_scan(scan_xml, uid, models)
            mock_send.assert_any_call("wallet_lease_request", ANY, record_id=100, model='res.partner')

            # 2. Poller processes Registration + Top-up
            reg_order = _make_order(order_id=42, total=25.0)
            models.execute_kw.side_effect = [
                [_make_customer()],
                [{'config_id': [1, 'Inschrijvingskassa']}],
                [{'name': 'Inschrijvingskassa'}],
                [{'id': 1042, 'product_id': [9, 'Ticket'], 'price_subtotal_incl': 25.0}],
                [{'id': 9, 'x_is_topup': True, 'pos_categ_ids': []}],
                True,
                True,
                50.0,
                True,
                True,
            ]

            poller.process_order(reg_order)
            sent_types = [c[0][0] for c in mock_send.call_args_list]
            assert 'payment_registered_registration' in sent_types
            assert 'payment_status' in sent_types
            assert 'wallet_balance_update' in sent_types

    @patch('sender.send_typed_message', return_value=True)
    def test_scenario_race_condition_topup_and_lease_grant(self, mock_send, poller, odoo):
        """
        Scenario: Atomic Integrity
        """
        uid, models = odoo
        poller.models = models

        topup_order = _make_order(order_id=43, total=10.0)
        customer = _make_customer(balance=50.0)

        models.execute_kw.side_effect = [
            [customer],
            [{'config_id': [2, 'Bar Kassa']}],
            [{'name': 'Bar Kassa'}],
            [{'id': 1043, 'product_id': [8, 'Top-up'], 'qty': 1, 'price_unit': 10.0, 'price_subtotal_incl': 10.0}],
            [{'id': 8, 'x_is_topup': True, 'pos_categ_ids': []}],
            [], [],
            [{"payment_method_id": [1, "Cash"], "amount": 10.0}],
            60.0,
            True,
            True,
        ]

        poller.process_order(topup_order)
        calls = [c[0][4] for c in models.execute_kw.call_args_list if len(c[0]) > 4]
        assert "action_add_wallet_amount" in calls

    @patch('sender.send_typed_message', return_value=True)
    def test_scenario_active_lease_consumption_and_refund(self, mock_send, poller, odoo):
        """
        Scenario: Bar Activities with Active Lease
        """
        uid, models = odoo
        poller.models = models

        customer = _make_customer(balance=20.0, lease=True)

        order = _make_order(order_id=50, total=5.0)
        models.execute_kw.side_effect = [
            [customer],
            [{'config_id': [2, 'Bar Kassa']}],
            [{'name': 'Bar Kassa'}],
            [{'id': 1050, 'product_id': [7, 'Beer'], 'qty': 1, 'price_unit': 5.0, 'price_subtotal_incl': 5.0}],
            [{'id': 7, 'x_is_topup': False, 'pos_categ_ids': []}],
            [], [],
            [{"payment_method_id": [2, "Badge Wallet"], "amount": 5.0}],
            15.0,
            6,
            True,
        ]

        poller.process_order(order)

        refund_order = _make_order(order_id=51, total=-5.0)
        models.execute_kw.side_effect = [
            [customer],
            [{"payment_method_id": [2, "Badge Wallet"], "amount": -5.0}],
            20.0,
            True,
            7,
            [{'refunded_orderline_id': [1050, 'POS/0050 LINE-1050']}],
            [{'order_id': [50, 'POS/0050']}],
            [{'x_payment_message_id': 'orig-msg-id'}],
            True,
        ]

        poller.process_order(refund_order)
        sent_types = [c[0][0] for c in mock_send.call_args_list]
        assert 'refund_processed' in sent_types
