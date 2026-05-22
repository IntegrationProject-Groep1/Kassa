# Technische Gids & Opstartplan

Team Kassa (Odoo POS) | Versie 5.0 - Volledige Harmonistatie v2.3

Integratieproject Desideriushogeschool 2026

| |     |
| --- | --- |
| **Veld** | **Waarde** |
| Project | Integratieproject Desideriushogeschool 2026 |
| Team | POS (Kassa) |
| Document Versie | 5.0 (Mei 2026) |
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
| Frontend | Drupal | Website — inschrijvingen, saldo tonen | Ja — stuurt sessie-events / ontvangt betaalstatus |
| Kassa (jullie) | Odoo POS | Betalingen op het event, consumpties bar | — |
| Facturatie | FOSSBilling | Facturen aanmaken en versturen | Nee — verloopt via CRM |
| CRM | Salesforce | Klant- en bedrijfsgegevens bijhouden | Ja — profielen synchroniseren, wallet lease |
| Planning | — | Sessieprogramma beheren | Ja — stuurt sessiecatalogus op aanvraag |
| Monitoring | Elastic Stack | Dashboard, uptime bewaken, alerts | Ja — heartbeat / errors sturen |
| IoT | Raspberry Pi | Badge scanner aan inkom en bar | Ja — stuurt badge IDs door |
| Identity | — | Centrale gebruikersidentiteit (master_uuid) | Ja — UUID's aanmaken en opzoeken |

## **1.2 Hoe een bericht stroomt — concreet voorbeeld**

Stel: een bezoeker rekent zijn consumpties af aan de bar. Dit is wat er gebeurt:

1.  **Kassa:** Medewerker bevestigt betaling in Odoo POS.
2.  **Poller:** `order_poller.py` detecteert het nieuwe order via XML-RPC.
3.  **Sender:** `sender.py` bouwt `consumption_order` + `payment_registered` XML (v2.3).
4.  **RabbitMQ:** Berichten worden gepubliceerd naar `kassa.exchange`.
5.  **CRM:** Salesforce leest de XML, matcht op `identity_uuid` en werkt het profiel bij.

## **2\. RabbitMQ Configuraties**

Kassa verstuurt berichten via `kassa.exchange` (topic exchange).

### Uitgaande berichten (Kassa publiceert)

| Queue | Routing key | Berichten |
| --- | --- | --- |
| `kassa.incoming` | — | `new_registration`, `profile_update`, `badge_scanned` (ontvangst) |
| `kassa.payments` | `kassa.payments.consumption` | `consumption_order`, `payment_registered` (consumptie) |
| `kassa.payments` | `kassa.payments.registration` | `payment_registered` (inschrijvingen) |
| `kassa.payments` | `kassa.payments.refund` | `refund_processed` |
| `kassa.payments` | `kassa.payments.badge` | `badge_assigned` |
| `kassa.payments` | `kassa.payments.invoice` | `invoice_request` |
| `frontend.payments` | `kassa.frontend.payment` | `payment_status` |
| `frontend.payments` | `kassa.frontend.wallet` | `wallet_balance_update` |
| `kassa.errors` | `kassa.errors` | `system_error` |
| Frontend queue | `kassa.to.frontend.user_sessions_request` | `user_sessions_request` (sessies opvragen per bezoeker) |
| CRM queue | `kassa.wallet.lease.request` | `wallet_lease_request` (balance authority aanvragen) |
| CRM queue | `kassa.wallet.lease.return` | `wallet_lease_return` (balance authority teruggeven) |

### Inkomende berichten (Kassa ontvangt op `kassa.incoming`)

| Routing key / bron | Berichttype | Van |
| --- | --- | --- |
| `kassa.incoming` | `new_registration` | CRM |
| `kassa.incoming` | `profile_update` | CRM |
| `kassa.incoming` | `badge_scanned` | IoT / Frontend (QR) |
| `kassa.incoming` | `cancel_registration` | CRM |
| `kassa.incoming` | `wallet_lease_grant` | CRM |
| `kassa.incoming` | `wallet_remote_topup` | CRM |
| `kassa.incoming` | `event_ended` | Frontend |
| `kassa.incoming` | `user_event` | user.events fanout (optioneel) |
| `kassa.incoming` | `user_registered` | Frontend (dual-publish) |
| `kassa.incoming` | `user_unregistered` | Frontend (dual-publish) |
| `frontend.to.kassa.user_sessions_response` | `user_sessions_response` | Frontend |
| `frontend.to.kassa.session.created` | `session_created` | Frontend |
| `frontend.to.kassa.session.updated` | `session_updated` | Frontend |
| `frontend.to.kassa.session.deleted` | `session_deleted` | Frontend |

## **3\. Odoo POS Architectuur**

### **3.1 Custom Velden — res.partner**

| Veld | Type | Beschrijving |
| --- | --- | --- |
| `x_user_id` | Char | De `master_uuid` (identity_uuid) uit de Identity Service / CRM. Cruciaal voor matching over systemen heen. |
| `x_badge_id` | Char | De gekoppelde badge ID (fysiek of QR). |
| `x_wallet_balance` | Float | Het huidige saldo op de badge (Single Source of Truth). |
| `x_session_title` | Char | JSON-array van sessietitels waarvoor de klant ingeschreven is. |
| `x_outstanding_amount` | Float | Openstaand te betalen bedrag (uit `payment_due.amount`). |
| `x_payment_status` | Char | Betaalstatus: `unpaid`, `paid`, etc. |
| `x_date_of_birth` | Date | Geboortedatum (gebruikt voor alcoholcontrole Story 17). |
| `x_lease_active` | Boolean | Wallet lease momenteel actief bij Kassa? |
| `x_lease_id` | Char | De lease ID ontvangen van CRM via `wallet_lease_grant`. |
| `x_lease_transaction_count` | Integer | Aantal transacties gedurende de actieve lease. |
| `x_pending_topup_balance` | Float | Topup gebufferd vóór ontvangst van `wallet_lease_grant` (race-condition buffer). |
| `x_identity_status` | Selection | Status identity-koppeling: `pending`, `linked`, `error`. |
| `x_identity_last_sync` | Datetime | Tijdstip van laatste identity-synchronisatiepoging. |
| `x_badge_sent` | Boolean | `badge_assigned` bericht al verstuurd voor deze partner? |
| `x_rabbitmq_error` | Text | Laatste XSD- of identity-foutdetails (voor operatordiagnose). |

### **3.2 Custom Velden — pos.order**

| Veld | Type | Beschrijving |
| --- | --- | --- |
| `x_rabbitmq_sent` | Boolean | Order al succesvol gepubliceerd naar RabbitMQ? |
| `x_rabbitmq_error` | Char | XSD-validatiefout bij verwerking van dit order. |
| `x_wallet_updated` | Boolean | Wallet saldo al bijgewerkt voor dit order (guard tegen dubbele aftrek)? |
| `x_payment_message_id` | Char | UUID van het verstuurd `payment_registered` bericht (voor refund correlation). |
| `x_invoice_message_id` | Char | UUID van het verstuurd `invoice_request` bericht (voor deduplicatie). |

### **3.3 Custom Velden — product.template / product.product**

| Veld | Model | Type | Beschrijving |
| --- | --- | --- | --- |
| `x_session_id` | `product.template` | Char | Koppeling aan planningssessie-ID (survives title renames). Primaire lookup-sleutel in `_ensure_session_product()`. |
| `x_is_topup` | `product.template` | Boolean | Vlag voor top-up producten. `order_poller.py` herkent top-ups via `is_topup_product()` (categorie 'Top-ups' of dit veld). |
| `x_age_restricted` | `product.template` | Boolean | Vlag voor producten met leeftijdsbeperking (bv. bier). Gereserveerd voor toekomstige leeftijdscontrole (Story 17). |

### **3.4 Odoo Addon: kassa_pos_custom**

Breidt de Odoo POS-interface uit om badge-scans te verwerken en real-time saldo-updates te tonen via de `bus.bus` integratie. Bevat OWL-componenten voor:
- Automatische klantherkenning bij badge-scan
- Live `x_outstanding_amount` tonen bij klantSelectie
- Automatisch "Inschrijving" product toevoegen aan orderregel
- Badge Wallet betaalmethode blokkeren bij anonieme bestelling (Story 19)
- Leeftijdscontrole bij alcoholproducten (Story 17)

## **4\. De Integratie Service (Python)**

De integratie service start **3 achtergrond-threads** vanuit `main.py`. `sender.py` is een gedeelde module die door de andere threads wordt aangeroepen — het is geen eigen thread.

### **4.1 Sender Module (`sender.py`)**
Gedeelde module — geen eigen thread. Verantwoordelijk voor het bouwen en versturen van XML berichten.
1.  **Header Generation:** Voegt een standaard header toe met `message_id`, `timestamp`, `source`, `type` en `version` (in deze strikte volgorde conform v2.3).
2.  **Validation:** Valideert elke uitgaande XML tegen de XSD's in `schemas/`.
3.  **Resilience:** Indien RabbitMQ onbereikbaar is, worden berichten gebufferd in `outbox/outbox.json` (max 500, pad instelbaar via `OUTBOX_DIR`).

### **4.2 Receiver Module (`receiver.py`) — Thread 1**
Luistert op `kassa.incoming` voor berichten van andere teams. Verwerkt **14 berichttypes**:

| Berichttype | Bron | Actie |
| --- | --- | --- |
| `new_registration` | CRM | Partner aanmaken/updaten in Odoo + bus event naar POS |
| `profile_update` | CRM | Profielgegevens bijwerken + bus event |
| `badge_scanned` | IoT / Frontend (QR) | Partner opzoeken via `x_badge_id` of `identity_uuid` (QR); wallet lease starten |
| `cancel_registration` | CRM | Partner op `active=False` zetten |
| `wallet_lease_grant` | CRM | Wallet balance reconciliëren; lease_id opslaan; `wallet_balance_update` sturen |
| `wallet_remote_topup` | CRM | Online topup verwerken; balance bijwerken; `wallet_balance_update` sturen |
| `event_ended` | Frontend | Alle actieve leases teruggeven aan CRM via `wallet_lease_return` |
| `user_event` | user.events fanout (optioneel) | Informationeel; geen Odoo-actie |
| `user_registered` | Frontend (dual-publish) | Sessie toevoegen aan partner `x_session_title`; `x_outstanding_amount` bijwerken |
| `user_unregistered` | Frontend (dual-publish) | Sessie verwijderen uit partner `x_session_title`; `x_outstanding_amount` bijwerken |
| `user_sessions_response` | Frontend | Sessie-POS producten aanmaken/bijwerken per bezoeker |
| `session_created` | Frontend | Nieuw POS product aanmaken voor sessie |
| `session_updated` | Frontend | Bestaand sessie-POS product bijwerken (naam/prijs) |
| `session_deleted` | Frontend | Log + ack; POS product bewaard voor bestaande transacties |

**Processing pipeline per bericht:**
1. XML parse-controle
2. Header lezen (message_id + type)
3. Idempotentie-check (OrderedDict, max 10.000 entries)
4. XSD-validatie
5. Odoo-verbinding openen
6. Business logic (`process_*` functie)
7. ACK + message_id cachen

**Foutafhandeling:**
- Unparseable XML → `basic_nack(requeue=False)` + `system_error`
- XSD validation failure → `basic_nack(requeue=False)` + `system_error`
- Unknown message type → `basic_nack(requeue=False)` + `system_error`
- Odoo connection/auth error → retry via `RETRY_QUEUE` (max 3×, 5s delay), daarna DLQ
- Duplicate message_id → `basic_ack`, geen Odoo-actie

### **4.3 Order Poller Module (`order_poller.py`) — Thread 2**
Draait continu (interval: `POLL_INTERVAL`, default 5 seconden) om nieuwe verkopen in Odoo te detecteren en door te sturen naar CRM/Frontend.

**Verwerkt orders in staat `paid`, `done` of `invoiced` met `x_rabbitmq_sent=False`.**

Per polling-cyclus:
1. Nieuwe orders ophalen + verwerken (consumption / registration / refund)
2. Badge assignments detecteren + `badge_assigned` sturen
3. Buffer flushen elke ~30 seconden

### **4.4 Partner Identity Poller (`partner_identity_poller.py`) — Thread 3**
Draait continu (interval: `IDENTITY_POLL_INTERVAL`, default 10 seconden). Detecteert Odoo-partners met een e-mailadres maar zonder `x_user_id` en koppelt hen automatisch via de Identity Service.

**Flow:**
1. Partners zoeken met `email != False` en `x_user_id = False` en `x_identity_status != linked`
2. Check of een andere Odoo-partner met hetzelfde e-mailadres al een `x_user_id` heeft (hergebruik)
3. Zo niet: `identity.user.create.request` RPC → `master_uuid` ontvangen
4. Bij `EMAIL_ALREADY_EXISTS`: fallback naar `identity.user.lookup.email.request`
5. `x_user_id` opslaan + `x_identity_status = linked`
6. Error-state partners worden overgeslagen totdat `IDENTITY_ERROR_RETRY_AFTER` seconden (default 3600) verstreken zijn

### **4.5 Wallet Lease Lifecycle**

Bij QR-scan of badge-scan op `entrance`/`bar`/`main_bar`/`session`:
1. `badge_scanned` ontvangen door receiver
2. Kassa stuurt `wallet_lease_request` naar CRM (als nog geen actieve lease)
3. CRM bevestigt met `wallet_lease_grant` (bevat `current_balance` + `lease_id`)
4. Kassa reconcileert: `x_wallet_balance = current_balance + x_pending_topup_balance`
5. Kassa beheert de balance tijdens het event (deduct bij betaling, bijtelling bij topup)
6. Bij event-einde of uitloggen: `wallet_lease_return` naar CRM met `final_balance` en `transaction_count`

**Race condition:** Als een topup binnenkomt vóór de lease grant is bevestigd, wordt het bedrag geparkeerd in `x_pending_topup_balance` en vervolgens samengevoegd bij ontvangst van `wallet_lease_grant`.

## **5\. Docker Infrastructuur**

Het systeem draait in drie containers:
- `kassa-odoo`: De Odoo 17 webserver.
- `kassa-db`: De PostgreSQL 15 database.
- `kassa-integratie`: De Python service die de koppeling met RabbitMQ verzorgt (draait 4 threads).

**Belangrijk:** Gebruik altijd volumes voor de database en de integratie-outbox om dataverlies bij herstarts te voorkomen. De outbox-locatie is instelbaar via `OUTBOX_DIR` (default: `outbox/`).

## **6\. Healthcheck**

Bij succesvolle opstart maakt `main.py` het bestand `/tmp/service_ready` aan. Docker kan hierop een healthcheck configureren.

---
*Team Kassa | Technische Gids v5.0 | Conform Contract v2.3 | 2026*
