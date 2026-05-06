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
        xml = sender.build_consumption_order_xml(items, customer_id="1", user_id=str(uuid.uuid4()))
        valid, errors = validate_xml(xml, "schema_consumption_order_v2.3.xsd")
        assert valid, f"XSD Error in consumption_order: {errors}"

    def test_payment_registered_compliance(self):
        xml = sender.build_payment_registered_xml(
            "consumption", "paid", 10.0, "2026-05-06", "TRX1", "on_site",
            user_id=str(uuid.uuid4()), correlation_id=str(uuid.uuid4())
        )
        valid, errors = validate_xml(xml, "schema_payment_registered_v2.1.xsd")
        assert valid, f"XSD Error in payment_registered: {errors}"

    def test_refund_processed_compliance(self):
        xml = sender.build_refund_processed_xml(
            str(uuid.uuid4()), "consumption_item", 5.0, "cash", "customer_request",
            "TRX1", user_id=str(uuid.uuid4())
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
        xml = sender.build_badge_assigned_xml("BADGE1", "user@example.com")
        valid, errors = validate_xml(xml, "schema_badge_assigned.xsd")
        assert valid, f"XSD Error in badge_assigned: {errors}"

    def test_log_compliance(self):
        xml = sender.build_log_xml("info", "payment", "Test log message")
        valid, errors = validate_xml(xml, "schema_log.xsd")
        assert valid, f"XSD Error in log: {errors}"

    def test_system_error_compliance(self):
        root = standardET.Element("message")
        sender._make_header(root, "system_error", order="B")
        body = standardET.SubElement(root, "body")
        standardET.SubElement(body, "error_code").text = "database_error"
        standardET.SubElement(body, "error_description").text = "Something went wrong"
        xml = sender._to_xml(root)
        valid, errors = validate_xml(xml, "schema_error.xsd")
        assert valid, f"XSD Error in system_error: {errors}"
