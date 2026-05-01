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

Feedback Loop (Best Practice):
    If a message fails strict XSD validation, the error is written back to Odoo
    in the `x_rabbitmq_error` field. The poller skips orders with errors to
    prevent infinite retry loops on broken data.

Offline resilience:
    Sending goes through sender.send_message(), which writes to outbox.json
    if the broker is unreachable. flush_buffer() is called every 30 seconds
    inside the polling loop to replay any queued messages in order.
"""

import xmlrpc.client  # nosec
import defusedxml.xmlrpc
import os
import time
import logging
from pathlib import Path
import collections
import defusedxml.ElementTree as ET
import uuid
import sender  # Import the sender module
from config_utils import get_env

defusedxml.xmlrpc.monkey_patch()

# Module-level logger
logger = logging.getLogger(__name__)

MAX_CACHE_SIZE = 10_000

# Odoo POS payment method name
PAYMENT_METHOD_WALLET = "Badge Wallet"

# XSD enum values for refund_processed XML
XML_REFUND_METHOD_WALLET = "badge_wallet"
XML_REFUND_METHOD_CASH = "cash"

# Default fallback values for refund XML fields
DEFAULT_REFUND_METHOD = XML_REFUND_METHOD_CASH
DEFAULT_REFUND_REASON = "customer_request"


class OrderPoller:
    def __init__(self):
        """Read Odoo credentials from the environment and prepare internal state."""
        self.odoo_url = get_env("ODOO_URL")
        self.odoo_db = get_env("ODOO_DB")
        self.odoo_user = get_env("ODOO_USER")
        self.odoo_pass = get_env("ODOO_PASS")

        self.odoo_uid = None
        self.models = None
        self.processed_orders = collections.OrderedDict()

        # Outbox folder setup
        self.outbox_dir = Path(os.environ.get("OUTBOX_DIR", "outbox"))
        self.outbox_dir.mkdir(parents=True, exist_ok=True)

    def connect_odoo(self):
        """Authenticate against Odoo."""
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
        """Fetch orders in state 'paid'/'done' that haven't been sent or errored."""
        try:
            buffered_ids = sender.get_buffered_record_ids(model="pos.order")
            logger.info(f"🔍 Polling for orders. Buffered IDs: {buffered_ids}")

            # Search for completed orders not yet sent and not marked with errors
            order_ids = self.models.execute_kw(
                self.odoo_db, self.odoo_uid, self.odoo_pass,
                'pos.order', 'search',
                [[['state', 'in', ['paid', 'done']],
                  ['x_rabbitmq_sent', '=', False],
                  ['x_rabbitmq_error', 'in', [False, '']]]]
            )
            logger.info(f"🔍 Found raw order IDs: {order_ids}")

            if buffered_ids:
                order_ids = [oid for oid in order_ids if oid not in buffered_ids]
                logger.info(f"🔍 Filtered order IDs: {order_ids}")

            if not order_ids:
                return []

            fields = [
                'id', 'name', 'partner_id', 'lines', 'amount_total',
                'amount_tax', 'payment_ids', 'create_date', 'session_id', 'account_move'
            ]
            try:
                # Attempt to read all integration fields
                orders = self.models.execute_kw(
                    self.odoo_db, self.odoo_uid, self.odoo_pass,
                    'pos.order', 'read',
                    [order_ids, fields + ['x_wallet_updated', 'x_payment_message_id', 'x_rabbitmq_error']])
            except xmlrpc.client.Fault:
                # Fallback if custom fields are missing
                orders = self.models.execute_kw(
                    self.odoo_db, self.odoo_uid, self.odoo_pass,
                    'pos.order', 'read',
                    [order_ids, fields])

            return orders
        except Exception as e:
            logger.error(f"❌ Error fetching orders: {e}")
            return []

    def get_customer_info(self, partner_id, country_map=None):
        """Fetch customer data from Odoo, including parent company info if needed."""
        if not partner_id:
            return None

        try:
            if isinstance(partner_id, (list, tuple)):
                partner_id = partner_id[0]

            base_fields = [
                'id', 'name', 'email', 'phone', 'is_company', 'parent_id',
                'x_wallet_balance', 'vat', 'street', 'city', 'zip', 'country_id'
            ]
            try:
                # Attempt to read all integration fields
                customer = self.models.execute_kw(
                    self.odoo_db, self.odoo_uid, self.odoo_pass, 'res.partner', 'read',
                    [partner_id, base_fields + ['x_user_id']])
            except Exception:
                logger.warning("⚠️  x_user_id field not found on res.partner")
                customer = self.models.execute_kw(
                    self.odoo_db, self.odoo_uid, self.odoo_pass, 'res.partner', 'read',
                    [partner_id, base_fields])

            if not customer:
                return None

            info = customer[0]
            # Determine customer type (private vs company)
            # A partner is 'company' if is_company=True OR if they have a parent that is a company
            if info.get('country_id'):
                country_id = info['country_id'][0]
                if country_map and country_id in country_map:
                    info['country_code'] = country_map[country_id]
                else:
                    try:
                        country_data = self.models.execute_kw(
                            self.odoo_db, self.odoo_uid, self.odoo_pass,
                            'res.country', 'read',
                            [[country_id], ['code']]
                        )
                        info['country_code'] = country_data[0].get('code', '').lower() if country_data else ""
                    except Exception as e:
                        logger.warning(f"⚠️ Could not fetch country code: {str(e)}")
                        info['country_code'] = ""
            else:
                info['country_code'] = ""

            info['customer_type'] = "private"
            if info.get('is_company'):
                info['customer_type'] = "company"
            elif info.get('parent_id'):
                # REUSE existing method for parent lookup to keep logic consistent
                parent_data = self.get_customer_info(info['parent_id'], country_map=country_map)
                if parent_data and parent_data.get('is_company'):
                    info['customer_type'] = "company"
                    # Use parent's country if child has none
                    if not info.get('country_code') and parent_data.get('country_code'):
                        info['country_code'] = parent_data['country_code']

            return info
        except Exception as e:
            logger.error(f"❌ Error fetching customer info: {e}")
            return None

    def is_topup_product(self, product_id: int, product_info_map: dict) -> bool:
        """
        Identify if a product is a Top-up based on the x_is_topup flag or POS category.
        Reuses the pre-fetched product_info_map for efficiency.
        """
        if not product_id:
            return False

        p = product_info_map.get(product_id, {})
        # Primary check: custom x_is_topup flag
        if p.get('x_is_topup'):
            return True

        # Fallback: POS category check (if 'Top-ups' is in the category IDs)
        # Note: In production we'd lookup the actual name, but x_is_topup is the preferred method.
        pos_categ_ids = p.get('pos_categ_ids', [])
        if pos_categ_ids:
            try:
                categories = self.models.execute_kw(
                    self.odoo_db, self.odoo_uid, self.odoo_pass,
                    'pos.category', 'read',
                    [pos_categ_ids, ['name']]
                )
                for cat in categories:
                    if cat.get('name') == 'Top-ups':
                        return True
            except Exception as e:
                logger.warning(f"⚠️ Could not fetch POS category names for product {product_id}: {e}")

        return False

    def process_order(self, order, country_map=None):
        """Process a single POS order and send as consumption_order."""
        order_id = order['id']

        if order_id in self.processed_orders:
            return False

        # Local cache for this polling cycle to optimize parent partner lookups
        self._customer_cache = {}

        try:
            customer_info = None
            is_anonymous = False

            if order['partner_id']:
                customer_info = self.get_customer_info(order['partner_id'], country_map=country_map)
                if not customer_info:
                    is_anonymous = True
            else:
                is_anonymous = True

            if order.get('amount_total', 0) < 0:
                all_sent = self._process_refund(order, order_id, customer_info, is_anonymous)
                payment_msg_id = None
            else:
                all_sent, payment_msg_id = self._process_consumption(order, customer_info, is_anonymous)

            self.processed_orders[order_id] = True
            if len(self.processed_orders) > MAX_CACHE_SIZE:
                self.processed_orders.popitem(last=False)

            if payment_msg_id:
                try:
                    self.models.execute_kw(
                        self.odoo_db, self.odoo_uid, self.odoo_pass,
                        'pos.order', 'write',
                        [[order_id], {'x_payment_message_id': payment_msg_id}]
                    )
                except Exception as e:
                    logger.warning(f"⚠️ Could not set x_payment_message_id on order: {e}")

            if all_sent:
                self.models.execute_kw(
                    self.odoo_db, self.odoo_uid, self.odoo_pass,
                    'pos.order', 'write',
                    [[order_id], {'x_rabbitmq_sent': True}]
                )
                status_text = "ANONYMOUS" if is_anonymous else customer_info['name']
                logger.info(f"📦 Order {order_id}: {status_text} (SENT)")
            else:
                logger.info(f"📁 Order {order_id} buffered")

            return True

        except sender.XSDValidationError as e:
            logger.error(f"❌ Contract violation in order {order_id}: {e}")
            try:
                self.models.execute_kw(
                    self.odoo_db, self.odoo_uid, self.odoo_pass,
                    'pos.order', 'write',
                    [[order_id], {
                        'x_rabbitmq_error': "Data validation failed (XSD). Check integration logs for details."
                    }]
                )
            except Exception as rpc_err:
                logger.error(f"Could not write error back to Odoo: {rpc_err}")
            return False

        except Exception as e:
            logger.error(f"❌ Error processing order {order_id}: {e}")
            return False
        finally:
            self._customer_cache = {}

    def _get_wallet_payment_amount(self, payment_ids) -> tuple[bool, float]:
        """Determine if a wallet was used and the amount."""
        if not payment_ids:
            return False, 0.0

        payments = self.models.execute_kw(
            self.odoo_db, self.odoo_uid, self.odoo_pass,
            'pos.payment', 'read',
            [payment_ids, ['payment_method_id', 'amount']]
        )
        is_badge_wallet = False
        wallet_amount = 0.0
        for pm in payments:
            method_tuple = pm.get('payment_method_id')
            if method_tuple and PAYMENT_METHOD_WALLET in method_tuple[1]:
                is_badge_wallet = True
                wallet_amount += abs(pm.get('amount', 0.0))

        return is_badge_wallet, wallet_amount

    def _process_refund(self, order, order_id, customer_info, is_anonymous) -> bool:
        """Handle refund logic."""
        payment_ids = order.get('payment_ids', [])
        is_badge_wallet, wallet_refund_amount = self._get_wallet_payment_amount(payment_ids)
        refund_method = XML_REFUND_METHOD_WALLET if is_badge_wallet else DEFAULT_REFUND_METHOD
        ok_wallet = True

        if is_badge_wallet and customer_info and not order.get('x_wallet_updated'):
            current_balance = customer_info.get('x_wallet_balance') or 0.0
            new_balance = round(float(current_balance) + wallet_refund_amount, 2)

            self.models.execute_kw(
                self.odoo_db, self.odoo_uid, self.odoo_pass,
                'res.partner', 'write',
                [[customer_info['id']], {'x_wallet_balance': new_balance}]
            )
            self.models.execute_kw(
                self.odoo_db, self.odoo_uid, self.odoo_pass,
                'pos.order', 'write',
                [[order_id], {'x_wallet_updated': True}]
            )

            wallet_xml = sender.build_wallet_balance_update_xml(
                user_id=customer_info.get('x_user_id'),
                new_balance=new_balance
            )
            ok_wallet = sender.send_typed_message('wallet_balance_update', wallet_xml, record_id=order_id)

        original_msg_id = str(uuid.uuid4())
        line_ids = [item[0] if isinstance(
            item, (list, tuple)) else item for item in order.get('lines', [])]

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
                        orig_line_id = orig_line[0] if isinstance(
                            orig_line, (list, tuple)) else orig_line
                        orig_line_data = self.models.execute_kw(
                            self.odoo_db, self.odoo_uid, self.odoo_pass,
                            'pos.order.line', 'read',
                            [[orig_line_id], ['order_id']]
                        )
                        if orig_line_data and orig_line_data[0].get('order_id'):
                            orig_order = orig_line_data[0]['order_id']
                            orig_order_id = orig_order[0] if isinstance(
                                orig_order, (list, tuple)) else orig_order

                            # Fetch x_payment_message_id from the original order
                            orig_order_full = self.models.execute_kw(
                                self.odoo_db, self.odoo_uid, self.odoo_pass,
                                'pos.order', 'read',
                                [[orig_order_id], ['x_payment_message_id']]
                            )
                            if orig_order_full and orig_order_full[0].get('x_payment_message_id'):
                                original_msg_id = orig_order_full[0]['x_payment_message_id']
                            break
            except Exception as e:
                logger.error(
                    f"❌ CRITICAL: Could not trace refund to original order for traceability (Order {order_id}): {e}"
                )

        refund_xml = sender.build_refund_processed_xml(
            original_payment_msg_id=original_msg_id,
            refund_type="consumption_item",
            refund_amount=abs(order['amount_total']),
            refund_method=refund_method,
            refund_reason=DEFAULT_REFUND_REASON,
            original_transaction_id=str(order['id']),
            user_id=customer_info.get('x_user_id') if customer_info else None,
            is_anonymous=is_anonymous
        )
        ok_refund = sender.send_typed_message('refund_processed', refund_xml, record_id=order_id)
        return ok_wallet and ok_refund

    def _process_consumption(self, order, customer_info, is_anonymous) -> tuple[bool, str | None]:
        """Handle regular sales orders."""
        items = []
        line_ids = [item[0] if isinstance(item, (list, tuple)) else item for item in (order.get('lines') or [])]

        if line_ids:
            line_details = self.models.execute_kw(
                self.odoo_db, self.odoo_uid, self.odoo_pass,
                'pos.order.line', 'read',
                [line_ids, ['id', 'product_id', 'qty', 'price_unit', 'tax_ids', 'price_subtotal_incl']]
            )

            # Bulk fetch product details
            product_ids = list(set([line['product_id'][0] for line in line_details]))
            product_info_map = {}
            all_cat_ids = set()
            if product_ids:
                products = self.models.execute_kw(
                    self.odoo_db, self.odoo_uid, self.odoo_pass,
                    'product.product', 'read',
                    [product_ids, ['id', 'x_is_topup', 'pos_categ_ids']]
                )
                product_info_map = {p['id']: p for p in products}
                for p in products:
                    all_cat_ids.update(p.get('pos_categ_ids', []))

            # Pre-fetch category names
            cat_map = {}
            if all_cat_ids:
                categories = self.models.execute_kw(
                    self.odoo_db, self.odoo_uid, self.odoo_pass,
                    'pos.category', 'read',
                    [list(all_cat_ids), ['id', 'name']]
                )
                cat_map = {c['id']: c['name'] for c in categories}

            all_tax_ids = list(set([tid for line in line_details for tid in (line.get('tax_ids') or [])]))
            tax_map = {}
            if all_tax_ids:
                tax_details = self.models.execute_kw(
                    self.odoo_db, self.odoo_uid, self.odoo_pass,
                    'account.tax', 'read',
                    [all_tax_ids, ['id', 'amount']]
                )
                tax_map = {t['id']: t['amount'] for t in tax_details}

            for line in line_details:
                prod_info = product_info_map.get(line['product_id'][0], {})

                # Check top-up status using pre-fetched data
                is_topup = prod_info.get('x_is_topup')
                if not is_topup:
                    for cid in prod_info.get('pos_categ_ids', []):
                        if cat_map.get(cid) == 'Top-ups':
                            is_topup = True
                            break

                vat_rate = 0
                amounts = [tax_map.get(t_id, 0) for t_id in (line.get('tax_ids') or [])]
                if amounts:
                    vat_rate = int(max(amounts))

                # Force vat_rate=0 for top-up products
                if is_topup:
                    vat_rate = 0

                # BEST PRACTICE: Use price_subtotal_incl to ensure the XML matches what the customer actually paid
                total_incl = float(line.get('price_subtotal_incl', line['qty'] * line['price_unit']))
                unit_price_incl = round(total_incl / line['qty'], 2) if line['qty'] != 0 else float(line['price_unit'])

                items.append({
                    'id': f"LINE-{line['id']}",
                    'sku': str(line['product_id'][0]),
                    'description': line['product_id'][1],
                    'quantity': int(line['qty']),
                    'unit_price': unit_price_incl,
                    'total_amount': total_incl,
                    'vat_rate': vat_rate,
                    'currency': 'eur',
                    'item_type': 'wallet_topup' if is_topup else None
                })

        customer_type = customer_info.get('customer_type', 'private') if customer_info else "private"

        xml_message = sender.build_consumption_order_xml(
            items=items,
            customer_id=str(customer_info['id']) if customer_info else None,
            user_id=customer_info.get('x_user_id') if customer_info else None,
            customer_type=customer_type,
            email=customer_info.get('email', '') if customer_info else '',
            is_anonymous=is_anonymous)

        order_id = order['id']
        ok_consumption = sender.send_typed_message('consumption_order', xml_message, record_id=order_id)
        correlation_id = ET.fromstring(xml_message).findtext('.//message_id')

        payment_ids = order.get('payment_ids', [])
        is_badge_wallet, wallet_paid_amount = self._get_wallet_payment_amount(payment_ids)
        ok_wallet = True

        if is_badge_wallet and customer_info and not order.get('x_wallet_updated'):
            # BEST PRACTICE: Use action_process_wallet_payment for atomic balance updates
            try:
                new_balance = self.models.execute_kw(
                    self.odoo_db, self.odoo_uid, self.odoo_pass,
                    'pos.order', 'action_process_wallet_payment',
                    [order_id, customer_info['id'], wallet_paid_amount]
                )
                wallet_xml = sender.build_wallet_balance_update_xml(customer_info.get('x_user_id'), new_balance)
                ok_wallet = sender.send_typed_message('wallet_balance_update', wallet_xml, record_id=order_id)
            except Exception as e:
                logger.error(f"❌ Atomic wallet update failed for order {order_id}: {e}")
                ok_wallet = False

        payment_xml = sender.build_payment_registered_xml(
            payment_context="consumption",
            invoice_status="paid",
            amount_paid=float(order.get('amount_total', 0.0)),
            due_date=order.get('create_date', '').split(" ")[0] if order.get('create_date') else "1970-01-01",
            trx_id=str(order['id']),
            payment_method="on_site",
            user_id=customer_info.get('x_user_id') if customer_info else None,
            correlation_id=correlation_id
        )
        ok_payment = sender.send_typed_message('payment_registered_consumption', payment_xml, record_id=order_id)
        payment_msg_id = ET.fromstring(payment_xml).findtext('.//message_id')

        # NEW: Trigger invoice_request if order is invoiced in Odoo
        ok_invoice = True
        if order.get('account_move') and not is_anonymous and customer_info:
            logger.info(f"🧾 Order {order_id} is invoiced — triggering invoice_request")

            country_code = customer_info.get('country_code', '')

            inv_data = {
                'name': customer_info.get('name'),
                'email': customer_info.get('email'),
                'address': {
                    'street': customer_info.get('street', ''),
                    'city': customer_info.get('city', ''),
                    'zip': customer_info.get('zip', ''),
                    'country': country_code
                },
                'vat_number': customer_info.get('vat', '')
            }
            invoice_xml = sender.build_invoice_request_xml(
                user_id=customer_info.get('x_user_id'),
                invoice_data=inv_data,
                correlation_id=str(correlation_id) if correlation_id else ""
            )
            ok_invoice = sender.send_typed_message('invoice_request', invoice_xml, record_id=order_id)

        return (ok_consumption and ok_payment and ok_wallet and ok_invoice), payment_msg_id

    def poll_badge_assignments(self):
        """
        BEST PRACTICE: Detect when a partner is assigned a badge in Odoo
        and send the Flow 2 (badge_assigned) message to CRM.
        """
        try:
            buffered_ids = sender.get_buffered_record_ids(model="res.partner")

            # Search for partners with a badge that hasn't been reported yet
            partner_ids = self.models.execute_kw(
                self.odoo_db, self.odoo_uid, self.odoo_pass,
                'res.partner', 'search',
                [[['x_badge_id', '!=', False],
                  ['x_badge_sent', '=', False],
                  ['x_user_id', '!=', False]]]
            )

            if buffered_ids:
                partner_ids = [pid for pid in partner_ids if pid not in buffered_ids]

            if not partner_ids:
                return

            partners = self.models.execute_kw(
                self.odoo_db, self.odoo_uid, self.odoo_pass,
                'res.partner', 'read',
                [partner_ids, ['id', 'x_badge_id', 'x_user_id']]
            )

            success_ids = []
            for p in partners:
                try:
                    badge_id = p['x_badge_id']
                    user_id = p['x_user_id']
                    logger.info(f"🏷️ Badge {badge_id} assigned to user {user_id} — sending badge_assigned")

                    badge_xml = sender.build_badge_assigned_xml(badge_id, user_id)
                    if sender.send_typed_message('badge_assigned', badge_xml, record_id=p['id'], model="res.partner"):
                        success_ids.append(p['id'])
                except sender.XSDValidationError as ve:
                    logger.error(f"❌ XSD Validation error for badge assignment (Partner {p['id']}): {ve}")
                    try:
                        self.models.execute_kw(
                            self.odoo_db, self.odoo_uid, self.odoo_pass,
                            'res.partner', 'write',
                            [[p['id']], {
                                'x_badge_sent': True,
                                'x_rabbitmq_error': f"Validation failed: {ve}"
                            }]
                        )
                    except Exception:
                        pass
                except Exception as e:
                    logger.error(f"❌ Error processing badge assignment for partner {p['id']}: {e}")

            if success_ids:
                self.models.execute_kw(
                    self.odoo_db, self.odoo_uid, self.odoo_pass,
                    'res.partner', 'write',
                    [success_ids, {'x_badge_sent': True}]
                )

        except Exception as e:
            logger.error(f"❌ Error in poll_badge_assignments: {e}")

    def poll(self, interval=5):
        """Run the polling loop indefinitely."""
        logger.info(f"Order Poller started (interval: {interval}s)")
        reconnect_counter = 0
        reconnect_interval = 30

        while True:
            try:
                # Flush the outbox buffer roughly every 30 seconds
                reconnect_counter += 1
                if reconnect_counter >= reconnect_interval / interval:
                    flushed_records = sender.flush_buffer()
                    if flushed_records:
                        self._mark_records_sent(flushed_records)
                    reconnect_counter = 0

                # Poll for orders
                orders = self.get_pending_orders()

                # Pre-fetch country data for all partners in the fetched orders
                partner_ids = list(set([o['partner_id'][0] for o in orders if o['partner_id']]))
                country_map = {}
                if partner_ids:
                    partners = self.models.execute_kw(
                        self.odoo_db, self.odoo_uid, self.odoo_pass,
                        'res.partner', 'read',
                        [partner_ids, ['country_id']]
                    )
                    country_ids = list(set([p['country_id'][0] for p in partners if p.get('country_id')]))
                    if country_ids:
                        countries = self.models.execute_kw(
                            self.odoo_db, self.odoo_uid, self.odoo_pass,
                            'res.country', 'read',
                            [country_ids, ['id', 'code']]
                        )
                        country_map = {c['id']: c.get('code', '').lower() for c in countries}

                for order in orders:
                    self.process_order(order, country_map=country_map)

                # Poll for badge assignments
                self.poll_badge_assignments()

                time.sleep(interval)

            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}")
                time.sleep(interval)

    def _mark_records_sent(self, records: list[tuple[str, int]]) -> None:
        """Mark records as sent after buffer flush (handles multiple models)."""
        model_to_ids = collections.defaultdict(list)
        for model, record_id in records:
            model_to_ids[model].append(record_id)

        for model, ids in model_to_ids.items():
            unique_ids = list(set(ids))
            field = 'x_rabbitmq_sent' if model == 'pos.order' else 'x_badge_sent'
            try:
                self.models.execute_kw(
                    self.odoo_db, self.odoo_uid, self.odoo_pass,
                    model, 'write',
                    [unique_ids, {field: True}]
                )
                logger.info(f"✅ Marked {len(unique_ids)} {model} records as sent after flush")
            except Exception as e:
                logger.warning(f"⚠️  Could not mark {model} records as sent after flush: {e}")


def main():
    poller = OrderPoller()
    if not poller.connect_odoo():
        return
    poller.poll(interval=5)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    main()
