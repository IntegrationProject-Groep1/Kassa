<div align="center">

<!-- Typing SVG Header -->
<img src="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=600&size=28&pause=1000&color=58A6FF&center=true&vCenter=true&width=600&lines=Team+POS+%7C+Kassa+Integration;Resilient+Event-Driven+Architecture;Odoo+%2B+RabbitMQ+%2B+Salesforce" alt="Kassa Integration Typing SVG" />

<br/>

<!-- Status & Tech Badges -->
[![Version](https://img.shields.io/badge/Version-1.0.0-3b82f6?style=flat-square&labelColor=161b22)](https://github.com/IntegrationProject-Groep1/Kassa)
[![Build](https://img.shields.io/badge/Build-Passing-22c55e?style=flat-square&labelColor=161b22)](https://github.com/IntegrationProject-Groep1/Kassa/actions)
[![License](https://img.shields.io/badge/License-LGPL--3-orange?style=flat-square&labelColor=161b22)](https://github.com/IntegrationProject-Groep1/Kassa/blob/dev/addons/kassa_pos_custom/__manifest__.py)
[![Odoo](https://img.shields.io/badge/Platform-Odoo%2016%2F17-875A7B?style=flat-square&logo=odoo&logoColor=white&labelColor=161b22)](https://www.odoo.com)
[![RabbitMQ](https://img.shields.io/badge/Messaging-RabbitMQ-FF6600?style=flat-square&logo=rabbitmq&logoColor=white&labelColor=161b22)](https://www.rabbitmq.com)

</div>

---

## 📖 Project Overview

The **Kassa Integration** is a mission-critical bridge designed for the Desideriushogeschool 2026 event ecosystem. It serves as the primary data conduit between the **Odoo Point of Sale** and external enterprise systems, ensuring high availability and transactional integrity.

> *"Bridging the gap between real-time retail operations and asynchronous enterprise data flows."*

---

## ✨ Core Capabilities

| Feature | Description | Status |
|---|---|---|
| **🛡️ Resilience** | Local `outbox.json` buffering for 100% message delivery during network outages. | ✅ |
| **🆔 Smart Identity** | IoT Badge scanning via Odoo `bus` for instantaneous customer identification. | ✅ |
| **🔞 Compliance** | Automated logic for age-restricted products and anonymous transaction blocking. | ✅ |
| **🔄 Sync Engine** | High-frequency polling and real-time consumption order dispatching. | ✅ |

---

## 🛠️ Technical Stack

| Domain | Technologies |
|---|---|
| **Core Languages** | ![Python](https://img.shields.io/badge/Python-3670A0?style=flat-square&logo=python&logoColor=ffdd54) ![SQL](https://img.shields.io/badge/SQL-4479A1?style=flat-square&logo=postgresql&logoColor=white) ![JavaScript](https://img.shields.io/badge/JavaScript-323330?style=flat-square&logo=javascript&logoColor=F7DF1E) |
| **Frameworks** | ![Odoo](https://img.shields.io/badge/Odoo-875A7B?style=flat-square&logo=odoo&logoColor=white) ![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=flat-square&logo=fastapi&logoColor=white) |
| **Infrastructure** | ![Docker](https://img.shields.io/badge/Docker-0db7ed?style=flat-square&logo=docker&logoColor=white) ![RabbitMQ](https://img.shields.io/badge/RabbitMQ-FF6600?style=flat-square&logo=rabbitmq&logoColor=white) ![GitHub Actions](https://img.shields.io/badge/CI%2FCD-2088FF?style=flat-square&logo=github-actions&logoColor=white) |
| **Architecture** | ![Event-Driven](https://img.shields.io/badge/Event--Driven-f97316?style=flat-square) ![XML-RPC](https://img.shields.io/badge/XML--RPC-6B7280?style=flat-square) |

---

## 🏗️ System Architecture

Our architecture is strictly decoupled. The integration service acts as the orchestrator, managing state between Odoo's synchronous API and the ecosystem's asynchronous messaging.

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

### 📋 Message Routing Legend

| Type | Direction | Target | Purpose |
| :--- | :---: | :--- | :--- |
| `new_registration` | 📥 | Odoo | Onboarding new customers from CRM. |
| `badge_scanned` | 📥 | POS | Instant UI profile loading. |
| `consumption_order`| 📤 | Salesforce | Finalizing transaction billing. |
| `system_error` | 📤 | Elastic | Real-time failure observability. |

---

## 📈 Integration Activity

<p align="center">
  <img height="180em" src="https://github-readme-stats.vercel.app/api?username=Jeremy-Luyckfasseel&show_icons=true&theme=github_dark&hide_border=true&count_private=true&include_all_commits=true" />
  <img height="180em" src="https://github-readme-stats.vercel.app/api/top-langs/?username=Jeremy-Luyckfasseel&layout=compact&theme=github_dark&hide_border=true" />
</p>

<p align="center">
  <img src="https://streak-stats.demolab.com/?user=Jeremy-Luyckfasseel&theme=github-dark-blue&hide_border=true" />
</p>

---

## 🚀 Deployment & Usage

### Rapid Setup
```bash
cp .env.example .env
docker-compose up -d
```

### Diagnostics
```bash
# Check Odoo Connectivity
docker-compose exec kassa-integratie python tools/ping_odoo.py

# Simulate Integration Message
docker-compose exec kassa-integratie python tools/create_test_order.py
```

---

<div align="center">

*"Turning complex business requirements into seamless technical solutions."*

<br/>

[![LinkedIn](https://img.shields.io/badge/LinkedIn-0077B5?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/jeremy-luyckfasseel-97244a32b)
[![Gmail](https://img.shields.io/badge/Gmail-D14836?style=for-the-badge&logo=gmail&logoColor=white)](mailto:luyckfasseel.jeremy@gmail.com)

</div>
