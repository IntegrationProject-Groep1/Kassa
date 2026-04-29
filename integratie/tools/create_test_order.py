"""
Test Order Creator — Maakt een test order in Odoo POS
"""

import xmlrpc.client  # nosec
import os
from datetime import datetime


def create_test_order():
    url = os.environ.get("ODOO_URL")
    db = os.environ.get("ODOO_DB")
    user = os.environ.get("ODOO_USER")
    password = os.environ.get("ODOO_PASS")

    try:
        # Authenticate
        common = xmlrpc.client.ServerProxy(
            f'{url}/xmlrpc/2/common', allow_none=True)
        uid = common.authenticate(db, user, password, {})

        if not uid:
            print("❌ Authentication failed")
            return False

        models = xmlrpc.client.ServerProxy(
            f'{url}/xmlrpc/2/object', allow_none=True)

        # Get the first POS session
        session_ids = models.execute_kw(
            db, uid, password,
            'pos.session', 'search',
            [[['state', '=', 'opened']]]
        )

        if not session_ids:
            print("❌ No active POS session found. Open a register first!")
            return False

        session_id = session_ids[0]
        print(f"✅ Found active session: {session_id}")

        # Get available products
        product_ids = models.execute_kw(
            db, uid, password,
            'product.product', 'search',
            [[]],
            {'limit': 1}
        )

        if not product_ids:
            print("❌ No products found")
            return False

        product_id = product_ids[0]
        print(f"✅ Found product: {product_id}")

        # Create order with all required fields
        order_data = {
            'session_id': session_id,
            'partner_id': False,  # Anonymous order
            'name': f"TEST-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            'date_order': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'amount_tax': 0.0,
            'amount_total': 10.00,
            'amount_paid': 10.00,  # Required: amount already paid
            'amount_return': 0.0,
            # Default company configurable
            'company_id': int(os.environ.get('ODOO_COMPANY_ID', 1)),
        }

        order_id = models.execute_kw(
            db, uid, password,
            'pos.order', 'create',
            [order_data]
        )

        print(f"✅ Created order: {order_id}")

        # Add order line
        line_data = {
            'order_id': order_id,
            'product_id': product_id,
            'qty': 1,
            'price_unit': 10.00,
            'price_subtotal': 10.00,
            'price_subtotal_incl': 10.00,  # Include tax
        }

        line_id = models.execute_kw(
            db, uid, password,
            'pos.order.line', 'create',
            [line_data]
        )

        print(f"✅ Added order line: {line_id}")

        # Mark order as paid using the action method
        try:
            models.execute_kw(
                db, uid, password,
                'pos.order', 'action_pos_order_paid',
                [order_id]
            )
        except Exception as e:
            print(
                f"⚠️  'action_pos_order_paid' failed: {e}. Falling back to direct write.")
            # Fallback: write the status directly
            models.execute_kw(
                db, uid, password,
                'pos.order', 'write',
                [order_id],
                {'state': 'paid'}
            )

        print("✅ Order marked as PAID!")
        print("\n🎉 Test order created successfully!")
        print(f"   Order ID: {order_id}")
        print("   Status: PAID")
        print("   Customer: ANONYMOUS")
        print("\n📡 Order Poller should pick this up in 5 seconds...")
        print("   Check logs: docker-compose logs -f kassa-integratie")

        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        return False


if __name__ == "__main__":
    create_test_order()
