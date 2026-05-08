import os
import threading
import time
import socket
import pika
import pytest

try:
    from integratie import identity_client
    from integratie import receiver
except ImportError:
    import identity_client  # type: ignore[no-redef]
    import receiver  # type: ignore[no-redef]


def _broker_reachable():
    rabbit = os.environ.get("RABBIT_HOST", "localhost")
    port = int(os.environ.get("RABBIT_PORT", "5672"))
    try:
        socket.create_connection((rabbit, port), timeout=0.5)
        return rabbit, port
    except OSError:
        return None, None


def _reply_worker(rabbit_host, queue_name, reply_xml):
    creds = pika.PlainCredentials(
        os.environ.get("RABBIT_USER", "guest"),
        os.environ.get("RABBIT_PASS", "guest"),
    )
    conn = pika.BlockingConnection(pika.ConnectionParameters(host=rabbit_host, credentials=creds))
    ch = conn.channel()
    ch.queue_declare(queue=queue_name, durable=True)

    def on_message(ch2, method, props, body):
        ch2.basic_publish(
            exchange="",
            routing_key=props.reply_to,
            body=reply_xml.encode("utf-8"),
            properties=pika.BasicProperties(correlation_id=props.correlation_id),
        )
        ch2.basic_ack(delivery_tag=method.delivery_tag)

    ch.basic_consume(queue=queue_name, on_message_callback=on_message)
    try:
        ch.start_consuming()
    except Exception:
        pass


def test_identity_rpc_with_real_rabbitmq():
    rabbit, port = _broker_reachable()
    if rabbit is None:
        pytest.skip("RabbitMQ not reachable on %s:%d" % (
            os.environ.get("RABBIT_HOST", "localhost"),
            int(os.environ.get("RABBIT_PORT", "5672")),
        ))

    queue = os.environ.get("IDENTITY_ROUTING_KEY_CREATE", "identity.user.create.request")

    reply_xml = """<?xml version='1.0'?>
<identity_response>
  <status>ok</status>
  <user>
    <master_uuid>integration-123</master_uuid>
    <email>int@test</email>
    <created_by>integration-test</created_by>
    <created_at>2026-05-08T10:00:00</created_at>
  </user>
</identity_response>"""

    t = threading.Thread(target=_reply_worker, args=(rabbit, queue, reply_xml), daemon=True)
    t.start()
    time.sleep(0.5)

    master_uuid = identity_client.create_user("int@test", source_system="integration-test")
    assert master_uuid == "integration-123"


def test_user_events_fanout_subscription_with_real_rabbitmq():
    rabbit, port = _broker_reachable()
    if rabbit is None:
        pytest.skip("RabbitMQ not reachable on %s:%d" % (
            os.environ.get("RABBIT_HOST", "localhost"),
            int(os.environ.get("RABBIT_PORT", "5672")),
        ))

    creds = pika.PlainCredentials(
        os.environ.get("RABBIT_USER", "guest"),
        os.environ.get("RABBIT_PASS", "guest"),
    )
    conn = pika.BlockingConnection(pika.ConnectionParameters(host=rabbit, credentials=creds))
    ch = conn.channel()

    # Declare and bind the consumer queue the same way the receiver does
    ch.exchange_declare(exchange="user.events", exchange_type="fanout", durable=True)
    test_queue = "test.user.events.integration"
    ch.queue_declare(queue=test_queue, durable=True)
    ch.queue_bind(exchange="user.events", queue=test_queue)

    # Publish a valid user_event to the fanout
    user_event_xml = (
        "<?xml version='1.0'?>"
        "<user_event>"
        "<event>UserCreated</event>"
        "<master_uuid>fanout-uuid-001</master_uuid>"
        "<email>fanout@test.com</email>"
        "<source_system>frontend</source_system>"
        "<timestamp>2026-05-08T10:00:00</timestamp>"
        "</user_event>"
    )
    ch.basic_publish(exchange="user.events", routing_key="", body=user_event_xml.encode("utf-8"))

    # Give the broker a moment to route it
    time.sleep(0.3)

    method, props, body = ch.basic_get(test_queue, auto_ack=True)
    assert method is not None, "No message received on user.events queue"
    received = body.decode("utf-8")
    assert "fanout-uuid-001" in received

    # Verify our XSD accepts it (same check the receiver callback does)
    receiver.validate_xml(received, "user_event")

    ch.queue_delete(queue=test_queue)
    conn.close()
