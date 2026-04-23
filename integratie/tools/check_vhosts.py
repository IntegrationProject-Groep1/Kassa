"""Check RabbitMQ vhost accessibility.

Usage:
    python check_vhosts.py
"""
import os
import pika


def check_vhost(vhost: str) -> None:
    user = os.environ.get("RABBIT_USER")
    password = os.environ.get("RABBIT_PASS")
    host = os.environ.get("RABBIT_HOST")
    port = int(os.environ.get("RABBIT_PORT", "5672"))

    credentials = pika.PlainCredentials(user, password)
    params = pika.ConnectionParameters(
        host=host,
        port=port,
        virtual_host=vhost,
        credentials=credentials
    )
    try:
        conn = pika.BlockingConnection(params)
        print(f"✅ Success with vhost: {vhost}")
        conn.close()
    except Exception as e:
        print(f"❌ Failed with vhost '{vhost}': {e}")


if __name__ == "__main__":
    vhosts_to_check = ['/', '/kassa', 'kassa', '/kassa_rabbitmq', 'kassa_rabbitmq']
    print("🔍 Checking RabbitMQ vhosts...\n")
    for vhost in vhosts_to_check:
        check_vhost(vhost)
