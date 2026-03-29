#!/usr/bin/env python3
"""Test RabbitMQ connection with provided credentials"""
import pika
import os
import traceback

RABBIT_HOST = os.environ.get("RABBIT_HOST", "")
RABBIT_USER = os.environ.get("RABBIT_USER", "")
RABBIT_PASS = os.environ.get("RABBIT_PASS", "")
port_env = os.environ.get("RABBIT_PORT")
try:
    RABBIT_PORT = int(port_env) if port_env else 5672
except ValueError:
    RABBIT_PORT = 5672
RABBIT_VHOST = os.environ.get("RABBIT_VHOST", "")

print("🔗 Testing RabbitMQ connection...")
print(f"   Host: {RABBIT_HOST}:{RABBIT_PORT}")
print(f"   User: {RABBIT_USER}")
print(f"   Vhost: {RABBIT_VHOST}")

try:
    creds = pika.PlainCredentials(RABBIT_USER, RABBIT_PASS)
    params = pika.ConnectionParameters(
        host=RABBIT_HOST,
        port=RABBIT_PORT,
        virtual_host=RABBIT_VHOST,
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
    except BaseException:
        print("   ⚠️  Exchange needs to be created")

    connection.close()
    print("\n🎉 RabbitMQ is working and accessible!")

except Exception as e:
    print(f"\n❌ Connection failed: {e}")
    print(f"\n   Error type: {type(e).__name__}")
    traceback.print_exc()
