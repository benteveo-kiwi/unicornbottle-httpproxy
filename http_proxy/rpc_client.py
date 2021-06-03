#!/usr/bin/env python
from h11._receivebuffer import ReceiveBuffer
from http_proxy import rabbitmq
from io import BytesIO
from mitmproxy.net.http import http1
from mitmproxy.net.http.http1 import assemble
from mitmproxy.net.http.http1.read import read_response_head
from mitmproxy.script import concurrent
from typing import Dict, Optional, Any
import base64
import json
import mitmproxy
import pika
import sys
import time
import uuid

# notes:
# https://stackoverflow.com/questions/28626213/mitm-proxy-getting-entire-request-and-response-string
# https://stackoverflow.com/questions/65553910/how-to-simulate-timeout-in-mitmproxy-addon

PROCESS_TIME_LIMIT = 15

class Request(object):
    def __init__(self, host:str, port:int, protocol:str, bytes:bytes) -> None:
        self.host = host
        self.port = port
        self.protocol = protocol
        self.bytes = base64.b64encode(bytes).decode('ascii')

    def toJSON(self) -> str:
        data = self.__dict__
        return json.dumps(data)

class TimeoutException(Exception):
    pass

class AlreadyCalledException(Exception):
    pass

class HTTPProxyClient(object):
    """
    This class handles sending HTTP connections to RabbitMQ, where they are
    picked up by server processes running on worker hosts. Note that one
    instance of this class must be instantiated per thread as it is certainly
    not thread-safe.
    """

    def __init__(self, connection : pika.BlockingConnection) -> None:
        """
        Connect to RabbitMQ. Creating a new connection per thread is OK per Pika's author 
        @see: https://github.com/pika/pika/issues/828#issuecomment-357773396
        Args:
            connection: a BlockingConnection instance.
        """
        self.called_already = False
        self.connection = connection
        self.channel = self.connection.channel()
        self.response : Optional[bytes] = None

        # Create a queue for handling the responses.
        result = self.channel.queue_declare(queue='', exclusive=True)
        self.callback_queue = result.method.queue
        self.channel.basic_consume(
            queue=self.callback_queue,
            on_message_callback=self.on_response,
            auto_ack=True)

    def on_response(self, ch : Any, method : Any, props : pika.spec.BasicProperties, body : bytes) -> None:
        """
        Gets called when a response is issued as per the RPC pattern.

        Args: 
            see https://pika.readthedocs.io/en/stable/modules/channel.html#pika.channel.Channel.basic_consume

        See:
            https://www.rabbitmq.com/tutorials/tutorial-six-python.html
        """
        if self.corr_id == props.correlation_id:
            self.response = body

    def call(self, message_body : bytes) -> bytes:
        """
        Handles writing to queue, polling until a response is received and timeouts.

        Args:
            message_body: A JSON serialised `Request` Object.
            The RPC response, as bytes.
        Raises:
            TimeoutException: PROCESS_TIME_LIMIT exceeded, request timeout.
        """

        if self.called_already:
            raise AlreadyCalledException()
        else:
            self.called_already = True

        self.response = None

        self.corr_id = str(uuid.uuid4())
        self.channel.basic_publish(
            exchange='',
            routing_key='rpc_queue',
            properties=pika.BasicProperties(
                reply_to=self.callback_queue,
                correlation_id=self.corr_id,
            ),
            body=message_body)

        self.connection.process_data_events(time_limit=PROCESS_TIME_LIMIT)

        self.connection.close()

        if not self.response:
            raise TimeoutException

        return self.response

class HTTPProxyAddon(object):
    """
    Handles integration with mitmproxy.
    """

    @concurrent # type: ignore
    def request(self, flow: mitmproxy.http.HTTPFlow ) -> None:
        """
        Main mitmproxy entry point. This function gets called on each request
        received after mitmproxy handles all the underlying HTTP shenanigans.

        For more documentation, you can run the following command:

        pydoc3 mitmproxy.http
        pydoc3 mitmproxy.net.http.request
        """
        connection = rabbitmq.new_connection()
        http_proxy_client = HTTPProxyClient(connection)

        self._request(http_proxy_client, flow)

    def get_raw_request(self, flow : mitmproxy.http.HTTPFlow) -> bytes:
        """
        Obtains the assembled raw bytes required for sending through a socket.

        Args:
            flow: https://docs.mitmproxy.org/dev/api/mitmproxy/http.html
        """
        request = flow.request.copy()
        request.decode(strict=False)
        raw_request : bytes = assemble.assemble_request(request)
        
        return raw_request

    def parse_response(self, request : mitmproxy.net.http.Request, response : bytes) -> mitmproxy.net.http.Response:
        response_file = BytesIO(response)
        response = http1.read_response(response_file, request)
        return response

    def _request(self, http_proxy_client : HTTPProxyClient, flow : mitmproxy.http.HTTPFlow) -> None:
        """
        Internal method to facilitate dependency injection for testing.

        Args:
            http_proxy_client: Instance of HTTPProxyClient.
            flow: https://docs.mitmproxy.org/dev/api/mitmproxy/http.html
        """

        mitmproxy_req = flow.request

        raw_request = self.get_raw_request(flow)

        req = Request(mitmproxy_req.host, mitmproxy_req.port, mitmproxy_req.scheme, raw_request)
        response_bytes = http_proxy_client.call(req.toJSON().encode())

        flow.response = self.parse_response(request, response_bytes)
