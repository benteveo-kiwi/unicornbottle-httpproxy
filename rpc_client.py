#!/usr/bin/env python
import pika
import sys
import time
import uuid

# notes:
# https://stackoverflow.com/questions/28626213/mitm-proxy-getting-entire-request-and-response-string
# https://stackoverflow.com/questions/65553910/how-to-simulate-timeout-in-mitmproxy-addon

PROCESS_TIME_LIMIT = 15

class TimeoutException(Exception):
    pass

class HTTPProxyClient(object):
    """
    This class handles sending HTTP connections to RabbitMQ, where they are
    picked up by server processes running on worker hosts. Note that one
    instance of this class must be instantiated per thread as it is certainly
    not thread-safe.
    """

    def __init__(self, connection):
        """
        Connect to RabbitMQ. Creating a new connection per thread is OK per Pika's author 
        @see: https://github.com/pika/pika/issues/828#issuecomment-357773396
        Args:
            connection: a BlockingConnection instance.
        """
        self.connection = connection
        self.channel = self.connection.channel()
        self.response = None

        # Create a queue for handling the responses.
        result = self.channel.queue_declare(queue='', exclusive=True)
        self.callback_queue = result.method.queue
        self.channel.basic_consume(
            queue=self.callback_queue,
            on_message_callback=self.on_response,
            auto_ack=True)

    def on_response(self, ch, method, props, body):
        """
        Gets called when a response is issued as per the RPC pattern.

        Args: 
            see https://pika.readthedocs.io/en/stable/modules/channel.html#pika.channel.Channel.basic_consume

        See:
            https://www.rabbitmq.com/tutorials/tutorial-six-python.html
        """
        if self.corr_id == props.correlation_id:
            self.response = body

    def call(self, n):
        """
        Handles writing to queue, polling until a response is received and timeouts.

        Return:
            The RPC response.
        Raises:
            TimeoutException: PROCESS_TIME_LIMIT exceeded, request timeout.
        """
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

        if not self.response:
            raise TimeoutException

        return self.response


if __name__ == "__main__":
    credentials = pika.PlainCredentials('httpproxy', 'SHJfakkjawkjhfkawjaw')
    connection = pika.BlockingConnection(
        pika.ConnectionParameters('localhost', 5672, '/', credentials=credentials))

    fibonacci_rpc = HTTPProxyClient(connection)

    nb = sys.argv[1]
    print(" [x] Requesting fib(%s)" % (nb,))
    response = fibonacci_rpc.call(nb)
    if response:
        print(" [.] Got %r" % response)
    else:
        print(" [-] Timeout :(")
