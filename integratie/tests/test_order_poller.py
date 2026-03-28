"""
Test suite for Order Poller module
"""
import pytest
import os
from unittest.mock import Mock, patch, MagicMock


def test_order_poller_initialization():
    """Test that OrderPoller initializes with environment variables"""
    # Set minimal environment variables
    os.environ['ODOO_URL'] = 'http://test:8069'
    os.environ['ODOO_DB'] = 'test_db'
    os.environ['ODOO_USER'] = 'test_user'
    os.environ['ODOO_PASS'] = 'test_pass'
    os.environ['RABBIT_HOST'] = 'localhost'
    os.environ['RABBIT_USER'] = 'guest'
    os.environ['RABBIT_PASS'] = 'guest'
    os.environ['RABBIT_EXCHANGE'] = 'test.exchange'
    
    from order_poller import OrderPoller
    
    poller = OrderPoller()
    
    assert poller.odoo_url == 'http://test:8069'
    assert poller.odoo_db == 'test_db'
    assert len(poller.processed_orders) == 0


def test_outbox_directory_creation():
    """Test that outbox directory is created on initialization"""
    os.environ['ODOO_URL'] = 'http://test:8069'
    os.environ['ODOO_DB'] = 'test_db'
    os.environ['ODOO_USER'] = 'test_user'
    os.environ['ODOO_PASS'] = 'test_pass'
    os.environ['RABBIT_HOST'] = 'localhost'
    os.environ['RABBIT_USER'] = 'guest'
    os.environ['RABBIT_PASS'] = 'guest'
    os.environ['RABBIT_EXCHANGE'] = 'test.exchange'
    
    from order_poller import OrderPoller
    from pathlib import Path
    
    poller = OrderPoller()
    
    assert poller.outbox_dir.exists()
    assert poller.outbox_dir.is_dir()


@patch('order_poller.xmlrpc.client.ServerProxy')
def test_connect_odoo_success(mock_server_proxy):
    """Test successful Odoo connection"""
    os.environ['ODOO_URL'] = 'http://test:8069'
    os.environ['ODOO_DB'] = 'test_db'
    os.environ['ODOO_USER'] = 'test_user'
    os.environ['ODOO_PASS'] = 'test_pass'
    os.environ['RABBIT_HOST'] = 'localhost'
    os.environ['RABBIT_USER'] = 'guest'
    os.environ['RABBIT_PASS'] = 'guest'
    os.environ['RABBIT_EXCHANGE'] = 'test.exchange'
    
    from order_poller import OrderPoller
    
    # Mock successful authentication
    mock_common = MagicMock()
    mock_common.authenticate.return_value = 1  # uid = 1
    mock_server_proxy.return_value = mock_common
    
    poller = OrderPoller()
    result = poller.connect_odoo()
    
    assert result is True
    assert poller.odoo_uid == 1


@patch('order_poller.xmlrpc.client.ServerProxy')
def test_connect_odoo_failure(mock_server_proxy):
    """Test failed Odoo connection"""
    os.environ['ODOO_URL'] = 'http://test:8069'
    os.environ['ODOO_DB'] = 'test_db'
    os.environ['ODOO_USER'] = 'test_user'
    os.environ['ODOO_PASS'] = 'test_pass'
    os.environ['RABBIT_HOST'] = 'localhost'
    os.environ['RABBIT_USER'] = 'guest'
    os.environ['RABBIT_PASS'] = 'guest'
    os.environ['RABBIT_EXCHANGE'] = 'test.exchange'
    
    from order_poller import OrderPoller
    
    # Mock connection error
    mock_server_proxy.side_effect = Exception('Connection refused')
    
    poller = OrderPoller()
    result = poller.connect_odoo()
    
    assert result is False
