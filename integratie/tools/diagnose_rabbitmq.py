#!/usr/bin/env python3
"""
RabbitMQ Diagnostic Script
Helps troubleshoot connectivity issues to Azure RabbitMQ endpoint
"""
import socket
import os
import sys

# Load environment
RABBIT_HOST = os.getenv('RABBIT_HOST')
RABBIT_PORT = 5672


def test_dns_resolution():
    """Test if hostname can be resolved to IP"""
    print("\n1️⃣  DNS RESOLUTION TEST")
    print("   Testing: {RABBIT_HOST}")
    try:
        ip = socket.gethostbyname(RABBIT_HOST)
        print("   ✅ Resolved to: {ip}")
        return ip
    except socket.gaierror:
        print("   ❌ Failed: {e}")
        return None


def test_tcp_connection(host, port, timeout=5):
    """Test raw TCP connection to host:port"""
    print("\n2️⃣  TCP CONNECTION TEST")
    print("   Testing: {host}:{port} (timeout: {timeout}s)")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
        print("   ✅ Connected successfully")
        sock.close()
        return True
    except socket.timeout:
        print("   ❌ Connection timed out (waited {timeout}s)")
        return False
    except ConnectionRefusedError:
        print("   ❌ Connection refused (port not accepting connections)")
        return False
    except OSError:
        print("   ❌ Network error: {e}")
        return False
    finally:
        sock.close()


def test_amqp_handshake(host, port):
    """Test AMQP protocol handshake"""
    print("\n3️⃣  AMQP HANDSHAKE TEST")
    print("   Testing: {host}:{port}")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)

    try:
        sock.connect((host, port))
        # AMQP server should send 0x4d 0x51 0x50 (MQP) in first few bytes
        data = sock.recv(16)
        if len(data) > 0:
            print("   ✅ Server responded ({len(data)} bytes): {data[:4]}")
            return True
        else:
            print("   ❌ Server accepted connection but sent no data")
            return False
    except Exception:
        print("   ❌ Failed: {e}")
        return False
    finally:
        sock.close()


def test_pika_connection():
    """Test with actual pika library"""
    print("\n4️⃣  PIKA CONNECTION TEST")
    try:
        import pika
        print("   Attempting pika connection (timeout: 5s)...")

        credentials = pika.PlainCredentials(
            os.getenv('RABBIT_USER', 'guest'),
            os.getenv('RABBIT_PASS', 'guest')
        )

        params = pika.ConnectionParameters(
            host=RABBIT_HOST,
            port=RABBIT_PORT,
            credentials=credentials,
            connection_attempts=1,
            retry_delay=0,
            socket_connect_timeout=5
        )

        conn = pika.BlockingConnection(params)
        print("   ✅ Pika connected successfully!")
        conn.close()
        return True
    except Exception:
        print("   ❌ Pika connection failed: {e}")
        return False


def main():
    print("=" * 60)
    print("RabbitMQ DIAGNOSTICS")
    print("=" * 60)

    if not RABBIT_HOST:
        print("❌ RABBIT_HOST is not set. Aborting diagnostics.")
        sys.exit(1)

    # Run tests
    ip = test_dns_resolution()

    if ip:
        tcp_ok = test_tcp_connection(ip, RABBIT_PORT, timeout=10)

        if tcp_ok:
            test_amqp_handshake(ip, RABBIT_PORT)

    test_pika_connection()

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY & NEXT STEPS")
    print("=" * 60)
    print("""
If test results show:
  ❌ DNS resolution fails:
     → Network can't reach Azure (check internet connection)

  ❌ TCP connection times out:
     → Firewall blocking port 5672 (ask Infrastructure team)
     → RabbitMQ service not running on Azure (ask Ahmed)

  ❌ TCP connection refused:
     → RabbitMQ service might be down (ask Ahmed to restart)

  ✅ All tests pass:
     → Check RabbitMQ credentials (RABBIT_USER, RABBIT_PASS)
     → Review RabbitMQ configuration on Azure side
    """)


if __name__ == '__main__':
    main()
