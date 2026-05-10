"""
Story 6 — Inkomticket betalen aan de deur

Tests for the Inschrijvingskassa routing in OrderPoller:
- Registration orders route to _process_registration(), not _process_consumption()
- payment_registered is sent with correct registration-specific fields
- payment_status is sent with payment_status='paid'
- x_rabbitmq_sent is set only when both messages succeed
- Anonymous orders on Inschrijvingskassa are NOT processed as registration
- Consumption orders (Bar Kassa) still route to _process_consumption()
- When one message fails, x_rabbitmq_sent is NOT set
"""
import os
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def setup_env():
    """Mock environment variables for all Story 6 tests."""
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


def _make_registration_order(order_id: int = 42) -> dict:
    return {
        'id': order_id,
        'name': 'POS/0042',
        'partner_id': [10, 'Jan Janssen'],
        'session_id': [5, 'Session 5'],
        'lines': [],
        'amount_total': 25.0,
        'payment_ids': [],
        'x_wallet_updated': False,
        'x_rabbitmq_sent': False,
        'x_payment_message_id': None,
        'x_invoice_message_id': None,
        'create_date': '2026-05-08 10:00:00',
        'to_invoice': False,
        'account_move': None,
    }


def _make_customer_info(user_id: str = 'UUID-001') -> dict:
    return {
        'id': 10,
        'name': 'Jan Janssen',
        'x_user_id': user_id,
        'x_badge_id': 'BADGE-10',
        'x_wallet_balance': 0.0,
        'is_company': False,
        'parent_id': False,
        'email': 'jan@example.com',
        'customer_type': 'private',
        'street': 'Kerkstraat 1',
        'zip': '1000',
        'city': 'Brussel',
        'country_code': 'be',
    }


# ---------------------------------------------------------------------------
# _process_registration: correct message types and field values
# ---------------------------------------------------------------------------

@patch('order_poller.sender')
def test_process_registration_sends_correct_message_types(mock_sender, poller):
    """_process_registration emits payment_registered_registration then payment_status."""
    order = _make_registration_order()
    customer = _make_customer_info('UUID-REG-001')

    mock_sender.build_payment_registered_xml.return_value = (
        '<message><header><message_id>pay-reg-1</message_id></header></message>'
    )
    mock_sender.build_payment_status_xml.return_value = (
        '<message><header><message_id>status-1</message_id></header></message>'
    )
    mock_sender.send_typed_message.side_effect = [True, True]
    poller.models.execute_kw.return_value = True

    all_sent, payment_msg_id = poller._process_registration(order, customer)

    assert all_sent is True
    assert payment_msg_id == 'pay-reg-1'

    types_sent = [c[0][0] for c in mock_sender.send_typed_message.call_args_list]
    assert types_sent == ['payment_registered_registration', 'payment_status']


@patch('order_poller.sender')
def test_process_registration_payment_registered_fields(mock_sender, poller):
    """payment_registered_xml is built with registration-specific field values."""
    order = _make_registration_order()
    customer = _make_customer_info('UUID-REG-002')

    mock_sender.build_payment_registered_xml.return_value = '<message/>'
    mock_sender.build_payment_status_xml.return_value = '<message/>'
    mock_sender.send_typed_message.return_value = True
    poller.models.execute_kw.return_value = True

    poller._process_registration(order, customer)

    kwargs = mock_sender.build_payment_registered_xml.call_args[1]
    assert kwargs['payment_context'] == 'registration'
    assert kwargs['invoice_status'] == 'paid'
    assert kwargs['payment_method'] == 'on_site'
    assert kwargs['amount_paid'] == 25.0
    assert kwargs['trx_id'] == '42'
    assert kwargs['due_date'] == '2026-05-08'
    assert kwargs['invoice_id'] is None
    assert kwargs['identity_uuid'] == 'UUID-REG-002'
    assert kwargs['correlation_id'] is None   # non-UUID order name must NOT be passed


@patch('order_poller.sender')
def test_process_registration_payment_status_fields(mock_sender, poller):
    """payment_status_xml is built with identity_uuid and status='paid'."""
    order = _make_registration_order()
    customer = _make_customer_info('UUID-REG-003')

    mock_sender.build_payment_registered_xml.return_value = '<message/>'
    mock_sender.build_payment_status_xml.return_value = '<message/>'
    mock_sender.send_typed_message.return_value = True
    poller.models.execute_kw.return_value = True

    poller._process_registration(order, customer)

    kwargs = mock_sender.build_payment_status_xml.call_args[1]
    assert kwargs['identity_uuid'] == 'UUID-REG-003'
    assert kwargs['status'] == 'paid'


@patch('order_poller.sender')
def test_process_registration_calls_update_partner(mock_sender, poller):
    """_process_registration calls _update_partner_registration_paid."""
    order = _make_registration_order()
    customer = _make_customer_info()

    mock_sender.build_payment_registered_xml.return_value = '<message/>'
    mock_sender.build_payment_status_xml.return_value = '<message/>'
    mock_sender.send_typed_message.return_value = True
    poller.models.execute_kw.return_value = True

    with patch.object(poller, '_update_partner_registration_paid') as mock_update:
        poller._process_registration(order, customer)
        mock_update.assert_called_once_with(10, 'Jan Janssen')


# ---------------------------------------------------------------------------
# _process_registration: partial failure
# ---------------------------------------------------------------------------

@patch('order_poller.sender')
def test_process_registration_returns_false_when_payment_fails(mock_sender, poller):
    """all_sent is False when the payment_registered message fails."""
    order = _make_registration_order()
    customer = _make_customer_info()

    mock_sender.build_payment_registered_xml.return_value = (
        '<message><header><message_id>pay-fail</message_id></header></message>'
    )
    mock_sender.build_payment_status_xml.return_value = '<message/>'
    mock_sender.send_typed_message.side_effect = [False, True]
    poller.models.execute_kw.return_value = True

    all_sent, payment_msg_id = poller._process_registration(order, customer)

    assert all_sent is False
    assert payment_msg_id == 'pay-fail'


@patch('order_poller.sender')
def test_process_registration_returns_false_when_status_fails(mock_sender, poller):
    """all_sent is False when the payment_status message fails."""
    order = _make_registration_order()
    customer = _make_customer_info()

    mock_sender.build_payment_registered_xml.return_value = (
        '<message><header><message_id>pay-ok</message_id></header></message>'
    )
    mock_sender.build_payment_status_xml.return_value = '<message/>'
    mock_sender.send_typed_message.side_effect = [True, False]
    poller.models.execute_kw.return_value = True

    all_sent, _ = poller._process_registration(order, customer)

    assert all_sent is False


# ---------------------------------------------------------------------------
# process_order: routing decisions
# ---------------------------------------------------------------------------

@patch('order_poller.sender')
def test_process_order_routes_inschrijvingskassa_to_registration(mock_sender, poller):
    """process_order calls _process_registration for Inschrijvingskassa orders."""
    order = _make_registration_order(42)
    customer = _make_customer_info()

    poller.get_customer_info = MagicMock(return_value=customer)
    # execute_kw calls: (1) _get_pos_config_name session read, (2) config read,
    # (3) partner write (paid), (4) bus event, (5) x_payment_message_id write,
    # (6) x_rabbitmq_sent write
    poller.models.execute_kw.side_effect = [
        [{'config_id': [3, 'Inschrijvingskassa']}],  # pos.session read
        [{'name': 'Inschrijvingskassa'}],              # pos.config read
        True,  # res.partner write (x_outstanding_amount / x_payment_status)
        True,  # pos.order send_partner_bus_event
        True,  # pos.order write x_payment_message_id
        True,  # pos.order write x_rabbitmq_sent
    ]

    mock_sender.build_payment_registered_xml.return_value = (
        '<message><header><message_id>pay-reg</message_id></header></message>'
    )
    mock_sender.build_payment_status_xml.return_value = '<message/>'
    mock_sender.send_typed_message.return_value = True

    with patch.object(poller, '_process_consumption') as mock_consumption:
        poller.process_order(order)
        mock_consumption.assert_not_called()

    types_sent = [c[0][0] for c in mock_sender.send_typed_message.call_args_list]
    assert 'payment_registered_registration' in types_sent
    assert 'payment_status' in types_sent
    assert 'consumption_order' not in types_sent


@patch('order_poller.sender')
def test_process_order_routes_bar_kassa_to_consumption(mock_sender, poller):
    """process_order calls _process_consumption for non-Inschrijvingskassa orders."""
    order = _make_registration_order(55)
    order['session_id'] = [7, 'Bar Session']
    customer = _make_customer_info()

    poller.get_customer_info = MagicMock(return_value=customer)
    poller.models.execute_kw.side_effect = [
        [{'config_id': [7, 'Bar Kassa']}],  # pos.session read
        [{'name': 'Bar Kassa'}],             # pos.config read
        True,  # pos.order write x_payment_message_id
        True,  # pos.order write x_rabbitmq_sent
    ]

    with patch.object(poller, '_process_registration') as mock_reg, \
         patch.object(poller, '_process_consumption',
                      return_value=(True, 'corr-1', 'pay-1')) as mock_cons:
        poller.process_order(order)
        mock_reg.assert_not_called()
        mock_cons.assert_called_once()


@patch('order_poller.sender')
def test_process_order_anonymous_inschrijvingskassa_routes_to_consumption(mock_sender, poller):
    """Anonymous orders on Inschrijvingskassa are NOT treated as registration."""
    order = _make_registration_order(66)
    order['partner_id'] = None  # anonymous

    poller.get_customer_info = MagicMock(return_value=None)
    poller.models.execute_kw.side_effect = [
        [{'config_id': [3, 'Inschrijvingskassa']}],  # pos.session read
        [{'name': 'Inschrijvingskassa'}],              # pos.config read
        True,  # pos.order write x_payment_message_id
        True,  # pos.order write x_rabbitmq_sent
    ]

    with patch.object(poller, '_process_registration') as mock_reg, \
         patch.object(poller, '_process_consumption',
                      return_value=(True, 'corr-anon', 'pay-anon')) as mock_cons:
        poller.process_order(order)
        mock_reg.assert_not_called()
        mock_cons.assert_called_once()


# ---------------------------------------------------------------------------
# process_order: x_rabbitmq_sent flag
# ---------------------------------------------------------------------------

@patch('order_poller.sender')
def test_process_order_sets_rabbitmq_sent_when_both_succeed(mock_sender, poller):
    """x_rabbitmq_sent=True is written to Odoo when both registration messages succeed."""
    order = _make_registration_order(77)
    customer = _make_customer_info()

    poller.get_customer_info = MagicMock(return_value=customer)
    poller.models.execute_kw.side_effect = [
        [{'config_id': [3, 'Inschrijvingskassa']}],
        [{'name': 'Inschrijvingskassa'}],
        True,  # res.partner write
        True,  # bus event
        True,  # x_payment_message_id write
        True,  # x_rabbitmq_sent write
    ]
    mock_sender.build_payment_registered_xml.return_value = (
        '<message><header><message_id>pay-77</message_id></header></message>'
    )
    mock_sender.build_payment_status_xml.return_value = '<message/>'
    mock_sender.send_typed_message.return_value = True

    poller.process_order(order)

    rabbitmq_sent_calls = [
        c for c in poller.models.execute_kw.call_args_list
        if len(c[0]) >= 6 and c[0][4] == 'write'
        and isinstance(c[0][5], list) and len(c[0][5]) == 2
        and isinstance(c[0][5][1], dict)
        and 'x_rabbitmq_sent' in c[0][5][1]
    ]
    assert rabbitmq_sent_calls, "x_rabbitmq_sent was never written"
    written_value = rabbitmq_sent_calls[0][0][5][1]['x_rabbitmq_sent']
    assert written_value is True


@patch('order_poller.sender')
def test_process_order_does_not_set_rabbitmq_sent_when_status_fails(mock_sender, poller):
    """x_rabbitmq_sent is NOT set when payment_status message fails."""
    order = _make_registration_order(88)
    customer = _make_customer_info()

    poller.get_customer_info = MagicMock(return_value=customer)
    poller.models.execute_kw.side_effect = [
        [{'config_id': [3, 'Inschrijvingskassa']}],
        [{'name': 'Inschrijvingskassa'}],
        True,  # res.partner write
        True,  # bus event
        True,  # x_payment_message_id write
        # x_rabbitmq_sent should NOT be called
    ]
    mock_sender.build_payment_registered_xml.return_value = (
        '<message><header><message_id>pay-88</message_id></header></message>'
    )
    mock_sender.build_payment_status_xml.return_value = '<message/>'
    mock_sender.send_typed_message.side_effect = [True, False]  # status fails

    poller.process_order(order)

    rabbitmq_sent_calls = [
        c for c in poller.models.execute_kw.call_args_list
        if len(c[0]) >= 6 and c[0][4] == 'write'
        and isinstance(c[0][5], list) and len(c[0][5]) == 2
        and isinstance(c[0][5][1], dict)
        and 'x_rabbitmq_sent' in c[0][5][1]
    ]
    assert not rabbitmq_sent_calls, "x_rabbitmq_sent should not be written on partial failure"


# ---------------------------------------------------------------------------
# process_order: invoice_request is suppressed for registration orders
# ---------------------------------------------------------------------------

@patch('order_poller.sender')
def test_process_order_no_invoice_request_for_registration(mock_sender, poller):
    """invoice_request is never sent for Inschrijvingskassa orders."""
    order = _make_registration_order(99)
    customer = _make_customer_info()

    poller.get_customer_info = MagicMock(return_value=customer)
    poller.models.execute_kw.side_effect = [
        [{'config_id': [3, 'Inschrijvingskassa']}],
        [{'name': 'Inschrijvingskassa'}],
        True, True, True, True,
    ]
    mock_sender.build_payment_registered_xml.return_value = (
        '<message><header><message_id>pay-99</message_id></header></message>'
    )
    mock_sender.build_payment_status_xml.return_value = '<message/>'
    mock_sender.send_typed_message.return_value = True

    with patch.object(poller, '_process_invoice_request') as mock_inv:
        poller.process_order(order)
        mock_inv.assert_not_called()
