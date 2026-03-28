import pika
import os

def test_vhost(vhost):
    user = os.environ.get("RABBIT_USER")
    password = os.environ.get("RABBIT_PASS")
    host = os.environ.get("RABBIT_HOST")
    port = int(os.environ.get("RABBIT_PORT", 30000))
    
    credentials = pika.PlainCredentials(user, password)
    params = pika.ConnectionParameters(
        host=host,
        port=port,
        virtual_host=vhost,
        credentials=credentials
    )
    try:
        conn = pika.BlockingConnection(params)
        print(f"Success with vhost: {vhost}")
        conn.close()
    except Exception as e:
        print(f"Failed with vhost {vhost}: {e}")

for vhost in ['/', '/kassa', 'kassa', '/kassa_rabbitmq', 'kassa_rabbitmq']:
    test_vhost(vhost)
