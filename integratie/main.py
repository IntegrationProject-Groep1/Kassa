import time
import sys
import threading
from order_poller import OrderPoller
import sender

def main():
    print("🚀 Kassa Integration Service Started", flush=True)
    print("📋 Flow: Odoo POS → Order Poller → Sender → RabbitMQ (+ outbox fallback)", flush=True)
    
    # Initialize and start Order Poller
    print("📦 Starting Order Poller...", flush=True)
    poller = OrderPoller()
    
    if not poller.connect_odoo():
        print("❌ Failed to connect to Odoo", flush=True)
        sys.exit(1)
    
    # Try to flush any buffered messages from previous runs
    print("🔄 Checking for buffered messages...", flush=True)
    sender.flush_buffer()
    
    print("✅ Order Poller initialized successfully", flush=True)
    print("✅ All services running. Press Ctrl+C to stop.", flush=True)
    
    # Run poller in a thread
    poller_thread = threading.Thread(target=poller.poll, kwargs={'interval': 5})
    poller_thread.daemon = True
    poller_thread.start()
    
    # Keep main thread alive
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("\n🛑 Service shutdown requested...", flush=True)
        sys.exit(0)

if __name__ == "__main__":
    main()



