# Vragen — Team Kassa (Odoo POS)

Beslissingslogboek | Integratieproject Desideriushogeschool 2026

Berichten gemarkeerd met ✔ DONE zijn vaststaande feiten. Vragen gemarkeerd met ? zijn nog open.

# **BEANTWOORD**

## Architectuur & flows

| |
| --- |
| **✔ DONE — Vraag 1 — Hoe verloopt de facturatieflow?** |
| Wanneer een klant betaalt aan de kassa, stuurt de kassa de betaalinfo naar het CRM-systeem (Salesforce). Het CRM is vervolgens verantwoordelijk om de factuur aan te maken via het facturatiesysteem (FOSSBilling). De kassa praat dus nooit rechtstreeks met het facturatiesysteem — alles loopt via het CRM. |

| |
| --- |
| **✔ DONE — Vraag 2 — Waar haalt de kassa inschrijvingsdata op?** |
| De kassa haalt inschrijvingen op uit het CRM (Salesforce), niet van de website (Frontend). De website registreert een inschrijving, maar het CRM beheert de klantdata en stuurt die door naar de kassa. De kassa stuurt betalingsstatus (payment_status) en badge-saldo updates (wallet_balance_update) naar de website (Drupal) — niet omgekeerd. |

| |
| --- |
| **✔ DONE — Vraag 3 — Kan iemand zowel op voorhand als aan de kassa betalen?** |
| Ja, beide is mogelijk. Een bezoeker kan het inschrijvingsgeld betalen via de website voor het event, of ter plekke aan de kassa bij aankomst. In beide gevallen wordt de betaling correct verwerkt. |

| |
| --- |
| **✔ DONE — Vraag 4 — Iemand zonder account wil een factuur — wat dan?** |
| Als iemand aan de kassa staat en een factuur wil maar nog geen account heeft: die persoon moet eerst zelf een account aanmaken op de website. De kassamedewerker doet dit niet voor hen. Pas als er een account is en de data in het CRM zit, kan de kassa de transactie verwerken en kan het CRM een factuur opmaken. |

| |
| --- |
| **✔ DONE — Vraag 5 — Aparte berichtenstroom voor besteldetails (pos.consumptions) — verwijderd** |
| Vroeger was er een aparte berichtenstroom die besteldetails zoals producten en prijzen rechtstreeks naar het facturatiesysteem stuurde. Dit is niet meer nodig: de kassa stuurt nu alle info — zowel betalingsdata als besteldetails — in één bericht naar het CRM. Het CRM regelt de rest. |

## Badges

| |
| --- |
| **✔ DONE — Vraag 6 — Hoe werken badges — zijn ze vooraf klaargemaakt of ter plekke gekoppeld?** |
| Badges zijn leeg bij aankomst en worden ter plekke aan de inschrijvingsbalie door het kassateam gekoppeld aan het account van de bezoeker. Er zijn geen vooraf gepersonaliseerde badges. In de normale flow is elke badge dus altijd gekoppeld aan een account voor de bezoeker verder het event opgaat. |

| |
| --- |
| **✔ DONE — Vraag 7 — Is een badge verplicht om iets te kopen?** |
| Nee. Elk event beslist zelf of badges gebruikt worden en of bezoekers geld op hun badge kunnen zetten. Aankopen zonder badge moeten altijd mogelijk zijn — de kassamedewerker verkoopt dan anoniem en de klant krijgt een kassaticket. Geen badge = geen toegang tot bedrijfsrekening en geen factuur achteraf (zie Q28). |

| |
| --- |
| **✔ DONE — Vraag 8 — Wanneer wordt een badge gescand?** |
| Op twee momenten: bij binnenkomst (om de bezoeker te registreren) en bij elke individuele aankoop aan de bar of kassa. De badge dient dus als identiteitskaart doorheen het hele event. |

| |
| --- |
| **✔ DONE — Vraag 9 — Wat als een badge niet herkend wordt aan de kassa?** |
| Dit mag normaal niet voorkomen want badges worden gekoppeld aan de inschrijvingsbalie. Als het toch gebeurt (badge defect, bericht nog vastgezeten in de queue, ...) en de persoon wil geen factuur: de kassa gaat anoniem verder en geeft een kassaticket. Wil de persoon wel een factuur: de kassa kan optioneel op naam/e-mail opzoeken voor een kassaticket, of de persoon meldt zich bij de infobalie voor een hernieuwde badge-koppeling (zie Q22). |

| |
| --- |
| **✔ DONE — Vraag 10 — Iemand koopt iets anoniem en wil geen factuur — mag dat?** |
| Ja. Als iemand geen account heeft en geen factuur wil, mag de kassa de aankoop afhandelen zonder koppeling aan een echte persoon. De aankoop wordt geregistreerd, maar achteraf is er geen factuur meer mogelijk voor die aankoop. |

## Kassa werking

| |
| --- |
| **✔ DONE — Vraag 11 — Wat als de kassa geen verbinding heeft — mogen aankopen doorgaan?** |
| Als de kassa de verbinding met het berichtensysteem verliest, mogen aankopen gewoon doorgaan. De kassa slaat de berichten lokaal op in outbox.json (Docker named volume outbox-data) en verstuurt ze zodra de verbinding hersteld is via flush_buffer(). Als het kassasysteem zelf uitvalt, zijn er geen aankopen mogelijk. |

| |
| --- |
| **✔ DONE — Vraag 12 — Kunnen er meerdere kassa's tegelijk actief zijn op een event?** |
| Ja, bv. een hoofdkassa en een barkassa tegelijk. Omdat elke bezoeker maar één badge heeft, is het onmogelijk dat dezelfde badge op hetzelfde moment op twee plekken gescand wordt. Meest logische aanpak: één gedeelde Odoo-instantie met meerdere POS-sessies, zodat alle aankopen centraal bijgehouden worden en er geen synchronisatieproblemen zijn tussen de kassa's. |

| |
| --- |
| **✔ DONE — Vraag 13 — Moet een mislukte betaling gelogd worden?** |
| Nee. Als een betaling mislukt (kaart geweigerd, onvoldoende saldo, ...) hoeft er niets bijgehouden te worden. De klant probeert gewoon opnieuw met een andere betaalmethode. Enkel succesvolle betalingen worden doorgestuurd naar het CRM. |

| |
| --- |
| **✔ DONE — Vraag 14 — Krijgt een bedrijf één factuur voor alle werknemers samen?** |
| Ja. Als meerdere werknemers van hetzelfde bedrijf aankopen doen op een event, bundelt het CRM alle aankopen en maakt op het einde van de dag één factuur aan voor dat bedrijf. De kassa stuurt per aankoop de nodige data door naar het CRM, maar de facturatiebundeling is volledig de verantwoordelijkheid van het CRM. |

## Aannames & technische keuzes

| |
| --- |
| **✔ DONE — Vraag 15 — Zijn badges een MVP-onderdeel of een 'mooie extra'?** |
| Badges zijn geen core-onderdeel van de MVP en maken geen deel uit van de minimale oplevering. Docenten verwachten ze echter wel omdat alles met AI gerealiseerd kan worden. We behandelen badges als onderdeel van het project maar geven ze een lagere prioriteit dan de kernfunctionaliteit. |

| |
| --- |
| **✔ DONE — Vraag 16 — Privepersoon wil toch een factuur — hoe verloopt dat?** |
| Een privepersoon die een factuur wil, moet een account hebben en identificeerbaar zijn (via badge-scan of bestaand CRM-profiel). De kassamedewerker stuurt de factuurgegevens (naam, adres, optioneel BTW-nummer) via een invoice_request bericht naar het CRM. Het CRM maakt dan de factuur aan. Volledig anonieme transacties zonder badge of account kunnen niet achteraf gefactureerd worden — die krijgen enkel een kassaticket. Flow 10 (invoice_request) in het XML-structurendocument dekt deze case. |

| |
| --- |
| **✔ DONE — Vraag 17 — CRM is down — kan de kassa nog werken?** |
| Ja. De kassa houdt alle inkomende klantdata lokaal bij in Odoo (via get_or_create_partner() en get_partner_for_badge()). Bij uitval van het CRM werkt de kassa verder op basis van de lokaal gecachte profielen in Odoo. Berichten worden gebufferd in outbox.json en verstuurd zodra de verbinding hersteld is. |

| |
| --- |
| **✔ DONE — Vraag 18 — XML versioning strategie** |
| We gebruiken version="2.0" in alle berichten, conform de huidige v2.0-documentset. Versiebeheer is de verantwoordelijkheid van de PM's. Als een veld gewijzigd of toegevoegd wordt, communiceren de PM's dit naar alle betrokken teams zodat iedereen gelijktijdig kan aanpassen. |

| |
| --- |
| **✔ DONE — Vraag 19 — Error codes afgestemd met Controlroom-team?** |
| De foutcodes zijn gedocumenteerd in de enum-tabel van Datamapping §5 en XML_Structuren §8. Het Controlroom-team dient deze tabel te kennen om Elastic alerts correct te configureren. Alle foutcodes zijn in snake_case lowercase conform de XML_naamgeving standaard:<br><br>invalid_xml_format, unknown_message_type, profile_not_found, odoo_api_error,<br><br>rabbitmq_connection_error, offline_queue_full, badge_not_found<br><br>Nota: eerdere versies vermeldden codes in ERR_PREFIX_formaat (bv. ERR_XML_VALIDATIE). Deze zijn vervangen door snake_case equivalenten conform PM-standaard. |

| |
| --- |
| **✔ DONE — Vraag 20 — Wie triggert de bevestigingsmail na betaling aan de kassa?** |
| Dit is niet de verantwoordelijkheid van het kassa-team. Het CRM en/of FOSSBilling regelen de mailbevestiging na factuurgeneratie. Particulieren die enkel een consumptie kopen zonder factuur vallen buiten deze flow — zij krijgen geen bevestigingsmail van ons systeem. |

| |
| --- |
| **✔ DONE — Vraag 21 — Verwacht het Controlroom-team ook transactiedata van de kassa?** |
| Nee, het Controlroom-team verwacht geen aparte of extra berichten van de kassa. Ze luisteren passief mee via RabbitMQ exchanges op de bestaande berichtenstromen. Ze pikken die data automatisch op en visualiseren ze in Kibana.<br><br>**Twee concrete actiepunten voor ons team:**<br><br>✅ GEIMPLEMENTEERD — Actiepunt 1: Berichten worden verstuurd via kassa.exchange (topic exchange) in sender.py v3.3. Het Controlroom-team kan passief meeluisteren via eigen bindings op routing key "kassa.#". Afstemming met Infra over het exacte exchange-type loopt nog via Q30.<br><br>✅ GEIMPLEMENTEERD — Actiepunt 2: Errors worden gerapporteerd naar kassa.errors als system_error XML-bericht via send_error_to_queue() in sender.py v3.3. Het Controlroom-team luistert hierop mee om een systeem als DEGRADED te markeren als er te veel fouten binnenkomen. Routing key: kassa.errors. |
| **Betrokken teams: Kassa-team, Infra-team** |

| |
| --- |
| **✔ DONE — Vraag 38 — Aankoopflow: consumption_order en payment_registered** |
| Beslissing Aankoopflow: Het Kassa-team laat het eigen type update_customer_behavior vallen en splitst bestellingen en betalingen op in consumption_order en payment_registered, 100% conform de PM-standaard. Flow 5 uit het XML-structurendocument is vervangen door Flow 5A (consumption_order) en Flow 5B (payment_registered), elk met eigen XML-voorbeeld en XSD-schema.<br><br>Routing keys: consumption_order en payment_registered (context: consumption) gebruiken kassa.payments.consumption. payment_registered (context: registration) gebruikt kassa.payments.registration. |
| **Betrokken teams: Kassa-team, CRM-team** |

| |
| --- |
| **✔ DONE — Vraag 22 — Badge werkt niet en persoon wil een factuur — wie lost dit op?** |
| De kassa doet geen IT-support — dat houdt de rij op. Als de badge defect is en de klant wil een kassaticket: kassamedewerker kan optioneel op naam/e-mail zoeken in Odoo om een ticket te genereren. Voor een echte badge-koppeling: bezoeker meldt zich bij de infobalie. Voor een factuur: de aankoop kan pas doorgaan als de badge correct gekoppeld is aan het account. |
| **Betrokken teams: Kassa-team, CRM-team, Frontend-team** |

| |
| --- |
| **✔ DONE — Vraag 23 — Moet de kassamedewerker altijd vragen of iemand een factuur wil voor ze starten?** |
| Nee. De kassa werkt vlot door. Anonieme betaler (cash/bancontact) = standaard kassaticket (bonnetje). Wil iemand een factuur op bedrijfsnaam? Dan scannen ze hun bedrijfsbadge. Achteraf factureren voor anonieme transacties doen we niet.<br><br>Onze insteek: Als hier geen vast proces voor is vanuit de organisatie, is Team Kassa bereid en in staat om hier zelf een pragmatische, werkbare oplossing voor te bedenken zodat de kassa vlot blijft draaien. |
| **Betrokken teams: Kassa-team** |

| |
| --- |
| **✔ DONE — Vraag 25 — Annulering en profielwijziging — stuurt CRM dit naar ons, en niet meer de Frontend?** |
| Uitgeklaard en bevestigd. Het CRM-systeem (Salesforce) beheert alle annuleringen en profielwijzigingen en stuurt deze rechtstreeks naar de kassa. De Frontend stuurt deze data niet meer rechtstreeks naar de kassa. |
| **Betrokken teams: Kassa-team, CRM-team, Frontend-team** |

## Badge-saldo & betalingen

| |
| --- |
| **✔ DONE — Vraag 26 — Kan een bezoeker zijn badge-saldo opwaarderen aan de kassa?** |
| Ja, via een Top-up product in Odoo/Kassa (bv. 'Top-up EUR 10' of 'Top-up EUR 20'). Bij verkoop stuurt de poller een consumption_order met item_type=wallet_topup en vervolgens een wallet_balance_update naar Drupal. Het saldo wordt bijgehouden in x_wallet_balance op res.partner in Odoo (Single Source of Truth). |
| **Betrokken teams: Kassa-team, Frontend-team** |

| |
| --- |
| **✔ DONE — Vraag 27 — Kan iemand deels met badge-saldo en deels met kaart of cash betalen?** |
| Out of scope. Gesplitste betalingen maken de kassa-logica onnodig complex. De regel is: ofwel betaal je het volledige bedrag met badge, ofwel alles met kaart of cash. Saldo te laag? Dan eerst opladen via een Top-up product. |
| **Betrokken teams: Kassa-team** |

## Events zonder badges

| |
| --- |
| **✔ DONE — Vraag 28 — Hoe toont iemand aan dat die bij een bedrijf hoort als er geen badges zijn?** |
| Geen badge (of digitale QR-code vanuit de app) = geen toegang tot de bedrijfsrekening. De kassa zoekt geen namen manueel op in een lijst — te foutgevoelig en traag. 'No badge = pay cash/card.' Frauderisico wordt zo volledig vermeden.<br><br>Onze insteek: Frauderisico: omdat werknemers aan de kassa niet ter plekke betalen (het gaat op de bedrijfsfactuur via company_link), kunnen mensen zonder verificatie simpelweg liegen dat ze bij een bedrijf horen. Er moet nagedacht worden over een waterdichte verificatie, bv. via een persoonlijke QR-code. |
| **Betrokken teams: Kassa-team, CRM-team, Frontend-team** |

## Integratie & infrastructuur

| |
| --- |
| **✔ DONE — Vraag 31 — Wie configureert de productcatalogus in Odoo en hoe?** |
| Demo: wij kiezen 5 fictieve producten (Koffie, Cola, Pintje, Broodje, Top-up EUR 10/20). De klant beheert de catalogus achteraf zelf uitsluitend in Odoo (Point of Sale > Producten). Geen synchronisatie met Frontend nodig.<br><br>Onze insteek: Voor demomomenten vullen wij de kassa met zelfgekozen fictieve producten. Prioriteit: Odoo zo opzetten dat de klant achteraf zelf eenvoudig de productcatalogus kan beheren. |
| **Betrokken teams: Kassa-team** |

| |
| --- |
| **✔ DONE — Vraag 32 — Badge ID formaat — QR-code, NFC of RFID?** |
| Modulair: alle drie technologieen (QR, NFC, RFID) leveren een string ID aan dat een persoon representeert. Onze implementatie werkt met elke technologie zolang het IoT-team een badge_id string aanlevert. Geen extra aanpassingen nodig aan onze kant. |
| **Betrokken teams: Kassa-team, IoT-team** |

| |
| --- |
| **✔ DONE — Vraag 33 — Planning & sessieverschuivingen — moet de kassa dit kennen?** |
| Geen impact op Kassa. Wij verkopen enkel consumpties. Terugbetalingen van tickets of sessies worden door Frontend/CRM/Facturatie afgehandeld. De kassa luistert niet naar session.update events.<br><br>Onze insteek: Planningsverschuivingen boeien de kassa enkel als er financiele gevolgen zijn. Zonder zulke financiele impact negeren wij de planning. |
| **Betrokken teams: Kassa-team, Planning-team, CRM-team** |

| |
| --- |
| **✔ DONE — Vraag 34 — Wallet-saldo eigenaar — Odoo of Drupal?** |
| Beslissing: Team Kassa (Odoo) is 100% de eigenaar en de Single Source of Truth van het badge-saldo. Het saldo wordt opgeslagen in x_wallet_balance op res.partner in Odoo. Aftrek bij Badge Wallet betaling en bijtelling bij Top-up worden uitgevoerd door poller.py via deduct_wallet_balance(). De Frontend (Drupal) ontvangt saldo-updates via wallet_balance_update berichten. |
| **Betrokken teams: Kassa-team, Frontend-team** |

| |
| --- |
| **✔ DONE — Vraag 35 — AI/MCP agent — moet de kassa specifieke data beschikbaar stellen?** |
| Nee. De AI Agent haalt zijn data centraal uit Elastic/CRM. Zolang wij alle transacties als events op RabbitMQ pushen (geconsumeerd door Elastic), heeft de agent genoeg data. Geen specifieke endpoints of formaten nodig. |
| **Betrokken teams: Kassa-team, AI-team** |

| |
| --- |
| **✔ DONE — Vraag 37 — Berichttypes — Welke exacte PM-gedefinieerde enum-types moeten wij gebruiken?** |
| Formeel goedgekeurd door PM: consumption_order, payment_registered en alle update-events (profile_update, cancel_registration, payment_status, wallet_balance_update, badge_assigned) mogen formeel gebruikt worden.<br><br>Volledig type-overzicht: new_registration, badge_scanned, invoice_request, system_error, heartbeat, consumption_order, payment_registered, profile_update, cancel_registration, payment_status, wallet_balance_update, badge_assigned, refund_processed.<br><br>Actiepunt: documenteer alle XML payloads in ClickUp zodat andere teams exact weten wat ze van ons kunnen consumeren. |
| **Betrokken teams: Kassa-team, CRM-team, Frontend-team, alle teams** |

## Infrastructuur & RabbitMQ

| **✔ DONE — Vraag 30 — RabbitMQ exchange/routing strategie — welke aanpak gebruikt Infra?** |
| Drie deelvragen zijn beantwoord op basis van de Tech Stack documentatie en de huidige sender.py implementatie:<br><br>**(1) Bevestiging van kassa.exchange als topic exchange:** Onze sender.py (v3.5) declareert kassa.exchange zelf als topic exchange bij het opstarten via channel.exchange_declare(). We zijn hiervoor niet afhankelijk van Infra — de exchange wordt automatisch aangemaakt als die nog niet bestaat. Dit is conform de Tech Stack (RABBIT_EXCHANGE environment variable, default: kassa.exchange).<br><br>**(2) Binding keys voor andere teams:** Teams die passief willen meeluisteren (bv. Controlroom) binden hun eigen queue aan kassa.exchange met de wildcard routing key kassa.# — dit geeft hen alle berichten van het kassa-systeem. Specifiekere bindings zijn ook mogelijk, bv. kassa.payments.# voor enkel betalingsberichten. Elk team regelt zijn eigen bindings — wij hoeven daar niets voor aan te passen.<br><br>**(3) Dead-letter queue (DLQ):** Een DLQ is een opvangwachtrij voor berichten die herhaaldelijk falen (bv. door een crash of verwerkingsfout). Onze receiver.py stuurt ongeldige berichten actief naar kassa.errors en geeft een basic_ack — er komen dus geen berichten in een DLQ terecht door onze code. Of Infra een DLQ configureert op de RabbitMQ-queues zelf is hun verantwoordelijkheid en heeft geen impact op onze implementatie. |
| **Betrokken teams: Kassa-team, Infra-team** |

Team Kassa | Vragen & Beslissingslogboek | Integratieproject Desideriushogeschool | 2026
