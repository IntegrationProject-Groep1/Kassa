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

Kassa is an event-driven middleware that bridges **Odoo POS** with external systems (Salesforce CRM, Drupal, IoT badge scanners, Elastic) via **RabbitMQ** as a central message broker.

```
CRM / IoT / Drupal ──> RabbitMQ (kassa.exchange) ──> Python integration service ──> Odoo POS (XML-RPC)
                                                           |
                                              outbox.json (offline buffer)
```

All code lives under `integratie/`. The three runtime components are:

**`receiver.py`** — RabbitMQ consumer on `kassa.incoming`. Handles 8 incoming message types (new_registration, profile_update, badge_scanned, cancel_registration, wallet_lease_grant, wallet_remote_topup, event_ended, user_event). Validates against XSD schemas, detects duplicates (OrderedDict, max 10k), retries on Odoo errors (max 3) → Dead Letter Queue on failure.

**`sender.py`** — RabbitMQ publisher to `kassa.exchange`. Publishes 9 outbound message types. Writes to `outbox/outbox.json` (Docker volume, max 500) when broker is unreachable. All outgoing messages are XSD-validated before publish.

**`order_poller.py`** — Background thread that polls Odoo every `POLL_INTERVAL` seconds for `pos.order` records in `paid`/`done` state. Detects consumption vs. refund, splits Badge Wallet vs. Cash/Invoice payments. Flushes outbox every 30 seconds. LRU cache (max 10k) prevents reprocessing.

**`odoo_setup.py`** — Runs once at startup. Waits for Odoo, auto-creates DB, installs POS + custom addons, creates custom fields (`x_user_id`, `x_badge_id`, `x_wallet_balance`, `x_session_title`), configures payment methods and POS profile.

**Supporting modules:** `config_utils.py` (env parsing), `typing_utils.py` (Odoo type hints), `monitoring.py` (session logging), `identity_client.py` (identity service HTTP client), `pos_profiles.py` (POS config).

## Key Design Rules

- **All inter-system communication goes through `kassa.exchange`** — no direct calls between systems.
- **Every XML message is validated against an XSD schema** before processing (incoming) or publishing (outgoing). Schemas live in `integratie/schemas/`.
- **Offline buffering is mandatory** — sender falls back to `outbox.json` if RabbitMQ is unreachable; never drop a message.
- **Duplicate detection is in-memory** — restart clears dedup state; this is acceptable per design.
- **Odoo access is via XML-RPC only** (`xmlrpc.client`) — never direct DB access.
- Invalid/malformed messages go to `kassa.errors` routing key and are nack'd with `requeue=False`.

## XSD Contract

The canonical message contract is `documentatie/XML_XSD_Contract_v2.3_Centralized.md`. All new message types or field changes must update the relevant XSD in `integratie/schemas/` and the contract document.

## CI

Three GitHub Actions workflows:
- **ci.yml** — flake8, mypy, pytest, Docker integration tests (runs on push to main/dev/prod)
- **deploy.yml** — builds and pushes Docker image to GHCR
- **security.yml** — Bandit (SAST), pip-audit, TruffleHog, Trivy

Tests must pass locally before pushing. `conftest.py` sets dummy env vars so tests run without a live stack.

## Environment

Copy `.env.example` → `.env`. Key vars: `ODOO_URL`, `RABBIT_HOST`, `RABBIT_EXCHANGE=kassa.exchange`, `RABBIT_INCOMING_QUEUE=kassa.incoming`, `POLL_INTERVAL` (seconds), `SUBSCRIBE_USER_EVENTS` (bool). Full var list in `.env.example`.
