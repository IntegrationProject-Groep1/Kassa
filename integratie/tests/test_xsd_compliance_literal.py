import uuid
from pathlib import Path
from lxml import etree
import xml.etree.ElementTree as standardET
import sender

_SCHEMA_DIR = Path(__file__).parent.parent / "schemas"


def validate_xml(xml_str, schema_filename):
    schema_path = _SCHEMA_DIR / schema_filename
    parser = etree.XMLParser(resolve_entities=False, dtd_validation=False, no_network=True)
    schema_doc = etree.parse(str(schema_path), parser)
    schema = etree.XMLSchema(schema_doc)
    xml_doc = etree.fromstring(xml_str.encode("utf-8"), parser=parser)
    return schema.validate(xml_doc), schema.error_log


class TestXSDCompliance:

    def test_consumption_order_compliance(self):
        items = [{
            'id': 'LINE-1', 'sku': 'SKU1', 'description': 'Item 1',
            'quantity': 1, 'unit_price': 10.0, 'total_amount': 10.0,
            'vat_rate': 21, 'currency': 'eur'
        }]
        xml = sender.build_consumption_order_xml(items, customer_id="1", identity_uuid=str(uuid.uuid4()))
        valid, errors = validate_xml(xml, "schema_consumption_order_v2.3.xsd")
        assert valid, f"XSD Error in consumption_order: {errors}"

    def test_payment_registered_compliance(self):
        xml = sender.build_payment_registered_xml(
            "consumption", "paid", 10.0, "2026-05-06", "TRX1", "on_site",
            identity_uuid=str(uuid.uuid4()), correlation_id=str(uuid.uuid4())
        )
        valid, errors = validate_xml(xml, "schema_payment_registered_v2.1.xsd")
        assert valid, f"XSD Error in payment_registered: {errors}"

    def test_payment_registered_no_due_date_compliance(self):
        """due_date is optional (minOccurs=0) — must be omitted, not empty."""
        xml = sender.build_payment_registered_xml(
            "registration", "paid", 50.0, None, "TRX2", "on_site",
            identity_uuid=str(uuid.uuid4()),
        )
        valid, errors = validate_xml(xml, "schema_payment_registered_v2.1.xsd")
        assert valid, f"XSD Error in payment_registered (no due_date): {errors}"

    def test_refund_processed_compliance(self):
        xml = sender.build_refund_processed_xml(
            str(uuid.uuid4()), "consumption_item", 5.0, "cash", "customer_request",
            "TRX1", identity_uuid=str(uuid.uuid4())
        )
        valid, errors = validate_xml(xml, "schema_refund_processed.xsd")
        assert valid, f"XSD Error in refund_processed: {errors}"

    def test_invoice_request_compliance(self):
        invoice_data = {
            "first_name": "Jan", "last_name": "Peeters", "email": "jan@example.be",
            "address": {
                "street": "Kiekenmarkt", "number": "42", "postal_code": "1000",
                "city": "Brussel", "country": "be"
            },
            "vat_number": "BE0123456789"
        }
        xml = sender.build_invoice_request_xml(str(uuid.uuid4()), invoice_data, str(uuid.uuid4()))
        valid, errors = validate_xml(xml, "schema_invoice_request.xsd")
        assert valid, f"XSD Error in invoice_request: {errors}"

    def test_wallet_balance_update_compliance(self):
        xml = sender.build_wallet_balance_update_xml(str(uuid.uuid4()), 50.0)
        valid, errors = validate_xml(xml, "schema_wallet_balance_update.xsd")
        assert valid, f"XSD Error in wallet_balance_update: {errors}"

    def test_badge_assigned_compliance(self):
        xml = sender.build_badge_assigned_xml("BADGE1", str(uuid.uuid4()))
        valid, errors = validate_xml(xml, "schema_badge_assigned.xsd")
        assert valid, f"XSD Error in badge_assigned: {errors}"

    def test_log_compliance(self):
        xml = sender.build_log_xml("info", "payment", "Test log message")
        valid, errors = validate_xml(xml, "schema_log.xsd")
        assert valid, f"XSD Error in log: {errors}"

    def test_system_error_compliance(self):
        root = standardET.Element("message")
        sender._make_header(root, "system_error")
        body = standardET.SubElement(root, "body")
        standardET.SubElement(body, "error_code").text = "database_error"
        standardET.SubElement(body, "error_description").text = "Something went wrong"
        xml = sender._to_xml(root)
        valid, errors = validate_xml(xml, "schema_error.xsd")
        assert valid, f"XSD Error in system_error: {errors}"

    def test_wallet_lease_request_compliance(self):
        xml = sender.build_wallet_lease_request_xml(
            identity_uuid=str(uuid.uuid4()),
            badge_id="BADGE-001",
        )
        valid, errors = validate_xml(xml, "schema_wallet_lease_request.xsd")
        assert valid, f"XSD Error in wallet_lease_request: {errors}"

    def test_wallet_lease_request_no_badge_id_compliance(self):
        """QR-path lease_request (badge_id omitted) must pass XSD."""
        xml = sender.build_wallet_lease_request_xml(
            identity_uuid=str(uuid.uuid4()),
            badge_id=None,
        )
        valid, errors = validate_xml(xml, "schema_wallet_lease_request.xsd")
        assert valid, f"XSD Error in wallet_lease_request (no badge_id): {errors}"

    def test_badge_scanned_badge_path_compliance(self):
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<message><header>"
            f"<message_id>{uuid.uuid4()}</message_id>"
            "<timestamp>2026-05-08T12:00:00Z</timestamp>"
            "<source>iot_gateway</source>"
            "<type>badge_scanned</type>"
            "<version>2.0</version>"
            "</header>"
            "<body>"
            "<badge_id>BADGE-001</badge_id>"
            "<location>entrance</location>"
            "<scanned_at>2026-05-08T12:00:00Z</scanned_at>"
            "</body></message>"
        )
        valid, errors = validate_xml(xml, "schema_badge_scanned.xsd")
        assert valid, f"XSD Error in badge_scanned (badge path): {errors}"

    def test_badge_scanned_qr_path_compliance(self):
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<message><header>"
            f"<message_id>{uuid.uuid4()}</message_id>"
            "<timestamp>2026-05-08T12:00:00Z</timestamp>"
            "<source>iot_gateway</source>"
            "<type>badge_scanned</type>"
            "<version>2.0</version>"
            "</header>"
            "<body>"
            f"<identity_uuid>{uuid.uuid4()}</identity_uuid>"
            "<location>bar</location>"
            "<scanned_at>2026-05-08T12:00:00Z</scanned_at>"
            "</body></message>"
        )
        valid, errors = validate_xml(xml, "schema_badge_scanned.xsd")
        assert valid, f"XSD Error in badge_scanned (QR path): {errors}"

    def test_badge_scanned_both_ids_rejected_by_xsd(self):
        """xs:choice enforces exactly one — both badge_id and identity_uuid must fail."""
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<message><header>"
            f"<message_id>{uuid.uuid4()}</message_id>"
            "<timestamp>2026-05-08T12:00:00Z</timestamp>"
            "<source>iot_gateway</source>"
            "<type>badge_scanned</type>"
            "<version>2.0</version>"
            "</header>"
            "<body>"
            "<badge_id>BADGE-001</badge_id>"
            f"<identity_uuid>{uuid.uuid4()}</identity_uuid>"
            "<location>entrance</location>"
            "<scanned_at>2026-05-08T12:00:00Z</scanned_at>"
            "</body></message>"
        )
        valid, _ = validate_xml(xml, "schema_badge_scanned.xsd")
        assert not valid, "xs:choice should reject message with both badge_id and identity_uuid"

    def test_badge_scanned_neither_id_rejected_by_xsd(self):
        """xs:choice enforces exactly one — neither badge_id nor identity_uuid must fail."""
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<message><header>"
            f"<message_id>{uuid.uuid4()}</message_id>"
            "<timestamp>2026-05-08T12:00:00Z</timestamp>"
            "<source>iot_gateway</source>"
            "<type>badge_scanned</type>"
            "<version>2.0</version>"
            "</header>"
            "<body>"
            "<location>entrance</location>"
            "<scanned_at>2026-05-08T12:00:00Z</scanned_at>"
            "</body></message>"
        )
        valid, _ = validate_xml(xml, "schema_badge_scanned.xsd")
        assert not valid, "xs:choice should reject message with neither badge_id nor identity_uuid"

    def test_wallet_lease_return_compliance(self):
        xml = sender.build_wallet_lease_return_xml(
            identity_uuid=str(uuid.uuid4()),
            final_balance=42.50,
            lease_id="LEASE-ABC",
            transaction_count=7,
        )
        valid, errors = validate_xml(xml, "schema_wallet_lease_return.xsd")
        assert valid, f"XSD Error in wallet_lease_return: {errors}"

    def test_wallet_lease_return_zero_balance_compliance(self):
        xml = sender.build_wallet_lease_return_xml(
            identity_uuid=str(uuid.uuid4()),
            final_balance=0.0,
            lease_id="",
            transaction_count=0,
        )
        valid, errors = validate_xml(xml, "schema_wallet_lease_return.xsd")
        assert valid, f"XSD Error in wallet_lease_return (zero balance): {errors}"

    def test_wallet_balance_update_with_authority_and_status_compliance(self):
        xml = sender.build_wallet_balance_update_xml(
            identity_uuid=str(uuid.uuid4()),
            new_balance=15.75,
            authority="kassa",
            status="active",
        )
        valid, errors = validate_xml(xml, "schema_wallet_balance_update.xsd")
        assert valid, f"XSD Error in wallet_balance_update (with authority/status): {errors}"

    def test_wallet_balance_update_without_optional_fields_still_valid(self):
        xml = sender.build_wallet_balance_update_xml(
            identity_uuid=str(uuid.uuid4()),
            new_balance=0.0,
        )
        valid, errors = validate_xml(xml, "schema_wallet_balance_update.xsd")
        assert valid, f"XSD Error in wallet_balance_update (no authority/status): {errors}"
