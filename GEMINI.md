# Gemini Project Context: Kassa (POS Integration)

Official repository for Team POS (Kassa) - Integration Project Desideriushogeschool 2026. This project manages an Odoo-based Point of Sale (POS) system and its integration with external systems (CRM, Frontend, IoT) via RabbitMQ.

## 🏗️ System Architecture

The project consists of three main components:
1.  **Odoo POS:** The core retail system (PostgreSQL backend).
2.  **Kassa Integration (Python):** A service that bridges Odoo and RabbitMQ.
    *   **Receiver:** Listens for incoming RabbitMQ messages (from CRM/IoT) to update Odoo.
    *   **Poller:** Monitors Odoo for new POS orders.
    *   **Sender:** Dispatches outgoing XML messages to RabbitMQ (with offline buffering).
3.  **RabbitMQ:** Message broker for asynchronous communication using the `kassa.exchange` (topic).

### 🛠️ Tech Stack
- **Languages:** Python 3.12, JavaScript (Odoo POS Owl/JS)
- **Framework:** Odoo 16/17 (Point of Sale)
- **Communication:** XML-RPC (Integration -> Odoo), XML over RabbitMQ (Integration -> External)
- **Database:** PostgreSQL 15
- **Infrastructure:** Docker, Kubernetes (k8s/)

---

## 🚀 Building and Running

### Prerequisites
- Docker & Docker Compose
- Python 3.12 (for local development)

### Commands
| Task | Command |
| :--- | :--- |
| **Start Environment** | `docker-compose up -d` |
| **Stop Environment** | `docker-compose down` |
| **View Integration Logs** | `docker-compose logs -f kassa-integratie` |
| **Run Tests** | `docker-compose exec kassa-integratie pytest integratie/tests/` |
| **Odoo Connectivity Check** | `docker-compose exec kassa-integratie python tools/ping_odoo.py` |
| **Manual Flush Buffer** | `docker-compose exec kassa-integratie python -c "import sender; sender.flush_buffer()"` |

---

## 📂 Key Directories & Files

### `integratie/` (Python Service)
- `main.py`: Entry point. Handles Odoo bootstrapping (via `odoo_setup.py`) and starts the `receiver` and `poller` threads.
- `receiver.py`: Processes incoming RabbitMQ messages and calls Odoo XML-RPC.
- `order_poller.py`: Periodically checks Odoo for new orders (`pos.order`) to send to the CRM.
- `sender.py`: Formats XML and publishes to RabbitMQ. Implements `outbox.json` buffering for offline resilience.
- `schemas/`: XSD files for validating XML messages.
- `tools/`: Diagnostic and utility scripts (ping Odoo, check RabbitMQ, etc.).

### `addons/kassa_pos_custom/` (Odoo Module)
- Customizes the POS frontend (Owl/JS) and backend models.
- Handles badge scanning events (`bus` integration) and age restrictions.

### `k8s/`
- Kubernetes manifests for production deployment.

---

## ⚙️ Development Conventions

### Offline Resilience
- **Mandatory Buffering:** All outgoing messages MUST pass through the `sender.py` buffering logic. If RabbitMQ is unreachable, messages are stored in `outbox/outbox.json`.
- **Idempotency:** The `odoo_setup.py` logic (called in `main.py`) is idempotent. It ensures the database, modules, and base data are configured correctly on every startup.

### XML Standards
- All external communication uses XML.
- Outgoing messages MUST be validated against the schemas in `integratie/schemas/` before sending.

### Testing
- **Pytest:** Use `pytest` for unit and integration tests in `integratie/tests/`.
- **Odoo Simulation:** Use `tools/create_test_order.py` to simulate POS transactions for testing the poller/sender flow.

### Environment Variables
- Configuration is managed via `.env`. See `.env.example` for required variables (ODOO_URL, RABBITMQ_HOST, etc.).

---

## 🆘 Troubleshooting

- **Odoo Assets 500:** If the POS UI fails to load after a restart, clear the attachment cache:
  `docker exec -i kassa_db psql -U odoo -d odoo_kassa -c "DELETE FROM ir_attachment WHERE url LIKE '/web/assets/%';"`
- **Buffer Issues:** If messages are stuck, check `outbox/outbox.json` permissions or run the `flush_buffer()` tool.
