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

## Local Odoo Customer Linking Flow

When a customer is created directly in Odoo/POS (e.g., by a kassamedewerker) with only an email address, the integration service automatically links them to the Identity Service.

- **Trigger:** A new `res.partner` record is created in Odoo with an email address but no `x_user_id`.
- **Flow:**
  1. The `PartnerIdentityPoller` detects the unlinked partner.
  2. It checks Odoo for any other partner with the same email that already has an `x_user_id` to reuse the link.
  3. If no local link exists, it calls `identity.user.create.request`.
  4. If the email already exists in Identity, it performs a lookup via `identity.user.lookup.email.request`.
  5. The returned `master_uuid` is stored in `res.partner.x_user_id`.
  6. No message is sent to CRM or other systems for this local-only flow.
- **Status Tracking:**
  - `res.partner.x_identity_status`: tracks the linking progress (`pending`, `linked`, `error`).
  - `res.partner.x_identity_last_sync`: timestamp of the last attempt.

## PartnerIdentityPoller — Runtime Component

`partner_identity_poller.py` runs as a **separate daemon thread** in the integration service, started by `main.py` alongside the receiver and order_poller threads.

**Class:** `PartnerIdentityPoller`

**Polling interval:** instelbaar via `IDENTITY_POLL_INTERVAL` environment variable (default: 10 seconden).

**Per cycle:**
1. Zoek partners met `email != False`, `x_user_id = False` en `x_identity_status != linked` (max 100 per cyclus).
2. Skip partners in `error`-state die korter dan `IDENTITY_ERROR_RETRY_AFTER` seconden (default: 3600) geleden gefaald hebben.
3. Valideer e-mailadres format via regex.
4. Check of een andere Odoo-partner met hetzelfde e-mailadres al een `x_user_id` heeft — zo ja: hergebruik.
5. Zo niet: roep `identity.user.create.request` aan.
6. Bij `EMAIL_ALREADY_EXISTS` (of `IdentityEmailAlreadyExists` exception): val terug op `identity.user.lookup.email.request`.
7. Sla `x_user_id` + `x_identity_status = linked` op in Odoo.
8. Bij `IdentityUnavailableError`: status = `pending` (silent retry volgende cyclus).
9. Bij andere fouten: status = `error`, details in `x_rabbitmq_error`.

**Identity Fallback in OrderPoller:**
Als een partner tijdens het verwerken van een order nog geen `x_user_id` heeft maar wel een e-mailadres, doet `order_poller.py` een last-resort `create_user` call via `identity_client.create_user()`. Dit is idempotent: het geeft de bestaande UUID terug als het e-mailadres al geregistreerd is. Na succes wordt de UUID teruggeschreven naar `res.partner.x_user_id`.

**Routing keys (configurable via env):**

| Variabele | Default routing key |
| --- | --- |
| `IDENTITY_ROUTING_KEY_CREATE` | `identity.user.create.request` |
| `IDENTITY_ROUTING_KEY_LOOKUP_EMAIL` | `identity.user.lookup.email.request` |
| `IDENTITY_ROUTING_KEY_LOOKUP_UUID` | `identity.user.lookup.uuid.request` |
