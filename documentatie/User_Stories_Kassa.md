# Uitgewerkte User Stories

Team KassaModule (Odoo POS)

Versie: Definitief (Technische Revisie)

Project: Integratieproject Desideriushogeschool 2026

Datum: 25 maart 2026

# **EPIC 1: PROFIELEN & INSCHRIJVINGEN (INKOMENDE FLOWS)**

## **Story 1: Nieuwe Inschrijvingen automatisch inladen**

> _MVP status: MVP_

_Als kassamedewerker wil ik dat nieuwe inschrijvingen vanuit de website automatisch in mijn kassasysteem verschijnen, zodat ik bezoekers bij aankomst direct kan opzoeken zonder hun gegevens handmatig te hoeven overtypen._

**ACCEPTATIECRITERIA:**

- Het receiver.py script luistert op de achtergrond naar new_registration berichten vanuit het CRM via de RabbitMQ kassa.incoming.
- Elk inkomend bericht wordt gevalideerd tegen het XSD-schema. Is het bericht ongeldig? Dan wordt het weggegooid en een system_error verstuurd naar kassa.errors.
- De kassa controleert via het unieke x_user_id of de klant al bestaat. Bestaat hij? Update zijn gegevens. Bestaat hij niet? Maak een nieuw profiel aan met alle gegevens uit het bericht (naam, e-mail, geboortedatum (date_of_birth), optioneel bedrijfsnaam en BTW-nummer).
- Na succesvolle verwerking wordt een basic_ack gestuurd naar RabbitMQ zodat het bericht niet opnieuw aangeboden wordt.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat receiver.py verbonden is met RabbitMQ op kassa.incoming

**En** er een geldig new_registration XML-bericht binnenkomt met user_id, email, first_name, last_name (via het contact-element), date_of_birth en optioneel company_name en vat_number

**En** er bestaat nog geen klant in Odoo met dit x_user_id

**Wanneer** receiver.py het bericht verwerkt

**Dan** wordt er een nieuw klantprofiel aangemaakt in Odoo (res.partner) met alle velden correct ingevuld

**En** stuurt receiver.py een basic_ack naar RabbitMQ

**Gegeven** dat hetzelfde bericht binnenkomt maar de klant al bestaat in Odoo

**Wanneer** receiver.py het bericht verwerkt

**Dan** worden de bestaande gegevens overschreven — er wordt geen duplicaat aangemaakt

**Gegeven** dat een bericht binnenkomt dat niet voldoet aan schema_new_registration.xsd

**Wanneer** receiver.py de XSD-validatie uitvoert

**Dan** wordt het bericht weggegooid, een system_error met code invalid_xml_format verstuurd naar kassa.errors, en toch een basic_ack gestuurd

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1. Zorg dat het ontvangstscript continu luistert op de inkomende wachtrij voor nieuwe berichten.
2. Controleer elk binnenkomend bericht op de correcte structuur via het bijhorende XSD-schema. Is het bericht fout? Gooi het weg en stuur een foutmelding naar de Controlroom.
3. Zoek de klant op in Odoo via zijn uniek klantnummer. Bestaat hij al? Update zijn gegevens. Bestaat hij nog niet? Maak een nieuw profiel aan met alle gegevens uit het bericht.
4. Bevestig aan de wachtrij dat het bericht verwerkt is, zodat het niet opnieuw aangeboden wordt.

## **Story 2: Klantgegevens up-to-date houden**

> _MVP status: MVP_

_Als bezoeker wil ik dat wijzigingen in mijn profiel (zoals een nieuw e-mailadres of bedrijfsnaam) direct worden doorgegeven aan de kassa, zodat mijn facturen of kassatickets altijd de juiste gegevens bevatten._

**ACCEPTATIECRITERIA:**

- Als iemand zijn gegevens aanpast in het centrale CRM, krijgt de kassa via een profile_update bericht bericht van.
- De kassa zoekt de betreffende klant op via zijn uniek x_user_id.
- De velden naam, e-mail, geboortedatum, bedrijfsnaam en BTW-nummer worden direct overschreven met de nieuwe waarden.
- Wordt de klant niet gevonden? Dan wordt een system_error met code profile_not_found verstuurd naar kassa.errors en toch een basic_ack gestuurd.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat een klantprofiel met x_user_id = X bestaat in Odoo

**Wanneer** er een profile_update bericht binnenkomt met diezelfde x_user_id en gewijzigde gegevens

**Dan** worden de velden first_name, last_name (via het contact-element), email, date_of_birth en eventueel company_name en vat_number overschreven in het bestaande Odoo-profiel

**Gegeven** dat een profile_update bericht binnenkomt met een x_user_id dat niet bestaat in Odoo

**Wanneer** receiver.py het bericht verwerkt

**Dan** wordt een system_error met code profile_not_found verstuurd naar kassa.errors

**En** stuurt receiver.py toch een basic_ack naar RabbitMQ

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1. Herken het profielwijzigingsbericht in het ontvangstscript en valideer de structuur via het XSD-schema.
2. Zoek de klant op in Odoo via zijn uniek klantnummer.
3. Overschrijf de gewijzigde gegevens (naam, e-mail, bedrijfsnaam, BTW-nummer, geboortedatum) in het lokale profiel.
4. Wordt de klant niet gevonden? Stuur een foutmelding naar de Controlroom en bevestig toch dat het bericht verwerkt is.

## **Story 3: Geannuleerde inschrijvingen blokkeren**

> _MVP status: MVP_

_Als organisatie wil ik dat bezoekers die hun ticket annuleren, ook in de kassa op "inactief" worden gezet, zodat zij niet per ongeluk toch nog aan de kassa gekoppeld kunnen worden._

**ACCEPTATIECRITERIA:**

- De kassa ontvangt annuleringen exclusief vanuit het CRM-systeem via een cancel_registration bericht.
- Bij een annulering zoekt de kassa het profiel op via x_user_id en zet de active flag in Odoo op False.
- Wordt de klant niet gevonden? Dan wordt een system_error met code profile_not_found verstuurd naar kassa.errors en toch een basic_ack gestuurd.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat een klantprofiel met x_user_id = X bestaat in Odoo

**Wanneer** het CRM een cancel_registration bericht stuurt met diezelfde x_user_id

**Dan** wordt de active flag van dat klantprofiel in Odoo op False gezet

**En** stuurt receiver.py een basic_ack naar RabbitMQ

**Gegeven** dat een cancel_registration bericht binnenkomt met een x_user_id dat niet bestaat in Odoo

**Wanneer** receiver.py het bericht verwerkt

**Dan** wordt een system_error met code profile_not_found verstuurd naar kassa.errors

**En** stuurt receiver.py toch een basic_ack naar RabbitMQ

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1. Herken het annuleringsbericht in het ontvangstscript en valideer de structuur via het XSD-schema.
2. Zoek de klant op in Odoo via zijn uniek klantnummer.
3. Zet het klantprofiel op inactief zodat de medewerker weet dat deze persoon niet meer verwacht wordt.
4. Wordt de klant niet gevonden? Stuur een foutmelding naar de Controlroom en bevestig toch dat het bericht verwerkt is.

# **EPIC 2: KASSAVERKOOP & BETALINGEN (UITGAANDE FLOWS)**

## **Story 4: Anoniem een drankje kopen**

> _MVP status: MVP_

_Als kassamedewerker wil ik bestellingen aan de bar supersnel kunnen afrekenen voor mensen zonder account, zodat de wachtrijen kort blijven._

**ACCEPTATIECRITERIA:**

- De medewerker slaat producten aan zonder een klant te selecteren.
- De bestelling wordt succesvol afgerekend en er rolt een bonnetje uit.
- poller.py pikt de afgeronde bestelling op en verstuurt een consumption_order met is_anonymous=true en is_company_linked=false naar kassa.payments, gevolgd door een payment_registered bericht.
- De bestelling wordt in Odoo gemarkeerd als verzonden (x_rabbitmq_sent=True) na succesvolle doorstuur.
- Lukt het versturen niet? Dan worden beide berichten opgeslagen in outbox.json.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat er een afgeronde pos.order in Odoo staat met state=done, x_rabbitmq_sent=False en geen gekoppelde partner_id

**Wanneer** poller.py deze order detecteert

**Dan** wordt een consumption_order XML verstuurd naar kassa.payments met is_anonymous=true en is_company_linked=false

**En** wordt daarna een payment_registered XML verstuurd naar dezelfde queue

**En** wordt x_rabbitmq_sent=True gezet op de order in Odoo

**Gegeven** dat RabbitMQ niet bereikbaar is op het moment van versturen

**Wanneer** poller.py de berichten probeert te sturen

**Dan** worden beide berichten opgeslagen in outbox.json

**En** wordt x_rabbitmq_sent niet op True gezet

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1. Laat het pollerscript elke paar seconden controleren of er nieuwe afgeronde bestellingen zijn in Odoo die nog niet doorgestuurd zijn.
2. Controleer per bestelling of er een klant aan gekoppeld is. Is dat niet het geval? Markeer de bestelling als anoniem (is_anonymous=true, is_company_linked=false).
3. Bouw het uitgaande bericht op conform het XSD-schema en stuur het naar de juiste wachtrij richting het CRM. Stuur daarna ook het betalingsbericht door.
4. Markeer de bestelling in Odoo als verzonden zodat ze niet opnieuw opgepikt wordt.
5. Lukt het versturen niet? Sla beide berichten tijdelijk op in de lokale buffer.

## **Story 5: Bestellen op bedrijfsnaam (met badge)**

> _MVP status: MVP_

_Als zakelijke bezoeker wil ik dat mijn bestellingen aan de bar direct geregistreerd worden op mijn naam, zodat de rekening netjes naar mijn werkgever gaat of van mijn badge-tegoed af gaat._

**ACCEPTATIECRITERIA:**

- De bestelling wordt in de kassa gekoppeld aan een geïdentificeerde klant.
- Na het afrekenen stuurt poller.py een consumption_order bericht met is_anonymous=false en is_company_linked=true, en een payment_registered bericht met payment_context=consumption naar kassa.payments.
- Als de klant afrekent met digitaal tegoed (Badge Wallet), verlaagt poller.py lokaal het saldo (x_wallet_balance) in Odoo én stuurt een wallet_balance_update bericht naar frontend.payments.
- De bestelling wordt in Odoo gemarkeerd als verzonden (x_rabbitmq_sent=True) na succesvolle doorstuur.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat er een afgeronde pos.order in Odoo staat met state=done, x_rabbitmq_sent=False en een gekoppelde partner_id van een bedrijfsklant (is_company=True)

**Wanneer** poller.py deze order detecteert

**Dan** wordt een consumption_order XML verstuurd naar kassa.payments met is_anonymous=false en is_company_linked=true

**En** wordt daarna een payment_registered XML verstuurd naar dezelfde queue

**En** wordt x_rabbitmq_sent=True gezet op de order in Odoo

**Gegeven** dat de betaalmethode van de order Badge Wallet was

**Wanneer** poller.py de order verwerkt

**Dan** wordt het x_wallet_balance veld van de klant in Odoo verlaagd met het bestelbedrag

**En** wordt een wallet_balance_update XML verstuurd naar frontend.payments

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1. Laat het pollerscript elke paar seconden controleren of er nieuwe afgeronde bestellingen zijn die nog niet doorgestuurd zijn.
2. Controleer of er een klant gekoppeld is aan de bestelling en of het een bedrijfsklant is.
3. Bouw het bestellingsbericht op conform het XSD-schema met de juiste klantinfo en stuur naar de wachtrij richting het CRM. Stuur daarna ook het betalingsbericht door.
4. Controleer of er betaald werd met badge-tegoed. Zo ja, verlaag het lokale saldo in Odoo en stuur een saldo-update naar de website.
5. Markeer de bestelling als verzonden in Odoo.

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

1. Herken in het pollerscript dat het om een inschrijvingsbetaling gaat in plaats van een consumptie.
2. Bouw het betalingsbericht op met de context 'registration' en stuur naar de wachtrij richting het CRM.
3. Stuur tegelijkertijd een betaald-statusbericht naar de wachtrij richting de website.
4. Markeer de bestelling als verzonden in Odoo.

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

## **Story 8: Een aankoop ongedaan maken (Terugbetaling)**

> _MVP status: MVP_

_Als kassamedewerker wil ik een verkeerd aangeslagen drankje direct kunnen annuleren en het geld teruggeven, zodat de klant niet te veel betaalt._

**ACCEPTATIECRITERIA:**

- De medewerker registreert een terugbetaling (negatief bedrag) in de kassa.
- De kassa verstuurt een refund_processed bericht naar kassa.payments, gekoppeld aan het originele transactienummer.
- Als de klant oorspronkelijk met badge-tegoed had betaald, wordt het x_wallet_balance in Odoo verhoogd en een wallet_balance_update verstuurd naar frontend.payments.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat er een afgeronde pos.order staat in Odoo met een negatief totaalbedrag en x_rabbitmq_sent=False
**Wanneer** poller.py deze order detecteert
**Dan** wordt een refund_processed XML verstuurd naar kassa.payments, gekoppeld aan het originele transactie-ID
**En** wordt x_rabbitmq_sent=True gezet op de order in Odoo

**Gegeven** dat de originele betaling via Badge Wallet was
**Wanneer** poller.py de terugbetaling verwerkt
**Dan** wordt het x_wallet_balance veld van de klant in Odoo verhoogd met het terugbetaalde bedrag
**En** wordt een wallet_balance_update XML verstuurd naar frontend.payments

**Gegeven** dat een order in Odoo een negatief totaalbedrag heeft en geen gekoppelde klant heeft (anoniem)
**Wanneer** poller.py deze order detecteert
**Dan** wordt een refund_processed XML verstuurd zonder `<user_id>`
**En** is de methode cash of card_reversal (nooit badge_wallet)

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1. Herken in het pollerscript bestellingen met een negatief totaalbedrag als terugbetalingen.
2. Bouw het terugbetalingsbericht op conform het XSD-schema, gekoppeld aan het originele transactienummer, en stuur naar de wachtrij richting het CRM.
3. Controleer of de originele betaling via badge-tegoed was. Zo ja, verhoog het lokale saldo in Odoo en stuur een saldo-update naar de website.
4. Markeer de terugbetaling als verzonden in Odoo.

# **EPIC 3: BADGES & SALDO (IOT & WALLET)**

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

1. Zorg dat het ontvangstscript luistert naar scanberichten van de IoT-scanner via de inkomende wachtrij en valideer het bericht via het XSD-schema.
2. Zoek het badge-ID op in Odoo en haal het bijhorende klantprofiel op.
3. Wordt de badge niet herkend? Verwijs door naar de foutafhandeling van Story 12.
4. Bevestig aan de wachtrij dat het bericht verwerkt is.

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

1. Detecteer in het pollerscript wanneer een nieuw badge-ID wordt opgeslagen bij een klantprofiel in Odoo.
2. Bouw het badge-koppelingssbericht op conform het XSD-schema.
3. Stuur het bericht naar de wachtrij richting het CRM zodat alle systemen de nieuwe koppeling kennen.
4. Markeer de actie als verzonden in Odoo.

## **Story 11: Digitaal tegoed (Top-up) kopen**

> _MVP status: secundair (Niet strikt MVP)_

_Als bezoeker wil ik met cash of mijn bankpas virtueel geld op mijn badge kunnen zetten, zodat ik later op de avond makkelijk drankjes kan afrekenen._

**ACCEPTATIECRITERIA:**

- De medewerker slaat een Top-up product (0% BTW) aan in Odoo POS.
- Het bedrag wordt opgeteld bij het x_wallet_balance van de klant in Odoo.
- Er wordt een consumption_order bericht verstuurd naar kassa.payments richting het CRM.
- Er wordt een wallet_balance_update bericht verstuurd naar frontend.payments richting de website.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat er een afgeronde pos.order staat in Odoo met een product van 0% BTW en x_rabbitmq_sent=False

**En** de order heeft een gekoppelde klant met een x_badge_id

**Wanneer** poller.py deze order detecteert

**Dan** wordt het x_wallet_balance van de klant in Odoo verhoogd met het aankoopbedrag

**En** wordt een consumption_order XML verstuurd naar kassa.payments

**En** wordt een wallet_balance_update XML verstuurd naar frontend.payments

**En** wordt x_rabbitmq_sent=True gezet op de order in Odoo

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1. Herken in het pollerscript een Top-up aankoop op basis van het 0% BTW-tarief van het product.
2. Verhoog het lokale badge-saldo van de klant in Odoo met het aangekochte bedrag.
3. Bouw het bestellingsbericht op conform het XSD-schema en stuur naar de wachtrij richting het CRM.
4. Stuur tegelijkertijd een saldo-updatebericht naar de wachtrij richting de website.
5. Markeer de bestelling als verzonden in Odoo.

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

# **EPIC 4: FOUTEN & SYSTEEMMONITORING (RESILIENCE & CONTROLROOM)**

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
3. Controleer bij het herstellen van de verbinding of er berichten in de buffer staan en stuur deze alsnog door in volgorde.
4. Heartbeat-berichten worden nooit gebufferd — die worden bij falen gewoon weggegooid.

## **Story 14: Kassa beschermen tegen foute data**

> _MVP status: MVP_

_Als beheerder wil ik dat de kassa onleesbare of onbekende berichten vanuit andere systemen netjes negeert en rapporteert, zodat de kassa niet crasht._

**ACCEPTATIECRITERIA:**

- Elk inkomend bericht wordt gevalideerd via het bijhorende XSD-schema.
- Klopt de structuur niet? Dan wordt het bericht weggegooid en een system_error met code invalid_xml_format verstuurd naar kassa.errors.
- Is het berichttype onbekend? Dan wordt een system_error met code unknown_message_type verstuurd naar kassa.errors.
- In beide gevallen krijgt het bericht een basic_ack zodat de queue niet geblokkeerd wordt.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat een inkomend bericht op kassa.incoming niet voldoet aan het XSD-schema

**Wanneer** receiver.py de validatie uitvoert

**Dan** wordt het bericht weggegooid en een system_error met code invalid_xml_format verstuurd naar kassa.errors

**En** stuurt receiver.py een basic_ack zodat het bericht de queue niet blokkeert

**Gegeven** dat een inkomend bericht een onbekend type heeft

**Wanneer** receiver.py het berichttype controleert

**Dan** wordt het bericht weggegooid en een system_error met code unknown_message_type verstuurd naar kassa.errors

**En** stuurt receiver.py een basic_ack

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1. Controleer elk inkomend bericht eerst op geldige XML-structuur via het bijhorende XSD-schema.
2. Is het berichttype onbekend of klopt de structuur niet? Gooi het bericht weg en stuur een foutmelding met de juiste foutcode naar de Controlroom.
3. Bevestig aan de wachtrij dat het bericht verwerkt is zodat het niet blijft herhalen.

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
3. Stuur een foutbericht met de code offline_queue_full naar de Controlroom zodat IT gewaarschuwd wordt.
4. De kassa blijft gewoon verkopen — enkel het doorsturen stopt.

# **EPIC 5: UITGEBREIDE RANDGEVALLEN (TECHNICAL SAD PATHS)**

## **Story 17: Alcoholcontrole**

> _MVP status: Secundair_

_Als kassamedewerker wil ik een automatische waarschuwing bij verkoop van alcohol aan minderjarigen, zodat ik de wettelijke leeftijdscontrole niet kan missen._

**ACCEPTATIECRITERIA:**

- De kassa berekent de actuele leeftijd op basis van het `x_date_of_birth` veld in Odoo (geboortedatum, type Date).
- Bij producten met de vlag `x_age_restricted` en berekende leeftijd < 18 jaar verschijnt een blokkerende pop-up.
- De kassamedewerker kan de blokkering handmatig overschrijven met een reden.
- **Let op:** Vereist custom POS JavaScript — dit is een bewuste uitzondering op de "geen code in Odoo" architectuurrestrictie.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat een klant ingelogd is via badge-scan en `x_date_of_birth` aanwezig is in Odoo

**En** de kassamedewerker voegt een product toe met de vlag `x_age_restricted`

**Wanneer** de berekende leeftijd van de klant < 18 jaar is

**Dan** verschijnt een blokkerende pop-up met de melding dat de klant minderjarig is

**En** kan de medewerker de verkoop enkel doorzetten na manuele bevestiging met reden

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1. Bereken de actuele leeftijd op basis van `x_date_of_birth` op het moment van scan.
2. Controleer bij elk toe te voegen product of het de `x_age_restricted` vlag draagt.
3. Is de klant jonger dan 18? Toon een blokkerende pop-up en vereist manuele bevestiging.
4. Implementeer als custom POS JavaScript (uitzondering op architectuurrestrictie).

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

1. Controleer vlak voor elke saldo-afschrijving of er een klant gekoppeld is aan de bestelling.
2. Is de bestelling anoniem maar wordt er toch via badge-tegoed betaald? Stop de afschrijving onmiddellijk.
3. Stuur een foutmelding naar de Controlroom.
4. Markeer de bestelling als afgehandeld zodat ze niet blijft hangen.

## **Story 20: Verbindingsfouten direct alarmeren**

> _MVP status: MVP_

_Als IT-beheerder wil ik dat verbindingsfouten met Odoo direct als foutmelding naar het centrale dashboard rollen, zodat wij problemen snel kunnen oplossen._

**ACCEPTATIECRITERIA:**

- Zodra het script de Odoo XML-RPC API niet kan bereiken, wordt dit gedetecteerd.
- Er wordt een system_error bericht met code odoo_api_error verstuurd naar kassa.errors.
- Het script pauzeert één seconde voor een nieuwe poging om een oneindige foutenlus te voorkomen.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat poller.py of receiver.py een Odoo XML-RPC aanroep uitvoert

**En** Odoo is niet bereikbaar of gooit een exception

**Wanneer** de fout wordt opgevangen

**Dan** wordt een system_error met code odoo_api_error verstuurd naar kassa.errors

**En** pauzeert het script één seconde voor een nieuwe poging zodat er geen oneindige foutenlus ontstaat

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1. Zorg voor foutafhandeling rondom alle communicatie met Odoo.
2. Lukt het ophalen of wegschrijven van data niet? Bouw een foutbericht op met de code odoo_api_error en stuur naar de monitoringswachtrij.
3. Pauzeer de verwerking kort zodat het systeem niet in een oneindige foutenlus terechtkomt.
