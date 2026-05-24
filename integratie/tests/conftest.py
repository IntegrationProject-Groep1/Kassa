# conftest.py – pytest configuration for the Kassa integration tests
# Adds the integratie/ directory to sys.path so that receiver, sender, etc.
# can be imported directly without a package prefix.

import os
import sys

import pytest

# Set dummy environment variables to allow modules to be imported during test collection
# without failing the require_env() validation.
os.environ.setdefault("RABBIT_HOST", "localhost")
os.environ.setdefault("RABBIT_USER", "guest")
os.environ.setdefault("RABBIT_PASS", "guest")
os.environ.setdefault("ODOO_URL", "http://localhost:8069")
os.environ.setdefault("ODOO_DB", "test_db")
os.environ.setdefault("ODOO_USER", "admin")
os.environ.setdefault("ODOO_PASS", "admin")

INTEGRATIE_DIR = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(INTEGRATIE_DIR))


@pytest.fixture(autouse=True)
def isolate_outbox(tmp_path):
    """Redirect sender's outbox buffer to an empty temp dir for each test.

    Prevents the real outbox/outbox.json (which may be full from production
    use) from causing BufferFullError in tests that trigger RabbitMQ sends.
    """
    import sender
    original = sender.BUFFER_FILE
    sender.BUFFER_FILE = tmp_path / "outbox.json"
    yield
    sender.BUFFER_FILE = original


@pytest.fixture(autouse=True)
def cleanup_env():
    """Clean up important env vars before/after each test for isolation."""
    env_vars = [
        "ODOO_URL", "ODOO_DB", "ODOO_USER", "ODOO_PASS",
        "RABBIT_HOST", "RABBIT_PORT", "RABBIT_USER", "RABBIT_PASS", "RABBIT_VHOST", "RABBIT_EXCHANGE",
        "RABBIT_INCOMING_QUEUE",
        "POLL_INTERVAL", "BADGE_PAYMENT_METHOD_NAME",
        "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB",
    ]

    original_values = {var: os.environ.get(var) for var in env_vars}
    yield

    for var, value in original_values.items():
        if value is None:
            os.environ.pop(var, None)
        else:
            os.environ[var] = value
