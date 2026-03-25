**Stappenplan — Implementatie Heartbeat (1 seconde)**

_Versie 2.1 — Conform XML_naamgeving standaard | Geïntegreerd document_

|     |     |
| --- | --- |
| **Project:** | Integratieproject Desideriushogeschool 2026 |
| **Team:** | Kassa (Odoo POS) |
| **Onderwerp:** | Technische opzet van de systeem-heartbeat |

# **1\. Doel van de Heartbeat**

Elk systeem binnen het project heeft een Heartbeat van 1 seconde. Dit is een periodiek XML-bericht dat naar de centrale RabbitMQ-postbus wordt gestuurd om aan de Elastic Controlroom te laten weten dat het Odoo-kassasysteem online is en normaal functioneert. De heartbeat bevat een status-veld (online of degraded) zodat de Controlroom niet alleen detecteert of een systeem leeft, maar ook of het volledig operationeel is.

|     |     |
| --- | --- |
| **Queue** | **Frequentie** |
| **queue.heartbeats** | 1 bericht per seconde |
| **Richting** | XSD |
| **Odoo (Kassa) → Elastic Stack (Monitoring)** | schema_heartbeat.xsd |

# **2\. Infrastructuur en Omgeving**

Het heartbeat-script draait in de kassa-integratie container, niet binnen Odoo zelf. Alle inloggegevens worden via environment variables ingeladen — nooit hardcoded in de code.

**Vereiste environment variables:**

|     |
| --- |
| RABBIT_HOST — Hostname van de RabbitMQ-server |
| RABBIT_USER — RabbitMQ gebruikersnaam |
| RABBIT_PASS — RabbitMQ wachtwoord |
| ODOO_URL — Odoo base URL (default: http://odoo:8069) |

# **3\. Benodigde Python-bibliotheken**

- pika — Connectie met RabbitMQ.
- time — Pauze van 1 seconde tussen berichten.
- datetime, timezone — Huidige UTC-tijd voor het XML-bericht.
- uuid — Unieke message_id's voor de header.
- xml.etree.ElementTree — XML payload bouwen.
- threading — Script op de achtergrond laten draaien.
- xmlrpc.client — Odoo API pingen voor degraded state detectie (conditie A).
- collections.deque — Rolling error-window bijhouden (conditie C).

# **4\. De XML Payload**

De heartbeat gebruikt de standaard &lt;message&gt;/&lt;header&gt;/&lt;body&gt; envelop. Alle velden zijn verplicht.

|     |     |
| --- | --- |
| **Veld** | **Waarde** |
| **&lt;header&gt;&lt;message_id&gt;** | Dynamisch: uniek UUID v4 per bericht |
| **&lt;header&gt;&lt;type&gt;** | Statisch: heartbeat |
| **&lt;header&gt;&lt;source&gt;** | Statisch: kassa |
| **&lt;header&gt;&lt;timestamp&gt;** | Dynamisch: YYYY-MM-DDTHH:MM:SSZ (UTC, geen microseconden) |
| **&lt;header&gt;&lt;version&gt;** | Statisch: 2.0 |
| **&lt;body&gt;&lt;status&gt;** | Dynamisch: online of degraded (altijd lowercase) |

**Voorbeeld XML:**

|     |
| --- |
| &lt;?xml version="1.0" encoding="UTF-8"?&gt; |
| &lt;message&gt; |
| &lt;header&gt; |
| &lt;message_id&gt;a1b2c3d4-e5f6-7890-abcd-ef1234567890&lt;/message_id&gt; |
| &lt;type&gt;heartbeat&lt;/type&gt; |
| &lt;source&gt;kassa&lt;/source&gt; |
| &lt;timestamp&gt;2026-04-15T14:32:01Z&lt;/timestamp&gt; |
| &lt;version&gt;2.0&lt;/version&gt; |
| &lt;/header&gt; |
| &lt;body&gt; |
| &lt;status&gt;online&lt;/status&gt; |
| &lt;/body&gt; |
| &lt;/message&gt; |

Timestamp generatie: gebruik strftime('%Y-%m-%dT%H:%M:%S') + 'Z' om exact het YYYY-MM-DDTHH:MM:SSZ formaat te produceren. datetime.isoformat() produceert microseconden en +00:00, wat niet conform de standaard is.

# **5\. Degraded State Logica**

De heartbeat rapporteert degraded als één van de volgende drie condities geldt:

|     |     |     |     |
| --- | --- | --- | --- |
| **Cond.** | **Beschrijving** | **Hoe gedetecteerd** | **Automatisch herstel** |
| A   | Odoo XML-RPC API niet bereikbaar | common.version() gooit exception | Volgende cyclus dat Odoo antwoordt |
| B   | RabbitMQ connectiefout vorige cyclus | rabbitmq_last_ok flag = False | Volgende succesvolle pika.BlockingConnection() |
| C   | Meer dan 5 errors in 60 seconden | len(gefilterde error_timestamps) > 5 | Zodra teller onder drempel daalt |

Status offline wordt nooit actief verstuurd. Als alles down is, kan het bericht toch niet verzonden worden — een ontbrekende heartbeat is zelf het offline-signaal voor de Controlroom.

# **6\. Python Implementatie (heartbeat.py — v2.1)**

|     |
| --- |
| \# heartbeat.py — v2.1 |
| import pika, time, threading, uuid |
| from datetime import datetime, timezone |
| import xml.etree.ElementTree as ET |
| import xmlrpc.client, os |
| from collections import deque |
|     |
| RABBIT_HOST = os.environ\["RABBIT_HOST"\] |
| RABBIT_USER = os.environ\["RABBIT_USER"\] |
| RABBIT_PASS = os.environ\["RABBIT_PASS"\] |
| ODOO_URL = os.environ.get("ODOO_URL", "http://odoo:8069") |
|     |
| \# ── Degraded state configuratie ──────────────────────────────────── |
| ERROR_THRESHOLD = 5 # Meer dan 5 errors in WINDOW_SECONDS → degraded |
| WINDOW_SECONDS = 60 # Rolling tijdvenster (seconden) |
| error_timestamps: deque = deque() |
| rabbitmq_last_ok: bool = True |
|     |
| def record_error(): |
| now = time.time() |
| error_timestamps.append(now) |
| while error_timestamps and (now - error_timestamps\[0\]) > WINDOW_SECONDS: |
| error_timestamps.popleft() |
|     |
| def check_odoo_reachable() -> bool: |
| """Ping Odoo XML-RPC API. Returns False als niet bereikbaar.""" |
| try: |
| common = xmlrpc.client.ServerProxy( |
| f"{ODOO_URL}/xmlrpc/2/common", allow_none=True) |
| common.version() |
| return True |
| except Exception: |
| return False |
|     |
| def get_system_status() -> str: |
| """ |
| Bepaalt heartbeat status: 'online' of 'degraded'. |
| Degraded condities (één volstaat): |
| A. Odoo API niet bereikbaar |
| B. RabbitMQ connectiefout in vorige cyclus |
| C. Meer dan ERROR_THRESHOLD errors in WINDOW_SECONDS |
| Status 'offline' wordt nooit actief verstuurd. |
| """ |
| if not check_odoo_reachable(): |
| print("\[HEARTBEAT\] Odoo niet bereikbaar → degraded") |
| return "degraded" |
| if not rabbitmq_last_ok: |
| print("\[HEARTBEAT\] RabbitMQ last connect failed → degraded") |
| return "degraded" |
| recent_errors = len(\[t for t in error_timestamps |
| if (time.time() - t) <= WINDOW_SECONDS\]) |
| if recent_errors > ERROR_THRESHOLD: |
| print(f"\[HEARTBEAT\] {recent_errors} errors → degraded") |
| return "degraded" |
| return "online" |
|     |
| def build_heartbeat_xml(status: str) -> str: |
| """Bouwt heartbeat conform &lt;message&gt;/&lt;header&gt;/&lt;body&gt; envelop.""" |
| root = ET.Element("message") |
| header = ET.SubElement(root, "header") |
| ET.SubElement(header, "message_id").text = str(uuid.uuid4()) |
| ET.SubElement(header, "type").text = "heartbeat" |
| ET.SubElement(header, "source").text = "kassa" |
| ET.SubElement(header, "timestamp").text = ( |
| datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S') + 'Z' |
| )   |
| ET.SubElement(header, "version").text = "2.0" |
| body = ET.SubElement(root, "body") |
| ET.SubElement(body, "status").text = status # online \| degraded |
| return ET.tostring(root, encoding="utf-8", |
| xml_declaration=True).decode("utf-8") |
|     |
| def send_heartbeat(): |
| global rabbitmq_last_ok |
| while True: |
| try: |
| credentials = pika.PlainCredentials(RABBIT_USER, RABBIT_PASS) |
| params = pika.ConnectionParameters( |
| host=RABBIT_HOST, credentials=credentials) |
| conn = pika.BlockingConnection(params) |
| channel = conn.channel() |
| channel.queue_declare(queue="queue.heartbeats", durable=True) |
| rabbitmq_last_ok = True # Verbinding geslaagd — reset conditie B |
| while True: |
| status = get_system_status() # Elke seconde evalueren |
| xml = build_heartbeat_xml(status) |
| channel.basic_publish( |
| exchange="", |
| routing_key="queue.heartbeats", |
| body=xml.encode("utf-8"), |
| properties=pika.BasicProperties(delivery_mode=2) |
| )   |
| if status == "degraded": |
| print("\[HEARTBEAT\] Status=DEGRADED verstuurd") |
| time.sleep(1) |
| except Exception as e: |
| rabbitmq_last_ok = False # Conditie B flag |
| record_error() # Telt mee voor conditie C |
| \# NIET bufferen — heartbeats zijn realtime, geen buffer |
| print(f"\[HEARTBEAT\] Connectiefout: {e} — retry in 1s") |
| time.sleep(1) |
|     |
| \# Start heartbeat in achtergrond daemon-thread |
| hb_thread = threading.Thread(target=send_heartbeat, daemon=True) |
| hb_thread.start() |

# **7\. Sad Paths en Error Handling**

|     |     |
| --- | --- |
| **Situatie** | **Gedrag** |
| **RabbitMQ verbinding verloren** | rabbitmq_last_ok = False. Volgende heartbeat na herstel verstuurt status=degraded. Gemiste heartbeats worden NIET gebufferd. |
| **Odoo API niet bereikbaar** | check_odoo_reachable() = False → status=degraded. Automatisch herstel. |
| **Te veel errors (>5 in 60s)** | error_timestamps teller > ERROR_THRESHOLD → status=degraded. |

⚠ NIET BUFFEREN — uitsluitend voor heartbeats

Heartbeats dienen voor realtime monitoring. Mislukte heartbeats worden NOOIT opgeslagen

of later doorgestuurd. Een vertraagde heartbeat geeft de Controlroom verouderde data.

Dit geldt UITSLUITEND voor heartbeats. Gewone berichten (consumption_order,

payment_registered, ...) worden wél gebufferd conform Vraag 11 & 17.

# **8\. XSD Schema (schema_heartbeat.xsd)**

|     |
| --- |
| &lt;?xml version="1.0" encoding="UTF-8"?&gt; |
| &lt;xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"&gt; |
|     |
| &lt;xs:complexType name="HeaderType"&gt; |
| &lt;xs:sequence&gt; |
| &lt;xs:element name="message_id" type="xs:string"/&gt; |
| &lt;xs:element name="type" type="xs:string" fixed="heartbeat"/&gt; |
| &lt;xs:element name="source" type="xs:string"/&gt; |
| &lt;xs:element name="timestamp" type="xs:dateTime"/&gt; |
| &lt;xs:element name="version" type="xs:string"/&gt; |
| &lt;/xs:sequence&gt; |
| &lt;/xs:complexType&gt; |
|     |
| &lt;xs:element name="message"&gt; |
| &lt;xs:complexType&gt;&lt;xs:sequence&gt; |
| &lt;xs:element name="header" type="HeaderType"/&gt; |
| &lt;xs:element name="body"&gt; |
| &lt;xs:complexType&gt;&lt;xs:sequence&gt; |
| &lt;xs:element name="status"&gt; |
| &lt;xs:simpleType&gt;&lt;xs:restriction base="xs:string"&gt; |
| &lt;xs:enumeration value="online"/&gt; |
| &lt;xs:enumeration value="degraded"/&gt; |
| &lt;xs:enumeration value="offline"/&gt; &lt;!-- Per ontwerp nooit actief verstuurd door kassa — ontbrekende heartbeat IS het offline-signaal --&gt; |
| &lt;/xs:restriction&gt;&lt;/xs:simpleType&gt; |
| &lt;/xs:element&gt; |
| &lt;/xs:sequence&gt;&lt;/xs:complexType&gt; |
| &lt;/xs:element&gt; |
| &lt;/xs:sequence&gt;&lt;/xs:complexType&gt; |
| &lt;/xs:element&gt; |
|     |
| &lt;/xs:schema&gt; |

_Team Kassa | Heartbeat v2.1 | Conform XML_naamgeving standaard | Integratieproject Desideriushogeschool | 2026_