# Technisch Overzicht — Team Kassa (Odoo POS)

Tech Stack Documentatie | Versie 1.0 | Integratieproject Desideriushogeschool 2026

| |     |
| --- | --- |
| **Veld** | **Waarde** |
| **Project** | Integratieproject Desideriushogeschool 2026 |
| **Team** | Kassa (Odoo POS) |
| **Versie** | 1.0 — Definitief |
| **Datum** | 2026 |

Dit document beschrijft de vaste, vereiste tech stack voor Team Kassa binnen het integratieproject.

## **1\. Definitieve Tech Stack & Architectuur**

| |     | |
| --- | --- | --- |
| **Component** | **Technologie** | **Toelichting** |
| **Kassasysteem** | Odoo 17.0 | Geimplementeerd via de odoo:17.0 Docker image. |
| **Database** | PostgreSQL 15 | Absolute vereiste — Odoo heeft deze database nodig om te functioneren. Docker image: postgres:15. |
| **Integratietaal** | Python 3.12 | Specifiek de python:3.12-slim Docker image. Integratiecode staat in aparte Python scripts naast Odoo (sender.py, receiver.py, poller.py). |
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
| xmlrpc.client | stdlib | Odoo XML-RPC API aanspreken voor bestellingen, klantprofielen, betaalmethoden en BTW-tarieven. |
| xml.etree.ElementTree | stdlib | XML payloads bouwen in sender.py. |
| datetime / timezone | stdlib | UTC-tijdstempel genereren in YYYY-MM-DDTHH:MM:SSZ formaat via \_now_utc(). |
| uuid | stdlib | Unieke message_id's (UUID v4) genereren. |
| threading | stdlib | Poller op de achtergrond als daemon-thread. |
| time | stdlib | Polling interval beheren. |
| collections.deque / OrderedDict | stdlib | LRU idempotentie-cache in receiver.py (OrderedDict). |
| json / pathlib | stdlib | Lezen en schrijven van de lokale outbox.json buffer. |
| os  | stdlib | Environment variables inladen voor credentials en configuratie. |

## **3\. Environment Variables**

Alle inloggegevens en configuratie worden via environment variables ingeladen. Nooit hardcoded in de code.

| |     | |
| --- | --- | --- |
| **Variabele** | **Verplicht** | **Beschrijving** |
| RABBIT_HOST | Ja  | Hostname van de RabbitMQ-server |
| RABBIT_USER | Ja  | RabbitMQ gebruikersnaam |
| RABBIT_PASS | Ja  | RabbitMQ wachtwoord |
| RABBIT_EXCHANGE | Nee | Exchange naam (default: kassa.exchange) |
| ODOO_URL | Nee | Odoo base URL (default: <http://odoo:8069>) |
| ODOO_DB | Ja  | Odoo database naam |
| ODOO_USER | Ja  | Odoo gebruikersnaam (e-mail) |
| ODOO_PASS | Ja  | Odoo wachtwoord |
| POLL_INTERVAL | Nee | Polling interval in seconden (default: 3) |

## **4\. Architectuurrestricties**

De volgende architectuurkeuzes zijn bewust gemaakt en mogen niet gewijzigd worden zonder overleg met het team:

| |     |
| --- | --- |
| **Restrictie** | **Reden** |
| Polling via poller.py | POS event trigger via XML-RPC polling op pos.order. Geen webhooks of Odoo-modules. |
| Buffer in outbox.json | Docker named volume outbox-data. PostgreSQL-buffer bewust niet gekozen. |
| Heartbeats via sidecar | Heartbeats worden niet meer door de kassa-applicatie verstuurd, maar afgehandeld door een sidecar container van het monitoring team. heartbeat.py is niet meer aanwezig in de kassa-integratie. |
| Gesplitste betalingen: out of scope | Zie Vraag 27. Ofwel volledig badge, ofwel volledig cash/kaart. |

Team Kassa | Tech Stack v1.0 | Integratieproject Desideriushogeschool | 2026
