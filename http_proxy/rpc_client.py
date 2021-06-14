from http_proxy import rabbitmq, log
from http_proxy.models import Request, Response
from io import BytesIO
from mitmproxy.script import concurrent
from typing import Dict, Optional, Any
import base64
import mitmproxy
import pika
import sys
import time
import uuid

# https://www.postgresql.org/docs/8.3/wal-async-commit.html
# https://www.stevenrombauts.be/2019/01/run-multiple-instances-of-the-same-systemd-unit/
# https://medium.com/@benmorel/creating-a-linux-service-with-systemd-611b5c8b91d6

PROCESS_TIME_LIMIT = 15
logger = log.getLogger("rpc_client", server=False)

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

        if self.response is None:
            raise TimeoutException

        return self.response

class HTTPProxyAddon(object):
    """
    Handles integration with mitmproxy.
    """

    def __init__(self):
        logger.info("mitmproxy addon started.")

    @concurrent # type: ignore
    def request(self, flow: mitmproxy.http.HTTPFlow) -> None:
        """
        Main mitmproxy entry point. This function gets called on each request
        received after mitmproxy handles all the underlying HTTP shenanigans.

        For more documentation, you can run the following command:

        pydoc3 mitmproxy.http
        pydoc3 mitmproxy.net.http.request
        """
        try:
            connection = rabbitmq.new_connection()
            http_proxy_client = HTTPProxyClient(connection)

            self._request(http_proxy_client, flow)
        except:
            logger.exception("Unhandled exception in request thread.", exc_info=True)
            flow.response = mitmproxy.http.HTTPResponse.make(502, b"HTTP Proxy unhandled exception")
        finally:
            connection.close()

    def _request(self, http_proxy_client : HTTPProxyClient, flow : mitmproxy.http.HTTPFlow) -> None:
        """
        Internal method to facilitate dependency injection for testing.

        Args:
            http_proxy_client: Instance of HTTPProxyClient.
            flow: https://docs.mitmproxy.org/dev/api/mitmproxy/http.html
        """

        req = Request(flow.request.get_state())
        response_json = http_proxy_client.call(req.toJSON().encode('utf-8'))

        flow.response = Response.fromJSON(response_json).toMITM()
        logger.info("Successfully handled request to %s. Response %s" % (flow.request.pretty_url, flow.response))

