import pika

def test_vhost(vhost):
    credentials = pika.PlainCredentials('kassa_rabbitmq', 'RCFD2Qgr8vkhC1wjGwR$')
    params = pika.ConnectionParameters(
        host='integrationproject-2526s2-dag01.westeurope.cloudapp.azure.com',
        port=30000,
        virtual_host=vhost,
        credentials=credentials
    )
    try:
        conn = pika.BlockingConnection(params)
        print(f"Success with vhost: {vhost}")
        conn.close()
    except Exception as e:
        print(f"Failed with vhost {vhost}: {e}")

for vhost in ['/', '/kassa', 'kassa', '/kassa_rabbitmq', 'kassa_rabbitmq']:
    test_vhost(vhost)
