# Uitgewerkte User stories

**Team KassaModule (Odoo POs)**

**Versie:** Definitief (Technische Revisie)

**Project:** Integratieproject Desideriushogeschool 2026

**Datum:** 25 maart 2026

EPIC 1: PROFIELEN & INSCHRIJVINGEN (INKOMENDE FLOWS)

# story 1: Nieuwe Inschrijvingen automatisch inladen

**MVP status: MVP**

_Als kassamedewerker wil ik dat nieuwe inschrijvingen vanuit de website automatisch in mijn kassasysteem verschijnen, zodat ik bezoekers bij aankomst direct kan opzoeken zonder hun gegevens handmatig te hoeven overtypen._

**ACCEPTATIECRITERIA:**

- Het receiver.py script luistert op de achtergrond naar new_registration berichten vanuit het CRM via de RabbitMQ queue.incoming.
- Zodra er een inschrijving binnenkomt, maakt de kassa stilletjes een nieuw klantprofiel aan in de lokale database.
- Het systeem onthoudt het unieke klantnummer, zodat we de klant overal in het systeem kunnen herkennen.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat het kassasysteem is opgestart en verbonden is.

**Wanneer** er een new_registration bericht vanuit het CRM binnenkomt.

**Dan** maakt de kassa direct een profiel aan voor deze bezoeker, klaar voor gebruik aan de inkom.

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1.  Zorg dat het receiver.py script luistert naar de inkomende RabbitMQ wachtrij.
2.  Haal de klantgegevens en het unieke user_id uit het inkomende XML-bericht.
3.  Gebruik de Odoo API om te controleren of de klant al bestaat. Zo niet, maak een nieuw profiel aan in de database.

# story 2: Klantgegevens up-to-date houden

**MVP status: MVP**

_Als bezoeker wil ik dat wijzigingen in mijn profiel (zoals een nieuw e-mailadres of bedrijfsnaam) direct worden doorgegeven aan de kassa, zodat mijn facturen of kassatickets altijd de juiste gegevens bevatten._

**ACCEPTATIECRITERIA:**

- Als iemand zijn gegevens aanpast in het centrale CRM, krijgt de kassa hier bericht van.
- De kassa zoekt de betreffende klant op in zijn eigen systeem.
- Oude gegevens worden direct overschreven met de nieuwe, actuele gegevens.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat een bezoeker al in de kassa staat.

**Wanneer** er een update-bericht vanuit het CRM binnenkomt met nieuwe gegevens.

**Dan** past de kassa het lokale profiel direct aan met de nieuwe naam of het nieuwe e- mailadres.

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1.  Vang het profile_update bericht op in het receiver-script.
2.  Gebruik de Odoo API om de klant op te zoeken via zijn externe ID (x_user_id).
3.  Stuur een update-actie naar de database om de veranderde velden te overschrijven.

# story 3: Geannuleerde inschrijvingen blokkeren

**MVP status: MVP**

_Als organisatie wil ik dat bezoekers die hun ticket annuleren, ook in de kassa op "inactief" worden gezet, zodat zij niet per ongeluk toch nog naar binnen kunnen of om betaling worden gevraagd._

**ACCEPTATIECRITERIA:**

- De kassa ontvangt annuleringen exclusief vanuit het CRM-systeem.

- Bij een annulering zoekt de kassa het profiel op en blokkeert of deactiveert dit voor het betreffende evenement.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat een bezoeker in de kassa geregistreerd staat voor een evenement.

**Wanneer** deze bezoeker zijn inschrijving annuleert.

**Dan** markeert het kassasysteem het profiel als inactief, zodat de medewerker weet dat deze persoon niet meer verwacht wordt.

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1.  Herken het cancel_registration bericht zodra het binnenkomt.
2.  Zoek de specifieke klant op via de API.
3.  Zet het Odoo-profiel op 'inactief' zodat de kassa dit account niet meer als actieve bezoeker beschouwt.

EPIC 2: KASSAVERKOOP & BETALINGEN (UITGAANDE FLOWS)

# story 4: Anoniem een drankje kopen

**MVP status: MVP**

_Als kassamedewerker wil ik bestellingen aan de bar supersnel kunnen afrekenen voor mensen zonder account, zodat de wachtrijen kort blijven._

**ACCEPTATIECRITERIA:**

- De medewerker slaat producten aan zonder een klant te selecteren.
- De bestelling wordt succesvol afgerekend en er rolt een bonnetje uit.
- De kassa geeft op de achtergrond aan het centrale systeem door dat er een verkoop is gedaan, maar vermeldt expliciet dat dit een "anonieme aankoop" is.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat een bezoeker een biertje bestelt en geen badge of account heeft.

**Wanneer** de barman de bestelling als betaald markeert.

**Dan** stuurt de kassa de financiële data door naar de administratie, maar laat het klant- gedeelte helemaal leeg.

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1.  Laat het poller.py script periodiek checken op nieuwe, afgeronde bestellingen in Odoo.
2.  Controleer of de bestelling géén gekoppelde klant heeft.
3.  Bouw in dat geval de uitgaande XML zónder het klantblok (is_anonymous=true) en stuur deze naar de uitgaande wachtrij. Markeert de order lokaal als verzonden.

# story 5: Bestellen op bedrijfsnaam (met badge)

**MVP status: MVP**

_Als zakelijke bezoeker wil ik dat mijn bestellingen aan de bar direct geregistreerd worden op mijn naam, zodat de rekening netjes naar mijn werkgever gaat of van mijn badge- tegoed af gaat._

**ACCEPTATIECRITERIA:**

- De bestelling wordt in de kassa gekoppeld aan een geïdentificeerde klant.
- Na het afrekenen stuurt de kassa een consumption_order bericht en een payment_registered bericht (met payment_context=consumption) naar het CRM.
- Als de klant afrekent met digitaal tegoed (badge), verlaagt poller.py lokaal het saldo (x_wallet_balance) in Odoo én geeft dit door aan de website via een wallet_balance_update bericht.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat een klant met een account een bestelling plaatst.

**Wanneer** de bestelling succesvol is verwerkt in de kassa.

**Dan** wordt de administratie in het CRM bijgewerkt, en als er tegoed is gebruikt, daalt het virtuele saldo direct.

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1.  Haal de ordergegevens en de bedrijfslink van de klant op via de API in poller.py.
2.  Verstuur de consumption_order en payment_registered berichten naar het CRM via de routing key kassa.payments.consumption.

3\. Check of de betaalmethode "Badge Wallet" was. Zo ja, trek het bedrag lokaal af van het Odoo saldo en push een saldo-update XML naar de Drupal wachtrij.

# story 6: Inkomticket betalen aan de deur

**MVP status: MVP**

_Als bezoeker die zijn ticket nog niet online betaald heeft, wil ik dit veilig aan de inkombalie kunnen doen, zodat ik alsnog naar binnen mag en de website weet dat ik betaald heb._

**ACCEPTATIECRITERIA:**

- De kassamedewerker zoekt de openstaande inschrijving op en rekent deze af.
- Het kassasysteem vertelt de website (Drupal) direct dat deze persoon betaald heeft.
- Het systeem vertelt het CRM dat het inschrijvingsgeld binnen is (zonder eigen factuur te maken).

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat een bezoeker aan de kassa staat met een onbetaalde registratie.

**Wanneer** de bezoeker contant of met pin betaalt.

**Dan** synchroniseert de kassa direct met de website en de administratie dat deze persoon betaald heeft.

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1.  Vang deze betaling in de scripts apart af (het gaat om registraties, niet om drankjes).
2.  Stuur een betaalbevestiging naar het CRM waarbij je expliciet aangeeft dat het de context 'registration' heeft.
3.  Stuur direct daarnaast een "betaald"-status bericht naar de frontend-wachtrij.

# story 7: Factuur vragen voor een drankje

**MVP status: MVP**

_Als particuliere bezoeker wil ik aan de bar kunnen vragen om een officiële factuur van mijn aankoop, zodat ik deze kan inbrengen als onkosten._

**ACCEPTATIECRITERIA:**

- De kassa maakt zelf geen facturen, maar verzamelt enkel de adresgegevens van de klant.
- Zodra de bestelling is afgerond, stuurt de kassa een speciaal "factuur-verzoek" naar het CRM.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat een particuliere bezoeker na het afrekenen om een factuur vraagt.

**Wanneer** de medewerker dit registreert in de kassa.

**Dan** verzendt de kassa de benodigde gegevens automatisch naar de systemen die de factuur genereren.

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1.  Herken vanuit de Odoo interface of een bestelling is gemarkeerd voor een factuur.
2.  Haal de benodigde adresgegevens van de klant op via de API.
3.  Bouw een specifiek invoice_request bericht en plaats dit op de wachtrij richting het CRM.

# story 8: Een aankoop ongedaan maken (Terugbetaling)

**MVP status: MVP**

_Als kassamedewerker wil ik een verkeerd aangeslagen drankje direct kunnen annuleren en het geld teruggeven, zodat de klant niet te veel betaalt._

**ACCEPTATIECRITERIA:**

- De medewerker slaat een "min-bedrag" (refund) aanslaat in de kassa.
- De kassa geeft aan de boekhouding door dat deze specifieke transactie is teruggedraaid.
- Als de klant met digitaal tegoed had betaald, stelt de kassa dit saldo weer automatisch naar boven bij.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat een klant klaagt over een verkeerde bestelling.

**Wanneer** de kassa een terugbetaling registreert.

**Dan** wordt het CRM geïnformeerd en krijgt de klant zijn digitale tegoed terug.

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1.  Detecteer bestellingen met een negatief totaalbedrag in de backend.
2.  Stuur een refund-bericht naar het CRM, en link dit aan het originele transactie-ID.
3.  Controleer de betaalmethode: als dit de badge-wallet was, voer dan een API-actie uit om het klantensaldo weer te verhogen.

EPIC 3: BADGES & SALDO (IOT & WALLET)

# story 9: De fysieke badge gebruiken aan de bar

**MVP status: secundair (Niet strikt MVP)**

_Als kassamedewerker wil ik dat de kassa de klant direct herkent zodra de scanner zijn badge leest, zodat ik geen namen hoef in te typen en direct kan verkopen._

**ACCEPTATIECRITERIA:**

- Zodra de scanner een badge ziet, ontvangt de kassa het scannummer.
- De kassa zoekt het scannummer razendsnel op in de eigen database.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat een klant met een gekoppelde badge aan de bar verschijnt.

**Wanneer** de badge gescand wordt door de hardware.

**Dan** opent het kassascherm direct het juiste profiel.

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1.  Zorg dat het receiver-script luistert naar scanberichten vanuit de IoT-hardware.
2.  Gebruik de database API om lokaal de klant bij deze badge te zoeken.
3.  Zorg dat the gevonden klantinformatie op het POS-scherm van de medewerker verschijnt.

# story 10: Een nieuwe badge uitgeven

**MVP status: secundair (Niet strikt MVP)**

_Als baliemedewerker wil ik bij aankomst van een gast een blanco badge kunnen pakken en deze aan zijn account koppelen, zodat hij direct kan betalen op het evenement._

**ACCEPTATIECRITERIA:**

- De medewerker voert in het systeem het nummer van de badge in bij de klant.
- De kassa vertelt de overige systemen direct dat deze badge vanaf nu bij deze persoon hoort.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat een bezoeker zich aanmeldt en een badge krijgt.

**Wanneer** de medewerker de badge linkt in het kassasysteem.

**Dan** wordt deze koppeling direct wereldkundig gemaakt binnen de hele IT-infrastructuur.

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1.  Zorg voor een detectiemechanisme dat signaleert wanneer er een nieuw badgenummer in een klantprofiel wordt opgeslagen.
2.  Bouw het badge_assigned bericht op en stuur dit naar de centrale wachtrij.

# story 11: Digitaal tegoed (Top-up) kopen

**MVP status: secundair (Niet strikt MVP)**

_Als bezoeker wil ik met cash of mijn bankpas virtueel geld op mijn badge kunnen zetten, zodat ik later op de avond makkelijk drankjes kan afrekenen._

**ACCEPTATIECRITERIA:**

- De medewerker slaat een "Top-up" product (0% BTW) aan.
- Het bedrag wordt virtueel opgeteld bij het saldo van de bezoeker.
- Er wordt direct een wallet_balance_update bericht naar de frontend (Drupal) gestuurd.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat een bezoeker 20 euro wil opladen.

**Wanneer** de medewerker de aankoop succesvol afrondt.

**Dan** registreert de kassa de tegoedverhoging en informeert de website.

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1.  Laat poller.py via get_tax_rate() detecteren of een product 0% BTW heeft, en voeg in dat geval automatisch de tag item_type=wallet_topup toe aan het consumption_order bericht.
2.  Gebruik de Odoo API om het lokale portefeuille-saldo van de klant te verhogen.
3.  Verstuur het consumption_order bericht naar het CRM (pos.payments queue) en push een wallet_balance_update bericht naar de website (frontend.payments queue).

# story 12: Wat als we een badge niet kennen?

**MVP status: secundair (Niet strikt MVP)**

_Als kassamedewerker wil ik dat het systeem niet vastloopt als een bezoeker per ongeluk een badge scant die niet in ons systeem staat._

**ACCEPTATIECRITERIA:**

- Als een badge onbekend is, probeert de kassa dit niet eindeloos opnieuw.
- Het systeem slaat onzichtbaar alarm bij de IT-dienst en stopt daar.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat een onbekende of defecte badge wordt gescand.

**Wanneer** het kassasysteem deze niet herkent in de database.

**Dan** gooit hij een waarschuwing naar IT en laat de kassa gewoon verder werken.

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1.  Als de database lookup tijdens een scan geen klant oplevert, laat het script dan niet crashen.
2.  Stuur een badge_not_found alert naar de monitoringswachtrij.
3.  Sluit het oorspronkelijke scanbericht expliciet af, zodat RabbitMQ niet in een oneindige loop terechtkomt.

EPIC 4: FOUTEN & SYSTEEMMONITORING (RESILIENCE & CONTROLROOM)

# story 13: Zonder internet toch blijven verkopen

**MVP status: MVP**

_Als festivalorganisator eis ik dat de barren gewoon drank kunnen blijven verkopen, zelfs als het centrale netwerk er even uit ligt._

**ACCEPTATIECRITERIA:**

- Als de kassa geen contact heeft met het hoofdnetwerk, bewaart hij bestellingen lokaal in een geheugenbestandje.
- Zodra het netwerk terug is, worden de bewaarde bestellingen alsnog verstuurd.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat de netwerkverbinding is weggevallen.

**Wanneer** de kassa berichten wil doorsturen.

**Dan** slaat hij ze tijdelijk op de eigen computer op en verstuurt hij ze pas als de verbinding is hersteld.

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1.  Zorg voor gedegen foutafhandeling (try/except) rondom het verzenden van berichten.
2.  Als verzenden naar RabbitMQ mislukt, schrijf de payload dan veilig weg in een lokaal bestand (outbox).
3.  Schrijf een opstart- of herstelfunctie die deze outbox leegmaakt en verstuurt zodra de connectie weer actief is.

# story 14: Kassa beschermen tegen foute data

**MVP status: MVP**

_Als beheerder wil ik dat de kassa onleesbare of onbekende berichten vanuit andere systemen netjes negeert en rapporteert, zodat de kassa niet crasht._

**ACCEPTATIECRITERIA:**

- Elk inkomend bericht wordt streng gecontroleerd.
- Klopt de structuur niet? Dan gooit hij het bericht weg en stuurt hij een storingsmelding naar het dashboard.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat een ander team per ongeluk foute data naar ons stuurt.

**Wanneer** de kassa dit probeert te lezen en faalt.

**Dan** breekt het proces netjes af en alarmeert het de beheerders.

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1.  Controleer de structuur (XML parsing) van inkomende berichten voordat je ze doorgeeft aan de logica.
2.  Vang foute formaten of onbekende berichtsoorten op.
3.  Weiger het corrupte bericht veilig en stuur een foutrapportage naar de Controlroom.

# story 15: systeem-hartslag (We zijn nog levend!)

**MVP status: MVP**

_Als monitoringsdienst wil ik elke seconde een "levenssignaal" ontvangen van de kassa, zodat we direct kunnen zien of alles nog werkt._

**ACCEPTATIECRITERIA:**

- Een onzichtbaar programma in de kassa stuurt elke seconde een statusbericht (online of degraded).
- Dit bericht gaat direct naar de Controlroom, zonder tussenstops.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat de kassa is ingeschakeld.

**Wanneer** de klok een seconde wegtikt.

**Dan** verzendt de kassa volautomatisch een status-update.

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1.  Bouw een apart, lichtgewicht Python-script dat in een lus draait (met een pauze van 1 seconde).
2.  Voer een snelle technische check uit om te zien of Odoo lokaal nog gezond reageert.
3.  Genereer een heartbeat-bericht en schiet dit rechtstreeks de monitoring-wachtrij in.

# story 16: Geen oude hartslagen nasturen

**MVP status: MVP**

_Als monitoringsdienst eis ik dat de kassa géén oude levenssignalen verstuurt na een netwerkstoring, we willen enkel de actuele status weten._

**ACCEPTATIECRITERIA:**

- "Hartslagen" worden absoluut nooit lokaal bewaard bij internetuitval.
- Mislukte hartslagen worden genegeerd.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat het internet is uitgevallen.

**Wanneer** de kassa een hartslag wil sturen.

**Dan** gooit hij deze bij falen direct weg zonder hem te bewaren voor later.

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1.  Houd de code van dit script bewust gescheiden van de buffer-logica van de reguliere kassa- berichten.
2.  Vang verbindingsfouten lokaal op, sla niks op, en probeer het gewoon een seconde later nog eens.

# story 16b: Dubbele berichten stil negeren (Idempotentie)

**MVP status: MVP**

_Als systeembeheerder wil ik dat de kassa elk inkomend bericht maar één keer verwerkt, zodat klantprofielen of saldo's niet corrupt raken als RabbitMQ een bericht dubbel aflevert._

**ACCEPTATIECRITERIA:**

- Het receiver.py script houdt een interne cache (LRU) bij van recent verwerkte message_id's.
- Als een inkomend bericht een ID heeft dat al in de cache staat, wordt de verwerking overgeslagen.
- Het duplicaat krijgt direct een succesvolle ACK naar RabbitMQ, zodat het stil uit de wachtrij verdwijnt zonder foutmelding.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat een bericht met een specifiek message_id al succesvol is verwerkt.

**Wanneer** RabbitMQ exact hetzelfde bericht per ongeluk nog eens aflevert.

**Dan** herkent de receiver dit, voert geen database-acties uit en stuurt een ACK om het bericht te verwijderen.

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1.  Implementeer een OrderedDict in receiver.py met een maximale grootte (bijv. 10.000 items).
2.  Controleer bij elk inkomend bericht of het message_id in deze dictionary zit.
3.  Zo ja: retourneer direct een ch.basic_ack en stop de logica.

# story 16c: Lokale buffer beschermen tegen overstroming (offline_queue_full)

**MVP status: MVP**

_Als IT-beheerder wil ik gewaarschuwd worden als de kassa langdurig offline is en de lokale buffer vol raakt, zodat we weten dat er transactiedata verloren dreigt te gaan._

**ACCEPTATIECRITERIA:**

- De kassa mag maximaal 500 berichten lokaal opslaan in de outbox.json buffer.
- Bij het bereiken van deze limiet, weigert de kassa nieuwe berichten lokaal op te slaan.
- Er wordt direct een system_error met de code offline_queue_full gegenereerd.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat het RabbitMQ netwerk langdurig plat ligt en er al 500 bestellingen in de outbox zitten.

**Wanneer** de kassamedewerker een 501e bestelling afrekent.

**Dan** gooit het systeem het nieuwe bericht veilig weg en stuurt het (zodra mogelijk) een alarm naar de Controlroom.

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1.  Definieer BUFFER_MAX_MESSAGES = 500 in sender.py.
2.  Controleer de lijstgrootte bij het wegschrijven in \_buffer_message(). Als limiet bereikt is, return zonder te schrijven.
3.  Roep send_error_to_queue("offline_queue_full", ...) aan om de monitoring in te lichten.

EPIC 5: UITGEBREIDE RANDGEVALLEN (TECHNICAL SAD PATHS)

# story 17: Foutieve betaling met virtueel saldo blokkeren

**MVP status: secundair (Niet strikt MVP)**

_Als financieel beheerder wil ik dat de kassa een betaling met digitaal tegoed snoeihard blokkeert als er géén klant aan de bestelling gekoppeld is, om spook-afschrijvingen te voorkomen._

**ACCEPTATIECRITERIA:**

- Als een "Anonieme verkoop" wordt afgerekend via de Wallet, ziet de achterliggende software dit en trekt nergens saldo vanaf.
- Er klinkt een digitaal alarm bij IT wegens een procedurefout.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat een barman een anonieme verkoop abusievelijk afrekent via digitaal saldo.

**Wanneer** de kassa dit wilt verwerken.

**Dan** verandert het geen saldo's, slaat alarm, en voorkomt dat het script vastloopt.

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1.  Voeg een extra veiligheidscontrole toe in het verwerkingsscript, vlak voordat er saldo wordt verlaagd.
2.  Indien betaalmethode=Badge, maar de klant is Anoniem: stop de berekening direct.
3.  Stuur een foutmelding naar de monitoring, maar markeer de order wél als afgehandeld zodat hij niet blijft hangen.

# story 18: Verbindingsfouten direct alarmeren

**MVP status: MVP**

_Als IT-beheerder wil ik dat een database-crash van de kassa direct als foutmelding naar het centrale dashboard rolt, zodat wij problemen snel kunnen oplossen._

**ACCEPTATIECRITERIA:**

- Zodra het interne systeem de eigen database niet kan bereiken, detecteert hij dit.
- Hij stuurt een gedetailleerd foutbericht en pauzeert even om een oneindige loop te voorkomen.

**BDD (GEGEVEN/WANNEER/DAN):**

**Gegeven** dat de interne kassa-database vastloopt.

**Wanneer** de software data wil ophalen en wordt geweigerd.

**Dan** pauzeert de verwerking en alarmeert het de beheerders.

**TECHNISCH STAPPENPLAN (HIGH-LEVEL):**

1.  Vang generieke verbindingsfouten tussen het script en de Odoo-omgeving netjes op.
2.  Bouw en verstuur een odoo_api_error naar de monitoring queue.
3.  Voeg een korte rustpauze toe of wijs inkomende berichten veilig af om de boel niet verder te overbelasten.