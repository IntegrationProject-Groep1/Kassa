# Uitgewerkte User Stories

Team KassaModule (Odoo POS)

Versie: Definitief (Technische Revisie)

Project: Integratieproject Desideriushogeschool 2026

Datum: 25 maart 2026

## **EPIC 1: PROFIELEN & INSCHRIJVINGEN (INKOMENDE FLOWS)**

## **Story 1: Nieuwe Inschrijvingen automatisch inladen**

> _MVP status: MVP_

_Als kassamedewerker wil ik dat nieuwe inschrijvingen vanuit de website automatisch in mijn kassasysteem verschijnen, zodat ik bezoekers bij aankomst direct kan opzoeken zonder hun gegevens handmatig te hoeven overtypen._

**ACCEPTATIECRITERIA:**

- Het receiver.py script luistert op de achtergrond naar new_registration berichten vanuit het CRM via de RabbitMQ kassa.incoming.
- Elk inkomend bericht wordt gevalideerd tegen het XSD-schema. Is het bericht ongeldig? Dan wordt een system_error verstuurd naar kassa.errors en wordt het bericht met basic_nack(requeue=false) naar de DLQ afgevoerd.
- De kassa controleert via het unieke x_user_id of de klant al bestaat. Bestaat hij? Update zijn gegevens. Bestaat hij niet? Maak een nieuw profiel aan met alle gegevens uit het bericht (naam, e-mail, geboortedatum (date_of_birth), optioneel bedrijfsnaam en BTW-nummer).
- Na succesvolle verwerking wordt een basic_ack gestuurd naar RabbitMQ zodat het bericht niet opnieuw aangeboden wordt.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat receiver.py verbonden is met RabbitMQ op kassa.incoming

**En** er een geldig new_registration XML-bericht binnenkomt met identity_uuid, email, first_name, last_name (via het contact-element), date_of_birth en optioneel company_name en vat_number

**En** er bestaat nog geen klant in Odoo met dit x_user_id

**Wanneer** receiver.py het bericht verwerkt

**Dan** wordt er een nieuw klantprofiel aangemaakt in Odoo (res.partner) met alle velden correct ingevuld

**En** stuurt receiver.py een basic_ack naar RabbitMQ

**Gegeven** dat hetzelfde bericht binnenkomt maar de klant al bestaat in Odoo

**Wanneer** receiver.py het bericht verwerkt

**Dan** worden de bestaande gegevens overschreven — er wordt geen duplicaat aangemaakt

**Gegeven** dat een bericht binnenkomt dat niet voldoet aan schema_new_registration.xsd

**Wanneer** receiver.py de XSD-validatie uitvoert

**Dan** wordt een system_error met code invalid_xml_format verstuurd naar kassa.errors

**En** wordt het bericht met basic_nack(requeue=false) naar de DLQ afgevoerd

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1. Zorg dat het ontvangstscript continu luistert op de inkomende wachtrij voor nieuwe berichten.
2. Controleer via de interne `message_id`-cache (OrderedDict, max 10.000 items) of het bericht al eerder verwerkt is. Zo ja, stuur direct `basic_ack` en stop verdere verwerking (zie Story 15).
3. Controleer elk binnenkomend bericht op de correcte structuur via het bijhorende XSD-schema. Is het bericht fout? Stuur een foutmelding naar de Controlroom en stuur het bericht via `basic_nack(requeue=false)` naar de DLQ.
4. Zoek de klant op in Odoo via zijn uniek klantnummer. Bestaat hij al? Update zijn gegevens. Bestaat hij nog niet? Maak een nieuw profiel aan met alle gegevens uit het bericht. Let op: `<type>private|company</type>` mapt naar het `is_company`-veld op `res.partner`.
5. Stuur `basic_ack` bij succesvolle verwerking; gebruik `basic_nack(requeue=false)` voor onherstelbare validatiefouten.

**DEFINITION OF DONE:**

- [ ] `receiver.py` maakt een nieuw `res.partner` aan in Odoo als `x_user_id` onbekend is
- [ ] `receiver.py` overschrijft bestaande gegevens als `x_user_id` al bestaat — geen duplicaat
- [ ] XSD-validatie actief op `schema_new_registration.xsd`
- [ ] Idempotentie getest: zelfde `message_id` twee keer → tweede keer stil genegeerd
- [ ] `system_error` met code `invalid_xml_format` verstuurd naar `kassa.errors` bij invalide XML
- [ ] Succes en duplicaten krijgen `basic_ack`
- [ ] Invalide XML krijgt `basic_nack(requeue=false)` en belandt in de DLQ
- [ ] `<type>private|company</type>` uit het inkomende bericht mapt correct naar `is_company=True/False` op `res.partner`
- [ ] `company_name` en `vat_number` worden correct opgeslagen indien aanwezig in het bericht

## **Story 2: Klantgegevens up-to-date houden**

> _MVP status: MVP_

_Als bezoeker wil ik dat wijzigingen in mijn profiel (zoals een nieuw e-mailadres of bedrijfsnaam) direct worden doorgegeven aan de kassa, zodat mijn facturen of kassatickets altijd de juiste gegevens bevatten._

**ACCEPTATIECRITERIA:**

- Als iemand zijn gegevens aanpast in het centrale CRM, krijgt de kassa via een profile_update bericht bericht van.
- De kassa zoekt de betreffende klant op via zijn uniek x_user_id.
- De velden naam, e-mail, geboortedatum, bedrijfsnaam en BTW-nummer worden direct overschreven met de nieuwe waarden.
- Wordt de klant niet gevonden? Dan maakt de kassa een nieuw profiel aan met de ontvangen gegevens (upsert-gedrag) en wordt geen system_error verstuurd.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat een klantprofiel met x_user_id = X bestaat in Odoo

**Wanneer** er een profile_update bericht binnenkomt met diezelfde x_user_id en gewijzigde gegevens

**Dan** worden de velden first_name, last_name (via het contact-element), email, date_of_birth en eventueel company_name en vat_number overschreven in het bestaande Odoo-profiel

**Gegeven** dat een profile_update bericht binnenkomt met een x_user_id dat niet bestaat in Odoo

**Wanneer** receiver.py het bericht verwerkt

**Dan** wordt een nieuw klantprofiel aangemaakt in Odoo met de ontvangen velden

**En** stuurt receiver.py een basic_ack naar RabbitMQ

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1. Herken het profielwijzigingsbericht in het ontvangstscript, controleer de `message_id`-cache op duplicaten en valideer de structuur via het XSD-schema.
2. Zoek de klant op in Odoo via zijn uniek klantnummer.
3. Overschrijf de gewijzigde gegevens (naam, e-mail, bedrijfsnaam, BTW-nummer, geboortedatum) in het lokale profiel.
4. Wordt de klant niet gevonden? Maak een nieuw profiel aan (upsert) en bevestig dat het bericht verwerkt is.

**DEFINITION OF DONE:**

- [ ] `receiver.py` overschrijft alle velden correct in het bestaande `res.partner` record, inclusief `x_date_of_birth`
- [ ] Onbekend `x_user_id` bij `profile_update` resulteert in creatie van een nieuw `res.partner` record (upsert)
- [ ] `basic_ack` verstuurd na succesvolle verwerking (zowel update als create)

## **Story 3: Geannuleerde inschrijvingen blokkeren**

> _MVP status: MVP_

_Als organisatie wil ik dat bezoekers die hun ticket annuleren, ook in de kassa op "inactief" worden gezet, zodat zij niet per ongeluk toch nog aan de kassa gekoppeld kunnen worden._

**ACCEPTATIECRITERIA:**

- De kassa ontvangt annuleringen exclusief vanuit het CRM-systeem via een cancel_registration bericht.
- Bij een annulering zoekt de kassa het profiel op via x_user_id en zet de active flag in Odoo op False.
- Wordt de klant niet gevonden? Dan wordt de annulering als no-op behandeld (geen profielwijziging), zonder system_error, en toch met basic_ack bevestigd.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat een klantprofiel met x_user_id = X bestaat in Odoo

**Wanneer** het CRM een cancel_registration bericht stuurt met diezelfde x_user_id

**Dan** wordt de active flag van dat klantprofiel in Odoo op False gezet

**En** stuurt receiver.py een basic_ack naar RabbitMQ

**Gegeven** dat een cancel_registration bericht binnenkomt met een x_user_id dat niet bestaat in Odoo

**Wanneer** receiver.py het bericht verwerkt

**Dan** wordt er geen profiel aangepast (no-op)

**En** stuurt receiver.py toch een basic_ack naar RabbitMQ

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1. Herken het annuleringsbericht in het ontvangstscript, controleer de `message_id`-cache op duplicaten en valideer de structuur via het XSD-schema.
2. Zoek de klant op in Odoo via zijn uniek klantnummer.
3. Zet het klantprofiel op inactief zodat de medewerker weet dat deze persoon niet meer verwacht wordt.
4. Wordt de klant niet gevonden? Behandel het bericht als no-op en bevestig toch dat het verwerkt is.

**DEFINITION OF DONE:**

- [ ] `receiver.py` zet `active=False` correct op het juiste `res.partner` record
- [ ] Onbekend `x_user_id` bij `cancel_registration` wordt no-op afgehandeld zonder `system_error`
- [ ] `basic_ack` verstuurd in alle gevallen

## **EPIC 2: KASSAVERKOOP & BETALINGEN (UITGAANDE FLOWS)**

## **Story 4: Anoniem een drankje kopen**

> _MVP status: MVP_

_Als kassamedewerker wil ik bestellingen aan de bar supersnel kunnen afrekenen voor mensen zonder account, zodat de wachtrijen kort blijven._

**ACCEPTATIECRITERIA:**

- De medewerker slaat producten aan zonder een klant te selecteren.
- De bestelling wordt succesvol afgerekend en er rolt een bonnetje uit.
- poller.py pikt de afgeronde bestelling op en verstuurt een consumption_order met is_anonymous=true naar kassa.payments, gevolgd door een payment_registered bericht.
- De bestelling wordt in Odoo gemarkeerd als verzonden (x_rabbitmq_sent=True) na succesvolle doorstuur.
- Lukt het versturen niet? Dan worden beide berichten opgeslagen in outbox.json.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat er een afgeronde pos.order in Odoo staat met state=done, x_rabbitmq_sent=False en geen gekoppelde partner_id

**Wanneer** poller.py deze order detecteert

**Dan** wordt een consumption_order XML verstuurd naar kassa.payments met is_anonymous=true

**En** wordt daarna een payment_registered XML verstuurd naar dezelfde queue

**En** wordt x_rabbitmq_sent=True gezet op de order in Odoo

**Gegeven** dat RabbitMQ niet bereikbaar is op het moment van versturen

**Wanneer** poller.py de berichten probeert te sturen

**Dan** worden beide berichten opgeslagen in outbox.json

**En** wordt x_rabbitmq_sent niet op True gezet

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1. Laat het pollerscript elke paar seconden controleren of er nieuwe afgeronde bestellingen zijn in Odoo die nog niet doorgestuurd zijn.
2. Controleer per bestelling of er een klant aan gekoppeld is. Is dat niet het geval? Markeer de bestelling als anoniem (`is_anonymous=true`).
3. Bouw de `consumption_order` XML op conform XSD v2.3: gebruik `LINE-{order_line_id}` als `<id>` (transactieregel-ID voor CRM-upsert) en het Odoo product-ID als `<sku>` per item. Valideer de XML vóór verzending en stuur naar routing key `kassa.payments.consumption`.
4. Bouw de `payment_registered` XML op met `payment_context=consumption`, `correlation_id` gelijk aan de `message_id` van de zojuist verstuurde `consumption_order`, en `payment_method=on_site` (ongeacht betaalmethode in Odoo — Badge Wallet is uitsluitend intern). Valideer en stuur naar `kassa.payments.consumption`.
5. Markeer de bestelling in Odoo als verzonden zodat ze niet opnieuw opgepikt wordt.
6. Lukt het versturen niet? Sla beide berichten tijdelijk op in de lokale buffer.

**DEFINITION OF DONE:**

- [ ] `poller.py` detecteert orders zonder `partner_id` en stuurt `consumption_order` met `is_anonymous=true`
- [ ] Elk `<item>` in `consumption_order` bevat `<id>` in `LINE-{id}` formaat (transactieregel-ID voor CRM-upsert) én `<sku>` (Odoo product-ID) conform XSD v2.3
- [ ] `payment_registered` wordt verstuurd na de `consumption_order`
- [ ] `correlation_id` in de header van `payment_registered` is gelijk aan de `message_id` van de bijhorende `consumption_order`
- [ ] `payment_method` in `payment_registered` is altijd `on_site` — ook bij Badge Wallet betaling (Badge Wallet is uitsluitend intern in Odoo)
- [ ] Uitgaande XML valide tegen `schema_consumption_order_v2.3.xsd` en `schema_payment_registered_v2.1.xsd`
- [ ] `x_rabbitmq_sent=True` gezet op de order na succesvolle verzending
- [ ] Buffer correct gevuld bij RabbitMQ-uitval — `x_rabbitmq_sent` blijft `False`

## **Story 5: Bestellen op bedrijfsnaam (met badge)**

> _MVP status: MVP_

_Als zakelijke bezoeker wil ik dat mijn bestellingen aan de bar direct geregistreerd worden op mijn naam, zodat de rekening netjes naar mijn werkgever gaat of van mijn badge-tegoed af gaat._

**ACCEPTATIECRITERIA:**

- De bestelling wordt in de kassa gekoppeld aan een geïdentificeerde klant.
- Na het afrekenen stuurt poller.py een consumption_order bericht met is_anonymous=false en `<type>company</type>`, en een payment_registered bericht met payment_context=consumption naar kassa.payments.
- Als de klant afrekent met digitaal tegoed (Badge Wallet), verlaagt poller.py lokaal het saldo (x_wallet_balance) in Odoo én stuurt een wallet_balance_update bericht naar frontend.payments.
- De bestelling wordt in Odoo gemarkeerd als verzonden (x_rabbitmq_sent=True) na succesvolle doorstuur.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat er een afgeronde pos.order in Odoo staat met state=done, x_rabbitmq_sent=False en een gekoppelde partner_id van een bedrijfsklant (is_company=True)

**Wanneer** poller.py deze order detecteert

**Dan** wordt een consumption_order XML verstuurd naar kassa.payments met is_anonymous=false en `<type>company</type>` conform XSD v2.3

**En** wordt daarna een payment_registered XML verstuurd naar dezelfde queue

**En** wordt x_rabbitmq_sent=True gezet op de order in Odoo

**Gegeven** dat de betaalmethode van de order Badge Wallet was

**Wanneer** poller.py de order verwerkt

**Dan** wordt het x_wallet_balance veld van de klant in Odoo verlaagd met het bestelbedrag

**En** wordt een wallet_balance_update XML verstuurd naar frontend.payments

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1. Laat het pollerscript elke paar seconden controleren of er nieuwe afgeronde bestellingen zijn die nog niet doorgestuurd zijn.
2. Controleer of er een klant gekoppeld is aan de bestelling en of het een bedrijfsklant is.
3. Bouw de `consumption_order` XML op conform XSD v2.3 met klantgegevens en `<type>company</type>`: gebruik `LINE-{order_line_id}` als `<id>` en het Odoo product-ID als `<sku>` per item. Valideer en stuur naar routing key `kassa.payments.consumption`.
4. Bouw de `payment_registered` XML op met `payment_context=consumption`, `correlation_id` gelijk aan de `message_id` van de `consumption_order`, en `payment_method=on_site` (ook bij Badge Wallet betaling). Valideer en stuur naar `kassa.payments.consumption`.
5. Controleer of er betaald werd met badge-tegoed. Zo ja, verlaag het lokale saldo in Odoo en stuur een `wallet_balance_update` naar routing key `kassa.frontend.wallet`.
6. Markeer de bestelling als verzonden in Odoo.

**DEFINITION OF DONE:**

- [ ] `consumption_order` verstuurd met `is_anonymous=false` en `<type>company</type>` voor bedrijfsklanten conform XSD v2.3 (niet `is_company_linked`)
- [ ] Elk `<item>` in `consumption_order` bevat `<id>` in `LINE-{id}` formaat (transactieregel-ID voor CRM-upsert) én `<sku>` (Odoo product-ID) conform XSD v2.3
- [ ] `correlation_id` in de header van `payment_registered` is gelijk aan de `message_id` van de bijhorende `consumption_order`
- [ ] `payment_method` in `payment_registered` is altijd `on_site` — ook bij Badge Wallet betaling (Badge Wallet is uitsluitend intern in Odoo)
- [ ] Badge Wallet betaling: `x_wallet_balance` verlaagd in Odoo én `wallet_balance_update` verstuurd naar `frontend.payments`
- [ ] Uitgaande XML valide tegen `schema_consumption_order_v2.3.xsd` en `schema_payment_registered_v2.1.xsd`
- [ ] `x_rabbitmq_sent=True` gezet na succesvolle verzending van alle berichten

## **Story 6: Inkomticket betalen aan de deur**

> _MVP status: MVP_

_Als bezoeker die zijn ticket nog niet online betaald heeft, wil ik dit veilig aan de inkombalie kunnen doen, zodat ik alsnog naar binnen mag en de website weet dat ik betaald heb._

**ACCEPTATIECRITERIA:**

- De kassamedewerker zoekt de openstaande inschrijving op en rekent deze af.
- Het kassasysteem verstuurt een payment_registered bericht met payment_context=registration naar kassa.payments via routing key kassa.payments.registration.
- Tegelijkertijd wordt een payment_status bericht verstuurd naar frontend.payments zodat Drupal de betaalstatus kan updaten.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat er een afgeronde pos.order staat in Odoo voor een inschrijvingsbetaling met state=done en x_rabbitmq_sent=False

**Wanneer** poller.py deze order detecteert

**Dan** wordt een payment_registered XML verstuurd naar kassa.payments met payment_context=registration via routing key kassa.payments.registration

**En** wordt een payment_status XML verstuurd naar frontend.payments

**En** wordt x_rabbitmq_sent=True gezet op de order in Odoo

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1. Herken in het pollerscript dat het om een inschrijvingsbetaling gaat via het POS-sessieprofiel ("Inschrijvingskassa") of een custom veld op `pos.order`. Bestellingen van de "Inschrijvingskassa" krijgen altijd `payment_context=registration`.
2. Bouw de `payment_registered` XML op met `payment_context=registration` en `identity_uuid` van de gekoppelde klant. Valideer vóór verzending en stuur naar routing key `kassa.payments.registration`.
3. Bouw de `payment_status` XML op met `identity_uuid` van de klant en `payment_status=paid`. Valideer en stuur naar routing key `kassa.frontend.payment`.
4. Markeer de bestelling als verzonden in Odoo.

**DEFINITION OF DONE:**

- [ ] `payment_registered` verstuurd met `payment_context=registration` via routing key `kassa.payments.registration`
- [ ] `payment_status` verstuurd naar `frontend.payments` met `identity_uuid` van de klant (verplicht veld in `schema_payment_status.xsd`)
- [ ] Uitgaande XML valide tegen `schema_payment_registered_v2.1.xsd` en `schema_payment_status.xsd`
- [ ] `x_rabbitmq_sent=True` gezet op de order

## **Story 7: Factuur vragen voor een drankje**

> _MVP status: MVP_

_Als geidentificeerde bezoeker wil ik aan de bar kunnen vragen om een officiële factuur van mijn aankoop, zodat ik deze kan inbrengen als onkosten._

**ACCEPTATIECRITERIA:**

- De kassa maakt zelf geen facturen, maar verzamelt de naam, het adres en optioneel het BTW-nummer van de klant.
- Zodra de bestelling is afgerond, stuurt de kassa een invoice_request bericht naar kassa.payments richting het CRM.
- Heeft de bezoeker nog geen account? Dan kan de kassa geen factuurverzoek aanmaken — de bezoeker moet eerst zelf een account aanmaken op de website.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat er een afgeronde pos.order staat in Odoo die gemarkeerd is voor facturatie, met een gekoppelde klant met adresgegevens

**Wanneer** poller.py deze order detecteert

**Dan** wordt een invoice_request XML opgebouwd met naam, adres en optioneel BTW-nummer van de klant

**En** wordt dit bericht verstuurd naar kassa.payments

**En** wordt x_rabbitmq_sent=True gezet op de order in Odoo

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1. Herken in het pollerscript dat een bestelling gemarkeerd is voor facturatie.
2. Haal de adresgegevens van de klant op uit Odoo (naam, adres, optioneel BTW-nummer).
3. Bouw het factuurverzoekbericht op conform het XSD-schema en stuur naar de wachtrij richting het CRM.
4. Markeer de bestelling als verzonden in Odoo.

**DEFINITION OF DONE:**

- [ ] `invoice_request` verstuurd met correcte naam, adres en optioneel BTW-nummer vanuit Odoo
- [ ] Klant zonder account: geen `invoice_request` aangemaakt — medewerker geïnformeerd
- [ ] Uitgaande XML valide tegen `schema_invoice_request.xsd`
- [ ] `x_rabbitmq_sent=True` gezet na succesvolle verzending

## **Story 8: Een aankoop ongedaan maken (Terugbetaling)**

> _MVP status: MVP_

_Als kassamedewerker wil ik een verkeerd aangeslagen drankje direct kunnen annuleren en het geld teruggeven, zodat de klant niet te veel betaalt._

**ACCEPTATIECRITERIA:**

- De medewerker registreert een terugbetaling (negatief bedrag) in de kassa.
- De kassa verstuurt een refund_processed bericht naar kassa.payments, met als correlation_id de message_id (UUID) van de originele payment_registered.
- Als de klant oorspronkelijk met badge-tegoed had betaald, wordt het x_wallet_balance in Odoo verhoogd en een wallet_balance_update verstuurd naar frontend.payments.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat er een afgeronde pos.order staat in Odoo met een negatief totaalbedrag en x_rabbitmq_sent=False
**Wanneer** poller.py deze order detecteert
**Dan** wordt een refund_processed XML verstuurd naar kassa.payments met correlation_id gelijk aan de message_id (UUID) van de originele payment_registered
**En** wordt x_rabbitmq_sent=True gezet op de order in Odoo

**Gegeven** dat de originele betaling via Badge Wallet was
**Wanneer** poller.py de terugbetaling verwerkt
**Dan** wordt het x_wallet_balance veld van de klant in Odoo verhoogd met het terugbetaalde bedrag
**En** wordt een wallet_balance_update XML verstuurd naar frontend.payments

**Gegeven** dat een order in Odoo een negatief totaalbedrag heeft en geen gekoppelde klant heeft (anoniem)
**Wanneer** poller.py deze order detecteert
**Dan** wordt een refund_processed XML verstuurd zonder `<identity_uuid>`
**En** is de methode cash of card_reversal (nooit badge_wallet)

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1. Herken in het pollerscript bestellingen met een negatief totaalbedrag als terugbetalingen.
2. Haal de `message_id` van de originele `payment_registered` op als `correlation_id`. Bouw de `refund_processed` XML op conform het XSD-schema met dit UUID als `correlation_id` en stuur naar routing key `kassa.payments.refund`. Valideer de XML vóór verzending.
3. Controleer of de originele betaling via badge-tegoed was. Zo ja, verhoog het lokale saldo in Odoo en stuur een saldo-update naar de website.
4. Markeer de terugbetaling als verzonden in Odoo.

**DEFINITION OF DONE:**

- [ ] `refund_processed` verstuurd met `correlation_id` gelijk aan de `message_id` van de originele `payment_registered` (UUID-formaat, niet `ORDER-{id}`)
- [ ] Badge Wallet refund: `x_wallet_balance` verhoogd in Odoo én `wallet_balance_update` verstuurd naar `frontend.payments`
- [ ] Anonieme refund: geen `<identity_uuid>` in bericht, methode altijd `cash` of `card_reversal`
- [ ] Uitgaande XML valide tegen `schema_refund_processed.xsd`
- [ ] `x_rabbitmq_sent=True` gezet op de terugbetalingsorder

## **EPIC 3: BADGES & SALDO (IOT & WALLET)**

## **Story 9: De fysieke badge gebruiken aan de bar**

> _MVP status: secundair (Niet strikt MVP)_

_Als kassamedewerker wil ik dat de kassa de klant direct herkent zodra de scanner zijn badge leest, zodat ik geen namen hoef in te typen en direct kan verkopen._

**ACCEPTATIECRITERIA:**

- Zodra de scanner een badge ziet, ontvangt receiver.py het badge_scanned bericht op kassa.incoming.
- De kassa zoekt het badge_id op in Odoo via het x_badge_id veld op res.partner en haalt het bijhorende klantprofiel op.
- Wordt de badge niet herkend? Dan start de foutafhandeling van Story 12.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat een badge_scanned bericht binnenkomt op kassa.incoming met een badge_id dat overeenkomt met een x_badge_id in Odoo

**Wanneer** receiver.py het bericht verwerkt

**Dan** wordt het bijhorende klantprofiel opgehaald uit Odoo

**En** stuurt receiver.py een basic_ack naar RabbitMQ

**Gegeven** dat een badge_scanned bericht binnenkomt met een badge_id dat niet bestaat in Odoo

**Wanneer** receiver.py de lookup uitvoert

**Dan** wordt de verwerking van Story 12 gestart

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1. Zorg dat het ontvangstscript luistert naar scanberichten van de IoT-scanner via de inkomende wachtrij, controleer de `message_id`-cache op duplicaten en valideer het bericht via het XSD-schema.
2. Zoek het badge-ID op in Odoo en haal het bijhorende klantprofiel op.
3. Wordt de badge niet herkend? Verwijs door naar de foutafhandeling van Story 12.
4. Bevestig aan de wachtrij dat het bericht verwerkt is.
5. Push een event via de **Odoo bus** (`bus.bus`) naar de actieve POS-sessie met het opgehaalde klantprofiel.
6. Een **OWL-component** in de POS-frontend luistert op dit bus-event en selecteert automatisch de klant in de lopende bestelling. Dit vereist een custom Odoo addon (`kassa_pos_custom`) met een JavaScript OWL-component onder `static/src/js/`.

**DEFINITION OF DONE:**

- [ ] `badge_scanned` correct verwerkt: klantprofiel opgehaald via `x_badge_id` op `res.partner`
- [ ] `receiver.py` pusht het klantprofiel via de Odoo bus naar de actieve POS-sessie na succesvolle lookup
- [ ] OWL-component in de POS ontvangt het bus-event en selecteert de klant automatisch in de lopende bestelling
- [ ] Custom Odoo addon (`kassa_pos_custom`) aangemaakt met correct `__manifest__.py` en POS asset-registratie
- [ ] Onbekende badge: verwerking van Story 12-flow gestart
- [ ] `basic_ack` verstuurd in alle gevallen

## **Story 10: Een nieuwe badge uitgeven**

> _MVP status: secundair (Niet strikt MVP)_

_Als baliemedewerker wil ik bij aankomst van een gast een blanco badge kunnen pakken en deze aan zijn account koppelen, zodat hij direct kan betalen op het evenement._

**ACCEPTATIECRITERIA:**

- De medewerker voert het badge-ID in bij de klant in Odoo (x_badge_id veld op res.partner wordt ingevuld).
- De kassa verstuurt een badge_assigned bericht naar kassa.payments zodat alle systemen de nieuwe koppeling kennen.
- Is het badge-ID al gekoppeld aan een andere klant? Dan wordt een foutmelding verstuurd naar de Controlroom.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat een medewerker een nieuw badge_id koppelt aan een bestaand klantprofiel in Odoo (x_badge_id wordt ingevuld)
**Wanneer** poller.py deze wijziging detecteert
**Dan** wordt een badge_assigned XML verstuurd naar kassa.payments
**En** wordt de actie als verzonden gemarkeerd in Odoo

**Gegeven** dat een medewerker een badge_id koppelt dat al bij een andere klant in Odoo is opgeslagen
**Wanneer** de API-call naar Odoo hierdoor faalt
**Dan** wordt een system_error verstuurd naar kassa.errors met de code odoo_api_error

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1. Detecteer in het pollerscript wanneer een nieuw badge-ID wordt opgeslagen bij een klantprofiel in Odoo door te pollen op `res.partner`-records waarbij `x_badge_id` ingevuld is maar de koppeling nog niet verstuurd is (bij te houden via een custom boolean veld op `res.partner`).
2. Bouw de `badge_assigned` XML op conform het XSD-schema. Valideer vóór verzending.
3. Stuur het bericht naar de wachtrij richting het CRM zodat alle systemen de nieuwe koppeling kennen.
4. Markeer de actie als verzonden in Odoo.

**DEFINITION OF DONE:**

- [ ] `badge_assigned` verstuurd bij succesvol koppelen van een nieuw badge-ID
- [ ] `system_error` met code `odoo_api_error` verstuurd bij duplicaat badge-ID
- [ ] Uitgaande XML valide tegen `schema_badge_assigned.xsd`
- [ ] Actie als afgehandeld gemarkeerd in Odoo

## **Story 11: Digitaal tegoed (Top-up) kopen**

> _MVP status: secundair (Niet strikt MVP)_

_Als bezoeker wil ik met cash of mijn bankpas virtueel geld op mijn badge kunnen zetten, zodat ik later op de avond makkelijk drankjes kan afrekenen._

**ACCEPTATIECRITERIA:**

- De medewerker slaat een product aan uit de POS-categorie 'Top-ups' in Odoo POS. Het systeem herkent dit als een saldo-verhoging.
- Het bedrag wordt opgeteld bij het x_wallet_balance van de klant in Odoo.
- Er wordt een consumption_order bericht verstuurd naar kassa.payments richting het CRM.
- Er wordt een wallet_balance_update bericht verstuurd naar frontend.payments richting de website.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat er een afgeronde pos.order staat in Odoo met een product uit de categorie 'Top-ups' (of `x_is_topup=True`) en x_rabbitmq_sent=False

**En** de order heeft een gekoppelde klant met een x_badge_id

**Wanneer** poller.py deze order detecteert

**Dan** wordt het x_wallet_balance van de klant in Odoo verhoogd met het aankoopbedrag

**En** wordt een consumption_order XML verstuurd naar kassa.payments

**En** wordt een wallet_balance_update XML verstuurd naar frontend.payments

**En** wordt x_rabbitmq_sent=True gezet op de order in Odoo

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1. Herken in het pollerscript een Top-up aankoop op basis van de POS-categorie 'Top-ups' of het custom veld `x_is_topup` via `is_topup_product()`. Forceer `vat_rate=0` in de XML-export voor deze producten.
2. Verhoog het lokale badge-saldo van de klant in Odoo met het aangekochte bedrag.
3. Bouw de `consumption_order` XML op conform XSD v2.3: gebruik `LINE-{order_line_id}` als `<id>`, Odoo product-ID als `<sku>`, `vat_rate=0` en `item_type=wallet_topup` per item. Valideer en stuur naar routing key `kassa.payments.consumption`.
4. Stuur een `wallet_balance_update` XML naar routing key `kassa.frontend.wallet`.
5. Markeer de bestelling als verzonden in Odoo.

**DEFINITION OF DONE:**

- [ ] `poller.py` herkent Top-up product via `is_topup_product()` (categorie-check of `x_is_topup`); forceert `vat_rate=0` en zet `item_type=wallet_topup` in de uitgaande XML
- [ ] Elk `<item>` in `consumption_order` bevat `<id>` in `LINE-{id}` formaat (transactieregel-ID voor CRM-upsert) én `<sku>` (Odoo product-ID) conform XSD v2.3
- [ ] `x_wallet_balance` verhoogd in Odoo met het correcte aankoopbedrag
- [ ] `consumption_order` verstuurd naar `kassa.payments`
- [ ] `wallet_balance_update` verstuurd naar `frontend.payments`
- [ ] Uitgaande XML valide tegen `schema_consumption_order_v2.3.xsd`
- [ ] `x_rabbitmq_sent=True` gezet na succesvolle verzending van alle berichten

## **Story 12: Wat als we een badge niet kennen?**

> _MVP status: secundair (Niet strikt MVP)_

_Als kassamedewerker wil ik dat het systeem niet vastloopt als een bezoeker per ongeluk een badge scant die niet in ons systeem staat._

**ACCEPTATIECRITERIA:**

- Als een badge onbekend is, stopt de kassa de verwerking zonder te crashen of eindeloos te herhalen.
- Er wordt een system_error bericht met code badge_not_found verstuurd naar kassa.errors, met de originele message_id van het scanbericht als related_message_id.
- Het scanbericht krijgt een basic_ack zodat het niet opnieuw aangeboden wordt door RabbitMQ.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat een badge_scanned bericht binnenkomt met een badge_id dat niet bestaat in Odoo

**Wanneer** receiver.py de lookup uitvoert

**Dan** wordt een system_error XML met code badge_not_found verstuurd naar kassa.errors, met de originele message_id van het scanbericht als related_message_id

**En** stuurt receiver.py een basic_ack naar RabbitMQ zodat het bericht niet opnieuw aangeboden wordt

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1. Als de database lookup tijdens een scan geen klant oplevert, stop dan de verwerking zonder te crashen.
2. Bouw een foutbericht op met de code badge_not_found en voeg het originele scanbericht-ID toe als referentie.
3. Stuur het foutbericht naar de monitoringswachtrij richting de Controlroom.
4. Bevestig aan de wachtrij dat het scanbericht verwerkt is zodat het niet opnieuw aangeboden wordt.

**DEFINITION OF DONE:**

- [ ] `system_error` met code `badge_not_found` verstuurd naar `kassa.errors`
- [ ] Originele `message_id` van het scanbericht aanwezig als `related_message_id` in het foutbericht
- [ ] `basic_ack` verstuurd zodat het scanbericht de queue niet blokkeert

## **EPIC 4: FOUTEN & SYSTEEMMONITORING (RESILIENCE & CONTROLROOM)**

## **Story 13: Zonder internet toch blijven verkopen**

> _MVP status: MVP_

_Als festivalorganisator eis ik dat de barren gewoon drank kunnen blijven verkopen, zelfs als het centrale netwerk er even uit ligt._

**ACCEPTATIECRITERIA:**

- Als de kassa geen contact heeft met RabbitMQ, bewaart hij berichten lokaal in outbox.json (max 500 berichten).
- Zodra het netwerk hersteld is, worden de gebufferde berichten alsnog verstuurd in volgorde en wordt outbox.json leeggemaakt.
- Heartbeat-berichten worden nooit gebufferd — die worden bij falen gewoon weggegooid.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat RabbitMQ niet bereikbaar is

**Wanneer** sender.py een bericht probeert te versturen

**Dan** wordt het bericht opgeslagen in outbox.json

**En** bevat outbox.json na deze actie maximaal 500 berichten

**Gegeven** dat de verbinding met RabbitMQ hersteld is en outbox.json berichten bevat

**Wanneer** sender.py opnieuw verbinding maakt

**Dan** worden alle gebufferde berichten alsnog verstuurd in volgorde

**En** wordt outbox.json leeggemaakt na succesvolle verzending

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1. Zorg voor foutafhandeling bij het versturen van berichten naar RabbitMQ.
2. Lukt het versturen niet? Sla het bericht op in de lokale buffer (outbox.json), met een maximum van 500 berichten.
3. Roep `flush_buffer()` aan vanuit het reconnect-pad in `sender.py` zodra de verbinding met RabbitMQ hersteld is. De functie stuurt alle gebufferde berichten in volgorde en maakt `outbox.json` leeg na volledige hersending.
4. Heartbeat-berichten worden nooit gebufferd — die worden bij falen gewoon weggegooid.

**DEFINITION OF DONE:**

- [ ] Berichten correct opgeslagen in `outbox.json` bij RabbitMQ-uitval
- [ ] Maximum van 500 berichten gerespecteerd — geen enkel bericht voorbij de limiet gebufferd
- [ ] `flush_buffer()` hersturt alle gebufferde berichten in volgorde bij reconnect
- [ ] `flush_buffer()` wordt daadwerkelijk aangeroepen vanuit het reconnect-pad in `sender.py` — niet enkel gedefinieerd
- [ ] `outbox.json` volledig leeggemaakt na succesvolle hersending
- [ ] `outbox.json` staat op een Docker named volume — overleeft container-herstart

## **Story 14: Kassa beschermen tegen foute data**

> _MVP status: MVP_

_Als beheerder wil ik dat de kassa onleesbare of onbekende berichten vanuit andere systemen netjes negeert en rapporteert, zodat de kassa niet crasht._

**ACCEPTATIECRITERIA:**

- Elk inkomend bericht wordt gevalideerd via het bijhorende XSD-schema.
- Klopt de structuur niet? Dan wordt een system_error met code invalid_xml_format verstuurd naar kassa.errors en gaat het bericht via basic_nack(requeue=false) naar de DLQ.
- Is het berichttype onbekend? Dan wordt een system_error met code unknown_message_type verstuurd naar kassa.errors.
- In beide gevallen krijgt het bericht een basic_nack(requeue=false), zodat het niet blijft herhalen en traceerbaar in de DLQ terechtkomt.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat een inkomend bericht op kassa.incoming niet voldoet aan het XSD-schema

**Wanneer** receiver.py de validatie uitvoert

**Dan** wordt een system_error met code invalid_xml_format verstuurd naar kassa.errors

**En** stuurt receiver.py een basic_nack(requeue=false) zodat het bericht in de DLQ belandt

**Gegeven** dat een inkomend bericht een onbekend type heeft

**Wanneer** receiver.py het berichttype controleert

**Dan** wordt een system_error met code unknown_message_type verstuurd naar kassa.errors

**En** stuurt receiver.py een basic_nack(requeue=false) zodat het bericht in de DLQ belandt

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1. Controleer elk inkomend bericht eerst op geldige XML-structuur via het bijhorende XSD-schema.
2. Is het berichttype onbekend of klopt de structuur niet? Stuur een foutmelding met de juiste foutcode naar de Controlroom.
3. Verstuur basic_nack(requeue=false) zodat het bericht niet blijft herhalen en in de DLQ terechtkomt voor analyse.

**DEFINITION OF DONE:**

- [ ] XSD-validatie actief voor alle inkomende berichttypes op `kassa.incoming`
- [ ] `system_error` met code `invalid_xml_format` verstuurd bij structuurfout
- [ ] `system_error` met code `unknown_message_type` verstuurd bij onbekend berichttype
- [ ] `basic_nack(requeue=false)` verstuurd in beide gevallen — berichten gaan gecontroleerd naar de DLQ

## **Story 15: Dubbele berichten stil negeren (Idempotentie)**

> _MVP status: MVP_

_Als systeembeheerder wil ik dat de kassa elk inkomend bericht maar één keer verwerkt, zodat klantprofielen of saldo's niet corrupt raken als RabbitMQ een bericht dubbel aflevert._

**ACCEPTATIECRITERIA:**

- Het receiver.py script houdt een interne cache (LRU via OrderedDict, max 10.000 items) bij van recent verwerkte message_id's.
- Als een inkomend bericht een ID heeft dat al in de cache staat, wordt de verwerking overgeslagen.
- Het duplicaat krijgt direct een basic_ack naar RabbitMQ, zodat het stil uit de wachtrij verdwijnt zonder foutmelding.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat een bericht met message_id = X al eerder succesvol is verwerkt door receiver.py

**En** de message_id staat nog in de interne OrderedDict cache

**Wanneer** RabbitMQ hetzelfde bericht met message_id = X opnieuw aflevert

**Dan** wordt de verwerking overgeslagen — er worden geen Odoo-acties uitgevoerd

**En** stuurt receiver.py direct een basic_ack naar RabbitMQ

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1. Houd in het ontvangstscript een interne lijst bij van recent verwerkte bericht-ID's (max 10.000 items).
2. Controleer bij elk nieuw bericht of het ID al in de lijst staat.
3. Staat het er al in? Bevestig aan de wachtrij dat het bericht verwerkt is en stop verdere verwerking.
4. Staat het er nog niet in? Voeg het toe aan de lijst en verwerk het bericht normaal.

**DEFINITION OF DONE:**

- [ ] `OrderedDict` cache actief in `receiver.py` met maximaal 10.000 items (LRU eviction)
- [ ] Duplicaat bericht (zelfde `message_id`) wordt stil genegeerd zonder Odoo-acties
- [ ] `basic_ack` verstuurd op het duplicaat

## **Story 16: Lokale buffer beschermen tegen overstroming (offline_queue_full)**

> _MVP status: MVP_

_Als IT-beheerder wil ik gewaarschuwd worden als de kassa langdurig offline is en de lokale buffer vol raakt, zodat we weten dat er transactiedata verloren dreigt te gaan._

**ACCEPTATIECRITERIA:**

- De kassa mag maximaal 500 berichten lokaal opslaan in de outbox.json buffer.
- Bij het bereiken van deze limiet weigert de kassa nieuwe berichten lokaal op te slaan.
- Er wordt direct een system_error met de code offline_queue_full gegenereerd en verstuurd naar kassa.errors zodra de verbinding hersteld is.
- De kassa blijft gewoon verkopen — enkel het doorsturen stopt.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat outbox.json al 500 berichten bevat

**En** RabbitMQ is niet bereikbaar

**Wanneer** sender.py een 501e bericht probeert te bufferen

**Dan** wordt het bericht weggegooid — outbox.json blijft op 500

**En** wordt een system_error met code offline_queue_full verstuurd naar kassa.errors zodra de verbinding hersteld is

**En** blijft de kassa gewoon verkopen — enkel het doorsturen stopt

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1. Controleer bij elk wegschrijven naar de lokale buffer of het maximum van 500 berichten al bereikt is.
2. Is de buffer vol? Gooi het nieuwe bericht weg zonder het op te slaan.
3. Sla de `system_error` met code `offline_queue_full` op in de buffer zodat hij verstuurd wordt zodra de verbinding hersteld is. De fout zelf wordt dus ook gebufferd.
4. De kassa blijft gewoon verkopen — enkel het doorsturen stopt.

**DEFINITION OF DONE:**

- [ ] Limiet van 500 berichten gerespecteerd in `outbox.json` — 501e bericht wordt weggegooid
- [ ] `system_error` met code `offline_queue_full` wordt bij volle buffer lokaal gebufferd en verstuurd zodra de verbinding hersteld is
- [ ] Kassa blijft verkopen bij volle buffer — enkel het doorsturen stopt
- [ ] Handmatig geverifieerd (of via integratietest) dat Odoo POS orders blijft verwerken wanneer de buffer vol is

## **EPIC 5: UITGEBREIDE RANDGEVALLEN (TECHNICAL SAD PATHS)**

## **Story 17: Alcoholcontrole**

> _MVP status: Secundair_

_Als kassamedewerker wil ik een automatische waarschuwing bij verkoop van alcohol aan minderjarigen, zodat ik de wettelijke leeftijdscontrole niet kan missen._

**ACCEPTATIECRITERIA:**

- De kassa berekent de actuele leeftijd op basis van het `x_date_of_birth` veld in Odoo (geboortedatum, type Date).
- Bij producten met de vlag `x_age_restricted` en berekende leeftijd < 18 jaar verschijnt een blokkerende pop-up.
- De kassamedewerker kan de blokkering handmatig overschrijven met een reden.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat een klant ingelogd is via badge-scan en `x_date_of_birth` aanwezig is in Odoo

**En** de kassamedewerker voegt een product toe met de vlag `x_age_restricted`

**Wanneer** de berekende leeftijd van de klant < 18 jaar is

**Dan** verschijnt een blokkerende pop-up met de melding dat de klant minderjarig is

**En** kan de medewerker de verkoop enkel doorzetten na manuele bevestiging met reden

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1. Bereken de actuele leeftijd op basis van `x_date_of_birth` op het moment van scan.
2. Controleer bij elk toe te voegen product of het de `x_age_restricted` vlag draagt.
3. Is de klant jonger dan 18? Toon een blokkerende pop-up en vereist manuele bevestiging met verplichte reden.
4. Implementeer als **OWL-component** binnen een custom Odoo addon (`kassa_pos_custom`). De component overschrijft de standaard `OrderWidget` of `Orderline` en voegt de leeftijdscheck toe bij het toevoegen van een product. De pop-up is een `AbstractAwaitablePopup`. Registreer de JavaScript-bestanden in `__manifest__.py` onder `point_of_sale._assets_pos`.

**DEFINITION OF DONE:**

- [ ] Leeftijdsberekening correct op basis van `x_date_of_birth` t.o.v. de huidige datum
- [ ] Blokkerende pop-up verschijnt correct bij product met `x_age_restricted=True` én leeftijd < 18
- [ ] Medewerker kan blokkering manueel overschrijven met verplichte reden
- [ ] Custom Odoo addon (`kassa_pos_custom`) aangemaakt met OWL-component en correct geregistreerd onder `point_of_sale._assets_pos` in `__manifest__.py`

## **Story 18: Twee POS-profielen**

> _MVP status: MVP_

_Als medewerker wil ik bij opstarten kunnen kiezen tussen "Bar Kassa" en "Inschrijvingskassa", zodat de juiste producten en betaalmethoden automatisch beschikbaar zijn._

**ACCEPTATIECRITERIA:**

- Bar Kassa: toont enkel consumpties, accepteert `badge_wallet` en cash/pin.
- Inschrijvingskassa: toont enkel inkomtickets, accepteert enkel cash/pin (geen `badge_wallet`).
- De kassamedewerker kiest het profiel bij het starten van een POS-sessie in Odoo.
- Beide profielen sturen dezelfde XML-structuren — enkel de beschikbare producten en betaalmethoden verschillen.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat een medewerker een nieuwe POS-sessie opstart

**Wanneer** de medewerker "Inschrijvingskassa" selecteert

**Dan** zijn enkel inkomtickets zichtbaar in de productcatalogus

**En** is `badge_wallet` niet beschikbaar als betaalmethode

**Wanneer** de medewerker "Bar Kassa" selecteert

**Dan** zijn enkel consumpties zichtbaar

**En** is `badge_wallet` beschikbaar naast cash en pin

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1. Maak twee aparte POS-configuraties aan in Odoo: "Bar Kassa" en "Inschrijvingskassa".
2. Koppel per configuratie de juiste productcategorieën en betaalmethoden.
3. De medewerker kiest bij sessiestart het gewenste profiel.

**DEFINITION OF DONE:**

- [ ] Twee POS-configuraties aangemaakt in Odoo: "Bar Kassa" en "Inschrijvingskassa"
- [ ] `badge_wallet` enkel beschikbaar als betaalmethode op het Bar Kassa-profiel
- [ ] Beide profielen tonen enkel de correcte productcategorieën
- [ ] Beide profielen getest bij sessiestart door een medewerker

## **Story 19: Foutieve betaling met virtueel saldo blokkeren**

> _MVP status: secundair (Niet strikt MVP)_

_Als financieel beheerder wil ik dat de kassa een betaling met digitaal tegoed snoeihard blokkeert als er geen klant aan de bestelling gekoppeld is, om spook-afschrijvingen te voorkomen._

**ACCEPTATIECRITERIA:**

- Als een anonieme verkoop wordt afgerekend via de Badge Wallet, detecteert de kassa deze inconsistentie en trekt nergens saldo vanaf.
- Er wordt een system_error bericht verstuurd naar kassa.errors.
- De bestelling wordt gemarkeerd als afgehandeld zodat hij niet blijft herhalen.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat een pos.order in Odoo geen gekoppelde partner_id heeft

**En** de betaalmethode van de order is Badge Wallet

**Wanneer** poller.py deze order verwerkt

**Dan** wordt er geen saldo afgetrokken van enig klantprofiel

**En** wordt een system_error verstuurd naar kassa.errors

**En** wordt de order gemarkeerd als afgehandeld zodat hij niet blijft herhalen

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1. Blokkeer de Badge Wallet betaalmethode in de POS-frontend wanneer geen klant gekoppeld is aan de lopende bestelling. Implementeer als **OWL-component** in `kassa_pos_custom` die de betaalknop voor Badge Wallet verbergt of uitschakelt zolang `order.partner` leeg is.
2. Mocht de inconsistente toestand toch de backend bereiken (anonieme order met Badge Wallet): stop de afschrijving onmiddellijk in `order_poller.py`.
3. Stuur een `system_error` met de juiste foutcode naar `kassa.errors`.
4. Markeer de bestelling als afgehandeld in Odoo zodat ze niet blijft hangen.

**DEFINITION OF DONE:**

- [ ] OWL-component in `kassa_pos_custom` verbergt/uitschakelt Badge Wallet betaalmethode wanneer geen klant geselecteerd is in de POS
- [ ] Combinatie anonieme order + Badge Wallet betaling die toch de backend bereikt → geen enkel saldo afgetrokken in `order_poller.py`
- [ ] `system_error` verstuurd naar `kassa.errors` bij deze inconsistente toestand
- [ ] Order gemarkeerd als afgehandeld in Odoo zodat hij niet blijft herhalen

## **Story 20: Verbindingsfouten direct alarmeren**

> _MVP status: MVP_

_Als IT-beheerder wil ik dat verbindingsfouten met Odoo direct als foutmelding naar het centrale dashboard rollen, zodat wij problemen snel kunnen oplossen._

**ACCEPTATIECRITERIA:**

- Zodra het script de Odoo XML-RPC API niet kan bereiken, wordt dit gedetecteerd.
- Er wordt een system_error bericht met code odoo_api_error verstuurd naar kassa.errors.
- Het script pauzeert één seconde voor een nieuwe poging.
- Retries zijn begrensd (bijvoorbeeld maximaal 3 pogingen per bericht); na het bereiken van de limiet wordt het bericht met basic_nack(requeue=false) naar de DLQ gestuurd.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat poller.py of receiver.py een Odoo XML-RPC aanroep uitvoert

**En** Odoo is niet bereikbaar of gooit een exception

**Wanneer** de fout wordt opgevangen

**Dan** wordt een system_error met code odoo_api_error verstuurd naar kassa.errors

**En** pauzeert het script één seconde voor een nieuwe poging

**En** wordt na het overschrijden van de retry-limiet een basic_nack(requeue=false) gestuurd zodat het bericht in de DLQ komt

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1. Wrap alle Odoo XML-RPC aanroepen in `poller.py` én `receiver.py` in een `try/except`-blok.
2. Lukt het ophalen of wegschrijven van data niet? Bouw een `system_error` met code `odoo_api_error` op en stuur naar routing key `kassa.errors`.
3. Pauzeer de verwerking telkens exact 1 seconde (`time.sleep(1)`) en probeer opnieuw. Begrens het aantal pogingen op maximaal 3 per bericht.
4. Bij het bereiken van de retry-limiet (3 pogingen): stuur `basic_nack(requeue=false)` zodat het bericht in de DLQ belandt voor latere analyse/herverwerking.

**DEFINITION OF DONE:**

- [ ] Alle Odoo XML-RPC aanroepen in `poller.py` en `receiver.py` wrapped in `try/except`
- [ ] `system_error` met code `odoo_api_error` verstuurd bij elke verbindingsfout of exception
- [ ] Script pauzeert exact 1 seconde tussen retries
- [ ] Retry-limiet is actief (bijvoorbeeld max 3 pogingen per bericht)
- [ ] Overschrijden retry-limiet resulteert in `basic_nack(requeue=false)` naar de DLQ

## **EPIC 6: INSCHRIJVINGSKASSA FLOWS**

## **Story 21: Nieuwe inschrijving direct zichtbaar en afrekenbaar in de kassa**

> _MVP status: MVP_

_Als kassamedewerker wil ik dat een bezoeker die zich via het tweede scherm aan de balie inschrijft direct zichtbaar is in de kassa met het juiste openstaande bedrag, zodat ik direct kan afrekenen zonder de kassasessie te herstarten of het bedrag handmatig in te typen._

**ACCEPTATIECRITERIA:**

- Zodra `receiver.py` een `new_registration` bericht verwerkt, slaat het naast de profielgegevens ook het openstaande bedrag (`payment_due.amount`) en de betaalstatus (`payment_due.status`) op als custom velden op het `res.partner` record in Odoo.
- De actieve POS-sessie op de Inschrijvingskassa ontvangt automatisch een cache-update voor deze ene partner — zonder sessie-herstart en zonder lopende transacties te onderbreken.
- Wanneer de medewerker de klant opzoekt en selecteert, toont de POS het openstaande bedrag duidelijk en wordt automatisch een generiek "Inschrijving" product aan het winkelmandje toegevoegd met het juiste openstaande bedrag als prijs.
- Hetzelfde geldt bij een `profile_update` die het bedrag of de status wijzigt.
- Zodra de inschrijving in de kassa is afgerekend, wordt het openstaande bedrag van de klant automatisch gereset naar €0,00 zodat dit bij een volgend bar-bezoek niet meer in beeld staat.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat een kassasessie actief is op de Inschrijvingskassa

**En** een bezoeker registreert zich via het tweede scherm aan de balie (website)

**Wanneer** `receiver.py` het `new_registration` bericht verwerkt

**Dan** wordt `x_outstanding_amount` en `x_payment_status` opgeslagen op het `res.partner` record in Odoo

**En** ontvangt de actieve POS-sessie een granulair cache-event voor enkel deze partner via de Odoo bus

**En** is de klant binnen enkele seconden vindbaar in de POS-zoekfunctie

**En** ziet de medewerker het openstaande bedrag bij het selecteren van de klant

**Gegeven** dat een lopende betaling of transactie actief is in de POS op het moment van de cache-update

**Wanneer** het bus-event binnenkomt

**Dan** wordt de actieve transactie niet onderbroken — de update gebeurt op de achtergrond

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1. Voeg twee custom velden toe aan `res.partner` in `main.py` via `ensure_custom_fields()`: `x_outstanding_amount` (float, "Openstaand bedrag") en `x_payment_status` (char, "Betaalstatus"). Deze worden aangemaakt bij opstarten van het integratiescript.
2. Sla in `process_new_registration()` in `receiver.py` na de partner-aanmaak of -update ook `x_outstanding_amount` en `x_payment_status` op in Odoo. Doe hetzelfde in `process_profile_update()` als het bericht een `payment_due`-element bevat.
3. Publiceer na de succesvolle write een `bus.bus` event via Odoo XML-RPC met het `partner_id` en de gewijzigde velden (naam, `x_outstanding_amount`, `x_payment_status`). Gebruik hetzelfde bus-mechanisme als Story 9.
4. Implementeer in `kassa_pos_custom` een OWL-component dat luistert op dit bus-event. Bij ontvangst: haal via één gerichte RPC-aanroep enkel die ene partner op uit Odoo en voeg hem toe aan (of update hem in) de lokale POS model store — **geen volledige partnerlijst herladen**. Dit is niet-blokkerend: lopende transacties worden niet aangeraakt.
5. Toon `x_outstanding_amount` en `x_payment_status` zichtbaar in de POS wanneer de medewerker de klant selecteert. Voeg daarnaast automatisch een generiek "Inschrijving" product toe aan de orderregel met het openstaande bedrag als prijs — zodat de medewerker niets handmatig hoeft in te typen. Dit product moet vooraf aangemaakt zijn in de Inschrijvingskassa (één generiek product, geen product per sessie).
6. Zodra de betaling succesvol verwerkt is in de Inschrijvingskassa, zet `order_poller.py` het `x_outstanding_amount` van de klant op `0` en `x_payment_status` op `paid` in Odoo — zodat bij een volgende kassa-interactie (bv. een consumptie aan de bar) geen openstaand bedrag meer getoond wordt.

**DEFINITION OF DONE:**

- [ ] `x_outstanding_amount` (float) en `x_payment_status` (char) aangemaakt als custom velden op `res.partner` via `main.py`
- [ ] `receiver.py` slaat `payment_due.amount` en `payment_due.status` op in deze velden na elke `new_registration` en relevante `profile_update`
- [ ] `receiver.py` publiceert een `bus.bus` event na succesvolle write met `partner_id` en gewijzigde velden
- [ ] OWL-component in `kassa_pos_custom` ontvangt het event en voegt **enkel de betrokken partner** granulair toe aan de lokale POS cache — geen volledige herlaad, geen transactie-onderbreking
- [ ] Openstaand bedrag en betaalstatus zichtbaar in POS bij selectie van de klant
- [ ] Bij selectie van klant met `x_outstanding_amount > 0`: OWL-component voegt automatisch een generiek "Inschrijving" product toe aan de orderregel met het openstaande bedrag als prijs
- [ ] Na succesvolle betaling via Inschrijvingskassa: `order_poller.py` zet `x_outstanding_amount = 0` en `x_payment_status = paid` op het `res.partner` record in Odoo
- [ ] Werkt ook bij `profile_update` met gewijzigd bedrag of status
- [ ] Vereist `kassa_pos_custom` addon (gedeeld met Story 9, 17 en 19)

## **EPIC 7: SESSIE & PLANNING INTEGRATIE**

## **Story 22: Sessie-inhoud automatisch bijhouden in de kassa**

> _MVP status: MVP_

_Als kassamedewerker wil ik dat sessies en lezingen die via het planningssysteem worden aangemaakt of gewijzigd direct als afrekenbaar product zichtbaar zijn in de Inschrijvingskassa, zodat ik op het event de correcte sessietickets kan selecteren zonder iets handmatig te moeten invoeren._

**ACCEPTATIECRITERIA:**

- Wanneer Frontend een `session_created` bericht stuurt, maakt de kassa automatisch een POS-product aan met de sessietitel en prijs (indien opgegeven). Het product is onmiddellijk beschikbaar in de Inschrijvingskassa.
- Wanneer Frontend een `session_updated` bericht stuurt, wordt het bestaande POS-product bijgewerkt (titel en/of prijs). `x_session_id` wordt als primaire sleutel gebruikt — een hernoeming maakt geen duplicaat aan.
- Wanneer Frontend een `session_deleted` bericht stuurt, wordt het POS-product **bewaard** (voor lopende transacties) en enkel gelogd. Er wordt geen product verwijderd.
- Na elke aanpassing ontvangt de actieve POS-sessie automatisch een bus-notificatie zodat het nieuwe product onmiddellijk zichtbaar is — zonder sessie-herstart.
- Wanneer een badge gescand wordt, stuurt de kassa een `user_sessions_request` naar Frontend om de ingeschreven sessies van de bezoeker op te halen. Bij ontvangst van `user_sessions_response` worden de bijhorende POS-producten aangemaakt of bijgewerkt.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat Frontend een `session_created` bericht stuurt met `session_id` en `title`

**Wanneer** `receiver.py` het bericht verwerkt

**Dan** is een POS-product met die titel beschikbaar in de Inschrijvingskassa

**En** wordt een bus-notificatie verstuurd naar de actieve POS-sessies

**Gegeven** dat Frontend een `session_updated` bericht stuurt met dezelfde `session_id` maar een gewijzigde titel of prijs

**Wanneer** `receiver.py` het bericht verwerkt

**Dan** wordt het bestaande POS-product bijgewerkt — er wordt geen duplicaat aangemaakt

**En** wordt een bus-notificatie verstuurd

**Gegeven** dat Frontend een `session_deleted` bericht stuurt

**Wanneer** `receiver.py` het bericht verwerkt

**Dan** blijft het POS-product bewaard en wordt enkel gelogd

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1. `receiver.py` luistert op `session_created`, `session_updated` en `session_deleted` routing keys vanuit Frontend.
2. `_ensure_session_product()` zoekt primair op `x_session_id` (overleeft hernoemen), met name-lookup als fallback voor bestaande producten zonder `x_session_id`.
3. Bij create/update: schrijf naam en prijs naar het POS-product; roep `kassa_notify_product_update` aan via Odoo bus zodat open POS-sessies het product direct zien.
4. Bij delete: log en ack — geen product verwijderen.
5. Na een succesvolle badge-scan: stuur `user_sessions_request` naar Frontend met `identity_uuid`; verwerk de `user_sessions_response` door `_ensure_session_product()` aan te roepen voor elke sessie in de respons.

**DEFINITION OF DONE:**

- [ ] `receiver.py` verwerkt `session_created`, `session_updated` en `session_deleted` correct
- [ ] `_ensure_session_product()` maakt nieuw product aan of update bestaand op basis van `x_session_id`; naam-fallback actief voor oudere producten
- [ ] Bus-notificatie (`kassa_notify_product_update`) verstuurd na create/update zodat de POS-sessie het product onmiddellijk toont
- [ ] `session_deleted`: POS-product bewaard, enkel gelogd
- [ ] `user_sessions_request` verstuurd na badge-scan met `identity_uuid`
- [ ] `user_sessions_response`: sessie-producten aangemaakt/bijgewerkt in Inschrijvingskassa

## **Story 23: Sessiescatalogus opvragen bij POS-opstart (Frontend integratie)**

> _MVP status: MVP_

_Als kassamedewerker wil ik dat bij het openen van een POS-sessie automatisch de volledige sessiescatalogus van Frontend wordt opgehaald, zodat alle beschikbare sessieproducten met de juiste prijzen direct beschikbaar zijn bij de eerste scan._

**ACCEPTATIECRITERIA:**

- Zodra `order_poller.py` een nieuw geopende POS-sessie detecteert (staat `opened`), verstuurt hij één `session_view_request` naar Frontend.
- Frontend antwoordt met een `session_view_response` die de volledige sessiescatalogus bevat. `receiver.py` verwerkt deze respons en zorgt dat alle sessieproducten aanwezig zijn in Odoo POS.
- Een herstart van de integratieservice triggert bij de volgende pollingcyclus automatisch een nieuwe `session_view_request` voor alle nog openstaande POS-sessies.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat een medewerker een nieuwe POS-sessie opstart in Odoo

**Wanneer** `order_poller.py` deze sessie voor de eerste keer detecteert tijdens een pollingcyclus

**Dan** wordt er één `session_view_request` verstuurd naar Frontend

**En** wordt de sessie-ID in de interne cache opgeslagen zodat geen dubbele aanvragen worden verstuurd

**Gegeven** dat Frontend antwoordt met een `session_view_response`

**Wanneer** `receiver.py` de respons verwerkt

**Dan** zijn alle sessies uit de catalogus beschikbaar als POS-product in Odoo

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1. `order_poller.check_pos_sessions()` polt elke cyclus op `pos.session` met staat `opened`.
2. Nieuwe sessie-ID's (niet in `_seen_pos_sessions`) triggeren een `session_view_request` XML naar Frontend.
3. De sessie-ID wordt toegevoegd aan `_seen_pos_sessions` (in-memory, reset bij herstart).
4. `receiver.py` verwerkt de binnenkomende `session_view_response` en roept `_ensure_session_product()` aan voor elke sessie.

**DEFINITION OF DONE:**

- [ ] `order_poller.check_pos_sessions()` detecteert nieuwe POS-sessies en verstuurt `session_view_request` naar Frontend
- [ ] Reeds geziene sessie-ID's worden niet opnieuw aangevraagd binnen dezelfde process-lifetime
- [ ] `receiver.py` verwerkt `session_view_response` en maakt sessieproducten aan in Odoo POS
- [ ] Herstart van de service triggert automatisch nieuwe aanvraag voor open sessies

## **EPIC 8: UITGEBREIDE WALLET & FACTURATIE FLOWS**

## **Story 24: Online saldo bijstorten via het CRM (Wallet Remote Topup)**

> _MVP status: MVP_

_Als bezoeker wil ik mijn badge-saldo online kunnen ophogen (via de website of een externe betaallink), zodat het extra tegoed direct beschikbaar is aan de bar zonder dat ik opnieuw een topup-product hoef te kopen._

**ACCEPTATIECRITERIA:**

- Als het CRM een `wallet_remote_topup` bericht stuurt voor een bezoeker met een actieve wallet-lease, wordt het opgegeven bedrag direct opgeteld bij `x_wallet_balance` in Odoo.
- Een `wallet_balance_update` XML wordt verstuurd naar Frontend zodat het nieuwe saldo onmiddellijk zichtbaar is op het scherm.
- Is de lease actief maar de `wallet_lease_grant` nog niet ontvangen (race-condition), dan wordt het bedrag geparkeerd in `x_pending_topup_balance` en samengevoegd zodra de lease-grant binnenkomt.
- Is er geen actieve lease (de bezoeker is nog niet ingescand), dan wordt de topup genegeerd en gelogd — er wordt geen saldo overschreven.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat een bezoeker een actieve wallet-lease heeft (`x_lease_active=True`) en de lease-grant is bevestigd (`x_lease_id` ingevuld)

**Wanneer** CRM een `wallet_remote_topup` bericht stuurt met een positief `add_amount`

**Dan** wordt `x_wallet_balance` in Odoo verhoogd met het opgegeven bedrag

**En** wordt een `wallet_balance_update` verstuurd naar Frontend

**Gegeven** dat de lease actief is maar de lease-grant nog niet bevestigd is (`x_lease_id` leeg)

**Wanneer** CRM een `wallet_remote_topup` bericht stuurt

**Dan** wordt het bedrag geparkeerd in `x_pending_topup_balance`

**En** wordt het samengevoegd bij ontvangst van `wallet_lease_grant`

**Gegeven** dat de bezoeker geen actieve lease heeft (`x_lease_active=False`)

**Wanneer** CRM een `wallet_remote_topup` bericht stuurt

**Dan** wordt de topup genegeerd en gelogd — geen saldowijziging

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1. `receiver.py` verwerkt `wallet_remote_topup` na XSD-validatie en idempotentie-check.
2. Zoek de partner op via `x_user_id`; controleer `x_lease_active` en `x_lease_id`.
3. Actieve lease met lease-grant bevestigd: roep `action_add_wallet_amount()` aan in Odoo en stuur `wallet_balance_update` naar `kassa.frontend.wallet`.
4. Actieve lease maar grant nog niet ontvangen: voeg `add_amount` toe aan `x_pending_topup_balance`.
5. Geen actieve lease: log en ack — geen saldowijziging.

**DEFINITION OF DONE:**

- [ ] `receiver.py` verwerkt `wallet_remote_topup` met XSD-validatie
- [ ] Actieve lease + grant bevestigd: `x_wallet_balance` verhoogd én `wallet_balance_update` verstuurd
- [ ] Race-condition: `add_amount` geparkeerd in `x_pending_topup_balance`; samengevoegd bij `wallet_lease_grant`
- [ ] Geen actieve lease: topup genegeerd, geen saldowijziging, gelogd
- [ ] Non-positief `add_amount` wordt stilletjes genegeerd
- [ ] Uitgaande XML valide tegen `schema_wallet_balance_update.xsd`

## **Story 25: Automatisch factuurverzoek voor bedrijfsklanten (B2B Auto-Invoice)**

> _MVP status: MVP_

_Als B2B-klant wil ik dat mijn aankopen aan de bar automatisch als factuurverzoek doorgestuurd worden naar het CRM, zodat ik niet telkens zelf aan de kassamedewerker hoef te vragen om een factuur._

**ACCEPTATIECRITERIA:**

- Voor bedrijfsklanten (`is_company=True` of klant heeft een bedrijf als ouder) activeert Odoo automatisch `to_invoice=True` bij het valideren van een POS-order.
- `order_poller.py` detecteert orders met `to_invoice=True` of een gekoppelde `account_move` en stuurt automatisch een `invoice_request` bericht — ook zonder expliciete aanvraag van de kassamedewerker.
- De `invoice_request` bevat de naam, het gesplitste adres (straatnaam en huisnummer apart), het land en het BTW-nummer van de klant.
- Is voor dezelfde order al een `invoice_request` verstuurd (`x_invoice_message_id` ingevuld), dan wordt er geen dubbele aanvraag gedaan.
- Anonieme orders en inschrijvingsbetalingen triggeren geen `invoice_request`.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat een POS-order in Odoo staat met `to_invoice=True`, een gekoppelde bedrijfsklant en `x_rabbitmq_sent=False`

**Wanneer** `order_poller.py` deze order detecteert

**Dan** wordt automatisch een `invoice_request` XML verstuurd naar `kassa.payments.invoice`

**En** wordt `x_invoice_message_id` opgeslagen op de order ter deduplicatie

**En** wordt `x_rabbitmq_sent=True` gezet na succesvolle verzending van alle berichten

**Gegeven** dat voor dezelfde order al een `invoice_request` werd verstuurd (`x_invoice_message_id` ingevuld)

**Wanneer** `order_poller.py` de order opnieuw detecteert

**Dan** wordt er geen tweede `invoice_request` aangemaakt

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1. In `order_poller.process_order()`: controleer `to_invoice` en `account_move`; sla op als `should_invoice`.
2. Als `should_invoice=True` en order niet anoniem en geen inschrijving: controleer `x_invoice_message_id` op duplicaten.
3. Bouw `invoice_request` XML op met klantgegevens: naam, gesplitst adres via `split_street_and_number()`, land (ISO-code), BTW-nummer. Valideer tegen `schema_invoice_request.xsd`.
4. Verstuur naar routing key `kassa.payments.invoice` en sla de `message_id` op in `x_invoice_message_id`.

**DEFINITION OF DONE:**

- [ ] `order_poller.py` verstuurt automatisch `invoice_request` bij `to_invoice=True` of `account_move` aanwezig — ook zonder expliciete aanvraag
- [ ] Adres correct gesplitst via `split_street_and_number()` in straatnaam en huisnummer
- [ ] Deduplicatie actief via `x_invoice_message_id` — geen dubbele aanvraag per order
- [ ] Anonieme orders en inschrijvingsbetalingen triggeren geen `invoice_request`
- [ ] Uitgaande XML valide tegen `schema_invoice_request.xsd`
- [ ] `x_invoice_message_id` opgeslagen op de order na succesvolle verzending

## **Story 26: BTW-nummer verplicht voor bedrijven**

> _MVP status: MVP_

_Als kassamedewerker wil ik dat het systeem bedrijfsinschrijvingen zonder BTW-nummer weigert en factuurverzoeken voor bedrijven zonder BTW-nummer blokkeert, zodat we nooit een onvolledig factuurverzoek naar het CRM sturen._

**ACCEPTATIECRITERIA:**

- Bij een inkomend `new_registration` bericht van het type `company`: als `vat_number` ontbreekt, wordt het bericht geweigerd met een `system_error` (code `invalid_xml_format`) naar `kassa.errors` en een `basic_nack(requeue=False)` naar de DLQ.
- Bij een `invoice_request` voor een klant van het type `company`: als het BTW-nummer leeg is in Odoo, wordt de `invoice_request` **niet** verstuurd. De order wordt gemarkeerd met een `x_rabbitmq_error` zodat de oorzaak traceerbaar is.
- Private klanten zijn niet onderworpen aan de BTW-verplichting.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat een `new_registration` bericht binnenkomt met `<type>company</type>` en zonder `<vat_number>`

**Wanneer** `receiver.py` het bericht valideert

**Dan** wordt een `system_error` met code `invalid_xml_format` verstuurd naar `kassa.errors`

**En** krijgt het bericht een `basic_nack(requeue=False)` naar de DLQ

**Gegeven** dat `order_poller.py` een `invoice_request` wil aanmaken voor een bedrijfsklant zonder BTW-nummer in Odoo

**Wanneer** de BTW-check uitgevoerd wordt

**Dan** wordt de `invoice_request` niet verstuurd

**En** wordt de order gemarkeerd met `x_rabbitmq_error` zodat de oorzaak traceerbaar is

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1. In `receiver.py` `process_new_registration()`: controleer bij `type=company` of `vat_number` aanwezig is. Ontbreekt het? Gooi een `ValueError` — de centrale foutafhandeling stuurt `system_error` en `basic_nack(requeue=False)`.
2. In `order_poller.py` `process_order()`: controleer bij `customer_type=company` of het `vat`-veld ingevuld is vóór het bouwen van de `invoice_request`. Zo niet: sla `x_rabbitmq_error` op op de order en sla de `invoice_request` over.
3. Private klanten (`is_company=False`, geen bedrijfsouder): BTW-check is niet van toepassing.

**DEFINITION OF DONE:**

- [ ] `receiver.py` weigert `new_registration` van type `company` zonder `vat_number` met `system_error` + `basic_nack(requeue=False)`
- [ ] `order_poller.py` blokkeert `invoice_request` voor bedrijfsklant zonder BTW-nummer in Odoo
- [ ] Geblokkeerde `invoice_request`: `x_rabbitmq_error` gezet op de order voor traceerbaarheid
- [ ] Private klanten zijn niet onderworpen aan de BTW-verplichting
