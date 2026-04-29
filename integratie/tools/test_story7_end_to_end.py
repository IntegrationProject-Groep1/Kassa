"""
End-to-End Test for Story 7: Invoice Request
Creates a real order with to_invoice=True and verifies the full flow
"""

import os
import sys
import time
import json
from datetime import datetime
from pathlib import Path

import defusedxml.xmlrpc
import xmlrpc.client  # nosec B411 - mitigated by monkey_patch below

defusedxml.xmlrpc.monkey_patch()  # Patch xmlrpc.client to use defusedxml

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def get_odoo_connection():
    """Authenticate with Odoo and return (models, uid, db, password)"""
    url = os.environ.get("ODOO_URL")
    db = os.environ.get("ODOO_DB")
    user = os.environ.get("ODOO_USER")
    password = os.environ.get("ODOO_PASS")

    common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common', allow_none=True)
    uid = common.authenticate(db, user, password, {})

    if not uid:
        print("❌ Authentication failed")
        return None, None, None, None

    models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object', allow_none=True)
    return models, uid, db, password


def create_test_customer(models, uid, db, password):
    """Create a test customer for invoice testing"""
    print("\n📝 Creating test customer...")

    # Fetch Belgium country ID dynamically
    try:
        country_ids = models.execute_kw(
            db, uid, password,
            'res.country', 'search',
            [[['code', '=', 'BE']]],
            {'limit': 1}
        )
        country_id = country_ids[0] if country_ids else 12  # Fallback to 12 if not found
    except Exception as e:
        print(f"⚠️  Could not fetch Belgium country ID: {e}, using fallback")
        country_id = 12

    customer_data = {
        'name': f"Test Customer {datetime.now().strftime('%H%M%S')}",
        'email': 'test.invoice@example.com',
        'phone': '0123456789',
        'street': 'Kiekenmarkt',
        'street2': '42',
        'zip': '1000',
        'city': 'Brussel',
        'country_id': country_id,  # Belgium (dynamically resolved)
        'vat': 'BE0123456789',
    }

    try:
        customer_id = models.execute_kw(
            db, uid, password,
            'res.partner', 'create',
            [customer_data]
        )
        print(f"✅ Customer created: ID {customer_id}")
        return customer_id
    except Exception as e:
        print(f"⚠️  Error creating customer: {e}")
        return False


def create_test_order_with_invoice(models, uid, db, password, customer_id):
    """Create a POS order with to_invoice=True"""
    print("\n📦 Creating POS order with to_invoice=True...")

    # Get active session
    session_ids = models.execute_kw(
        db, uid, password,
        'pos.session', 'search',
        [[['state', '=', 'opened']]]
    )

    if not session_ids:
        print("❌ No active POS session. Open a register first!")
        print("   Go to POS → Orders and click 'New Session'")
        return False

    session_id = session_ids[0]
    print(f"✅ Using session: {session_id}")

    # Get a product
    product_ids = models.execute_kw(
        db, uid, password,
        'product.product', 'search',
        [[['sale_ok', '=', True]]],
        {'limit': 1}
    )

    if not product_ids:
        print("❌ No products found")
        return False

    product_id = product_ids[0]

    # Create order
    order_data = {
        'session_id': session_id,
        'partner_id': customer_id,  # Linked to customer
        'name': f"INV-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        'date_order': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'amount_tax': 2.50,
        'amount_total': 12.50,
        'amount_paid': 12.50,
        'amount_return': 0.0,
        'to_invoice': True,  # ← STORY 7: Mark for invoicing
        'company_id': 1,
    }

    try:
        order_id = models.execute_kw(
            db, uid, password,
            'pos.order', 'create',
            [order_data]
        )
        print(f"✅ Order created: ID {order_id}")

        # Add order line
        line_data = {
            'order_id': order_id,
            'product_id': product_id,
            'qty': 1,
            'price_unit': 10.00,
            'price_subtotal': 10.00,
            'price_subtotal_incl': 12.50,
        }

        line_id = models.execute_kw(
            db, uid, password,
            'pos.order.line', 'create',
            [line_data]
        )
        print(f"✅ Added order line: {line_id}")

        # Mark as paid
        try:
            models.execute_kw(
                db, uid, password,
                'pos.order', 'action_pos_order_paid',
                [order_id]
            )
        except Exception:
            models.execute_kw(
                db, uid, password,
                'pos.order', 'write',
                [[order_id], {'state': 'paid'}]
            )

        print("✅ Order marked as PAID")
        return order_id

    except Exception as e:
        print(f"❌ Error creating order: {e}")
        return False


def verify_order_state(models, uid, db, password, order_id):
    """Check the order state before poller runs"""
    print(f"\n🔍 Checking order {order_id} state...")

    fields = ['id', 'name', 'state', 'to_invoice', 'x_rabbitmq_sent', 'partner_id']
    order = models.execute_kw(
        db, uid, password,
        'pos.order', 'read',
        [[order_id], fields]
    )

    if order:
        o = order[0]
        print(f"   📌 Order: {o['name']}")
        print(f"   👤 Customer: {o['partner_id']}")
        print(f"   💳 State: {o['state']}")
        print(f"   🧾 To Invoice: {o['to_invoice']}")
        print(f"   📡 RabbitMQ Sent: {o['x_rabbitmq_sent']}")
        return o
    return None


def run_poller():
    """Run the order poller to process the order"""
    print("\n🚀 Running order poller...")

    try:
        from order_poller import OrderPoller
        poller = OrderPoller()
        poller.run_once()
        print("✅ Poller executed")
        return True
    except Exception as e:
        print(f"❌ Poller error: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_invoice_message_sent(models, uid, db, password, order_id):
    """Check if invoice_request was sent"""
    print(f"\n📨 Checking if invoice_request was sent for order {order_id}...")

    fields = ['x_rabbitmq_sent']
    result = models.execute_kw(
        db, uid, password,
        'pos.order', 'read',
        [[order_id], fields]
    )

    if result and result[0]['x_rabbitmq_sent']:
        print("✅ x_rabbitmq_sent = True")
        return True
    else:
        print("⚠️  x_rabbitmq_sent = False (check logs for errors)")
        return False


def check_outbox_buffer():
    """Check if messages were buffered"""
    print("\n📂 Checking outbox buffer...")

    outbox_path = Path("/app/outbox/outbox.json")
    if outbox_path.exists():
        try:
            with open(outbox_path, 'r') as f:
                data = json.load(f)

            invoice_msgs = [msg for msg in data.get('messages', [])
                            if msg.get('message_type') == 'invoice_request']

            if invoice_msgs:
                print(f"✅ Found {len(invoice_msgs)} buffered invoice_request messages")
                for msg in invoice_msgs[:1]:  # Show first one
                    print(f"   - Order {msg.get('order_id')}: {msg.get('message_type')}")
                return True
            else:
                print("⚠️  No invoice_request messages in buffer")
                return False
        except Exception as e:
            print(f"⚠️  Error reading buffer: {e}")
            return False
    else:
        print("ℹ️  No outbox buffer (all messages sent successfully)")
        return False


def main():
    print("=" * 60)
    print("🧪 Story 7 - End-to-End Test: Invoice Request")
    print("=" * 60)

    # Connect to Odoo
    models, uid, db, password = get_odoo_connection()
    if not models:
        print("❌ Failed to connect to Odoo")
        return False

    print("✅ Connected to Odoo")

    # Create customer
    customer_id = create_test_customer(models, uid, db, password)
    if not customer_id:
        return False

    # Create order with to_invoice=True
    order_id = create_test_order_with_invoice(models, uid, db, password, customer_id)
    if not order_id:
        return False

    # Verify initial state
    before = verify_order_state(models, uid, db, password, order_id)

    # Run poller
    time.sleep(1)  # Small delay to ensure order is persisted
    run_poller()
    time.sleep(1)  # Give poller time to process

    # Verify after poller
    after = verify_order_state(models, uid, db, password, order_id)

    # Check for buffered messages
    check_outbox_buffer()

    print("\n" + "=" * 60)
    print("📊 TEST RESULTS")
    print("=" * 60)

    if before and before['to_invoice']:
        print("✅ Order has to_invoice=True")
    else:
        print("❌ Order missing to_invoice flag")

    if after and after['x_rabbitmq_sent']:
        print("✅ Order marked x_rabbitmq_sent=True (invoice sent!)")
        print("\n🎉 SUCCESS: Story 7 End-to-End Test PASSED")
        return True
    else:
        print("⚠️  Order NOT marked as sent (check logs for errors)")
        print("\n⚠️  INCONCLUSIVE: Check docker compose logs for details")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
