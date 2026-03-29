# XML_Structuren_Kassa.docx

**Technische Integratiedocumentatie — XML & XSD**
Team Kassa (Odoo POS) — Versie 2.3 — Geïntegreerd document
Conform XML\_naamgeving standaard (snake\_case) | Integratieproject Desideriushogeschool 2026
# 1\. Overzicht van alle Flows
Alle messageType-waarden zijn conform de snake\_case naamgevingsstandaard. Flows 11–16 zijn uitbreidingen op de basisflows.

| **#** | **Richting** | **Van** | **Naar** | **Queue** | **type (enum)** | **Bestand** |
| ---| ---| ---| ---| ---| ---| --- |
| 1 | Inkomend | CRM | Odoo | kassa.incoming | new\_registration | schema\_nieuwe\_inschrijving.xsd |
| 2 | Inkomend | IoT | Odoo | kassa.incoming | badge\_scanned | schema\_scan\_badge.xsd |
| 3 | Inkomend | CRM | Odoo | kassa.incoming | profile\_update | schema\_profiel\_update.xsd |
| 4 | Inkomend | CRM | Odoo | kassa.incoming | cancel\_registration | schema\_cancel\_registration.xsd |
| 5A | Uitgaand | Odoo | CRM | kassa.payments | consumption\_order | schema\_consumption\_order\_v2.1.xsd |
| 5B | Uitgaand | Odoo | CRM | kassa.payments | payment\_registered | schema\_payment\_registered\_v2.1.xsd |
| 6 | Uitgaand | Odoo | Elastic | heartbeat | heartbeat | schema\_heartbeat.xsd |
| 7 | Uitgaand | Odoo | Elastic | kassa.errors | system\_error | schema\_error.xsd |
| 8 | Uitgaand | Odoo | Drupal | frontend.payments | payment\_status | schema\_payment\_status.xsd |
| 9 | Uitgaand | Odoo | Drupal | frontend.payments | wallet\_balance\_update | schema\_wallet\_balance\_update.xsd |
| 10 | Uitgaand | Odoo | CRM | kassa.payments | invoice\_request | schema\_invoice\_request.xsd |
| 11 | Uitgaand | Odoo | CRM | kassa.payments | consumption\_order (is\_anonymous=true) | schema\_consumption\_order\_v2.1.xsd |
| 12 | Uitgaand | Odoo | CRM | kassa.payments | badge\_assigned | schema\_badge\_assigned.xsd |
| 13 | Uitgaand (2-staps) | Odoo | CRM + Drupal | kassa.payments + frontend.payments | consumption\_order + wallet\_balance\_update | zie Flow 5A + Flow 9 |
| 14 | Uitgaand | Odoo | CRM | kassa.payments | payment\_registered (context=registration) | schema\_payment\_registered\_v2.1.xsd |
| 15 | Uitgaand | Odoo | CRM | kassa.payments | refund\_processed | schema\_refund\_processed.xsd |
| 16 | Intern sad path | Odoo | Elastic | kassa.errors | system\_error (badge\_not\_found) | schema\_error.xsd |

# 2\. Inkomende Flows (Kassa ontvangt)

| **📥 FLOW 1: Nieuwe Inschrijving**<br>CRM (Salesforce) → Odoo (Kassa Team) via kassa.incoming |
| --- |
| **Van:** CRM (Salesforce) |
| **Naar:** Odoo (Kassa Team) |
| **Queue:** kassa.incoming |
| **type:** new\_registration |
| **Bestand:** schema\_nieuwe\_inschrijving.xsd |

Voorbeeld XML:
<?xml version="1.0" encoding="UTF-8"?>
<message>
<header>
<message\_id>MSG-CRM-1001</message\_id>
<type>new\_registration</type>
<source>crm</source>
<timestamp>2026-02-24T16:00:00Z</timestamp>
<version>2.0</version>
</header>
<body>
<customer>
<email>[info@techbedrijf.be](mailto:info@techbedrijf.be)</email>
<contact>
<first\_name>Jan</first\_name>
<last\_name>Peeters</last\_name>
</contact>
<company\_name>TechCompany NV</company\_name>
<type>company</type>
<vat\_number>BE0123456789</vat\_number>
<user\_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user\_id>
<age>22</age>
</customer>
<payment\_due>
<amount>50.00</amount>
<status>unpaid</status>
</payment\_due>
</body>
</message>
XSD Schema:
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
<xs:complexType name="HeaderType"><xs:sequence>
<xs:element name="message\_id" type="xs:string"/>
<xs:element name="type" type="xs:string" fixed="new\_registration"/>
<xs:element name="source" type="xs:string"/>
<xs:element name="timestamp" type="xs:dateTime"/>
<xs:element name="version" type="xs:string"/>
</xs:sequence></xs:complexType>
<xs:complexType name="CustomerType"><xs:sequence>
<xs:element name="email" type="xs:string"/>
<xs:complexType name="ContactType"><xs:sequence>
<xs:element name="first\_name" type="xs:string"/>
<xs:element name="last\_name" type="xs:string"/>
</xs:sequence></xs:complexType>
<xs:element name="contact" type="ContactType"/>
<xs:element name="company\_name" type="xs:string" minOccurs="0"/>
<xs:element name="type">
<xs:simpleType>
<xs:restriction base="xs:string">
<xs:enumeration value="private"/>
<xs:enumeration value="company"/>
</xs:restriction>
</xs:simpleType>
</xs:element>
<xs:element name="vat\_number" type="xs:string" minOccurs="0"/>
<xs:element name="user\_id" type="xs:string"/>
<xs:element name="age" type="xs:integer"/>
</xs:sequence></xs:complexType>
<xs:complexType name="PaymentDueType"><xs:sequence>
<xs:element name="amount" type="xs:decimal"/>
<xs:element name="status"><xs:simpleType><xs:restriction base="xs:string">
<xs:enumeration value="unpaid"/><xs:enumeration value="paid"/>
</xs:restriction></xs:simpleType></xs:element>
</xs:sequence></xs:complexType>
<xs:element name="message"><xs:complexType><xs:sequence>
<xs:element name="header" type="HeaderType"/>
<xs:element name="body"><xs:complexType><xs:sequence>
<xs:element name="customer" type="CustomerType"/>
<xs:element name="payment\_due" type="PaymentDueType"/>
</xs:sequence></xs:complexType></xs:element>
</xs:sequence></xs:complexType></xs:element>
</xs:schema>

| **📥 FLOW 2: Scan Badge**<br>IoT (Raspberry Pi) → Odoo (Kassa Team) via kassa.incoming |
| --- |
| **Van:** Raspberry Pi (IoT Team) |
| **Naar:** Odoo (Kassa Team) |
| **Queue:** kassa.incoming |
| **type:** badge\_scanned |
| **Bestand:** schema\_scan\_badge.xsd |

Aankopen zonder badge moeten altijd mogelijk zijn (Vraag 7). Het sad path (badge niet herkend) wordt gedocumenteerd in Flow 16.
Voorbeeld XML:
<?xml version="1.0" encoding="UTF-8"?>
<message>
<header>
<message\_id>MSG-IOT-5544</message\_id>
<type>badge\_scanned</type>
<source>iot\_scanner\_bar</source>
<timestamp>2026-02-24T19:15:00Z</timestamp>
<version>2.0</version>
</header>
<body>
<badge\_id>QR-98765-ABC</badge\_id>
<location>hoofdbar</location>
</body>
</message>
XSD Schema:
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
<xs:complexType name="HeaderType"><xs:sequence>
<xs:element name="message\_id" type="xs:string"/>
<xs:element name="type" type="xs:string" fixed="badge\_scanned"/>
<xs:element name="source" type="xs:string"/>
<xs:element name="timestamp" type="xs:dateTime"/>
<xs:element name="version" type="xs:string"/>
</xs:sequence></xs:complexType>
<xs:element name="message"><xs:complexType><xs:sequence>
<xs:element name="header" type="HeaderType"/>
<xs:element name="body"><xs:complexType><xs:sequence>
<xs:element name="badge\_id" type="xs:string"/>
<xs:element name="location" type="xs:string"/>
</xs:sequence></xs:complexType></xs:element>
</xs:sequence></xs:complexType></xs:element>
</xs:schema>

| **📥 FLOW 3: ProfileUpdate**<br>CRM (Salesforce) → Odoo (Kassa Team) via kassa.incoming |
| --- |
| **Van:** Salesforce CRM |
| **Naar:** Odoo (Kassa Team) |
| **Queue:** kassa.incoming |
| **type:** profile\_update |
| **Bestand:** schema\_profiel\_update.xsd |

Voorbeeld XML:
<?xml version="1.0" encoding="UTF-8"?>
<message>
<header>
<message\_id>MSG-CRM-7788</message\_id>
<type>profile\_update</type>
<source>crm</source>
<timestamp>2026-02-24T19:15:00Z</timestamp>
<version>2.0</version>
</header>
<body>
<user\_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user\_id>
<email>[info@techbedrijf.be](mailto:info@techbedrijf.be)</email>
<contact>
<first\_name>Jan</first\_name>
<last\_name>Peeters</last\_name>
</contact>
<company\_name>TechCompany NV</company\_name>
<age>22</age>
<type>company</type>
<vat\_number>BE0123456789</vat\_number>
</body>
</message>
XSD Schema (schema\_profiel\_update.xsd):
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
<xs:complexType name="HeaderType"><xs:sequence>
<xs:element name="message\_id" type="xs:string"/>
<xs:element name="type" type="xs:string" fixed="profile\_update"/>
<xs:element name="source" type="xs:string"/>
<xs:element name="timestamp" type="xs:dateTime"/>
<xs:element name="version" type="xs:string"/>
</xs:sequence></xs:complexType>
<xs:element name="message"><xs:complexType><xs:sequence>
<xs:element name="header" type="HeaderType"/>
<xs:element name="body"><xs:complexType><xs:sequence>
<xs:element name="user\_id" type="xs:string"/>
<xs:element name="email" type="xs:string"/>
<xs:complexType name="ContactType"><xs:sequence>
<xs:element name="first\_name" type="xs:string"/>
<xs:element name="last\_name" type="xs:string"/>
</xs:sequence></xs:complexType>
<xs:element name="contact" type="ContactType"/>
<xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
<xs:enumeration value="private"/><xs:enumeration value="company"/>
</xs:restriction></xs:simpleType></xs:element>
<xs:element name="company\_name" type="xs:string" minOccurs="0"/>
<xs:element name="vat\_number" type="xs:string" minOccurs="0"/>
<xs:element name="age" type="xs:positiveInteger"/>
</xs:sequence></xs:complexType></xs:element>
</xs:sequence></xs:complexType></xs:element>
</xs:schema>

| **📥 FLOW 4: CancelRegistration**<br>CRM (Salesforce) → Odoo via kassa.incoming |
| --- |
| **Van:** Salesforce CRM |
| **Naar:** Odoo (Kassa Team) |
| **Queue:** kassa.incoming |
| **type:** cancel\_registration |
| **Bestand:** schema\_cancel\_registration.xsd |

Voorbeeld XML:
<?xml version="1.0" encoding="UTF-8"?>
<message>
<header>
<message\_id>f12e3d4c-5b6a-7d8e-9f0a-1b2c3d4e5f6a</message\_id>
<type>cancel\_registration</type>
<source>crm</source>
<timestamp>2026-03-04T11:05:00Z</timestamp>
<version>2.0</version>
</header>
<body>
<user\_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user\_id>
<session\_id>session-uuid-001</session\_id>
</body>
</message>
XSD Schema (schema\_cancel\_registration.xsd):
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
<xs:complexType name="HeaderType"><xs:sequence>
<xs:element name="message\_id" type="xs:string"/>
<xs:element name="type" type="xs:string" fixed="cancel\_registration"/>
<xs:element name="source" type="xs:string"/>
<xs:element name="timestamp" type="xs:dateTime"/>
<xs:element name="version" type="xs:string"/>
</xs:sequence></xs:complexType>
<xs:element name="message"><xs:complexType><xs:sequence>
<xs:element name="header" type="HeaderType"/>
<xs:element name="body"><xs:complexType><xs:sequence>
<xs:element name="user\_id" type="xs:string"/>
<xs:element name="session\_id" type="xs:string"/>
</xs:sequence></xs:complexType></xs:element>
</xs:sequence></xs:complexType></xs:element>
</xs:schema>
# 3\. Uitgaande Flows — Kassa naar CRM

| **📤 FLOW 5A: Bestelling doorsturen (consumption\_order)**<br>Odoo (Kassa) → Salesforce (CRM) via kassa.payments | routing key: kassa.payments.consumption |
| --- |
| **Van:** Odoo (Kassa Team) |
| **Naar:** Salesforce (CRM) |
| **Queue:** kassa.payments |
| **Routing key:** kassa.payments.consumption |
| **type:** consumption\_order |
| **Bestand:** schema\_consumption\_order\_v2.1.xsd |
| **XSD versie:** v2.1 — dekt ook anonieme aankopen (Flow 11) en top-up producten (Flow 13) |

Voorbeeld XML:
<?xml version="1.0" encoding="UTF-8"?>
<message>
<header>
<message\_id>f47ac10b-58cc-4372-a567-0e02b2c3d479</message\_id>
<type>consumption\_order</type>
<source>kassa</source>
<timestamp>2026-02-24T18:30:00Z</timestamp>
<version>2.0</version>
</header>
<body>
<is\_anonymous>false</is\_anonymous>
<customer>
<id>12345</id>
<user\_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user\_id>
<type>company</type>
<email>[info@bedrijf.be](mailto:info@bedrijf.be)</email>
<address><street>Kiekenmarkt</street><number>42</number>
<postal\_code>1000</postal\_code><city>Brussel</city><country>be</country></address>
</customer>
<items>
<item>
<id>BEV-001</id>
<description>Koffie</description>
<quantity>2</quantity>
<unit\_price currency="eur">2.50</unit\_price>
<vat\_rate>6</vat\_rate>
</item>
</items>
</body>
</message>
XSD Schema (schema\_consumption\_order\_v2.1.xsd):
<?xml version="1.0" encoding="UTF-8"?>
<!-- Wijzigingen t.o.v. v2.0:
\- is\_anonymous boolean toegevoegd (default false)
\- <customer> volledig optioneel (minOccurs=0)
\- item\_type optioneel veld toegevoegd (wallet\_topup voor top-up producten)
\- vat\_rate enum hersteld, waarde 0 toegevoegd voor top-up producten -->
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
<xs:complexType name="HeaderType"><xs:sequence>
<xs:element name="message\_id" type="xs:string"/>
<xs:element name="type" type="xs:string" fixed="consumption\_order"/>
<xs:element name="source" type="xs:string"/>
<xs:element name="timestamp" type="xs:dateTime"/>
<xs:element name="version" type="xs:string"/>
</xs:sequence></xs:complexType>
<xs:complexType name="AddressType"><xs:sequence>
<xs:element name="street" type="xs:string"/>
<xs:element name="number" type="xs:string"/>
<xs:element name="postal\_code" type="xs:string"/>
<xs:element name="city" type="xs:string"/>
<xs:element name="country" type="xs:string"/>
</xs:sequence></xs:complexType>
<!-- CustomerType: alle velden optioneel in XSD.
Conditionele validatie (is\_anonymous=false -> klantdata verplicht)
afgedwongen in [receiver.py](http://receiver.py), niet door XSD. -->
<xs:complexType name="CustomerType"><xs:sequence>
<xs:element name="id" type="xs:integer" minOccurs="0"/>
<xs:element name="user\_id" type="xs:string" minOccurs="0"/>
<xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
<xs:enumeration value="private"/>
<xs:enumeration value="company"/>
</xs:restriction></xs:simpleType></xs:element>
<xs:element name="email" type="xs:string" minOccurs="0"/>
<xs:element name="address" type="AddressType" minOccurs="0"/>
</xs:sequence></xs:complexType>
<xs:complexType name="ItemType"><xs:sequence>
<xs:element name="id" type="xs:string"/>
<xs:element name="description" type="xs:string"/>
<xs:element name="quantity" type="xs:positiveInteger"/>
<xs:element name="unit\_price">
<xs:complexType><xs:simpleContent>
<xs:extension base="xs:decimal">
<xs:attribute name="currency" type="xs:string" use="required"/>
</xs:extension></xs:simpleContent></xs:complexType>
</xs:element>
<xs:element name="vat\_rate"><xs:simpleType><xs:restriction base="xs:integer">
<xs:enumeration value="0"/> <!-- Top-up producten -->
<xs:enumeration value="6"/>
<xs:enumeration value="12"/>
<xs:enumeration value="21"/>
</xs:restriction></xs:simpleType></xs:element>
<!-- item\_type optioneel: waarde wallet\_topup voor top-up producten -->
<xs:element name="item\_type" type="xs:string" minOccurs="0"/>
</xs:sequence></xs:complexType>
<xs:element name="message"><xs:complexType><xs:sequence>
<xs:element name="header" type="HeaderType"/>
<xs:element name="body"><xs:complexType><xs:sequence>
<xs:element name="is\_anonymous" type="xs:boolean" minOccurs="0" default="false"/>
<xs:element name="customer" type="CustomerType" minOccurs="0"/>
<xs:element name="items"><xs:complexType><xs:sequence>
<xs:element name="item" type="ItemType" maxOccurs="unbounded"/>
</xs:sequence></xs:complexType></xs:element>
</xs:sequence></xs:complexType></xs:element>
</xs:sequence></xs:complexType></xs:element>
</xs:schema>

| **📤 FLOW 5B: Betaling registreren (payment\_registered — context: consumption)**<br>Odoo (Kassa) → Salesforce (CRM) via kassa.payments | routing key: kassa.payments.consumption |
| --- |
| **Van:** Odoo (Kassa Team) |
| **Naar:** Salesforce (CRM) |
| **Queue:** kassa.payments |
| **Routing key:** kassa.payments.consumption |
| **type:** payment\_registered |
| **payment\_context:** consumption |
| **Bestand:** schema\_payment\_registered\_v2.1.xsd |
| **correlation\_id:** message\_id van de bijhorende consumption\_order |

Voorbeeld XML:
<?xml version="1.0" encoding="UTF-8"?>
<message>
<header>
<message\_id>a23bc45d-89ef-1234-b567-1f03c3d4e580</message\_id>
<type>payment\_registered</type>
<source>kassa</source>
<timestamp>2026-02-24T18:35:00Z</timestamp>
<version>2.0</version>
<correlation\_id>f47ac10b-58cc-4372-a567-0e02b2c3d479</correlation\_id>
</header>
<body>
<payment\_context>consumption</payment\_context>
<invoice>
<id>INV-2026-001</id>
<status>paid</status>
<amount\_paid currency="eur">15.00</amount\_paid>
<due\_date>2026-02-24</due\_date>
</invoice>
<transaction>
<id>TRX-987654</id>
<payment\_method>company\_link</payment\_method>
</transaction>
</body>
</message>
XSD Schema: schema\_payment\_registered\_v2.1.xsd (zie ook Flow 14 — zelfde schema).
<?xml version="1.0" encoding="UTF-8"?>
<!-- Wijzigingen t.o.v. v2.0:
\- payment\_context toegevoegd (registration | consumption) - verplicht
\- <invoice><id> optioneel (minOccurs=0): afwezig bij registration
\- <user\_id> op body-niveau optioneel: aanwezig bij registration
\- payment\_method enum conform PM-standaard: company\_link, on\_site, online
\- due\_date: datum van de aankoop zelf (order date\_order) bij consumption -->
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
<xs:complexType name="HeaderType"><xs:sequence>
<xs:element name="message\_id" type="xs:string"/>
<xs:element name="type" type="xs:string" fixed="payment\_registered"/>
<xs:element name="source" type="xs:string"/>
<xs:element name="timestamp" type="xs:dateTime"/>
<xs:element name="version" type="xs:string"/>
<xs:element name="correlation\_id" type="xs:string" minOccurs="0"/>
</xs:sequence></xs:complexType>
<xs:complexType name="CurrencyAmountType"><xs:simpleContent>
<xs:extension base="xs:decimal">
<xs:attribute name="currency" type="xs:string" use="required"/>
</xs:extension></xs:simpleContent></xs:complexType>
<xs:element name="message"><xs:complexType><xs:sequence>
<xs:element name="header" type="HeaderType"/>
<xs:element name="body"><xs:complexType><xs:sequence>
<xs:element name="payment\_context"><xs:simpleType>
<xs:restriction base="xs:string">
<xs:enumeration value="registration"/>
<xs:enumeration value="consumption"/>
</xs:restriction></xs:simpleType></xs:element>
<xs:element name="user\_id" type="xs:string" minOccurs="0"/>
<xs:element name="invoice"><xs:complexType><xs:sequence>
<xs:element name="id" type="xs:string" minOccurs="0"/>
<xs:element name="status"><xs:simpleType><xs:restriction base="xs:string">
<xs:enumeration value="paid"/>
<xs:enumeration value="pending"/>
<xs:enumeration value="cancelled"/>
</xs:restriction></xs:simpleType></xs:element>
<xs:element name="amount\_paid" type="CurrencyAmountType"/>
<xs:element name="due\_date" type="xs:date"/>
</xs:sequence></xs:complexType></xs:element>
<xs:element name="transaction"><xs:complexType><xs:sequence>
<xs:element name="id" type="xs:string"/>
<xs:element name="payment\_method"><xs:simpleType>
<xs:restriction base="xs:string">
<xs:enumeration value="company\_link"/>
<xs:enumeration value="on\_site"/>
<xs:enumeration value="online"/>
</xs:restriction></xs:simpleType></xs:element>
</xs:sequence></xs:complexType></xs:element>
</xs:sequence></xs:complexType></xs:element>
</xs:sequence></xs:complexType></xs:element>
</xs:schema>
# 4\. Uitgaande Flows — Kassa naar Elastic (Monitoring)

| **💓 FLOW 6: Heartbeat**<br>Odoo (Kassa) → Elastic Stack via heartbeat (direct, geen exchange) |
| --- |
| **Van:** Odoo (Kassa Team) |
| **Naar:** Elastic Stack (Monitoring) |
| **Queue:** heartbeat |
| **Routing:** Direct — geen exchange |
| **type:** heartbeat |
| **Bestand:** schema\_heartbeat.xsd |
| **Frequentie:** 1 bericht per seconde |

Zie Heartbeat\_Kassa.docx voor de volledige implementatie inclusief degraded state logica.
Voorbeeld XML:
<?xml version="1.0" encoding="UTF-8"?>
<message>
<header>
<message\_id>a1b2c3d4-e5f6-7890-abcd-ef1234567890</message\_id>
<type>heartbeat</type>
<source>kassa</source>
<timestamp>2026-04-15T14:32:01Z</timestamp>
<version>2.0</version>
</header>
<body>
<status>online</status>
</body>
</message>
XSD Schema (schema\_heartbeat.xsd):
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
<xs:complexType name="HeaderType"><xs:sequence>
<xs:element name="message\_id" type="xs:string"/>
<xs:element name="type" type="xs:string" fixed="heartbeat"/>
<xs:element name="source" type="xs:string"/>
<xs:element name="timestamp" type="xs:dateTime"/>
<xs:element name="version" type="xs:string"/>
</xs:sequence></xs:complexType>
<xs:element name="message"><xs:complexType><xs:sequence>
<xs:element name="header" type="HeaderType"/>
<xs:element name="body"><xs:complexType><xs:sequence>
<xs:element name="status"><xs:simpleType><xs:restriction base="xs:string">
<xs:enumeration value="online"/>
<xs:enumeration value="degraded"/>
<xs:enumeration value="offline"/> <!-- Nooit actief verstuurd — ontbrekende heartbeat IS het offline-signaal -->
</xs:restriction></xs:simpleType></xs:element>
</xs:sequence></xs:complexType></xs:element>
</xs:sequence></xs:complexType></xs:element>
</xs:schema>

| **🚨 FLOW 7: Error Log (Sad Path)**<br>Odoo (Kassa) → Elastic Stack via kassa.errors | routing key: kassa.errors |
| --- |
| **Van:** Odoo (Kassa Team) |
| **Naar:** Elastic Stack / Admins |
| **Queue:** kassa.errors |
| **Routing key:** kassa.errors |
| **type:** system\_error |
| **Bestand:** schema\_error.xsd |

Voorbeeld XML:
<?xml version="1.0" encoding="UTF-8"?>
<message>
<header>
<message\_id>c9d2e415-5f6a-4b7c-8e1d-2a3b4c5d6e7f</message\_id>
<type>system\_error</type>
<source>kassa</source>
<timestamp>2026-02-24T19:25:00Z</timestamp>
<version>2.0</version>
</header>
<body>
<error\_code>invalid\_xml\_format</error\_code>
<error\_description>Message does not comply with schema\_nieuwe\_inschrijving.xsd</error\_description>
<related\_message\_id>MSG-CRM-1001</related\_message\_id>
</body>
</message>
XSD Schema (schema\_error.xsd):
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
<xs:complexType name="HeaderType"><xs:sequence>
<xs:element name="message\_id" type="xs:string"/>
<xs:element name="type" type="xs:string" fixed="system\_error"/>
<xs:element name="source" type="xs:string"/>
<xs:element name="timestamp" type="xs:dateTime"/>
<xs:element name="version" type="xs:string"/>
</xs:sequence></xs:complexType>
<xs:element name="message"><xs:complexType><xs:sequence>
<xs:element name="header" type="HeaderType"/>
<xs:element name="body"><xs:complexType><xs:sequence>
<xs:element name="error\_code"><xs:simpleType><xs:restriction base="xs:string">
<xs:enumeration value="invalid\_xml\_format"/>
<xs:enumeration value="unknown\_message\_type"/>
<xs:enumeration value="profile\_not\_found"/>
<xs:enumeration value="odoo\_api\_error"/>
<xs:enumeration value="rabbitmq\_connection\_error"/>
<xs:enumeration value="offline\_queue\_full"/>
<xs:enumeration value="badge\_not\_found"/>
</xs:restriction></xs:simpleType></xs:element>
<xs:element name="error\_description" type="xs:string"/>
<xs:element name="related\_message\_id" type="xs:string" minOccurs="0"/>
</xs:sequence></xs:complexType></xs:element>
</xs:sequence></xs:complexType></xs:element>
</xs:schema>
# 5\. Uitgaande Flows — Kassa naar Drupal (Frontend)

| **📤 FLOW 8: PaymentStatus**<br>Odoo (Kassa) → Drupal (Frontend) via frontend.payments | routing key: kassa.frontend.payment |
| --- |
| **Van:** Odoo (Kassa Team) |
| **Naar:** Drupal (Frontend) |
| **Queue:** frontend.payments |
| **Routing key:** kassa.frontend.payment |
| **type:** payment\_status |
| **Trigger:** Uitsluitend bij payment\_context=registration (inschrijvingsgeld betaald aan kassa) |
| **Bestand:** schema\_payment\_status.xsd |

Voorbeeld XML:
<?xml version="1.0" encoding="UTF-8"?>
<message>
<header>
<message\_id>d98a7c65-4b5e-4c6f-8d9e-1a2b3c4d5e6f</message\_id>
<type>payment\_status</type>
<source>kassa</source>
<timestamp>2026-03-04T10:15:30Z</timestamp>
<version>2.0</version>
</header>
<body>
<user\_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user\_id>
<payment\_status>paid</payment\_status>
</body>
</message>
XSD Schema (schema\_payment\_status.xsd):
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
<xs:complexType name="HeaderType"><xs:sequence>
<xs:element name="message\_id" type="xs:string"/>
<xs:element name="type" type="xs:string" fixed="payment\_status"/>
<xs:element name="source" type="xs:string"/>
<xs:element name="timestamp" type="xs:dateTime"/>
<xs:element name="version" type="xs:string"/>
</xs:sequence></xs:complexType>
<xs:element name="message"><xs:complexType><xs:sequence>
<xs:element name="header" type="HeaderType"/>
<xs:element name="body"><xs:complexType><xs:sequence>
<xs:element name="user\_id" type="xs:string"/>
<xs:element name="payment\_status"><xs:simpleType><xs:restriction base="xs:string">
<xs:enumeration value="paid"/>
<xs:enumeration value="pending"/>
</xs:restriction></xs:simpleType></xs:element>
</xs:sequence></xs:complexType></xs:element>
</xs:sequence></xs:complexType></xs:element>
</xs:schema>

| **📤 FLOW 9: Wallet Balance Update**<br>Odoo (Kassa) → Drupal (Frontend) via frontend.payments | routing key: kassa.frontend.wallet |
| --- |
| **Van:** Odoo (Kassa Team) |
| **Naar:** Drupal (Frontend) |
| **Queue:** frontend.payments |
| **Routing key:** kassa.frontend.wallet |
| **type:** wallet\_balance\_update |
| **Bestand:** schema\_wallet\_balance\_update.xsd |
| **Triggers:** Na badge-aankoop (Badge Wallet betaling), na top-up (Flow 13), na terugbetaling via badge\_wallet (Flow 15) |

Voorbeeld XML:
<?xml version="1.0" encoding="UTF-8"?>
<message>
<header>
<message\_id>e54a8b72-1c2d-3e4f-5678-7a8b9c0d1e2f</message\_id>
<type>wallet\_balance\_update</type>
<source>kassa</source>
<timestamp>2026-03-06T20:30:00Z</timestamp>
<version>2.0</version>
</header>
<body>
<user\_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user\_id>
<wallet\_balance>15.50</wallet\_balance>
</body>
</message>
XSD Schema (schema\_wallet\_balance\_update.xsd):
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
<xs:complexType name="HeaderType"><xs:sequence>
<xs:element name="message\_id" type="xs:string"/>
<xs:element name="type" type="xs:string" fixed="wallet\_balance\_update"/>
<xs:element name="source" type="xs:string"/>
<xs:element name="timestamp" type="xs:dateTime"/>
<xs:element name="version" type="xs:string"/>
</xs:sequence></xs:complexType>
<xs:element name="message"><xs:complexType><xs:sequence>
<xs:element name="header" type="HeaderType"/>
<xs:element name="body"><xs:complexType><xs:sequence>
<xs:element name="user\_id" type="xs:string"/>
<xs:element name="wallet\_balance" type="xs:decimal"/>
</xs:sequence></xs:complexType></xs:element>
</xs:sequence></xs:complexType></xs:element>
</xs:schema>
# 6\. Overige Uitgaande Flows

| **📤 FLOW 10: Factuuraanvraag (invoice\_request)**<br>Odoo (Kassa) → Salesforce (CRM) via kassa.payments | routing key: kassa.payments.invoice |
| --- |
| **Van:** Odoo (Kassa Team) |
| **Naar:** Salesforce (CRM) |
| **Queue:** kassa.payments |
| **Routing key:** kassa.payments.invoice |
| **type:** invoice\_request |
| **Bestand:** schema\_invoice\_request.xsd |

Voorbeeld XML:
<?xml version="1.0" encoding="UTF-8"?>
<message>
<header>
<message\_id>b12c3d4e-5f6a-7890-bcde-f01234567890</message\_id>
<type>invoice\_request</type>
<source>kassa</source>
<timestamp>2026-02-24T20:00:00Z</timestamp>
<version>2.0</version>
<correlation\_id>f47ac10b-58cc-4372-a567-0e02b2c3d479</correlation\_id>
</header>
<body>
<user\_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user\_id>
<invoice\_data>
<first\_name>Jan</first\_name>
<last\_name>Peeters</last\_name>
<email>[jan@peeters.be](mailto:jan@peeters.be)</email>
<address>
<street>Kiekenmarkt</street>
<number>42</number>
<postal\_code>1000</postal\_code>
<city>Brussel</city>
<country>be</country>
</address>
<vat\_number>BE0123456789</vat\_number>
</invoice\_data>
</body>
</message>
XSD Schema (schema\_invoice\_request.xsd):
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
<xs:complexType name="HeaderType"><xs:sequence>
<xs:element name="message\_id" type="xs:string"/>
<xs:element name="type" type="xs:string" fixed="invoice\_request"/>
<xs:element name="source" type="xs:string"/>
<xs:element name="timestamp" type="xs:dateTime"/>
<xs:element name="version" type="xs:string"/>
<xs:element name="correlation\_id" type="xs:string" minOccurs="0"/>
</xs:sequence></xs:complexType>
<xs:complexType name="AddressType"><xs:sequence>
<xs:element name="street" type="xs:string"/>
<xs:element name="number" type="xs:string"/>
<xs:element name="postal\_code" type="xs:string"/>
<xs:element name="city" type="xs:string"/>
<xs:element name="country" type="xs:string"/>
</xs:sequence></xs:complexType>
<xs:complexType name="InvoiceDataType"><xs:sequence>
<xs:element name="first\_name" type="xs:string"/>
<xs:element name="last\_name" type="xs:string"/>
<xs:element name="email" type="xs:string"/>
<xs:element name="address" type="AddressType"/>
<xs:element name="vat\_number" type="xs:string" minOccurs="0"/>
</xs:sequence></xs:complexType>
<xs:element name="message"><xs:complexType><xs:sequence>
<xs:element name="header" type="HeaderType"/>
<xs:element name="body"><xs:complexType><xs:sequence>
<xs:element name="user\_id" type="xs:string"/>
<xs:element name="invoice\_data" type="InvoiceDataType"/>
</xs:sequence></xs:complexType></xs:element>
</xs:sequence></xs:complexType></xs:element>
</xs:schema>
# 7\. Uitgebreide Flows

| **📤 FLOW 11: Anonieme Aankoop**<br>Odoo (Kassa) → Salesforce (CRM) via kassa.payments | routing key: kassa.payments.consumption |
| --- |
| **Van:** Odoo (Kassa Team) |
| **Naar:** Salesforce (CRM) |
| **Queue:** kassa.payments |
| **Routing key:** kassa.payments.consumption |
| **type:** consumption\_order |
| **is\_anonymous:** true |
| **Bestand:** schema\_consumption\_order\_v2.1.xsd — zelfde XSD als Flow 5A |

Een bezoeker koopt iets aan de kassa zonder badge en zonder account. De <customer>-sectie wordt volledig weggelaten. De XSD (v2.1) valideert dit correct via minOccurs=0 op het <customer> element.
Voorbeeld XML:
<?xml version="1.0" encoding="UTF-8"?>
<message>
<header>
<message\_id>f11a0000-0000-0000-0000-000000000001</message\_id>
<type>consumption\_order</type>
<source>kassa</source>
<timestamp>2026-04-15T15:00:00Z</timestamp>
<version>2.0</version>
</header>
<body>
<is\_anonymous>true</is\_anonymous>
<items>
<item>
<id>BEV-002</id>
<description>Cola</description>
<quantity>1</quantity>
<unit\_price currency="eur">2.00</unit\_price>
<vat\_rate>6</vat\_rate>
</item>
</items>
</body>
</message>
Sad path: Als is\_anonymous=false maar <customer> ontbreekt, faalt XSD-validatie en gaat het bericht naar de DLQ. Na een anonieme aankoop is achteraf geen factuur meer mogelijk — de klant krijgt enkel een kassaticket.
_XSD Schema: hergebruikt schema\_consumption\_order\_v2.1.xsd — zie Flow 5A._

| **📤 FLOW 12: Badge Koppeling aan Account (badge\_assigned)**<br>Odoo (Kassa) → Salesforce (CRM) via kassa.payments | routing key: kassa.payments.badge |
| --- |
| **Van:** Odoo (Kassa Team) |
| **Naar:** Salesforce (CRM) |
| **Queue:** kassa.payments |
| **Routing key:** kassa.payments.badge |
| **type:** badge\_assigned |
| **Bestand:** schema\_badge\_assigned.xsd |
| **PM-goedkeuring:** Formeel goedgekeurd (Vraag 37) |
| **Trigger:** Kassamedewerker koppelt badge aan bezoeker bij inschrijvingsbalie |

Voorbeeld XML:
<?xml version="1.0" encoding="UTF-8"?>
<message>
<header>
<message\_id>f12b0000-0000-0000-0000-000000000002</message\_id>
<type>badge\_assigned</type>
<source>kassa</source>
<timestamp>2026-04-15T09:05:00Z</timestamp>
<version>2.0</version>
</header>
<body>
<badge\_id>BADGE-RF-00142</badge\_id>
<user\_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user\_id>
<assigned\_at>2026-04-15T09:05:00Z</assigned\_at>
</body>
</message>
XSD Schema (schema\_badge\_assigned.xsd):
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
<xs:complexType name="HeaderType"><xs:sequence>
<xs:element name="message\_id" type="xs:string"/>
<xs:element name="type" type="xs:string" fixed="badge\_assigned"/>
<xs:element name="source" type="xs:string"/>
<xs:element name="timestamp" type="xs:dateTime"/>
<xs:element name="version" type="xs:string"/>
</xs:sequence></xs:complexType>
<xs:element name="message"><xs:complexType><xs:sequence>
<xs:element name="header" type="HeaderType"/>
<xs:element name="body"><xs:complexType><xs:sequence>
<xs:element name="badge\_id" type="xs:string"/>
<xs:element name="user\_id" type="xs:string"/>
<xs:element name="assigned\_at" type="xs:dateTime"/>
</xs:sequence></xs:complexType></xs:element>
</xs:sequence></xs:complexType></xs:element>
</xs:schema>

| **📤 FLOW 13: Badge Saldo Opladen (Top-up Product)**<br>Odoo (Kassa) → CRM + Drupal via kassa.payments + frontend.payments |
| --- |
| **Mechanisme:** Top-up = gewoon Odoo-product. Geen apart berichttype — gebruikt consumption\_order + wallet\_balance\_update. |
| **Stap 1 — type:** consumption\_order (Flow 5A) — items bevat het Top-up product met item\_type=wallet\_topup |
| **Stap 1 — Queue:** kassa.payments → Salesforce CRM | routing key: kassa.payments.consumption |
| **Stap 2 — type:** wallet\_balance\_update (Flow 9) |
| **Stap 2 — Queue:** frontend.payments → Drupal | routing key: kassa.frontend.wallet |
| **vat\_rate:** 0 (saldo-opwaardering is geen belaste dienst) |
| **Bestand:** schema\_consumption\_order\_v2.1.xsd + schema\_wallet\_balance\_update.xsd |

Voorbeeld XML — Top-up via consumption\_order:
<?xml version="1.0" encoding="UTF-8"?>
<message>
<header>
<message\_id>f13c0000-0000-0000-0000-000000000099</message\_id>
<type>consumption\_order</type>
<source>kassa</source>
<timestamp>2026-04-15T11:30:00Z</timestamp>
<version>2.0</version>
</header>
<body>
<is\_anonymous>false</is\_anonymous>
<customer>
<id>12345</id>
<user\_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user\_id>
<type>private</type>
<email>[jan@peeters.be](mailto:jan@peeters.be)</email>
</customer>
<items>
<item>
<id>TOPUP-010</id>
<description>Top-up EUR 10</description>
<quantity>1</quantity>
<unit\_price currency="eur">10.00</unit\_price>
<vat\_rate>0</vat\_rate>
<item\_type>wallet\_topup</item\_type>
</item>
</items>
</body>
</message>
_XSD Schema: hergebruikt schema\_consumption\_order\_v2.1.xsd (stap 1, zie Flow 5A) en schema\_wallet\_balance\_update.xsd (stap 2, zie Flow 9)._
Stap 2 — wallet\_balance\_update naar Drupal: zie Flow 9 XML-voorbeeld. Stuurt het nieuwe saldo na de top-up.

| **📤 FLOW 14: Inschrijvingsvergoeding Betaald aan Kassa**<br>Odoo (Kassa) → Salesforce (CRM) via kassa.payments | routing key: kassa.payments.registration |
| --- |
| **Van:** Odoo (Kassa Team) |
| **Naar:** Salesforce (CRM) |
| **Queue:** kassa.payments |
| **Routing key:** kassa.payments.registration |
| **type:** payment\_registered |
| **payment\_context:** registration |
| **correlation\_id:** message\_id van de originele new\_registration (Flow 1) |
| **Bestand:** schema\_payment\_registered\_v2.1.xsd — zelfde XSD als Flow 5B |
| **Verschil met Flow 5B:** <invoice><id> AFWEZIG (CRM maakt factuur aan). <user\_id> AANWEZIG op body-niveau. |

Voorbeeld XML:
<?xml version="1.0" encoding="UTF-8"?>
<message>
<header>
<message\_id>f14d0000-0000-0000-0000-000000000004</message\_id>
<type>payment\_registered</type>
<source>kassa</source>
<timestamp>2026-04-15T09:15:00Z</timestamp>
<version>2.0</version>
<correlation\_id>MSG-CRM-1001</correlation\_id>
</header>
<body>
<payment\_context>registration</payment\_context>
<user\_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user\_id>
<invoice>
<!-- id weggelaten: factuur bestaat nog niet, CRM maakt die aan -->
<status>paid</status>
<amount\_paid currency="eur">50.00</amount\_paid>
<due\_date>2026-04-15</due\_date>
</invoice>
<transaction>
<id>TRX-2026-04150001</id>
<payment\_method>on\_site</payment\_method>
</transaction>
</body>
</message>
Sad path: Als het CRM de inschrijving niet als betaald kan markeren (CRM down, user\_id niet gevonden), stuurt de kassa een system\_error naar kassa.errors met error\_code=profile\_not\_found en de correlation\_id van de originele new\_registration.
_XSD Schema: hergebruikt schema\_payment\_registered\_v2.1.xsd — zie Flow 5B._

| **💶 FLOW 15: Terugbetaling (refund\_processed)**<br>Odoo (Kassa) → Salesforce (CRM) via kassa.payments | routing key: kassa.payments.refund |
| --- |
| **Van:** Odoo (Kassa Team) |
| **Naar:** Salesforce (CRM) |
| **Queue:** kassa.payments |
| **Routing key:** kassa.payments.refund |
| **type:** refund\_processed |
| **PM-goedkeuring:** Opgenomen als goedgekeurd |
| **correlation\_id:** message\_id van de originele payment\_registered die terugbetaald wordt |
| **Bestand:** schema\_refund\_processed.xsd |
| **Trigger:** Kassamedewerker initieert correctie: dubbele aanrekening, kassafout, onmiddellijke klacht. |
| **Scope:** Enkel kassacorrecties. Planningswijzigingen zijn verantwoordelijkheid van CRM/Facturatie. |

Voorbeeld XML:
<?xml version="1.0" encoding="UTF-8"?>
<message>
<header>
<message\_id>f15e0000-0000-0000-0000-000000000005</message\_id>
<type>refund\_processed</type>
<source>kassa</source>
<timestamp>2026-04-15T16:45:00Z</timestamp>
<version>2.0</version>
<correlation\_id>f14d0000-0000-0000-0000-000000000004</correlation\_id>
</header>
<body>
<refund\_type>consumption\_item</refund\_type>
<user\_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user\_id>
<refund>
<amount currency="eur">5.00</amount>
<method>badge\_wallet</method>
<reason>duplicate\_payment</reason>
<description>Dubbele aanrekening gecorrigeerd door kassamedewerker</description>
</refund>
<original\_transaction\_id>TRX-2026-04150001</original\_transaction\_id>
<new\_wallet\_balance currency="eur">20.50</new\_wallet\_balance>
</body>
</message>
Als method=badge\_wallet: stuur daarna ook wallet\_balance\_update naar Drupal (Flow 9). Anonieme terugbetaling: badge\_wallet niet mogelijk. Gebruik cash of card\_reversal, stuur refund\_processed zonder <user\_id>. CRM down: buffer het bericht conform Vraag 17.
XSD Schema (schema\_refund\_processed.xsd):
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
<xs:complexType name="HeaderType"><xs:sequence>
<xs:element name="message\_id" type="xs:string"/>
<xs:element name="type" type="xs:string" fixed="refund\_processed"/>
<xs:element name="source" type="xs:string"/>
<xs:element name="timestamp" type="xs:dateTime"/>
<xs:element name="version" type="xs:string"/>
<xs:element name="correlation\_id" type="xs:string" minOccurs="0"/>
</xs:sequence></xs:complexType>
<xs:complexType name="CurrencyAmountType"><xs:simpleContent>
<xs:extension base="xs:decimal">
<xs:attribute name="currency" type="xs:string" use="required"/>
</xs:extension></xs:simpleContent></xs:complexType>
<xs:element name="message"><xs:complexType><xs:sequence>
<xs:element name="header" type="HeaderType"/>
<xs:element name="body"><xs:complexType><xs:sequence>
<xs:element name="refund\_type"><xs:simpleType><xs:restriction base="xs:string">
<xs:enumeration value="consumption\_item"/>
<xs:enumeration value="partial"/>
</xs:restriction></xs:simpleType></xs:element>
<xs:element name="user\_id" type="xs:string" minOccurs="0"/>
<xs:element name="refund"><xs:complexType><xs:sequence>
<xs:element name="amount" type="CurrencyAmountType"/>
<xs:element name="method"><xs:simpleType><xs:restriction base="xs:string">
<xs:enumeration value="badge\_wallet"/>
<xs:enumeration value="cash"/>
<xs:enumeration value="card\_reversal"/>
</xs:restriction></xs:simpleType></xs:element>
<xs:element name="reason"><xs:simpleType><xs:restriction base="xs:string">
<xs:enumeration value="duplicate\_payment"/>
<xs:enumeration value="customer\_request"/>
<xs:enumeration value="system\_error"/>
</xs:restriction></xs:simpleType></xs:element>
<xs:element name="description" type="xs:string" minOccurs="0"/>
</xs:sequence></xs:complexType></xs:element>
<xs:element name="original\_transaction\_id" type="xs:string"/>
<xs:element name="new\_wallet\_balance" type="CurrencyAmountType" minOccurs="0"/>
</xs:sequence></xs:complexType></xs:element>
</xs:sequence></xs:complexType></xs:element>
</xs:schema>

| **🔍 FLOW 16: Badge Scan Sad Path (badge\_not\_found)**<br>Intern Odoo gedrag → system\_error naar kassa.errors | routing key: kassa.errors |
| --- |
| **Type:** Intern sad path — geen apart inkomend/uitgaand berichttype |
| **Trigger:** Badge gescand (Flow 2) maar badge\_id niet gevonden in lokale Odoo-cache |
| **Respons:** system\_error naar kassa.errors met error\_code=badge\_not\_found |
| **ACK strategie:** ACK (niet NACK) — een onbekende badge blijft onbekend totdat Flow 12 uitgevoerd wordt |

Voorbeeld system\_error bij badge niet gevonden:
<?xml version="1.0" encoding="UTF-8"?>
<message>
<header>
<message\_id>f16f0000-0000-0000-0000-000000000006</message\_id>
<type>system\_error</type>
<source>kassa</source>
<timestamp>2026-04-15T14:55:00Z</timestamp>
<version>2.0</version>
</header>
<body>
<error\_code>badge\_not\_found</error\_code>
<error\_description>Badge BADGE-RF-99999 niet gevonden in lokale Odoo-cache.</error\_description>
<related\_message\_id>MSG-IOT-5523</related\_message\_id>
</body>
</message>
Operationele paden na badge\_not\_found:

| **Beslissing kassamedewerker** | **Actie** |
| ---| --- |
| Pad A — Anoniem | Kassamedewerker klikt 'Anoniem verder'. Kassa gaat door als Flow 11. Geen factuur mogelijk achteraf. |
| Pad B — Wachten | Klant wil badge\_wallet of factuur. Medewerker stuurt klant naar inschrijvingsbalie. Badge wordt opnieuw gekoppeld via Flow 12. Volgende scan slaagt. |
| Pad C — Noodkoppeling | Medewerker zoekt klant op naam/e-mail in Odoo en voert Flow 12 handmatig uit ter plekke. ~2 minuten tijdsinvestering. |
| Monitoring | kassa.errors ontvangt system\_error met code badge\_not\_found. Als dezelfde badge\_id >3x mislukt binnen 5 minuten triggert Controlroom een alert. |

Waarom ACK en geen NACK bij badge\_not\_found? Een NACK met requeue=True stuurt het bericht opnieuw aan de queue. Maar een badge die nu onbekend is, blijft dat tot Flow 12 uitgevoerd wordt. Onbeperkt retry-en verstopt de queue en produceert een stortvloed aan identieke errors in Elastic. De juiste strategie: ACK + system\_error + operationele afhandeling.
_XSD Schema: hergebruikt schema\_error.xsd — zie Flow 7._
# 8\. Enum Waarden — Volledige Referentie
Gebruik uitsluitend de onderstaande waarden. Conform XML\_naamgeving §4.

| **Element** | **Toegestane waarden** | **Toelichting** |
| ---| ---| --- |
| <header><type> | new\_registration, badge\_scanned, consumption\_order, payment\_registered, system\_error, profile\_update, payment\_status, cancel\_registration, wallet\_balance\_update, invoice\_request, heartbeat, badge\_assigned, refund\_processed | PM-goedgekeurd (Vraag 37) |
| <body><status> (heartbeat) | online, degraded, offline | Operationele status kassa |
| <invoice><status> | paid, pending, cancelled | Status van de factuur |
| <transaction><payment\_method> | company\_link, on\_site, online | PM-standaard §4. on\_site dekt cash, kaart en badge wallet. Geen andere waarden. |
| <payment\_context> | registration, consumption | Verplicht veld in payment\_registered. Bepaalt ook routing key. |
| <customer><type> | private, company | Bepaalt of bedrijfsvelden verplicht zijn |
| <payment\_due><status> | unpaid, paid | Inschrijvingsstatus in new\_registration |
| <payment\_status> | paid, pending | Doorgestuurd naar Drupal — enkel bij payment\_context=registration |
| <refund><method> | badge\_wallet, cash, card\_reversal | Terugbetalingsmethode |
| <refund><reason> | duplicate\_payment, customer\_request, system\_error | Gestandaardiseerde reden |
| <refund\_type> | consumption\_item, partial | Scope van de terugbetaling |
| <error\_code> | invalid\_xml\_format, unknown\_message\_type, profile\_not\_found, odoo\_api\_error, rabbitmq\_connection\_error, offline\_queue\_full, badge\_not\_found | Altijd lowercase. unknown\_message\_type: onbekend berichttype ontvangen in [receiver.py](http://receiver.py). |
| <vat\_rate> | 0, 6, 12, 21 | 0 uitsluitend voor Top-up producten. Opgehaald via [account.tax](http://account.tax) in [poller.py](http://poller.py). |

Team Kassa | XML Structuren v2.3 | Conform XML\_naamgeving standaard | Integratieproject Desideriushogeschool | 2026