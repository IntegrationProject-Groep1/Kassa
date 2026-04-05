"""
Order Poller — Retrieves completed orders from Odoo POS
and sends them to RabbitMQ via sender.py
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

# Odoo POS payment method name (must match Odoo configuration exactly)
PAYMENT_METHOD_WALLET = "Badge Wallet"

# XSD enum values for refund_processed XML (per Datamapping_Kassa.md line 284)
XML_REFUND_METHOD_WALLET = "badge_wallet"
XML_REFUND_METHOD_CASH = "cash"

# Default fallback values for refund XML fields
DEFAULT_REFUND_METHOD = XML_REFUND_METHOD_CASH
DEFAULT_REFUND_REASON = "Processed via POS"


class OrderPoller:
    def __init__(self):
        """Initialize Odoo connection"""
        self.odoo_url = os.environ.get("ODOO_URL")
        self.odoo_db = os.environ.get("ODOO_DB")
        self.odoo_user = os.environ.get("ODOO_USER")
        self.odoo_pass = os.environ.get("ODOO_PASS")

        self.odoo_uid = None
        self.models = None
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
                self.models = xmlrpc.client.ServerProxy(
                    f'{self.odoo_url}/xmlrpc/2/object', allow_none=True)
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

            # Search for completed orders not yet sent to RabbitMQ
            order_ids = self.models.execute_kw(
                self.odoo_db, self.odoo_uid, self.odoo_pass,
                'pos.order', 'search',
                [[['state', 'in', ['paid', 'done']], ['x_rabbitmq_sent', '=', False]]]
            )

            if not order_ids:
                return []

            fields = [
                'id', 'name', 'partner_id', 'lines', 'amount_total',
                'amount_tax', 'payment_ids', 'create_date', 'session_id'
            ]
            try:
                # Try reading with x_wallet_updated
                orders = self.models.execute_kw(
                    self.odoo_db, self.odoo_uid, self.odoo_pass,
                    'pos.order', 'read',
                    [order_ids, fields + ['x_wallet_updated']])
            except xmlrpc.client.Fault:
                # Fallback if x_wallet_updated does not exist
                orders = self.models.execute_kw(
                    self.odoo_db, self.odoo_uid, self.odoo_pass,
                    'pos.order', 'read',
                    [order_ids, fields])

            return orders
        except Exception as e:
            logger.error(f"❌ Error fetching orders: {e}")
            return []

    def get_customer_info(self, partner_id):
        """Fetch customer details from Odoo"""
        if not partner_id:
            return None

        try:

            # partner_id is usually a tuple like (ID, name)
            if isinstance(partner_id, (list, tuple)):
                partner_id = partner_id[0]

            base_fields = ['id', 'name', 'email', 'phone', 'is_company', 'parent_id', 'x_wallet_balance']
            try:
                customer = self.models.execute_kw(
                    self.odoo_db, self.odoo_uid, self.odoo_pass, 'res.partner', 'read',
                    [partner_id, base_fields + ['x_user_id']])
            except Exception:
                # x_user_id is a custom field that may not exist yet in this Odoo instance
                logger.warning("⚠️  x_user_id field not found on res.partner — fetching without it")
                customer = self.models.execute_kw(
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

            if order.get('amount_total', 0) < 0:
                self._process_refund(order, order_id, customer_info)
            else:
                self._process_consumption(order, customer_info, is_anonymous)

            # Update in-memory cache immediately after send to suppress duplicates
            # within the same session even if the Odoo write below fails.
            self.processed_orders[order_id] = True
            if len(self.processed_orders) > MAX_CACHE_SIZE:
                self.processed_orders.popitem(last=False)

            # Persist sent status in Odoo — survives container restarts.
            # at-least-once: if this write fails the in-memory cache still
            # prevents a duplicate storm within the current session.
            self.models.execute_kw(
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

    def _process_refund(self, order, order_id, customer_info):
        """Handle refund logic and wallet updates"""
        # 1. Determine the payment method in Odoo via payment_ids
        payment_ids = order.get('payment_ids', [])
        is_badge_wallet = False
        refund_method = DEFAULT_REFUND_METHOD

        if payment_ids:
            payments = self.models.execute_kw(
                self.odoo_db, self.odoo_uid, self.odoo_pass,
                'pos.payment', 'read',
                [payment_ids, ['payment_method_id', 'amount']]
            )
            wallet_refund_amount = 0.0
            for pm in payments:
                method_tuple = pm.get('payment_method_id')
                if method_tuple and PAYMENT_METHOD_WALLET in method_tuple[1]:
                    is_badge_wallet = True
                    refund_method = XML_REFUND_METHOD_WALLET
                    wallet_refund_amount += abs(pm.get('amount', 0.0))

        # 2. Update wallet balance if necessary
        if is_badge_wallet and customer_info and not order.get('x_wallet_updated'):
            refund_amount_positive = wallet_refund_amount
            current_balance = customer_info.get('x_wallet_balance') or 0.0
            new_balance = round(float(current_balance) + refund_amount_positive, 2)

            self.models.execute_kw(
                self.odoo_db, self.odoo_uid, self.odoo_pass,
                'res.partner', 'write',
                [[customer_info['id']], {'x_wallet_balance': new_balance}]
            )

            try:
                self.models.execute_kw(
                    self.odoo_db, self.odoo_uid, self.odoo_pass,
                    'pos.order', 'write',
                    [[order_id], {'x_wallet_updated': True}]
                )
            except xmlrpc.client.Fault as e:
                logger.warning(f"⚠️  x_wallet_updated field might not exist on pos.order: {e}")

            wallet_xml = sender.build_wallet_balance_update_xml(
                user_id=customer_info.get('x_user_id'),
                new_balance=new_balance
            )
            sender.send_typed_message('wallet_balance_update', wallet_xml)
        # 3. Always send refund_processed XML
        original_msg_id = "Unknown"
        line_ids = [item[0] if isinstance(item, (list, tuple)) else item for item in order.get('lines', [])]

        if line_ids:
            try:
                refund_lines = self.models.execute_kw(
                    self.odoo_db, self.odoo_uid, self.odoo_pass,
                    'pos.order.line', 'read',
                    [line_ids, ['refunded_orderline_id']]
                )
                for r_line in refund_lines:
                    orig_line = r_line.get('refunded_orderline_id')
                    if orig_line:
                        orig_line_id = orig_line[0] if isinstance(orig_line, (list, tuple)) else orig_line
                        orig_line_data = self.models.execute_kw(
                            self.odoo_db, self.odoo_uid, self.odoo_pass,
                            'pos.order.line', 'read',
                            [[orig_line_id], ['order_id']]
                        )
                        if orig_line_data and orig_line_data[0].get('order_id'):
                            orig_order = orig_line_data[0]['order_id']
                            orig_order_id = orig_order[0] if isinstance(orig_order, (list, tuple)) else orig_order
                            # TODO: Replace ORDER-{id} with Master UUID once available project-wide.
                            # The correlation_id spec (Datamapping_Kassa.md §246) expects a UUID v4.
                            # For now we use the Odoo order ID as a stable, human-readable reference.
                            original_msg_id = f"ORDER-{orig_order_id}"
                            break
            except Exception as e:
                logger.warning(f"⚠️ Could not fetch original order ID for refund: {e}")

        logger.info(f"🔍 Refund order {order['id']} traced to: {original_msg_id}")
        refund_xml = sender.build_refund_processed_xml(
            original_payment_msg_id=original_msg_id,
            refund_type="POS_RETURN",
            refund_amount=abs(order['amount_total']),
            refund_method=refund_method,
            refund_reason=DEFAULT_REFUND_REASON,
            original_transaction_id=str(order['id']),
            user_id=customer_info.get('x_user_id') if customer_info else None
        )
        sender.send_typed_message('refund_processed', refund_xml)

    def _process_consumption(self, order, customer_info, is_anonymous):
        """Handle regular sales orders and dispatch consumption_order"""
        items = []
        # Extract all line IDs
        line_ids = [item[0] if isinstance(item, (list, tuple)) else item for item in order['lines']]

        if line_ids:
            line_details = self.models.execute_kw(
                self.odoo_db, self.odoo_uid, self.odoo_pass,
                'pos.order.line', 'read',
                [line_ids, ['id', 'product_id', 'qty', 'price_unit', 'tax_ids']]
            )
            # Pre-fetch all associated taxes in one bulk call
            all_tax_ids = list(set([tid for line in line_details for tid in line.get('tax_ids', [])]))
            tax_map = {}
            if all_tax_ids:
                tax_details = self.models.execute_kw(
                    self.odoo_db, self.odoo_uid, self.odoo_pass,
                    'account.tax', 'read',
                    [all_tax_ids, ['id', 'amount']]
                )
                tax_map = {t['id']: t['amount'] for t in tax_details}

            # Iterate through the pre-fetched lines
            for line in line_details:
                product_name = line['product_id'][1] if line['product_id'] else 'Unknown'

                vat_rate = 0
                tax_ids_for_line = line.get('tax_ids', [])
                if tax_ids_for_line:
                    # Use tax_map to find max amount
                    amounts = [tax_map.get(t_id, 0) for t_id in tax_ids_for_line]
                    if amounts:
                        vat_rate = int(max(amounts))

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
                parent_detail = self.models.execute_kw(
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
