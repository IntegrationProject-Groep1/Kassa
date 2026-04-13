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
        poller.process_order(order)
        mock_consumption.assert_called_once()
        mock_refund.assert_not_called()


@patch('order_poller.sender')
def test_process_order_marks_rabbitmq_sent(mock_sender, poller):
    """After processing, x_rabbitmq_sent is written to Odoo."""
    order = {'id': 7, 'partner_id': None, 'amount_total': 5.0, 'lines': []}

    with patch.object(poller, '_process_consumption') as mock_pc:
        mock_pc.return_value = (True, "12345-msg-id")
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

    with patch.object(poller, '_process_consumption', return_value=False):
        poller.models.execute_kw.return_value = True
        poller.process_order(order)

    # Verify x_rabbitmq_sent was NOT written
    all_calls = poller.models.execute_kw.call_args_list
    write_calls = [c for c in all_calls if len(c[0]) > 4
                   and c[0][3] == 'pos.order' and c[0][4] == 'write']
    assert len(write_calls) == 0


def test_mark_orders_sent_writes_bulk_to_odoo(poller):
    """_mark_orders_sent executes a bulk write using a list of unique IDs."""
    order_ids = [11, 22, 11, 33]  # includes a duplicate

    poller._mark_orders_sent(order_ids)

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
        [{'payment_method_id': (2, 'Cash'), 'amount': -5.0}],  # pos.payment read
        [],  # pos.order.line read (no lines)
    ]

    poller._process_refund(order, 10, None, is_anonymous=True)

    mock_sender.send_typed_message.assert_called_once_with(
        'refund_processed', mock_sender.build_refund_processed_xml.return_value, order_id=10
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
        [{'payment_method_id': (3, 'Badge Wallet'), 'amount': -4.0}],  # payments
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
        [{'payment_method_id': (3, 'Badge Wallet'), 'amount': -4.0}],  # payments
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
            {'id': 10, 'product_id': (1, 'Beer'), 'qty': 2, 'price_unit': 3.0, 'tax_ids': [5]},
            {'id': 11, 'product_id': (2, 'Water'), 'qty': 1, 'price_unit': 1.5, 'tax_ids': []},
        ],
        # account.tax bulk read
        [{'id': 5, 'amount': 6.0}],
    ]

    mock_sender.build_payment_registered_xml.return_value = (
        '<message><header><message_id>12345</message_id></header></message>'
    )
    poller._process_consumption(order, None, is_anonymous=True)


@patch('order_poller.sender')
def test_process_consumption_bulk_tax_fetch(mock_sender, poller):
    """Taxes are fetched in a single bulk call, not per line."""
    mock_sender.build_consumption_order_xml.return_value = (
        '<message><header><message_id>12345</message_id></header></message>'
    )
    order = {'id': 21, 'lines': [(10,), (11,)], 'amount_total': 15.0}
    poller.models.execute_kw.side_effect = [
        [
            {'id': 10, 'product_id': (1, 'A'), 'qty': 1, 'price_unit': 5.0, 'tax_ids': [3]},
            {'id': 11, 'product_id': (2, 'B'), 'qty': 1, 'price_unit': 2.0, 'tax_ids': [3]},
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
                     'parent_id': (3, 'ACME Corp'), 'x_user_id': None, 'email': ''}
    # parent company lookup
    poller.models.execute_kw.return_value = [{'is_company': True}]

    mock_sender.build_payment_registered_xml.return_value = (
        '<message><header><message_id>12345</message_id></header></message>'
    )
    poller._process_consumption(order, customer_info, is_anonymous=False)

    call_kwargs = mock_sender.build_consumption_order_xml.call_args[1]
    assert call_kwargs['customer_type'] == 'company'


@patch('order_poller.sender')
def test_process_consumption_private_customer_type(mock_sender, poller):
    """A customer with no parent and is_company=False has customer_type 'private'."""
    mock_sender.build_consumption_order_xml.return_value = (
        '<message><header><message_id>12345</message_id></header></message>'
    )
    order = {'id': 23, 'lines': [], 'amount_total': 15.0}
    customer_info = {'id': 6, 'name': 'Jane', 'is_company': False,
                     'parent_id': False, 'x_user_id': None, 'email': ''}

    mock_sender.build_payment_registered_xml.return_value = (
        '<message><header><message_id>12345</message_id></header></message>'
    )
    poller._process_consumption(order, customer_info, is_anonymous=False)

    call_kwargs = mock_sender.build_consumption_order_xml.call_args[1]
    assert call_kwargs['customer_type'] == 'private'
