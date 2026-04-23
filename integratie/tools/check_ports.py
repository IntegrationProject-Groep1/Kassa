#!/usr/bin/env python3
"""Check multiple AMQP port configurations.

Usage:
    python check_ports.py
"""
import os
import sys
import pika
import socket
import ssl

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config_utils import get_env  # noqa: E402


def main() -> None:
    rabbit_host = get_env("RABBIT_HOST", "")
    rabbit_user = get_env("RABBIT_USER", "")
    rabbit_pass = get_env("RABBIT_PASS", "")

    # Try multiple ports in order
    ports_to_try = [
        (5672, False, "Standard AMQP"),
        (5671, True, "AMQP over TLS"),
        (30001, False, "Management console port"),
        (15672, False, "Management HTTP fallback"),
    ]

    print("=" * 60)
    print("TESTING MULTIPLE AMQP CONFIGURATIONS")
    print("=" * 60)

    # First, raw socket test to see what's reachable
    print("\n🔍 RAW PORT SCANNING:")
    for port, use_tls, description in ports_to_try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        try:
            sock.connect((rabbit_host, port))
            print(f"   ✅ Port {port:5d} ({description:30s}) — OPEN")
            sock.close()
        except socket.timeout:
            print(f"   ❌ Port {port:5d} ({description:30s}) — TIMEOUT")
        except ConnectionRefusedError:
            print(f"   ❌ Port {port:5d} ({description:30s}) — REFUSED")
        except Exception as e:
            print(f"   ❌ Port {port:5d} ({description:30s}) — ERROR: "
                  f"{type(e).__name__}")

    # Now try AMQP connections
    print("\n\n📡 PIKA CONNECTION TESTS:")

    for port, use_tls, description in ports_to_try[:2]:  # Only AMQP-capable ports
        print(f"\n   Trying {description} (port {port})...")
        try:
            creds = pika.PlainCredentials(rabbit_user, rabbit_pass)
            params = pika.ConnectionParameters(
                host=rabbit_host,
                port=port,
                credentials=creds,
                connection_attempts=1,
                retry_delay=0,
                ssl_options=pika.SSLOptions(ssl.create_default_context()) if use_tls else None  # type: ignore
            )

            connection = pika.BlockingConnection(params)
            print(f"   ✅ SUCCESS on port {port}!")
            connection.close()
            break
        except Exception as e:
            print(f"   ❌ Failed: {type(e).__name__}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
