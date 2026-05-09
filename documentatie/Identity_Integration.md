**Identity Service Integration**

- Queues / routing keys:
  - identity.user.create.request — request to create or claim an identity
  - identity.user.lookup.email.request — lookup by email
  - identity.user.lookup.uuid.request — lookup by master_uuid

- Identity RPC format (flat XML request — no <message><header><body> envelope):

Request (create):

```xml
<?xml version="1.0"?>
<identity_request>
  <email>user@example.com</email>
  <source_system>frontend</source_system>
</identity_request>
```

Successful response:

```xml
<identity_response>
  <status>ok</status>
  <user>
    <master_uuid>...</master_uuid>
    <email>user@example.com</email>
    <created_by>frontend</created_by>
    <created_at>2026-04-24T09:15:00Z</created_at>
  </user>
</identity_response>
```

Error example:

```xml
<identity_response>
  <status>error</status>
  <error_code>EMAIL_ALREADY_EXISTS</error_code>
  <message>Een gebruiker met dit e-mailadres bestaat al. Gebruik lookup endpoint.</message>
</identity_response>
```

Other known error codes: `CREATE_FAILED`, `LOOKUP_FAILED`, `NOT_FOUND`.
Note: the current identity service implementation is idempotent for create — duplicate emails
return status=ok with the existing master_uuid. EMAIL_ALREADY_EXISTS is in the contract (§15.4)
and handled defensively, but may not be returned by the current service version.

- Caller rules:
  - Call Identity RPC (create) before sending `new_registration` to CRM.
  - Validate `correlation_id` on replies; use `reply_to`, `correlation_id`, `message_id`, and `timestamp` AMQP properties.
  - Retry RPC 3 times with exponential backoff; if unavailable, Frontend must show an error and CRM should park the message.
  - Do not generate temporary/local UUIDs as fallback.

- Mapping:
  - `master_uuid` from Identity is the canonical user identifier across services.
  - In Kassa/Odoo we store it as `res.partner.x_user_id`.
