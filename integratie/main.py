# main.py – Kassa Integration Service entry point
# Team Kassa (Odoo POS) | Integratieproject Desideriushogeschool 2026
#
# Starts all integration components in separate daemon threads:
#   - receiver   → listens on queue.incoming (RabbitMQ)
#   - poller     → polls Odoo for new POS orders
#
# Odoo bootstrap is delegated to odoo_setup.py (idempotent, runs on every startup).

import logging
import os
import socket
import sys
import threading
import time
import xmlrpc.client  # nosec
import defusedxml.xmlrpc

import receiver
import sender
import monitoring
from order_poller import OrderPoller
from partner_identity_poller import PartnerIdentityPoller
from pos_profiles import ensure_pos_profiles
from config_utils import get_env, require_env
from odoo_setup import (
    wait_for_odoo,
    setup_database,
    ensure_pos_installed,
    ensure_kassa_addons,
    ensure_custom_fields,
    ensure_tax_settings,
    ensure_pos_categories,
    ensure_payment_methods,
    ensure_demo_products,
)

defusedxml.xmlrpc.monkey_patch()


def _classify_connection_error(exc: BaseException) -> str | None:
    """Return a human-readable reason string if exc is a network/DNS failure, else None."""
    seen: set[int] = set()
    queue: list[BaseException] = [exc]
    while queue:
        err = queue.pop()
        if id(err) in seen:
            continue
        seen.add(id(err))
        if isinstance(err, socket.gaierror):
            return "host not found (DNS resolution failed)"
        if isinstance(err, ConnectionRefusedError):
            return "connection refused (service may not be running yet)"
        if isinstance(err, TimeoutError):
            return "connection timed out"
        # pika wraps socket errors as: AMQPConnectionError((<class 'socket.gaierror'>, instance))
        if err.args and isinstance(err.args[0], tuple) and len(err.args[0]) >= 1:
            cls = err.args[0][0]
            if isinstance(cls, type) and issubclass(cls, socket.gaierror):
                return "host not found (DNS resolution failed)"
            if isinstance(cls, type) and issubclass(cls, ConnectionRefusedError):
                return "connection refused (service may not be running yet)"
        for attr in ("__cause__", "__context__"):
            chained = getattr(err, attr, None)
            if chained:
                queue.append(chained)
    return None


def _run_receiver() -> None:
    """Start the RabbitMQ receiver in a thread. Retries on connection failure."""
    _logger = logging.getLogger("main")
    retry_delay = 5  # seconds between retries
    while True:
        try:
            receiver.start_listening()
        except Exception as exc:
            host = os.environ.get("RABBIT_HOST", "rabbitmq")
            reason = _classify_connection_error(exc)
            if reason:
                _logger.warning(
                    "Cannot connect to RabbitMQ at '%s': %s. Retrying in %ds.",
                    host, reason, retry_delay,
                )
            else:
                _logger.error(
                    "Receiver crashed (%s): %s — retrying in %ds.",
                    type(exc).__name__, exc, retry_delay,
                )
            time.sleep(retry_delay)


def main():
    # Configure root logging first — before any module emits log lines.
    # All loggers (receiver, order_poller, sender, …) inherit this configuration.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logging.getLogger("pika").setLevel(logging.WARNING)

    print("🚀 Kassa Integration Service Started", flush=True)
    print("📋 Flow: Odoo POS → Order Poller → Sender → RabbitMQ (+ outbox fallback)", flush=True)

    odoo_env = require_env("ODOO_URL", "ODOO_DB", "ODOO_USER", "ODOO_PASS")
    odoo_url = odoo_env["ODOO_URL"]
    odoo_db = odoo_env["ODOO_DB"]
    odoo_user = odoo_env["ODOO_USER"]
    odoo_pass = odoo_env["ODOO_PASS"]
    odoo_master_pass = get_env("ODOO_MASTER_PASS")
    odoo_load_demo_data = get_env("ODOO_LOAD_DEMO_DATA", "false").strip().lower() in {
        "1", "true", "yes", "on",
    }

    # Step 1: Wait for Odoo web server to be reachable
    if not wait_for_odoo(odoo_url):
        print("❌ Odoo web server did not become available. Exiting.", flush=True)
        sys.exit(1)

    # Step 2: Auto-create database if it doesn't exist
    if not setup_database(
        odoo_url,
        odoo_db,
        odoo_user,
        odoo_pass,
        odoo_master_pass,
        odoo_load_demo=odoo_load_demo_data,
    ):
        print("❌ Database setup failed. Exiting.", flush=True)
        sys.exit(1)

    # Step 3: Auto-install POS module if needed
    if not ensure_pos_installed(odoo_url, odoo_db, odoo_user, odoo_pass):
        print("❌ POS module installation failed. Exiting.", flush=True)
        sys.exit(1)

    # Step 3b: Auto-install/upgrade Kassa custom addons
    ensure_kassa_addons(odoo_url, odoo_db, odoo_user, odoo_pass)

    # Step 4: Ensure custom Odoo fields exist (x_user_id, x_badge_id, etc.)
    ensure_custom_fields(odoo_url, odoo_db, odoo_user, odoo_pass)

    # Step 5: Configure tax settings globally
    tax_map = ensure_tax_settings(odoo_url, odoo_db, odoo_user, odoo_pass)

    # Step 6: Setup POS base data (categories, payment methods, demo products, pos.config)
    topup_cat_id, drinks_cat_id, _ = ensure_pos_categories(odoo_url, odoo_db, odoo_user, odoo_pass)
    ensure_payment_methods(odoo_url, odoo_db, odoo_user, odoo_pass)

    common = xmlrpc.client.ServerProxy(f"{odoo_url}/xmlrpc/2/common", allow_none=True)
    uid = common.authenticate(odoo_db, odoo_user, odoo_pass, {})

    if not uid:
        print("❌ Odoo authentication failed before POS profile setup. Exiting.", flush=True)
        sys.exit(1)

    ensure_demo_products(odoo_url, odoo_db, odoo_user, odoo_pass, topup_cat_id, drinks_cat_id, tax_map)
    ensure_pos_profiles(odoo_url, odoo_db, uid, odoo_pass)

    # ── Receiver thread ────────────────────────────────────────────────────────
    receiver_thread = threading.Thread(
        target=_run_receiver,
        name="receiver",
        daemon=True,
    )
    receiver_thread.start()
    print("✅ Receiver thread started", flush=True)

    # Step 7: Initialize and start Order Poller
    print("📦 Starting Order Poller...", flush=True)
    poller = OrderPoller()

    if not poller.connect_odoo():
        print("❌ Failed to connect to Odoo", flush=True)
        sys.exit(1)

    # Try to flush any buffered messages from previous runs
    print("🔄 Checking for buffered messages...", flush=True)
    sender.flush_buffer()

    print("✅ Order Poller initialized successfully", flush=True)

    # Run poller in a thread
    poller_thread = threading.Thread(
        target=poller.poll,
        kwargs={'interval': int(os.environ.get("POLL_INTERVAL", 5))},
    )
    poller_thread.daemon = True
    poller_thread.start()
    print("✅ Poller thread started", flush=True)

    # Step 7b: Initialize and start Partner Identity Poller
    print("👤 Starting Partner Identity Poller...", flush=True)
    identity_poller = PartnerIdentityPoller()
    if not identity_poller.connect_odoo():
        print("❌ Failed to connect to Odoo for Partner Identity Poller. Exiting.", flush=True)
        sys.exit(1)

    identity_poller_thread = threading.Thread(
        target=identity_poller.poll,
        kwargs={'interval': int(os.environ.get("IDENTITY_POLL_INTERVAL", 10))},
        name="identity_poller",
        daemon=True,
    )
    identity_poller_thread.start()
    print("✅ Partner Identity Poller thread started", flush=True)

    # Create marker file for healthcheck to indicate the service is fully ready
    try:
        with open("/tmp/service_ready", "w") as f:  # nosec B108
            f.write("ready")
        print("✅ Service ready marker created", flush=True)
    except Exception as e:
        print(f"⚠️ Could not create ready marker: {e}", flush=True)

    print("✅ All services running. Press Ctrl+C to stop.", flush=True)

    # Step 8: Start Monitoring (Startup Log)
    monitoring.monitor.log("info", "session", "Kassa Integration Service started and monitoring active.")

    # Keep main thread alive
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("\n🛑 Service shutdown requested – stopping service.", flush=True)
        sys.exit(0)


if __name__ == "__main__":
    main()
