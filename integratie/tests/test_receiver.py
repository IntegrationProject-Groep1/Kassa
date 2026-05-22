# test_receiver.py – Unit tests for receiver.py
# Team Kassa (Odoo POS) | Integratieproject Desideriushogeschool 2026
#
# Run with:  pytest tests/test_receiver.py -v
#
# All Odoo XML-RPC calls and RabbitMQ interactions are mocked.
# No live services are required.

import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, patch

import pytest

import receiver


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clear_idempotency_cache():
    """Reset the in-memory LRU cache before and after each test."""
    receiver.seen_message_ids.clear()
    yield
    receiver.seen_message_ids.clear()


@pytest.fixture
def odoo():
    """Return (uid, models_mock) mimicking get_odoo_connection()."""
    uid = 1
    models = MagicMock()
    return uid, models


@pytest.fixture
def ch():
    """Mock RabbitMQ channel."""
    return MagicMock()


@pytest.fixture
def method():
    """Mock RabbitMQ method with a delivery tag."""
    m = MagicMock()
    m.delivery_tag = 42
    return m


# ── Helpers ────────────────────────────────────────────────────────────────────

def _xml_bytes(msg_type: str, body_xml: str, message_id: str = "test-msg-001") -> bytes:
    """Build a minimal valid message XML for tests."""
    source = "iot_gateway" if msg_type == "badge_scanned" else "crm"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<message>"
        "<header>"
        f"<message_id>{message_id}</message_id>"
        f"<type>{msg_type}</type>"
        f"<source>{source}</source>"
        "<timestamp>2026-03-28T12:00:00Z</timestamp>"
        "<version>2.0</version>"
        "</header>"
        f"<body>{body_xml}</body>"
        "</message>"
    ).encode("utf-8")


# ── is_duplicate ───────────────────────────────────────────────────────────────

class TestIsDuplicate:
    def test_first_seen_returns_false(self):
        assert receiver.is_duplicate("msg-abc") is False

    def test_second_seen_returns_true(self):
        receiver.is_duplicate("msg-abc")
        assert receiver.is_duplicate("msg-abc") is True

    def test_different_ids_not_duplicate(self):
        assert receiver.is_duplicate("msg-001") is False
        assert receiver.is_duplicate("msg-002") is False

    def test_lru_eviction(self):
        # Fill cache to MAX_CACHE_SIZE + 1; first entry should be evicted
        original_max = receiver.MAX_CACHE_SIZE
        receiver.MAX_CACHE_SIZE = 3
        try:
            receiver.is_duplicate("a")
            receiver.is_duplicate("b")
            receiver.is_duplicate("c")
            receiver.is_duplicate("d")  # triggers eviction of "a"
            # "a" was evicted → no longer a duplicate
            assert receiver.is_duplicate("a") is False
            # re-adding "a" evicts "b" as well; "c" and "d" survive
            assert receiver.is_duplicate("c") is True
            assert receiver.is_duplicate("d") is True
        finally:
            receiver.MAX_CACHE_SIZE = original_max


# ── validate_xml ───────────────────────────────────────────────────────────────

class TestValidateXml:
    def test_unknown_type_skips_validation(self):
        # Should not raise – schema is simply absent
        receiver.validate_xml("<message/>", "totally_unknown_type")

    def test_missing_schema_file_skips_validation(self, tmp_path, monkeypatch):
        # Point SCHEMA_MAP to a non-existent file
        monkeypatch.setitem(receiver.SCHEMA_MAP, "badge_scanned", str(tmp_path / "missing.xsd"))
        receiver.validate_xml("<message/>", "badge_scanned")  # should not raise

    def test_valid_badge_scanned_xml_passes(self):
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<message>"
            "<header>"
            "<message_id>550e8400-e29b-41d4-a716-446655440000</message_id>"
            "<timestamp>2026-03-28T12:00:00Z</timestamp>"
            "<source>kassa</source>"
            "<type>badge_scanned</type>"
            "<version>2.0</version>"
            "</header>"
            "<body><badge_id>BADGE-001</badge_id>"
            "<location>bar</location>"
            "<scanned_at>2026-03-28T12:00:00Z</scanned_at></body>"
            "</message>"
        )
        receiver.validate_xml(xml, "badge_scanned")  # should not raise

    def test_valid_user_event_passes(self):
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<user_event>"
            "<event>UserCreated</event>"
            "<master_uuid>a1b2c3d4-e5f6-7890-abcd-ef1234567890</master_uuid>"
            "<email>jan.peeters@ehb.be</email>"
            "<source_system>frontend</source_system>"
            "<timestamp>2026-05-08T10:00:00</timestamp>"
            "</user_event>"
        )
        receiver.validate_xml(xml, "user_event")  # should not raise

    def test_invalid_user_event_raises(self):
        # Missing required fields — should fail XSD validation
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<user_event>"
            "<event>UserCreated</event>"
            "</user_event>"
        )
        with pytest.raises(ValueError, match="XSD validation failed"):
            receiver.validate_xml(xml, "user_event")


# ── process_new_registration ───────────────────────────────────────────────────

class TestProcessNewRegistration:
    NEW_REG_BODY = (
        "<customer>"
        "<identity_uuid>550e8400-e29b-41d4-a716-446655440001</identity_uuid>"
        "<email>test@example.com</email>"
        "<date_of_birth>1996-01-01</date_of_birth>"
        "<contact><first_name>Alice</first_name><last_name>Wonderland</last_name></contact>"
        "<type>private</type>"
        "<session_id>sess-001</session_id>"
        "<payment_due><amount currency=\"eur\">25.00</amount><status>unpaid</status></payment_due>"
        "</customer>"
    )

    def _root(self):
        return ET.fromstring(
            "<message><header/><body>" + self.NEW_REG_BODY + "</body></message>"
        )

    def test_creates_new_partner_when_not_found(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [],   # search_read → no existing partner
            99,   # create → new partner id
        ]
        receiver.process_new_registration(self._root(), uid, models)

        create_call = models.execute_kw.call_args_list[1]
        assert create_call[0][4] == "create"
        vals = create_call[0][5][0]
        assert vals["x_user_id"] == "550e8400-e29b-41d4-a716-446655440001"
        assert vals["name"] == "Alice Wonderland"
        assert vals["is_company"] is False

    def test_updates_existing_partner(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [{"id": 5, "name": "Alice", "x_user_id": "550e8400-e29b-41d4-a716-446655440001"}],  # search_read
            True,                                                    # write
        ]
        receiver.process_new_registration(self._root(), uid, models)

        write_call = models.execute_kw.call_args_list[1]
        assert write_call[0][4] == "write"
        assert write_call[0][5][0] == [5]

    def test_raises_when_identity_uuid_missing(self, odoo):
        uid, models = odoo
        root = ET.fromstring(
            "<message><header/><body>"
            "<customer>"
            "<email>a@b.com</email><contact><first_name>X</first_name>"
            "<last_name>Y</last_name></contact><type>private</type>"
            "<payment_due><amount currency=\"eur\">0</amount><status>unpaid</status></payment_due>"
            "</customer>"
            "</body></message>"
        )
        with pytest.raises(ValueError, match="identity_uuid missing"):
            receiver.process_new_registration(root, uid, models)

    def test_company_sets_is_company_true(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [[], 10]
        root = ET.fromstring(
            "<message><header/><body>"
            "<customer>"
            "<identity_uuid>550e8400-e29b-41d4-a716-446655440002</identity_uuid>"
            "<email>info@corp.be</email><contact><first_name>Corp</first_name><last_name>Member</last_name></contact>"
            "<company_name>Corp NV</company_name><date_of_birth>1990-01-01</date_of_birth>"
            "<type>company</type><vat_number>BE0123</vat_number>"
            "<session_id>s1</session_id>"
            "<payment_due><amount currency=\"eur\">100</amount><status>paid</status></payment_due>"
            "</customer>"
            "</body></message>"
        )
        receiver.process_new_registration(root, uid, models)
        create_call = models.execute_kw.call_args_list[1]
        vals = create_call[0][5][0]
        assert vals["is_company"] is True
        assert vals["vat"] == "BE0123"


# ── process_wallet_lease_grant ────────────────────────────────────────────────

class TestProcessWalletLeaseGrant:
    def _make_grant_xml(self, payment_due=None):
        payment_due_el = (
            f'<payment_due><amount currency="eur">{payment_due}</amount></payment_due>'
            if payment_due is not None else ""
        )
        return ET.fromstring(
            "<message><header/><body>"
            "<identity_uuid>550e8400-e29b-41d4-a716-446655440000</identity_uuid>"
            '<current_balance currency="eur">50.00</current_balance>'
            "<lease_id>LEASE-001</lease_id>"
            f"{payment_due_el}"
            "</body></message>"
        )

    def test_grant_with_amount_due_sets_outstanding(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [{"id": 7, "name": "Jan Peeters", "x_payment_status": "unpaid"}],  # search_read
            True,   # write
            True,   # bus event
        ]
        receiver.process_wallet_lease_grant(self._make_grant_xml(payment_due=25.0), uid, models)

        write_call = models.execute_kw.call_args_list[1]
        written_vals = write_call[0][5][1]
        assert written_vals["x_outstanding_amount"] == 25.0
        assert written_vals["x_wallet_balance"] == 50.0
        assert written_vals["x_lease_active"] is True

    def test_grant_without_amount_due_does_not_set_outstanding(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [{"id": 7, "name": "Jan Peeters", "x_payment_status": "unpaid"}],  # search_read
            True,   # write
            True,   # bus event
        ]
        receiver.process_wallet_lease_grant(self._make_grant_xml(), uid, models)

        write_call = models.execute_kw.call_args_list[1]
        written_vals = write_call[0][5][1]
        assert "x_outstanding_amount" not in written_vals

    def test_grant_publishes_bus_event(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [{"id": 7, "name": "Jan Peeters", "x_payment_status": "unpaid"}],
            True,
            True,
        ]
        receiver.process_wallet_lease_grant(self._make_grant_xml(payment_due=25.0), uid, models)

        bus_call = models.execute_kw.call_args_list[2]
        assert bus_call[0][3] == "pos.order"
        assert bus_call[0][4] == "send_partner_bus_event"

    def test_grant_unknown_partner_logs_warning(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [[]]  # search_read → not found
        receiver.process_wallet_lease_grant(self._make_grant_xml(payment_due=25.0), uid, models)
        assert models.execute_kw.call_count == 1  # only the search, no write


# ── _ensure_session_product ────────────────────────────────────────────────────

class TestEnsureSessionProduct:
    def test_creates_product_when_not_found(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [],          # search_read product.template → not found
            [{"id": 10}],  # search_read pos.category "Sessions"
            42,          # create product.template → new id
        ]
        receiver._ensure_session_product(uid, models, "Workshop: IoT met Python")

        create_call = models.execute_kw.call_args_list[2]
        assert create_call[0][3] == "product.template"
        assert create_call[0][4] == "create"
        vals = create_call[0][5][0]
        assert vals["name"] == "Workshop: IoT met Python"
        assert vals["available_in_pos"] is True
        assert vals["type"] == "consu"
        assert vals["list_price"] == 0.0

    def test_skips_when_product_already_exists(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [{"id": 7, "list_price": 0.0}],  # search_read product.template → found, same price
        ]
        receiver._ensure_session_product(uid, models, "Workshop: IoT met Python")

        # Only one XML-RPC call (the search); no create, no price write
        assert models.execute_kw.call_count == 1

    def test_creates_product_with_price(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [],            # product not found
            [{"id": 10}],  # Sessions category found
            42,            # create
        ]
        receiver._ensure_session_product(uid, models, "Keynote", price=15.0)

        create_call = models.execute_kw.call_args_list[2]
        assert create_call[0][5][0]["list_price"] == 15.0

    def test_updates_price_when_product_exists_with_different_price(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [{"id": 7, "list_price": 0.0}],  # found, price differs
            True,                             # write
        ]
        receiver._ensure_session_product(uid, models, "Keynote", price=25.0)

        write_call = models.execute_kw.call_args_list[1]
        assert write_call[0][4] == "write"
        assert write_call[0][5][1]["list_price"] == 25.0

    def test_no_price_write_when_price_unchanged(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [{"id": 7, "list_price": 25.0}],  # found, same price
        ]
        receiver._ensure_session_product(uid, models, "Keynote", price=25.0)

        assert models.execute_kw.call_count == 1

    def test_new_registration_with_session_title_calls_ensure_product(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [],              # search_read res.partner → not found
            99,              # create partner
            [],              # search_read product.template → not found
            [{"id": 10}],   # search_read pos.category
            55,              # create product
            True,            # pos.order.send_partner_bus_event
        ]
        root = ET.fromstring(
            "<message><header/><body>"
            "<customer>"
            "<identity_uuid>550e8400-e29b-41d4-a716-446655440099</identity_uuid>"
            "<email>t@t.com</email>"
            "<contact><first_name>Jan</first_name><last_name>Jansen</last_name></contact>"
            "<type>private</type>"
            "<session_title>Workshop: IoT met Python</session_title>"
            "<payment_due><amount currency=\"eur\">25.00</amount><status>unpaid</status></payment_due>"
            "</customer>"
            "</body></message>"
        )
        receiver.process_new_registration(root, uid, models)

        # Verify product creation was called with the correct session title
        product_create = next(
            c for c in models.execute_kw.call_args_list
            if c[0][3] == "product.template" and c[0][4] == "create"
        )
        assert product_create[0][5][0]["name"] == "Workshop: IoT met Python"

    def test_new_registration_without_session_title_skips_product(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [],   # search_read res.partner → not found
            99,   # create partner
            True,  # bus event
        ]
        root = ET.fromstring(
            "<message><header/><body>"
            "<customer>"
            "<identity_uuid>550e8400-e29b-41d4-a716-446655440099</identity_uuid>"
            "<email>t@t.com</email>"
            "<contact><first_name>Jan</first_name><last_name>Jansen</last_name></contact>"
            "<type>private</type>"
            "<payment_due><amount currency=\"eur\">25.00</amount><status>unpaid</status></payment_due>"
            "</customer>"
            "</body></message>"
        )
        receiver.process_new_registration(root, uid, models)

        # No product.template calls
        product_calls = [
            c for c in models.execute_kw.call_args_list
            if c[0][3] == "product.template"
        ]
        assert product_calls == []


# ── process_user_sessions_response ────────────────────────────────────────────

class TestProcessUserSessionsResponse:
    """Tests for process_user_sessions_response — QR-scan per-user session handler."""

    def _make_root(self, sessions_xml: str, status: str = "ok", count: int = 1,
                   correlation_id: str = "550e8400-e29b-41d4-a716-446655440002") -> ET.Element:
        xml = (
            "<message>"
            "<header>"
            f"<message_id>550e8400-e29b-41d4-a716-446655440000</message_id>"
            "<timestamp>2026-05-13T09:00:00Z</timestamp>"
            "<source>planning</source>"
            "<type>user_sessions_response</type>"
            "<version>2.0</version>"
            f"<correlation_id>{correlation_id}</correlation_id>"
            "</header>"
            "<body>"
            f"<status>{status}</status>"
            f"<session_count>{count}</session_count>"
            f"<sessions>{sessions_xml}</sessions>"
            "</body>"
            "</message>"
        )
        return ET.fromstring(xml)

    def _session_xml(self, title: str = "Workshop A", price: str = "20.00") -> str:
        return (
            "<session>"
            "<session_id>sess-001</session_id>"
            f"<title>{title}</title>"
            "<start_datetime>2026-05-15T10:00:00Z</start_datetime>"
            "<end_datetime>2026-05-15T12:00:00Z</end_datetime>"
            "<location>B2</location>"
            "<session_type>workshop</session_type>"
            "<status>published</status>"
            "<max_attendees>30</max_attendees>"
            "<current_attendees>5</current_attendees>"
            f'<price currency="eur">{price}</price>'
            "</session>"
        )

    def test_creates_product_for_session(self, odoo):
        uid, models = odoo
        root = self._make_root(self._session_xml("Workshop A", "20.00"))
        models.execute_kw.side_effect = [
            [],            # x_session_id search → not found
            [],            # name search → not found
            [{"id": 10}],  # Sessions category
            99,            # create product
            1,             # kassa_notify_product_update
        ]
        receiver.process_user_sessions_response(root, uid, models)

        create_call = models.execute_kw.call_args_list[3]
        assert create_call[0][4] == "create"
        vals = create_call[0][5][0]
        assert vals["name"] == "Workshop A"
        assert vals["list_price"] == 20.0

    def test_no_action_when_status_not_found(self, odoo):
        uid, models = odoo
        root = self._make_root("", status="not_found", count=0)
        receiver.process_user_sessions_response(root, uid, models)
        models.execute_kw.assert_not_called()

    def test_no_action_when_sessions_empty(self, odoo):
        uid, models = odoo
        root = self._make_root("", status="ok", count=0)
        receiver.process_user_sessions_response(root, uid, models)
        models.execute_kw.assert_not_called()

    def test_bus_notify_called_after_products_ensured(self, odoo):
        """kassa_notify_product_update is called once after all products are ensured."""
        uid, models = odoo
        root = self._make_root(self._session_xml("QR Session", "15.00"))
        models.execute_kw.side_effect = [
            [],            # product not found
            [{"id": 5}],   # category found
            88,            # create
            1,             # notify
        ]
        receiver.process_user_sessions_response(root, uid, models)

        notify_call = models.execute_kw.call_args_list[3]
        assert notify_call[0][3] == "pos.session"
        assert notify_call[0][4] == "kassa_notify_product_update"

    def test_bus_notify_called_even_when_product_already_exists(self, odoo):
        """Notify fires regardless of whether a new product was created or already existed."""
        uid, models = odoo
        root = self._make_root(self._session_xml())
        models.execute_kw.side_effect = [
            # found by x_session_id with all fields in sync → no write
            [{"id": 7, "name": "Workshop A", "list_price": 20.0, "x_session_id": "sess-001"}],
            1,  # notify
        ]
        receiver.process_user_sessions_response(root, uid, models)

        notify_call = models.execute_kw.call_args_list[1]
        assert notify_call[0][3] == "pos.session"
        assert notify_call[0][4] == "kassa_notify_product_update"

    def test_bus_notify_failure_does_not_crash_handler(self, odoo):
        uid, models = odoo
        root = self._make_root(self._session_xml())
        models.execute_kw.side_effect = [
            # found by x_session_id with all fields in sync → no write
            [{"id": 7, "name": "Workshop A", "list_price": 20.0, "x_session_id": "sess-001"}],
            Exception("Odoo unavailable"),  # notify fails
        ]
        receiver.process_user_sessions_response(root, uid, models)  # must not raise
        assert models.execute_kw.call_count == 2

    def test_multiple_sessions_each_ensured_then_single_notify(self, odoo):
        """Two sessions → two _ensure_session_product calls → one kassa_notify_product_update."""
        uid, models = odoo
        two_sessions = (
            self._session_xml("Session A", "10.00")
            + self._session_xml("Session B", "15.00")
        )
        root = self._make_root(two_sessions, count=2)
        models.execute_kw.side_effect = [
            [],            # product A not found
            [{"id": 5}],   # category
            71,            # create A
            [],            # product B not found
            [{"id": 5}],   # category
            72,            # create B
            1,             # notify (called once, not twice)
        ]
        receiver.process_user_sessions_response(root, uid, models)

        notify_calls = [
            c for c in models.execute_kw.call_args_list
            if c[0][3] == "pos.session" and c[0][4] == "kassa_notify_product_update"
        ]
        assert len(notify_calls) == 1

    def test_session_price_passed_to_ensure_product(self, odoo):
        uid, models = odoo
        root = self._make_root(self._session_xml("Priced Session", "42.50"))
        models.execute_kw.side_effect = [[], [], [{"id": 5}], 90, 1]
        receiver.process_user_sessions_response(root, uid, models)

        create_call = models.execute_kw.call_args_list[3]
        vals = create_call[0][5][0]
        assert vals["list_price"] == 42.5

    def test_correlation_id_logged_from_header(self, odoo):
        """Handler reads correlation_id from header (not body). Just verify it runs cleanly."""
        uid, models = odoo
        custom_corr = "660e8400-e29b-41d4-a716-446655440099"
        root = self._make_root(self._session_xml(), correlation_id=custom_corr)
        # found by x_session_id with all fields in sync → no write
        models.execute_kw.side_effect = [
            [{"id": 3, "name": "Workshop A", "list_price": 20.0, "x_session_id": "sess-001"}],
            1,
        ]
        receiver.process_user_sessions_response(root, uid, models)
        assert models.execute_kw.call_count == 2


# ── process_profile_update ─────────────────────────────────────────────────────

class TestProcessProfileUpdate:
    BODY = (
        "<identity_uuid>550e8400-e29b-41d4-a716-446655440003</identity_uuid>"
        "<email>new@example.com</email>"
        "<contact><first_name>Bob</first_name><last_name>Builder</last_name></contact>"
        "<date_of_birth>1986-01-01</date_of_birth>"
        "<type>private</type>"
    )

    def _root(self):
        return ET.fromstring("<message><header/><body>" + self.BODY + "</body></message>")

    def test_updates_existing_partner(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [{"id": 7, "name": "Bob Old"}],
            True,
        ]
        receiver.process_profile_update(self._root(), uid, models)

        write_call = models.execute_kw.call_args_list[1]
        assert write_call[0][4] == "write"
        vals = write_call[0][5][1]
        assert vals["email"] == "new@example.com"
        assert vals["x_date_of_birth"] == "1986-01-01"

    def test_creates_partner_when_not_found(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [[], 8]
        receiver.process_profile_update(self._root(), uid, models)

        create_call = models.execute_kw.call_args_list[1]
        assert create_call[0][4] == "create"
        vals = create_call[0][5][0]
        assert vals["x_user_id"] == "550e8400-e29b-41d4-a716-446655440003"

    def test_updates_payment_info(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [[{"id": 7}], True]
        xml = (
            "<message><header/><body>"
            "<identity_uuid>550e8400-e29b-41d4-a716-446655440003</identity_uuid>"
            "<email>x@x.com</email>"
            "<contact><first_name>X</first_name><last_name>Y</last_name></contact>"
            "<payment_due><amount>50.0</amount><status>paid</status></payment_due>"
            "</body></message>"
        )
        receiver.process_profile_update(ET.fromstring(xml), uid, models)
        write_call = models.execute_kw.call_args_list[1]
        vals = write_call[0][5][1]
        assert vals["x_payment_status"] == "paid"
        assert vals["x_outstanding_amount"] == 50.0


# ── process_badge_scan ─────────────────────────────────────────────────────────

class TestProcessBadgeScan:
    def _root(self, badge_id: str):
        return ET.fromstring(
            "<message>"
            "<header><message_id>550e8400-e29b-41d4-a716-446655440004</message_id></header>"
            "<body>"
            f"<badge_id>{badge_id}</badge_id>"
            "<location>session</location>"
            "<scanned_at>2026-04-20T10:00:00Z</scanned_at>"
            "</body>"
            "</message>"
        )

    def test_known_badge_prints_info(self, odoo, caplog):
        import logging
        caplog.set_level(logging.INFO)
        uid, models = odoo
        models.execute_kw.return_value = [
            {"id": 3, "name": "Alice", "x_user_id": "550e8400-e29b-41d4-a716-446655440001",
             "x_wallet_balance": 12.50, "x_date_of_birth": "1996-01-01", "is_company": False}
        ]
        receiver.process_badge_scan(self._root("BADGE-001"), uid, models)

        assert "Processing badge(BADGE-001) scan from session at 2026-04-20T10:00:00Z" in caplog.text
        assert "Recognised: Odoo ID=3" in caplog.text
        assert "Location=session" in caplog.text

    @patch("receiver.send_error_to_queue")
    def test_unknown_badge_sends_error(self, mock_send_error, odoo):
        uid, models = odoo
        models.execute_kw.return_value = []
        receiver.process_badge_scan(self._root("BADGE-UNKNOWN"), uid, models)
        mock_send_error.assert_called_once_with(
            error_code="badge_not_found",
            related_message_id="550e8400-e29b-41d4-a716-446655440004",
            error_description="Badge BADGE-UNKNOWN not found in local Odoo cache.",
        )

    def test_missing_identifier_raises(self, odoo):
        uid, models = odoo
        root = ET.fromstring(
            "<message><header/><body><location>bar</location></body></message>"
        )
        with pytest.raises(ValueError, match="neither badge_id nor identity_uuid"):
            receiver.process_badge_scan(root, uid, models)


# ── process_cancel_registration ───────────────────────────────────────────────

class TestProcessCancelRegistration:
    def _root(self, identity_uuid: str = "550e8400-e29b-41d4-a716-446655440005"):
        return ET.fromstring(
            "<message><header/><body>"
            f"<identity_uuid>{identity_uuid}</identity_uuid>"
            "<session_id>sess-001</session_id>"
            "</body></message>"
        )

    def test_deactivates_existing_partner(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [{"id": 9, "name": "Carol"}],
            True,
        ]
        receiver.process_cancel_registration(self._root(), uid, models)

        write_call = models.execute_kw.call_args_list[1]
        assert write_call[0][4] == "write"
        assert write_call[0][5][1] == {"active": False}

    def test_no_action_when_not_found(self, odoo, caplog):
        uid, models = odoo
        models.execute_kw.return_value = []
        receiver.process_cancel_registration(self._root(), uid, models)
        # write should NOT have been called
        for c in models.execute_kw.call_args_list:
            assert c[0][4] != "write"
        assert "no action" in caplog.text

    def test_raises_when_identity_uuid_missing(self, odoo):
        uid, models = odoo
        root = ET.fromstring(
            "<message><header/><body><session_id>s</session_id></body></message>"
        )
        with pytest.raises(ValueError, match="identity_uuid missing"):
            receiver.process_cancel_registration(root, uid, models)


# ── process_message (full pipeline) ───────────────────────────────────────────

class TestProcessMessage:
    """End-to-end tests for the process_message RabbitMQ callback."""

    @patch("receiver.get_odoo_connection")
    @patch("receiver.validate_xml")
    def test_acks_on_success(self, mock_validate, mock_odoo, ch, method):
        uid = 1
        models = MagicMock()
        models.execute_kw.side_effect = [[], 50]  # create new partner
        mock_odoo.return_value = (uid, models)

        body = _xml_bytes(
            "new_registration",
            "<customer>"
            "<identity_uuid>550e8400-e29b-41d4-a716-446655440001</identity_uuid>"
            "<email>x@x.com</email><contact><first_name>X</first_name>"
            "<last_name>Y</last_name></contact><type>private</type>"
            "<date_of_birth>2006-01-01</date_of_birth><session_id>s1</session_id>"
            "<payment_due><amount currency=\"eur\">10</amount><status>unpaid</status></payment_due>"
            "</customer>",
        )
        receiver.process_message(ch, method, None, body)
        ch.basic_ack.assert_called_once_with(delivery_tag=42)
        ch.basic_nack.assert_not_called()

    @patch("receiver.get_odoo_connection")
    @patch("receiver.validate_xml")
    def test_successful_delivery_marks_message_id(self, mock_validate, mock_odoo, ch, method):
        uid = 1
        models = MagicMock()
        models.execute_kw.side_effect = [[], 50]
        mock_odoo.return_value = (uid, models)

        body = _xml_bytes(
            "new_registration",
            "<customer>"
            "<identity_uuid>550e8400-e29b-41d4-a716-446655440001</identity_uuid>"
            "<email>x@x.com</email><contact><first_name>X</first_name>"
            "<last_name>Y</last_name></contact><type>private</type>"
            "<date_of_birth>2006-01-01</date_of_birth><session_id>s1</session_id>"
            "<payment_due><amount currency=\"eur\">10</amount><status>unpaid</status></payment_due>"
            "</customer>",
            message_id="550e8400-e29b-41d4-a716-446655440006",
        )

        receiver.process_message(ch, method, None, body)

        assert "550e8400-e29b-41d4-a716-446655440006" in receiver.seen_message_ids

    @patch("receiver.send_error_to_queue")
    def test_nacks_on_invalid_xml(self, mock_send_error, ch, method):
        receiver.process_message(ch, method, None, b"not valid xml <<<")
        ch.basic_nack.assert_called_once_with(delivery_tag=42, requeue=False)
        mock_send_error.assert_called_once()
        assert mock_send_error.call_args[0][0] == "invalid_xml_format"

    @patch("receiver.send_error_to_queue")
    def test_nacks_on_unknown_message_type(self, mock_send_error, ch, method):
        body = _xml_bytes("completely_unknown", "<data/>")
        receiver.process_message(ch, method, None, body)
        ch.basic_nack.assert_called_once_with(delivery_tag=42, requeue=False)
        mock_send_error.assert_called()

    def test_acks_duplicate_without_processing(self, ch, method):
        receiver.seen_message_ids["550e8400-e29b-41d4-a716-446655440001"] = "2026-01-01T00:00:00Z"

        body = _xml_bytes("new_registration", "<customer/>", message_id="550e8400-e29b-41d4-a716-446655440001")
        receiver.process_message(ch, method, None, body)

        ch.basic_ack.assert_called_once_with(delivery_tag=42)
        ch.basic_nack.assert_not_called()

    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    @patch("receiver.validate_xml")
    def test_nacks_on_odoo_connection_error(self, mock_validate, mock_odoo, mock_send_error, ch, method):
        mock_odoo.side_effect = ConnectionError("Odoo down")
        body = _xml_bytes(
            "badge_scanned",
            "<badge_id>B1</badge_id><location>bar</location>"
            "<scanned_at>2026-03-28T12:00:00Z</scanned_at>",
        )
        receiver.process_message(ch, method, None, body)

        # In the new robust receiver, we basic_publish to retry queue and basic_ack the original
        ch.basic_publish.assert_called_once()
        routing_key = ch.basic_publish.call_args[1]["routing_key"]
        assert "retry" in routing_key
        ch.basic_ack.assert_called_once_with(delivery_tag=42)
        ch.basic_nack.assert_not_called()

    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    @patch("receiver.validate_xml")
    def test_odoo_failure_does_not_cache_message_id(self, mock_validate, mock_odoo, mock_send_error, ch, method):
        mock_odoo.side_effect = ConnectionError("Temporary Odoo outage")
        body = _xml_bytes(
            "badge_scanned",
            "<badge_id>B1</badge_id><location>bar</location>"
            "<scanned_at>2026-03-28T12:00:00Z</scanned_at>",
            message_id="550e8400-e29b-41d4-a716-446655440007",
        )

        receiver.process_message(ch, method, None, body)

        # Should NOT be in seen_message_ids yet (only after successful Odoo write)
        assert "550e8400-e29b-41d4-a716-446655440007" not in receiver.seen_message_ids
        ch.basic_ack.assert_called_once()

    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    @patch("receiver.validate_xml")
    def test_nacks_on_missing_type_field(self, mock_validate, mock_odoo, mock_send_error, ch, method):
        body = (
            b'<?xml version="1.0"?>'
            b"<message>"
            b"<header><message_id>550e8400-e29b-41d4-a716-446655440008</message_id></header>"
            b"<body/>"
            b"</message>"
        )
        receiver.process_message(ch, method, None, body)
        ch.basic_nack.assert_called_once_with(delivery_tag=42, requeue=False)

    @patch("receiver.get_odoo_connection")
    @patch("receiver.validate_xml")
    def test_cancel_registration_acks_on_success(self, mock_validate, mock_odoo, ch, method):
        uid = 1
        models = MagicMock()
        models.execute_kw.side_effect = [[{"id": 3, "name": "Dave"}], True]
        mock_odoo.return_value = (uid, models)

        body = _xml_bytes(
            "cancel_registration",
            "<identity_uuid>550e8400-e29b-41d4-a716-446655440009</identity_uuid><session_id>s1</session_id>",
        )
        receiver.process_message(ch, method, None, body)
        ch.basic_ack.assert_called_once_with(delivery_tag=42)

    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    @patch("receiver.validate_xml")
    def test_badge_scan_unknown_still_acks(self, mock_validate, mock_odoo, mock_send_error, ch, method):
        """Unknown badge → sends error but must still ACK (not NACK)."""
        uid = 1
        models = MagicMock()
        models.execute_kw.return_value = []  # badge not found
        mock_odoo.return_value = (uid, models)

        body = _xml_bytes(
            "badge_scanned",
            "<badge_id>BADGE-X</badge_id><location>bar</location>"
            "<scanned_at>2026-03-28T12:00:00Z</scanned_at>",
        )
        receiver.process_message(ch, method, None, body)

        ch.basic_ack.assert_called_once_with(delivery_tag=42)
        ch.basic_nack.assert_not_called()
        expected_msg = "Badge BADGE-X not found in local Odoo cache."
        mock_send_error.assert_called_once_with(
            error_code="badge_not_found",
            related_message_id="test-msg-001",
            error_description=expected_msg,
        )


# ── _publish_partner_bus_event ─────────────────────────────────────────────────

class TestPublishPartnerBusEvent:
    # ── call structure ────────────────────────────────────────────────────────

    def test_calls_pos_order_send_partner_bus_event(self, odoo):
        uid, models = odoo
        models.execute_kw.return_value = True
        receiver._publish_partner_bus_event(uid, models, 42, 25.0, "unpaid", "Alice")

        call = models.execute_kw.call_args_list[0]
        assert call[0][3] == "pos.order"
        assert call[0][4] == "send_partner_bus_event"
        args = call[0][5]
        assert args[0] == 42          # partner_id
        assert args[1] == 25.0        # outstanding_amount
        assert args[2] == "unpaid"    # payment_status
        assert args[3] == "Alice"     # name

    def test_exactly_one_call(self, odoo):
        uid, models = odoo
        models.execute_kw.return_value = True
        receiver._publish_partner_bus_event(uid, models, 7, 0.0, "paid", "Bob")

        assert models.execute_kw.call_count == 1

    def test_correct_args_forwarded(self, odoo):
        uid, models = odoo
        models.execute_kw.return_value = True
        receiver._publish_partner_bus_event(uid, models, 99, 5.0, "paid", "Y")

        args = models.execute_kw.call_args_list[0][0][5]
        assert args[0] == 99     # partner_id
        assert args[1] == 5.0    # outstanding_amount
        assert args[2] == "paid"  # payment_status
        assert args[3] == "Y"     # name

    def test_zero_amount_forwarded_correctly(self, odoo):
        uid, models = odoo
        models.execute_kw.return_value = True
        receiver._publish_partner_bus_event(uid, models, 5, 0.0, "paid", "Free")

        args = models.execute_kw.call_args_list[0][0][5]
        assert args[1] == 0.0

    def test_paid_status_forwarded_correctly(self, odoo):
        uid, models = odoo
        models.execute_kw.return_value = True
        receiver._publish_partner_bus_event(uid, models, 5, 50.0, "paid", "Settled")

        args = models.execute_kw.call_args_list[0][0][5]
        assert args[2] == "paid"

    # ── resilience ────────────────────────────────────────────────────────────

    def test_does_not_raise_on_error(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = Exception("bus down")
        receiver._publish_partner_bus_event(uid, models, 1, 0.0, "paid", "Bob")

    # ── integration: bus fired from process_new_registration ─────────────────

    def test_bus_fired_after_partner_created(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [],   # partner not found
            77,   # create → partner_id = 77
            True,  # bus
        ]
        root = ET.fromstring(
            "<message><header/><body><customer>"
            "<identity_uuid>550e8400-e29b-41d4-a716-446655440099</identity_uuid>"
            "<email>new@test.com</email>"
            "<contact><first_name>New</first_name><last_name>Guy</last_name></contact>"
            "<type>private</type>"
            "<payment_due><status>unpaid</status><amount>0.00</amount></payment_due>"
            "</customer></body></message>"
        )
        receiver.process_new_registration(root, uid, models)

        bus_call = models.execute_kw.call_args_list[2]
        assert bus_call[0][3] == "pos.order"
        assert bus_call[0][4] == "send_partner_bus_event"
        assert bus_call[0][5][0] == 77

    def test_bus_fired_after_partner_updated(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [{"id": 55, "name": "Alice", "x_user_id": "550e8400-e29b-41d4-a716-446655440099",
              "x_session_title": "[]"}],
            True,  # write
            True,  # bus
        ]
        root = ET.fromstring(
            "<message><header/><body><customer>"
            "<identity_uuid>550e8400-e29b-41d4-a716-446655440099</identity_uuid>"
            "<email>alice@test.com</email>"
            "<contact><first_name>Alice</first_name><last_name>Smith</last_name></contact>"
            "<type>private</type>"
            "<payment_due><status>unpaid</status><amount>15.00</amount></payment_due>"
            "</customer></body></message>"
        )
        receiver.process_new_registration(root, uid, models)

        bus_call = models.execute_kw.call_args_list[2]
        assert bus_call[0][3] == "pos.order"
        assert bus_call[0][4] == "send_partner_bus_event"
        assert bus_call[0][5][0] == 55

    def test_bus_not_blocked_by_write_failure(self, odoo):
        """If the Odoo write fails, process_new_registration should propagate the
        error before reaching the bus — this verifies the bus is not called when
        the preceding write raises, keeping state consistent."""
        uid, models = odoo
        models.execute_kw.side_effect = [
            [{"id": 5, "name": "Err", "x_user_id": "550e8400-e29b-41d4-a716-446655440005",
              "x_session_title": None}],
            Exception("Odoo write failed"),
        ]
        root = ET.fromstring(
            "<message><header/><body><customer>"
            "<identity_uuid>550e8400-e29b-41d4-a716-446655440005</identity_uuid>"
            "<email>err@test.com</email>"
            "<contact><first_name>Err</first_name><last_name>Test</last_name></contact>"
            "<type>private</type>"
            "<payment_due><status>unpaid</status><amount>5.00</amount></payment_due>"
            "</customer></body></message>"
        )
        with pytest.raises(Exception, match="Odoo write failed"):
            receiver.process_new_registration(root, uid, models)

        # Only 2 calls: search_read + write(failed) — no bus calls
        assert models.execute_kw.call_count == 2


# ── process_new_registration — payment fields ──────────────────────────────────

class TestProcessNewRegistrationPaymentFields:
    NEW_REG_BODY = (
        "<customer>"
        "<identity_uuid>550e8400-e29b-41d4-a716-446655440001</identity_uuid>"
        "<email>test@example.com</email>"
        "<date_of_birth>1996-01-01</date_of_birth>"
        "<contact><first_name>Alice</first_name><last_name>Wonderland</last_name></contact>"
        "<type>private</type>"
        "<session_id>sess-001</session_id>"
        "<payment_due><amount currency=\"eur\">25.00</amount><status>unpaid</status></payment_due>"
        "</customer>"
    )

    def _root(self):
        return ET.fromstring(
            "<message><header/><body>" + self.NEW_REG_BODY + "</body></message>"
        )

    def test_payment_fields_included_in_create(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [[], 99, True]  # search, create, bus sendone
        receiver.process_new_registration(self._root(), uid, models)

        create_call = models.execute_kw.call_args_list[1]
        vals = create_call[0][5][0]
        assert vals["x_outstanding_amount"] == 25.0
        assert vals["x_payment_status"] == "unpaid"

    def test_payment_fields_included_in_update(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [{"id": 5, "name": "Alice Wonderland", "x_user_id": "550e8400-e29b-41d4-a716-446655440001"}],
            True, True,  # write, bus sendone
        ]
        receiver.process_new_registration(self._root(), uid, models)

        write_call = models.execute_kw.call_args_list[1]
        vals = write_call[0][5][1]
        assert vals["x_outstanding_amount"] == 25.0
        assert vals["x_payment_status"] == "unpaid"

    def test_bus_event_published_after_create(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [[], 99, True]
        receiver.process_new_registration(self._root(), uid, models)

        bus_call = models.execute_kw.call_args_list[2]
        assert bus_call[0][3] == "pos.order"
        assert bus_call[0][4] == "send_partner_bus_event"

    def test_zero_amount_on_invalid_float(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [[], 99, True]
        root = ET.fromstring(
            "<message><header/><body>"
            "<customer><identity_uuid>550e8400-e29b-41d4-a716-446655440001</identity_uuid>"
            "<email>a@b.com</email><contact><first_name>X</first_name>"
            "<last_name>Y</last_name></contact><type>private</type>"
            "<date_of_birth>2000-01-01</date_of_birth><session_id>s1</session_id>"
            "<payment_due><amount currency=\"eur\">not-a-number</amount><status>unpaid</status></payment_due>"
            "</customer>"
            "</body></message>"
        )
        receiver.process_new_registration(root, uid, models)
        create_call = models.execute_kw.call_args_list[1]
        vals = create_call[0][5][0]
        assert vals["x_outstanding_amount"] == 0.0


# ── process_profile_update — payment_due handling ─────────────────────────────

class TestProcessProfileUpdatePaymentDue:
    BASE_BODY = (
        "<identity_uuid>550e8400-e29b-41d4-a716-446655440003</identity_uuid>"
        "<email>new@example.com</email>"
        "<contact><first_name>Bob</first_name><last_name>Builder</last_name></contact>"
        "<type>private</type>"
    )

    def _root(self, extra: str = ""):
        return ET.fromstring(
            "<message><header/><body>" + self.BASE_BODY + extra + "</body></message>"
        )

    def test_payment_fields_written_when_payment_due_present(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [{"id": 7, "name": "Bob Old"}],
            True, True,  # write, bus sendone
        ]
        root = self._root("<payment_due><amount>50.00</amount><status>unpaid</status></payment_due>")
        receiver.process_profile_update(root, uid, models)

        write_call = models.execute_kw.call_args_list[1]
        vals = write_call[0][5][1]
        assert vals["x_outstanding_amount"] == 50.0
        assert vals["x_payment_status"] == "unpaid"

    def test_payment_fields_absent_when_no_payment_due(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [{"id": 7, "name": "Bob Old"}],
            True,  # write only — no bus call expected
        ]
        receiver.process_profile_update(self._root(), uid, models)

        write_call = models.execute_kw.call_args_list[1]
        vals = write_call[0][5][1]
        assert "x_outstanding_amount" not in vals
        assert "x_payment_status" not in vals

    def test_bus_event_published_when_payment_due_present(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [{"id": 7, "name": "Bob Builder"}],
            True, True,
        ]
        root = self._root("<payment_due><amount>10.00</amount><status>paid</status></payment_due>")
        receiver.process_profile_update(root, uid, models)

        bus_call = models.execute_kw.call_args_list[2]
        assert bus_call[0][3] == "pos.order"
        assert bus_call[0][4] == "send_partner_bus_event"
        args = bus_call[0][5]
        assert args[2] == "paid"  # payment_status is the 3rd positional arg

    def test_no_bus_event_without_payment_due(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [{"id": 7, "name": "Bob Builder"}],
            True,
        ]
        receiver.process_profile_update(self._root(), uid, models)

        all_models_calls = [c[0][3] for c in models.execute_kw.call_args_list]
        assert "bus.bus" not in all_models_calls


# ── T1-3: LRU eviction at exactly MAX_CACHE_SIZE boundary ─────────────────────

class TestLruEvictionBoundary:
    """Story 15: Dedup cache evicts oldest entry when size exceeds MAX_CACHE_SIZE."""

    def test_eviction_at_real_boundary(self):
        import uuid as _uuid
        original = receiver.MAX_CACHE_SIZE
        receiver.MAX_CACHE_SIZE = 10
        try:
            receiver.seen_message_ids.clear()
            first_id = str(_uuid.uuid4())
            receiver._remember_message_id(first_id)
            for _ in range(9):
                receiver._remember_message_id(str(_uuid.uuid4()))
            # Cache is full at 10; inserting one more must evict first_id
            receiver._remember_message_id(str(_uuid.uuid4()))
            # first_id was evicted → is_duplicate returns False (not seen)
            assert receiver.is_duplicate(first_id, track_if_new=False) is False
        finally:
            receiver.MAX_CACHE_SIZE = original
            receiver.seen_message_ids.clear()

    def test_most_recent_id_still_tracked_after_eviction(self):
        import uuid as _uuid
        original = receiver.MAX_CACHE_SIZE
        receiver.MAX_CACHE_SIZE = 5
        try:
            receiver.seen_message_ids.clear()
            ids = [str(_uuid.uuid4()) for _ in range(5)]
            for mid in ids:
                receiver._remember_message_id(mid)
            new_id = str(_uuid.uuid4())
            receiver._remember_message_id(new_id)  # evicts ids[0]
            # new_id should still be tracked
            assert receiver.is_duplicate(new_id, track_if_new=False) is True
        finally:
            receiver.MAX_CACHE_SIZE = original
            receiver.seen_message_ids.clear()


# ── T1-6: Retry exhaustion → system_error + basic_nack ───────────────────────

class TestRetryExhaustion:
    """Story 20: Max retries exhausted sends system_error and nacks to DLQ."""

    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    @patch("receiver.validate_xml")
    def test_retry_exhaustion_sends_error_and_nacks(
        self, mock_validate, mock_odoo, mock_send_error, ch, method
    ):
        mock_odoo.side_effect = ConnectionError("Odoo permanently down")
        props = type("Props", (), {"headers": {"x-retry-count": receiver.MAX_RETRIES}})()

        body = _xml_bytes("badge_scanned",
                          "<badge_id>B1</badge_id><location>bar</location>"
                          "<scanned_at>2026-03-28T12:00:00Z</scanned_at>")
        receiver.process_message(ch, method, props, body)

        mock_send_error.assert_called_once()
        assert mock_send_error.call_args[0][0] == "odoo_api_error"
        ch.basic_nack.assert_called_once_with(delivery_tag=42, requeue=False)
        ch.basic_ack.assert_not_called()

    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    @patch("receiver.validate_xml")
    def test_retry_increments_count_and_republishes(
        self, mock_validate, mock_odoo, mock_send_error, ch, method
    ):
        mock_odoo.side_effect = ConnectionError("Temporary Odoo failure")
        props = type("Props", (), {"headers": {"x-retry-count": 1}})()

        body = _xml_bytes("badge_scanned",
                          "<badge_id>B1</badge_id><location>bar</location>"
                          "<scanned_at>2026-03-28T12:00:00Z</scanned_at>")
        receiver.process_message(ch, method, props, body)

        # Should republish to retry queue with incremented count
        ch.basic_publish.assert_called_once()
        publish_kwargs = ch.basic_publish.call_args[1]
        assert "retry" in publish_kwargs.get("routing_key", "").lower()
        # And ack the original
        ch.basic_ack.assert_called_once_with(delivery_tag=42)
        ch.basic_nack.assert_not_called()


# ── T2-1: Parametrized XSD invalid tests for all message types ────────────────

class TestInvalidXsdNacksForAllTypes:
    """Story 14: Any message with a schema violation must nack with invalid_xml_format."""

    @pytest.mark.parametrize("msg_type", [
        "new_registration",
        "profile_update",
        "cancel_registration",
        "badge_scanned",
        "wallet_lease_grant",
        "wallet_remote_topup",
        "event_ended",
        "session_created",
        "session_updated",
        "session_deleted",
        "user_sessions_response",
    ])
    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    def test_invalid_body_nacks_with_invalid_xml_format(
        self, mock_odoo, mock_send_error, msg_type, ch, method
    ):
        source = "iot_gateway" if msg_type == "badge_scanned" else "frontend" if msg_type in (
            "session_created", "session_updated", "session_deleted", "user_sessions_response"
        ) else "crm"

        # Build a message with a valid envelope but empty/broken body — XSD will reject it
        broken_body = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<message>"
            "<header>"
            "<message_id>550e8400-e29b-41d4-a716-446655440000</message_id>"
            f"<type>{msg_type}</type>"
            f"<source>{source}</source>"
            "<timestamp>2026-05-14T12:00:00Z</timestamp>"
            "<version>2.0</version>"
            "</header>"
            "<body><broken_field>this is invalid</broken_field></body>"
            "</message>"
        ).encode("utf-8")

        receiver.process_message(ch, method, None, broken_body)

        ch.basic_nack.assert_called_once_with(delivery_tag=42, requeue=False)
        mock_send_error.assert_called_once()
        assert mock_send_error.call_args[0][0] == "invalid_xml_format"


# ── Story 1/2: payment_due.status defaults to 'unpaid' ───────────────────────

class TestPaymentDueStatusDefault:
    """Stories 1 & 2: Absence of <status> in payment_due must default to 'unpaid', not 'pending'."""

    def test_new_registration_defaults_to_unpaid(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [[], 99, True]
        root = ET.fromstring(
            "<message><header/><body>"
            "<customer>"
            "<identity_uuid>550e8400-e29b-41d4-a716-446655440001</identity_uuid>"
            "<email>a@b.com</email>"
            "<contact><first_name>X</first_name><last_name>Y</last_name></contact>"
            "<type>private</type>"
            "<date_of_birth>2000-01-01</date_of_birth>"
            "<session_id>s1</session_id>"
            "<payment_due><amount currency=\"eur\">15.00</amount></payment_due>"
            "</customer>"
            "</body></message>"
        )
        receiver.process_new_registration(root, uid, models)

        create_call = models.execute_kw.call_args_list[1]
        vals = create_call[0][5][0]
        assert vals["x_payment_status"] == "unpaid", \
            f"Expected 'unpaid', got '{vals['x_payment_status']}'"

    def test_profile_update_defaults_to_unpaid(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [[{"id": 5, "name": "Bob"}], True, True]
        root = ET.fromstring(
            "<message><header/><body>"
            "<identity_uuid>550e8400-e29b-41d4-a716-446655440003</identity_uuid>"
            "<email>bob@example.com</email>"
            "<contact><first_name>Bob</first_name><last_name>Builder</last_name></contact>"
            "<type>private</type>"
            "<payment_due><amount>20.00</amount></payment_due>"
            "</body></message>"
        )
        receiver.process_profile_update(root, uid, models)

        write_call = models.execute_kw.call_args_list[1]
        vals = write_call[0][5][1]
        assert vals["x_payment_status"] == "unpaid", \
            f"Expected 'unpaid', got '{vals['x_payment_status']}'"


# ── process_user_registered ───────────────────────────────────────────────────

class TestProcessUserRegistered:
    UUID = "550e8400-e29b-41d4-a716-446655440010"

    def _root(self, session_id="sess-001", session_title="Workshop AI",
              price="25.00", payment_status="pending"):
        price_el = f'<price currency="eur">{price}</price>' if price else ""
        status_el = f"<payment_status>{payment_status}</payment_status>" if payment_status else ""
        return ET.fromstring(
            "<message><header/><body>"
            f"<customer>"
            f"<identity_uuid>{self.UUID}</identity_uuid>"
            f"<session_id>{session_id}</session_id>"
            f"</customer>"
            f"<session_title>{session_title}</session_title>"
            f"{price_el}"
            f"{status_el}"
            "</body></message>"
        )

    def test_adds_session_and_sets_outstanding(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [{"id": 7, "name": "Jan", "x_session_title": "[]", "x_outstanding_amount": 0.0}],
            True,
        ]
        receiver.process_user_registered(self._root(), uid, models)

        write_call = models.execute_kw.call_args_list[1]
        vals = write_call[0][5][1]
        import json
        sessions = json.loads(vals["x_session_title"])
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == "sess-001"
        assert sessions[0]["price"] == 25.0
        assert vals["x_outstanding_amount"] == 25.0
        assert vals["x_payment_status"] == "pending"

    def test_accumulates_multiple_sessions(self, odoo):
        uid, models = odoo
        import json
        existing = json.dumps([{"session_id": "sess-000", "title": "Existing", "price": 10.0}])
        models.execute_kw.side_effect = [
            [{"id": 7, "name": "Jan", "x_session_title": existing, "x_outstanding_amount": 10.0}],
            True,
        ]
        receiver.process_user_registered(self._root(session_id="sess-001", price="25.00"), uid, models)

        write_call = models.execute_kw.call_args_list[1]
        vals = write_call[0][5][1]
        sessions = json.loads(vals["x_session_title"])
        assert len(sessions) == 2
        assert vals["x_outstanding_amount"] == 35.0

    def test_does_not_duplicate_same_session(self, odoo):
        uid, models = odoo
        import json
        existing = json.dumps([{"session_id": "sess-001", "title": "Workshop AI", "price": 25.0}])
        models.execute_kw.side_effect = [
            [{"id": 7, "name": "Jan", "x_session_title": existing, "x_outstanding_amount": 25.0}],
            True,
        ]
        receiver.process_user_registered(self._root(session_id="sess-001"), uid, models)

        write_call = models.execute_kw.call_args_list[1]
        vals = write_call[0][5][1]
        sessions = json.loads(vals["x_session_title"])
        assert len(sessions) == 1

    def test_partner_not_found_logs_warning_no_write(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [[]]  # not found
        receiver.process_user_registered(self._root(), uid, models)
        assert models.execute_kw.call_count == 1  # only the search, no write

    def test_raises_without_identity_uuid(self, odoo):
        uid, models = odoo
        root = ET.fromstring(
            "<message><header/><body>"
            "<customer><session_id>s1</session_id></customer>"
            "</body></message>"
        )
        with pytest.raises(ValueError, match="identity_uuid missing"):
            receiver.process_user_registered(root, uid, models)

    def test_price_absent_does_not_count_toward_outstanding(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [{"id": 7, "name": "Jan", "x_session_title": "[]", "x_outstanding_amount": 0.0}],
            True,
        ]
        receiver.process_user_registered(self._root(price=None), uid, models)

        write_call = models.execute_kw.call_args_list[1]
        vals = write_call[0][5][1]
        assert vals["x_outstanding_amount"] == 0.0

    def test_existing_outstanding_preserved_when_price_absent(self, odoo):
        """CRM-authoritative outstanding is not zeroed when user_registered has no price."""
        uid, models = odoo
        models.execute_kw.side_effect = [
            [{"id": 7, "name": "Jan", "x_session_title": "[]", "x_outstanding_amount": 50.0}],
            True,
        ]
        receiver.process_user_registered(self._root(price=None), uid, models)

        write_call = models.execute_kw.call_args_list[1]
        vals = write_call[0][5][1]
        assert vals["x_outstanding_amount"] == 50.0

    def test_outstanding_accumulates_on_top_of_existing_amount(self, odoo):
        """Price is added to whatever Odoo currently stores, not recalculated from scratch."""
        uid, models = odoo
        import json
        # Existing entry has no price (plain-string legacy entry normalised to price=None)
        existing = json.dumps([{"session_id": "sess-000", "title": "Legacy", "price": None}])
        models.execute_kw.side_effect = [
            [{"id": 7, "name": "Jan", "x_session_title": existing, "x_outstanding_amount": 40.0}],
            True,
        ]
        receiver.process_user_registered(self._root(session_id="sess-001", price="25.00"), uid, models)

        write_call = models.execute_kw.call_args_list[1]
        vals = write_call[0][5][1]
        # 40 (authoritative from Odoo) + 25 (new session price) = 65, not 25
        assert vals["x_outstanding_amount"] == 65.0


# ── process_user_unregistered ─────────────────────────────────────────────────

class TestProcessUserUnregistered:
    UUID = "550e8400-e29b-41d4-a716-446655440011"

    def _root(self, session_id="sess-001", session_title="Workshop AI"):
        return ET.fromstring(
            "<message><header/><body>"
            f"<identity_uuid>{self.UUID}</identity_uuid>"
            f"<session_id>{session_id}</session_id>"
            f"<session_title>{session_title}</session_title>"
            "</body></message>"
        )

    def test_removes_session_and_decrements_outstanding(self, odoo):
        uid, models = odoo
        import json
        existing = json.dumps([
            {"session_id": "sess-001", "title": "Workshop AI", "price": 25.0},
            {"session_id": "sess-002", "title": "Keynote", "price": 10.0},
        ])
        models.execute_kw.side_effect = [
            [{"id": 8, "name": "Jan", "x_session_title": existing,
              "x_outstanding_amount": 35.0, "x_payment_status": "pending"}],
            True,
        ]
        receiver.process_user_unregistered(self._root(session_id="sess-001"), uid, models)

        write_call = models.execute_kw.call_args_list[1]
        vals = write_call[0][5][1]
        sessions = json.loads(vals["x_session_title"])
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == "sess-002"
        assert vals["x_outstanding_amount"] == 10.0
        assert vals["x_payment_status"] == "pending"

    def test_last_session_removed_zeros_outstanding(self, odoo):
        uid, models = odoo
        import json
        existing = json.dumps([{"session_id": "sess-001", "title": "Workshop AI", "price": 25.0}])
        models.execute_kw.side_effect = [
            [{"id": 8, "name": "Jan", "x_session_title": existing,
              "x_outstanding_amount": 25.0, "x_payment_status": "pending"}],
            True,
        ]
        receiver.process_user_unregistered(self._root(), uid, models)

        write_call = models.execute_kw.call_args_list[1]
        vals = write_call[0][5][1]
        import json as _json
        sessions = _json.loads(vals["x_session_title"])
        assert sessions == []
        assert vals["x_outstanding_amount"] == 0.0
        assert vals["x_payment_status"] == "paid"

    def test_partner_not_found_no_write(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [[]]
        receiver.process_user_unregistered(self._root(), uid, models)
        assert models.execute_kw.call_count == 1

    def test_raises_without_identity_uuid(self, odoo):
        uid, models = odoo
        root = ET.fromstring(
            "<message><header/><body>"
            "<session_id>s1</session_id>"
            "</body></message>"
        )
        with pytest.raises(ValueError, match="identity_uuid missing"):
            receiver.process_user_unregistered(root, uid, models)

    def test_unregistering_nonexistent_session_is_noop(self, odoo):
        uid, models = odoo
        import json
        existing = json.dumps([{"session_id": "sess-999", "title": "Other", "price": 5.0}])
        models.execute_kw.side_effect = [
            [{"id": 8, "name": "Jan", "x_session_title": existing,
              "x_outstanding_amount": 5.0, "x_payment_status": "pending"}],
            True,
        ]
        receiver.process_user_unregistered(self._root(session_id="sess-001"), uid, models)

        write_call = models.execute_kw.call_args_list[1]
        vals = write_call[0][5][1]
        import json as _json
        sessions = _json.loads(vals["x_session_title"])
        assert len(sessions) == 1  # sess-999 untouched
        assert vals["x_outstanding_amount"] == 5.0

    def test_paid_partner_partial_unregister_keeps_paid_status(self, odoo):
        """Unregistering one session must not revert a fully-paid partner back to pending."""
        uid, models = odoo
        import json
        existing = json.dumps([
            {"session_id": "sess-001", "title": "Workshop AI", "price": 25.0},
            {"session_id": "sess-002", "title": "Keynote", "price": 10.0},
        ])
        # Partner paid in full: order_poller set outstanding=0 and status="paid"
        models.execute_kw.side_effect = [
            [{"id": 8, "name": "Jan", "x_session_title": existing,
              "x_outstanding_amount": 0.0, "x_payment_status": "paid"}],
            True,
        ]
        receiver.process_user_unregistered(self._root(session_id="sess-001"), uid, models)

        write_call = models.execute_kw.call_args_list[1]
        vals = write_call[0][5][1]
        # outstanding stays 0 (max(0, 0 - 25) = 0); status must stay "paid"
        assert vals["x_outstanding_amount"] == 0.0
        assert vals["x_payment_status"] == "paid"

    def test_unregister_clamps_outstanding_at_zero_when_partially_paid(self, odoo):
        """Outstanding never goes negative when a session is removed after partial payment."""
        uid, models = odoo
        import json
        existing = json.dumps([{"session_id": "sess-001", "title": "Workshop AI", "price": 25.0}])
        # Partner partially paid: outstanding was reduced to 10 (paid 15 out of 25)
        models.execute_kw.side_effect = [
            [{"id": 8, "name": "Jan", "x_session_title": existing,
              "x_outstanding_amount": 10.0, "x_payment_status": "pending"}],
            True,
        ]
        receiver.process_user_unregistered(self._root(), uid, models)

        write_call = models.execute_kw.call_args_list[1]
        vals = write_call[0][5][1]
        assert vals["x_outstanding_amount"] == 0.0  # max(0, 10 - 25) = 0
        assert vals["x_payment_status"] == "paid"
