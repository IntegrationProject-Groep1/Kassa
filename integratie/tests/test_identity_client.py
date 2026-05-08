import pytest

from integratie import identity_client


def test_parse_identity_response_ok():
    xml = '''<?xml version="1.0" encoding="UTF-8"?>
<identity_response>
  <status>ok</status>
  <user>
    <master_uuid>1234-uuid</master_uuid>
    <email>u@example.com</email>
    <created_by>frontend</created_by>
    <created_at>2026-04-24T09:15:00Z</created_at>
  </user>
</identity_response>'''
    status, payload = identity_client._parse_identity_response(xml)
    assert status == "ok"
    assert payload["master_uuid"] == "1234-uuid"
    assert payload["email"] == "u@example.com"


def test_create_user_success(monkeypatch):
    sample = '''<?xml version="1.0" encoding="UTF-8"?>
<identity_response>
  <status>ok</status>
  <user>
    <master_uuid>abcd-1234</master_uuid>
    <email>e@test</email>
    <created_by>test</created_by>
    <created_at>2026-05-08T10:00:00</created_at>
  </user>
</identity_response>'''

    monkeypatch.setattr(identity_client, "_rpc_call", lambda rk, b: sample)
    mid = identity_client.create_user("e@test", source_system="test")
    assert mid == "abcd-1234"


def test_create_user_email_exists(monkeypatch):
    sample = '''<?xml version="1.0" encoding="UTF-8"?>
<identity_response>
  <status>error</status>
  <error_code>EMAIL_ALREADY_EXISTS</error_code>
  <message>Exists</message>
</identity_response>'''

    monkeypatch.setattr(identity_client, "_rpc_call", lambda rk, b: sample)
    with pytest.raises(identity_client.IdentityEmailAlreadyExists):
        identity_client.create_user("dup@test", source_system="test")


def test_create_user_unavailable(monkeypatch):
    def raise_unavailable(rk, b):
        raise identity_client.IdentityUnavailableError("Down")

    monkeypatch.setattr(identity_client, "_rpc_call", raise_unavailable)
    with pytest.raises(identity_client.IdentityUnavailableError):
        identity_client.create_user("x@test", source_system="test")


def test_parse_identity_response_xsd_invalid():
    # Missing required <user> children — XSD should reject this
    bad_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<identity_response>
  <status>ok</status>
  <user>
    <master_uuid>only-uuid</master_uuid>
  </user>
</identity_response>'''
    with pytest.raises(identity_client.IdentityError, match="XSD validation"):
        identity_client._parse_identity_response(bad_xml)


def test_parse_identity_response_invalid_xml():
    with pytest.raises(identity_client.IdentityError, match="not valid XML"):
        identity_client._parse_identity_response("this is not xml at all")


def test_lookup_by_email_success(monkeypatch):
    sample = '''<?xml version="1.0" encoding="UTF-8"?>
<identity_response>
  <status>ok</status>
  <user>
    <master_uuid>lookup-uuid</master_uuid>
    <email>found@test.com</email>
    <created_by>frontend</created_by>
    <created_at>2026-05-08T10:00:00</created_at>
  </user>
</identity_response>'''
    monkeypatch.setattr(identity_client, "_rpc_call", lambda rk, b: sample)
    result = identity_client.lookup_by_email("found@test.com")
    assert result is not None
    assert result["master_uuid"] == "lookup-uuid"
    assert result["email"] == "found@test.com"


def test_lookup_by_email_not_found(monkeypatch):
    sample = '''<?xml version="1.0" encoding="UTF-8"?>
<identity_response>
  <status>error</status>
  <error_code>NOT_FOUND</error_code>
  <message>No user with that email</message>
</identity_response>'''
    monkeypatch.setattr(identity_client, "_rpc_call", lambda rk, b: sample)
    result = identity_client.lookup_by_email("missing@test.com")
    assert result is None


def test_lookup_by_uuid_success(monkeypatch):
    sample = '''<?xml version="1.0" encoding="UTF-8"?>
<identity_response>
  <status>ok</status>
  <user>
    <master_uuid>known-uuid</master_uuid>
    <email>known@test.com</email>
    <created_by>crm</created_by>
    <created_at>2026-05-08T10:00:00</created_at>
  </user>
</identity_response>'''
    monkeypatch.setattr(identity_client, "_rpc_call", lambda rk, b: sample)
    result = identity_client.lookup_by_uuid("known-uuid")
    assert result is not None
    assert result["master_uuid"] == "known-uuid"


def test_lookup_by_uuid_not_found(monkeypatch):
    sample = '''<?xml version="1.0" encoding="UTF-8"?>
<identity_response>
  <status>error</status>
  <error_code>NOT_FOUND</error_code>
  <message>No user with that UUID</message>
</identity_response>'''
    monkeypatch.setattr(identity_client, "_rpc_call", lambda rk, b: sample)
    result = identity_client.lookup_by_uuid("ghost-uuid")
    assert result is None
