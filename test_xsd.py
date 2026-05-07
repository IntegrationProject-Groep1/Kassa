import sys
import uuid
sys.path.insert(0, 'integratie')
from receiver import validate_xml

TEST_ID = 'abcdef12'
TEST_USER_ID = str(uuid.uuid4())

header = f"""<header>
    <message_id>{str(uuid.uuid4())}</message_id>
    <timestamp>2026-03-31T10:00:00Z</timestamp>
    <source>crm</source>
    <type>new_registration</type>
    <version>2.0</version>
    <correlation_id>{str(uuid.uuid4())}</correlation_id>
  </header>"""

xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<message>
  {header}
  <body>
    <customer>
      <identity_uuid>{TEST_USER_ID}</identity_uuid>
      <email>test@{TEST_ID}.be</email>
      <date_of_birth>1990-01-01</date_of_birth>
      <contact>
        <first_name>Test</first_name>
        <last_name>User</last_name>
      </contact>
      <type>private</type>
      <session_id>sess-001</session_id>
      <payment_due>
        <amount currency="eur">10.00</amount>
        <status>unpaid</status>
      </payment_due>
    </customer>
  </body>
</message>"""

try:
    validate_xml(xml, 'new_registration')
    print('VALID')
except Exception as e:
    print('INVALID:', e)
