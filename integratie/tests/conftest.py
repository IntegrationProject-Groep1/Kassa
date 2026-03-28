"""
Pytest configuration and fixtures
"""
import pytest
import sys
import os
from pathlib import Path

# Add parent directory to path so we can import modules
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(autouse=True)
def cleanup_env():
    """Clean up environment variables before each test"""
    env_vars = [
        'ODOO_URL', 'ODOO_DB', 'ODOO_USER', 'ODOO_PASS',
        'RABBIT_HOST', 'RABBIT_USER', 'RABBIT_PASS', 'RABBIT_EXCHANGE',
        'POLL_INTERVAL', 'BADGE_PAYMENT_METHOD_NAME',
        'POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_DB'
    ]
    
    original_values = {}
    for var in env_vars:
        original_values[var] = os.environ.get(var)
    
    yield
    
    # Restore original values
    for var, value in original_values.items():
        if value is None:
            os.environ.pop(var, None)
        else:
            os.environ[var] = value
