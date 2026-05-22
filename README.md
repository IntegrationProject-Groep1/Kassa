<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&amp;color=0:0d1117,40:0f2744,70:1f3a5f,100:0d1117&amp;height=230&amp;text=POS%20Integration&amp;desc=Odoo%20%E2%80%A2%20RabbitMQ%20%E2%80%A2%20Docker%20%E2%80%A2%20Python&amp;fontColor=58A6FF&amp;fontSize=54&amp;fontAlignY=42&amp;descAlignY=65&amp;descSize=18&amp;descColor=8b949e&amp;animation=fadeIn" width="100%"/>

<br>

![Odoo](https://img.shields.io/badge/Odoo_POS-714B67?style=for-the-badge&logo=odoo&logoColor=white)
![Python](https://img.shields.io/badge/Python_3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)
![RabbitMQ](https://img.shields.io/badge/RabbitMQ-FF6600?style=for-the-badge&logo=rabbitmq&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL_15-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)

<br>

> **Official repository of Team POS (Kassa) — Integration Project Desideriushogeschool 2026**
>
> *A generic, reusable event-driven Point of Sale system built on Odoo POS, communicating asynchronously with Salesforce CRM, Drupal Frontend, Planning, Identity Service, Elastic, and IoT Badge Scanners via RabbitMQ.*

<br>

</div>

<br>

<a id="table-of-contents"></a>
<img src="https://capsule-render.vercel.app/api?type=rect&amp;color=0:0d1117,100:1f3a5f&amp;height=40&amp;text=%E2%97%88%20TABLE%20OF%20CONTENTS&amp;fontColor=58A6FF&amp;fontSize=18&amp;fontAlign=15&amp;fontAlignY=62" width="100%"/>

<br>

- [System Architecture](#system-architecture)
- [Message Flows & Routing](#message-flows--routing)
- [Documentation & Data Mapping](#documentation--data-mapping)
- [Local Development & Setup](#local-development--setup)
- [Repository Structure](#repository-structure)
- [CI/CD & Deployment](#cicd--deployment)
- [Team](#team)

<br>
<br>

<a id="system-architecture"></a>
<img src="https://capsule-render.vercel.app/api?type=soft&amp;color=0:0d1117,100:1a3f6f&amp;height=50&amp;text=%E2%97%88%20SYSTEM%20ARCHITECTURE&amp;fontColor=58A6FF&amp;fontSize=18&amp;fontAlign=16&amp;fontAlignY=62" width="100%"/>

<br>

```mermaid
flowchart LR
    subgraph Sources["External Sources"]
        CRM[Salesforce CRM]
        FE[Drupal Frontend]
        IOT[IoT Badge Scanners]
        PLAN[Planning]
        ID[Identity Service]
    end

    RMQ{{"RabbitMQ\nkassa.exchange"}}

    subgraph POS["Team POS (Kassa)"]
        PY["Python Integration\nreceiver · order_poller\npartner_identity_poller\nsender"]
        ODOO[("Odoo 17 POS\n+ PostgreSQL 15")]
        ADDON["kassa_pos_custom\n(Odoo addon + OWL)"]
    end

    subgraph Sinks["External Sinks"]
        CRM2[Salesforce CRM]
        DRUPAL[Drupal Frontend]
        ELASTIC[Elastic Monitoring]
        PLAN2[Planning]
    end

    CRM -- "new_registration\nprofile_update\ncancel_registration\nwallet_lease_grant\nwallet_remote_topup" --> RMQ
    FE -- "user_registered\nuser_unregistered\nevent_ended\nsession_created/updated/deleted\nuser_sessions_response" --> RMQ
    IOT -- "badge_scanned" --> RMQ
    PLAN -- "session_view_response" --> RMQ
    RMQ -- "kassa.incoming" --> PY
    PY <-->|XML-RPC| ODOO
    ODOO --- ADDON
    PY -- "consumption_order\npayment_registered\nbadge_assigned\ninvoice_request\nrefund_processed\nwallet_lease_request/return" --> RMQ
    PY <-->|RPC| ID
    RMQ -- "kassa.payments.*" --> CRM2
    RMQ -- "kassa.frontend.*" --> DRUPAL
    RMQ -- "kassa.errors" --> ELASTIC
    RMQ -- "session_view_request\nuser_sessions_request" --> PLAN2
```

The Python integration service communicates with Odoo exclusively via the built-in **XML-RPC API**. All inter-system communication is asynchronous, via structured **XML messages over RabbitMQ** (`kassa.exchange`, topic exchange). The `kassa_pos_custom` Odoo addon extends the POS UI with OWL components for QR scanning, real-time partner updates via the Odoo bus, and payment guards.

<br>

<details open>
<summary><b>Core Design Principles</b></summary>
<br>

| Principle | Description |
| :--- | :--- |
| **Loosely Coupled** | Systems never talk directly — everything flows through `kassa.exchange` (topic exchange) |
| **Offline-first Buffering** | If RabbitMQ is down, messages queue in `outbox.json` (Docker volume `outbox-data`) and auto-retry via `flush_buffer()`. The POS continues selling. |
| **Local Odoo Cache** | When the CRM is unreachable, the POS operates on locally cached customer profiles. Syncs on reconnect. |
| **Error Handling** | Invalid messages are caught as `system_error`, routed to `kassa.errors`, and rejected with `basic_nack(requeue=false)` into the Dead Letter Queue. |
| **Heartbeats** | Managed by a dedicated monitoring sidecar container — not by the POS integration itself. |

</details>

<br>
<br>

<a id="message-flows--routing"></a>
<img src="https://capsule-render.vercel.app/api?type=rect&amp;color=0:1f3a5f,100:0d1117&amp;height=40&amp;text=%E2%97%88%20MESSAGE%20FLOWS%20%26amp%3B%20ROUTING&amp;fontColor=58A6FF&amp;fontSize=18&amp;fontAlign=17&amp;fontAlignY=62" width="100%"/>

<br>

<details open>
<summary><b>Incoming — <code>kassa.incoming</code> &amp; Frontend exchange</b></summary>
<br>

| Type | From | Action |
| :--- | :--- | :--- |
| `new_registration` | CRM | Create or update customer profile; set `customer_rank=1` for POS visibility |
| `profile_update` | CRM | Update customer profile fields in Odoo |
| `cancel_registration` | CRM | Deactivate customer profile (`active=False`) |
| `badge_scanned` | IoT / Frontend (QR) | Look up by `x_badge_id` or `identity_uuid`; start wallet lease |
| `wallet_lease_grant` | CRM | Reconcile `x_wallet_balance`; store `x_lease_id`; publish `wallet_balance_update` |
| `wallet_remote_topup` | CRM | Add balance to active lease; park in `x_pending_topup_balance` if grant pending |
| `event_ended` | Frontend | Return all active wallet leases to CRM via `wallet_lease_return` |
| `user_registered` | Frontend (dual-publish) | Add session to `x_session_title`; update `x_outstanding_amount` additively |
| `user_unregistered` | Frontend (dual-publish) | Remove session; subtract price from `x_outstanding_amount` |
| `user_sessions_response` | Frontend | Create/update POS session products per visitor |
| `session_created` | Frontend | Create new POS product for session |
| `session_updated` | Frontend | Update existing session POS product (name/price) |
| `session_deleted` | Frontend | Log and ack — product kept for ongoing transactions |
| `session_view_response` | Planning | Bulk-upsert full session catalogue into Odoo POS |
| `user_event` | user.events fanout | Informational only — no Odoo action |

</details>

<br>

<details open>
<summary><b>Outgoing — <code>kassa.exchange</code></b></summary>
<br>

| Type | Routing Key | Destination |
| :--- | :--- | :--- |
| `consumption_order` | `kassa.payments.consumption` | Salesforce CRM |
| `payment_registered` | `kassa.payments.consumption` / `kassa.payments.registration` | Salesforce CRM |
| `invoice_request` | `kassa.payments.invoice` | Salesforce CRM |
| `badge_assigned` | `kassa.payments.badge` | Salesforce CRM |
| `refund_processed` | `kassa.payments.refund` | Salesforce CRM |
| `wallet_lease_request` | `kassa.wallet.lease.request` | Salesforce CRM |
| `wallet_lease_return` | `kassa.wallet.lease.return` | Salesforce CRM |
| `payment_status` | `kassa.frontend.payment` | Drupal Frontend |
| `wallet_balance_update` | `kassa.frontend.wallet` | Drupal Frontend |
| `user_sessions_request` | `kassa.to.frontend.user_sessions_request` | Drupal Frontend |
| `session_view_request` | via `planning.exchange` | Planning |
| `system_error` | `kassa.errors` | Elastic |

</details>

> The Controlroom team can passively monitor **all** POS messages via the wildcard binding `kassa.#`.

<br>
<br>

<a id="documentation--data-mapping"></a>
<img src="https://capsule-render.vercel.app/api?type=soft&amp;color=0:0d1117,100:163652&amp;height=50&amp;text=%E2%97%88%20DOCUMENTATION%20%26amp%3B%20DATA%20MAPPING&amp;fontColor=58A6FF&amp;fontSize=18&amp;fontAlign=20&amp;fontAlignY=62" width="100%"/>

<br>

All architecture, data flows, and XML standards live in the `documentatie/` directory *(written in Dutch)*:

<br>

| File | Contents |
| :--- | :--- |
| [Technische_Gids_Kassa.md](documentatie/Technische_Gids_Kassa.md) | Full architecture, all modules explained, Docker setup, wallet lease lifecycle |
| [Tech_Stack_Kassa.md](documentatie/Tech_Stack_Kassa.md) | Technologies, Python libraries, environment variables, architecture constraints |
| [XML_XSD_Contract_v2.3_Centralized.md](documentatie/XML_XSD_Contract_v2.3_Centralized.md) | **Authoritative** XML/XSD contract — all message types, schemas, enums |
| [XML_Structuren_Kassa.md](documentatie/XML_Structuren_Kassa.md) | XML examples and XSD schema references per flow |
| [Datamapping_Kassa.md](documentatie/Datamapping_Kassa.md) | Field mapping from Odoo to XML per message type, enum values |
| [Identity_Integration.md](documentatie/Identity_Integration.md) | Identity Service RPC format, routing keys, PartnerIdentityPoller flow |
| [User_Stories_Kassa.md](documentatie/User_Stories_Kassa.md) | MVP features, BDD scenarios, acceptance criteria, Definition of Done |
| [Vragen_Kassa.md](documentatie/Vragen_Kassa.md) | Decision log — all technical and functional choices explained |

<br>
<br>

<a id="local-development--setup"></a>
<img src="https://capsule-render.vercel.app/api?type=rect&amp;color=0:0d1117,50:1f3a5f,100:0d1117&amp;height=40&amp;text=%E2%97%88%20LOCAL%20DEVELOPMENT%20%26amp%3B%20SETUP&amp;fontColor=58A6FF&amp;fontSize=18&amp;fontAlign=18&amp;fontAlignY=62" width="100%"/>

<br>

### Prerequisites

![Docker](https://img.shields.io/badge/Docker_%26_Compose-required-2496ED?style=flat-square&logo=docker&logoColor=white)
![Git](https://img.shields.io/badge/Git-required-F05032?style=flat-square&logo=git&logoColor=white)

### Quickstart

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
> *Expected:* `Authenticatie geslaagd! Scripts kunnen data veilig wegschrijven.`

<br>

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

<a id="repository-structure"></a>
<img src="https://capsule-render.vercel.app/api?type=soft&amp;color=0:0d1117,100:1a2f50&amp;height=50&amp;text=%E2%97%88%20REPOSITORY%20STRUCTURE&amp;fontColor=58A6FF&amp;fontSize=18&amp;fontAlign=15&amp;fontAlignY=62" width="100%"/>

<br>

```text
📦 Kassa/
 ┣ 📂 addons/
 ┃ ┗ 📂 kassa_pos_custom/    # Odoo addon — extends POS UI
 ┃   ┣ 📂 models/            # Custom fields (res.partner, product.template, pos.session)
 ┃   ┣ 📂 controllers/       # HTTP: /kassa/qr_scan endpoint + service-worker override
 ┃   ┣ 📂 static/src/js/     # OWL components: QR scanner, partner bus updates, payment guards
 ┃   ┗ 📂 views/             # XML templates for POS UI extensions
 ┣ 📂 documentatie/          # Architecture, mapping, and flow documentation (Dutch)
 ┣ 📂 integratie/            # Python integration service
 ┃ ┣ 📂 schemas/             # XSD validation files (one per message type)
 ┃ ┣ 📂 tests/               # Pytest test suite
 ┃ ┣ 📂 tools/               # Ping and diagnostic scripts
 ┃ ┣ 📄 main.py              # Entrypoint — starts 3 daemon threads + health file
 ┃ ┣ 📄 receiver.py          # Thread 1 — consumes kassa.incoming (14 message types)
 ┃ ┣ 📄 order_poller.py      # Thread 2 — polls Odoo POS orders; triggers outgoing flows
 ┃ ┣ 📄 partner_identity_poller.py  # Thread 3 — links unmatched partners to Identity Service
 ┃ ┣ 📄 sender.py            # Shared module — builds + validates + publishes XML; outbox buffer
 ┃ ┣ 📄 odoo_setup.py        # One-time bootstrap: DB creation, addon install, custom fields
 ┃ ┣ 📄 identity_client.py   # RPC client for the central Identity Service
 ┃ ┣ 📄 config_utils.py      # Environment variable parsing helpers
 ┃ ┣ 📄 monitoring.py        # Structured log publisher to the monitoring queue
 ┃ ┣ 📄 pos_profiles.py      # Idempotent POS config setup (Bar Kassa + Inschrijvingskassa)
 ┃ ┗ 📄 mcp_server.py        # FastMCP server — exposes Odoo POS data as tools for Claude Code
 ┣ 📂 outbox/                # Docker named volume — outbox.json offline message buffer
 ┣ 📄 .env.example           # Environment variable reference
 ┣ 📄 docker-compose.yml     # Odoo 17 + PostgreSQL 15 + integration service
 ┗ 📄 README.md
```

<br>
<br>

<a id="cicd--deployment"></a>
<img src="https://capsule-render.vercel.app/api?type=rect&amp;color=0:0d1117,100:2a1f5f&amp;height=40&amp;text=%E2%97%88%20CI%2FCD%20%26amp%3B%20DEPLOYMENT&amp;fontColor=58A6FF&amp;fontSize=18&amp;fontAlign=13&amp;fontAlignY=62" width="100%"/>

<br>

Three GitHub Actions workflows run automatically:

| Workflow | Trigger | Action |
| :--- | :--- | :--- |
| **ci.yml** | push to `main` or `dev` | flake8 lint → mypy type-check → pytest → Docker integration tests |
| **deploy.yml** | push to `main` | Build Docker image → push to GHCR |
| **security.yml** | push to `main` or `dev` | Bandit (SAST) → pip-audit → TruffleHog → Trivy image scan |

### Branch Strategy

| Branch | Purpose |
| :--- | :--- |
| `main` | Production — stable, approved code, triggers deployment |
| `dev` | Active development |
| `feature/...` | New features |
| `fix/...` | Bug fixes |

<br>
<br>

<a id="team"></a>
<img src="https://capsule-render.vercel.app/api?type=soft&amp;color=0:0d1117,100:1f3a5f&amp;height=50&amp;text=%E2%97%88%20TEAM&amp;fontColor=58A6FF&amp;fontSize=18&amp;fontAlign=8&amp;fontAlignY=62" width="100%"/>

<br>

<div align="center">
<table>
  <tr>
    <td align="center" width="240">
      <a href="https://github.com/Jeremy-Luyckfasseel">
        <img src="https://github.com/Jeremy-Luyckfasseel.png" width="110" height="110" style="border-radius:50%"/>
      </a>
      <br/><br/>
      <a href="https://github.com/Jeremy-Luyckfasseel"><b>Jeremy Luyckfasseel</b></a>
      <br/><br/>
      <img src="https://img.shields.io/badge/Team%20Lead-58A6FF?style=for-the-badge&amp;labelColor=0d1117"/>
    </td>
    <td width="40"></td>
    <td align="center" width="240">
      <a href="https://github.com/Ahmeedddddd">
        <img src="https://github.com/Ahmeedddddd.png" width="110" height="110" style="border-radius:50%"/>
      </a>
      <br/><br/>
      <a href="https://github.com/Ahmeedddddd"><b>Ahmed Takadoumi</b></a>
      <br/><br/>
      <img src="https://img.shields.io/badge/Developer-1f3a5f?style=for-the-badge&amp;labelColor=0d1117"/>
    </td>
    <td width="40"></td>
    <td align="center" width="240">
      <a href="https://github.com/zenoemvn">
        <img src="https://github.com/zenoemvn.png" width="110" height="110" style="border-radius:50%"/>
      </a>
      <br/><br/>
      <a href="https://github.com/zenoemvn"><b>Zeno Van Neygen</b></a>
      <br/><br/>
      <img src="https://img.shields.io/badge/Developer-1f3a5f?style=for-the-badge&amp;labelColor=0d1117"/>
    </td>
  </tr>
</table>
</div>

<br>
<br>

<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&amp;color=0:0d1117,40:0f2744,70:1f3a5f,100:0d1117&amp;height=120&amp;section=footer&amp;text=Team%20POS%20%E2%80%94%20Desideriushogeschool%202026&amp;fontColor=8b949e&amp;fontSize=14&amp;fontAlignY=65" width="100%"/>

</div>