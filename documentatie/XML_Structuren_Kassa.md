**Technische Integratiedocumentatie — XML & XSD**

Team Kassa (Odoo POS) — Versie 2.3 — Geïntegreerd document

Conform XML_naamgeving standaard (snake_case) | Integratieproject Desideriushogeschool 2026

# **1\. Overzicht van alle Flows**

Alle messageType-waarden zijn conform de snake_case naamgevingsstandaard. Flows 11–16 zijn uitbreidingen op de basisflows.

|     |     |     |     |     |     |     |
| --- | --- | --- | --- | --- | --- | --- |
| **#** | **Richting** | **Van** | **Naar** | **Queue** | **type (enum)** | **Bestand** |
| 1   | Inkomend | CRM | Odoo | queue.incoming | new_registration | schema_nieuwe_inschrijving.xsd |
| 2   | Inkomend | IoT | Odoo | queue.incoming | badge_scanned | schema_scan_badge.xsd |
| 3   | Inkomend | CRM | Odoo | queue.incoming | profile_update | schema_profiel_update.xsd |
| 4   | Inkomend | CRM | Odoo | queue.incoming | cancel_registration | schema_cancel_registration.xsd |
| 5A  | Uitgaand | Odoo | CRM | pos.payments | consumption_order | schema_consumption_order_v2.1.xsd |
| 5B  | Uitgaand | Odoo | CRM | pos.payments | payment_registered | schema_payment_registered_v2.1.xsd |
| 6   | Uitgaand | Odoo | Elastic | queue.heartbeats | heartbeat | schema_heartbeat.xsd |
| 7   | Uitgaand | Odoo | Elastic | queue.errors | system_error | schema_error.xsd |
| 8   | Uitgaand | Odoo | Drupal | frontend.payments | payment_status | schema_payment_status.xsd |
| 9   | Uitgaand | Odoo | Drupal | frontend.payments | wallet_balance_update | schema_wallet_balance_update.xsd |
| 10  | Uitgaand | Odoo | CRM | pos.payments | invoice_request | schema_invoice_request.xsd |
| 11  | Uitgaand | Odoo | CRM | pos.payments | consumption_order (is_anonymous=true) | schema_consumption_order_v2.1.xsd |
| 12  | Uitgaand | Odoo | CRM | pos.payments | badge_assigned | schema_badge_assigned.xsd |
| 13  | Uitgaand (2-staps) | Odoo | CRM + Drupal | pos.payments + frontend.payments | consumption_order + wallet_balance_update | zie Flow 5A + Flow 9 |
| 14  | Uitgaand | Odoo | CRM | pos.payments | payment_registered (context=registration) | schema_payment_registered_v2.1.xsd |
| 15  | Uitgaand | Odoo | CRM | pos.payments | refund_processed | schema_refund_processed.xsd |
| 16  | Intern sad path | Odoo | Elastic | queue.errors | system_error (badge_not_found) | schema_error.xsd |

# **2\. Inkomende Flows (Kassa ontvangt)**

|     |
| --- |
| **📥 FLOW 1: Nieuwe Inschrijving**<br><br>CRM (Salesforce) → Odoo (Kassa Team) via queue.incoming |
| **Van:** CRM (Salesforce) |
| **Naar:** Odoo (Kassa Team) |
| **Queue:** queue.incoming |
| **type:** new_registration |
| **Bestand:** schema_nieuwe_inschrijving.xsd |

Voorbeeld XML:

&lt;?xml version="1.0" encoding="UTF-8"?&gt;

&lt;message&gt;

&lt;header&gt;

&lt;message_id&gt;MSG-CRM-1001&lt;/message_id&gt;

&lt;type&gt;new_registration&lt;/type&gt;

&lt;source&gt;crm&lt;/source&gt;

&lt;timestamp&gt;2026-02-24T16:00:00Z&lt;/timestamp&gt;

&lt;version&gt;2.0&lt;/version&gt;

&lt;/header&gt;

&lt;body&gt;

&lt;customer&gt;

&lt;email&gt;info@techbedrijf.be&lt;/email&gt;

&lt;name&gt;Jan Peeters&lt;/name&gt;

&lt;company_name&gt;TechCompany NV&lt;/company_name&gt;

&lt;type&gt;company&lt;/type&gt;

&lt;vat_number&gt;BE0123456789&lt;/vat_number&gt;

&lt;user_id&gt;e8b27c1d-4f2a-4b3e-9c5f-123456789abc&lt;/user_id&gt;

&lt;age&gt;22&lt;/age&gt;

&lt;/customer&gt;

&lt;payment_due&gt;

&lt;amount&gt;50.00&lt;/amount&gt;

&lt;status&gt;unpaid&lt;/status&gt;

&lt;/payment_due&gt;

&lt;/body&gt;

&lt;/message&gt;

XSD Schema:

&lt;?xml version="1.0" encoding="UTF-8"?&gt;

&lt;xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"&gt;

&lt;xs:complexType name="HeaderType"&gt;&lt;xs:sequence&gt;

&lt;xs:element name="message_id" type="xs:string"/&gt;

&lt;xs:element name="type" type="xs:string" fixed="new_registration"/&gt;

&lt;xs:element name="source" type="xs:string"/&gt;

&lt;xs:element name="timestamp" type="xs:dateTime"/&gt;

&lt;xs:element name="version" type="xs:string"/&gt;

&lt;/xs:sequence&gt;&lt;/xs:complexType&gt;

&lt;xs:complexType name="CustomerType"&gt;&lt;xs:sequence&gt;

&lt;xs:element name="email" type="xs:string"/&gt;

&lt;xs:element name="name" type="xs:string"/&gt;

&lt;xs:element name="company_name" type="xs:string" minOccurs="0"/&gt;

&lt;xs:element name="type" type="xs:string"/&gt;

&lt;xs:element name="vat_number" type="xs:string" minOccurs="0"/&gt;

&lt;xs:element name="user_id" type="xs:string"/&gt;

&lt;xs:element name="age" type="xs:integer"/&gt;

&lt;/xs:sequence&gt;&lt;/xs:complexType&gt;

&lt;xs:complexType name="PaymentDueType"&gt;&lt;xs:sequence&gt;

&lt;xs:element name="amount" type="xs:decimal"/&gt;

&lt;xs:element name="status"&gt;&lt;xs:simpleType&gt;&lt;xs:restriction base="xs:string"&gt;

&lt;xs:enumeration value="unpaid"/&gt;&lt;xs:enumeration value="paid"/&gt;

&lt;/xs:restriction&gt;&lt;/xs:simpleType&gt;&lt;/xs:element&gt;

&lt;/xs:sequence&gt;&lt;/xs:complexType&gt;

&lt;xs:element name="message"&gt;&lt;xs:complexType&gt;&lt;xs:sequence&gt;

&lt;xs:element name="header" type="HeaderType"/&gt;

&lt;xs:element name="body"&gt;&lt;xs:complexType&gt;&lt;xs:sequence&gt;

&lt;xs:element name="customer" type="CustomerType"/&gt;

&lt;xs:element name="payment_due" type="PaymentDueType"/&gt;

&lt;/xs:sequence&gt;&lt;/xs:complexType&gt;&lt;/xs:element&gt;

&lt;/xs:sequence&gt;&lt;/xs:complexType&gt;&lt;/xs:element&gt;

&lt;/xs:schema&gt;

|     |
| --- |
| **📥 FLOW 2: Scan Badge**<br><br>IoT (Raspberry Pi) → Odoo (Kassa Team) via queue.incoming |
| **Van:** Raspberry Pi (IoT Team) |
| **Naar:** Odoo (Kassa Team) |
| **Queue:** queue.incoming |
| **type:** badge_scanned |
| **Bestand:** schema_scan_badge.xsd |

Aankopen zonder badge moeten altijd mogelijk zijn (Vraag 7). Het sad path (badge niet herkend) wordt gedocumenteerd in Flow 16.

Voorbeeld XML:

&lt;?xml version="1.0" encoding="UTF-8"?&gt;

&lt;message&gt;

&lt;header&gt;

&lt;message_id&gt;MSG-IOT-5544&lt;/message_id&gt;

&lt;type&gt;badge_scanned&lt;/type&gt;

&lt;source&gt;iot_scanner_bar&lt;/source&gt;

&lt;timestamp&gt;2026-02-24T19:15:00Z&lt;/timestamp&gt;

&lt;version&gt;2.0&lt;/version&gt;

&lt;/header&gt;

&lt;body&gt;

&lt;badge_id&gt;QR-98765-ABC&lt;/badge_id&gt;

&lt;location&gt;hoofdbar&lt;/location&gt;

&lt;/body&gt;

&lt;/message&gt;

XSD Schema:

&lt;?xml version="1.0" encoding="UTF-8"?&gt;

&lt;xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"&gt;

&lt;xs:complexType name="HeaderType"&gt;&lt;xs:sequence&gt;

&lt;xs:element name="message_id" type="xs:string"/&gt;

&lt;xs:element name="type" type="xs:string" fixed="badge_scanned"/&gt;

&lt;xs:element name="source" type="xs:string"/&gt;

&lt;xs:element name="timestamp" type="xs:dateTime"/&gt;

&lt;xs:element name="version" type="xs:string"/&gt;

&lt;/xs:sequence&gt;&lt;/xs:complexType&gt;

&lt;xs:element name="message"&gt;&lt;xs:complexType&gt;&lt;xs:sequence&gt;

&lt;xs:element name="header" type="HeaderType"/&gt;

&lt;xs:element name="body"&gt;&lt;xs:complexType&gt;&lt;xs:sequence&gt;

&lt;xs:element name="badge_id" type="xs:string"/&gt;

&lt;xs:element name="location" type="xs:string"/&gt;

&lt;/xs:sequence&gt;&lt;/xs:complexType&gt;&lt;/xs:element&gt;

&lt;/xs:sequence&gt;&lt;/xs:complexType&gt;&lt;/xs:element&gt;

&lt;/xs:schema&gt;

|     |
| --- |
| **📥 FLOW 3: ProfileUpdate**<br><br>CRM (Salesforce) → Odoo (Kassa Team) via queue.incoming |
| **Van:** Salesforce CRM |
| **Naar:** Odoo (Kassa Team) |
| **Queue:** queue.incoming |
| **type:** profile_update |
| **Bestand:** schema_profiel_update.xsd |

Voorbeeld XML:

&lt;?xml version="1.0" encoding="UTF-8"?&gt;

&lt;message&gt;

&lt;header&gt;

&lt;message_id&gt;MSG-CRM-7788&lt;/message_id&gt;

&lt;type&gt;profile_update&lt;/type&gt;

&lt;source&gt;crm&lt;/source&gt;

&lt;timestamp&gt;2026-02-24T19:15:00Z&lt;/timestamp&gt;

&lt;version&gt;2.0&lt;/version&gt;

&lt;/header&gt;

&lt;body&gt;

&lt;user_id&gt;e8b27c1d-4f2a-4b3e-9c5f-123456789abc&lt;/user_id&gt;

&lt;email&gt;info@techbedrijf.be&lt;/email&gt;

&lt;name&gt;Jan Peeters&lt;/name&gt;

&lt;company_name&gt;TechCompany NV&lt;/company_name&gt;

&lt;age&gt;22&lt;/age&gt;

&lt;type&gt;company&lt;/type&gt;

&lt;vat_number&gt;BE0123456789&lt;/vat_number&gt;

&lt;/body&gt;

&lt;/message&gt;

XSD Schema (schema_profiel_update.xsd):

&lt;?xml version="1.0" encoding="UTF-8"?&gt;

&lt;xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"&gt;

&lt;xs:complexType name="HeaderType"&gt;&lt;xs:sequence&gt;

&lt;xs:element name="message_id" type="xs:string"/&gt;

&lt;xs:element name="type" type="xs:string" fixed="profile_update"/&gt;

&lt;xs:element name="source" type="xs:string"/&gt;

&lt;xs:element name="timestamp" type="xs:dateTime"/&gt;

&lt;xs:element name="version" type="xs:string"/&gt;

&lt;/xs:sequence&gt;&lt;/xs:complexType&gt;

&lt;xs:element name="message"&gt;&lt;xs:complexType&gt;&lt;xs:sequence&gt;

&lt;xs:element name="header" type="HeaderType"/&gt;

&lt;xs:element name="body"&gt;&lt;xs:complexType&gt;&lt;xs:sequence&gt;

&lt;xs:element name="user_id" type="xs:string"/&gt;

&lt;xs:element name="email" type="xs:string"/&gt;

&lt;xs:element name="name" type="xs:string"/&gt;

&lt;xs:element name="type"&gt;&lt;xs:simpleType&gt;&lt;xs:restriction base="xs:string"&gt;

&lt;xs:enumeration value="company"/&gt;&lt;xs:enumeration value="private"/&gt;

&lt;/xs:restriction&gt;&lt;/xs:simpleType&gt;&lt;/xs:element&gt;

&lt;xs:element name="company_name" type="xs:string" minOccurs="0"/&gt;

&lt;xs:element name="vat_number" type="xs:string" minOccurs="0"/&gt;

&lt;xs:element name="age" type="xs:positiveInteger"/&gt;

&lt;/xs:sequence&gt;&lt;/xs:complexType&gt;&lt;/xs:element&gt;

&lt;/xs:sequence&gt;&lt;/xs:complexType&gt;&lt;/xs:element&gt;

&lt;/xs:schema&gt;

|     |
| --- |
| **📥 FLOW 4: CancelRegistration**<br><br>CRM (Salesforce) → Odoo via queue.incoming |
| **Van:** Salesforce CRM |
| **Naar:** Odoo (Kassa Team) |
| **Queue:** queue.incoming |
| **type:** cancel_registration |
| **Bestand:** schema_cancel_registration.xsd |

Voorbeeld XML:

&lt;?xml version="1.0" encoding="UTF-8"?&gt;

&lt;message&gt;

&lt;header&gt;

&lt;message_id&gt;f12e3d4c-5b6a-7d8e-9f0a-1b2c3d4e5f6a&lt;/message_id&gt;

&lt;type&gt;cancel_registration&lt;/type&gt;

&lt;source&gt;crm&lt;/source&gt;

&lt;timestamp&gt;2026-03-04T11:05:00Z&lt;/timestamp&gt;

&lt;version&gt;2.0&lt;/version&gt;

&lt;/header&gt;

&lt;body&gt;

&lt;user_id&gt;e8b27c1d-4f2a-4b3e-9c5f-123456789abc&lt;/user_id&gt;

&lt;session_id&gt;session-uuid-001&lt;/session_id&gt;

&lt;/body&gt;

&lt;/message&gt;

XSD Schema (schema_cancel_registration.xsd):

&lt;?xml version="1.0" encoding="UTF-8"?&gt;

&lt;xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"&gt;

&lt;xs:complexType name="HeaderType"&gt;&lt;xs:sequence&gt;

&lt;xs:element name="message_id" type="xs:string"/&gt;

&lt;xs:element name="type" type="xs:string" fixed="cancel_registration"/&gt;

&lt;xs:element name="source" type="xs:string"/&gt;

&lt;xs:element name="timestamp" type="xs:dateTime"/&gt;

&lt;xs:element name="version" type="xs:string"/&gt;

&lt;/xs:sequence&gt;&lt;/xs:complexType&gt;

&lt;xs:element name="message"&gt;&lt;xs:complexType&gt;&lt;xs:sequence&gt;

&lt;xs:element name="header" type="HeaderType"/&gt;

&lt;xs:element name="body"&gt;&lt;xs:complexType&gt;&lt;xs:sequence&gt;

&lt;xs:element name="user_id" type="xs:string"/&gt;

&lt;xs:element name="session_id" type="xs:string"/&gt;

&lt;/xs:sequence&gt;&lt;/xs:complexType&gt;&lt;/xs:element&gt;

&lt;/xs:sequence&gt;&lt;/xs:complexType&gt;&lt;/xs:element&gt;

&lt;/xs:schema&gt;

# **3\. Uitgaande Flows — Kassa naar CRM**

|     |
| --- |
| **📤 FLOW 5A: Bestelling doorsturen (consumption_order)**<br><br>Odoo (Kassa) → Salesforce (CRM) via pos.payments \| routing key: kassa.payments.consumption |
| **Van:** Odoo (Kassa Team) |
| **Naar:** Salesforce (CRM) |
| **Queue:** pos.payments |
| **Routing key:** kassa.payments.consumption |
| **type:** consumption_order |
| **Bestand:** schema_consumption_order_v2.1.xsd |
| **XSD versie:** v2.1 — dekt ook anonieme aankopen (Flow 11) en top-up producten (Flow 13) |

Voorbeeld XML:

&lt;?xml version="1.0" encoding="UTF-8"?&gt;

&lt;message&gt;

&lt;header&gt;

&lt;message_id&gt;f47ac10b-58cc-4372-a567-0e02b2c3d479&lt;/message_id&gt;

&lt;type&gt;consumption_order&lt;/type&gt;

&lt;source&gt;kassa&lt;/source&gt;

&lt;timestamp&gt;2026-02-24T18:30:00Z&lt;/timestamp&gt;

&lt;version&gt;2.0&lt;/version&gt;

&lt;/header&gt;

&lt;body&gt;

&lt;is_anonymous&gt;false&lt;/is_anonymous&gt;

&lt;customer&gt;

&lt;id&gt;12345&lt;/id&gt;

&lt;user_id&gt;e8b27c1d-4f2a-4b3e-9c5f-123456789abc&lt;/user_id&gt;

&lt;is_company_linked&gt;true&lt;/is_company_linked&gt;

&lt;company_id&gt;e8b27c1d-COMPANY-UUID-example&lt;/company_id&gt;

&lt;email&gt;info@bedrijf.be&lt;/email&gt;

&lt;address&gt;&lt;street&gt;Kiekenmarkt&lt;/street&gt;&lt;number&gt;42&lt;/number&gt;

&lt;postal_code&gt;1000&lt;/postal_code&gt;&lt;city&gt;Brussel&lt;/city&gt;&lt;country&gt;be&lt;/country&gt;&lt;/address&gt;

&lt;/customer&gt;

&lt;items&gt;

&lt;item&gt;

&lt;id&gt;BEV-001&lt;/id&gt;

&lt;description&gt;Koffie&lt;/description&gt;

&lt;quantity&gt;2&lt;/quantity&gt;

&lt;unit_price currency="eur"&gt;2.50&lt;/unit_price&gt;

&lt;vat_rate&gt;6&lt;/vat_rate&gt;

&lt;/item&gt;

&lt;/items&gt;

&lt;/body&gt;

&lt;/message&gt;

XSD Schema (schema_consumption_order_v2.1.xsd):

&lt;?xml version="1.0" encoding="UTF-8"?&gt;

<!-- Wijzigingen t.o.v. v2.0:

\- is_anonymous boolean toegevoegd (default false)

\- &lt;customer&gt; volledig optioneel (minOccurs=0)

\- item_type optioneel veld toegevoegd (wallet_topup voor top-up producten)

\- vat_rate enum hersteld, waarde 0 toegevoegd voor top-up producten -->

&lt;xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"&gt;

&lt;xs:complexType name="HeaderType"&gt;&lt;xs:sequence&gt;

&lt;xs:element name="message_id" type="xs:string"/&gt;

&lt;xs:element name="type" type="xs:string" fixed="consumption_order"/&gt;

&lt;xs:element name="source" type="xs:string"/&gt;

&lt;xs:element name="timestamp" type="xs:dateTime"/&gt;

&lt;xs:element name="version" type="xs:string"/&gt;

&lt;/xs:sequence&gt;&lt;/xs:complexType&gt;

&lt;xs:complexType name="AddressType"&gt;&lt;xs:sequence&gt;

&lt;xs:element name="street" type="xs:string"/&gt;

&lt;xs:element name="number" type="xs:string"/&gt;

&lt;xs:element name="postal_code" type="xs:string"/&gt;

&lt;xs:element name="city" type="xs:string"/&gt;

&lt;xs:element name="country" type="xs:string"/&gt;

&lt;/xs:sequence&gt;&lt;/xs:complexType&gt;

<!-- CustomerType: alle velden optioneel in XSD.

Conditionele validatie (is_anonymous=false -> klantdata verplicht)

afgedwongen in receiver.py, niet door XSD. -->

&lt;xs:complexType name="CustomerType"&gt;&lt;xs:sequence&gt;

&lt;xs:element name="id" type="xs:integer" minOccurs="0"/&gt;

&lt;xs:element name="user_id" type="xs:string" minOccurs="0"/&gt;

&lt;xs:element name="is_company_linked" type="xs:boolean" minOccurs="0"/&gt;

&lt;xs:element name="company_id" type="xs:string" minOccurs="0"/&gt;

&lt;xs:element name="email" type="xs:string" minOccurs="0"/&gt;

&lt;xs:element name="address" type="AddressType" minOccurs="0"/&gt;

&lt;/xs:sequence&gt;&lt;/xs:complexType&gt;

&lt;xs:complexType name="ItemType"&gt;&lt;xs:sequence&gt;

&lt;xs:element name="id" type="xs:string"/&gt;

&lt;xs:element name="description" type="xs:string"/&gt;

&lt;xs:element name="quantity" type="xs:positiveInteger"/&gt;

&lt;xs:element name="unit_price"&gt;

&lt;xs:complexType&gt;&lt;xs:simpleContent&gt;

&lt;xs:extension base="xs:decimal"&gt;

&lt;xs:attribute name="currency" type="xs:string" use="required"/&gt;

&lt;/xs:extension&gt;&lt;/xs:simpleContent&gt;&lt;/xs:complexType&gt;

&lt;/xs:element&gt;

&lt;xs:element name="vat_rate"&gt;&lt;xs:simpleType&gt;&lt;xs:restriction base="xs:integer"&gt;

&lt;xs:enumeration value="0"/&gt; &lt;!-- Top-up producten --&gt;

&lt;xs:enumeration value="6"/&gt;

&lt;xs:enumeration value="12"/&gt;

&lt;xs:enumeration value="21"/&gt;

&lt;/xs:restriction&gt;&lt;/xs:simpleType&gt;&lt;/xs:element&gt;

&lt;!-- item_type optioneel: waarde wallet_topup voor top-up producten --&gt;

&lt;xs:element name="item_type" type="xs:string" minOccurs="0"/&gt;

&lt;/xs:sequence&gt;&lt;/xs:complexType&gt;

&lt;xs:element name="message"&gt;&lt;xs:complexType&gt;&lt;xs:sequence&gt;

&lt;xs:element name="header" type="HeaderType"/&gt;

&lt;xs:element name="body"&gt;&lt;xs:complexType&gt;&lt;xs:sequence&gt;

&lt;xs:element name="is_anonymous" type="xs:boolean" minOccurs="0" default="false"/&gt;

&lt;xs:element name="customer" type="CustomerType" minOccurs="0"/&gt;

&lt;xs:element name="items"&gt;&lt;xs:complexType&gt;&lt;xs:sequence&gt;

&lt;xs:element name="item" type="ItemType" maxOccurs="unbounded"/&gt;

&lt;/xs:sequence&gt;&lt;/xs:complexType&gt;&lt;/xs:element&gt;

&lt;/xs:sequence&gt;&lt;/xs:complexType&gt;&lt;/xs:element&gt;

&lt;/xs:sequence&gt;&lt;/xs:complexType&gt;&lt;/xs:element&gt;

&lt;/xs:schema&gt;

|     |
| --- |
| **📤 FLOW 5B: Betaling registreren (payment_registered — context: consumption)**<br><br>Odoo (Kassa) → Salesforce (CRM) via pos.payments \| routing key: kassa.payments.consumption |
| **Van:** Odoo (Kassa Team) |
| **Naar:** Salesforce (CRM) |
| **Queue:** pos.payments |
| **Routing key:** kassa.payments.consumption |
| **type:** payment_registered |
| **payment_context:** consumption |
| **Bestand:** schema_payment_registered_v2.1.xsd |
| **correlation_id:** message_id van de bijhorende consumption_order |

Voorbeeld XML:

&lt;?xml version="1.0" encoding="UTF-8"?&gt;

&lt;message&gt;

&lt;header&gt;

&lt;message_id&gt;a23bc45d-89ef-1234-b567-1f03c3d4e580&lt;/message_id&gt;

&lt;type&gt;payment_registered&lt;/type&gt;

&lt;source&gt;kassa&lt;/source&gt;

&lt;timestamp&gt;2026-02-24T18:35:00Z&lt;/timestamp&gt;

&lt;version&gt;2.0&lt;/version&gt;

&lt;correlation_id&gt;f47ac10b-58cc-4372-a567-0e02b2c3d479&lt;/correlation_id&gt;

&lt;/header&gt;

&lt;body&gt;

&lt;payment_context&gt;consumption&lt;/payment_context&gt;

&lt;invoice&gt;

&lt;id&gt;INV-2026-001&lt;/id&gt;

&lt;status&gt;paid&lt;/status&gt;

&lt;amount_paid currency="eur"&gt;15.00&lt;/amount_paid&gt;

&lt;due_date&gt;2026-02-24&lt;/due_date&gt;

&lt;/invoice&gt;

&lt;transaction&gt;

&lt;id&gt;TRX-987654&lt;/id&gt;

&lt;payment_method&gt;company_link&lt;/payment_method&gt;

&lt;/transaction&gt;

&lt;/body&gt;

&lt;/message&gt;

XSD Schema: schema_payment_registered_v2.1.xsd (zie ook Flow 14 — zelfde schema).

&lt;?xml version="1.0" encoding="UTF-8"?&gt;

<!-- Wijzigingen t.o.v. v2.0:

\- payment_context toegevoegd (registration | consumption) - verplicht

\- &lt;invoice&gt;&lt;id&gt; optioneel (minOccurs=0): afwezig bij registration

\- &lt;user_id&gt; op body-niveau optioneel: aanwezig bij registration

\- payment_method enum conform PM-standaard: company_link, on_site, online

\- due_date: datum van de aankoop zelf (order date_order) bij consumption -->

&lt;xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"&gt;

&lt;xs:complexType name="HeaderType"&gt;&lt;xs:sequence&gt;

&lt;xs:element name="message_id" type="xs:string"/&gt;

&lt;xs:element name="type" type="xs:string" fixed="payment_registered"/&gt;

&lt;xs:element name="source" type="xs:string"/&gt;

&lt;xs:element name="timestamp" type="xs:dateTime"/&gt;

&lt;xs:element name="version" type="xs:string"/&gt;

&lt;xs:element name="correlation_id" type="xs:string" minOccurs="0"/&gt;

&lt;/xs:sequence&gt;&lt;/xs:complexType&gt;

&lt;xs:complexType name="CurrencyAmountType"&gt;&lt;xs:simpleContent&gt;

&lt;xs:extension base="xs:decimal"&gt;

&lt;xs:attribute name="currency" type="xs:string" use="required"/&gt;

&lt;/xs:extension&gt;&lt;/xs:simpleContent&gt;&lt;/xs:complexType&gt;

&lt;xs:element name="message"&gt;&lt;xs:complexType&gt;&lt;xs:sequence&gt;

&lt;xs:element name="header" type="HeaderType"/&gt;

&lt;xs:element name="body"&gt;&lt;xs:complexType&gt;&lt;xs:sequence&gt;

&lt;xs:element name="payment_context"&gt;&lt;xs:simpleType&gt;

&lt;xs:restriction base="xs:string"&gt;

&lt;xs:enumeration value="registration"/&gt;

&lt;xs:enumeration value="consumption"/&gt;

&lt;/xs:restriction&gt;&lt;/xs:simpleType&gt;&lt;/xs:element&gt;

&lt;xs:element name="user_id" type="xs:string" minOccurs="0"/&gt;

&lt;xs:element name="invoice"&gt;&lt;xs:complexType&gt;&lt;xs:sequence&gt;

&lt;xs:element name="id" type="xs:string" minOccurs="0"/&gt;

&lt;xs:element name="status"&gt;&lt;xs:simpleType&gt;&lt;xs:restriction base="xs:string"&gt;

&lt;xs:enumeration value="paid"/&gt;

&lt;xs:enumeration value="pending"/&gt;

&lt;xs:enumeration value="cancelled"/&gt;

&lt;/xs:restriction&gt;&lt;/xs:simpleType&gt;&lt;/xs:element&gt;

&lt;xs:element name="amount_paid" type="CurrencyAmountType"/&gt;

&lt;xs:element name="due_date" type="xs:date"/&gt;

&lt;/xs:sequence&gt;&lt;/xs:complexType&gt;&lt;/xs:element&gt;

&lt;xs:element name="transaction"&gt;&lt;xs:complexType&gt;&lt;xs:sequence&gt;

&lt;xs:element name="id" type="xs:string"/&gt;

&lt;xs:element name="payment_method"&gt;&lt;xs:simpleType&gt;

&lt;xs:restriction base="xs:string"&gt;

&lt;xs:enumeration value="company_link"/&gt;

&lt;xs:enumeration value="on_site"/&gt;

&lt;xs:enumeration value="online"/&gt;

&lt;/xs:restriction&gt;&lt;/xs:simpleType&gt;&lt;/xs:element&gt;

&lt;/xs:sequence&gt;&lt;/xs:complexType&gt;&lt;/xs:element&gt;

&lt;/xs:sequence&gt;&lt;/xs:complexType&gt;&lt;/xs:element&gt;

&lt;/xs:sequence&gt;&lt;/xs:complexType&gt;&lt;/xs:element&gt;

&lt;/xs:schema&gt;

# **4\. Uitgaande Flows — Kassa naar Elastic (Monitoring)**

|     |
| --- |
| **💓 FLOW 6: Heartbeat**<br><br>Odoo (Kassa) → Elastic Stack via queue.heartbeats (direct, geen exchange) |
| **Van:** Odoo (Kassa Team) |
| **Naar:** Elastic Stack (Monitoring) |
| **Queue:** queue.heartbeats |
| **Routing:** Direct — geen exchange |
| **type:** heartbeat |
| **Bestand:** schema_heartbeat.xsd |
| **Frequentie:** 1 bericht per seconde |

Zie Heartbeat_Kassa.docx voor de volledige implementatie inclusief degraded state logica.

Voorbeeld XML:

&lt;?xml version="1.0" encoding="UTF-8"?&gt;

&lt;message&gt;

&lt;header&gt;

&lt;message_id&gt;a1b2c3d4-e5f6-7890-abcd-ef1234567890&lt;/message_id&gt;

&lt;type&gt;heartbeat&lt;/type&gt;

&lt;source&gt;kassa&lt;/source&gt;

&lt;timestamp&gt;2026-04-15T14:32:01Z&lt;/timestamp&gt;

&lt;version&gt;2.0&lt;/version&gt;

&lt;/header&gt;

&lt;body&gt;

&lt;status&gt;online&lt;/status&gt;

&lt;/body&gt;

&lt;/message&gt;

|     |
| --- |
| **🚨 FLOW 7: Error Log (Sad Path)**<br><br>Odoo (Kassa) → Elastic Stack via queue.errors \| routing key: kassa.errors |
| **Van:** Odoo (Kassa Team) |
| **Naar:** Elastic Stack / Admins |
| **Queue:** queue.errors |
| **Routing key:** kassa.errors |
| **type:** system_error |
| **Bestand:** schema_error.xsd |

Voorbeeld XML:

&lt;?xml version="1.0" encoding="UTF-8"?&gt;

&lt;message&gt;

&lt;header&gt;

&lt;message_id&gt;c9d2e415-5f6a-4b7c-8e1d-2a3b4c5d6e7f&lt;/message_id&gt;

&lt;type&gt;system_error&lt;/type&gt;

&lt;source&gt;kassa&lt;/source&gt;

&lt;timestamp&gt;2026-02-24T19:25:00Z&lt;/timestamp&gt;

&lt;version&gt;2.0&lt;/version&gt;

&lt;/header&gt;

&lt;body&gt;

&lt;error_code&gt;invalid_xml_format&lt;/error_code&gt;

&lt;error_description&gt;Message does not comply with schema_nieuwe_inschrijving.xsd&lt;/error_description&gt;

&lt;related_message_id&gt;MSG-CRM-1001&lt;/related_message_id&gt;

&lt;/body&gt;

&lt;/message&gt;

# **5\. Uitgaande Flows — Kassa naar Drupal (Frontend)**

|     |
| --- |
| **📤 FLOW 8: PaymentStatus**<br><br>Odoo (Kassa) → Drupal (Frontend) via frontend.payments \| routing key: kassa.frontend.payment |
| **Van:** Odoo (Kassa Team) |
| **Naar:** Drupal (Frontend) |
| **Queue:** frontend.payments |
| **Routing key:** kassa.frontend.payment |
| **type:** payment_status |
| **Trigger:** Uitsluitend bij payment_context=registration (inschrijvingsgeld betaald aan kassa) |
| **Bestand:** schema_payment_status.xsd |

Voorbeeld XML:

&lt;?xml version="1.0" encoding="UTF-8"?&gt;

&lt;message&gt;

&lt;header&gt;

&lt;message_id&gt;d98a7c65-4b5e-4c6f-8d9e-1a2b3c4d5e6f&lt;/message_id&gt;

&lt;type&gt;payment_status&lt;/type&gt;

&lt;source&gt;kassa&lt;/source&gt;

&lt;timestamp&gt;2026-03-04T10:15:30Z&lt;/timestamp&gt;

&lt;version&gt;2.0&lt;/version&gt;

&lt;/header&gt;

&lt;body&gt;

&lt;user_id&gt;e8b27c1d-4f2a-4b3e-9c5f-123456789abc&lt;/user_id&gt;

&lt;payment_status&gt;paid&lt;/payment_status&gt;

&lt;/body&gt;

&lt;/message&gt;

|     |
| --- |
| **📤 FLOW 9: Wallet Balance Update**<br><br>Odoo (Kassa) → Drupal (Frontend) via frontend.payments \| routing key: kassa.frontend.wallet |
| **Van:** Odoo (Kassa Team) |
| **Naar:** Drupal (Frontend) |
| **Queue:** frontend.payments |
| **Routing key:** kassa.frontend.wallet |
| **type:** wallet_balance_update |
| **Bestand:** schema_wallet_balance_update.xsd |
| **Triggers:** Na badge-aankoop (Badge Wallet betaling), na top-up (Flow 13), na terugbetaling via badge_wallet (Flow 15) |

Voorbeeld XML:

&lt;?xml version="1.0" encoding="UTF-8"?&gt;

&lt;message&gt;

&lt;header&gt;

&lt;message_id&gt;e54a8b72-1c2d-3e4f-5678-7a8b9c0d1e2f&lt;/message_id&gt;

&lt;type&gt;wallet_balance_update&lt;/type&gt;

&lt;source&gt;kassa&lt;/source&gt;

&lt;timestamp&gt;2026-03-06T20:30:00Z&lt;/timestamp&gt;

&lt;version&gt;2.0&lt;/version&gt;

&lt;/header&gt;

&lt;body&gt;

&lt;user_id&gt;e8b27c1d-4f2a-4b3e-9c5f-123456789abc&lt;/user_id&gt;

&lt;wallet_balance&gt;15.50&lt;/wallet_balance&gt;

&lt;/body&gt;

&lt;/message&gt;

# **6\. Overige Uitgaande Flows**

|     |
| --- |
| **📤 FLOW 10: Factuuraanvraag (invoice_request)**<br><br>Odoo (Kassa) → Salesforce (CRM) via pos.payments \| routing key: kassa.payments.invoice |
| **Van:** Odoo (Kassa Team) |
| **Naar:** Salesforce (CRM) |
| **Queue:** pos.payments |
| **Routing key:** kassa.payments.invoice |
| **type:** invoice_request |
| **Bestand:** schema_invoice_request.xsd |

Voorbeeld XML:

&lt;?xml version="1.0" encoding="UTF-8"?&gt;

&lt;message&gt;

&lt;header&gt;

&lt;message_id&gt;b12c3d4e-5f6a-7890-bcde-f01234567890&lt;/message_id&gt;

&lt;type&gt;invoice_request&lt;/type&gt;

&lt;source&gt;kassa&lt;/source&gt;

&lt;timestamp&gt;2026-02-24T20:00:00Z&lt;/timestamp&gt;

&lt;version&gt;2.0&lt;/version&gt;

&lt;correlation_id&gt;f47ac10b-58cc-4372-a567-0e02b2c3d479&lt;/correlation_id&gt;

&lt;/header&gt;

&lt;body&gt;

&lt;user_id&gt;e8b27c1d-4f2a-4b3e-9c5f-123456789abc&lt;/user_id&gt;

&lt;invoice_data&gt;

&lt;name&gt;Jan Peeters&lt;/name&gt;

&lt;email&gt;jan@peeters.be&lt;/email&gt;

&lt;address&gt;

&lt;street&gt;Kiekenmarkt&lt;/street&gt;

&lt;number&gt;42&lt;/number&gt;

&lt;postal_code&gt;1000&lt;/postal_code&gt;

&lt;city&gt;Brussel&lt;/city&gt;

&lt;country&gt;be&lt;/country&gt;

&lt;/address&gt;

&lt;vat_number&gt;BE0123456789&lt;/vat_number&gt;

&lt;/invoice_data&gt;

&lt;/body&gt;

&lt;/message&gt;

# **7\. Uitgebreide Flows**

|     |
| --- |
| **📤 FLOW 11: Anonieme Aankoop**<br><br>Odoo (Kassa) → Salesforce (CRM) via pos.payments \| routing key: kassa.payments.consumption |
| **Van:** Odoo (Kassa Team) |
| **Naar:** Salesforce (CRM) |
| **Queue:** pos.payments |
| **Routing key:** kassa.payments.consumption |
| **type:** consumption_order |
| **is_anonymous:** true |
| **Bestand:** schema_consumption_order_v2.1.xsd — zelfde XSD als Flow 5A |

Een bezoeker koopt iets aan de kassa zonder badge en zonder account. De &lt;customer&gt;-sectie wordt volledig weggelaten. De XSD (v2.1) valideert dit correct via minOccurs=0 op het &lt;customer&gt; element.

Voorbeeld XML:

&lt;?xml version="1.0" encoding="UTF-8"?&gt;

&lt;message&gt;

&lt;header&gt;

&lt;message_id&gt;f11a0000-0000-0000-0000-000000000001&lt;/message_id&gt;

&lt;type&gt;consumption_order&lt;/type&gt;

&lt;source&gt;kassa&lt;/source&gt;

&lt;timestamp&gt;2026-04-15T15:00:00Z&lt;/timestamp&gt;

&lt;version&gt;2.0&lt;/version&gt;

&lt;/header&gt;

&lt;body&gt;

&lt;is_anonymous&gt;true&lt;/is_anonymous&gt;

&lt;items&gt;

&lt;item&gt;

&lt;id&gt;BEV-002&lt;/id&gt;

&lt;description&gt;Cola&lt;/description&gt;

&lt;quantity&gt;1&lt;/quantity&gt;

&lt;unit_price currency="eur"&gt;2.00&lt;/unit_price&gt;

&lt;vat_rate&gt;6&lt;/vat_rate&gt;

&lt;/item&gt;

&lt;/items&gt;

&lt;/body&gt;

&lt;/message&gt;

Sad path: Als is_anonymous=false maar &lt;customer&gt; ontbreekt, faalt XSD-validatie en gaat het bericht naar de DLQ. Na een anonieme aankoop is achteraf geen factuur meer mogelijk — de klant krijgt enkel een kassaticket.

|     |
| --- |
| **📤 FLOW 12: Badge Koppeling aan Account (badge_assigned)**<br><br>Odoo (Kassa) → Salesforce (CRM) via pos.payments \| routing key: kassa.payments.badge |
| **Van:** Odoo (Kassa Team) |
| **Naar:** Salesforce (CRM) |
| **Queue:** pos.payments |
| **Routing key:** kassa.payments.badge |
| **type:** badge_assigned |
| **Bestand:** schema_badge_assigned.xsd |
| **PM-goedkeuring:** Formeel goedgekeurd (Vraag 37) |
| **Trigger:** Kassamedewerker koppelt badge aan bezoeker bij inschrijvingsbalie |

Voorbeeld XML:

&lt;?xml version="1.0" encoding="UTF-8"?&gt;

&lt;message&gt;

&lt;header&gt;

&lt;message_id&gt;f12b0000-0000-0000-0000-000000000002&lt;/message_id&gt;

&lt;type&gt;badge_assigned&lt;/type&gt;

&lt;source&gt;kassa&lt;/source&gt;

&lt;timestamp&gt;2026-04-15T09:05:00Z&lt;/timestamp&gt;

&lt;version&gt;2.0&lt;/version&gt;

&lt;/header&gt;

&lt;body&gt;

&lt;badge_id&gt;BADGE-RF-00142&lt;/badge_id&gt;

&lt;user_id&gt;e8b27c1d-4f2a-4b3e-9c5f-123456789abc&lt;/user_id&gt;

&lt;assigned_at&gt;2026-04-15T09:05:00Z&lt;/assigned_at&gt;

&lt;/body&gt;

&lt;/message&gt;

|     |
| --- |
| **📤 FLOW 13: Badge Saldo Opladen (Top-up Product)**<br><br>Odoo (Kassa) → CRM + Drupal via pos.payments + frontend.payments |
| **Mechanisme:** Top-up = gewoon Odoo-product. Geen apart berichttype — gebruikt consumption_order + wallet_balance_update. |
| **Stap 1 — type:** consumption_order (Flow 5A) — items bevat het Top-up product met item_type=wallet_topup |
| **Stap 1 — Queue:** pos.payments → Salesforce CRM \| routing key: kassa.payments.consumption |
| **Stap 2 — type:** wallet_balance_update (Flow 9) |
| **Stap 2 — Queue:** frontend.payments → Drupal \| routing key: kassa.frontend.wallet |
| **vat_rate:** 0 (saldo-opwaardering is geen belaste dienst) |
| **Bestand:** schema_consumption_order_v2.1.xsd + schema_wallet_balance_update.xsd |

Voorbeeld XML — Top-up via consumption_order:

&lt;?xml version="1.0" encoding="UTF-8"?&gt;

&lt;message&gt;

&lt;header&gt;

&lt;message_id&gt;f13c0000-0000-0000-0000-000000000099&lt;/message_id&gt;

&lt;type&gt;consumption_order&lt;/type&gt;

&lt;source&gt;kassa&lt;/source&gt;

&lt;timestamp&gt;2026-04-15T11:30:00Z&lt;/timestamp&gt;

&lt;version&gt;2.0&lt;/version&gt;

&lt;/header&gt;

&lt;body&gt;

&lt;is_anonymous&gt;false&lt;/is_anonymous&gt;

&lt;customer&gt;

&lt;id&gt;12345&lt;/id&gt;

&lt;user_id&gt;e8b27c1d-4f2a-4b3e-9c5f-123456789abc&lt;/user_id&gt;

&lt;is_company_linked&gt;false&lt;/is_company_linked&gt;

&lt;email&gt;jan@peeters.be&lt;/email&gt;

&lt;/customer&gt;

&lt;items&gt;

&lt;item&gt;

&lt;id&gt;TOPUP-010&lt;/id&gt;

&lt;description&gt;Top-up EUR 10&lt;/description&gt;

&lt;quantity&gt;1&lt;/quantity&gt;

&lt;unit_price currency="eur"&gt;10.00&lt;/unit_price&gt;

&lt;vat_rate&gt;0&lt;/vat_rate&gt;

&lt;item_type&gt;wallet_topup&lt;/item_type&gt;

&lt;/item&gt;

&lt;/items&gt;

&lt;/body&gt;

&lt;/message&gt;

Stap 2 — wallet_balance_update naar Drupal: zie Flow 9 XML-voorbeeld. Stuurt het nieuwe saldo na de top-up.

|     |
| --- |
| **📤 FLOW 14: Inschrijvingsvergoeding Betaald aan Kassa**<br><br>Odoo (Kassa) → Salesforce (CRM) via pos.payments \| routing key: kassa.payments.registration |
| **Van:** Odoo (Kassa Team) |
| **Naar:** Salesforce (CRM) |
| **Queue:** pos.payments |
| **Routing key:** kassa.payments.registration |
| **type:** payment_registered |
| **payment_context:** registration |
| **correlation_id:** message_id van de originele new_registration (Flow 1) |
| **Bestand:** schema_payment_registered_v2.1.xsd — zelfde XSD als Flow 5B |
| **Verschil met Flow 5B:** &lt;invoice&gt;&lt;id&gt; AFWEZIG (CRM maakt factuur aan). &lt;user_id&gt; AANWEZIG op body-niveau. |

Voorbeeld XML:

&lt;?xml version="1.0" encoding="UTF-8"?&gt;

&lt;message&gt;

&lt;header&gt;

&lt;message_id&gt;f14d0000-0000-0000-0000-000000000004&lt;/message_id&gt;

&lt;type&gt;payment_registered&lt;/type&gt;

&lt;source&gt;kassa&lt;/source&gt;

&lt;timestamp&gt;2026-04-15T09:15:00Z&lt;/timestamp&gt;

&lt;version&gt;2.0&lt;/version&gt;

&lt;correlation_id&gt;MSG-CRM-1001&lt;/correlation_id&gt;

&lt;/header&gt;

&lt;body&gt;

&lt;payment_context&gt;registration&lt;/payment_context&gt;

&lt;user_id&gt;e8b27c1d-4f2a-4b3e-9c5f-123456789abc&lt;/user_id&gt;

&lt;invoice&gt;

&lt;!-- id weggelaten: factuur bestaat nog niet, CRM maakt die aan --&gt;

&lt;status&gt;paid&lt;/status&gt;

&lt;amount_paid currency="eur"&gt;50.00&lt;/amount_paid&gt;

&lt;due_date&gt;2026-04-15&lt;/due_date&gt;

&lt;/invoice&gt;

&lt;transaction&gt;

&lt;id&gt;TRX-2026-04150001&lt;/id&gt;

&lt;payment_method&gt;on_site&lt;/payment_method&gt;

&lt;/transaction&gt;

&lt;/body&gt;

&lt;/message&gt;

Sad path: Als het CRM de inschrijving niet als betaald kan markeren (CRM down, user_id niet gevonden), stuurt de kassa een system_error naar queue.errors met error_code=profile_not_found en de correlation_id van de originele new_registration.

|     |
| --- |
| **💶 FLOW 15: Terugbetaling (refund_processed)**<br><br>Odoo (Kassa) → Salesforce (CRM) via pos.payments \| routing key: kassa.payments.refund |
| **Van:** Odoo (Kassa Team) |
| **Naar:** Salesforce (CRM) |
| **Queue:** pos.payments |
| **Routing key:** kassa.payments.refund |
| **type:** refund_processed |
| **PM-goedkeuring:** Opgenomen als goedgekeurd |
| **correlation_id:** message_id van de originele payment_registered die terugbetaald wordt |
| **Bestand:** schema_refund_processed.xsd |
| **Trigger:** Kassamedewerker initieert correctie: dubbele aanrekening, kassafout, onmiddellijke klacht. |
| **Scope:** Enkel kassacorrecties. Planningswijzigingen zijn verantwoordelijkheid van CRM/Facturatie. |

Voorbeeld XML:

&lt;?xml version="1.0" encoding="UTF-8"?&gt;

&lt;message&gt;

&lt;header&gt;

&lt;message_id&gt;f15e0000-0000-0000-0000-000000000005&lt;/message_id&gt;

&lt;type&gt;refund_processed&lt;/type&gt;

&lt;source&gt;kassa&lt;/source&gt;

&lt;timestamp&gt;2026-04-15T16:45:00Z&lt;/timestamp&gt;

&lt;version&gt;2.0&lt;/version&gt;

&lt;correlation_id&gt;f14d0000-0000-0000-0000-000000000004&lt;/correlation_id&gt;

&lt;/header&gt;

&lt;body&gt;

&lt;refund_type&gt;consumption_item&lt;/refund_type&gt;

&lt;user_id&gt;e8b27c1d-4f2a-4b3e-9c5f-123456789abc&lt;/user_id&gt;

&lt;refund&gt;

&lt;amount currency="eur"&gt;5.00&lt;/amount&gt;

&lt;method&gt;badge_wallet&lt;/method&gt;

&lt;reason&gt;duplicate_payment&lt;/reason&gt;

&lt;description&gt;Dubbele aanrekening gecorrigeerd door kassamedewerker&lt;/description&gt;

&lt;/refund&gt;

&lt;original_transaction_id&gt;TRX-2026-04150001&lt;/original_transaction_id&gt;

&lt;new_wallet_balance currency="eur"&gt;20.50&lt;/new_wallet_balance&gt;

&lt;/body&gt;

&lt;/message&gt;

Als method=badge_wallet: stuur daarna ook wallet_balance_update naar Drupal (Flow 9). Anonieme terugbetaling: badge_wallet niet mogelijk. Gebruik cash of card_reversal, stuur refund_processed zonder &lt;user_id&gt;. CRM down: buffer het bericht conform Vraag 17.

|     |
| --- |
| **🔍 FLOW 16: Badge Scan Sad Path (badge_not_found)**<br><br>Intern Odoo gedrag → system_error naar queue.errors \| routing key: kassa.errors |
| **Type:** Intern sad path — geen apart inkomend/uitgaand berichttype |
| **Trigger:** Badge gescand (Flow 2) maar badge_id niet gevonden in lokale Odoo-cache |
| **Respons:** system_error naar queue.errors met error_code=badge_not_found |
| **ACK strategie:** ACK (niet NACK) — een onbekende badge blijft onbekend totdat Flow 12 uitgevoerd wordt |

Voorbeeld system_error bij badge niet gevonden:

&lt;?xml version="1.0" encoding="UTF-8"?&gt;

&lt;message&gt;

&lt;header&gt;

&lt;message_id&gt;f16f0000-0000-0000-0000-000000000006&lt;/message_id&gt;

&lt;type&gt;system_error&lt;/type&gt;

&lt;source&gt;kassa&lt;/source&gt;

&lt;timestamp&gt;2026-04-15T14:55:00Z&lt;/timestamp&gt;

&lt;version&gt;2.0&lt;/version&gt;

&lt;/header&gt;

&lt;body&gt;

&lt;error_code&gt;badge_not_found&lt;/error_code&gt;

&lt;error_description&gt;Badge BADGE-RF-99999 niet gevonden in lokale Odoo-cache.&lt;/error_description&gt;

&lt;related_message_id&gt;MSG-IOT-5523&lt;/related_message_id&gt;

&lt;/body&gt;

&lt;/message&gt;

Operationele paden na badge_not_found:

|     |     |
| --- | --- |
| **Beslissing kassamedewerker** | **Actie** |
| Pad A — Anoniem | Kassamedewerker klikt 'Anoniem verder'. Kassa gaat door als Flow 11. Geen factuur mogelijk achteraf. |
| Pad B — Wachten | Klant wil badge_wallet of factuur. Medewerker stuurt klant naar inschrijvingsbalie. Badge wordt opnieuw gekoppeld via Flow 12. Volgende scan slaagt. |
| Pad C — Noodkoppeling | Medewerker zoekt klant op naam/e-mail in Odoo en voert Flow 12 handmatig uit ter plekke. ~2 minuten tijdsinvestering. |
| Monitoring | queue.errors ontvangt system_error met code badge_not_found. Als dezelfde badge_id >3x mislukt binnen 5 minuten triggert Controlroom een alert. |

Waarom ACK en geen NACK bij badge_not_found? Een NACK met requeue=True stuurt het bericht opnieuw aan de queue. Maar een badge die nu onbekend is, blijft dat tot Flow 12 uitgevoerd wordt. Onbeperkt retry-en verstopt de queue en produceert een stortvloed aan identieke errors in Elastic. De juiste strategie: ACK + system_error + operationele afhandeling.

# **8\. Enum Waarden — Volledige Referentie**

Gebruik uitsluitend de onderstaande waarden. Conform XML_naamgeving §4.

|     |     |     |
| --- | --- | --- |
| **Element** | **Toegestane waarden** | **Toelichting** |
| &lt;header&gt;&lt;type&gt; | new_registration, badge_scanned, consumption_order, payment_registered, system_error, profile_update, payment_status, cancel_registration, wallet_balance_update, invoice_request, heartbeat, badge_assigned, refund_processed | PM-goedgekeurd (Vraag 37) |
| &lt;body&gt;&lt;status&gt; (heartbeat) | online, degraded, offline | Operationele status kassa |
| &lt;invoice&gt;&lt;status&gt; | paid, pending, cancelled | Status van de factuur |
| &lt;transaction&gt;&lt;payment_method&gt; | company_link, on_site, online | PM-standaard §4. on_site dekt cash, kaart en badge wallet. Geen andere waarden. |
| &lt;payment_context&gt; | registration, consumption | Verplicht veld in payment_registered. Bepaalt ook routing key. |
| &lt;customer&gt;&lt;type&gt; | company, private | Bepaalt of bedrijfsvelden verplicht zijn |
| &lt;payment_due&gt;&lt;status&gt; | unpaid, paid | Inschrijvingsstatus in new_registration |
| &lt;payment_status&gt; | paid, pending | Doorgestuurd naar Drupal — enkel bij payment_context=registration |
| &lt;refund&gt;&lt;method&gt; | badge_wallet, cash, card_reversal | Terugbetalingsmethode |
| &lt;refund&gt;&lt;reason&gt; | duplicate_payment, customer_request, system_error | Gestandaardiseerde reden |
| &lt;refund_type&gt; | consumption_item, partial | Scope van de terugbetaling |
| &lt;error_code&gt; | invalid_xml_format, unknown_message_type, profile_not_found, odoo_api_error, rabbitmq_connection_error, offline_queue_full, badge_not_found | Altijd lowercase. unknown_message_type: onbekend berichttype ontvangen in receiver.py. |
| &lt;vat_rate&gt; | 0, 6, 12, 21 | 0 uitsluitend voor Top-up producten. Opgehaald via account.tax in poller.py. |

Team Kassa | XML Structuren v2.3 | Conform XML_naamgeving standaard | Integratieproject Desideriushogeschool | 2026