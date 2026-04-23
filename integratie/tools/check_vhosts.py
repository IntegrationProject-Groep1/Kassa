"""Check RabbitMQ vhost accessibility.

Usage:
    python check_vhosts.py
"""
import os
import sys
import pika

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config_utils import get_env, parse_rabbit_port  # noqa: E402


def check_vhost(vhost: str) -> None:
    user = get_env("RABBIT_USER")
    password = get_env("RABBIT_PASS")
    host = get_env("RABBIT_HOST")
    port = parse_rabbit_port()

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
