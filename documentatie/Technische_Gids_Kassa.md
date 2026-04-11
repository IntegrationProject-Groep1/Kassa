# Technische Gids & Opstartplan

Team Kassa (Odoo POS) | Versie 3.2 - Definitief geïntegreerd document

Integratieproject Desideriushogeschool 2026

| |     |
| --- | --- |
| **Veld** | **Waarde** |
| Project | Integratieproject Desideriushogeschool 2026 |
| Team | Kassa (Odoo POS) |
| Versie | 3.5 — sender v3.5 (total_amount per item); poller v1.3 (is_topup_product categorie-check); XSD consumption_order → v2.2 |
| Tech stack | Odoo 17, PostgreSQL 15, Python 3.12, RabbitMQ, Docker, GitHub Actions |

## **1\. Het grote plaatje — hoe hangt alles samen?**

Dit project heeft 9 softwaresystemen die allemaal met elkaar communiceren via één centraal systeem: RabbitMQ. Elk systeem staat op zichzelf (loosely coupled) en communiceert enkel via de centrale berichtenwachtrij.

Loosely coupled: elk systeem staat op zichzelf en kent andere systemen NIET rechtstreeks. Communicatie: enkel via RabbitMQ — een centrale postbus. Actie & Reactie: systeem X plaatst een bericht in de postbus. Systeem Y leest het en doet zijn ding.

## **1.1 Alle systemen op een rij**

| |     | |     |
| --- | --- | --- | --- |
| **Systeem** | **Software** | **Wat doet het?** | **Contact met Kassa?** |
| Frontend | Drupal | Website — inschrijvingen, saldo tonen | Ja — stuurt inschrijvingen / ontvangt betaalstatus |
| Kassa (jullie) | Odoo POS | Betalingen op het event, consumpties bar | —   |
| Facturatie | FOSSBilling | Facturen aanmaken en versturen | Nee — verloopt via CRM |
| CRM | Salesforce | Klant- en bedrijfsgegevens bijhouden | Ja — profielen synchroniseren |
| Monitoring | Elastic Stack | Dashboard, uptime bewaken, alerts | Ja — heartbeat / errors sturen |
| Mailing | SendGrid | E-mails versturen | Indirect via CRM/Facturatie |
| Planning | Office 365 | Schema van sessies en sprekers | Nee (voor kassa) |
| Infra | VMs / Docker | Servers, containers, pipelines beheren | Ja — jullie draaien op hun infra |
| IoT | Raspberry Pi | Badge scanner aan inkom en bar | Ja — stuurt badge IDs door |

## **1.2 Hoe een bericht stroomt — concreet voorbeeld**

Stel: een zakelijke bezoeker rekent zijn consumpties af aan de bar. Dit is wat er stap voor stap gebeurt:

| |     | |
| --- | --- | --- |
| **Stap** | **Wie** | **Actie** |
| 1   | Kassamedewerker | Klikt 'Betaling bevestigd' in Odoo POS |
| 2   | poller.py | Detecteert nieuwe 'done' order via XML-RPC polling op Odoo |
| 3   | sender.py | Bouwt consumption_order + payment_registered XML |
| 4   | kassa.exchange | Berichten worden gepubliceerd met juiste routing keys |
| 5   | Salesforce CRM | Leest berichten en werkt klantprofiel bij op basis van user_id |
| 6   | FOSSBilling | CRM triggert FOSSBilling om de totaalfactuur te maken |
| 7   | SendGrid | Stuurt de factuurmail naar de klant |

Jullie doen enkel stap 1 t.e.m. 4. De rest doen andere teams.

## **2\. RabbitMQ — de postbus tussen alle systemen**

## **2.1 Wat is RabbitMQ?**

RabbitMQ is de centrale postbus van het project. In plaats van dat elk systeem rechtstreeks met elk ander systeem communiceert, legt iedereen berichten in de postbus en haalt iedereen berichten op die voor hen bedoeld zijn.

Producer (= Sender): het systeem dat een bericht stuurt naar RabbitMQ. Jullie Odoo doet dit. Queue: een wachtrij waar berichten in zitten te wachten tot ze opgepikt worden. Consumer (= Receiver): het systeem dat berichten leest uit een queue. Jullie Odoo doet dit ook.

## **2.2 De queues en routing keys**

Kassa verstuurt berichten via kassa.exchange (topic exchange). Het Controlroom-team kan passief meeluisteren via eigen bindings op routing key 'kassa.#'. Afstemming met Infra over exchange-configuratie loopt nog (Vraag 30).

Routing keys voor payment_registered zijn gesplitst per payment_context. Gebruik altijd de specifieke msg_type in send_typed_message().

| |     | |     | |
| --- | --- | --- | --- | --- |
| **Queue** | **Routing key** | **Verstuurt** | **Leest** | **Waarvoor** |
| kassa.incoming | —   | Frontend, CRM, IoT | Odoo (Kassa) | Inschrijvingen, profielupdates, badge scans |
| kassa.payments | kassa.payments.consumption | Odoo (Kassa) | Salesforce CRM | consumption_order, payment_registered (consumption) |
| kassa.payments | kassa.payments.registration | Odoo (Kassa) | Salesforce CRM | payment_registered (registration) |
| kassa.payments | kassa.payments.refund | Odoo (Kassa) | Salesforce CRM | refund_processed |
| kassa.payments | kassa.payments.badge | Odoo (Kassa) | Salesforce CRM | badge_assigned |
| kassa.payments | kassa.payments.invoice | Odoo (Kassa) | Salesforce CRM | invoice_request |
| frontend.payments | kassa.frontend.payment | Odoo (Kassa) | Drupal | payment_status |
| frontend.payments | kassa.frontend.wallet | Odoo (Kassa) | Drupal | wallet_balance_update |
| kassa.errors | kassa.errors | Odoo (Kassa) bij fout | Elastic Stack | Fouten melden |

## **3\. Odoo POS — hoe werkt het en hoe schrijf je er code voor?**

## **3.1 Wat is Odoo?**

Odoo is een groot open-source ERP-systeem. Jullie gebruiken enkel de POS-module (Point of Sale). Odoo draait als webapplicatie. Jullie code draait NAAST Odoo en communiceert via een API.

## **3.2 De Odoo XML-RPC API**

Odoo heeft een ingebouwde XML-RPC API. Je stuurt een verzoek, Odoo antwoordt met data. Hier is hoe je klanten zoekt op basis van de externe user_id (UUID):

import xmlrpc.client

ODOO_URL = '<http://localhost:8069>'

ODOO_DB = 'odoo_kassa'

ODOO_USER = '<admin@school.be>'

ODOO_PASS = 'jouw_wachtwoord'

\# Stap 1: Inloggen en uid ophalen

common = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/common')

uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASS, {})

\# Stap 2: Object endpoint voor verdere calls

models = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/object')

\# Stap 3: Klant opzoeken via externe UUID (x_user_id custom veld)

klant = models.execute_kw(

ODOO_DB, uid, ODOO_PASS,

'res.partner', 'search_read',

\[\[\['x_user_id', '=', 'e8b27c1d-4f2a-4b3e-9c5f-123456789abc'\]\]\],

{'fields': \['id', 'name', 'x_user_id'\], 'limit': 1}

)

if klant:

print(f"Klant gevonden: {klant\[0\]\['name'\]} (Odoo ID: {klant\[0\]\['id'\]})")

else:

print('Klant niet gevonden -> nieuwe registratie aanmaken')

## **3.2.1 Incident: Odoo webassets 500 na container herstart**

Symptoom: Odoo POS of backend laadt niet volledig en geeft 500-fouten op paden zoals /web/assets/... met FileNotFoundError in ir_attachment.

Root cause: de database verwijst naar asset-bijlagen in de filestore, maar die bestanden ontbreken op schijf. Dit gebeurt typisch wanneer /var/lib/odoo niet persistent gemount is en de container opnieuw aangemaakt werd.

Preventie (verplicht): mount altijd een Docker named volume op /var/lib/odoo in de kassa-web service.

Herstelprocedure op VM:

1. Compose met persistent filestore deployen.

2. Odoo container recreaten:
docker compose up -d --force-recreate kassa-web

3. Enkel asset-records laten herbouwen:
docker exec -i kassa_db psql -U odoo -d odoo_kassa -c "DELETE FROM ir_attachment WHERE url LIKE '/web/assets/%';"

4. Odoo herstarten:
docker compose restart kassa-web

5. Browser hard refresh (Ctrl+F5).

Opmerking: XML-RPC deprecation warnings in Odoo 19 zijn informatief en niet de oorzaak van deze 500-fouten.

## **3.3 Belangrijke Odoo modellen**

| |     | |
| --- | --- | --- |
| **Model** | **Wat stelt het voor?** | **Wanneer gebruiken?** |
| res.partner | Klanten en bedrijven | Profiel opzoeken via x_user_id, aanmaken, updaten |
| pos.order | Kassabestellingen | Bestelling registreren, status opvragen |
| pos.order.line | Regels in een bestelling | Producten, prijzen en BTW-tarieven per order ophalen |
| pos.session | Een kassasessie | Weten welke sessie actief is |
| product.product | Producten | Producten opzoeken voor bestelling |
| pos.payment | Betalingen per order | Betaalmethode detecteren (bv. Badge Wallet) |
| account.tax | Belastingtarieven | BTW-percentage ophalen via tax_ids van orderregels |
| pos.category | POS-productcategorieën | Top-up producten identificeren via de categorie 'Top-ups' in `is_topup_product()` |
| product.product | Producten (uitgebreid) | Custom veld `x_is_topup` opvragen als alternatieve identificatie voor Top-up producten |

## **3.4 Custom velden in Odoo**

De integratie vereist een aantal custom velden op res.partner en pos.order. Deze worden aangemaakt via Odoo > Instellingen > Technisch > Velden.

| |     | |     |
| --- | --- | --- | --- |
| **Model** | **Veldnaam** | **Type** | **Gebruik** |
| res.partner | x_user_id | Char | Externe UUID van het CRM — primaire koppelsleutel |
| res.partner | x_badge_id | Char | Badge ID — aangemaakt bij Flow 12 (badge_assigned) |
| res.partner | x_wallet_balance | Float | Badge saldo in EUR — Single Source of Truth |
| res.partner | x_date_of_birth | Date | Geboortedatum bezoeker — voor alcoholcontrole (leeftijd berekend in code) |
| res.partner | x_outstanding_amount | Float | Openstaand inschrijvingsbedrag in EUR — ingelezen uit `<payment_due><amount>` in `new_registration` / `profile_update`. Gereset naar 0 door `order_poller.py` na succesvolle betaling via Inschrijvingskassa (Story 21). |
| res.partner | x_payment_status | Char | Betaalstatus van de inschrijving — ingelezen uit `<payment_due><status>` (`unpaid` of `paid`). Gezet op `paid` door `order_poller.py` na succesvolle betaling (Story 21). |
| pos.order | x_rabbitmq_sent | Boolean | True als order al naar RabbitMQ is verstuurd — voor poller |
| product.product | x_is_topup | Boolean | Markeert een product als Top-up — primair identificatiekenmerk voor `poller.py`. Alternatief voor categorie-check. Aanmaken via Odoo > Instellingen > Technisch > Velden op model `product.product`. |

**Betaalmethoden aanmaken in Odoo POS (geen custom veld nodig):**

| |     | |
| --- | --- | --- |
| **Betaalmethode** | **Aanmaken via** | **Gebruik** |
| Cash | Odoo > Point of Sale > Configuratie > Betaalmethoden | Contante betaling |
| Bancontact | Odoo > Point of Sale > Configuratie > Betaalmethoden | Kaartbetaling |
| Badge Wallet | Odoo > Point of Sale > Configuratie > Betaalmethoden | Badge-saldo betaling — naam moet overeenkomen met BADGE_PAYMENT_METHOD_NAME in poller.py |

De betaalmethode 'Badge Wallet' is uitsluitend intern in Odoo. In de externe XML (payment_registered) wordt altijd 'on_site' verstuurd — dit is conform de PM-standaard.

## **3.5 Odoo Addon: kassa_pos_custom**

De `kassa_pos_custom` addon breidt de standaard Odoo POS-interface uit via OWL-componenten (het JavaScript UI-framework van Odoo 17). Deze addon is vereist voor Stories 9, 17, 19 en 21.

**Afhankelijkheid Story 21 — real-time cache update:**

Na het verwerken van een `new_registration` of `profile_update` publiceert `receiver.py` een `bus.bus` event via Odoo XML-RPC. Een OWL-component in `kassa_pos_custom` luistert op dit event. Bij ontvangst haalt de component via één gerichte RPC-aanroep enkel die ene partner op en voegt hem toe aan (of update hem in) de lokale POS model store — **zonder volledige partnerlijst te herladen en zonder lopende transacties te onderbreken**.

Dit mechanisme is dezelfde `bus.bus` infrastructuur als Story 9 (badge wallet saldo update in de POS UI).

**Vereiste configuratie:**

- `kassa_pos_custom` addon geïnstalleerd en geactiveerd in Odoo
- `bus.bus` polling actief in de POS-sessie (standaard ingeschakeld in Odoo 17 POS)
- Custom velden `x_outstanding_amount` en `x_payment_status` aangemaakt op `res.partner` (zie §3.4)

## **4\. Sender, Receiver & Poller — de brug tussen Odoo en RabbitMQ**

## **4.1 De Sender — berichten versturen (v3.5)**

sender.py verzorgt alle uitgaande berichten. Bevat de buffer-logica (incl. bufferlimiet), exchange-setup, routing key mapping, alle builder-functies voor de 7 uitgaande berichttypes, send_error_to_queue en de publieke hulpfunctie now_utc().

**Wijzigingen t.o.v. v3.4:**

• total_amount toegevoegd aan build_consumption_order_xml per item (quantity × unit_price)

• schema_consumption_order_v2.2.xsd → v2.2

**Wijzigingen t.o.v. v3.3 (eerder):**

• ROUTING_KEYS gesplitst: payment_registered_consumption (kassa.payments.consumption) en payment_registered_registration (kassa.payments.registration)

• now_utc() hernoemd van \_now_utc() — nu publiek importeerbaar vanuit receiver.py

• BUFFER_MAX_MESSAGES = 500 toegevoegd — offline_queue_full error bij volle buffer

• send_error_to_queue refactored: gebruikt nu \_make_header() — geen handmatige header-opbouw meer

• Alle 9 functies aanwezig: 7 builders + send_error_to_queue + send_typed_message (dispatcher)

\# sender.py — v3.5 — total_amount per item toegevoegd (XSD v2.2)

\# Alle berichten via kassa.exchange (topic). Bij verbindingsverlies

\# worden berichten lokaal gebufferd in /app/outbox/outbox.json.

\# Dit pad is gemount als Docker named volume — overleeft container-herstart.

import pika, json, os, uuid, pathlib

import xml.etree.ElementTree as ET

from datetime import datetime, timezone

RABBIT_HOST = os.environ.get("RABBIT_HOST")

RABBIT_USER = os.environ.get("RABBIT_USER")

RABBIT_PASS = os.environ.get("RABBIT_PASS")

EXCHANGE_NAME = os.environ.get("RABBIT_EXCHANGE", "kassa.exchange")

\# Afstemming met Infra-team over exchange type en bindings loopt nog (Vraag 30)

\# ── Routing key mapping ──────────────────────────────────────────────────

\# payment_registered heeft twee keys: één per payment_context.

\# Gebruik 'payment_registered_consumption' of 'payment_registered_registration'

\# als msg_type in send_typed_message() — nooit 'payment_registered' rechtstreeks.

ROUTING_KEYS = {

"consumption_order": "kassa.payments.consumption",

"payment_registered_consumption": "kassa.payments.consumption",

"payment_registered_registration":"kassa.payments.registration",

"invoice_request": "kassa.payments.invoice",

"badge_assigned": "kassa.payments.badge",

"refund_processed": "kassa.payments.refund",

"payment_status": "kassa.frontend.payment",

"wallet_balance_update": "kassa.frontend.wallet",

"system_error": "kassa.errors",

}

\# ── Lokale buffer ─────────────────────────────────────────────────────────

\# outbox.json staat op een Docker named volume (zie docker-compose.yml).

BUFFER_FILE = pathlib.Path("/app/outbox/outbox.json")

BUFFER_MAX_MESSAGES = 500 # Maximaal 500 berichten — daarna offline_queue_full

def \_buffer_message(routing_key: str, message_xml: str) -> None:

entry = {"routing_key": routing_key, "xml": message_xml}

entries = \_read_buffer()

if len(entries) >= BUFFER_MAX_MESSAGES:

\# Buffer vol — bericht weggooien en error rapporteren naar queue.errors

print(f"\[SENDER\] Buffer vol ({BUFFER_MAX_MESSAGES} items) — bericht gedrop: {routing_key}")

send_error_to_queue("offline_queue_full", None,

f"Outbox vol: {len(entries)}/{BUFFER_MAX_MESSAGES} — bericht niet gebufferd: {routing_key}")

return

entries.append(entry)

BUFFER_FILE.parent.mkdir(parents=True, exist_ok=True)

BUFFER_FILE.write_text(json.dumps(entries, ensure_ascii=False))

def \_read_buffer() -> list:

if not BUFFER_FILE.exists():

return \[\]

try:

return json.loads(BUFFER_FILE.read_text())

except Exception:

return \[\]

def flush_buffer() -> None:

"""Herstuur alle gebufferde berichten. Aanroepen bij succesvolle reconnect."""

entries = \_read_buffer()

if not entries:

return

succeeded = \[\]

for entry in entries:

try:

send_message(entry\["routing_key"\], entry\["xml"\])

succeeded.append(entry)

except Exception as e:

print(f"\[BUFFER\] Herstuur mislukt voor {entry.get('routing_key','?')}: {e}")

break # stop bij eerste fout, probeer later opnieuw

remaining = \[e for e in entries if e not in succeeded\]

if remaining:

BUFFER_FILE.write_text(json.dumps(remaining, ensure_ascii=False))

else:

BUFFER_FILE.unlink(missing_ok=True)

if succeeded:

print(f"\[BUFFER\] {len(succeeded)} gebufferde berichten hersturen geslaagd.")

\# ── RabbitMQ connectie en exchange ───────────────────────────────────────

def connect_to_rabbitmq():

credentials = pika.PlainCredentials(RABBIT_USER, RABBIT_PASS)

params = pika.ConnectionParameters(host=RABBIT_HOST, credentials=credentials)

return pika.BlockingConnection(params)

def setup_exchange(channel):

channel.exchange_declare(

exchange=EXCHANGE_NAME,

exchange_type="topic", # Controlroom bindt op 'kassa.#'

durable=True

)

def send_message(routing_key: str, message_xml: str) -> None:

"""Verstuurt via kassa.exchange. Bij fout: bufferen in outbox.json."""

try:

conn = connect_to_rabbitmq()

channel = conn.channel()

setup_exchange(channel)

channel.basic_publish(

exchange=EXCHANGE_NAME,

routing_key=routing_key,

body=message_xml.encode("utf-8"),

properties=pika.BasicProperties(delivery_mode=2)

)

conn.close()

print(f"\[SENDER\] Verstuurd: routing_key={routing_key}")

except Exception as e:

\# Bufferen conform Vraag 11 & 17 — kassa blijft werken bij uitval

\_buffer_message(routing_key, message_xml)

print(f"\[SENDER\] Gebufferd (routing_key={routing_key}): {e}")

def send_typed_message(msg_type: str, message_xml: str) -> None:

routing_key = ROUTING_KEYS.get(msg_type, f"kassa.misc.{msg_type}")

send_message(routing_key, message_xml)

\# ── Hulpfuncties ──────────────────────────────────────────────────────────

def now_utc() -> str:

"""ISO-8601 UTC: YYYY-MM-DDTHH:MM:SSZ — geen microseconden, geen +00:00"""

return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S') + 'Z'

def \_make_header(root, msg_type, correlation_id=None):

header = ET.SubElement(root, "header")

ET.SubElement(header, "message_id").text = str(uuid.uuid4())

ET.SubElement(header, "type").text = msg_type

ET.SubElement(header, "source").text = "kassa"

ET.SubElement(header, "timestamp").text = now_utc()

ET.SubElement(header, "version").text = "2.0"

if correlation_id:

ET.SubElement(header, "correlation_id").text = correlation_id

return header

def \_to_xml(root) -> str:

return ET.tostring(root, encoding="utf-8",

xml_declaration=True).decode("utf-8")

\# ── Builder functies — alle uitgaande flows ───────────────────────────────

def build_consumption_order_xml(

items, customer_id=None, user_id=None,

is_company_linked=False, company_id=None,

email=None, address=None, is_anonymous=False

) -> str:

root = ET.Element("message")

\_make_header(root, "consumption_order")

body = ET.SubElement(root, "body")

ET.SubElement(body, "is_anonymous").text = str(is_anonymous).lower()

if not is_anonymous:

cust = ET.SubElement(body, "customer")

ET.SubElement(cust, "id").text = str(customer_id)

ET.SubElement(cust, "user_id").text = user_id

ET.SubElement(cust, "is_company_linked").text = str(is_company_linked).lower()

if company_id:

ET.SubElement(cust, "company_id").text = company_id

ET.SubElement(cust, "email").text = email

if address:

addr = ET.SubElement(cust, "address")

for k, v in address.items():

ET.SubElement(addr, k).text = v

items_el = ET.SubElement(body, "items")

for i in (items or \[\]):

el = ET.SubElement(items_el, "item")

ET.SubElement(el, "id").text = i\["id"\]

ET.SubElement(el, "description").text = i\["description"\]

ET.SubElement(el, "quantity").text = str(i\["quantity"\])

up = ET.SubElement(el, "unit_price")

up.text = str(i\["unit_price"\])

up.set("currency", i.get("currency", "eur"))

\# total_amount: quantity × unit_price, berekend door poller.py (v1.2)

tp = ET.SubElement(el, "total_amount")

tp.text = f"{i\['total_amount'\]:.2f}"

tp.set("currency", i.get("currency", "eur"))

ET.SubElement(el, "vat_rate").text = str(i\["vat_rate"\])

if i.get("item_type"):

ET.SubElement(el, "item_type").text = i\["item_type"\]

return \_to_xml(root)

def build_payment_registered_xml(

payment_context, invoice_status, amount_paid,

due_date, trx_id, payment_method,

invoice_id=None, user_id=None, correlation_id=None

) -> str:

root = ET.Element("message")

\_make_header(root, "payment_registered", correlation_id)

body = ET.SubElement(root, "body")

ET.SubElement(body, "payment_context").text = payment_context

if user_id:

ET.SubElement(body, "user_id").text = user_id

inv = ET.SubElement(body, "invoice")

if invoice_id:

ET.SubElement(inv, "id").text = invoice_id

ET.SubElement(inv, "status").text = invoice_status

ap = ET.SubElement(inv, "amount_paid")

ap.text = str(amount_paid)

ap.set("currency", "eur")

ET.SubElement(inv, "due_date").text = due_date

trx = ET.SubElement(body, "transaction")

ET.SubElement(trx, "id").text = trx_id

ET.SubElement(trx, "payment_method").text = payment_method

return \_to_xml(root)

def build_payment_status_xml(user_id: str, status: str) -> str:

root = ET.Element("message")

\_make_header(root, "payment_status")

body = ET.SubElement(root, "body")

ET.SubElement(body, "user_id").text = user_id

ET.SubElement(body, "payment_status").text = status

return \_to_xml(root)

def build_wallet_balance_update_xml(user_id: str, balance: float) -> str:

root = ET.Element("message")

\_make_header(root, "wallet_balance_update")

body = ET.SubElement(root, "body")

ET.SubElement(body, "user_id").text = user_id

ET.SubElement(body, "wallet_balance").text = f"{balance:.2f}"

return \_to_xml(root)

def build_invoice_request_xml(

user_id: str, invoice_data: dict, correlation_id=None

) -> str:

root = ET.Element("message")

\_make_header(root, "invoice_request", correlation_id)

body = ET.SubElement(root, "body")

ET.SubElement(body, "user_id").text = user_id

inv = ET.SubElement(body, "invoice_data")

ET.SubElement(inv, "name").text = invoice_data\["name"\]

ET.SubElement(inv, "email").text = invoice_data\["email"\]

addr = ET.SubElement(inv, "address")

for k, v in invoice_data\["address"\].items():

ET.SubElement(addr, k).text = v

if invoice_data.get("vat_number"):

ET.SubElement(inv, "vat_number").text = invoice_data\["vat_number"\]

return \_to_xml(root)

def build_badge_assigned_xml(badge_id: str, user_id: str) -> str:

root = ET.Element("message")

\_make_header(root, "badge_assigned")

body = ET.SubElement(root, "body")

ET.SubElement(body, "badge_id").text = badge_id

ET.SubElement(body, "user_id").text = user_id

ET.SubElement(body, "assigned_at").text = now_utc()

return \_to_xml(root)

def build_refund_processed_xml(

original_payment_msg_id: str,

refund_type: str, refund_amount: float,

refund_method: str, refund_reason: str,

original_transaction_id: str,

user_id=None, description=None, new_wallet_balance=None

) -> str:

root = ET.Element("message")

\_make_header(root, "refund_processed", original_payment_msg_id)

body = ET.SubElement(root, "body")

ET.SubElement(body, "refund_type").text = refund_type

if user_id:

ET.SubElement(body, "user_id").text = user_id

refund = ET.SubElement(body, "refund")

amt = ET.SubElement(refund, "amount")

amt.text = str(refund_amount)

amt.set("currency", "eur")

ET.SubElement(refund, "method").text = refund_method

ET.SubElement(refund, "reason").text = refund_reason

if description:

ET.SubElement(refund, "description").text = description

ET.SubElement(body, "original_transaction_id").text = original_transaction_id

if new_wallet_balance is not None:

wb = ET.SubElement(body, "new_wallet_balance")

wb.text = f"{new_wallet_balance:.2f}"

wb.set("currency", "eur")

return \_to_xml(root)

\# ── Foutafhandeling — system_error naar queue.errors ─────────────────────

def send_error_to_queue(

error_code: str, related_message_id, error_description: str

) -> None:

"""Stuurt system_error bericht via kassa.exchange (routing key: kassa.errors)."""

root = ET.Element("message")

\_make_header(root, "system_error") # hergebruik van centrale header-builder

body = ET.SubElement(root, "body")

ET.SubElement(body, "error_code").text = error_code.lower()

ET.SubElement(body, "error_description").text = error_description\[:500\]

if related_message_id:

ET.SubElement(body, "related_message_id").text = related_message_id

error_xml = ET.tostring(root, encoding="utf-8",

xml_declaration=True).decode("utf-8")

try:

send_message("kassa.errors", error_xml)

except Exception as err:

\# Als de error zelf ook niet verstuurd kan worden: enkel loggen

print(f"\[SENDER\] Kon error niet sturen naar queue: {err}")

## **4.2 De Receiver — berichten ontvangen (v3.3)**

receiver.py verwerkt alle inkomende berichten van kassa.incoming. Bevat idempotentie-check, XSD-validatie placeholder en correcte error handling.

**Wijzigingen t.o.v. v3.2:**

• now_utc() geïmporteerd vanuit sender.py — is_duplicate() gebruikt now_utc() i.p.v. inline datetime

• Import: from sender import send_message, flush_buffer, send_error_to_queue, now_utc

\# receiver.py — v3.3 — Idempotentie + now_utc import + correcte imports en error handling

\# send_error_to_queue en now_utc geïmporteerd vanuit sender.py.

import pika, os

import xml.etree.ElementTree as ET

from collections import OrderedDict

from sender import send_message, flush_buffer, send_error_to_queue, now_utc

RABBIT_HOST = os.environ.get("RABBIT_HOST")

RABBIT_USER = os.environ.get("RABBIT_USER")

RABBIT_PASS = os.environ.get("RABBIT_PASS")

\# ── Idempotentie cache ────────────────────────────────────────────────────

MAX_CACHE_SIZE = 10_000

seen_message_ids: OrderedDict = OrderedDict()

def is_duplicate(message_id: str) -> bool:

if message_id in seen_message_ids:

print(f"\[IDEMPOTENTIE\] Duplicaat: {message_id} — skip")

return True

seen_message_ids\[message_id\] = (

now_utc()

)

if len(seen_message_ids) > MAX_CACHE_SIZE:

seen_message_ids.popitem(last=False) # LRU eviction

return False

\# ── RabbitMQ connectie ────────────────────────────────────────────────────

def connect_to_rabbitmq():

credentials = pika.PlainCredentials(RABBIT_USER, RABBIT_PASS)

params = pika.ConnectionParameters(host=RABBIT_HOST, credentials=credentials)

return pika.BlockingConnection(params)

\# ── Message verwerking ────────────────────────────────────────────────────

def validate_message(xml_root, msg_type) -> bool:

"""XSD-validatie via lxml. Implementeer per schema voor productie."""

\# from lxml import etree

\# schema = etree.XMLSchema(file=SCHEMA_MAP.get(msg_type))

\# return schema.validate(xml_root)

return True # TODO: implementeer XSD-validatie voor productie

def process_message(ch, method, properties, body):

xml_text = body.decode("utf-8")

related_message_id = None

try:

root = ET.fromstring(xml_text)

mid_el = root.find("header/message_id")

related_message_id = mid_el.text if mid_el is not None else None

msg_type = root.find("header/type").text

\# Idempotentie check — duplicaten stil droppen

if related_message_id and is_duplicate(related_message_id):

ch.basic_ack(delivery_tag=method.delivery_tag)

return

print(f"\[RECEIVER\] Ontvangen: {msg_type} (id={related_message_id})")

if not validate_message(root, msg_type):

raise ValueError(f"Ongeldig berichtformaat voor type {msg_type}")

if msg_type == "new_registration": process_registration(root)

elif msg_type == "profile_update": process_profile_update(root)

elif msg_type == "badge_scanned": process_badge_scan(root)

elif msg_type == "cancel_registration":process_cancel_registration(root)

else:

raise ValueError(f"Onbekend berichttype: {msg_type}")

ch.basic_ack(delivery_tag=method.delivery_tag)

except ET.ParseError as e:

send_error_to_queue("invalid_xml_format", related_message_id,

f"XML parse fout: {e}")

ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

except ValueError as e:

code = ("unknown_message_type" if "Onbekend" in str(e)

else "invalid_xml_format")

send_error_to_queue(code, related_message_id, str(e))

ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

except Exception as e:

send_error_to_queue("odoo_api_error", related_message_id, str(e))

ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

def start_listening(queue_name: str):

conn = connect_to_rabbitmq()

channel = conn.channel()

channel.queue_declare(queue=queue_name, durable=True)

channel.basic_qos(prefetch_count=1)

flush_buffer() # hersend gebufferde berichten bij succesvolle verbinding

channel.basic_consume(queue=queue_name, on_message_callback=process_message)

print(f"\[RECEIVER\] Luisteren op queue: {queue_name} ...")

channel.start_consuming()

## **4.3 Heartbeat — afgehandeld door sidecar (niet meer in kassa-code)**

heartbeat.py is gedocumenteerd in een apart document: Heartbeat_Kassa.docx. Samenvatting:

• Stuurt DIRECT naar heartbeat — niet via kassa.exchange.

• get_system_status() evalueert 3 condities: Odoo bereikbaar, RabbitMQ OK, foutenteller.

• Status 'degraded' als één conditie faalt. Status 'offline' wordt nooit actief verstuurd.

• Mislukte heartbeats worden NIET gebufferd — alleen realtime heartbeats zijn zinvol.

• Timestamp formaat: YYYY-MM-DDTHH:MM:SSZ via strftime (identiek aan now_utc() in sender.py).

## **4.4 De Poller — POS events triggeren (v1.2)**

poller.py draait als daemon-thread en bevraagt Odoo elke POLL_INTERVAL seconden op nieuwe 'done' POS-orders via XML-RPC.

**Wijzigingen t.o.v. v1.2:**

• Top-up identificatie: `is_topup_product()` helperfunctie toegevoegd. Identificeert Top-up producten via POS-categorie 'Top-ups' of custom veld `x_is_topup` op `product.product`. De eerdere detectie puur via `vat_rate=0` is vervangen — `vat_rate=0` wordt nu geforceerd ín de XML-export als gevolg van de categorie-check, niet meer als trigger ervoor.

• `pos.order.line` query uitgebreid met `categ_id` in de fields-lijst voor categorie-lookup.

**Wijzigingen t.o.v. v1.1:**

• total_amount berekening toegevoegd aan item dict in process_order() (line_total = round(qty × price_unit, 2))

**Wijzigingen t.o.v. v1.0 (eerder):**

• due_date: order\['date_order'\]\[:10\] — YYYY-MM-DD, datum van de aankoop zelf

• BTW-tarief: twee-staps lookup via get_tax_rate() → account.tax (was hardcoded op 21%)

• Badge Wallet detectie: get_badge_payment_info() via pos.payment → payment_method_id.name

• Wallet-aftrek: deduct_wallet_balance() schrijft nieuw saldo naar x_wallet_balance op res.partner

• wallet_balance_update naar Drupal verstuurd na elke Badge Wallet betaling

• x_company_id verwijderd — company_id nu via parent_id → x_user_id (Odoo standaard relatie)

• payment_registered verstuurd via 'payment_registered_consumption' (gesplitste routing key)

• date_order toegevoegd aan order fields; tax_ids toegevoegd aan order line fields

Hoe het werkt:

| |     |
| --- | --- |
| **Stap** | **Actie** |
| 1   | Kassamedewerker bevestigt betaling in Odoo POS → order krijgt state='done' |
| 2   | poller.py detecteert de order via search_read op state='done' EN x_rabbitmq_sent=False |
| 3   | poller.py haalt orderregels op met `tax_ids` en `categ_id`; roept `get_tax_rate()` aan per regel voor het BTW-percentage; roept `is_topup_product()` aan per regel voor Top-up identificatie |
| 4   | poller.py detecteert betaalmethode via pos.payment → payment_method_id.name |
| 5   | poller.py bouwt consumption_order XML via sender.py |
| 6   | poller.py bouwt payment_registered XML (context: consumption) via sender.py |
| 7   | Als Badge Wallet: wallet-aftrek op res.partner, wallet_balance_update naar Drupal |
| 8   | Berichten verstuurd via kassa.exchange met correcte routing keys |
| 9   | mark_order_sent() zet x_rabbitmq_sent=True → order wordt niet dubbel verstuurd |

payment_status naar Drupal wordt ENKEL verstuurd bij payment_context=registration (inschrijvingsgeld betaald aan kassa — Flow 14). De poller verwerkt uitsluitend consumption orders. Registratiebetalingen aan de kassa zijn een apart manueel getriggerd flow.

\# poller.py — v1.3 — Top-up identificatie via categorie-check (is_topup_product)

\# wallet balance update, company via parent_id

\# Dit script draait in de kassa-integratie container en bevraagt Odoo

\# elke POLL_INTERVAL seconden op nieuwe 'done' POS-orders.

import xmlrpc.client, threading, time, os

from sender import (

build_consumption_order_xml, build_payment_registered_xml,

build_wallet_balance_update_xml,

send_typed_message, flush_buffer, send_error_to_queue

)

ODOO_URL = os.environ.get("ODOO_URL", "<http://odoo:8069>")

ODOO_DB = os.environ.get("ODOO_DB", "odoo_kassa")

ODOO_USER = os.environ.get("ODOO_USER")

ODOO_PASS = os.environ.get("ODOO_PASS")

POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "3"))

\# Naam van de badge wallet betaalmethode in Odoo POS.

\# Aanmaken via: Odoo > Point of Sale > Configuratie > Betaalmethoden.

\# Pas deze constante aan als de naam in Odoo afwijkt.

BADGE_PAYMENT_METHOD_NAME = "Badge Wallet"

\# Naam van de POS-categorie die Top-up producten groepeert.

\# Aanmaken via: Odoo > Point of Sale > Configuratie > Productcategorieën.

\# Alternatief: gebruik het custom veld x_is_topup op product.product.

TOPUP_CATEGORY_NAME = "Top-ups"

\# ─────────────────────────────────────────────────────────────────────────

def get_odoo_connection():

common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")

uid = common.authenticate(ODOO_DB, ODOO_USER, ODOO_PASS, {})

models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")

return uid, models

def get_unprocessed_orders(models, uid) -> list:

"""Haalt 'done' orders op waarbij x_rabbitmq_sent = False."""

return models.execute_kw(

ODOO_DB, uid, ODOO_PASS,

"pos.order", "search_read",

\[\[\["state", "=", "done"\],

\["x_rabbitmq_sent", "=", False\]\]\],

{"fields": \["id", "name", "partner_id", "lines",

"amount_total", "payment_ids", "date_order"\],

"limit": 50}

)

def mark_order_sent(models, uid, order_id: int) -> None:

"""Zet x_rabbitmq_sent=True na succesvolle publicatie."""

models.execute_kw(

ODOO_DB, uid, ODOO_PASS,

"pos.order", "write",

\[\[order_id\], {"x_rabbitmq_sent": True}\]

)

def get_tax_rate(models, uid, tax_ids: list) -> int:

"""

Haalt het BTW-percentage op via account.tax voor de gegeven tax_ids.

Geeft 0 terug als er geen belasting is.

Geeft het eerste percentage terug als er meerdere zijn.

Opmerking: dit is NIET de primaire methode om Top-up producten te detecteren.

Gebruik is_topup_product() daarvoor. get_tax_rate() levert het werkelijke

BTW-tarief op voor alle andere producten.

"""

if not tax_ids:

return 0

taxes = models.execute_kw(

ODOO_DB, uid, ODOO_PASS,

"account.tax", "search_read",

\[\[\["id", "in", tax_ids\]\]\],

{"fields": \["amount"\], "limit": 1}

)

return int(taxes\[0\]\["amount"\]) if taxes else 0

def is_topup_product(models, uid, product_id: int) -> bool:

"""

Identificeert of een product een Top-up is via de POS-categorie of x_is_topup vlag.

Primaire check: POS-categorie naam == TOPUP_CATEGORY_NAME ('Top-ups').

Fallback check: custom veld x_is_topup == True op product.product.

Dit is de robuuste vervanger voor de eerdere detectie via vat_rate=0.

De koppeling 'BTW=0 => Top-up' is losgelaten: de categorie bepaalt

wat een Top-up is; vat_rate=0 wordt daarna geforceerd in de XML-export.

"""

if not product_id:

return False

product = models.execute_kw(

ODOO_DB, uid, ODOO_PASS,

"product.product", "search_read",

\[\[\["id", "=", product_id\]\]\],

{"fields": \["pos_category_id", "x_is_topup"\], "limit": 1}

)

if not product:

return False

p = product\[0\]

\# Primaire check: POS-categorie

categ = p.get("pos_category_id")

if categ and categ\[1\] == TOPUP_CATEGORY_NAME:

return True

\# Fallback: custom vlag

if p.get("x_is_topup"):

return True

return False

def get_badge_payment_info(models, uid, payment_ids: list) -> bool:

"""

Controleert of de bestelling (deels) met Badge Wallet betaald werd.

Kijkt via pos.payment -> payment_method_id.name.

Extern blijft de payment_method altijd 'on_site' in de XML.

Geeft True terug als de betaalmethode overeenkomt met

BADGE_PAYMENT_METHOD_NAME.

"""

if not payment_ids:

return False

payments = models.execute_kw(

ODOO_DB, uid, ODOO_PASS,

"pos.payment", "search_read",

\[\[\["id", "in", payment_ids\]\]\],

{"fields": \["payment_method_id"\]}

)

for p in payments:

method_name = p.get("payment_method_id", \[None, ""\])\[1\]

if method_name == BADGE_PAYMENT_METHOD_NAME:

return True

return False

def deduct_wallet_balance(models, uid, partner_id: int, amount: float) -> float:

"""

Trekt het bedrag af van x_wallet_balance op res.partner.

Saldo kan nooit onder nul dalen.

Geeft het nieuwe saldo terug.

"""

partner = models.execute_kw(

ODOO_DB, uid, ODOO_PASS,

"res.partner", "search_read",

\[\[\["id", "=", partner_id\]\]\],

{"fields": \["x_wallet_balance"\], "limit": 1}

)

old_balance = partner\[0\].get("x_wallet_balance", 0.0) if partner else 0.0

new_balance = max(0.0, old_balance - amount)

models.execute_kw(

ODOO_DB, uid, ODOO_PASS,

"res.partner", "write",

\[\[partner_id\], {"x_wallet_balance": new_balance}\]

)

return new_balance

def process_order(models, uid, order: dict) -> None:

order_id = order\["id"\]

partner = order.get("partner_id") # False bij anonieme aankoop

is_anon = not bool(partner)

\# date_order formaat: '2026-04-15 09:05:00' — eerste 10 tekens = YYYY-MM-DD

due_date = order\["date_order"\]\[:10\]

\# ── Orderregels ophalen inclusief tax_ids en product_id voor correcte BTW en Top-up detectie ──

lines = models.execute_kw(

ODOO_DB, uid, ODOO_PASS,

"pos.order.line", "search_read",

\[\[\["order_id", "=", order_id\]\]\],

{"fields": \["product_id", "qty", "price_unit", "tax_ids"\]}

)

items = \[\]

for l in lines:

vat_rate = get_tax_rate(models, uid, l.get("tax_ids", \[\]))

product_id = l\["product_id"\]\[0\] if l.get("product_id") else None

topup = is_topup_product(models, uid, product_id)

item = {

"id": str(l\["product_id"\]\[0\]),

"description": l\["product_id"\]\[1\],

"quantity": int(l\["qty"\]),

"unit_price": l\["price_unit"\],

"total_amount": round(l\["qty"\] * l\["price_unit"\], 2),  \# quantity × unit_price

"vat_rate": 0 if topup else vat_rate,  \# forceer 0 voor Top-up ongeacht BTW-instelling

"currency": "eur",

}

\# Top-up producten worden herkend via categorie/x_is_topup — niet via BTW

if topup:

item\["item_type"\] = "wallet_topup"

items.append(item)

\# ── Betaalmethode detecteren ──────────────────────────────────────────

is_badge = get_badge_payment_info(

models, uid, order.get("payment_ids", \[\])

)

\# ── consumption_order samenstellen ───────────────────────────────────

if is_anon:

xml_co = build_consumption_order_xml(items=items, is_anonymous=True)

else:

pd = models.execute_kw(

ODOO_DB, uid, ODOO_PASS,

"res.partner", "search_read",

\[\[\["id", "=", partner\[0\]\]\]\],

{"fields": \["id", "x_user_id", "email", "is_company",

"parent_id", "street", "city", "zip"\]}

)\[0\]

\# company_id ophalen via standaard Odoo parent_id relatie.

\# parent_id\[0\] = Odoo ID, parent_id\[1\] = naam.

\# We gebruiken de x_user_id van de parent als company_id in de XML.

company_id = None

if pd.get("parent_id"):

parent_rec = models.execute_kw(

ODOO_DB, uid, ODOO_PASS,

"res.partner", "search_read",

\[\[\["id", "=", pd\["parent_id"\]\[0\]\]\]\],

{"fields": \["x_user_id"\], "limit": 1}

)

if parent_rec:

company_id = parent_rec\[0\].get("x_user_id")

is_company_linked = bool(pd.get("parent_id") or pd.get("is_company"))

xml_co = build_consumption_order_xml(

items=items,

customer_id=pd\["id"\],

user_id=pd.get("x_user_id", ""),

is_company_linked=is_company_linked,

company_id=company_id,

email=pd.get("email", ""),

is_anonymous=False,

)

send_typed_message("consumption_order", xml_co)

\# ── payment_registered (context: consumption) ─────────────────────────

xml_pr = build_payment_registered_xml(

payment_context="consumption",

invoice_status="paid",

amount_paid=order\["amount_total"\],

due_date=due_date,

trx_id=f"TRX-{order_id}",

payment_method="on_site", # extern altijd on_site

)

send_typed_message("payment_registered_consumption", xml_pr)

\# ── Wallet-aftrek en saldo-update bij Badge Wallet betaling ───────────

\# Sad path guard: Badge Wallet betaling voor een anonieme order is een

\# inconsistente toestand: zonder partner_id kan het saldo niet afgetrokken worden.

\# Odoo POS verhindert dit fysiek (Badge Wallet vereist klantprofiel),

\# maar we rapporteren de toestand expliciet als dit toch optreedt.

if is_badge and is_anon:

\# Inconsistente toestand: Badge Wallet betaling zonder gekoppeld klantprofiel

send_error_to_queue(

"odoo_api_error", str(order_id),

f"Badge Wallet betaling op anonieme order {order_id} — saldo niet afgetrokken"

)

if is_badge and not is_anon:

new_balance = deduct_wallet_balance(

models, uid, partner\[0\], order\["amount_total"\]

)

xml_wb = build_wallet_balance_update_xml(

user_id=pd.get("x_user_id", ""),

balance=new_balance,

)

send_typed_message("wallet_balance_update", xml_wb)

print(f"\[POLLER\] Badge wallet aftrek: EUR {order\['amount_total'\]:.2f},"

f" nieuw saldo: EUR {new_balance:.2f}")

\# ── Opmerking: payment_status naar Drupal ─────────────────────────────

\# payment_status wordt ENKEL verstuurd bij payment_context=registration

\# (inschrijvingsgeld betaald aan kassa — Flow 14).

\# De poller verwerkt uitsluitend consumption orders.

\# Registratiebetalingen zijn een apart manueel getriggerd flow.

mark_order_sent(models, uid, order_id)

print(f"\[POLLER\] Order {order\['name'\]} verstuurd naar RabbitMQ")

def poll_loop():

while True:

try:

uid, models = get_odoo_connection()

flush_buffer() # hersend gebufferde berichten bij reconnect

while True:

for order in get_unprocessed_orders(models, uid):

process_order(models, uid, order)

time.sleep(POLL_INTERVAL)

except Exception as e:

print(f"\[POLLER\] Fout: {e} — retry in {POLL_INTERVAL}s")

time.sleep(POLL_INTERVAL)

poller_thread = threading.Thread(target=poll_loop, daemon=True)

poller_thread.start()

## **4.5 Klantidentificatie & lokale cache**

Odoo werkt intern met twee klant-identifiers met fundamenteel verschillende scope.

| |     | |     |
| --- | --- | --- | --- |
| **Identifier** | **Formaat** | **Scope** | **Beheerd door** |
| &lt;user_id&gt; | UUID v4 (string) | Extern — uniek over ALLE systemen (CRM, Drupal, Kassa) | Salesforce CRM — aangemaakt bij registratie |
| &lt;customer&gt;&lt;id&gt; | Integer (Odoo intern) | Intern — Odoo res.partner record ID. Niet geldig buiten Odoo. | Odoo POS — automatisch aangemaakt bij eerste new_registration |

def get_or_create_partner(models, uid, db, password, user_id, reg_data):

"""Zoekt klant op via x_user_id (externe UUID). Maakt aan als nieuw."""

result = models.execute_kw(

db, uid, password, 'res.partner', 'search_read',

\[\[\['x_user_id', '=', user_id\]\]\],

{'fields': \['id', 'name', 'x_user_id'\], 'limit': 1}

)

if result:

print(f"\[CACHE\] Klant gevonden: {result\[0\]\['name'\]} (Odoo ID={result\[0\]\['id'\]})")

return result\[0\]\['id'\]

\# Niet gevonden: aanmaken

odoo_id = models.execute_kw(

db, uid, password, 'res.partner', 'create',

\[{'name': reg_data.get('name', 'Onbekend'),

'email': reg_data.get('email', ''),

'x_user_id': user_id,

'is_company': reg_data.get('type') == 'company'}\]

)

print(f"\[CACHE\] Klant aangemaakt: Odoo ID={odoo_id}")

return odoo_id

def get_partner_for_badge(models, uid, db, password, badge_id):

"""

Lookup bij badge_scanned via lokale Odoo-cache (x_badge_id).

Geen live CRM-call — werkt ook bij CRM-uitval (Vraag 17).

Returns: partner dict of None (badge niet gevonden).

"""

result = models.execute_kw(

db, uid, password, 'res.partner', 'search_read',

\[\[\['x_badge_id', '=', badge_id\]\]\],

{'fields': \['id', 'name', 'x_user_id',

'x_wallet_balance', 'x_date_of_birth', 'is_company'\],

'limit': 1}

)

if result:

partner = result\[0\]

print(f"\[CACHE\] Badge {badge_id} -> {partner\['name'\]}",

f"(saldo: EUR {partner.get('x_wallet_balance', 0):.2f})")

return partner

print(f"\[CACHE\] Badge {badge_id} niet herkend in lokale Odoo-cache")

return None # -> kassa toont foutmelding, medewerker beslist anoniem/wachten

## **4.6 Demo Productcatalogus & Beheer**

Voor de demo kiest het team 5 fictieve standaardproducten. De klant beheert de catalogus achteraf zelf in Odoo via Point of Sale > Producten. Geen synchronisatie met de Frontend nodig.

| |     | |     |
| --- | --- | --- | --- |
| **Product** | **Prijs** | **BTW** | **Type** |
| Koffie | EUR 2.50 | 6%  | Normaal product |
| Cola | EUR 2.00 | 6%  | Normaal product |
| Pintje | EUR 3.00 | 6%  | Normaal product |
| Broodje | EUR 4.50 | 6%  | Normaal product |
| Top-up 10 EUR | EUR 10.00 | 0%  | Service product (item_type=wallet_topup) |
| Top-up 20 EUR | EUR 20.00 | 0%  | Service product (item_type=wallet_topup) |

Top-up producten hebben BTW=0% in Odoo. De poller identificeert ze via `is_topup_product()`: primaire check op POS-categorie 'Top-ups', fallback op `x_is_topup=True`. Voor geïdentificeerde Top-up producten forceert `poller.py` `vat_rate=0` in de XML-export en zet automatisch `item_type='wallet_topup'`. De categorie 'Top-ups' moet éénmalig aangemaakt worden in Odoo via Point of Sale > Configuratie > Productcategorieën en gekoppeld worden aan de Top-up producten.

## **5\. Docker — hoe draait jullie systeem?**

## **5.1 Docker Compose voor Team Kassa**

De docker-compose.yml definieert drie containers: odoo, db en kassa-integratie. Let op het verplichte outbox-data volume: zonder dit volume verdwijnt outbox.json bij een container-herstart en gaan gebufferde berichten verloren.

\# docker-compose.yml — Team Kassa

version: "3.8"

services:

odoo:

image: odoo:17.0

container_name: kassa-odoo

ports:

\- "8069:8069"

environment:

\- HOST=db

\- USER=odoo

\- PASSWORD=odoo_ww

volumes:

\- odoo-data:/var/lib/odoo

\- ./odoo-config:/etc/odoo

depends_on:

\- db

restart: unless-stopped

db:

image: postgres:15

container_name: kassa-db

environment:

\- POSTGRES_USER=odoo

\- POSTGRES_PASSWORD=odoo_ww

\- POSTGRES_DB=odoo_kassa

volumes:

\- db-data:/var/lib/postgresql/data

restart: unless-stopped

kassa-integratie:

build: ./integratie

container_name: kassa-integratie

environment:

\- ODOO_URL=<http://odoo:8069>

\- ODOO_DB=odoo_kassa

\- ODOO_USER=<admin@school.be>

\- ODOO_PASS=${ODOO_PASS}

\- RABBIT_HOST=${RABBIT_HOST}

\- RABBIT_USER=${RABBIT_USER}

\- RABBIT_PASS=${RABBIT_PASS}

\- RABBIT_EXCHANGE=kassa.exchange

\- POLL_INTERVAL=3

volumes:

\# VERPLICHT: outbox.json buiten de container zodat

\# gebufferde berichten een container-herstart overleven.

\- outbox-data:/app/outbox

depends_on:

\- odoo

restart: unless-stopped

volumes:

odoo-data:

db-data:

outbox-data: # Named volume voor outbox.json (buffer Vraag 11 & 17)

## **5.2 Nuttige Docker commando's**

| |     |
| --- | --- |
| **Commando** | **Wat doet het?** |
| docker-compose up -d | Start alle containers op de achtergrond |
| docker-compose down | Stop en verwijder alle containers |
| docker-compose logs -f kassa-integratie | Bekijk live logs van de integratie-container |
| docker-compose logs -f odoo | Bekijk live logs van Odoo |
| docker-compose exec kassa-integratie bash | Open een shell in de integratie-container |

## **6\. Git structuur & CI/CD pipeline**

## **6.1 Git branches — verplicht in de opdracht**

| |     | |
| --- | --- | --- |
| **Branch** | **Waarvoor?** | **Wie mag pushen?** |
| main | Stabiele, goedgekeurde code — altijd werkend | Niemand direct — via merge |
| dev | Actieve ontwikkeling — werk hier dagelijks | Developers |
| prod | Productiecode — trigger voor automatische deploy | Teamlead via merge |
| feature/... | Nieuwe functies (bv. feature/heartbeat) | Developer |
| fix/... | Bugfixes (bv. fix/badge-scanner) | Developer |

## **6.2 CI/CD pipeline — GitHub Actions**

Zodra er wordt gepusht naar prod, wordt de pipeline uitgevoerd: tests draaien, daarna deploy naar de server.

\# .github/workflows/pipeline.yml

name: Kassa Integratie Pipeline

on:

push:

branches: \[dev, prod\]

jobs:

test:

runs-on: ubuntu-latest

steps:

\- uses: actions/checkout@v4

\- uses: actions/setup-python@v4

with:

python-version: '3.12'

\- run: pip install -r requirements.txt

\- run: pip install pytest

\- run: pytest tests/ -v

deploy:

needs: test

if: github.ref == 'refs/heads/prod'

runs-on: ubuntu-latest

steps:

\- uses: actions/checkout@v4

\- name: SSH sleutel laden

uses: webfactory/ssh-agent@v0.9.0

with:

ssh-private-key: ${{ secrets.SSH_PRIVATE_KEY }}

\- name: Server toevoegen aan known_hosts

run: ssh-keyscan -H ${{ secrets.DEPLOY_HOST }} >> ~/.ssh/known_hosts

\- name: Deploy naar server

run: |

ssh ${{ secrets.DEPLOY_USER }}@${{ secrets.DEPLOY_HOST }} 'cd /app/kassa && git pull && docker-compose up -d --build'

## **7\. Buffering & resilience samenvatting**

De kassa moet blijven werken ook als externe systemen tijdelijk uitvallen. Onderstaande tabel vat de strategie per situatie samen.

| |     | |
| --- | --- | --- |
| **Situatie** | **Gedrag** | **Bron** |
| CRM (Salesforce) down | Kassa werkt verder op lokale Odoo-cache. Berichten worden gebufferd in outbox.json en hersturd bij reconnect. | Vraag 17 |
| RabbitMQ verbinding weg | Berichten worden gebufferd. flush_buffer() hersturt alles bij volgende succesvolle connectie. | Vraag 11 |
| Odoo POS zelf uitvalt | Geen aankopen mogelijk — Odoo is het kassasysteem. | Vraag 11 |
| Meerdere kassa's actief | Eén gedeelde Odoo-instantie met meerdere POS-sessies. Geen synchronisatieproblemen. | Vraag 12 |

outbox.json staat op een Docker named volume (outbox-data). Zonder volume-mount gaan gebufferde berichten verloren bij een container-herstart. Controleer docker-compose.yml.

Team Kassa | Technische Gids v3.4 | Conform XML_naamgeving standaard | Integratieproject Desideriushogeschool | 2026
