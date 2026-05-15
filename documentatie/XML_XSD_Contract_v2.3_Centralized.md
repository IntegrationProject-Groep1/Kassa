# XML / XSD Contract v2.3 — Integration Project Groep 1

> **Dit document is het officiële en GECENTRALISEERDE berichtencontract voor alle teams.**  
> Elk bericht dat over RabbitMQ gaat, moet voldoen aan de structuur en XSD's in dit document. Dit is de enige 'Source of Truth' voor alle XML en XSD schema's in het project.
> Versie: **2.3** — Gesynchroniseerd met Kassa Team v2.5 implementatie (April 2026).
>
>  **Dit is het ENIGE geldige contract.** Alle teams moeten hun code hieraan aanpassen — afwijkingen die nog in code zitten zijn een **contractbreuk** en moeten dringend worden weggewerkt. Zie sectie 0.5 voor de exacte audit-bevindingen per team.

---

> **Gebruik voor distributie:** `XML_XSD_Contract_Distribution_CLEAN.md` — schoon bestand met alleen audit, XSD's en voorbeelden per team. Geen changelog, geen onnodige tekst.

---

## Changelog

| Datum | Versie | Wijziging |
|-------|--------|-----------|
| 2026-05-11 | v2.3 | **Secties 19.2 & 19.5 bijgewerkt** — `session_view_response` uitgebreid met optioneel `<price currency="eur">` per sessie (Rule 3 ✅). `session_update_request` uitgebreid met optioneel `<current_attendees>` en `<price currency="eur">`. Voorbeeld XML's bijgewerkt. |
| 2026-05-11 | v2.3 | **Sectie 19.7 bijgewerkt** — `user_sessions_response` XSD uitgebreid met optioneel `<price currency="eur">` element per sessie (Rule 3 ✅). Voorbeeld XML en regelcontrole bijgewerkt. |
| 2026-05-11 | v2.3 | **Sectie 19.7 toegevoegd** — `user_sessions_request` / `user_sessions_response` RPC (Kassa & Frontend → Planning). Quick reference tabellen voor Kassa, Frontend en Planning bijgewerkt. Queue/exchange overzicht uitgebreid met routing keys voor dit RPC-paar. Globale regelcontrole: alle 6 regels geslaagd. Request-XSD uitgebreid met `source="frontend"` zodat zowel Kassa als Frontend dit RPC-bericht kunnen versturen. |
| 2026-05-11 | v2.3 | **Sectie 26.2 bijgewerkt** — `wallet_lease_grant` XSD uitgebreid met optioneel `<payment_due>` element (openstaande inschrijvingskosten bezoeker). Bevat `<amount currency="eur">` (Rule 3 ✅) en optionele `<status>` (unpaid/paid). Voorbeeld XML bijgewerkt. |

---

##  QUICK REFERENCE — Per Team: Wat ontvang jij? Wat verstuur je?

> ### 🛑 PROJECT-WIDE RULE: THE SIDECAR PRINCIPLE
> **Geen enkel applicatie-team (CRM, Frontend, Kassa, etc.) mag zelf heartbeat-code implementeren OF de sidecar beheren.** 
> Heartbeats worden EXCLUSIEF afgehandeld door de project-sidecar (`heartbeat/sidecar.py`). Deze wordt **automatisch gestart en beheerd door het Monitoring/Infrastructuur-team** op de VM zodra jouw containers gedeployed zijn. Applicatie-teams hebben hier 0% omkijken naar.


### **Team Kassa** — Betalingen & Kassamachine

| Richting | Berichttype | Van/Naar | Sectie |
|----------|---|---|---|
| **ONTVANGT** | `new_registration`, `profile_update`, `cancel_registration` | ← CRM | [10. CRM → Kassa](#10-crm--kassa) |
| **ONTVANGT** | `badge_scanned` | ← IoT (Raspberry Pi) of Kassa (QR) | [6.3](#63-badge_scanned) |
| **ONTVANGT** | `event_ended` | ← Frontend | [11.7](#117-event_ended-frontend--kassa) |
| **VERZENDT** | `consumption_order` | → CRM | [6.1](#61-consumption_order) |
| **VERZENDT** | `badge_assigned` | → CRM | [6.2](#62-badge_assigned) |
| **VERZENDT** | `refund_processed` | → CRM | [6.4](#64-refund_processed) |
| **VERZENDT** | `invoice_request` | → CRM | [6.5](#65-invoice_request-kassa--crm) |
| **VERZENDT** | `payment_registered` | → CRM | [6.6](#66-payment_registered-kassa--rabbitmq) |
| **VERZENDT** | `payment_status`, `wallet_balance_update` | → Frontend | [18](#18-frontend--kassa-direct-flows) |
| **RPC** | `user_sessions_request` / `user_sessions_response` | ↔ Planning | [19.7](#197-user_sessions_request--user_sessions_response-rpc) |
| **BROADCAST** | `heartbeat` (via sidecar) | → Monitoring | [3. Heartbeat](#3-heartbeat--alle-teams--monitoring) |

**XSD's referentie:** `Kassa/integratie/schemas/` — wordt als referentie-implementatie gebruikt door andere teams.

---

### **Team CRM** — Centraal routering & data-sync

| Richting | Berichttype | Van/Naar | Sectie |
|----------|---|---|---|
| **ONTVANGT** | `new_registration` | ← Frontend | [5.1](#51-new_registration) |
| **ONTVANGT** | `user_registered` | ← Frontend | [5.5](#55-user_registered) |
| **ONTVANGT** | `user_created`, `user_updated`, `user_deleted` | ← Frontend | [5.2-5.4](#52-user_updated) |
| **ONTVANGT** | `cancel_registration` | ← Frontend | [5.6](#56-cancel_registration-frontend--crm) |
| **ONTVANGT** | `company_member_removed` | ← Frontend | [5.8](#58-company_member_removed) |
| **ONTVANGT** | `company_registration` | ← Frontend | [5.9](#59-company_registration-frontend--crm) |
| **ONTVANGT** | `company_update` | ← Frontend | [5.10](#510-company_update-frontend--crm) |
| **ONTVANGT** | `company_delete` | ← Frontend | [5.11](#511-company_delete-frontend--crm) |
| **ONTVANGT** | `session_created`, `session_updated` | ← Planning | [7.1-7.2](#71-session_created) |
| **ONTVANGT** | `payment_registered` | ← Kassa | [6.6](#66-payment_registered-kassa--rabbitmq) |
| **ONTVANGT** | `invoice_status` | ← Facturatie | [8.1](#81-invoice_status) |
| **ONTVANGT** | `mailing_status` | ← Mailing | [9.1](#91-mailing_status) |
| **ONTVANGT** | `user_checkin` | ← Frontend | [19.1](#191-user_checkin) |
| **ONTVANGT** | `user_event` (fanout) | ← Identity | [15.5](#155-fanout-event--usercreated) |
| **VERZENDT** | `new_registration`, `profile_update`, `cancel_registration` | → Kassa | [10.1-10.3](#101-new_registration-crm--kassa) |
| **VERZENDT** | `profile_update` | → Facturatie | [10.4](#104-profile_update-crm--facturatie) |
| **VERZENDT** | `invoice_request` | → Facturatie | [11.1](#111-invoice_request-crm--facturatie) |
| **VERZENDT** | `send_mailing` | → Mailing | [12.1](#121-send_mailing-crm--mailing) |
| **VERZENDT** | `payment_registered` | → Frontend | [14.1](#141-payment_registered-crm--frontend) |
| **VERZENDT** | `vat_validation_error` | → Frontend | [20.1](#201-vat_validation_error) |
| **RPC** | `identity_request` | → Identity | [15.1-15.3](#151-rpc-request--gebruiker-aanmaken) |
| **BROADCAST** | `heartbeat` (via sidecar) | → Monitoring | [3](#3-heartbeat--alle-teams--monitoring) |

---

### **Team Frontend** — Gebruiker registratie & events

| Richting | Berichttype | Van/Naar | Sectie |
|----------|---|---|---|
| **VERZENDT** | `new_registration` | → CRM | [5.1](#51-new_registration-frontend--crm) |
| **VERZENDT** | `user_created` | → CRM | [5.2](#52-user_created) |
| **VERZENDT** | `user_updated` | → CRM | [5.3](#53-user_updated) |
| **VERZENDT** | `user_deleted` | → CRM | [5.4](#54-user_deleted) |
| **VERZENDT** | `user_registered` | → CRM | [5.5](#55-user_registered) |
| **VERZENDT** | `user_checkin` | → CRM | [19.1](#191-user_checkin) |
| **VERZENDT** | `company_member_removed` | → CRM | [5.8](#58-company_member_removed) |
| **VERZENDT** | `company_registration` | → CRM | [5.9](#59-company_registration-frontend--crm) |
| **VERZENDT** | `company_update` | → CRM | [5.10](#510-company_update-frontend--crm) |
| **VERZENDT** | `company_delete` | → CRM | [5.11](#511-company_delete-frontend--crm) |
| **VERZENDT** | `event_ended` | → Facturatie, Kassa (exchange: `event.ended`) | [5.7](#57-event_ended), [11.6](#116-event_ended-frontend--facturatie), [11.7](#117-event_ended-frontend--kassa) |
| **VERZENDT** | `calendar_invite` | → Planning | [19.3](#193-calendar_invite--calendar_invite_confirmed) |
| **VERZENDT** | `session_create_request` | → Planning | [19.4](#194-session_create_request-frontend--planning) |
| **VERZENDT** | `session_update_request` | → Planning | [19.5](#195-session_update_request-frontend--planning) |
| **VERZENDT** | `session_delete_request` | → Planning | [19.6](#196-session_delete_request-frontend--planning) |
| **VERZENDT** | `payment_registered` | → Facturatie | [11.5](#115-payment_registered-frontend--facturatie) |
| **ONTVANGT** | `payment_registered` | ← CRM | [14.1](#141-payment_registered-crm--frontend) |
| **ONTVANGT** | `payment_status`, `wallet_balance_update` | ← Kassa | [18](#18-frontend--kassa-direct-flows) |
| **ONTVANGT** | `session_created`, `session_updated`, `session_deleted` | ← Planning | [7](#7-planning--crm) |
| **ONTVANGT** | `calendar_invite_confirmed` | ← Planning | [19.3](#193-calendar_invite--calendar_invite_confirmed) |
| **ONTVANGT** | `invoice_available` | ← Facturatie | [13.5](#135-facturatie--frontend) |
| **ONTVANGT** | `vat_validation_error` | ← CRM / Facturatie | [20.1](#201-vat_validation_error) |
| **RPC** | `session_view_request` / `session_view_response` | ↔ Planning | [19.2](#192-session_view_request--session_view_response-rpc) |
| **RPC** | `user_sessions_request` / `user_sessions_response` | ↔ Planning | [19.7](#197-user_sessions_request--user_sessions_response-rpc) |
| **RPC** | `identity_request` | → Identity | [15.1-15.3](#151-rpc-request--gebruiker-aanmaken) |
| **BROADCAST** | `heartbeat` (via sidecar) | → Monitoring | [3](#3-heartbeat--alle-teams--monitoring) |

---

### **Team Planning** — Sessies & agenda

| Richting | Berichttype | Van/Naar | Sectie |
|----------|---|---|---|
| **VERZENDT** | `session_created`, `session_updated`, `session_deleted` | → CRM | [7](#7-planning--crm) |
| **VERZENDT** | `session_created`, `session_updated`, `session_deleted` | → Frontend | [7](#7-planning--crm) |
| **VERZENDT** | `calendar_invite_confirmed` | → Frontend | [19.3](#193-calendar_invite--calendar_invite_confirmed) |
| **ONTVANGT** | `calendar_invite` | ← Frontend | [19.3](#193-calendar_invite--calendar_invite_confirmed) |
| **ONTVANGT** | `cancel_registration` | ← CRM | [10.3](#103-cancel_registration-crm--kassa--planning) |
| **ONTVANGT** | `session_create_request` | ← Frontend | [19.4](#194-session_create_request-frontend--planning) |
| **ONTVANGT** | `session_update_request` | ← Frontend | [19.5](#195-session_update_request-frontend--planning) |
| **ONTVANGT** | `session_delete_request` | ← Frontend | [19.6](#196-session_delete_request-frontend--planning) |
| **RPC** | `session_view_request` / `session_view_response` | ↔ Frontend | [19.2](#192-session_view_request--session_view_response-rpc) |
| **RPC** | `user_sessions_request` / `user_sessions_response` | ↔ Kassa, Frontend | [19.7](#197-user_sessions_request--user_sessions_response-rpc) |
| **REST** | `Token Registration` | ← Frontend | [19.0](#190-oauth-token-registration-rest-api) |
| **BROADCAST** | `heartbeat` (via sidecar) | → Monitoring | [3](#3-heartbeat--alle-teams--monitoring) |

**XSD's referentie:** `Planning/xsd/`

**Belangrijk:** Gebruikt Master UUID (Session Persistence) via `correlation_id` voor alle sessie-gerelateerde berichten.

---

### **Team Facturatie** — Factuurverwerking

| Richting | Berichttype | Van/Naar | Sectie |
|----------|---|---|---|
| **ONTVANGT** | `invoice_request` | ← CRM | [11.1](#111-invoice_request-crm--facturatie) |
| **ONTVANGT** | `consumption_order` (passthrough) | ← CRM/Kassa | [11.3](#113-consumption_order-crm--facturatie--passthrough) |
| **ONTVANGT** | `new_registration` | ← CRM | [10.1](#101-new_registration-crm--kassa) |
| **ONTVANGT** | `profile_update` | ← CRM | [10.4](#104-profile_update-crm--facturatie) |
| **ONTVANGT** | `payment_registered` | ← Frontend (online betalingen) | [11.5](#115-payment_registered-frontend--facturatie) |
| **ONTVANGT** | `event_ended` | ← Frontend | [11.6](#116-event_ended-frontend--facturatie) |
| **VERZENDT** | `invoice_status` | → CRM | [8.1](#81-invoice_status) |
| **VERZENDT** | `payment_registered` | → CRM | [8.2](#82-payment_registered) |
| **VERZENDT** | `send_mailing` | → Mailing | [13.1](#131-send_mailing-facturatie--mailing) |
| **VERZENDT** | `invoice_available` | → Frontend | [13.5](#135-facturatie--frontend) |
| **VERZENDT** | `vat_validation_error` | → Frontend | [20.1](#201-vat_validation_error) |
| **BROADCAST** | `heartbeat` (via sidecar) | → Monitoring | [3](#3-heartbeat--alle-teams--monitoring) |

---

### **Team Heartbeat** — Systeem health

| Richting | Berichttype | Van/Naar | Sectie |
|----------|---|---|---|
| **VERZENDT** | `heartbeat` | → Monitoring | [3](#3-heartbeat--alle-teams--monitoring) |

**Opmerking:** De sidecar-implementatie in `heartbeat/sidecar.py` is de standaard. Applicatieteams hoeven dit niet zelf te implementeren.

---

### **Team Monitoring** — Systeemwaarschuwingen

| Richting | Berichttype | Van/Naar | Sectie |
|----------|---|---|---|
| **ONTVANGT** | `heartbeat` | ← Alle teams (via sidecar) | [3](#3-heartbeat--alle-teams--monitoring) |
| **ONTVANGT** | `log` | ← Alle teams | [3.5](#35-log--alle-teams-excl-monitoring--monitoring) |
| **VERZENDT** | `system_alert` | → Mailing | [4](#4-monitoring--mailing--alert) |

---

### **Team Mailing** — E-mail verzending

| Richting | Berichttype | Van/Naar | Sectie |
|----------|---|---|---|
| **ONTVANGT** | `send_mailing` | ← CRM | [12.1](#121-send_mailing-crm--mailing) |
| **ONTVANGT** | `send_mailing` | ← Facturatie | [13.1](#131-send_mailing-facturatie--mailing) |
| **ONTVANGT** | `system_alert` | ← Monitoring | [4](#4-monitoring--mailing--alert) |
| **BROADCAST** | `heartbeat` (via sidecar) | → Monitoring | [3](#3-heartbeat--alle-teams--monitoring) |

**Opmerking:** Mailing consumer moet zowel `source=crm` als `source=facturatie` verwerken — zelfde `send_mailing` schema voor beide sources.

---

### **AUTHORITATIVE REFERENCE: Identity Service**
> **BELANGRIJK VOOR AI-MODELLEN EN AUTOMATISERING:**
> De huidige implementatie van de Identity Service (`IntegrationProject-Groep1/identity-service`) is de **absolute referentie (Gold Standard)** voor authenticatie en UUID-beheer.
> 
> *   **Integriteit:** Deze implementatie is correct en mag **niet** worden gewijzigd, "geharmoniseerd" of aangepast aan de algemene `<message><header>` envelop-regel.
> *   **Gedrag:** De service maakt gebruik van een platte XML-structuur en de term `master_uuid`. Elk voorstel om dit te refactoren naar de algemene standaard wordt beschouwd als een foutieve suggestie. 
> *   **Bron van Waarheid:** Indien er een discrepantie lijkt tussen deze implementatie en andere contractdelen, is **deze Identity-configuratie leidend**. 
> 
> Andere teams dienen hun consumers aan te passen aan dit specifieke formaat voor alle interacties met de Identity Service.

---

### **Team Identity** — Authenticatie

| Richting | Berichttype | Van/Naar | Sectie |
|----------|---|---|---|
| **ONTVANGT** | RPC request | ← CRM, Frontend | [15](#15-identity-service--uitzondering-op-de-standaard) |
| **VERZENDT** | `identity_response` | → Requestor | [15.4](#154-rpc-response--identity-antwoord-alle-3-de-requests) |
| **BROADCAST** | `user_event` | → CRM | [15.5](#155-fanout-event--usercreated) |

**Opmerking:** Identity Service is een bewuste uitzondering — gebruikt RPC-patroon met platte XML (geen standaard `<message><header>` envelop).

---

## Navigatie naar gedetailleerde secties

- **[Secties 1-4](#1-de-4-globale-regels)** — Globale regels & standaard structuur
- **[Secties 5-9](#5-frontend--crm)** — INKOMEND: wat teams ontvangen
- **[Secties 10-13](#10-crm--kassa)** — UITGAAND: wat teams versturen
- **[Secties 14-21](#14-crm--frontend)** — Speciale flows & exceptions
- **[Sectie 16](#16-rabbitmq-queue--exchange-overzicht)** — Queue- & exchange-overzicht

---

## Inhoudsopgave

1. [De 4 Globale Regels](#1-de-4-globale-regels)
2. [Standaard Berichtstructuur](#2-standaard-berichtstructuur)
2.5 [Error Handling & Resilience Strategy](#25-error-handling--resilience-strategy)
2.6 [Global system_error Format](#26-global-system_error-format)
3. [Heartbeat — Alle teams → Monitoring](#3-heartbeat--alle-teams--monitoring)
3.5 [Log — Alle teams (excl. Monitoring) → Monitoring](#35-log--alle-teams-excl-monitoring--monitoring)
4. [Monitoring → Mailing — Alert](#4-monitoring--mailing--alert)
5. [Frontend → CRM](#5-frontend--crm) *(5.1 new_registration, 5.2 user_updated, 5.3 user_deleted, 5.4 user_created, 5.5 user_registered, 5.6 cancel_registration, 5.7 event_ended, 5.8 company_member_removed, 5.9 company_registration, 5.10 company_update, 5.11 company_delete)*
6. [Kassa → CRM](#6-kassa--crm)
7. [Planning → CRM](#7-planning--crm)
8. [Facturatie → CRM](#8-facturatie--crm)
9. [Mailing → CRM](#9-mailing--crm)
10. [CRM → Kassa](#10-crm--kassa)
11. [CRM → Facturatie](#11-crm--facturatie) *(11.1 invoice_request, 11.2 invoice_cancelled, 11.3 consumption_order passthrough, 11.5 payment_registered Frontend direct)*
12. [CRM → Mailing](#12-crm--mailing)
13. [Facturatie → Mailing](#13-facturatie--mailing)
13.5 [Facturatie → Frontend](#135-facturatie--frontend)
14. [CRM → Frontend](#14-crm--frontend)
15. [Identity Service (Uitzondering!)](#15-identity-service--uitzondering-op-de-standaard)
16. [RabbitMQ Queue & Exchange Overzicht](#16-rabbitmq-queue--exchange-overzicht)
17. [Per-Team Samenvatting](#17-per-team-samenvatting)
18. [Frontend ← Kassa (Direct flows)](#18-frontend--kassa-direct-flows)
19. [Frontend ↔ Planning (Directe flows)](#19-frontend--planning-directe-flows) *(19.1 user_checkin, 19.2 session_view RPC ~~DEPRECATED~~, 19.3 calendar_invite, 19.4 session_create_request, 19.5 session_update_request, 19.6 session_delete_request, 19.7 user_sessions RPC → Frontend, 19.8 Frontend → Kassa sessiewijzigingen)*
20. [CRM / Facturatie → Frontend: BTW Validatiefout](#20-crm--facturatie--frontend-btw-validatiefout) *(20.1 vat_validation_error)*
21. [Migratie Roadmap (NIEUW v2.3)](#21-migratie-roadmap)
22. [Validatie Checklist](#22-validatie-checklist-per-bericht)
23. [Cross-Team Interface Analyse](#23-cross-team-interface-analyse--welke-xml-moet-gesynchroniseerd-worden)
24. [Centralisatie](#24-centralisatie--hoe-dit-document-te-gebruiken)
25. [Final Rule](#25-final-rule)

---

## 1. De 4 Globale Regels

Deze regels gelden voor **elk** bericht zonder uitzondering.

### Regel 1 — Header v2.0: geen `<receiver>`, geen `xmlns`

```xml
<!--  CORRECT -->
<message>
  <header>
    <version>2.0</version>
    ...
  </header>
</message>

<!--  FOUT — xmlns verboden -->
<message xmlns="urn:integration:planning:v1">
  <header>
    <version>2.0</version>
  </header>
</message>

<!--  FOUT — receiver verboden -->
<message>
  <header>
    <receiver>kassa</receiver>
  </header>
</message>
```

**Waarom:** In een event-driven RabbitMQ-architectuur weet de zender niet wie er luistert. `<receiver>` breekt loose coupling. `xmlns` is inconsistent met alle andere teams.

---

### Regel 2 — `<contact>` nesting voor namen

```xml
<!--  CORRECT -->
<customer>
  <contact>
    <first_name>Jan</first_name>
    <last_name>Peeters</last_name>
  </contact>
</customer>

<!--  FOUT — los in parent tag -->
<customer>
  <first_name>Jan</first_name>
  <last_name>Peeters</last_name>
</customer>
```

**Waarom:** Consistentie over de hele keten. Elk systeem leest namen op exact dezelfde manier.

---

### Regel 3 — Valuta verplicht op geldbedragen

```xml
<!--  CORRECT -->
<unit_price currency="eur">5.50</unit_price>
<amount currency="eur">150.00</amount>
<amount_paid currency="eur">75.00</amount_paid>

<!--  FOUT — geen currency attribuut -->
<unit_price>5.50</unit_price>
```

**Waarom:** Een bedrag zonder valuta is gevaarlijk. Financiële velden zijn altijd `xs:decimal` met verplicht `currency="eur"` attribuut.

---

### Regel 4 — `date_of_birth` in plaats van `age`

```xml
<!--  CORRECT -->
<date_of_birth>1995-03-21</date_of_birth>

<!--  FOUT — age is dynamisch en verandert elk jaar -->
<age>29</age>
```

**Waarom:** CRM is de Single Source of Truth. Een leeftijd berekent elk systeem zelf op basis van de geboortedatum.

---

### Regel 5 — Master UUID vs Interne ID's

```xml
<!--  CORRECT — Gebruik de Master UUID van de Identity Service -->
<identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>

<!--  FOUT — Gebruik GEEN interne database ID's van je eigen systeem -->
<identity_uuid>drupal-user-4821</identity_uuid>
<identity_uuid>sf-contact-00891</identity_uuid>
<identity_uuid>odoo-partner-99</identity_uuid>
```

**Waarom:** Interne ID's (Salesforce ID, Drupal UID, Odoo Partner ID) zijn alleen zinvol binnen de eigen service. Voor communicatie tussen teams is de **Master UUID** van de Identity Service de enige geldige identifier. Interne queries worden gedaan met de eigen ID, maar voor XML-berichten naar buiten gebruik je verplicht de **`identity_uuid`**.

---

### Regel 6 — Adres splitsing (Straat vs Huisnummer)

```xml
<!--  CORRECT — Straat en nummer zijn strikt gescheiden -->
<address>
  <street>Kiekenmarkt</street>
  <number>42</number>
  <postal_code>1000</postal_code>
  <city>Brussel</city>
  <country>be</country>
</address>

<!--  FOUT — Alles in de straat tag, nummer leeg -->
<address>
  <street>Kiekenmarkt 42</street>
  <number></number>
  <postal_code>1000</postal_code>
  <city>Brussel</city>
  <country>be</country>
</address>
```

**Waarom:** Systemen zoals Odoo slaan de straat vaak op als één vrije tekstveld. Echter, voor de layout van facturen (Team Facturatie) en database-integriteit is een strikte scheiding tussen de straatnaam en het huisnummer verplicht. Berichten met een leeg `<number>` veld kunnen door de XSD-validatie van de ontvanger worden geweigerd.

**Splitting-algoritme (voor Odoo/Integratie):**
Indien de bron-data slechts één veld bevat, moet de integratie-laag (bijv. `order_poller.py`) de tekst splitsen:
1. Scan de string van achter naar voren.
2. Identificeer het eerste getal (en eventuele bus-toevoegingen zoals "bus B" of "A").
3. Isoleer dit deel als `<number>`.
4. Alles wat vóór dit getal staat is de `<street>` (verwijder eventuele spaties aan het begin of einde).

---

## 2. Standaard Berichtstructuur

Elk bericht heeft de volgende structuur:

```xml
<message>
  <header>
    <message_id>550e8400-e29b-41d4-a716-446655440000</message_id>
    <timestamp>2026-04-24T10:30:00Z</timestamp>
    <source>crm</source>
    <type>new_registration</type>
    <version>2.0</version>
    <!-- optioneel: alleen bij request-response flows -->
    <correlation_id>7f3a1b2c-4d5e-6f7a-8b9c-0d1e2f3a4b5c</correlation_id>
  </header>
  <body>
    <!-- berichtspecifieke inhoud -->
  </body>
</message>
```

### Header XSD (gedeeld door alle berichten)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">

  <xs:complexType name="HeaderType">
    <xs:sequence>
      <xs:element name="message_id" type="UUIDType"/>
      <xs:element name="timestamp"  type="xs:dateTime"/>
      <xs:element name="source"     type="SourceType"/>
      <xs:element name="type"       type="xs:string"/>
      <xs:element name="version">
        <xs:simpleType>
          <xs:restriction base="xs:string">
            <xs:enumeration value="2.0"/>
          </xs:restriction>
        </xs:simpleType>
      </xs:element>
      <xs:element name="correlation_id" type="UUIDType" minOccurs="0"/>
    </xs:sequence>
  </xs:complexType>

  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:simpleType name="SourceType">
    <xs:restriction base="xs:string">
      <xs:enumeration value="frontend"/>
      <xs:enumeration value="crm"/>
      <xs:enumeration value="kassa"/>
      <xs:enumeration value="planning"/>
      <xs:enumeration value="facturatie"/>
      <xs:enumeration value="mailing"/>
      <xs:enumeration value="monitoring"/>
      <xs:enumeration value="identity-service"/>
      <xs:enumeration value="iot_gateway"/>
    </xs:restriction>
  </xs:simpleType>

  <!-- Herbruikbaar contactblok -->
  <xs:complexType name="ContactType">
    <xs:sequence>
      <xs:element name="first_name" type="xs:string"/>
      <xs:element name="last_name"  type="xs:string"/>
    </xs:sequence>
  </xs:complexType>

  <!-- Geldbedrag met verplichte valuta -->
  <xs:complexType name="AmountType">
    <xs:simpleContent>
      <xs:extension base="xs:decimal">
        <xs:attribute name="currency" type="xs:string" fixed="eur" use="required"/>
      </xs:extension>
      </xs:simpleContent>
      </xs:complexType>
</xs:schema>
```

---

## 2.5 Error Handling & Resilience Strategy

Om de robuustheid van het systeem te garanderen, spreken we de volgende strategie af voor foutafhandeling.

### 2.5.1 Validatiefouten (XSD)
*   **Actie:** Bij een inkomend bericht dat niet voldoet aan de XSD, stuur je een **ACK** naar RabbitMQ (om de queue niet te verstoppen) en publiceer je direct een `system_error` (zie 2.6) naar je eigen error queue.
*   **Error Code:** `invalid_xml_format`.

### 2.5.2 Resilience: Identity Service (SSoT) is Down
De Master UUID is verplicht voor registraties. Als de Identity Service niet bereikbaar is via RPC:
1.  **NIET** doorgaan met een tijdelijke of interne ID.
2.  **Retry:** Probeer de RPC-call 3 keer met een exponentiële back-off.
3.  **Fail Fast:** Als het nog steeds niet lukt, toon een foutmelding aan de gebruiker (Frontend) of parkeer het bericht in een lokale "Wait-for-Identity" queue (CRM).
4.  **Reporting:** Stuur een `system_error` met code `identity_service_unavailable`.

### 2.5.3 Dead Letter Queues (DLQ)
Gebruik DLQ's alleen voor **infrastructurele fouten** (bijv. database verbinding verbroken).
*   **Logische fouten** (ongeldige data, UUID niet gevonden) horen **niet** in de DLQ maar moeten worden afgehandeld via `system_error` en een ACK op het originele bericht.

### 2.5.4 Kassa Specifieke Regels (ACK/NACK)
*   **Badge Not Found:** Voor `badge_not_found` stuurt het Kassa-systeem een **ACK** (geen NACK) om oneindige lussen te voorkomen. Dit gaat vergezeld van een `system_error` bericht naar de `kassa.errors` queue voor monitoring.

---
## 2.6 Global `system_error` Format

Elk team gebruikt dit formaat om fouten te rapporteren naar Monitoring of hun eigen error queue.

**Gezamenlijke Error Codes:**

| Code | Wanneer |
|------|---------|
| `invalid_xml_format` | Binnenkomend bericht voldoet niet aan XSD |
| `unknown_message_type` | Onbekend berichttype ontvangen |
| `profile_not_found` | De Master UUID (`identity_uuid`) is niet bekend in je systeem |
| `identity_service_unavailable` | Kan geen Master UUID ophalen bij de Identity Service |
| `database_error` | Interne database fout bij verwerken bericht |

### 2.6 `system_error`

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="header">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="message_id" type="UUIDType"/>
              <xs:element name="timestamp"  type="xs:dateTime"/>
              <xs:element name="source"     type="xs:string"/>
              <xs:element name="type"       type="xs:string" fixed="system_error"/>
              <xs:element name="version"    type="xs:string" fixed="2.0"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
        <xs:element name="body">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="error_code" type="xs:string"/>
              <xs:choice>
                <xs:element name="error_description" type="xs:string"/>
                <xs:element name="message" type="xs:string"/>
              </xs:choice>
              <xs:element name="component" type="xs:string" minOccurs="0"/>
              <!-- related_message_id: message_id van het bericht dat de fout veroorzaakte -->
              <xs:element name="related_message_id" type="xs:string" minOccurs="0"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML — Master UUID niet gevonden

```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>63a4b5c6-d7e8-9012-abcd-012345600012</message_id>
    <timestamp>2026-05-15T19:05:00Z</timestamp>
    <source>crm</source>
    <type>system_error</type>
    <version>2.0</version>
  </header>
  <body>
    <error_code>profile_not_found</error_code>
    <error_description>Master UUID e8b27c1d-... niet gevonden in Salesforce</error_description>
    <related_message_id>c3d4e5f6-a7b8-9012-cdef-012345678902</related_message_id>
  </body>
</message>
```

---

## 3. Heartbeat — Alle teams → Monitoring

- **Exchange:** `""` (AMQP default exchange — geen named exchange)
- **Queue:** `heartbeat` (durable — direct adresseerbaar via default exchange)
- **Interval:** elke 1 seconde
- **Wie stuurt:** Wordt afgehandeld door de **Sidecar**, niet door de applicatie-logica zelf.

### 3.1 De "Sidecar Principle" Clarificatie

> **"Applicatie-services hoeven heartbeats NIET intern te implementeren indien ze gedeployed zijn met de standaard project-sidecar. De sidecar is de enige producent van heartbeat-berichten."**

Voor een beter begrip van het contract maken we onderscheid tussen:
*   **Logical Requirement:** Het systeem als geheel moet gemonitord worden. Elke component moet zijn aanwezigheid melden.
*   **Technical Implementation:** Dit wordt centraal afgehandeld via `heartbeat/sidecar.py`. Applicatieteams hoeven geen code te schrijven voor heartbeats; zij moeten enkel zorgen dat de sidecar correct meedraait in hun deployment (container/pod).

### 3.2 Routing

De sidecar publiceert heartbeats met `exchange=""` en `routing_key="heartbeat"` — dit stuurt het bericht rechtstreeks naar de `heartbeat` queue via de AMQP default exchange. Logstash (Monitoring) luistert direct op die queue. Er is geen named exchange nodig.

### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="header">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="message_id" type="UUIDType"/>
              <xs:element name="timestamp"  type="xs:dateTime"/>
              <xs:element name="source"     type="xs:string"/>
              <xs:element name="type">
                <xs:simpleType><xs:restriction base="xs:string">
                  <xs:enumeration value="heartbeat"/>
                </xs:restriction></xs:simpleType>
              </xs:element>
              <xs:element name="version">
                <xs:simpleType><xs:restriction base="xs:string">
                  <xs:enumeration value="2.0"/>
                </xs:restriction></xs:simpleType>
              </xs:element>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
        <xs:element name="body">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="status">
                <xs:simpleType><xs:restriction base="xs:string">
                  <xs:enumeration value="online"/>
                  <xs:enumeration value="offline"/>
                </xs:restriction></xs:simpleType>
              </xs:element>
              <xs:element name="uptime" type="xs:nonNegativeInteger"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
```

### Voorbeeld XML

```xml
<message>
  <header>
    <message_id>a1b2c3d4-e5f6-7890-abcd-ef1234567890</message_id>
    <timestamp>2026-04-24T10:30:00Z</timestamp>
    <source>crm</source>
    <type>heartbeat</type>
    <version>2.0</version>
  </header>
  <body>
    <status>online</status>
    <uptime>3600</uptime>
  </body>
</message>
```

> ** Let op voor Monitoring-team:** Het veld `source` in de header komt overeen met het `system`-veld dat jullie intern gebruiken voor de Logstash-mapping. Toegestane waarden: `frontend`, `crm`, `kassa`, `planning`, `facturatie`, `mailing`, `monitoring`, `identity-service`, `iot_gateway`.

---

## 3.5 Log — Alle teams (excl. Monitoring) → Monitoring

- **Exchange:** `""` (AMQP default exchange)
- **Queue:** `logs` (durable)
- **Wie stuurt:** Elke applicatieservice die een loggable event wil rapporteren aan Monitoring.

### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="header">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="message_id" type="UUIDType"/>
              <xs:element name="timestamp"  type="xs:dateTime"/>
              <xs:element name="source">
                <xs:simpleType><xs:restriction base="xs:string">
                  <xs:enumeration value="crm"/>
                  <xs:enumeration value="kassa"/>
                  <xs:enumeration value="facturatie"/>
                  <xs:enumeration value="frontend"/>
                  <xs:enumeration value="planning"/>
                  <xs:enumeration value="mailing"/>
                  <xs:enumeration value="identity-service"/>
                  <xs:enumeration value="iot_gateway"/>
                </xs:restriction></xs:simpleType>
              </xs:element>
              <xs:element name="type">
                <xs:simpleType><xs:restriction base="xs:string">
                  <xs:enumeration value="log"/>
                </xs:restriction></xs:simpleType>
              </xs:element>
              <xs:element name="version">
                <xs:simpleType><xs:restriction base="xs:string">
                  <xs:enumeration value="2.0"/>
                </xs:restriction></xs:simpleType>
              </xs:element>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
        <xs:element name="body">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="level">
                <xs:simpleType><xs:restriction base="xs:string">
                  <xs:enumeration value="info"/>
                  <xs:enumeration value="warning"/>
                  <xs:enumeration value="error"/>
                </xs:restriction></xs:simpleType>
              </xs:element>
              <xs:element name="action">
                <xs:simpleType><xs:restriction base="xs:string">
                  <xs:enumeration value="registration"/>
                  <xs:enumeration value="user"/>
                  <xs:enumeration value="payment"/>
                  <xs:enumeration value="invoice"/>
                  <xs:enumeration value="session"/>
                  <xs:enumeration value="calendar"/>
                  <xs:enumeration value="email"/>
                  <xs:enumeration value="wallet"/>
                  <xs:enumeration value="refund"/>
                  <xs:enumeration value="identity"/>
                  <xs:enumeration value="xml_validation"/>
                  <xs:enumeration value="system_error"/>
                  <xs:enumeration value="badge"/>
                </xs:restriction></xs:simpleType>
              </xs:element>
              <xs:element name="message" type="xs:string"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
```

### Voorbeeld XML

```xml
<message>
  <header>
    <message_id>b2c3d4e5-f6a7-8901-bcde-f12345678901</message_id>
    <timestamp>2026-04-24T10:30:00Z</timestamp>
    <source>kassa</source>
    <type>log</type>
    <version>2.0</version>
  </header>
  <body>
    <level>info</level>
    <action>payment</action>
    <message>Payment processed successfully for badge 12345</message>
  </body>
</message>
```

---

## 4. Monitoring → Mailing — Alert

- **Exchange:** `""` (AMQP default exchange)
- **Queue:** `to_mailing` (durable)
- **Wanneer:** Een systeem is down gegaan (heartbeat timeout — geen heartbeat ontvangen in meer dan 3 seconden)

> **Opmerking:** Dit is een intern formaat tussen de Monitoring-detector en Mailing. Het gebruikt een platte `<alert>` root in plaats van de standaard `<message>` envelop — dit is een geoorloofde uitzondering voor deze interne flow. Ook al breekt dit Regel 1, het Monitoring-team mag hiervan afwijken voor interne berichten die niet door andere teams geconsumeerd worden.

### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="alert">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="type"      type="xs:string" fixed="HEARTBEAT_CRITICAL"/>
        <xs:element name="system"    type="xs:string"/>
        <xs:element name="message"   type="xs:string"/>
        <xs:element name="timestamp" type="xs:dateTime"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
```

### Voorbeeld XML

```xml
<alert>
  <type>HEARTBEAT_CRITICAL</type>
  <system>facturatie</system>
  <message>Systeem facturatie heeft al meer dan 3s geen heartbeat gestuurd.</message>
  <timestamp>2026-05-07T18:35:12Z</timestamp>
</alert>
```

---

## 5. Frontend → CRM

- **Queue:** `crm.incoming`

### 5.1 `new_registration`

Wanneer een nieuwe persoon zich inschrijft via de website.

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType><xs:sequence>

      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id"     type="UUIDType"/>
          <xs:element name="timestamp"      type="xs:dateTime"/>
          <xs:element name="source"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="frontend"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="new_registration"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="version"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="2.0"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="correlation_id" type="UUIDType"/>
        </xs:sequence></xs:complexType>
      </xs:element>

      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <xs:element name="customer">
            <xs:complexType><xs:sequence>
              <!-- identity_uuid: de master_uuid van de Identity Service -->
              <xs:element name="identity_uuid" type="UUIDType"/>
              <xs:element name="email"         type="xs:string"/>
              <xs:element name="type"          type="xs:string"/>
              <xs:element name="is_company_linked" type="xs:boolean"/>
              <xs:element name="vat_number"    type="xs:string" minOccurs="0"/>
              <xs:element name="date_of_birth" type="xs:date"/>
              <xs:element name="contact">
                <xs:complexType><xs:sequence>
                  <xs:element name="first_name" type="xs:string"/>
                  <xs:element name="last_name"  type="xs:string"/>
                </xs:sequence></xs:complexType>
              </xs:element>
              <xs:element name="address" type="xs:string"/>
              <xs:element name="company_id" type="xs:string" minOccurs="0"/>
              <xs:element name="payment_due">
                <xs:complexType><xs:sequence>
                  <xs:element name="amount">
                    <xs:complexType><xs:simpleContent><xs:extension base="xs:decimal">
                      <xs:attribute name="currency" type="xs:string" fixed="eur" use="required"/>
                    </xs:extension></xs:simpleContent></xs:complexType>
                  </xs:element>
                  <xs:element name="status" type="xs:string" fixed="unpaid"/>
                </xs:sequence></xs:complexType>
              </xs:element>
            </xs:sequence></xs:complexType>
          </xs:element>
        </xs:sequence></xs:complexType>
      </xs:element>

    </xs:sequence></xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML

```xml
<message>
  <header>
    <message_id>c3d4e5f6-a7b8-9012-cdef-012345678902</message_id>
    <timestamp>2026-04-24T09:15:00Z</timestamp>
    <source>frontend</source>
    <type>new_registration</type>
    <version>2.0</version>
    <correlation_id>c3d4e5f6-a7b8-9012-cdef-012345678902</correlation_id>
  </header>
  <body>
    <customer>
      <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
      <email>jan.peeters@ehb.be</email>
      <type>private</type>
      <is_company_linked>false</is_company_linked>
      <date_of_birth>1995-03-21</date_of_birth>
      <contact>
        <first_name>Jan</first_name>
        <last_name>Peeters</last_name>
      </contact>
      <address>Nijverheidskaai 170, 1070 Brussel</address>
      <payment_due>
        <amount currency="eur">0.00</amount>
        <status>unpaid</status>
      </payment_due>
    </customer>
  </body>
</message>
```

> ** Tip voor Frontend:** Stuur `payment_due` altijd mee. Bij een gratis sessie: `<amount currency="eur">0.00</amount>` met status `unpaid`. CRM gebruikt dit om Kassa en Facturatie te informeren over het verschuldigde bedrag.


---

### 5.2 `user_updated`

Wanneer een gebruiker zijn profiel wijzigt.

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id"     type="UUIDType"/>
          <xs:element name="timestamp"      type="xs:dateTime"/>
          <xs:element name="source"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="frontend"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="user_updated"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="version"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="2.0"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="correlation_id" type="UUIDType" minOccurs="0"/>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <xs:element name="customer">
            <xs:complexType><xs:sequence>
              <!-- identity_uuid: de master_uuid van de Identity Service -->
              <xs:element name="identity_uuid" type="UUIDType"/>
              <xs:element name="email"         type="xs:string"/>
              <xs:element name="date_of_birth" type="xs:date" minOccurs="0"/>
              <xs:element name="contact">
                <xs:complexType><xs:sequence>
                  <xs:element name="first_name" type="xs:string"/>
                  <xs:element name="last_name"  type="xs:string"/>
                </xs:sequence></xs:complexType>
              </xs:element>
              <xs:element name="type">
                <xs:simpleType><xs:restriction base="xs:string">
                  <xs:enumeration value="private"/>
                  <xs:enumeration value="company"/>
                </xs:restriction></xs:simpleType>
              </xs:element>
              <xs:element name="company_name" type="xs:string" minOccurs="0"/>
              <xs:element name="vat_number"   type="xs:string" minOccurs="0"/>
              <xs:element name="company_id"   type="xs:string" minOccurs="0"/>
            </xs:sequence></xs:complexType>
          </xs:element>
        </xs:sequence></xs:complexType>
      </xs:element>
    </xs:sequence></xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML

```xml
<message>
  <header>
    <message_id>d4e5f6a7-b8c9-0123-defa-123456789003</message_id>
    <timestamp>2026-04-24T11:00:00Z</timestamp>
    <source>frontend</source>
    <type>user_updated</type>
    <version>2.0</version>
  </header>
  <body>
    <customer>
      <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
      <email>jan.peeters.nieuw@ehb.be</email>
      <contact>
        <first_name>Jan</first_name>
        <last_name>Peeters</last_name>
      </contact>
      <type>private</type>
    </customer>
  </body>
</message>
```

---

### 5.3 `user_deleted`

Wanneer een account volledig wordt verwijderd.  
> **Naamwijziging:** was `user.unregistered` → nu `user_deleted` (snake_case, duidelijker).

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id"     type="UUIDType"/>
          <xs:element name="timestamp"      type="xs:dateTime"/>
          <xs:element name="source"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="frontend"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="user_deleted"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="version"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="2.0"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="correlation_id" type="UUIDType" minOccurs="0"/>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <!-- identity_uuid: de master_uuid van de Identity Service -->
          <xs:element name="identity_uuid" type="UUIDType"/>
          <xs:element name="email"         type="xs:string"/>
          <xs:element name="reason"        type="xs:string" minOccurs="0"/>
        </xs:sequence></xs:complexType>
      </xs:element>
    </xs:sequence></xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML

```xml
<message>
  <header>
    <message_id>e5f6a7b8-c9d0-1234-efab-234567890004</message_id>
    <timestamp>2026-04-24T14:22:00Z</timestamp>
    <source>frontend</source>
    <type>user_deleted</type>
    <version>2.0</version>
  </header>
  <body>
    <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
    <email>jan.peeters@ehb.be</email>
    <reason>Account op verzoek van gebruiker verwijderd</reason>
  </body>
</message>
```

---

### 5.4 `user_created`

Wanneer een nieuw gebruikersaccount wordt aangemaakt zonder directe sessie-inschrijving (profile-only). Voor sessie-inschrijvingen gebruik je `new_registration` (§5.1).

> **Volgorde t.o.v. Identity Service:** dit bericht wordt pas gepubliceerd nadat Frontend de `master_uuid` heeft opgehaald via de Identity RPC (`identity.user.create.request`, zie §15.1). Identity zelf broadcast óók een `user_event` (UserCreated) op de `user.events` fanout (§15.5) — dit `user_created` bericht naar CRM is een aanvumbling met de profielvelden die Identity niet heeft (naam, geboortedatum, bedrijfsdata).

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id"     type="UUIDType"/>
          <xs:element name="timestamp"      type="xs:dateTime"/>
          <xs:element name="source"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="frontend"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="user_created"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="version"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="2.0"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="correlation_id" type="UUIDType" minOccurs="0"/>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <xs:element name="customer">
            <xs:complexType><xs:sequence>
              <!-- identity_uuid: de master_uuid van de Identity Service -->
              <xs:element name="identity_uuid" type="UUIDType"/>
              <xs:element name="email"         type="xs:string"/>
              <xs:element name="date_of_birth" type="xs:date"/>
              <xs:element name="contact">
                <xs:complexType><xs:sequence>
                  <xs:element name="first_name" type="xs:string"/>
                  <xs:element name="last_name"  type="xs:string"/>
                </xs:sequence></xs:complexType>
              </xs:element>
              <xs:element name="type">
                <xs:simpleType><xs:restriction base="xs:string">
                  <xs:enumeration value="private"/>
                  <xs:enumeration value="company"/>
                </xs:restriction></xs:simpleType>
              </xs:element>
              <xs:element name="company_name" type="xs:string" minOccurs="0"/>
              <xs:element name="vat_number"   type="xs:string" minOccurs="0"/>
              <xs:element name="company_id"   type="xs:string" minOccurs="0"/>
            </xs:sequence></xs:complexType>
          </xs:element>
        </xs:sequence></xs:complexType>
      </xs:element>
    </xs:sequence></xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML — particulier

```xml
<message>
  <header>
    <message_id>1a2b3c4d-5e6f-7890-1234-567890abcdef</message_id>
    <timestamp>2026-04-24T09:14:00Z</timestamp>
    <source>frontend</source>
    <type>user_created</type>
    <version>2.0</version>
  </header>
  <body>
    <customer>
      <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
      <email>jan.peeters@ehb.be</email>
      <date_of_birth>1995-03-21</date_of_birth>
      <contact>
        <first_name>Jan</first_name>
        <last_name>Peeters</last_name>
      </contact>
      <type>private</type>
    </customer>
  </body>
</message>
```

#### Voorbeeld XML — bedrijf

```xml
<message>
  <header>
    <message_id>2b3c4d5e-6f70-8901-2345-67890abcdef0</message_id>
    <timestamp>2026-04-24T09:14:00Z</timestamp>
    <source>frontend</source>
    <type>user_created</type>
    <version>2.0</version>
  </header>
  <body>
    <customer>
      <identity_uuid>f9c38d2e-5f3b-4c4f-ad6f-234567890bcd</identity_uuid>
      <email>info@ehb.be</email>
      <date_of_birth>1980-01-01</date_of_birth>
      <contact>
        <first_name>An</first_name>
        <last_name>Janssens</last_name>
      </contact>
      <type>company</type>
      <company_name>Erasmushogeschool Brussel</company_name>
      <vat_number>BE0876543210</vat_number>
      <company_id>ehb-001</company_id>
    </customer>
  </body>
</message>
```

> **Voor CRM:** Maak/update een Salesforce Contact met deze velden. Géén sessie-inschrijving aanmaken — dat gebeurt later via `new_registration` (§5.1) als de gebruiker zich daadwerkelijk inschrijft op een sessie.

---

### 5.5 `user_registered`

Wanneer een gebruiker zich inschrijft voor een specifieke festivalsessie. Bevat sessie-details en initiële betaalstatus.  
> **Naamwijziging:** was `user.registered` → nu `user_registered` (snake_case, v2.0 standaard).  
> **Queue-correctie:** was `frontend.user.registered` → nu `crm.incoming`.

**Queue:** `crm.incoming`  
**Richting:** Frontend → CRM

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id"     type="UUIDType"/>
          <xs:element name="timestamp"      type="xs:dateTime"/>
          <xs:element name="source"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="frontend"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="user_registered"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="version"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="2.0"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="correlation_id" type="UUIDType" minOccurs="0"/>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <xs:element name="customer">
            <xs:complexType><xs:sequence>
              <!-- identity_uuid: de master_uuid van de Identity Service -->
              <xs:element name="identity_uuid" type="UUIDType"/>
              <xs:element name="email"         type="xs:string"/>
              <xs:element name="contact">
                <xs:complexType><xs:sequence>
                  <xs:element name="first_name" type="xs:string"/>
                  <xs:element name="last_name"  type="xs:string"/>
                </xs:sequence></xs:complexType>
              </xs:element>
              <xs:element name="type">
                <xs:simpleType><xs:restriction base="xs:string">
                  <xs:enumeration value="private"/>
                  <xs:enumeration value="company"/>
                </xs:restriction></xs:simpleType>
              </xs:element>
              <!-- Verplicht wanneer type=company -->
              <xs:element name="company_name" type="xs:string" minOccurs="0"/>
              <xs:element name="vat_number"   type="xs:string" minOccurs="0"/>
              <xs:element name="session_id"    type="xs:string"/>
            </xs:sequence></xs:complexType>
          </xs:element>
          <xs:element name="session_title"   type="xs:string" minOccurs="0"/>
          <xs:element name="payment_status">
            <xs:simpleType><xs:restriction base="xs:string">
              <xs:enumeration value="pending"/>
              <xs:enumeration value="paid"/>
            </xs:restriction></xs:simpleType>
          </xs:element>
        </xs:sequence></xs:complexType>
      </xs:element>
    </xs:sequence></xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML (particulier)

```xml
<message>
  <header>
    <message_id>a1b2c3d4-e5f6-7890-abcd-ef1234567890</message_id>
    <timestamp>2026-05-01T10:00:00Z</timestamp>
    <source>frontend</source>
    <type>user_registered</type>
    <version>2.0</version>
    <correlation_id>a1b2c3d4-e5f6-7890-abcd-ef1234567890</correlation_id>
  </header>
  <body>
    <customer>
      <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
      <email>jan.peeters@ehb.be</email>
      <contact>
        <first_name>Jan</first_name>
        <last_name>Peeters</last_name>
      </contact>
      <type>private</type>
      <session_id>sess-2026-mainstage-01</session_id>
    </customer>
    <payment_status>pending</payment_status>
  </body>
</message>
```

#### Voorbeeld XML (bedrijf)

```xml
<message>
  <header>
    <message_id>b2c3d4e5-f6a7-8901-bcde-f01234567891</message_id>
    <timestamp>2026-05-01T10:05:00Z</timestamp>
    <source>frontend</source>
    <type>user_registered</type>
    <version>2.0</version>
    <correlation_id>b2c3d4e5-f6a7-8901-bcde-f01234567891</correlation_id>
  </header>
  <body>
    <customer>
      <identity_uuid>f9c38d2e-5f3b-4c4f-ad6f-234567890bcd</identity_uuid>
      <email>marie.desmet@acme.be</email>
      <contact>
        <first_name>Marie</first_name>
        <last_name>Desmet</last_name>
      </contact>
      <type>company</type>
      <company_name>Acme NV</company_name>
      <vat_number>BE0123456789</vat_number>
      <session_id>sess-2026-workshop-04</session_id>
    </customer>
    <payment_status>pending</payment_status>
  </body>
</message>
```

---

### 5.6 `cancel_registration` (Frontend → CRM)

Wanneer een gebruiker zijn inschrijving annuleert via de website.

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id"     type="UUIDType"/>
          <xs:element name="timestamp"      type="xs:dateTime"/>
          <xs:element name="source"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="frontend"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="cancel_registration"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="version"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="2.0"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="correlation_id" type="UUIDType"/>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <xs:element name="identity_uuid" type="UUIDType"/>
          <xs:element name="session_id"    type="xs:string"/>
          <xs:element name="reason"        type="xs:string" minOccurs="0"/>
        </xs:sequence></xs:complexType>
      </xs:element>
    </xs:sequence></xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML

```xml
<message>
  <header>
    <message_id>c3a0b1c2-d3e4-5678-abcd-678901200018</message_id>
    <timestamp>2026-05-10T14:30:00Z</timestamp>
    <source>frontend</source>
    <type>cancel_registration</type>
    <version>2.0</version>
    <correlation_id>c3d4e5f6-a7b8-9012-cdef-012345678901</correlation_id>
  </header>
  <body>
    <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
    <session_id>sess-keynote-001</session_id>
    <reason>Dubbele boeking per ongeluk</reason>
  </body>
</message>
```

---

### 5.7 `event_ended`

Wanneer een sessie of event is afgelopen.

- **Queue:** `event.ended`
- **Richting:** Frontend → CRM

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" elementFormDefault="qualified">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id"     type="UUIDType"/>
          <xs:element name="timestamp"      type="xs:dateTime"/>
          <xs:element name="source"         type="xs:string" fixed="frontend"/>
          <xs:element name="type"           type="xs:string" fixed="event_ended"/>
          <xs:element name="version"        type="xs:string" fixed="2.0"/>
          <xs:element name="correlation_id" type="UUIDType" minOccurs="0"/>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <xs:element name="session_id" type="xs:string"/>
          <xs:element name="ended_at"   type="xs:dateTime"/>
        </xs:sequence></xs:complexType>
      </xs:element>
    </xs:sequence></xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML

```xml
<message>
  <header>
    <message_id>b3a8c7d6-e5f4-3210-abcd-ef1234567890</message_id>
    <timestamp>2026-05-15T22:00:00Z</timestamp>
    <source>frontend</source>
    <type>event_ended</type>
    <version>2.0</version>
  </header>
  <body>
    <session_id>sess-keynote-001</session_id>
    <ended_at>2026-05-15T22:00:00Z</ended_at>
  </body>
</message>
```

---

### 5.8 `company_member_removed` (Frontend → CRM)

Wanneer een bedrijfsbeheerder een uitnodiging intrekt voordat de gebruiker zich heeft geregistreerd, of wanneer een lid van een bedrijf handmatig wordt ontkoppeld. Dit bericht instrueert CRM om de koppeling tussen de gebruiker (`identity_uuid`) en het bedrijf (`company_id`) te verwijderen.

- **Queue:** `crm.incoming`
- **Richting:** Frontend → CRM

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id"     type="UUIDType"/>
          <xs:element name="timestamp"      type="xs:dateTime"/>
          <xs:element name="source"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="frontend"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="company_member_removed"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="version"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="2.0"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="correlation_id" type="UUIDType" minOccurs="0"/>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <xs:element name="customer">
            <xs:complexType><xs:sequence>
              <xs:element name="identity_uuid" type="UUIDType"/>
              <xs:element name="email"         type="xs:string"/>
              <xs:element name="company_id"   type="xs:string"/>
              <xs:element name="reason">
                <xs:simpleType><xs:restriction base="xs:string">
                  <xs:enumeration value="invite_revoked"/>
                  <xs:enumeration value="admin_removed"/>
                </xs:restriction></xs:simpleType>
              </xs:element>
            </xs:sequence></xs:complexType>
          </xs:element>
        </xs:sequence></xs:complexType>
      </xs:element>
    </xs:sequence></xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML

```xml
<message>
  <header>
    <message_id>a1b2c3d4-e5f6-7890-abcd-ef1234567890</message_id>
    <timestamp>2026-05-08T14:30:00Z</timestamp>
    <source>frontend</source>
    <type>company_member_removed</type>
    <version>2.0</version>
  </header>
  <body>
    <customer>
      <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
      <email>uitgenodigde@example.com</email>
      <company_id>uid-3</company_id>
      <reason>invite_revoked</reason>
    </customer>
  </body>
</message>
```

#### Verwacht Gedrag CRM
1. Zoek de gebruiker op via `identity_uuid`.
2. Verwijder de koppeling tussen de gebruiker en het bedrijf (`company_id`).
3. **Zet het gebruikerstype terug naar `private`** als er geen andere bedrijfskoppeling meer overblijft voor deze gebruiker.
4. Als de gebruiker nog geen account heeft aangemaakt (invite was pending), verwijdert CRM de pre-registratie.
5. Log de actie met de meegeleverde `reason`.

---

### 5.9 `company_registration` (Frontend → CRM)

Wanneer een nieuw bedrijf wordt geregistreerd via de frontend. CRM slaat de bedrijfsgegevens op in Salesforce.

- **Queue:** `crm.incoming`
- **Richting:** Frontend → CRM

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">

  <xs:simpleType name="guid">
    <xs:restriction base="xs:string">
      <xs:pattern value="[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType>
      <xs:sequence>

        <xs:element name="header">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="message_id" type="guid"/>
              <xs:element name="timestamp" type="xs:dateTime"/>
              <xs:element name="source" type="xs:string"/>
              <xs:element name="type" type="xs:string"/>
              <xs:element name="version" type="xs:decimal"/>
              <xs:element name="master_uuid" type="guid"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>

        <xs:element name="body">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="company">
                <xs:complexType>
                  <xs:sequence>
                    <xs:element name="master_uuid" type="guid"/>
                    <xs:element name="name" type="xs:string"/>
                    <xs:element name="email" type="xs:string"/>
                    <xs:element name="vat_number">
                      <xs:simpleType>
                        <xs:restriction base="xs:string">
                          <xs:pattern value="[A-Z]{2}[0-9]{10}"/>
                        </xs:restriction>
                      </xs:simpleType>
                    </xs:element>
                    <xs:element name="vat_rate" type="xs:integer"/>
                  </xs:sequence>
                </xs:complexType>
              </xs:element>
            </xs:sequence>
          </xs:complexType>
        </xs:element>

      </xs:sequence>
    </xs:complexType>
  </xs:element>

</xs:schema>
```

#### Voorbeeld XML

```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>11111111-1111-1111-1111-111111111111</message_id>
    <timestamp>2026-05-09T09:51:49Z</timestamp>
    <source>frontend</source>
    <type>company_registration</type>
    <version>2.0</version>
    <master_uuid>aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa</master_uuid>
  </header>
  <body>
    <company>
      <master_uuid>aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa</master_uuid>
      <name>Acme BV</name>
      <email>info@acme.be</email>
      <vat_number>BE0123456789</vat_number>
      <vat_rate>21</vat_rate>
    </company>
  </body>
</message>
```

#### Verwacht Gedrag CRM
1. Valideer het bericht tegen de XSD.
2. Maak een nieuw bedrijfsprofiel aan in Salesforce op basis van `master_uuid`.
3. Sla naam, e-mail, BTW-nummer en BTW-tarief op.

> **Opmerking:** De `master_uuid` in de header en in `<company>` zijn identiek — dit is de unieke identifier van het bedrijf.

---

### 5.10 `company_update` (Frontend → CRM)

Wanneer bedrijfsgegevens worden gewijzigd of leden worden toegevoegd/verwijderd. CRM past het bedrijfsprofiel in Salesforce aan en beheert de personeelslijst op basis van de meegestuurde member-acties.

- **Queue:** `crm.incoming`
- **Richting:** Frontend → CRM

> **Aandacht:** Er bestaat ook een `company_member_removed` bericht (§5.8) dat uitsluitend dient voor het ontkoppelen van leden. `company_update` is breder: het combineert veldwijzigingen én ledenwijzigingen in één bericht. Teams die enkel een lid willen verwijderen kunnen `company_member_removed` blijven gebruiken; voor gecombineerde updates is `company_update` de aangewezen weg.

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">

  <xs:simpleType name="guid">
    <xs:restriction base="xs:string">
      <xs:pattern value="[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:simpleType name="memberAction">
    <xs:restriction base="xs:string">
      <xs:enumeration value="add"/>
      <xs:enumeration value="remove"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType>
      <xs:sequence>

        <xs:element name="header">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="message_id" type="guid"/>
              <xs:element name="timestamp" type="xs:dateTime"/>
              <xs:element name="source" type="xs:string"/>
              <xs:element name="type" type="xs:string"/>
              <xs:element name="version" type="xs:decimal"/>
              <xs:element name="master_uuid" type="guid"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>

        <xs:element name="body">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="company">
                <xs:complexType>
                  <xs:sequence>
                    <xs:element name="name" type="xs:string"/>
                    <xs:element name="email" type="xs:string"/>
                    <xs:element name="vat_number" type="xs:string"/>

                    <xs:element name="members" minOccurs="0">
                      <xs:complexType>
                        <xs:sequence>
                          <xs:element name="member" maxOccurs="unbounded">
                            <xs:complexType>
                              <xs:sequence>
                                <xs:element name="master_uuid" type="guid"/>
                                <xs:element name="action" type="memberAction"/>
                              </xs:sequence>
                            </xs:complexType>
                          </xs:element>
                        </xs:sequence>
                      </xs:complexType>
                    </xs:element>

                  </xs:sequence>
                </xs:complexType>
              </xs:element>
            </xs:sequence>
          </xs:complexType>
        </xs:element>

      </xs:sequence>
    </xs:complexType>
  </xs:element>

</xs:schema>
```

#### Voorbeeld XML

```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>22222222-2222-2222-2222-222222222222</message_id>
    <timestamp>2026-05-09T09:51:49Z</timestamp>
    <source>frontend</source>
    <type>company_update</type>
    <version>2.0</version>
    <master_uuid>aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa</master_uuid>
  </header>
  <body>
    <company>
      <name>Acme BVBA</name>
      <email>finance@acme.be</email>
      <vat_number>BE0123456789</vat_number>
      <members>
        <member>
          <master_uuid>bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb</master_uuid>
          <action>add</action>
        </member>
        <member>
          <master_uuid>cccccccc-cccc-cccc-cccc-cccccccccccc</master_uuid>
          <action>remove</action>
        </member>
      </members>
    </company>
  </body>
</message>
```

#### Verwacht Gedrag CRM
1. Zoek het bedrijf op via `master_uuid` in de header.
2. Werk naam, e-mail en BTW-nummer bij in Salesforce.
3. Verwerk elk `<member>` element: bij `add` wordt de medewerker gekoppeld aan het bedrijf, bij `remove` wordt de koppeling verbroken.
4. Negeer berichten met ontbrekende verplichte velden (`name`, `email`, `vat_number`).

---

### 5.11 `company_delete` (Frontend → CRM)

Wanneer een bedrijf verwijderd moet worden. CRM voert een soft delete uit in Salesforce zodat de gegevens herstelbaar blijven.

- **Queue:** `crm.incoming`
- **Richting:** Frontend → CRM

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">

  <xs:simpleType name="guid">
    <xs:restriction base="xs:string">
      <xs:pattern value="[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType>
      <xs:sequence>

        <xs:element name="header">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="message_id" type="guid"/>
              <xs:element name="timestamp" type="xs:dateTime"/>
              <xs:element name="source" type="xs:string"/>
              <xs:element name="type" type="xs:string"/>
              <xs:element name="version" type="xs:decimal"/>
              <xs:element name="master_uuid" type="guid"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>

        <xs:element name="body">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="company">
                <xs:complexType>
                  <xs:sequence>
                    <xs:element name="master_uuid" type="guid"/>
                  </xs:sequence>
                </xs:complexType>
              </xs:element>
            </xs:sequence>
          </xs:complexType>
        </xs:element>

      </xs:sequence>
    </xs:complexType>
  </xs:element>

</xs:schema>
```

#### Voorbeeld XML

```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>33333333-3333-3333-3333-333333333333</message_id>
    <timestamp>2026-05-09T09:51:49Z</timestamp>
    <source>frontend</source>
    <type>company_delete</type>
    <version>2.0</version>
    <master_uuid>aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa</master_uuid>
  </header>
  <body>
    <company>
      <master_uuid>aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa</master_uuid>
    </company>
  </body>
</message>
```

#### Verwacht Gedrag CRM
1. Zoek het bedrijf op via `master_uuid`.
2. Voer een **soft delete** uit — het bedrijfsprofiel wordt gemarkeerd als verwijderd maar blijft in Salesforce bewaard voor eventueel herstel.
3. Ontkoppel alle gekoppelde medewerkers van het bedrijf.

---

## 6. Kassa → CRM

- **Queue:** `crm.incoming`

### 6.1 `consumption_order`

Klant bestelt consumpties aan de bar. Schema v2.3 — bevat `sku`, `vat_rate` en `total_amount` per lijn.

> **� Koppeling met factuur:** De `message_id` van dit bericht wordt de `correlation_id` in het bijhorende `invoice_request` (zie 6.5). Zo koppelt Facturatie de juiste orderlijnen aan de factuur.

#### XSD (v2.3)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">

  <xs:complexType name="AddressType">
    <xs:sequence>
      <xs:element name="street"      type="xs:string"/>
      <xs:element name="number"      type="xs:string"/>
      <xs:element name="postal_code" type="xs:string"/>
      <xs:element name="city"        type="xs:string"/>
      <xs:element name="country"     type="xs:string"/>
    </xs:sequence>
  </xs:complexType>

  <xs:complexType name="CustomerType">
    <xs:sequence>
      <xs:element name="id"      type="xs:string" minOccurs="0"/>
      <xs:element name="identity_uuid" type="UUIDType" minOccurs="0"/>
      <xs:element name="type">
        <xs:simpleType>
          <xs:restriction base="xs:string">
            <xs:enumeration value="private"/>
            <xs:enumeration value="company"/>
          </xs:restriction>
        </xs:simpleType>
      </xs:element>
      <xs:element name="email"   type="xs:string"   minOccurs="0"/>
      <xs:element name="address" type="AddressType" minOccurs="0"/>
    </xs:sequence>
  </xs:complexType>

  <xs:complexType name="ItemType">
    <xs:sequence>
      <xs:element name="id"          type="xs:string"/>
      <xs:element name="sku"         type="xs:string"/>
      <xs:element name="description" type="xs:string"/>
      <!-- xs:integer: laat negatieve waarden toe voor kortingen/retouren -->
      <xs:element name="quantity"    type="xs:integer"/>
      <xs:element name="unit_price">
        <xs:complexType>
          <xs:simpleContent>
            <xs:extension base="xs:decimal">
              <xs:attribute name="currency" type="xs:string" fixed="eur" use="required"/>
            </xs:extension>
          </xs:simpleContent>
        </xs:complexType>
      </xs:element>
      <xs:element name="vat_rate">
        <xs:simpleType>
          <xs:restriction base="xs:integer">
            <xs:enumeration value="0"/>
            <xs:enumeration value="6"/>
            <xs:enumeration value="12"/>
            <xs:enumeration value="21"/>
          </xs:restriction>
        </xs:simpleType>
      </xs:element>
      <xs:element name="total_amount">
        <xs:complexType>
          <xs:simpleContent>
            <xs:extension base="xs:decimal">
              <xs:attribute name="currency" type="xs:string" fixed="eur" use="required"/>
            </xs:extension>
          </xs:simpleContent>
        </xs:complexType>
      </xs:element>
      <xs:element name="item_type"  type="xs:string"  minOccurs="0"/>
      <xs:element name="session_id" type="xs:integer" minOccurs="0"/>
    </xs:sequence>
  </xs:complexType>

  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="header">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="message_id" type="UUIDType"/>
              <xs:element name="timestamp"  type="xs:dateTime"/>
              <xs:element name="source"     type="xs:string" fixed="kassa"/>
              <xs:element name="type"       type="xs:string" fixed="consumption_order"/>
              <xs:element name="version"    type="xs:string" fixed="2.0"/>
              <xs:element name="correlation_id" type="UUIDType" minOccurs="0"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
        <xs:element name="body">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="is_anonymous" type="xs:boolean" minOccurs="0" default="false"/>
              <xs:element name="customer"     type="CustomerType" minOccurs="0"/>
              <xs:element name="items">
                <xs:complexType>
                  <xs:sequence>
                    <xs:element name="item" type="ItemType" maxOccurs="unbounded"/>
                  </xs:sequence>
                </xs:complexType>
              </xs:element>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
```

#### Business Logic Rules (Verplicht)
*   **Regel 1 (Top-ups):** Voor wallet-herladingen moet `item_type` de waarde `wallet_topup` hebben en `vat_rate` moet `0` zijn. Dit is een niet-belastbare financiële transactie.
*   **Regel 2 (Anoniem):** Als `is_anonymous` op `true` staat, wordt het `<customer>` blok weggelaten. In dit geval kan er later geen factuur worden aangevraagd; de klant ontvangt enkel een fysiek kasticket.
*   **Regel 3 (Sessie-items):** Als een item een sessieticket betreft, voegt Kassa een `<session_id>` toe met het numerieke ID van de bijhorende sessie. Horeca- en andere niet-sessie-items laten `<session_id>` weg. Eén bestelling kan een mix bevatten van sessie-items (met `session_id`) en overige items (zonder). Facturatie gebruikt `session_id` voor financiële rapportage per sessie.

#### Voorbeeld XML

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
      <id>12345</id>
      <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
      <type>company</type>
      <email>info@bedrijf.be</email>
      <address>
        <street>Kiekenmarkt</street>
        <number>42</number>
        <postal_code>1000</postal_code>
        <city>Brussel</city>
        <country>be</country>
      </address>
    </customer>
    <items>
      <!-- Sessieticket A: session_id aanwezig → Facturatie boekt €50 op sessie 1234 -->
      <item>
        <id>LINE-4201</id>
        <sku>SES-001</sku>
        <description>Workshop Python</description>
        <quantity>1</quantity>
        <unit_price currency="eur">50.00</unit_price>
        <vat_rate>21</vat_rate>
        <total_amount currency="eur">50.00</total_amount>
        <session_id>1234</session_id>
      </item>
      <!-- Sessieticket B: session_id aanwezig → Facturatie boekt €30 op sessie 5678 -->
      <item>
        <id>LINE-4202</id>
        <sku>SES-002</sku>
        <description>Lezing Design Thinking</description>
        <quantity>1</quantity>
        <unit_price currency="eur">30.00</unit_price>
        <vat_rate>21</vat_rate>
        <total_amount currency="eur">30.00</total_amount>
        <session_id>5678</session_id>
      </item>
      <!-- Horecaproduct: geen session_id → Facturatie boekt €5 als horeca-omzet -->
      <item>
        <id>LINE-4203</id>
        <sku>BEV-001</sku>
        <description>Koffie</description>
        <quantity>2</quantity>
        <unit_price currency="eur">2.50</unit_price>
        <vat_rate>6</vat_rate>
        <total_amount currency="eur">5.00</total_amount>
      </item>
    </items>
  </body>
</message>
```

---
### 6.2 `badge_assigned`

Een badge/QR-code wordt gekoppeld aan een klant bij de inkom.

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id" type="UUIDType"/>
          <xs:element name="timestamp"  type="xs:dateTime"/>
          <xs:element name="source"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="kassa"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="badge_assigned"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="version"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="2.0"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="correlation_id" type="UUIDType" minOccurs="0"/>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <!-- identity_uuid: de master_uuid van de Identity Service -->
          <xs:element name="identity_uuid" type="UUIDType"/>
          <xs:element name="badge_id"    type="xs:string"/>
          <xs:element name="assigned_at" type="xs:dateTime"/>
        </xs:sequence></xs:complexType>
      </xs:element>
    </xs:sequence></xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML

```xml
<message>
  <header>
    <message_id>07a8b9c0-d1e2-3456-abcd-456789000006</message_id>
    <timestamp>2026-05-15T18:05:00Z</timestamp>
    <source>kassa</source>
    <type>badge_assigned</type>
    <version>2.0</version>
  </header>
  <body>
    <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
    <badge_id>BADGE-0042</badge_id>
    <assigned_at>2026-05-15T18:05:00Z</assigned_at>
  </body>
</message>
```

---

### 6.3 `badge_scanned`

Een badge of QR-code wordt gescand aan de inkom of kassa.  
**Flow:** IoT (Raspberry Pi) of Kassa → Kassa  
**Routing Key:** `kassa.incoming`

> De body gebruikt `xs:choice` om exact één identifier af te dwingen: `badge_id` bij badge-scan, `identity_uuid` bij QR-scan. XSD 1.0 ondersteunt geen conditionele validatie op basis van elementwaarden, maar `xs:choice` dwingt de constraint "precies één van beide" correct af. Backward compatible: bestaande badge-berichten (enkel `badge_id`) zijn geldig als keuze-arm 1.

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id" type="UUIDType"/>
          <xs:element name="timestamp"  type="xs:dateTime"/>
          <xs:element name="source"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="iot_gateway"/>
            <xs:enumeration value="kassa"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="badge_scanned"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="version"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="2.0"/></xs:restriction></xs:simpleType></xs:element>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <xs:choice>
            <xs:element name="badge_id"      type="xs:string"/>
            <xs:element name="identity_uuid" type="UUIDType"/>
          </xs:choice>
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

#### Voorbeeld XML — badge-scan (bestaand scenario)

```xml
<message>
  <header>
    <message_id>18b9c0d1-e2f3-4567-bcde-567890100007</message_id>
    <timestamp>2026-05-15T18:06:30Z</timestamp>
    <source>iot_gateway</source>
    <type>badge_scanned</type>
    <version>2.0</version>
  </header>
  <body>
    <badge_id>BADGE-0042</badge_id>
    <location>entrance</location>
    <scanned_at>2026-05-15T18:06:30Z</scanned_at>
  </body>
</message>
```

#### Voorbeeld XML — QR-scan (nieuw scenario)

```xml
<message>
  <header>
    <message_id>29c0d1e2-f3a4-5678-cdef-678901200008</message_id>
    <timestamp>2026-05-15T18:06:35Z</timestamp>
    <source>kassa</source>
    <type>badge_scanned</type>
    <version>2.0</version>
  </header>
  <body>
    <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
    <location>entrance</location>
    <scanned_at>2026-05-15T18:06:35Z</scanned_at>
  </body>
</message>
```

---

### 6.4 `refund_processed`

Kassa stuurt dit bij elke terugbetaling. Routing key: `kassa.payments.refund`.

> **`correlation_id`:** message_id van de originele `payment_registered` die terugbetaald wordt.
>
> **`refund.method`:** `badge_wallet` is hier **wel** geldig (badge-saldo terugstorten). Anonieme refunds: altijd `cash` of `card_reversal`, nooit `badge_wallet`.
>
> **`new_wallet_balance`:** alleen aanwezig bij method=`badge_wallet` — het nieuwe saldo na de terugboeking.

#### XSD (conform Kassa schema_refund_processed.xsd)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">

  <xs:complexType name="CurrencyAmountType">
    <xs:simpleContent>
      <xs:extension base="xs:decimal">
        <xs:attribute name="currency" type="xs:string" fixed="eur" use="required"/>
      </xs:extension>
    </xs:simpleContent>
  </xs:complexType>

  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="header">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="message_id"     type="UUIDType"/>
              <xs:element name="timestamp"      type="xs:dateTime"/>
              <xs:element name="source"><xs:simpleType><xs:restriction base="xs:string">
                <xs:enumeration value="kassa"/></xs:restriction></xs:simpleType></xs:element>
              <xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
                <xs:enumeration value="refund_processed"/></xs:restriction></xs:simpleType></xs:element>
              <xs:element name="version"><xs:simpleType><xs:restriction base="xs:string">
                <xs:enumeration value="2.0"/></xs:restriction></xs:simpleType></xs:element>
              <xs:element name="correlation_id" type="UUIDType" minOccurs="0"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
        <xs:element name="body">
          <xs:complexType>
            <xs:sequence>
              <!-- identity_uuid optioneel: anonieme refunds hebben geen identity_uuid -->
              <xs:element name="identity_uuid" type="UUIDType" minOccurs="0"/>
              <xs:element name="refund_type">
                <xs:simpleType>
                  <xs:restriction base="xs:string">
                    <xs:enumeration value="consumption_item"/>
                    <xs:enumeration value="partial"/>
                  </xs:restriction>
                </xs:simpleType>
              </xs:element>
              <xs:element name="refund">
                <xs:complexType>
                  <xs:sequence>
                    <xs:element name="amount" type="CurrencyAmountType"/>
                    <xs:element name="method">
                      <xs:simpleType>
                        <xs:restriction base="xs:string">
                          <!-- badge_wallet: saldo terugstorten op badge -->
                          <xs:enumeration value="badge_wallet"/>
                          <xs:enumeration value="cash"/>
                          <xs:enumeration value="card_reversal"/>
                        </xs:restriction>
                      </xs:simpleType>
                    </xs:element>
                    <xs:element name="reason">
                      <xs:simpleType>
                        <xs:restriction base="xs:string">
                          <xs:enumeration value="duplicate_payment"/>
                          <xs:enumeration value="customer_request"/>
                          <xs:enumeration value="system_error"/>
                        </xs:restriction>
                      </xs:simpleType>
                    </xs:element>
                    <xs:element name="description" type="xs:string" minOccurs="0"/>
                  </xs:sequence>
                </xs:complexType>
              </xs:element>
              <!-- original_transaction_id: transaction.id van de originele payment_registered -->
              <xs:element name="original_transaction_id" type="xs:string"/>
              <!-- new_wallet_balance: alleen aanwezig bij method=badge_wallet -->
              <xs:element name="new_wallet_balance" type="CurrencyAmountType" minOccurs="0"/>
              <!-- items optioneel: welke artikelen terugbetaald werden -->
              <xs:element name="items" minOccurs="0">
                <xs:complexType>
                  <xs:sequence>
                    <xs:element name="item" maxOccurs="unbounded">
                      <xs:complexType>
                        <xs:sequence>
                          <xs:element name="sku"          type="xs:string"/>
                          <xs:element name="description"  type="xs:string"/>
                          <xs:element name="quantity"     type="xs:integer"/>
                          <xs:element name="unit_price"   type="CurrencyAmountType"/>
                          <xs:element name="total_amount" type="CurrencyAmountType"/>
                          <xs:element name="vat_rate"     type="xs:integer" minOccurs="0"/>
                        </xs:sequence>
                      </xs:complexType>
                    </xs:element>
                  </xs:sequence>
                </xs:complexType>
              </xs:element>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
```

#### Business Logic Rules
*   **Regel 1 (Saldo Update):** Als de `method` gelijk is aan `badge_wallet`, zal Kassa ook een `wallet_balance_update` bericht broadcasten naar de Frontend.

#### Voorbeeld XML — badge_wallet refund

```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>f15e0000-0000-0000-0000-000000000005</message_id>
    <timestamp>2026-05-15T16:45:00Z</timestamp>
    <source>kassa</source>
    <type>refund_processed</type>
    <version>2.0</version>
    <correlation_id>f14d0000-0000-0000-0000-000000000004</correlation_id>
  </header>
  <body>
    <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
    <refund_type>consumption_item</refund_type>
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

#### Voorbeeld XML — anonieme cash refund

```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>30d1e2f3-a4b5-6789-defa-789012300009</message_id>
    <timestamp>2026-05-15T20:15:00Z</timestamp>
    <source>kassa</source>
    <type>refund_processed</type>
    <version>2.0</version>
    <correlation_id>8fc6d7e8-f9a0-1234-cdef-234567800014</correlation_id>
  </header>
  <body>
    <!-- geen identity_uuid bij anonieme terugbetaling -->
    <refund_type>consumption_item</refund_type>
    <refund>
      <amount currency="eur">5.00</amount>
      <method>cash</method>
      <reason>customer_request</reason>
    </refund>
    <original_transaction_id>TRX-987654</original_transaction_id>
  </body>
</message>
```

> **Na badge_wallet refund:** stuur ook `wallet_balance_update` naar `frontend.payments` (routing: `kassa.frontend.wallet`) met het bijgewerkte saldo.
### 6.5 `invoice_request` (Kassa → CRM)

Kassa vraagt een factuur aan voor een bedrijf. De koppeling met de bijhorende `consumption_order` gebeurt via de `correlation_id` in de header.

> ** Uitzondering op Regel 2:** Dit bericht gebruikt een `<invoice_data>` wrapper in plaats van `<contact>` voor de naam. Dit komt overeen met de werkelijke Kassa-code (Odoo POS) en CRM-receiver. Andere berichten blijven de `<contact>` nesting gebruiken.

> **� Koppeling:** `correlation_id` = de `message_id` van het bijhorende `consumption_order` bericht.

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">

  <xs:complexType name="AddressType">
    <xs:sequence>
      <xs:element name="street"      type="xs:string"/>
      <xs:element name="number"      type="xs:string"/>
      <xs:element name="postal_code" type="xs:string"/>
      <xs:element name="city"        type="xs:string"/>
      <xs:element name="country"     type="xs:string"/>
    </xs:sequence>
  </xs:complexType>

  <xs:complexType name="InvoiceDataType">
    <xs:sequence>
      <xs:element name="contact">
        <xs:complexType>
          <xs:sequence>
            <xs:element name="first_name"  type="xs:string"/>
            <xs:element name="last_name"   type="xs:string"/>
          </xs:sequence>
        </xs:complexType>
      </xs:element>
      <xs:element name="email"       type="xs:string"/>
      <xs:element name="address"     type="AddressType"/>
      <xs:element name="vat_number"  type="xs:string" minOccurs="0"/>
    </xs:sequence>
  </xs:complexType>

  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="header">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="message_id"    type="UUIDType"/>
              <xs:element name="timestamp"     type="xs:dateTime"/>
              <xs:element name="source"><xs:simpleType><xs:restriction base="xs:string">
                <xs:enumeration value="kassa"/></xs:restriction></xs:simpleType></xs:element>
              <xs:element name="type"          type="xs:string" fixed="invoice_request"/>
              <xs:element name="version"       type="xs:string" fixed="2.0"/>
              <!-- correlation_id = message_id van het consumption_order bericht -->
              <xs:element name="correlation_id" type="UUIDType"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
        <xs:element name="body">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="identity_uuid" type="UUIDType"/>
              <xs:element name="payment_status">
                <xs:simpleType><xs:restriction base="xs:string">
                  <xs:enumeration value="paid"/>
                  <xs:enumeration value="pending"/>
                </xs:restriction></xs:simpleType>
              </xs:element>
              <xs:element name="payment_method" type="xs:string" minOccurs="0"/>
              <xs:element name="invoice_data" type="InvoiceDataType"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML

```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>b12c3d4e-5f6a-7890-bcde-f01234567890</message_id>
    <timestamp>2026-05-15T20:00:00Z</timestamp>
    <source>kassa</source>
    <type>invoice_request</type>
    <version>2.0</version>
    <correlation_id>f47ac10b-58cc-4372-a567-0e02b2c3d479</correlation_id>
  </header>
  <body>
    <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
    <payment_status>paid</payment_status>
    <payment_method>cash</payment_method>
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

---

### 6.6 `payment_registered` (Kassa → RabbitMQ)

Kassa stuurt dit na elke afgeronde kassatransactie.

- **consumption** → routing key `kassa.payments.consumption` (samen met `consumption_order`)
- **registration** → routing key `kassa.payments.registration` (inschrijvingsgeld aan kassa)

> **`identity_uuid` & `invoice.id`:** Deze zijn optioneel (`minOccurs="0"`) om "anonieme" kassabetalingen of betalingen waarvoor de CRM-sync nog niet is afgerond te ondersteunen. In dat geval koppelt Facturatie de betaling aan een generieke "Bar Klant" in FossBilling.
>
> **`correlation_id`:** bij consumption = `message_id` van de bijhorende `consumption_order`. Bij registration = `message_id` van de originele `new_registration`.
>
> **`payment_method`:** `company_link` (bedrijfsrekening), `on_site` (cash/kaart/badge wallet), `online`.
>
> **`invoice.id`:** optioneel — afwezig bij `registration` (CRM maakt factuur aan). Aanwezig bij `consumption`.
>
> **`identity_uuid`** op body-niveau: optioneel bij consumptie, verplicht bij registratie.

#### XSD (v2.1 — conform Kassa schema_payment_registered_v2.1.xsd)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">

  <xs:complexType name="CurrencyAmountType">
    <xs:simpleContent>
      <xs:extension base="xs:decimal">
        <xs:attribute name="currency" type="xs:string" fixed="eur" use="required"/>
      </xs:extension>
    </xs:simpleContent>
  </xs:complexType>

  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="header">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="message_id"     type="UUIDType"/>
              <xs:element name="timestamp"      type="xs:dateTime"/>
              <xs:element name="source"         type="xs:string"/>
              <xs:element name="type"           type="xs:string"/>
              <xs:element name="version"        type="xs:string"/>
              <xs:element name="correlation_id" type="UUIDType" minOccurs="0"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
        <xs:element name="body">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="identity_uuid" type="UUIDType" minOccurs="0"/>
              <xs:element name="invoice">
                <xs:complexType>
                  <xs:sequence>
                    <xs:element name="id" type="xs:string" minOccurs="0"/>
                    <xs:element name="amount_paid" type="CurrencyAmountType"/>
                    <xs:element name="status">
                      <xs:simpleType>
                        <xs:restriction base="xs:string">
                          <xs:enumeration value="paid"/>
                          <xs:enumeration value="pending"/>
                          <xs:enumeration value="cancelled"/>
                        </xs:restriction>
                      </xs:simpleType>
                    </xs:element>
                    <xs:element name="due_date"    type="xs:date" minOccurs="0"/>
                  </xs:sequence>
                </xs:complexType>
              </xs:element>
              <xs:element name="payment_context">
                <xs:simpleType>
                  <xs:restriction base="xs:string">
                    <xs:enumeration value="registration"/>
                    <xs:enumeration value="consumption"/>
                    <xs:enumeration value="online_invoice"/>
                    <xs:enumeration value="session_registration"/>
                  </xs:restriction>
                </xs:simpleType>
              </xs:element>
              <xs:element name="transaction">
                <xs:complexType>
                  <xs:sequence>
                    <xs:element name="id" type="xs:string"/>
                    <xs:element name="payment_method">
                      <xs:simpleType>
                        <xs:restriction base="xs:string">
                          <xs:enumeration value="company_link"/>
                          <xs:enumeration value="on_site"/>
                          <xs:enumeration value="online"/>
                        </xs:restriction>
                      </xs:simpleType>
                    </xs:element>
                  </xs:sequence>
                </xs:complexType>
              </xs:element>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML — consumption (Flow 5B)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>a23bc45d-89ef-1234-b567-1f03c3d4e580</message_id>
    <timestamp>2026-05-15T18:35:00Z</timestamp>
    <source>kassa</source>
    <type>payment_registered</type>
    <version>2.0</version>
    <correlation_id>f47ac10b-58cc-4372-a567-0e02b2c3d479</correlation_id>
  </header>
  <body>
    <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
    <invoice>
      <id>INV-2026-001</id>
      <amount_paid currency="eur">15.00</amount_paid>
      <status>paid</status>
      <due_date>2026-05-15</due_date>
    </invoice>
    <payment_context>consumption</payment_context>
    <transaction>
      <id>TRX-987654</id>
      <payment_method>company_link</payment_method>
    </transaction>
  </body>
</message>
```

#### Voorbeeld XML — registration (Flow 14)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>f14d0000-0000-0000-0000-000000000004</message_id>
    <timestamp>2026-05-15T09:15:00Z</timestamp>
    <source>kassa</source>
    <type>payment_registered</type>
    <version>2.0</version>
    <correlation_id>9f47ac10-b58c-4372-a567-0e02b2c3d479</correlation_id>
  </header>
  <body>
    <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
    <invoice>
      <!-- id weggelaten: factuur bestaat nog niet, CRM maakt die aan -->
      <amount_paid currency="eur">50.00</amount_paid>
      <status>paid</status>
      <due_date>2026-05-15</due_date>
    </invoice>
    <payment_context>registration</payment_context>
    <transaction>
      <id>TRX-2026-04150001</id>
      <payment_method>on_site</payment_method>
    </transaction>
  </body>
</message>
```
### 6.7 `payment_status` (Kassa → Frontend)

Kassa stuurt dit naar Drupal nadat een **inschrijvingsbetaling** aan de kassa is afgerond. Drupal updatet de weergave van de betaalstatus voor de gebruiker.

- **Queue:** `frontend.payments`
- **Routing key:** `kassa.frontend.payment`

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="header">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="message_id" type="UUIDType"/>
              <xs:element name="timestamp"  type="xs:dateTime"/>
              <xs:element name="source"     type="xs:string" fixed="kassa"/>
              <xs:element name="type"       type="xs:string" fixed="payment_status"/>
              <xs:element name="version"    type="xs:string" fixed="2.0"/>
              <xs:element name="correlation_id" type="UUIDType" minOccurs="0"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
        <xs:element name="body">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="identity_uuid" type="UUIDType"/>
              <xs:element name="payment_status">
                <xs:simpleType>
                  <xs:restriction base="xs:string">
                    <xs:enumeration value="paid"/>
                    <xs:enumeration value="pending"/>
                  </xs:restriction>
                </xs:simpleType>
              </xs:element>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML

```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>41e2f3a4-b5c6-7890-efab-890123400010</message_id>
    <timestamp>2026-05-15T18:35:00Z</timestamp>
    <source>kassa</source>
    <type>payment_status</type>
    <version>2.0</version>
  </header>
  <body>
    <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
    <payment_status>paid</payment_status>
  </body>
</message>
```

---

### 6.8 `wallet_balance_update` (Canonical Broadcast)

Dit is het **centrale bericht** voor badge-saldo wijzigingen. Het wordt gebruikt voor zowel directe updates (Kassa → Frontend) als het Authority Lease Model (Broadcast).

- **Exchange:** `wallet.updates` (fanout) of `frontend.exchange` (direct)
- **Routing key:** `wallet.balance_update` (indien van toepassing)
- **Triggers:** badge-aankoop, top-up, refund, of wijziging in lease-autoriteit.

#### XSD (Unified v2.3)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="header">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="message_id" type="UUIDType"/>
              <xs:element name="timestamp"  type="xs:dateTime"/>
              <xs:element name="source">
                <xs:simpleType>
                  <xs:restriction base="xs:string">
                    <xs:enumeration value="crm"/>
                    <xs:enumeration value="kassa"/>
                  </xs:restriction>
                </xs:simpleType>
              </xs:element>
              <xs:element name="type"       type="xs:string" fixed="wallet_balance_update"/>
              <xs:element name="version"    type="xs:string" fixed="2.0"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
        <xs:element name="body">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="identity_uuid" type="UUIDType"/>
              <xs:element name="wallet_balance">
                <xs:complexType>
                  <xs:simpleContent>
                    <xs:extension base="xs:decimal">
                      <xs:attribute name="currency" type="xs:string" fixed="eur" use="required"/>
                    </xs:extension>
                  </xs:simpleContent>
                </xs:complexType>
              </xs:element>
              <!-- Authority Lease Model Velden (Optioneel voor compatibiliteit) -->
              <xs:element name="authority" minOccurs="0">
                <xs:simpleType>
                  <xs:restriction base="xs:string">
                    <xs:enumeration value="crm"/>
                    <xs:enumeration value="kassa"/>
                  </xs:restriction>
                </xs:simpleType>
              </xs:element>
              <xs:element name="status" minOccurs="0">
                <xs:simpleType>
                  <xs:restriction base="xs:string">
                    <xs:enumeration value="active"/>
                    <xs:enumeration value="frozen"/>
                    <xs:enumeration value="overdrawn"/>
                  </xs:restriction>
                </xs:simpleType>
              </xs:element>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML (Full - Lease Model)

```xml
<message>
  <header>
    <message_id>e54a8b72-1c2d-3e4f-5678-7a8b9c0d1e2f</message_id>
    <timestamp>2026-05-15T20:30:00Z</timestamp>
    <source>kassa</source>
    <type>wallet_balance_update</type>
    <version>2.0</version>
  </header>
  <body>
    <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
    <wallet_balance currency="eur">15.50</wallet_balance>
    <authority>kassa</authority>
    <status>active</status>
  </body>
</message>
```
### 6.9 `system_error` (Kassa → kassa.errors)

Kassa stuurt dit bij elk foutscenario. Monitoring ontvangt dit voor het dashboard. Dit bericht volgt het **globale formaat uit [Sectie 2.6](#26-global-system_error-format)**.

**Kassa-specifieke Error Codes:**

| Code | Wanneer |
|------|---------|
| `badge_not_found` | badge_id niet gevonden in Odoo |
| `odoo_api_error` | De Kassa-integratie kan de Odoo XML-RPC API niet bereiken. |
| `offline_queue_full` | De lokale outbox-buffer heeft de limiet (500 berichten) bereikt. |

*(Voor algemene codes zoals `invalid_xml_format`, zie sectie 2.6)*

#### Voorbeeld XML — onbekende badge

```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>63a4b5c6-d7e8-9012-abcd-012345600012</message_id>
    <type>system_error</type>
    <source>kassa</source>
    <timestamp>2026-05-15T19:05:00Z</timestamp>
    <version>2.0</version>
  </header>
  <body>
    <error_code>badge_not_found</error_code>
    <error_description>Badge BADGE-9999 niet gevonden in Odoo</error_description>
    <related_message_id>18b9c0d1-e2f3-4567-bcde-567890100007</related_message_id>
  </body>
</message>
```


---

## 7. Planning → CRM

- **Exchange:** `planning.exchange` (topic)
- **Queue:** `planning.session.events`
- **Routing keys:** `planning.session.created`, `planning.session.updated`, `planning.session.deleted`
- **CRM luistert op:** `planning.session.events`

> ** Wijziging voor Planning-team:**
> - `version` moet `2.0` zijn (was `1.0`)
> - `xmlns="urn:integration:planning:v1"` verwijderen van het `<message>` element
> - **Master UUID (Session Persistence):** Alle berichten behorend bij dezelfde sessie (created, updated, deleted) MOETEN dezelfde `correlation_id` bevatten. Dit is de Master UUID voor de sessie, gegenereerd door de Master UUID Manager in Planning.
### 7.1 `session_created`

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id"    type="UUIDType"/>
          <xs:element name="timestamp"     type="xs:dateTime"/>
          <xs:element name="source"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="planning"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="session_created"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="version"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="2.0"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="correlation_id" type="UUIDType" minOccurs="0"/>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <xs:element name="session_id"        type="xs:string"/>
          <xs:element name="title"             type="xs:string"/>
          <xs:element name="start_datetime"    type="xs:dateTime"/>
          <xs:element name="end_datetime"      type="xs:dateTime"/>
          <xs:element name="location"          type="xs:string"/>
          <xs:element name="session_type">
            <xs:simpleType><xs:restriction base="xs:string">
              <xs:enumeration value="keynote"/>
              <xs:enumeration value="workshop"/>
              <xs:enumeration value="reception"/>
              <xs:enumeration value="other"/>
            </xs:restriction></xs:simpleType>
          </xs:element>
          <xs:element name="status">
            <xs:simpleType><xs:restriction base="xs:string">
              <xs:enumeration value="draft"/>
              <xs:enumeration value="published"/>
              <xs:enumeration value="cancelled"/>
            </xs:restriction></xs:simpleType>
          </xs:element>
          <xs:element name="max_attendees"     type="xs:positiveInteger"/>
          <xs:element name="current_attendees" type="xs:nonNegativeInteger"/>
          <!-- speaker: optioneel — niet elke sessie heeft een externe spreker -->
          <xs:element name="speaker" minOccurs="0">
            <xs:complexType><xs:sequence>
              <!-- identity_uuid: de master_uuid van de Identity Service (indien spreker een gebruiker is) -->
              <xs:element name="identity_uuid" type="UUIDType" minOccurs="0"/>
              <xs:element name="contact">
                <xs:complexType><xs:sequence>
                  <xs:element name="first_name" type="xs:string"/>
                  <xs:element name="last_name"  type="xs:string"/>
                </xs:sequence></xs:complexType>
              </xs:element>
              <xs:element name="organisation" type="xs:string" minOccurs="0"/>
              <xs:element name="email"        type="xs:string" minOccurs="0"/>
            </xs:sequence></xs:complexType>
          </xs:element>
        </xs:sequence></xs:complexType>
      </xs:element>
    </xs:sequence></xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML

```xml
<message>
  <header>
    <message_id>4be2f3a4-b5c6-7890-efab-890123400010</message_id>
    <timestamp>2026-04-20T08:00:00Z</timestamp>
    <source>planning</source>
    <type>session_created</type>
    <version>2.0</version>
  </header>
  <body>
    <session_id>sess-keynote-001</session_id>
    <title>Keynote: AI in Healthcare</title>
    <start_datetime>2026-05-15T14:00:00Z</start_datetime>
    <end_datetime>2026-05-15T15:00:00Z</end_datetime>
    <location>Aula A - Campus Jette</location>
    <session_type>keynote</session_type>
    <status>published</status>
    <max_attendees>120</max_attendees>
    <current_attendees>0</current_attendees>
    <speaker>
      <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
      <contact>
        <first_name>Sarah</first_name>
        <last_name>Leclercq</last_name>
      </contact>
      <organisation>UZ Brussel</organisation>
      <email>s.leclercq@uzbrussel.be</email>
    </speaker>
  </body>
</message>
```

---

### 7.2 `session_updated`

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id"    type="UUIDType"/>
          <xs:element name="timestamp"     type="xs:dateTime"/>
          <xs:element name="source"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="planning"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="session_updated"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="version"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="2.0"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="correlation_id" type="UUIDType" minOccurs="0"/>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <xs:element name="session_id"        type="xs:string"/>
          <xs:element name="title"             type="xs:string"/>
          <xs:element name="start_datetime"    type="xs:dateTime"/>
          <xs:element name="end_datetime"      type="xs:dateTime"/>
          <xs:element name="location"          type="xs:string"/>
          <xs:element name="session_type">
            <xs:simpleType><xs:restriction base="xs:string">
              <xs:enumeration value="keynote"/>
              <xs:enumeration value="workshop"/>
              <xs:enumeration value="reception"/>
              <xs:enumeration value="other"/>
            </xs:restriction></xs:simpleType>
          </xs:element>
          <xs:element name="status">
            <xs:simpleType><xs:restriction base="xs:string">
              <xs:enumeration value="draft"/>
              <xs:enumeration value="published"/>
              <xs:enumeration value="cancelled"/>
            </xs:restriction></xs:simpleType>
          </xs:element>
          <xs:element name="max_attendees"     type="xs:positiveInteger"/>
          <xs:element name="current_attendees" type="xs:nonNegativeInteger"/>
          <xs:element name="change_reason"     type="xs:string" minOccurs="0"/>
          <xs:element name="speaker" minOccurs="0">
            <xs:complexType><xs:sequence>
              <!-- identity_uuid: de master_uuid van de Identity Service (indien spreker een gebruiker is) -->
              <xs:element name="identity_uuid" type="UUIDType" minOccurs="0"/>
              <xs:element name="contact">
                <xs:complexType><xs:sequence>
                  <xs:element name="first_name" type="xs:string"/>
                  <xs:element name="last_name"  type="xs:string"/>
                </xs:sequence></xs:complexType>
              </xs:element>
              <xs:element name="organisation" type="xs:string" minOccurs="0"/>
              <xs:element name="email"        type="xs:string" minOccurs="0"/>
            </xs:sequence></xs:complexType>
          </xs:element>
        </xs:sequence></xs:complexType>
      </xs:element>
    </xs:sequence></xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML — spreker heeft 30 min vertraging

```xml
<message>
  <header>
    <message_id>5cf3a4b5-c6d7-8901-fabc-901234500011</message_id>
    <timestamp>2026-05-15T13:45:00Z</timestamp>
    <source>planning</source>
    <type>session_updated</type>
    <version>2.0</version>
  </header>
  <body>
    <session_id>sess-keynote-001</session_id>
    <title>Keynote: AI in Healthcare</title>
    <start_datetime>2026-05-15T14:30:00Z</start_datetime>
    <end_datetime>2026-05-15T15:30:00Z</end_datetime>
    <location>Aula A - Campus Jette</location>
    <session_type>keynote</session_type>
    <status>published</status>
    <max_attendees>120</max_attendees>
    <current_attendees>87</current_attendees>
    <change_reason>Spreker heeft 30 minuten vertraging door file</change_reason>
    <speaker>
      <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
      <contact>
        <first_name>Sarah</first_name>
        <last_name>Leclercq</last_name>
      </contact>
      <organisation>UZ Brussel</organisation>
    </speaker>
  </body>
</message>
```

---

### 7.3 `session_deleted`

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id"     type="UUIDType"/>
          <xs:element name="timestamp"      type="xs:dateTime"/>
          <xs:element name="source"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="planning"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="session_deleted"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="version"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="2.0"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="correlation_id" type="UUIDType" minOccurs="0"/>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <xs:element name="session_id" type="xs:string"/>
          <xs:element name="reason"     type="xs:string" minOccurs="0"/>
          <xs:element name="deleted_by" type="xs:string" minOccurs="0"/>
        </xs:sequence></xs:complexType>
      </xs:element>
    </xs:sequence></xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML

```xml
<message>
  <header>
    <message_id>6da4b5c6-d7e8-9012-abcd-012345600012</message_id>
    <timestamp>2026-05-14T16:00:00Z</timestamp>
    <source>planning</source>
    <type>session_deleted</type>
    <version>2.0</version>
  </header>
  <body>
    <session_id>sess-workshop-003</session_id>
    <reason>Spreker is ziek gevallen</reason>
    <deleted_by>planning-admin</deleted_by>
  </body>
</message>
```

---

## 8. Facturatie → CRM

- **Queue:** `crm.incoming`

### 8.1 `invoice_status`

Facturatie meldt de nieuwe status van een factuur.

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType><xs:sequence>
        <xs:element name="header">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="message_id"     type="UUIDType"/>
              <xs:element name="timestamp"      type="xs:dateTime"/>
              <xs:element name="source"><xs:simpleType><xs:restriction base="xs:string">
                <xs:enumeration value="facturatie"/></xs:restriction></xs:simpleType></xs:element>
              <xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
                <xs:enumeration value="invoice_status"/></xs:restriction></xs:simpleType></xs:element>
              <xs:element name="version"><xs:simpleType><xs:restriction base="xs:string">
                <xs:enumeration value="2.0"/></xs:restriction></xs:simpleType></xs:element>
              <xs:element name="correlation_id" type="UUIDType" minOccurs="0"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <xs:element name="invoice_id"    type="xs:string"/>
          <xs:element name="identity_uuid" type="UUIDType"/>
          <xs:element name="status">
            <xs:simpleType><xs:restriction base="xs:string">
              <xs:enumeration value="draft"/>
              <xs:enumeration value="sent"/>
              <xs:enumeration value="paid"/>
              <xs:enumeration value="overdue"/>
              <xs:enumeration value="cancelled"/>
            </xs:restriction></xs:simpleType>
          </xs:element>
          <xs:element name="amount">
            <xs:complexType><xs:simpleContent><xs:extension base="xs:decimal">
              <xs:attribute name="currency" type="xs:string" fixed="eur" use="required"/>
              </xs:extension></xs:simpleContent></xs:complexType>
          </xs:element>
          <xs:element name="due_date" type="xs:date" minOccurs="0"/>
        </xs:sequence></xs:complexType>
      </xs:element>
    </xs:sequence></xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML

```xml
<message>
  <header>
    <message_id>7eb5c6d7-e8f9-0123-bcde-123456700013</message_id>
    <timestamp>2026-05-16T09:00:00Z</timestamp>
    <source>facturatie</source>
    <type>invoice_status</type>
    <version>2.0</version>
  </header>
  <body>
    <invoice_id>foss-inv-00142</invoice_id>
    <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
    <status>paid</status>
    <amount currency="eur">150.00</amount>
    <due_date>2026-06-15</due_date>
  </body>
</message>
```

---

### 8.2 `payment_registered` (Facturatie → CRM)

Facturatie stuurt dit naar CRM nadat een online betaling (via de facturatie-link) succesvol is afgerond.

#### XSD (v2.3 — Unified Structure)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">

  <xs:complexType name="CurrencyAmountType">
    <xs:simpleContent>
      <xs:extension base="xs:decimal">
        <xs:attribute name="currency" type="xs:string" fixed="eur" use="required"/>
      </xs:extension>
    </xs:simpleContent>
  </xs:complexType>

  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="header">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="message_id"     type="UUIDType"/>
              <xs:element name="timestamp"      type="xs:dateTime"/>
              <xs:element name="source"><xs:simpleType><xs:restriction base="xs:string">
                <xs:enumeration value="facturatie"/></xs:restriction></xs:simpleType></xs:element>
              <xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
                <xs:enumeration value="payment_registered"/></xs:restriction></xs:simpleType></xs:element>
              <xs:element name="version"><xs:simpleType><xs:restriction base="xs:string">
                <xs:enumeration value="2.0"/></xs:restriction></xs:simpleType></xs:element>
              <xs:element name="correlation_id" type="UUIDType" minOccurs="0"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
        <xs:element name="body">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="identity_uuid" type="UUIDType" minOccurs="0"/>
              <xs:element name="invoice">
                <xs:complexType>
                  <xs:sequence>
                    <xs:element name="id" type="xs:string" minOccurs="0"/>
                    <xs:element name="amount_paid" type="CurrencyAmountType"/>
                    <xs:element name="status">
                      <xs:simpleType>
                        <xs:restriction base="xs:string">
                          <xs:enumeration value="paid"/>
                          <xs:enumeration value="pending"/>
                          <xs:enumeration value="cancelled"/>
                        </xs:restriction>
                      </xs:simpleType>
                    </xs:element>
                    <xs:element name="due_date"    type="xs:date" minOccurs="0"/>
                  </xs:sequence>
                </xs:complexType>
              </xs:element>
              <xs:element name="payment_context">
                <xs:simpleType>
                  <xs:restriction base="xs:string">
                    <xs:enumeration value="registration"/>
                    <xs:enumeration value="consumption"/>
                    <xs:enumeration value="online_invoice"/>
                    <xs:enumeration value="session_registration"/>
                  </xs:restriction>
                </xs:simpleType>
              </xs:element>
              <xs:element name="transaction" minOccurs="0">
                <xs:complexType>
                  <xs:sequence>
                    <xs:element name="id" type="xs:string"/>
                    <xs:element name="payment_method">
                      <xs:simpleType>
                        <xs:restriction base="xs:string">
                          <xs:enumeration value="company_link"/>
                          <xs:enumeration value="on_site"/>
                          <xs:enumeration value="online"/>
                        </xs:restriction>
                      </xs:simpleType>
                    </xs:element>
                  </xs:sequence>
                </xs:complexType>
              </xs:element>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML

```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>f14d0000-0000-0000-0000-000000000004</message_id>
    <timestamp>2026-05-15T09:15:00Z</timestamp>
    <source>facturatie</source>
    <type>payment_registered</type>
    <version>2.0</version>
  </header>
  <body>
    <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
    <invoice>
      <id>INV-2026-001</id>
      <amount_paid currency="eur">50.00</amount_paid>
      <status>paid</status>
    </invoice>
    <payment_context>online_invoice</payment_context>
    <transaction>
      <id>PAY-ONLINE-9988</id>
      <payment_method>online</payment_method>
    </transaction>
  </body>
</message>
```

---

## 9. Mailing → CRM

- **Queue:** `crm.incoming`

### 9.1 `mailing_status`

Mailing rapporteert het resultaat van een verzonden campagne.

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id" type="UUIDType"/>
          <xs:element name="timestamp"  type="xs:dateTime"/>
          <xs:element name="source"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="mailing"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="mailing_status"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="version"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="2.0"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="correlation_id" type="UUIDType" minOccurs="0"/>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <xs:element name="campaign_id" type="xs:string"/>
          <xs:element name="subject"     type="xs:string"/>
          <xs:element name="sent"        type="xs:integer"/>
          <xs:element name="delivered"   type="xs:integer"/>
          <xs:element name="bounced"     type="xs:integer"/>
          <!-- bounced_emails: optioneel maar sterk aanbevolen — staat direct na bounced -->
          <!-- CRM gebruikt dit om ongeldige e-mailadressen te markeren in Salesforce -->
          <xs:element name="bounced_emails" minOccurs="0">
            <xs:complexType><xs:sequence>
              <xs:element name="email" type="xs:string" minOccurs="0" maxOccurs="unbounded"/>
            </xs:sequence></xs:complexType>
          </xs:element>
          <xs:element name="opened"      type="xs:integer"/>
          <xs:element name="status">
            <xs:simpleType><xs:restriction base="xs:string">
              <xs:enumeration value="completed"/>
              <xs:enumeration value="partial_failure"/>
              <xs:enumeration value="failed"/>
            </xs:restriction></xs:simpleType>
          </xs:element>
        </xs:sequence></xs:complexType>
      </xs:element>
    </xs:sequence></xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML

```xml
<message>
  <header>
    <message_id>90d7e8f9-a0b1-2345-defa-345678900015</message_id>
    <timestamp>2026-05-15T10:05:00Z</timestamp>
    <source>mailing</source>
    <type>mailing_status</type>
    <version>2.0</version>
    <correlation_id>a1b2c3d4-e5f6-7890-abcd-ef1234567890</correlation_id>
  </header>
  <body>
    <campaign_id>sg-campaign-0089</campaign_id>
    <subject>Bevestiging inschrijving Shiftfestival 2026</subject>
    <sent>342</sent>
    <delivered>339</delivered>
    <bounced>3</bounced>
    <bounced_emails>
      <email>oud.adres@verlopen.be</email>
      <email>typo@gmial.com</email>
      <email>verwijderd@bedrijf.be</email>
    </bounced_emails>
    <opened>201</opened>
    <status>completed</status>
  </body>
</message>
```

> **� Voor het Mailing-team:** Vul `bounced_emails` in met de exacte e-mailadressen van `bounced` count. CRM markeert deze automatisch als ongeldig in Salesforce zodat ze nooit opnieuw aangeschreven worden.

---

## 10. CRM → Kassa

- **Queue:** `kassa.incoming`

### 10.1 `new_registration` (CRM → Kassa)

CRM stuurt een nieuw klantprofiel door zodat Kassa betalingen kan verwerken.  
> **Wijziging:** `age` is verwijderd. Kassa berekent zelf de leeftijd op basis van `date_of_birth`.

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id"     type="UUIDType"/>
          <xs:element name="timestamp"      type="xs:dateTime"/>
          <xs:element name="source"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="crm"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="new_registration"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="version"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="2.0"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="correlation_id" type="UUIDType"/>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <xs:element name="customer">
            <xs:complexType><xs:sequence>
              <!-- identity_uuid: de master_uuid van de Identity Service -->
              <xs:element name="identity_uuid"   type="UUIDType"/>
              <xs:element name="email"          type="xs:string"/>
              <xs:element name="date_of_birth"  type="xs:date"/>
              <xs:element name="contact">
                <xs:complexType><xs:sequence>
                  <xs:element name="first_name" type="xs:string"/>
                  <xs:element name="last_name"  type="xs:string"/>
                </xs:sequence></xs:complexType>
              </xs:element>
              <!-- type: private|company → is_company op res.partner in Odoo -->
              <xs:element name="type">
                <xs:simpleType><xs:restriction base="xs:string">
                  <xs:enumeration value="private"/>
                  <xs:enumeration value="company"/>
                </xs:restriction></xs:simpleType>
              </xs:element>
              <xs:element name="company_name" type="xs:string" minOccurs="0"/>
              <xs:element name="vat_number"   type="xs:string" minOccurs="0"/>
              <xs:element name="company_id"   type="xs:string" minOccurs="0"/>
              <xs:element name="badge_id"     type="xs:string" minOccurs="0"/>
              <xs:element name="payment_due">
                <xs:complexType><xs:sequence>
                  <xs:element name="amount">
                    <xs:complexType><xs:simpleContent><xs:extension base="xs:decimal">
                      <xs:attribute name="currency" type="xs:string" fixed="eur" use="required"/>
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
            </xs:sequence></xs:complexType>
          </xs:element>
        </xs:sequence></xs:complexType>
      </xs:element>
    </xs:sequence></xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML

```xml
<message>
  <header>
    <message_id>a1e8f9a0-b1c2-3456-efab-456789000016</message_id>
    <timestamp>2026-04-24T09:16:00Z</timestamp>
    <source>crm</source>
    <type>new_registration</type>
    <version>2.0</version>
    <correlation_id>c3d4e5f6-a7b8-9012-cdef-012345678902</correlation_id>
  </header>
  <body>
    <customer>
      <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
      <email>jan.peeters@ehb.be</email>
      <date_of_birth>1995-03-21</date_of_birth>
      <contact>
        <first_name>Jan</first_name>
        <last_name>Peeters</last_name>
      </contact>
      <type>company</type>
      <company_name>Erasmushogeschool Brussel</company_name>
      <vat_number>BE0876543210</vat_number>
      <company_id>ehb-001</company_id>
      <payment_due>
        <amount currency="eur">25.00</amount>
        <status>unpaid</status>
      </payment_due>
    </customer>
  </body>
</message>
```

---

### 10.2 `profile_update` (CRM → Kassa)

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id"     type="UUIDType"/>
          <xs:element name="timestamp"      type="xs:dateTime"/>
          <xs:element name="source"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="crm"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="profile_update"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="version"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="2.0"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="correlation_id" type="UUIDType" minOccurs="0"/>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <!-- identity_uuid: de master_uuid van de Identity Service -->
          <xs:element name="identity_uuid"   type="UUIDType"/>
          <xs:element name="email"         type="xs:string"/>
          <xs:element name="date_of_birth" type="xs:date" minOccurs="0"/>
          <xs:element name="contact">
            <xs:complexType><xs:sequence>
              <xs:element name="first_name" type="xs:string"/>
              <xs:element name="last_name"  type="xs:string"/>
            </xs:sequence></xs:complexType>
          </xs:element>
          <xs:element name="type" minOccurs="0">
            <xs:simpleType><xs:restriction base="xs:string">
              <xs:enumeration value="private"/>
              <xs:enumeration value="company"/>
            </xs:restriction></xs:simpleType>
          </xs:element>
          <xs:element name="company_name" type="xs:string" minOccurs="0"/>
          <xs:element name="vat_number"   type="xs:string" minOccurs="0"/>
          <xs:element name="company_id"   type="xs:string" minOccurs="0"/>
          <xs:element name="payment_due" minOccurs="0">
            <xs:complexType><xs:sequence>
              <xs:element name="amount">
                <xs:complexType><xs:simpleContent><xs:extension base="xs:decimal">
                  <xs:attribute name="currency" type="xs:string" fixed="eur" use="required"/>
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
        </xs:sequence></xs:complexType>
      </xs:element>
    </xs:sequence></xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML

```xml
<message>
  <header>
    <message_id>b2f9a0b1-c2d3-4567-fabc-567890100017</message_id>
    <timestamp>2026-04-24T11:01:00Z</timestamp>
    <source>crm</source>
    <type>profile_update</type>
    <version>2.0</version>
  </header>
  <body>
    <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
    <email>jan.peeters.nieuw@ehb.be</email>
    <contact>
      <first_name>Jan</first_name>
      <last_name>Peeters</last_name>
    </contact>
    <type>company</type>
    <company_name>Erasmushogeschool Brussel</company_name>
  </body>
</message>
```

---

### 10.3 `cancel_registration` (CRM → Kassa & Planning)

> **Gap Resolution (April 2026):** CRM stuurt dit bericht nu ook door naar Planning (via `calendar.exchange`) zodat `current_attendees` daar correct verlaagd kan worden bij een annulatie.

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">

  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id"     type="UUIDType"/>
          <xs:element name="timestamp"      type="xs:dateTime"/>
          <xs:element name="source"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="crm"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="cancel_registration"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="version"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="2.0"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="correlation_id" type="UUIDType" minOccurs="0"/>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <xs:element name="identity_uuid" type="UUIDType"/>
          <xs:element name="session_id"    type="xs:string"/>
          <xs:element name="reason"        type="xs:string" minOccurs="0"/>
        </xs:sequence></xs:complexType>
      </xs:element>
    </xs:sequence></xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML

```xml
<message>
  <header>
    <message_id>c3a0b1c2-d3e4-5678-abcd-678901200018</message_id>
    <timestamp>2026-05-10T14:00:00Z</timestamp>
    <source>crm</source>
    <type>cancel_registration</type>
    <version>2.0</version>
  </header>
  <body>
    <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
    <session_id>sess-keynote-001</session_id>
    <reason>Klant heeft zelf annulatie gevraagd</reason>
  </body>
</message>
```

---

### 10.4 `profile_update` (CRM → Facturatie)

> **Gap Resolution (Mei 2026):** Gevonden in `Facturatie/src/services/xsd/profile_update.xsd` — routing was nog niet gedocumenteerd in het contract. Facturatie abonneert op `profile_update` van CRM om klantgegevens up-to-date te houden voor factuurverwerking (o.a. btw-nummer, bedrijfsnaam, betalingsstatus).

- **Exchange:** `crm.exchange`
- **Routing Key:** `crm.to.facturatie.profile_update`
- **Queue (ontvanger):** `facturatie.incoming`
- **Wanneer:** CRM publiceert een profiel-update en stuurt dit naar zowel Kassa (§10.2) als Facturatie.

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id"     type="UUIDType"/>
          <xs:element name="timestamp"      type="xs:dateTime"/>
          <xs:element name="source"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="crm"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="profile_update"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="version"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="2.0"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="correlation_id" type="UUIDType" minOccurs="0"/>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <xs:element name="identity_uuid"   type="UUIDType"/>
          <xs:element name="email"         type="xs:string"/>
          <xs:element name="date_of_birth" type="xs:date" minOccurs="0"/>
          <xs:element name="contact">
            <xs:complexType><xs:sequence>
              <xs:element name="first_name" type="xs:string"/>
              <xs:element name="last_name"  type="xs:string"/>
            </xs:sequence></xs:complexType>
          </xs:element>
          <xs:element name="type" minOccurs="0">
            <xs:simpleType><xs:restriction base="xs:string">
              <xs:enumeration value="private"/>
              <xs:enumeration value="company"/>
            </xs:restriction></xs:simpleType>
          </xs:element>
          <xs:element name="company_name" type="xs:string" minOccurs="0"/>
          <xs:element name="vat_number"   type="xs:string" minOccurs="0"/>
          <xs:element name="company_id"   type="xs:string" minOccurs="0"/>
          <xs:element name="payment_due" minOccurs="0">
            <xs:complexType><xs:sequence>
              <xs:element name="amount">
                <xs:complexType><xs:simpleContent><xs:extension base="xs:decimal">
                  <xs:attribute name="currency" type="xs:string" fixed="eur" use="required"/>
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
        </xs:sequence></xs:complexType>
      </xs:element>
    </xs:sequence></xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML

```xml
<message>
  <header>
    <message_id>f4a1b2c3-d4e5-6789-abcd-789012300019</message_id>
    <timestamp>2026-04-24T11:01:00Z</timestamp>
    <source>crm</source>
    <type>profile_update</type>
    <version>2.0</version>
  </header>
  <body>
    <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
    <email>jan.peeters@ehb.be</email>
    <contact>
      <first_name>Jan</first_name>
      <last_name>Peeters</last_name>
    </contact>
    <type>company</type>
    <company_name>Erasmushogeschool Brussel</company_name>
    <vat_number>BE0123456789</vat_number>
  </body>
</message>
```

> **Opmerking:** Identiek schema als §10.2 (CRM → Kassa). Facturatie gebruikt dit bericht voor synchronisatie van btw-nummer en bedrijfsgegevens t.b.v. correcte facturatie.

---

## 11. CRM → Facturatie

- **Queue:** `facturatie.incoming`

### 11.1 `invoice_request` (CRM → Facturatie)

CRM routeert de factuuraanvraag van Kassa door naar Facturatie. **CRM doet geen merge** — de `<items>` zitten niet in dit bericht. Facturatie koppelt de orderlijnen zelf via de `correlation_id`.

> **Architectuurprincipe:** CRM is een dom doorgeefluik. De `correlation_id` in de header verwijst naar de `message_id` van de bijhorende `consumption_order` (zie 11.3). Facturatie matcht die twee berichten zelf en bouwt de factuur op.
>
> **`<invoice_data>` uitzondering:** Zoals in 6.5, zitten `first_name`/`last_name` direct in `<invoice_data>` (niet in `<contact>` wrapper). Dit is een gedocumenteerde uitzondering op Regel 2, conform de Kassa-code.

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">

  <xs:complexType name="AddressType">
    <xs:sequence>
      <xs:element name="street"      type="xs:string"/>
      <xs:element name="number"      type="xs:string"/>
      <xs:element name="postal_code" type="xs:string"/>
      <xs:element name="city"        type="xs:string"/>
      <xs:element name="country"     type="xs:string"/>
    </xs:sequence>
  </xs:complexType>

  <xs:complexType name="InvoiceDataType">
    <xs:sequence>
      <xs:element name="contact">
        <xs:complexType>
          <xs:sequence>
            <xs:element name="first_name"  type="xs:string"/>
            <xs:element name="last_name"   type="xs:string"/>
          </xs:sequence>
        </xs:complexType>
      </xs:element>
      <xs:element name="email"        type="xs:string"/>
      <xs:element name="address"      type="AddressType"/>
      <xs:element name="company_name" type="xs:string" minOccurs="0"/>
      <xs:element name="vat_number"   type="xs:string" minOccurs="0"/>
    </xs:sequence>
  </xs:complexType>

  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="header">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="message_id"     type="UUIDType"/>
              <xs:element name="timestamp"      type="xs:dateTime"/>
              <xs:element name="source"><xs:simpleType><xs:restriction base="xs:string">
                <xs:enumeration value="crm"/></xs:restriction></xs:simpleType></xs:element>
              <xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
                <xs:enumeration value="invoice_request"/></xs:restriction></xs:simpleType></xs:element>
              <xs:element name="version"><xs:simpleType><xs:restriction base="xs:string">
                <xs:enumeration value="2.0"/></xs:restriction></xs:simpleType></xs:element>
              <!-- correlation_id = message_id van de bijhorende consumption_order (zie 11.3) -->
              <xs:element name="correlation_id" type="UUIDType"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
        <xs:element name="body">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="identity_uuid" type="UUIDType"/>
              <xs:element name="payment_status">
                <xs:simpleType><xs:restriction base="xs:string">
                  <xs:enumeration value="paid"/>
                  <xs:enumeration value="pending"/>
                </xs:restriction></xs:simpleType>
              </xs:element>
              <xs:element name="payment_method" type="xs:string" minOccurs="0"/>
              <xs:element name="invoice_data" type="InvoiceDataType"/>
              <!-- GEEN <items> of <total> — Facturatie haalt die uit de consumption_order -->
            </xs:sequence>
          </xs:complexType>
        </xs:element>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML

```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>d4b1c2d3-e4f5-6789-bcde-789012300019</message_id>
    <timestamp>2026-05-16T08:00:00Z</timestamp>
    <source>crm</source>
    <type>invoice_request</type>
    <version>2.0</version>
    <!-- correlation_id matcht de message_id van de consumption_order -->
    <correlation_id>f47ac10b-58cc-4372-a567-0e02b2c3d479</correlation_id>
  </header>
  <body>
    <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
    <payment_status>paid</payment_status>
    <payment_method>cash</payment_method>
    <invoice_data>
      <contact>
        <first_name>Jan</first_name>
        <last_name>Peeters</last_name>
      </contact>
      <email>jan.peeters@ehb.be</email>
      <address>
        <street>Laarbeeklaan</street>
        <number>121</number>
        <postal_code>1090</postal_code>
        <city>Jette</city>
        <country>BE</country>
      </address>
      <company_name>Erasmushogeschool Brussel</company_name>
      <vat_number>BE0876543210</vat_number>
    </invoice_data>
    <!-- Geen items — Facturatie haalt die zelf op via correlation_id + consumption_order -->
  </body>
</message>
```

---

### 11.2 `invoice_cancelled` (CRM → Facturatie)

CRM stuurt dit bericht naar Facturatie wanneer een factuur geannuleerd of terugbetaald moet worden. Er zijn twee flows:

| Flow | Wanneer | Lookup-sleutel |
|---|---|---|
| **Kassa-refund** | Kassier verwerkt terugbetaling in POS → Kassa stuurt `refund_processed` → CRM stuurt dit door | `correlation_id` in header (= `message_id` van originele `invoice_request`) |
| **Directe annulatie** | CRM annuleert zelf (bv. inschrijving geannuleerd) | `invoice_id` in body (= Facturatie-intern ID, ontvangen via `invoice_status`) |

> **Regel:** Minstens één van `invoice_id` of `correlation_id` MOET aanwezig zijn. Facturatie gebruikt `invoice_id` als die aanwezig is (snelste pad), anders zoekt het op via `correlation_id`.

> **`items` aanwezig** = gedeeltelijke creditnota voor die specifieke artikelen. **`items` afwezig** = volledige annulatie van de factuur.

#### Globale regelcontrole

| Regel | Status | Opmerking |
|---|---|---|
| Regel 1 — geen `xmlns`, geen `<receiver>` | ✅ | Correct |
| Regel 2 — `<contact>` nesting | ✅ | Geen namen in dit bericht |
| Regel 3 — valuta op geldbedragen | ✅ | `unit_price` en `total_amount` gebruiken `CurrencyAmountType` met `currency="eur"` |
| Regel 4 — `date_of_birth` | ✅ | Geen datumvelden |
| Regel 5 — Master UUID | ✅ | `identity_uuid` gebruikt `UUIDType` patroon |
| Regel 6 — adres splitsing | ✅ | Geen adresvelden |

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">

  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:complexType name="CurrencyAmountType">
    <xs:simpleContent>
      <xs:extension base="xs:decimal">
        <xs:attribute name="currency" type="xs:string" fixed="eur" use="required"/>
      </xs:extension>
    </xs:simpleContent>
  </xs:complexType>

  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id"  type="UUIDType"/>
          <xs:element name="timestamp"   type="xs:dateTime"/>
          <xs:element name="source"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="crm"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="invoice_cancelled"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="version"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="2.0"/></xs:restriction></xs:simpleType></xs:element>
          <!-- correlation_id = message_id van de originele invoice_request (verplicht bij Kassa-refund flow) -->
          <xs:element name="correlation_id" type="UUIDType" minOccurs="0"/>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <xs:element name="identity_uuid" type="UUIDType"/>
          <!-- invoice_id = Facturatie-intern ID ontvangen via invoice_status (verplicht bij directe annulatie flow) -->
          <xs:element name="invoice_id"    type="xs:string" minOccurs="0"/>
          <xs:element name="reason"        type="xs:string" minOccurs="0"/>
          <!-- items: aanwezig = gedeeltelijke creditnota, afwezig = volledige annulatie -->
          <xs:element name="items" minOccurs="0">
            <xs:complexType>
              <xs:sequence>
                <xs:element name="item" maxOccurs="unbounded">
                  <xs:complexType>
                    <xs:sequence>
                      <xs:element name="sku"          type="xs:string"/>
                      <xs:element name="description"  type="xs:string"/>
                      <xs:element name="quantity"     type="xs:integer"/>
                      <xs:element name="unit_price"   type="CurrencyAmountType"/>
                      <xs:element name="total_amount" type="CurrencyAmountType"/>
                      <xs:element name="vat_rate"     type="xs:integer" minOccurs="0"/>
                    </xs:sequence>
                  </xs:complexType>
                </xs:element>
              </xs:sequence>
            </xs:complexType>
          </xs:element>
        </xs:sequence></xs:complexType>
      </xs:element>
    </xs:sequence></xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML — volledige annulatie via invoice_id (directe annulatie, bv. inschrijving)

```xml
<message>
  <header>
    <message_id>e5c2d3e4-f5a6-7890-cdef-890123400020</message_id>
    <timestamp>2026-05-10T14:01:00Z</timestamp>
    <source>crm</source>
    <type>invoice_cancelled</type>
    <version>2.0</version>
  </header>
  <body>
    <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
    <invoice_id>foss-inv-00142</invoice_id>
    <reason>Inschrijving geannuleerd door klant</reason>
    <!-- geen items → Facturatie annuleert de volledige factuur -->
  </body>
</message>
```

#### Voorbeeld XML — gedeeltelijke creditnota via correlation_id (Kassa-refund)

```xml
<message>
  <header>
    <message_id>a1b2c3d4-e5f6-7890-abcd-ef1234567891</message_id>
    <timestamp>2026-05-10T15:30:00Z</timestamp>
    <source>crm</source>
    <type>invoice_cancelled</type>
    <version>2.0</version>
    <!-- correlation_id = message_id van de originele invoice_request -->
    <correlation_id>f47ac10b-58cc-4372-a567-0e02b2c3d479</correlation_id>
  </header>
  <body>
    <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
    <reason>Klant heeft Workshop Python geretourneerd aan de kassa</reason>
    <items>
      <item>
        <sku>SES-001</sku>
        <description>Workshop Python</description>
        <quantity>1</quantity>
        <unit_price currency="eur">50.00</unit_price>
        <total_amount currency="eur">50.00</total_amount>
        <vat_rate>21</vat_rate>
      </item>
    </items>
  </body>
</message>
```

---

### 11.3 `consumption_order` (CRM → Facturatie) — Passthrough

CRM stuurt de `consumption_order` **1-op-1 door** naar Facturatie zodra het die van Kassa ontvangt. CRM slaat de order op in Salesforce en routeert het bericht zonder enige aanpassing.

> **Architectuurprincipe:** CRM doet hier niets slims. Geen merge, geen transformatie. Facturatie ontvangt twee berichten:
> 1. De `consumption_order` (via deze passthrough) — bevat alle items, prijzen, BTW en klantdata
> 2. De `invoice_request` (via 11.1) — bevat de facturatiegegevens + `correlation_id`
>
> Facturatie matcht beide berichten via `correlation_id` == `message_id` van de `consumption_order` en bouwt de factuur op.

**XSD & XML:** Exact identiek aan Sectie 6.1. Zie aldaar voor het volledige schema (v2.3) met `sku`, `vat_rate`, `total_amount` en `CustomerType`.

**Flow diagram:**

```
Kassa  consumption_order (msg_id: f47ac10b)  CRM  passthrough  facturatie.incoming
Kassa  invoice_request   (corr_id: f47ac10b)  CRM  passthrough  facturatie.incoming

Facturatie ontvangt beide, matcht op correlation_id = f47ac10b, bouwt factuur.
```


---

---

### 11.5 `payment_registered` (Frontend → Facturatie)

> **Nieuw — Issue #27.** Frontend stuurt dit bericht **rechtstreeks** naar `facturatie.incoming` wanneer een betaling via de webshop (online factuur) is bevestigd. Facturatie zet de factuur onmiddellijk op 'paid' in FossBilling.
>
> **Kassa vs. online:** Kassa-betalingen sturen `payment_status` mee in `invoice_request` (§11.1). Sectie 11.5 dekt online betalingen die **direct** van Frontend naar Facturatie gaan — zonder CRM als tussenpersoon.

- **Queue:** `facturatie.incoming`
- **Source:** `frontend`
- **Wanneer:** na succesvolle online betaling van een factuur via de webshop

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" elementFormDefault="qualified">

  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:simpleType name="SourceType">
    <xs:restriction base="xs:string">
      <xs:enumeration value="crm"/>
      <xs:enumeration value="kassa"/>
      <xs:enumeration value="frontend"/>
      <xs:enumeration value="planning"/>
      <xs:enumeration value="facturatie"/>
      <xs:enumeration value="monitoring"/>
      <xs:enumeration value="mailing"/>
      <xs:enumeration value="identity-service"/>
      <xs:enumeration value="iot_gateway"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="header" type="HeaderType"/>
        <xs:element name="body" type="PaymentRegisteredBodyType"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

  <xs:complexType name="HeaderType">
    <xs:sequence>
      <xs:element name="message_id" type="UUIDType"/>
      <xs:element name="timestamp" type="xs:dateTime"/>
      <xs:element name="source" type="xs:string"/>
      <xs:element name="type" type="xs:string"/>
      <xs:element name="version" type="xs:string"/>
      <xs:element name="correlation_id" type="UUIDType" minOccurs="0"/>
    </xs:sequence>
  </xs:complexType>

  <xs:complexType name="PaymentRegisteredBodyType">
    <xs:sequence>
      <xs:element name="identity_uuid" type="UUIDType" minOccurs="0"/>
      <xs:element name="invoice">
        <xs:complexType>
          <xs:sequence>
            <xs:element name="id" type="xs:string" minOccurs="0"/>
            <xs:element name="amount_paid" type="AmountType"/>
            <xs:element name="status">
              <xs:simpleType>
                <xs:restriction base="xs:string">
                  <xs:enumeration value="paid"/>
                  <xs:enumeration value="pending"/>
                  <xs:enumeration value="cancelled"/>
                </xs:restriction>
              </xs:simpleType>
            </xs:element>
            <xs:element name="due_date"    type="xs:date" minOccurs="0"/>
          </xs:sequence>
        </xs:complexType>
      </xs:element>
      <xs:element name="payment_context">
        <xs:simpleType>
          <xs:restriction base="xs:string">
            <xs:enumeration value="registration"/>
            <xs:enumeration value="consumption"/>
            <xs:enumeration value="online_invoice"/>
            <xs:enumeration value="session_registration"/>
          </xs:restriction>
        </xs:simpleType>
      </xs:element>
      <xs:element name="transaction" minOccurs="0">
        <xs:complexType>
          <xs:sequence>
            <xs:element name="id" type="xs:string"/>
            <xs:element name="payment_method">
              <xs:simpleType>
                <xs:restriction base="xs:string">
                  <xs:enumeration value="company_link"/>
                  <xs:enumeration value="on_site"/>
                  <xs:enumeration value="online"/>
                </xs:restriction>
              </xs:simpleType>
            </xs:element>
          </xs:sequence>
        </xs:complexType>
      </xs:element>
    </xs:sequence>
  </xs:complexType>

  <xs:complexType name="AmountType">
    <xs:simpleContent>
      <xs:extension base="xs:decimal">
        <xs:attribute name="currency" type="xs:string" fixed="eur" use="required"/>
      </xs:extension>
    </xs:simpleContent>
  </xs:complexType>

</xs:schema>
```

#### Voorbeeld XML

```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>a1b2c3d4-1111-4111-b111-111111111115</message_id>
    <timestamp>2026-05-06T14:00:00Z</timestamp>
    <source>frontend</source>
    <type>payment_registered</type>
    <version>2.0</version>
  </header>
  <body>
    <identity_uuid>b2c3d4e5-2222-4222-b222-222222222222</identity_uuid>
    <invoice>
      <id>26</id>
      <amount_paid currency="eur">150.00</amount_paid>
      <status>paid</status>
    </invoice>
    <payment_context>online_invoice</payment_context>
    <transaction>
      <id>TRANS-ABC123</id>
      <payment_method>online</payment_method>
    </transaction>
  </body>
</message>
```

> **Actiepunt Frontend:** Implementeer `PaymentRegisteredSender` die dit bericht publiceert naar queue `facturatie.incoming` na elke succesvolle betaling.
>
> **Actiepunt Facturatie:** Voeg een consumer toe op `facturatie.incoming` die berichten met `source=frontend` en `type=payment_registered` verwerkt → zet invoice op 'paid' in FossBilling.

---

### 11.6 `event_ended` (Frontend → Facturatie)

> **Nieuw — Issue #34.** Frontend stuurt dit bericht **rechtstreeks** naar `facturatie.incoming` (naast het bestaande bericht naar CRM) wanneer een sessie of event is afgelopen. Facturatie heeft dit bericht nodig om de facturatie-flow naar Mailing te triggeren.
> 
> **Consistentie:** Dit bericht is qua structuur identiek aan sectie 5.7, maar wordt hier specifiek gedocumenteerd voor de integratie met Facturatie.

- **Queue:** `facturatie.incoming`
- **Source:** `frontend`
- **Wanneer:** onmiddellijk na het beëindigen van een event/sessie in de frontend.

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" elementFormDefault="qualified">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id"     type="UUIDType"/>
          <xs:element name="timestamp"      type="xs:dateTime"/>
          <xs:element name="source"         type="xs:string" fixed="frontend"/>
          <xs:element name="type"           type="xs:string" fixed="event_ended"/>
          <xs:element name="version"        type="xs:string" fixed="2.0"/>
          <xs:element name="correlation_id" type="UUIDType" minOccurs="0"/>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <xs:element name="session_id" type="xs:string"/>
          <xs:element name="ended_at"   type="xs:dateTime"/>
        </xs:sequence></xs:complexType>
      </xs:element>
    </xs:sequence></xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML

```xml
<message>
  <header>
    <message_id>b3a8c7d6-e5f4-3210-abcd-ef1234567890</message_id>
    <timestamp>2026-05-15T22:00:00Z</timestamp>
    <source>frontend</source>
    <type>event_ended</type>
    <version>2.0</version>
  </header>
  <body>
    <session_id>sess-keynote-001</session_id>
    <ended_at>2026-05-15T22:00:00Z</ended_at>
  </body>
</message>
```

> **Actiepunt Frontend:** Zorg dat de `event_ended` sender ook publiceert naar queue `facturatie.incoming`.
>
> **Actiepunt Facturatie:** Voeg een consumer toe op `facturatie.incoming` die berichten met `source=frontend` en `type=event_ended` verwerkt → trigger mailing van openstaande facturen.

---

### 11.7 `event_ended` (Frontend → Kassa)

> **Consistentie:** Structureel identiek aan §5.7 en §11.6. Frontend publiceert hetzelfde bericht een derde keer, nu naar `kassa.incoming`.

- **Queue:** `kassa.incoming`
- **Source:** `frontend`
- **Wanneer:** onmiddellijk na het beëindigen van een event/sessie in de frontend.

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" elementFormDefault="qualified">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id"     type="UUIDType"/>
          <xs:element name="timestamp"      type="xs:dateTime"/>
          <xs:element name="source"         type="xs:string" fixed="frontend"/>
          <xs:element name="type"           type="xs:string" fixed="event_ended"/>
          <xs:element name="version"        type="xs:string" fixed="2.0"/>
          <xs:element name="correlation_id" type="UUIDType" minOccurs="0"/>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <xs:element name="session_id" type="xs:string"/>
          <xs:element name="ended_at"   type="xs:dateTime"/>
        </xs:sequence></xs:complexType>
      </xs:element>
    </xs:sequence></xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML

```xml
<message>
  <header>
    <message_id>b3a8c7d6-e5f4-3210-abcd-ef1234567890</message_id>
    <timestamp>2026-05-15T22:00:00Z</timestamp>
    <source>frontend</source>
    <type>event_ended</type>
    <version>2.0</version>
  </header>
  <body>
    <session_id>sess-keynote-001</session_id>
    <ended_at>2026-05-15T22:00:00Z</ended_at>
  </body>
</message>
```

> **Actiepunt Frontend:** Publiceer `event_ended` ook naar queue `kassa.incoming` (derde publish, naast `event.ended` en `facturatie.incoming`).
>
> **Actiepunt Kassa:** Voeg een consumer toe op `kassa.incoming` die berichten met `source=frontend` en `type=event_ended` verwerkt → trigger `wallet_lease_return` (§26.3) voor alle actieve leases van de betreffende sessie.

---

## 12. CRM → Mailing

- **Queue:** `crm.to.mailing`

### 12.1 `send_mailing` (CRM → Mailing)

CRM vraagt Mailing om een e-mail te versturen.  
> **Naamwijziging:** was `mailing_status` → nu `send_mailing`. Dit is een **commando**, geen status.

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id" type="UUIDType"/>
          <xs:element name="timestamp"  type="xs:dateTime"/>
          <xs:element name="source"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="crm"/>
            <xs:enumeration value="facturatie"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="send_mailing"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="version"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="2.0"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="correlation_id" type="UUIDType"/>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <xs:element name="campaign_id" type="xs:string"/>
          <xs:element name="subject"     type="xs:string"/>
          <xs:element name="mail_type">
            <xs:simpleType><xs:restriction base="xs:string">
              <xs:enumeration value="registration_confirmation"/>
              <xs:enumeration value="payment_confirmation"/>
              <xs:enumeration value="invoice_ready"/>
              <xs:enumeration value="session_update"/>
              <xs:enumeration value="general_announcement"/>
            </xs:restriction></xs:simpleType>
          </xs:element>
          <xs:element name="recipients">
            <xs:complexType><xs:sequence>
              <xs:element name="recipient" maxOccurs="unbounded">
                <xs:complexType><xs:sequence>
                  <xs:element name="email"         type="xs:string"/>
                  <xs:element name="identity_uuid" type="UUIDType"/>
                  <xs:element name="contact">
                    <xs:complexType><xs:sequence>
                      <xs:element name="first_name" type="xs:string"/>
                      <xs:element name="last_name"  type="xs:string"/>
                    </xs:sequence></xs:complexType>
                  </xs:element>
                </xs:sequence></xs:complexType>
              </xs:element>
            </xs:sequence></xs:complexType>
          </xs:element>
          <!-- template_data: JSON string met variabelen voor SendGrid template -->
          <xs:element name="template_data" type="xs:string" minOccurs="0"/>
          <!-- body_html: plain HTML — wanneer geen SendGrid template gebruikt wordt -->
          <xs:element name="body_html" type="xs:string" minOccurs="0"/>
          <!-- attachment: Base64 bijlage (factuur-PDF, badge QR-code) — zie Mailing doc sectie 3 -->
          <xs:element name="attachment" minOccurs="0">
            <xs:complexType>
              <xs:sequence>
                <xs:element name="filename"     type="xs:string"/>
                <xs:element name="content_type" type="xs:string"/>
                <xs:element name="base64_data"  type="xs:string"/>
              </xs:sequence>
            </xs:complexType>
          </xs:element>
        </xs:sequence></xs:complexType>
      </xs:element>
    </xs:sequence></xs:complexType>
  </xs:element>
</xs:schema>
```

> **Bewijs (Mailing doc sectie 3):** Mailing parseert expliciet: *"type, e-mailadres, naam, onderwerp, inhoud, eventuele bijlage"* en voegt Base64-bijlagen toe als SendGrid Attachment.

#### Voorbeeld XML — inschrijvingsbevestiging

```xml
<message>
  <header>
    <message_id>f6d3e4f5-a6b7-8901-defa-901234500021</message_id>
    <timestamp>2026-04-24T09:17:00Z</timestamp>
    <source>crm</source>
    <type>send_mailing</type>
    <version>2.0</version>
    <correlation_id>c3d4e5f6-a7b8-9012-cdef-012345678902</correlation_id>
  </header>
  <body>
    <campaign_id>sg-campaign-0089</campaign_id>
    <subject>Bevestiging inschrijving Shiftfestival 2026</subject>
    <mail_type>registration_confirmation</mail_type>
    <recipients>
      <recipient>
        <email>jan.peeters@ehb.be</email>
        <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
        <contact>
          <first_name>Jan</first_name>
          <last_name>Peeters</last_name>
        </contact>
      </recipient>
    </recipients>
    <template_data>{"session_title":"Keynote: AI in Healthcare","session_date":"15 mei 2026 14:00"}</template_data>
  </body>
</message>
```

---

## 13. Facturatie → Mailing

- **Queue:** `facturatie.to.mailing`
- Facturatie gebruikt **hetzelfde `send_mailing` formaat** als CRM, met `source: facturatie`

### 13.1 `send_mailing` (Facturatie → Mailing)

> **Voor Mailing-team:** jullie consumer moet berichten met `source=facturatie` én `source=crm` verwerken. Het `type` is in beide gevallen `send_mailing`.

#### XSD

> **Facturatie gebruikt exact dezelfde XSD als §12.1 (CRM → Mailing).** De `source`-enum in §12.1 accepteert al zowel `crm` als `facturatie`. Er is geen aparte XSD nodig — valideer inkomende berichten op `facturatie.to.mailing` tegen het schema in §12.1.

#### Voorbeeld XML — factuur klaar

```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>c17f1edc-9d29-4a92-a10e-5b133baa4312</message_id>
    <timestamp>2026-05-14T14:48:09Z</timestamp>
    <source>facturatie</source>
    <type>send_mailing</type>
    <version>2.0</version>
    <correlation_id>f47ac10b-58cc-4372-a567-0e02b2c3d479</correlation_id>
  </header>
  <body>
    <campaign_id>foss-invoice-228</campaign_id>
    <subject>Uw factuur staat klaar</subject>
    <mail_type>invoice_ready</mail_type>
    <recipients>
      <recipient>
        <email>jan.peeters@bedrijf.be</email>
        <identity_uuid>a1b2c3d4-e5f6-7890-abcd-ef1234567890</identity_uuid>
        <contact>
          <first_name>Jan</first_name>
          <last_name>Peeters</last_name>
        </contact>
      </recipient>
    </recipients>
    <template_data>{"invoice_number":"FOSS00228","invoice_date":"2026-05-14","due_date":"2026-05-19","seller":{"company":"Desiderius","address":"Nijverheidskaai 170, 1070 Anderlecht","email":"desiderius@email.com","vat_number":"","iban":"","bic":""},"buyer":{"first_name":"Jan","last_name":"Peeters","email":"jan.peeters@bedrijf.be","address":"...","vat_number":""},"items":[{"description":"Inschrijvingskosten","quantity":1,"unit_price":"250.00","vat_rate":21.0,"vat_amount":"52.50","total":"302.50","currency":"eur"}],"summary":{"subtotal":"250.00","vat_total":"52.50","total":"302.50","currency":"eur"},"payment":{"reference":"+++228/2026/00001+++","method":"on_site"}}</template_data>
    <attachment>
      <filename>factuur-FOSS00228.pdf</filename>
      <content_type>application/pdf</content_type>
      <base64_data>JVBERi0xLjcKMSAwIG9iago8PCAvVHlwZSAvQ2F0...[volledige base64]</base64_data>
    </attachment>
  </body>
</message>
```

---

## 13.5 Facturatie → Frontend

- **Queue:** `facturatie.to.frontend`
- **Triggers:** `new_registration` — na aanmaak van registratiefactuur, `invoice_request` — na aanmaak van factuur voor één consumption order, `event_ended` — per bedrijf na aanmaak van geconsolideerde factuur

Facturatie stuurt na elke succesvolle factuuraanmaak een `invoice_available` bericht naar de Frontend.

### 13.5.1 `invoice_available`

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="header">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="message_id" type="UUIDType"/>
              <xs:element name="timestamp"  type="xs:dateTime"/>
              <xs:element name="source"     type="xs:string" fixed="facturatie"/>
              <xs:element name="type"       type="xs:string" fixed="invoice_available"/>
              <xs:element name="version">
                <xs:simpleType><xs:restriction base="xs:string">
                  <xs:enumeration value="2.0"/>
                </xs:restriction></xs:simpleType>
              </xs:element>
              <xs:element name="correlation_id" type="UUIDType" minOccurs="0"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
        <xs:element name="body">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="identity_uuid" type="UUIDType"/>
              <xs:element name="invoice_id"    type="xs:string"/>
              <xs:element name="pdf_url"       type="xs:anyURI"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML

```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>a3f1c2d4-7e89-4b0a-bc12-3f456d789012</message_id>
    <timestamp>2026-05-06T10:30:00Z</timestamp>
    <source>facturatie</source>
    <type>invoice_available</type>
    <version>2.0</version>
  </header>
  <body>
    <identity_uuid>550e8400-e29b-41d4-a716-446655440000</identity_uuid>
    <invoice_id>142</invoice_id>
    <pdf_url>https://facturatie.desiderius.me/invoice/142</pdf_url>
  </body>
</message>
```

---

---

## 14. CRM → Frontend

- **Queue:** `frontend.incoming`

> ** Queue nog aan te maken:** `frontend.incoming` staat niet in de huidige RabbitMQ configuratie. Het Frontend-team moet deze queue aanmaken en hun consumer (`PaymentRegisteredReceiver`) eraan binden.

### 14.1 `payment_registered` (CRM → Frontend)

CRM informeert de Drupal Frontend over een bevestigde betaling. Frontend gebruikt dit om de betaalstatus van de gebruiker bij te werken.

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="header">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="message_id"     type="UUIDType"/>
              <xs:element name="timestamp"      type="xs:dateTime"/>
              <xs:element name="source"><xs:simpleType><xs:restriction base="xs:string">
                <xs:enumeration value="crm"/></xs:restriction></xs:simpleType></xs:element>
              <xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
                <xs:enumeration value="payment_registered"/></xs:restriction></xs:simpleType></xs:element>
              <xs:element name="version"><xs:simpleType><xs:restriction base="xs:string">
                <xs:enumeration value="2.0"/></xs:restriction></xs:simpleType></xs:element>
              <xs:element name="correlation_id" type="UUIDType" minOccurs="0"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
        <xs:element name="body">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="identity_uuid" type="UUIDType"/>
              <xs:element name="invoice">
                <xs:complexType>
                  <xs:sequence>
                    <xs:element name="id" type="xs:string"/>
                    <xs:element name="amount_paid">
                      <xs:complexType>
                        <xs:simpleContent>
                          <xs:extension base="xs:decimal">
                            <xs:attribute name="currency" type="xs:string" fixed="eur" use="required"/>
                          </xs:extension>
                        </xs:simpleContent>
                      </xs:complexType>
                    </xs:element>
                    <xs:element name="status" type="xs:string" fixed="paid"/>
                  </xs:sequence>
                </xs:complexType>
              </xs:element>
              <!-- payment_context: geeft aan waarvoor betaald werd -->
              <xs:element name="payment_context">
                <xs:simpleType>
                  <xs:restriction base="xs:string">
                    <xs:enumeration value="online_invoice"/>
                    <xs:enumeration value="session_registration"/>
                    <xs:enumeration value="consumption"/>
                  </xs:restriction>
                </xs:simpleType>
              </xs:element>
              <!-- transaction: optioneel — aanwezig wanneer betaaldetails beschikbaar zijn -->
              <xs:element name="transaction" minOccurs="0">
                <xs:complexType>
                  <xs:sequence>
                    <xs:element name="id" type="xs:string"/>
                    <xs:element name="payment_method">
                      <xs:simpleType>
                        <xs:restriction base="xs:string">
                          <xs:enumeration value="company_link"/>
                          <xs:enumeration value="on_site"/>
                          <xs:enumeration value="online"/>
                        </xs:restriction>
                      </xs:simpleType>
                    </xs:element>
                  </xs:sequence>
                </xs:complexType>
              </xs:element>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML

```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>c23d4e5f-6a7b-8901-cdef-234567890123</message_id>
    <timestamp>2026-05-15T22:00:00Z</timestamp>
    <source>crm</source>
    <type>payment_registered</type>
    <version>2.0</version>
  </header>
  <body>
    <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
    <invoice>
      <id>INV-2026-001</id>
      <amount_paid currency="eur">150.00</amount_paid>
      <status>paid</status>
    </invoice>
    <payment_context>online_invoice</payment_context>
    <transaction>
      <id>PAY-ONLINE-9988</id>
      <payment_method>online</payment_method>
    </transaction>
  </body>
</message>
```


---

## 15. Identity Service  Uitzondering op de standaard

> **De Identity Service gebruikt NIET de standaard `<message><header>` envelop.**  
> Dit systeem werkt via snel synchrone RPC (Request/Reply) en heeft zijn eigen platte XML structuur.  
> Elke registratie-flow start verplicht met een Identity-lookup om een officiële `master_uuid` te verkrijgen.

### Hoe werkt RPC in RabbitMQ?

1. De caller stuurt een bericht naar de request-queue met verplichte AMQP properties:  
   - `reply_to`: naam van een tijdelijke (exclusive) antwoord-queue  
   - `correlation_id`: een UUID om het antwoord aan het verzoek te koppelen  
  - `message_id`: unieke ID van het request (verplicht omdat deze flow geen XML-header heeft)
  - `timestamp`: event-tijdstip in UTC (verplicht omdat deze flow geen XML-header heeft)
2. Identity Service verwerkt het verzoek en stuurt het antwoord naar de `reply_to` queue  
3. De caller leest het antwoord op zijn tijdelijke queue, verifieert de `correlation_id`

---

### 15.1 RPC Request — Gebruiker aanmaken

- **Queue:** `identity.user.create.request`
- **Wanneer:** Bij elke nieuwe registratie, vóórdat het `new_registration` bericht naar CRM gestuurd wordt

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <!--
    TYPE   : identity_request (create)
    FLOW   : Elk systeem → Identity Service  (queue: identity.user.create.request)
    LET OP : Geen <messcorrelation_id, message_id en timestamp in als message properties
  -->
  <xs:element name="identity_request">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="email"         type="xs:string"/>
        <xs:element name="source_system" type="xs:string"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML

```xml
<identity_request>
  <email>jan.peeters@ehb.be</email>
  <source_system>frontend</source_system>
</identity_request>
```

> **AMQP properties (stel dit in op het bericht zelf, niet in de XML):**
> ```
> reply_to      = "amq.rabbitmq.reply-to"   (of eigen tijdelijke queue)
> correlation_id = "c3d4e5f6-a7b8-9012-cdef-012345678902"
> message_id     = "req-identity-0001"
> timestamp      = "2026-04-24T09:15:00Z"
> ```

---

### 15.2 RPC Request — Gebruiker opzoeken op e-mail

- **Queue:** `identity.user.lookup.email.request`
- **Wanneer:** Als je de `master_uuid` van een bestaande gebruiker nodig hebt op basis van e-mailadres

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="identity_request">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="email" type="xs:string"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML

```xml
<identity_request>
  <email>jan.peeters@ehb.be</email>
</identity_request>
```

---

### 15.3 RPC Request — Gebruiker opzoeken op UUID

- **Queue:** `identity.user.lookup.uuid.request`
- **Wanneer:** Als je klantdata nodig hebt en enkel de `master_uuid` kent

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="identity_request">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="master_uuid" type="xs:string"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML

```xml
<identity_request>
  <master_uuid>a1b2c3d4-e5f6-7890-abcd-ef1234567890</master_uuid>
</identity_request>
```

---

### 15.4 RPC Response — Identity antwoord (alle 3 de requests)

Identity antwoordt altijd op de `reply_to` queue met hetzelfde formaat.

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <!--
    TYPE   : identity_response
    FLOW   : Identity Service → caller (via reply_to queue)
    LET OP : Geen <message><header> wrapper
    Controleer altijd status = "ok" voor je master_uuid gebruikt.
    Bij status = "error": lees error_code en message voor reden.
  -->
  <xs:element name="identity_response">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="status">
          <xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="ok"/>
            <xs:enumeration value="error"/>
          </xs:restriction></xs:simpleType>
        </xs:element>
        <xs:element name="user" minOccurs="0">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="master_uuid" type="xs:string"/>
              <xs:element name="email"       type="xs:string"/>
              <xs:element name="created_by"  type="xs:string"/>
              <xs:element name="created_at"  type="xs:dateTime"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
        <xs:element name="error_code" type="xs:string" minOccurs="0"/>
        <xs:element name="message"    type="xs:string" minOccurs="0"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML — succes

```xml
<identity_response>
  <status>ok</status>
  <user>
    <master_uuid>a1b2c3d4-e5f6-7890-abcd-ef1234567890</master_uuid>
    <email>jan.peeters@ehb.be</email>
    <created_by>frontend</created_by>
    <created_at>2026-04-24T09:15:00Z</created_at>
  </user>
</identity_response>
```

#### Voorbeeld XML — fout (e-mail al in gebruik)

```xml
<identity_response>
  <status>error</status>
  <error_code>EMAIL_ALREADY_EXISTS</error_code>
  <message>Een gebruiker met dit e-mailadres bestaat al. Gebruik lookup endpoint.</message>
</identity_response>
```

---

### 15.5 Fanout Event — `UserCreated`

Zodra Identity succesvol een nieuwe gebruiker aanmaakt, broadcast het dit naar **alle systemen** via de `user.events` fanout exchange.

- **Exchange:** `user.events` (fanout)
- **Elk team** dat klantdata beheert (CRM, Kassa, Facturatie) moet een eigen queue binden aan deze exchange

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <!--
    TYPE   : user_event (UserCreated)
    FLOW   : Identity Service → Alle teams (exchange: user.events, fanout)
    LET OP : Geen <message><header> wrapper — eigen Identity formaat
  -->
  <xs:element name="user_event">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="event">
          <xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="UserCreated"/>
          </xs:restriction></xs:simpleType>
        </xs:element>
        <xs:element name="master_uuid"   type="xs:string"/>
        <xs:element name="email"         type="xs:string"/>
        <xs:element name="source_system" type="xs:string"/>
        <xs:element name="timestamp"     type="xs:dateTime"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML

```xml
<user_event>
  <event>UserCreated</event>
  <master_uuid>a1b2c3d4-e5f6-7890-abcd-ef1234567890</master_uuid>
  <email>jan.peeters@ehb.be</email>
  <source_system>frontend</source_system>
  <timestamp>2026-04-24T09:15:01Z</timestamp>
</user_event>
```

---

### 15.6 Registratie Flow — Stap voor stap (Frontend als voorbeeld)

> Dit is de verplichte volgorde bij elke nieuwe inschrijving. Sla stap 1–3 nooit over.

```
1. Gebruiker vult formulier in op de website (Drupal)
         ↓
2. Frontend stuurt RPC naar identity.user.create.request
   <identity_request>
     <email>jan.peeters@ehb.be</email>
     <source_system>frontend</source_system>
   </identity_request>
         ↓
3. Frontend wacht op identity_response (reply_to queue)
   → status = "ok"  → haal master_uuid op uit <user>
   → status = "error" → toon foutmelding aan gebruiker
         ↓
4. Frontend bouwt v2.0 <message> op voor new_registration
   en plaatst master_uuid in het customer-blok
         ↓
5. Frontend stuurt new_registration naar crm.incoming
```

> **Waarom is dit verplicht?**  
> CRM (Salesforce) weigert een `new_registration` te verwerken zonder geldige `master_uuid`. De Identity Service is de enige in het systeem die idempotent UUIDs genereert (uuid7). Zo kan dezelfde persoon zich nooit twee keer aanmelden met hetzelfde e-mailadres.

## 16. RabbitMQ Queue & Exchange Overzicht

| Van | Naar | Queue | Exchange / Routing |
|-----|------|-------|-------------------|
| Frontend | CRM | `crm.incoming` | — |
| Frontend | Facturatie | `facturatie.incoming` | — (payment_registered direct, sectie 11.5) |
| Kassa | CRM | `crm.incoming` | exchange: `kassa.exchange`, routing: `kassa.payments.consumption` / `registration` / `refund` / `invoice` / `badge` |
| IoT (Raspberry Pi) | Kassa | `kassa.incoming` | exchange: `kassa.exchange`, routing: `kassa.incoming` |
| Planning | CRM | `planning.session.events` | exchange: `planning.exchange`, routing: `planning.session.*` |
| Facturatie | CRM | `crm.incoming` | — |
| Mailing | CRM | `crm.incoming` | — |
| CRM | Kassa | `kassa.incoming` | exchange: `kassa.exchange` (topic) |
| CRM | Facturatie | `facturatie.incoming` | — |
| CRM | Mailing | `crm.to.mailing` | — |
| CRM | Planning | `planning.calendar.invite` | exchange: `calendar.exchange`, routing: `crm.to.planning.cancel_registration` |
| Facturatie | Mailing | `facturatie.to.mailing` | — |
| Facturatie | Frontend | `facturatie.to.frontend` | — (invoice_available) |
| Monitoring | Mailing | `to_mailing` | default exchange (`""`), platte `<alert>` root (intern formaat, sectie 4) |
| Alle teams | Monitoring | `heartbeat` | default exchange (`""`), routing_key: `heartbeat` (direct naar queue) |
| Alle teams | Monitoring | `logs` | default exchange (`""`), routing_key: `logs` |
| Frontend/CRM | Planning | `planning.calendar.invite` | exchange: `calendar.exchange`, routing: `frontend.to.planning.calendar.invite` |
| Planning | Frontend | reply_to queue (RPC) | exchange: `calendar.exchange`, routing: `planning.to.frontend.calendar.invite.confirmed` |
| Frontend/CRM | Planning | `planning.session.events` | exchange: `planning.exchange`, routing: `frontend.to.planning.session.view` (RPC) |
| Planning | Frontend | reply_to queue (RPC) | exchange: `planning.exchange`, routing: `planning.to.frontend.session.view.response` |
| Frontend | Planning | `planning.session.events` | exchange: `planning.exchange`, routing: `frontend.to.planning.session.create` / `update` / `delete` |
| Planning | Frontend | — | exchange: `planning.exchange`, routing: `planning.to.frontend.session.created` / `updated` / `deleted` |
| **Alle teams** | **Identity** | `identity.user.create.request` | RPC (Sectie 15) |
| **Alle teams** | **Identity** | `identity.user.lookup.email.request` | RPC |
| **Alle teams** | **Identity** | `identity.user.lookup.uuid.request` | RPC |
| **Identity** | **Alle teams** | — | exchange: `user.events` (**fanout**) |
| **CRM** | **Alle teams** | — | exchange: `frontend.user.unregistered` (**fanout**) |
| **CRM** | **Planning** | `planning.registration` | exchange: `planning.exchange`, routing: `crm.to.planning.registration_confirmed` |
| **Planning** | **Alle teams** | — | exchange: `planning.exchange`, routing: `planning.session.occupancy` (Broadcast) |
| **Kassa** | **CRM** | `crm.incoming` | exchange: `kassa.exchange`, routing: `kassa.to.crm.wallet_lease_request` |
| **CRM** | **Kassa** | `kassa.incoming` | exchange: `crm.exchange`, routing: `crm.to.kassa.wallet_lease_grant` |
| **Kassa** | **CRM** | `crm.incoming` | exchange: `kassa.exchange`, routing: `kassa.to.crm.wallet_lease_return` |
| **Authority** | **Alle teams** | — | exchange: `wallet.updates`, routing: `wallet.balance_update` (Broadcast) |
| **Frontend** | **CRM** | `crm.incoming` | exchange: `frontend.exchange`, routing: `frontend.to.crm.wallet_topup_request` |
| **CRM** | **Kassa** | `kassa.incoming` | exchange: `crm.exchange`, routing: `crm.to.kassa.wallet_remote_topup` |

### 16.1 Dead Letter Queues (DLQ)
Elke service is verantwoordelijk voor zijn eigen DLQ-afhandeling bij validatiefouten of crashes.

| Service | DLQ Name |
|---------|----------|
| CRM | `crm.dead-letter` |
| Facturatie | `facturatie.dlq` |
| Kassa | `kassa.dlx` |
| Planning | `planning.dlx` |


---

## 17. Per-Team Samenvatting

> Overzicht van alle flows per team **met exchange- en routing key details**. Gebruik de Quick Reference bovenaan voor een overzicht zonder routingdetails.

---

### Team Frontend

| Richting | Berichttype | Queue / Exchange / Routing |
|----------|-------------|---------------------------|
| → CRM | `new_registration`, `user_created`, `user_updated`, `user_deleted`, `user_registered` | queue: `crm.incoming` |
| → CRM | `cancel_registration`, `company_*`, `company_member_removed` | queue: `crm.incoming` |
| → CRM | `user_checkin` | queue: `crm.incoming` |
| → Facturatie, Kassa | `event_ended` | queue: `event.ended` + `facturatie.incoming` + `kassa.incoming` |
| → Facturatie | `payment_registered` | queue: `facturatie.incoming` |
| → Planning | `calendar_invite` | exchange: `calendar.exchange`, routing: `frontend.to.planning.calendar.invite` |
| → Planning | `session_create_request` | exchange: `planning.exchange`, routing: `frontend.to.planning.session.create` |
| → Planning | `session_update_request` | exchange: `planning.exchange`, routing: `frontend.to.planning.session.update` |
| → Planning | `session_delete_request` | exchange: `planning.exchange`, routing: `frontend.to.planning.session.delete` |
| → Planning | `session_view_request` (RPC) | exchange: `planning.exchange`, routing: `frontend.to.planning.session.view` |
| → Planning | `user_sessions_request` (RPC) | exchange: `planning.exchange`, routing: `frontend.to.planning.user_sessions_request` |
| → Identity | `identity_request` (RPC) | queue: `identity.user.create.request` |
| ← CRM | `payment_registered` | queue: `frontend.incoming` |
| ← CRM / Facturatie | `vat_validation_error` | queue: `frontend.incoming` |
| ← Kassa | `payment_status` | queue: `frontend.payments`, routing: `kassa.frontend.payment` |
| ← Kassa | `wallet_balance_update` | queue: `frontend.payments`, routing: `kassa.frontend.wallet` |
| ← Planning | `calendar_invite_confirmed` | reply_to queue, routing: `planning.to.frontend.calendar.invite.confirmed` |
| ← Planning | `session_view_response` (RPC) | reply_to queue, routing: `planning.to.frontend.session.view.response` |
| ← Planning | `user_sessions_response` (RPC) | reply_to queue, routing: `planning.to.frontend.user_sessions_response` |
| ← Planning | `session_created` | exchange: `planning.exchange`, routing: `planning.to.frontend.session.created` |
| ← Planning | `session_updated` | exchange: `planning.exchange`, routing: `planning.to.frontend.session.updated` |
| ← Planning | `session_deleted` | exchange: `planning.exchange`, routing: `planning.to.frontend.session.deleted` |
| ← Facturatie | `invoice_available` | queue: `frontend.incoming` |

**Verplichte registratie-volgorde:**
1. Stuur RPC naar `identity.user.create.request` met e-mailadres
2. Wacht op `identity_response` → haal `master_uuid` op
3. Pas dán stuur je `new_registration` naar CRM met die `master_uuid`

---

### Team Kassa (Odoo POS)

| Richting | Berichttype | Queue / Routing key |
|----------|-------------|---------------------|
| → CRM | `consumption_order` | routing: `kassa.payments.consumption` |
| → CRM | `payment_registered` | routing: `kassa.payments.consumption` of `kassa.payments.registration` |
| → CRM | `badge_assigned` | routing: `kassa.payments.badge` |
| → CRM | `refund_processed` | routing: `kassa.payments.refund` |
| → CRM | `invoice_request` | routing: `kassa.payments.invoice` |
| → Frontend | `payment_status` | queue: `frontend.payments`, routing: `kassa.frontend.payment` |
| → Frontend | `wallet_balance_update` | exchange: `kassa.exchange`, routing: `kassa.frontend.wallet` |
| → kassa.errors | `system_error` | queue: `kassa.errors` |
| ← IoT / Kassa | `badge_scanned` | queue: `kassa.incoming` |
| ← CRM | `new_registration`, `profile_update`, `cancel_registration` | queue: `kassa.incoming` |
| ← Frontend | `event_ended` | queue: `kassa.incoming` |
| → Planning | `user_sessions_request` (RPC) | exchange: `planning.exchange`, routing: `kassa.to.planning.user_sessions_request` |
| ← Planning | `user_sessions_response` (RPC) | reply_to queue, routing: `planning.to.kassa.user_sessions_response` |

---

### Team Planning (Office365 / Outlook)

| Richting | Berichttype | Exchange / Queue / Routing key |
|----------|-------------|--------------------------------|
| → CRM | `session_created` | exchange: `planning.exchange`, routing: `planning.session.created` |
| → CRM | `session_updated` | exchange: `planning.exchange`, routing: `planning.session.updated` |
| → CRM | `session_deleted` | exchange: `planning.exchange`, routing: `planning.session.deleted` |
| → Frontend | `session_created` | exchange: `planning.exchange`, routing: `planning.to.frontend.session.created` |
| → Frontend | `session_updated` | exchange: `planning.exchange`, routing: `planning.to.frontend.session.updated` |
| → Frontend | `session_deleted` | exchange: `planning.exchange`, routing: `planning.to.frontend.session.deleted` |
| → Frontend | `calendar_invite_confirmed` | exchange: `calendar.exchange`, routing: `planning.to.frontend.calendar.invite.confirmed` |
| → Frontend | `session_view_response` (RPC) | reply_to queue, routing: `planning.to.frontend.session.view.response` |
| ← Frontend | `calendar_invite` | exchange: `calendar.exchange`, routing: `frontend.to.planning.calendar.invite` |
| ← Frontend | `session_create_request` | exchange: `planning.exchange`, routing: `frontend.to.planning.session.create` |
| ← Frontend | `session_update_request` | exchange: `planning.exchange`, routing: `frontend.to.planning.session.update` |
| ← Frontend | `session_delete_request` | exchange: `planning.exchange`, routing: `frontend.to.planning.session.delete` |
| ← Frontend | `session_view_request` (RPC) | exchange: `planning.exchange`, routing: `frontend.to.planning.session.view` |
| ← Kassa | `user_sessions_request` (RPC) | exchange: `planning.exchange`, routing: `kassa.to.planning.user_sessions_request` |
| ← Frontend | `user_sessions_request` (RPC) | exchange: `planning.exchange`, routing: `frontend.to.planning.user_sessions_request` |
| → Kassa/Frontend | `user_sessions_response` (RPC) | reply_to queue, routing: `planning.to.kassa.user_sessions_response` / `planning.to.frontend.user_sessions_response` |
| ← CRM | `cancel_registration` | exchange: `calendar.exchange`, routing: `crm.to.planning.cancel_registration` |

**Belangrijk:** Gebruikt Master UUID via `correlation_id` voor alle sessie-gerelateerde berichten. `correlation_id` = de `session_uuid` uit de Planning database.

---

### Team Facturatie (FossBilling)

| Richting | Berichttype | Queue / Routing |
|----------|-------------|-----------------|
| ← CRM | `invoice_request` | queue: `facturatie.incoming` |
| ← CRM | `invoice_cancelled` | queue: `facturatie.incoming` |
| ← CRM | `consumption_order` (passthrough) | queue: `facturatie.incoming` |
| ← CRM | `new_registration`, `profile_update` | queue: `facturatie.incoming` |
| ← Frontend | `payment_registered` (direct) | queue: `facturatie.incoming` |
| ← Frontend | `event_ended` | queue: `facturatie.incoming` |
| → CRM | `invoice_status` | queue: `crm.incoming` |
| → CRM | `payment_registered` | queue: `crm.incoming` |
| → Mailing | `send_mailing` | queue: `facturatie.to.mailing` |
| → Frontend | `invoice_available` | queue: `frontend.incoming` |
| → Frontend | `vat_validation_error` | queue: `frontend.incoming` |

---

### Team Mailing (SendGrid)

| Richting | Berichttype | Queue |
|----------|-------------|-------|
| ← CRM | `send_mailing` | queue: `crm.to.mailing` |
| ← Facturatie | `send_mailing` | queue: `facturatie.to.mailing` |
| ← Monitoring | `system_alert` (intern formaat) | queue: `to_mailing` |
| → CRM | `mailing_status` | queue: `crm.incoming` |

**Opmerking:** Mailing verwerkt `send_mailing` van zowel `source=crm` als `source=facturatie` — zelfde schema, andere queue.

---

### Team Monitoring (ELK Stack)

| Richting | Berichttype | Queue |
|----------|-------------|-------|
| ← Alle teams | `heartbeat` (via sidecar) | queue: `heartbeat` |
| ← Alle teams | `log` | queue: `logs` |
| → Mailing | `system_alert` (intern formaat) | queue: `to_mailing` |

---

### Team CRM (Salesforce)

CRM is de centrale data-hub. Zie secties 5–14 voor alle gedetailleerde flows.

| Richting | Berichttype | Queue / Exchange / Routing |
|----------|-------------|---------------------------|
| ← Frontend | `new_registration`, `user_*`, `company_*`, `cancel_registration`, `event_ended`, `user_checkin` | queue: `crm.incoming` |
| ← Planning | `session_created`, `session_updated`, `session_deleted` | exchange: `planning.exchange`, routing: `planning.session.*` |
| ← Kassa | `consumption_order`, `payment_registered`, `badge_assigned`, `refund_processed`, `invoice_request` | routing: `kassa.payments.*` |
| ← Facturatie | `invoice_status`, `payment_registered` | queue: `crm.incoming` |
| ← Mailing | `mailing_status` | queue: `crm.incoming` |
| ← Identity | `user_event` (fanout) | exchange: `user.events` (fanout) |
| → Kassa | `new_registration`, `profile_update`, `cancel_registration` | queue: `kassa.incoming` |
| → Facturatie | `profile_update`, `invoice_request`, `consumption_order` | queue: `facturatie.incoming` |
| → Mailing | `send_mailing` | queue: `crm.to.mailing` |
| → Frontend | `payment_registered`, `vat_validation_error` | queue: `frontend.incoming` |
| → Planning | `cancel_registration` | exchange: `calendar.exchange`, routing: `crm.to.planning.cancel_registration` |
| → Identity | `identity_request` (RPC) | queue: `identity.user.create.request` |

## 18. Frontend ← Kassa (Direct flows)


> **Let op:** Deze berichten gaan **niet** via CRM. Kassa stuurt deze direct naar de `frontend.payments` queue.
> Frontend moet luisteren op deze queue voor betaal- en saldo-updates.

- **Queue:** `frontend.payments`
- **Exchange:** `kassa.exchange` (topic)
- **Routing keys:**
  - `kassa.frontend.payment` → `payment_status` berichten
  - `kassa.frontend.wallet` → `wallet_balance_update` berichten

| Richting | Type | Routing key |
|----------|------|-------------|
| ← Kassa | `payment_status` | `kassa.frontend.payment` |
| ← Kassa | `wallet_balance_update` | `kassa.frontend.wallet` |

**XSD & XML:** Exact identiek aan Sectie 6.7 en 6.8.

> **Voor Frontend-team:** Jullie user story zegt "receive messages via RabbitMQ (session.update, payment_status, badge.assigned)". De routing is:
> - `payment_status` ← Kassa direct (routing key: `kassa.frontend.payment`)
> - `wallet_balance_update` ← Kassa direct (routing key: `kassa.frontend.wallet`)
> - `payment_registered` ← CRM (queue: `frontend.incoming`) — zie Sectie 14
> - `session_updated` ← Planning via CRM? Of direct? **Afstemmen met Planning-team.**
> - `badge_assigned` — wordt verwerkt door CRM, Kassa stuurt dit naar `crm.incoming`. Frontend ontvangt geen directe badge_assigned.

---

## 19. Frontend ↔ Planning (Directe flows)

> **GECENTRALISEERD:** Deze flows zijn de officiële standaard voor de communicatie tussen Frontend en Planning. 
> Ze zijn essentieel voor het ophalen van sessiedata (`session_view_request/response`) die getoond wordt op de frontend zodat gebruikers zich kunnen inschrijven.
> Deze flows gaan **direct** tussen Frontend en Planning, niet via CRM.

---

### 19.1 `user_checkin`

- **Queue:** `crm.incoming`
- **Wanneer:** bezoeker incheckt via badge-scan aan de inkom

> ** Fixes t.o.v. v1.0 codebase:**
> `xmlns`, `targetNamespace` verwijderd.
> `<receiver>` tag **verwijderd** (breekt Regel 1!).
> `version`: `"1.0"` → `"2.0"`.
> Type: `user.checkin` → `user_checkin` (snake_case, Regel 1).
> `session_id` toegevoegd (optioneel — voor opkomst per spreker tracking door Monitoring).
> `checkin_at` hernoemd van `timestamp` (was dubbelop met header.timestamp).

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="header">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="message_id" type="UUIDType"/>
              <xs:element name="timestamp"  type="xs:dateTime"/>
              <xs:element name="source">
                <xs:simpleType><xs:restriction base="xs:string">
                  <xs:enumeration value="frontend"/>
                  <xs:enumeration value="kassa"/>
                </xs:restriction></xs:simpleType>
              </xs:element>
              <xs:element name="type">
                <xs:simpleType><xs:restriction base="xs:string">
                  <xs:enumeration value="user_checkin"/>
                </xs:restriction></xs:simpleType>
              </xs:element>
              <xs:element name="version">
                <xs:simpleType><xs:restriction base="xs:string">
                  <xs:enumeration value="2.0"/>
                </xs:restriction></xs:simpleType>
              </xs:element>
              <xs:element name="correlation_id" type="UUIDType" minOccurs="0"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
        <xs:element name="body">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="identity_uuid"    type="UUIDType"/>
              <xs:element name="badge_id"   type="xs:string"/>
              <!-- session_id: optioneel — voor opkomst per sessie tracking -->
              <xs:element name="session_id" type="xs:string" minOccurs="0"/>
              <xs:element name="checkin_at" type="xs:dateTime"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML

```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>f6a7b8c9-d0e1-2345-fabc-345678900005</message_id>
    <timestamp>2026-05-15T13:58:00Z</timestamp>
    <source>kassa</source>
    <type>user_checkin</type>
    <version>2.0</version>
  </header>
  <body>
    <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
    <badge_id>BADGE-0042</badge_id>
    <session_id>sess-keynote-001</session_id>
    <checkin_at>2026-05-15T13:58:00Z</checkin_at>
  </body>
</message>
```

---

### 19.0 OAuth Token Registration (REST API)

Voordat gebruikers hun kalender kunnen synchroniseren, moet elke gebruiker na het inloggen eenmalig zijn OAuth-tokens registreren bij de Planning Service.

- **Endpoint:** `POST http://<planning-service-host>:30050/api/tokens`
- **Auth:** `Authorization: Bearer <API_TOKEN_SECRET>`
- **Content-Type:** `application/json`

**Request Body:**
```json
{
  "identity_uuid":       "e8b27c1d-4f2a-4b3e-9c5f-123456789abc",
  "access_token":  "eyJ...",
  "refresh_token": "0.A...",
  "expires_in":    3600
}
```

| Veld | Verplicht | Beschrijving |
|------|-----------|--------------|
| `identity_uuid` | ✅ | Master UUID van de gebruiker (moet matchen met `calendar_invite`) |
| `access_token` | ✅ | Microsoft OAuth access token |
| `refresh_token` | ✅ | Microsoft OAuth refresh token |
| `expires_in` | ❌ | Seconden tot verloop (default: 3600) |

**Response:**
```json
{ "status": "ok", "identity_uuid": "e8b27c1d-4f2a-4b3e-9c5f-123456789abc" }
```

> **Security Note:** Tokens worden encrypted at rest (Fernet) opgeslagen. Planning refresht ze automatisch.

---

### 19.2 `session_view_request` / `session_view_response` (RPC) ~~DEPRECATED~~

> **⚠️ Verwijderd in v2.3:** Planning is als service weggevallen. Deze RPC bestaat niet meer. Sessiedata komt nu via `session_created` / `session_updated` / `session_deleted` push-berichten van Frontend naar Kassa (zie sectie 19.8).

- **Request exchange:** `planning.exchange` *(niet meer actief)*
- **Request routing key:** `frontend.to.planning.session.view` *(niet meer actief)*

#### XSD — Request

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="header">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="message_id"     type="UUIDType"/>
              <xs:element name="timestamp"      type="xs:dateTime"/>
              <xs:element name="source">
                <xs:simpleType><xs:restriction base="xs:string">
                  <xs:enumeration value="frontend"/>
                  <xs:enumeration value="crm"/>
                </xs:restriction></xs:simpleType>
              </xs:element>
              <xs:element name="type">
                <xs:simpleType><xs:restriction base="xs:string">
                  <xs:enumeration value="session_view_request"/>
                </xs:restriction></xs:simpleType>
              </xs:element>
              <xs:element name="version">
                <xs:simpleType><xs:restriction base="xs:string">
                  <xs:enumeration value="2.0"/>
                </xs:restriction></xs:simpleType>
              </xs:element>
              <xs:element name="correlation_id" type="UUIDType" minOccurs="0"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
        <xs:element name="body">
          <xs:complexType>
            <xs:sequence>
              <!-- session_id optioneel: afwezig = alle sessies ophalen -->
              <xs:element name="session_id" type="xs:string" minOccurs="0"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
```

#### XSD — Response

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="header">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="message_id"     type="UUIDType"/>
              <xs:element name="timestamp"      type="xs:dateTime"/>
              <xs:element name="source"         type="xs:string" fixed="planning"/>
              <xs:element name="type">
                <xs:simpleType><xs:restriction base="xs:string">
                  <xs:enumeration value="session_view_response"/>
                </xs:restriction></xs:simpleType>
              </xs:element>
              <xs:element name="version"        type="xs:string" fixed="2.0"/>
              <xs:element name="correlation_id" type="UUIDType" minOccurs="0"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
        <xs:element name="body">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="request_message_id"  type="xs:string"/>
              <xs:element name="requested_session_id" type="xs:string" minOccurs="0"/>
              <xs:element name="status">
                <xs:simpleType>
                  <xs:restriction base="xs:string">
                    <xs:enumeration value="ok"/>
                    <xs:enumeration value="not_found"/>
                  </xs:restriction>
                </xs:simpleType>
              </xs:element>
              <xs:element name="session_count" type="xs:integer"/>
              <xs:element name="sessions">
                <xs:complexType>
                  <xs:sequence>
                    <xs:element name="session" maxOccurs="unbounded" minOccurs="0">
                      <xs:complexType>
                        <xs:sequence>
                          <xs:element name="session_id"      type="xs:string"/>
                          <xs:element name="title"           type="xs:string"/>
                          <xs:element name="start_datetime"  type="xs:dateTime"/>
                          <xs:element name="end_datetime"    type="xs:dateTime"/>
                          <xs:element name="location"        type="xs:string"/>
                          <xs:element name="session_type"    type="xs:string"/>
                          <xs:element name="status"          type="xs:string"/>
                          <xs:element name="max_attendees"   type="xs:integer"/>
                          <xs:element name="current_attendees" type="xs:integer"/>
                          <!-- Price per session (optional; absent = free or unknown) -->
                          <xs:element name="price" minOccurs="0">
                            <xs:complexType>
                              <xs:simpleContent>
                                <xs:extension base="xs:decimal">
                                  <xs:attribute name="currency" type="xs:string" fixed="eur" use="required"/>
                                </xs:extension>
                              </xs:simpleContent>
                            </xs:complexType>
                          </xs:element>
                          <xs:element name="speaker" minOccurs="0">
                            <xs:complexType>
                              <xs:sequence>
                                <xs:element name="identity_uuid" type="UUIDType" minOccurs="0"/>
                                <xs:element name="contact">
                                  <xs:complexType>
                                    <xs:sequence>
                                      <xs:element name="first_name" type="xs:string"/>
                                      <xs:element name="last_name"  type="xs:string"/>
                                    </xs:sequence>
                                  </xs:complexType>
                                </xs:element>
                                <xs:element name="organisation" type="xs:string" minOccurs="0"/>
                                <xs:element name="email"        type="xs:string" minOccurs="0"/>
                              </xs:sequence>
                            </xs:complexType>
                          </xs:element>
                        </xs:sequence>
                      </xs:complexType>
                    </xs:element>
                  </xs:sequence>
                </xs:complexType>
              </xs:element>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML — Request (Specifiek)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>a1b2c3d4-e5f6-7890-abcd-ef1234567890</message_id>
    <timestamp>2026-05-15T09:00:00Z</timestamp>
    <source>frontend</source>
    <type>session_view_request</type>
    <version>2.0</version>
    <correlation_id>c1d2e3f4-a5b6-7890-cdef-012345678901</correlation_id>
  </header>
  <body>
    <session_id>sess-keynote-001</session_id>
  </body>
</message>
```

#### Voorbeeld XML — Request (Alles)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>f9e8d7c6-b5a4-3210-9876-543210fedcba</message_id>
    <timestamp>2026-05-15T09:05:00Z</timestamp>
    <source>frontend</source>
    <type>session_view_request</type>
    <version>2.0</version>
  </header>
  <body>
    <!-- session_id afwezig voor ophalen van alle sessies -->
  </body>
</message>
```

#### Voorbeeld XML — Response (Specifiek)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>b2c3d4e5-f6a7-8901-bcde-f12345678901</message_id>
    <timestamp>2026-05-15T09:00:01Z</timestamp>
    <source>planning</source>
    <type>session_view_response</type>
    <version>2.0</version>
    <correlation_id>c1d2e3f4-a5b6-7890-cdef-012345678901</correlation_id>
  </header>
  <body>
    <request_message_id>a1b2c3d4-e5f6-7890-abcd-ef1234567890</request_message_id>
    <requested_session_id>sess-keynote-001</requested_session_id>
    <status>ok</status>
    <session_count>1</session_count>
    <sessions>
      <session>
        <session_id>sess-keynote-001</session_id>
        <title>Keynote: AI in Healthcare</title>
        <start_datetime>2026-05-15T14:00:00Z</start_datetime>
        <end_datetime>2026-05-15T15:00:00Z</end_datetime>
        <location>Aula A - Campus Jette</location>
        <session_type>keynote</session_type>
        <status>published</status>
        <max_attendees>120</max_attendees>
        <current_attendees>0</current_attendees>
        <price currency="eur">0.00</price>
        <speaker>
          <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
          <contact>
            <first_name>Sarah</first_name>
            <last_name>Leclercq</last_name>
          </contact>
          <organisation>UZ Brussel</organisation>
          <email>s.leclercq@uzbrussel.be</email>
        </speaker>
      </session>
    </sessions>
  </body>
</message>
```

#### Voorbeeld XML — Response (Alles)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>d4e5f6a7-b2c3-8901-bcde-f12345678901</message_id>
    <timestamp>2026-05-15T09:05:01Z</timestamp>
    <source>planning</source>
    <type>session_view_response</type>
    <version>2.0</version>
    <correlation_id>f9e8d7c6-b5a4-3210-9876-543210fedcba</correlation_id>
  </header>
  <body>
    <request_message_id>f9e8d7c6-b5a4-3210-9876-543210fedcba</request_message_id>
    <status>ok</status>
    <session_count>2</session_count>
    <sessions>
      <session>
        <session_id>sess-keynote-001</session_id>
        <title>Keynote: AI in Healthcare</title>
        <!-- ... -->
      </session>
      <session>
        <session_id>sess-workshop-002</session_id>
        <title>Workshop: Machine Learning Basics</title>
        <!-- ... -->
      </session>
    </sessions>
  </body>
</message>
```

---

### 19.3 `calendar_invite` / `calendar_invite_confirmed`

Frontend vraagt Planning om een Office365/Outlook kalenderafspraak aan te maken voor een ingeschreven gebruiker.

- **Invite exchange:** `calendar.exchange`
- **Invite routing key:** `frontend.to.planning.calendar.invite`
- **Confirmed exchange:** `calendar.exchange`
- **Confirmed routing key:** `planning.to.frontend.calendar.invite.confirmed` (op reply_to queue)

#### XSD — calendar_invite (Frontend → Planning)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="header">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="message_id"     type="xs:string"/>
              <xs:element name="timestamp"      type="xs:dateTime"/>
              <xs:element name="source">
                <xs:simpleType><xs:restriction base="xs:string">
                  <xs:enumeration value="frontend"/>
                  <xs:enumeration value="crm"/>
                </xs:restriction></xs:simpleType>
              </xs:element>
              <xs:element name="type">
                <xs:simpleType><xs:restriction base="xs:string">
                  <xs:enumeration value="calendar_invite"/>
                </xs:restriction></xs:simpleType>
              </xs:element>
              <xs:element name="version">
                <xs:simpleType><xs:restriction base="xs:string">
                  <xs:enumeration value="2.0"/>
                </xs:restriction></xs:simpleType>
              </xs:element>
              <xs:element name="correlation_id" type="xs:string" minOccurs="0"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
        <xs:element name="body">
          <xs:complexType>
            <xs:sequence>
              <!-- identity_uuid: de master_uuid van de Identity Service -->
              <xs:element name="identity_uuid"  type="UUIDType"/>
              <xs:element name="session_id"     type="xs:string"/>
              <xs:element name="title"          type="xs:string"/>
              <xs:element name="start_datetime" type="xs:dateTime"/>
              <xs:element name="end_datetime"   type="xs:dateTime"/>
              <xs:element name="location"       type="xs:string" minOccurs="0"/>
              <!-- attendee_email: VERPLICHT — e-mailadres waarvoor de agenda-afspraak aangemaakt wordt -->
              <xs:element name="attendee_email" type="xs:string"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
```

#### XSD — calendar_invite_confirmed (Planning → Frontend)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="header">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="message_id"     type="xs:string"/>
              <xs:element name="timestamp"      type="xs:dateTime"/>
              <xs:element name="source">
                <xs:simpleType><xs:restriction base="xs:string">
                  <xs:enumeration value="planning"/>
                </xs:restriction></xs:simpleType>
              </xs:element>
              <xs:element name="type">
                <xs:simpleType><xs:restriction base="xs:string">
                  <xs:enumeration value="calendar_invite_confirmed"/>
                </xs:restriction></xs:simpleType>
              </xs:element>
              <xs:element name="version">
                <xs:simpleType><xs:restriction base="xs:string">
                  <xs:enumeration value="2.0"/>
                </xs:restriction></xs:simpleType>
              </xs:element>
              <xs:element name="correlation_id" type="xs:string" minOccurs="0"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
        <xs:element name="body">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="session_id"          type="xs:string"/>
              <xs:element name="original_message_id" type="xs:string"/>
              <xs:element name="status">
                <xs:simpleType><xs:restriction base="xs:string">
                  <xs:enumeration value="confirmed"/>
                  <xs:enumeration value="failed"/>
                </xs:restriction></xs:simpleType>
              </xs:element>
              <xs:element name="ics_url" type="xs:string" minOccurs="0"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML — calendar_invite

```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>c3d4e5f6-a7b8-9012-cdef-012345678902</message_id>
    <timestamp>2026-04-24T09:17:00Z</timestamp>
    <source>frontend</source>
    <type>calendar_invite</type>
    <version>2.0</version>
    <correlation_id>cal-req-4821</correlation_id>
  </header>
  <body>
    <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
    <session_id>sess-keynote-001</session_id>
    <title>Keynote: AI in Healthcare</title>
    <start_datetime>2026-05-15T14:00:00Z</start_datetime>
    <end_datetime>2026-05-15T15:00:00Z</end_datetime>
    <location>Aula A - Campus Jette</location>
    <attendee_email>jan.peeters@ehb.be</attendee_email>
  </body>
</message>
```

#### Voorbeeld XML — calendar_invite_confirmed

```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>d4e5f6a7-b8c9-0123-defa-123456789003</message_id>
    <timestamp>2026-04-24T09:17:02Z</timestamp>
    <source>planning</source>
    <type>calendar_invite_confirmed</type>
    <version>2.0</version>
    <correlation_id>cal-req-4821</correlation_id>
  </header>
  <body>
    <session_id>sess-keynote-001</session_id>
    <original_message_id>c3d4e5f6-a7b8-9012-cdef-012345678902</original_message_id>
    <status>confirmed</status>
    <ics_url>http://planning.integration.local/ical/user-uuid-123?token=abc...</ics_url>
  </body>
</message>
```

---

### 19.4 `session_create_request` (Frontend → Planning)

Wanneer een administrator in Drupal een nieuwe sessie aanmaakt.

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id" type="xs:string"/>
          <xs:element name="timestamp"  type="xs:dateTime"/>
          <xs:element name="source"     fixed="frontend" type="xs:string"/>
          <xs:element name="type"       fixed="session_create_request" type="xs:string"/>
          <xs:element name="version"    fixed="2.0" type="xs:string"/>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <xs:element name="session_id"     type="xs:string"/>
          <xs:element name="title"          type="xs:string"/>
          <xs:element name="start_datetime" type="xs:dateTime"/>
          <xs:element name="end_datetime"   type="xs:dateTime"/>
          <xs:element name="location"       type="xs:string" minOccurs="0"/>
          <xs:element name="session_type"   type="xs:string" minOccurs="0"/>
          <xs:element name="status"         type="xs:string" minOccurs="0"/>
          <xs:element name="max_attendees"  type="xs:integer" minOccurs="0"/>
        </xs:sequence></xs:complexType>
      </xs:element>
    </xs:sequence></xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML

```xml
<message>
  <header>
    <message_id>f6a7b8c9-d0e1-4567-abcd-ef1234567890</message_id>
    <timestamp>2026-05-15T14:00:00Z</timestamp>
    <source>frontend</source>
    <type>session_create_request</type>
    <version>2.0</version>
  </header>
  <body>
    <session_id>sess-uuid-001</session_id>
    <title>Keynote: AI 2026</title>
    <start_datetime>2026-05-15T14:00:00Z</start_datetime>
    <end_datetime>2026-05-15T15:00:00Z</end_datetime>
    <location>Zaal A</location>
    <max_attendees>150</max_attendees>
  </body>
</message>
```

---

### 19.5 `session_update_request` (Frontend → Planning)

Wanneer een administrator in Drupal een bestaande sessie wijzigt.

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id" type="xs:string"/>
          <xs:element name="timestamp"  type="xs:dateTime"/>
          <xs:element name="source"     fixed="frontend" type="xs:string"/>
          <xs:element name="type"       fixed="session_update_request" type="xs:string"/>
          <xs:element name="version"    fixed="2.0" type="xs:string"/>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <xs:element name="session_id"     type="xs:string"/>
          <xs:element name="title"          type="xs:string"/>
          <xs:element name="start_datetime" type="xs:dateTime"/>
          <xs:element name="end_datetime"   type="xs:dateTime"/>
          <xs:element name="location"           type="xs:string" minOccurs="0"/>
          <xs:element name="session_type"       type="xs:string" minOccurs="0"/>
          <xs:element name="status"             type="xs:string" minOccurs="0"/>
          <xs:element name="max_attendees"      type="xs:integer" minOccurs="0"/>
          <xs:element name="current_attendees"  type="xs:nonNegativeInteger" minOccurs="0"/>
          <!-- Price per session (optional; absent = free or unknown) -->
          <xs:element name="price" minOccurs="0">
            <xs:complexType>
              <xs:simpleContent>
                <xs:extension base="xs:decimal">
                  <xs:attribute name="currency" type="xs:string" fixed="eur" use="required"/>
                </xs:extension>
              </xs:simpleContent>
            </xs:complexType>
          </xs:element>
        </xs:sequence></xs:complexType>
      </xs:element>
    </xs:sequence></xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML

```xml
<message>
  <header>
    <message_id>f6a7b8c9-d0e1-4567-abcd-ef1234567890</message_id>
    <timestamp>2026-05-15T14:00:00Z</timestamp>
    <source>frontend</source>
    <type>session_update_request</type>
    <version>2.0</version>
  </header>
  <body>
    <session_id>sess-uuid-001</session_id>
    <title>Keynote: AI 2026</title>
    <start_datetime>2026-05-15T14:00:00Z</start_datetime>
    <end_datetime>2026-05-15T15:00:00Z</end_datetime>
    <location>Zaal A</location>
    <max_attendees>150</max_attendees>
    <current_attendees>42</current_attendees>
    <price currency="eur">25.00</price>
  </body>
</message>
```

---

### 19.6 `session_delete_request` (Frontend → Planning)

Wanneer een administrator in Drupal een sessie verwijdert.

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id" type="xs:string"/>
          <xs:element name="timestamp"  type="xs:dateTime"/>
          <xs:element name="source"     fixed="frontend" type="xs:string"/>
          <xs:element name="type"       fixed="session_delete_request" type="xs:string"/>
          <xs:element name="version"    fixed="2.0" type="xs:string"/>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <xs:element name="session_id" type="xs:string"/>
          <xs:element name="reason"     type="xs:string" minOccurs="0"/>
        </xs:sequence></xs:complexType>
      </xs:element>
    </xs:sequence></xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML

```xml
<message>
  <header>
    <message_id>a1b2c3d4-e5f6-7890-abcd-ef1234567890</message_id>
    <timestamp>2026-05-15T14:00:00Z</timestamp>
    <source>frontend</source>
    <type>session_delete_request</type>
    <version>2.0</version>
  </header>
  <body>
    <session_id>sess-uuid-001</session_id>
    <reason>cancelled</reason>
  </body>
</message>
```

---

### 19.7 `user_sessions_request` / `user_sessions_response` (RPC)

Kassa vraagt de sessielijst op van een bezoeker bij **Frontend** (voorheen Planning) op basis van zijn/haar `identity_uuid`. Dit wordt getriggerd wanneer een QR-code wordt gescand. Frontend antwoordt synchroon via het RPC-patroon op de `reply_to` queue.

> **⚠️ Breaking change v2.3:** Planning is verwijderd als RPC-target. Kassa stuurt nu via `kassa.exchange` naar Frontend. De response heeft `source="frontend"`.

- **Request exchange (Kassa):** `kassa.exchange`
- **Request routing key (Kassa):** `kassa.to.frontend.user_sessions_request`
- **Response routing key:** beantwoord op `reply_to` queue — `correlation_id` matcht de request

> **XSD-bestand (Kassa):** `Kassa/integratie/schemas/schema_user_sessions_request.xsd`  
> **XSD-bestand (response):** `Kassa/integratie/schemas/schema_user_sessions_response.xsd`

#### Globale regelcontrole

| Regel | Status | Opmerking |
|-------|--------|-----------|
| Regel 1 — geen `xmlns` op `<message>`, geen `<receiver>` | ✅ | Beide XSD's correct |
| Regel 2 — `<contact>` nesting voor namen | ✅ | Response: speaker heeft `<contact><first_name>/<last_name>` |
| Regel 3 — valuta op geldbedragen | ✅ | Response: `<price currency="eur">` per sessie (optioneel; afwezig = gratis of onbekend) |
| Regel 4 — `date_of_birth` i.p.v. `age` | ✅ | Geen leeftijdsveld |
| Regel 5 — Master UUID (`identity_uuid`) | ✅ | Gebruikt `UUIDType` patroon |
| Regel 6 — adres splitsing | ✅ | Geen adresvelden |

#### XSD — Request

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">

  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <!--
    user_sessions_request — Kassa / Frontend → Planning (RPC request)
    Sent by Kassa when a visitor's QR code is scanned, or by Frontend to fetch a user's sessions.
    Planning responds with user_sessions_response on the reply_to queue.
    Routing key (Kassa):    kassa.to.planning.user_sessions_request
    Routing key (Frontend): frontend.to.planning.user_sessions_request
  -->
  <xs:element name="message">
    <xs:complexType>
      <xs:sequence>

        <xs:element name="header">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="message_id"     type="UUIDType"/>
              <xs:element name="timestamp"      type="xs:dateTime"/>
              <xs:element name="source">
                <xs:simpleType>
                  <xs:restriction base="xs:string">
                    <xs:enumeration value="kassa"/>
                    <xs:enumeration value="frontend"/>
                  </xs:restriction>
                </xs:simpleType>
              </xs:element>
              <xs:element name="type">
                <xs:simpleType>
                  <xs:restriction base="xs:string">
                    <xs:enumeration value="user_sessions_request"/>
                  </xs:restriction>
                </xs:simpleType>
              </xs:element>
              <xs:element name="version">
                <xs:simpleType>
                  <xs:restriction base="xs:string">
                    <xs:enumeration value="2.0"/>
                  </xs:restriction>
                </xs:simpleType>
              </xs:element>
              <!-- correlation_id is required for RPC reply matching -->
              <xs:element name="correlation_id" type="UUIDType"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>

        <xs:element name="body">
          <xs:complexType>
            <xs:sequence>
              <!-- Master UUID of the visitor whose sessions are requested -->
              <xs:element name="identity_uuid" type="UUIDType"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>

      </xs:sequence>
    </xs:complexType>
  </xs:element>

</xs:schema>
```

#### XSD — Response

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">

  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <!--
    user_sessions_response — Planning → Kassa (RPC response)
    Published by Planning in reply to a user_sessions_request.
    The correlation_id matches the request's correlation_id.
    Routing key: planning.to.kassa.user_sessions_response
  -->
  <xs:element name="message">
    <xs:complexType>
      <xs:sequence>

        <xs:element name="header">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="message_id"     type="UUIDType"/>
              <xs:element name="timestamp"      type="xs:dateTime"/>
              <xs:element name="source">
                <xs:simpleType>
                  <xs:restriction base="xs:string">
                    <xs:enumeration value="planning"/>
                    <xs:enumeration value="frontend"/>
                  </xs:restriction>
                </xs:simpleType>
              </xs:element>
              <xs:element name="type">
                <xs:simpleType>
                  <xs:restriction base="xs:string">
                    <xs:enumeration value="user_sessions_response"/>
                  </xs:restriction>
                </xs:simpleType>
              </xs:element>
              <xs:element name="version">
                <xs:simpleType>
                  <xs:restriction base="xs:string">
                    <xs:enumeration value="2.0"/>
                  </xs:restriction>
                </xs:simpleType>
              </xs:element>
              <!-- Must match the correlation_id from the request -->
              <xs:element name="correlation_id" type="UUIDType"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>

        <xs:element name="body">
          <xs:complexType>
            <xs:sequence>
              <!-- Echoes back the identity_uuid from the request -->
              <xs:element name="identity_uuid" type="UUIDType"/>
              <!-- ok | not_found -->
              <xs:element name="status">
                <xs:simpleType>
                  <xs:restriction base="xs:string">
                    <xs:enumeration value="ok"/>
                    <xs:enumeration value="not_found"/>
                  </xs:restriction>
                </xs:simpleType>
              </xs:element>
              <xs:element name="session_count" type="xs:nonNegativeInteger"/>
              <xs:element name="sessions">
                <xs:complexType>
                  <xs:sequence>
                    <xs:element name="session" minOccurs="0" maxOccurs="unbounded">
                      <xs:complexType>
                        <xs:sequence>
                          <xs:element name="session_id"        type="xs:string"/>
                          <xs:element name="title"             type="xs:string"/>
                          <xs:element name="start_datetime"    type="xs:dateTime"/>
                          <xs:element name="end_datetime"      type="xs:dateTime"/>
                          <xs:element name="location"          type="xs:string"/>
                          <xs:element name="session_type">
                            <xs:simpleType>
                              <xs:restriction base="xs:string">
                                <xs:enumeration value="keynote"/>
                                <xs:enumeration value="workshop"/>
                                <xs:enumeration value="reception"/>
                                <xs:enumeration value="other"/>
                              </xs:restriction>
                            </xs:simpleType>
                          </xs:element>
                          <xs:element name="status">
                            <xs:simpleType>
                              <xs:restriction base="xs:string">
                                <xs:enumeration value="draft"/>
                                <xs:enumeration value="published"/>
                                <xs:enumeration value="cancelled"/>
                              </xs:restriction>
                            </xs:simpleType>
                          </xs:element>
                          <xs:element name="max_attendees"     type="xs:positiveInteger"/>
                          <xs:element name="current_attendees" type="xs:nonNegativeInteger"/>
                          <!-- Price the attendee owes for this session (optional; absent = free or unknown) -->
                          <xs:element name="price" minOccurs="0">
                            <xs:complexType>
                              <xs:simpleContent>
                                <xs:extension base="xs:decimal">
                                  <xs:attribute name="currency" type="xs:string" fixed="eur" use="required"/>
                                </xs:extension>
                              </xs:simpleContent>
                            </xs:complexType>
                          </xs:element>
                          <xs:element name="speaker" minOccurs="0">
                            <xs:complexType>
                              <xs:sequence>
                                <xs:element name="identity_uuid" type="UUIDType" minOccurs="0"/>
                                <xs:element name="contact">
                                  <xs:complexType>
                                    <xs:sequence>
                                      <xs:element name="first_name" type="xs:string"/>
                                      <xs:element name="last_name"  type="xs:string"/>
                                    </xs:sequence>
                                  </xs:complexType>
                                </xs:element>
                                <xs:element name="organisation" type="xs:string" minOccurs="0"/>
                                <xs:element name="email"        type="xs:string" minOccurs="0"/>
                              </xs:sequence>
                            </xs:complexType>
                          </xs:element>
                        </xs:sequence>
                      </xs:complexType>
                    </xs:element>
                  </xs:sequence>
                </xs:complexType>
              </xs:element>
            </xs:sequence>
          </xs:complexType>
        </xs:element>

      </xs:sequence>
    </xs:complexType>
  </xs:element>

</xs:schema>
```

#### Voorbeeld XML — Request (Kassa)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>a1b2c3d4-e5f6-7890-abcd-ef1234567890</message_id>
    <timestamp>2026-05-11T10:30:00Z</timestamp>
    <source>kassa</source>
    <type>user_sessions_request</type>
    <version>2.0</version>
    <correlation_id>c1d2e3f4-a5b6-7890-cdef-012345678901</correlation_id>
  </header>
  <body>
    <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
  </body>
</message>
```

#### Voorbeeld XML — Response (Planning)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>b2c3d4e5-f6a7-8901-bcde-f12345678901</message_id>
    <timestamp>2026-05-11T10:30:01Z</timestamp>
    <source>planning</source>
    <type>user_sessions_response</type>
    <version>2.0</version>
    <correlation_id>c1d2e3f4-a5b6-7890-cdef-012345678901</correlation_id>
  </header>
  <body>
    <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
    <status>ok</status>
    <session_count>2</session_count>
    <sessions>
      <session>
        <session_id>sess-keynote-001</session_id>
        <title>Keynote: AI in Healthcare</title>
        <start_datetime>2026-05-15T14:00:00Z</start_datetime>
        <end_datetime>2026-05-15T15:00:00Z</end_datetime>
        <location>Aula A - Campus Jette</location>
        <session_type>keynote</session_type>
        <status>published</status>
        <max_attendees>120</max_attendees>
        <current_attendees>45</current_attendees>
        <price currency="eur">0.00</price>
        <speaker>
          <identity_uuid>f9a38d2e-5c4b-6e7f-0a1b-234567890bcd</identity_uuid>
          <contact>
            <first_name>Sarah</first_name>
            <last_name>Leclercq</last_name>
          </contact>
          <organisation>UZ Brussel</organisation>
          <email>s.leclercq@uzbrussel.be</email>
        </speaker>
      </session>
      <session>
        <session_id>sess-workshop-042</session_id>
        <title>Workshop: Data Governance</title>
        <start_datetime>2026-05-15T16:00:00Z</start_datetime>
        <end_datetime>2026-05-15T17:30:00Z</end_datetime>
        <location>Lokaal B3 - Campus Jette</location>
        <session_type>workshop</session_type>
        <status>published</status>
        <max_attendees>30</max_attendees>
        <current_attendees>12</current_attendees>
        <price currency="eur">75.00</price>
      </session>
    </sessions>
  </body>
</message>
```

---

## 19.8 Frontend → Kassa: Sessiewijzigingen (Push)

Frontend pusht proactief sessiewijzigingen voor specifieke gebruikers naar Kassa via `kassa.exchange`. Kassa werkt `x_session_title` op de partner bij en notificeert de POS.

- **Exchange:** `kassa.exchange`
- **Queue (Kassa):** `kassa.incoming`

| Berichttype | Routing key |
|---|---|
| `session_created` | `frontend.to.kassa.session.created` |
| `session_updated` | `frontend.to.kassa.session.updated` |
| `session_deleted` | `frontend.to.kassa.session.deleted` |

> **Let op:** Dit zijn gebruikersregistratie-events (een specifieke gebruiker heeft zich in- of uitgeschreven voor een sessie), niet sessiecatalogus-updates. Voor cataloguswijzigingen zie sectie 7 (Planning → CRM).

### 19.8.1 `session_created` (Frontend → Kassa)

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>
  <xs:complexType name="CurrencyAmountType">
    <xs:simpleContent>
      <xs:extension base="xs:decimal">
        <xs:attribute name="currency" type="xs:string" fixed="eur" use="required"/>
      </xs:extension>
    </xs:simpleContent>
  </xs:complexType>
  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id"    type="UUIDType"/>
          <xs:element name="timestamp"     type="xs:dateTime"/>
          <xs:element name="source"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="frontend"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="session_created"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="version"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="2.0"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="correlation_id" type="UUIDType" minOccurs="0"/>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <!-- identity_uuid: voor welke gebruiker deze sessieregistratie geldt -->
          <xs:element name="identity_uuid" type="UUIDType"/>
          <xs:element name="session">
            <xs:complexType><xs:sequence>
              <xs:element name="session_id" type="xs:string"/>
              <xs:element name="title"      type="xs:string"/>
              <!-- price optioneel: afwezig = gratis -->
              <xs:element name="price"      type="CurrencyAmountType" minOccurs="0"/>
            </xs:sequence></xs:complexType>
          </xs:element>
        </xs:sequence></xs:complexType>
      </xs:element>
    </xs:sequence></xs:complexType>
  </xs:element>
</xs:schema>
```

### 19.8.2 `session_updated` (Frontend → Kassa)

Zelfde body als `session_created`. Kassa zoekt op `session_id` en update titel en prijs in-place (upsert als niet gevonden).

#### XSD

Identiek aan 19.8.1, met `<xs:enumeration value="session_updated"/>` als type.

### 19.8.3 `session_deleted` (Frontend → Kassa)

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>
  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id"    type="UUIDType"/>
          <xs:element name="timestamp"     type="xs:dateTime"/>
          <xs:element name="source"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="frontend"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="session_deleted"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="version"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="2.0"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="correlation_id" type="UUIDType" minOccurs="0"/>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <xs:element name="identity_uuid" type="UUIDType"/>
          <xs:element name="session_id"   type="xs:string"/>
          <xs:element name="reason"       type="xs:string" minOccurs="0"/>
        </xs:sequence></xs:complexType>
      </xs:element>
    </xs:sequence></xs:complexType>
  </xs:element>
</xs:schema>
```

---

## 20. CRM / Facturatie → Frontend: BTW Validatiefout

- **Queue:** `frontend.incoming`
- **Wanneer:** BTW-nummer is ongeldig bij registratie of factuuraanvraag

> ** Kritieke fix t.o.v. v1.0 codebase:**
> De originele developer had `<header minOccurs="0">` gemaakt als workaround.
> Dit is een **anti-pattern dat Regel 1 breekt**. De header is nu **verplicht**.
> CRM en Facturatie moeten de header altijd meesturen — ze kenden dit schema al.

### 20.1 `vat_validation_error`

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType>
      <xs:sequence>
        <!-- header VERPLICHT — geen minOccurs="0" zoals in v1.0 -->
        <xs:element name="header">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="message_id"     type="UUIDType"/>
              <xs:element name="timestamp"      type="xs:dateTime"/>
              <xs:element name="source">
                <xs:simpleType><xs:restriction base="xs:string">
                  <xs:enumeration value="crm"/>
                  <xs:enumeration value="facturatie"/>
                </xs:restriction></xs:simpleType>
              </xs:element>
              <xs:element name="type">
                <xs:simpleType><xs:restriction base="xs:string">
                  <xs:enumeration value="vat_validation_error"/>
                </xs:restriction></xs:simpleType>
              </xs:element>
              <xs:element name="version">
                <xs:simpleType><xs:restriction base="xs:string">
                  <xs:enumeration value="2.0"/>
                </xs:restriction></xs:simpleType>
              </xs:element>
              <xs:element name="correlation_id" type="UUIDType" minOccurs="0"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
        <xs:element name="body">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="identity_uuid" type="UUIDType" minOccurs="0"/>
              <xs:element name="vat_number" type="xs:string"/>
              <xs:element name="error_message" type="xs:string" minOccurs="0"/>
              <xs:element name="timestamp" type="xs:dateTime" minOccurs="0"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML

```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>e5f6a7b8-c9d0-1234-efab-234567890004</message_id>
    <timestamp>2026-04-24T09:20:00Z</timestamp>
    <source>crm</source>
    <type>vat_validation_error</type>
    <version>2.0</version>
  </header>
  <body>
    <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
    <vat_number>BE0000000000</vat_number>
    <error_message>BTW-nummer BE0000000000 bestaat niet in de VIES-databank</error_message>
  </body>
</message>
```

---

## 21. Sessie Bezetting Synchronisatie

Deze flow zorgt ervoor dat alle teams (Frontend, Kassa, CRM) real-time op de hoogte zijn van de bezettingsgraad van sessies om overboeking te voorkomen.

### 21.1 `session_registration_confirmed` (CRM → Planning)

CRM stuurt dit commando naar Planning zodra een inschrijving definitief is (na betaling of gratis registratie).

- **Queue:** `planning.registration`
- **Wanneer:** Inschrijving is 'paid' of bevestigd in CRM

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="header">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="message_id"     type="UUIDType"/>
              <xs:element name="timestamp"      type="xs:dateTime"/>
              <xs:element name="source"         type="xs:string" fixed="crm"/>
              <xs:element name="type"           type="xs:string" fixed="session_registration_confirmed"/>
              <xs:element name="version"        type="xs:string" fixed="2.0"/>
              <xs:element name="correlation_id" type="UUIDType" minOccurs="0"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
        <xs:element name="body">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="session_id"    type="xs:string"/>
              <xs:element name="identity_uuid" type="UUIDType"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML

```xml
<message>
  <header>
    <message_id>c23d4e5f-6a7b-8901-cdef-234567890999</message_id>
    <timestamp>2026-05-15T10:00:00Z</timestamp>
    <source>crm</source>
    <type>session_registration_confirmed</type>
    <version>2.0</version>
    <correlation_id>f47ac10b-58cc-4372-a567-0e02b2c3d479</correlation_id>
  </header>
  <body>
    <session_id>sess-keynote-001</session_id>
    <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
  </body>
</message>
```

---

### 21.2 `session_occupancy_update` (Planning → Alle teams)

Planning broadcast de nieuwe stand naar iedereen via de fanout/topic exchange.

- **Exchange:** `planning.exchange`
- **Routing Key:** `planning.session.occupancy`
- **Wie luistert:** Frontend, Kassa, CRM

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="message">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="header">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="message_id" type="xs:string"/>
              <xs:element name="timestamp"  type="xs:dateTime"/>
              <xs:element name="source"     type="xs:string" fixed="planning"/>
              <xs:element name="type"       type="xs:string" fixed="session_occupancy_update"/>
              <xs:element name="version"    type="xs:string" fixed="2.0"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
        <xs:element name="body">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="session_id"        type="xs:string"/>
              <xs:element name="current_attendees" type="xs:nonNegativeInteger"/>
              <xs:element name="max_attendees"     type="xs:positiveInteger"/>
              <xs:element name="status">
                <xs:simpleType>
                  <xs:restriction base="xs:string">
                    <xs:enumeration value="available"/>
                    <xs:enumeration value="full"/>
                  </xs:restriction>
                </xs:simpleType>
              </xs:element>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML

```xml
<message>
  <header>
    <message_id>d4e5f6a7-b8c9-0123-defa-123456789111</message_id>
    <timestamp>2026-05-15T10:00:02Z</timestamp>
    <source>planning</source>
    <type>session_occupancy_update</type>
    <version>2.0</version>
  </header>
  <body>
    <session_id>sess-keynote-001</session_id>
    <current_attendees>98</current_attendees>
    <max_attendees>100</max_attendees>
    <status>available</status>
  </body>
</message>
```

---

## 22. Migratie Roadmap

> Op basis van de v2.3 audit. Volg deze volgorde om DLQ-verkeer en breekkoppelingen tijdens de migratie te minimaliseren.

### Fase 1: Infrastructuur & Monitoring (laagrisico — 1-2 dagen)

1. **Heartbeat-service**: herwrite XML-builder naar `<message>` envelop (sectie 3)
2. **Monitoring**: vervang `alert.xsd` door `system_alert` in `<message>` envelop (sectie 4) + Logstash parser bijwerken
3. Test: Alle teams kunnen heartbeats sturen, Monitoring leest ze correct

### Fase 2: Planning XSD's (DONE )

4. **Planning**: alle 7 XSD's in `/xsd/` folder gecorrigeerd (April 2026)
5. Test: `producer.py` valideert correct, CRM ontvangt sessions zonder DLQ-fouten

### Fase 3: Facturatie XSD's (1-2 dagen)

6. **Facturatie**: vervang `invoice_request.xsd`, `new_registration.xsd`, fix `invoice_created_notification`, `payment_registered.xsd` (sectie 11.1, 5.1, 13)
7. **Facturatie**: outbound type `send_invoice` → `invoice_status` (sectie 8.1)
8. **Facturatie**: queue listener `crm.to.facturatie` → `facturatie.incoming`
9. Test: CRM kan `invoice_request` sturen, Facturatie verwerkt correct

### Fase 4: CRM aanpassingen (1-2 dagen)

10. **CRM** `receiver.js`: `session_update` → `session_updated`
11. **CRM** `sender.js`: `<age>` → `<date_of_birth>`, `invoice_request` body herwerken, queue naar `facturatie.incoming`, `mailing_status` → `send_mailing`
12. **CRM**: implementeer passthrough voor `consumption_order` naar `facturatie.incoming` (geen `payment_registered` meer — betaalstatus zit in `invoice_request`)
13. Test: Kassa → CRM → Facturatie flow werkt end-to-end

### Fase 5: Frontend volledige migratie (2-3 dagen — grootste werk)

14. **Frontend**: ALLE PHP senders migreren naar v2.0 header (xmlns weg, receiver weg, version=2.0, master_uuid weg)
15. **Frontend**: Type-naam migraties (user.X → user_X, calendar.invite → calendar_invite)
16. **Frontend**: `CalendarInviteSender.php` voeg `<version>` en `<attendee_email>` toe
17. **Frontend**: Identity RPC implementeren vóór CRM-call bij registratie
18. Test: Volledige registratie- en check-in-flow werkt

### Fase 6: Cleanup & validatie

19. Alle teams: bind queues aan `user.events` fanout exchange
20. Alle teams: monitor `dead-letter` queues — zou nu leeg moeten blijven
21. Update CI tests in alle repo's met nieuwe XSD's

### Communicatie

> Voor elke fase: stuur een Slack-bericht naar het hele projectteam **vóór** de wijziging live gaat. Coördineer met PM zodat geen team verrast wordt door brekende contracten.

---

## 23. Validatie Checklist (per bericht)

Gebruik deze checklist bij het bouwen of reviewen van elke nieuwe sender of XSD:

- [ ] Standaard `<message>` envelop met `<header>` en `<body>` (geen platte root elementen zoals `<heartbeat>` of `<alert>`)
- [ ] Header bevat: `version=2.0`, `type` (snake_case), `source`, `message_id` (UUID), `timestamp` (xs:dateTime)
- [ ] Header bevat GEEN `<receiver>`, GEEN `<master_uuid>`, GEEN custom velden
- [ ] `<message>` element heeft GEEN `xmlns` attribuut
- [ ] XSD heeft GEEN `targetNamespace` en GEEN default `xmlns` namespace
- [ ] XSD validatie geslaagd voor het bericht
- [ ] Type in snake_case (geen punten, geen camelCase)
- [ ] `correlation_id` correct gebruikt waar verplicht (zie sectie 4 + tabel sectie 16)
- [ ] Geldbedragen hebben `currency="eur"` attribuut
- [ ] Namen zijn genest in `<contact>` wrapper (uitzondering: `<invoice_data>` body, sectie 11.1)
- [ ] `<date_of_birth>` gebruikt (nooit `<age>`)
- [ ] Datums in `xs:dateTime` formaat (niet `xs:string`)
- [ ] **Session Master UUID:** Alle RabbitMQ berichten gerelateerd aan één sessie (create, update, delete) gebruiken de **Master UUID** in het `correlation_id` veld.
- [ ] Bij errors: `system_error` bericht naar de juiste queue (kassa.errors, crm.dead-letter, etc.)

---

## 24. Cross-Team Interface Analyse — Welke XML moet gesynchroniseerd worden?

> Dit is de visuele samenvatting van de audit. Het laat zien welke teams op dezelfde interface-punten samen iets fout doen vs. wie individueel afwijkt.

### Legende

| Kleur | Betekenis | Actie |
|-------|-----------|-------|
|  Rood | Één team wijkt af, de andere is correct — **breekt nu al** | Fix enkel het afwijkende team |
| � Oranje | **Beide** teams wijken af maar matchen toevallig — werkt nu, breekt bij eerste fix | Synchroon migreren (tegelijk beide aanpassen) |
|  Groen | Berichten correct, maar intern schema fout (eigen validatie) | Team past intern XSD aan, geen impact op andere teams |

---

### Interface 1 — CRM → Kassa: `new_registration` 

```
         
  CRM stuurt (sender.js)               Kassa verwacht (XSD)          
                                                                              
  <identity_uuid>                              <identity_uuid>                      
  <age>30</age>                  MISMATCH   <date_of_birth> verplicht       
  <contact> wrapper                          <contact> wrapper verplicht    
  <date_of_birth> ontbreekt                 <age> niet in schema            
          
```

**Gevolg:** XSD-validatie FAALT bij Kassa → bericht naar DLQ → Kassa weet niet dat klant bestaat.  
**Fix:** Enkel CRM `sender.js` aanpassen (`<age>` weg, `<date_of_birth>` toevoegen). Kassa hoeft niets te doen.

---

### Interface 2 — CRM → Facturatie: `invoice_request`

```
         
  CRM stuurt (sender.js)             Facturatie verwacht (XSD)     
                                                                              
  <master_uuid> in header         matcht    <master_uuid> in header       
  <items> in body                 ←maar→    <items> in body               
  <customer> wrapper              beiden    <customer> wrapper            
  <correlation_id> mist           fout      <correlation_id> mist         
  queue: crm.to.facturatie                  luistert op: crm.to.facturatie 
          
```

**Gevolg:** Werkt toevallig nu (beiden fout én matchen). Zodra één team fixes, breekt alles.  
**Correcte structuur per contract sectie 11.1:**
```xml
<!-- Body moet worden (v2.3): -->
<body>
  <identity_uuid>{uuid}</identity_uuid>
  <invoice_data>
    <contact>
      <first_name>...</first_name>
      <last_name>...</last_name>
    </contact>
    <email>...</email>
    <address>...</address>
    <vat_number>...</vat_number>  <!-- optioneel -->
  </invoice_data>
  <!-- GEEN <items> — Facturatie matcht zelf via correlation_id + consumption_order -->
</body>
```
**Fix:** CRM `sender.js` EN Facturatie `invoice_request.xsd` **tegelijk** aanpassen + queue `crm.to.facturatie` → `facturatie.incoming`.

---

### Interface 3 — Frontend → CRM: event types 

```
         
  Frontend stuurt (PHP senders)        CRM verwacht (receiver.js)    
                                                                              
  xmlns="urn:...:v1" op                       geen xmlns op <message>         
  <message>                      MISMATCH                                   
  <receiver> in header                      geen <receiver> in header       
  <version>1.0</version>                    <version>2.0</version>          
  type="user.unregistered"                  type="user_deleted" verwacht    
          
```

**Gevolg:** CRM parseert het bericht wel, maar type-routing mislukt (`user.unregistered` onbekend) → bericht naar dead-letter.  
**Fix:** Enkel Frontend senders aanpassen. CRM hoeft niets te doen.

---

### Interface 4 — Planning → CRM: `session_created`/`session_updated` 

```
         
  Planning stuurt (producer.py)      CRM verwacht (receiver.js)      
                                                                              
  type="session_created"             OK      case "session_updated" ← fix    
  xs:dateTime in XML                xs:dateTime veld               
  geen namespace in bericht                  geen namespace vereist         
                                                                              
    
                                                                              
  INTERN: XSD's in /xsd/                    INTERN: case "session_update"   
  targetNamespace aanwezig                  → "session_updated" fix       
  xs:string i.p.v. dateTime                                                 
          
```

**Gevolg:** Berichten worden correct verstuurd en ontvangen. Interne XSD-fouten bij Planning breken enkel Planning's eigen pre-publish validatie (niet de communicatie). CRM `receiver.js` heeft één case-fix nodig (`session_update` → `session_updated`).  
**Fix:** Planning past intern `/xsd/` aan. CRM past één case in `receiver.js` aan. Onafhankelijk van elkaar.

---

### Samenvatting: welke interfaces moeten synchroon gemigreerd worden?

| Interface | Type | Wie past aan | Timing |
|-----------|------|-------------|--------|
| CRM → Kassa (`new_registration`) |  Eén team fout | Alleen CRM | Onafhankelijk |
| CRM → Facturatie (`invoice_request`) | � Beiden fout | CRM + Facturatie | **Tegelijk** |
| Frontend → CRM (alle event types) |  Één team fout | Alleen Frontend | Onafhankelijk |
| Planning → CRM (`session_updated`) |  Intern issue | Planning (XSD) + CRM (1 case) | Onafhankelijk |
| Heartbeat → Monitoring (`heartbeat`) |  Één team fout | Alleen Heartbeat service | Onafhankelijk |
| Facturatie (`invoice_created_notification`) |  Intern issue | Alleen Facturatie | Onafhankelijk |

>  **De enige synchrone migratie is CRM + Facturatie voor `invoice_request`.** Alle andere fixes kunnen teams onafhankelijk uitvoeren zonder de communicatie te breken.

---

## 25. Centralisatie — Hoe dit document te gebruiken

### Wat dit document IS

Dit document bevat in **sectie 3 t/m 19** de **volledige canonieke XSD's en XML-voorbeelden** zoals elk bericht er *correct* uit moet zien. Dit zijn niet alleen de verschillen — dit zijn de complete schemas.

### Wat elk team moet doen

Elk team vervangt hun eigen lokale XSD-bestanden met de schemas uit dit document:

| Team | Lokale XSD-bestanden vervangen | Bron in dit contract |
|------|-------------------------------|----------------------|
| Frontend | Geen eigen XSD's — PHP senders bouwen XML inline | Sectie 5 (Frontend → CRM) + Sectie 17 (Frontend ↔ Planning) |
| CRM | `src/sender.js` XML builders | Sectie 10 (CRM → Kassa), 11 (CRM → Facturatie), 12 (CRM → Mailing) |
| Facturatie | `invoice_request.xsd`, `new_registration.xsd`, etc. | Sectie 11 (inkomend), Sectie 8 (uitgaand) |
| Planning | `/xsd/*.xsd` (alle 7 bestanden) | Sectie 7 (Planning → CRM), Sectie 17 (Planning ↔ Frontend) |
| Kassa | `integratie/schemas/*.xsd`  al conform | — |
| Heartbeat | XML builder | Sectie 3 (Heartbeat format) |
| Monitoring | `alert.xsd` | Sectie 4 (Monitoring → Mailing) |

### Optionele volgende stap: gedeelde XSD-repository

Als teams hun XSD's willen delen zodat ze niet meer kunnen uitlopen:

```
IntegrationProject-Groep1/
 shared-contracts/          ← nieuwe repo
     xsd/
        heartbeat.xsd
        system_error.xsd
        new_registration_frontend_crm.xsd
        new_registration_crm_kassa.xsd
        invoice_request_crm_facturatie.xsd
        session_created.xsd
        ... (één bestand per berichttype)
     XML_XSD_Contract_v2.3_Centralized 1.md   ← dit document
```

Elk team voegt dan dit als git-submodule toe en valideert inkomende berichten tegen de shared XSD. Zo is het contract machine-leesbaar én mensleesbaar.

---

## 26. Authority Lease Model (Badge Saldo)

Dit model regelt het eigenaarschap over het badge-saldo tussen CRM (Online Authority) en Kassa (On-Site Authority).

### 26.1 `wallet_lease_request` (Kassa → CRM)

Kassa vraagt de macht over het saldo zodra een bezoeker het terrein betreedt.

- **Exchange:** `kassa.exchange`
- **Routing Key:** `kassa.to.crm.wallet_lease_request`
- **Wanneer:** Eerste badge-scan of QR-scan bij inkom of kassa.

> **`badge_id`:** optioneel — afwezig bij QR-scan (identity_uuid volstaat). Aanwezig bij badge-scan.

#### XSD
```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id" type="UUIDType"/>
          <xs:element name="timestamp"  type="xs:dateTime"/>
          <xs:element name="source"     type="xs:string" fixed="kassa"/>
          <xs:element name="type"       type="xs:string" fixed="wallet_lease_request"/>
          <xs:element name="version"    type="xs:string" fixed="2.0"/>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <xs:element name="identity_uuid" type="UUIDType"/>
          <xs:element name="badge_id"      type="xs:string" minOccurs="0"/>
        </xs:sequence></xs:complexType>
      </xs:element>
    </xs:sequence></xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML — via badge
```xml
<message>
  <header>
    <message_id>a1b2c3d4-e5f6-7890-abcd-ef1234567890</message_id>
    <timestamp>2026-05-15T09:00:00Z</timestamp>
    <source>kassa</source>
    <type>wallet_lease_request</type>
    <version>2.0</version>
  </header>
  <body>
    <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
    <badge_id>BADGE-0042</badge_id>
  </body>
</message>
```

#### Voorbeeld XML — via QR-scan
```xml
<message>
  <header>
    <message_id>b2c3d4e5-f6a7-8901-bcde-f01234567891</message_id>
    <timestamp>2026-05-15T09:00:05Z</timestamp>
    <source>kassa</source>
    <type>wallet_lease_request</type>
    <version>2.0</version>
  </header>
  <body>
    <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
  </body>
</message>
```

---

### 26.2 `wallet_lease_grant` (CRM → Kassa)

CRM bevriest de online portemonnee en geeft het saldo door aan de Kassa.

- **Exchange:** `crm.exchange`
- **Routing Key:** `crm.to.kassa.wallet_lease_grant`
- **Wanneer:** Na validatie van lease_request.

#### XSD
```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id"     type="UUIDType"/>
          <xs:element name="timestamp"      type="xs:dateTime"/>
          <xs:element name="source"         type="xs:string" fixed="crm"/>
          <xs:element name="type"           type="xs:string" fixed="wallet_lease_grant"/>
          <xs:element name="version"        type="xs:string" fixed="2.0"/>
          <xs:element name="correlation_id" type="UUIDType"/>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <xs:element name="identity_uuid" type="UUIDType"/>
          <xs:element name="current_balance">
            <xs:complexType><xs:simpleContent><xs:extension base="xs:decimal">
              <xs:attribute name="currency" type="xs:string" fixed="eur" use="required"/>
            </xs:extension></xs:simpleContent></xs:complexType>
          </xs:element>
          <xs:element name="lease_id" type="xs:string"/>
          <!-- payment_due: total registration fees still owed by this visitor (optional) -->
          <xs:element name="payment_due" minOccurs="0">
            <xs:complexType><xs:sequence>
              <xs:element name="amount">
                <xs:complexType><xs:simpleContent><xs:extension base="xs:decimal">
                  <xs:attribute name="currency" type="xs:string" fixed="eur" use="required"/>
                </xs:extension></xs:simpleContent></xs:complexType>
              </xs:element>
              <xs:element name="status" minOccurs="0">
                <xs:simpleType><xs:restriction base="xs:string">
                  <xs:enumeration value="unpaid"/>
                  <xs:enumeration value="paid"/>
                </xs:restriction></xs:simpleType>
              </xs:element>
            </xs:sequence></xs:complexType>
          </xs:element>
        </xs:sequence></xs:complexType>
      </xs:element>
    </xs:sequence></xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML
```xml
<message>
  <header>
    <message_id>b2c3d4e5-f6a7-8901-bcde-f12345678901</message_id>
    <timestamp>2026-05-15T09:00:05Z</timestamp>
    <source>crm</source>
    <type>wallet_lease_grant</type>
    <version>2.0</version>
    <correlation_id>a1b2c3d4-e5f6-7890-abcd-ef1234567890</correlation_id>
  </header>
  <body>
    <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
    <current_balance currency="eur">50.00</current_balance>
    <lease_id>LEASE-2026-XYZ</lease_id>
    <!-- payment_due is optional — omit if no outstanding fees -->
    <payment_due>
      <amount currency="eur">25.00</amount>
      <status>unpaid</status>
    </payment_due>
  </body>
</message>
```

---

### 26.3 `wallet_lease_return` (Kassa → CRM)

Kassa geeft de macht terug aan het CRM (einde dag of bij vertrek).

- **Exchange:** `kassa.exchange`
- **Routing Key:** `kassa.to.crm.wallet_lease_return`

#### XSD
```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id" type="UUIDType"/>
          <xs:element name="timestamp"  type="xs:dateTime"/>
          <xs:element name="source"     type="xs:string" fixed="kassa"/>
          <xs:element name="type"       type="xs:string" fixed="wallet_lease_return"/>
          <xs:element name="version"    type="xs:string" fixed="2.0"/>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <xs:element name="identity_uuid" type="UUIDType"/>
          <xs:element name="final_balance">
            <xs:complexType><xs:simpleContent><xs:extension base="xs:decimal">
              <xs:attribute name="currency" type="xs:string" fixed="eur" use="required"/>
            </xs:extension></xs:simpleContent></xs:complexType>
          </xs:element>
          <xs:element name="lease_id" type="xs:string"/>
          <xs:element name="transaction_count" type="xs:nonNegativeInteger"/>
        </xs:sequence></xs:complexType>
      </xs:element>
    </xs:sequence></xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML
```xml
<message>
  <header>
    <message_id>c3d4e5f6-a7b8-9012-cdef-012345678902</message_id>
    <timestamp>2026-05-15T23:59:00Z</timestamp>
    <source>kassa</source>
    <type>wallet_lease_return</type>
    <version>2.0</version>
  </header>
  <body>
    <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
    <final_balance currency="eur">12.50</final_balance>
    <lease_id>LEASE-2026-XYZ</lease_id>
    <transaction_count>5</transaction_count>
  </body>
</message>
```

---

### 26.4 `wallet_balance_update` (Broadcast)

Dit bericht wordt verzonden door de partij die **op dat moment de autoriteit heeft**. In het lease-model zijn de velden `authority` en `status` verplicht om de synchronisatie tussen CRM en Kassa te waarborgen.

- **Exchange:** `wallet.updates` (**fanout**)
- **Routing Key:** n.v.t. (gebruik fanout exchange binding)
- **Wie luistert:** Frontend, Monitoring, CRM (indien Kassa de baas is), Kassa (indien CRM de baas is)

#### XSD & Schema
Zie **[Sectie 6.8: `wallet_balance_update` (Canonical Definition)](#68-wallet_balance_update-canonical-broadcast)** voor het volledige XSD-schema en de berichtstructuur.

---

### 26.5 `wallet_topup_request` (Frontend → CRM)

Gebruiker herlaadt zijn badge online via de website of app.

- **Exchange:** `frontend.exchange`
- **Routing Key:** `frontend.to.crm.wallet_topup_request`
- **Wanneer:** Na succesvolle online betaling (Bancontact/Creditcard).

#### XSD
```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id" type="UUIDType"/>
          <xs:element name="timestamp"  type="xs:dateTime"/>
          <xs:element name="source"     type="xs:string" fixed="frontend"/>
          <xs:element name="type"       type="xs:string" fixed="wallet_topup_request"/>
          <xs:element name="version"    type="xs:string" fixed="2.0"/>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <xs:element name="identity_uuid" type="UUIDType"/>
          <xs:element name="topup_amount">
            <xs:complexType><xs:simpleContent><xs:extension base="xs:decimal">
              <xs:attribute name="currency" type="xs:string" fixed="eur" use="required"/>
            </xs:extension></xs:simpleContent></xs:complexType>
          </xs:element>
          <xs:element name="transaction_id" type="xs:string"/>
        </xs:sequence></xs:complexType>
      </xs:element>
    </xs:sequence></xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML
```xml
<message>
  <header>
    <message_id>d1e2f3a4-b5c6-7890-abcd-ef1234567010</message_id>
    <timestamp>2026-05-15T14:00:00Z</timestamp>
    <source>frontend</source>
    <type>wallet_topup_request</type>
    <version>2.0</version>
  </header>
  <body>
    <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
    <topup_amount currency="eur">20.00</topup_amount>
    <transaction_id>PAY-WEB-445566</transaction_id>
  </body>
</message>
```

---

### 26.6 `wallet_remote_topup` (CRM → Kassa)

CRM stuurt dit bericht enkel als de autoriteit momenteel bij de Kassa ligt.

- **Exchange:** `crm.exchange`
- **Routing Key:** `crm.to.kassa.wallet_remote_topup`
- **Wanneer:** CRM ontvangt een `wallet_topup_request` maar `authority` is momenteel `kassa`.

#### XSD
```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:simpleType name="UUIDType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id"     type="UUIDType"/>
          <xs:element name="timestamp"      type="xs:dateTime"/>
          <xs:element name="source"         type="xs:string" fixed="crm"/>
          <xs:element name="type"           type="xs:string" fixed="wallet_remote_topup"/>
          <xs:element name="version"        type="xs:string" fixed="2.0"/>
          <xs:element name="correlation_id" type="UUIDType"/>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <xs:element name="identity_uuid" type="UUIDType"/>
          <xs:element name="add_amount">
            <xs:complexType><xs:simpleContent><xs:extension base="xs:decimal">
              <xs:attribute name="currency" type="xs:string" fixed="eur" use="required"/>
            </xs:extension></xs:simpleContent></xs:complexType>
          </xs:element>
          <xs:element name="reason" type="xs:string"/>
        </xs:sequence></xs:complexType>
      </xs:element>
    </xs:sequence></xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML
```xml
<message>
  <header>
    <message_id>e2f3a4b5-c6d7-8901-bcde-f12345678020</message_id>
    <timestamp>2026-05-15T14:00:02Z</timestamp>
    <source>crm</source>
    <type>wallet_remote_topup</type>
    <version>2.0</version>
    <correlation_id>d1e2f3a4-b5c6-7890-abcd-ef1234567010</correlation_id>
  </header>
  <body>
    <identity_uuid>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</identity_uuid>
    <add_amount currency="eur">20.00</add_amount>
    <reason>online_topup</reason>
  </body>
</message>
```

---

## 27. Legacy / Deprecated Schemas — Gevonden in Repos

> **Gap Resolution (Mei 2026):** Onderstaande XSD-bestanden zijn aangetroffen in de Facturatie-repo maar stonden nog niet in het contract. Ze worden hier gedocumenteerd als **deprecated** — ze mogen niet meer voor nieuwe berichten gebruikt worden. Teams die ze nog consumeren moeten migreren naar de v2.0 varianten.

---

### 27.1 `payment_registered_outgoing` (Facturatie — DEPRECATED)

> **Status: DEPRECATED** — vervangen door de standaard `payment_registered` (§8.2). Gebruikt `customer_id` i.p.v. `identity_uuid` en heeft geen standaard v2.0 header-velden. Niet gebruiken voor nieuwe integraties.

- **Bestandslocatie:** `Facturatie/src/services/xsd/payment_registered_outgoing.xsd`
- **Vervanger:** §8.2 `payment_registered` (Facturatie → CRM)

#### XSD (archief — niet gebruiken)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id" type="xs:string"/>
          <xs:element name="timestamp"  type="xs:dateTime"/>
          <xs:element name="source"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="facturatie"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="payment_registered"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="version"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="2.0"/></xs:restriction></xs:simpleType></xs:element>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <xs:element name="invoice_id"  type="xs:string"/>
          <xs:element name="customer_id" type="xs:string"/>
          <xs:element name="amount_paid">
            <xs:complexType><xs:simpleContent><xs:extension base="xs:decimal">
              <xs:attribute name="currency" use="required">
                <xs:simpleType><xs:restriction base="xs:string">
                  <xs:enumeration value="eur"/></xs:restriction></xs:simpleType>
              </xs:attribute>
            </xs:extension></xs:simpleContent></xs:complexType>
          </xs:element>
          <xs:element name="payment_method">
            <xs:simpleType><xs:restriction base="xs:string">
              <xs:enumeration value="cash"/>
              <xs:enumeration value="card"/>
              <xs:enumeration value="bank_transfer"/>
            </xs:restriction></xs:simpleType>
          </xs:element>
          <xs:element name="paid_at" type="xs:dateTime"/>
        </xs:sequence></xs:complexType>
      </xs:element>
    </xs:sequence></xs:complexType>
  </xs:element>
</xs:schema>
```

**Migratie-instructie:** Vervang `customer_id` door `identity_uuid` (UUID-formaat) en gebruik de v2.0 `payment_registered` XSD uit §8.2.

---

### 27.2 `invoice_link` (Facturatie — DEPRECATED)

> **Status: DEPRECATED** — vervangen door `invoice_available` (§13.5.1). Bevat een verboden `<master_uuid>` in de header en gebruikt een `xs:integer` voor `invoice_id` wat niet compatibel is met de v2.0 standaard. Niet gebruiken voor nieuwe integraties.

- **Bestandslocatie:** `Facturatie/src/services/xsd/invoice_link.xsd`
- **Vervanger:** §13.5.1 `invoice_available` (Facturatie → Frontend)

#### XSD (archief — niet gebruiken)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="message">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="header">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="message_id" type="xs:string"/>
              <xs:element name="version" type="xs:decimal" fixed="2.0"/>
              <xs:element name="type" type="xs:string"/>
              <xs:element name="timestamp" type="xs:dateTime"/>
              <xs:element name="source" type="xs:string"/>
              <xs:element name="master_uuid">
                <xs:simpleType>
                  <xs:restriction base="xs:string">
                    <xs:pattern value="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"/>
                  </xs:restriction>
                </xs:simpleType>
              </xs:element>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
        <xs:element name="body">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="invoice_id" type="xs:integer"/>
              <xs:element name="pdf_url" type="xs:anyURI"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
```

**Migratie-instructie:** Gebruik `invoice_available` (§13.5.1) met `identity_uuid` in body, `invoice_id` als `xs:string`, en standaard v2.0 header zonder `<master_uuid>`.

---

## 28. Final Rule

> **Als twee teams hetzelfde bericht anders interpreteren, is het contract fout.**

Niet het team.
Maak een issue aan op GitHub en update dit document.

Maar: dit document IS nu de canonieke bron. Zolang er geen issue + update geweest is, geldt deze versie.

---

*Document v2.3 — Gegenereerd op basis van volledige repo-audit + bestaande v2.0 contract — April 2026*
*Sectie 10.4, 27 en 28 toegevoegd Mei 2026 — gap resolution na repo-scan*
*Volgende geplande revisie: na demo 3 — toevoegen of aanpassen via Pull Request*
