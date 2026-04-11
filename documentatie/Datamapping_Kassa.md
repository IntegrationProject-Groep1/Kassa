# Datamapping Documentatie — Team Kassa (Odoo POS)

Versie 2.5 — Conform XML_naamgeving standaard (snake_case) | Geintegreerd document

Integratieproject Desideriushogeschool 2026

## 1\. Systeemlegenda

| |     | |     |
| --- | --- | --- | --- |
| **Systeem** | **Omschrijving** | **Systeem** | **Omschrijving** |
| Kassa | Kassasysteem (Odoo POS) aan de bar of hoofdkassa. Verstuurt consumptie- en betalingsberichten. | IoT | Raspberry Pi badge scanners. Sturen badge_id door naar Kassa. |
| CRM | Salesforce — klantdata, facturatie-coördinatie, profielbeheer. | Elastic | Elastic Stack — monitoring, heartbeats, error alerts. |
| Drupal | Frontend website — ontvangt betaalstatus en wallet-saldo updates. | FOSSBilling | Facturatiesysteem — aangestuurd door CRM, nooit rechtstreeks door Kassa. |

## 2\. Berichtflow per Scenario

Overzicht van alle berichten die verstuurd worden, met type-waarden conform snake_case standaard.

| |     | |     | |     |
| --- | --- | --- | --- | --- | --- |
| **Scenario** | **type (enum)** | **Van** | **Naar** | **Routing (Exchange & Key)** | **Trigger** |
| Bezoeker schrijft in | new_registration | CRM (Salesforce) | Kassa | Queue: kassa.incoming | Inschrijving bevestigd op website |
| Bezoeker scant badge | badge_scanned | IoT (Raspberry Pi) | Kassa | Queue: kassa.incoming | Badge gescand door scanner |
| CRM werkt profiel bij | profile_update | CRM (Salesforce) | Kassa | Queue: kassa.incoming | Profiel bijgewerkt in Salesforce |
| Klant annuleert inschrijving | cancel_registration | CRM (Salesforce) | Kassa | Queue: kassa.incoming | Annulering via website |
| Bestelling doorsturen CRM | consumption_order | Kassa | CRM | kassa.exchange → kassa.payments.consumption | Na elke afgeronde aankoop |
| Anonieme aankoop | consumption_order (is_anonymous=true) | Kassa | CRM | kassa.exchange → kassa.payments.consumption | Aankoop zonder badge/account |
| Betaling registreren CRM | payment_registered | Kassa | CRM | kassa.exchange → kassa.payments.consumption | Na succesvolle betaling |
| Inschrijving betaald | payment_registered (context=registration) | Kassa | CRM | kassa.exchange → kassa.payments.registration | Inschrijvingsgeld betaald aan kassa |
| Klant vraagt factuur | invoice_request | Kassa | CRM | kassa.exchange → kassa.payments.invoice | Kassamedewerker verzamelt factuurgegevens |
| Badge koppelen aan account | badge_assigned | Kassa | CRM | kassa.exchange → kassa.payments.badge | Badge gekoppeld aan bezoeker bij balie |
| Terugbetaling verwerkt | refund_processed | Kassa | CRM | kassa.exchange → kassa.payments.refund | Kassamedewerker initieert correctie |
| Validatie/systeemfout | system_error | Kassa | Elastic | kassa.exchange → kassa.errors | Fout gedetecteerd |
| Klant betaalt inschrijving | payment_status | Kassa | Drupal | kassa.exchange → kassa.frontend.payment | Betaling succesvol afgerond |
| Betaling met badge | wallet_balance_update | Kassa | Drupal | kassa.exchange → kassa.frontend.wallet | Klant betaalt een bestelling met de Badge Wallet _(Saldo daalt)_ |
| Top-up via kassa (Flow 13) | wallet_balance_update | Kassa | Drupal | kassa.exchange → kassa.frontend.wallet | Klant koopt een Top-up product aan de kassa _(Saldo stijgt)_ |
| Terugbetaling badge (Flow 15) | wallet_balance_update | Kassa | Drupal | kassa.exchange → kassa.frontend.wallet | Klant krijgt een refund uitbetaald op de badge_wallet _(Saldo stijgt)_ |

## 3\. Master Datamapping Overzicht

Elk dataveld dat uitgewisseld wordt, met bron, bestemming, XML-veld en validatieregels.

| |     | |     | |
| --- | --- | --- | --- | --- |
| **CRM (Salesforce) → Kassa — new_registration** | |     | |     |
| **Nieuwe inschrijving. Kassa maakt of updatet het klantprofiel in Odoo.** | |     | |     |
| **Object** | **XML-Veld** | **Datatype** | **Verplicht** | **Toelichting / Validatieregel** |
| Header | &lt;header&gt;&lt;message_id&gt; | String (UUID) | Ja  | Opslaan voor tracing en audit |
| Header | &lt;header&gt;&lt;type&gt; | Enum | Ja  | Altijd: new_registration |
| Header | &lt;header&gt;&lt;source&gt; | String | Ja  | Altijd: crm |
| Header | &lt;header&gt;&lt;timestamp&gt; | ISO-8601 UTC | Ja  | Formaat: YYYY-MM-DDTHH:MM:SSZ |
| Header | &lt;header&gt;&lt;version&gt; | String | Ja  | Altijd: 2.0 |
| Customer | &lt;customer&gt;&lt;user_id&gt; | UUID v4 | Ja  | Externe sleutel — uniek over alle systemen. Opgeslagen als x_user_id in Odoo res.partner. |
| Customer | &lt;customer&gt;&lt;email&gt; | String | Ja  | Geldig e-mailadresformaat |
| Customer | &lt;customer&gt;&lt;contact&gt;&lt;first_name&gt; | String | Ja  | Voornaam bezoeker |
| Customer | &lt;customer&gt;&lt;contact&gt;&lt;last_name&gt; | String | Ja  | Achternaam bezoeker |
| Customer | &lt;customer&gt;&lt;type&gt; | Enum | Ja  | company of private |
| Customer | &lt;customer&gt;&lt;company_name&gt; | String | Cond. | Verplicht als type = company |
| Customer | &lt;customer&gt;&lt;vat_number&gt; | String | Cond. | Verplicht als type = company |
| Customer | &lt;customer&gt;&lt;date_of_birth&gt; | Date (xs:date) | Ja  | Geboortedatum (YYYY-MM-DD). Gebruikt voor leeftijdsberekening bij alcoholcontrole. Vervangt age. |
| Betaling | &lt;payment_due&gt;&lt;amount&gt; | Decimal | Ja  | Te betalen inschrijvingsbedrag. Opgeslagen in Odoo als `res.partner.x_outstanding_amount`. |
| Betaling | &lt;payment_due&gt;&lt;status&gt; | Enum | Ja  | Status inschrijvingsbetaling: `unpaid` of `paid`. Opgeslagen in Odoo als `res.partner.x_payment_status`. |

| |     | |     | |
| --- | --- | --- | --- | --- |
| **IoT (Raspberry Pi) → Kassa — badge_scanned** | |     | |     |
| **Badge gescand aan inkom of bar. Aankopen zonder badge moeten altijd mogelijk zijn.** | |     | |     |
| **Object** | **XML-Veld** | **Datatype** | **Verplicht** | **Toelichting / Validatieregel** |
| Header | &lt;header&gt;&lt;message_id&gt; | String | Ja  | Opslaan voor tracing. Gebruikt als related_message_id bij badge_not_found error. |
| Header | &lt;header&gt;&lt;type&gt; | Enum | Ja  | Altijd: badge_scanned |
| Header | &lt;header&gt;&lt;source&gt; | String | Ja  | ID van scanner, bv. iot_scanner_bar |
| Header | &lt;header&gt;&lt;timestamp&gt; | ISO-8601 UTC | Ja  | Formaat: YYYY-MM-DDTHH:MM:SSZ |
| Header | &lt;header&gt;&lt;version&gt; | String | Ja  | Altijd: 2.0 |
| Body | &lt;badge_id&gt; | String | Ja  | Uniek ID van de gescande badge/QR-code. Opzoeken in lokale Odoo-cache (x_badge_id). |
| Body | &lt;location&gt; | String | Ja  | Locatie van de scanner, bv. hoofdbar, inkom, bar2 |

| |     | |     | |
| --- | --- | --- | --- | --- |
| **CRM (Salesforce) → Kassa — profile_update** | |     | |     |
| **Profielwijziging. Kassa werkt het klantprofiel bij in Odoo.** | |     | |     |
| **Object** | **XML-Veld** | **Datatype** | **Verplicht** | **Toelichting / Validatieregel** |
| Header | &lt;header&gt;&lt;message_id&gt; | String | Ja  | Opslaan voor tracing en audit |
| Header | &lt;header&gt;&lt;type&gt; | Enum | Ja  | Altijd: profile_update |
| Header | &lt;header&gt;&lt;source&gt; | String | Ja  | Altijd: crm |
| Header | &lt;header&gt;&lt;timestamp&gt; | ISO-8601 UTC | Ja  | Formaat: YYYY-MM-DDTHH:MM:SSZ |
| Header | &lt;header&gt;&lt;version&gt; | String | Ja  | Altijd: 2.0 |
| Body | &lt;user_id&gt; | UUID v4 | Ja  | Externe sleutel — unieke sleutel voor klantprofiel (x_user_id in Odoo) |
| Body | &lt;email&gt; | String | Ja  | Geldig e-mailadresformaat |
| Body | &lt;contact&gt;&lt;first_name&gt; | String | Ja  | Voornaam |
| Body | &lt;contact&gt;&lt;last_name&gt; | String | Ja  | Achternaam |
| Body | &lt;type&gt; | Enum | Ja  | company of private. Bepaalt of company_name en vat_number verplicht zijn. |
| Body | &lt;company_name&gt; | String | Cond. | Verplicht als type = company |
| Body | &lt;vat_number&gt; | String | Cond. | Verplicht als type = company |
| Body | &lt;date_of_birth&gt; | Date (xs:date) | Ja  | Geboortedatum (YYYY-MM-DD). Bijgewerkte waarde. Vervangt age. |

| |     | |     | |
| --- | --- | --- | --- | --- |
| **CRM (Salesforce) → Kassa — cancel_registration** | |     | |     |
| **Annulering van een inschrijving. Kassa deactiveert het klantprofiel voor die sessie.** | |     | |     |
| **Object** | **XML-Veld** | **Datatype** | **Verplicht** | **Toelichting / Validatieregel** |
| Header | &lt;header&gt;&lt;message_id&gt; | String | Ja  | Opslaan voor tracing en audit |
| Header | &lt;header&gt;&lt;type&gt; | Enum | Ja  | Altijd: cancel_registration |
| Header | &lt;header&gt;&lt;source&gt; | String | Ja  | Altijd: crm |
| Header | &lt;header&gt;&lt;timestamp&gt; | ISO-8601 UTC | Ja  | Formaat: YYYY-MM-DDTHH:MM:SSZ |
| Header | &lt;header&gt;&lt;version&gt; | String | Ja  | Altijd: 2.0 |
| Body | &lt;user_id&gt; | UUID v4 | Ja  | Unieke sleutel klantprofiel (x_user_id in Odoo) |
| Body | &lt;session_id&gt; | UUID v4 | Ja  | Sessie- of event-ID dat geannuleerd wordt. Te bevestigen met CRM-team. |

| |     | |     | |
| --- | --- | --- | --- | --- |
| **Kassa → CRM (Salesforce) — consumption_order** | |     | |     |
| **Na elke afgeronde aankoop. Ondersteunt zowel gekoppelde als anonieme aankopen.** | |     | |     |
| **Object** | **XML-Veld** | **Datatype** | **Verplicht** | **Toelichting / Validatieregel** |
| Header | &lt;header&gt;&lt;message_id&gt; | UUID v4 | Ja  | Uniek UUID v4 per bericht |
| Header | &lt;header&gt;&lt;type&gt; | Enum | Ja  | Altijd: consumption_order |
| Header | &lt;header&gt;&lt;source&gt; | String | Ja  | Bv. kassa_bar_01 |
| Header | &lt;header&gt;&lt;timestamp&gt; | ISO-8601 UTC | Ja  | Formaat: YYYY-MM-DDTHH:MM:SSZ |
| Header | &lt;header&gt;&lt;version&gt; | String | Ja  | Altijd: 2.0 |
| Body | &lt;is_anonymous&gt; | Boolean | Nee | true = anonieme aankoop zonder klantdata. Ontbreekt of false = klantdata verplicht (backward compatible). |
| Customer | &lt;customer&gt;&lt;id&gt; | String | Cond. | Odoo intern partner ID. Verplicht als is_anonymous = false. |
| Customer | &lt;customer&gt;&lt;user_id&gt; | UUID v4 | Cond. | Externe sleutel. Verplicht als is_anonymous = false. Unieke sleutel voor matching in CRM. |
| Customer | &lt;customer&gt;&lt;type&gt; | Enum | Cond. | Verplicht als is_anonymous = false. Waarden: company of private (lowercase). Afgeleid uit Odoo res.partner: company als is_company=true of gekoppeld aan parent company; anders private. |
| Customer | &lt;customer&gt;&lt;email&gt; | String | Cond. | Verplicht als is_anonymous = false. |
| Customer | &lt;customer&gt;&lt;address&gt; | Object | Nee | Optioneel adresblok. Niet verstuurd door de huidige poller implementatie. |
| Item | &lt;item&gt;&lt;id&gt; | String (LINE-xxx) | Ja  | Uniek transactieregel-ID (formaat LINE-{pos.order.line id}). Wordt door CRM gebruikt als Consumption_ID (External ID) voor Upsert. Niet leeg. |
| Item | &lt;item&gt;&lt;sku&gt; | String | Ja  | Fysiek product-ID uit Odoo (product_id[0]). Voorheen de waarde van &lt;id&gt;. |
| Item | &lt;item&gt;&lt;description&gt; | String | Ja  | Productnaam |
| Item | &lt;item&gt;&lt;quantity&gt; | Integer | Ja  | Positief geheel getal, min. 1 |
| Item | &lt;item&gt;&lt;unit_price currency="eur"&gt; | Decimal | Ja  | Positief decimaal, excl. BTW. Attribuut currency altijd eur. |
| Item | &lt;item&gt;&lt;total_amount currency="eur"&gt; | Decimal | Ja  | Totaalbedrag voor deze bestelregel (quantity × unit_price). Berekend door poller.py. Attribuut currency altijd eur. Toegevoegd in schema v2.2. |
| Item | &lt;item&gt;&lt;vat_rate&gt; | Integer | Ja  | Enum: 0, 6, 12 of 21. Waarde 0 voor Top-up producten. De poller identificeert Top-up producten op basis van de POS-categorie 'Top-ups' of het custom veld `x_is_topup` op `product.product` — niet enkel op BTW-tarief. Voor deze producten wordt `vat_rate=0` altijd geforceerd in de XML-export door `poller.py`, ongeacht de BTW-instelling in Odoo. |
| Item | &lt;item&gt;&lt;item_type&gt; | String | Nee | Optioneel. Waarde `wallet_topup` voor producten uit de categorie 'Top-ups' of met `x_is_topup=True`. De poller stelt dit in via `is_topup_product()` en forceert hierbij altijd `vat_rate=0` in de XML, ongeacht andere instellingen in Odoo. |

| |
| --- |
| **Kassa → CRM (Salesforce) — payment_registered** |
| **Na succesvolle betaling. Twee contexten: consumptie en inschrijving.** |

Het veld &lt;payment_context&gt; onderscheidt inschrijvingsbetalingen (registration) van consumptiebe­talingen (consumption). Dit bepaalt hoe het CRM het bericht verwerkt.

| |     | |     | |
| --- | --- | --- | --- | --- |
| **Object** | **XML-Veld** | **Datatype** | **Verplicht** | **Toelichting / Validatieregel** |
| Header | &lt;header&gt;&lt;message_id&gt; | UUID v4 | Ja  | Uniek UUID v4 per bericht |
| Header | &lt;header&gt;&lt;type&gt; | Enum | Ja  | Altijd: payment_registered |
| Header | &lt;header&gt;&lt;source&gt; | String | Ja  | Altijd: kassa |
| Header | &lt;header&gt;&lt;timestamp&gt; | ISO-8601 UTC | Ja  | Formaat: YYYY-MM-DDTHH:MM:SSZ |
| Header | &lt;header&gt;&lt;version&gt; | String | Ja  | Altijd: 2.0 |
| Header | &lt;header&gt;&lt;correlation_id&gt; | UUID v4 | Cond. | Bij consumption: message_id van de bijhorende consumption_order. Bij registration: message_id van de originele new_registration (Flow 1). |
| Body | &lt;payment_context&gt; | Enum | Ja  | registration of consumption. Verplicht in alle varianten. |
| Body | &lt;user_id&gt; | UUID v4 | Cond. | Aanwezig bij payment_context=registration. Laat CRM toe de inschrijving te markeren als betaald. |
| Invoice | &lt;invoice&gt;&lt;id&gt; | String | Cond. | Aanwezig bij consumption (factuur bestaat). AFWEZIG bij registration (CRM maakt factuur aan). |
| Invoice | &lt;invoice&gt;&lt;status&gt; | Enum | Ja  | paid, pending of cancelled |
| Invoice | &lt;invoice&gt;&lt;amount_paid currency="eur"&gt; | Decimal | Ja  | Positief decimaal. Attribuut currency altijd eur. |
| Invoice | &lt;invoice&gt;&lt;due_date&gt; | Date | Ja  | Formaat: YYYY-MM-DD. Bij consumption: datum van de aankoop zelf (order date_order). |
| Transaction | &lt;transaction&gt;&lt;id&gt; | String | Ja  | Odoo POS transactie-ID. Niet leeg. |
| Transaction | &lt;transaction&gt;&lt;payment_method&gt; | Enum | Ja  | company_link, on_site of online (PM-standaard). on_site dekt cash, kaart en badge wallet betalingen. |

| |     | |     | |
| --- | --- | --- | --- | --- |
| **Kassa → Elastic Stack — system_error** | |     | |     |
| **Bij validatiefouten of systeemfouten. Stuurt naar kassa.errors.** | |     | |     |
| **Object** | **XML-Veld** | **Datatype** | **Verplicht** | **Toelichting / Validatieregel** |
| Header | &lt;header&gt;&lt;message_id&gt; | UUID v4 | Ja  | Uniek per bericht |
| Header | &lt;header&gt;&lt;type&gt; | Enum | Ja  | Altijd: system_error |
| Header | &lt;header&gt;&lt;source&gt; | String | Ja  | Altijd: kassa |
| Header | &lt;header&gt;&lt;timestamp&gt; | ISO-8601 UTC | Ja  | Formaat: YYYY-MM-DDTHH:MM:SSZ |
| Header | &lt;header&gt;&lt;version&gt; | String | Ja  | Altijd: 2.0 |
| Body | &lt;error_code&gt; | String | Ja  | Zie enum tabel §5. Altijd lowercase. |
| Body | &lt;error_description&gt; | String | Ja  | Leesbare beschrijving voor de admin |
| Body | &lt;related_message_id&gt; | String | Nee | message_id van het bericht dat de fout veroorzaakte. Verplicht bij badge_not_found. |

| |     | |     | |
| --- | --- | --- | --- | --- |
| **Kassa → Drupal (Frontend) — payment_status** | |     | |     |
| **Na succesvolle betaling van een inschrijving aan de kassa (payment_context=registration).** | |     | |     |
| **Object** | **XML-Veld** | **Datatype** | **Verplicht** | **Toelichting / Validatieregel** |
| Header | &lt;header&gt;&lt;message_id&gt; | UUID v4 | Ja  | Uniek UUID v4 per bericht |
| Header | &lt;header&gt;&lt;type&gt; | Enum | Ja  | Altijd: payment_status |
| Header | &lt;header&gt;&lt;source&gt; | String | Ja  | Altijd: kassa |
| Header | &lt;header&gt;&lt;timestamp&gt; | ISO-8601 UTC | Ja  | Formaat: YYYY-MM-DDTHH:MM:SSZ |
| Header | &lt;header&gt;&lt;version&gt; | String | Ja  | Altijd: 2.0 |
| Body | &lt;user_id&gt; | UUID v4 | Ja  | Unieke sleutel klantprofiel (x_user_id) |
| Body | &lt;payment_status&gt; | Enum | Ja  | paid of pending |

| |     | |     | |
| --- | --- | --- | --- | --- |
| **Kassa → Drupal (Frontend) — wallet_balance_update** | |     | |     |
| **Na elke badge-aankoop, Top-up, Badge Wallet betaling of terugbetaling via badge_wallet (Flow 15). Drupal toont het bijgewerkte saldo op de profielpagina.** | |     | |     |
| **Object** | **XML-Veld** | **Datatype** | **Verplicht** | **Toelichting / Validatieregel** |
| Header | &lt;header&gt;&lt;message_id&gt; | UUID v4 | Ja  | Uniek UUID v4 per bericht |
| Header | &lt;header&gt;&lt;type&gt; | Enum | Ja  | Altijd: wallet_balance_update |
| Header | &lt;header&gt;&lt;source&gt; | String | Ja  | Altijd: kassa |
| Header | &lt;header&gt;&lt;timestamp&gt; | ISO-8601 UTC | Ja  | Formaat: YYYY-MM-DDTHH:MM:SSZ |
| Header | &lt;header&gt;&lt;version&gt; | String | Ja  | Altijd: 2.0 |
| Body | &lt;user_id&gt; | UUID v4 | Ja  | Unieke sleutel klantprofiel |
| Body | &lt;wallet_balance&gt; | Decimal (EUR) | Ja  | Huidig saldo NA transactie. Positief decimaal. Geschreven naar x_wallet_balance in Odoo door poller.py. |

| |     | |     | |
| --- | --- | --- | --- | --- |
| **Kassa → CRM (Salesforce) — invoice_request** | |     | |     |
| **Factuuraanvraag van een particuliere klant aan de kassa.** | |     | |     |
| **Object** | **XML-Veld** | **Datatype** | **Verplicht** | **Toelichting / Validatieregel** |
| Header | &lt;header&gt;&lt;message_id&gt; | UUID v4 | Ja  | Uniek UUID v4 per bericht |
| Header | &lt;header&gt;&lt;type&gt; | Enum | Ja  | Altijd: invoice_request |
| Header | &lt;header&gt;&lt;source&gt; | String | Ja  | Altijd: kassa |
| Header | &lt;header&gt;&lt;timestamp&gt; | ISO-8601 UTC | Ja  | Formaat: YYYY-MM-DDTHH:MM:SSZ |
| Header | &lt;header&gt;&lt;version&gt; | String | Ja  | Altijd: 2.0 |
| Header | &lt;header&gt;&lt;correlation_id&gt; | UUID v4 | Cond. | UUID van bijhorend consumption_order bericht. Optioneel maar sterk aanbevolen. |
| Body | &lt;user_id&gt; | UUID v4 | Ja  | Unieke sleutel klantprofiel matching |
| Invoice data | &lt;invoice_data&gt;&lt;first_name&gt; | String | Ja  | Voornaam factuurontvanger |
| Invoice data | &lt;invoice_data&gt;&lt;last_name&gt; | String | Ja  | Achternaam factuurontvanger |
| Invoice data | &lt;invoice_data&gt;&lt;email&gt; | String | Ja  | Geldig e-mailadresformaat |
| Invoice data | &lt;invoice_data&gt;&lt;address&gt;&lt;street&gt; | String | Ja  | Straatnaam |
| Invoice data | &lt;invoice_data&gt;&lt;address&gt;&lt;number&gt; | String | Ja  | Huisnummer |
| Invoice data | &lt;invoice_data&gt;&lt;address&gt;&lt;postal_code&gt; | String | Ja  | Postcode |
| Invoice data | &lt;invoice_data&gt;&lt;address&gt;&lt;city&gt; | String | Ja  | Gemeente |
| Invoice data | &lt;invoice_data&gt;&lt;address&gt;&lt;country&gt; | String | Ja  | ISO-3166 lowercase (bv. be) |
| Invoice data | &lt;invoice_data&gt;&lt;vat_number&gt; | String | Cond. | Optioneel. Verplicht als factuur op bedrijfsnaam. |

| |     | |     | |
| --- | --- | --- | --- | --- |
| **Kassa → CRM (Salesforce) — badge_assigned** | |     | |     |
| **Bij aankomst koppelt de kassamedewerker een badge aan het account. Formeel goedgekeurd door PM (Vraag 37).** | |     | |     |
| **Object** | **XML-Veld** | **Datatype** | **Verplicht** | **Toelichting / Validatieregel** |
| Header | &lt;header&gt;&lt;message_id&gt; | UUID v4 | Ja  | Uniek UUID v4 per bericht |
| Header | &lt;header&gt;&lt;type&gt; | Enum | Ja  | Altijd: badge_assigned |
| Header | &lt;header&gt;&lt;source&gt; | String | Ja  | Altijd: kassa |
| Header | &lt;header&gt;&lt;timestamp&gt; | ISO-8601 UTC | Ja  | Formaat: YYYY-MM-DDTHH:MM:SSZ |
| Header | &lt;header&gt;&lt;version&gt; | String | Ja  | Altijd: 2.0 |
| Body | &lt;badge_id&gt; | String | Ja  | Uniek ID van de badge. Formaat afhankelijk van technologie (QR/NFC/RFID). |
| Body | &lt;user_id&gt; | UUID v4 | Ja  | UUID van de bezoeker. CRM koppelt dit in Salesforce. |
| Body | &lt;assigned_at&gt; | ISO-8601 UTC | Ja  | Tijdstip van koppeling. Voor audittrail en conflictdetectie. |

| |     | |     | |
| --- | --- | --- | --- | --- |
| **Kassa → CRM (Salesforce) — refund_processed** | |     | |     |
| **Terugbetaling na kassacorrectie. Kassa initieert enkel kassacorrecties — planningswijzigingen zijn verantwoordelijkheid van CRM/Facturatie.** | |     | |     |
| **Object** | **XML-Veld** | **Datatype** | **Verplicht** | **Toelichting / Validatieregel** |
| Header | &lt;header&gt;&lt;message_id&gt; | UUID v4 | Ja  | Uniek UUID v4 per bericht |
| Header | &lt;header&gt;&lt;type&gt; | Enum | Ja  | Altijd: refund_processed |
| Header | &lt;header&gt;&lt;source&gt; | String | Ja  | Altijd: kassa |
| Header | &lt;header&gt;&lt;timestamp&gt; | ISO-8601 UTC | Ja  | Formaat: YYYY-MM-DDTHH:MM:SSZ |
| Header | &lt;header&gt;&lt;version&gt; | String | Ja  | Altijd: 2.0 |
| Header | &lt;header&gt;&lt;correlation_id&gt; | UUID v4 | Ja  | message_id van de originele payment_registered die terugbetaald wordt. |
| Body | &lt;refund_type&gt; | Enum | Ja  | consumption_item of partial |
| Body | &lt;user_id&gt; | UUID v4 | Cond. | Aanwezig als originele betaling niet anoniem was. |
| Body | &lt;refund&gt;&lt;amount currency="eur"&gt; | Decimal | Ja  | Terug te betalen bedrag. Attribuut currency altijd eur. |
| Body | &lt;refund&gt;&lt;method&gt; | Enum | Ja  | badge_wallet, cash of card_reversal |
| Body | &lt;refund&gt;&lt;reason&gt; | Enum | Ja  | duplicate_payment, customer_request of system_error |
| Body | &lt;refund&gt;&lt;description&gt; | String | Nee | Leesbare omschrijving voor CRM-notitie |
| Body | &lt;original_transaction_id&gt; | String | Ja  | Odoo POS transactie-ID van de oorspronkelijke betaling |
| Body | &lt;new_wallet_balance currency="eur"&gt; | Decimal | Cond. | Nieuw saldo na terugbetaling. Alleen aanwezig als method=badge_wallet. |

## 4\. Conditionele Velden — Businessregels

| |     | |     |
| --- | --- | --- | --- |
| **Veld** | **Conditie** | **Actie bij ontbreken** | **Foutmelding (kassa.errors)** |
| &lt;vat_number&gt; | Verplicht als customer.type = company | → kassa.errors | ERROR: btw_nummer required when type=company |
| &lt;location&gt; | Verplicht bij badge_scanned | → kassa.errors | ERROR: location required for badge_scanned |
| &lt;company_name&gt; | Verplicht als customer.type = company | → kassa.errors | ERROR: company_name required when type=company |
| &lt;customer&gt; blok | Verplicht als is_anonymous = false of afwezig | → kassa.errors / DLQ | XSD-validatiefout: customer required when is_anonymous=false |
| &lt;invoice&gt;&lt;id&gt; | Verplicht bij payment_context=consumption. Afwezig bij registration. | Geen fout — by design | CRM maakt factuur aan bij registration |
| &lt;related_message_id&gt; | Optioneel bij system_error, verplicht bij badge_not_found | Bericht wordt alsnog verstuurd | —   |

Conditionele logica (zoals vat_number verplicht als type=company) wordt afgedwongen in de Python receiver, niet door het basis-XSD.

## 5\. Enum Waarden — Volledige Referentie

Gebruik uitsluitend de onderstaande waarden. Geen hoofdletters, geen spaties, geen Nederlandse varianten.

| |     | |
| --- | --- | --- |
| **Element** | **Toegestane waarden** | **Toelichting** |
| &lt;header&gt;&lt;type&gt; | new_registration, badge_scanned, consumption_order, payment_registered, system_error, profile_update, payment_status, cancel_registration, wallet_balance_update, invoice_request, badge_assigned, refund_processed | Bepaalt routing en validatie. PM-goedgekeurd (Vraag 37). |
| &lt;customer&gt;&lt;type&gt; | company, private | Bepaalt of factuur aangemaakt wordt en of bedrijfsvelden verplicht zijn. |
| &lt;payment_due&gt;&lt;status&gt; | unpaid, paid | Status van de inschrijvingsbetaling in new_registration |
| &lt;payment_status&gt; | paid, pending | Betaalstatus doorgestuurd naar Drupal |
| &lt;invoice&gt;&lt;status&gt; | paid, pending, cancelled | Status van de factuur in payment_registered |
| &lt;transaction&gt;&lt;payment_method&gt; | company_link, on_site, online | Betaalmethode — conform PM XML_naamgeving standaard §4. on_site dekt cash, kaart en badge wallet. Geen andere waarden toegestaan. |
| &lt;error_code&gt; | invalid_xml_format, unknown_message_type, profile_not_found, odoo_api_error, offline_queue_full, badge_not_found | Foutcategorisering voor Elastic — altijd lowercase. unknown_message_type: onbekend type in receiver.py. |
| &lt;refund&gt;&lt;method&gt; | badge_wallet, cash, card_reversal | Terugbetalingsmethode |
| &lt;refund&gt;&lt;reason&gt; | duplicate_payment, customer_request, system_error | Gestandaardiseerde reden voor terugbetaling |
| &lt;refund_type&gt; | consumption_item, partial | Scope van de terugbetaling |
| &lt;payment_context&gt; | registration, consumption | Onderscheidt inschrijvings- van consumptiebetaling in payment_registered |
| &lt;vat_rate&gt; | 0, 6, 12, 21 | 0 voor Top-up producten. De poller identificeert deze producten via de POS-categorie 'Top-ups' of het custom veld `x_is_topup` op `product.product`, niet enkel op het BTW-tarief. `vat_rate=0` wordt altijd geforceerd in de XML-export voor deze producten door `poller.py`. BTW-percentage voor overige producten opgehaald via `account.tax`. |

Team Kassa | Datamapping v2.5 | Conform XML_naamgeving standaard | Integratieproject Desideriushogeschool | 2026
