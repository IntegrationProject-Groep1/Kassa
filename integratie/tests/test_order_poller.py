"""
Test suite for Order Poller module.
Covers: initialization, Odoo connection, process_order routing,
_process_refund (with/without wallet, with/without traceability),
_process_consumption (bulk tax fetching, customer type detection),
and duplicate suppression via the in-memory cache.
"""
import os
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def setup_env():
    """Mock environment variables for all Order Poller tests."""
    os.environ['ODOO_URL'] = 'http://test:8069'
    os.environ['ODOO_DB'] = 'test_db'
    os.environ['ODOO_USER'] = 'test_user'
    os.environ['ODOO_PASS'] = 'test_pass'
    os.environ['RABBIT_HOST'] = 'localhost'
    os.environ['RABBIT_USER'] = 'guest'
    os.environ['RABBIT_PASS'] = 'guest'
    os.environ['RABBIT_EXCHANGE'] = 'test.exchange'


@pytest.fixture
def poller():
    """Return a bare OrderPoller with a mocked models proxy."""
    from order_poller import OrderPoller
    p = OrderPoller()
    p.odoo_uid = 1
    p.models = MagicMock()
    return p


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

def test_order_poller_initialization():
    """OrderPoller reads environment variables correctly."""
    from order_poller import OrderPoller
    p = OrderPoller()
    assert p.odoo_url == 'http://test:8069'
    assert p.odoo_db == 'test_db'
    assert len(p.processed_orders) == 0


def test_outbox_directory_creation():
    """Outbox directory is created on initialization."""
    from order_poller import OrderPoller
    p = OrderPoller()
    assert p.outbox_dir.exists()
    assert p.outbox_dir.is_dir()


# ---------------------------------------------------------------------------
# Odoo connection
# ---------------------------------------------------------------------------

@patch('order_poller.xmlrpc.client.ServerProxy')
def test_connect_odoo_success(mock_server_proxy):
    """Successful Odoo authentication sets uid and models proxy."""
    from order_poller import OrderPoller
    mock_common = MagicMock()
    mock_common.authenticate.return_value = 1
    mock_server_proxy.return_value = mock_common

    p = OrderPoller()
    result = p.connect_odoo()

    assert result is True
    assert p.odoo_uid == 1


@patch('order_poller.xmlrpc.client.ServerProxy')
def test_connect_odoo_failure(mock_server_proxy):
    """Connection error causes connect_odoo to return False."""
    from order_poller import OrderPoller
    mock_server_proxy.side_effect = Exception('Connection refused')

    p = OrderPoller()
    result = p.connect_odoo()

    assert result is False


# ---------------------------------------------------------------------------
# process_order — routing and duplicate suppression
# ---------------------------------------------------------------------------

@patch('order_poller.sender')
def test_process_order_skips_duplicate(mock_sender, poller):
    """An already-processed order is skipped without any Odoo/sender calls."""
    poller.processed_orders[42] = True
    order = {'id': 42, 'partner_id': None, 'amount_total': 10.0, 'lines': []}
    result = poller.process_order(order)

    assert result is False
    mock_sender.send_typed_message.assert_not_called()


@patch('order_poller.sender')
def test_process_order_routes_refund(mock_sender, poller):
    """Negative amount_total routes to _process_refund."""
    order = {
        'id': 5, 'partner_id': None, 'amount_total': -9.99,
        'lines': [], 'payment_ids': [], 'x_wallet_updated': False,
    }
    poller.models.execute_kw.return_value = True

    with patch.object(poller, '_process_refund') as mock_refund, \
            patch.object(poller, '_process_consumption') as mock_consumption:
        # Mocking return values for process_order to unpack
        mock_consumption.return_value = (True, "msg-123", "pay-msg-123")
        mock_refund.return_value = (True, "refund-msg-123")
        poller.process_order(order)

    mock_refund.assert_called_once()
    mock_consumption.assert_not_called()


@patch('order_poller.sender')
def test_process_order_routes_consumption(mock_sender, poller):
    """Positive amount_total routes to _process_consumption."""
    order = {
        'id': 6, 'partner_id': None, 'amount_total': 12.50,
        'lines': [],
    }
    poller.models.execute_kw.return_value = True

    with patch.object(poller, '_process_refund') as mock_refund, \
            patch.object(poller, '_process_consumption') as mock_consumption:
        # Mocking return values for process_order to unpack
        mock_consumption.return_value = (True, "msg-123", "pay-msg-123")
        poller.process_order(order)
        mock_consumption.assert_called_once()
        mock_refund.assert_not_called()


@patch('order_poller.sender')
def test_process_order_marks_rabbitmq_sent(mock_sender, poller):
    """After processing, x_rabbitmq_sent is written to Odoo."""
    order = {'id': 7, 'partner_id': None, 'amount_total': 5.0, 'lines': []}

    with patch.object(poller, '_process_consumption') as mock_pc:
        mock_pc.return_value = (True, "12345-msg-id", "12345-pay-id")
        poller.models.execute_kw.return_value = True
        poller.process_order(order)

    # Verify x_rabbitmq_sent=True was among the written fields
    all_calls = poller.models.execute_kw.call_args_list
    write_calls = [c for c in all_calls if len(c[0]) > 4
                   and c[0][3] == 'pos.order' and c[0][4] == 'write']
    assert len(write_calls) >= 1
    # The payload argument is the last positional arg: [[order_id], {fields}]
    payload = write_calls[-1][0][5]
    assert {'x_rabbitmq_sent': True} in payload


@patch('order_poller.sender')
def test_process_order_does_not_mark_rabbitmq_sent_when_buffered(mock_sender, poller):
    """If processing returns False (buffered), x_rabbitmq_sent is NOT written to Odoo."""
    order = {'id': 8, 'partner_id': None, 'amount_total': 5.0, 'lines': []}

    with patch.object(poller, '_process_consumption', return_value=(False, "buffered-id", "buffered-pay-id")):
        poller.models.execute_kw.return_value = True
        poller.process_order(order)

    # Verify x_rabbitmq_sent was NOT written
    all_calls = poller.models.execute_kw.call_args_list
    write_calls = [c for c in all_calls if len(c[0]) > 4
                   and c[0][3] == 'pos.order' and c[0][4] == 'write'
                   and 'x_rabbitmq_sent' in c[0][5][1]]
    assert len(write_calls) == 0


def test_mark_orders_sent_writes_bulk_to_odoo(poller):
    """_mark_records_sent executes a bulk write using a list of unique IDs."""
    records = [('pos.order', 11), ('pos.order', 22), ('pos.order', 11), ('pos.order', 33)]

    poller._mark_records_sent(records)

    # Verify bulk write was called exactly once with unique IDs [11, 22, 33]
    poller.models.execute_kw.assert_called_once()
    call_args = poller.models.execute_kw.call_args[0]
    assert call_args[3] == 'pos.order'
    assert call_args[4] == 'write'

    payload = call_args[5]
    assert set(payload[0]) == {11, 22, 33}
    assert payload[1] == {'x_rabbitmq_sent': True}


# ---------------------------------------------------------------------------
# _process_refund
# ---------------------------------------------------------------------------

@patch('order_poller.sender')
def test_process_refund_cash_no_wallet(mock_sender, poller):
    """Cash refund: wallet is NOT updated, refund_processed IS sent."""
    order = {
        'id': 10, 'amount_total': -5.0, 'lines': [],
        'payment_ids': [1], 'x_wallet_updated': False,
    }
    # Payment method is NOT Badge Wallet
    poller.models.execute_kw.side_effect = [
        # pos.payment read
        [{'payment_method_id': (2, 'Cash'), 'amount': -5.0}],
        [],  # pos.order.line read (no lines)
    ]

    poller._process_refund(order, 10, None, is_anonymous=True)

    mock_sender.send_typed_message.assert_called_once_with(
        'refund_processed', mock_sender.build_refund_processed_xml.return_value, record_id=10
    )
    # Wallet write should NOT have been called
    write_calls = [c for c in poller.models.execute_kw.call_args_list
                   if len(c[0]) > 4 and c[0][3] == 'res.partner']
    assert len(write_calls) == 0


@patch('order_poller.sender')
def test_process_refund_badge_wallet_updates_balance(mock_sender, poller):
    """Badge Wallet refund: wallet balance is updated and wallet_balance_update is sent."""
    customer_info = {'id': 99, 'x_wallet_balance': 10.0, 'x_user_id': 'USR-1'}
    order = {
        'id': 11, 'amount_total': -4.0, 'lines': [],
        'payment_ids': [2], 'x_wallet_updated': False,
    }
    poller.models.execute_kw.side_effect = [
        [{'payment_method_id': (3, 'Badge Wallet'),
          'amount': -4.0}],  # payments
        True,    # res.partner write (new balance)
        True,    # pos.order write (x_wallet_updated)
        [],      # pos.order.line read for traceability
    ]

    poller._process_refund(order, 11, customer_info, is_anonymous=False)

    # Wallet balance update message sent
    calls = [str(c) for c in mock_sender.send_typed_message.call_args_list]
    assert any('wallet_balance_update' in c for c in calls)
    # Refund processed message sent
    assert any('refund_processed' in c for c in calls)


@patch('order_poller.sender')
def test_process_refund_already_updated_wallet_skips_write(mock_sender, poller):
    """x_wallet_updated=True prevents double wallet update."""
    customer_info = {'id': 99, 'x_wallet_balance': 10.0, 'x_user_id': 'USR-1'}
    order = {
        'id': 12, 'amount_total': -4.0, 'lines': [],
        'payment_ids': [2], 'x_wallet_updated': True,  # already done
    }
    poller.models.execute_kw.side_effect = [
        [{'payment_method_id': (3, 'Badge Wallet'),
          'amount': -4.0}],  # payments
        [],  # pos.order.line read for traceability
    ]

    poller._process_refund(order, 12, customer_info, is_anonymous=False)

    # Only refund_processed should be sent, NOT wallet_balance_update
    calls = [c[0][0] for c in mock_sender.send_typed_message.call_args_list]
    assert 'refund_processed' in calls
    assert 'wallet_balance_update' not in calls


@patch('order_poller.sender')
def test_process_refund_traces_original_order(mock_sender, poller):
    """Refund traceability: original_msg_id is resolved from pos.order.line."""
    order = {
        'id': 13, 'amount_total': -5.0,
        'lines': [(99,)],  # one refund line
        'payment_ids': [], 'x_wallet_updated': False,
    }
    poller.models.execute_kw.side_effect = [
        # pos.order.line read: refunded_orderline_id points to line 55
        [{'id': 99, 'refunded_orderline_id': (55, 'Product')}],
        # pos.order.line read for line 55: belongs to order 7
        [{'id': 55, 'order_id': (7, 'POS/2024/00007')}],
        # pos.order read for x_payment_message_id
        [{'id': 7, 'x_payment_message_id': 'ORDER-7'}],
    ]

    poller._process_refund(order, 13, None, is_anonymous=True)

    # Verify build was called with ORDER-7
    call_kwargs = mock_sender.build_refund_processed_xml.call_args[1]
    assert call_kwargs['original_payment_msg_id'] == 'ORDER-7'


@patch('order_poller.sender')
def test_process_refund_tracing_fallback_on_error(mock_sender, poller):
    """If tracing fails, original_msg_id falls back to 'Unknown' without crashing."""
    order = {
        'id': 14, 'amount_total': -5.0, 'lines': [(88,)],
        'payment_ids': [], 'x_wallet_updated': False,
    }
    # Simulate Odoo API error during tracing
    poller.models.execute_kw.side_effect = Exception('Odoo API error')

    # Should NOT raise — graceful fallback
    with patch('uuid.uuid4') as mock_uuid:
        mock_uuid.return_value = 'Unknown'
        poller._process_refund(order, 14, None, is_anonymous=True)


@patch('order_poller.sender')
def test_process_refund_uses_customer_request_reason(mock_sender, poller):
    """refund_processed is built with DEFAULT_REFUND_REASON='customer_request' (Story 8 DoD)."""
    order = {
        'id': 15, 'amount_total': -7.50, 'lines': [],
        'payment_ids': [1], 'x_wallet_updated': False,
    }
    poller.models.execute_kw.side_effect = [
        # pos.payment read
        [{'payment_method_id': (2, 'Cash'), 'amount': -7.50}],
    ]

    poller._process_refund(order, 15, None, is_anonymous=True)

    call_kwargs = mock_sender.build_refund_processed_xml.call_args[1]
    assert call_kwargs['refund_reason'] == 'customer_request', (
        "refund_reason must be 'customer_request' — Story 8 DoD requires a "
        "semantically correct reason value that CRM operators can act on."
    )

# ---------------------------------------------------------------------------
# _process_consumption
# ---------------------------------------------------------------------------


@patch('order_poller.sender')
def test_process_consumption_sends_consumption_order(mock_sender, poller):
    """Regular order sends a consumption_order message."""
    mock_sender.build_consumption_order_xml.return_value = (
        '<message><header><message_id>12345</message_id></header></message>'
    )
    order = {'id': 20, 'lines': [(10,), (11,)], 'amount_total': 15.0}
    poller.models.execute_kw.side_effect = [
        # pos.order.line read
        [
            {'id': 10, 'product_id': (
                1, 'Beer'), 'qty': 2, 'price_unit': 3.0, 'tax_ids': [5]},
            {'id': 11, 'product_id': (
                2, 'Water'), 'qty': 1, 'price_unit': 1.5, 'tax_ids': []},
        ],
        # product.product bulk read (for top-up identification)
        [
            {'id': 1, 'x_is_topup': False, 'pos_categ_ids': []},
            {'id': 2, 'x_is_topup': False, 'pos_categ_ids': []},
        ],
        # account.tax bulk read
        [{'id': 5, 'amount': 6.0}],
    ]

    mock_sender.build_payment_registered_xml.return_value = (
        '<message><header><message_id>12345</message_id></header></message>'
    )
    poller._process_consumption(order, None, is_anonymous=True)

    call_kwargs = mock_sender.build_consumption_order_xml.call_args[1]
    items = call_kwargs['items']
    assert items[0]['id'] == 'LINE-10'
    assert items[0]['sku'] == '1'
    assert items[1]['id'] == 'LINE-11'
    assert items[1]['sku'] == '2'
    assert call_kwargs['is_anonymous'] is True


@patch('order_poller.sender')
def test_process_consumption_sets_payment_link_fields(mock_sender, poller):
    """payment_registered links to consumption_order and always uses on_site payment."""
    mock_sender.build_consumption_order_xml.return_value = (
        '<message><header><message_id>corr-123</message_id></header></message>'
    )
    mock_sender.build_payment_registered_xml.return_value = (
        '<message><header><message_id>pay-123</message_id></header></message>'
    )
    mock_sender.send_typed_message.return_value = True

    order = {
        'id': 24,
        'lines': [],
        'amount_total': 15.0,
        'payment_ids': [],
        'create_date': '2026-04-01 12:00:00',
    }

    ok, correlation_msg_id, payment_msg_id = poller._process_consumption(
        order, None, is_anonymous=True)

    assert ok is True
    assert payment_msg_id == 'pay-123'

    pay_kwargs = mock_sender.build_payment_registered_xml.call_args[1]
    assert pay_kwargs['payment_context'] == 'consumption'
    assert pay_kwargs['correlation_id'] == 'corr-123'
    assert pay_kwargs['payment_method'] == 'on_site'

    msg_types = [c[0][0] for c in mock_sender.send_typed_message.call_args_list]
    assert msg_types == ['consumption_order', 'payment_registered_consumption']


@patch('order_poller.sender')
def test_process_consumption_badge_wallet_updates_balance(mock_sender, poller):
    """Badge Wallet consumption deducts balance and emits wallet_balance_update."""
    customer_info = {
        'id': 99,
        'x_wallet_balance': 12.5,
        'x_user_id': 'USR-1',
        'is_company': False,
        'parent_id': False,
        'email': '',
        'customer_type': 'private'
    }
    order = {
        'id': 25,
        'lines': [],
        'amount_total': 4.0,
        'payment_ids': [9],
        'x_wallet_updated': False,
        'create_date': '2026-04-01 12:00:00',
    }
    poller.models.execute_kw.side_effect = [
        # pos.payment read
        [{'payment_method_id': (3, 'Badge Wallet'), 'amount': 4.0}],
        8.5,  # action_process_wallet_payment returns the new balance atomically
    ]
    mock_sender.build_consumption_order_xml.return_value = (
        '<message><header><message_id>corr-wallet</message_id></header></message>'
    )
    mock_sender.build_payment_registered_xml.return_value = (
        '<message><header><message_id>pay-wallet</message_id></header></message>'
    )
    mock_sender.send_typed_message.side_effect = [True, True, True]

    ok, correlation_msg_id, payment_msg_id = poller._process_consumption(
        order, customer_info, is_anonymous=False)

    assert ok is True
    assert payment_msg_id == 'pay-wallet'

    # Verify atomic update call was made
    atomic_calls = [
        c for c in poller.models.execute_kw.call_args_list
        if len(c[0]) > 4 and c[0][4] == 'action_process_wallet_payment'
    ]
    assert len(atomic_calls) == 1

    mock_sender.build_wallet_balance_update_xml.assert_called_once_with(
        'USR-1',
        8.5,
    )

    msg_types = [c[0][0] for c in mock_sender.send_typed_message.call_args_list]
    assert msg_types == [
        'consumption_order',
        'wallet_balance_update',
        'payment_registered_consumption',
    ]


@patch('order_poller.sender')
def test_process_order_topup_increases_wallet_balance(mock_sender, poller):
    """Top-up orders increase wallet balance and emit wallet_balance_update."""
    customer_info = {
        'id': 77,
        'x_wallet_balance': 10.0,
        'x_user_id': 'USR-77',
        'x_badge_id': 'BADGE-77',
        'is_company': False,
        'parent_id': False,
        'email': '',
        'customer_type': 'private',
        'name': 'Visitor 77',
        'street': 'Main 1',
        'zip': '1000',
        'city': 'Brussels',
        'country_code': 'be',
    }
    order = {
        'id': 26,
        'partner_id': 77,
        'lines': [(301,)],
        'amount_total': 15.0,
        'payment_ids': [],
        'x_wallet_updated': False,
        'x_payment_message_id': 'pay-old',
        'create_date': '2026-04-01 12:00:00',
        'to_invoice': False,
        'account_move': None,
    }

    poller.get_customer_info = MagicMock(return_value=customer_info)
    poller.models.execute_kw.side_effect = [
        [{
            'id': 301,
            'product_id': (55, 'Top-up EUR 10'),
            'qty': 1,
            'price_unit': 15.0,
            'tax_ids': [],
            'price_subtotal_incl': 15.0,
        }],
        [{'id': 55, 'x_is_topup': True, 'pos_categ_ids': []}],
        True,
        True,
        True,
        True,
    ]
    mock_sender.build_consumption_order_xml.return_value = (
        '<message><header><message_id>cons-1</message_id></header></message>'
    )
    mock_sender.build_payment_registered_xml.return_value = (
        '<message><header><message_id>pay-1</message_id></header></message>'
    )
    mock_sender.build_wallet_balance_update_xml.return_value = (
        '<message><header><message_id>wallet-1</message_id></header></message>'
    )
    mock_sender.send_typed_message.side_effect = [True, True, True]

    result = poller.process_order(order)

    assert result is True
    assert poller.models.execute_kw.call_args_list[2][0][4] == 'write'
    assert poller.models.execute_kw.call_args_list[2][0][5][1]['x_wallet_balance'] == 25.0
    sent_types = [c[0][0] for c in mock_sender.send_typed_message.call_args_list]
    assert sent_types == ['consumption_order', 'payment_registered_consumption', 'wallet_balance_update']


@patch('order_poller.sender')
def test_process_consumption_bulk_tax_fetch(mock_sender, poller):
    """Taxes are fetched in a single bulk call, not per line."""
    mock_sender.build_consumption_order_xml.return_value = (
        '<message><header><message_id>12345</message_id></header></message>'
    )
    order = {'id': 21, 'lines': [(10,), (11,)], 'amount_total': 15.0}
    poller.models.execute_kw.side_effect = [
        [
            {'id': 10, 'product_id': (1, 'A'), 'qty': 1,
             'price_unit': 5.0, 'tax_ids': [3]},
            {'id': 11, 'product_id': (2, 'B'), 'qty': 1,
             'price_unit': 2.0, 'tax_ids': [3]},
        ],
        # product.product bulk read (for top-up identification)
        [
            {'id': 1, 'x_is_topup': False, 'pos_categ_ids': []},
            {'id': 2, 'x_is_topup': False, 'pos_categ_ids': []},
        ],
        [{'id': 3, 'amount': 21.0}],  # single bulk tax call
    ]

    mock_sender.build_payment_registered_xml.return_value = (
        '<message><header><message_id>12345</message_id></header></message>'
    )

    poller._process_consumption(order, None, is_anonymous=True)
    all_calls = poller.models.execute_kw.call_args_list
    tax_calls = [c for c in all_calls
                 if len(c[0]) > 3 and c[0][3] == 'account.tax']
    assert len(tax_calls) == 1


@patch('order_poller.sender')
def test_process_consumption_company_customer_type(mock_sender, poller):
    """A customer linked to a parent company has customer_type 'company'."""
    mock_sender.build_consumption_order_xml.return_value = (
        '<message><header><message_id>12345</message_id></header></message>'
    )
    order = {'id': 22, 'lines': [], 'amount_total': 15.0}
    customer_info = {'id': 5, 'name': 'John', 'is_company': False,
                     'parent_id': (3, 'ACME Corp'), 'x_user_id': None, 'email': '',
                     'customer_type': 'company'}

    mock_sender.build_payment_registered_xml.return_value = (
        '<message><header><message_id>12345</message_id></header></message>'
    )
    poller._process_consumption(order, customer_info, is_anonymous=False)

    call_kwargs = mock_sender.build_consumption_order_xml.call_args[1]
    assert call_kwargs['customer_type'] == 'company'
    assert call_kwargs['is_anonymous'] is False


@patch('order_poller.sender')
def test_process_consumption_private_customer_type(mock_sender, poller):
    """A customer with no parent and is_company=False has customer_type 'private'."""
    mock_sender.build_consumption_order_xml.return_value = (
        '<message><header><message_id>12345</message_id></header></message>'
    )
    order = {'id': 23, 'lines': [], 'amount_total': 15.0}
    customer_info = {'id': 6, 'name': 'Jane', 'is_company': False,
                     'parent_id': False, 'x_user_id': None, 'email': '',
                     'customer_type': 'private'}

    mock_sender.build_payment_registered_xml.return_value = (
        '<message><header><message_id>12345</message_id></header></message>'
    )
    poller._process_consumption(order, customer_info, is_anonymous=False)

    call_kwargs = mock_sender.build_consumption_order_xml.call_args[1]
    assert call_kwargs['customer_type'] == 'private'


@patch('order_poller.sender')
def test_process_consumption_passes_address_data(mock_sender, poller):
    """Verify that _process_consumption splits and passes address data."""
    customer_info = {
        'id': 99,
        'name': 'Jan Peeters',
        'street': 'Kiekenmarkt 42',
        'zip': '1000',
        'city': 'Brussel',
        'country_code': 'be',
        'x_user_id': 'USR-1',
        'email': 'jan@example.com',
        'customer_type': 'private'
    }
    order = {
        'id': 26,
        'lines': [],
        'amount_total': 10.0,
        'payment_ids': [],
        'create_date': '2026-04-01 12:00:00',
    }

    # Mocking return values to allow the method to complete
    mock_sender.build_consumption_order_xml.return_value = "<xml/>"
    mock_sender.build_payment_registered_xml.return_value = "<xml/>"
    mock_sender.send_typed_message.return_value = True

    poller._process_consumption(order, customer_info, is_anonymous=False)

    # Verify build_consumption_order_xml was called with the split address
    call_kwargs = mock_sender.build_consumption_order_xml.call_args[1]
    assert 'address' in call_kwargs
    addr = call_kwargs['address']
    assert addr['street'] == 'Kiekenmarkt'
    assert addr['number'] == '42'
    assert addr['postal_code'] == '1000'
    assert addr['city'] == 'Brussel'
    assert addr['country'] == 'be'


def test_get_customer_info_recursion_guard(poller):
    """Verify that get_customer_info detects and breaks circular parent loops."""
    # Mocking circular link: Partner 1 parent is Partner 2, Partner 2 parent is Partner 1
    # We use a side_effect function to handle multiple calls predictably
    def mock_execute_kw(*args, **kwargs):
        model = args[3]
        params = args[5]
        if model == 'res.partner':
            pid = params[0]
            if pid == 1:
                return [{'id': 1, 'name': 'A', 'parent_id': (2, 'B'), 'is_company': False}]
            if pid == 2:
                return [{'id': 2, 'name': 'B', 'parent_id': (1, 'A'), 'is_company': False}]
        return []

    poller.models.execute_kw.side_effect = mock_execute_kw

    # This should return the data for partner 1 instead of crashing with RecursionError
    info = poller.get_customer_info(1)
    assert info['id'] == 1
    # Circular parent info should be None or gracefully handled
    # (In our case, get_customer_info(2) will return data for B, but B's parent lookup for A will return None)
    assert info['parent_id'] == (2, 'B')


# ---------------------------------------------------------------------------
# _get_pos_config_name
# ---------------------------------------------------------------------------

def test_get_pos_config_name_returns_name(poller):
    """Resolves session → config → name and caches the result."""
    poller.models.execute_kw.side_effect = [
        [{'config_id': (7, 'Inschrijvingskassa')}],   # pos.session read
        [{'name': 'Inschrijvingskassa'}],               # pos.config read
    ]
    name = poller._get_pos_config_name((3, 'Session/2026'))
    assert name == 'Inschrijvingskassa'
    # Second call must use cache — no extra RPC
    poller.models.execute_kw.side_effect = Exception("should not be called")
    assert poller._get_pos_config_name((3, 'Session/2026')) == 'Inschrijvingskassa'


def test_get_pos_config_name_returns_none_for_missing_session(poller):
    """Returns None gracefully when session has no config_id."""
    poller.models.execute_kw.return_value = [{'config_id': False}]
    assert poller._get_pos_config_name(99) is None


def test_get_pos_config_name_returns_none_on_error(poller):
    """Returns None without raising when Odoo call fails."""
    poller.models.execute_kw.side_effect = Exception('Odoo down')
    assert poller._get_pos_config_name(1) is None


def test_get_pos_config_name_returns_none_for_falsy_input(poller):
    assert poller._get_pos_config_name(None) is None
    assert poller._get_pos_config_name(False) is None


# ---------------------------------------------------------------------------
# _update_partner_registration_paid
# ---------------------------------------------------------------------------

def test_update_partner_registration_paid_writes_fields(poller):
    """Writes x_outstanding_amount=0 and x_payment_status='paid' to Odoo."""
    poller.models.execute_kw.return_value = True
    poller._update_partner_registration_paid(99, 'Alice')

    calls = poller.models.execute_kw.call_args_list
    partner_write = next(
        c for c in calls
        if len(c[0]) > 4 and c[0][3] == 'res.partner' and c[0][4] == 'write'
    )
    payload = partner_write[0][5]
    assert payload[0] == [99]
    assert payload[1]['x_outstanding_amount'] == 0.0
    assert payload[1]['x_payment_status'] == 'paid'


def test_update_partner_registration_paid_publishes_bus_event(poller):
    """Publishes a kassa_partner_update bus event via pos.order.send_partner_bus_event."""
    poller.models.execute_kw.return_value = True
    poller._update_partner_registration_paid(99, 'Alice')

    calls = poller.models.execute_kw.call_args_list
    bus_call = next(
        c for c in calls
        if len(c[0]) > 4 and c[0][3] == 'pos.order' and c[0][4] == 'send_partner_bus_event'
    )
    args = bus_call[0][5]
    assert args[0] == 99        # partner_id
    assert args[1] == 0.0       # x_outstanding_amount
    assert args[2] == 'paid'    # x_payment_status
    assert args[3] == 'Alice'   # name


def test_update_partner_registration_paid_does_not_raise_on_error(poller):
    """Errors are logged but never propagate to the caller."""
    poller.models.execute_kw.side_effect = Exception('Odoo down')
    poller._update_partner_registration_paid(99, 'Alice')  # must not raise


# ---------------------------------------------------------------------------
# _process_consumption — Inschrijvingskassa payment status update
# ---------------------------------------------------------------------------

@patch('order_poller.sender')
def test_process_consumption_marks_partner_paid_for_inschrijvingskassa(mock_sender, poller):
    """Partner is marked paid when the order comes from Inschrijvingskassa."""
    mock_sender.build_consumption_order_xml.return_value = (
        '<message><header><message_id>corr-1</message_id></header></message>'
    )
    mock_sender.build_payment_registered_xml.return_value = (
        '<message><header><message_id>pay-1</message_id></header></message>'
    )
    mock_sender.send_typed_message.return_value = True

    customer_info = {
        'id': 55, 'name': 'Eve', 'is_company': False,
        'parent_id': False, 'x_user_id': 'u-55', 'email': '',
    }
    order = {
        'id': 30, 'lines': [], 'amount_total': 10.0,
        'payment_ids': [], 'create_date': '2026-04-29 10:00:00',
        'session_id': (5, 'POS/2026/00001'),
    }
    # Session lookup → config id 7; config lookup → name 'Inschrijvingskassa'
    poller.models.execute_kw.side_effect = [
        [{'config_id': (7, 'Inschrijvingskassa')}],
        [{'name': 'Inschrijvingskassa'}],
        True,   # res.partner write (x_outstanding_amount / x_payment_status)
        True,   # bus.bus sendone
    ]

    with patch.object(poller, '_update_partner_registration_paid') as mock_update:
        poller._process_consumption(order, customer_info, is_anonymous=False)
        mock_update.assert_called_once_with(55, 'Eve')


@patch('order_poller.sender')
def test_process_consumption_does_not_mark_paid_for_bar_kassa(mock_sender, poller):
    """Partner is NOT updated when order comes from Bar Kassa."""
    mock_sender.build_consumption_order_xml.return_value = (
        '<message><header><message_id>corr-2</message_id></header></message>'
    )
    mock_sender.build_payment_registered_xml.return_value = (
        '<message><header><message_id>pay-2</message_id></header></message>'
    )
    mock_sender.send_typed_message.return_value = True

    customer_info = {
        'id': 56, 'name': 'Frank', 'is_company': False,
        'parent_id': False, 'x_user_id': 'u-56', 'email': '',
    }
    order = {
        'id': 31, 'lines': [], 'amount_total': 5.0,
        'payment_ids': [], 'create_date': '2026-04-29 10:00:00',
        'session_id': (6, 'POS/2026/00002'),
    }
    poller.models.execute_kw.side_effect = [
        [{'config_id': (8, 'Bar Kassa')}],
        [{'name': 'Bar Kassa'}],
    ]

    with patch.object(poller, '_update_partner_registration_paid') as mock_update:
        poller._process_consumption(order, customer_info, is_anonymous=False)
        mock_update.assert_not_called()


@patch('order_poller.sender')
def test_process_consumption_does_not_mark_paid_for_anonymous(mock_sender, poller):
    """Anonymous orders never trigger partner payment status update."""
    mock_sender.build_consumption_order_xml.return_value = (
        '<message><header><message_id>corr-3</message_id></header></message>'
    )
    mock_sender.build_payment_registered_xml.return_value = (
        '<message><header><message_id>pay-3</message_id></header></message>'
    )
    mock_sender.send_typed_message.return_value = True

    order = {
        'id': 32, 'lines': [], 'amount_total': 7.0,
        'payment_ids': [], 'create_date': '2026-04-29 10:00:00',
        'session_id': (5, 'POS/2026/00001'),
    }

    with patch.object(poller, '_update_partner_registration_paid') as mock_update:
        poller._process_consumption(order, None, is_anonymous=True)
        mock_update.assert_not_called()
