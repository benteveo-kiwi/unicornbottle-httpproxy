#!/usr/bin/env python
import pika
import uuid
import time

POLL_INTERVAL = 0.1

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
        # TODO: add multiple concurrent call handling?
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

        while self.response is None:
            # TODO: add sleep here.
            # TODO: add timeout.

            time.sleep(POLL_INTERVAL)
            self.connection.process_data_events()

        return int(self.response)


fibonacci_rpc = FibonacciRpcClient()

import random
nb = random.randint(1, 30)
print(" [x] Requesting fib(%s)" % (nb,))
response = fibonacci_rpc.call(nb)
print(" [.] Got %r" % response)
