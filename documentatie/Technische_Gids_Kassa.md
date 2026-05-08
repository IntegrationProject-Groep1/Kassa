# Technische Gids & Opstartplan

Team Kassa (Odoo POS) | Versie 4.0 - Volledige Harmonistatie v2.3

Integratieproject Desideriushogeschool 2026

| |     |
| --- | --- |
| **Veld** | **Waarde** |
| Project | Integratieproject Desideriushogeschool 2026 |
| Team | POS (Kassa) |
| Document Versie | 4.0 (Mei 2026) |
| Status | Voltooid (Conform Contract v2.3) |
| XML Standaard | Snake Case (Rule 1) & Contract v2.3 |
| Tech stack | Odoo 17, PostgreSQL 15, Python 3.12, RabbitMQ, Docker, GitHub Actions |

## **1\. Het grote plaatje — hoe hangt alles samen?**

Dit project heeft 9 softwaresystemen die allemaal met elkaar communiceren via één centraal systeem: RabbitMQ. Elk systeem staat op zichzelf (loosely coupled) en communiceert enkel via de centrale berichtenwachtrij.

- **Loosely coupled:** elk systeem staat op zichzelf en kent andere systemen NIET rechtstreeks.
- **Communicatie:** enkel via RabbitMQ — een centrale postbus.
- **Actie & Reactie:** systeem X plaatst een bericht in de postbus. Systeem Y leest het en doet zijn ding.

## **1.1 Alle systemen op een rij**

| Systeem | Software | Wat doet het? | Contact met Kassa? |
| --- | --- | --- | --- |
| Frontend | Drupal | Website — inschrijvingen, saldo tonen | Ja — stuurt inschrijvingen / ontvangt betaalstatus |
| Kassa (jullie) | Odoo POS | Betalingen op het event, consumpties bar | — |
| Facturatie | FOSSBilling | Facturen aanmaken en versturen | Nee — verloopt via CRM |
| CRM | Salesforce | Klant- en bedrijfsgegevens bijhouden | Ja — profielen synchroniseren |
| Monitoring | Elastic Stack | Dashboard, uptime bewaken, alerts | Ja — heartbeat / errors sturen |
| IoT | Raspberry Pi | Badge scanner aan inkom en bar | Ja — stuurt badge IDs door |

## **1.2 Hoe een bericht stroomt — concreet voorbeeld**

Stel: een bezoeker rekent zijn consumpties af aan de bar. Dit is wat er gebeurt:

1.  **Kassa:** Medewerker bevestigt betaling in Odoo POS.
2.  **Poller:** `order_poller.py` detecteert het nieuwe order via XML-RPC.
3.  **Sender:** `sender.py` bouwt `consumption_order` + `payment_registered` XML (v2.3).
4.  **RabbitMQ:** Berichten worden gepubliceerd naar `kassa.exchange`.
5.  **CRM:** Salesforce leest de XML, matcht op `identity_uuid` en werkt het profiel bij.

## **2\. RabbitMQ Configuraties**

Kassa verstuurt berichten via `kassa.exchange` (topic exchange).

| Queue | Routing key | Berichten |
| --- | --- | --- |
| `kassa.incoming` | — | `new_registration`, `profile_update`, `badge_scanned` |
| `kassa.payments` | `kassa.payments.consumption` | `consumption_order`, `payment_registered` |
| `kassa.payments` | `kassa.payments.registration` | `payment_registered` (inschrijvingen) |
| `kassa.payments` | `kassa.payments.refund` | `refund_processed` |
| `kassa.payments` | `kassa.payments.badge` | `badge_assigned` |
| `kassa.payments` | `kassa.payments.invoice` | `invoice_request` |
| `frontend.payments` | `kassa.frontend.payment` | `payment_status` |
| `frontend.payments` | `kassa.frontend.wallet` | `wallet_balance_update` |
| `kassa.errors` | `kassa.errors` | `system_error` |

## **3\. Odoo POS Architectuur**

### **3.1 Custom Velden (res.partner)**
- `x_user_id` (Char): Bevat de `identity_uuid` uit het CRM. Cruciaal voor matching over systemen heen.
- `x_badge_id` (Char): De gekoppelde badge ID.
- `x_wallet_balance` (Float): Het huidige saldo op de badge.
- `x_session_title` (Char): De naam van de sessie waarvoor de klant is ingeschreven.

### **3.2 Odoo Addon: kassa_pos_custom**
Breidt de Odoo POS-interface uit om badge-scans te verwerken en real-time saldo-updates te tonen via de `bus.bus` integratie.

## **4\. De Integratie Service (Python)**

### **4.1 Sender Module (`sender.py`)**
Verantwoordelijk voor het bouwen en versturen van XML berichten.
1.  **Header Generation:** Voegt een standaard header toe met `message_id`, `timestamp`, `source`, `type` en `version` (in deze strikte volgorde conform v2.3).
2.  **Validation:** Valideert elke uitgaande XML tegen de XSD's in `schemas/`.
3.  **Resilience:** Indien RabbitMQ onbereikbaar is, worden berichten gebufferd in `outbox/outbox.json`.

### **4.2 Receiver Module (`receiver.py`)**
Luistert op `kassa.incoming` voor berichten van andere teams.
1.  **Validatie:** Elke inkomende XML wordt gevalideerd tegen de lokale XSD.
2.  **Matching:** Klanten worden gezocht in Odoo op basis van de `identity_uuid` (opgeslagen in `x_user_id`).
3.  **Idempotentie:** Onthoudt `message_id`'s om dubbele verwerking te voorkomen.

### **4.3 Poller Module (`order_poller.py`)**
Draait continu om nieuwe verkopen in Odoo te detecteren en door te sturen naar het CRM.

## **5\. Docker Infrastructuur**

Het systeem draait in drie containers:
- `kassa-odoo`: De Odoo 17 webserver.
- `kassa-db`: De PostgreSQL 15 database.
- `kassa-integratie`: De Python service die de koppeling met RabbitMQ verzorgt.

**Belangrijk:** Gebruik altijd volumes voor de database en de integratie-outbox om dataverlies bij herstarts te voorkomen.

---
*Team Kassa | Technische Gids v4.0 | Conform Contract v2.3 | 2026*
