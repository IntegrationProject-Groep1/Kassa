# Technisch Overzicht — Team Kassa (Odoo POS)

Tech Stack Documentatie | Versie 2.0 | Integratieproject Desideriushogeschool 2026

| |     |
| --- | --- |
| **Veld** | **Waarde** |
| **Project** | Integratieproject Desideriushogeschool 2026 |
| **Team** | Kassa (Odoo POS) |
| **Versie** | 2.0 — Definitief |
| **Datum** | 2026 |

Dit document beschrijft de vaste, vereiste tech stack voor Team Kassa binnen het integratieproject.

## **1\. Definitieve Tech Stack & Architectuur**

| |     | |
| --- | --- | --- |
| **Component** | **Technologie** | **Toelichting** |
| **Kassasysteem** | Odoo 17.0 | Geimplementeerd via de odoo:17.0 Docker image. |
| **Database** | PostgreSQL 15 | Absolute vereiste — Odoo heeft deze database nodig om te functioneren. Docker image: postgres:15. |
| **Integratietaal** | Python 3.12 | Specifiek de python:3.12-slim Docker image. Integratiecode staat in aparte Python scripts naast Odoo (sender.py, receiver.py, order_poller.py, partner_identity_poller.py). |
| **API Communicatie** | Odoo XML-RPC | Ingebouwde Odoo XML-RPC API via de standaard Python-bibliotheek xmlrpc.client. Gebruikt voor ophalen en wegschrijven van bestellingen en klantprofielen. |
| **Message Broker** | RabbitMQ + pika 1.3.2 | Centrale knooppunt voor alle communicatie tussen systemen. Python-bibliotheek pika versie 1.3.2. |
| **Dataformaat** | XML + XSD | Alle communicatie via RabbitMQ verloopt asynchroon in XML-formaat. Berichten moeten voldoen aan vaste XSD-schema's. |
| **Infrastructuur** | Docker + Docker Compose | Odoo, PostgreSQL en de Python-integratiescripts draaien in afzonderlijke, samenwerkende Docker containers. |
| **Versiebeheer** | Git + GitHub | Strikte branch-structuur: main, dev, prod, feature/..., fix/... |
| **CI/CD** | GitHub Actions | Geautomatiseerde pipeline: tests op push naar dev en prod; deploy naar server op push naar prod. |

## **2\. Python-bibliotheken**

Overzicht van alle Python-bibliotheken gebruikt in de integratiescripts:

| |     | |
| --- | --- | --- |
| **Bibliotheek** | **Versie** | **Gebruik** |
| pika | 1.3.2 | Connectie met RabbitMQ — versturen en ontvangen van berichten. |
| lxml | stdlib-vervanging | XSD-validatie van inkomende berichten via `etree.XMLSchema` in receiver.py. |
| defusedxml | — | Beveiligingspatch voor XML-RPC en ElementTree om XXE-aanvallen te voorkomen; gebruikt in receiver.py, order_poller.py en partner_identity_poller.py. |
| xmlrpc.client | stdlib | Odoo XML-RPC API aanspreken voor bestellingen, klantprofielen, betaalmethoden en BTW-tarieven. |
| xml.etree.ElementTree | stdlib | XML payloads bouwen in sender.py. |
| datetime / timezone | stdlib | UTC-tijdstempel genereren in YYYY-MM-DDTHH:MM:SSZ formaat via `_now_utc()`. |
| uuid | stdlib | Unieke message_id's (UUID v4) genereren. |
| threading | stdlib | Alle pollers en receiver starten als daemon-threads vanuit main.py. |
| time | stdlib | Polling interval beheren. |
| collections.deque / OrderedDict | stdlib | LRU idempotentie-cache in receiver.py (OrderedDict, max 10.000 entries). |
| json / pathlib | stdlib | Lezen en schrijven van de lokale outbox.json buffer. |
| os  | stdlib | Environment variables inladen voor credentials en configuratie. |
| re  | stdlib | E-mailvalidatie in partner_identity_poller.py; adres-parsing in order_poller.py. |

## **3\. Environment Variables**

Alle inloggegevens en configuratie worden via environment variables ingeladen. Nooit hardcoded in de code.

### Verplichte variabelen

| **Variabele** | **Beschrijving** |
| --- | --- |
| RABBIT_HOST | Hostname van de RabbitMQ-server |
| RABBIT_USER | RabbitMQ gebruikersnaam |
| RABBIT_PASS | RabbitMQ wachtwoord |
| ODOO_DB | Odoo database naam |
| ODOO_USER | Odoo gebruikersnaam (e-mail) |
| ODOO_PASS | Odoo wachtwoord |

### Optionele variabelen (met default waarde)

| **Variabele** | **Default** | **Beschrijving** |
| --- | --- | --- |
| ODOO_URL | `http://odoo:8069` | Odoo base URL |
| ODOO_MASTER_PASS | — | Odoo master wachtwoord voor database-beheer (aanmaken/verwijderen) |
| ODOO_LOAD_DEMO_DATA | `false` | Laad Odoo demo-data bij aanmaak van de database |
| RABBIT_PORT | `5672` | RabbitMQ poort |
| RABBIT_VHOST | `/` | RabbitMQ virtual host |
| RABBIT_EXCHANGE | `kassa.exchange` | Exchange naam |
| RABBIT_INCOMING_QUEUE | `kassa.incoming` | Naam van de inkomende queue |
| RABBIT_DLX | `kassa.exchange` | Dead Letter Exchange (zet op `kassa.dlx` op gedeelde Azure-server) |
| RABBIT_DLQ | `kassa.incoming.dlq` | Dead Letter Queue naam |
| RABBIT_DLX_ROUTING_KEY | `kassa.incoming.dlq` | Routing key voor de DLQ |
| POLL_INTERVAL | `5` | Order polling interval in seconden |
| IDENTITY_POLL_INTERVAL | `10` | Partner Identity Poller interval in seconden |
| IDENTITY_ERROR_RETRY_AFTER | `3600` | Cooldown in seconden voor partners in error-state bij de Identity Poller |
| SUBSCRIBE_USER_EVENTS | `false` | Inschrijven op `user.events` fanout exchange voor minimale gebruikers-notificaties |
| MONITOR_SUCCESS_LOGS | `true` | Toggle voor success-level logs naar monitoring queue (uitschakelen bij hoge traffic) |
| OUTBOX_DIR | `outbox` | Pad naar de directory voor outbox.json buffering |
| BADGE_PAYMENT_METHOD_NAME | `Badge Wallet` | Exacte naam van de Badge Wallet betaalmethode in Odoo POS |
| IDENTITY_ROUTING_KEY_CREATE | `identity.user.create.request` | Identity Service routing key voor aanmaken gebruiker |
| IDENTITY_ROUTING_KEY_LOOKUP_EMAIL | `identity.user.lookup.email.request` | Identity Service routing key voor opzoeken op e-mail |
| IDENTITY_ROUTING_KEY_LOOKUP_UUID | `identity.user.lookup.uuid.request` | Identity Service routing key voor opzoeken op UUID |

### PostgreSQL variabelen (voor de Odoo container)

| **Variabele** | **Beschrijving** |
| --- | --- |
| POSTGRES_USER | PostgreSQL gebruikersnaam |
| POSTGRES_PASSWORD | PostgreSQL wachtwoord |
| POSTGRES_DB | PostgreSQL database naam (typisch `postgres`) |

## **4\. Architectuurrestricties**

De volgende architectuurkeuzes zijn bewust gemaakt en mogen niet gewijzigd worden zonder overleg met het team:

| **Restrictie** | **Reden** |
| --- | --- |
| Polling via order_poller.py | POS event trigger via XML-RPC polling op pos.order. Geen webhooks of Odoo-modules. |
| Buffer in outbox.json | Docker named volume `outbox-data`. PostgreSQL-buffer bewust niet gekozen. Pad instelbaar via `OUTBOX_DIR`. |
| Heartbeats via sidecar | Heartbeats worden niet meer door de kassa-applicatie verstuurd, maar afgehandeld door een sidecar container van het monitoring team. `heartbeat.py` is niet meer aanwezig. |
| Gesplitste betalingen: out of scope | Zie Vraag 27. Ofwel volledig badge, ofwel volledig cash/kaart. |
| POLL_INTERVAL default = 5s | De code-default in main.py is 5 seconden; `.env.example` gebruikt 3 als voorbeeldwaarde. |
| Geen lokale UUIDs als fallback | Alle identity_uuid's komen van de Identity Service. Nooit lokaal genereren. |

Team Kassa | Tech Stack v2.0 | Integratieproject Desideriushogeschool | 2026
