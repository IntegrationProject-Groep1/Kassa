# main.py – Kassa Integration Service entry point
# Team Kassa (Odoo POS) | Integratieproject Desideriushogeschool 2026
#
# Starts all integration components in separate daemon threads:
#   - receiver   → listens on queue.incoming (RabbitMQ)
#   - poller     → polls Odoo for new POS orders  (when available)
#   - heartbeat  → sends periodic heartbeat        (when available)

import sys
import threading
import time

import receiver


def _run_receiver() -> None:
    """Start the RabbitMQ receiver in a thread. Retries on connection failure."""
    retry_delay = 5  # seconds between retries
    while True:
        try:
            receiver.start_listening()
        except Exception as exc:
            print(f"[MAIN] Receiver crashed: {exc} – retrying in {retry_delay}s…", flush=True)
            time.sleep(retry_delay)


def main() -> None:
    print("[MAIN] Kassa Integration Service starting…", flush=True)

    # ── Receiver thread ────────────────────────────────────────────────────────
    receiver_thread = threading.Thread(
        target=_run_receiver,
        name="receiver",
        daemon=True,
    )
    receiver_thread.start()
    print("[MAIN] ✓ Receiver thread started", flush=True)

    # ── Poller thread (uncomment when poller.py is available) ─────────────────
    # import poller
    # poller_thread = threading.Thread(target=poller.start_polling, name="poller", daemon=True)
    # poller_thread.start()
    # print("[MAIN] ✓ Poller thread started", flush=True)

    # ── Heartbeat thread (uncomment when heartbeat.py sidecar is ready) ───────
    # import heartbeat
    # hb_thread = threading.Thread(target=heartbeat.start, name="heartbeat", daemon=True)
    # hb_thread.start()
    # print("[MAIN] ✓ Heartbeat thread started", flush=True)

    # ── Keep main thread alive ─────────────────────────────────────────────────
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("\n[MAIN] Shutdown requested – stopping service.", flush=True)
        sys.exit(0)


if __name__ == "__main__":
    main()
