# POS Integration — Odoo POS

> *Generic reusable event Point of Sale system built on Odoo POS.*

![Odoo](https://img.shields.io/badge/Odoo_Point_Of_Sale-714B67?style=for-the-badge&logo=odoo&logoColor=white)
![Python](https://img.shields.io/badge/Python_3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)
![RabbitMQ](https://img.shields.io/badge/RabbitMQ-FF6600?style=for-the-badge&logo=rabbitmq&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL_15-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)

> Official repository of Team POS (Kassa) for the Integration Project Desideriushogeschool 2026.
> This project manages the Point of Sale (POS) system and handles asynchronous communication with the CRM (Salesforce), Frontend (Drupal), Monitoring System (Elastic), and IoT Badge Scanners via RabbitMQ.

---

## 📋 Table of Contents

- [System Architecture](#system-architecture)
- [Message Flows & Routing](#message-flows--routing)
- [Documentation & Data Mapping](#documentation--data-mapping)
- [Local Development & Setup](#local-development--setup)
- [Repository Structure](#repository-structure)
- [CI/CD & Deployment](#cicd--deployment)
- [Team Roles](#team-roles)

---

## 🏗️ System Architecture

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

The Python POS Integration container communicates with Odoo exclusively via the built-in XML-RPC API. Asynchronous communication with external systems operates strictly through structured XML messages over RabbitMQ.

**Core Principles:**

- **Loosely Coupled:** Systems do not communicate directly with each other — everything flows through `kassa.exchange` (topic exchange).
- **Offline-first buffering:** If RabbitMQ is down, messages are stored locally in `outbox.json` (Docker named volume `outbox-data`) and automatically retried upon reconnection via `flush_buffer()`. The POS continues selling even without network connectivity.
- **Local Odoo Cache:** When the CRM is unreachable, the POS continues operating on locally cached customer profiles in Odoo. Incoming messages are processed once the connection is restored.
- **Error Handling:** Invalid messages are not retried but caught as `system_error` and routed to `kassa.errors`. The original message is then rejected with `basic_nack(requeue=false)` to safely land in the Dead Letter Queue (DLQ) for analysis.
- **Heartbeats:** Managed by a separate monitoring sidecar container — not by the POS integration itself.

---

## 📨 Message Flows & Routing

### Incoming (`kassa.incoming`)

| Type | From | Action |
| :--- | :--- | :--- |
| `new_registration` | CRM | Create or update customer profile in Odoo |
| `profile_update` | CRM | Update customer profile in Odoo |
| `cancel_registration` | CRM | Deactivate customer profile in Odoo |
| `badge_scanned` | IoT | Look up badge, load customer profile in POS |

### Outgoing (`kassa.exchange`)

| Type | Routing key | To |
| :--- | :--- | :--- |
| `consumption_order` | `kassa.payments.consumption` | Salesforce CRM |
| `payment_registered` | `kassa.payments.consumption` / `kassa.payments.registration` | Salesforce CRM |
| `invoice_request` | `kassa.payments.invoice` | Salesforce CRM |
| `badge_assigned` | `kassa.payments.badge` | Salesforce CRM |
| `refund_processed` | `kassa.payments.refund` | Salesforce CRM |
| `payment_status` | `kassa.frontend.payment` | Drupal |
| `wallet_balance_update` | `kassa.frontend.wallet` | Drupal |
| `system_error` | `kassa.errors` | Elastic |

> The Controlroom team can passively monitor all POS messages via the wildcard binding `kassa.#`.

---

## 📚 Documentation & Data Mapping

Our complete architecture, data flows, and XML standards are documented in the `documentatie/` directory:

| File | Contents |
| :--- | :--- |
| [Technische_Gids_Kassa.md](documentatie/Technische_Gids_Kassa.md) | Full architecture, all scripts with code examples, Docker setup, CI/CD |
| [Tech_Stack_Kassa.md](documentatie/Tech_Stack_Kassa.md) | Technologies, Python libraries, environment variables, architecture constraints |
| [XML_Structuren_Kassa.md](documentatie/XML_Structuren_Kassa.md) | Exact XML examples and XSD schemas per flow |
| [Datamapping_Kassa.md](documentatie/Datamapping_Kassa.md) | Field mapping from Odoo to XML per message type, enum values |
| [User_Stories_Kassa.md](documentatie/User_Stories_Kassa.md) | MVP features, BDD scenarios, acceptance criteria, Definition of Done |
| [Vragen_Kassa.md](documentatie/Vragen_Kassa.md) | Decision log — all technical and functional choices explained |

*(Note: The actual documentation files are currently written in Dutch).*

---

## 💻 Local Development & Setup

### Requirements

- Docker & Docker Compose
- Git

### Startup

1. **Configure Environment:** Copy `.env.example` to `.env` and fill in the credentials.

   ```bash
   cp .env.example .env
   ```

2. **Start Stack:**

   ```bash
   docker-compose up -d
   ```

3. **Connection Test:** Validate the XML-RPC connection to Odoo:

   ```bash
   docker-compose exec kassa-integratie python tools/ping_odoo.py
   ```

   *Expected output:* `✅ Authenticatie geslaagd! Scripts kunnen data veilig wegschrijven.` *(Authentication successful! Scripts can safely write data.)*

### Useful Commands

| Command | What it does |
| :--- | :--- |
| `docker-compose up -d` | Start all containers in the background |
| `docker-compose down` | Stop and remove all containers |
| `docker-compose logs -f kassa-integratie` | Live logs from the integration container |
| `docker-compose logs -f odoo` | Live logs from Odoo |
| `docker-compose exec kassa-integratie bash` | Open a shell in the integration container |

### Run Scripts

```bash
docker-compose exec kassa-integratie python integratie/tools/test_sender.py
```

### ⚠️ Known Pitfall — Odoo webassets 500 after restart

If Odoo POS throws a 500 error on `/web/assets/...` after a container restart, run:

```bash
docker exec -i kassa_db psql -U odoo -d odoo_kassa -c "DELETE FROM ir_attachment WHERE url LIKE '/web/assets/%';"
docker-compose restart kassa-web
```

See §3.2.1 of the Technical Guide for a comprehensive explanation.

---

## 📁 Repository Structure

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

---

## 🔄 CI/CD & Deployment

The GitHub Actions pipeline is triggered automatically upon a push to `dev` or `prod`:

| Step | Trigger | Action |
| :--- | :--- | :--- |
| **Tests** | push to `dev` or `prod` | `pytest tests/ -v` |
| **Deploy** | push to `prod` | SSH deploy to server via `docker-compose up -d --build` |

### Branch Strategy

| Branch | Purpose |
| :--- | :--- |
| `main` | Stable, approved code |
| `prod` | Production code — triggers deployment |
| `dev` | Active development |
| `feature/...` | New features |
| `fix/...` | Bug fixes |

---

## 👥 Team

| Role | Name |
| :--- | :--- |
| **Team Lead** | [name] |
| **Developer** | [name] |
| **Developer** | [name] |
