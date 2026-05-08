# Datamapping Documentatie — Team Kassa (Odoo POS)

Versie 3.0 (Volledige Harmonistatie v2.3) — Conform XML_naamgeving standaard (snake_case) | Geintegreerd document

Integratieproject Desideriushogeschool 2026

## 1. Strategie & Definities

- **Master UUID:** Alle systemen gebruiken de `identity_uuid` (gegenereerd door CRM/Identity) als de primaire unieke sleutel voor personen.
- **Odoo Mapping:** De `identity_uuid` wordt in Odoo opgeslagen in het custom veld `x_user_id` op het `res.partner` model.
- **Header Standaard:** Alle berichten gebruiken de v2.3 header-volgorde: `message_id`, `timestamp`, `source`, `type`, `version`.

## 2. Scenario Mapping

| Scenario | type (enum) | Van | Naar | Routing (Exchange & Key) | Trigger |
| --- | --- | --- | --- | --- | --- |
| Bezoeker schrijft in | new_registration | CRM | Kassa | Queue: kassa.incoming | Inschrijving bevestigd op website |
| CRM werkt profiel bij | profile_update | CRM | Kassa | Queue: kassa.incoming | Profiel bijgewerkt in Salesforce |
| Bestelling doorsturen CRM | consumption_order | Kassa | CRM | kassa.payments.consumption | Na elke afgeronde aankoop |
| Betaling registreren CRM | payment_registered | Kassa | CRM | kassa.payments.consumption | Na succesvolle betaling |
| Klant vraagt factuur | invoice_request | Kassa | CRM | kassa.payments.invoice | Kassamedewerker verzamelt data |

## 3. Master Datamapping Overzicht

### CRM -> Kassa (Inkomend)

| Object | XML-Veld | Odoo Veld | Toelichting |
| --- | --- | --- | --- |
| Customer | <customer><identity_uuid> | x_user_id | De Master UUID voor matching. |
| Contact | <contact><first_name> | name (deel 1) | Voornaam van de bezoeker. |
| Contact | <contact><last_name> | name (deel 2) | Achternaam van de bezoeker. |
| Session | <session_title> | x_session_title | Titel van de sessie voor display. |
| Payment | <payment_due><amount> | x_outstanding_amount | Te betalen bedrag (attr: currency="eur"). |

### Kassa -> CRM (Uitgaand)

| Object | XML-Veld | Bron (Odoo) | Toelichting |
| --- | --- | --- | --- |
| Consumption | <customer><identity_uuid> | x_user_id | Koppeling aan het juiste profiel. |
| Item | <item><sku> | product_id.id | Intern Odoo product ID. |
| Item | <item><total_amount> | price_subtotal_incl | Totaal incl. BTW (attr: currency="eur"). |
| Payment | <payment_context> | — | 'consumption' of 'registration'. |

## 4. Enum Waarden

| Element | Toegestane waarden |
| --- | --- |
| <header><type> | new_registration, profile_update, consumption_order, payment_registered, ... |
| <payment_context> | consumption, registration |
| <customer><type> | private, company |

---
*Team Kassa | Datamapping v3.0 | Conform Contract v2.3 | 2026*
