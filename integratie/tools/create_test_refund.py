import defusedxml.xmlrpc
defusedxml.xmlrpc.monkey_patch()  # Patch xmlrpc.client to use defusedxml
import xmlrpc.client  # nosec B411 - mitigated by monkey_patch above
import os
from datetime import datetime


def test_refund():
    url = os.environ.get("ODOO_URL", "http://localhost:8069")
    db = os.environ.get("ODOO_DB", "kassa-db")
    user = os.environ.get("ODOO_USER", "odoo")
    password = os.environ.get("ODOO_PASS", "myodoo")

    try:
        common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common', allow_none=True)
        uid = common.authenticate(db, user, password, {})
        models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object', allow_none=True)

        if not uid:
            print("❌ Authentication failed. Make sure kassa-web is running.")
            return

        # Find active POS session
        sessions = models.execute_kw(db, uid, password, 'pos.session', 'search', [[['state', '=', 'opened']]])
        if not sessions:
            print("❌ No active POS session found. Please open a POS register via the Odoo web interface first!")
            return

        session_id = sessions[0]

        # Find "Badge Wallet" payment method
        payment_methods = models.execute_kw(
            db, uid, password, 'pos.payment.method', 'search_read',
            [[['name', 'ilike', 'Badge Wallet']]], {'fields': ['id', 'name']}
        )

        if not payment_methods:
            print("⚠️ 'Badge Wallet' payment method not found. Using the first available method instead.")
            all_methods = models.execute_kw(db, uid, password, 'pos.payment.method', 'search', [[]])
            if not all_methods:
                print("❌ No payment methods currently exist. Add one in Odoo POS configuration.")
                return
            payment_method_id = all_methods[0]
        else:
            payment_method_id = payment_methods[0]['id']
            print(f"✅ Found Badge Wallet payment method: ID {payment_method_id}")

        # Find a test customer
        customers = models.execute_kw(db, uid, password, 'res.partner', 'search', [[]], {'limit': 1})
        partner_id = customers[0] if customers else False

        if partner_id:
            print(f"✅ Assigning order to Customer ID: {partner_id}")

        # Find a test product
        products = models.execute_kw(db, uid, password, 'product.product', 'search', [[]], {'limit': 1})
        if not products:
            print("❌ No products found in Odoo.")
            return
        product_id = products[0]

        print("🔄 Creating negative order (refund)...")
        # Create the NEGATIVE order header
        order_data = {
            'session_id': session_id,
            'partner_id': partner_id,
            'name': f"REFUND-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            'amount_tax': 0.0,
            'amount_total': -15.00,  # Negative amount!
            'amount_paid': -15.00,
            'amount_return': 0.0,
        }
        order_id = models.execute_kw(db, uid, password, 'pos.order', 'create', [order_data])

        # Create the negative order line
        models.execute_kw(db, uid, password, 'pos.order.line', 'create', [{
            'order_id': order_id,
            'product_id': product_id,
            'qty': -1,
            'price_unit': 15.00,
            'price_subtotal': -15.00,
            'price_subtotal_incl': -15.00,
        }])

        # Create the payment line to link it to the "Badge Wallet" (essential for testing our new logic)
        models.execute_kw(db, uid, password, 'pos.payment', 'create', [{
            'pos_order_id': order_id,
            'payment_method_id': payment_method_id,
            'amount': -15.00,
        }])

        # Mark as paid
        models.execute_kw(db, uid, password, 'pos.order', 'write', [[order_id], {'state': 'paid'}])

        print(f"✅ Refund order {order_id} marked as PAID!")
        print("✅ The Order Poller should detect it shortly and send the RabbitMQ messages.")
        print("   Check logs with: docker compose logs -f kassa-integratie")

    except Exception as e:
        print(f"❌ Error occurred: {e}")


if __name__ == "__main__":
    test_refund()
