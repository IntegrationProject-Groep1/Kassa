<div align="center">
  <img src="https://capsule-render.vercel.app/api?type=waving&color=gradient&customColorList=10,4B0082,100:00BFFF&height=250&section=header&text=Kassa%20Integration&fontSize=80&animation=fadeIn&fontColor=ffffff&fontAlignY=35&desc=THE%20RESILIENT%20PULSE%20OF%20EVENT%20RETAIL&descAlignY=65&descSize=20" />

  <!-- Tech Badges -->
  <img src="https://img.shields.io/badge/Python%203.12-3776AB?style=flat-square&logo=python&logoColor=white&labelColor=161b22" />
  <img src="https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white&labelColor=161b22" />
  <img src="https://img.shields.io/badge/RabbitMQ-FF6600?style=flat-square&logo=rabbitmq&logoColor=white&labelColor=161b22" />
  <img src="https://img.shields.io/badge/Odoo%2017-875A7B?style=flat-square&logo=odoo&logoColor=white&labelColor=161b22" />
  <img src="https://img.shields.io/badge/2025%20--%202026-161b22?style=flat-square&labelColor=161b22" />

  <br/>

  <!-- CI/CD & Project Stats -->
  [![CI Pipeline](https://github.com/IntegrationProject-Groep1/Kassa/actions/workflows/ci.yml/badge.svg)](https://github.com/IntegrationProject-Groep1/Kassa/actions/workflows/ci.yml)
  [![Security Scanning](https://github.com/IntegrationProject-Groep1/Kassa/actions/workflows/security.yml/badge.svg)](https://github.com/IntegrationProject-Groep1/Kassa/actions/workflows/security.yml)
  ![Views](https://komarev.com/ghpvc/?username=IntegrationProject-Groep1-Kassa&label=REPOSITORY%20VIEWS&color=00BFFF&style=flat-square)

  <br/>

  <!-- Skill Icons Grid -->
  <a href="https://skillicons.dev">
    <img src="https://skillicons.dev/icons?i=python,js,postgres,docker,rabbitmq,githubactions,linux" />
  </a>
</div>

---

## Overview

The **Kassa Integration** is the mission-critical communication bridge for Team POS at Desideriushogeschool 2026. It orchestrates high-integrity data flows between **Odoo 17** and external enterprise platforms including Salesforce CRM, Drupal, and IoT infrastructure.

Built on an event-driven architecture, it guarantees **100% message durability** through a sophisticated local buffering system, ensuring that retail operations never stop, even during network instability.

---

## 📊 Project Health

<p align="center">
  <img src="https://img.shields.io/github/last-commit/IntegrationProject-Groep1/Kassa?style=for-the-badge&logo=github&color=00BFFF&labelColor=161b22" />
  <img src="https://img.shields.io/github/repo-size/IntegrationProject-Groep1/Kassa?style=for-the-badge&logo=github&color=00BFFF&labelColor=161b22" />
  <img src="https://img.shields.io/github/languages/top/IntegrationProject-Groep1/Kassa?style=for-the-badge&logo=python&color=00BFFF&labelColor=161b22" />
</p>

---

## Core Capabilities & Resilience

### Offline-First Design
The integration service is built to handle RabbitMQ unavailability. Outgoing messages are automatically routed through the `sender.py` resilient publisher:
- **Persistent Buffering**: If the broker is unreachable, messages are stored in `outbox/outbox.json` (mounted as a Docker volume).
- **Ordered Replay**: The `flush_buffer()` mechanism ensures messages are re-delivered in the exact order they were created once connectivity is restored.

### Technical Highlights
- **IoT Badge Integration**: Uses Odoo 17's `bus` service to push real-time customer data to the POS UI upon physical badge scans.
- **Compliance Engine**: Automated logic for age-restricted products and validation of anonymous wallet transactions.
- **Idempotency**: A FIFO bounded cache (10,000 entries) in `receiver.py` prevents duplicate message processing.

---

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=rect&color=gradient&customColorList=10,4B0082,100:00BFFF&height=80&section=header&text=System%20Architecture&fontSize=40&fontColor=ffffff&fontAlignY=50" />
</p>

The service acts as a decoupled orchestrator, managing state between Odoo's synchronous XML-RPC API and the asynchronous RabbitMQ bus.

```mermaid
graph TD
    subgraph "External Ecosystem"
        CRM[Salesforce CRM]
        IoT[IoT Badge Scanners]
        Frontend[Drupal Frontend]
        Monitor[Elastic Monitoring]
    end

    subgraph "Kassa Integration Service"
        Receiver[Receiver Thread]
        Poller[Order Poller]
        Sender[Resilient Sender]
        Outbox[(Local Outbox)]
    end

    subgraph "Odoo 17 Environment"
        Odoo[Odoo POS]
        DB[(PostgreSQL)]
    end

    CRM -- "Profile Updates" --> RabbitMQ((RabbitMQ Exchange))
    IoT -- "Badge Events" --> RabbitMQ
    
    RabbitMQ -- "Incoming XML" --> Receiver
    Receiver -- "XML-RPC" --> Odoo
    
    Odoo -- "Orders" --> Poller
    Poller -- "Buffering" --> Sender
    Sender -. "Persistence" .-> Outbox
    Sender -- "Outgoing XML" --> RabbitMQ
    
    RabbitMQ -- "Order Status" --> CRM
    RabbitMQ -- "Wallet Updates" --> Frontend
    RabbitMQ -- "Errors" --> Monitor
    
    Odoo <--> DB
```

### 📋 Message Routing Matrix

| Message Type | Direction | Routing Key | Purpose |
| :--- | :--- | :--- | :--- |
| `new_registration` | **Incoming** | `kassa.incoming` | Sync new customer profiles from CRM. |
| `profile_update` | **Incoming** | `kassa.incoming` | Update existing customer details in Odoo. |
| `badge_scanned` | **Incoming** | `kassa.incoming` | Trigger real-time UI profile loading. |
| `cancel_registration`| **Incoming** | `kassa.incoming` | Deactivate customer profiles (soft delete). |
| `consumption_order` | **Outgoing** | `kassa.payments.consumption` | Sync transaction data with Salesforce. |
| `payment_registered` | **Outgoing** | `kassa.payments.*` | Confirm payments (Consumption/Registration). |
| `invoice_request` | **Outgoing** | `kassa.payments.invoice` | Request invoice generation in Salesforce. |
| `badge_assigned` | **Outgoing** | `kassa.payments.badge` | Link new badge to customer in Salesforce. |
| `refund_processed` | **Outgoing** | `kassa.payments.refund` | Sync refunds with Salesforce. |
| `payment_status` | **Outgoing** | `kassa.frontend.payment` | Update Drupal transaction status. |
| `wallet_balance_update`| **Outgoing** | `kassa.frontend.wallet` | Push wallet changes to Drupal. |
| `heartbeat` | **Outgoing** | `kassa.heartbeat` | System health pulse. |
| `system_error` | **Outgoing** | `kassa.errors` | Log failures to Elastic/Monitoring. |

---

## CI/CD & Quality Assurance

The project employs a robust multi-stage GitHub Actions pipeline:

### CI Pipeline (`ci.yml`)
Runs on every push/PR to `main`, `dev`, or `prod`:
- **Linting**: Flake8 enforcement (max-length 120).
- **Static Analysis**: MyPy type checking across the integration suite.
- **Testing**: Exhaustive Pytest suite covering receivers, senders, and order polling logic.

### Security Scanning (`security.yml`)
- **SAST**: Bandit scans for Python-specific security vulnerabilities.
- **Secrets**: TruffleHog scans the entire history for leaked credentials.
- **Containers**: Trivy vulnerability scanning of the filesystem and dependencies.

---

## 📚 Project Documentation

Detailed technical and functional documentation can be found in the `documentatie/` directory:

| Document | Description |
| :--- | :--- |
| [Technische Gids](documentatie/Technische_Gids_Kassa.md) | Full setup, architecture details, and script explanations. |
| [Datamapping](documentatie/Datamapping_Kassa.md) | Odoo-to-XML field mappings and enum definitions. |
| [XML Structuren](documentatie/XML_Structuren_Kassa.md) | Exhaustive examples of all message formats. |
| [User Stories](documentatie/User_Stories_Kassa.md) | BDD scenarios and acceptance criteria for all features. |
| [Decisions (Vragen)](documentatie/Vragen_Kassa.md) | Architectural decision log and technical Q&A. |

---

## Repository Structure

```text
📦 Kassa
 ┣ 📂 .github/workflows      # CI, Deploy, and Security pipelines
 ┣ 📂 addons/                # Custom Odoo 17 modules (badge scanning, UI logic)
 ┣ 📂 documentatie/          # Technical and functional documentation
 ┣ 📂 integratie/            # Python integration service
 ┃ ┣ 📂 schemas/             # XML XSD validation schemas (14 types)
 ┃ ┣ 📂 tests/               # Pytest integration/unit suites
 ┃ ┣ 📂 tools/               # Integration-specific diagnostic tools
 ┃ ┣ 📜 main.py              # Orchestration entrypoint
 ┃ ┣ 📜 receiver.py          # RabbitMQ consumer (idempotent)
 ┃ ┣ 📜 sender.py            # Resilient publisher (buffered)
 ┃ ┗ 📜 order_poller.py      # Odoo 17 order extraction
 ┣ 📂 outbox/                # Local buffer persistence (Docker volume)
 ┣ 📂 tools/                 # Root utility and diagnostic scripts
 ┣ 📜 docker-compose.yml     # Local dev orchestration stack
 ┣ 📜 Dockerfile             # Integration service container definition
 ┗ 📜 README.md
```

---

## Getting Started

### 1. Prerequisites
- **Docker & Docker Compose**
- **Python 3.12+** (optional, for local development)

### 2. Rapid Launch (Docker)
The integration service automatically bootstraps the Odoo database, installs required modules, and configures custom fields on startup.

```bash
cp .env.example .env
# Edit .env and set ODOO_MASTER_PASS and other credentials
docker-compose up -d
```

- **Odoo POS**: [http://localhost:8069](http://localhost:8069)

### 3. Local Python Setup (Development)
If you wish to run the integration scripts or tests outside of Docker:
```bash
python -m venv .venv
source .venv/bin/activate  # Or .venv\Scripts\activate on Windows
pip install -r integratie/requirements.txt
```

### 4. Diagnostics & Verification
```bash
# Verify XML-RPC connectivity to Odoo
docker-compose exec kassa-integratie python tools/ping_odoo.py

# Run full test suite
docker-compose exec kassa-integratie pytest integratie/tests/
```

---

<div align="center">

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=soft&color=gradient&customColorList=10,4B0082,100:00BFFF&height=120&section=header&text=Meet%20The%20Team&fontSize=40&fontColor=ffffff&fontAlignY=40&animation=twinkle" />
</p>

<br/>

<p align="center">
  <a href="https://github.com/Jeremy-Luyckfasseel">
    <img src="https://capsule-render.vercel.app/api?type=blur&text=Jeremy%20Luyckfasseel&color=4B0082&height=140&fontSize=40&fontColor=ffffff&desc=TEAM%20LEAD&descAlignY=70&descSize=15" />
  </a>
</p>
<p align="center">
  <a href="https://github.com/AhmedTakadoumi">
    <img src="https://capsule-render.vercel.app/api?type=blur&text=Ahmed%20Takadoumi&color=3776AB&height=120&fontSize=30&fontColor=ffffff&desc=CORE%20DEVELOPER&descAlignY=70&descSize=12" />
  </a>
  &nbsp;&nbsp;
  <a href="https://github.com/zenovn">
    <img src="https://capsule-render.vercel.app/api?type=blur&text=Zeno%20Van%20Neygen&color=00BFFF&height=120&fontSize=30&fontColor=ffffff&desc=CORE%20DEVELOPER&descAlignY=70&descSize=12" />
  </a>
</p>

<br/>

*"Turning complex business requirements into seamless technical solutions."*

<br/>

**Official Repository - Integration Project Desideriushogeschool 2026**

</div>
