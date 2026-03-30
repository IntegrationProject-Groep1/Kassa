"""
order_poller.py — Polls Odoo POS for completed orders and publishes them to RabbitMQ.

Runs in a background thread started by main.py. Every `interval` seconds
(default: 5) it fetches all POS orders in state 'paid' or 'done' and sends
each one as a consumption_order XML message via sender.send_typed_message().

Duplicate prevention:
    A module-level OrderedDict (processed_orders) tracks every order ID that
    has been sent in this session. Orders already in the dict are skipped.
    The dict is capped at 10,000 entries (LRU eviction) to prevent unbounded
    memory growth in long-running deployments.

Anonymous vs named customers:
    If the POS order has no linked partner (partner_id is False/None) the order
    is treated as anonymous. If a partner is linked but get_customer_info()
    fails to fetch it, the order also falls back to anonymous rather than
    failing entirely.

Company detection:
    A customer is considered company-linked if:
      1. Their own res.partner record has is_company=True, OR
      2. They have a parent_id whose res.partner record has is_company=True
         (i.e. they are a contact under a company account).
    The second check requires an extra Odoo read — see process_order().

Offline resilience:
    Sending goes through sender.send_message(), which writes to outbox.json
    if the broker is unreachable. flush_buffer() is called every 30 seconds
    inside the polling loop to replay any buffered messages.
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


class OrderPoller:
    def __init__(self):
        """
        Read Odoo credentials from the environment and prepare internal state.

        processed_orders is an OrderedDict used as a bounded set: values are
        always True, the key is the Odoo order ID. OrderedDict preserves
        insertion order which makes the LRU eviction in process_order()
        deterministic (oldest entry removed first).
        """
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
        """
        Authenticate against the Odoo XML-RPC endpoint and store the uid.

        Returns True on success, False if authentication fails or the server
        is unreachable. The caller (main.py) exits if this returns False.
        """
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
        """
        Return all POS orders in state 'paid' or 'done' from Odoo.

        'Pending' here means not yet processed by this poller session, not a
        separate Odoo field. Filtering against processed_orders happens in
        process_order(), not here, so this query always returns the full set.
        """
        try:
            models = xmlrpc.client.ServerProxy(
                f'{self.odoo_url}/xmlrpc/2/object', allow_none=True)

            # Search for completed orders (paid or done)
            order_ids = models.execute_kw(
                self.odoo_db, self.odoo_uid, self.odoo_pass,
                'pos.order', 'search',
                [[['state', 'in', ['paid', 'done']]]]
            )

            if not order_ids:
                return []

            # Read order details
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
                                         'create_date',
                                         'session_id']])

            return orders
        except Exception as e:
            logger.error(f"❌ Error fetching orders: {e}")
            return []

    def get_customer_info(self, partner_id):
        """
        Fetch a res.partner record from Odoo and return it as a dict.

        partner_id can be either a plain integer or the (id, display_name)
        tuple that Odoo XML-RPC returns for many2one fields — both forms are
        handled. Returns None if the partner cannot be fetched.
        """
        if not partner_id:
            return None

        try:
            models = xmlrpc.client.ServerProxy(
                f'{self.odoo_url}/xmlrpc/2/object', allow_none=True)

            # Odoo XML-RPC returns many2one fields as [id, "Display Name"]
            if isinstance(partner_id, (list, tuple)):
                partner_id = partner_id[0]

            customer = models.execute_kw(
                self.odoo_db, self.odoo_uid, self.odoo_pass, 'res.partner', 'read', [
                    partner_id, [
                        'id', 'name', 'email', 'phone', 'is_company', 'parent_id', 'x_user_id']])

            return customer[0] if customer else None
        except Exception as e:
            logger.error(f"❌ Error fetching customer info: {e}")
            return None

    def process_order(self, order):
        """
        Build and send the consumption_order message for one POS order.

        Returns True if the order was sent (or skipped as a duplicate),
        False if an exception prevented processing.

        Steps:
          1. Check processed_orders — skip if already sent this session.
          2. Resolve the linked partner (anonymous if none or lookup fails).
          3. Read each order line to get product name, quantity, and VAT rate.
          4. Determine company linkage (see company detection note below).
          5. Build the XML and send via sender.send_typed_message().
          6. Record order_id in processed_orders.
        """
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

            # Build items list from order lines
            models = xmlrpc.client.ServerProxy(
                f'{self.odoo_url}/xmlrpc/2/object', allow_none=True)

            items = []
            for line_data in order['lines']:
                # line_data is typically a tuple/list: (line_id,) or just the
                # id
                if isinstance(line_data, (list, tuple)):
                    line_id = line_data[0]
                else:
                    line_id = line_data

                # Fetch line details
                line_detail = models.execute_kw(
                    self.odoo_db, self.odoo_uid, self.odoo_pass,
                    'pos.order.line', 'read',
                    [line_id, ['product_id', 'qty', 'price_unit', 'tax_ids']]
                )

                if line_detail:
                    line = line_detail[0]
                    product_name = line['product_id'][1] if line['product_id'] else 'Unknown'

                    # Fetch tax details
                    vat_rate = 0.0
                    tax_ids = line.get('tax_ids', [])
                    if tax_ids:
                        tax_details = models.execute_kw(
                            self.odoo_db, self.odoo_uid, self.odoo_pass,
                            'account.tax', 'read',
                            [tax_ids, ['amount']]
                        )
                        if tax_details:
                            # Use the highest tax rate or the first one
                            vat_rate = max(t['amount']
                                           for t in tax_details) / 100.0

                    items.append({
                        'id': str(line_id),
                        'description': product_name,
                        'quantity': int(line['qty']),
                        'unit_price': float(line['price_unit']),
                        'vat_rate': float(vat_rate),
                        'currency': 'eur'
                    })

            # Determine company linkage.
            # Odoo models individual contacts under their employer using
            # parent_id. A customer is company-linked if:
            #   a) Their own record is a company (is_company=True), OR
            #   b) They have a parent_id and that parent is a company.
            # Case (b) requires an extra read because the XML-RPC many2one
            # field only gives us the parent ID and name, not is_company.
            is_company_linked = False
            company_id = None
            if customer_info:
                if customer_info.get('is_company'):
                    # The customer record itself is the company
                    is_company_linked = True
                    company_id = str(customer_info['id'])
                elif customer_info.get('parent_id'):
                    # Customer is a contact under a potential parent company;
                    # fetch the parent to confirm it is marked as a company
                    parent_id_val = customer_info['parent_id'][0]
                    parent_detail = models.execute_kw(
                        self.odoo_db, self.odoo_uid, self.odoo_pass,
                        'res.partner', 'read',
                        [parent_id_val, ['is_company']]
                    )
                    if parent_detail and parent_detail[0].get('is_company'):
                        is_company_linked = True
                        company_id = str(parent_id_val)

            # Build consumption_order XML using sender builder
            xml_message = sender.build_consumption_order_xml(
                items=items,
                customer_id=str(
                    customer_info['id']) if customer_info else None,
                user_id=str(
                    customer_info.get('x_user_id')) if customer_info else None,
                is_company_linked=is_company_linked,
                company_id=company_id,
                email=customer_info.get(
                    'email',
                    '') if customer_info else '',
                is_anonymous=is_anonymous)

            # Send via sender module (automatically handles RabbitMQ + outbox
            # fallback)
            sender.send_typed_message('consumption_order', xml_message)

            # Mark as processed so this order is skipped on the next poll cycle
            self.processed_orders[order_id] = True
            # Keep the dict bounded: evict the oldest entry once we exceed 10,000
            if len(self.processed_orders) > 10000:
                self.processed_orders.popitem(last=False)

            status_text = "ANONYMOUS" if is_anonymous else customer_info['name']
            logger.info(f"📦 Order {order_id}: {status_text}")
            return True

        except Exception as e:
            logger.error(f"❌ Error processing order {order_id}: {e}")
            return False

    def poll(self, interval=5):
        """
        Run the polling loop indefinitely, sleeping `interval` seconds between cycles.

        flush_buffer() is called every 30 seconds (reconnect_interval) rather
        than every cycle to avoid hammering the broker with reconnect attempts
        when it is down. The counter resets after each flush.
        """
        logger.info(f"Order Poller started (interval: {interval}s)")
        reconnect_counter = 0
        reconnect_interval = 30

        while True:
            try:
                # Flush the outbox buffer roughly every 30 seconds
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
