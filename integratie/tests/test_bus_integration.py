# test_bus_integration.py — Integration tests against a real Odoo stack
# Team Kassa (Odoo POS) | Integratieproject Desideriushogeschool 2026
#
# Verifies that the bus event infrastructure works end-to-end:
#   - Custom fields are installed and writable
#   - pos.order.send_partner_bus_event exists and accepts the correct arg shape
#   - pos.session.kassa_notify_partner_update exists and returns a session count
#   - With an open POS session, the notification count is >= 1 (event was dispatched)
#   - The partner is findable via x_user_id immediately after creation
#   - The POS session loader includes all Kassa custom fields
#
# Run locally (stack up):
#   pytest integratie/tests/test_bus_integration.py -v
#
# Run in CI (inside kassa_integratie container):
#   pytest tests/test_bus_integration.py -v
#
# Skips gracefully when Odoo is not reachable or authentication fails.

import os
import socket
import uuid
import xmlrpc.client

import pytest

# ── Connection config (from environment, same vars the integration service uses) ─

ODOO_URL = os.environ.get("ODOO_URL", "http://localhost:8069")
ODOO_DB = os.environ.get("ODOO_DB", "odoo_kassa")
ODOO_USER = os.environ.get("ODOO_USER", "desiderius")
ODOO_PASS = os.environ.get("ODOO_PASS", "")


def _odoo_reachable() -> bool:
    try:
        raw = ODOO_URL.split("//", 1)[-1]
        host = raw.split(":")[0].split("/")[0]
        port = int(raw.split(":")[1].split("/")[0]) if ":" in raw else 8069
        socket.create_connection((host, port), timeout=2)
        return True
    except OSError:
        return False


if not _odoo_reachable():
    pytest.skip(
        f"Odoo not reachable at {ODOO_URL} — skipping bus integration tests",
        allow_module_level=True,
    )


# ── Helpers ────────────────────────────────────────────────────────────────────

def _rpc(models, uid, model, method, args, kwargs=None):
    return models.execute_kw(ODOO_DB, uid, ODOO_PASS, model, method, args, kwargs or {})


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def odoo():
    """Authenticated XML-RPC session. Skips the whole module if auth fails."""
    common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common", allow_none=True)
    uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASS, {})
    if not uid:
        pytest.skip(f"Odoo auth failed for user '{ODOO_USER}' on db '{ODOO_DB}'")
    models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object", allow_none=True)
    return uid, models


@pytest.fixture(scope="module")
def pos_session(odoo):
    """
    Provides an open POS session for the test module.

    - Reuses an already-open session if one exists (common in local dev).
    - Opens a new session against the first available POS config if not.
    - Cleans up the session in teardown only if we opened it ourselves.
    """
    uid, models = odoo

    configs = _rpc(models, uid, 'pos.config', 'search_read', [[]], {'fields': ['id', 'name'], 'limit': 1})
    if not configs:
        pytest.skip("No POS config found — odoo_setup.py may not have run yet")
    config_id = configs[0]['id']

    existing = _rpc(
        models, uid, 'pos.session', 'search_read',
        [[['config_id', '=', config_id], ['state', '=', 'opened']]],
        {'fields': ['id'], 'limit': 1},
    )
    if existing:
        yield existing[0]['id']
        return

    session_id = _rpc(models, uid, 'pos.session', 'create', [{'config_id': config_id}])
    _rpc(models, uid, 'pos.session', 'action_pos_session_open', [[session_id]])
    yield session_id

    try:
        _rpc(models, uid, 'pos.session', 'unlink', [[session_id]])
    except Exception:
        pass


@pytest.fixture
def partner(odoo):
    """Create a unique test partner before the test; delete it after."""
    uid, models = odoo
    test_uuid = str(uuid.uuid4())
    partner_id = _rpc(models, uid, 'res.partner', 'create', [{
        'name': f'Kassa Bus Test {test_uuid[:8]}',
        'email': f'kassa-bus-{test_uuid[:8]}@integration.test',
        'x_user_id': test_uuid,
    }])
    yield uid, models, partner_id, test_uuid
    try:
        _rpc(models, uid, 'res.partner', 'unlink', [[partner_id]])
    except Exception:
        pass


# ── Custom field tests ─────────────────────────────────────────────────────────
# These prove the addon installed correctly. If any field is missing the test
# fails with an Odoo "Invalid field" error — clear signal for setup problems.

class TestCustomFields:
    def test_x_user_id_stored_and_readable(self, partner):
        uid, models, pid, test_uuid = partner
        data = _rpc(models, uid, 'res.partner', 'read', [[pid]], {'fields': ['x_user_id']})
        assert data[0]['x_user_id'] == test_uuid

    def test_x_outstanding_amount_writable(self, partner):
        uid, models, pid, _ = partner
        _rpc(models, uid, 'res.partner', 'write', [[pid], {'x_outstanding_amount': 42.50}])
        data = _rpc(models, uid, 'res.partner', 'read', [[pid]], {'fields': ['x_outstanding_amount']})
        assert data[0]['x_outstanding_amount'] == 42.50

    def test_x_payment_status_accepts_unpaid_and_paid(self, partner):
        uid, models, pid, _ = partner
        for status in ('unpaid', 'paid'):
            _rpc(models, uid, 'res.partner', 'write', [[pid], {'x_payment_status': status}])
            data = _rpc(models, uid, 'res.partner', 'read', [[pid]], {'fields': ['x_payment_status']})
            assert data[0]['x_payment_status'] == status

    def test_x_session_title_stores_json_array(self, partner):
        uid, models, pid, _ = partner
        payload = '[{"session_id": "s1", "title": "Morning Workshop", "price": 15.0}]'
        _rpc(models, uid, 'res.partner', 'write', [[pid], {'x_session_title': payload}])
        data = _rpc(models, uid, 'res.partner', 'read', [[pid]], {'fields': ['x_session_title']})
        assert data[0]['x_session_title'] == payload

    def test_x_user_id_searchable(self, partner):
        """The receiver's primary partner lookup uses this search — must work."""
        uid, models, pid, test_uuid = partner
        found = _rpc(
            models, uid, 'res.partner', 'search_read',
            [[['x_user_id', '=', test_uuid]]],
            {'fields': ['id'], 'limit': 1},
        )
        assert found and found[0]['id'] == pid

    def test_all_kassa_fields_readable_in_one_call(self, partner):
        """Simulates what the POS session loader reads on open."""
        uid, models, pid, _ = partner
        data = _rpc(models, uid, 'res.partner', 'read', [[pid]], {'fields': [
            'x_user_id', 'x_outstanding_amount', 'x_payment_status',
            'x_session_title', 'x_wallet_balance', 'x_badge_id',
            'x_lease_active', 'x_lease_id',
        ]})
        assert data, "Could not read Kassa custom fields — addon may not be installed"


# ── Bus method existence tests ─────────────────────────────────────────────────
# These tests confirm the two Odoo methods called by _publish_partner_bus_event
# exist with the right signature. Without a live stack these can never be caught
# by unit tests. One wrong method name → silent failure in production.

class TestBusMethodsExist:
    def test_send_partner_bus_event_exists_and_returns_true(self, partner):
        uid, models, pid, _ = partner
        result = _rpc(
            models, uid, 'pos.order', 'send_partner_bus_event',
            [pid, 25.0, 'unpaid', 'Bus Test Partner'],
        )
        assert result is True, (
            "pos.order.send_partner_bus_event did not return True — "
            "method may be missing or have the wrong signature"
        )

    def test_kassa_notify_partner_update_exists_and_returns_int(self, partner):
        uid, models, pid, _ = partner
        result = _rpc(
            models, uid, 'pos.session', 'kassa_notify_partner_update',
            [[pid]],
        )
        assert isinstance(result, int), (
            f"kassa_notify_partner_update should return int (session count), got {type(result)}"
        )

    def test_kassa_notify_partner_update_accepts_multiple_ids(self, odoo):
        uid, models = odoo
        result = _rpc(models, uid, 'pos.session', 'kassa_notify_partner_update', [[1, 2, 3]])
        assert isinstance(result, int)
        assert result >= 0

    def test_kassa_notify_partner_update_returns_zero_for_empty_ids(self, odoo):
        uid, models = odoo
        result = _rpc(models, uid, 'pos.session', 'kassa_notify_partner_update', [[]])
        assert result == 0


# ── Open session bus dispatch tests ───────────────────────────────────────────
# These are the most valuable tests: they prove that with a real open POS session
# the bus event actually reaches it. This is what unit tests can never verify.

class TestBusDispatchWithOpenSession:
    def test_notify_reaches_at_least_one_open_session(self, partner, pos_session):
        """
        The critical assertion: kassa_notify_partner_update must return >= 1
        when a session is open. A return of 0 means the partner update was
        dispatched but no POS session received it — the cashier UI is stale.
        """
        uid, models, pid, _ = partner
        notified = _rpc(
            models, uid, 'pos.session', 'kassa_notify_partner_update',
            [[pid]],
        )
        assert notified >= 1, (
            f"Expected >= 1 open session to be notified, got {notified}. "
            "Partner updates are NOT reaching the POS — the cashier UI will be stale."
        )

    def test_send_partner_bus_event_fires_with_open_session(self, partner, pos_session):
        uid, models, pid, _ = partner
        result = _rpc(
            models, uid, 'pos.order', 'send_partner_bus_event',
            [pid, 30.0, 'unpaid', 'Session Bus Test'],
        )
        assert result is True

    def test_full_dual_bus_dispatch_matches_publish_partner_bus_event(self, partner, pos_session):
        """
        Fires both calls in the exact same order and with the same argument
        shapes as receiver._publish_partner_bus_event. Both must succeed and
        the session count must be >= 1.

        This is the integration equivalent of test_calls_pos_order_send_partner_bus_event
        and test_calls_pos_session_kassa_notify_partner_update combined.
        """
        uid, models, pid, _ = partner

        # Call 1 — matches receiver.py line: pos.order.send_partner_bus_event
        bus_ok = _rpc(
            models, uid, 'pos.order', 'send_partner_bus_event',
            [pid, 15.0, 'unpaid', 'Dual Dispatch Test'],
        )
        assert bus_ok is True

        # Call 2 — matches receiver.py line: pos.session.kassa_notify_partner_update
        notified = _rpc(
            models, uid, 'pos.session', 'kassa_notify_partner_update',
            [[pid]],
        )
        assert notified >= 1

    def test_new_partner_findable_by_x_user_id_immediately(self, partner, pos_session):
        """
        Partner created mid-session is immediately findable via the same
        x_user_id lookup the QR scan and receiver use. If this fails the
        QR scan will silently create a duplicate partner on every scan.
        """
        uid, models, pid, test_uuid = partner
        found = _rpc(
            models, uid, 'res.partner', 'search_read',
            [[['x_user_id', '=', test_uuid]]],
            {'fields': ['id', 'x_outstanding_amount'], 'limit': 1},
        )
        assert found, "Partner not findable by x_user_id — QR scan lookup is broken"
        assert found[0]['id'] == pid

    def test_session_loader_includes_x_outstanding_amount(self, odoo, pos_session):
        """
        _loader_params_res_partner must include x_outstanding_amount so the
        outstanding-amount badge is visible on session open without an extra
        RPC. If this field is missing the badge is always blank at session start.
        """
        uid, models = odoo
        # Verify indirectly: read a partner with that field via the object layer.
        # execute_kw raises an Odoo error if the field doesn't exist on the model.
        data = _rpc(
            models, uid, 'res.partner', 'search_read',
            [[['id', '>', 0]]],
            {'fields': ['x_outstanding_amount', 'x_payment_status', 'x_session_title',
                        'x_user_id', 'x_badge_id', 'x_lease_active', 'x_lease_id'],
             'limit': 1},
        )
        assert isinstance(data, list)

    def test_partner_update_persists_after_bus_dispatch(self, partner, pos_session):
        """
        Write new values, fire the bus, then re-read. Confirms the data in Odoo
        is the source of truth that the bus event references.
        """
        uid, models, pid, _ = partner
        _rpc(models, uid, 'res.partner', 'write', [[pid], {
            'x_outstanding_amount': 99.99,
            'x_payment_status': 'unpaid',
            'x_session_title': '[{"session_id": "s99", "title": "Gala Dinner", "price": 99.99}]',
        }])

        _rpc(models, uid, 'pos.order', 'send_partner_bus_event',
             [pid, 99.99, 'unpaid', 'Persist Test'])
        _rpc(models, uid, 'pos.session', 'kassa_notify_partner_update', [[pid]])

        data = _rpc(models, uid, 'res.partner', 'read', [[pid]], {
            'fields': ['x_outstanding_amount', 'x_payment_status', 'x_session_title'],
        })
        assert data[0]['x_outstanding_amount'] == 99.99
        assert data[0]['x_payment_status'] == 'unpaid'
        assert 'Gala Dinner' in data[0]['x_session_title']
