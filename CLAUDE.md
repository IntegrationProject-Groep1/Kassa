# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r integratie/requirements.txt
pip install -r integratie/requirements-dev.txt

# Run all tests
pytest integratie/tests/ -v

# Run a single test file or specific test
pytest integratie/tests/test_receiver.py -v
pytest integratie/tests/test_receiver.py::test_new_registration -v
pytest integratie/tests/test_order_poller.py -v -k "test_send_consumption"

# Lint
flake8 integratie/ --max-line-length=120

# Type check
mypy --config-file=mypy.ini -p integratie

# Start full stack (Odoo + Postgres + RabbitMQ + integration service)
docker-compose up -d
```

## Architecture

Kassa is an event-driven middleware that bridges **Odoo POS** with external systems (Salesforce CRM, Drupal, IoT badge scanners, Planning, Elastic) via **RabbitMQ** as a central message broker.

```
CRM / IoT / Frontend / Planning ──> RabbitMQ (kassa.exchange) ──> Python integration service ──> Odoo POS (XML-RPC)
                                                                           |
                                                              outbox.json (offline buffer, path: OUTBOX_DIR)
```

All code lives under `integratie/`. The **three** runtime threads started by `main.py` are:

**`receiver.py`** — RabbitMQ consumer on `kassa.incoming`. Handles **14 incoming message types**:
- `new_registration`, `profile_update`, `badge_scanned`, `cancel_registration` (CRM/IoT)
- `wallet_lease_grant`, `wallet_remote_topup`, `event_ended` (CRM wallet lifecycle)
- `user_event` (fanout, informational only)
- `user_registered`, `user_unregistered` (Frontend dual-publish — session enrolment/withdrawal; updates partner's session list and outstanding amount)
- `user_sessions_response`, `session_created`, `session_updated`, `session_deleted` (Frontend session management)

Also binds routing keys for `session_view_response` from Planning. Validates against XSD schemas, detects duplicates (OrderedDict, max 10k), retries on Odoo errors (max 3, via RETRY_QUEUE with 5s TTL) → Dead Letter Queue on failure.

**`sender.py`** — RabbitMQ publisher to `kassa.exchange`. Publishes outbound message types including consumption_order, payment_registered, refund_processed, invoice_request, badge_assigned, payment_status, wallet_balance_update, wallet_lease_request, wallet_lease_return, user_sessions_request, session_view_request. Writes to `outbox.json` (Docker volume, max 500, path configurable via `OUTBOX_DIR`) when broker is unreachable. All outgoing messages are XSD-validated before publish.

**`order_poller.py`** — Background thread that polls Odoo every `POLL_INTERVAL` seconds (default: **5**) for `pos.order` records in `paid`/`done`/`invoiced` state. Detects consumption vs. refund vs. registration, splits Badge Wallet vs. Cash/Invoice/Customer Account payments. Also polls for badge assignments (`poll_badge_assignments`) and detects new POS sessions to trigger `session_view_request` to Planning (`check_pos_sessions`). Flushes outbox every 30 seconds. LRU cache (max 10k) prevents reprocessing.

**`partner_identity_poller.py`** — Background thread (interval: `IDENTITY_POLL_INTERVAL`, default: 10s) that finds Odoo partners with an email but no `x_user_id` and links them via the Identity Service RPC. Sets `x_identity_status` to `pending`/`linked`/`error`.

**`odoo_setup.py`** — Runs once at startup. Waits for Odoo, auto-creates DB, installs POS + custom addons, creates custom fields, configures payment methods and POS profiles.

**Supporting modules:** `config_utils.py` (env parsing), `typing_utils.py` (Odoo type hints), `monitoring.py` (session logging), `identity_client.py` (identity service RPC client), `pos_profiles.py` (POS config), `mcp_server.py` (MCP server for tooling integration).

## Key Design Rules

- **All inter-system communication goes through `kassa.exchange`** — no direct calls between systems.
- **Every XML message is validated against an XSD schema** before processing (incoming) or publishing (outgoing). Schemas live in `integratie/schemas/`.
- **Offline buffering is mandatory** — sender falls back to `outbox.json` if RabbitMQ is unreachable; never drop a message.
- **Duplicate detection is in-memory** — restart clears dedup state; this is acceptable per design.
- **Odoo access is via XML-RPC only** (`xmlrpc.client`) — never direct DB access.
- Invalid/malformed messages go to `kassa.errors` routing key and are nack'd with `requeue=False`.
- **badge_scanned supports two variants**: `badge_id` (physical badge) or `identity_uuid` (QR code). The receiver handles both.
- **Wallet lease lifecycle**: badge/QR scan triggers `wallet_lease_request` → CRM responds with `wallet_lease_grant` → Kassa owns the balance → `wallet_lease_return` at event end or checkout.

## Custom Fields

Key custom fields on `res.partner`: `x_user_id` (master_uuid), `x_badge_id`, `x_wallet_balance`, `x_session_title` (JSON array), `x_outstanding_amount`, `x_payment_status`, `x_date_of_birth`, `x_lease_active`, `x_lease_id`, `x_lease_transaction_count`, `x_pending_topup_balance`, `x_identity_status`, `x_identity_last_sync`, `x_badge_sent`.

Key custom fields on `pos.order`: `x_rabbitmq_sent`, `x_rabbitmq_error`, `x_wallet_updated`, `x_payment_message_id`, `x_invoice_message_id`.

Key custom fields on `product.template`: `x_session_id`. On `product.product`: `x_is_topup`.

## XSD Contract

The canonical message contract is `documentatie/XML_XSD_Contract_v2.3_Centralized.md`. All new message types or field changes must update the relevant XSD in `integratie/schemas/` and the contract document.

## CI

Three GitHub Actions workflows:
- **ci.yml** — flake8, mypy, pytest, Docker integration tests (runs on push to main/dev/prod)
- **deploy.yml** — builds and pushes Docker image to GHCR
- **security.yml** — Bandit (SAST), pip-audit, TruffleHog, Trivy

Tests must pass locally before pushing. `conftest.py` sets dummy env vars so tests run without a live stack.

## Environment

Copy `.env.example` → `.env`. Key vars: `ODOO_URL`, `RABBIT_HOST`, `RABBIT_EXCHANGE=kassa.exchange`, `RABBIT_INCOMING_QUEUE=kassa.incoming`, `POLL_INTERVAL` (seconds, default 5), `IDENTITY_POLL_INTERVAL` (seconds, default 10), `SUBSCRIBE_USER_EVENTS` (bool). Full var list in `.env.example` and `documentatie/Tech_Stack_Kassa.md`.
