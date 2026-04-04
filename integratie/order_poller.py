"""
Order Poller — Haalt afgeronde bestellingen uit Odoo POS
en stuurt ze naar RabbitMQ via sender.py
"""

import xmlrpc.client
import os
import time
import logging
from pathlib import Path
import collections
import sender  # Import the sender module

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

MAX_CACHE_SIZE = 10_000
PAYMENT_METHOD_WALLET = "Badge Wallet"


class OrderPoller:
    def __init__(self):
        """Initialize Odoo connection"""
        self.odoo_url = os.environ.get("ODOO_URL")
        self.odoo_db = os.environ.get("ODOO_DB")
        self.odoo_user = os.environ.get("ODOO_USER")
        self.odoo_pass = os.environ.get("ODOO_PASS")

        self.odoo_uid = None
        self.processed_orders = collections.OrderedDict()

        # Outbox folder setup
        self.outbox_dir = Path(os.environ.get("OUTBOX_DIR", "outbox"))
        self.outbox_dir.mkdir(parents=True, exist_ok=True)

    def connect_odoo(self):
        """Authenticate with Odoo"""
        try:
            common = xmlrpc.client.ServerProxy(
                f'{self.odoo_url}/xmlrpc/2/common', allow_none=True)
            self.odoo_uid = common.authenticate(
                self.odoo_db, self.odoo_user, self.odoo_pass, {})

            if self.odoo_uid:
                logger.info("✅ Odoo connection established")
                return True
            else:
                logger.error("❌ Odoo authentication failed")
                return False
        except Exception as e:
            logger.error(f"❌ Odoo connection error: {e}")
            return False

    def get_pending_orders(self):
        """Fetch completed orders from Odoo POS that haven't been sent yet"""
        try:
            models = xmlrpc.client.ServerProxy(
                f'{self.odoo_url}/xmlrpc/2/object', allow_none=True)

            # Search for completed orders not yet sent to RabbitMQ
            order_ids = models.execute_kw(
                self.odoo_db, self.odoo_uid, self.odoo_pass,
                'pos.order', 'search',
                [[['state', 'in', ['paid', 'done']], ['x_rabbitmq_sent', '=', False]]]
            )

            if not order_ids:
                return []

            try:
                # Try reading with x_wallet_updated
                orders = models.execute_kw(self.odoo_db,
                                           self.odoo_uid,
                                           self.odoo_pass,
                                           'pos.order',
                                           'read',
                                           [order_ids,
                                            ['id',
                                             'name',
                                             'partner_id',
                                             'lines',
                                             'amount_total',
                                             'amount_tax',
                                             'payment_ids',
                                             'create_date',
                                             'session_id',
                                             'x_wallet_updated']])
            except Exception:
                # Fallback if x_wallet_updated does not exist
                orders = models.execute_kw(self.odoo_db,
                                           self.odoo_uid,
                                           self.odoo_pass,
                                           'pos.order',
                                           'read',
                                           [order_ids,
                                            ['id',
                                             'name',
                                             'partner_id',
                                             'lines',
                                             'amount_total',
                                             'amount_tax',
                                             'payment_ids',
                                             'create_date',
                                             'session_id']])

            return orders
        except Exception as e:
            logger.error(f"❌ Error fetching orders: {e}")
            return []

    def get_customer_info(self, partner_id):
        """Fetch customer details from Odoo"""
        if not partner_id:
            return None

        try:
            models = xmlrpc.client.ServerProxy(
                f'{self.odoo_url}/xmlrpc/2/object', allow_none=True)

            # partner_id is usually a tuple like (ID, name)
            if isinstance(partner_id, (list, tuple)):
                partner_id = partner_id[0]

            base_fields = ['id', 'name', 'email', 'phone', 'is_company', 'parent_id', 'x_wallet_balance']
            try:
                customer = models.execute_kw(
                    self.odoo_db, self.odoo_uid, self.odoo_pass, 'res.partner', 'read',
                    [partner_id, base_fields + ['x_user_id']])
            except Exception:
                # x_user_id is a custom field that may not exist yet in this Odoo instance
                logger.warning("⚠️  x_user_id field not found on res.partner — fetching without it")
                customer = models.execute_kw(
                    self.odoo_db, self.odoo_uid, self.odoo_pass, 'res.partner', 'read',
                    [partner_id, base_fields])

            return customer[0] if customer else None
        except Exception as e:
            logger.error(f"❌ Error fetching customer info: {e}")
            return None

    def process_order(self, order):
        """Process a single order: fetch details, build XML, send via sender"""
        order_id = order['id']

        # Skip if already processed
        if order_id in self.processed_orders:
            return False

        try:
            # Get customer info if linked
            customer_info = None
            is_anonymous = False

            if order['partner_id']:
                customer_info = self.get_customer_info(order['partner_id'])
                if not customer_info:
                    is_anonymous = True
            else:
                is_anonymous = True

            models = xmlrpc.client.ServerProxy(f'{self.odoo_url}/xmlrpc/2/object', allow_none=True)

            if order.get('amount_total', 0) < 0:
                # Het is een terugbetaling

                # 1. Bekijk de betalingsmethode in Odoo via payment_ids
                payment_ids = order.get('payment_ids', [])
                is_badge_wallet = False
                refund_method = "Cash/Card"

                if payment_ids:
                    payments = models.execute_kw(
                        self.odoo_db, self.odoo_uid, self.odoo_pass,
                        'pos.payment', 'read',
                        [payment_ids, ['payment_method_id', 'amount']]
                    )
                    wallet_refund_amount = 0.0
                    for pm in payments:
                        method_tuple = pm.get('payment_method_id')
                        if method_tuple and PAYMENT_METHOD_WALLET in method_tuple[1]:
                            is_badge_wallet = True
                            refund_method = PAYMENT_METHOD_WALLET
                            wallet_refund_amount += abs(pm.get('amount', 0.0))

                # 2. Update wallet balance if necessary
                if is_badge_wallet and customer_info and not order.get('x_wallet_updated'):
                    refund_amount_positive = wallet_refund_amount
                    current_balance = customer_info.get('x_wallet_balance') or 0.0
                    new_balance = float(current_balance) + refund_amount_positive

                    models.execute_kw(
                        self.odoo_db, self.odoo_uid, self.odoo_pass,
                        'res.partner', 'write',
                        [[customer_info['id']], {'x_wallet_balance': new_balance}]
                    )
                    
                    try:
                        models.execute_kw(
                            self.odoo_db, self.odoo_uid, self.odoo_pass,
                            'pos.order', 'write',
                            [[order_id], {'x_wallet_updated': True}]
                        )
                    except Exception as e:
                        logger.warning(f"⚠️  x_wallet_updated field might not exist on pos.order: {e}")

                    wallet_xml = sender.build_wallet_balance_update_xml(
                        user_id=customer_info.get('x_user_id'),
                        new_balance=new_balance
                    )
                    sender.send_typed_message('wallet_balance_update', wallet_xml)

                # 3. Always send refund_processed XML
                refund_xml = sender.build_refund_processed_xml(
                    original_payment_msg_id="Unknown",
                    refund_type="POS_RETURN",
                    refund_amount=abs(order['amount_total']),
                    refund_method=refund_method,
                    refund_reason="Verwerkt via Kassa",
                    original_transaction_id=str(order['id']),
                    user_id=customer_info.get('x_user_id') if customer_info else None
                )
                sender.send_typed_message('refund_processed', refund_xml)
            else:
                # Reguliere bestelling
                items = []
                for line_data in order['lines']:
                    if isinstance(line_data, (list, tuple)):
                        line_id = line_data[0]
                    else:
                        line_id = line_data

                    line_detail = models.execute_kw(
                        self.odoo_db, self.odoo_uid, self.odoo_pass,
                        'pos.order.line', 'read',
                        [line_id, ['id', 'product_id', 'qty', 'price_unit', 'tax_ids']]
                    )

                    if line_detail:
                        line = line_detail[0]
                        product_name = line['product_id'][1] if line['product_id'] else 'Unknown'

                        vat_rate = 0
                        tax_ids = line.get('tax_ids', [])
                        if tax_ids:
                            tax_details = models.execute_kw(
                                self.odoo_db, self.odoo_uid, self.odoo_pass,
                                'account.tax', 'read',
                                [tax_ids, ['amount']]
                            )
                            if tax_details:
                                vat_rate = int(max(t['amount'] for t in tax_details))

                        items.append({
                            'id': f"LINE-{line['id']}",
                            'sku': str(line['product_id'][0]),
                            'description': product_name,
                            'quantity': int(line['qty']),
                            'unit_price': float(line['price_unit']),
                            'total_amount': round(line['qty'] * line['price_unit'], 2),
                            'vat_rate': vat_rate,
                            'currency': 'eur'
                        })

                customer_type = "private"
                if customer_info:
                    if customer_info.get('is_company'):
                        customer_type = "company"
                    elif customer_info.get('parent_id'):
                        parent_id_val = customer_info['parent_id'][0]
                        parent_detail = models.execute_kw(
                            self.odoo_db, self.odoo_uid, self.odoo_pass,
                            'res.partner', 'read',
                            [parent_id_val, ['is_company']]
                        )
                        if parent_detail and parent_detail[0].get('is_company'):
                            customer_type = "company"

                # Build consumption_order XML using sender builder
                xml_message = sender.build_consumption_order_xml(
                    items=items,
                    customer_id=str(customer_info['id']) if customer_info else None,
                    user_id=str(customer_info.get('x_user_id')) if customer_info else None,
                    customer_type=customer_type,
                    email=customer_info.get('email', '') if customer_info else '',
                    is_anonymous=is_anonymous)

                # Send via sender module
                sender.send_typed_message('consumption_order', xml_message)

            # Update in-memory cache immediately after send to suppress duplicates
            # within the same session even if the Odoo write below fails.
            self.processed_orders[order_id] = True
            if len(self.processed_orders) > MAX_CACHE_SIZE:
                self.processed_orders.popitem(last=False)

            # Persist sent status in Odoo — survives container restarts.
            # at-least-once: if this write fails the in-memory cache still
            # prevents a duplicate storm within the current session.
            models.execute_kw(
                self.odoo_db, self.odoo_uid, self.odoo_pass,
                'pos.order', 'write',
                [[order_id], {'x_rabbitmq_sent': True}]
            )

            status_text = "ANONYMOUS" if is_anonymous else customer_info['name']
            logger.info(f"📦 Order {order_id}: {status_text}")
            return True

        except Exception as e:
            logger.error(f"❌ Error processing order {order_id}: {e}")
            return False

    def poll(self, interval=5):
        """Main polling loop"""
        logger.info(f"Order Poller started (interval: {interval}s)")
        reconnect_counter = 0
        reconnect_interval = 30

        while True:
            try:
                # Every 30 seconds try to flush outbox
                reconnect_counter += 1
                if reconnect_counter >= reconnect_interval / interval:
                    sender.flush_buffer()
                    reconnect_counter = 0

                # Get and process pending orders
                orders = self.get_pending_orders()

                for order in orders:
                    self.process_order(order)

                time.sleep(interval)

            except KeyboardInterrupt:
                logger.info("Order Poller stopped")
                break
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}")
                time.sleep(interval)


def main():
    poller = OrderPoller()

    if not poller.connect_odoo():
        logger.error("❌ Failed to connect to Odoo")
        return

    logger.info("🚀 Order Poller initialized successfully")
    poller.poll(interval=5)


if __name__ == "__main__":
    main()
