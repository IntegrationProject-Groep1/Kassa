import pytest
from unittest.mock import MagicMock, patch
from order_poller import OrderPoller
import sender


def test_is_topup_product_fallback():
    poller = OrderPoller()
    poller.models = MagicMock()
    poller.models.execute_kw.return_value = [{'id': 99, 'name': 'Drinks & Top-ups'}]

    product_info = {'pos_categ_ids': [99]}

    # Act
    is_topup = poller.is_topup_product(1, {1: product_info})

    # Assert
    assert is_topup is True
    poller.models.execute_kw.assert_called_once()
    args = poller.models.execute_kw.call_args[0]
    assert args[3] == 'pos.category'
    assert args[4] == 'read'


def test_is_topup_product_fallback_no_match():
    poller = OrderPoller()
    poller.models = MagicMock()
    poller.models.execute_kw.return_value = [{'id': 99, 'name': 'Food'}]

    product_info = {'pos_categ_ids': [99]}

    # Act
    is_topup = poller.is_topup_product(1, {1: product_info})

    # Assert
    assert is_topup is False


@patch('sender.get_buffered_record_ids')
@patch('sender.build_badge_assigned_xml')
@patch('sender.send_typed_message')
def test_poll_badge_assignments_xsd_error(mock_send, mock_build, mock_buffered):
    poller = OrderPoller()
    poller.odoo_db = 'test_db'
    poller.odoo_uid = 1
    poller.odoo_pass = 'test_pass'
    poller.models = MagicMock()

    mock_buffered.return_value = set()

    # Setup mock to return a partner during search and read
    def execute_kw_side_effect(db, uid, pwd, model, method, *args, **kwargs):
        if method == 'search':
            return [10]
        elif method == 'read':
            return [{'id': 10, 'x_badge_id': 'BADGE123', 'x_user_id': 'USER123'}]
        elif method == 'write':
            return True
        return []

    poller.models.execute_kw.side_effect = execute_kw_side_effect

    # Make send_typed_message raise XSDValidationError
    mock_send.side_effect = sender.XSDValidationError("Fake XSD Error")

    # Act
    poller.poll_badge_assignments()

    # Assert
    # Verify that a write was called on res.partner to set x_badge_sent and x_rabbitmq_error
    write_calls = [c for c in poller.models.execute_kw.call_args_list if c[0][4] == 'write']
    assert len(write_calls) > 0
    write_args = write_calls[0][0][5]
    assert write_args[0] == [10]
    assert 'x_badge_sent' in write_args[1]
    assert write_args[1]['x_badge_sent'] is True
    assert 'x_rabbitmq_error' in write_args[1]
    assert "Fake XSD Error" in write_args[1]['x_rabbitmq_error']


@patch('sender._validate_outgoing')
@patch('sender.send_error_to_queue')
def test_sender_xxe_mitigation(mock_send_error, mock_validate):
    # Simulate _validate_outgoing failing (e.g. malformed or xsd violation)
    mock_validate.side_effect = ValueError("Validation Failed")

    xxe_payload = (
        '<?xml version="1.0"?>'
        '<!DOCTYPE message [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
        '<message><header><message_id>&xxe;</message_id></header></message>'
    )

    with pytest.raises(sender.XSDValidationError):
        sender.send_typed_message("consumption_order", xxe_payload)

    # The XXE attack should cause defusedxml to throw EntitiesForbidden internally,
    # which is caught, leaving related_message_id as None.
    mock_send_error.assert_called_once()
    args, kwargs = mock_send_error.call_args
    assert args[1] is None  # related_message_id should be None


@patch('order_poller.sender')
def test_process_consumption_zero_value_fallback(mock_sender):
    poller = OrderPoller()
    poller.models = MagicMock()

    def execute_kw_side_effect(db, uid, pwd, model, method, *args, **kwargs):
        if model == 'pos.order.line' and method == 'read':
            return [{
                'id': 100,
                'product_id': [1, 'Test Product'],
                'qty': 1,
                'price_unit': 10.0,
                'tax_ids': [],
                'price_subtotal_incl': 0.0  # ZERO VALUE, e.g. 100% discount
            }]
        return []

    poller.models.execute_kw.side_effect = execute_kw_side_effect

    order = {'id': 1, 'lines': [100], 'amount_total': 0.0, 'payment_ids': []}
    customer_info = {'id': 1, 'name': 'Test', 'customer_type': 'private'}

    mock_sender.build_payment_registered_xml.return_value = "<xml/>"
    mock_sender.build_consumption_order_xml.return_value = "<xml><header><message_id>123</message_id></header></xml>"

    # Act
    poller._process_consumption(order, customer_info, is_anonymous=False)

    # Assert
    # Extract the items passed to build_consumption_order_xml
    call_args = mock_sender.build_consumption_order_xml.call_args[1]
    items = call_args['items']
    assert len(items) == 1
    # If 'or' fallback was present, total_incl would be 10.0 (qty*price_unit).
    # With 'get(..., qty*price_unit)' fallback, total_incl should be 0.0 because 0.0 is passed.
    assert items[0]['total_amount'] == 0.0
