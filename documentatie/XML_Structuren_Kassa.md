# XML_Structuren_Kassa.md

## XML_Structuren_Kassa.docx

**Technische Integratiedocumentatie — XML & XSD**
Team Kassa (Odoo POS) — Versie 4.0 — Volledige Harmonistatie v2.3
Conform XML_naamgeving standaard (snake_case) | Integratieproject Desideriushogeschool 2026

## 1. Overzicht van alle Flows

Alle messageType-waarden zijn conform de snake_case naamgevingsstandaard.

### Inkomende flows (Kassa ontvangt)

| # | Van | Naar | Routing / Queue | type (enum) | XSD Bestand |
| ---| ---| ---| ---| ---| --- |
| 1 | CRM | Odoo | `kassa.incoming` | new_registration | schema_new_registration.xsd |
| 2 | IoT / Frontend | Odoo | `kassa.incoming` | badge_scanned | schema_badge_scanned.xsd |
| 3 | CRM | Odoo | `kassa.incoming` | profile_update | schema_profile_update.xsd |
| 4 | CRM | Odoo | `kassa.incoming` | cancel_registration | schema_cancel_registration.xsd |
| 6A | CRM | Odoo | `kassa.incoming` | wallet_lease_grant | schema_wallet_lease_grant.xsd |
| 6B | CRM | Odoo | `kassa.incoming` | wallet_remote_topup | schema_wallet_remote_topup.xsd |
| 6C | CRM | Odoo | `kassa.incoming` | event_ended | schema_event_ended.xsd |
| 16 | Frontend | Odoo | `frontend.to.kassa.user_sessions_response` | user_sessions_response | schema_user_sessions_response.xsd |
| 17A | Frontend | Odoo | `frontend.to.kassa.session.created` | session_created | schema_session_created.xsd |
| 17B | Frontend | Odoo | `frontend.to.kassa.session.updated` | session_updated | schema_session_updated.xsd |
| 17C | Frontend | Odoo | `frontend.to.kassa.session.deleted` | session_deleted | schema_session_deleted.xsd |
| 18 | Planning | Odoo | via `planning.exchange` | session_view_response | schema_session_view_response.xsd |

### Uitgaande flows (Kassa verstuurt)

| # | Van | Naar | Routing key | type (enum) | XSD Bestand |
| ---| ---| ---| ---| ---| --- |
| 5A | Odoo | CRM | `kassa.payments.consumption` | consumption_order | schema_consumption_order_v2.3.xsd |
| 5B | Odoo | CRM | `kassa.payments.consumption` | payment_registered (context=consumption) | schema_payment_registered_v2.1.xsd |
| 7 | Odoo | Elastic | `kassa.errors` | system_error | schema_error.xsd |
| 8 | Odoo | Drupal | `kassa.frontend.payment` | payment_status | schema_payment_status.xsd |
| 9 | Odoo | Drupal | `kassa.frontend.wallet` | wallet_balance_update | schema_wallet_balance_update.xsd |
| 10 | Odoo | CRM | `kassa.payments.invoice` | invoice_request | schema_invoice_request.xsd |
| 11 | Odoo | CRM | `kassa.payments.consumption` | consumption_order (is_anonymous=true) | schema_consumption_order_v2.3.xsd |
| 12 | Odoo | CRM | `kassa.payments.badge` | badge_assigned | schema_badge_assigned.xsd |
| 14 | Odoo | CRM | `kassa.payments.registration` | payment_registered (context=registration) | schema_payment_registered_v2.1.xsd |
| 15 | Odoo | CRM | `kassa.payments.refund` | refund_processed | schema_refund_processed.xsd |
| 6D | Odoo | CRM | `kassa.wallet.lease.request` | wallet_lease_request | schema_wallet_lease_request.xsd |
| 6E | Odoo | CRM | `kassa.wallet.lease.return` | wallet_lease_return | schema_wallet_lease_return.xsd |
| 19 | Odoo | Frontend | `kassa.to.frontend.user_sessions_request` | user_sessions_request | schema_user_sessions_request.xsd |
| 20 | Odoo | Planning | via `planning.exchange` | session_view_request | schema_session_view_request.xsd |

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
    <version>2.3</version>
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

| 📥 FLOW 2: Scan Badge / QR-code<br>IoT (Raspberry Pi) of Frontend → Odoo (Kassa Team) via kassa.incoming |
| --- |
| Van: Raspberry Pi (IoT Team) of Frontend (QR-code scan) |
| Naar: Odoo (Kassa Team) |
| Queue: kassa.incoming |
| type: badge_scanned |
| Bestand: schema_badge_scanned.xsd |

**Twee varianten:** fysieke badge (`badge_id`) of QR-code (`identity_uuid`). De receiver accepteert beide; als geen van beide aanwezig is, gooit de code een fout.

Voorbeeld XML (fysieke badge):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>550e8400-e29b-41d4-a716-446655440002</message_id>
    <timestamp>2026-05-15T19:15:00Z</timestamp>
    <source>iot_gateway</source>
    <type>badge_scanned</type>
    <version>2.3</version>
  </header>
  <body>
    <badge_id>QR-98765-ABC</badge_id>
    <location>main_bar</location>
    <scanned_at>2026-05-15T19:15:00Z</scanned_at>
  </body>
</message>
```

Voorbeeld XML (QR-code via identity_uuid):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>550e8400-e29b-41d4-a716-446655440099</message_id>
    <timestamp>2026-05-15T19:20:00Z</timestamp>
    <source>frontend</source>
    <type>badge_scanned</type>
    <version>2.3</version>
  </header>
  <body>
    <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
    <location>session</location>
    <scanned_at>2026-05-15T19:20:00Z</scanned_at>
  </body>
</message>
```

**Locatie-gedrag:** Bij locaties `entrance`, `bar`, `main_bar`, `session` start de receiver automatisch de wallet lease lifecycle (stuurt `wallet_lease_request` naar CRM als nog geen actieve lease). Bij locatie `session` wordt ook een `user_sessions_request` verstuurd naar de Frontend.

| 📥 FLOW 6A: Wallet Lease Bevestiging<br>CRM → Odoo via kassa.incoming |
| --- |
| Van: CRM |
| Naar: Odoo (Kassa Team) |
| Queue: kassa.incoming |
| type: wallet_lease_grant |
| Bestand: schema_wallet_lease_grant.xsd |

Voorbeeld XML:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>aabbccdd-1122-3344-5566-778899aabbcc</message_id>
    <timestamp>2026-05-15T19:16:00Z</timestamp>
    <source>crm</source>
    <type>wallet_lease_grant</type>
    <version>2.3</version>
  </header>
  <body>
    <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
    <lease_id>LEASE-20260515-001</lease_id>
    <current_balance>25.00</current_balance>
  </body>
</message>
```

| 📥 FLOW 6B: Remote Top-up<br>CRM → Odoo via kassa.incoming |
| --- |
| Van: CRM |
| Naar: Odoo (Kassa Team) |
| Queue: kassa.incoming |
| type: wallet_remote_topup |
| Bestand: schema_wallet_remote_topup.xsd |

Voorbeeld XML:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>11223344-5566-7788-99aa-bbccddeeff00</message_id>
    <timestamp>2026-05-15T20:00:00Z</timestamp>
    <source>crm</source>
    <type>wallet_remote_topup</type>
    <version>2.3</version>
  </header>
  <body>
    <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
    <add_amount>10.00</add_amount>
    <reason>online_topup</reason>
  </body>
</message>
```

| 📥 FLOW 6C: Event Beëindigd<br>CRM / Organisator → Odoo via kassa.incoming |
| --- |
| Van: CRM |
| Naar: Odoo (Kassa Team) |
| Queue: kassa.incoming |
| type: event_ended |
| Bestand: schema_event_ended.xsd |

Bij ontvangst: alle actieve leases worden onmiddellijk teruggegeven aan CRM via `wallet_lease_return` berichten.

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
    <version>2.3</version>
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

**Opmerking:** `source` is `kassa` — dit is een uitgaand bericht van Kassa naar CRM.

Voorbeeld XML:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>b12c3d4e-5f6a-7890-bcde-f01234567890</message_id>
    <timestamp>2026-05-15T20:00:00Z</timestamp>
    <source>kassa</source>
    <type>invoice_request</type>
    <version>2.3</version>
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

| **📤 FLOW 6D: Wallet Lease Aanvragen (wallet_lease_request)** | routing key: kassa.wallet.lease.request |
| --- | --- |
| **type:** wallet_lease_request | **Bestand:** schema_wallet_lease_request.xsd |

Verstuurd door receiver.py bij badge-scan op entrance/bar/main_bar/session wanneer nog geen actieve lease bestaat.

| **📤 FLOW 6E: Wallet Lease Teruggeven (wallet_lease_return)** | routing key: kassa.wallet.lease.return |
| --- | --- |
| **type:** wallet_lease_return | **Bestand:** schema_wallet_lease_return.xsd |

Verstuurd bij check-out of bij ontvangst van `event_ended`. Bevat `final_balance`, `lease_id` en `transaction_count`.

| **📤 FLOW 19: Sessies Opvragen (user_sessions_request)** | routing key: kassa.to.frontend.user_sessions_request |
| --- | --- |
| **type:** user_sessions_request | **Bestand:** schema_user_sessions_request.xsd |

Verstuurd door receiver.py bij badge-scan op locatie `session`. Frontend antwoordt met `user_sessions_response`.

| **📤 FLOW 20: Sessiescatalogus Opvragen (session_view_request)** | via planning.exchange |
| --- | --- |
| **type:** session_view_request | **Bestand:** schema_session_view_request.xsd |

Verstuurd door order_poller.py bij detectie van een nieuwe POS-sessie (`check_pos_sessions()`). Planning antwoordt met `session_view_response` zodat de sessiescatalogus met prijzen beschikbaar is in de Inschrijvingskassa.

## 4. Enum Waarden — Volledige Referentie

| Element | Toegestane waarden |
| ---| --- |
| `<header><type>` (inkomend) | new_registration, badge_scanned, profile_update, cancel_registration, wallet_lease_grant, wallet_remote_topup, event_ended, user_event, user_sessions_response, session_created, session_updated, session_deleted, session_view_response |
| `<header><type>` (uitgaand) | consumption_order, payment_registered, payment_status, wallet_balance_update, invoice_request, badge_assigned, refund_processed, system_error, wallet_lease_request, wallet_lease_return, user_sessions_request, session_view_request |
| `<transaction><payment_method>` | company_link, on_site, online |
| `<payment_context>` | registration, consumption |
| `<customer><type>` | private, company, anonymous |
| `<x_identity_status>` | pending, linked, error |

---
*Team Kassa | XML Structuren v4.0 | Conform Contract v2.3 | 2026*
