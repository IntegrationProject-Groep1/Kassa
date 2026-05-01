# XML_Structuren_Kassa.md

## XML_Structuren_Kassa.docx

**Technische Integratiedocumentatie — XML & XSD**
Team Kassa (Odoo POS) — Versie 2.5 — Geïntegreerd document
Conform XML_naamgeving standaard (snake_case) | Integratieproject Desideriushogeschool 2026

## 1. Overzicht van alle Flows

Alle messageType-waarden zijn conform de snake_case naamgevingsstandaard. Flows 11–16 zijn uitbreidingen op de basisflows.

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
| 13 | Uitgaand (2-staps) | Odoo | CRM + Drupal | kassa.exchange → kassa.payments.consumption + kassa.frontend.wallet | consumption_order + wallet_balance_update | zie Flow 5A + Flow 9 |
| 14 | Uitgaand | Odoo | CRM | kassa.exchange → kassa.payments.registration | payment_registered (context=registration) | schema_payment_registered_v2.1.xsd |
| 15 | Uitgaand | Odoo | CRM | kassa.exchange → kassa.payments.refund | refund_processed | schema_refund_processed.xsd |
| 16 | Intern sad path | Odoo | Elastic | kassa.exchange → kassa.errors | system_error (badge_not_found) | schema_error.xsd |

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
    <message_id>MSG-CRM-1001</message_id>
    <type>new_registration</type>
    <source>crm</source>
    <timestamp>2026-02-24T16:00:00Z</timestamp>
    <version>2.0</version>
  </header>
  <body>
    <customer>
      <user_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user_id>
      <email>jan.peeters@ehb.be</email>
      <date_of_birth>1995-06-15</date_of_birth>
      <contact>
        <first_name>Jan</first_name>
        <last_name>Peeters</last_name>
      </contact>
      <type>private</type>
      <session_id>sess-001</session_id>
      <payment_due>
        <amount currency="eur">50.00</amount>
        <status>unpaid</status>
      </payment_due>
    </customer>
  </body>
</message>
```
XSD Schema:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:complexType name="HeaderType">
    <xs:sequence>
      <xs:element name="message_id" type="xs:string"/>
      <xs:element name="type" type="xs:string" fixed="new_registration"/>
      <xs:element name="source" type="xs:string"/>
      <xs:element name="timestamp" type="xs:dateTime"/>
      <xs:element name="version" type="xs:string" fixed="2.0"/>
    </xs:sequence>
  </xs:complexType>

  <xs:complexType name="CustomerType">
    <xs:sequence>
      <xs:element name="user_id" type="xs:string"/>
      <xs:element name="email" type="xs:string"/>
      <xs:element name="date_of_birth" type="xs:date"/>
      <xs:element name="contact">
        <xs:complexType><xs:sequence>
          <xs:element name="first_name" type="xs:string"/>
          <xs:element name="last_name" type="xs:string"/>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="type">
        <xs:simpleType><xs:restriction base="xs:string">
          <xs:enumeration value="private"/>
          <xs:enumeration value="company"/>
        </xs:restriction></xs:simpleType>
      </xs:element>
      <xs:element name="company_name" type="xs:string" minOccurs="0"/>
      <xs:element name="vat_number" type="xs:string" minOccurs="0"/>
      <xs:element name="company_id" type="xs:string" minOccurs="0"/>
      <xs:element name="badge_id" type="xs:string" minOccurs="0"/>
      <xs:element name="session_id" type="xs:string"/>
      <xs:element name="session_title" type="xs:string" minOccurs="0"/>
      <xs:element name="payment_due">
        <xs:complexType><xs:sequence>
          <xs:element name="amount">
            <xs:complexType><xs:simpleContent><xs:extension base="xs:decimal">
              <xs:attribute name="currency" type="xs:string" fixed="eur"/>
            </xs:extension></xs:simpleContent></xs:complexType>
          </xs:element>
          <xs:element name="status">
            <xs:simpleType><xs:restriction base="xs:string">
              <xs:enumeration value="unpaid"/>
              <xs:enumeration value="paid"/>
            </xs:restriction></xs:simpleType>
          </xs:element>
        </xs:sequence></xs:complexType>
      </xs:element>
    </xs:sequence>
  </xs:complexType>

  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header" type="HeaderType"/>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <xs:element name="customer" type="CustomerType"/>
        </xs:sequence></xs:complexType>
      </xs:element>
    </xs:sequence></xs:complexType>
  </xs:element>
</xs:schema>
```

| 📥 FLOW 2: Scan Badge<br>IoT (Raspberry Pi) → Odoo (Kassa Team) via kassa.incoming |
| --- |
| Van: Raspberry Pi (IoT Team) |
| Naar: Odoo (Kassa Team) |
| Queue: kassa.incoming |
| type: badge_scanned |
| Bestand: schema_badge_scanned.xsd |

Aankopen zonder badge moeten altijd mogelijk zijn (Vraag 7). Het sad path (badge niet herkend) wordt gedocumenteerd in Flow 16.
Voorbeeld XML:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>MSG-IOT-5544</message_id>
    <type>badge_scanned</type>
    <source>iot_gateway</source>
    <timestamp>2026-02-24T19:15:00Z</timestamp>
    <version>2.0</version>
  </header>
  <body>
    <badge_id>QR-98765-ABC</badge_id>
    <location>main_bar</location>
    <scanned_at>2026-02-24T19:15:00Z</scanned_at>
  </body>
</message>
```
XSD Schema (schema_badge_scanned.xsd):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id" type="xs:string"/>
          <xs:element name="type" type="xs:string" fixed="badge_scanned"/>
          <xs:element name="source" type="xs:string"/>
          <xs:element name="timestamp" type="xs:dateTime"/>
          <xs:element name="version" type="xs:string" fixed="2.0"/>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <xs:element name="badge_id" type="xs:string"/>
          <xs:element name="location">
            <xs:simpleType><xs:restriction base="xs:string">
              <xs:enumeration value="entrance"/>
              <xs:enumeration value="bar"/>
              <xs:enumeration value="main_bar"/>
              <xs:enumeration value="session"/>
            </xs:restriction></xs:simpleType>
          </xs:element>
          <xs:element name="scanned_at" type="xs:dateTime"/>
        </xs:sequence></xs:complexType>
      </xs:element>
    </xs:sequence></xs:complexType>
  </xs:element>
</xs:schema>
```

| 📥 FLOW 3: ProfileUpdate<br>CRM (Salesforce) → Odoo (Kassa Team) via kassa.incoming |
| --- |
| Van: Salesforce CRM |
| Naar: Odoo (Kassa Team) |
| Queue: kassa.incoming |
| type: profile_update |
| Bestand: schema_profile_update.xsd |

Voorbeeld XML:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>MSG-CRM-7788</message_id>
    <type>profile_update</type>
    <source>crm</source>
    <timestamp>2026-02-24T19:15:00Z</timestamp>
    <version>2.0</version>
  </header>
  <body>
    <user_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user_id>
    <email>jan.peeters@ehb.be</email>
    <contact>
      <first_name>Jan</first_name>
      <last_name>Peeters</last_name>
    </contact>
    <payment_due>
      <amount currency="eur">0.00</amount>
      <status>paid</status>
    </payment_due>
  </body>
</message>
```
XSD Schema (schema_profile_update.xsd):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
<xs:complexType name="HeaderType"><xs:sequence>
<xs:element name="message_id" type="xs:string"/>
<xs:element name="type" type="xs:string" fixed="profile_update"/>
<xs:element name="source" type="xs:string"/>
<xs:element name="timestamp" type="xs:dateTime"/>
<xs:element name="version" type="xs:string"/>
</xs:sequence></xs:complexType>
<xs:element name="message"><xs:complexType><xs:sequence>
<xs:element name="header" type="HeaderType"/>
<xs:element name="body"><xs:complexType><xs:sequence>
<xs:element name="user_id" type="xs:string"/>
<xs:element name="email" type="xs:string"/>
<xs:complexType name="ContactType"><xs:sequence>
<xs:element name="first_name" type="xs:string"/>
<xs:element name="last_name" type="xs:string"/>
</xs:sequence></xs:complexType>
<xs:element name="contact" type="ContactType"/>
<xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
<xs:enumeration value="private"/><xs:enumeration value="company"/>
</xs:restriction></xs:simpleType></xs:element>
<xs:element name="company_name" type="xs:string" minOccurs="0"/>
<xs:element name="vat_number" type="xs:string" minOccurs="0"/>
<xs:element name="company_id" type="xs:string" minOccurs="0"/>
<xs:element name="date_of_birth" type="xs:date"/>
<xs:element name="payment_due" minOccurs="0">
  <xs:complexType><xs:sequence>
    <xs:element name="amount">
      <xs:complexType><xs:simpleContent><xs:extension base="xs:decimal">
        <xs:attribute name="currency" type="xs:string" use="required"/>
      </xs:extension></xs:simpleContent></xs:complexType>
    </xs:element>
    <xs:element name="status">
      <xs:simpleType><xs:restriction base="xs:string">
        <xs:enumeration value="pending"/>
        <xs:enumeration value="paid"/>
      </xs:restriction></xs:simpleType>
    </xs:element>
  </xs:sequence></xs:complexType>
</xs:element>
</xs:sequence></xs:complexType></xs:element>
</xs:sequence></xs:complexType></xs:element>
</xs:schema>
```

| 📥 FLOW 4: CancelRegistration<br>CRM (Salesforce) → Odoo via kassa.incoming |
| --- |
| Van: Salesforce CRM |
| Naar: Odoo (Kassa Team) |
| Queue: kassa.incoming |
| type: cancel_registration |
| Bestand: schema_cancel_registration.xsd |

Voorbeeld XML:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
...
</message>
```

XSD Schema (schema_cancel_registration.xsd):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
...
</xs:schema>
```

3. Uitgaande Flows — Kassa naar CRM

| **📤 FLOW 5A: Bestelling doorsturen (consumption_order)**<br>Odoo (Kassa) → Salesforce (CRM) via kassa.payments | routing key: kassa.payments.consumption |
| --- |
| **Van:** Odoo (Kassa Team) |
| **Naar:** Salesforce (CRM) |
| **Exchange:** kassa.exchange |
| **Routing key:** kassa.payments.consumption |
| **type:** consumption_order |
| **Bestand:** schema_consumption_order_v2.3.xsd |
| **XSD versie:** v2.3 — dekt ook anonieme aankopen (Flow 11) en top-up producten (Flow 13); <id> is nu de unieke transactieregel-ID (LINE-xxx / Consumption_ID), <sku> toegevoegd als fysiek product-ID |

Voorbeeld XML:

```xml
<?xml version="1.0" encoding="UTF-8"?><message>
<header>
<message_id>f47ac10b-58cc-4372-a567-0e02b2c3d479</message_id>
<type>consumption_order</type>
<source>kassa</source>
<timestamp>2026-02-24T18:30:00Z</timestamp>
<version>2.0</version>
</header>
<body>
<is_anonymous>false</is_anonymous>
<customer>
<id>12345</id>
<user_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user_id>
<type>company</type>
<email>info@bedrijf.be</email>
<address><street>Kiekenmarkt</street><number>42</number>
<postal_code>1000</postal_code><city>Brussel</city><country>be</country></address>
</customer>
<items>
<item>
<id>LINE-4201</id>
<sku>BEV-001</sku>
<description>Koffie</description>
<quantity>2</quantity>
<unit_price currency="eur">2.50</unit_price>
<total_amount currency="eur">5.00</total_amount>
<vat_rate>6</vat_rate>
</item>
</items>
</body>
</message>
```

XSD Schema (schema_consumption_order_v2.3.xsd):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!-- Wijzigingen t.o.v. v2.2:
- id in ItemType is nu de unieke transactieregel-ID (LINE-xxx), gebruikt als Consumption_ID door CRM voor Upsert
- sku toegevoegd aan ItemType: het fysieke product-ID uit Odoo (voorheen de waarde van <id>)
Wijzigingen t.o.v. v2.1:
- total_amount toegevoegd aan ItemType (quantity x unit_price, berekend door poller.py)
Wijzigingen t.o.v. v2.0:
- is_anonymous boolean toegevoegd (default false)
- <customer> volledig optioneel (minOccurs=0)
- item_type optioneel veld toegevoegd (wallet_topup voor top-up producten)
- vat_rate enum hersteld, waarde 0 toegevoegd voor top-up producten -->
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
<xs:complexType name="HeaderType"><xs:sequence>
<xs:element name="message_id" type="xs:string"/>
<xs:element name="type" type="xs:string" fixed="consumption_order"/>
<xs:element name="source" type="xs:string"/>
<xs:element name="timestamp" type="xs:dateTime"/>
<xs:element name="version" type="xs:string"/>
</xs:sequence></xs:complexType>
<xs:complexType name="AddressType"><xs:sequence>
<xs:element name="street" type="xs:string"/>
<xs:element name="number" type="xs:string"/>
<xs:element name="postal_code" type="xs:string"/>
<xs:element name="city" type="xs:string"/>
<xs:element name="country" type="xs:string"/>
</xs:sequence></xs:complexType>
<!-- CustomerType: alle velden optioneel in XSD.
Conditionele validatie (is_anonymous=false -> klantdata verplicht)
afgedwongen in code, niet door XSD. -->
<xs:complexType name="CustomerType"><xs:sequence>
<xs:element name="id" type="xs:string" minOccurs="0"/>
<xs:element name="user_id" type="xs:string" minOccurs="0"/>
<xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
<xs:enumeration value="private"/>
<xs:enumeration value="company"/>
</xs:restriction></xs:simpleType></xs:element>
<xs:element name="email" type="xs:string" minOccurs="0"/>
<xs:element name="address" type="AddressType" minOccurs="0"/>
</xs:sequence></xs:complexType>
<xs:complexType name="ItemType"><xs:sequence>
<!-- id: unieke transactieregel-ID (formaat LINE-xxx). Gebruikt als Consumption_ID door CRM voor Upsert. -->
<xs:element name="id" type="xs:string"/>
<!-- sku: fysiek product-ID uit Odoo (voorheen de waarde van <id>). -->
<xs:element name="sku" type="xs:string"/>
<xs:element name="description" type="xs:string"/>
<xs:element name="quantity" type="xs:positiveInteger"/>
<xs:element name="unit_price">
<xs:complexType><xs:simpleContent>
<xs:extension base="xs:decimal">
<xs:attribute name="currency" type="xs:string" use="required"/>
</xs:extension></xs:simpleContent></xs:complexType>
</xs:element>
<xs:element name="vat_rate"><xs:simpleType><xs:restriction base="xs:integer">
<xs:enumeration value="0"/> <!-- Top-up producten -->
<xs:enumeration value="6"/>
<xs:enumeration value="12"/>
<xs:enumeration value="21"/>
</xs:restriction></xs:simpleType></xs:element>
<xs:element name="total_amount">
<xs:complexType><xs:simpleContent>
<xs:extension base="xs:decimal">
<xs:attribute name="currency" type="xs:string" use="required"/>
</xs:extension></xs:simpleContent></xs:complexType>
</xs:element>
<!-- item_type optioneel: waarde wallet_topup voor top-up producten -->
<xs:element name="item_type" type="xs:string" minOccurs="0"/>
</xs:sequence></xs:complexType>
<xs:element name="message"><xs:complexType><xs:sequence>
<xs:element name="header" type="HeaderType"/>
<xs:element name="body"><xs:complexType><xs:sequence>
<xs:element name="is_anonymous" type="xs:boolean" minOccurs="0" default="false"/>
<xs:element name="customer" type="CustomerType" minOccurs="0"/>
<xs:element name="items"><xs:complexType><xs:sequence>
<xs:element name="item" type="ItemType" maxOccurs="unbounded"/>
</xs:sequence></xs:complexType></xs:element>
</xs:sequence></xs:complexType></xs:element>
</xs:sequence></xs:complexType></xs:element>
</xs:schema>
```

```

| **📤 FLOW 5B: Betaling registreren (payment_registered — context: consumption)**<br>Odoo (Kassa) → Salesforce (CRM) via kassa.payments | routing key: kassa.payments.consumption |
| --- |
| **Van:** Odoo (Kassa Team) |
| **Naar:** Salesforce (CRM) |
| **Exchange:** kassa.exchange |
| **Routing key:** kassa.payments.consumption |
| **type:** payment_registered |
| **payment_context:** consumption |
| **Bestand:** schema_payment_registered_v2.1.xsd |
| **correlation_id:** message_id van de bijhorende consumption_order |

Voorbeeld XML:

```xml
<?xml version="1.0" encoding="UTF-8"?><message>
<header>
<message_id>a23bc45d-89ef-1234-b567-1f03c3d4e580</message_id>
<type>payment_registered</type>
<source>kassa</source>
<timestamp>2026-02-24T18:35:00Z</timestamp>
<version>2.0</version>
<correlation_id>f47ac10b-58cc-4372-a567-0e02b2c3d479</correlation_id>
</header>
<body>
<payment_context>consumption</payment_context>
<invoice>
<id>INV-2026-001</id>
<status>paid</status>
<amount_paid currency="eur">15.00</amount_paid>
<due_date>2026-02-24</due_date>
</invoice>
<transaction>
<id>TRX-987654</id>
<payment_method>company_link</payment_method>
</transaction>
</body>
</message>
```

XSD Schema: schema_payment_registered_v2.1.xsd (zie ook Flow 14 — zelfde schema).

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!-- Wijzigingen t.o.v. v2.0:
- payment_context toegevoegd (registration | consumption) - verplicht
- <invoice><id> optioneel (minOccurs=0): afwezig bij registration
- <user_id> op body-niveau optioneel: aanwezig bij registration
- payment_method enum conform PM-standaard: company_link, on_site, online
- due_date: datum van de aankoop zelf (order date_order) bij consumption -->
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
<xs:complexType name="HeaderType"><xs:sequence>
<xs:element name="message_id" type="xs:string"/>
<xs:element name="type" type="xs:string" fixed="payment_registered"/>
<xs:element name="source" type="xs:string"/>
<xs:element name="timestamp" type="xs:dateTime"/>
<xs:element name="version" type="xs:string"/>
<xs:element name="correlation_id" type="xs:string" minOccurs="0"/>
</xs:sequence></xs:complexType>
<xs:complexType name="CurrencyAmountType"><xs:simpleContent>
<xs:extension base="xs:decimal">
<xs:attribute name="currency" type="xs:string" use="required"/>
</xs:extension></xs:simpleContent></xs:complexType>
<xs:element name="message"><xs:complexType><xs:sequence>
<xs:element name="header" type="HeaderType"/>
<xs:element name="body"><xs:complexType><xs:sequence>
<xs:element name="payment_context"><xs:simpleType>
<xs:restriction base="xs:string">
<xs:enumeration value="registration"/>
<xs:enumeration value="consumption"/>
</xs:restriction></xs:simpleType></xs:element>
<xs:element name="user_id" type="xs:string" minOccurs="0"/>
<xs:element name="invoice"><xs:complexType><xs:sequence>
<xs:element name="id" type="xs:string" minOccurs="0"/>
<xs:element name="status"><xs:simpleType><xs:restriction base="xs:string">
<xs:enumeration value="paid"/>
<xs:enumeration value="pending"/>
<xs:enumeration value="cancelled"/>
</xs:restriction></xs:simpleType></xs:element>
<xs:element name="amount_paid" type="CurrencyAmountType"/>
<xs:element name="due_date" type="xs:date"/>
</xs:sequence></xs:complexType></xs:element>
<xs:element name="transaction"><xs:complexType><xs:sequence>
<xs:element name="id" type="xs:string"/>
<xs:element name="payment_method"><xs:simpleType>
<xs:restriction base="xs:string">
<xs:enumeration value="company_link"/>
<xs:enumeration value="on_site"/>
<xs:enumeration value="online"/>
</xs:restriction></xs:simpleType></xs:element>
</xs:sequence></xs:complexType></xs:element>
</xs:sequence></xs:complexType></xs:element>
</xs:sequence></xs:complexType></xs:element>
</xs:schema>
```

# 4. Uitgaande Flows — Kassa naar Elastic (Monitoring)

| **🚨 FLOW 7: Error Log (Sad Path)**<br>Odoo (Kassa) → Elastic Stack via kassa.errors | routing key: kassa.errors |
| --- |
| **Van:** Odoo (Kassa Team) |
| **Naar:** Elastic Stack / Admins |
| **Exchange:** kassa.exchange |
| **Routing key:** kassa.errors |
| **type:** system_error |
| **Bestand:** schema_error.xsd |

Voorbeeld XML:

```xml
<?xml version="1.0" encoding="UTF-8"?><message>
<header>
<message_id>c9d2e415-5f6a-4b7c-8e1d-2a3b4c5d6e7f</message_id>
<type>system_error</type>
<source>kassa</source>
<timestamp>2026-02-24T19:25:00Z</timestamp>
<version>2.0</version>
</header>
<body>
<error_code>invalid_xml_format</error_code>
<error_description>Message does not comply with schema_new_registration.xsd</error_description>
<related_message_id>MSG-CRM-1001</related_message_id>
</body>
</message>
```

XSD Schema (schema_error.xsd):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
<xs:complexType name="HeaderType"><xs:sequence>
<xs:element name="message_id" type="xs:string"/>
<xs:element name="type" type="xs:string" fixed="system_error"/>
<xs:element name="source" type="xs:string"/>
<xs:element name="timestamp" type="xs:dateTime"/>
<xs:element name="version" type="xs:string"/>
</xs:sequence></xs:complexType>
<xs:element name="message"><xs:complexType><xs:sequence>
<xs:element name="header" type="HeaderType"/>
<xs:element name="body"><xs:complexType><xs:sequence>
<xs:element name="error_code"><xs:simpleType><xs:restriction base="xs:string">
<xs:enumeration value="invalid_xml_format"/>
<xs:enumeration value="unknown_message_type"/>
<xs:enumeration value="profile_not_found"/>
<xs:enumeration value="odoo_api_error"/>
<xs:enumeration value="offline_queue_full"/>
<xs:enumeration value="badge_not_found"/>
</xs:restriction></xs:simpleType></xs:element>
<xs:element name="error_description" type="xs:string"/>
<xs:element name="related_message_id" type="xs:string" minOccurs="0"/>
</xs:sequence></xs:complexType></xs:element>
</xs:sequence></xs:complexType></xs:element>
</xs:schema>
```

5. Uitgaande Flows — Kassa naar Drupal (Frontend)

| **📤 FLOW 8: PaymentStatus**<br>Odoo (Kassa) → Drupal (Frontend) via frontend.payments | routing key: kassa.frontend.payment |
| --- |
| **Van:** Odoo (Kassa Team) |
| **Naar:** Drupal (Frontend) |
| **Exchange:** kassa.exchange |
| **Routing key:** kassa.frontend.payment |
| **type:** payment_status |
| **Trigger:** Uitsluitend bij payment_context=registration (inschrijvingsgeld betaald aan kassa) |
| **Bestand:** schema_payment_status.xsd |

Voorbeeld XML:

```xml
<?xml version="1.0" encoding="UTF-8"?><message>
<header>
<message_id>d98a7c65-4b5e-4c6f-8d9e-1a2b3c4d5e6f</message_id>
<type>payment_status</type>
<source>kassa</source>
<timestamp>2026-03-04T10:15:30Z</timestamp>
<version>2.0</version>
</header>
<body>
<user_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user_id>
<payment_status>paid</payment_status>
</body>
</message>
```

XSD Schema (schema_payment_status.xsd):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
<xs:complexType name="HeaderType"><xs:sequence>
<xs:element name="message_id" type="xs:string"/>
<xs:element name="type" type="xs:string" fixed="payment_status"/>
<xs:element name="source" type="xs:string"/>
<xs:element name="timestamp" type="xs:dateTime"/>
<xs:element name="version" type="xs:string"/>
</xs:sequence></xs:complexType>
<xs:element name="message"><xs:complexType><xs:sequence>
<xs:element name="header" type="HeaderType"/>
<xs:element name="body"><xs:complexType><xs:sequence>
<xs:element name="user_id" type="xs:string"/>
<xs:element name="payment_status"><xs:simpleType><xs:restriction base="xs:string">
<xs:enumeration value="paid"/>
<xs:enumeration value="pending"/>
</xs:restriction></xs:simpleType></xs:element>
</xs:sequence></xs:complexType></xs:element>
</xs:sequence></xs:complexType></xs:element>
</xs:schema>
```

```

| **📤 FLOW 9: Wallet Balance Update**<br>Odoo (Kassa) → Drupal (Frontend) via frontend.payments | routing key: kassa.frontend.wallet |
| --- |
| **Van:** Odoo (Kassa Team) |
| **Naar:** Drupal (Frontend) |
| **Exchange:** kassa.exchange |
| **Routing key:** kassa.frontend.wallet |
| **type:** wallet_balance_update |
| **Bestand:** schema_wallet_balance_update.xsd |
| **Triggers:** Na badge-aankoop (Badge Wallet betaling), na top-up (Flow 13), na terugbetaling via badge_wallet (Flow 15) |

Voorbeeld XML:

```xml
<?xml version="1.0" encoding="UTF-8"?><message>
<header>
<message_id>e54a8b72-1c2d-3e4f-5678-7a8b9c0d1e2f</message_id>
<type>wallet_balance_update</type>
<source>kassa</source>
<timestamp>2026-03-06T20:30:00Z</timestamp>
<version>2.0</version>
</header>
<body>
<user_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user_id>
<wallet_balance>15.50</wallet_balance>
</body>
</message>
```

XSD Schema (schema_wallet_balance_update.xsd):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
<xs:complexType name="HeaderType"><xs:sequence>
<xs:element name="message_id" type="xs:string"/>
<xs:element name="type" type="xs:string" fixed="wallet_balance_update"/>
<xs:element name="source" type="xs:string"/>
<xs:element name="timestamp" type="xs:dateTime"/>
<xs:element name="version" type="xs:string"/>
</xs:sequence></xs:complexType>
<xs:element name="message"><xs:complexType><xs:sequence>
<xs:element name="header" type="HeaderType"/>
<xs:element name="body"><xs:complexType><xs:sequence>
<xs:element name="user_id" type="xs:string"/>
<xs:element name="wallet_balance" type="xs:decimal"/>
</xs:sequence></xs:complexType></xs:element>
</xs:sequence></xs:complexType></xs:element>
</xs:schema>
```

6. Overige Uitgaande Flows

| **📤 FLOW 10: Factuuraanvraag (invoice_request)**<br>Odoo (Kassa) → Salesforce (CRM) via kassa.payments | routing key: kassa.payments.invoice |
| --- |
| **Van:** Odoo (Kassa Team) |
| **Naar:** Salesforce (CRM) |
| **Exchange:** kassa.exchange |
| **Routing key:** kassa.payments.invoice |
| **type:** invoice_request |
| **Bestand:** schema_invoice_request.xsd |

Voorbeeld XML:

```xml
<?xml version="1.0" encoding="UTF-8"?><message>
<header>
<message_id>b12c3d4e-5f6a-7890-bcde-f01234567890</message_id>
<type>invoice_request</type>
<source>kassa</source>
<timestamp>2026-02-24T20:00:00Z</timestamp>
<version>2.0</version>
<correlation_id>f47ac10b-58cc-4372-a567-0e02b2c3d479</correlation_id>
</header>
<body>
<user_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user_id>
<invoice_data>
<first_name>Jan</first_name>
<last_name>Peeters</last_name>
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

XSD Schema (schema_invoice_request.xsd):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
<xs:complexType name="HeaderType"><xs:sequence>
<xs:element name="message_id" type="xs:string"/>
<xs:element name="type" type="xs:string" fixed="invoice_request"/>
<xs:element name="source" type="xs:string"/>
<xs:element name="timestamp" type="xs:dateTime"/>
<xs:element name="version" type="xs:string"/>
<xs:element name="correlation_id" type="xs:string" minOccurs="0"/>
</xs:sequence></xs:complexType>
<xs:complexType name="AddressType"><xs:sequence>
<xs:element name="street" type="xs:string"/>
<xs:element name="number" type="xs:string"/>
<xs:element name="postal_code" type="xs:string"/>
<xs:element name="city" type="xs:string"/>
<xs:element name="country" type="xs:string"/>
</xs:sequence></xs:complexType>
<xs:complexType name="InvoiceDataType"><xs:sequence>
<xs:element name="first_name" type="xs:string"/>
<xs:element name="last_name" type="xs:string"/>
<xs:element name="email" type="xs:string"/>
<xs:element name="address" type="AddressType"/>
<xs:element name="vat_number" type="xs:string" minOccurs="0"/>
</xs:sequence></xs:complexType>
<xs:element name="message"><xs:complexType><xs:sequence>
<xs:element name="header" type="HeaderType"/>
<xs:element name="body"><xs:complexType><xs:sequence>
<xs:element name="user_id" type="xs:string"/>
<xs:element name="invoice_data" type="InvoiceDataType"/>
</xs:sequence></xs:complexType></xs:element>
</xs:sequence></xs:complexType></xs:element>
</xs:schema>
```

7. Uitgebreide Flows

| **📤 FLOW 11: Anonieme Aankoop**<br>Odoo (Kassa) → Salesforce (CRM) via kassa.payments | routing key: kassa.payments.consumption |
| --- |
| **Van:** Odoo (Kassa Team) |
| **Naar:** Salesforce (CRM) |
| **Exchange:** kassa.exchange |
| **Routing key:** kassa.payments.consumption |
| **type:** consumption_order |
| **is_anonymous:** true |
| **Bestand:** schema_consumption_order_v2.3.xsd — zelfde XSD als Flow 5A |

Een bezoeker koopt iets aan de kassa zonder badge en zonder account. De <customer>-sectie wordt volledig weggelaten. De XSD (v2.3) valideert dit correct via minOccurs=0 op het <customer> element.
Voorbeeld XML:

```xml
<?xml version="1.0" encoding="UTF-8"?><message>
<header>
<message_id>f11a0000-0000-0000-0000-000000000001</message_id>
<type>consumption_order</type>
<source>kassa</source>
<timestamp>2026-04-15T15:00:00Z</timestamp>
<version>2.0</version>
</header>
<body>
<is_anonymous>true</is_anonymous>
<items>
<item>
<id>LINE-4202</id>
<sku>BEV-002</sku>
<description>Cola</description>
<quantity>1</quantity>
<unit_price currency="eur">2.00</unit_price>
<vat_rate>6</vat_rate>
</item>
</items>
</body>
</message>
```

Sad path: Als is_anonymous=false maar <customer> ontbreekt, faalt XSD-validatie en gaat het bericht naar de DLQ. Na een anonieme aankoop is achteraf geen factuur meer mogelijk — de klant krijgt enkel een kassaticket.
_XSD Schema: hergebruikt schema_consumption_order_v2.3.xsd — zie Flow 5A._| **📤 FLOW 12: Badge Koppeling aan Account (badge_assigned)**<br>Odoo (Kassa) → Salesforce (CRM) via kassa.payments | routing key: kassa.payments.badge |
| --- |
| **Van:** Odoo (Kassa Team) |
| **Naar:** Salesforce (CRM) |
| **Exchange:** kassa.exchange |
| **Routing key:** kassa.payments.badge |
| **type:** badge_assigned |
| **Bestand:** schema_badge_assigned.xsd |
| **PM-goedkeuring:** Formeel goedgekeurd (Vraag 37) |
| **Trigger:** Kassamedewerker koppelt badge aan bezoeker bij inschrijvingsbalie |

Voorbeeld XML:

```xml
<?xml version="1.0" encoding="UTF-8"?><message>
<header>
<message_id>f12b0000-0000-0000-0000-000000000002</message_id>
<type>badge_assigned</type>
<source>kassa</source>
<timestamp>2026-04-15T09:05:00Z</timestamp>
<version>2.0</version>
</header>
<body>
<badge_id>BADGE-RF-00142</badge_id>
<user_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user_id>
<assigned_at>2026-04-15T09:05:00Z</assigned_at>
</body>
</message>
```

XSD Schema (schema_badge_assigned.xsd):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
<xs:complexType name="HeaderType"><xs:sequence>
<xs:element name="message_id" type="xs:string"/>
<xs:element name="type" type="xs:string" fixed="badge_assigned"/>
<xs:element name="source" type="xs:string"/>
<xs:element name="timestamp" type="xs:dateTime"/>
<xs:element name="version" type="xs:string"/>
</xs:sequence></xs:complexType>
<xs:element name="message"><xs:complexType><xs:sequence>
<xs:element name="header" type="HeaderType"/>
<xs:element name="body"><xs:complexType><xs:sequence>
<xs:element name="badge_id" type="xs:string"/>
<xs:element name="user_id" type="xs:string"/>
<xs:element name="assigned_at" type="xs:dateTime"/>
</xs:sequence></xs:complexType></xs:element>
</xs:sequence></xs:complexType></xs:element>
</xs:schema>
```

| 📤 FLOW 13: Badge Saldo Opladen (Top-up Product)<br>Odoo (Kassa) → CRM + Drupal via kassa.payments + frontend.payments |
| --- |
| Mechanisme: Top-up = gewoon Odoo-product. Geen apart berichttype — gebruikt consumption_order + wallet_balance_update. |
| Stap 1 — type: consumption_order (Flow 5A) — items bevat het Top-up product met item_type=wallet_topup |
| Stap 1 — Queue: kassa.payments → Salesforce CRM<br>routing key: kassa.payments.consumption |
| Stap 2 — type: wallet_balance_update (Flow 9) |
| Stap 2 — Queue: frontend.payments → Drupal<br>routing key: kassa.frontend.wallet |
| vat_rate: 0 (saldo-opwaardering is geen belaste dienst) |
| Bestand: schema_consumption_order_v2.3.xsd + schema_wallet_balance_update.xsd |

Voorbeeld XML — Top-up via consumption_order:

```xml
<?xml version="1.0" encoding="UTF-8"?><message>
<header>
<message_id>f13c0000-0000-0000-0000-000000000099</message_id>
<type>consumption_order</type>
<source>kassa</source>
<timestamp>2026-04-15T11:30:00Z</timestamp>
<version>2.0</version>
</header>
<body>
<is_anonymous>false</is_anonymous>
<customer>
<id>12345</id>
<user_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user_id>
<type>private</type>
<email>jan@peeters.be</email>
</customer>
<items>
<item>
<id>LINE-4210</id>
<sku>TOPUP-010</sku>
<description>Top-up EUR 10</description>
<quantity>1</quantity>
<unit_price currency="eur">10.00</unit_price>
<vat_rate>0</vat_rate>
<item_type>wallet_topup</item_type>
</item>
</items>
</body>
</message>
```

_XSD Schema: hergebruikt schema_consumption_order_v2.3.xsd (stap 1, zie Flow 5A) en schema_wallet_balance_update.xsd (stap 2, zie Flow 9)._
Stap 2 — wallet_balance_update naar Drupal: zie Flow 9 XML-voorbeeld. Stuurt het nieuwe saldo na de top-up.| **📤 FLOW 14: Inschrijvingsvergoeding Betaald aan Kassa**<br>Odoo (Kassa) → Salesforce (CRM) via kassa.payments | routing key: kassa.payments.registration |
| --- |
| **Van:** Odoo (Kassa Team) |
| **Naar:** Salesforce (CRM) |
| **Exchange:** kassa.exchange |
| **Routing key:** kassa.payments.registration |
| **type:** payment_registered |
| **payment_context:** registration |
| **correlation_id:** message_id van de originele new_registration (Flow 1) |
| **Bestand:** schema_payment_registered_v2.1.xsd — zelfde XSD als Flow 5B |
| **Verschil met Flow 5B:** <invoice><id> AFWEZIG (CRM maakt factuur aan). <user_id> AANWEZIG op body-niveau. |

Voorbeeld XML:

```xml
<?xml version="1.0" encoding="UTF-8"?><message>
<header>
<message_id>f14d0000-0000-0000-0000-000000000004</message_id>
<type>payment_registered</type>
<source>kassa</source>
<timestamp>2026-04-15T09:15:00Z</timestamp>
<version>2.0</version>
<correlation_id>MSG-CRM-1001</correlation_id>
</header>
<body>
<payment_context>registration</payment_context>
<user_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user_id>
<invoice>
<!-- id weggelaten: factuur bestaat nog niet, CRM maakt die aan -->
<status>paid</status>
<amount_paid currency="eur">50.00</amount_paid>
<due_date>2026-04-15</due_date>
</invoice>
<transaction>
<id>TRX-2026-04150001</id>
<payment_method>on_site</payment_method>
</transaction>
</body>
</message>
```

Sad path: Als het CRM de inschrijving niet als betaald kan markeren (CRM down, user_id niet gevonden), stuurt de kassa een system_error naar kassa.errors met error_code=profile_not_found en de correlation_id van de originele new_registration.
_XSD Schema: hergebruikt schema_payment_registered_v2.1.xsd — zie Flow 5B._| **💶 FLOW 15: Terugbetaling (refund_processed)**<br>Odoo (Kassa) → Salesforce (CRM) via kassa.payments | routing key: kassa.payments.refund |
| --- |
| **Van:** Odoo (Kassa Team) |
| **Naar:** Salesforce (CRM) |
| **Exchange:** kassa.exchange |
| **Routing key:** kassa.payments.refund |
| **type:** refund_processed |
| **PM-goedkeuring:** Opgenomen als goedgekeurd |
| **correlation_id:** message_id van de originele payment_registered die terugbetaald wordt |
| **Bestand:** schema_refund_processed.xsd |
| **Trigger:** Kassamedewerker initieert correctie: dubbele aanrekening, kassafout, onmiddellijke klacht. |
| **Scope:** Enkel kassacorrecties. Planningswijzigingen zijn verantwoordelijkheid van CRM/Facturatie. |

Voorbeeld XML:

```xml
<?xml version="1.0" encoding="UTF-8"?><message>
<header>
<message_id>f15e0000-0000-0000-0000-000000000005</message_id>
<type>refund_processed</type>
<source>kassa</source>
<timestamp>2026-04-15T16:45:00Z</timestamp>
<version>2.0</version>
<correlation_id>f14d0000-0000-0000-0000-000000000004</correlation_id>
</header>
<body>
<refund_type>consumption_item</refund_type>
<user_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user_id>
<refund>
<amount currency="eur">5.00</amount>
<method>badge_wallet</method>
<reason>duplicate_payment</reason>
<description>Dubbele aanrekening gecorrigeerd door kassamedewerker</description>
</refund>
<original_transaction_id>TRX-2026-04150001</original_transaction_id>
<new_wallet_balance currency="eur">20.50</new_wallet_balance>
</body>
</message>
```

Als method=badge_wallet: stuur daarna ook wallet_balance_update naar Drupal (Flow 9). Anonieme terugbetaling: badge_wallet niet mogelijk. Gebruik cash of card_reversal, stuur refund_processed zonder <user_id>. CRM down: buffer het bericht conform Vraag 17.
XSD Schema (schema_refund_processed.xsd):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
<xs:complexType name="HeaderType"><xs:sequence>
<xs:element name="message_id" type="xs:string"/>
<xs:element name="type" type="xs:string" fixed="refund_processed"/>
<xs:element name="source" type="xs:string"/>
<xs:element name="timestamp" type="xs:dateTime"/>
<xs:element name="version" type="xs:string"/>
<xs:element name="correlation_id" type="xs:string" minOccurs="0"/>
</xs:sequence></xs:complexType>
<xs:complexType name="CurrencyAmountType"><xs:simpleContent>
<xs:extension base="xs:decimal">
<xs:attribute name="currency" type="xs:string" use="required"/>
</xs:extension></xs:simpleContent></xs:complexType>
<xs:element name="message"><xs:complexType><xs:sequence>
<xs:element name="header" type="HeaderType"/>
<xs:element name="body"><xs:complexType><xs:sequence>
<xs:element name="refund_type"><xs:simpleType><xs:restriction base="xs:string">
<xs:enumeration value="consumption_item"/>
<xs:enumeration value="partial"/>
</xs:restriction></xs:simpleType></xs:element>
<xs:element name="user_id" type="xs:string" minOccurs="0"/>
<xs:element name="refund"><xs:complexType><xs:sequence>
<xs:element name="amount" type="CurrencyAmountType"/>
<xs:element name="method"><xs:simpleType><xs:restriction base="xs:string">
<xs:enumeration value="badge_wallet"/>
<xs:enumeration value="cash"/>
<xs:enumeration value="card_reversal"/>
</xs:restriction></xs:simpleType></xs:element>
<xs:element name="reason"><xs:simpleType><xs:restriction base="xs:string">
<xs:enumeration value="duplicate_payment"/>
<xs:enumeration value="customer_request"/>
<xs:enumeration value="system_error"/>
</xs:restriction></xs:simpleType></xs:element>
<xs:element name="description" type="xs:string" minOccurs="0"/>
</xs:sequence></xs:complexType></xs:element>
<xs:element name="original_transaction_id" type="xs:string"/>
<xs:element name="new_wallet_balance" type="CurrencyAmountType" minOccurs="0"/>
</xs:sequence></xs:complexType></xs:element>
</xs:sequence></xs:complexType></xs:element>
</xs:schema>
```

```

| **🔍 FLOW 16: Badge Scan Sad Path (badge_not_found)**<br>Intern Odoo gedrag → system_error naar kassa.errors | routing key: kassa.errors |
| --- |
| **Type:** Intern sad path — geen apart inkomend/uitgaand berichttype |
| **Trigger:** Badge gescand (Flow 2) maar badge_id niet gevonden in lokale Odoo-cache |
| **Respons:** system_error naar kassa.errors met error_code=badge_not_found |
| **ACK strategie:** ACK (niet NACK) — een onbekende badge blijft onbekend totdat Flow 12 uitgevoerd wordt |

Voorbeeld system_error bij badge niet gevonden:

```xml
<?xml version="1.0" encoding="UTF-8"?><message>
<header>
<message_id>f16f0000-0000-0000-0000-000000000006</message_id>
<type>system_error</type>
<source>kassa</source>
<timestamp>2026-04-15T14:55:00Z</timestamp>
<version>2.0</version>
</header>
<body>
<error_code>badge_not_found</error_code>
<error_description>Badge BADGE-RF-99999 niet gevonden in lokale Odoo-cache.</error_description>
<related_message_id>MSG-IOT-5523</related_message_id>
</body>
</message>
```

Operationele paden na badge_not_found:

| Beslissing kassamedewerker | Actie |
| ---| --- |
| Pad A — Anoniem | Kassamedewerker klikt 'Anoniem verder'. Kassa gaat door als Flow 11. Geen factuur mogelijk achteraf. |
| Pad B — Wachten | Klant wil badge_wallet of factuur. Medewerker stuurt klant naar inschrijvingsbalie. Badge wordt opnieuw gekoppeld via Flow 12. Volgende scan slaagt. |
| Pad C — Noodkoppeling | Medewerker zoekt klant op naam/e-mail in Odoo en voert Flow 12 handmatig uit ter plekke. ~2 minuten tijdsinvestering. |
| Monitoring | kassa.errors ontvangt system_error met code badge_not_found. Als dezelfde badge_id >3x mislukt binnen 5 minuten triggert Controlroom een alert. |

Waarom ACK en geen NACK bij badge_not_found? Een NACK met requeue=True stuurt het bericht opnieuw aan de queue. Maar een badge die nu onbekend is, blijft dat tot Flow 12 uitgevoerd wordt. Onbeperkt retry-en verstopt de queue en produceert een stortvloed aan identieke errors in Elastic. De juiste strategie: ACK + system_error + operationele afhandeling.
_XSD Schema: hergebruikt schema_error.xsd — zie Flow 7._

## 8. Enum Waarden — Volledige Referentie

Gebruik uitsluitend de onderstaande waarden. Conform XML_naamgeving §4.

| Element | Toegestane waarden | Toelichting |
| ---| ---| --- |
| <header><type> | new_registration, badge_scanned, consumption_order, payment_registered, system_error, profile_update, payment_status, cancel_registration, wallet_balance_update, invoice_request, badge_assigned, refund_processed | PM-goedgekeurd (Vraag 37) |
| <invoice><status> | paid, pending, cancelled | Status van de factuur |
| <transaction><payment_method> | company_link, on_site, online | PM-standaard §4. on_site dekt cash, kaart en badge wallet. Geen andere waarden. |
| <payment_context> | registration, consumption | Verplicht veld in payment_registered. Bepaalt ook routing key. |
| <customer><type> | private, company | Bepaalt of bedrijfsvelden verplicht zijn |
| <payment_due><status> | unpaid, paid | Inschrijvingsstatus in new_registration |
| <payment_status> | paid, pending | Doorgestuurd naar Drupal — enkel bij payment_context=registration |
| <refund><method> | badge_wallet, cash, card_reversal | Terugbetalingsmethode |
| <refund><reason> | duplicate_payment, customer_request, system_error | Gestandaardiseerde reden |
| <refund_type> | consumption_item, partial | Scope van de terugbetaling |
| <error_code> | invalid_xml_format, unknown_message_type, profile_not_found, odoo_api_error, offline_queue_full, badge_not_found | Altijd lowercase. unknown_message_type: onbekend berichttype ontvangen in [receiver.py](http://receiver.py). |
| <vat_rate> | 0, 6, 12, 21 | 0 voor Top-up producten. De poller identificeert deze via de POS-categorie 'Top-ups' of het custom veld `x_is_topup` op `product.product` — niet enkel op BTW-tarief. `vat_rate=0` wordt altijd geforceerd in de XML-export voor deze producten door `poller.py`. BTW-percentage voor overige producten opgehaald via `account.tax`. |

Team Kassa | XML Structuren v2.4 | Conform XML_naamgeving standaard | Integratieproject Desideriushogeschool | 2026
