import os
import threading
import time
import socket
import pika
import pytest

from integratie import identity_client


def _reply_worker(rabbit_host, queue_name, reply_xml):
    creds = pika.PlainCredentials(os.environ.get("RABBIT_USER", "guest"), os.environ.get("RABBIT_PASS", "guest"))
    conn = pika.BlockingConnection(pika.ConnectionParameters(host=rabbit_host, credentials=creds))
    ch = conn.channel()
    ch.queue_declare(queue=queue_name, durable=True)

    def on_message(ch2, method, props, body):
        # Reply using correlation id and reply_to
        ch2.basic_publish(
            exchange="",
            routing_key=props.reply_to,
            body=reply_xml.encode("utf-8"),
            properties=pika.BasicProperties(correlation_id=props.correlation_id)
        )
        ch2.basic_ack(delivery_tag=method.delivery_tag)

    ch.basic_consume(queue=queue_name, on_message_callback=on_message)
    try:
        ch.start_consuming()
    except Exception:
        pass


def test_identity_rpc_with_real_rabbitmq():
    rabbit = os.environ.get("RABBIT_HOST", "localhost")
    queue = os.environ.get("IDENTITY_ROUTING_KEY_CREATE", "identity.user.create.request")

    # Skip if no RabbitMQ is reachable on the configured host/port
    port = int(os.environ.get("RABBIT_PORT", "5672"))
    try:
        socket.create_connection((rabbit, port), timeout=0.5)
    except OSError:
        pytest.skip("RabbitMQ not reachable on %s:%d" % (rabbit, port))

    # Start a background thread to reply to requests
    reply_xml = """<?xml version='1.0'?>
<identity_response>
  <status>ok</status>
  <user>
    <master_uuid>integration-123</master_uuid>
    <email>int@test</email>
  </user>
</identity_response>"""

    t = threading.Thread(target=_reply_worker, args=(rabbit, queue, reply_xml), daemon=True)
    t.start()

    # Allow background worker to start
    time.sleep(0.5)

    # Call create_user which should make an RPC and receive the reply
    master_uuid = identity_client.create_user("int@test", source_system="integration-test")
    assert master_uuid == "integration-123"
