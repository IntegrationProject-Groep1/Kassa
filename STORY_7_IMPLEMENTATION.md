# Story 7: Factuur vragen voor een drankje — Implementation Summary

## Overview
**Story 7** implements the invoice request feature that allows identified POS customers to request a formal invoice for their purchases. This document verifies that the implementation is complete and meets all Definition of Done criteria.

---

## Implementation Status: ✅ COMPLETE

### Core Components Implemented

#### 1. **Order Detection** (`order_poller.py`)
- ✅ Detects orders marked with `to_invoice=True` 
- ✅ Skips invoice request for anonymous customers
- ✅ Gathers complete customer address data (name, email, street, city, ZIP, country)
- ✅ Extracts VAT number if present

**File:** [integratie/order_poller.py](integratie/order_poller.py)

**Key Logic (lines 240-246):**
```python
# Story 7: Invoice Request logic
if order.get('to_invoice'):
    if is_anonymous:
        logger.warning(f"⚠️ Klant zonder account: geen invoice_request aangemaakt — medewerker geïnformeerd")
    else:
        inv_sent = self._process_invoice_request(order, customer_info)
        all_sent = all_sent and inv_sent
```

#### 2. **Invoice Request Builder** (`sender.py`)
- ✅ Builds XML conforming to `schema_invoice_request.xsd`
- ✅ Supports first_name/last_name or fallback full_name parsing
- ✅ Includes optional VAT number field
- ✅ Generates proper message headers with UUID and timestamp
- ✅ Supports correlation_id linking to original consumption_order

**File:** [integratie/sender.py](integratie/sender.py#L532)

**Function Signature:**
```python
def build_invoice_request_xml(
    user_id: str, 
    invoice_data: dict, 
    correlation_id=None
) -> str:
```

#### 3. **RabbitMQ Routing**
- ✅ Sends to exchange: `kassa.exchange`
- ✅ Routing key: `kassa.payments.invoice`
- ✅ Message type: `invoice_request`

**Configuration (sender.py, line 81):**
```python
"invoice_request": "kassa.payments.invoice",
```

#### 4. **Odoo Field**
- ✅ Uses standard Odoo field `to_invoice` on `pos.order`
- ⚠️ No custom field required — native Odoo boolean field

#### 5. **Outbox Fallback**
- ✅ Messages buffered to `integratie/outbox/outbox.json` if RabbitMQ unavailable
- ✅ Automatic retry on service restart

---

## Definition of Done Checklist

### DoD Item 1: ✅ Correct Fields Sent
**Requirement:** `invoice_request` verstuurd met correcte naam, adres en optioneel BTW-nummer vanuit Odoo

**Evidence:**
- Address components: `street`, `number`, `postal_code`, `city`, `country`
- Customer fields: `first_name`, `last_name`, `email`
- Optional: `vat_number` (only if present in Odoo partner record)

**Test:** `test_dod_invoice_request_sent_with_correct_fields` ✅ PASSED

### DoD Item 2: ✅ No Invoice for Anonymous Customers
**Requirement:** Klant zonder account: geen `invoice_request` aangemaakt — medewerker geïnformeerd

**Implementation:** 
- Order poller checks `is_anonymous` flag
- Skips invoice processing if customer has no account
- Logs warning message (line 243): "⚠️ Klant zonder account: geen invoice_request aangemaakt"

**Test:** `test_process_order_skips_invoice_for_anonymous` ✅ PASSED

### DoD Item 3: ✅ XSD Schema Validation
**Requirement:** Uitgaande XML valide tegen `schema_invoice_request.xsd`

**Schema Location:** [integratie/schemas/schema_invoice_request.xsd](integratie/schemas/schema_invoice_request.xsd)

**Schema Elements:**
```xml
<message>
  <header>
    <message_id/>
    <type>invoice_request</type>
    <source/>
    <timestamp/>
    <version/>
    <correlation_id/>
  </header>
  <body>
    <user_id/>
    <invoice_data>
      <first_name/>
      <last_name/>
      <email/>
      <address>
        <street/>
        <number/>
        <postal_code/>
        <city/>
        <country/>
      </address>
      <vat_number/> <!-- optional -->
    </invoice_data>
  </body>
</message>
```

**Test:** `test_invoice_request_xml_validates_against_schema` ✅ PASSED

### DoD Item 4: ✅ Odoo Flag Update
**Requirement:** `x_rabbitmq_sent=True` gezet na succesvolle verzending

**Implementation:** 
- Handled by `order_poller.process_order()` (line 257-262)
- Sets `x_rabbitmq_sent=True` when all messages sent successfully
- Works for all message types including `invoice_request`

**Code (order_poller.py, lines 257-262):**
```python
if all_sent:
    # All messages reached RabbitMQ — safe to mark as sent in Odoo.
    self.models.execute_kw(
        self.odoo_db, self.odoo_uid, self.odoo_pass,
        'pos.order', 'write',
        [[order_id], {'x_rabbitmq_sent': True}]
    )
```

---

## Technical Implementation Details

### Order Processing Flow

```
pos.order with to_invoice=True
    ↓
OrderPoller.process_order()
    ↓
Detect: order.get('to_invoice') == True
    ↓
Is customer anonymous?
    ├─ YES → Skip invoice, log warning
    └─ NO → Continue
        ↓
    Fetch customer address data
        ↓
    _process_invoice_request(order, customer_info)
        ↓
    Build XML (build_invoice_request_xml)
        ↓
    Send to RabbitMQ (send_typed_message)
        ↓
    All sent successfully?
    ├─ YES → Set x_rabbitmq_sent=True
    └─ NO → Buffer to outbox.json
```

### Data Mapping (Odoo → XML)

| Odoo Field                    | XML Element      | Required | Note |
|-------------------------------|------------------|----------|------|
| `res.partner.name`            | `first_name` + `last_name` | Yes | Split or fallback |
| `res.partner.email`           | `email`          | Yes | Validated |
| `res.partner.street`          | `address.street` | Yes | |
| `res.partner.street2`         | `address.number` | Yes | Default: "1" |
| `res.partner.zip`             | `address.postal_code` | Yes | |
| `res.partner.city`            | `address.city`   | Yes | |
| `res.partner.country_id`      | `address.country` | Yes | ISO code (be, nl, etc.) |
| `res.partner.vat`             | `vat_number`     | No | Only if present |
| `res.partner.x_user_id`       | `user_id`        | Yes | UUID v4, fallback: ODOO-{id} |

---

## Test Coverage

### New Test Suite: `test_invoice_request.py`

**12 test cases created covering:**

1. **XML Building**
   - ✅ With VAT number
   - ✅ Without VAT number
   - ✅ With correlation_id

2. **Schema Validation**
   - ✅ Generated XML validates against XSD

3. **Order Poller Integration**
   - ✅ Processes orders with `to_invoice=True`
   - ✅ Skips anonymous customers
   - ✅ Gathers correct address data

4. **RabbitMQ Messaging**
   - ✅ Sent to correct routing key: `kassa.payments.invoice`

5. **Definition of Done**
   - ✅ Correct fields sent
   - ✅ No invoice for anonymous
   - ✅ XSD validation
   - ✅ Flag update

**Test Results:** ✅ **12/12 PASSED**

```
tests/test_invoice_request.py::TestBuildInvoiceRequestXML::test_build_invoice_request_with_vat PASSED
tests/test_invoice_request.py::TestBuildInvoiceRequestXML::test_build_invoice_request_without_vat PASSED
tests/test_invoice_request.py::TestBuildInvoiceRequestXML::test_build_invoice_request_with_correlation_id PASSED
tests/test_invoice_request.py::TestInvoiceRequestXMLValidation::test_invoice_request_xml_validates_against_schema PASSED
tests/test_invoice_request.py::TestOrderPollerInvoiceRequestDetection::test_process_order_with_to_invoice_flag PASSED
tests/test_invoice_request.py::TestOrderPollerInvoiceRequestDetection::test_process_order_skips_invoice_for_anonymous PASSED
tests/test_invoice_request.py::TestOrderPollerInvoiceRequestDetection::test_process_invoice_request_gathers_address_data PASSED
tests/test_invoice_request.py::TestInvoiceRequestMessaging::test_invoice_request_sent_to_correct_routing_key PASSED
tests/test_invoice_request.py::TestInvoiceRequestDoD::test_dod_invoice_request_sent_with_correct_fields PASSED
tests/test_invoice_request.py::TestInvoiceRequestDoD::test_dod_no_invoice_for_anonymous_customer PASSED
tests/test_invoice_request.py::TestInvoiceRequestDoD::test_dod_xml_validates_against_schema PASSED
tests/test_invoice_request.py::TestInvoiceRequestDoD::test_dod_x_rabbitmq_sent_marked_after_success PASSED
```

---

## Edge Cases Handled

| Case | Behavior | Status |
|------|----------|--------|
| Anonymous customer requests invoice | Invoice request skipped, warning logged | ✅ Implemented |
| Customer has no VAT number | XML sent without vat_number element | ✅ Implemented |
| Customer has incomplete address | Default values used (e.g., street="Onbekend") | ✅ Implemented |
| RabbitMQ unavailable | Message buffered to outbox.json | ✅ Implemented |
| Duplicate order processing | In-memory cache prevents duplicate processing | ✅ Implemented |

---

## Running the Tests

```bash
# Run all Story 7 tests
docker compose exec kassa-integratie python -m pytest tests/test_invoice_request.py -v

# Run specific test
docker compose exec kassa-integratie python -m pytest tests/test_invoice_request.py::TestBuildInvoiceRequestXML::test_build_invoice_request_with_vat -v
```

---

## Integration with Other Stories

**Story 7 integrates with:**

- **Story 1-5** (Consumption orders): Invoice requests are triggered AFTER consumption_order processing
- **Story 6** (Payment registration): Sent alongside payment_registered message
- **Story 21** (Refunds): Not applicable for refunds (negative amounts)

**Message Sequencing Example:**
```
Order paid in Odoo with to_invoice=True
    ↓
1. Send consumption_order (Story 4)
    ↓
2. Send payment_registered (Story 6)
    ↓
3. Send invoice_request (Story 7) ← NEW
    ↓
Set x_rabbitmq_sent=True
```

---

## Files Modified/Created

| File | Change | Status |
|------|--------|--------|
| [integratie/order_poller.py](integratie/order_poller.py#L240) | Added Story 7 detection logic | ✅ Complete |
| [integratie/sender.py](integratie/sender.py#L532) | Already implemented | ✅ Complete |
| [integratie/schemas/schema_invoice_request.xsd](integratie/schemas/schema_invoice_request.xsd) | Exists | ✅ Complete |
| [integratie/tests/test_invoice_request.py](integratie/tests/test_invoice_request.py) | **NEW** - Comprehensive test suite | ✅ Complete |

---

## Known Limitations

1. **Address Parsing:** Street number extracted from `street2` field; if not present, defaults to "1"
2. **Country Code:** Inferred from country name (be, nl, etc.); custom mapping may be needed for other countries
3. **Name Splitting:** If both first_name and last_name absent in Odoo, full_name split by whitespace

---

## Verification Checklist

- [x] XSD schema exists and is accessible
- [x] Order poller detects `to_invoice` flag correctly
- [x] Invoice request XML built with all required fields
- [x] VAT number included when present
- [x] Anonymous customers excluded with logging
- [x] Message sent to correct RabbitMQ routing key
- [x] `x_rabbitmq_sent` flag set after success
- [x] Comprehensive test coverage (12 test cases)
- [x] All tests passing
- [x] Documentation complete

---

## Summary

✅ **Story 7 is fully implemented and tested.**

The invoice request feature is production-ready and meets all Definition of Done criteria. The implementation correctly:

1. Detects orders marked for invoicing
2. Gathers complete customer data from Odoo
3. Builds valid XML conforming to the XSD schema
4. Sends messages to the correct RabbitMQ queue
5. Skips anonymous customers with appropriate logging
6. Marks orders as sent in Odoo

**Next Steps:**
- Deploy to production
- Monitor RabbitMQ queue for invoice_request messages
- Verify CRM (Salesforce) successfully consumes messages
