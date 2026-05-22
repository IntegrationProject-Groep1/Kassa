# Datamapping Documentatie — Team Kassa (Odoo POS)

Versie 4.0 (Volledige Harmonistatie v2.3) — Conform XML_naamgeving standaard (snake_case) | Geintegreerd document

Integratieproject Desideriushogeschool 2026

## 1. Strategie & Definities

- **Master UUID:** Alle systemen gebruiken de `identity_uuid` (gegenereerd door de Identity Service / CRM) als de primaire unieke sleutel voor personen.
- **Odoo Mapping:** De `identity_uuid` wordt in Odoo opgeslagen in het custom veld `x_user_id` op het `res.partner` model.
- **Header Standaard:** Alle berichten gebruiken de v2.3 header-volgorde: `message_id`, `timestamp`, `source`, `type`, `version`.

## 2. Scenario Mapping

### Inkomende flows (CRM/IoT/Frontend → Kassa)

| Scenario | type (enum) | Van | Naar | Routing / Queue | Trigger |
| --- | --- | --- | --- | --- | --- |
| Bezoeker schrijft in | new_registration | CRM | Kassa | `kassa.incoming` | Inschrijving bevestigd op website |
| CRM werkt profiel bij | profile_update | CRM | Kassa | `kassa.incoming` | Profiel bijgewerkt in Salesforce |
| Badge/QR gescand | badge_scanned | IoT / Frontend | Kassa | `kassa.incoming` | Badge aan inkom, bar of sessie gescand |
| Inschrijving geannuleerd | cancel_registration | CRM | Kassa | `kassa.incoming` | Bezoeker annuleert ticket |
| Wallet lease bevestigd | wallet_lease_grant | CRM | Kassa | `kassa.incoming` | CRM bevestigt balance authority na lease request |
| Online top-up ontvangen | wallet_remote_topup | CRM | Kassa | `kassa.incoming` | Bezoeker laadt saldo op via website |
| Event beëindigd | event_ended | Frontend | Kassa | `kassa.incoming` | Organisator sluit het event af |
| Sessie inschrijving | user_registered | Frontend (dual-publish) | Kassa | `kassa.incoming` | Bezoeker schrijft in voor een sessie |
| Sessie uitschrijving | user_unregistered | Frontend (dual-publish) | Kassa | `kassa.incoming` | Bezoeker schrijft zich uit voor een sessie |
| Sessies per bezoeker | user_sessions_response | Frontend | Kassa | `frontend.to.kassa.user_sessions_response` | Antwoord op user_sessions_request |
| Nieuwe sessie aangemaakt | session_created | Frontend | Kassa | `frontend.to.kassa.session.created` | Planning maakt nieuwe sessie aan |
| Sessie bijgewerkt | session_updated | Frontend | Kassa | `frontend.to.kassa.session.updated` | Titel of prijs van sessie gewijzigd |
| Sessie verwijderd | session_deleted | Frontend | Kassa | `frontend.to.kassa.session.deleted` | Sessie uit programma verwijderd |
| Sessiescatalogus | session_view_response | Planning | Kassa | via `planning.exchange` | Antwoord op session_view_request bij POS-opstart |

### Uitgaande flows (Kassa → CRM/Frontend/Planning)

| Scenario | type (enum) | Van | Naar | Routing key | Trigger |
| --- | --- | --- | --- | --- | --- |
| Bestelling doorsturen CRM | consumption_order | Kassa | CRM | `kassa.payments.consumption` | Na elke afgeronde aankoop |
| Betaling registreren (consumptie) | payment_registered | Kassa | CRM | `kassa.payments.consumption` | Na succesvolle consumptie-betaling |
| Betaling registreren (inschrijving) | payment_registered | Kassa | CRM | `kassa.payments.registration` | Na succesvolle inschrijvings-betaling |
| Klant vraagt factuur | invoice_request | Kassa | CRM | `kassa.payments.invoice` | Kassamedewerker verzamelt data; to_invoice=True |
| Terugbetaling verwerken | refund_processed | Kassa | CRM | `kassa.payments.refund` | Negatief order gedetecteerd |
| Badge koppelen | badge_assigned | Kassa | CRM | `kassa.payments.badge` | Nieuwe badge_id gekoppeld aan partner |
| Betaalstatus naar website | payment_status | Kassa | Frontend | `kassa.frontend.payment` | Na inschrijvings-betaling |
| Saldo update naar website | wallet_balance_update | Kassa | Frontend | `kassa.frontend.wallet` | Na badge-betaling, topup of lease grant |
| Wallet lease aanvragen | wallet_lease_request | Kassa | CRM | `kassa.wallet.lease.request` | Badge/QR scan op entrance/bar/session |
| Wallet lease teruggeven | wallet_lease_return | Kassa | CRM | `kassa.wallet.lease.return` | Event beëindigd of check-out |
| Sessies bezoeker opvragen | user_sessions_request | Kassa | Frontend | `kassa.to.frontend.user_sessions_request` | Badge/QR scan op locatie `session` |
| Sessiescatalogus opvragen | session_view_request | Kassa | Planning | via `planning.exchange` | Nieuwe POS-sessie gedetecteerd bij opstart |
| Fout rapporteren | system_error | Kassa | Elastic | `kassa.errors` | Validatiefout, onbekend type, Odoo-fout |

## 3. Master Datamapping Overzicht

### CRM / Frontend -> Kassa (Inkomend — res.partner velden)

| Object | XML-Veld | Odoo Veld | Toelichting |
| --- | --- | --- | --- |
| Customer | `<customer><identity_uuid>` | `x_user_id` | De Master UUID voor matching. |
| Contact | `<contact><first_name>` | `name` (deel 1) | Voornaam van de bezoeker. |
| Contact | `<contact><last_name>` | `name` (deel 2) | Achternaam van de bezoeker. |
| Session | `<session_title>` | `x_session_title` | JSON-array van sessietitels voor display. |
| Payment | `<payment_due><amount>` | `x_outstanding_amount` | Te betalen bedrag (attr: currency="eur"). |
| Payment | `<payment_due><status>` | `x_payment_status` | Betaalstatus: unpaid, paid, etc. |
| Customer | `<date_of_birth>` | `x_date_of_birth` | Geboortedatum (type: Date). |
| Customer | `<badge_id>` | `x_badge_id` | Badge ID (optioneel in new_registration). |
| Customer | `<type>` | `is_company` | `private` → False, `company` → True. |
| Customer | `<vat_number>` | `vat` | BTW-nummer (verplicht voor bedrijven per §11.1). |

### Kassa -> CRM (Uitgaand — consumption_order)

| Object | XML-Veld | Bron (Odoo) | Toelichting |
| --- | --- | --- | --- |
| Consumption | `<customer><identity_uuid>` | `x_user_id` | Koppeling aan het juiste profiel. |
| Item | `<item><id>` | `LINE-{order_line_id}` | Transactieregel-ID voor CRM-upsert. |
| Item | `<item><sku>` | `product_id.id` | Intern Odoo product ID. |
| Item | `<item><total_amount>` | `price_subtotal_incl` | Totaal incl. BTW (attr: currency="eur"). |
| Item | `<item><item_type>` | is_topup? | `wallet_topup` voor top-up producten, anders afwezig. |
| Payment | `<payment_context>` | sessie-type | `consumption` of `registration`. |

### Wallet Lease Lifecycle Mapping

| Event | Actie in Odoo | Bericht gestuurd |
| --- | --- | --- |
| Badge/QR scan (entrance/bar/session) | `x_lease_active = True`, `x_lease_id = ""` | `wallet_lease_request` → CRM |
| `wallet_lease_grant` ontvangen | `x_wallet_balance = current_balance + pending`, `x_lease_id = lease_id` | `wallet_balance_update` → Frontend |
| Badge-betaling | `x_wallet_balance` verlaagd, `x_lease_transaction_count` verhoogd | `wallet_balance_update` → Frontend |
| Topup tijdens actieve lease | `x_wallet_balance` verhoogd | `wallet_balance_update` → Frontend |
| Topup vóór lease grant | `x_pending_topup_balance` verhoogd (buffer) | — (merged bij lease grant) |
| `event_ended` ontvangen | `x_lease_active = False`, lease state gewist | `wallet_lease_return` → CRM per partner |

## 4. Enum Waarden

| Element | Toegestane waarden |
| --- | --- |
| `<header><type>` (inkomend) | new_registration, profile_update, badge_scanned, cancel_registration, wallet_lease_grant, wallet_remote_topup, event_ended, user_event, user_registered, user_unregistered, user_sessions_response, session_created, session_updated, session_deleted, session_view_response |
| `<header><type>` (uitgaand) | consumption_order, payment_registered, refund_processed, invoice_request, badge_assigned, payment_status, wallet_balance_update, system_error, wallet_lease_request, wallet_lease_return, user_sessions_request, session_view_request |
| `<payment_context>` | consumption, registration |
| `<customer><type>` | private, company, anonymous |
| `<transaction><payment_method>` | company_link, on_site, online |

## 5. Foutcodes (system_error)

Alle foutcodes zijn snake_case lowercase conform de XML_naamgeving standaard:

| Code | Wanneer |
| --- | --- |
| `invalid_xml_format` | Bericht voldoet niet aan XSD-schema |
| `unknown_message_type` | Onbekend `<type>` in header |
| `profile_not_found` | `identity_uuid` niet gevonden bij QR-scan |
| `odoo_api_error` | Odoo XML-RPC onbereikbaar of fout |
| `rabbitmq_connection_error` | RabbitMQ onbereikbaar |
| `offline_queue_full` | outbox.json heeft 500 berichten bereikt |
| `badge_not_found` | `badge_id` niet gevonden in Odoo |
| `badge_wallet_anonymous_blocked` | Badge Wallet betaling op anonieme order gedetecteerd |
| `identity_service_unavailable` | Identity Service onbereikbaar tijdens order-verwerking |
| `partner_not_linked` | Partner gevonden via badge/QR maar heeft geen `x_user_id` |

---
*Team Kassa | Datamapping v4.0 | Conform Contract v2.3 | 2026*
