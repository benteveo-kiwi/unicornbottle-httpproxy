#!/usr/bin/env python
import pika
import uuid
import time

PROCESS_TIME_LIMIT = 15

class FibonacciRpcClient(object):

    def __init__(self):
        credentials = pika.PlainCredentials('httpproxy', 'SHJfakkjawkjhfkawjaw')
        self.connection = pika.BlockingConnection(
            pika.ConnectionParameters('localhost', 5672, '/', credentials=credentials))

        self.channel = self.connection.channel()

        result = self.channel.queue_declare(queue='', exclusive=True)
        self.callback_queue = result.method.queue

        self.channel.basic_consume(
            queue=self.callback_queue,
            on_message_callback=self.on_response,
            auto_ack=True)

    def on_response(self, ch, method, props, body):
        if self.corr_id == props.correlation_id:
            self.response = body

    def call(self, n):
        self.response = None
        self.corr_id = str(uuid.uuid4())
        self.channel.basic_publish(
            exchange='',
            routing_key='rpc_queue',
            properties=pika.BasicProperties(
                reply_to=self.callback_queue,
                correlation_id=self.corr_id,
            ),
            body=str(n))

        self.connection.process_data_events(time_limit=PROCESS_TIME_LIMIT)

        return self.response


fibonacci_rpc = FibonacciRpcClient()

import sys
nb = sys.argv[1]
print(" [x] Requesting fib(%s)" % (nb,))
response = fibonacci_rpc.call(nb)
if response:
    print(" [.] Got %r" % response)
else:
    print(" [-] Timeout :(")
