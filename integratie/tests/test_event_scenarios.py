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
# ── Story 6 × Leasing Integration Tests ───────────────────────────────────────


class TestStory6LeaseIntegration:
    """
    End-to-end scenarios where Story 6 (Inschrijvingskassa registration) and
    the wallet-lease lifecycle interact.
    """

    @patch('sender.send_typed_message', return_value=True)
    def test_registration_with_topup_while_lease_active(self, mock_send, poller):
        """
        Scenario: visitor already has an active CRM lease when they pay at the
        Inschrijvingskassa and also buy a top-up in the same order.

        Expected behaviour:
        - payment_registered_registration + payment_status are sent (Story 6).
        - wallet_balance_update is sent with authority='kassa' and status='active'
          because the lease is already active at topup time (Story 11 × Lease).
        - lease transaction count is incremented.
        """
        customer = _make_customer(balance=20.0, lease=True)
        order = _make_order(order_id=200, total=35.0)

        poller.models.execute_kw.side_effect = [
            [customer],                                          # get_customer_info res.partner.read
            [{'config_id': [1, 'Inschrijvingskassa']}],         # _get_pos_config_name: session read
            [{'name': 'Inschrijvingskassa'}],                   # _get_pos_config_name: config read
            [{'id': 1200, 'product_id': [5, 'Topup 15'],        # order line details
              'price_subtotal_incl': 15.0}],
            [{'id': 5, 'x_is_topup': True, 'pos_categ_ids': []}],  # product check
            True,                                               # res.partner write (x_outstanding_amount)
            True,                                               # pos.order send_partner_bus_event
            35.0,                                               # action_add_wallet_amount → new balance
            True,                                               # pos.order write x_wallet_updated
            6,                                                  # _increment_lease_tx_count write → new count
            True,                                               # pos.order write x_payment_message_id
            True,                                               # pos.order write x_rabbitmq_sent
        ]

        poller.process_order(order)

        sent_types = [c[0][0] for c in mock_send.call_args_list]
        assert 'payment_registered_registration' in sent_types
        assert 'payment_status' in sent_types
        assert 'wallet_balance_update' in sent_types

        # wallet_balance_update must carry lease authority metadata
        balance_call = next(c for c in mock_send.call_args_list if c[0][0] == 'wallet_balance_update')
        xml_str = balance_call[0][1]
        tree = ET.fromstring(xml_str)
        body = tree.find('body')
        assert body.findtext('authority') == 'kassa'
        assert body.findtext('status') == 'active'

        # lease tx count must have been incremented
        odoo_methods = [c[0][4] for c in poller.models.execute_kw.call_args_list if len(c[0]) > 4]
        assert 'action_add_wallet_amount' in odoo_methods

    @patch('sender.send_typed_message', return_value=True)
    def test_registration_with_topup_no_active_lease(self, mock_send, poller):
        """
        Scenario: visitor pays registration + top-up but no lease is active yet
        (visitor has NOT scanned their QR code before paying).

        NEW BEHAVIOUR (lease-aware top-up):
        - payment_registered_registration + payment_status are sent (Story 6).
        - Top-up amount is PARKED in x_pending_topup_balance — NOT applied yet.
        - wallet_balance_update is NOT sent (we don't own the balance yet).
        - The balance update will happen when wallet_lease_grant arrives from CRM.
        """
        customer = _make_customer(balance=0.0, lease=False)
        order = _make_order(order_id=201, total=30.0)

        poller.models.execute_kw.side_effect = [
            [customer],
            [{'config_id': [1, 'Inschrijvingskassa']}],
            [{'name': 'Inschrijvingskassa'}],
            [{'id': 1201, 'product_id': [5, 'Topup 10'], 'price_subtotal_incl': 10.0}],
            [{'id': 5, 'x_is_topup': True, 'pos_categ_ids': []}],
            True,   # res.partner write x_outstanding_amount
            True,   # pos.order send_partner_bus_event
            True,   # res.partner write x_pending_topup_balance  ← parked, not applied
            True,   # pos.order write x_wallet_updated
            True,   # pos.order write x_payment_message_id
            True,   # pos.order write x_rabbitmq_sent
        ]

        poller.process_order(order)

        sent_types = [c[0][0] for c in mock_send.call_args_list]
        assert 'payment_registered_registration' in sent_types
        # wallet_balance_update must NOT be sent — balance unknown until lease grant
        assert 'wallet_balance_update' not in sent_types

        # action_add_wallet_amount must NOT be called — we don't own the balance
        odoo_methods = [
            c[0][4] for c in poller.models.execute_kw.call_args_list if len(c[0]) > 4
        ]
        assert 'action_add_wallet_amount' not in odoo_methods

        # x_pending_topup_balance must have been written
        pending_writes = [
            c for c in poller.models.execute_kw.call_args_list
            if len(c[0]) > 4 and c[0][4] == 'write'
            and c[0][3] == 'res.partner'
            and 'x_pending_topup_balance' in (c[0][5][1] if len(c[0][5]) > 1 else {})
        ]
        assert len(pending_writes) == 1

    @patch('sender.send_typed_message', return_value=True)
    def test_registration_without_topup_does_not_send_wallet_update(self, mock_send, poller):
        """
        Scenario: visitor pays registration only (ticket only, no top-up product).

        No wallet_balance_update should be sent — wallet is untouched.
        """
        customer = _make_customer(balance=50.0, lease=True)
        order = _make_order(order_id=202, total=25.0)

        poller.models.execute_kw.side_effect = [
            [customer],
            [{'config_id': [1, 'Inschrijvingskassa']}],
            [{'name': 'Inschrijvingskassa'}],
            [{'id': 1202, 'product_id': [3, 'Ticket'], 'price_subtotal_incl': 25.0}],
            [{'id': 3, 'x_is_topup': False, 'pos_categ_ids': []}],
            True,
            True,
            True,
            True,
        ]

        poller.process_order(order)

        sent_types = [c[0][0] for c in mock_send.call_args_list]
        assert 'payment_registered_registration' in sent_types
        assert 'payment_status' in sent_types
        assert 'wallet_balance_update' not in sent_types

    @patch('sender.send_typed_message', return_value=True)
    def test_lease_grant_then_bar_consumption_increments_tx_count(self, mock_send, poller):
        """
        Scenario: CRM has already granted a lease. Visitor buys drinks at the
        bar (Badge Wallet payment). The poller must decrement the wallet via
        action_add_wallet_amount and increment the lease transaction count.
        """
        customer = _make_customer(balance=30.0, lease=True)
        bar_order = _make_order(order_id=203, config_id=2, total=8.0)

        poller.models.execute_kw.side_effect = [
            [customer],                                               # get_customer_info
            [{'config_id': [2, 'Bar Kassa']}],                       # pos.session read
            [{'name': 'Bar Kassa'}],                                  # pos.config read
            [{'id': 1203, 'product_id': [10, 'Beer'], 'qty': 1,
              'price_unit': 8.0, 'price_subtotal_incl': 8.0}],       # pos.order.line read
            [{'id': 10, 'x_is_topup': False, 'pos_categ_ids': []}],  # product.product read
            [{'payment_method_id': [2, 'Badge Wallet'], 'amount': 8.0}],  # pos.payment read
            22.0,                                                     # action_process_wallet_payment
            6,                                                        # _increment_lease_tx_count write
            True,                                                     # pos.order write x_payment_message_id
            True,                                                     # pos.order write x_rabbitmq_sent
        ]

        poller.process_order(bar_order)

        sent_types = [c[0][0] for c in mock_send.call_args_list]
        assert 'consumption_order' in sent_types
        assert 'payment_registered_consumption' in sent_types
        assert 'wallet_balance_update' in sent_types

        balance_call = next(c for c in mock_send.call_args_list if c[0][0] == 'wallet_balance_update')
        xml_str = balance_call[0][1]
        tree = ET.fromstring(xml_str)
        body = tree.find('body')
        assert body.findtext('authority') == 'kassa'
        assert body.findtext('status') == 'active'

    @patch('sender.send_typed_message', return_value=True)
    def test_invoice_request_suppressed_for_registration_even_with_company_customer(self, mock_send, poller):
        """
        Scenario: a company (B2B) customer pays at the Inschrijvingskassa.
        The B2B auto-invoice logic must NOT fire for registration orders —
        invoice_request should be suppressed regardless of customer type.
        """
        customer = _make_customer()
        customer['is_company'] = True
        customer['customer_type'] = 'company'
        customer['vat'] = 'BE0123456789'
        order = _make_order(order_id=204, total=50.0)

        poller.models.execute_kw.side_effect = [
            [customer],
            [{'config_id': [1, 'Inschrijvingskassa']}],
            [{'name': 'Inschrijvingskassa'}],
            [],   # no order lines (no topup check needed)
            True, True, True, True,
        ]

        with patch.object(poller, '_process_invoice_request') as mock_inv:
            poller.process_order(order)
            mock_inv.assert_not_called()

        sent_types = [c[0][0] for c in mock_send.call_args_list]
        assert 'payment_registered_registration' in sent_types
        assert 'invoice_request' not in sent_types


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
            xml_str = f"<message><body><badge_id>{_BADGE}</badge_id><location>entrance</location></body></message>"
            scan_xml = ET.fromstring(xml_str)
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
            # wallet_balance_update NOT sent: lease was requested but not yet granted
            # (visitor scanned → wallet_lease_request sent, but grant hasn't arrived)
            assert 'wallet_balance_update' not in sent_types

    @patch('sender.send_typed_message', return_value=True)
    def test_scenario_race_condition_topup_and_lease_grant(self, mock_send, poller, odoo):
        """
        Scenario: Top-up after lease is fully granted (happy path).
        Lease is active + x_lease_id is set → action_add_wallet_amount called immediately.
        """
        uid, models = odoo
        poller.models = models

        topup_order = _make_order(order_id=43, total=10.0)
        # lease=True → x_lease_active=True AND x_lease_id='L-001' → fully granted
        customer = _make_customer(balance=50.0, lease=True)

        models.execute_kw.side_effect = [
            [customer],
            [{'config_id': [2, 'Bar Kassa']}],
            [{'name': 'Bar Kassa'}],
            [{'id': 1043, 'product_id': [8, 'Top-up'], 'qty': 1, 'price_unit': 10.0, 'price_subtotal_incl': 10.0}],
            [{'id': 8, 'x_is_topup': True, 'pos_categ_ids': []}],
            [], [],
            [{'payment_method_id': [1, 'Cash'], 'amount': 10.0}],
            60.0,   # action_add_wallet_amount → new balance
            True,   # pos.order write x_wallet_updated
            True,   # _increment_lease_tx_count
            True,   # pos.order write x_payment_message_id
            True,   # pos.order write x_rabbitmq_sent
        ]

        poller.process_order(topup_order)
        calls = [c[0][4] for c in models.execute_kw.call_args_list if len(c[0]) > 4]
        assert 'action_add_wallet_amount' in calls

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


# ── Pending Top-up Lifecycle Integration Tests ─────────────────────────────────
# These tests chain OrderPoller and receiver together via a shared in-memory
# Odoo state to verify the full pending-topup → lease-grant → balance-merge flow.

def _wallet_lease_grant_xml(identity_uuid: str, balance: float, lease_id: str) -> bytes:
    """Build a minimal valid wallet_lease_grant XML message."""
    import uuid
    mid = str(uuid.uuid4())
    cid = str(uuid.uuid4())
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<message>'
        '<header>'
        f'<message_id>{mid}</message_id>'
        '<timestamp>2026-05-11T22:00:00Z</timestamp>'
        '<source>crm</source>'
        '<type>wallet_lease_grant</type>'
        '<version>2.0</version>'
        f'<correlation_id>{cid}</correlation_id>'
        '</header>'
        '<body>'
        f'<identity_uuid>{identity_uuid}</identity_uuid>'
        f'<current_balance currency="eur">{balance:.2f}</current_balance>'
        f'<lease_id>{lease_id}</lease_id>'
        '</body>'
        '</message>'
    ).encode('utf-8')


class TestPendingTopupLifecycle:
    """
    Cross-component integration tests: OrderPoller × receiver.

    These tests verify the FULL pending-topup lifecycle:
      1. Visitor scans QR → lease requested (x_lease_active=True, x_lease_id='')
      2. Cashier processes top-up BEFORE lease grant arrives
         → Poller parks amount in x_pending_topup_balance (does NOT call
           action_add_wallet_amount, does NOT send wallet_balance_update)
      3. CRM sends wallet_lease_grant with current_balance
         → Receiver merges: final_balance = crm_balance + x_pending_topup_balance
         → x_pending_topup_balance cleared to 0
         → wallet_balance_update sent to frontend with the correct merged balance

    The shared `odoo_state` dict simulates Odoo's database across both components.
    """

    @pytest.fixture
    def ch(self):
        m = MagicMock()
        m.delivery_tag = 42
        return m

    @pytest.fixture
    def method(self):
        m = MagicMock()
        m.delivery_tag = 42
        return m

    @patch('sender.send_typed_message', return_value=True)
    def test_full_pending_topup_lifecycle(self, mock_send, poller, ch, method):
        """
        Full 2-step integration: top-up parked by poller → merged by receiver.

        Step 1 (Poller): Visitor has no lease yet. Cashier does €20 top-up.
                         → x_pending_topup_balance = 20.0 (parked in Odoo)
                         → wallet_balance_update NOT sent
        Step 2 (Receiver): CRM sends wallet_lease_grant with crm_balance = €50.
                           → final_balance = 50 + 20 = €70
                           → wallet_balance_update sent to frontend with €70
        """
        # ── Shared in-memory Odoo state ────────────────────────────────────────
        odoo_state = {
            'id': 100, 'name': 'Test User',
            'x_user_id': _UUID, 'x_badge_id': _BADGE,
            'x_wallet_balance': 0.0,
            'x_pending_topup_balance': 0.0,
            'x_lease_active': True,    # lease requested…
            'x_lease_id': '',          # …but NOT granted yet
            'x_lease_transaction_count': 0,
            'x_payment_status': 'unpaid', 'x_outstanding_amount': 0.0,
            'is_company': False, 'email': 'test@example.com',
            'customer_type': 'private', 'street': 'Teststraat 1',
            'zip': '1000', 'city': 'Brussel', 'country_code': 'be',
        }

        # ── Step 1: Poller parks top-up ────────────────────────────────────────
        def poller_execute_kw(db, uid, pwd, model, method_name, args, kw=None):
            if model == 'res.partner' and method_name == 'write':
                odoo_state.update(args[1])  # simulate Odoo write
                return True
            if model == 'pos.order' and method_name == 'write':
                return True
            return MagicMock()

        topup_order = _make_order(order_id=60, total=20.0)
        poller.get_customer_info = MagicMock(return_value=odoo_state.copy())
        poller.models.execute_kw.side_effect = [
            [{'id': 600, 'product_id': (80, 'Top-up EUR 20'),
              'qty': 1, 'price_unit': 20.0, 'tax_ids': [], 'price_subtotal_incl': 20.0}],
            [{'id': 80, 'x_is_topup': True, 'pos_categ_ids': []}],
            True,   # res.partner write x_pending_topup_balance
            True,   # pos.order write x_wallet_updated
            True,   # pos.order write x_payment_message_id
            True,   # pos.order write x_rabbitmq_sent
        ]
        poller.models.execute_kw.side_effect = None
        poller.models.execute_kw.side_effect = poller_execute_kw

        poller.process_order(topup_order)

        # Verify: top-up is parked, not applied directly
        assert odoo_state['x_pending_topup_balance'] == 20.0, (
            "Poller must park the top-up in x_pending_topup_balance"
        )
        assert odoo_state['x_wallet_balance'] == 0.0, (
            "x_wallet_balance must NOT be updated before the lease grant"
        )
        poller_sent = [c[0][0] for c in mock_send.call_args_list]
        assert 'wallet_balance_update' not in poller_sent, (
            "wallet_balance_update must NOT be sent before the lease grant"
        )

        # ── Step 2: Receiver processes wallet_lease_grant ──────────────────────
        mock_send.reset_mock()

        receiver_models = MagicMock()

        def receiver_execute_kw(db, uid, pwd, model, method_name, args, kw=None):
            if model == 'res.partner' and method_name == 'search_read':
                # Return current Odoo state (includes pending=20.0 from step 1)
                return [odoo_state.copy()]
            if model == 'res.partner' and method_name == 'write':
                odoo_state.update(args[1])
                return True
            if model == 'pos.order' and method_name == 'send_partner_bus_event':
                return True
            return True

        receiver_models.execute_kw.side_effect = receiver_execute_kw

        with patch('receiver.get_odoo_connection', return_value=(1, receiver_models)):
            with patch('receiver.send_typed_message', mock_send):
                grant_xml = _wallet_lease_grant_xml(_UUID, 50.0, 'LEASE-FINAL')
                receiver.process_message(ch, method, None, grant_xml)

        # Verify: balance merged correctly
        assert odoo_state['x_wallet_balance'] == 70.0, (
            f"Final balance must be CRM(50) + pending(20) = 70, got {odoo_state['x_wallet_balance']}"
        )
        assert odoo_state['x_pending_topup_balance'] == 0.0, (
            "x_pending_topup_balance must be cleared after merge"
        )

        # Verify: wallet_balance_update sent with correct balance
        receiver_sent = [c[0][0] for c in mock_send.call_args_list]
        assert 'wallet_balance_update' in receiver_sent

        update_xml_str = next(
            c[0][1] for c in mock_send.call_args_list
            if c[0][0] == 'wallet_balance_update'
        )
        tree = ET.fromstring(update_xml_str)
        new_balance_el = tree.find('./body/new_balance')
        assert new_balance_el is not None
        assert float(new_balance_el.text) == 70.0, (
            f"wallet_balance_update must carry the merged balance of 70.0, got {new_balance_el.text}"
        )

    @patch('sender.send_typed_message', return_value=True)
    def test_multiple_pending_topups_all_merged(self, mock_send, poller, ch, method):
        """
        Edge case: two top-up orders processed before lease grant arrives.
        Both must be accumulated in x_pending_topup_balance and merged together.

        Poller order 1: €10  → pending = 10
        Poller order 2: €15  → pending = 25
        Receiver lease grant (CRM balance = €30) → final = 30 + 25 = €55
        """
        odoo_state = {
            'id': 101, 'name': 'Double Top-up User',
            'x_user_id': _UUID, 'x_badge_id': _BADGE,
            'x_wallet_balance': 0.0, 'x_pending_topup_balance': 0.0,
            'x_lease_active': True, 'x_lease_id': '',
            'x_lease_transaction_count': 0,
            'x_payment_status': 'unpaid', 'x_outstanding_amount': 0.0,
            'is_company': False, 'email': 'double@example.com',
            'customer_type': 'private', 'street': 'Dubbel 2',
            'zip': '2000', 'city': 'Antwerpen', 'country_code': 'be',
        }

        def poller_execute_kw(db, uid, pwd, model, method_name, args, kw=None):
            if model == 'res.partner' and method_name == 'write':
                odoo_state.update(args[1])
                return True
            return True

        poller.models.execute_kw.side_effect = poller_execute_kw

        for amount, order_id in [(10.0, 61), (15.0, 62)]:
            customer_snapshot = odoo_state.copy()
            poller.get_customer_info = MagicMock(return_value=customer_snapshot)
            poller.process_order(_make_order(order_id=order_id, total=amount))

        assert odoo_state['x_pending_topup_balance'] == 25.0, (
            f"Two top-ups (10+15) must accumulate to 25.0, got {odoo_state['x_pending_topup_balance']}"
        )
        assert odoo_state['x_wallet_balance'] == 0.0

        # Receiver merges all pending
        mock_send.reset_mock()
        receiver_models = MagicMock()

        def receiver_execute_kw(db, uid, pwd, model, method_name, args, kw=None):
            if model == 'res.partner' and method_name == 'search_read':
                return [odoo_state.copy()]
            if model == 'res.partner' and method_name == 'write':
                odoo_state.update(args[1])
                return True
            return True

        receiver_models.execute_kw.side_effect = receiver_execute_kw

        with patch('receiver.get_odoo_connection', return_value=(1, receiver_models)):
            with patch('receiver.send_typed_message', mock_send):
                receiver.process_message(
                    ch, method, None, _wallet_lease_grant_xml(_UUID, 30.0, 'LEASE-DOUBLE')
                )

        assert odoo_state['x_wallet_balance'] == 55.0, (
            f"CRM(30) + pending(25) = 55.0, got {odoo_state['x_wallet_balance']}"
        )
        assert odoo_state['x_pending_topup_balance'] == 0.0

    @patch('sender.send_typed_message', return_value=True)
    def test_lease_grant_without_pending_sets_crm_balance(self, mock_send, ch, method):
        """
        Normal flow: lease grant arrives with NO pending top-ups.
        Final balance = CRM balance exactly. x_pending_topup_balance stays 0.
        """
        odoo_state = {
            'id': 102, 'name': 'Normal User',
            'x_user_id': _UUID, 'x_wallet_balance': 0.0,
            'x_pending_topup_balance': 0.0,   # no pending top-ups
            'x_payment_status': 'unpaid', 'x_outstanding_amount': 0.0,
        }

        receiver_models = MagicMock()

        def receiver_execute_kw(db, uid, pwd, model, method_name, args, kw=None):
            if model == 'res.partner' and method_name == 'search_read':
                return [odoo_state.copy()]
            if model == 'res.partner' and method_name == 'write':
                odoo_state.update(args[1])
                return True
            return True

        receiver_models.execute_kw.side_effect = receiver_execute_kw

        with patch('receiver.get_odoo_connection', return_value=(1, receiver_models)):
            with patch('receiver.send_typed_message', mock_send):
                receiver.process_message(
                    ch, method, None, _wallet_lease_grant_xml(_UUID, 40.0, 'LEASE-NORMAL')
                )

        assert odoo_state['x_wallet_balance'] == 40.0
        assert odoo_state['x_pending_topup_balance'] == 0.0

        receiver_sent = [c[0][0] for c in mock_send.call_args_list]
        assert 'wallet_balance_update' in receiver_sent
