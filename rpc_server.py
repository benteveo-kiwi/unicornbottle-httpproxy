#!/usr/bin/env python
import pika

# SjaiowfjoiawfojiAWFAWAWFAFWafw

credentials = pika.PlainCredentials('httpproxy', 'SHJfakkjawkjhfkawjaw')
connection = pika.BlockingConnection(
    pika.ConnectionParameters('localhost', 5672, '/', credentials=credentials))

channel = connection.channel()

channel.queue_declare(queue='rpc_queue')


def fib(n):
    if n == 0:
        return 0
    elif n == 1:
        return 1
    else:
        return fib(n - 1) + fib(n - 2)


def on_request(ch, method, props, body):
    n = int(body)

    ch.basic_ack(delivery_tag=method.delivery_tag)

    print(" [.] fib(%s)" % n)
    response = fib(n)

    ch.basic_publish(exchange='',
                     routing_key=props.reply_to,
                     properties=pika.BasicProperties(correlation_id = \
                                                         props.correlation_id),
                     body=str(response))


channel.basic_qos(prefetch_count=1)
channel.basic_consume(queue='rpc_queue', on_message_callback=on_request)

print(" [x] Awaiting RPC requests")
channel.start_consuming()
