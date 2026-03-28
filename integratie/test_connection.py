#!/usr/bin/env python3
"""Test RabbitMQ connection with provided credentials"""
import pika

RABBIT_HOST = "integrationproject-2526s2-dag01.westeurope.cloudapp.azure.com"
RABBIT_USER = "kassa_rabbitmq"
RABBIT_PASS = "RCFD2Qgr8vkhC1wjGwR$"
RABBIT_PORT = 5672

print("🔗 Testing RabbitMQ connection...")
print(f"   Host: {RABBIT_HOST}:{RABBIT_PORT}")
print(f"   User: {RABBIT_USER}")

try:
    creds = pika.PlainCredentials(RABBIT_USER, RABBIT_PASS)
    params = pika.ConnectionParameters(
        host=RABBIT_HOST,
        port=RABBIT_PORT,
        credentials=creds,
        connection_attempts=1,
        retry_delay=0,
    )
    
    connection = pika.BlockingConnection(params)
    channel = connection.channel()
    
    print("\n✅ CONNECTION SUCCESSFUL!")
    print(f"   Channel created: {channel}")
    
    # Verify exchange exists or create it
    try:
        channel.exchange_declare(
            exchange='kassa.exchange',
            exchange_type='topic',
            passive=True  # Just check if exists
        )
        print("   ✅ Exchange 'kassa.exchange' exists")
    except:
        print("   ⚠️  Exchange needs to be created")
    
    connection.close()
    print("\n🎉 RabbitMQ is working and accessible!")
    
except Exception as e:
    print(f"\n❌ Connection failed: {e}")
    print(f"\n   Error type: {type(e).__name__}")
    import traceback
    traceback.print_exc()
