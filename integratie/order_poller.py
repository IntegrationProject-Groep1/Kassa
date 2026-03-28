"""
Order Poller — Haalt afgeronde bestellingen uit Odoo POS
en stuurt ze naar RabbitMQ voor CRM verwerking
Met outbox fallback voor reliability
"""

import xmlrpc.client
import os
import pika
import time
import logging
import json
from datetime import datetime, timezone
from uuid import uuid4
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom
from pathlib import Path

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class OrderPoller:
    def __init__(self):
        """Initialize Odoo and RabbitMQ connections"""
        self.odoo_url = os.environ.get("ODOO_URL")
        self.odoo_db = os.environ.get("ODOO_DB")
        self.odoo_user = os.environ.get("ODOO_USER")
        self.odoo_pass = os.environ.get("ODOO_PASS")
        
        self.rabbit_host = os.environ.get("RABBIT_HOST")
        self.rabbit_user = os.environ.get("RABBIT_USER")
        self.rabbit_pass = os.environ.get("RABBIT_PASS")
        self.rabbit_exchange = os.environ.get("RABBIT_EXCHANGE")
        
        self.odoo_uid = None
        self.rabbit_channel = None
        self.rabbit_connection = None
        self.rabbit_available = False
        self.processed_orders = set()
        
        # Outbox folder setup
        self.outbox_dir = Path("/app/outbox")
        self.outbox_dir.mkdir(exist_ok=True)
        
    def connect_odoo(self):
        """Authenticate with Odoo"""
        try:
            common = xmlrpc.client.ServerProxy(f'{self.odoo_url}/xmlrpc/2/common', allow_none=True)
            self.odoo_uid = common.authenticate(self.odoo_db, self.odoo_user, self.odoo_pass, {})
            
            if self.odoo_uid:
                logger.info("✅ Odoo connection established")
                return True
            else:
                logger.error("❌ Odoo authentication failed")
                return False
        except Exception as e:
            logger.error(f"❌ Odoo connection error: {e}")
            return False
    
    def connect_rabbitmq(self):
        """Connect to RabbitMQ (non-blocking)"""
        try:
            credentials = pika.PlainCredentials(self.rabbit_user, self.rabbit_pass)
            self.rabbit_connection = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host=self.rabbit_host,
                    credentials=credentials,
                    heartbeat=600,
                    blocked_connection_timeout=10,  # Shorter timeout
                    connection_attempts=1  # Only try once
                )
            )
            self.rabbit_channel = self.rabbit_connection.channel()
            
            # Declare exchange
            self.rabbit_channel.exchange_declare(
                exchange=self.rabbit_exchange,
                exchange_type='direct',
                durable=True
            )
            
            self.rabbit_available = True
            logger.info("✅ RabbitMQ connection established")
            return True
        except Exception as e:
            self.rabbit_available = False
            logger.warning(f"⚠️ RabbitMQ connection failed: {e}")
            logger.warning("   → Will use outbox folder until RabbitMQ is available")
            return False
    
    def try_reconnect_rabbitmq(self):
        """Periodic reconnection attempt"""
        if not self.rabbit_available:
            logger.info("🔄 Attempting to reconnect to RabbitMQ...")
            self.connect_rabbitmq()
    
    def get_pending_orders(self):
        """Fetch completed orders from Odoo POS that haven't been sent yet"""
        try:
            models = xmlrpc.client.ServerProxy(f'{self.odoo_url}/xmlrpc/2/object', allow_none=True)
            
            # Search for orders with state 'paid' or 'done'
            order_ids = models.execute_kw(
                self.odoo_db, self.odoo_uid, self.odoo_pass,
                'pos.order', 'search',
                [[['state', '=', 'paid']]]
            )
            
            if not order_ids:
                return []
            
            # Read order details
            orders = models.execute_kw(
                self.odoo_db, self.odoo_uid, self.odoo_pass,
                'pos.order', 'read',
                [order_ids, ['id', 'name', 'partner_id', 'lines', 'amount_total', 'amount_tax', 'create_date', 'session_id']]
            )
            
            return orders
        except Exception as e:
            logger.error(f"❌ Error fetching orders: {e}")
            return []
    
    def get_order_lines(self, line_ids):
        """Fetch detailed order line information"""
        try:
            models = xmlrpc.client.ServerProxy(f'{self.odoo_url}/xmlrpc/2/object', allow_none=True)
            
            lines = models.execute_kw(
                self.odoo_db, self.odoo_uid, self.odoo_pass,
                'pos.order.line', 'read',
                [line_ids, ['product_id', 'qty', 'price_unit', 'price_subtotal', 'tax_ids']]
            )
            
            return lines
        except Exception as e:
            logger.error(f"❌ Error fetching order lines: {e}")
            return []
    
    def get_customer_info(self, partner_id):
        """Fetch customer details from Odoo"""
        if not partner_id:
            return None
        
        try:
            models = xmlrpc.client.ServerProxy(f'{self.odoo_url}/xmlrpc/2/object', allow_none=True)
            
            # partner_id is usually a tuple like (ID, name)
            if isinstance(partner_id, (list, tuple)):
                partner_id = partner_id[0]
            
            customer = models.execute_kw(
                self.odoo_db, self.odoo_uid, self.odoo_pass,
                'res.partner', 'read',
                [partner_id, ['id', 'name', 'email', 'phone', 'street', 'street2', 'city', 'zip', 'country_id', 'company_type']]
            )
            
            return customer[0] if customer else None
        except Exception as e:
            logger.error(f"❌ Error fetching customer info: {e}")
            return None
    
    def build_xml_message(self, order, customer_info=None):
        """Build XML consumption_order message"""
        message = Element('message')
        
        # Header
        header = SubElement(message, 'header')
        SubElement(header, 'message_id').text = str(uuid4())
        SubElement(header, 'type').text = 'consumption_order'
        SubElement(header, 'source').text = 'kassa'
        SubElement(header, 'timestamp').text = datetime.now(timezone.utc).isoformat()
        SubElement(header, 'version').text = '2.0'
        
        # Body
        body = SubElement(message, 'body')
        
        # Anonymous flag
        is_anonymous = customer_info is None
        SubElement(body, 'is_anonymous').text = 'true' if is_anonymous else 'false'
        
        # Order info
        SubElement(body, 'order_id').text = str(order['name'])
        SubElement(body, 'total_amount').text = str(order['amount_total'])
        SubElement(body, 'tax_amount').text = str(order['amount_tax'])
        SubElement(body, 'timestamp').text = order['create_date']
        
        # Customer info (optional)
        if customer_info:
            customer = SubElement(body, 'customer')
            SubElement(customer, 'id').text = str(customer_info['id'])
            SubElement(customer, 'name').text = customer_info['name']
            SubElement(customer, 'email').text = customer_info.get('email', '')
            SubElement(customer, 'company_name').text = customer_info['name']  # Could be enhanced
            SubElement(customer, 'is_company_linked').text = 'true'
        
        # Items
        items = SubElement(body, 'items')
        for line in order['lines']:
            item = SubElement(items, 'item')
            SubElement(item, 'product_id').text = str(line['product_id'][0]) if line['product_id'] else 'UNKNOWN'
            SubElement(item, 'description').text = line['product_id'][1] if line['product_id'] else 'Unknown Product'
            SubElement(item, 'quantity').text = str(int(line['qty']))
            SubElement(item, 'unit_price').text = str(line['price_unit'])
            SubElement(item, 'subtotal').text = str(line['price_subtotal'])
        
        # Pretty print XML
        xml_str = tostring(message, encoding='unicode')
        dom = minidom.parseString(xml_str)
        pretty_xml = dom.toprettyxml()
        
        # Remove XML declaration if present and clean up
        pretty_xml = '\n'.join(line for line in pretty_xml.split('\n') if line.strip() and not line.startswith('<?xml'))
        
        return pretty_xml
    
    def save_to_outbox(self, xml_message, order_id):
        """Save message to outbox folder for later delivery"""
        try:
            filename = f"order_{order_id}_{int(time.time())}.xml"
            filepath = self.outbox_dir / filename
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(xml_message)
            
            logger.info(f"📁 Order {order_id} saved to outbox: {filename}")
            return True
        except Exception as e:
            logger.error(f"❌ Error saving to outbox: {e}")
            return False
    
    def send_to_rabbitmq(self, xml_message, order_id):
        """Publish message to RabbitMQ or save to outbox if unavailable"""
        if not self.rabbit_available:
            logger.warning(f"⚠️ RabbitMQ unavailable - saving order {order_id} to outbox")
            return self.save_to_outbox(xml_message, order_id)
        
        try:
            self.rabbit_channel.basic_publish(
                exchange=self.rabbit_exchange,
                routing_key='pos.payments',
                body=xml_message,
                properties=pika.BasicProperties(
                    content_type='application/xml',
                    delivery_mode=pika.spec.PERSISTENT_DELIVERY_MODE,
                    headers={'order_id': str(order_id)}
                )
            )
            logger.info(f"✅ Order {order_id} sent to RabbitMQ")
            return True
        except Exception as e:
            logger.error(f"❌ RabbitMQ publish failed: {e}")
            logger.warning(f"⚠️ Saving order {order_id} to outbox as fallback")
            return self.save_to_outbox(xml_message, order_id)
    
    def process_outbox(self):
        """Try to send messages from outbox (called periodically)"""
        if not self.rabbit_available:
            return
        
        try:
            xml_files = list(self.outbox_dir.glob("order_*.xml"))
            if not xml_files:
                return
            
            logger.info(f"📤 Processing {len(xml_files)} messages from outbox...")
            
            for filepath in xml_files:
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        xml_message = f.read()
                    
                    # Extract order_id from filename
                    order_id = filepath.stem.split('_')[1]
                    
                    # Try to send
                    self.rabbit_channel.basic_publish(
                        exchange=self.rabbit_exchange,
                        routing_key='pos.payments',
                        body=xml_message,
                        properties=pika.BasicProperties(
                            content_type='application/xml',
                            delivery_mode=pika.spec.PERSISTENT_DELIVERY_MODE,
                        )
                    )
                    
                    # Delete file on success
                    filepath.unlink()
                    logger.info(f"📤 Outbox message {order_id} delivered and removed")
                except Exception as e:
                    logger.error(f"❌ Failed to send outbox message: {e}")
        except Exception as e:
            logger.error(f"❌ Error processing outbox: {e}")
    
    def poll(self, interval=5):
        """Main polling loop"""
        logger.info(f"Order Poller started (interval: {interval}s)")
        reconnect_counter = 0
        reconnect_interval = 30  # Try to reconnect every 30 seconds
        
        while True:
            try:
                # Periodically try to reconnect to RabbitMQ
                reconnect_counter += 1
                if reconnect_counter >= reconnect_interval / interval:
                    self.try_reconnect_rabbitmq()
                    self.process_outbox()
                    reconnect_counter = 0
                
                orders = self.get_pending_orders()
                
                for order in orders:
                    order_id = order['id']
                    
                    # Skip if already processed
                    if order_id in self.processed_orders:
                        continue
                    
                    # Get customer info
                    customer_info = None
                    if order['partner_id']:
                        customer_info = self.get_customer_info(order['partner_id'])
                    
                    # Get order lines
                    if order['lines']:
                        order_lines = self.get_order_lines(order['lines'])
                        order['lines'] = order_lines
                    
                    # Build and send XML
                    xml_message = self.build_xml_message(order, customer_info)
                    
                    status = "ANONYMOUS" if customer_info is None else customer_info['name']
                    
                    if self.send_to_rabbitmq(xml_message, order_id):
                        self.processed_orders.add(order_id)
                        logger.info(f"Order {order_id}: {status}")
                
                time.sleep(interval)
            
            except KeyboardInterrupt:
                logger.info("Order Poller stopped")
                break
            except Exception as e:
                logger.error(f"❌ Polling error: {e}")
                time.sleep(interval)


def main():
    poller = OrderPoller()
    
    if not poller.connect_odoo():
        logger.error("Failed to connect to Odoo")
        return
    
    poller.connect_rabbitmq()  # Non-blocking
    
    logger.info("🚀 Order Poller initialized successfully")
    logger.info(f"   RabbitMQ Status: {'✅ Connected' if poller.rabbit_available else '⚠️ Disconnected (using outbox)'}")
    poller.poll(interval=5)


if __name__ == "__main__":
    main()

