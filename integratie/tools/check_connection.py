#!/usr/bin/env python3
"""Check RabbitMQ connection with provided credentials.

Usage:
    python check_connection.py
"""
import os
import sys
import pika
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config_utils import get_env, parse_rabbit_port  # noqa: E402


def main() -> None:
    rabbit_host = get_env("RABBIT_HOST", "")
    rabbit_user = get_env("RABBIT_USER", "")
    rabbit_pass = get_env("RABBIT_PASS", "")
    rabbit_port = parse_rabbit_port()
    rabbit_vhost = get_env("RABBIT_VHOST", "")

    print("🔗 Testing RabbitMQ connection...")
    print(f"   Host: {rabbit_host}:{rabbit_port}")
    print(f"   User: {rabbit_user}")
    print(f"   Vhost: {rabbit_vhost}")

    try:
        creds = pika.PlainCredentials(rabbit_user, rabbit_pass)
        params = pika.ConnectionParameters(
            host=rabbit_host,
            port=rabbit_port,
            virtual_host=rabbit_vhost,
            credentials=creds,
            connection_attempts=1,
            retry_delay=0,
        )

        connection = pika.BlockingConnection(params)
        channel = connection.channel()

        print("\n✅ CONNECTION SUCCESSFUL!")
        print(f"   Channel created: {channel}")

        # Verify exchange exists or create it
        try:
            channel.exchange_declare(
                exchange='kassa.exchange',
                exchange_type=pika.exchange_type.ExchangeType.topic,
                passive=True  # Just check if exists
            )
            print("   ✅ Exchange 'kassa.exchange' exists")
        except pika.exceptions.AMQPError:
            print("   ⚠️  Exchange needs to be created")

        connection.close()
        print("\n🎉 RabbitMQ is working and accessible!")

    except Exception as e:
        print(f"\n❌ Connection failed: {e}")
        print(f"\n   Error type: {type(e).__name__}")
        traceback.print_exc()


if __name__ == "__main__":
    main()
