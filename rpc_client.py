#!/usr/bin/env python
from mitmproxy.net.http.http1 import assemble
from mitmproxy.script import concurrent
import base64
import json
import pika
import rabbitmq
import sys
import time
import uuid

# notes:
# https://stackoverflow.com/questions/28626213/mitm-proxy-getting-entire-request-and-response-string
# https://stackoverflow.com/questions/65553910/how-to-simulate-timeout-in-mitmproxy-addon

PROCESS_TIME_LIMIT = 15

class Request(object):
    def __init__(self, host, port, protocol, bytes):
        self.host = host
        self.port = port
        self.protocol = protocol
        self.bytes = base64.b64encode(bytes).decode('ascii')

    def toJSON(self):
        return json.dumps(self.__dict__)

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

        self.connection.close()

        if not self.response:
            raise TimeoutException

        return self.response

class HTTPProxyAddon(object):
    """
    Handles integration with mitmproxy.
    """

    @concurrent
    def request(self, flow):
        """
        Main mitmproxy entry point. This function gets called on each request
        received after mitmproxy handles all the underlying HTTP shenanigans.

        For more documentation, you can run the following command:

        pydoc3 mitmproxy.http
        pydoc3 mitmproxy.net.http.request
        """
        connection = rabbitmq.new_connection()
        http_proxy_client = HTTPProxyClient(connection)

        return self._request(http_proxy_client, flow)

    def get_raw_request(self, flow):
        """
        Obtains the assembled raw bytes required for sending through a socket.

        Args:
            flow: https://docs.mitmproxy.org/dev/api/mitmproxy/http.html
        """
        request = flow.request.copy()
        request.decode(strict=False)
        raw_request = assemble.assemble_request(request)
        
        return raw_request

    def _request(self, http_proxy_client, flow):
        """
        Internal method to facilitate dependency injection for testing.

        Args:
            http_proxy_client: Instance of HTTPProxyClient.
            flow: https://docs.mitmproxy.org/dev/api/mitmproxy/http.html
        """

        mitmproxy_req = flow.request

        raw_request = self.get_raw_request(flow)

        req = Request(mitmproxy_req.host, mitmproxy_req.port, mitmproxy_req.scheme, raw_request)
        response = http_proxy_client.call(req.toJSON())

        try:
            print(" [.] Got %r" % response)
        except TimeoutException:
            print(" [-] Timeout :(")

addons = [
    HTTPProxyAddon()
]
