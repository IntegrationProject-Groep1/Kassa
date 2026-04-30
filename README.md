<div align="center">

<!-- Typing SVG Header - TEAM FOCUSED -->
<img src="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=600&size=28&pause=1000&color=58A6FF&center=true&vCenter=true&width=600&lines=Team+POS+%7C+Kassa+Integration;Resilient+Event-Driven+Architecture;Odoo+%2B+RabbitMQ+%2B+Salesforce" alt="Kassa Integration" />

<br/>

<!-- Status & Tech Badges -->
[![Version](https://img.shields.io/badge/Version-1.0.0-3b82f6?style=flat-square&labelColor=161b22)](https://github.com/IntegrationProject-Groep1/Kassa)
[![Build Status](https://img.shields.io/badge/Build-Passing-22c55e?style=flat-square&labelColor=161b22)](https://github.com/IntegrationProject-Groep1/Kassa/actions)
[![License](https://img.shields.io/badge/License-LGPL--3-orange?style=flat-square&labelColor=161b22)](https://github.com/IntegrationProject-Groep1/Kassa/blob/dev/addons/kassa_pos_custom/__manifest__.py)
[![Odoo](https://img.shields.io/badge/Platform-Odoo%2016%2F17-875A7B?style=flat-square&logo=odoo&logoColor=white&labelColor=161b22)](https://www.odoo.com)
[![RabbitMQ](https://img.shields.io/badge/Messaging-RabbitMQ-FF6600?style=flat-square&logo=rabbitmq&logoColor=white&labelColor=161b22)](https://www.rabbitmq.com)

<br/>

<!-- Skill Icons Grid - PROJECT RELEVANT -->
<a href="https://skillicons.dev">
  <img src="https://skillicons.dev/icons?i=python,js,postgres,docker,rabbitmq,githubactions,linux" />
</a>

</div>

---

## Overview

The **Kassa Integration** is the core communication layer for Team POS at Desideriushogeschool 2026. It manages the flow of data between the **Odoo Point of Sale** and external enterprise systems (Salesforce, Drupal, IoT) using a resilient, event-driven architecture.

---

## Core Capabilities

- **Resilience**: Local `outbox.json` buffering ensures 100% message delivery during network outages.
- **Smart Identity**: IoT Badge scanning via Odoo `bus` for instantaneous customer identification in the POS UI.
- **Compliance**: Automated logic for age-restricted products and anonymous transaction blocking.
- **Sync Engine**: High-frequency polling and real-time consumption order dispatching via RabbitMQ.

---

## System Architecture

The integration service acts as a decoupled orchestrator between Odoo's synchronous API and the ecosystem's asynchronous messaging.

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

    subgraph "Odoo Environment"
        Odoo[Odoo POS]
        DB[(PostgreSQL)]
    end

    CRM -- "Profile Updates" --> RabbitMQ((RabbitMQ Exchange))
    IoT -- "Badge Events" --> RabbitMQ
    
    RabbitMQ -- "Incoming XML" --> Receiver
    Receiver -- "XML-RPC" --> Odoo
    
    Odoo -- "Orders" --> Poller
    Poller -- "Buffering" --> Sender
    Sender -. "Offline Persistence" .-> Outbox
    Sender -- "Outgoing XML" --> RabbitMQ
    
    RabbitMQ -- "Order Status" --> CRM
    RabbitMQ -- "Wallet Updates" --> Frontend
    RabbitMQ -- "Errors" --> Monitor
    
    Odoo <--> DB
```

### Message Routing Details

| Message Type | Direction | Routing Key | Purpose |
| :--- | :---: | :--- | :--- |
| `new_registration` | 📥 | `kassa.incoming` | Sync new customers from CRM to Odoo. |
| `badge_scanned` | 📥 | `kassa.incoming` | Trigger UI profile load via Odoo bus. |
| `consumption_order`| 📤 | `kassa.payments.consumption` | Finalize transaction billing in Salesforce. |
| `system_error` | 📤 | `kassa.errors` | Real-time observability in Elastic. |

---

## Repository Structure

```text
📦 Kassa
 ┣ 📂 addons/                # Custom Odoo modules (badge scanning, age restrictions)
 ┣ 📂 integratie/            # Python integration service
 ┃ ┣ 📂 schemas/             # XML XSD validation schemas
 ┃ ┣ 📂 tests/               # Pytest suites
 ┃ ┣ 📂 tools/               # Diagnostic and simulation scripts
 ┃ ┣ 📜 main.py              # Service entrypoint
 ┃ ┣ 📜 receiver.py          # RabbitMQ message consumer
 ┃ ┣ 📜 sender.py            # Resilient message publisher
 ┃ ┗ 📜 order_poller.py      # Odoo order monitor
 ┣ 📂 k8s/                   # Kubernetes deployment manifests
 ┣ 📜 docker-compose.yml     # Local orchestration stack
 ┗ 📜 README.md
```

---

## Getting Started

### Prerequisites
- Docker & Docker Compose
- Python 3.12+ (for local testing)

### Launch Stack
```bash
cp .env.example .env
docker-compose up -d
```

### Connectivity Check
Validate the XML-RPC connection to Odoo:
```bash
docker-compose exec kassa-integratie python tools/ping_odoo.py
```

---

## Team

| Role | Name |
| :--- | :--- |
| **Team Lead** | Jeremy Luyckfasseel |
| **Developer** | Ahmed Takadoumi |
| **Developer** | Zeno Van Neygen |

---

<div align="center">
  Official Repository - Team POS Integration Project 2026
</div>
