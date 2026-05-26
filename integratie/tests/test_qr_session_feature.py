# test_qr_session_feature.py — Comprehensive tests for QR-scan + session-products feature
#
# Covers:
#   - new_registration JSON array append / dedup / legacy-string handling
#   - _ensure_session_product edge cases (no category, already exists, empty title)
#   - wallet_lease_grant + payment_due: unit and full pipeline (process_message)
#   - Multi-session scenarios: user registered for 2+ sessions
#   - XSD compliance for wallet_lease_grant with / without payment_due (inbound)
#   - bus event published after new_registration and wallet_lease_grant
#
# All Odoo XML-RPC calls and RabbitMQ interactions are mocked.
# process_message() tests exercise real XSD validation.

import json
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from lxml import etree

import receiver


# ── Shared fixtures ────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clear_idempotency_cache():
    receiver.seen_message_ids.clear()
    yield
    receiver.seen_message_ids.clear()


@pytest.fixture
def odoo():
    uid = 1
    models = MagicMock()
    return uid, models


@pytest.fixture
def ch():
    m = MagicMock()
    m.delivery_tag = 77
    return m


@pytest.fixture
def method():
    m = MagicMock()
    m.delivery_tag = 77
    return m


# ── XML builders ────────────────────────────────────────────────────────────────

_UUID = "550e8400-e29b-41d4-a716-446655440000"
_UUID2 = "660e8400-e29b-41d4-a716-446655440001"


def _make_id() -> str:
    return str(uuid.uuid4())


def _new_registration_xml(
    identity_uuid: str = _UUID,
    email: str = "alice@example.com",
    first_name: str = "Alice",
    last_name: str = "Wonder",
    session_title: str | None = None,
    payment_status: str = "unpaid",
    payment_amount: float = 25.0,
    message_id: str | None = None,
) -> bytes:
    """Build a fully XSD-valid new_registration message."""
    mid = message_id or _make_id()
    cid = _make_id()
    session_el = f"<session_title>{session_title}</session_title>" if session_title else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<message><header>"
        f"<message_id>{mid}</message_id>"
        "<timestamp>2026-05-11T10:00:00Z</timestamp>"
        "<source>crm</source>"
        "<type>new_registration</type>"
        "<version>2.0</version>"
        f"<correlation_id>{cid}</correlation_id>"
        "</header><body><customer>"
        f"<identity_uuid>{identity_uuid}</identity_uuid>"
        f"<email>{email}</email>"
        "<date_of_birth>1996-01-01</date_of_birth>"
        "<contact>"
        f"<first_name>{first_name}</first_name>"
        f"<last_name>{last_name}</last_name>"
        "</contact>"
        "<type>private</type>"
        f"{session_el}"
        "<payment_due>"
        f'<amount currency="eur">{payment_amount:.2f}</amount>'
        f"<status>{payment_status}</status>"
        "</payment_due>"
        "</customer></body></message>"
    ).encode("utf-8")


def _wallet_lease_grant_xml(
    identity_uuid: str = _UUID,
    balance: float = 50.0,
    lease_id: str = "LEASE-001",
    payment_due: float | None = None,
    message_id: str | None = None,
) -> bytes:
    """Build a fully XSD-valid wallet_lease_grant message (payment_due optional)."""
    mid = message_id or _make_id()
    cid = _make_id()
    due_el = (
        f'<payment_due><amount currency="eur">{payment_due:.2f}</amount></payment_due>'
        if payment_due is not None else ""
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<message><header>"
        f"<message_id>{mid}</message_id>"
        "<timestamp>2026-05-11T10:00:00Z</timestamp>"
        "<source>crm</source>"
        "<type>wallet_lease_grant</type>"
        "<version>2.0</version>"
        f"<correlation_id>{cid}</correlation_id>"
        "</header><body>"
        f"<identity_uuid>{identity_uuid}</identity_uuid>"
        f'<current_balance currency="eur">{balance:.2f}</current_balance>'
        f"<lease_id>{lease_id}</lease_id>"
        f"{due_el}"
        "</body></message>"
    ).encode("utf-8")


def _partner(
    odoo_id: int = 10,
    identity_uuid: str = _UUID,
    session_title_json: str = "",
    payment_status: str = "unpaid",
    outstanding: float = 0.0,
    lease_active: bool = False,
) -> dict:
    return {
        "id": odoo_id,
        "name": "Alice Wonder",
        "x_user_id": identity_uuid,
        "x_session_title": session_title_json,
        "x_payment_status": payment_status,
        "x_outstanding_amount": outstanding,
        "x_wallet_balance": 25.0,
        "x_lease_active": lease_active,
        "x_lease_id": "LEASE-X" if lease_active else "",
        "x_lease_transaction_count": 0,
    }


# ── TestNewRegistrationSessionTitleAppend ──────────────────────────────────────

class TestNewRegistrationSessionTitleAppend:
    """Unit tests for the JSON array append logic in process_new_registration."""

    def _reg_root(
        self,
        session_title: str | None = None,
        identity_uuid: str = _UUID,
    ) -> ET.Element:
        session_el = f"<session_title>{session_title}</session_title>" if session_title else ""
        return ET.fromstring(
            "<message><header/><body><customer>"
            f"<identity_uuid>{identity_uuid}</identity_uuid>"
            "<email>a@b.com</email>"
            "<date_of_birth>1990-01-01</date_of_birth>"
            "<contact><first_name>Alice</first_name><last_name>Wonder</last_name></contact>"
            "<type>private</type>"
            f"{session_el}"
            '<payment_due><amount currency="eur">10.00</amount><status>unpaid</status></payment_due>'
            "</customer></body></message>"
        )

    def test_first_session_creates_json_array(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [{"id": 5, "name": "Alice", "x_user_id": _UUID, "x_session_title": ""}],
            True,   # write
            [],     # search_read product.template → not found
            [],     # search_read pos.category
            55,     # create product
            True,   # bus event
        ]
        receiver.process_new_registration(self._reg_root("Workshop A"), uid, models)

        write_call = models.execute_kw.call_args_list[1]
        vals = write_call[0][5][1]
        titles = json.loads(vals["x_session_title"])
        assert titles == ["Workshop A"]

    def test_second_session_appends_to_array(self, odoo):
        uid, models = odoo
        existing_json = json.dumps(["Workshop A"])
        models.execute_kw.side_effect = [
            [{"id": 5, "name": "Alice", "x_user_id": _UUID, "x_session_title": existing_json}],
            True,   # write
            [],     # product.template not found
            [],     # pos.category not found
            56,     # create product
            True,   # bus event
        ]
        receiver.process_new_registration(self._reg_root("Workshop B"), uid, models)

        write_call = models.execute_kw.call_args_list[1]
        vals = write_call[0][5][1]
        titles = json.loads(vals["x_session_title"])
        assert "Workshop A" in titles
        assert "Workshop B" in titles
        assert len(titles) == 2

    def test_duplicate_session_not_appended(self, odoo):
        uid, models = odoo
        existing_json = json.dumps(["Workshop A"])
        models.execute_kw.side_effect = [
            [{"id": 5, "name": "Alice", "x_user_id": _UUID, "x_session_title": existing_json}],
            True,   # write
            [{"id": 7}],  # product already exists
            True,   # bus event
        ]
        receiver.process_new_registration(self._reg_root("Workshop A"), uid, models)

        write_call = models.execute_kw.call_args_list[1]
        vals = write_call[0][5][1]
        titles = json.loads(vals["x_session_title"])
        assert titles.count("Workshop A") == 1

    def test_legacy_plain_string_migrated_to_array(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [{"id": 5, "name": "Alice", "x_user_id": _UUID, "x_session_title": "Old Session"}],
            True,
            [],     # product not found
            [],     # category not found
            57,     # create product
            True,   # bus event
        ]
        receiver.process_new_registration(self._reg_root("New Session"), uid, models)

        write_call = models.execute_kw.call_args_list[1]
        vals = write_call[0][5][1]
        titles = json.loads(vals["x_session_title"])
        assert "Old Session" in titles
        assert "New Session" in titles

    def test_no_session_title_does_not_set_x_session_title(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [],     # search_read → not found
            99,     # create
            True,   # bus event
        ]
        receiver.process_new_registration(self._reg_root(), uid, models)

        create_call = models.execute_kw.call_args_list[1]
        vals = create_call[0][5][0]
        assert "x_session_title" not in vals

    def test_three_sessions_accumulated(self, odoo):
        uid, models = odoo
        existing_json = json.dumps(["A", "B"])
        models.execute_kw.side_effect = [
            [{"id": 5, "name": "Alice", "x_user_id": _UUID, "x_session_title": existing_json}],
            True,
            [],     # product not found
            [],     # category not found
            58,     # create product
            True,   # bus event
        ]
        receiver.process_new_registration(self._reg_root("C"), uid, models)

        write_call = models.execute_kw.call_args_list[1]
        vals = write_call[0][5][1]
        titles = json.loads(vals["x_session_title"])
        assert set(titles) == {"A", "B", "C"}

    def test_corrupted_json_treated_as_plain_string(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [{"id": 5, "name": "Alice", "x_user_id": _UUID, "x_session_title": "{not-valid-json"}],
            True,
            [],     # product not found
            [],     # category not found
            59,     # create product
            True,   # bus event
        ]
        receiver.process_new_registration(self._reg_root("Workshop A"), uid, models)

        write_call = models.execute_kw.call_args_list[1]
        vals = write_call[0][5][1]
        titles = json.loads(vals["x_session_title"])
        assert "Workshop A" in titles
        # corrupted string treated as one existing entry
        assert "{not-valid-json" in titles


# ── TestEnsureSessionProduct ───────────────────────────────────────────────────

class TestEnsureSessionProductEdgeCases:
    """Edge-case unit tests for _ensure_session_product."""

    def test_creates_product_without_sessions_category(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [],          # product not found
            [],          # pos.category "Sessions" not found → categ_id = False
            77,          # create product
        ]
        receiver._ensure_session_product(uid, models, "Keynote")

        create_call = models.execute_kw.call_args_list[2]
        vals = create_call[0][5][0]
        assert vals["name"] == "Keynote"
        assert "pos_categ_ids" not in vals

    def test_creates_product_with_sessions_category(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [],              # product not found
            [{"id": 15}],   # category found
            78,              # create product
        ]
        receiver._ensure_session_product(uid, models, "Keynote")

        create_call = models.execute_kw.call_args_list[2]
        vals = create_call[0][5][0]
        assert vals["pos_categ_ids"] == [(6, 0, [15])]

    def test_skips_create_when_product_exists(self, odoo):
        uid, models = odoo
        # found, no price change → write still fires to clear taxes_id
        models.execute_kw.side_effect = [
            [{"id": 5, "list_price": 0.0}],  # found
            True,                             # write (taxes_id clear)
        ]
        receiver._ensure_session_product(uid, models, "Existing Workshop")
        creates = [c for c in models.execute_kw.call_args_list if c[0][4] == "create"]
        assert len(creates) == 0
        writes = [c for c in models.execute_kw.call_args_list if c[0][4] == "write"]
        assert len(writes) == 1

    def test_product_type_is_consu(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [[], [], 79]
        receiver._ensure_session_product(uid, models, "Test")
        create_call = models.execute_kw.call_args_list[2]
        vals = create_call[0][5][0]
        assert vals["type"] == "consu"

    def test_product_list_price_is_zero(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [[], [], 80]
        receiver._ensure_session_product(uid, models, "Test")
        create_call = models.execute_kw.call_args_list[2]
        vals = create_call[0][5][0]
        assert vals["list_price"] == 0.0

    def test_product_available_in_pos(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [[], [], 81]
        receiver._ensure_session_product(uid, models, "Test")
        create_call = models.execute_kw.call_args_list[2]
        vals = create_call[0][5][0]
        assert vals["available_in_pos"] is True

    def test_idempotent_second_call_does_nothing(self, odoo):
        uid, models = odoo
        # No session_id → x_session_id lookup is skipped.
        # First call (3 ops): name search → not found, category → none, create.
        # Second call (2 ops): name search → found, write to clear taxes_id.
        models.execute_kw.side_effect = [
            [],                               # first: name search → not found
            [],                               # first: no category
            44,                               # first: created
            [{"id": 44, "list_price": 0.0}],  # second: name search → found
            True,                             # second: write (taxes_id clear)
        ]
        receiver._ensure_session_product(uid, models, "Workshop X")
        receiver._ensure_session_product(uid, models, "Workshop X")
        creates = [c for c in models.execute_kw.call_args_list if c[0][4] == "create"]
        assert len(creates) == 1  # only on first call


# ── TestWalletLeaseGrantAmountDueUnit ─────────────────────────────────────────

class TestWalletLeaseGrantAmountDueUnit:
    """Unit tests for process_wallet_lease_grant with payment_due field."""

    def _grant_root(self, payment_due: float | None = None) -> ET.Element:
        due_el = (
            f'<payment_due><amount currency="eur">{payment_due}</amount></payment_due>'
            if payment_due is not None else ""
        )
        return ET.fromstring(
            "<message><header/><body>"
            f"<identity_uuid>{_UUID}</identity_uuid>"
            '<current_balance currency="eur">60.00</current_balance>'
            "<lease_id>LEASE-42</lease_id>"
            f"{due_el}"
            "</body></message>"
        )

    def _partner_record(self, outstanding: float = 0.0, status: str = "unpaid") -> list:
        return [{"id": 10, "name": "Alice", "x_payment_status": status, "x_outstanding_amount": outstanding}]

    def test_payment_due_written_to_odoo(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [self._partner_record(), True, True]
        receiver.process_wallet_lease_grant(self._grant_root(payment_due=30.0), uid, models)

        write_call = models.execute_kw.call_args_list[1]
        vals = write_call[0][5][1]
        assert vals["x_outstanding_amount"] == 30.0

    def test_payment_due_zero_written(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [self._partner_record(), True, True]
        receiver.process_wallet_lease_grant(self._grant_root(payment_due=0.0), uid, models)

        write_call = models.execute_kw.call_args_list[1]
        vals = write_call[0][5][1]
        assert vals["x_outstanding_amount"] == 0.0

    def test_no_payment_due_does_not_set_outstanding(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [self._partner_record(), True, True]
        receiver.process_wallet_lease_grant(self._grant_root(), uid, models)

        write_call = models.execute_kw.call_args_list[1]
        vals = write_call[0][5][1]
        assert "x_outstanding_amount" not in vals

    def test_wallet_balance_always_written(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [self._partner_record(), True, True]
        receiver.process_wallet_lease_grant(self._grant_root(payment_due=20.0), uid, models)

        write_call = models.execute_kw.call_args_list[1]
        vals = write_call[0][5][1]
        assert vals["x_wallet_balance"] == 60.0

    def test_lease_active_set_true(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [self._partner_record(), True, True]
        receiver.process_wallet_lease_grant(self._grant_root(payment_due=5.0), uid, models)

        write_call = models.execute_kw.call_args_list[1]
        vals = write_call[0][5][1]
        assert vals["x_lease_active"] is True

    def test_bus_event_called_with_payment_due(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [self._partner_record(), True, True]
        receiver.process_wallet_lease_grant(self._grant_root(payment_due=35.0), uid, models)

        bus_call = models.execute_kw.call_args_list[2]
        assert bus_call[0][3] == "pos.order"
        assert bus_call[0][4] == "send_partner_bus_event"
        # outstanding_amount passed to bus event = payment_due
        bus_args = bus_call[0][5]
        assert bus_args[1] == 35.0

    def test_bus_event_uses_stored_amount_when_no_payment_due(self, odoo):
        """When payment_due absent, bus event carries x_outstanding_amount from DB (not hardcoded 0)."""
        uid, models = odoo
        models.execute_kw.side_effect = [
            [{"id": 10, "name": "Alice", "x_payment_status": "paid", "x_outstanding_amount": 42.0}],
            True, True,
        ]
        receiver.process_wallet_lease_grant(self._grant_root(), uid, models)

        bus_call = models.execute_kw.call_args_list[2]
        bus_args = bus_call[0][5]
        assert bus_args[1] == 42.0

    def test_bus_event_zero_when_no_payment_due_and_no_outstanding(self, odoo):
        """Placeholder partner with no outstanding amount: bus event carries 0.0."""
        uid, models = odoo
        models.execute_kw.side_effect = [
            [{"id": 10, "name": "Alice", "x_payment_status": "unpaid", "x_outstanding_amount": 0.0}],
            True, True,
        ]
        receiver.process_wallet_lease_grant(self._grant_root(), uid, models)

        bus_call = models.execute_kw.call_args_list[2]
        bus_args = bus_call[0][5]
        assert bus_args[1] == 0.0

    def test_unknown_partner_no_write_no_bus(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [[]]  # no partner found
        receiver.process_wallet_lease_grant(self._grant_root(payment_due=20.0), uid, models)

        assert models.execute_kw.call_count == 1  # only the search, no write or bus


# ── TestWalletLeaseGrantPipelineAmountDue ─────────────────────────────────────

class TestWalletLeaseGrantPipelineAmountDue:
    """End-to-end process_message() integration tests — real XSD validation."""

    def _p(self, outstanding: float = 25.0, status: str = "unpaid") -> list:
        return [{"id": 10, "name": "Alice", "x_payment_status": status, "x_outstanding_amount": outstanding}]

    @patch("receiver.send_typed_message")
    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    def test_grant_with_payment_due_passes_xsd_and_updates_odoo(
        self, mock_conn, mock_error, mock_send, ch, method
    ):
        models = MagicMock()
        models.execute_kw.side_effect = [self._p(), True, True]
        mock_conn.return_value = (1, models)

        body = _wallet_lease_grant_xml(payment_due=25.0)
        receiver.process_message(ch, method, None, body)

        mock_error.assert_not_called()
        ch.basic_nack.assert_not_called()
        ch.basic_ack.assert_called_once()

        write_call = models.execute_kw.call_args_list[1]
        vals = write_call[0][5][1]
        assert vals["x_outstanding_amount"] == 25.0
        assert vals["x_wallet_balance"] == 50.0

    @patch("receiver.send_typed_message")
    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    def test_grant_without_payment_due_passes_xsd(
        self, mock_conn, mock_error, mock_send, ch, method
    ):
        models = MagicMock()
        # x_outstanding_amount already set by new_registration; grant has no payment_due
        models.execute_kw.side_effect = [self._p(outstanding=30.0), True, True]
        mock_conn.return_value = (1, models)

        body = _wallet_lease_grant_xml()  # no payment_due
        receiver.process_message(ch, method, None, body)

        mock_error.assert_not_called()
        ch.basic_ack.assert_called_once()

        write_call = models.execute_kw.call_args_list[1]
        vals = write_call[0][5][1]
        assert "x_outstanding_amount" not in vals  # not overwritten by grant

    @patch("receiver.send_typed_message")
    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    def test_grant_without_payment_due_bus_event_uses_stored_amount(
        self, mock_conn, mock_error, mock_send, ch, method
    ):
        """Bus event carries the real outstanding amount from new_registration, not 0."""
        models = MagicMock()
        models.execute_kw.side_effect = [self._p(outstanding=30.0), True, True]
        mock_conn.return_value = (1, models)

        receiver.process_message(ch, method, None, _wallet_lease_grant_xml())

        bus_call = models.execute_kw.call_args_list[2]
        assert bus_call[0][4] == "send_partner_bus_event"
        assert bus_call[0][5][1] == 30.0  # real amount, not 0.0

    @patch("receiver.send_typed_message")
    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    def test_grant_with_payment_due_publishes_bus_event(
        self, mock_conn, mock_error, mock_send, ch, method
    ):
        models = MagicMock()
        models.execute_kw.side_effect = [self._p(), True, True]
        mock_conn.return_value = (1, models)

        receiver.process_message(ch, method, None, _wallet_lease_grant_xml(payment_due=40.0))

        bus_call = models.execute_kw.call_args_list[2]
        assert bus_call[0][3] == "pos.order"
        assert bus_call[0][4] == "send_partner_bus_event"

    @patch("receiver.send_typed_message")
    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    def test_duplicate_grant_silently_skipped(
        self, mock_conn, mock_error, mock_send, ch, method
    ):
        models = MagicMock()
        models.execute_kw.side_effect = [self._p(), True, True]
        mock_conn.return_value = (1, models)

        mid = _make_id()
        body = _wallet_lease_grant_xml(payment_due=25.0, message_id=mid)

        receiver.process_message(ch, method, None, body)
        receiver.process_message(ch, method, None, body)

        # Write should be called only once (first delivery)
        write_calls = [
            c for c in models.execute_kw.call_args_list
            if len(c[0]) > 4 and c[0][4] == "write"
        ]
        assert len(write_calls) == 1

    @patch("receiver.send_typed_message")
    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    def test_invalid_grant_missing_correlation_id_rejected(
        self, mock_conn, mock_error, mock_send, ch, method
    ):
        mock_conn.return_value = (1, MagicMock())
        bad_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<message><header>"
            f"<message_id>{_make_id()}</message_id>"
            "<timestamp>2026-05-11T10:00:00Z</timestamp>"
            "<source>crm</source>"
            "<type>wallet_lease_grant</type>"
            "<version>2.0</version>"
            # correlation_id intentionally omitted
            "</header><body>"
            f"<identity_uuid>{_UUID}</identity_uuid>"
            '<current_balance currency="eur">50.00</current_balance>'
            "<lease_id>LEASE-001</lease_id>"
            "</body></message>"
        ).encode("utf-8")

        receiver.process_message(ch, method, None, bad_xml)

        ch.basic_nack.assert_called_once()
        mock_error.assert_called_once()
        mock_conn.return_value[1].execute_kw.assert_not_called()

    @patch("receiver.send_typed_message")
    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    def test_grant_xsd_validated_xml_is_complete(
        self, mock_conn, mock_error, mock_send, ch, method
    ):
        """Confirm the test XML builder itself produces a schema-valid message."""
        from pathlib import Path
        from lxml import etree as lxml_etree

        body_bytes = _wallet_lease_grant_xml(payment_due=15.0)
        schema_path = Path(receiver.__file__).parent / "schemas" / "schema_wallet_lease_grant.xsd"
        parser = lxml_etree.XMLParser(resolve_entities=False, dtd_validation=False, no_network=True)
        schema = lxml_etree.XMLSchema(lxml_etree.parse(str(schema_path), parser))
        doc = lxml_etree.fromstring(body_bytes, parser=parser)
        assert schema.validate(doc), f"XSD failed: {schema.error_log}"


# ── TestNewRegistrationSessionIntegration ─────────────────────────────────────

class TestNewRegistrationSessionIntegration:
    """End-to-end process_message() tests for new_registration with session_title."""

    @patch("receiver.send_typed_message")
    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    def test_new_registration_with_session_creates_product(
        self, mock_conn, mock_error, mock_send, ch, method
    ):
        models = MagicMock()
        models.execute_kw.side_effect = [
            [],              # search_read partner → not found
            99,              # create partner
            [],              # product.template not found
            [{"id": 10}],   # pos.category found
            55,              # create product
            True,            # bus event
        ]
        mock_conn.return_value = (1, models)

        body = _new_registration_xml(session_title="Workshop: IoT met Python")
        receiver.process_message(ch, method, None, body)

        mock_error.assert_not_called()
        ch.basic_ack.assert_called_once()

        product_create = next(
            c for c in models.execute_kw.call_args_list
            if len(c[0]) > 4 and c[0][3] == "product.template" and c[0][4] == "create"
        )
        assert product_create[0][5][0]["name"] == "Workshop: IoT met Python"
        assert product_create[0][5][0]["available_in_pos"] is True

    @patch("receiver.send_typed_message")
    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    def test_new_registration_without_session_skips_product(
        self, mock_conn, mock_error, mock_send, ch, method
    ):
        models = MagicMock()
        models.execute_kw.side_effect = [
            [],   # partner not found
            88,   # create
            True,  # bus event
        ]
        mock_conn.return_value = (1, models)

        body = _new_registration_xml()  # no session_title
        receiver.process_message(ch, method, None, body)

        ch.basic_ack.assert_called_once()
        product_calls = [
            c for c in models.execute_kw.call_args_list
            if len(c[0]) > 3 and c[0][3] == "product.template"
        ]
        assert product_calls == []

    @patch("receiver.send_typed_message")
    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    def test_new_registration_session_title_stored_as_json_array(
        self, mock_conn, mock_error, mock_send, ch, method
    ):
        models = MagicMock()
        models.execute_kw.side_effect = [
            [],      # partner not found
            89,      # create
            [],      # product not found
            [],      # no category
            60,      # create product
            True,    # bus event
        ]
        mock_conn.return_value = (1, models)

        receiver.process_message(ch, method, None, _new_registration_xml(session_title="Keynote"))

        create_call = models.execute_kw.call_args_list[1]
        vals = create_call[0][5][0]
        titles = json.loads(vals["x_session_title"])
        assert titles == ["Keynote"]

    @patch("receiver.send_typed_message")
    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    def test_new_registration_publishes_bus_event(
        self, mock_conn, mock_error, mock_send, ch, method
    ):
        models = MagicMock()
        models.execute_kw.side_effect = [
            [],   # partner not found
            90,   # create
            True,  # bus event
        ]
        mock_conn.return_value = (1, models)

        receiver.process_message(ch, method, None, _new_registration_xml())

        bus_call = models.execute_kw.call_args_list[2]
        assert bus_call[0][3] == "pos.order"
        assert bus_call[0][4] == "send_partner_bus_event"

    @patch("receiver.send_typed_message")
    @patch("receiver.send_error_to_queue")
    @patch("receiver.get_odoo_connection")
    def test_new_registration_invalid_xsd_rejected(
        self, mock_conn, mock_error, mock_send, ch, method
    ):
        mock_conn.return_value = (1, MagicMock())
        # Missing required <date_of_birth> and <contact> → XSD rejects
        bad_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<message><header>"
            f"<message_id>{_make_id()}</message_id>"
            "<timestamp>2026-05-11T10:00:00Z</timestamp>"
            "<source>crm</source>"
            "<type>new_registration</type>"
            "<version>2.0</version>"
            f"<correlation_id>{_make_id()}</correlation_id>"
            "</header><body><customer>"
            f"<identity_uuid>{_UUID}</identity_uuid>"
            "<email>x@x.com</email>"
            # date_of_birth intentionally missing
            "<type>private</type>"
            '<payment_due><amount currency="eur">0.00</amount><status>unpaid</status></payment_due>'
            "</customer></body></message>"
        ).encode("utf-8")

        receiver.process_message(ch, method, None, bad_xml)

        ch.basic_nack.assert_called_once()
        mock_error.assert_called_once()


# ── TestMultiSessionFlow ───────────────────────────────────────────────────────

class TestMultiSessionFlow:
    """Tests for multi-session scenarios (user registered for 2+ sessions)."""

    def _reg_root(self, session_title: str, existing_json: str = "", identity_uuid: str = _UUID) -> ET.Element:
        session_el = f"<session_title>{session_title}</session_title>"
        return ET.fromstring(
            "<message><header/><body><customer>"
            f"<identity_uuid>{identity_uuid}</identity_uuid>"
            "<email>a@b.com</email>"
            "<date_of_birth>1990-01-01</date_of_birth>"
            "<contact><first_name>Alice</first_name><last_name>Wonder</last_name></contact>"
            "<type>private</type>"
            f"{session_el}"
            '<payment_due><amount currency="eur">10.00</amount><status>unpaid</status></payment_due>'
            "</customer></body></message>"
        )

    def test_two_sessions_stored_correctly(self, odoo):
        uid, models = odoo
        # First registration: no existing sessions
        models.execute_kw.side_effect = [
            [],      # search_read → partner not found
            100,     # create partner
            [],      # product.template not found
            [],      # pos.category not found
            61,      # create product "Session A"
            True,    # bus event
            # Second registration for same partner:
            [{"id": 100, "name": "Alice", "x_user_id": _UUID, "x_session_title": '["Session A"]'}],
            True,    # write
            [],      # product.template for "Session B" not found
            [],      # category not found
            62,      # create product "Session B"
            True,    # bus event
        ]
        receiver.process_new_registration(self._reg_root("Session A"), uid, models)
        receiver.process_new_registration(self._reg_root("Session B"), uid, models)

        second_write = models.execute_kw.call_args_list[7]
        vals = second_write[0][5][1]
        titles = json.loads(vals["x_session_title"])
        assert "Session A" in titles
        assert "Session B" in titles

    def test_each_session_gets_its_own_product(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [],      # partner not found
            100,     # create
            [],      # product "Sess A" not found
            [],      # no category
            70,      # create product "Sess A"
            True,    # bus event
            [{"id": 100, "name": "Alice", "x_user_id": _UUID, "x_session_title": '["Sess A"]'}],
            True,    # write
            [],      # product "Sess B" not found
            [],      # no category
            71,      # create product "Sess B"
            True,    # bus event
        ]
        receiver.process_new_registration(self._reg_root("Sess A"), uid, models)
        receiver.process_new_registration(self._reg_root("Sess B"), uid, models)

        product_creates = [
            c for c in models.execute_kw.call_args_list
            if len(c[0]) > 4 and c[0][3] == "product.template" and c[0][4] == "create"
        ]
        created_names = {c[0][5][0]["name"] for c in product_creates}
        assert created_names == {"Sess A", "Sess B"}

    def test_same_session_registered_twice_deduplicated(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [],      # partner not found
            100,     # create
            [],      # product "Workshop" not found
            [],      # no category
            72,      # create product
            True,    # bus event
            # Second registration for same session:
            [{"id": 100, "name": "Alice", "x_user_id": _UUID, "x_session_title": '["Workshop"]'}],
            True,    # write
            [{"id": 72}],  # product already exists → no create
            True,    # bus event
        ]
        receiver.process_new_registration(self._reg_root("Workshop"), uid, models)
        receiver.process_new_registration(self._reg_root("Workshop"), uid, models)

        second_write = models.execute_kw.call_args_list[7]
        vals = second_write[0][5][1]
        titles = json.loads(vals["x_session_title"])
        assert titles.count("Workshop") == 1

    def test_grant_with_payment_due_covers_all_sessions(self, odoo):
        """payment_due in wallet_lease_grant is the total for all sessions combined."""
        uid, models = odoo
        models.execute_kw.side_effect = [
            [{"id": 10, "name": "Alice", "x_payment_status": "unpaid"}],
            True,   # write
            True,   # bus event
        ]
        root = ET.fromstring(
            "<message><header/><body>"
            f"<identity_uuid>{_UUID}</identity_uuid>"
            '<current_balance currency="eur">80.00</current_balance>'
            "<lease_id>LEASE-99</lease_id>"
            '<payment_due><amount currency="eur">60.00</amount></payment_due>'
            "</body></message>"
        )
        receiver.process_wallet_lease_grant(root, uid, models)

        write_call = models.execute_kw.call_args_list[1]
        vals = write_call[0][5][1]
        # 60.00 covers e.g. two sessions at 30.00 each
        assert vals["x_outstanding_amount"] == 60.0


# ── TestNewRegistrationXsdCompliance ──────────────────────────────────────────

class TestNewRegistrationXsdCompliance:
    """Verify the new_registration XML builder produces valid XSD output."""

    def _validate(self, xml_bytes: bytes) -> tuple[bool, object]:
        schema_path = Path(receiver.__file__).parent / "schemas" / "schema_new_registration.xsd"
        parser = etree.XMLParser(resolve_entities=False, dtd_validation=False, no_network=True)
        schema = etree.XMLSchema(etree.parse(str(schema_path), parser))
        doc = etree.fromstring(xml_bytes, parser=parser)
        return schema.validate(doc), schema.error_log

    def test_new_registration_with_session_title_valid(self):
        xml = _new_registration_xml(session_title="Workshop A")
        valid, errors = self._validate(xml)
        assert valid, f"XSD failed: {errors}"

    def test_new_registration_without_session_title_valid(self):
        xml = _new_registration_xml()
        valid, errors = self._validate(xml)
        assert valid, f"XSD failed: {errors}"

    def test_new_registration_paid_status_valid(self):
        xml = _new_registration_xml(payment_status="paid", payment_amount=50.0)
        valid, errors = self._validate(xml)
        assert valid, f"XSD failed: {errors}"


# ── TestGrantAmountDueXsdCompliance ───────────────────────────────────────────

class TestGrantPaymentDueXsdCompliance:
    """Verify wallet_lease_grant XSD accepts / rejects payment_due correctly."""

    def _validate(self, xml_bytes: bytes) -> tuple[bool, object]:
        schema_path = Path(receiver.__file__).parent / "schemas" / "schema_wallet_lease_grant.xsd"
        parser = etree.XMLParser(resolve_entities=False, dtd_validation=False, no_network=True)
        schema = etree.XMLSchema(etree.parse(str(schema_path), parser))
        doc = etree.fromstring(xml_bytes, parser=parser)
        return schema.validate(doc), schema.error_log

    def test_with_payment_due_valid(self):
        xml = _wallet_lease_grant_xml(payment_due=25.0)
        valid, errors = self._validate(xml)
        assert valid, f"XSD failed: {errors}"

    def test_without_payment_due_valid(self):
        xml = _wallet_lease_grant_xml()
        valid, errors = self._validate(xml)
        assert valid, f"XSD failed: {errors}"

    def test_payment_due_amount_requires_currency_attribute(self):
        """payment_due/amount without currency attribute must fail XSD."""
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<message><header>"
            f"<message_id>{_make_id()}</message_id>"
            "<timestamp>2026-05-11T10:00:00Z</timestamp>"
            "<source>crm</source>"
            "<type>wallet_lease_grant</type>"
            "<version>2.0</version>"
            f"<correlation_id>{_make_id()}</correlation_id>"
            "</header><body>"
            f"<identity_uuid>{_UUID}</identity_uuid>"
            '<current_balance currency="eur">50.00</current_balance>'
            "<lease_id>LEASE-001</lease_id>"
            "<payment_due><amount>25.00</amount></payment_due>"  # missing currency attr
            "</body></message>"
        ).encode("utf-8")
        valid, _ = self._validate(xml)
        assert not valid, "payment_due/amount without currency= must fail XSD"

    def test_payment_due_wrong_currency_rejected(self):
        """payment_due/amount with currency='usd' must fail (fixed='eur')."""
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<message><header>"
            f"<message_id>{_make_id()}</message_id>"
            "<timestamp>2026-05-11T10:00:00Z</timestamp>"
            "<source>crm</source>"
            "<type>wallet_lease_grant</type>"
            "<version>2.0</version>"
            f"<correlation_id>{_make_id()}</correlation_id>"
            "</header><body>"
            f"<identity_uuid>{_UUID}</identity_uuid>"
            '<current_balance currency="eur">50.00</current_balance>'
            "<lease_id>LEASE-001</lease_id>"
            '<payment_due><amount currency="usd">25.00</amount></payment_due>'
            "</body></message>"
        ).encode("utf-8")
        valid, _ = self._validate(xml)
        assert not valid, "payment_due/amount currency='usd' should fail XSD (fixed='eur')"


# ── TestBusEventAfterNewRegistration ──────────────────────────────────────────

class TestBusEventAfterNewRegistration:
    """Verify bus event is published after new_registration creates/updates a partner."""

    def _reg_root(self, session_title: str | None = None) -> ET.Element:
        session_el = f"<session_title>{session_title}</session_title>" if session_title else ""
        return ET.fromstring(
            "<message><header/><body><customer>"
            f"<identity_uuid>{_UUID}</identity_uuid>"
            "<email>a@b.com</email>"
            "<date_of_birth>1990-01-01</date_of_birth>"
            "<contact><first_name>Alice</first_name><last_name>Wonder</last_name></contact>"
            "<type>private</type>"
            f"{session_el}"
            '<payment_due><amount currency="eur">30.00</amount><status>unpaid</status></payment_due>'
            "</customer></body></message>"
        )

    def test_bus_event_called_for_new_partner(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [[], 91, True]
        receiver.process_new_registration(self._reg_root(), uid, models)

        bus_call = models.execute_kw.call_args_list[2]
        assert bus_call[0][4] == "send_partner_bus_event"

    def test_bus_event_called_for_existing_partner(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [{"id": 5, "name": "Alice", "x_user_id": _UUID, "x_session_title": ""}],
            True,   # write
            True,   # bus event
        ]
        receiver.process_new_registration(self._reg_root(), uid, models)

        bus_call = models.execute_kw.call_args_list[2]
        assert bus_call[0][4] == "send_partner_bus_event"

    def test_bus_event_amount_matches_payment_due(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [[], 92, True]
        receiver.process_new_registration(self._reg_root(), uid, models)

        bus_call = models.execute_kw.call_args_list[2]
        bus_args = bus_call[0][5]
        # outstanding_amount = payment_due amount = 30.00
        assert bus_args[1] == 30.0

    def test_bus_event_with_session_title_still_called(self, odoo):
        uid, models = odoo
        models.execute_kw.side_effect = [
            [],      # partner not found
            93,      # create
            [],      # product not found
            [],      # no category
            63,      # create product
            True,    # bus event
        ]
        receiver.process_new_registration(self._reg_root("Keynote"), uid, models)

        bus_call = models.execute_kw.call_args_list[5]
        assert bus_call[0][4] == "send_partner_bus_event"
