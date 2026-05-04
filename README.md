<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:0d1117,40:0f2744,70:1f3a5f,100:0d1117&height=230&text=POS%20Integration&desc=Odoo%20%E2%80%A2%20RabbitMQ%20%E2%80%A2%20Docker%20%E2%80%A2%20Python&fontColor=58A6FF&fontSize=54&fontAlignY=42&descAlignY=65&descSize=18&descColor=8b949e&animation=fadeIn" width="100%"/>

<br>

![Odoo](https://img.shields.io/badge/Odoo_POS-714B67?style=for-the-badge&logo=odoo&logoColor=white)
![Python](https://img.shields.io/badge/Python_3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)
![RabbitMQ](https://img.shields.io/badge/RabbitMQ-FF6600?style=for-the-badge&logo=rabbitmq&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL_15-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)

<br>

> **Official repository of Team POS (Kassa) — Integration Project Desideriushogeschool 2026**
>
> *A generic, reusable event-driven Point of Sale system built on Odoo POS, communicating asynchronously with Salesforce CRM, Drupal, Elastic, and IoT Badge Scanners via RabbitMQ.*

<br>

</div>

<br>

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:0d1117,100:1f3a5f&height=40&text=%E2%97%88%20TABLE%20OF%20CONTENTS&fontColor=58A6FF&fontSize=18&fontAlign=15&fontAlignY=62" width="100%"/>

<br>

&nbsp;&nbsp;🏗️ &nbsp;[System Architecture](#-system-architecture) &nbsp;·&nbsp;
📨 &nbsp;[Message Flows](#-message-flows--routing) &nbsp;·&nbsp;
📚 &nbsp;[Documentation](#-documentation--data-mapping) &nbsp;·&nbsp;
💻 &nbsp;[Local Setup](#-local-development--setup) &nbsp;·&nbsp;
📁 &nbsp;[Repository Structure](#-repository-structure) &nbsp;·&nbsp;
🔄 &nbsp;[CI/CD](#-cicd--deployment) &nbsp;·&nbsp;
👥 &nbsp;[Team](#-team)

<br>
<br>

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:0d1117,100:1f3a5f&height=40&text=%E2%97%88%20SYSTEM%20ARCHITECTURE&fontColor=58A6FF&fontSize=18&fontAlign=16&fontAlignY=62" width="100%"/>

<br>

```mermaid
flowchart LR
    subgraph Incoming
        CRM[Salesforce CRM]
        IoT[IoT Badge Scanners]
    end

    RMQ{RabbitMQ\nkassa.exchange}

    subgraph Team POS
        PY[Python POS Integration\nsender · receiver · poller]
        ODOO[(Odoo POS\n+ PostgreSQL)]
    end

    subgraph Outgoing
        CRM2[Salesforce CRM]
        DRUPAL[Drupal Frontend]
        ELASTIC[Elastic Monitoring]
    end

    CRM -- "new_registration\nprofile_update\ncancel_registration" --> RMQ
    IoT -- "badge_scanned" --> RMQ
    RMQ -- "kassa.incoming" --> PY
    PY <-->|XML-RPC| ODOO
    PY -- "consumption_order\npayment_registered\nbadge_assigned\ninvoice_request\nrefund_processed" --> RMQ
    RMQ -- "kassa.payments.*" --> CRM2
    RMQ -- "kassa.frontend.*" --> DRUPAL
    RMQ -- "kassa.errors" --> ELASTIC
```

The Python POS Integration container communicates with Odoo exclusively via the built-in **XML-RPC API**. All communication with external systems is asynchronous, through structured **XML messages over RabbitMQ**.

<br>

<details>
<summary><b>⚙️ Core Design Principles</b></summary>
<br>

| Principle | Description |
| :--- | :--- |
| 🔗 **Loosely Coupled** | Systems never talk directly — everything flows through `kassa.exchange` (topic exchange) |
| 📦 **Offline-first Buffering** | If RabbitMQ is down, messages queue in `outbox.json` (Docker volume `outbox-data`) and auto-retry via `flush_buffer()`. POS keeps selling. |
| 💾 **Local Odoo Cache** | When the CRM is unreachable, the POS operates on locally cached customer profiles. Syncs on reconnect. |
| 🚨 **Error Handling** | Invalid messages are caught as `system_error`, routed to `kassa.errors`, and rejected with `basic_nack(requeue=false)` → Dead Letter Queue. |
| 💓 **Heartbeats** | Managed by a dedicated monitoring sidecar container — not by the POS integration itself. |

</details>

<br>
<br>

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:0d1117,100:1f3a5f&height=40&text=%E2%97%88%20MESSAGE%20FLOWS%20%26%20ROUTING&fontColor=58A6FF&fontSize=18&fontAlign=17&fontAlignY=62" width="100%"/>

<br>

<details open>
<summary><b>📥 Incoming — <code>kassa.incoming</code></b></summary>
<br>

| Type | From | Action |
| :--- | :--- | :--- |
| `new_registration` | CRM | Create or update customer profile in Odoo |
| `profile_update` | CRM | Update customer profile in Odoo |
| `cancel_registration` | CRM | Deactivate customer profile in Odoo |
| `badge_scanned` | IoT | Look up badge, load customer profile in POS |

</details>

<br>

<details open>
<summary><b>📤 Outgoing — <code>kassa.exchange</code></b></summary>
<br>

| Type | Routing Key | Destination |
| :--- | :--- | :--- |
| `consumption_order` | `kassa.payments.consumption` | Salesforce CRM |
| `payment_registered` | `kassa.payments.consumption` / `kassa.payments.registration` | Salesforce CRM |
| `invoice_request` | `kassa.payments.invoice` | Salesforce CRM |
| `badge_assigned` | `kassa.payments.badge` | Salesforce CRM |
| `refund_processed` | `kassa.payments.refund` | Salesforce CRM |
| `payment_status` | `kassa.frontend.payment` | Drupal |
| `wallet_balance_update` | `kassa.frontend.wallet` | Drupal |
| `system_error` | `kassa.errors` | Elastic |

</details>

> 💡 The Controlroom team can passively monitor **all** POS messages via the wildcard binding `kassa.#`.

<br>
<br>

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:0d1117,100:1f3a5f&height=40&text=%E2%97%88%20DOCUMENTATION%20%26%20DATA%20MAPPING&fontColor=58A6FF&fontSize=18&fontAlign=20&fontAlignY=62" width="100%"/>

<br>

All architecture, data flows, and XML standards live in the `documentatie/` directory *(written in Dutch)*:

<br>

| 📄 File | 📝 Contents |
| :--- | :--- |
| [Technische_Gids_Kassa.md](documentatie/Technische_Gids_Kassa.md) | Full architecture, all scripts with code examples, Docker setup, CI/CD |
| [Tech_Stack_Kassa.md](documentatie/Tech_Stack_Kassa.md) | Technologies, Python libraries, environment variables, architecture constraints |
| [XML_Structuren_Kassa.md](documentatie/XML_Structuren_Kassa.md) | Exact XML examples and XSD schemas per flow |
| [Datamapping_Kassa.md](documentatie/Datamapping_Kassa.md) | Field mapping from Odoo to XML per message type, enum values |
| [User_Stories_Kassa.md](documentatie/User_Stories_Kassa.md) | MVP features, BDD scenarios, acceptance criteria, Definition of Done |
| [Vragen_Kassa.md](documentatie/Vragen_Kassa.md) | Decision log — all technical and functional choices explained |

<br>
<br>

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:0d1117,100:1f3a5f&height=40&text=%E2%97%88%20LOCAL%20DEVELOPMENT%20%26%20SETUP&fontColor=58A6FF&fontSize=18&fontAlign=18&fontAlignY=62" width="100%"/>

<br>

### Prerequisites

![Docker](https://img.shields.io/badge/Docker_%26_Compose-required-2496ED?style=flat-square&logo=docker&logoColor=white)
![Git](https://img.shields.io/badge/Git-required-F05032?style=flat-square&logo=git&logoColor=white)

### 🚀 Quickstart

**1. Configure Environment**
```bash
cp .env.example .env
# Fill in credentials in .env
```

**2. Start the full stack**
```bash
docker-compose up -d
```

**3. Validate the XML-RPC connection to Odoo**
```bash
docker-compose exec kassa-integratie python tools/ping_odoo.py
```
> ✅ *Expected:* `Authenticatie geslaagd! Scripts kunnen data veilig wegschrijven.`

<br>

### 🛠️ Useful Commands

| Command | What it does |
| :--- | :--- |
| `docker-compose up -d` | Start all containers in the background |
| `docker-compose down` | Stop and remove all containers |
| `docker-compose logs -f kassa-integratie` | Live logs from the integration container |
| `docker-compose logs -f odoo` | Live logs from Odoo |
| `docker-compose exec kassa-integratie bash` | Open a shell in the integration container |

### ▶️ Run Scripts

```bash
docker-compose exec kassa-integratie python integratie/tools/test_sender.py
```

<br>

> [!WARNING]
> **Known Pitfall — Odoo webassets 500 after restart**
>
> If Odoo POS throws a `500` error on `/web/assets/...` after a container restart, run:
> ```bash
> docker exec -i kassa_db psql -U odoo -d odoo_kassa -c "DELETE FROM ir_attachment WHERE url LIKE '/web/assets/%';"
> docker-compose restart kassa-web
> ```
> See §3.2.1 of the Technical Guide for a full explanation.

<br>
<br>

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:0d1117,100:1f3a5f&height=40&text=%E2%97%88%20REPOSITORY%20STRUCTURE&fontColor=58A6FF&fontSize=18&fontAlign=15&fontAlignY=62" width="100%"/>

<br>

```text
📦 Kassa-dev
 ┣ 📂 documentatie/          # Architecture, mapping, and flow documentation
 ┣ 📂 integratie/            # Python integration scripts
 ┃ ┣ 📂 schemas/             # XSD validation files
 ┃ ┣ 📂 tests/               # Pytest files
 ┃ ┣ 📂 tools/               # Ping and diagnostic scripts
 ┃ ┣ 📜 main.py              # Entrypoint — starts receiver + poller
 ┃ ┣ 📜 receiver.py          # Processes incoming RabbitMQ messages
 ┃ ┣ 📜 sender.py            # Builds and dispatches outgoing XML messages
 ┃ ┗ 📜 poller.py            # Polls Odoo for new POS orders, triggers flows
 ┣ 📂 outbox/                # Mounted as Docker volume — outbox.json buffer
 ┣ 📜 .env.example           # Example environment variables
 ┣ 📜 docker-compose.yml     # Odoo + PostgreSQL + POS integration stack
 ┗ 📜 README.md
```

<br>
<br>

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:0d1117,100:1f3a5f&height=40&text=%E2%97%88%20CI%2FCD%20%26%20DEPLOYMENT&fontColor=58A6FF&fontSize=18&fontAlign=13&fontAlignY=62" width="100%"/>

<br>

The GitHub Actions pipeline triggers automatically on push to `dev` or `prod`:

| Step | Trigger | Action |
| :--- | :--- | :--- |
| ✅ **Tests** | push → `dev` or `prod` | `pytest tests/ -v` |
| 🚀 **Deploy** | push → `prod` | SSH deploy via `docker-compose up -d --build` |

### 🌿 Branch Strategy

| Branch | Purpose |
| :--- | :--- |
| `main` | Stable, approved code |
| `prod` | Production — triggers deployment |
| `dev` | Active development |
| `feature/...` | New features |
| `fix/...` | Bug fixes |

<br>
<br>

<img src="https://capsule-render.vercel.app/api?type=rect&color=0:0d1117,100:1f3a5f&height=40&text=%E2%97%88%20TEAM&fontColor=58A6FF&fontSize=18&fontAlign=8&fontAlignY=62" width="100%"/>

<br>

<div align="center">

| 🏅 Role | 👤 Name |
| :---: | :---: |
| **Team Lead** | Jeremy Luyckfasseel |
| **Developer** | Ahmed Takadoumi |
| **Developer** | Zeno Van Neygen |

</div>

<br>
<br>

<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:0d1117,40:0f2744,70:1f3a5f,100:0d1117&height=120&section=footer&text=Team%20POS%20%E2%80%94%20Desideriushogeschool%202026&fontColor=8b949e&fontSize=14&fontAlignY=65" width="100%"/>

</div>
