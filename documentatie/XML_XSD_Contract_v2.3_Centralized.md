# XML / XSD Contract v2.3 — Integration Project Groep 1

> **Dit document is het officiële en GECENTRALISEERDE berichtencontract voor alle teams.**  
> Elk bericht dat over RabbitMQ gaat, moet voldoen aan de structuur en XSD's in dit document. Dit is de enige 'Source of Truth' voor alle XML en XSD schema's in het project.
> Versie: **2.3** — Gecentraliseerd na volledige repo-audit (April 2026).
>
>  **Dit is het ENIGE geldige contract.** Alle teams moeten hun code hieraan aanpassen — afwijkingen die nog in code zitten zijn een **contractbreuk** en moeten dringend worden weggewerkt. Zie sectie 0.5 voor de exacte audit-bevindingen per team.

---

> **Gebruik voor distributie:** `XML_XSD_Contract_Distribution_CLEAN.md` — schoon bestand met alleen audit, XSD's en voorbeelden per team. Geen changelog, geen onnodige tekst.

---

##  QUICK REFERENCE — Per Team: Wat ontvang jij? Wat verstuur je?

Klik op jouw team om direct naar de gedetailleerde specificaties te gaan. **Groen ()** = conform, geen actie. **Rood ()** = kritieke wijzigingen nodig.

###  **Team Kassa** — Betalingen & Kassamachine (CONFORM )
**Audit Status:** Volledig conform — geen wijzigingen nodig

| Richting | Berichttype | Van/Naar | Sectie |
|----------|---|---|---|
|  **ONTVANGT** | `new_registration`, `profile_update`, `cancel_registration` | ← CRM | [10. CRM → Kassa](#10-crm--kassa) |
|  **VERZENDT** | `payment_registered` | → CRM | [6.6 Kassa → CRM](#66-payment_registered-kassa--rabbitmq) |
|  **VERZENDT** | `payment_status`, `wallet_balance_update` | → Frontend | [16](#16-rabbitmq-queue--exchange-overzicht) |
|  **BROADCAST** | `heartbeat` | → Monitoring | [3. Heartbeat](#3-heartbeat--alle-teams--monitoring) |

**XSD's referentie:**
- `Kassa/integratie/schemas/` ( compleet — wordt als voorbeeld gebruikt)

**Opmerking:** Kassa bevat de best-practice implementatie. Andere teams gebruiken dit als template.

---

###  **Team CRM** — Centraal routering & data-sync (KRITIEK - 6 fixes)
**Audit Status:** Meerdere kritieke afwijkingen in sender.js en receiver.js

| Richting | Berichttype | Van/Naar | Huidi-Status | Sectie |
|----------|---|---|---|---|
|  **ONTVANGT** | `new_registration` | ← Frontend | v2.0  | [5.1](#51-new_registration-frontend--crm) |
|  **ONTVANGT** | `user_created`, `user_updated`, `user_deleted` | ← Frontend |  dotted type | [5.2-5.4](#52-user_created-frontend--crm) |
|  **ONTVANGT** | `session_created`, `session_updated` | ← Planning |  `session_update` (fout) | [7.1-7.2](#71-session_created-planning--crm) |
|  **ONTVANGT** | `payment_registered` | ← Kassa |  | [6.1](#61-payment_registered-kassa--crm) |
|  **ONTVANGT** | `invoice_created_notification` | ← Facturatie |  | [8.1](#81-invoice_created_notification-facturatie--crm) |
|  **ONTVANGT** | `mailing_status` | ← Mailing |  (moet `send_mailing` zijn) | [9.1](#91-mailing_status-mailing--crm) |
|  **VERZENDT** | `new_registration` | → Kassa |  bevat `<age>` | [10.1](#101-new_registration-crm--kassa) |
|  **VERZENDT** | `profile_update` | → Kassa |  bevat `<age>` | [10.2](#102-profile_update-crm--kassa) |
|  **VERZENDT** | `cancel_registration` | → Planning |  (NIEUW - Option A) | [10.3](#103-cancel_registration-crm--kassa--planning) |
|  **VERZENDT** | `invoice_request` | → Facturatie |  bevat `<items>`, queue fout | [11.1](#111-invoice_request-crm--facturatie) |
|  **VERZENDT** | `send_mailing` | → Mailing |  type is `mailing_status` | [12.1](#121-send_mailing-crm--mailing) |
|  **VERZENDT** | `payment_registered` | → Frontend |  | [13.1](#131-payment_registered-crm--frontend) |
|  **BROADCAST** | `heartbeat` | → Monitoring |  | [3](#3-heartbeat--alle-teams--monitoring) |

**Kritieke fixes (src/sender.js + src/receiver.js):**
1.  Regel line 20: `session_update` → `session_updated`
2.  Regel line 191, 245: `<age>` → `<date_of_birth>`
3.  Regel line 45-63: `invoice_request` body → `<invoice_data>` i.p.v. `<items>`
4.  Regel line 85: type `mailing_status` → `send_mailing`
5.  Regel line 124: queue `crm.to.facturatie` → `facturatie.incoming`
6.  NIEUW: Forward `cancel_registration` naar Planning (Option A)

---

###  **Team Frontend** — Gebruiker registratie & events (KRITIEK - volledige header-migratie)
**Audit Status:** Alle senders gemengd v1.0/v2.0 — moet naar v2.0

| Richting | Berichttype | Van/Naar | Huidi-Status | Sectie |
|----------|---|---|---|---|
|  **VERZENDT** | `new_registration` | → CRM |  bevat `<master_uuid>`, `<age>` | [5.1](#51-new_registration-frontend--crm) |
|  **VERZENDT** | `user_created` | → CRM |  v1.0 header + dotted type | _(XSD nog te documenteren — zie audit 0.6)_ |
|  **VERZENDT** | `user_updated` | → CRM |  v1.0 header | [5.2](#52-user_updated) |
|  **VERZENDT** | `user_deleted` | → CRM |  v1.0 header + `user.unregistered` | [5.3](#53-user_deleted-frontend--crm) |
|  **VERZENDT** | `user_checkin` | → CRM |  v1.0 header + `user.checkin` | [21.1](#211-user_checkin-frontend--crm) |
|  **VERZENDT** | `calendar_invite` | → Planning |  dotted type + mist `version` | [17.2](#172-calendar_invite-frontend--planning) |
|  **ONTVANGT** | `payment_registered` | ← CRM |  | [13.1](#131-payment_registered-crm--frontend) |
|  **ONTVANGT** | `payment_status` | ← Kassa |  | [16](#16-rabbitmq-queue--exchange-overzicht) |
|  **ONTVANGT** | `session_created`, `session_updated` | ← Planning |  | [7](#7-planning--crm) |
|  **BROADCAST** | `heartbeat` | → Monitoring |  | [3](#3-heartbeat--alle-teams--monitoring) |

**Kritieke fixes (web/modules/custom/rabbitmq_sender/src/):**
-  NewRegistrationSender.php: `<master_uuid>` verwijderen, `<age>` → `<date_of_birth>`, `<customer>` → `<contact>`
-  UserCreatedSender.php: v1.0 header → v2.0, type `user.created` → `user_created`
-  UserRegisteredSender.php: v1.0 header → v2.0, type `user.registered` → `user_registered`
-  UserUpdatedSender.php: v1.0 header → v2.0, type `user.updated` → `user_updated`
-  UserUnregisteredSender.php: v1.0 header → v2.0, type `user.unregistered` → `user_deleted`
-  UserCheckinSender.php: v1.0 header → v2.0, type `user.checkin` → `user_checkin`
-  CalendarInviteSender.php: v1.0 header → v2.0, type `calendar.invite` → `calendar_invite`, voeg `version` toe

---

###  **Team Planning** — Sessies & agenda (CONFORM )
**Audit Status:** Volledig conform (April 2026 update). **OPMERKING:** Gecentraliseerde session management RPC handlers verplicht volgens Sectie 17.


| Richting | Berichttype | Van/Naar | Sectie |
|----------|---|---|---|
|  **VERZENDT** | `session_created`, `session_updated`, `session_deleted` | → CRM | [7](#7-planning--crm) |
|  **ONTVANGT** | `calendar_invite` | ← Frontend | [17.2](#172-calendar_invite-frontend--planning) |
|  **ONTVANGT** | `cancel_registration` | ← CRM | [10.3](#103-cancel_registration-crm--kassa--planning) |
|  **ONTVANGT** | `session_create_request` | ← Frontend | [17.3](#173-session_create_request-frontend--planning) |
|  **ONTVANGT** | `session_update_request` | ← Frontend | [17.4](#174-session_update_request-frontend--planning) |
|  **ONTVANGT** | `session_delete_request` | ← Frontend | [17.5](#175-session_delete_request-frontend--planning) |
|  **VERZENDT** | `calendar_invite_confirmed` | → Frontend | [17.2](#172-calendar_invite_confirmed-planning--frontend) |
|  **RPC** | `session_view_request` / `session_view_response` | ↔ Frontend | [17.1](#171-session_view_request--session_view_response-rpc) |
|  **REST** | `Token Registration` | ← Frontend | [17.0](#170-oauth-token-registration-rest-api) |
|  **BROADCAST** | `heartbeat` | → Monitoring | [3](#3-heartbeat--alle-teams--monitoring) |

**XSD's referentie:**
- `Planning/xsd/` ( bijgewerkt naar v2.0)

**Belangrijk:** Gebruikt nu Master UUID (Session Persistence) via `correlation_id` voor alle sessie-gerelateerde berichten.

---

###  **Team Facturatie** — Factuurverwerking (KRITIEK - 4 XSD's + queue)
**Audit Status:** XSD's fout, queue fout, geen actieve builder

| Richting | Berichttype | Van/Naar | Huidi-Status | Sectie |
|----------|---|---|---|---|
|  **ONTVANGT** | `invoice_request` | ← CRM |  XSD bevat `<items>` | [11.1](#111-invoice_request-crm--facturatie) |
|  **ONTVANGT** | `consumption_order` (passthrough) | ← CRM/Kassa |  | [11.3](#113-consumption_order-crm--facturatie--passthrough) |
|  **ONTVANGT** | `new_registration` | ← CRM |  | [10.1](#101-new_registration-crm--kassa) |
|  **VERZENDT** | `invoice_status` | → CRM |  type is `send_invoice` | [8.1](#81-invoice_status) |
|  **VERZENDT** | `payment_registered` | → CRM |  XSD bevat `<master_uuid>` | [8.2](#82-payment_registered) |
|  **VERZENDT** | `send_mailing` | → Mailing |  | [13.1](#131-send_mailing-facturatie--mailing) |
|  **BROADCAST** | `heartbeat` | → Monitoring |  | [3](#3-heartbeat--alle-teams--monitoring) |

**Kritieke fixes (Facturatie/schemas/):**
-  Queue listener: `crm.to.facturatie` → `facturatie.incoming`
-  invoice_request.xsd: VERVANG volledig — verwijder `<items>`, vervang `<customer>` door `<invoice_data>`
-  new_registration.xsd: `<customer>` → `<contact>` wrapper
-  invoice_created_notification: fix schema xmlns, version 1.0 → 2.0
-  payment_registered.xsd: verwijder `<master_uuid>`

---

###  **Team Heartbeat** — Systeem health (KRITIEK - volledige herwrite)
**Audit Status:** Platte XML root in plaats van standaard envelope

| Richting | Berichttype | Van/Naar | Huidi-Status | Sectie |
|----------|---|---|---|---|
|  **VERZENDT** | `heartbeat` | → Monitoring |  platte root | [3](#3-heartbeat--alle-teams--monitoring) |

**Kritieke fix (heartbeat/sidecar.py):**
-  XML builder: `<heartbeat>` platte root → standaard `<message><header><body>` envelope
-  Header: voeg `version=2.0`, `type=heartbeat`, `source={systeem}`, unieke `message_id` toe
-  Body: `<status>online|degraded|offline</status>` (in plaats van `<system>`, `<uptime>`, etc.)

---

###  **Team Monitoring** — Systeemwaarschuwingen (KRITIEK - 1 XSD + Logstash)
**Audit Status:** Alert schema moet naar message envelope

| Richting | Berichttype | Van/Naar | Huidi-Status | Sectie |
|----------|---|---|---|---|
|  **ONTVANGT** | `heartbeat` | ← Alle teams |  | [3](#3-heartbeat--alle-teams--monitoring) |
|  **VERZENDT** | `system_alert` | → Mailing |  platte `<alert>` root | [4](#4-monitoring--mailing--alert) |

**Kritieke fixes (monitoring/):**
-  alert.xsd: VERVANG platte `<alert>` root → standaard `<message><header><body>` envelope
-  test/producer.py: platte heartbeat → standaard envelope
-  Logstash config: heartbeat parsing aanpassen aan nieuwe envelop-structuur

---

###  **Team Mailing** — E-mail verzending (CONFORM met 2 flows)
**Audit Status:** Geen code gevonden in scope, maar schema volledige gedocumenteerd

| Richting | Berichttype | Van/Naar | Huidi-Status | Sectie |
|----------|---|---|---|---|
|  **ONTVANGT** | `send_mailing` | ← CRM + Facturatie |  | [12.1](#121-send_mailing-crm--mailing) / [13.1](#131-send_mailing-facturatie--mailing) |
|  **ONTVANGT** | `system_alert` | ← Monitoring |  | [4](#4-monitoring--mailing--alert) |
|  **BROADCAST** | `heartbeat` | → Monitoring |  | [3](#3-heartbeat--alle-teams--monitoring) |

**Opmerkingen:**
- Mailing consumer moet zowel `source=crm` als `source=facturatie` verwerken
- Zelfde `send_mailing` schema voor beide sources

---

###  **Team Identity** — Authenticatie (UITZONDERING )
**Audit Status:** Conform — gebruikt platte XML (geoorloofde uitzondering)

| Richting | Berichttype | Van/Naar | Huidi-Status | Sectie |
|----------|---|---|---|---|
|  **ONTVANGT** | RPC request | ← CRM, Frontend |  platte XML (OK) | [15](#15-identity-service--uitzondering-op-de-standaard) |
|  **VERZENDT** | `identity_response` | → Requestor |  platte XML (OK) | [15.4](#154-rpc-response--identity-antwoord-alle-3-de-requests) |
|  **BROADCAST** | `user_event` | → CRM |  platte XML (OK) | [15.5](#155-fanout-event--usercreated) |

**Opmerkingen:**
- Identity Service is **bewust uitzondering** — uses RPC pattern met platte XML
- Geen wijzigingen nodig

---

## Navigatie naar gedetailleerde secties

- **[Sectie 0.5](#05-repo-audit-bevindingen-april-2026--wat-staat-er-nu-in-de-code)** — Volledige audit met source:line verwijzingen
- **[Secties 1-4](#1-de-4-globale-regels)** — Globale regels & standaard structuur
- **[Secties 5-9](#5-frontend--crm)** — INKOMEND: wat teams ontvangen
- **[Secties 10-13](#10-crm--kassa)** — UITGAAND: wat teams versturen
- **[Secties 14-21](#14-crm--frontend)** — Speciale flows & exceptions
- **[Sectie 16](#16-rabbitmq-queue--exchange-overzicht)** — Queue- & exchange-overzicht

---

---

## 0. Repo Audit Bevindingen (April 2026) — Wat staat er NU in de code?

> Deze sectie documenteert exact welke afwijkingen er nog in elke repo zitten ten opzichte van dit contract. Elk punt is een **harde actie** — geen interpretatie, geen onderhandeling.

### 0.5.1 Addendum — Gevalideerde scanresultaten (met bronregels)

Dit addendum overschrijft alle eerdere audituitspraken die niet met bronregel konden worden onderbouwd.

- Scope scan: `Kassa`, `CRM`, `Facturatie`, `Planning`, `IP-groep1-frontend`, `heartbeat`, `monitoring`, `identity-service`
- First-party `.xsd` gevonden: **0**
- First-party `.xml` gevonden: **0**
- XML-builders wel gevonden in code: **ja** (JS/PHP/Python)

**Afwijkingen met bronverwijzing:**

- CRM gebruikt nog `session_update` i.p.v. `session_updated` (`CRM/src/receiver.js:20`).
- CRM `invoice_request` bouwt `<customer>`, `<invoice>`, `<items>` i.p.v. contract-`<invoice_data>` (`CRM/src/sender.js:45`, `CRM/src/sender.js:53`, `CRM/src/sender.js:61`).
- CRM publiceert `invoice_request` nog naar `crm.to.facturatie` (`CRM/src/sender.js:124`).
- CRM bouwt outbound type `mailing_status` i.p.v. `send_mailing` (`CRM/src/sender.js:85`).
- CRM bouwt nog `<age>` in Kassa-flows (`CRM/src/sender.js:191`, `CRM/src/sender.js:245`).
- Frontend `UserCreatedSender` gebruikt nog namespace + receiver + version 1.0 + dotted type (`IP-groep1-frontend/web/modules/custom/rabbitmq_sender/src/UserCreatedSender.php:49`, `IP-groep1-frontend/web/modules/custom/rabbitmq_sender/src/UserCreatedSender.php:54`, `IP-groep1-frontend/web/modules/custom/rabbitmq_sender/src/UserCreatedSender.php:55`, `IP-groep1-frontend/web/modules/custom/rabbitmq_sender/src/UserCreatedSender.php:56`).
- Frontend `UserRegisteredSender` gebruikt nog dotted type `user.registered` en version 1.0 (`IP-groep1-frontend/web/modules/custom/rabbitmq_sender/src/UserRegisteredSender.php:64`, `IP-groep1-frontend/web/modules/custom/rabbitmq_sender/src/UserRegisteredSender.php:65`).
- Frontend `UserUnregisteredSender` gebruikt nog type `user.unregistered` en receiver-list in header (`IP-groep1-frontend/web/modules/custom/rabbitmq_sender/src/UserUnregisteredSender.php:67`, `IP-groep1-frontend/web/modules/custom/rabbitmq_sender/src/UserUnregisteredSender.php:68`, `IP-groep1-frontend/web/modules/custom/rabbitmq_sender/src/UserUnregisteredSender.php:69`).
- Frontend `UserCheckinSender` gebruikt nog type `user.checkin`, receiver en version 1.0 (`IP-groep1-frontend/web/modules/custom/rabbitmq_sender/src/UserCheckinSender.php:57`, `IP-groep1-frontend/web/modules/custom/rabbitmq_sender/src/UserCheckinSender.php:58`, `IP-groep1-frontend/web/modules/custom/rabbitmq_sender/src/UserCheckinSender.php:59`).
- Frontend `CalendarInviteSender` gebruikt nog dotted `calendar.invite` (`IP-groep1-frontend/web/modules/custom/rabbitmq_sender/src/CalendarInviteSender.php:25`) en zet geen `version` in header.
- Planning producer/test gemigreerd naar v2.0 (April 2026 update).
- Heartbeat service publiceert platte `<heartbeat>` root (`heartbeat/sidecar.py:50`).
- Monitoring test-producer publiceert platte `<heartbeat>` root (`monitoring/test/producer.py:30`).
- Identity-service gebruikt platte uitzonderingsberichten `identity_response` en `user_event` (`identity-service/rabbitmq_service.py:55`, `identity-service/rabbitmq_service.py:68`, `identity-service/rabbitmq_service.py:157`).
- Facturatie bevat momenteel geen actieve XML builder-code (`Facturatie/src/main.py` is leeg).
- Kassa integratiecode bevat momenteel geen XML message-builder (alleen keep-alive/XML-RPC utility).

### 0.5.2 Integrity Check Addendum — flow-voor-flow validatie (April 2026)

Resultaat van een extra inhoudscontrole op datacompleetheid + XSD-integriteit per kritieke flow.

- `consumption_order` (6.1): `unit_price` en `total_amount` gebruiken al verplicht currency-attribuut in de XSD. Geen blokkerende mismatch gevonden.
- `invoice_request` (6.5 en 11.1): body-structuur is consistent op `<invoice_data>` en gebruikt `correlation_id` voor koppeling met `consumption_order`.
- `new_registration` (10.1): contract is uitgelijnd op `<payment_due>` (niet `<amount_due>`).
- `badge_scanned` (6.3): integriteit bijgewerkt voor runtime-compatibiliteit:
  - `location` accepteert nu ook `main_bar` naast `entrance|bar|session`.
  - `source` accepteert nu `kassa` of `iot_gateway` (voor gateway-scenario's).
- `session_created` en `session_updated` (7.1/7.2): `speaker` volgt nu Regel 2 met verplichte `<contact>` wrapper i.p.v. losse `<name>`.
- `identity_request` (14.x): AMQP-properties nu explicieter gedocumenteerd omdat deze flow geen `<message><header>` envelop heeft.

**Overblijvend aandachtspunt:** De documentstructuur bevat nog dubbele hoofdsectienummers (historisch gegroeid); dit is een documentatie-risico, geen XSD-validatiefout.

###  Team Kassa — `IntegrationProject-Groep1/Kassa`

**Status: VOLLEDIG CONFORM **

Kassa's `XML_Structuren_Kassa.md` v2.5 en de bijhorende XSD-bestanden in `integratie/schemas/` voldoen volledig aan dit contract. Geen wijzigingen vereist.

Wat goed is:
-  Standaard `<message>` envelop overal
-  Header v2.0 conform (`version=2.0`, geen `<receiver>`, geen `<master_uuid>`)
-  `<contact>` wrapper rond namen
-  `currency="eur"` op alle bedragen
-  `<date_of_birth>` (geen `<age>`)
-  Snake_case message types
-  `correlation_id` correct gebruikt voor event chaining
-  XSD-validatie geïmplementeerd in receiver
-  `system_error` formaat naar `kassa.errors`
-  Routing keys correct: `kassa.payments.consumption/registration/refund/invoice/badge` + `kassa.frontend.payment/wallet`

> **Voor andere teams:** Gebruik de Kassa-implementatie als voorbeeld. De `integratie/sender.py` en `XML_Structuren_Kassa.md` zijn de referentie-implementatie.

---

###  Team CRM — `IntegrationProject-Groep1/CRM`

**Status: KRITIEKE AFWIJKINGEN — directe actie vereist**

#### Schendingen in `src/receiver.js`:
-  Handler `session_update` actief (oude naam) — moet `session_updated` zijn (sectie 7.2)
-  Handelt `mailing_status` af — dat is correct als inkomend van Mailing (sectie 9.1), maar het outgoing type voor CRM→Mailing moet `send_mailing` zijn

#### Schendingen in `src/sender.js`:
-  `sendNewRegistrationToKassa()`: bouwt nog `<age>` veld op — verwijderen en `<date_of_birth>` gebruiken (sectie 10.1)
-  `sendInvoiceRequest()`: voegt nog `<master_uuid>` toe in header — verwijderen (sectie 11.1)
-  `sendInvoiceRequest()`: voegt `<items>` blok toe in body — verwijderen, CRM is passthrough (sectie 11.1)
-  `sendInvoiceRequest()`: gebruikt `<customer>` body wrapper — moet `<invoice_data>` zijn (sectie 11.1)
-  `sendMailingSend()`: type-naam is `mailing_status` — moet `send_mailing` zijn (sectie 12.1)

#### Schendingen in queue-configuratie:
-  Outbound naar Facturatie via queue `crm.to.facturatie` — moet `facturatie.incoming` zijn (sectie 11)

#### Wat al correct is:
-  `src/heartbeat.js`: gebruikt al de standaard `<message>` envelop met v2.0 header
-  `src/sender.js` `buildMessage()`: header zonder `<receiver>` en zonder `xmlns`
-  `crm.dead-letter` queue voor falende berichten

#### Concrete actiepunten:
- [ ] `src/receiver.js`: hernoem case `'session_update'` → `'session_updated'`
- [ ] `src/sender.js` `buildNewRegistrationXml()`: verwijder `<age>`, voeg `<date_of_birth>` toe vanuit `crm_user_sync.date_of_birth`
- [ ] `src/sender.js` `buildInvoiceRequestXml()`: vervang volledige body door `<user_id>` + `<invoice_data>` (geen items, geen master_uuid)
- [ ] `src/sender.js` `sendInvoiceRequest()`: queue parameter `'crm.to.facturatie'` → `'facturatie.incoming'`
- [ ] `src/sender.js` `buildMailingSendXml()`: header `<type>mailing_status</type>` → `<type>send_mailing</type>`
- [ ] `tests/sender.test.js`: bijwerken zodat tests de nieuwe schemas valideren

---

###  Team Frontend — `IntegrationProject-Groep1/IP-groep1-frontend`

**Status: GROTE MIGRATIE NODIG — meeste senders zitten nog op v1.0 header**

#### Globaal probleem:
De repo heeft TWEE header-stijlen door elkaar:
- `NewRegistrationSender.php`: gebruikt v2.0 header maar bevat nog `<master_uuid>`
- ALLE andere senders: gebruiken nog v1.0 header met `xmlns="urn:integration:planning:v1"`, `<receiver>` tag, en `<version>1.0</version>`

**Dit MOET volledig naar v2.0 header gemigreerd worden voor ALLE senders zonder uitzondering.**

#### Schendingen per sender:

**`NewRegistrationSender.php`:**
-  Header bevat nog `<master_uuid>` — verwijderen (zie sectie 5.1)
-  Body bevat nog `<age>` — vervangen door `<date_of_birth>`
-  Body gebruikt `<customer>` met losse `first_name`/`last_name` — moet `<contact>` wrapper hebben (Regel 2)

**`UserUnregisteredSender.php`:**
-  Type `user.unregistered` → `user_deleted` (changelog #7, sectie 5.3)
-  Header heeft `xmlns="urn:integration:planning:v1"` — verwijderen
-  Header heeft `<receiver>` tag — verwijderen
-  `version=1.0` → `2.0`
-  Body heeft `<master_uuid>` — verwijderen

**`UserCreatedSender.php`:**
-  Type `user.created` → `user_created` (snake_case)
-  v1.0 header → v2.0 header (zelfde fixes als hierboven)

**`UserRegisteredSender.php`:**
-  Type `user.registered` → `user_registered`
-  v1.0 header → v2.0 header

**`UserUpdatedSender.php`:**
-  Type `user.updated` → `user_updated`
-  v1.0 header → v2.0 header

**`UserCheckinSender.php`:**
-  Type `user.checkin` → `user_checkin` (changelog #49, sectie 21.1)
-  Header heeft `<receiver>` tag — verwijderen
-  `version=1.0` → `2.0`
-  `xmlns` namespace verwijderen
-  `<session_id>` toevoegen (optioneel maar aanbevolen voor opkomst-tracking)

**`CalendarInviteSender.php`:**
-  Type `calendar.invite` → `calendar_invite` (changelog #46, sectie 17.2)
-  Header mist `<version>` veld volledig — toevoegen `<version>2.0</version>`
-  `xmlns` namespace verwijderen
-  Body mist `<attendee_email>` — toevoegen (verplicht)

**`EventEndedSender.php`:**
-  Gebruikt al v2.0 header — correct

#### Receivers die nog moeten worden bijgewerkt:
- `SessionCreatedReceiver.php`: type-validatie moet `session_created` accepteren (zonder namespace)
- `SessionUpdateReceiver.php`: type-validatie moet `session_updated` accepteren (niet `session_update`)
- `BadgeScannedReceiver.php`:  correct
- `PaymentRegisteredReceiver.php`:  correct

#### Concrete actiepunten:
- [ ] **Migreer ALLE senders** naar v2.0 header (verwijder xmlns, receiver, master_uuid, version=1.0)
- [ ] Hernoem types: `user.unregistered` → `user_deleted`, `user.created` → `user_created`, `user.registered` → `user_registered`, `user.updated` → `user_updated`, `user.checkin` → `user_checkin`, `calendar.invite` → `calendar_invite`
- [ ] `NewRegistrationSender.php`: `<age>` → `<date_of_birth>`, namen in `<contact>` wrapper
- [ ] `CalendarInviteSender.php`: voeg `<version>2.0</version>` toe + `<attendee_email>` body
- [ ] `SessionUpdateReceiver.php`: accepteer `session_updated` als type-waarde (niet `session_update`)
- [ ] Identity RPC implementeren VÓÓR de CRM-call bij registratie (sectie 15.6)

---

###  Team Facturatie — `IntegrationProject-Groep1/Facturatie`

**Status: KRITIEKE XSD'S MOETEN VERVANGEN WORDEN**

#### Schendingen in XSD's:

**`invoice_request.xsd` (volledig fout):**
-  Bevat `<items>` blok in body — verwijderen, CRM is passthrough (sectie 11.1)
-  Bevat `<customer>` body wrapper — moet `<invoice_data>` zijn met platte `first_name`/`last_name`
-  Header bevat `<master_uuid>` — verwijderen
-  Header mist verplichte `<correlation_id>` — toevoegen (verplicht in deze flow)

**`new_registration.xsd`:**
-  `first_name`/`last_name` los in `<customer>` — moet in `<contact>` wrapper (Regel 2)
-  Header bevat `<master_uuid>` — verwijderen
-  Mist `<vat_number>`, `<company_name>`, `<payment_due>` velden die in v2.0.1 zijn toegevoegd

**`invoice_created_notification` schema:**
-  `<version>1.0</version>` → moet `<version>2.0</version>` zijn
-  `<xs:schema xmlns="">` → moet `xmlns:xs="http://www.w3.org/2001/XMLSchema"` zijn (de huidige `xmlns=""` is broken)

**`payment_registered.xsd` (Facturatie → CRM):**
-  Header heeft `<master_uuid>` — verwijderen
-  Source heeft "crm_system" als string-waarde — moet `crm` of `facturatie` zijn (afhankelijk van richting)

#### Schendingen in outbound types:
-  Outgoing type voor "factuur klaar"-bericht naar CRM is `send_invoice` — moet `invoice_status` zijn (sectie 8.1)

#### Schendingen in queue-configuratie:
-  Listener op queue `crm.to.facturatie` — moet `facturatie.incoming` zijn (sectie 11)

#### Concrete actiepunten:
- [ ] **VERVANG `invoice_request.xsd` volledig** met de XSD uit sectie 11.1 van dit contract
- [ ] **VERVANG `new_registration.xsd`** met `<contact>` wrapper, zonder `<master_uuid>`
- [ ] **`invoice_created_notification`**: corrigeer schema xmlns + version naar 2.0
- [ ] **`payment_registered.xsd`**: verwijder `<master_uuid>`, source-validatie correct
- [ ] Outbound `send_invoice` → `invoice_status` (sectie 8.1)
- [ ] Queue listener: `crm.to.facturatie` → `facturatie.incoming`
- [ ] `currency="eur"` toevoegen op alle bedragen waar dat nog ontbreekt
- [ ] Eigen XSD-validatie implementeren voor inkomende berichten (faal → DLQ)
- [ ] `send_mailing` consumer implementeren (Facturatie → Mailing flow)

---

###  Team Planning — `IntegrationProject-Groep1/Planning`

**Status: VOLLEDIG CONFORM **

Planning heeft in de update van April 2026 alle kritieke afwijkingen weggewerkt.

Wat nu correct is:
-  **XSD's**: Alle 7 XSD's in `/xsd/` folder zijn gemigreerd naar v2.0 (geen namespaces, `xs:dateTime` voor datums, snake_case types).
-  **Routing Keys**: Gebruikt nu de standaard `frontend.to.planning` en `planning.to.frontend` prefixes.
-  **Master UUID**: Implementatie van Master UUID Manager voor sessies; `correlation_id` wordt consistent gebruikt voor persistence over created/updated/deleted events.
-  **OAuth**: REST API voor token registration gedocumenteerd en operationeel.
-  **ICS Link**: Toegevoegd aan bevestigingsberichten voor brede compatibiliteit.

---

###  Heartbeat Service — `IntegrationProject-Groep1/heartbeat`

**Status: VOLLEDIG ANTI-PATROON — moet herschreven worden**

#### Schending:
-  Stuurt platte XML root: `<heartbeat><system>...</system><timestamp>...</timestamp><uptime>...</uptime></heartbeat>`
-  Geen `<message>` envelop — breekt sectie 2 van het contract
-  Geen `<header>` met `version`, `type`, `source`, `message_id`, `timestamp`

#### Concrete actiepunten:
- [ ] **Volledige herwrite** van XML-builder: gebruik standaard `<message>` envelop (zie sectie 3)
- [ ] Header: `version=2.0`, `type=heartbeat`, `source={systeem_naam}`, unieke `message_id` per heartbeat
- [ ] Body: `<status>online|degraded|offline</status>`
- [ ] Verwijder oud `<system>` veld — komt uit `header.source`
- [ ] Behoud `<uptime>` als optioneel body-veld indien gewenst (niet in standaard XSD)

---

###  Team Monitoring — `IntegrationProject-Groep1/Monitoring`

**Status: ALERT-FORMAAT MOET GEMIGREERD WORDEN**

#### Schendingen:
-  `alert.xsd` definieert nog platte `<alert>` root — moet standaard `<message>` envelop zijn (sectie 4)
-  `<source>` zat in body als `<s>` — hernoemen naar `<source>` of `<system>`
-  Logstash heartbeat-parser leest nog oud `<system>` veld — moet `header.source` lezen

#### Concrete actiepunten:
- [ ] **VERVANG `alert.xsd`** met de XSD uit sectie 4 (`type=system_alert`, message envelop)
- [ ] Logstash parser: bron lezen uit `header.source` i.p.v. body `<system>`
- [ ] Heartbeat consumer aanpassen aan nieuwe envelop-structuur

---

###  Team Identity — `IntegrationProject-Groep1/identity-service`

**Status: CONFORM (uitzondering op envelop-regel — mag platte XML)**

Identity Service gebruikt platte XML zonder `<message><header>` wrapper — dit is een **gedocumenteerde uitzondering** in sectie 15. Geen wijzigingen nodig. Andere teams die de Identity Service consumeren moeten weten dat dit anders werkt dan de standaard.

---

### Samenvatting Audit

| Team | Status | Aantal kritieke wijzigingen | Geschatte werklast |
|------|--------|----------------------------|---------------------|
| Kassa |  Conform | 0 | — |
| Identity |  Conform (uitzondering) | 0 | — |
| Planning |  Producer OK, XSD's fout | 7 XSD-bestanden bijwerken | ~1 dag |
| Monitoring |  Eén schema migreren | 1 XSD + Logstash config | ~halve dag |
| CRM |  Meerdere senders + receiver | 5 builders + 1 queue config | ~1-2 dagen |
| Facturatie |  XSD's vervangen | 4 XSD's + 1 queue + 1 type | ~1-2 dagen |
| Frontend |  Volledige header migratie | 6 senders volledig herwerken | ~2-3 dagen |
| Heartbeat |  Volledige herwrite | XML builder herschrijven | ~halve dag |

> **Volgorde van uitvoering aanbevolen:** Heartbeat → Monitoring → Planning → Facturatie → CRM → Frontend. Dit minimaliseert berichten die naar de DLQ gaan tijdens de migratie.

---

## 0.6 Missing from original v2.0 contract

Deze onderdelen bestaan aantoonbaar in code of operationele documentatie, maar stonden niet expliciet in het originele v2.0 contract:

- Identity RPC antwoordformaat `<identity_response>` met foutcodes (`identity-service/rabbitmq_service.py:55`, `identity-service/rabbitmq_service.py:68`).
- Identity fanout event `<user_event>` met `<event>UserCreated</event>` (`identity-service/rabbitmq_service.py:157`).
- CRM verwerkt nog legacy berichttype `session_update` (moet als legacy pad gemarkeerd worden totdat migratie klaar is) (`CRM/src/receiver.js:20`).
- Frontend gebruikt nog legacy dotted eventtypes (`user.created`, `user.registered`, `user.unregistered`, `user.checkin`, `calendar.invite`) die in v2.0 als snake_case bedoeld waren.

## 0.7 Critical gaps found during full scan

- Gap 1: Er staan geen first-party XSD-bestanden in de gescande teamrepositories. Daardoor is schema-validatie in code niet afdwingbaar via repo-artifacts.
- Gap 2: Er staan geen losse XML voorbeeldbestanden (`*.xml`) in de teamrepositories; contractvoorbeelden leven enkel in code/tests.
- Gap 3: Meerdere teams draaien mixed contractversies tegelijk (v1.0 en v2.0 headers naast elkaar), wat compatibiliteitsfouten veroorzaakt.
- Gap 4: Planning en Frontend delen nog dotted `calendar.invite` i.p.v. contract-`calendar_invite`.
- Gap 5: Heartbeat formaat is niet geharmoniseerd tussen services (platte root i.p.v. standaard envelope).
- Gap 6: CRM gebruikt nog oude facturatie-routing en legacy body-structuur voor `invoice_request`.

**Dit was niet in het originele contract:** de mate van repository-leegte voor XSD/XML artifacts (geen first-party `.xsd`/`.xml`).

**Dit ontbrak in de code:** contract-conforme implementatie van meerdere v2.0 velden/types in Frontend, Planning, CRM, Heartbeat en Monitoring.

## 0.8 Delta-update voor Secties 3-19 (contract vs. code)

| Sectie | Berichttype(n) | Contractstatus | Code-realiteit uit scan | Actie |
|---|---|---|---|---|
| 3 | `heartbeat` | `message/header/body` envelope | `heartbeat/sidecar.py:50` gebruikt platte `<heartbeat>` | Builder migreren |
| 4 | `system_alert` | `message/header/body` envelope | In scope geen first-party alert XSD/XML gevonden; monitoring test gebruikt platte heartbeat XML | Monitoring flow harmoniseren |
| 5 | Frontend -> CRM (`new_registration`, `user_updated`, `user_deleted`) | v2.0 + snake_case | `NewRegistrationSender` deels v2.0, andere senders nog legacy v1.0/dotted | Alle senders uniformeren |
| 6 | Kassa -> CRM | Contract beschreven | Geen actieve Kassa XML-builder of XSD gevonden in gescande repo-inhoud | Implementatieartefacts toevoegen |
| 7 | Planning -> CRM (`session_created`, `session_updated`, `session_deleted`) | snake_case, v2.0 | Planning gebruikt `calendar.invite`, namespace en `1.0`; CRM gebruikt `session_update` | Type/header migratie |
| 8 | Facturatie -> CRM | Contract beschreven | Geen actieve XML-builder/XSD in `Facturatie` | Implementatieartefacts toevoegen |
| 9 | Mailing -> CRM | Contract beschreven | In scope geen first-party mailing builder gevonden | Validatie in Mailing repo nodig |
| 10 | CRM -> Kassa (`new_registration`, `profile_update`) | `date_of_birth` | CRM bouwt nog `age` (`CRM/src/sender.js:191`, `CRM/src/sender.js:245`) | Veldmigratie |
| 11 | CRM -> Facturatie (`invoice_request`) | `invoice_data` passthrough | CRM bouwt `customer` + `invoice` + `items`; queue `crm.to.facturatie` | Body + routing corrigeren |
| 12 | CRM -> Mailing (`send_mailing`) | `send_mailing` | CRM bouwt type `mailing_status` | Type corrigeren |
| 13 | Facturatie -> Mailing / CRM -> Frontend | Contract beschreven | Geen first-party XML builders gevonden in Facturatie-scope | Implementeren of contract markeren als pending |
| 14 | Identity uitzondering | Platte XML toegestaan | `identity_response` en `user_event` aanwezig en consistent | Geen kritieke wijziging |
| 15-16 | Queue-overzicht en team-samenvatting | Documentair | Code toont mixed queue/type conventies | Overzicht synchroniseren met code |
| 17 | Frontend <-> Planning (`calendar_invite`) | `calendar_invite` | Frontend/Planning gebruiken `calendar.invite` | Type migreren |
| 18 | `vat_validation_error` | Header verplicht, gestandaardiseerd | Frontend receiver leest body-velden, valideert geen header-constraint | Receiver-validatie aanscherpen |
| 19 | `user_checkin` | `user_checkin`, v2.0 | Frontend sender gebruikt `user.checkin`, `receiver`, `1.0` | Type/header migreren |

---

## Inhoudsopgave

0.5. [**Repo Audit Bevindingen (NIEUW v2.3)**](#05-repo-audit-bevindingen-april-2026--wat-staat-er-nu-in-de-code)
1. [De 4 Globale Regels](#1-de-4-globale-regels)
2. [Standaard Berichtstructuur](#2-standaard-berichtstructuur)
2.5 [Error Handling & Resilience Strategy](#25-error-handling--resilience-strategy)
2.6 [Global system_error Format](#26-global-system_error-format)
3. [Heartbeat — Alle teams → Monitoring](#3-heartbeat--alle-teams--monitoring)
4. [Monitoring → Mailing — Alert](#4-monitoring--mailing--alert)
5. [Frontend → CRM](#5-frontend--crm)
6. [Kassa → CRM](#6-kassa--crm)
7. [Planning → CRM](#7-planning--crm)
8. [Facturatie → CRM](#8-facturatie--crm)
9. [Mailing → CRM](#9-mailing--crm)
10. [CRM → Kassa](#10-crm--kassa)
11. [CRM → Facturatie](#11-crm--facturatie) *(11.1 invoice_request, 11.2 invoice_cancelled, 11.3 consumption_order passthrough, 11.4 payment_registered passthrough)*
12. [CRM → Mailing](#12-crm--mailing)
13. [Facturatie → Mailing](#13-facturatie--mailing)
14. [CRM → Frontend](#14-crm--frontend)
15. [Identity Service (Uitzondering!)](#15-identity-service--uitzondering-op-de-standaard)
16. [RabbitMQ Queue & Exchange Overzicht](#16-rabbitmq-queue--exchange-overzicht)
17. [Per-Team Samenvatting](#17-per-team-samenvatting)
18. [Frontend ← Kassa (Direct flows)](#18-frontend--kassa-direct-flows)
19. [Frontend ↔ Planning (Directe flows)](#19-frontend--planning-directe-flows)
20. [CRM / Facturatie → Frontend: BTW Validatiefout](#20-crm--facturatie--frontend-btw-validatiefout)
21. [Frontend / Kassa → CRM + Monitoring: Check-in](#21-frontend--kassa--crm--monitoring-check-in)
22. [Migratie Roadmap (NIEUW v2.3)](#22-migratie-roadmap)
23. [Validatie Checklist](#23-validatie-checklist-per-bericht)
24. [Cross-Team Interface Analyse](#24-cross-team-interface-analyse--welke-xml-moet-gesynchroniseerd-worden)
25. [Centralisatie](#25-centralisatie--hoe-dit-document-te-gebruiken)
26. [Final Rule](#26-final-rule)

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
<user_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user_id>

<!--  FOUT — Gebruik GEEN interne database ID's van je eigen systeem -->
<user_id>drupal-user-4821</user_id>
<user_id>sf-contact-00891</user_id>
<user_id>odoo-partner-99</user_id>
```

**Waarom:** Interne ID's (Salesforce ID, Drupal UID, Odoo Partner ID) zijn alleen zinvol binnen de eigen service. Voor communicatie tussen teams is de **Master UUID** van de Identity Service de enige geldige identifier. Interne queries worden gedaan met de eigen ID, maar voor XML-berichten naar buiten gebruik je verplicht de Master UUID.

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
        <xs:attribute name="currency" use="required">
          <xs:simpleType>
            <xs:restriction base="xs:string">
              <xs:enumeration value="eur"/>
            </xs:restriction>
          </xs:simpleType>
        </xs:attribute>
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

---

## 2.6 Global `system_error` Format

Elk team gebruikt dit formaat om fouten te rapporteren naar Monitoring of hun eigen error queue.

**Gezamenlijke Error Codes:**

| Code | Wanneer |
|------|---------|
| `invalid_xml_format` | Binnenkomend bericht voldoet niet aan XSD |
| `unknown_message_type` | Onbekend berichttype ontvangen |
| `profile_not_found` | De Master UUID (`user_id`) is niet bekend in je systeem |
| `identity_service_unavailable` | Kan geen Master UUID ophalen bij de Identity Service |
| `database_error` | Interne database fout bij verwerken bericht |

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
              <xs:element name="type"       type="xs:string" fixed="system_error"/>
              <xs:element name="source"     type="xs:string"/>
              <xs:element name="timestamp"  type="xs:dateTime"/>
              <xs:element name="version"    type="xs:string" fixed="2.0"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
        <xs:element name="body">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="error_code"          type="xs:string"/>
              <xs:element name="error_description"   type="xs:string"/>
              <!-- related_message_id: message_id van het bericht dat de fout veroorzaakte -->
              <xs:element name="related_message_id"  type="xs:string" minOccurs="0"/>
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
    <type>system_error</type>
    <source>crm</source>
    <timestamp>2026-05-15T19:05:00Z</timestamp>
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

- **Queue:** `heartbeat`
- **Interval:** elke 1 seconde
- **Wie stuurt:** frontend, crm, kassa, planning, facturatie, mailing, monitoring

### XSD

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
                  <xs:enumeration value="degraded"/>
                  <xs:enumeration value="offline"/>
                </xs:restriction></xs:simpleType>
              </xs:element>
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
  </body>
</message>
```

> ** Let op voor Monitoring-team:** Het veld `source` in de header komt overeen met het `system`-veld dat jullie intern gebruiken voor de Logstash-mapping. Toegestane waarden: `frontend`, `crm`, `kassa`, `planning`, `facturatie`, `mailing`, `monitoring`.

---

## 4. Monitoring → Mailing — Alert

- **Exchange:** `monitoring.alerts`  
- **Queue:** `monitoring.alerts`
- **Wanneer:** Een systeem is down gegaan of terug online gekomen

> ** Wijziging voor Mailing-team:** Jullie huidige `<alert><s>...</s>` formaat wordt vervangen door het standaard `<message>` formaat met een `<source>` tag in het body-blok (was `<s>`). Pas `alert.xsd` en de consumer aan.

### XSD

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
              <xs:element name="source">
                <xs:simpleType><xs:restriction base="xs:string">
                  <xs:enumeration value="monitoring"/>
                </xs:restriction></xs:simpleType>
              </xs:element>
              <xs:element name="type">
                <xs:simpleType><xs:restriction base="xs:string">
                  <xs:enumeration value="system_alert"/>
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
              <xs:element name="system" type="xs:string"/>
              <xs:element name="status">
                <xs:simpleType><xs:restriction base="xs:string">
                  <xs:enumeration value="down"/>
                  <xs:enumeration value="up"/>
                  <xs:enumeration value="degraded"/>
                </xs:restriction></xs:simpleType>
              </xs:element>
              <xs:element name="last_seen" type="xs:dateTime" minOccurs="0"/>
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
    <timestamp>2026-04-24T10:35:12Z</timestamp>
    <source>monitoring</source>
    <type>system_alert</type>
    <version>2.0</version>
  </header>
  <body>
    <system>facturatie</system>
    <status>down</status>
    <last_seen>2026-04-24T10:34:10Z</last_seen>
  </body>
</message>
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
  <xs:element name="message">
    <xs:complexType><xs:sequence>

      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id" type="xs:string"/>
          <xs:element name="timestamp"  type="xs:dateTime"/>
          <xs:element name="source"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="frontend"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="new_registration"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="version"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="2.0"/></xs:restriction></xs:simpleType></xs:element>
        </xs:sequence></xs:complexType>
      </xs:element>

      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <xs:element name="customer">
            <xs:complexType><xs:sequence>
              <!-- user_id: de master_uuid van de Identity Service -->
              <xs:element name="user_id"       type="xs:string"/>
              <xs:element name="email"         type="xs:string"/>
              <xs:element name="date_of_birth" type="xs:date"/>
              <xs:element name="contact">
                <xs:complexType><xs:sequence>
                  <xs:element name="first_name" type="xs:string"/>
                  <xs:element name="last_name"  type="xs:string"/>
                </xs:sequence></xs:complexType>
              </xs:element>
              <xs:element name="phone"      type="xs:string" minOccurs="0"/>
              <xs:element name="company_id" type="xs:string" minOccurs="0"/>
              <xs:element name="session_id" type="xs:string"/>
              <xs:element name="payment_due">
                <xs:complexType><xs:sequence>
                  <xs:element name="amount">
                    <xs:complexType><xs:simpleContent><xs:extension base="xs:decimal">
                      <xs:attribute name="currency" type="xs:string" use="required"/>
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
  </header>
  <body>
    <customer>
      <user_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user_id>
      <email>jan.peeters@ehb.be</email>
      <date_of_birth>1995-03-21</date_of_birth>
      <contact>
        <first_name>Jan</first_name>
        <last_name>Peeters</last_name>
      </contact>
      <phone>+32477123456</phone>
      <company_id>ehb-001</company_id>
      <session_id>sess-keynote-001</session_id>
      <payment_due>
        <amount currency="eur">25.00</amount>
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
  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id" type="xs:string"/>
          <xs:element name="timestamp"  type="xs:dateTime"/>
          <xs:element name="source"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="frontend"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="user_updated"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="version"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="2.0"/></xs:restriction></xs:simpleType></xs:element>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <xs:element name="customer">
            <xs:complexType><xs:sequence>
              <!-- user_id: de master_uuid van de Identity Service -->
              <xs:element name="user_id"       type="xs:string"/>
              <xs:element name="email"         type="xs:string"/>
              <xs:element name="date_of_birth" type="xs:date" minOccurs="0"/>
              <xs:element name="contact">
                <xs:complexType><xs:sequence>
                  <xs:element name="first_name" type="xs:string"/>
                  <xs:element name="last_name"  type="xs:string"/>
                </xs:sequence></xs:complexType>
              </xs:element>
              <xs:element name="phone"      type="xs:string" minOccurs="0"/>
              <xs:element name="company_id" type="xs:string" minOccurs="0"/>
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
      <user_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user_id>
      <email>jan.peeters.nieuw@ehb.be</email>
      <contact>
        <first_name>Jan</first_name>
        <last_name>Peeters</last_name>
      </contact>
      <phone>+32477999888</phone>
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
  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id" type="xs:string"/>
          <xs:element name="timestamp"  type="xs:dateTime"/>
          <xs:element name="source"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="frontend"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="user_deleted"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="version"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="2.0"/></xs:restriction></xs:simpleType></xs:element>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <!-- user_id: de master_uuid van de Identity Service -->
          <xs:element name="user_id"     type="xs:string"/>
          <xs:element name="email"       type="xs:string"/>
          <xs:element name="reason"      type="xs:string" minOccurs="0"/>
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
    <user_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user_id>
    <email>jan.peeters@ehb.be</email>
    <reason>Account op verzoek van gebruiker verwijderd</reason>
  </body>
</message>
```

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
      <xs:element name="user_id" type="xs:string" minOccurs="0"/>
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
              <xs:attribute name="currency" type="xs:string" use="required"/>
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
              <xs:attribute name="currency" type="xs:string" use="required"/>
            </xs:extension>
          </xs:simpleContent>
        </xs:complexType>
      </xs:element>
      <xs:element name="item_type" type="xs:string" minOccurs="0"/>
    </xs:sequence>
  </xs:complexType>

  <xs:element name="message">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="header">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="message_id" type="xs:string"/>
              <xs:element name="type"       type="xs:string" fixed="consumption_order"/>
              <xs:element name="source"     type="xs:string"/>
              <xs:element name="timestamp"  type="xs:dateTime"/>
              <xs:element name="version"    type="xs:string"/>
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

#### Voorbeeld XML

```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>f47ac10b-58cc-4372-a567-0e02b2c3d479</message_id>
    <type>consumption_order</type>
    <source>kassa</source>
    <timestamp>2026-05-15T18:30:00Z</timestamp>
    <version>2.0</version>
  </header>
  <body>
    <is_anonymous>false</is_anonymous>
    <customer>
      <id>12345</id>
      <user_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user_id>
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
      <item>
        <id>LINE-4201</id>
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
  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id" type="xs:string"/>
          <xs:element name="timestamp"  type="xs:dateTime"/>
          <xs:element name="source"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="kassa"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="badge_assigned"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="version"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="2.0"/></xs:restriction></xs:simpleType></xs:element>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <xs:element name="user_id" type="xs:string"/>
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
    <user_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user_id>
    <badge_id>BADGE-0042</badge_id>
    <assigned_at>2026-05-15T18:05:00Z</assigned_at>
  </body>
</message>
```

---

### 6.3 `badge_scanned`

Een badge wordt gescand aan de inkom (IoT / Raspberry Pi).

#### XSD

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
            <xs:enumeration value="kassa"/>
            <xs:enumeration value="iot_gateway"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="badge_scanned"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="version"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="2.0"/></xs:restriction></xs:simpleType></xs:element>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <xs:element name="badge_id"   type="xs:string"/>
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

#### Voorbeeld XML

```xml
<message>
  <header>
    <message_id>18b9c0d1-e2f3-4567-bcde-567890100007</message_id>
    <timestamp>2026-05-15T18:06:30Z</timestamp>
    <source>kassa</source>
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
        <xs:attribute name="currency" type="xs:string" use="required"/>
      </xs:extension>
    </xs:simpleContent>
  </xs:complexType>

  <xs:element name="message">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="header">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="message_id"     type="xs:string"/>
              <xs:element name="type"           type="xs:string" fixed="refund_processed"/>
              <xs:element name="source"         type="xs:string" fixed="kassa"/>
              <xs:element name="timestamp"      type="xs:dateTime"/>
              <xs:element name="version"        type="xs:string" fixed="2.0"/>
              <!-- correlation_id = message_id van de originele payment_registered -->
              <xs:element name="correlation_id" type="xs:string" minOccurs="0"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
        <xs:element name="body">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="refund_type">
                <xs:simpleType>
                  <xs:restriction base="xs:string">
                    <xs:enumeration value="consumption_item"/>
                    <xs:enumeration value="partial"/>
                  </xs:restriction>
                </xs:simpleType>
              </xs:element>
              <!-- user_id optioneel: anonieme refunds hebben geen user_id -->
              <xs:element name="user_id" type="xs:string" minOccurs="0"/>
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
            </xs:sequence>
          </xs:complexType>
        </xs:element>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
```

#### Voorbeeld XML — badge_wallet refund

```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>f15e0000-0000-0000-0000-000000000005</message_id>
    <type>refund_processed</type>
    <source>kassa</source>
    <timestamp>2026-05-15T16:45:00Z</timestamp>
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

#### Voorbeeld XML — anonieme cash refund

```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>30d1e2f3-a4b5-6789-defa-789012300009</message_id>
    <type>refund_processed</type>
    <source>kassa</source>
    <timestamp>2026-05-15T20:15:00Z</timestamp>
    <version>2.0</version>
    <correlation_id>8fc6d7e8-f9a0-1234-cdef-234567800014</correlation_id>
  </header>
  <body>
    <refund_type>consumption_item</refund_type>
    <!-- geen user_id bij anonieme terugbetaling -->
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
      <!--  first_name/last_name zitten hier NIET in een <contact> wrapper
           Dit is een gedocumenteerde uitzondering specifiek voor Kassa→CRM invoice_request -->
      <xs:element name="first_name"  type="xs:string"/>
      <xs:element name="last_name"   type="xs:string"/>
      <xs:element name="email"       type="xs:string"/>
      <xs:element name="address"     type="AddressType"/>
      <xs:element name="vat_number"  type="xs:string" minOccurs="0"/>
    </xs:sequence>
  </xs:complexType>

  <xs:element name="message">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="header">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="message_id"    type="xs:string"/>
              <xs:element name="type"          type="xs:string" fixed="invoice_request"/>
              <xs:element name="source"        type="xs:string"/>
              <xs:element name="timestamp"     type="xs:dateTime"/>
              <xs:element name="version"       type="xs:string"/>
              <!-- correlation_id = message_id van het consumption_order bericht -->
              <xs:element name="correlation_id" type="xs:string" minOccurs="0"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
        <xs:element name="body">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="user_id"      type="xs:string"/>
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
    <type>invoice_request</type>
    <source>kassa</source>
    <timestamp>2026-05-15T20:00:00Z</timestamp>
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

---

### 6.6 `payment_registered` (Kassa → RabbitMQ)

Kassa stuurt dit na elke afgeronde kassatransactie.

- **consumption** → routing key `kassa.payments.consumption` (samen met `consumption_order`)
- **registration** → routing key `kassa.payments.registration` (inschrijvingsgeld aan kassa)

> **`correlation_id`:** bij consumption = `message_id` van de bijhorende `consumption_order`. Bij registration = `message_id` van de originele `new_registration`.
>
> **`payment_method`:** `company_link` (bedrijfsrekening), `on_site` (cash/kaart/badge wallet), `online`.
>
> **`invoice.id`:** optioneel — afwezig bij `registration` (CRM maakt factuur aan). Aanwezig bij `consumption`.
>
> **`user_id`** op body-niveau: optioneel bij consumptie, verplicht bij registratie.

#### XSD (v2.1 — conform Kassa schema_payment_registered_v2.1.xsd)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">

  <xs:complexType name="CurrencyAmountType">
    <xs:simpleContent>
      <xs:extension base="xs:decimal">
        <xs:attribute name="currency" type="xs:string" use="required"/>
      </xs:extension>
    </xs:simpleContent>
  </xs:complexType>

  <xs:element name="message">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="header">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="message_id"     type="xs:string"/>
              <xs:element name="type"           type="xs:string" fixed="payment_registered"/>
              <xs:element name="source"         type="xs:string" fixed="kassa"/>
              <xs:element name="timestamp"      type="xs:dateTime"/>
              <xs:element name="version"        type="xs:string" fixed="2.0"/>
              <xs:element name="correlation_id" type="xs:string" minOccurs="0"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
        <xs:element name="body">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="payment_context">
                <xs:simpleType>
                  <xs:restriction base="xs:string">
                    <xs:enumeration value="registration"/>
                    <xs:enumeration value="consumption"/>
                  </xs:restriction>
                </xs:simpleType>
              </xs:element>
              <!-- user_id optioneel bij consumption, aanwezig bij registration -->
              <xs:element name="user_id" type="xs:string" minOccurs="0"/>
              <xs:element name="invoice">
                <xs:complexType>
                  <xs:sequence>
                    <!-- id optioneel bij registration: CRM maakt factuur aan -->
                    <xs:element name="id" type="xs:string" minOccurs="0"/>
                    <xs:element name="status">
                      <xs:simpleType>
                        <xs:restriction base="xs:string">
                          <xs:enumeration value="paid"/>
                          <xs:enumeration value="pending"/>
                          <xs:enumeration value="cancelled"/>
                        </xs:restriction>
                      </xs:simpleType>
                    </xs:element>
                    <xs:element name="amount_paid" type="CurrencyAmountType"/>
                    <xs:element name="due_date"    type="xs:date"/>
                  </xs:sequence>
                </xs:complexType>
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
    <type>payment_registered</type>
    <source>kassa</source>
    <timestamp>2026-05-15T18:35:00Z</timestamp>
    <version>2.0</version>
    <correlation_id>f47ac10b-58cc-4372-a567-0e02b2c3d479</correlation_id>
  </header>
  <body>
    <payment_context>consumption</payment_context>
    <user_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user_id>
    <invoice>
      <id>INV-2026-001</id>
      <status>paid</status>
      <amount_paid currency="eur">15.00</amount_paid>
      <due_date>2026-05-15</due_date>
    </invoice>
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
    <type>payment_registered</type>
    <source>kassa</source>
    <timestamp>2026-05-15T09:15:00Z</timestamp>
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
      <due_date>2026-05-15</due_date>
    </invoice>
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
  <xs:element name="message">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="header">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="message_id" type="xs:string"/>
              <xs:element name="type"       type="xs:string" fixed="payment_status"/>
              <xs:element name="source"     type="xs:string" fixed="kassa"/>
              <xs:element name="timestamp"  type="xs:dateTime"/>
              <xs:element name="version"    type="xs:string" fixed="2.0"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
        <xs:element name="body">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="user_id" type="xs:string"/>
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
    <type>payment_status</type>
    <source>kassa</source>
    <timestamp>2026-05-15T18:35:00Z</timestamp>
    <version>2.0</version>
  </header>
  <body>
    <user_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user_id>
    <payment_status>paid</payment_status>
  </body>
</message>
```

---

### 6.8 `wallet_balance_update` (Kassa → Frontend)

Kassa stuurt het **nieuwe badge-saldo** na elke saldo-wijziging naar Drupal.

- **Queue:** `frontend.payments`
- **Routing key:** `kassa.frontend.wallet`
- **Triggers:** badge-aankoop, top-up (Flow 13), badge-refund (Flow 15)

> **Veld is `wallet_balance`** — het volledige nieuwe saldo na de wijziging. Geen `change_amount` of `update_type` — Drupal berekent de delta zelf indien nodig.

#### XSD (conform Kassa schema_wallet_balance_update.xsd)

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
              <xs:element name="type"       type="xs:string" fixed="wallet_balance_update"/>
              <xs:element name="source"     type="xs:string" fixed="kassa"/>
              <xs:element name="timestamp"  type="xs:dateTime"/>
              <xs:element name="version"    type="xs:string" fixed="2.0"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
        <xs:element name="body">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="user_id"        type="xs:string"/>
              <!-- wallet_balance: het nieuwe saldo na de wijziging -->
              <xs:element name="wallet_balance">
                <xs:complexType>
                  <xs:simpleContent>
                    <xs:extension base="xs:decimal">
                      <xs:attribute name="currency" type="xs:string" fixed="eur" use="required"/>
                    </xs:extension>
                  </xs:simpleContent>
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
    <message_id>e54a8b72-1c2d-3e4f-5678-7a8b9c0d1e2f</message_id>
    <type>wallet_balance_update</type>
    <source>kassa</source>
    <timestamp>2026-05-15T20:30:00Z</timestamp>
    <version>2.0</version>
  </header>
  <body>
    <user_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user_id>
    <wallet_balance currency="eur">15.50</wallet_balance>
  </body>
</message>
```
### 6.9 `system_error` (Kassa → kassa.errors)

Kassa stuurt dit bij elk foutscenario. Monitoring ontvangt dit voor het dashboard. Dit bericht volgt het **globale formaat uit [Sectie 2.6](#26-global-system_error-format)**.

**Kassa-specifieke Error Codes:**

| Code | Wanneer |
|------|---------|
| `badge_not_found` | badge_id niet gevonden in Odoo |
| `odoo_api_error` | Odoo XML-RPC niet bereikbaar |
| `offline_queue_full` | outbox.json heeft limiet van 500 berichten bereikt |

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
  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id"    type="xs:string"/>
          <xs:element name="timestamp"     type="xs:dateTime"/>
          <xs:element name="source"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="planning"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="session_created"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="version"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="2.0"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="correlation_id" type="xs:string" minOccurs="0"/>
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
              <!-- user_id: de master_uuid van de Identity Service (indien spreker een gebruiker is) -->
              <xs:element name="user_id"      type="xs:string" minOccurs="0"/>
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
      <user_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user_id>
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
  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id"    type="xs:string"/>
          <xs:element name="timestamp"     type="xs:dateTime"/>
          <xs:element name="source"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="planning"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="session_updated"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="version"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="2.0"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="correlation_id" type="xs:string" minOccurs="0"/>
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
              <!-- user_id: de master_uuid van de Identity Service (indien spreker een gebruiker is) -->
              <xs:element name="user_id"      type="xs:string" minOccurs="0"/>
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
      <user_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user_id>
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
  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id" type="xs:string"/>
          <xs:element name="timestamp"  type="xs:dateTime"/>
          <xs:element name="source"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="planning"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="session_deleted"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="version"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="2.0"/></xs:restriction></xs:simpleType></xs:element>
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

- **Queue:** `facturatie.to.crm`

### 8.1 `invoice_status`

Facturatie meldt de nieuwe status van een factuur.

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="message">
    <xs:complexType><xs:sequence>
        <xs:element name="header">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="message_id" type="xs:string"/>
              <xs:element name="timestamp"  type="xs:dateTime"/>
              <xs:element name="source"     type="xs:string"/>
              <xs:element name="type"       type="xs:string"/>
              <xs:element name="version"    type="xs:string"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <xs:element name="invoice_id"  type="xs:string"/>
          <xs:element name="user_id"     type="xs:string"/>
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
              <xs:attribute name="currency" use="required">
                <xs:simpleType><xs:restriction base="xs:string">
                  <xs:enumeration value="eur"/></xs:restriction></xs:simpleType>
              </xs:attribute>
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
    <user_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user_id>
    <status>paid</status>
    <amount currency="eur">150.00</amount>
    <due_date>2026-06-15</due_date>
  </body>
</message>
```

---

### 8.2 `payment_registered`

Een betaling werd verwerkt in FossBilling.

#### XSD

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
          <xs:element name="invoice_id"    type="xs:string"/>
          <xs:element name="user_id"       type="xs:string"/>
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

#### Voorbeeld XML

```xml
<message>
  <header>
    <message_id>8fc6d7e8-f9a0-1234-cdef-234567800014</message_id>
    <timestamp>2026-05-15T18:30:00Z</timestamp>
    <source>facturatie</source>
    <type>payment_registered</type>
    <version>2.0</version>
  </header>
  <body>
    <invoice_id>foss-inv-00142</invoice_id>
    <user_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user_id>
    <amount_paid currency="eur">150.00</amount_paid>
    <payment_method>cash</payment_method>
    <paid_at>2026-05-15T18:29:00Z</paid_at>
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
  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id" type="xs:string"/>
          <xs:element name="timestamp"  type="xs:dateTime"/>
          <xs:element name="source"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="mailing"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="mailing_status"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="version"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="2.0"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="correlation_id" type="xs:string" minOccurs="0"/>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <xs:element name="campaign_id" type="xs:string"/>
          <xs:element name="subject"     type="xs:string"/>
          <xs:element name="sent"        type="xs:integer"/>
          <xs:element name="delivered"   type="xs:integer"/>
          <xs:element name="bounced"     type="xs:integer"/>
          <xs:element name="opened"      type="xs:integer"/>
          <!-- bounced_emails: optioneel maar sterk aanbevolen -->
          <!-- CRM gebruikt dit om ongeldige e-mailadressen te markeren in Salesforce -->
          <xs:element name="bounced_emails" minOccurs="0">
            <xs:complexType><xs:sequence>
              <xs:element name="email" type="xs:string" minOccurs="0" maxOccurs="unbounded"/>
            </xs:sequence></xs:complexType>
          </xs:element>
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
  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id" type="xs:string"/>
          <xs:element name="timestamp"  type="xs:dateTime"/>
          <xs:element name="source"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="crm"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="new_registration"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="version"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="2.0"/></xs:restriction></xs:simpleType></xs:element>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <xs:element name="customer">
            <xs:complexType><xs:sequence>
              <!-- user_id: de master_uuid van de Identity Service -->
              <xs:element name="user_id"         type="xs:string"/>
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
              <xs:element name="session_id"    type="xs:string"/>
              <!-- session_title: optioneel maar aanbevolen voor Kassa-display -->
              <xs:element name="session_title"  type="xs:string" minOccurs="0"/>
              <xs:element name="payment_due">
                <xs:complexType><xs:sequence>
                  <xs:element name="amount">
                    <xs:complexType><xs:simpleContent><xs:extension base="xs:decimal">
                      <xs:attribute name="currency" use="required">
                        <xs:simpleType><xs:restriction base="xs:string">
                          <xs:enumeration value="eur"/></xs:restriction></xs:simpleType>
                      </xs:attribute>
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
  </header>
  <body>
    <customer>
      <user_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user_id>
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
      <session_id>sess-keynote-001</session_id>
      <session_title>Keynote: AI in Healthcare</session_title>
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
  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id" type="xs:string"/>
          <xs:element name="timestamp"  type="xs:dateTime"/>
          <xs:element name="source"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="crm"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="profile_update"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="version"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="2.0"/></xs:restriction></xs:simpleType></xs:element>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <!-- user_id: de master_uuid van de Identity Service -->
          <xs:element name="user_id"         type="xs:string"/>
          <xs:element name="email"         type="xs:string"/>
          <xs:element name="date_of_birth" type="xs:date" minOccurs="0"/>
          <xs:element name="contact">
            <xs:complexType><xs:sequence>
              <xs:element name="first_name" type="xs:string"/>
              <xs:element name="last_name"  type="xs:string"/>
            </xs:sequence></xs:complexType>
          </xs:element>
          <xs:element name="company_name" type="xs:string" minOccurs="0"/>
          <xs:element name="vat_number"   type="xs:string" minOccurs="0"/>
          <xs:element name="company_id"   type="xs:string" minOccurs="0"/>
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
    <user_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user_id>
    <email>jan.peeters.nieuw@ehb.be</email>
    <contact>
      <first_name>Jan</first_name>
      <last_name>Peeters</last_name>
    </contact>
  </body>
</message>
```

---

### 10.3 `cancel_registration` (CRM → Kassa & Planning)

> **Gap Resolution (Mei 2026):** CRM stuurt dit bericht nu ook door naar Planning (via `calendar.exchange`) zodat `current_attendees` daar correct verlaagd kan worden bij een annulatie.

#### XSD

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
            <xs:enumeration value="crm"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="cancel_registration"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="version"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="2.0"/></xs:restriction></xs:simpleType></xs:element>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <xs:element name="user_id" type="xs:string"/>
          <xs:element name="session_id"  type="xs:string"/>
          <xs:element name="reason"      type="xs:string" minOccurs="0"/>
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
    <user_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user_id>
    <session_id>sess-keynote-001</session_id>
    <reason>Klant heeft zelf annulatie gevraagd</reason>
  </body>
</message>
```

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
      <!--  Gedocumenteerde uitzondering: geen <contact> wrapper hier -->
      <xs:element name="first_name"   type="xs:string"/>
      <xs:element name="last_name"    type="xs:string"/>
      <xs:element name="email"        type="xs:string"/>
      <xs:element name="address"      type="AddressType"/>
      <xs:element name="company_name" type="xs:string" minOccurs="0"/>
      <xs:element name="vat_number"   type="xs:string" minOccurs="0"/>
    </xs:sequence>
  </xs:complexType>

  <xs:element name="message">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="header">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="message_id"     type="xs:string"/>
              <xs:element name="type"           type="xs:string" fixed="invoice_request"/>
              <xs:element name="source"         type="xs:string" fixed="crm"/>
              <xs:element name="timestamp"      type="xs:dateTime"/>
              <xs:element name="version"        type="xs:string" fixed="2.0"/>
              <!-- correlation_id = message_id van de bijhorende consumption_order (zie 11.3) -->
              <xs:element name="correlation_id" type="xs:string"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
        <xs:element name="body">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="user_id"      type="xs:string"/>
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
    <type>invoice_request</type>
    <source>crm</source>
    <timestamp>2026-05-16T08:00:00Z</timestamp>
    <version>2.0</version>
    <!-- correlation_id matcht de message_id van de consumption_order -->
    <correlation_id>f47ac10b-58cc-4372-a567-0e02b2c3d479</correlation_id>
  </header>
  <body>
    <user_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user_id>
    <invoice_data>
      <first_name>Jan</first_name>
      <last_name>Peeters</last_name>
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

#### XSD

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
            <xs:enumeration value="crm"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="invoice_cancelled"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="version"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="2.0"/></xs:restriction></xs:simpleType></xs:element>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <xs:element name="invoice_id"  type="xs:string"/>
          <xs:element name="user_id" type="xs:string"/>
          <xs:element name="reason"      type="xs:string" minOccurs="0"/>
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
    <message_id>e5c2d3e4-f5a6-7890-cdef-890123400020</message_id>
    <timestamp>2026-05-10T14:01:00Z</timestamp>
    <source>crm</source>
    <type>invoice_cancelled</type>
    <version>2.0</version>
  </header>
  <body>
    <invoice_id>foss-inv-00142</invoice_id>
    <user_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user_id>
    <reason>Inschrijving geannuleerd door klant</reason>
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

### 11.4 `payment_registered` (CRM → Facturatie) — Passthrough

Wanneer Kassa een `payment_registered` stuurt naar `crm.incoming` (routing: `kassa.payments.registration`), geeft CRM dit **1-op-1 door** naar `facturatie.incoming`. Facturatie zet de factuurstatus in FossBilling op `paid`.

> **Bewijs:** Facturatie user story 8: *"betalingsbericht ontvangen van CRM wanneer deelnemer inschrijving aan kassa betaalt → factuurstatus onmiddellijk op 'betaald'"*
>
> **transaction_id in FossBilling:** FossBilling kan vragen om een `transaction_id`. Dit is de `message_id` van het doorgestuurde `payment_registered` bericht (Facturatie user story 10 noot).

**XSD & XML:** Zie Sectie 6.6 — exact identiek, enkel `source` wijzigt niet (blijft `kassa`), CRM voegt geen velden toe.


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
  <xs:element name="message">
    <xs:complexType><xs:sequence>
      <xs:element name="header">
        <xs:complexType><xs:sequence>
          <xs:element name="message_id" type="xs:string"/>
          <xs:element name="timestamp"  type="xs:dateTime"/>
          <xs:element name="source"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="crm"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="type"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="send_mailing"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="version"><xs:simpleType><xs:restriction base="xs:string">
            <xs:enumeration value="2.0"/></xs:restriction></xs:simpleType></xs:element>
          <xs:element name="correlation_id" type="xs:string"/>
        </xs:sequence></xs:complexType>
      </xs:element>
      <xs:element name="body">
        <xs:complexType><xs:sequence>
          <xs:element name="campaign_id" type="xs:string"/>
          <xs:element name="subject"     type="xs:string"/>
          <xs:element name="template_id" type="xs:string"/>
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
                  <xs:element name="email"       type="xs:string"/>
                  <xs:element name="user_id"     type="xs:string"/>
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
    <template_id>tmpl-registration-confirm</template_id>
    <mail_type>registration_confirmation</mail_type>
    <recipients>
      <recipient>
        <email>jan.peeters@ehb.be</email>
        <user_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user_id>
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

- **Queue:** `crm.to.mailing` (zelfde queue als CRM, Mailing behandelt beide)
- Facturatie gebruikt **hetzelfde `send_mailing` formaat** als CRM, met `source: facturatie`

### 13.1 `send_mailing` (Facturatie → Mailing)

> **Voor Mailing-team:** jullie consumer moet berichten met `source=facturatie` én `source=crm` verwerken. Het `type` is in beide gevallen `send_mailing`.

#### Voorbeeld XML — factuur klaar

```xml
<message>
  <header>
    <message_id>07e4f5a6-b7c8-9012-efab-012345600022</message_id>
    <timestamp>2026-05-16T09:05:00Z</timestamp>
    <source>facturatie</source>
    <type>send_mailing</type>
    <version>2.0</version>
    <correlation_id>d4e5f6a7-b8c9-0123-defa-123456789003</correlation_id>
  </header>
  <body>
    <campaign_id>sg-invoice-00142</campaign_id>
    <subject>Uw factuur voor Shiftfestival 2026</subject>
    <template_id>tmpl-invoice-ready</template_id>
    <mail_type>invoice_ready</mail_type>
    <recipients>
      <recipient>
        <email>jan.peeters@ehb.be</email>
        <user_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user_id>
        <contact>
          <first_name>Jan</first_name>
          <last_name>Peeters</last_name>
        </contact>
      </recipient>
    </recipients>
    <template_data>{"invoice_id":"foss-inv-00142","amount":"31.50","currency":"eur","due_date":"2026-06-15"}</template_data>
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
  <!--
    TYPE   : payment_registered
    FLOW   : CRM → Frontend  (queue: frontend.incoming)
    VERSIE : 2.0
    Frontend's PaymentRegisteredReceiver.php luistert op deze queue
    en updatet de betaalstatus van de gebruiker in Drupal.
  -->
  <xs:element name="message">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="header">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="message_id" type="xs:string"/>
              <xs:element name="type"       type="xs:string" fixed="payment_registered"/>
              <xs:element name="source"     type="xs:string" fixed="crm"/>
              <xs:element name="timestamp"  type="xs:dateTime"/>
              <xs:element name="version"    type="xs:string" fixed="2.0"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
        <xs:element name="body">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="user_id" type="xs:string"/>
              <xs:element name="invoice">
                <xs:complexType>
                  <xs:sequence>
                    <xs:element name="id" type="xs:string"/>
                    <xs:element name="amount_paid">
                      <xs:complexType>
                        <xs:simpleContent>
                          <xs:extension base="xs:decimal">
                            <xs:attribute name="currency" type="xs:string" use="required"/>
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
    <type>payment_registered</type>
    <source>crm</source>
    <timestamp>2026-05-15T22:00:00Z</timestamp>
    <version>2.0</version>
  </header>
  <body>
    <user_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user_id>
    <invoice>
      <id>INV-2026-001</id>
      <amount_paid currency="eur">150.00</amount_paid>
      <status>paid</status>
    </invoice>
    <payment_context>online_invoice</payment_context>
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
    LET OP : Geen <message><header> wrapper — dit is een platte RPC structuur
    AMQP   : Stel reply_to, correlation_id, message_id en timestamp in als message properties
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
| Kassa | CRM | `crm.incoming` | exchange: `kassa.exchange`, routing: `kassa.payments.consumption` / `registration` / `refund` / `invoice` / `badge` |
| Planning | CRM | `planning.session.events` | exchange: `planning.exchange`, routing: `planning.session.*` |
| Facturatie | CRM | `facturatie.to.crm` | — |
| Mailing | CRM | `crm.incoming` | — |
| CRM | Kassa | `kassa.incoming` | exchange: `kassa.exchange` (topic) |
| CRM | Facturatie | `facturatie.incoming` | — |
| CRM | Mailing | `crm.to.mailing` | — |
| CRM | Planning | `planning.calendar.invite` | exchange: `calendar.exchange`, routing: `crm.to.planning.cancel_registration` |
| Facturatie | Mailing | `facturatie.to.mailing` | — |
| Monitoring | Mailing | `monitoring.alerts` | — |
| Alle teams | Monitoring | `heartbeat` | — |
| Frontend/CRM | Planning | `planning.calendar.invite` | exchange: `calendar.exchange`, routing: `frontend.to.planning.calendar.invite` |
| Planning | Frontend | reply_to queue (RPC) | exchange: `calendar.exchange`, routing: `planning.to.frontend.calendar.invite.confirmed` |
| Frontend/CRM | Planning | `planning.session.events` | exchange: `planning.exchange`, routing: `frontend.to.planning.session.view` (RPC) |
| Planning | Frontend | reply_to queue (RPC) | exchange: `planning.exchange`, routing: `planning.to.frontend.session.view.response` |
| Frontend | Planning | `planning.session.events` | exchange: `planning.exchange`, routing: `frontend.to.planning.session.create` / `update` / `delete` |
| Planning | Frontend | — | exchange: `planning.exchange`, routing: `planning.to.frontend.session.created` / `updated` / `deleted` |
| Alle teams | Identity | `identity.user.create.request` | RPC |
| Alle teams | Identity | `identity.user.lookup.email.request` | RPC |
| Identity | Alle teams | fanout via `user.events` exchange | — |

---

## 17. Per-Team Samenvatting

### Team Frontend

| Richting | Type | Queue / Exchange / Routing |
|----------|------|---------------------------|
| ← CRM | `payment_registered` | `frontend.incoming` (aan te maken) |
| ← Kassa | `payment_status` | `frontend.payments` (routing: `kassa.frontend.payment`) |
| ← Kassa | `wallet_balance_update` | `frontend.payments` (routing: `kassa.frontend.wallet`) |
| ← CRM/Facturatie | `vat_validation_error` | `frontend.incoming` |
| → Planning | `calendar_invite` | exchange: `calendar.exchange`, routing: `frontend.to.planning.calendar.invite` |
| ← Planning | `calendar_invite_confirmed` | reply_to queue, routing: `planning.to.frontend.calendar.invite.confirmed` |
| → Planning | `session_view_request` | exchange: `planning.exchange`, routing: `frontend.to.planning.session.view` (RPC) |
| ← Planning | `session_view_response` | reply_to queue, routing: `planning.to.frontend.session.view.response` |
| → Planning | `session_create_request` | exchange: `planning.exchange`, routing: `frontend.to.planning.session.create` |
| → Planning | `session_update_request` | exchange: `planning.exchange`, routing: `frontend.to.planning.session.update` |
| → Planning | `session_delete_request` | exchange: `planning.exchange`, routing: `frontend.to.planning.session.delete` |
| ← Planning | `session_created` | exchange: `planning.exchange`, routing: `planning.to.frontend.session.created` |
| ← Planning | `session_updated` | exchange: `planning.exchange`, routing: `planning.to.frontend.session.updated` |
| ← Planning | `session_deleted` | exchange: `planning.exchange`, routing: `planning.to.frontend.session.deleted` |
| → CRM | `user_deleted` | `crm.incoming` |
| → CRM | `cancel_registration` | `crm.incoming` |
| → CRM | `user_checkin` | `crm.incoming` |

**Verplichte registratie-volgorde:**
1. Stuur RPC naar `identity.user.create.request` met e-mailadres
2. Wacht op `identity_response` → haal `master_uuid` op
3. Pas dán stuur je `new_registration` naar CRM met die `master_uuid`

**Actiepunten (v2.3 audit — KRITIEK):**

>  Deze hele lijst is een directe consequentie van de scan. Niets is "optioneel" — alles is fout in de huidige code.

PHP senders die volledig moeten gemigreerd worden naar de v2.0 header:
- [ ] `UserUnregisteredSender.php` — type `user.unregistered` → `user_deleted`, xmlns weg, `<receiver>` weg, `version=2.0`, geen `<master_uuid>`
- [ ] `UserCreatedSender.php` — type `user.created` → `user_created`, idem header-migratie
- [ ] `UserRegisteredSender.php` — type `user.registered` → `user_registered`, idem header-migratie
- [ ] `UserUpdatedSender.php` — type `user.updated` → `user_updated`, idem header-migratie
- [ ] `UserCheckinSender.php` — type `user.checkin` → `user_checkin`, idem + voeg `<session_id>` body toe (sectie 21.1)
- [ ] `CalendarInviteSender.php` — type `calendar.invite` → `calendar_invite`, voeg `<version>2.0</version>` toe (was afwezig!), voeg `<attendee_email>` toe in body (sectie 17.2)
- [ ] `NewRegistrationSender.php` — verwijder `<master_uuid>` uit header, vervang `<age>` door `<date_of_birth>`, namen in `<contact>` wrapper (sectie 5.1)

Receivers:
- [ ] `SessionUpdateReceiver.php` — accepteer `session_updated` als type-waarde (niet `session_update`)

Nieuwe functionaliteit (uit v2.0):
- [ ] `<payment_due currency="eur">` meesturen bij `new_registration` (0.00 bij gratis sessie, sectie 5.1)
- [ ] Identity RPC implementeren vóór CRM-call bij elke registratie (sectie 15.6)
- [ ] Bind queue aan `user.events` exchange voor fanout van Identity Service

---

### Team Kassa (Odoo POS)

| Richting | Type | Queue / Routing key |
|----------|------|---------------------|
| → CRM | `consumption_order` | `kassa.payments.consumption` |
| → CRM | `payment_registered` | `kassa.payments.consumption` of `kassa.payments.registration` |
| → CRM | `badge_assigned` | `kassa.payments.badge` |
| → CRM | `badge_scanned` | `kassa.payments.consumption` |
| → CRM | `refund_processed` | `kassa.payments.refund` |
| → CRM | `invoice_request` | `kassa.payments.invoice` |
| → Frontend | `payment_status` | `frontend.payments` (routing: `kassa.frontend.payment`) |
| → Frontend | `wallet_balance_update` | `frontend.payments` (routing: `kassa.frontend.wallet`) |
| → kassa.errors | `system_error` | `kassa.errors` |
| ← CRM | `new_registration` | `kassa.incoming` |
| ← CRM | `profile_update` | `kassa.incoming` |
| ← CRM | `cancel_registration` | `kassa.incoming` |

**Status v2.3 audit:  CONFORM — Geen wijzigingen vereist!**

Kassa's `XML_Structuren_Kassa.md` v2.5 voldoet volledig aan dit contract. De hieronder vermelde actiepunten zijn historische items uit v2.0 die ondertussen allemaal zijn afgewerkt — ze blijven hier voor referentie.

**Historische actiepunten (afgewerkt):**
- [x] `<age>` verwijderen — leeftijd lokaal berekenen via `date_of_birth`
- [x] `currency="eur"` attribuut op alle bedragen
- [x] `refund_processed`: `correlation_id` = message_id originele `payment_registered` (UUID)
- [x] `refund_processed`: `payment_method` = `cash` of `card_reversal` (nooit `badge_wallet`)
- [x] `payment_registered` sturen na elke kassatransactie (routing: consumption/registration)
- [x] `payment_status` sturen naar `frontend.payments` na inschrijvingsbetaling
- [x] `wallet_balance_update` sturen naar `frontend.payments` bij badge saldo-wijziging
- [x] `system_error` sturen naar `kassa.errors` bij elk foutscenario
- [x] `new_registration` (CRM→Kassa): `type`, `company_name`, `vat_number`, `payment_due.status` verwerken
- [x] `profile_update` (CRM→Kassa): `company_name`, `vat_number`, `payment_due` verwerken
- [x] `<session_title>` uitlezen voor display op Kassa-scherm
- [x] `version` → `"2.0"`, geen `<receiver>`

**Resterende actie:**
- [ ] Luisteren op `user.events` fanout exchange voor nieuwe gebruikers (Identity flow)
---

### Team Planning (Office365 / Outlook)
| Richting | Type | Exchange / Queue / Routing key |
|----------|------|--------------------------------|
| → CRM | `session_created` | exchange: `planning.exchange`, routing: `planning.session.created` |
| → CRM | `session_updated` | exchange: `planning.exchange`, routing: `planning.session.updated` |
| → CRM | `session_deleted` | exchange: `planning.exchange`, routing: `planning.session.deleted` |
| → Frontend | `session_created` | exchange: `planning.exchange`, routing: `planning.to.frontend.session.created` |
| → Frontend | `session_updated` | exchange: `planning.exchange`, routing: `planning.to.frontend.session.updated` |
| → Frontend | `session_deleted` | exchange: `planning.exchange`, routing: `planning.to.frontend.session.deleted` |
| ← Frontend/CRM | `calendar_invite` | exchange: `calendar.exchange`, routing: `frontend.to.planning.calendar.invite` |
| → Frontend | `calendar_invite_confirmed` | reply_to queue, routing: `planning.to.frontend.calendar.invite.confirmed` |
| ← Frontend/CRM | `session_view_request` | exchange: `planning.exchange`, routing: `frontend.to.planning.session.view` (RPC) |
| → Frontend | `session_view_response` | reply_to queue, routing: `planning.to.frontend.session.view.response` |
| ← Frontend | `session_create_request` | exchange: `planning.exchange`, routing: `frontend.to.planning.session.create` |
| ← Frontend | `session_update_request` | exchange: `planning.exchange`, routing: `frontend.to.planning.session.update` |
| ← Frontend | `session_delete_request` | exchange: `planning.exchange`, routing: `frontend.to.planning.session.delete` |
| ← CRM | `cancel_registration` | exchange: `calendar.exchange`, routing: `crm.to.planning.cancel_registration` |

**Status v2.3 audit:  VOLLEDIG CONFORM (Mei 2026 update) **

Planning heeft alle resterende afwijkingen weggewerkt en de XSD-validatie volledig conform v2.0 gemaakt. Tevens is de gap in de annulatie-flow gedicht via Option A (forwarding door CRM).

**Afgewerkte actiepunten (Mei 2026):**
- [x] **XSD's**: Alle 7 XSD's in `/xsd/` folder gemigreerd naar v2.0 (geen namespaces, `xs:dateTime`, snake_case types).
- [x] `calendar_invite.xsd`: `attendee_email` verplicht toegevoegd.
- [x] **Heartbeat**: Broadcaster actief op queue `heartbeat`.
- [x] **Annulatie Flow**: Handler geïmplementeerd voor `cancel_registration` (inkomend van CRM) om `current_attendees` te verlagen.

**Routing/runtime:**
- [x] Session events worden nu gepubliceerd op beide routing keys: `planning.session.*` (CRM) én `planning.to.frontend.session.*` (Frontend).
- [x] Luistert op `planning.calendar.invite` queue voor inkomende kalenderverzoeken.
- [x] Luistert op `calendar.exchange` voor `cancel_registration` berichten geforward door CRM.
---

### Team Facturatie (FossBilling)
| Richting | Type | Queue |
|----------|------|-------|
| ← CRM | `invoice_request` | `facturatie.incoming` |
| ← CRM | `invoice_cancelled` | `facturatie.incoming` |
| ← CRM | `consumption_order` (passthrough) | `facturatie.incoming` |
| ← CRM | `payment_registered` (passthrough) | `facturatie.incoming` |
| → CRM | `invoice_status` | `facturatie.to.crm` |
| → CRM | `payment_registered` | `facturatie.to.crm` |
| → Mailing | `send_mailing` | `facturatie.to.mailing` |

**Status v2.3 audit:  KRITIEKE XSD'S MOETEN VERVANGEN WORDEN**

Meerdere XSD's bevatten verboden velden of fundamenteel verkeerde structuur. Dit blokkeert een correcte data-uitwisseling met CRM en Mailing.

**Actiepunten (v2.3 audit — KRITIEK):**

XSD-bestanden volledig vervangen:
- [ ] **`invoice_request.xsd`**: vervang volledig met de XSD uit sectie 11.1 — verwijder `<items>`, `<customer>` body, `<master_uuid>` header. Gebruik `<invoice_data>` body en maak `<correlation_id>` verplicht in header.
- [ ] **`new_registration.xsd`**: voeg `<contact>` wrapper toe rond `first_name`/`last_name`, verwijder `<master_uuid>` uit header, voeg `<vat_number>`, `<company_name>`, `<payment_due>` toe (sectie 5.1 + 10.1)
- [ ] **`invoice_created_notification` schema**: `xs:schema xmlns=""` → `xmlns:xs="http://www.w3.org/2001/XMLSchema"` (huidige is broken), `<version>1.0</version>` → `<version>2.0</version>`
- [ ] **`payment_registered.xsd`**: verwijder `<master_uuid>` uit header (sectie 8.2)

Outbound types:
- [ ] Type voor "factuur klaar" Facturatie → CRM: `send_invoice` → `invoice_status` (sectie 8.1)

Queue & validatie:
- [ ] Listener queue `crm.to.facturatie` → `facturatie.incoming` (sectie 11)
- [ ] `currency="eur"` attribuut op ALLE bedragen waar dat nog ontbreekt
- [ ] Eigen XSD-validatie in receiver: faal → `crm.dead-letter` queue
- [ ] `send_mailing` consumer implementeren — Facturatie → Mailing flow ontbreekt nog volledig (sectie 13)
- [ ] Bind queue aan `user.events` exchange voor Identity fanout (sectie 15.5)

---

### Team Mailing (SendGrid)
| Richting | Type | Queue |
|----------|------|-------|
| ← CRM | `send_mailing` | `crm.to.mailing` |
| ← Facturatie | `send_mailing` | `facturatie.to.mailing` |
| ← Monitoring | `system_alert` | `monitoring.alerts` |
| → CRM | `mailing_status` | `crm.incoming` |

**Actiepunten:**  
1. **`alert.xsd` vervangen** door het nieuwe `system_alert` formaat met `<message>` wrapper  
2. **`send_mailing` consumer implementeren** — dit ontbreekt momenteel volledig  
3. **`<source>` tag** — huidig `<s>` in jullie alert.xsd hernoemen naar `<source>` in het `<body>` blok van het nieuwe `system_alert` formaat  
4. Na verzending altijd een `mailing_status` terugsturen naar CRM met `correlation_id`  

---

### Team Monitoring (ELK Stack)
| Richting | Type | Queue |
|----------|------|-------|
| ← Alle teams | `heartbeat` | `heartbeat` |
| → Mailing | `system_alert` | `monitoring.alerts` |

**Status v2.3 audit:  ALERT-FORMAAT MIGREREN + Heartbeat-service herwerken**

**Actiepunten (v2.3 audit):**
- [ ] **VERVANG `alert.xsd`** met de XSD uit sectie 4 (`type=system_alert`, standaard `<message>` envelop)
- [ ] Logstash heartbeat-parser bijwerken: bron lezen uit `header.source` i.p.v. body `<system>`
- [ ] **`heartbeat`-service repo** (`IntegrationProject-Groep1/heartbeat`): volledige herwrite van XML-builder — zie sectie 3 (vervang platte `<heartbeat>` root door `<message>` envelop)
- [ ] Heartbeat consumer aanpassen aan nieuwe envelop-structuur

---

### Team CRM (Salesforce)
CRM is de centrale data-hub. Zie secties 5–13 voor alle flows.

**Status v2.3 audit:  KRITIEKE AFWIJKINGEN — directe actie vereist**

CRM is technisch goed opgezet (Node.js + jsforce + amqplib + fast-xml-parser + xmlbuilder2) maar heeft enkele duidelijke afwijkingen van het contract die nu opgelost moeten worden.

**Wat al correct is:**
-  `src/heartbeat.js` gebruikt al de standaard `<message>` envelop
-  XSD-validatie en `crm.dead-letter` voor falende berichten
-  Header zonder `<receiver>` en `xmlns`

**Actiepunten (v2.3 audit — KRITIEK):**

`src/receiver.js`:
- [ ] Hernoem case `'session_update'` → `'session_updated'` in de switch-statement (sectie 7.2)
- [ ] Bind `planning.session.events` queue correct aan `planning.exchange` topic exchange
- [ ] `user_checkin` handler implementeren (sectie 21.1) — opslaan als aanwezigheid in Salesforce

`src/sender.js`:
- [ ] `buildNewRegistrationXml()` (CRM → Kassa): verwijder `<age>`, voeg `<date_of_birth>` toe vanuit `crm_user_sync.date_of_birth` (sectie 10.1)
- [ ] `buildInvoiceRequestXml()` (CRM → Facturatie): vervang body volledig — `<user_id>` + `<invoice_data>`, GEEN `<items>`, GEEN `<master_uuid>` in header, `<correlation_id>` verplicht (sectie 11.1)
- [ ] `sendInvoiceRequest()`: queue parameter `'crm.to.facturatie'` → `'facturatie.incoming'`
- [ ] `buildMailingSendXml()`: type `mailing_status` → `send_mailing` (sectie 12.1)
- [ ] `consumption_order` 1-op-1 doorgeven naar `facturatie.incoming` (passthrough, sectie 11.3)
- [ ] `payment_registered` (Kassa registration) doorgeven naar `facturatie.incoming` (passthrough, sectie 11.4)
- [ ] `payment_registered` sturen naar `frontend.incoming` na betalingsbevestiging (sectie 14)
- [ ] `cancel_registration` forwarden naar `calendar.exchange` (routing: `crm.to.planning.cancel_registration`) voor Team Planning (Mei 2026 update)
- [ ] `vat_validation_error` sturen naar `frontend.incoming` bij ongeldig BTW-nr (sectie 20)

Tests:
- [ ] `tests/sender.test.js` bijwerken zodat alle nieuwe schema's correct gevalideerd worden

Salesforce / data:
- [ ] `master_uuid` opslaan als extern veld in Salesforce Contact (van Identity fanout, sectie 15.5)
- [ ] Bind queue aan `user.events` fanout exchange

---

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

### 17.0 OAuth Token Registration (REST API)

Voordat gebruikers hun kalender kunnen synchroniseren, moet elke gebruiker na het inloggen eenmalig zijn OAuth-tokens registreren bij de Planning Service.

- **Endpoint:** `POST http://<planning-service-host>:30050/api/tokens`
- **Auth:** `Authorization: Bearer <API_TOKEN_SECRET>`
- **Content-Type:** `application/json`

**Request Body:**
```json
{
  "user_id":       "user-uuid-123",
  "access_token":  "eyJ...",
  "refresh_token": "0.A...",
  "expires_in":    3600
}
```

| Veld | Verplicht | Beschrijving |
|------|-----------|--------------|
| `user_id` | ✅ | Master UUID van de gebruiker (moet matchen met `calendar_invite`) |
| `access_token` | ✅ | Microsoft OAuth access token |
| `refresh_token` | ✅ | Microsoft OAuth refresh token |
| `expires_in` | ❌ | Seconden tot verloop (default: 3600) |

**Response:**
```json
{ "status": "ok", "user_id": "user-uuid-123" }
```

> **Security Note:** Tokens worden encrypted at rest (Fernet) opgeslagen. Planning refresht ze automatisch.

---

### 17.1 `session_view_request` / `session_view_response` (RPC)

Frontend vraagt sessiedetails op bij Planning. Planning antwoordt synchroon via het RPC-patroon.

- **Request exchange:** `planning.exchange`
- **Request routing key:** `frontend.to.planning.session.view`
- **Response exchange:** `planning.exchange`
- **Response routing key:** `planning.to.frontend.session.view.response` (op reply_to queue)

#### XSD — Request

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
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
                  <xs:enumeration value="session_view_request"/>
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
  <xs:element name="message">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="header">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="message_id"     type="xs:string"/>
              <xs:element name="timestamp"      type="xs:dateTime"/>
              <xs:element name="source"         type="xs:string" fixed="planning"/>
              <xs:element name="type"           type="xs:string" fixed="session_view_response"/>
              <xs:element name="version"        type="xs:string" fixed="2.0"/>
              <xs:element name="correlation_id" type="xs:string" minOccurs="0"/>
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
                          <xs:element name="speaker" minOccurs="0">
                            <xs:complexType>
                              <xs:sequence>
                                <xs:element name="user_id"      type="xs:string"/>
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

#### Voorbeeld XML — Request

```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>a1b2c3d4-e5f6-7890-abcd-ef1234567890</message_id>
    <timestamp>2026-05-15T09:00:00Z</timestamp>
    <source>frontend</source>
    <type>session_view_request</type>
    <version>2.0</version>
    <correlation_id>frontend-req-001</correlation_id>
  </header>
  <body>
    <session_id>sess-keynote-001</session_id>
  </body>
</message>
```

#### Voorbeeld XML — Response

```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>
  <header>
    <message_id>b2c3d4e5-f6a7-8901-bcde-f12345678901</message_id>
    <timestamp>2026-05-15T09:00:01Z</timestamp>
    <source>planning</source>
    <type>session_view_response</type>
    <version>2.0</version>
    <correlation_id>frontend-req-001</correlation_id>
  </header>
  <body>
    <request_message_id>a1b2c3d4-e5f6-7890-abcd-ef1234567890</request_message_id>
    <requested_session_id>sess-keynote-001</requested_session_id>
    <status>ok</status>   <!-- ok | not_found -->
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
        <current_attendees>87</current_attendees>
        <speaker>
          <user_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user_id>
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

---

### 17.2 `calendar_invite` / `calendar_invite_confirmed`

Frontend vraagt Planning om een Office365/Outlook kalenderafspraak aan te maken voor een ingeschreven gebruiker.

- **Invite exchange:** `calendar.exchange`
- **Invite routing key:** `frontend.to.planning.calendar.invite`
- **Confirmed exchange:** `calendar.exchange`
- **Confirmed routing key:** `planning.to.frontend.calendar.invite.confirmed` (op reply_to queue)

#### XSD — calendar_invite (Frontend → Planning)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
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
              <!-- user_id: de master_uuid van de Identity Service -->
              <xs:element name="user_id"        type="xs:string"/>
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
    <user_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user_id>
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

### 17.3 `session_create_request` (Frontend → Planning)

Wanneer een administrator in Drupal een nieuwe sessie aanmaakt.

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
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

### 17.4 `session_update_request` (Frontend → Planning)

Wanneer een administrator in Drupal een bestaande sessie wijzigt.

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
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
  </body>
</message>
```

---

### 17.5 `session_delete_request` (Frontend → Planning)

Wanneer een administrator in Drupal een sessie verwijdert.

#### XSD

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
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

## 20. CRM / Facturatie → Frontend: BTW Validatiefout

- **Queue:** `frontend.incoming`
- **Wanneer:** BTW-nummer is ongeldig bij registratie of factuuraanvraag

> ** Kritieke fix t.o.v. v1.0 codebase:**
> De originele developer had `<header minOccurs="0">` gemaakt als workaround.
> Dit is een **anti-pattern dat Regel 1 breekt**. De header is nu **verplicht**.
> CRM en Facturatie moeten de header altijd meesturen — ze kenden dit schema al.

### 18.1 `vat_validation_error`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="message">
    <xs:complexType>
      <xs:sequence>
        <!-- header VERPLICHT — geen minOccurs="0" zoals in v1.0 -->
        <xs:element name="header">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="message_id" type="xs:string"/>
              <xs:element name="timestamp"  type="xs:dateTime"/>
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
              <xs:element name="correlation_id" type="xs:string" minOccurs="0"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
        <xs:element name="body">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="user_id"       type="xs:string"/>
              <xs:element name="vat_number"    type="xs:string"/>
              <xs:element name="error_message" type="xs:string" minOccurs="0"/>
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
    <user_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user_id>
    <vat_number>BE0000000000</vat_number>
    <error_message>BTW-nummer BE0000000000 bestaat niet in de VIES-databank</error_message>
  </body>
</message>
```

---

## 21. Frontend / Kassa → CRM + Monitoring: Check-in

- **Queue:** `crm.incoming`
- **Wanneer:** bezoeker incheckt via badge-scan aan de inkom

> ** Fixes t.o.v. v1.0 codebase:**
> `xmlns`, `targetNamespace` verwijderd.
> `<receiver>` tag **verwijderd** (breekt Regel 1!).
> `version`: `"1.0"` → `"2.0"`.
> Type: `user.checkin` → `user_checkin` (snake_case, Regel 1).
> `session_id` toegevoegd (optioneel — voor opkomst per spreker tracking door Monitoring).
> `checkin_at` hernoemd van `timestamp` (was dubbelop met header.timestamp).

### 21.1 `user_checkin`

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
              <xs:element name="correlation_id" type="xs:string" minOccurs="0"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
        <xs:element name="body">
          <xs:complexType>
            <xs:sequence>
              <xs:element name="user_id"    type="xs:string"/>
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
    <user_id>e8b27c1d-4f2a-4b3e-9c5f-123456789abc</user_id>
    <badge_id>BADGE-0042</badge_id>
    <session_id>sess-keynote-001</session_id>
    <checkin_at>2026-05-15T13:58:00Z</checkin_at>
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
12. **CRM**: implementeer passthrough voor `consumption_order` en `payment_registered` naar `facturatie.incoming`
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
                                                                              
  <user_id>                                  <user_id>                      
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
<!-- Body moet worden: -->
<body>
  <user_id>{uuid}</user_id>
  <invoice_data>
    <first_name>...</first_name>  <!-- GEEN <contact> wrapper hier — gedocumenteerde uitzondering -->
    <last_name>...</last_name>
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
     XML_XSD_Contract_v2.3.md   ← dit document
```

Elk team voegt dan dit als git-submodule toe en valideert inkomende berichten tegen de shared XSD. Zo is het contract machine-leesbaar én mensleesbaar.

---

## 26. Final Rule

> **Als twee teams hetzelfde bericht anders interpreteren, is het contract fout.**

Niet het team.
Maak een issue aan op GitHub en update dit document.

Maar: dit document IS nu de canonieke bron. Zolang er geen issue + update geweest is, geldt deze versie.

---

*Document v2.3 — Gegenereerd op basis van volledige repo-audit + bestaande v2.0 contract — April 2026*
*Volgende geplande revisie: na demo 3 — toevoegen of aanpassen via Pull Request*

