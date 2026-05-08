import time
import types
import pytest

from integratie import identity_client


class FakeChannel:
    def __init__(self, reply_body: bytes = b"", respond=True, delay=0):
        self.reply_body = reply_body
        self.respond = respond
        self.delay = delay
        self.last_props = None

    def queue_declare(self, queue, exclusive=False):
        class Method:
            def __init__(self):
                self.queue = "amq.gen-fake"

        return types.SimpleNamespace(method=Method())

    def basic_publish(self, exchange, routing_key, body, properties=None):
        self.last_props = properties

    def basic_get(self, queue, auto_ack=True):
        # Simulate optional delay before reply
        if not self.respond:
            return (None, None, None)
        if self.delay:
            time.sleep(self.delay)
        # Create a fake header_frame with correlation_id matching last props
        header = types.SimpleNamespace(correlation_id=getattr(self.last_props, "correlation_id", None))
        method = types.SimpleNamespace()
        return (method, header, self.reply_body)


def test_rpc_success(monkeypatch):
    sample = (
        b"<?xml version='1.0'?>"
        b"<identity_response><status>ok</status><user>"
        b"<master_uuid>rpc-1</master_uuid></user></identity_response>"
    )
    fake = FakeChannel(reply_body=sample, respond=True)
    monkeypatch.setattr(identity_client, "connect_to_rabbitmq", lambda: (None, fake))

    res = identity_client._rpc_call("identity.user.create.request", b"<x/>".decode("utf-8"))
    assert "master_uuid" in res


def test_rpc_email_exists(monkeypatch):
    sample = (
        b"<?xml version='1.0'?>"
        b"<identity_response><status>error</status>"
        b"<error_code>EMAIL_ALREADY_EXISTS</error_code><message>Exists</message></identity_response>"
    )
    fake = FakeChannel(reply_body=sample, respond=True)
    monkeypatch.setattr(identity_client, "connect_to_rabbitmq", lambda: (None, fake))

    # Use create_user which should raise IdentityEmailAlreadyExists
    with pytest.raises(identity_client.IdentityEmailAlreadyExists):
        identity_client.create_user("dup@example.com", source_system="test")


def test_rpc_timeout(monkeypatch):
    fake = FakeChannel(respond=False)
    monkeypatch.setattr(identity_client, "connect_to_rabbitmq", lambda: (None, fake))
    # reduce retries/timeouts for test speed
    monkeypatch.setattr(identity_client, "RPC_RETRIES", 2)
    monkeypatch.setattr(identity_client, "RPC_TIMEOUT", 0.2)
    with pytest.raises(identity_client.IdentityUnavailableError):
        identity_client._rpc_call("identity.user.create.request", "<x/>")
