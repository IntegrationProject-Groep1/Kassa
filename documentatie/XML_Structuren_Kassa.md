# XML_Structuren_Kassa.md

## XML_Structuren_Kassa.docx

**Technische Integratiedocumentatie — XML & XSD**
Team Kassa (Odoo POS) — Versie 3.0 — Volledige Harmonistatie v2.3
Conform XML_naamgeving standaard (snake_case) | Integratieproject Desideriushogeschool 2026

## 1. Overzicht van alle Flows

Alle messageType-waarden zijn conform de snake_case naamgevingsstandaard. 

| # | Richting | Van | Naar | Routing (Exchange & Key) | type (enum) | Bestand |
| ---| ---| ---| ---| ---| ---| --- |
| 1 | Inkomend | CRM | Odoo | kassa.incoming | new_registration | schema_new_registration.xsd |
| 2 | Inkomend | IoT | Odoo | kassa.incoming | badge_scanned | schema_badge_scanned.xsd |
| 3 | Inkomend | CRM | Odoo | kassa.incoming | profile_update | schema_profile_update.xsd |
| 4 | Inkomend | CRM | Odoo | kassa.incoming | cancel_registration | schema_cancel_registration.xsd |
| 5A | Uitgaand | Odoo | CRM | kassa.exchange → kassa.payments.consumption | consumption_order | schema_consumption_order_v2.3.xsd |
| 5B | Uitgaand | Odoo | CRM | kassa.exchange → kassa.payments.consumption | payment_registered | schema_payment_registered_v2.1.xsd |
| 7 | Uitgaand | Odoo | Elastic | kassa.exchange → kassa.errors | system_error | schema_error.xsd |
| 8 | Uitgaand | Odoo | Drupal | kassa.exchange → kassa.frontend.payment | payment_status | schema_payment_status.xsd |
| 9 | Uitgaand | Odoo | Drupal | kassa.exchange → kassa.frontend.wallet | wallet_balance_update | schema_wallet_balance_update.xsd |
| 10 | Uitgaand | Odoo | CRM | kassa.exchange → kassa.payments.invoice | invoice_request | schema_invoice_request.xsd |
| 11 | Uitgaand | Odoo | CRM | kassa.exchange → kassa.payments.consumption | consumption_order (is_anonymous=true) | schema_consumption_order_v2.3.xsd |
| 12 | Uitgaand | Odoo | CRM | kassa.exchange → kassa.payments.badge | badge_assigned | schema_badge_assigned.xsd |
| 14 | Uitgaand | Odoo | CRM | kassa.exchange → kassa.payments.registration | payment_registered (context=registration) | schema_payment_registered_v2.1.xsd |
| 15 | Uitgaand | Odoo | CRM | kassa.exchange → kassa.payments.refund | refund_processed | schema_refund_processed.xsd |

## 2. Inkomende Flows (Kassa ontvangt)

| 📥 FLOW 1: Nieuwe Inschrijving<br>CRM (Salesforce) → Odoo (Kassa Team) via kassa.incoming |
| --- |
| Van: CRM (Salesforce) |
| Naar: Odoo (Kassa Team) |
| Queue: kassa.incoming |
| type: new_registration |
| Bestand: schema_new_registration.xsd |

Voorbeeld XML:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>550e8400-e29b-41d4-a716-446655440001</message_id>
    <timestamp>2026-05-15T10:00:00Z</timestamp>
    <source>crm</source>
    <type>new_registration</type>
    <version>2.0</version>
    <correlation_id>c3a0b1c2-d3e4-5678-abcd-678901200018</correlation_id>
  </header>
  <body>
    <customer>
      <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
      <email>jan.peeters@ehb.be</email>
      <date_of_birth>1995-06-15</date_of_birth>
      <contact>
        <first_name>Jan</first_name>
        <last_name>Peeters</last_name>
      </contact>
      <type>private</type>
      <session_id>sess-001</session_id>
      <session_title>Introductie tot Odoo</session_title>
      <payment_due>
        <amount currency="eur">50.00</amount>
        <status>unpaid</status>
      </payment_due>
    </customer>
  </body>
</message>
```

| 📥 FLOW 2: Scan Badge<br>IoT (Raspberry Pi) → Odoo (Kassa Team) via kassa.incoming |
| --- |
| Van: Raspberry Pi (IoT Team) |
| Naar: Odoo (Kassa Team) |
| Queue: kassa.incoming |
| type: badge_scanned |
| Bestand: schema_badge_scanned.xsd |

Voorbeeld XML:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>550e8400-e29b-41d4-a716-446655440002</message_id>
    <timestamp>2026-05-15T19:15:00Z</timestamp>
    <source>iot_gateway</source>
    <type>badge_scanned</type>
    <version>2.0</version>
  </header>
  <body>
    <badge_id>QR-98765-ABC</badge_id>
    <location>main_bar</location>
    <scanned_at>2026-05-15T19:15:00Z</scanned_at>
  </body>
</message>
```

## 3. Uitgaande Flows — Kassa naar CRM

| **📤 FLOW 5A: Bestelling doorsturen (consumption_order)** | routing key: kassa.payments.consumption |
| --- | --- |
| **type:** consumption_order | **Bestand:** schema_consumption_order_v2.3.xsd |

Voorbeeld XML:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>f47ac10b-58cc-4372-a567-0e02b2c3d479</message_id>
    <timestamp>2026-05-15T18:30:00Z</timestamp>
    <source>kassa</source>
    <type>consumption_order</type>
    <version>2.0</version>
  </header>
  <body>
    <is_anonymous>false</is_anonymous>
    <customer>
      <id>123</id>
      <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
      <type>private</type>
      <email>jan.peeters@ehb.be</email>
      <address>
        <street>Kiekenmarkt</street>
        <number>42</number>
        <postal_code>1000</postal_code>
        <city>Brussel</city>
        <country>be</country>
      </address>
    </customer>
    <items>
      <item>
        <id>LINE-4201</id>
        <sku>101</sku>
        <description>Stella Artois 33cl</description>
        <quantity>2</quantity>
        <unit_price currency="eur">2.50</unit_price>
        <vat_rate>21</vat_rate>
        <total_amount currency="eur">5.00</total_amount>
      </item>
    </items>
  </body>
</message>
```

| **📤 FLOW 10: Factuuraanvraag (invoice_request)** | routing key: kassa.payments.invoice |
| --- | --- |
| **type:** invoice_request | **Bestand:** schema_invoice_request.xsd |

Voorbeeld XML:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>b12c3d4e-5f6a-7890-bcde-f01234567890</message_id>
    <timestamp>2026-05-15T20:00:00Z</timestamp>
    <source>crm</source>
    <type>invoice_request</type>
    <version>2.0</version>
    <correlation_id>f47ac10b-58cc-4372-a567-0e02b2c3d479</correlation_id>
  </header>
  <body>
    <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
    <invoice_data>
      <contact>
        <first_name>Jan</first_name>
        <last_name>Peeters</last_name>
      </contact>
      <email>jan@peeters.be</email>
      <address>
        <street>Kiekenmarkt</street>
        <number>42</number>
        <postal_code>1000</postal_code>
        <city>Brussel</city>
        <country>be</country>
      </address>
      <vat_number>BE0123456789</vat_number>
    </invoice_data>
  </body>
</message>
```

## 4. Enum Waarden — Volledige Referentie

| Element | Toegestane waarden |
| ---| --- |
| <header><type> | new_registration, badge_scanned, consumption_order, payment_registered, system_error, profile_update, payment_status, cancel_registration, wallet_balance_update, invoice_request, badge_assigned, refund_processed |
| <transaction><payment_method> | company_link, on_site, online |
| <payment_context> | registration, consumption |
| <customer><type> | private, company |

---
*Team Kassa | XML Structuren v3.0 | Conform Contract v2.3 | 2026*
